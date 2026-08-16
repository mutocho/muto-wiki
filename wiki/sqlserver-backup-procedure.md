---
title: SQL Server 백업 프로시저 SP_DB_BACKUP — 결함 수정본
category: db운영
tags: [dba, sqlserver, backup, retention, security, runbook]
summary: 사내 SP_DB_BACKUP의 결함 5건(전역 삭제·xp_cmdshell 잔류·파싱 예외·무알람 실패·CHECKSUM 누락)을 수정한 버전. 파일명·디바이스명 형식은 유지해 기존 백업과 호환된다.
sources:
  - "사내 SQL Server 구축 표준 메모의 SP_DB_BACKUP v1.0 (2020-06-29 작성, 2026-08-15 적재)"
  - "결함 분석·수정은 자체 작성 — 공식 문서 대조 미완"
status: draft
created: 2026-08-15
updated: 2026-08-16
notion_page_id: "3bdfb969-b8be-8150-98d7-cbb893a9cd34"
notion_synced: "2026-08-15T22:55:00+0900"
---

> [!tip] 핵심 Takeaway
> - **삭제를 수행하는 운영 스크립트는 "무엇을 남기는가"가 아니라 "무엇에 매칭되는가"로 검토한다.** 원본의 최대 결함은 백업이 아니라 **정리 조건에 DB 식별자가 없던 것**이었다
> - **`LIKE`로 대상을 좁힐 때 식별자의 `_`·`%`·`[`를 이스케이프하지 않으면 범위가 넓어진다.** `ORDER_DB01` 같은 이름에서 `_`가 와일드카드로 동작한다 — 삭제 조건에서는 곧 오삭제
> - **보안 설정을 켰다 끄는 대신 켤 필요가 없는 API를 쓴다.** 폴더 생성은 `xp_cmdshell`이 아니라 `sys.xp_create_subdir`
> - **운영 프로시저의 오류는 `SELECT`이 아니라 `THROW`다.** Agent Job은 결과셋을 보지 않는다 — 무알람 실패는 곧 백업 공백
> - 이 페이지는 `draft`다. **개발/QA에서 정리 동작까지 검증한 뒤 운영 적용한다** — 특히 5단계 삭제 대상 조회를 `SELECT`으로 먼저 확인할 것

# SQL Server 백업 프로시저 — 결함 수정본

원본은 [[sqlserver-operations]]의 "구축 시 배포하는 운영 Job·프로시저" 절에 동작 흐름과
결함 목록이 정리돼 있다. 이 페이지는 그 결함을 실제로 고친 스크립트다.

## 결함 → 수정 매핑

| # | 원본 결함 | 수정 |
|---|---|---|
| 1 | 정리 조건이 `날짜 + 확장자`뿐이라 **다른 DB의 백업까지 삭제** | 디바이스명·물리경로·확장자 3중으로 대상 DB에 한정. 식별자의 LIKE 와일드카드는 `ESCAPE`로 무력화 |
| 2 | `xp_cmdshell`을 켜고 끄는 구간이 백업 전체를 감싸 **중단 시 켜진 채 잔류** | `sys.xp_create_subdir`로 교체. **보안 설정을 전혀 건드리지 않는다** |
| 3 | `CAST(LEFT(RIGHT(name,15),8) AS BIGINT)`가 **비정형 디바이스명에서 변환 오류** | 이름 패턴 검사 + `TRY_CONVERT` — 실패해도 `NULL`이라 조용히 제외된다 |
| 4 | 오류를 `SELECT`으로만 반환해 **Agent Job이 성공으로 끝남** | `THROW`. 백업 실패와 정리 실패를 **다른 메시지로 구분** |
| 5 | `CHECKSUM`이 `COMPRESSION`과 한 덩어리라 **비압축 백업은 체크섬 검증이 꺼짐** | `CHECKSUM`은 항상, `COMPRESSION`만 조건부 |

**호환성** — 백업 파일명(`<DB>_BACKUP_<YYYYMMDD>_<HHMMSS>.<ext>`)과 디바이스명 형식을
그대로 유지했다. 따라서 **기존에 쌓인 백업도 이 버전이 정리한다.** 형식을 바꿨다면
과거 파일이 영원히 남았을 것이다.

## 스크립트

```sql
USE master;
GO

CREATE OR ALTER PROC dbo.SP_DB_BACKUP
(
    @DB_NAME            SYSNAME         = NULL  --  백업할 DB명 (필수)
,   @PATH               NVARCHAR(200)   = NULL  --  백업 루트 경로 (필수, 환경별 지정)
,   @BACKUP_TYPE        CHAR(1)         = 'F'   --  F: FULL, L: LOG, D: DIFFERENTIAL
,   @MAINTENANCE_DAY    INT             = 30    --  보관 기간(일). 0이면 정리하지 않음
,   @IS_COMPRESS        TINYINT         = 1     --  백업 압축 여부
)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @INSTANCE_NAME   SYSNAME        = @@SERVICENAME
        ,   @FILE_NAME       NVARCHAR(300)  = N''
        ,   @FILE_EXTENSION  NVARCHAR(5)    = N''
        ,   @FOLDER_PATH     NVARCHAR(400)  = N''
        ,   @FULL_PATH       NVARCHAR(500)  = N''
        ,   @SQL             NVARCHAR(2000) = N''
        ,   @DATE            CHAR(8)
        ,   @TIME            CHAR(6)
        ,   @CUTOFF_DATE     DATE
        ,   @NAME_PATTERN    NVARCHAR(600)
        ,   @PATH_PATTERN    NVARCHAR(600)
        ,   @DEV_NAME        SYSNAME
        ,   @CLEANUP_FAILED  INT            = 0
        ,   @CLEANUP_TOTAL   INT            = 0;

    DECLARE @DEVICES TABLE (DEVICE_NAME SYSNAME PRIMARY KEY);

    /*------------------------------------------------------------------
        1. 파라미터 검증 — 잘못된 입력으로 백업이 "성공"하지 않게 한다
    ------------------------------------------------------------------*/
    IF @BACKUP_TYPE NOT IN ('F', 'L', 'D')
        THROW 50001, N'@BACKUP_TYPE은 F, L, D 중 하나여야 합니다.', 1;

    IF @PATH IS NULL OR LTRIM(RTRIM(@PATH)) = N''
        THROW 50002, N'@PATH는 필수입니다. 환경별 백업 경로를 지정하세요.', 1;

    --  동적 SQL로 들어가는 값이므로 따옴표를 원천 차단한다
    IF @PATH LIKE N'%' + CHAR(39) + N'%'
        THROW 50003, N'@PATH에 작은따옴표를 쓸 수 없습니다.', 1;

    IF @MAINTENANCE_DAY IS NULL OR @MAINTENANCE_DAY < 0
        THROW 50004, N'@MAINTENANCE_DAY는 0 이상이어야 합니다.', 1;

    --  DB명을 카탈로그에서 되찾아 온다. 이후 로직은 이 정규화된 이름만 쓴다
    SELECT  @DB_NAME = d.name
    FROM    sys.databases AS d
    WHERE   d.name = @DB_NAME
    AND     d.state_desc = N'ONLINE';

    IF @DB_NAME IS NULL
        THROW 50005, N'대상 DB가 없거나 ONLINE 상태가 아닙니다.', 1;

    --  SIMPLE 복구 모델에서 로그 백업은 불가능하다. 시도하면 실패가 아니라 오해를 남긴다
    IF @BACKUP_TYPE = 'L'
       AND EXISTS (SELECT 1 FROM sys.databases
                   WHERE name = @DB_NAME AND recovery_model_desc = N'SIMPLE')
        THROW 50006, N'SIMPLE 복구 모델 DB는 로그 백업을 할 수 없습니다.', 1;

    /*------------------------------------------------------------------
        2. 경로·파일명 구성  —  xp_cmdshell 을 쓰지 않는다
    ------------------------------------------------------------------*/
    SET @FILE_EXTENSION = CASE @BACKUP_TYPE WHEN 'L' THEN N'trn'
                                            WHEN 'D' THEN N'DIFF'
                                            ELSE          N'bak' END;

    IF RIGHT(@PATH, 1) <> N'\'  SET @PATH = @PATH + N'\';

    SELECT  @DATE = CONVERT(CHAR(8), GETDATE(), 112)
        ,   @TIME = REPLACE(LEFT(CONVERT(VARCHAR(12), GETDATE(), 114), 8), ':', '');

    SET @FOLDER_PATH = @PATH + @INSTANCE_NAME + N'\' + @DB_NAME + N'\';
    SET @FILE_NAME   = @DB_NAME + N'_BACKUP_' + @DATE + N'_' + @TIME;
    SET @FULL_PATH   = @FOLDER_PATH + @FILE_NAME + N'.' + @FILE_EXTENSION;

    BEGIN TRY
        --  결함 2 수정: 보안 설정을 바꾸지 않고 폴더를 만든다
        EXEC sys.xp_create_subdir @FOLDER_PATH;

        /*--------------------------------------------------------------
            3. 백업 실행 — 결함 5 수정: CHECKSUM 은 압축 여부와 무관하게 항상
        --------------------------------------------------------------*/
        SET @SQL = N'BACKUP '
                 + CASE WHEN @BACKUP_TYPE = 'L' THEN N'LOG' ELSE N'DATABASE' END
                 + N' ' + QUOTENAME(@DB_NAME)
                 + N' TO DISK = N''' + REPLACE(@FULL_PATH, N'''', N'''''') + N''''
                 + N' WITH INIT, NOFORMAT, NOSKIP, CHECKSUM'
                 + CASE WHEN @IS_COMPRESS = 1  THEN N', COMPRESSION'  ELSE N'' END
                 + CASE WHEN @BACKUP_TYPE  = 'D' THEN N', DIFFERENTIAL' ELSE N'' END;

        EXEC sys.sp_executesql @SQL;

        --  보관 관리용 레지스트리. 백업이 성공한 뒤에만 등록한다
        EXEC sys.sp_addumpdevice @devtype = 'disk'
                               , @logicalname = @FILE_NAME
                               , @physicalname = @FULL_PATH;
    END TRY
    BEGIN CATCH
        --  결함 4 수정: 결과셋이 아니라 오류로 올린다
        DECLARE @ERR NVARCHAR(2000) = N'BACKUP FAILED [' + @DB_NAME + N'/'
                                    + @BACKUP_TYPE + N'] ' + ERROR_MESSAGE();
        THROW 50010, @ERR, 1;
    END CATCH;

    /*------------------------------------------------------------------
        4. 보관 기간 경과분 정리
           결함 1 수정: 대상 DB·경로·확장자 3중으로 한정
           결함 3 수정: 이름 패턴 검사 + TRY_CONVERT
    ------------------------------------------------------------------*/
    IF @MAINTENANCE_DAY = 0  RETURN;   --  0 이면 정리하지 않는다

    SET @CUTOFF_DATE = DATEADD(DAY, -@MAINTENANCE_DAY, CAST(GETDATE() AS DATE));

    --  DB명·경로에 들어있는 LIKE 와일드카드(_ % [ \)를 무력화한다.
    --  이 처리를 빼면 `ORDER_DB01` 의 `_` 가 임의의 한 글자로 동작해 대상이 넓어진다
    SET @NAME_PATTERN =
        REPLACE(REPLACE(REPLACE(REPLACE(@DB_NAME, N'\', N'\\'), N'_', N'\_'),
                N'%', N'\%'), N'[', N'\[')
        + N'\_BACKUP\_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]\_[0-9][0-9][0-9][0-9][0-9][0-9]';

    SET @PATH_PATTERN =
        REPLACE(REPLACE(REPLACE(REPLACE(@FOLDER_PATH, N'\', N'\\'), N'_', N'\_'),
                N'%', N'\%'), N'[', N'\[')
        + N'%';

    INSERT INTO @DEVICES (DEVICE_NAME)
    SELECT  bd.name
    FROM    sys.backup_devices AS bd
    WHERE   bd.name                 LIKE @NAME_PATTERN ESCAPE N'\'   --  이 DB의 것만
    AND     bd.physical_device_name LIKE @PATH_PATTERN ESCAPE N'\'   --  이 폴더의 것만
    AND     bd.physical_device_name LIKE N'%.' + @FILE_EXTENSION     --  이 백업 타입만
    AND     TRY_CONVERT(DATE, SUBSTRING(bd.name, LEN(bd.name) - 14, 8), 112) < @CUTOFF_DATE;

    SELECT @CLEANUP_TOTAL = COUNT(*) FROM @DEVICES;

    WHILE EXISTS (SELECT 1 FROM @DEVICES)
    BEGIN
        SELECT TOP (1) @DEV_NAME = DEVICE_NAME FROM @DEVICES;

        BEGIN TRY
            --  DELFILE: 디바이스 등록과 실제 파일을 함께 삭제
            EXEC sys.sp_dropdevice @logicalname = @DEV_NAME, @delfile = 'DELFILE';
        END TRY
        BEGIN CATCH
            --  한 건 실패가 나머지 정리를 막지 않게 한다. 대신 끝에서 반드시 알린다
            SET @CLEANUP_FAILED += 1;
        END CATCH;

        DELETE FROM @DEVICES WHERE DEVICE_NAME = @DEV_NAME;
    END;

    /*------------------------------------------------------------------
        5. 정리 실패도 알린다 — 단 백업 성공과 구분되는 메시지로
    ------------------------------------------------------------------*/
    IF @CLEANUP_FAILED > 0
    BEGIN
        DECLARE @MSG NVARCHAR(2000) =
            N'BACKUP OK / CLEANUP FAILED [' + @DB_NAME + N'] '
          + CAST(@CLEANUP_FAILED AS NVARCHAR(10)) + N'/'
          + CAST(@CLEANUP_TOTAL  AS NVARCHAR(10)) + N' 건 삭제 실패. 백업 파일은 정상 생성됨.';
        THROW 50020, @MSG, 1;
    END;
END;
GO
```

## 배포 전 확인

1. **삭제 대상을 먼저 눈으로 본다.** 4단계의 `INSERT INTO @DEVICES ... SELECT`를 그대로
   `SELECT`으로 바꿔 실행해 **대상 DB의 파일만 잡히는지** 확인한 뒤 프로시저를 만든다.
   여기가 원본이 틀렸던 지점이고, 틀리면 되돌릴 수 없다
2. `sys.xp_create_subdir`은 **미문서화 확장 프로시저**다. Maintenance Plan이 내부적으로 쓰는
   것과 같으며 sysadmin 권한이 필요하다. 조직 정책상 미문서화 API가 금지라면
   **폴더를 사전 생성하고 이 호출을 제거**한다 — 그래도 `xp_cmdshell`로 되돌리지는 않는다
3. Agent Job 스텝에서 호출할 때 **`@PATH`를 반드시 넘긴다.** 기본값을 제거해서 빠뜨리면
   에러가 나도록 했다 — 조용히 엉뚱한 경로에 쌓이는 것보다 낫다
4. 기존 `dbo.SP_DB_BACKUP`을 `CREATE OR ALTER`로 덮으므로 **원본을 먼저 스크립트로 백업**해 둔다

## 남긴 설계 결정

- **덤프 디바이스를 보관 레지스트리로 계속 쓴다.** `msdb.dbo.backupset` 기반이 더 정확하지만,
  바꾸면 **기존에 쌓인 백업 파일을 정리할 수단이 사라진다.** 호환을 우선했다
- **`WITH INIT`을 유지했다.** 파일명이 초 단위로 유일해 실제로 덮어쓸 일은 거의 없다
- **백업 검증(`RESTORE VERIFYONLY`)은 넣지 않았다.** 결함 수정 범위를 넘고, 대용량 DB에서
  백업 창을 두 배로 늘린다. 별도 검증 Job으로 분리하는 것이 맞다 ^[inferred]

## Open Questions

- **같은 DB·같은 타입을 1초 안에 두 번 실행하면 디바이스명이 충돌한다.** 파일명에 백업 타입
  구분자가 없어 FULL과 LOG가 같은 초에 실행돼도 이름이 겹친다. 실사용에서 발생 가능한
  시나리오인지 확인 필요 — 필요하면 파일명 형식을 바꿔야 하고, 그러면 호환성을 잃는다
- **`sp_addumpdevice`로 등록된 디바이스가 `master`에 계속 쌓인다.** 정리에서 누락된 항목이
  영구 잔존하는데, 상한이나 정리 주기가 정해져 있지 않다
- 이 수정본은 **작성만 했고 실행 검증 전이다.** `status: draft` 유지 근거 →
  [[verbal-source-verification-policy]]

## Related

- [[sqlserver-operations]] — 원본 프로시저의 동작 흐름과 결함 목록, 그리고 이 프로시저를
  배포하는 신규 인스턴스 구축 표준
- [[db-security-review-patterns]] — 결함 1·2·4는 이 체크리스트의 항목으로 등록돼 있다.
  삭제 조건 식별자 누락, 보안 설정 토글, `SELECT` 오류 반환
- [[db-change-safe-patterns]] — 같은 "변경 명령" 등급. **개발/QA 검증 후 운영 승격**이라는 취급이 동일하다
- [[db-access-control]] — `xp_cmdshell`·sysadmin 권한을 어디까지 허용할지의 기준
- [[sqlserver-xevent-sessions]] — 같은 구축 표준으로 함께 배포되는 진단 세션. 백업과 달리 파괴적 단계가 없어 검증 부담이 낮다
- [[verbal-source-verification-policy]] — 사내 프로시저 출처라 결함 5건 수정본도 실행 검증 전까지 `draft`인 근거
