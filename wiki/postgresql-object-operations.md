---
title: PostgreSQL 오브젝트 운영 — 소유권·DDL·인덱스·파티션·뷰
category: db운영
tags: [postgresql, ddl, index, partitioning, schema]
summary: 테이블 소유권과 SET ROLE, 타입·복사 방식, 트랜잭션 DDL, 온라인 인덱스·파티션, 뷰와 시퀀스의 운영 안전 기준.
sources: ["사용자 제공 PostgreSQL 오브젝트 메모 (2026-08-16)", "PostgreSQL 공식 문서: CREATE TABLE·CREATE VIEW·CREATE INDEX·Table Partitioning·CREATE SEQUENCE (2026-08-16 대조)"]
status: draft
base_confidence: 0.78
provenance:
  extracted: 0.91
  inferred: 0.07
  ambiguous: 0.02
lifecycle: draft
lifecycle_changed: 2026-08-16
tier: supporting
created: 2026-08-16
updated: 2026-08-16
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - DDL 배포 전 `session_user`, `current_user`, 예상 소유자를 검사한다. 스키마 소유자와 테이블 소유자는 자동으로 일치하지 않으므로 배포자는 `SET ROLE <owner>` 후 생성한다
> - `ALTER DEFAULT PRIVILEGES`는 객체 생성 Role 기준이다. 소유자가 어긋난 객체는 소유권 이관과 현재 권한 보정 없이는 미래 권한 정책에 편입되지 않는다
> - 운영 인덱스 작업은 `CONCURRENTLY` + `lock_timeout` + INVALID 후속 검사를 한 단위로 실행한다. “온라인”을 “무잠금”으로 해석하지 않는다
> - 파티션 ATTACH는 범위 CHECK를 미리 검증해 스캔과 락 시간을 줄이고, 부모 인덱스는 자식별 CIC 후 ATTACH한다
> - 시퀀스 값은 롤백되지 않아 원래부터 gapless가 아니다. `CACHE`를 키우면 구멍과 세션 간 반환 순서 역전이 더 커질 수 있으므로 업무 일련번호로 사용하지 않는다

# PostgreSQL 오브젝트 운영

이 페이지는 [[postgresql-operations]]의 오브젝트 운영 세부 런북이다. 실행용 DDL 골격은 [[db-change-safe-patterns]], 검증·진단 쿼리는 [[operational-queries]]에 두고, Role 분리 원칙은 [[db-access-control]]을 따른다.

## 소유권과 배포 Role

- 테이블은 스키마 소유자가 아니라 `CREATE TABLE`을 실행한 `current_user`가 소유한다. DBA가 서비스 스키마에 직접 생성하면 스키마 소유자와 테이블 소유자가 달라질 수 있다.
- `ALTER DEFAULT PRIVILEGES FOR ROLE svc_owner`는 `svc_owner`가 앞으로 생성할 객체에만 적용된다. 다른 Role이 만든 기존 객체에는 적용되지 않는다.
- PostgreSQL에서 `current_role`은 `current_user`의 동의어이며 권한 검사에 쓰이는 유효 Role이다. 로그인 주체는 `session_user`로 확인한다. 원문의 “CURRENT_USER = 세션 유저” 설명은 반대이므로 교정했다.

```sql
SELECT session_user, current_user, current_role;

SET ROLE svc_owner;
CREATE TABLE svc.orders (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY);
RESET ROLE;

-- 이미 잘못 생성된 객체
ALTER TABLE svc.orders OWNER TO svc_owner;
```

소유권 변경 뒤에도 로그인 Role과 권한 묶음 Role의 현재 GRANT가 기대값과 일치하는지 별도로 검사한다. 소유자 변경만으로 `ALTER DEFAULT PRIVILEGES`가 과거 객체에 소급 적용되지는 않는다.

## 식별자와 타입 선택

- 따옴표 없는 식별자는 소문자로 접힌다. 큰따옴표 식별자는 대소문자가 보존되어 모든 참조에서 정확한 따옴표가 필요하므로, 자동화 표준은 소문자 `snake_case`로 제한한다.
- 문자열 기본형은 `text`다. `varchar(n)`은 길이 자체가 업무 제약일 때 사용하고 `char(n)`은 공백 패딩과 비교 의미의 혼란 때문에 신규 설계에서 제외한다. 기존 문서의 “`char(n)`이면 인덱스를 사용하지 않는다”는 단정은 부정확해 폐기한다.
- 자동 증가 키는 `serial`보다 `GENERATED ... AS IDENTITY`, 금액은 `numeric`, 글로벌 시각은 `timestamptz`를 우선 검토한다. `timestamp without time zone`은 서버 시간대에 따라 값이 자동 변환되는 타입이 아니라 시간대 의미를 저장하지 않는 타입이므로, 입력·표시 규약이 없으면 해석 사고가 난다.
- JSON은 연산·인덱싱이 필요하면 보통 `jsonb`, 원문 보존이 요구되면 `json`을 선택한다. 무조건적인 `jsonb` 치환은 하지 않는다.^[inferred]

## 트랜잭션 DDL

PostgreSQL의 많은 DDL은 트랜잭션으로 묶어 롤백할 수 있다. 그러나 락과 테이블 재작성 비용까지 사라지는 것은 아니므로 운영 변경에는 `lock_timeout`과 영향 검사가 필요하다.

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';
CREATE TABLE svc.t1 (id bigint);
ALTER TABLE svc.t1 ADD COLUMN name text;
CREATE INDEX idx_t1_name ON svc.t1 (name);
ROLLBACK;
```

트랜잭션 블록에서 실행할 수 없는 대표 명령은 `CREATE/DROP DATABASE`, `CREATE/DROP TABLESPACE`, `CREATE INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY`, `VACUUM`, `ALTER SYSTEM`이다. 버전별 예외가 있을 수 있으므로 배포기가 명령 종류를 분류해 트랜잭션 실행 여부를 결정한다.

## 테이블 복사

| 목적 | 방식 | 복사되는 것 | 운영 주의 |
|---|---|---|---|
| 조회 결과를 새 테이블로 물질화 | `CREATE TABLE ... AS SELECT` | 결과 컬럼과 데이터 | 인덱스·PK·FK·기본값은 별도 설계 |
| 결과 구조만 생성 | CTAS + `WITH NO DATA` | 결과 컬럼 정의 | 원본 테이블의 제약을 복제하는 기능이 아님 |
| 원본 정의를 선택 복제 | `CREATE TABLE ... (LIKE ... INCLUDING ...)` | 선택한 기본값·제약·인덱스·통계 등 | `INCLUDING ALL`은 필요 없는 속성까지 복제 가능 |

`LIKE ... INCLUDING DEFAULTS`가 `nextval(...)` 기본값을 복사하면 원본과 새 테이블이 같은 시퀀스를 참조할 수 있다. 복사 후 `pg_get_serial_sequence`, `pg_attrdef`, 제약·인덱스·소유자를 검증한다.

## Bloat 재구성

- 일반 `VACUUM`은 dead tuple을 재사용 가능하게 하지만 보통 파일을 OS에 반환하지 않는다. `VACUUM FULL`은 테이블을 재작성하고 `ACCESS EXCLUSIVE` 락을 잡으므로 서비스 중 자동 실행을 금지한다.
- `pg_repack`은 장시간 읽기·쓰기 차단을 줄이는 대안이지만 설치, 추가 디스크, PK/UNIQUE 요건과 전환 시점의 짧은 강한 락을 검토해야 한다. “세션 잠금 없이”라는 표현은 쓰지 않는다.^[inferred]
- `pg_squeeze` 등 다른 도구도 지원 버전, 복제·트리거 영향, 실패 복구 절차를 검증하기 전 표준화하지 않는다.

## 인덱스 운영

- 일반 `CREATE INDEX`는 읽기는 허용하지만 쓰기를 막는다. `CONCURRENTLY`는 DML을 막는 락을 피하는 대신 다중 스캔, 더 긴 실행 시간, 트랜잭션 블록 실행 불가, 실패 시 INVALID 잔존 등의 비용이 있다.
- 동일 테이블에는 동시 concurrent index build가 하나만 실행될 수 있다. UNIQUE CIC/REINDEX 중에는 같은 테이블의 `INSERT ... ON CONFLICT`가 예상 밖 unique violation으로 실패할 가능성도 고려한다.
- `DROP INDEX CONCURRENTLY`, `REINDEX ... CONCURRENTLY`도 제약과 짧은 락 구간이 있으므로 `lock_timeout`, 진행률, INVALID 검사와 롤백/재시도 계획을 함께 둔다.

```sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
  ON svc.orders (created_at);

SELECT n.nspname, c.relname
FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT i.indisvalid;
```

## 파티션 운영

- 선언적 파티션은 RANGE·LIST·HASH로 나뉜다. 파티션 키는 보존 정책, pruning 조건, 파티션별 작업 단위를 기준으로 선택하며 단순히 “핫블록 방지”만을 이유로 HASH를 고르지 않는다.^[inferred]
- 부모 파티션 테이블에는 `CREATE INDEX CONCURRENTLY`를 직접 사용할 수 없다. `CREATE INDEX ON ONLY`로 INVALID 부모 인덱스를 만들고, 각 자식에 CIC를 수행한 뒤 `ALTER INDEX ... ATTACH PARTITION`으로 연결한다. 모든 자식이 연결되면 부모 인덱스가 VALID가 된다.
- 기존 테이블을 ATTACH하기 전에 파티션 범위를 증명하는 CHECK 제약을 만들고 검증하면 ATTACH 중 전체 스캔을 피할 수 있다. DEFAULT 파티션이 있으면 새 범위의 행이 없음을 증명하는 제약도 검토한다.
- `DETACH PARTITION ... CONCURRENTLY`는 부모의 락 수준을 낮추지만 내부적으로 두 트랜잭션과 기존 트랜잭션 대기를 사용하고 제약이 있으므로 “무잠금”으로 표기하지 않는다.

## 뷰와 Materialized View

- 기본 뷰는 기저 릴레이션의 권한을 뷰 소유자 기준으로 검사한다. 제한된 데이터만 노출하는 권한 경계로 사용할 수 있지만, 이것은 `SECURITY DEFINER` 함수와 동일한 의미가 아니다.
- PostgreSQL 15+의 `WITH (security_invoker=true)`는 기저 릴레이션 권한과 RLS 정책을 호출자 기준으로 검사한다. 호출자는 뷰와 기저 릴레이션 양쪽 권한이 필요하므로, 모든 보안 뷰에 무조건 적용하는 옵션이 아니라 의도한 권한 모델에 따라 선택한다.
- `CREATE OR REPLACE VIEW`는 기존 컬럼의 이름·순서·타입 호환 제약이 있다. 교체 시 의존 객체와 락 대기를 점검한다.
- Materialized View는 결과를 저장한다. `REFRESH ... CONCURRENTLY`에는 모든 행을 유일하게 식별하는 적합한 UNIQUE 인덱스가 필요하며, 일반 REFRESH보다 추가 비용이 든다.

## 시퀀스

- `nextval`과 `setval`의 소비는 트랜잭션 롤백으로 되돌아가지 않는다. 따라서 `CACHE 1`도 gapless를 보장하지 않는다.
- `CACHE > 1`이면 세션이 값을 선점하므로 종료 시 미사용 번호가 버려지고, 여러 세션이 관찰하는 반환 순서가 숫자 순서와 다를 수 있다. 고유성만 기대한다.
- 테이블 컬럼용 수동 시퀀스에는 `OWNED BY table.column`을 검토한다. 같은 소유자·스키마 조건을 만족하면 컬럼/테이블 삭제 시 수명주기를 함께 관리할 수 있다.
- 법적·회계상 연속 번호가 필요하면 시퀀스가 아니라 직렬화된 별도 번호 발급 절차를 설계한다.^[inferred]

## 자동화 체크리스트

- [ ] DDL 직전 `session_user`, `current_user`, 대상 스키마와 예상 owner가 일치하는가
- [ ] 새 객체 생성 뒤 owner, 현재 GRANT, default privileges 기대값을 검사했는가
- [ ] 따옴표 식별자, `char(n)`, `serial`, 업무 의미 없는 `timestamp`를 스키마 린터가 차단하는가
- [ ] DDL이 트랜잭션 가능/불가 명령으로 분류되고 `lock_timeout`과 실패 정리 절차가 있는가
- [ ] CTAS/LIKE 뒤 제약·인덱스·기본값·시퀀스·소유권을 검증하는가
- [ ] CIC/REINDEX/DETACH 뒤 INVALID·진행 상태·잔여 임시 객체를 검사하는가
- [ ] 뷰의 definer/invoker와 RLS 조합이 의도한 권한 경계인지 테스트했는가

## Sources

- 사용자 제공 PostgreSQL 오브젝트 메모 (2026-08-16)
- PostgreSQL 공식 문서, *CREATE TABLE*, *CREATE TABLE AS*, *CREATE VIEW*
- PostgreSQL 공식 문서, *CREATE INDEX*, *REINDEX*, *Table Partitioning*
- PostgreSQL 공식 문서, *System Information Functions and Operators*, *CREATE SEQUENCE*
