---
title: DDL·DML 안전 실행 패턴 (MySQL·PostgreSQL·SQL Server)
category: db운영
tags: [dba, snippet, ddl, dml, mysql, postgresql, sqlserver]
summary: 운영 DB에 스키마·데이터 변경을 넣을 때의 3사 안전 절차 — 락 가드, ONLINE/CONCURRENTLY, 건수 대조, 청크 분할. 전부 변경 명령이므로 승인 게이트 필수. 실행 검증 전.
sources: [표준 시스템 뷰·카탈로그 기반 자체 작성 (2026-08-04), "사용자 제공 PostgreSQL 오브젝트 메모 및 PostgreSQL 공식 DDL 문서 대조 (2026-08-16)", "operational-queries에서 분리 (2026-08-16)"]
status: draft
created: 2026-08-16
updated: 2026-08-16
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **대량 DML 전 가드를 건다**: MySQL `sql_safe_updates=1` / PG `lock_timeout` / MSSQL `SET LOCK_TIMEOUT`. 자동화 도구에서는 세션 초기화 단계에 강제로 넣어 사람의 주의력에 의존하지 않는다
> - **DML은 4단계가 한 단위다**: 같은 `WHERE`로 `count(*)` → 트랜잭션 → 영향 건수 대조 → 커밋. 자동화가 이 순서를 건너뛸 수 없게 만든다
> - **MySQL `ALTER`는 `ALGORITHM`·`LOCK`을 항상 명시한다.** 조건을 못 맞출 때 조용히 테이블을 복사하는 대신 **에러로 실패**시키는 것이 명시의 진짜 목적
> - **DDL 롤백 가능 여부가 엔진별로 갈린다.** PG는 대부분 트랜잭션 롤백 가능, MySQL DDL은 암묵적 커밋이라 롤백이 없다 — 롤백 계획을 엔진별로 분기해야 한다
> - **조각화율만 보고 REBUILD 대상을 자동 생성하지 않는다.** `TRUNCATE`, `WHERE` 없는 UPDATE/DELETE도 의도적으로 넣지 않았다 — 생성기에 태울 명령이 아니다
> - 아직 실행 검증 전(`draft`)이다. 특히 MSSQL `RESUMABLE`·`ONLINE` 조합과 MySQL `ALGORITHM=INSTANT` 적용 조건은 버전·에디션에 따라 실패한다

# DDL·DML 안전 실행 패턴

**이 페이지는 전부 변경 명령이다.** [[operational-queries]]의 읽기 전용 진단 쿼리와 달리 승인 게이트를 반드시 거친다 — 이 경계를 페이지로 분리한 것이 의도다. 권한 관련 변경은 [[db-permission-queries]]에 따로 있고, 검토 관점의 위험 패턴은 [[db-security-review-patterns]]가 다룬다.

- **작성 근거는 각 엔진의 표준 동작이며, 이 환경의 실제 인스턴스에서 실행 검증하지 않았다.**
- **그대로 복붙해 실행하는 용도가 아니다.** 안전 절차(대상 건수 선확인 → 트랜잭션 → 건수 대조 → 커밋)를 포함한 골격이며, 운영 적용은 승인·점검 절차를 따른다.
- `TRUNCATE`, `WHERE` 없는 UPDATE/DELETE, 조각화율 단독 판단 REBUILD 생성기는 **의도적으로 넣지 않았다.** [[notion-remediation-backlog]]에 이들이 교정 대상으로 잡혀 있다.
- 실행 전 대상 확인은 [[operational-queries]]의 진단 쿼리로 한다 — 조회와 변경을 같은 블록에 섞지 않는다.

## 1. DDL 안전 패턴

**PostgreSQL**

인덱스는 **무조건 `CONCURRENTLY`**. 트랜잭션 안에서 실행할 수 없고, 실패 시 INVALID 인덱스가 잔존한다:

```sql
CREATE INDEX CONCURRENTLY idx_orders_created_at ON app.orders (created_at);

-- 실패 여부 확인
SELECT n.nspname, c.relname AS invalid_index
FROM pg_index i
JOIN pg_class     c ON c.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT i.indisvalid;

-- INVALID면 정리 후 재생성
DROP INDEX CONCURRENTLY app.idx_orders_created_at;
```

`ALTER TABLE`은 **`lock_timeout` 가드를 먼저 건다.** ACCESS EXCLUSIVE 대기가 뒤따르는 모든 쿼리를 막기 때문에, 잡히지 않으면 즉시 포기하고 재시도하는 편이 안전하다:

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';
ALTER TABLE app.orders ADD COLUMN status text;   -- 메타데이터만 변경
COMMIT;
```

| 작업 | 재작성(rewrite) | 비고 |
|---|---|---|
| `ADD COLUMN` (NULL 허용) | 없음 | 메타데이터만 |
| `ADD COLUMN ... DEFAULT` | **11+ 없음**, 10 이하 전체 재작성 | 버전 확인 필수 |
| `ALTER COLUMN TYPE` | 있음 | 대형 테이블은 신컬럼+백필+스위치로 우회 |
| `ADD CONSTRAINT CHECK` | 전체 스캔 | `NOT VALID` 2단계로 회피 |
| `SET NOT NULL` | 전체 스캔 | 12+는 동등한 CHECK가 있으면 스캔 생략 |
| `DROP COLUMN` | 없음 | 공간은 즉시 반환되지 않음 |

제약 추가는 2단계로 나눠 ACCESS EXCLUSIVE 보유 시간을 줄인다:

```sql
ALTER TABLE app.orders
  ADD CONSTRAINT chk_status CHECK (status IN ('new','paid','done')) NOT VALID;

ALTER TABLE app.orders VALIDATE CONSTRAINT chk_status;   -- 약한 락으로 검증만
```

파티션 인덱스 — 부모는 `CONCURRENTLY`를 지원하지 않으므로 자식별로 만들어 붙인다 ([[postgresql-object-operations]]):

```sql
-- 1) 부모에 INVALID 인덱스 생성 (자식이 모두 붙으면 자동 valid)
CREATE INDEX ON ONLY app.events (created_at);

-- 2) 자식별 CONCURRENTLY
CREATE INDEX CONCURRENTLY events_2026_08_created_at_idx
  ON app.events_2026_08 (created_at);

-- 3) 부모 인덱스에 부착
ALTER INDEX app.events_created_at_idx
  ATTACH PARTITION app.events_2026_08_created_at_idx;
```

파티션 ATTACH 전 CHECK 선생성으로 풀스캔을 회피한다:

```sql
ALTER TABLE app.events_2026_09
  ADD CONSTRAINT events_2026_09_range
  CHECK (created_at >= '2026-09-01' AND created_at < '2026-10-01');

ALTER TABLE app.events
  ATTACH PARTITION app.events_2026_09
  FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

ALTER TABLE app.events DETACH PARTITION app.events_2025_08 CONCURRENTLY;  -- 14+
```

> PG의 DDL은 대부분 **트랜잭션 롤백이 가능**하다. 대표적인 트랜잭션 블록 실행 불가 명령은 `CREATE/DROP DATABASE`, `CREATE/DROP TABLESPACE`, `CREATE INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY`, `VACUUM`, `ALTER SYSTEM`이다. 소유권·복사·뷰·시퀀스까지 포함한 판단표는 [[postgresql-object-operations]].
> 재구성은 `VACUUM FULL`(ACCESS EXCLUSIVE)이 아니라 `pg_repack`을 쓴다.

**MySQL**

**`ALGORITHM`·`LOCK`을 항상 명시한다.** 명시하면 조건을 만족하지 못할 때 조용히 테이블을 복사하는 대신 **에러로 실패**한다 — 이게 명시하는 진짜 이유다:

```sql
ALTER TABLE app.orders
  ADD INDEX idx_created_at (created_at),
  ALGORITHM = INPLACE, LOCK = NONE;
```

```sql
-- 8.0.12+ 즉시 컬럼 추가 (테이블 복사 없음)
ALTER TABLE app.orders ADD COLUMN status VARCHAR(16), ALGORITHM = INSTANT;
```

> 임의 위치 INSTANT ADD COLUMN은 8.0.29부터지만, **8.0.29는 회수 릴리스로 사용 금지**다([[mysql-operations]]). 8.0.30+ 또는 8.4 LTS를 쓴다.

진행 상황·메타데이터 락 확인:

```sql
-- ONLINE DDL 진행률 (stage 계측 활성 필요)
SELECT stage, substage, work_completed, work_estimated,
       ROUND(100 * work_completed / NULLIF(work_estimated, 0), 1) AS pct
FROM performance_schema.events_stages_current;

-- MDL 대기 (DDL이 안 끝날 때 원인 추적)
SELECT object_schema, object_name, lock_type, lock_status, owner_thread_id
FROM performance_schema.metadata_locks
WHERE lock_status = 'PENDING';
```

> `ALGORITHM=COPY`가 불가피한 대형 테이블은 `gh-ost` / `pt-online-schema-change`로 트리거·바이너리로그 기반 복사를 쓴다.
> DDL은 **암묵적 커밋**이다 — 트랜잭션으로 감싸도 롤백되지 않는다. PG와 가장 크게 다른 지점.

**SQL Server**

인덱스 재구성은 `ONLINE`·`RESUMABLE`·저우선순위 대기를 함께 지정한다:

```sql
ALTER INDEX idx_orders_created_at ON app.orders
REBUILD WITH (
    ONLINE = ON,              -- Enterprise/Azure
    RESUMABLE = ON,           -- 2017+, ONLINE = ON 필수
    MAXDOP = 2,               -- 환경별 조정
    SORT_IN_TEMPDB = ON
);
```

전환 시점 블로킹을 제한:

```sql
ALTER INDEX idx_orders_created_at ON app.orders
REBUILD WITH (
    ONLINE = (ON (WAIT_AT_LOW_PRIORITY (MAX_DURATION = 5 MINUTES,
                                        ABORT_AFTER_WAIT = SELF)))
);
```

중단·재개:

```sql
SELECT object_id, index_id, name, state_desc, percent_complete, total_execution_time
FROM sys.index_resumable_operations;

ALTER INDEX idx_orders_created_at ON app.orders PAUSE;
ALTER INDEX idx_orders_created_at ON app.orders RESUME;
ALTER INDEX idx_orders_created_at ON app.orders ABORT;
```

> **조각화율만 보고 REBUILD 대상을 자동 생성하지 않는다.** [[operational-queries]]의 Bloat·조각화 진단(7번)으로 대상을 확인하고, `page_count > 1000`·조각화 30%+에 한해 REBUILD, 5~30%는 `REORGANIZE`를 검토한다. `MAXDOP = 0`(전체 코어)과 `ONLINE` 누락 조합이 [[notion-remediation-backlog]]의 교정 대상이다.
> `RESUMABLE = ON`은 `MAXDOP`을 런타임에 변경할 수 없고, 일부 옵션과 함께 쓸 수 없다 — 실행 전 조합을 개발 환경에서 확인한다.^[inferred]

## 2. DML 안전 패턴

**4단계 절차 — 엔진 무관 공통**

1. **같은 `WHERE`로 `SELECT count(*)` 먼저** — 대상 건수를 눈으로 본다
2. **트랜잭션으로 감싸고 영향 건수를 1)과 대조한 뒤 커밋**
3. **대량이면 청크 분할** — 한 트랜잭션에 몰면 락 보유·언두/로그 폭증
4. **lock timeout 가드** — 무한 대기로 서비스를 막지 않는다

**PostgreSQL**

```sql
-- 1) 대상 확인
SELECT count(*) FROM app.orders
WHERE status = 'draft' AND created_at < '2025-01-01';

-- 2) 트랜잭션 + 건수 대조
BEGIN;
SET LOCAL lock_timeout = '3s';
UPDATE app.orders SET status = 'archived'
WHERE status = 'draft' AND created_at < '2025-01-01';
-- 출력된 UPDATE 건수가 1)과 일치하는지 확인
COMMIT;   -- 불일치하면 ROLLBACK;
```

청크 DELETE — **청크마다 커밋한다.** 하나의 긴 트랜잭션은 VACUUM cutoff를 붙잡아 전체 DB의 데드 튜플 정리를 막는다([[postgresql-operations]]):

```sql
-- 아래를 0건 반환까지 반복 (각 실행이 독립 트랜잭션)
DELETE FROM app.orders
WHERE id IN (
    SELECT id FROM app.orders
    WHERE created_at < '2024-01-01'
    ORDER BY id
    LIMIT 5000
);
```

변경 내역을 남겨야 할 때는 `RETURNING`으로 받는다:

```sql
UPDATE app.orders SET status = 'archived'
WHERE id = 12345
RETURNING id, status, updated_at;
```

**MySQL**

`sql_safe_updates`가 **키 조건 없는 UPDATE/DELETE를 엔진 차원에서 차단**한다 — 사람의 주의력보다 확실하다:

```sql
SET SESSION sql_safe_updates = 1;
SET SESSION innodb_lock_wait_timeout = 5;

-- 1) 대상 확인
SELECT COUNT(*) FROM app.orders
WHERE status = 'draft' AND created_at < '2025-01-01';

-- 2) 트랜잭션 + 건수 대조
START TRANSACTION;
UPDATE app.orders SET status = 'archived'
WHERE status = 'draft' AND created_at < '2025-01-01';
SELECT ROW_COUNT();     -- 1)과 대조
COMMIT;                 -- 불일치하면 ROLLBACK;
```

청크 DELETE:

```sql
-- 0건 반환까지 반복
DELETE FROM app.orders
WHERE created_at < '2024-01-01'
ORDER BY id
LIMIT 5000;
```

> 청크 사이에 커밋해 Undo·History List Length가 쌓이지 않게 한다. 진행 중 확인은 [[operational-queries]]의 트랜잭션 나이 진단(9번) `trx_rseg_history_len`으로 한다.
> `sql_safe_updates=1`이면 인덱스 없는 컬럼만으로 걸린 WHERE도 거부된다. 이때는 조건을 인덱스 컬럼으로 바꾸는 게 정답이고, 플래그를 끄는 건 마지막 수단이다.

**SQL Server**

```sql
SET XACT_ABORT ON;
SET LOCK_TIMEOUT 5000;   -- ms

-- 1) 대상 확인
SELECT COUNT(*) FROM app.orders
WHERE status = 'draft' AND created_at < '2025-01-01';

-- 2) 트랜잭션 + 건수 대조
BEGIN TRAN;
UPDATE app.orders SET status = 'archived'
WHERE status = 'draft' AND created_at < '2025-01-01';
PRINT @@ROWCOUNT;       -- 1)과 대조
COMMIT TRAN;            -- 불일치하면 ROLLBACK TRAN;
```

청크 DELETE 루프 ([[sqlserver-operations]]):

```sql
WHILE 1 = 1
BEGIN
    DELETE TOP (5000) FROM app.orders
    WHERE created_at < '2024-01-01';

    IF @@ROWCOUNT = 0 BREAK;

    WAITFOR DELAY '00:00:01';   -- 로그 백업·복제가 따라올 여유
END
```

UPSERT는 `MERGE` 대신 `UPDLOCK` + `HOLDLOCK` — `MERGE`는 동시성 버그로 운영 비권장([[sqlserver-operations]]):

```sql
BEGIN TRAN;
    IF EXISTS (SELECT 1 FROM app.counters WITH (UPDLOCK, HOLDLOCK) WHERE id = @id)
        UPDATE app.counters SET cnt = cnt + 1 WHERE id = @id;
    ELSE
        INSERT INTO app.counters (id, cnt) VALUES (@id, 1);
COMMIT TRAN;
```

> 원격 트랜잭션(DTC)이 걸리면 `SET XACT_ABORT ON`이 **필수**다 — 원격 오류는 로컬 `TRY...CATCH`에 잡히지 않는다.
> `TRUNCATE`는 이 페이지에 넣지 않았다. 최소 로깅이라 빠르지만 DDL에 가깝고 롤백 조건·FK 제약이 다르며, "TRUNCATE 생성기"가 [[notion-remediation-backlog]] P1 교정 대상이다. 필요하면 대상·복구 계획을 명시한 별도 절차서로 만든다.
> 대량 DELETE는 Ghost Record 지연 삭제로 블로킹이 생길 수 있다. `TF661`(지연 삭제 비활성)은 공간 미회수 부작용이 있어 신중히 판단한다.

## 후속 / 미수록

- 이 페이지의 명령은 **개발/QA에서 실행 확인 후 운영 절차서로 승격**할 대상이다. 특히 SQL Server `RESUMABLE`·`ONLINE` 옵션 조합, MySQL `ALGORITHM=INSTANT` 적용 가능 조건은 버전·에디션에 따라 실패하므로 사전 확인이 필요하다.
- 미수록: `TRUNCATE` 절차, 온라인 스키마 변경 도구(`gh-ost`·`pt-osc`)의 실제 실행 옵션.
- 같은 "검증 후 승격" 등급의 스크립트로 [[sqlserver-backup-procedure]]가 있다. 백업과 **파일 삭제**를 함께 수행하므로, 정리 대상 조회를 `SELECT`으로 먼저 확인하는 절차가 이 페이지보다 더 엄격하게 요구된다.
- [[aurora-dsql]]은 이 페이지 대상이 아니다 — OCC 기반이라 락 가드 개념이 다르고 미지원 DDL이 많다.

## Related

- [[operational-queries|운영 진단 쿼리 모음]] — 변경 전 대상을 확인하는 읽기 전용 쿼리. **조회는 저쪽, 변경은 이쪽**이 이 두 페이지의 경계다
- [[db-permission-queries|3-엔진 권한 감사·부여 쿼리]] — 같은 승인 게이트 등급의 권한 변경 명령
- [[db-access-control|3-엔진 계정·권한 관리 표준]] — DDL을 실행할 배포자 Role의 권한 범위. 앱 계정에 DDL을 주지 않는다는 원칙이 이 페이지 사용의 전제다
- [[db-security-review-patterns|DB 문서 보안 검토 위험 패턴]] — 이 페이지의 변경 명령이 검토 대상이 되는 관점
- [[postgresql-object-operations|PostgreSQL 오브젝트 운영]] — 소유권·복사·뷰·시퀀스까지 포함한 DDL 판단표
- [[mysql-operations|MySQL/Aurora MySQL 운영 지식]] · [[postgresql-operations|PostgreSQL 운영 지식]] · [[sqlserver-operations|SQL Server 운영 지식]] — 엔진별 운영 맥락
- [[notion-remediation-backlog|Notion 지식베이스 교정 백로그]] — TRUNCATE 생성기·조각화율 단독 판단 등 여기서 배제한 패턴의 출처
- [[notion-llm-wiki-governance]] — 실행 명령에 DBMS·버전·트랜잭션 영향·롤백을 명시하는 기준
