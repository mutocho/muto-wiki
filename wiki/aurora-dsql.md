---
title: AWS Aurora DSQL — 분산 서버리스 PostgreSQL 호환 DB
tags: [dba, aws, aurora, dsql, architecture]
summary: Aurora DSQL 핵심 특성과 공식 한도 — OCC(SQLSTATE 40001) 앱 리트라이 필수, FK/Trigger/PL-pgSQL/TRUNCATE 미지원, 클러스터당 DB 1개·스키마 10개, 트랜잭션 3000행/10MiB/5분, DPU 과금.
sources:
  - "AWS Aurora DSQL 세미나 노트 (2026-08-04)"
  - "AWS Docs: Migrating from PostgreSQL to Aurora DSQL (https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility-migration-guide.html, 2026-08-04 확인)"
  - "AWS Docs: Cluster quotas and database limits (https://docs.aws.amazon.com/aurora-dsql/latest/userguide/CHAP_quotas.html, 2026-08-04 확인)"
  - "AWS Docs: Aurora DSQL and PostgreSQL (https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with.html, 2026-08-04 확인)"
  - "AWS Pricing: Amazon Aurora DSQL Pricing (https://aws.amazon.com/rds/aurora/dsql/pricing/, 2026-08-04 확인)"
category: db운영
status: verified
created: 2026-08-04
updated: 2026-08-15
notion_page_id: "3bdfb969-b8be-8125-a96b-cabce44b6c55"
notion_synced: "2026-08-15T19:21:54+0900"
---

> [!tip] 핵심 Takeaway
> - **DSQL 도입 검토의 첫 질문은 "앱이 리트라이를 할 수 있는가"다.** OCC이므로 `SQLSTATE 40001`이 정상 동작의 일부이고, **멱등 콜백 + 지수 백오프**가 전제다. 직접 짜지 말고 언어별 DSQL Connector를 쓴다. HikariCP를 쓴다면 `40001`을 커넥션 축출 사유로 보지 않게 `SQLExceptionOverride`로 `DO_NOT_EVICT` 처리한 뒤 그 위에 리트라이를 얹는 **2계층 구성**이 필요하다
> - **부적합 신호가 명확하다** — PL/pgSQL 저장 프로시저 의존, FK 기반 참조 정합성 의존, 3,000행 초과 벌크 DML, 5분 초과 장기 트랜잭션, 11개 이상 스키마. 하나라도 걸리면 마이그레이션 대상이 아니다 ^[inferred]
> - **스토리지는 무제한이 아니다 — 클러스터당 10 TiB 기본**(증액 시 256 TiB), 초과 시 `DISK_FULL(53100)`. 세미나 노트의 "제약 없음"은 오류였다
> - **비용은 IO가 아니라 DPU + 스토리지**다. DPU에는 통계 갱신·인덱스 유지보수 같은 백그라운드 작업도 포함된다. 유휴 시 DPU 0 (scale to zero)
> - **VACUUM·파라미터 튜닝·유지보수 윈도우 개념이 없다.** DBA 운영 부하가 구조적으로 사라지는 대신, 통제 수단도 함께 사라진다는 뜻
> - 미확인 항목 3건(Firecracker 1:1, buffer pool 부재, v2 PG18)은 세미나 발언뿐이다 — 인용 전 재확인 → [[verbal-source-verification-policy]]

# AWS Aurora DSQL

세미나 노트를 AWS 공식 문서로 대조한 결과. **아래 `^[세미나 발언]` 표시 항목만 공식 문서 미확인**이고 나머지는 문서 기반이다.

## 아키텍처

- 분산 DB. 멀티 리전 **multi-master(active-active)**에서 ACID 보장. 리전 내 **3개 AZ에 복제**되지만 과금은 리전당 논리 1부.
- 내부는 PostgreSQL이 아니지만 **PostgreSQL v3 wire protocol**을 그대로 써서 `psql`·`pgjdbc`·`psycopg` 등 표준 클라이언트/드라이버가 붙는다. **PG 16 기반.**
- 차기 v2는 PG 18 기반 예정.^[세미나 발언 — 공식 로드맵 미확인, 변동 가능]
- 커넥션당 Firecracker microVM 1:1 매칭.^[세미나 발언 — 공식 문서 미기재]
- **buffer pool 개념이 없어 모든 read가 disk에서 읽음.**^[세미나 발언 — 공식 문서 미기재]
- **VACUUM 불필요** — 스토리지 최적화·통계 수집·튜닝을 시스템이 자동 수행. 파라미터 튜닝·유지보수 윈도우 개념 없음.
- 자동 파티셔닝·자동 스케일링. tablespace 없음. 버전 업그레이드 다운타임 zero.
- MySQL용 DSQL 계획 없음.^[세미나 발언]

## 동시성 — 낙관적 락(OCC)

- 락을 걸지 않고 진행, **commit 시점에 충돌 감지**. 락 대기가 없으므로 **데드락이 발생하지 않고**, 느린 트랜잭션이 다른 트랜잭션을 막지 않는다.
- **격리수준은 PostgreSQL `Repeatable Read`로 고정** — 변경 불가. (세미나 노트엔 없던 항목)
- 충돌 시 **SQLSTATE `40001`** 직렬화 오류 반환. 두 갈래로 구분되며 앱 처리 방법은 동일(둘 다 일시적 → 재시도):
  - `OC000` — 데이터 충돌 (두 트랜잭션이 같은 행에 write)
  - `OC001` — 스키마 충돌 (동시 DDL, 예: async 인덱스가 트랜잭션 중 valid 전환)
- **앱에 리트라이 로직 필수.** 콜백은 **멱등(idempotent)**이어야 한다 — 충돌 시 여러 번 실행될 수 있다. 지수 백오프 + 지터가 표준.
- 각 언어 DSQL Connector가 OCC 리트라이 헬퍼를 제공(Go `occretry.WithRetry`, Node `AuroraDSQLPool.transaction`, PHP `occMaxRetries`) — 직접 짜지 말고 이걸 쓴다.
- **HikariCP 사용 시 주의**: `40001`을 커넥션 축출 사유로 보지 않게 `SQLExceptionOverride`로 `DO_NOT_EVICT` 처리 후, 그 위에 리트라이를 얹는 2계층 구성이 필요하다.
- 경합 최소화 설계: **랜덤 PK(UUID)로 키 범위 분산**. AWS는 분산 조율이 불필요해 insert 확장성이 좋다는 이유로 **PK 타입을 UUID로 권장**. 순차 ID가 필요하면 sequence/identity 컬럼은 `CACHE` 지정 시 지원.

## 미지원 기능 (앱 레이어로 이전 필요)

| 미지원 | 대안 |
|---|---|
| **FK 제약** (강제되지 않음) | 앱 레이어 검증. 부모 없는 자식 INSERT가 막히지 않으므로 명시적 존재 확인 필요 |
| **Trigger** | 앱 이벤트 로직, EventBridge, 앱 로깅 기반 audit trail |
| **PL/pgSQL 등 절차형 언어** | SQL 함수만 지원. 복잡한 로직은 앱 또는 Lambda |
| **TRUNCATE** | `DELETE FROM <table>`, 또는 `DROP TABLE` + `CREATE TABLE` |
| **임시 테이블** | CTE(`WITH`), 서브쿼리, 또는 고유 이름 실테이블 + 정리 로직 |
| **SAVEPOINT** | (SQLAlchemy psycopg dialect가 초기화에 사용 → `isolation_level="AUTOCOMMIT"`으로 회피) |
| **`CREATE INDEX`(동기)** | **`CREATE INDEX ASYNC`** — 대형 테이블 무중단 인덱스 생성 |
| **tablespace / 수동 스토리지 관리** | 자동 |

## 공식 한도

### 데이터베이스 한도

| 항목 | 한도 | 에러 코드 |
|---|---|---|
| **클러스터당 데이터베이스** | **1개** (내장 `postgres` 고정) | `unsupported statement` |
| 데이터베이스당 스키마 | **10개** | `54000` |
| 데이터베이스당 테이블 | 1,000개 | `54000` |
| 데이터베이스당 뷰 / 시퀀스 | 각 5,000개 | `54000` |
| 테이블당 컬럼 | 255개 | `54011` |
| 테이블당 인덱스 | 24개 | `54000` |
| PK·보조인덱스 컬럼 수 | 8개 | `54011` |
| PK·보조인덱스 키 결합 크기 | 1 KiB | `54000` |
| 행 크기 / 비인덱스 컬럼 크기 | 2 MiB / 1 MiB | `54000` |
| **트랜잭션 변경 행 수** | **3,000행** (보조 인덱스 수 무관, INSERT/UPDATE/DELETE 공통) | `54000` |
| **트랜잭션 변경 데이터 크기** | **10 MiB** | `54000` |
| **트랜잭션 최대 시간** | **5분** (`transaction age limit of 300s exceeded`) | `54000` |
| 쿼리 작업 메모리 | 128 MiB/트랜잭션 | `53200` |
| 메시지 크기 | 10 MiB | `08P01` |
| **커넥션 지속시간** | **60분 후 타임아웃** | — |

### 클러스터 쿼터 (계정·리전 단위)

| 항목 | 기본값 | 조정 |
|---|---|---|
| 단일 리전 클러스터 | 20개 | 가능 |
| 멀티 리전 클러스터 | 5개 | 가능 |
| **클러스터당 스토리지** | **10 TiB** (승인 시 최대 256 TiB) — `DISK_FULL(53100)` | 가능 |
| 클러스터당 커넥션 | 10,000 | 가능 |
| 신규 커넥션 rate | 100/초 (버스트 1,000) | 불가 |
| CDC 스트림 | 5개 | 불가 |

> **세미나 노트 수정** — "스토리지 크기 제약 없음"은 **부정확**. 무제한이 아니라 **10 TiB 기본 한도**이며 초과 시 `DISK_FULL(53100)`. 한도 증액은 가능(최대 256 TiB).

## 트랜잭션·스키마 제약 (마이그레이션 시 걸리는 부분)

- **DDL과 DML은 별도 트랜잭션**이어야 하고, **한 트랜잭션에 DDL은 1개**만.
- 인코딩 UTF-8 고정, **collation은 `C`만**, 시스템 타임존 **UTC** 고정(클라이언트 표시용 `TimeZone` 파라미터는 설정 가능).
- 권한은 **스키마 레벨 GRANT**로 관리. admin이 `CREATE SCHEMA` + `GRANT USAGE ON SCHEMA`, 비-admin은 사용자 생성 스키마에 객체를 만든다(public 스키마는 admin 소유).
- 인증은 **IAM 시간제한 토큰** — 각 언어 DSQL Connector가 토큰 생성·갱신을 처리.
- **DB가 1개뿐**이므로 논리 분리는 스키마(최대 10개) 또는 **클러스터를 나누는 것**으로 해결. 스키마 단위 분리 시 `search_path` 운영은 [[postgresql-operations]]의 PG 규칙과 동일하게 적용된다.^[inferred]

## 비용

- **DPU(Distributed Processing Unit) + 스토리지(GB-월)** 2요소.
- DPU는 compute·read·write·CDC 스트리밍을 **단일 정규화 단위로 통합**한 것. 사용자 SQL뿐 아니라 통계 갱신·인덱스 유지보수·auto ANALYZE 같은 백그라운드 작업도 포함된다.
- **유휴 시 DPU 0** — 스토리지만 과금. 인스턴스 시간 과금 없음(scale to zero).
- CloudWatch에서 DPU 구성요소별(compute/read/write/streaming) 분해 확인 가능. `TotalDPU`·`ClusterStorageSize` 알람 권장. `EXPLAIN ANALYZE VERBOSE`로 쿼리별 비용 인식.

> **세미나 노트 보정** — "비용 = IO + storage"는 방향은 맞지만 정확히는 **DPU + storage**. DPU가 compute까지 포함한 통합 단위다.

## 적용 판단

- OLTP 전용. **OLAP 성능은 나오지 않음.**^[세미나 발언]
- **단일 리전이라도 Write가 많은 워크로드면 해법이 될 수 있다.**^[세미나 발언]
- throughput은 높지만 멀티 리전 구성 시 write latency 증가 가능.^[세미나 발언]
- 커넥션 풀링 권장 — 커넥션 rate 100/초 한도와 60분 타임아웃 때문에 필수에 가깝다.
- **부적합 신호**: PL/pgSQL 저장 프로시저 의존, FK 기반 참조 정합성 의존, 3,000행 초과 벌크 DML 배치, 5분 초과 장기 트랜잭션, 11개 이상 스키마 필요.^[inferred]

## 공식 문서 링크

- [Aurora DSQL User Guide](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/)
- [Aurora DSQL and PostgreSQL (호환성 개요)](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with.html)
- [Migrating from PostgreSQL to Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility-migration-guide.html)
- [Cluster quotas and database limits](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/CHAP_quotas.html)
- [Endpoints and service quotas](https://docs.aws.amazon.com/general/latest/gr/dsql.html)
- [How billing works in Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/billing-metering.html)
- [Aurora DSQL 요금 페이지](https://aws.amazon.com/rds/aurora/dsql/pricing/)
- [System tables and commands](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-systems-tables.html)

## 미확인 / 후속 확인 필요

- Firecracker microVM 커넥션 1:1, buffer pool 부재, PG 18 기반 v2 로드맵 — **세미나 발언만 있고 공식 문서에서 확인 못했다.** AWS re:Invent 세션 자료나 아키텍처 블로그로 재확인 필요.
- 백업·PITR 절차, 모니터링 지표 세트, 기존 Aurora PostgreSQL → DSQL 실제 마이그레이션 경로(DMS 지원 여부)는 이 페이지 범위 밖 — 별도 조사 필요.
- 지원 데이터 타입 목록(`Supported data types in Aurora DSQL`) 미확인.

## Related

- [[cloud-platform-knowledge|클라우드·플랫폼 지식]]
- [[postgresql-operations|PostgreSQL 운영 지식]]
- [[db-common-concepts|DBMS 공통 개념·3사 비교]]
- [[operational-queries]] — PG 계열 진단 쿼리 (DSQL 미지원 항목 주의)
