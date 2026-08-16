---
title: PostgreSQL 운영 지식 — 계정·파라미터·설계·모니터링
category: db운영
tags: [dba, postgresql, monitoring, architecture, vacuum]
summary: 접속·SCRAM 인증, 계정/권한·스키마 표준, 확장 모듈, 파라미터, 오브젝트 운영, XID wraparound와 알람 기준을 다룬 PostgreSQL 운영 런북.
sources: ["Notion: PostgreSQL 지식 인덱스 트리 (2026-07-30)", "도서 노트: PostgreSQL DBA를 위한 Admin 이야기", "사용자 제공 PostgreSQL 운영 메모 (2026-08-15)", "사용자 제공 PostgreSQL 오브젝트 메모 (2026-08-16)", "PostgreSQL 공식 문서: Password Authentication·Schemas·Predefined Roles·CREATE TABLE·CREATE VIEW·CREATE INDEX (2026-08-16 대조)"]
status: reviewed
created: 2026-08-04
updated: 2026-08-16
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - 신규 클러스터는 **최소 listen/HBA 범위·SCRAM·TLS·public CREATE 회수·소유/로그인 Role 분리·기본 권한**을 오픈 게이트로 자동 검사한다
> - `ALTER DEFAULT PRIVILEGES`는 객체 생성 Role 기준이다. 배포 주체를 `SET ROLE`로 고정하지 않으면 신규 테이블 권한이 조용히 누락된다
> - `idle_in_transaction_session_timeout`과 XID age 단계별 알람을 필수화하고, wraparound 대응은 장기 트랜잭션 → 슬롯 → freeze 순으로 진행한다
> - `work_mem`은 작업 노드마다 할당되므로 전역 상향하지 않는다. 운영 인덱스는 `CONCURRENTLY`로 수행하고 INVALID 잔존을 후속 검사한다

# PostgreSQL 운영 지식

## 접속·인증 기준선

- `psql -h <host> -p 5432 -d <database> -U <role>`로 접속한다. `PGHOST`·`PGPORT`·`PGDATABASE`·`PGUSER`는 자동화 입력으로 쓸 수 있지만, `PGPASSWORD`는 프로세스 환경 노출 가능성이 있어 상시 저장하지 않는다. 비대화형 작업은 권한을 소유자만 읽을 수 있게 제한한 `.pgpass` 또는 시크릿 저장소를 사용한다.
- `listen_addresses`는 서버가 수신할 인터페이스를, `pg_hba.conf`는 DB·Role·출발지·인증 방식을 결정한다. 양쪽 모두 필요한 범위만 허용하고 보안그룹/ACL도 함께 적용한다. 네트워크 경계만 믿고 HBA를 `0.0.0.0/0`로 여는 패턴은 자동화 기본값에서 금지한다.^[inferred]
- 원격 패스워드 인증은 `hostssl ... scram-sha-256`을 기본으로 하고 TLS 인증서 검증을 병행한다. MD5 저장 암호는 PostgreSQL에서 폐기 예정이므로, 클라이언트 호환성 확인 → `password_encryption='scram-sha-256'` → 비밀번호 재설정 → HBA 전환 순으로 제거한다.
- `trust`는 패스워드 없이 접속을 허용하므로 호환성 우회책으로 사용하지 않는다. 로컬 관리 접속의 `peer`도 OS 계정 경계를 검토한 뒤 제한적으로 사용한다.

예시 규칙은 실제 CIDR과 Role로 치환하며 광역 허용을 템플릿에 남기지 않는다.

```conf
# TYPE    DATABASE    USER          ADDRESS          METHOD
hostssl   svcdb       svcapp        10.20.30.0/24    scram-sha-256
hostssl   replication replicator    10.20.40.10/32   scram-sha-256
local     all         postgres                       peer
```

## 계정·권한 표준

- 유저=롤(LOGIN 유무 차이). 소유(svc)/서비스(svcapp)/배치(svcbat)/조회(svcsel) 분리 + 권한묶음 롤.
- `GRANT ON ALL TABLES`는 현재 객체만 적용 → **`ALTER DEFAULT PRIVILEGES FOR USER <소유자>` 필수**. 단 테이블 생성자 기준이므로 `SET ROLE`로 생성 주체 일관성 유지.
- PG15+ 신규 DB는 `public` 스키마를 `pg_database_owner`가 소유해 DB 소유자가 관리한다. PG14 이하에서 생성했거나 구버전에서 업그레이드한 DB는 PUBLIC의 `CREATE`가 남아 있을 수 있으므로 `REVOKE CREATE ON SCHEMA public FROM PUBLIC` 적용 여부와 기존 객체를 감사한다.
- 함수 기본 public EXECUTE 회수 권장. SECURITY DEFINER는 search_path 고정 + 리뷰.
- 슈퍼유저 대신 시스템 롤: `pg_monitor` / `pg_read_all_data`(14+) / `pg_maintain`(17+).
- 인증은 SCRAM을 기본으로 한다. MD5 암호는 폐기 예정이며 구형 클라이언트가 남아 있으면 드라이버 업그레이드 후 비밀번호를 재설정해 SCRAM 해시로 전환한다.
- 계정 삭제 절차: GRANT 정리 → `REASSIGN OWNED` → `DROP OWNED` → `DROP USER`.
- 운영 SQL과 SECURITY DEFINER 함수는 스키마를 명시한다. `search_path`에 포함된 스키마에 비신뢰 Role이 `CREATE`할 수 있으면 객체 가로채기가 가능하므로, 경로 등록과 CREATE 권한 감사를 한 묶음으로 검사한다.

## 데이터베이스·스키마 프로비저닝

- 클러스터의 Role은 DB 간 공유되지만 접속 세션은 한 데이터베이스에만 연결된다. 데이터베이스 안에서 스키마가 논리적 네임스페이스를 제공한다.
- 로케일·인코딩이 `template1`과 다르면 `template0`으로 생성한다. `LC_COLLATE='C'`는 바이트 순서 정렬이 업무 의미와 일치할 때만 선택하고, 한글 정렬·대소문자 규칙·애플리케이션 비교 요구를 먼저 테스트한다.
- 오브젝트 소유 Role과 로그인 Role을 분리하고, 서비스 Role에는 `CONNECT` → 스키마 `USAGE` → 오브젝트 권한을 단계별로 부여한다. 신규 객체 권한은 소유 Role의 `ALTER DEFAULT PRIVILEGES`로 설정한다.

```sql
CREATE DATABASE svcdb
  ENCODING 'UTF8'
  LC_COLLATE 'C'
  LC_CTYPE 'C'
  TEMPLATE template0;

CREATE SCHEMA svc AUTHORIZATION svc_owner;
REVOKE CONNECT ON DATABASE svcdb FROM PUBLIC;
GRANT CONNECT ON DATABASE svcdb TO svcapp;
GRANT USAGE ON SCHEMA svc TO app_rw, app_ro;
```

실제 Role 생성·현재 객체 권한·기본 권한·검증 명령은 [[db-permission-queries]]의 권한 부여 절차를 사용하고, 3사 공통 분리 원칙은 [[db-access-control]]을 따른다.

## 확장 모듈 관리

- `pg_stat_statements`는 운영 쿼리 회귀 분석의 기본 확장으로 검토한다. `shared_preload_libraries` 변경과 재기동이 필요하므로 파라미터 변경, 재기동, DB별 `CREATE EXTENSION`, 수집 검증을 하나의 배포 절차로 묶는다.
- `pg_prewarm`, `pgstattuple`, `postgres_fdw`, `pgcrypto` 등은 요구가 있는 DB에만 설치한다. 확장 설치 권한, 설치 스키마, 패키지/엔진 버전 호환성, 업그레이드 책임자를 사전에 정한다.
- `uuid-ossp`를 관성적으로 설치하지 않는다. 사용 중인 PostgreSQL 버전에서 내장 UUID 함수가 요구를 충족하는지 먼저 확인한다.

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
```

## 신규 클러스터 오픈 게이트

- [ ] 수신 인터페이스, HBA CIDR·DB·Role, 네트워크 ACL이 모두 최소 범위인가
- [ ] TLS와 `scram-sha-256`이 실제 클라이언트에서 검증됐고 MD5 Role이 남지 않았는가
- [ ] PUBLIC의 DB `CONNECT`, public 스키마 `CREATE`, 함수 `EXECUTE`가 정책과 일치하는가
- [ ] 소유·배포·서비스·배치·조회·모니터링 Role이 분리됐는가
- [ ] 현재 객체 권한과 `ALTER DEFAULT PRIVILEGES FOR ROLE <owner>`가 모두 설정됐는가
- [ ] `search_path`의 모든 사용자 스키마가 신뢰 가능한 생성자만 `CREATE` 가능한가
- [ ] `pg_stat_statements`, 로그, 백업/PITR, autovacuum, 장기 트랜잭션과 XID 알람이 검증됐는가

## 파라미터 베이스라인

- `shared_buffers` RAM 25~40%. `effective_cache_size` RAM 75%. `random_page_cost` SSD 1.1. OLTP는 `jit=off`.
- **`work_mem`은 쿼리 내 작업(sort/hash)당 할당 → OOM 함정.** 기본 작게, 배치 세션에서만 `SET LOCAL work_mem`. `hash_mem_multiplier` 2.0(PG15+).
- `maintenance_work_mem` ≈ RAM 5%. `autovacuum_work_mem=-1`이면 이를 상속(×workers 주의).
- **`idle_in_transaction_session_timeout`(~600s) 미설정이 bloat 장애 1순위 원인.**
- `max_wal_size`는 WAL 볼륨의 40%, `wal_compression=zstd`(PG15+; 14 이하 on), `default_toast_compression=lz4`, checkpoint_timeout 15분 + completion_target 0.9.
- 로그: `log_min_duration_statement=1000`, `log_lock_waits=on`, `log_temp_files`, pgBadger 호환 `log_line_prefix`. `compute_query_id=on`(14+), pg_stat_statements + auto_explain(sample 0.1).
- autovacuum은 항상 on (대량 마이그레이션 시만 예외).

## 오브젝트·테이블 설계

- 테이블 소유자는 스키마 소유자가 아니라 DDL의 `current_user`다. 배포자는 `session_user`와 `current_user`를 확인하고 `SET ROLE <owner>`로 생성 주체를 고정한다. 상세 런북은 [[postgresql-object-operations]].
- 운영 인덱스 작업은 **무조건 CONCURRENTLY**. 실패 시 INVALID 잔존 → `pg_index.indisvalid` 확인 후 재생성.
- 파티션: 부모는 CIC 미지원 → `CREATE INDEX ON ONLY 부모` → 자식별 CIC → `ATTACH PARTITION`. ATTACH 전 CHECK 제약 선생성으로 풀스캔 회피. DETACH CONCURRENTLY(14+).
- VACUUM FULL 운영 금지(Access Exclusive) → pg_repack.
- `char(n)`은 공백 패딩·비교 의미 혼란 때문에 금지(text 기본). “bpchar 형변환 때문에 인덱스 미사용”이라는 일괄 설명은 부정확하다. IDENTITY > serial. PK `bigint GENERATED ALWAYS AS IDENTITY` + 외부 노출용은 별도 uuid. 금액 `numeric`, 시각 `timestamptz`.
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

## psql 메타커맨드

- 타입 목록은 `\dT`. `\dT*`는 패턴 `*`가 붙은 형태로 search_path 상의 전체 타입, `\dT+`는 내부 크기·요소 타입·소유자·ACL·설명까지, `\dTS`는 내장 시스템 타입 포함, `\dT *.*`는 모든 스키마.
- `\dT*`가 동작하는 이유: psql이 백슬래시 커맨드명을 영숫자까지만 읽고 끊어 `\dT` + 인자 `*`로 파싱하기 때문. 같은 원리로 `\dt*`, `\dn*`도 성립.^[inferred]
- ENUM 라벨 확인은 `\dT+ <타입명>`, SQL로는 `pg_type` + `pg_enum` 조인.

## 발견된 위험·품질 이슈 (원본 교정 필요)

- pg_hba `0.0.0.0/0` 예시는 "보안그룹 위임" 전제가 빠진 채 복붙되면 위험.
- 성능튜닝 페이지의 MySQL 히트율 쿼리에 PG 전용 `FILTER (WHERE ...)` 문법 혼입 — MySQL에서 실행 불가.
- 도서 노트에 평문 패스워드 예제·오탈자 다수, 발행일/대상 버전 미기재.
- 실제 서비스명 추정 롤명이 포함된 원시 스크립트 페이지 존재(목적·롤백 설명 없음).
- 사용자 제공 메모의 `listen_addresses='*'` + HBA `0.0.0.0/0` 예시는 보안그룹 전제가 있어도 방어 계층을 줄이므로 프로비저닝 기본값으로 사용하지 않는다.^[inferred]
- 사용자 제공 메모의 MD5·`trust` 호환성 우회는 신규 구축 표준에서 제외한다. MD5는 폐기 예정이고 `trust`는 인증을 생략하므로, 클라이언트 업그레이드와 SCRAM 전환이 기본 조치다.

## Related

- [[db-common-concepts]] — 3사 비교 관점에서의 PG 위치
- [[operational-queries]] — 진단 쿼리 (읽기 전용)
- [[db-change-safe-patterns]] — `CONCURRENTLY` 인덱스, `lock_timeout` 가드, `NOT VALID` 2단계 제약, 청크 DELETE의 실행 골격
- [[db-permission-queries]] — `ALTER DEFAULT PRIVILEGES`·`search_path` 등록·계정 삭제 순서의 실제 명령
- [[db-access-control]] — 3-엔진 공통 계정 설계 표준
- [[monitoring-incident-runbook]] — wraparound 경보 대응 절차
- [[aurora-dsql]] — PG 호환이지만 VACUUM·파라미터 개념이 없는 분산 변종
- [[worklog-kakaogames-2026]] — forum DB search_path 적용 업무 기록
- [[postgresql-object-operations]] — 소유권·타입·DDL·인덱스·파티션·뷰·시퀀스 상세 런북

## Sources

- 사용자 제공 PostgreSQL 운영 메모 (2026-08-15)
- PostgreSQL 공식 문서, *Password Authentication*
- PostgreSQL 공식 문서, *Schemas*
- PostgreSQL 공식 문서, *Predefined Roles*
