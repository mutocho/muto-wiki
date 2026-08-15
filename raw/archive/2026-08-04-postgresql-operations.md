---
title: PostgreSQL 운영 지식 — 계정·파라미터·설계·모니터링 (Notion 심층 수집)
tags: [dba, postgresql, monitoring, architecture]
topics: [dba]
summary: >-
  계정/권한 표준 패턴, 파라미터 베이스라인, 인덱스/파티션 운영 원칙, XID wraparound,
  Prometheus 알람 기준, PG13~18 버전별 차이. 도서 노트 + 운영 문서 통합.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: PostgreSQL 지식 인덱스 트리 (https://app.notion.com/p/cf78b06d234f4da6b9b67e6965ef263c, 2026-07-30)"
  - "Notion: PostgreSQL DBA를 위한 Admin 이야기 도서 노트 (https://app.notion.com/p/357fb969b8be80769008c410f94296e3)"
---

# PostgreSQL 운영 지식

## 계정·권한 표준

- 유저=롤(LOGIN 유무 차이). 소유(svc)/서비스(svcapp)/배치(svcbat)/조회(svcsel) 분리 + 권한묶음 롤.
- `GRANT ON ALL TABLES`는 현재 객체만 적용 → **`ALTER DEFAULT PRIVILEGES FOR USER <소유자>` 필수**. 단 테이블 생성자 기준이므로 `SET ROLE`로 생성 주체 일관성 유지.
- PG15+: public 스키마 CREATE는 DB 소유자만 가능. PG14 이하는 `REVOKE ALL ON SCHEMA public FROM public` 권장.
- 함수 기본 public EXECUTE 회수 권장. SECURITY DEFINER는 search_path 고정 + 리뷰.
- 슈퍼유저 대신 시스템 롤: `pg_monitor` / `pg_read_all_data`(14+) / `pg_maintain`(17+).
- 인증: PG14+ 기본 scram-sha-256 (~13은 md5). 구형 JDBC는 42.2.x+ 업그레이드.
- 계정 삭제 절차: GRANT 정리 → `REASSIGN OWNED` → `DROP OWNED` → `DROP USER`.

## 파라미터 베이스라인

- `shared_buffers` RAM 25~40%. `effective_cache_size` RAM 75%. `random_page_cost` SSD 1.1. OLTP는 `jit=off`.
- **`work_mem`은 쿼리 내 작업(sort/hash)당 할당 → OOM 함정.** 기본 작게, 배치 세션에서만 `SET LOCAL work_mem`. `hash_mem_multiplier` 2.0(PG15+).
- `maintenance_work_mem` ≈ RAM 5%. `autovacuum_work_mem=-1`이면 이를 상속(×workers 주의).
- **`idle_in_transaction_session_timeout`(~600s) 미설정이 bloat 장애 1순위 원인.**
- `max_wal_size`는 WAL 볼륨의 40%, `wal_compression=zstd`(PG15+; 14 이하 on), `default_toast_compression=lz4`, checkpoint_timeout 15분 + completion_target 0.9.
- 로그: `log_min_duration_statement=1000`, `log_lock_waits=on`, `log_temp_files`, pgBadger 호환 `log_line_prefix`. `compute_query_id=on`(14+), pg_stat_statements + auto_explain(sample 0.1).
- autovacuum은 항상 on (대량 마이그레이션 시만 예외).

## 오브젝트·테이블 설계

- 운영 인덱스 작업은 **무조건 CONCURRENTLY**. 실패 시 INVALID 잔존 → `pg_index.indisvalid` 확인 후 재생성.
- 파티션: 부모는 CIC 미지원 → `CREATE INDEX ON ONLY 부모` → 자식별 CIC → `ATTACH PARTITION`. ATTACH 전 CHECK 제약 선생성으로 풀스캔 회피. DETACH CONCURRENTLY(14+).
- VACUUM FULL 운영 금지(Access Exclusive) → pg_repack.
- `char(n)` 금지(text 기본, bpchar 형변환으로 인덱스 미사용). IDENTITY > serial. PK `bigint GENERATED ALWAYS AS IDENTITY` + 외부 노출용은 별도 uuid. 금액 `numeric`, 시각 `timestamptz`.
- **FK 컬럼 인덱스는 자동 생성되지 않음 → 직접 생성.** 복합 인덱스는 동등→범위→정렬 순. HOT Update + fillfactor 80.
- DDL은 트랜잭션 롤백 가능(예외: CREATE DATABASE/TABLESPACE, CIC 등).
- Unlogged 테이블: WAL 미발생, 크래시 시 전체 소실 — ETL/임시 용도만.

## 아키텍처·VACUUM

- 멀티프로세스(세션당 1프로세스) → PgBouncer 사실상 필수.
- TOAST: 2KB 초과 시 압축 → 외부 저장. 테이블이 공유 버퍼 1/4 초과 시 링 버퍼 전환(성능 특성 변화 — 튜닝 포인트, pg_stat_io는 PG16+).
- XID 32비트 wraparound: `age(datfrozenxid)` 모니터링. Cutoff는 DB 전체 단일 값 → 슬로우 쿼리 하나가 전체 테이블의 데드 튜플 정리를 막는다. PG13+ INSERT-only 테이블 autovacuum 지원.
- 복제: 물리 복제는 커밋 전에도 WAL 스트리밍(지연 짧음). 논리 복제는 버전 상이 가능 → 메이저 업그레이드 활용. 동기 모드는 리플리카 2대+.
- 백업: pg_basebackup은 PG17부터 블록 단위 증분. pgBackRest는 파일 단위 증분 + 병렬·델타 복구 → 16까지는 pgBackRest 유리.

## 알람 기준 (RDS/Aurora + postgres_exporter, 기준선 보정 전제)

- P1: down 2분 / connection 85~90% / disk 90~95% / replication lag 5분 또는 5~10GB / **XID age 10억 경보·15억·18억 (20억 강제 셧다운)** / lock wait 1~5분 / long tx 15분 / idle-in-tx 5~15분 / slot retained WAL 5~20GB.
- P2: dead tuple 20~30% (`n_live_tup>100k` 조건 병행) / cache hit <95% / temp bytes 기준선 2배 / WAL 2~3배 / checkpoints_req 증가 / deadlock 즉시.
- 장애 시 wraparound 대응: 장기 트랜잭션 종료 → 미사용 슬롯 `pg_drop_replication_slot` → `vacuumdb --freeze --jobs N`.
- 디스크 폭주 원인: WAL(슬롯/아카이브/대량 변경) 또는 temp(work_mem 부족).
- PG12 CTE 분기점: 11 이하 최적화 펜스, 12+ 기본 인라인(`MATERIALIZED`로 제어).

## 발견된 위험·품질 이슈 (원본 교정 필요)

- pg_hba `0.0.0.0/0` 예시는 "보안그룹 위임" 전제가 빠진 채 복붙되면 위험.
- 성능튜닝 페이지의 MySQL 히트율 쿼리에 PG 전용 `FILTER (WHERE ...)` 문법 혼입 — MySQL에서 실행 불가.
- 도서 노트에 평문 패스워드 예제·오탈자 다수, 발행일/대상 버전 미기재.
- 실제 서비스명 추정 롤명이 포함된 원시 스크립트 페이지 존재(목적·롤백 설명 없음).
