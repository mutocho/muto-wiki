---
title: MySQL 8.0.42 파티션 pruning 캐시 회귀 (Bug #119309)
tags: [dba, mysql, troubleshooting, partitioning, bug]
summary: 8.0.42 회귀 — DEFAULT CURRENT_TIMESTAMP 파티션 키에 prepared INSERT를 재사용하면 경계 통과 후 ERROR 1748. 캐시는 첫 실행 때 생기므로 INSERT 이력이 없는 테이블은 증상이 안 보인다.
sources:
  - "MySQL Bug #119309 — An insert prepared statement fails to write across partitions (https://bugs.mysql.com/bug.php?id=119309, 2026-08-05 확인 / 2026-08-06 재확인)"
  - "자체 재현 테스트 (second-brain session 2026-08-05)"
  - "사내 DB 버그 사례 정리 (2026-08-06) — Reorganize 해소 사례"
category: db운영
status: verified
created: 2026-08-05
updated: 2026-08-15
notion_page_id: "3bdfb969-b8be-8191-9dc1-d1f4ada54d07"
notion_synced: "2026-08-15T22:55:00+0900"
---

> [!tip] 핵심 Takeaway
> - **8.0.42는 증상이 없어도 안전한 게 아니다.** pruning 캐시는 그 테이블에 INSERT가 실제 실행될 때 생기므로, 조용한 테이블은 "안전"이 아니라 "미노출"일 뿐이다. **버그 리포트에 없는 조건이며 자체 재현으로 규명한 이 위키의 고유 자산**
> - **영향 범위 판정 기준을 이렇게 쓴다**: "에러가 났는가"가 아니라 **"조건 3가지(시각 기반 RANGE 파티션 + `DEFAULT CURRENT_TIMESTAMP` + prepared/SP 재사용)를 만족하는 테이블 × 장수 커넥션"**. 조사 스크립트를 이 기준으로 만든다
> - **평소 안 쓰이다 장애 때 처음 쓰이는 테이블(에러 로그류)을 조사에서 빼면 안 된다.** 첫 INSERT에 캐시가 생기고 다음 경계에서 터진다
> - **"고쳤다"고 착각하게 만드는 조치가 둘 있다.** ① **Reorganize는 고침이 아니라 리셋** — 다음 경계에서 재발하므로 "조치 완료"로 종결시키면 안 된다([[verbal-source-verification-policy]]의 대표 사례). ② **파티션을 미리 넉넉히 만들어도 해결되지 않는다** — 문제는 미래 파티션의 부재가 아니라 굳어버린 비트맵이다
> - **사내 문서의 "8.0.41 버그" 표기는 오류다.** 8.0.41은 정상, 8.0.42가 회귀 — 판단이 정반대로 뒤집히는 차이
> - 재현은 경계를 기다리지 말고 `SET TIMESTAMP`으로. **단, 경계 이전 시각 INSERT를 먼저 해서 캐시를 만들어야 한다.** 테스트 인스턴스 전용

# MySQL 8.0.42 파티션 pruning 캐시 회귀 (Bug #119309)

## 증상

타임스탬프 RANGE 파티션 테이블에 **prepared statement로 INSERT**할 때, 파티션 경계를 넘어간 뒤 같은 statement를 재실행하면 실패한다.

```
ERROR 1748 (HY000): Found a row not matching the given partition set
```

- **영향 버전: 8.0.42** — 8.0.41 및 그 이전에는 없던 **회귀**다. 리포터(Ivo Matsuo) 진술: *"I do not see the problem in 8.0.41 or older"*. Oracle(Roy Lyseng)이 `Verified as described`로 확인.
- Bug #119309, 상태 `Verified`, 심각도 S3.

> **사내 문서 정정** — 이 건을 "8.0.41 업스트림 버그"로 적은 자료가 있으나, **8.0.41은 정상이고 8.0.42에서 유입된 회귀**다. 버전 판단을 뒤집는 차이이므로(8.0.41 유지 = 안전, 8.0.42 업그레이드 = 노출) 인용 시 확인할 것.

## 발생 조건

세 가지가 모두 겹칠 때만 발생한다:

1. `RANGE` 파티션 + 파티션 표현식이 시각 기반 (`unix_timestamp(created_timestamp)` 등)
2. 파티션 키 컬럼이 **`DEFAULT CURRENT_TIMESTAMP`** — INSERT 문이 그 컬럼을 명시하지 않고 서버 기본값에 의존
3. **prepared statement 또는 stored procedure를 준비해 두고 재사용** — 리포트에 SP도 명시돼 있다(*"first execution of statement in procedure happens at time point"*). SP 본문의 문장도 내부적으로 준비·캐시되므로 같은 결함을 탄다.

## 원인 — 리포트의 코드 레벨 분석

파티션 프루닝이 **`Sql_cmd_insert_base::prepare_inner()`에서 테이블 락을 잡기 전에 미리 수행**되고, 그 시점의 시각을 기준으로 `partition_info::lock_partitions` 비트맵이 확정된다. **이 비트맵은 재실행 때 갱신되지 않는다.**

- `partition_info::lock_partitions` — prepare 시점에 한 번 계산되고 그대로 재사용됨 (**결함 지점**)
- `partition_info::read_partitions` — 실행마다 정상적으로 재계산됨

시간이 경계를 넘어가면 행은 새 파티션으로 가야 하는데 `lock_partitions`는 과거 파티션 집합을 고정하고 있어, 실제 행과 잠긴 파티션 집합이 어긋나고 서버가 1748로 거부한다.

> **"커넥션 연결 시점"이 아니라 "prepare / 최초 실행 시점"이 기준이다.** 커넥션을 열어만 두고 해당 statement를 아직 실행하지 않았다면 비트맵은 존재하지 않는다(아래 "핵심" 항목).

## 핵심 — 왜 어떤 테이블은 멀쩡해 보이는가

**pruning 캐시는 그 테이블에 INSERT가 실제로 실행될 때 만들어진다. INSERT 이력이 없으면 캐시 자체가 없으므로 경계를 넘어도 정상 INSERT된다.**

자체 재현 테스트로 확인한 사실이며, 버그 리포트가 명시하지 않은 부분이다. 운영에서 다음을 뜻한다:

- **증상이 안 나타난다고 해서 해당 버전이 안전한 게 아니다.** 그 테이블에 트래픽이 없었을 뿐일 수 있다.
- 반대로, **평소 쓰지 않다가 장애 시점에 처음 쓰이는 테이블**(에러 로그류)은 첫 INSERT 시점에 캐시가 생기고, 그 커넥션이 오래 살아 있으면 다음 경계에서 터진다. 조사 대상에서 빼면 안 된다.
- 영향 범위 판정은 "에러가 났는가"가 아니라 **"조건 3가지를 만족하는 테이블 + 장수 커넥션의 prepared statement 재사용 여부"**로 해야 한다.

## 리포트의 최소 재현 케이스

```sql
CREATE TABLE `test_table` (
  `id` int NOT NULL,
  `created_timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`, `created_timestamp`)
) ENGINE=InnoDB
PARTITION BY RANGE (unix_timestamp(`created_timestamp`))
(PARTITION pMIN VALUES LESS THAN (1762341952) ENGINE = InnoDB,
 PARTITION pMAX VALUES LESS THAN MAXVALUE ENGINE = InnoDB);

PREPARE stmt FROM 'INSERT INTO test_table (id) VALUES (?)';
SET @id = 1;
EXECUTE stmt USING @id;    -- 정상. 이 시점에 lock_partitions 확정

-- 파티션 경계 시각을 지난 뒤
EXECUTE stmt USING @id;    -- ERROR 1748
```

`INSERT`가 `created_timestamp`를 **명시하지 않는다**는 점이 핵심이다 — 값이 `DEFAULT CURRENT_TIMESTAMP`로 채워지기 때문에 프루닝이 prepare 시점 시각에 묶인다.

## 재현 방법 — 경계를 기다리지 않는다

`SET TIMESTAMP`으로 세션의 현재 시각을 조작해 즉시 재현한다. **순서가 핵심이다 — 먼저 경계 이전 시각으로 INSERT해 pruning 캐시를 만들어야 한다.**

```sql
-- 1) 경계 이전 시각으로 세션 시계를 맞추고 INSERT → 이 시점에 pruning 캐시 형성
SET TIMESTAMP = UNIX_TIMESTAMP('2026-08-01 00:01:50');
-- (prepared statement 준비 후 실행)

-- 2) 경계를 넘긴 시각으로 이동
SET TIMESTAMP = UNIX_TIMESTAMP('2026-09-01 00:01:50');

-- 3) 같은 prepared statement 재실행 → ERROR 1748
```

1)을 건너뛰고 2)부터 시작하면 캐시가 없어 **정상 INSERT되고 재현에 실패한다.** 이게 위 "왜 멀쩡해 보이는가"와 같은 현상이다.

> `SET TIMESTAMP`은 `NOW()`·`CURRENT_TIMESTAMP`·`DEFAULT CURRENT_TIMESTAMP`에 적용되지만 **`SYSDATE()`에는 적용되지 않는다**(`sysdate-is-now` 옵션 미사용 시). 파티션 표현식이나 컬럼 기본값이 `SYSDATE()`를 쓰면 이 방법으로 재현되지 않는다.
> `SET TIMESTAMP`은 복제가 시각을 재현할 때 쓰는 변수다. **테스트 인스턴스에서만 쓰고 운영 세션에서는 쓰지 않는다.**

## 수정 상태

- **Dmitry Lenev 패치 기여** — `DEFAULT CURRENT_TIMESTAMP`에 의존하는 파티션 표현식은 `prepare_inner()`에서의 프루닝을 **미루고 `Sql_cmd_insert_values::execute_inner()` 시점에 수행**하도록 바꾼다. 즉 실행마다 재계산되는 `read_partitions`를 쓰고, 굳어버리는 `lock_partitions`에 의존하지 않는다. prepared statement 파라미터를 다루는 기존 방식과 같은 접근이다.
- **8.0.45, 8.4.x, 9.x 브랜치 적용 대상** — 2026-08-06 확인 시점 기준 **통합 전(패치 기여 단계)**.

## 대응

### 근본 대책

1. **버전 회피.** 8.0.42를 쓰지 않는다. 8.0.41 이하 또는 수정이 반영된 릴리스(8.0.45+/8.4/9.x)로 간다. 8.0/8.4가 LTS 라인 — [[mysql-operations]]의 버전 이정표 참조.
2. **INSERT에서 파티션 키 값을 명시적으로 넘긴다.** 파라미터로 전달되는 값은 프루닝이 이미 실행 시점 기준으로 처리되므로 결함 경로를 타지 않는다. `INSERT INTO t (id) VALUES (?)` → `INSERT INTO t (id, created_timestamp) VALUES (?, NOW())` 형태. 애플리케이션 변경이 가능한 경우 가장 확실한 회피다.^[inferred — 리포트의 수정 전략에서 도출, 미검증]

### 증상 해소 (재발 방지 아님)

3. **테이블 Reorganize / 파티션 재구성** — 현장에서 확인된 해소 방법. DDL이 테이블 정의 버전을 올려 열려 있던 TABLE 인스턴스가 닫히고, `partition_info`가 새로 만들어지면서 굳은 `lock_partitions` 비트맵이 사라진다.^[inferred — 동작 기제는 도출, 리포트에 기재 없음]

   > **주의: 이건 고침이 아니라 리셋이다.** 새로 준비된 statement는 그 시점 시각으로 다시 비트맵을 굳히므로, **다음 파티션 경계에서 같은 증상이 재발한다.** 파티션 추가 배치가 경계마다 도는 환경이면 결과적으로 매번 리셋되어 "해결된 것처럼" 보이지만, 경계 통과 시각과 배치 실행 시각 사이의 창에서는 계속 1748이 난다.

4. **prepared statement 재준비 / 커넥션 재수립.** 경계 통과 후 `DEALLOCATE PREPARE` → 재준비, 또는 커넥션 풀의 **최대 수명(max lifetime)을 파티션 주기보다 짧게** 설정. 3번과 마찬가지로 노출 창을 줄이는 완화책이다.

### 하면 안 되는 것 / 오해

5. **파티션을 미리 넉넉히 만들어도 해결되지 않는다.** 미래 파티션의 존재 여부가 아니라, 굳어버린 비트맵이 과거 파티션 집합을 가리키는 게 문제다.
6. 영향 조사에서 **에러 로그성 저빈도 테이블을 제외하지 않는다** (위 "핵심" 항목).

## 확인 필요

- `FLUSH TABLES`만으로 캐시가 무효화되는지 미검증 — Reorganize와 같은 기제라면 동작해야 하고 훨씬 가볍다.^[inferred]
- 파티션 키 값을 애플리케이션이 명시하는 경우 실제로 회피되는지 미검증 (대응 2번).^[inferred]
- Aurora MySQL 3(8.0 호환) 해당 여부 미확인 — 8.0.42 상당 마이너 버전이 어느 Aurora 릴리스에 매핑되는지 확인 필요.
- Reorganize 후 다음 경계에서 재발하는지 실측 미확인 — 원인 설명상 재발해야 한다.^[inferred]

## Related

- [[mysql-operations|MySQL/Aurora MySQL 운영 지식]]
- [[operational-queries|운영 쿼리 모음 — 진단·권한·DDL/DML]]
- [[monitoring-incident-runbook|모니터링·장애 대응 런북]]
- [[dba-agent-work-plan]] — 이런 회귀를 주간 점검으로 자동 포착하려는 계획
- [[worklog-kakaogames-2026]] — 이 조사를 수행한 업무 기록
