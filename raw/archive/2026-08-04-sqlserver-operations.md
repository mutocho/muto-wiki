---
title: SQL Server 운영 지식 — VLF·스니핑·HA·버전 (Notion 심층 수집)
tags: [dba, sqlserver, performance, ha]
topics: [dba]
summary: >-
  VLF 관리, Parameter Sniffing 대응 우선순위, 성능 카운터 현대 기준값, Always On AG vs FCI,
  설치·설정 표준, 2019/2022/2025 버전 비교, T-SQL 실무 패턴.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: SQL Server 지식 인덱스 트리 (https://app.notion.com/p/b68d9685b7c84da2b25d9f1e2877ab60, 2026-07-30)"
---

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

- 혼합 모드 후 `ALTER LOGIN sa DISABLE` + 명명 관리자 계정(CHECK_POLICY/EXPIRATION ON, 비밀번호는 시크릿 저장소 주입).
- TempDB mdf 파일 코어 수 기준 최대 8개. 즉시 파일 초기화(2016+ 설치 옵션, ldf는 2022부터 64MB 제한 지원).
- sp_configure: backup compression 1, blocked process threshold 1s, optimize for ad hoc 1, DAC 1, min=max server memory. (MAXDOP·메모리 값은 환경별 — 문서의 고정값 복붙 금지.)
- Trace flag 1204/1222(데드락 로그), 3226(백업 성공 로그 억제). 845/1118은 현대 버전 불필요.
- DTC는 필요 시에만 + `XACT_ABORT ON` 필수 (원격 오류는 로컬 TRY CATCH에 안 잡힘).
- Ghost Record: 인덱스 리프 삭제는 마크 후 지연 삭제. 대량 삭제 루프 시 블로킹 가능 (TF661은 공간 미회수 부작용 — 신중).

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
