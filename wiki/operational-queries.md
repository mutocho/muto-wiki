---
title: 운영 진단 쿼리 모음 (MySQL·PostgreSQL·SQL Server)
tags: [dba, snippet, monitoring, troubleshooting, mysql, postgresql, sqlserver]
summary: 3사 엔진 진단 쿼리 11종 대조 — 세션·블로킹·슬로우쿼리·커넥션·크기·인덱스·bloat·복제지연·트랜잭션나이·캐시·대기통계. 전부 읽기 전용. 실행 검증 전이므로 버전 확인 필수.
sources: [표준 시스템 뷰·카탈로그 기반 자체 작성 (2026-08-04), "권한·DDL/DML 절을 db-permission-queries·db-change-safe-patterns로 분리 (2026-08-16)"]
category: db운영
status: draft
created: 2026-08-04
updated: 2026-08-16
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **이 페이지는 전부 읽기 전용(SELECT/SHOW)이다.** 진단 에이전트에 통째로 실어도 되는 유일한 쿼리 묶음 — 변경 명령은 [[db-permission-queries]]·[[db-change-safe-patterns]]로 분리했고 그쪽은 승인 게이트가 필요하다
> - **아직 실행 검증 전(`draft`)이다.** 개발/QA 인스턴스에서 확인한 뒤 현장 쿼리로 교체하는 것이 미완 과제. 검증 전에는 자동화에 그대로 태우지 않는다
> - **3사 대조 구조가 이 페이지의 가치다.** 같은 목적의 쿼리를 엔진별로 나란히 두면 다중 엔진 진단 툴의 추상화 경계가 그대로 보인다
> - 임계값은 전부 일반론이다 — **기준선 보정 없이 알람 규칙으로 박지 않는다** ([[monitoring-incident-runbook]])
> - 원본 문서에서 발견된 오류(MySQL에 PG 전용 `FILTER (WHERE)` 혼입, `blocked > 50` 임계치 오독)를 옮겨오지 않도록 주의 — [[notion-remediation-backlog]]

# 운영 진단 쿼리 모음

## 이 페이지의 검증 상태 — 먼저 읽을 것

- **작성 근거는 각 엔진의 표준 시스템 뷰·카탈로그이며, 이 환경의 실제 인스턴스에서 실행 검증하지 않았다.** `status: draft`가 그 뜻이다.
- **운영 DB에 처음 붙이기 전 개발·QA 인스턴스에서 먼저 실행**하고, 결과 컬럼과 버전 호환을 확인한 뒤 쓴다. 컬럼명·뷰 위치는 버전마다 바뀐다(각 항목의 버전 주의 참조).
- **이 페이지는 읽기 전용 쿼리만 담는다. 변경 명령을 여기에 추가하지 않는다.** 권한 부여는 [[db-permission-queries]], DDL·DML은 [[db-change-safe-patterns]]로 간다 — [[notion-remediation-backlog]]에 "통계 리셋 명령이 조회 쿼리 사이에 섞여 있음", "조각화율만으로 REBUILD 스크립트 생성"이 교정 대상으로 잡혀 있다. **조회와 변경을 같은 블록에 섞지 않는다.**
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

## 후속 / 미수록

- **실제 사용 중인 쿼리로 대체·검증 필요.** 위는 표준 뷰 기반 일반형이므로, 현장에서 쓰는 버전이 있으면 그것으로 교체하고 `status`를 올린다.
- 미수록: 파티션 현황, 통계 최신성(마지막 ANALYZE/UPDATE STATISTICS), 백업 이력 조회, Aurora 전용 지표 뷰.
- [[aurora-dsql]]은 이 페이지 대상이 아니다 — 시스템 카탈로그가 제한적이고 VACUUM·bloat·복제 지연 개념 자체가 없다.

## Related

- [[db-permission-queries|3-엔진 권한 감사·부여 쿼리]] — 여기서 분리한 권한 절. 감사는 읽기 전용이지만 부여는 승인 게이트 대상
- [[db-change-safe-patterns|DDL·DML 안전 실행 패턴]] — 여기서 분리한 변경 명령. **조회는 이쪽, 변경은 저쪽**이 두 페이지의 경계다
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
- [[postgresql-object-operations]] — 여기서 조회한 오브젝트(크기·인덱스·파티션)를 실제로 바꿀 때의 PG 런북
- [[mysql-partition-pruning-prepared-stmt-bug]] — 영향 조사 대상 테이블을 찾을 때
- [[notion-llm-wiki-governance]] — 실행 명령에 버전·영향·롤백을 기재하는 기준
