---
title: SQL Server 운영 지식 — 구축 표준·VLF·스니핑·HA·버전
category: db운영
tags: [dba, sqlserver, performance, ha, version, provisioning, backup]
summary: 신규 인스턴스 구축 표준(Collation·TempDB·sp_configure·Trace flag), 에러로그 순환 Job과 백업 프로시저 및 그 결함, VLF 관리, Parameter Sniffing 대응 우선순위, 성능 카운터 현대 기준값, AG vs FCI, 2019/2022/2025 비교.
sources:
  - "Notion: SQL Server 지식 인덱스 트리 (2026-07-30)"
  - "사내 SQL Server 구축 표준 메모 (2026-08-15 적재) — 설치 단계·sp_configure·Trace flag·에러로그 Job·SP_DB_BACKUP·XEvent"
status: draft
created: 2026-08-04
updated: 2026-08-15
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **구축 표준의 `sp_configure` 값은 두 종류로 갈린다.** backup compression·blocked process threshold 5s·optimize for ad hoc·DAC는 **전 인스턴스 하드코딩 가능**. MAXDOP·min/max memory·fill factor는 **환경 종속이라 복붙 금지** — 프로비저닝 자동화에서 이 둘을 반드시 분리한다
> - **`SP_DB_BACKUP`은 현 상태로 자동 스케줄 금지.** 보관 정책이 DB별이 아니라 **확장자 기준 전역**이라 한 DB의 백업 실행이 다른 DB의 백업 파일을 지운다. 수정 전에는 수동 실행만
> - **일상 백업 절차 안에서 `xp_cmdshell`을 켰다 끈다** — 중단되면 켜진 채 남는다. [[db-security-review-patterns]]의 "일상 절차에 보안 상태 변경 혼입" 패턴에 정확히 해당
> - **`TRUSTWORTHY ON`은 권한 상승 경로다.** DB 소유자가 sysadmin이면 db_owner가 인스턴스 전체를 장악할 수 있다. `EXECUTE AS OWNER`가 실제로 필요한 DB에만, 소유자를 확인하고 켠다
> - **PLE 300초는 구식 기준이다.** 현대 서버는 1,000~3,000초+. 옛 임계치를 그대로 쓰는 알람은 상시 오탐이거나 상시 무탐이다
> - **Parameter Sniffing 대응은 순서가 있다**: 쿼리 재작성 → PSP 최적화(2022+) → `OPTION(RECOMPILE)`/`OPTIMIZE FOR` → 로컬 변수 → 전역 설정. 전역부터 손대면 다른 쿼리가 망가진다
> - **AG는 DB 단위, FCI는 인스턴스 단위**(로그인·Job 포함 페일오버). HA 설계 문의의 첫 질문
> - **SQL Server 2016 연장 지원이 2026-07-15에 종료됐다.** 잔존 인스턴스 조사가 지연된 과제

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

## 신규 인스턴스 구축 표준

### 설치 단계

| 항목 | 표준값 | 비고 |
|---|---|---|
| Collation | `Latin1_General_CI_AS_KS` | 한글 정렬 관점의 적정성은 미확인 → Open Questions |
| 볼륨 유지 관리 작업 권한 | DB 엔진 서비스 계정에 부여 | 즉시 파일 초기화(IFI). **2016부터 설치 마법사에서 지정 가능** |
| 인증 모드 | 혼합 모드 | 설치 후 `ALTER LOGIN sa DISABLE` + 명명 관리자 계정(CHECK_POLICY/EXPIRATION ON, 비밀번호는 시크릿 저장소 주입) |

**TempDB** — 데이터 파일은 데이터 볼륨, 로그 파일은 로그 볼륨으로 분리한다.

| 파일 | 개수 | 초기 크기 | 자동 증가 |
|---|---|---|---|
| mdf | 8 | 500 MB | 100 MB |
| ldf | 1 | 2,000 MB | 100 MB |

> mdf 8개는 **코어 수 기준 상한**이다. 8코어 미만 장비에 그대로 적용하지 않는다 —
> 코어 수와 같게(최대 8) 잡는 것이 기준이다.^[inferred]
> ldf는 2022부터 64 MB 단위 증가 제한을 지원한다.

### DB 단위 옵션

- **`AUTO_UPDATE_STATISTICS_ASYNC` ON** 권장 — 통계 갱신을 비동기로 처리해 갱신 대기로 인한 쿼리 지연을 없앤다.
  `AUTO_UPDATE_STATISTICS`가 ON이어야 의미가 있고, 갱신 완료 전 쿼리는 **낡은 통계로 컴파일**된다.^[inferred]
- **`TRUSTWORTHY` ON** — `EXECUTE AS OWNER`를 쓸 때 필요하지만 **권한 상승 경로**다.
  DB 소유자가 sysadmin이면 해당 DB의 db_owner가 인스턴스 전체 권한을 얻는다.
  **실제로 필요한 DB에만, 소유자를 확인하고 켠다** → [[db-security-review-patterns]], [[db-access-control]]

### sp_configure

**전 인스턴스 공통으로 박아도 되는 값**:

```sql
EXEC sp_configure 'backup compression default', 1;      -- 백업 압축
EXEC sp_configure 'blocked process threshold (s)', 5;   -- 5초 이상 블로킹 보고서
EXEC sp_configure 'optimize for ad hoc workloads', 1;   -- 2회 실행 시에만 플랜 캐시 적재
EXEC sp_configure 'remote admin connections', 1;        -- DAC 원격 접속
```

**환경 종속 — 값을 그대로 복붙하면 안 되는 것**:

| 옵션 | 메모의 값 | 주의 |
|---|---|---|
| `max degree of parallelism` | 1 | OLTP에서 느린 쿼리 하나가 전 CPU를 점유하는 것을 막으려는 선택. 배치·리포팅이 섞인 인스턴스에는 부적합 |
| `min/max server memory (MB)` | 4096 / 4096 | **장비 메모리 기준으로 산정한다.** min=max는 의도된 고정 방식 |
| `fill factor (%)` | 90 | 인스턴스 전역 기본값. 모든 인덱스가 10% 공간을 비우게 되므로 인덱스 단위 지정이 원칙 ^[inferred] |
| `clr enabled` | 1 | **필요할 때만.** 공격 표면이 늘어난다 |

`show advanced options`는 작업 전 1, 작업 후 0으로 되돌린다. `RECONFIGURE WITH OVERRIDE` 동반.

### Trace flag

| 플래그 | 용도 | 상태 |
|---|---|---|
| 1204 | 데드락을 에러로그에 기록 | 사용 |
| 1222 | 데드락을 XML 형식으로 기록 | 사용 — 단 `system_health`가 이미 deadlock graph를 잡는다 → [[sqlserver-xevent-sessions]] |
| 3226 | **백업 성공** 메시지를 에러로그에 남기지 않음 | 사용 — 로그 노이즈 제거 |
| ~~845~~ | Lock pages in memory 활성화 | **불필요** — 2012부터 기본 활성 |
| ~~1118~~ | 혼합 익스텐트 대신 단일 익스텐트 할당 강제 | **불필요** — 2016부터 DB 옵션 `MIXED_PAGE_ALLOCATION`으로 제어하며 기본값 OFF(항상 단일 익스텐트) |

- 영구 적용은 **구성 관리자 → 시작 매개 변수**에 `-T1204` 형태로 추가
- 서비스 중 임시 적용은 `DBCC TRACEON(1204, -1)` — `-1`이 전역 범위

### 기타

- DTC는 필요 시에만 + `XACT_ABORT ON` 필수 (원격 오류는 로컬 TRY CATCH에 안 잡힘).
- Ghost Record: 인덱스 리프 삭제는 마크 후 지연 삭제. 대량 삭제 루프 시 블로킹 가능 (TF661은 공간 미회수 부작용 — 신중).

## 구축 시 배포하는 운영 Job·프로시저

### 에러로그 주간 순환 (`DB_Error_Log_Initialization`)

`msdb`에 SQL Agent Job을 만들어 **매주 월요일 22:00에 `sp_cycle_errorlog`**를 실행한다.
순환하지 않으면 에러로그 파일 하나가 무한정 커져 장애 시 열리지 않는다.

- 스텝: `EXEC sp_cycle_errorlog` (`@database_name = master`, `@subsystem = TSQL`)
- 스케줄: `@freq_type=8`(주간), `@freq_interval=2`(월요일), `@freq_recurrence_factor=1`
- 실패 시 Job 실패 처리(`@on_fail_action=2`), 전체를 `TRY/CATCH` + 명시 트랜잭션으로 감싸 부분 생성 방지
- **소유자(`@owner_login_name`)는 배포 환경의 관리 계정으로 치환한다** — 개인 계정으로 두면 퇴사·권한 회수 시 Job이 죽는다

> 기본 보관 개수는 6개다. 주간 순환이면 약 6주치만 남는다 — 더 필요하면
> `NumErrorLogs` 레지스트리 값을 함께 올려야 한다.^[inferred]

### 백업 프로시저 (`master.dbo.SP_DB_BACKUP`)

DB명·경로·백업 타입(F/L/D)·보관일수·압축 여부를 받아 백업하고, 보관 기간이 지난 백업을
**덤프 디바이스와 파일까지 함께 삭제**하는 프로시저. 동작 흐름:

1. `xp_cmdshell` 활성화 → `mkdir <경로>\<인스턴스>\<DB>\` → 폴더 생성
2. 파일명 `<DB>_BACKUP_<YYYYMMDD>_<HHMMSS>.<bak|trn|DIFF>` 생성
3. `BACKUP DATABASE/LOG ... WITH INIT, NOFORMAT, NOSKIP [,COMPRESSION, CHECKSUM] [,DIFFERENTIAL]`
4. `sp_addumpdevice`로 디바이스 등록 (보관 관리용 레지스트리로 사용)
5. `master.dbo.sysdevices`에서 이름의 날짜가 보관 기한보다 오래된 항목을 찾아
   `sp_dropdevice @name, 'DELFILE'` — **디바이스와 실제 파일을 함께 삭제**
6. `xp_cmdshell` 비활성화

> [!warning] 현 상태로 자동 스케줄에 걸지 말 것 — 결함 4건
>
> 1. **보관 정책이 DB별이 아니라 확장자 기준 전역이다.** 5단계의 조건이
>    `날짜 < 기준일 AND phyname LIKE '%.bak'` 뿐이고 **`@DB_NAME` 필터가 없다.**
>    보관 30일로 A DB를 백업하면 보관 90일로 운영하던 B DB의 60일 된 백업 파일까지 지워진다.
>    → 삭제 조건에 DB명·인스턴스명을 반드시 추가해야 한다
> 2. **`xp_cmdshell`을 켜고 끄는 구간이 백업 전체를 감싼다.** 실행이 중단되면(클라이언트 취소·`KILL`)
>    마지막 비활성화가 실행되지 않아 **인스턴스 전역에 켜진 채 남는다.**
>    → 폴더는 사전 생성하거나 Agent의 CmdExec 스텝으로 분리한다
> 3. **디바이스 이름 파싱이 예외에 취약하다.** `CAST(LEFT(RIGHT(name,15),8) AS BIGINT)`는
>    날짜 패턴이 아닌 기존 덤프 디바이스가 하나라도 있으면 변환 오류를 낸다.
>    확장자 필터가 먼저 평가된다는 보장이 없다 → 정리 단계가 조용히 실패한다 ^[inferred]
> 4. **오류를 `SELECT`으로만 반환한다.** Agent Job에서 호출하면 성공으로 끝나
>    **백업 실패가 알람되지 않는다.** → `THROW` 또는 `RAISERROR`로 승격 필요
>
> 원문 주석에도 모순이 있다 — 파라미터 정의는 `@MAINTENANCE_DAY`를 "보관 기간(일)"이라 하고
> 하단 호출 예제는 "유지 주기(시간)"이라 한다. `DATEADD(DAY, ...)`를 쓰므로 **일이 맞다.**^[ambiguous]

경로·DB명·계정은 배포 환경 값으로 치환해 쓴다. 원본 스크립트 전문은 위키에 남기지 않는다 —
실 서비스 DB명·인스턴스 번호가 박혀 있다 (§9-2).

**위 5건을 고친 배포용 스크립트는 [[sqlserver-backup-procedure]]에 있다.**
파일명·디바이스명 형식을 유지해 기존 백업과 호환되므로, 원본을 그대로 대체할 수 있다.
단 실행 검증 전이므로 정리 단계의 삭제 대상을 `SELECT`으로 먼저 확인하고 적용한다.

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

## Open Questions

- **데드락이 최대 3중으로 기록된다.** 여기 Trace flag 1204/1222(에러로그) + `system_health`(기본
  제공, deadlock graph 포함) + 선택적 전용 XEvent 세션. 1204/1222를 유지할지 정리 대상이다.^[inferred]
- **Collation `Latin1_General_CI_AS_KS`가 한글 데이터에 적정한지 미확인.**
  `NVARCHAR`면 저장은 무관하나 **정렬·비교는 Latin1_General 규칙**을 따른다.
  `KS`(kana sensitive)는 일본어 가나 구분 옵션이라 한글과 직접 관계가 없다.
  기존 인스턴스와의 호환 때문에 굳어진 값인지, 신규에도 유지할 값인지 확인 필요.^[inferred]
- **`SP_DB_BACKUP` 수정본이 실행 검증 전이다.** 스크립트는 [[sqlserver-backup-procedure]]에
  작성돼 있으나 개발/QA에서 정리 동작까지 확인한 뒤 운영에 적용해야 한다.

## Related

- [[db-common-concepts]] — 3사 비교 관점에서의 SQL Server 위치
- [[operational-queries]] — 대기 통계·블로킹 등 진단 쿼리
- [[db-access-control]] — 고정 롤 대신 사용자 정의 Role을 쓰는 근거
- [[cloud-platform-knowledge]] — Azure Blob 백업 절차와 TDE 주의사항
- [[db-security-review-patterns]] — 인덱스 리빌드·Database Mail 위험 패턴
