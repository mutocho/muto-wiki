---
title: 운영 쿼리 모음 — 진단·권한·DDL/DML (MySQL·PostgreSQL·SQL Server)
tags: [dba, snippet, monitoring, troubleshooting, mysql, postgresql, sqlserver]
summary: 3사 엔진 쿼리 모음 — 진단(1~11)·권한 감사(12)는 읽기 전용, 권한 부여(13)·DDL(14)·DML(15)은 안전 절차 포함 변경 명령. 실행 검증 전이므로 버전·조합 확인 필수.
sources: [표준 시스템 뷰·카탈로그 기반 자체 작성 (2026-08-04), "사용자 제공 PostgreSQL 오브젝트 메모 및 PostgreSQL 공식 DDL 문서 대조 (2026-08-16)"]
category: db운영
status: draft
created: 2026-08-04
updated: 2026-08-16
notion_page_id: "3bdfb969-b8be-81a6-b74a-f9e3ec136313"
notion_synced: "2026-08-15T19:48:09+0900"
---

> [!tip] 핵심 Takeaway
> - **1~12는 읽기 전용, 13~15는 변경 명령이다.** 이 경계가 이 페이지의 가장 중요한 구조 — 진단 에이전트에 실어도 되는 것과 승인 게이트를 반드시 거쳐야 하는 것의 경계다
> - **아직 실행 검증 전(`draft`)이다.** 개발/QA 인스턴스에서 확인한 뒤 현장 쿼리로 교체하는 것이 미완 과제. 검증 전에는 자동화에 그대로 태우지 않는다
> - **대량 DML 전 가드를 건다**: MySQL `sql_safe_updates=1` / PG `lock_timeout` / MSSQL `SET LOCK_TIMEOUT`. 자동화 도구에서는 세션 초기화 단계에 강제로 넣는다
> - **3사 대조 구조가 이 페이지의 가치다.** 같은 목적의 쿼리를 엔진별로 나란히 두면 다중 엔진 진단 툴의 추상화 경계가 그대로 보인다
> - 원본 문서에서 발견된 오류(MySQL에 PG 전용 `FILTER (WHERE)` 혼입, `blocked > 50` 임계치 오독)를 옮겨오지 않도록 주의 — [[notion-remediation-backlog]]

# 운영 진단 쿼리 모음

## 이 페이지의 검증 상태 — 먼저 읽을 것

- **작성 근거는 각 엔진의 표준 시스템 뷰·카탈로그이며, 이 환경의 실제 인스턴스에서 실행 검증하지 않았다.** `lifecycle: draft`, `provenance.inferred: 0.7`이 그 뜻이다.
- **운영 DB에 처음 붙이기 전 개발·QA 인스턴스에서 먼저 실행**하고, 결과 컬럼과 버전 호환을 확인한 뒤 쓴다. 컬럼명·뷰 위치는 버전마다 바뀐다(각 항목의 버전 주의 참조).
- **섹션 1~11과 12는 읽기 전용(SELECT/SHOW), 섹션 13~15는 변경 명령(GRANT/DDL/DML)이다.** 이 경계를 페이지 구조로 분리한 것은 의도적이다 — [[notion-remediation-backlog]]에 "통계 리셋 명령이 조회 쿼리 사이에 섞여 있음", "조각화율만으로 REBUILD 스크립트 생성"이 교정 대상으로 잡혀 있다. **조회와 변경을 같은 블록에 섞지 않는다.**
- **변경 명령(13~15)은 그대로 복붙해 실행하는 용도가 아니다.** 안전 절차(대상 건수 선확인 → 트랜잭션 → 건수 대조 → 커밋)를 포함한 골격이며, 운영 적용은 승인·점검 절차를 따른다. `TRUNCATE`, `WHERE` 없는 UPDATE/DELETE, 조각화율 단독 판단 REBUILD 생성기는 **의도적으로 넣지 않았다.**
- 임계값은 **일반론이며 반드시 기준선 보정**한다 — [[monitoring-incident-runbook]]의 원칙과 동일.
- 조회 순서는 [[monitoring-incident-runbook]]의 감시 흐름을 따른다: CloudWatch → PI/Database Insights → **엔진 내부 뷰(이 페이지)** → 슬로우 쿼리·실행 계획 → 조치.

## 1. 활성 세션 / 장기 실행 쿼리

**PostgreSQL**

```sql
SELECT pid, usename, application_name, client_addr, state,
       now() - xact_start  AS xact_age,
       now() - query_start AS query_age,
       wait_event_type, wait_event,
       left(query, 200) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
```

`idle in transaction` 단독 확인 — bloat 장애 1순위 원인이므로 별도로 본다([[postgresql-operations]]):

```sql
SELECT pid, usename, application_name,
       now() - state_change AS idle_age,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY state_change;
```

**MySQL**

```sql
SELECT id, user, host, db, command, time, state, LEFT(info, 200) AS info
FROM performance_schema.processlist
WHERE command <> 'Sleep'
ORDER BY time DESC;
```

> 버전 주의: `performance_schema.processlist`는 **8.0+**이며 `information_schema.processlist`와 달리 전역 뮤텍스를 잡지 않아 부하 시 더 안전하다. 5.7에서는 `information_schema.processlist`를 쓴다.

장기 트랜잭션 (Undo 폭증·HLL 증가 원인 추적 — [[mysql-operations]]):

```sql
SELECT trx_id, trx_state, trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_sec,
       trx_mysql_thread_id, trx_rows_modified, trx_isolation_level,
       LEFT(trx_query, 200) AS trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

**SQL Server**

```sql
SELECT r.session_id, s.login_name, s.host_name, s.program_name,
       r.status, r.command, r.wait_type, r.wait_time, r.blocking_session_id,
       r.total_elapsed_time, r.cpu_time, r.reads, r.writes,
       SUBSTRING(t.text, (r.statement_start_offset/2)+1,
         ((CASE r.statement_end_offset WHEN -1 THEN DATALENGTH(t.text)
                ELSE r.statement_end_offset END - r.statement_start_offset)/2)+1) AS running_stmt
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.session_id <> @@SPID
  AND s.is_user_process = 1
ORDER BY r.total_elapsed_time DESC;
```

> `sys.sysprocesses`는 하위호환용 구식 뷰다. `blocked` 컬럼은 **차단자의 SPID이며 임계치가 아니다** — [[notion-remediation-backlog]]에 오독 사례로 등록돼 있다.

## 2. 블로킹 / 락 대기

**PostgreSQL** (`pg_blocking_pids` 9.6+)

```sql
SELECT a.pid                       AS blocked_pid,
       a.usename                   AS blocked_user,
       now() - a.query_start       AS blocked_for,
       pg_blocking_pids(a.pid)     AS blocking_pids,
       a.wait_event_type, a.wait_event,
       left(a.query, 200)          AS blocked_query
FROM pg_stat_activity a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

**MySQL** — sys 뷰가 가장 짧다:

```sql
SELECT * FROM sys.innodb_lock_waits;
```

원시 뷰로 직접 볼 때:

```sql
SELECT r.trx_id AS waiting_trx, r.trx_mysql_thread_id AS waiting_thread,
       TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) AS wait_sec,
       LEFT(r.trx_query, 100) AS waiting_query,
       b.trx_id AS blocking_trx, b.trx_mysql_thread_id AS blocking_thread,
       LEFT(b.trx_query, 100) AS blocking_query
FROM performance_schema.data_lock_waits w
JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_engine_transaction_id
JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_engine_transaction_id;
```

> 버전 주의: 락 대기 뷰가 **8.0에서 `performance_schema.data_lock_waits`로 이동**했다. 5.7은 `information_schema.innodb_lock_waits`이고 컬럼명도 다르다(`requesting_trx_id`/`blocking_trx_id`). 5.7 문법을 8.0에 복붙하면 실패한다.

**SQL Server**

```sql
SELECT r.session_id, r.blocking_session_id, r.wait_type, r.wait_time,
       r.wait_resource, r.status, r.command,
       LEFT(t.text, 200) AS blocked_stmt
FROM sys.dm_exec_requests r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE r.blocking_session_id <> 0;
```

> `blocked process report`를 쓰려면 `sp_configure 'blocked process threshold'`가 0보다 커야 하고(구축 표준은 **5초** — [[sqlserver-operations]]), 이벤트는 Extended Events로 수집한다. `system_health`에는 이 이벤트가 없어 **전용 세션이 필수**다 — 세션 정의는 [[sqlserver-xevent-sessions]].
>
> 위 쿼리는 **지금 이 순간의 블로킹**을 본다. 이미 끝난 블로킹의 사후 분석은 XEvent 파일 쪽이다.

## 3. 슬로우 쿼리 Top N

**PostgreSQL** (`pg_stat_statements` 확장 필요)

```sql
SELECT queryid, calls,
       round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric,  2) AS mean_ms,
       rows,
       round(100.0 * shared_blks_hit
             / NULLIF(shared_blks_hit + shared_blks_read, 0), 1) AS hit_pct,
       left(query, 200) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

> 버전 주의: **PG13에서 `total_time` → `total_exec_time`, `mean_time` → `mean_exec_time`으로 개명**됐다. PG12 이하는 옛 컬럼명을 쓴다.
> 누적 통계이므로 마지막 리셋 시점을 함께 봐야 의미가 있다: `SELECT stats_reset FROM pg_stat_statements_info;` (PG14+)

**MySQL**

```sql
SELECT LEFT(digest_text, 200) AS digest_text, schema_name, count_star,
       ROUND(sum_timer_wait/1e12, 2) AS total_sec,
       ROUND(avg_timer_wait/1e9,  2) AS avg_ms,
       sum_rows_examined, sum_rows_sent,
       ROUND(sum_rows_examined/NULLIF(count_star,0), 1) AS rows_examined_avg
FROM performance_schema.events_statements_summary_by_digest
ORDER BY sum_timer_wait DESC
LIMIT 20;
```

> `sys.statement_analysis`가 더 읽기 쉽지만, **sys 뷰의 latency 컬럼은 포맷된 문자열**(`1.23 s`)이라 `ORDER BY total_latency`가 사전순 정렬이 되어 잘못된 Top N이 나온다. 정렬이 필요하면 원시 뷰(위) 또는 `sys.x$statement_analysis`(피코초 원시값)를 쓴다.
> `rows_examined / rows_sent` 비율이 크면 인덱스 미사용 신호 — 실행 계획 확인으로 넘어간다([[mysql-operations]]).

**SQL Server** — 플랜 캐시 기준:

```sql
SELECT TOP 20
       qs.execution_count,
       qs.total_elapsed_time/1000                      AS total_elapsed_ms,
       qs.total_elapsed_time/qs.execution_count/1000    AS avg_elapsed_ms,
       qs.total_worker_time/1000                       AS total_cpu_ms,
       qs.total_logical_reads,
       qs.total_logical_reads/qs.execution_count       AS avg_logical_reads,
       SUBSTRING(t.text, (qs.statement_start_offset/2)+1,
         ((CASE qs.statement_end_offset WHEN -1 THEN DATALENGTH(t.text)
                ELSE qs.statement_end_offset END - qs.statement_start_offset)/2)+1) AS stmt
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) t
ORDER BY qs.total_elapsed_time DESC;
```

> `dm_exec_query_stats`는 **플랜 캐시가 축출되면 사라진다.** 시계열 회귀 분석은 Query Store(2016+, 2022부터 기본 활성)가 정확하다 — [[sqlserver-operations]]의 3차 대응 단계에서 쓰는 도구.

## 4. 커넥션 현황

**PostgreSQL**

```sql
SELECT current_setting('max_connections')::int AS max_conn,
       count(*)                                AS used,
       round(100.0 * count(*)
             / current_setting('max_connections')::int, 1) AS used_pct
FROM pg_stat_activity;

SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY 2 DESC;
```

**MySQL**

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN
  ('Threads_connected','Threads_running','Max_used_connections','Aborted_connects');
SHOW GLOBAL VARIABLES LIKE 'max_connections';
```

> `Threads_running`이 실제 부하 지표다(`Threads_connected`는 유휴 포함) — [[mysql-operations]].

**SQL Server**

```sql
SELECT s.status, COUNT(*) AS sessions
FROM sys.dm_exec_sessions s
WHERE s.is_user_process = 1
GROUP BY s.status;
```

## 5. 테이블·인덱스 크기

**PostgreSQL**

```sql
SELECT n.nspname AS schema_name, c.relname AS table_name,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
       pg_size_pretty(pg_relation_size(c.oid))       AS heap,
       pg_size_pretty(pg_indexes_size(c.oid))        AS indexes,
       c.reltuples::bigint                           AS est_rows
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 20;
```

**MySQL**

```sql
SELECT table_schema, table_name,
       ROUND(data_length /1024/1024, 1) AS data_mb,
       ROUND(index_length/1024/1024, 1) AS index_mb,
       ROUND((data_length+index_length)/1024/1024, 1) AS total_mb,
       table_rows
FROM information_schema.tables
WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys')
ORDER BY (data_length + index_length) DESC
LIMIT 20;
```

> `table_rows`는 InnoDB에서 **추정치**다. 정확한 건수는 `COUNT(*)`로 직접 세야 한다.

**SQL Server**

```sql
SELECT s.name AS schema_name, t.name AS table_name, p.rows,
       SUM(a.total_pages) * 8 / 1024 AS total_mb,
       SUM(a.used_pages)  * 8 / 1024 AS used_mb
FROM sys.tables t
JOIN sys.schemas    s ON s.schema_id = t.schema_id
JOIN sys.indexes    i ON i.object_id = t.object_id
JOIN sys.partitions p ON p.object_id = i.object_id AND p.index_id = i.index_id
JOIN sys.allocation_units a ON a.container_id = p.partition_id
WHERE i.index_id <= 1
GROUP BY s.name, t.name, p.rows
ORDER BY total_mb DESC;
```

## 6. 미사용 / 중복 인덱스

**공통 주의**: 인덱스 사용 통계는 누적값이므로 **리셋 시점 확인이 필수**다. 재시작 직후 수치로 "미사용" 판단을 내리면 필요한 인덱스를 지운다. 배치·월말 작업만 쓰는 인덱스는 관측 창을 길게 잡아야 한다.

**PostgreSQL**

```sql
SELECT s.schemaname, s.relname AS table_name, s.indexrelname AS index_name,
       s.idx_scan,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
  AND NOT i.indisunique
  AND NOT i.indisprimary
ORDER BY pg_relation_size(s.indexrelid) DESC;

-- 통계 리셋 시점 확인
SELECT datname, stats_reset FROM pg_stat_database WHERE datname = current_database();
```

**MySQL** (`performance_schema` 활성 필요)

```sql
SELECT * FROM sys.schema_unused_indexes;
SELECT * FROM sys.schema_redundant_indexes;
```

**SQL Server**

```sql
SELECT OBJECT_SCHEMA_NAME(i.object_id) AS schema_name,
       OBJECT_NAME(i.object_id)        AS table_name,
       i.name                          AS index_name,
       ISNULL(us.user_seeks,   0) AS user_seeks,
       ISNULL(us.user_scans,   0) AS user_scans,
       ISNULL(us.user_lookups, 0) AS user_lookups,
       ISNULL(us.user_updates, 0) AS user_updates
FROM sys.indexes i
LEFT JOIN sys.dm_db_index_usage_stats us
       ON us.object_id  = i.object_id
      AND us.index_id   = i.index_id
      AND us.database_id = DB_ID()
WHERE i.type_desc <> 'HEAP'
  AND i.is_primary_key = 0
  AND i.is_unique_constraint = 0
  AND ISNULL(us.user_seeks,0) + ISNULL(us.user_scans,0) + ISNULL(us.user_lookups,0) = 0
ORDER BY ISNULL(us.user_updates, 0) DESC;

-- 통계 리셋 시점(= 인스턴스 시작 시각) 확인
SELECT sqlserver_start_time FROM sys.dm_os_sys_info;
```

## 7. Bloat / 조각화 진단

**PostgreSQL** — dead tuple 비율. [[postgresql-operations]]의 P2 알람 기준(dead 20~30% + `n_live_tup>100k`)과 같은 조건:

```sql
SELECT schemaname, relname, n_live_tup, n_dead_tup,
       round(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS dead_pct,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
WHERE n_live_tup > 100000
ORDER BY dead_pct DESC NULLS LAST
LIMIT 20;
```

> 정밀 bloat 측정은 `pgstattuple` 확장이 필요하고 **전체 스캔이므로 운영 시간대 실행 금지**. 재구성은 `VACUUM FULL`이 아니라 `pg_repack`을 쓴다.

**SQL Server** — 조각화 조회 (`LIMITED` 모드, 소형 인덱스 제외):

```sql
SELECT OBJECT_SCHEMA_NAME(ips.object_id) AS schema_name,
       OBJECT_NAME(ips.object_id)        AS table_name,
       i.name AS index_name, ips.index_type_desc,
       ips.avg_fragmentation_in_percent, ips.page_count
FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
JOIN sys.indexes i ON i.object_id = ips.object_id AND i.index_id = ips.index_id
WHERE ips.page_count > 1000
  AND ips.avg_fragmentation_in_percent > 30
ORDER BY ips.avg_fragmentation_in_percent DESC;
```

> **이 결과로 REBUILD 스크립트를 자동 생성하지 않는다.** 조각화율 단독 판단은 [[notion-remediation-backlog]]에 교정 대상으로 등록된 안티패턴이다. `DETAILED` 모드는 전체 스캔이므로 운영 시간대 금지.

## 8. 복제 지연

**PostgreSQL** (프라이머리에서)

```sql
SELECT client_addr, application_name, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

슬롯이 붙잡고 있는 WAL — 디스크 폭주 원인 1순위:

```sql
SELECT slot_name, slot_type, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC NULLS LAST;
```

**MySQL**

```sql
SHOW REPLICA STATUS;
```

> 버전 주의: **8.0.22+에서 `SHOW REPLICA STATUS`**, 이전은 `SHOW SLAVE STATUS`. 지연 컬럼도 `Seconds_Behind_Source` / `Seconds_Behind_Master`로 다르다. Aurora MySQL은 이 값 대신 `AuroraReplicaLag` CloudWatch 지표를 본다.

**SQL Server** (Always On AG)

```sql
SELECT ar.replica_server_name, DB_NAME(drs.database_id) AS db_name,
       drs.synchronization_state_desc, drs.synchronization_health_desc,
       drs.log_send_queue_size, drs.redo_queue_size, drs.last_commit_time
FROM sys.dm_hadr_database_replica_states drs
JOIN sys.availability_replicas ar ON ar.replica_id = drs.replica_id;
```

## 9. 트랜잭션 나이 / wraparound·Undo

**PostgreSQL** — XID wraparound. 알람 기준은 10억(경보)/15억/18억, 20억에서 강제 셧다운([[postgresql-operations]]):

```sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;

-- 어느 테이블이 cutoff를 잡고 있는지
SELECT n.nspname, c.relname, age(c.relfrozenxid) AS xid_age
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','m')
ORDER BY xid_age DESC
LIMIT 20;
```

> cutoff는 **DB 전체 단일 값**이므로 슬로우 쿼리 하나가 전체 테이블의 데드 튜플 정리를 막는다. 1번 항목의 장기 트랜잭션 조회와 함께 본다.

**MySQL** — History List Length:

```sql
SELECT count AS history_list_length
FROM information_schema.innodb_metrics
WHERE name = 'trx_rseg_history_len';
```

> `SHOW ENGINE INNODB STATUS`의 TRANSACTIONS 섹션에서도 같은 값을 볼 수 있다. 수십만 이상이면 장기 트랜잭션이 Purge를 막고 있는 상태다. `innodb_purge_threads`·`batch_size`는 **원인 확인 전 조정 금지** — [[mysql-operations]].

## 10. 캐시 히트율 / 메모리

**PostgreSQL** (P2 알람 기준 <95%)

```sql
SELECT round(100.0 * sum(blks_hit)
             / NULLIF(sum(blks_hit + blks_read), 0), 2) AS cache_hit_pct
FROM pg_stat_database;
```

**MySQL** (buffer pool hit 99%+ 기대)

```sql
SELECT
  ROUND(100 * (1 - r.VARIABLE_VALUE / NULLIF(q.VARIABLE_VALUE, 0)), 2) AS bp_hit_pct
FROM performance_schema.global_status r
JOIN performance_schema.global_status q
  ON r.VARIABLE_NAME = 'Innodb_buffer_pool_reads'
 AND q.VARIABLE_NAME = 'Innodb_buffer_pool_read_requests';
```

> `performance_schema.global_status`는 **5.7+**. `information_schema.global_status`는 5.7에서 deprecated, 8.0에서 제거됐다.
> [[postgresql-operations]]에 기록된 교정 사항 — 원본 문서의 MySQL 히트율 쿼리에 PG 전용 `FILTER (WHERE ...)` 문법이 섞여 있어 MySQL에서 실행 불가였다. 위 쿼리는 그 오류를 피한 형태다.

**SQL Server** (PLE 현대 기준 1,000~3,000초+, Memory Grants Pending = 0 — [[sqlserver-operations]])

```sql
SELECT RTRIM(object_name) AS object_name, RTRIM(counter_name) AS counter_name,
       RTRIM(instance_name) AS instance_name, cntr_value
FROM sys.dm_os_performance_counters
WHERE counter_name IN ('Page life expectancy', 'Memory Grants Pending',
                       'Buffer cache hit ratio', 'Buffer cache hit ratio base');
```

인스턴스 메모리 사용 현황:

```sql
SELECT total_physical_memory_kb/1024  AS total_physical_mb,
       available_physical_memory_kb/1024 AS available_physical_mb,
       system_memory_state_desc
FROM sys.dm_os_sys_memory;

SELECT physical_memory_in_use_kb/1024 AS sqlserver_in_use_mb,
       large_page_allocations_kb/1024 AS large_page_mb,
       memory_utilization_percentage,
       process_physical_memory_low, process_virtual_memory_low
FROM sys.dm_os_process_memory;
```

## 11. 대기 통계 (SQL Server)

```sql
SELECT TOP 20 wait_type, waiting_tasks_count,
       wait_time_ms, wait_time_ms - signal_wait_time_ms AS resource_wait_ms,
       max_wait_time_ms
FROM sys.dm_os_wait_stats
WHERE waiting_tasks_count > 0
  AND wait_type NOT LIKE 'SLEEP%'
  AND wait_type NOT LIKE 'BROKER%'
  AND wait_type NOT LIKE 'XE%'
  AND wait_type NOT IN ('CLR_SEMAPHORE','LAZYWRITER_SLEEP','RESOURCE_QUEUE',
                        'CHECKPOINT_QUEUE','REQUEST_FOR_DEADLOCK_SEARCH',
                        'LOGMGR_QUEUE','DIRTY_PAGE_POLL','HADR_FILESTREAM_IOMGR_IOCOMPLETION',
                        'SQLTRACE_INCREMENTAL_FLUSH_SLEEP','WAITFOR')
ORDER BY wait_time_ms DESC;
```

> **양성(benign) 대기 제외 목록은 위가 전부가 아니다** — 실제로는 40여 종이며 버전마다 늘어난다. 여기 목록은 흔한 것만 추린 축약형이므로, 결과 상위에 낯선 `*_SLEEP`·`*_QUEUE` 계열이 보이면 제외 목록에 추가한다.^[inferred]
> `CXPACKET` 상위면 MAXDOP·Cost Threshold 검토, 컴파일 폭주면 `OPTIMIZE FOR AD HOC` + 파라미터화 — [[sqlserver-operations]]의 CPU 100% 대응 흐름.

## 12. 권한 감사 (읽기 전용)

**공통 원칙** — [[db-access-control]]의 표준과 짝을 이룬다. 권한 변경 후에는 **반드시 실측 조회로 검증**한다(부여 성공 ≠ 의도한 권한).

> **비밀번호 해시 컬럼은 조회하지 않는다.** MySQL `mysql.user.authentication_string`, PG `pg_authid.rolpassword`, MSSQL `sys.sql_logins.password_hash`는 이 페이지의 모든 쿼리에서 제외했다. `SELECT *`로 이 테이블들을 훑으면 해시가 터미널·로그에 남는다.

**PostgreSQL**

```sql
-- 롤 목록·속성 (슈퍼유저·LOGIN 여부 감사)
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb,
       rolcanlogin, rolreplication, rolbypassrls,
       rolconnlimit, rolvaliduntil
FROM pg_roles
WHERE rolname NOT LIKE 'pg\_%'
ORDER BY rolsuper DESC, rolname;

-- 롤 멤버십 (권한 묶음 상속 관계)
SELECT m.rolname AS member, g.rolname AS granted_role, am.admin_option
FROM pg_auth_members am
JOIN pg_roles m ON m.oid = am.member
JOIN pg_roles g ON g.oid = am.roleid
ORDER BY member, granted_role;

-- 테이블 권한
SELECT table_schema, table_name, grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee;

-- 스키마 권한
SELECT n.nspname AS schema_name,
       pg_get_userbyid(a.grantee) AS grantee,
       a.privilege_type, a.is_grantable
FROM pg_namespace n
CROSS JOIN LATERAL aclexplode(n.nspacl) a
WHERE n.nspname NOT LIKE 'pg\_%'
  AND n.nspname <> 'information_schema'
ORDER BY schema_name, grantee;
```

> `nspacl`이 NULL(기본 ACL 그대로)인 스키마는 `CROSS JOIN LATERAL`에서 행이 사라진다. 누락 여부는 `SELECT nspname, nspacl FROM pg_namespace`로 별도 확인한다.

**DEFAULT PRIVILEGES 확인** — `GRANT ON ALL TABLES`는 현재 객체만 적용되므로([[postgresql-operations]]) 이 조회가 실제 운영 여부를 가른다:

```sql
SELECT pg_get_userbyid(d.defaclrole) AS for_owner_role,
       n.nspname AS schema_name,
       CASE d.defaclobjtype WHEN 'r' THEN 'table'    WHEN 'S' THEN 'sequence'
                            WHEN 'f' THEN 'function' WHEN 'T' THEN 'type'
                            WHEN 'n' THEN 'schema'   ELSE d.defaclobjtype::text END AS obj_type,
       d.defaclacl AS default_acl
FROM pg_default_acl d
LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
ORDER BY for_owner_role, schema_name, obj_type;
```

특정 권한 유효성 단건 확인:

```sql
SELECT has_table_privilege('svcsel', 'app.orders', 'SELECT')  AS can_select,
       has_schema_privilege('svcsel', 'app', 'USAGE')          AS has_usage,
       has_table_privilege('svcsel', 'app.orders', 'UPDATE')   AS can_update;  -- 조회 계정은 false여야 정상
```

롤별 `search_path` 등록값 확인:

```sql
SELECT r.rolname, d.datname, s.setconfig
FROM pg_db_role_setting s
LEFT JOIN pg_roles    r ON r.oid = s.setrole
LEFT JOIN pg_database d ON d.oid = s.setdatabase;
```

> `setrole = 0`이면 데이터베이스 전체 설정(`ALTER DATABASE ... SET`), `setdatabase = 0`이면 롤 전역 설정이다. 두 값이 모두 있으면 `ALTER ROLE ... IN DATABASE ... SET`.

**MySQL**

```sql
-- 계정 목록·상태 (해시 컬럼 제외)
SELECT user, host, account_locked, password_expired,
       password_lifetime, password_last_changed, plugin
FROM mysql.user
ORDER BY user, host;

-- 특정 계정의 실제 권한
SHOW GRANTS FOR 'svcapp'@'10.%';

-- 권한 전수 조회
SELECT * FROM information_schema.user_privileges;    -- 글로벌
SELECT * FROM information_schema.schema_privileges;  -- 스키마
SELECT * FROM information_schema.table_privileges;   -- 테이블
```

8.0 롤 매핑:

```sql
SELECT from_user AS role_name, from_host, to_user AS member, to_host, with_admin_option
FROM mysql.role_edges
ORDER BY role_name, member;

SELECT * FROM mysql.default_roles;
```

> 버전 주의: **롤은 8.0+**. 5.7은 롤 개념이 없어 권한을 계정에 직접 부여해야 하며, `mysql.role_edges`·`mysql.default_roles`가 존재하지 않는다.
> `SHOW GRANTS`는 롤을 통해 상속된 권한을 기본으로 펼치지 않는다. 유효 권한은 `SHOW GRANTS FOR 'svcapp'@'10.%' USING 'app_rw';`로 롤을 지정해 확인한다.

**SQL Server**

```sql
-- DB 수준 권한
SELECT dp.name AS principal_name, dp.type_desc, dp.authentication_type_desc,
       perm.class_desc, perm.permission_name, perm.state_desc,
       OBJECT_SCHEMA_NAME(perm.major_id) AS schema_name,
       OBJECT_NAME(perm.major_id)        AS object_name
FROM sys.database_permissions perm
JOIN sys.database_principals dp ON dp.principal_id = perm.grantee_principal_id
WHERE dp.name NOT LIKE '##%'
ORDER BY principal_name, permission_name;

-- DB 롤 멤버십
SELECT r.name AS role_name, m.name AS member_name, m.type_desc
FROM sys.database_role_members drm
JOIN sys.database_principals r ON r.principal_id = drm.role_principal_id
JOIN sys.database_principals m ON m.principal_id = drm.member_principal_id
ORDER BY role_name, member_name;

-- 서버 롤 멤버십 (sysadmin 감사)
SELECT sp.name AS login_name, sp.type_desc, sp.is_disabled,
       r.name AS server_role
FROM sys.server_principals sp
LEFT JOIN sys.server_role_members srm ON srm.member_principal_id = sp.principal_id
LEFT JOIN sys.server_principals    r  ON r.principal_id = srm.role_principal_id
WHERE sp.name NOT LIKE '##%'
ORDER BY server_role, login_name;
```

유효 권한 확인 (본인 / 특정 사용자로 가정):

```sql
SELECT * FROM fn_my_permissions('app.orders', 'OBJECT');

EXECUTE AS USER = 'svcsel';
  SELECT * FROM fn_my_permissions('app.orders', 'OBJECT');
REVERT;
```

고아 사용자 (대응 로그인이 없는 DB 사용자 — 복원 후 흔히 발생):

```sql
SELECT dp.name, dp.type_desc, dp.sid
FROM sys.database_principals dp
LEFT JOIN sys.server_principals sp ON sp.sid = dp.sid
WHERE dp.type IN ('S','U','G')
  AND dp.principal_id > 4
  AND sp.sid IS NULL;
```

## 13. 권한 부여 (변경 — 승인 필요)

**설계 원칙** ([[db-access-control]], [[postgresql-operations]])

- 롤 분리: 소유 `svc` / 서비스 `svcapp` / 배치 `svcbat` / 조회 `svcsel` / 모니터링 `svcmon`
- **권한은 묶음 롤에 부여하고, 로그인 계정에는 롤만 준다.** 계정에 직접 부여하면 계정이 늘 때마다 누락이 생긴다
- 금지: 앱 계정에 슈퍼유저 / `sysadmin` / `db_owner` — 시스템 롤로 대체
- 비밀번호는 코드·문서에 남기지 않고 시크릿 저장소에서 주입

**PostgreSQL**

```sql
-- 1) 권한 묶음 롤 (로그인 불가)
CREATE ROLE app_rw NOLOGIN;
CREATE ROLE app_ro NOLOGIN;

-- 2) 스키마 사용 권한
GRANT USAGE ON SCHEMA app TO app_rw, app_ro;

-- 3) 현재 존재하는 객체
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES    IN SCHEMA app TO app_rw;
GRANT USAGE, SELECT                  ON ALL SEQUENCES IN SCHEMA app TO app_rw;
GRANT SELECT                         ON ALL TABLES    IN SCHEMA app TO app_ro;

-- 4) 앞으로 생성될 객체 — 3)만으로는 신규 테이블에 권한이 없다
ALTER DEFAULT PRIVILEGES FOR ROLE svc IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE svc IN SCHEMA app
  GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE svc IN SCHEMA app
  GRANT SELECT ON TABLES TO app_ro;

-- 5) 로그인 롤에 묶음 부여
GRANT app_rw TO svcapp, svcbat;
GRANT app_ro TO svcsel;

-- 6) 검증 (12번 섹션)
SELECT has_table_privilege('svcsel', 'app.orders', 'UPDATE');  -- false 기대
```

> **`ALTER DEFAULT PRIVILEGES`는 `FOR ROLE <소유자>`가 핵심이다.** 기본 권한은 *객체를 생성한 롤* 기준으로 적용되므로, 마이그레이션 도구가 `svc`가 아닌 다른 롤로 테이블을 만들면 4)가 적용되지 않는다. 생성 주체를 `SET ROLE svc;`로 고정한다.

단일 스키마 구성이라 스키마 명시 없이 쿼리하려면 `search_path`를 등록한다:

```sql
-- 데이터베이스 전체 (모든 롤 + 향후 추가될 롤까지 한 번에)
ALTER DATABASE <db> SET search_path = app, extensions, pg_temp;

-- 롤별로 달라야 할 때만
ALTER ROLE svcapp IN DATABASE <db> SET search_path = app, extensions, pg_temp;
```

> `pg_temp`를 명시하지 않으면 **암묵적으로 맨 앞**에서 검색되어, 임시 객체로 `app.*`를 가로챌 여지가 생긴다. 끝에 명시해 우선순위를 낮춘다. `pg_catalog`는 항상 맨 앞이므로 신경 쓰지 않아도 된다.
> 로그인 시점에 적용되므로 **기존 세션에는 반영되지 않는다.** 재접속 후 `SHOW search_path;`로 확인. role-level 설정은 *인증한 롤* 기준이라 `SET ROLE`로 전환한 롤의 값으로 바뀌지 않는다.

모니터링 계정 (슈퍼유저 대신 시스템 롤):

```sql
CREATE ROLE svcmon LOGIN;
GRANT pg_monitor TO svcmon;             -- 10+
GRANT pg_read_all_data TO svcmon;       -- 14+ (조회 전용 감사에 필요할 때만)
```

계정 삭제 — 순서를 지켜야 소유 객체가 고아가 되지 않는다:

```sql
-- 1) 남은 권한 확인 (12번 섹션의 role_table_grants)
-- 2) 소유 객체 이관
REASSIGN OWNED BY old_role TO svc;
-- 3) 남은 권한 부여 내역 제거
DROP OWNED BY old_role;
-- 4) 삭제
DROP ROLE old_role;
```

**MySQL**

```sql
-- 1) 롤 생성·권한 부여 (8.0+)
CREATE ROLE 'app_rw', 'app_ro';
GRANT SELECT, INSERT, UPDATE, DELETE ON app.* TO 'app_rw';
GRANT SELECT                         ON app.* TO 'app_ro';

-- 2) 계정에 롤 부여 + 기본 롤 활성화
GRANT 'app_rw' TO 'svcapp'@'10.%';
GRANT 'app_ro' TO 'svcsel'@'10.%';
SET DEFAULT ROLE ALL TO 'svcapp'@'10.%', 'svcsel'@'10.%';

-- 3) 검증
SHOW GRANTS FOR 'svcsel'@'10.%' USING 'app_ro';
```

> **`SET DEFAULT ROLE`을 빼먹으면 접속 직후 권한이 0이다.** 롤을 부여해도 세션에서 활성화되지 않으면 적용되지 않는다(또는 앱이 매 접속마다 `SET ROLE`을 호출해야 한다).
> 5.7은 롤이 없으므로 계정에 직접 부여한다.

모니터링 계정 (조회 전용 — [[db-access-control]]):

```sql
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'svcmon'@'10.%';
GRANT SELECT ON performance_schema.* TO 'svcmon'@'10.%';
```

**SQL Server**

```sql
-- 1) DB 롤 + 스키마 단위 권한
CREATE ROLE app_rw;
CREATE ROLE app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::app TO app_rw;
GRANT SELECT                         ON SCHEMA::app TO app_ro;

-- 2) 멤버 추가
ALTER ROLE app_rw ADD MEMBER svcapp;
ALTER ROLE app_ro ADD MEMBER svcsel;

-- 3) 검증 (12번 섹션의 database_role_members / fn_my_permissions)
```

> **스키마 단위(`ON SCHEMA::app`) 부여가 테이블 단위보다 안전하다** — 신규 테이블에 권한이 자동 적용되어 PG의 `ALTER DEFAULT PRIVILEGES`와 같은 역할을 한다.

모니터링 계정 — 버전에 따라 권한 이름이 다르다:

```sql
GRANT VIEW SERVER STATE TO svcmon;              -- 2019 이하
GRANT VIEW SERVER PERFORMANCE STATE TO svcmon;  -- 2022+ (세분화됨)
GRANT VIEW ANY DEFINITION TO svcmon;            -- 2022+, 스키마 조회가 필요할 때
```

sa 비활성화 + 명명 관리자 계정 ([[sqlserver-operations]]):

```sql
ALTER LOGIN sa DISABLE;
-- 관리자 계정은 CHECK_POLICY / CHECK_EXPIRATION ON으로 생성, 비밀번호는 시크릿 저장소 주입
```

## 14. DDL 안전 패턴 (변경 — 승인 필요)

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

> **조각화율만 보고 REBUILD 대상을 자동 생성하지 않는다.** 7번 섹션 조회로 대상을 확인하고, `page_count > 1000`·조각화 30%+에 한해 REBUILD, 5~30%는 `REORGANIZE`를 검토한다. `MAXDOP = 0`(전체 코어)과 `ONLINE` 누락 조합이 [[notion-remediation-backlog]]의 교정 대상이다.
> `RESUMABLE = ON`은 `MAXDOP`을 런타임에 변경할 수 없고, 일부 옵션과 함께 쓸 수 없다 — 실행 전 조합을 개발 환경에서 확인한다.^[inferred]

## 15. DML 안전 패턴 (변경 — 승인 필요)

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

> 청크 사이에 커밋해 Undo·History List Length가 쌓이지 않게 한다. 9번 섹션의 `trx_rseg_history_len`으로 진행 중 확인.
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

- **실제 사용 중인 쿼리로 대체·검증 필요.** 위는 표준 뷰 기반 일반형이므로, 현장에서 쓰는 버전이 있으면 그것으로 교체하고 `lifecycle`을 올린다.
- 미수록: 파티션 현황, 통계 최신성(마지막 ANALYZE/UPDATE STATISTICS), 백업 이력 조회, Aurora 전용 지표 뷰, `TRUNCATE` 절차, 행 수준 보안(RLS)·컬럼 마스킹 설정.
- 13~15의 변경 명령은 **개발/QA에서 실행 확인 후 운영 절차서로 승격**할 대상이다. 특히 SQL Server `RESUMABLE`·`ONLINE` 옵션 조합, MySQL `ALGORITHM=INSTANT` 적용 가능 조건은 버전·에디션에 따라 실패하므로 사전 확인이 필요하다.
- [[aurora-dsql]]은 이 페이지 대상이 아니다 — 시스템 카탈로그가 제한적이고 VACUUM·bloat·복제 지연 개념 자체가 없다.
- 같은 "검증 후 승격" 등급의 스크립트로 [[sqlserver-backup-procedure]]가 있다. 백업과 **파일 삭제**를 함께 수행하므로, 정리 대상 조회를 `SELECT`으로 먼저 확인하는 절차가 13~15보다 더 엄격하게 요구된다.

## Related

- [[monitoring-incident-runbook|모니터링·장애 대응 런북]]
- [[mysql-operations|MySQL/Aurora MySQL 운영 지식]]
- [[postgresql-operations|PostgreSQL 운영 지식]]
- [[sqlserver-operations|SQL Server 운영 지식]]
- [[db-common-concepts|DBMS 공통 개념·3사 비교]]
- [[db-access-control|3-엔진 계정·권한 관리 표준]]
- [[db-security-review-patterns|DB 문서 보안 검토 위험 패턴]]
- [[notion-remediation-backlog|Notion 지식베이스 교정 백로그]]
- [[dba-ops-standards]] — 이 쿼리들을 실행하는 장애 대응 5단계
- [[dbgw-queries]] — dbgw 메타DB 전용 실무 쿼리
- [[mysql-partition-pruning-prepared-stmt-bug]] — 영향 조사 대상 테이블을 찾을 때
- [[notion-llm-wiki-governance]] — 실행 명령에 버전·영향·롤백을 기재하는 기준
