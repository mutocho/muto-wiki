---
title: SQL Server 운영 지식 — VLF·스니핑·HA·버전
category: db운영
tags: [dba, sqlserver, performance, ha, version]
summary: VLF 관리, Parameter Sniffing 대응 우선순위, 성능 카운터 현대 기준값, Always On AG vs FCI, 설치·설정 표준, 2019/2022/2025 버전 비교, T-SQL 실무 패턴.
sources: ["Notion: SQL Server 지식 인덱스 트리 (2026-07-30)", "Microsoft Learn: Server memory configuration options", "Microsoft Learn: Configure MAXDOP", "Microsoft Learn: tempdb database", "Microsoft Learn: Database instant file initialization"]
status: draft
created: 2026-08-04
updated: 2026-08-15
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - 신규 설치는 버전·에디션·RPO/RTO를 먼저 확정하고, 설치 직후 **CU·메모리 상한·TempDB·백업 복구 테스트**를 배포 게이트로 검사한다
> - `min server memory = max server memory`로 고정하지 않는다. `min=0`에서 시작하고, `max`는 OS·백업 버퍼·에이전트·동일 호스트의 다른 인스턴스가 쓸 메모리를 제외해 산정한다
> - MAXDOP·Cost Threshold·TempDB 크기는 고정값을 복붙하지 말고 NUMA/CPU 구조와 실제 대기 통계로 검증한다
> - Parameter Sniffing은 쿼리 재작성 → PSP(2022+) → 쿼리 단위 힌트 순으로 대응하고, 인스턴스 전역 변경은 최후에 한다

# SQL Server 운영 지식

## VLF·로그 관리

- 잦은 소량 자동 증가가 VLF 과다 유발 → 초기 크기·증가 단위를 규모/복구모델/백업주기 기준으로 산정 (고정 표준값 금지).
- 로그 재사용 대기 원인(로그 백업 미실행, 오픈 트랜잭션 — `DBCC OPENTRAN`) 병행 확인. VLF 수는 `dm_db_log_info`.

## Parameter Sniffing

파라미터는 히스토그램, 로컬 변수는 평균 선택도 사용. 대응 우선순위: 쿼리 재작성 → PSP 최적화(2022+) → `OPTION(RECOMPILE)`/`OPTIMIZE FOR` → 로컬 변수 → 전역 설정은 최후.

## 성능 카운터 현대 기준값 (기준선 보정 전제)

- PLE: 현대 서버 1,000~3,000초+ (**300초는 구식 기준**). Buffer Cache Hit 99%+.
- Memory Grants Pending = 0. CPU 80%+ 지속 의심. Compilations/sec는 Batch Requests의 10~20% 미만.
- 디스크 read/write 5ms 우수, 20ms+ 병목. Processes blocked 지속 시 심각.
- CPU 100% 대응: Top SQL 교차 확인 → 통계 갱신/Query Store force last good plan → CXPACKET이면 MAXDOP·Cost Threshold → 컴파일 폭주면 OPTIMIZE FOR AD HOC + 파라미터화. Deadlock graph는 system_health XE에서 추출.

## Always On

- AG: DB 단위, 공유 스토리지 불필요, 리스너·읽기 라우팅, 동기=무손실/비동기=DR. Basic AG는 Standard에서 2복제본/1DB.
- FCI: 인스턴스 단위, 공유 스토리지, 로그인·Job 포함 페일오버.

## 설치·설정 표준

### 1. 설치 전 결정

- 지원 수명과 기능 요구로 버전·에디션을 확정하고 최신 CU 적용 계획을 포함한다.
- 데이터, 로그, TempDB, 백업 경로와 예상 용량·IOPS·증가 단위를 사전에 정한다. 데이터와 로그의 장애 영역을 가능하면 분리한다.
- 전용 저권한 서비스 계정을 사용하고 필요한 기능(Database Engine, Agent, Full-Text 등)만 설치한다. DTC, CLR, `xp_cmdshell`, FILESTREAM은 요구가 있을 때만 활성화한다.
- 인증은 Windows 인증을 우선한다. 혼합 모드가 필요하면 `sa`를 비활성화하고 명명 관리자 계정과 비밀 저장소를 사용한다.

### 2. 설치 직후 기준선

- 데이터 파일 즉시 초기화(IFI)를 활성화한다. 이는 데이터 파일 생성·증가를 빠르게 하지만 삭제된 영역이 초기화되지 않으므로 물리 디스크 접근 통제를 병행한다. 일반적인 로그 증가는 IFI 대상이 아니며 SQL Server 2022+의 64MB 이하 로그 증가만 예외다.
- `max server memory (MB)`는 `총 RAM - OS - SQL Server 외부 할당 - 에이전트/백업/보안 제품 - 다른 인스턴스`로 시작값을 산정한다. Microsoft의 단일 인스턴스 간이 시작점은 다른 프로세스가 쓰지 않는 가용 메모리의 약 75%이며, `min server memory (MB)`는 특별한 검증 근거가 없으면 기본값 0을 유지한다. `min`과 `max`를 같거나 가깝게 두지 않는다.
- MAXDOP는 NUMA 노드별 논리 CPU 수를 기준으로 시작한다. 단일 NUMA가 8 CPU 이하면 그 이하, 8 초과면 8을 일반 시작점으로 삼되, NUMA 경계를 넘지 않도록 하고 `CXPACKET`/`CXCONSUMER`, 처리량, 응답시간으로 재검증한다.
- `cost threshold for parallelism`은 기본값 5를 운영 표준으로 간주하지 않는다. 대표 워크로드를 계측해 단계적으로 조정하며 MAXDOP와 함께 검증한다.
- `tempdb` 데이터 파일은 논리 CPU가 8개 이하면 CPU 수만큼, 초과면 8개로 시작한다. 모든 데이터 파일의 초기 크기와 고정 MB 증가량을 같게 하고 정상 피크를 수용하도록 미리 할당한다. PAGELATCH 경합이 지속될 때만 4개씩 늘린다.
- 백업 압축 기본값, 원격 DAC, `optimize for ad hoc workloads`는 운영 정책과 워크로드에 맞춰 활성화한다. `blocked process threshold`는 모니터링 수집 주기와 정상 트랜잭션 시간을 근거로 정하며 1초를 무조건 표준화하지 않는다.

### 3. 데이터베이스 기본 정책

- 복구 모델은 RPO에 맞춘다. FULL/BULK_LOGGED이면 전체 백업만으로 끝내지 말고 로그 백업 주기와 체인 모니터링을 함께 배포한다.
- 데이터·로그 파일의 초기 크기와 자동 증가는 백분율이 아닌 고정 MB로 설정하고, 예상 피크를 사전 할당한다. 자동 증가는 용량 계획의 대체재가 아니라 비상 안전망이다.
- Query Store 활성화 여부와 보존 기간을 정하고, 애플리케이션 호환성 검증 후 database compatibility level을 목표 버전에 맞춘다.
- 사용자·서비스 계정은 최소 권한의 사용자 정의 Role로 부여한다. 세부 원칙은 [[db-access-control]]을 따른다.

### 4. 운영 인수 조건

- 전체·차등·로그 백업이 목적지에 생성되는지만 보지 말고 별도 검증 환경에서 실제 복원하여 RPO/RTO를 측정한다.
- SQL Server Agent 작업, Database Mail/알림, CHECKDB, 백업 실패, 디스크 여유, 파일 자동 증가, 장기 실행·블로킹·데드락 수집을 모니터링에 연결한다. 공통 진단 쿼리는 [[operational-queries]]에 둔다.
- 설치 설정을 코드화하고 `sys.configurations`, `sys.database_files`, 백업 이력, 서비스 계정 권한을 수집해 기대값과 비교한다. 비밀번호·접속 문자열은 결과에 저장하지 않는다.
- 배포 전 연결 암호화와 인증서 신뢰 체인을 실제 클라이언트에서 검증하고, 고정 포트와 방화벽 규칙은 필요한 출발지에만 허용한다.

- DTC는 필요 시에만 활성화하고 분산 트랜잭션 코드에는 `SET XACT_ABORT ON`을 적용한다.
- Ghost Record는 인덱스 리프 삭제 후 지연 정리된다. 대량 삭제 루프의 블로킹을 관찰하며 TF661은 공간 미회수 부작용 때문에 자동 적용하지 않는다.

## 버전 비교

- **2019(15.x)**: IQP(스칼라 UDF 인라이닝, Batch Mode on Rowstore), ADR, TempDB 메타데이터 메모리 최적화, OPTIMIZE_FOR_SEQUENTIAL_KEY, UTF-8.
- **2022(16.x)**: PSP 최적화, Query Store 기본 활성+Hints, Ledger, S3 호환 백업, GENERATE_SERIES/DATE_BUCKET, Standard Resource Governor.
- **2025(17.x, 2025-11 GA)**: VECTOR 타입+DiskANN, 네이티브 JSON 타입+인덱스, T-SQL RegEx, Optimized Locking(TID+LAQ), ZSTD 백업 압축.
- 2017부터 SP 폐지(CU+GDR). **SQL Server 2016 연장 지원 2026-07-15 종료** — ESU 또는 업그레이드 필요.

## T-SQL 실무 패턴

- NOLOCK 위험 → RCSI 권장. MERGE는 동시성 버그로 운영 비권장 → UPDLOCK+HOLDLOCK 패턴.
- SCOPE_IDENTITY/OUTPUT 절. Key Lookup 다발 시 INCLUDE 인덱스. 테이블 변수(행 1 추정) vs #temp. 청크 DELETE는 `DELETE TOP(n)` 루프.

## 발견된 위험·품질 이슈 (원본 교정 필요)

- 조각화율만으로 전체 대상 `REBUILD WITH (MAXDOP=0, SORT_IN_TEMPDB=ON)` 생성하는 스크립트 — ONLINE 옵션 없음, 임계·기준 미기재 → 자동 실행 금지.
- `sys.sysprocesses WHERE blocked > 50` 단편 메모 — blocked는 SPID이지 임계치가 아님(오독 유발).
- 성능 카운터·Always On 문서에 AI 대화 잔재, 설치 문서 첨부 미완, sp_configure의 환경 종속 값이 표준처럼 기재.

## Related

- [[db-common-concepts]] — 3사 비교 관점에서의 SQL Server 위치
- [[operational-queries]] — 대기 통계·블로킹 등 진단 쿼리
- [[db-access-control]] — 고정 롤 대신 사용자 정의 Role을 쓰는 근거
- [[cloud-platform-knowledge]] — Azure Blob 백업 절차와 TDE 주의사항
- [[db-security-review-patterns]] — 인덱스 리빌드·Database Mail 위험 패턴

## Sources

- Microsoft Learn, *Server memory configuration options*
- Microsoft Learn, *Server configuration: max degree of parallelism*
- Microsoft Learn, *tempdb database*
- Microsoft Learn, *Database instant file initialization*
