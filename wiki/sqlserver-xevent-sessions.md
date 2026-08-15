---
title: SQL Server XEvent 세션 표준 — 느린 쿼리·블로킹·오류·데드락
category: db운영
tags: [dba, sqlserver, xevent, monitoring, provisioning]
summary: 신규 인스턴스에 배포하는 Extended Events 세션 3종 정의. system_health와 중복되는 부분을 걷어내고 필터·타깃·보관 상한을 확정. 데드락은 별도 세션 불필요(보관 연장 목적만 예외).
sources:
  - "사내 SQL Server 구축 표준 메모의 'XEvent 설정' 항목 (수집 대상 4종만 기재, 2026-08-15 적재)"
  - "MS Learn: Use the system_health session (https://learn.microsoft.com/en-us/sql/relational-databases/extended-events/use-the-system-health-session, 2026-08-15 확인)"
  - "세션 정의·임계값은 자체 작성 — 실행 검증 전"
status: draft
created: 2026-08-15
updated: 2026-08-15
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **데드락 전용 세션을 만들지 마라.** `system_health`가 이미 deadlock graph를 잡는다. 별도 세션의 유일한 정당한 이유는 **보관 기간 연장**뿐이다
> - **블로킹은 반대다 — `system_health`에 `blocked_process_report`가 없다.** 반드시 별도 세션이며, `sp_configure 'blocked process threshold (s)'`가 0보다 커야 이벤트 자체가 발생하지 않는다
> - **오류 수집은 severity만으로 거르면 안 된다.** `system_health`는 sev ≥ 20만 잡고, 가장 중요한 I/O 경고(825)는 **severity 10**이라 severity 필터를 통과하지 못한다 — 오류 번호를 명시 열거한다
> - **XEvent 보관은 시간이 아니라 용량이다.** `max_file_size × max_rollover_files`가 하드 상한이므로 **바쁜 날일수록 보관 시간이 짧아진다.** 사후 분석을 전제한다면 커버 시간을 계산해 감시할 것
> - **`EVENT_RETENTION_MODE = NO_EVENT_LOSS`는 절대 쓰지 않는다.** 이벤트 유실을 막으려다 엔진을 멈춘다

# SQL Server XEvent 세션 표준

원본 구축 메모에는 수집 대상 4종(slow query, blocked process, deadlock, error log)만 있고
**필터·타깃·보관 정책이 없었다.** 이 페이지가 그 빈칸을 채운 배포용 정의다.
구축 표준 전체 맥락은 [[sqlserver-operations]].

## 먼저 — `system_health`와 무엇이 겹치는가

`system_health`는 기본 제공되며 인스턴스 시작과 함께 자동 실행된다.
**중복 수집은 디스크와 오버헤드만 늘리므로, 세션을 만들기 전에 이 표를 본다.**

| 원본 메모의 수집 대상 | `system_health` 포함 여부 | 별도 세션 |
|---|---|---|
| deadlock | ✅ **포함** — deadlock graph까지 | **불필요** (보관 연장 목적만 예외) |
| blocked process | ❌ **미포함** — 30초 초과 락 대기의 callstack은 잡지만 `blocked_process_report`는 아니다 | **필수** |
| error log | △ **부분** — severity ≥ 20 + 메모리 오류(17803, 701, 802, 8645, 8651, 8657, 8902)만 | **필요** (sev 17~19 및 저severity 중요 오류) |
| slow query | ❌ **미포함** | **필수** |

`system_health`의 event_file 상한은 **Standard·Enterprise 기준 100 MB × 10개**
(그 외 에디션 5 MB × 4개)다. 바쁜 인스턴스에서는 며칠치만 남는다.

> **`system_health`를 중지·변경·삭제하지 않는다.** MS가 명시적으로 권고하며,
> 변경해도 이후 제품 업데이트에서 덮어써질 수 있다.

## 공통 설계 규칙

- **타깃은 `event_file` 하나.** `ring_buffer`는 재시작하면 사라져 사후 분석에 쓸 수 없다
- **`STARTUP_STATE = ON`** — 서비스 재시작 후 자동으로 다시 켜진다. 빠뜨리면 장애 재부팅 뒤
  조용히 수집이 멈춘다
- **`EVENT_RETENTION_MODE = ALLOW_SINGLE_EVENT_LOSS`** (기본값). `NO_EVENT_LOSS`는
  버퍼가 차면 **이벤트를 발생시킨 세션을 대기시킨다** — 진단 도구가 장애 원인이 된다
- **`MAX_DISPATCH_LATENCY = 30 SECONDS`** — 파일에 내려쓰기까지 지연. 짧게 잡을수록 I/O가 는다
- **저장 위치는 데이터·로그 볼륨과 분리한다.** 아래 예시의 `X:\SQL_XEL\`은 배포 환경 값으로 치환
- 폴더는 **사전 생성**하거나 `sys.xp_create_subdir`로 만든다. 서비스 계정에 쓰기 권한이 필요하다 —
  `xp_cmdshell`을 켜지 않는다 ([[sqlserver-backup-procedure]]와 같은 원칙)

**보관량 계산** — `max_file_size(MB) × max_rollover_files` 가 세션당 디스크 하드 상한이다.

| 세션 | 파일 크기 | 파일 수 | 상한 |
|---|---|---|---|
| `xe_slow_query` | 128 MB | 10 | 1.25 GB |
| `xe_blocked_process` | 64 MB | 10 | 640 MB |
| `xe_error_reported` | 64 MB | 10 | 640 MB |

## 1. 느린 쿼리 — `xe_slow_query`

```sql
CREATE EVENT SESSION [xe_slow_query] ON SERVER
ADD EVENT sqlserver.sql_batch_completed (
    ACTION ( sqlserver.client_app_name
           , sqlserver.client_hostname
           , sqlserver.database_name
           , sqlserver.session_id
           , sqlserver.username )
    --  duration 단위는 마이크로초. 3,000,000 = 3초
    WHERE  ( sqlserver.is_system = 0 AND duration >= 3000000 )
),
ADD EVENT sqlserver.rpc_completed (
    ACTION ( sqlserver.client_app_name
           , sqlserver.client_hostname
           , sqlserver.database_name
           , sqlserver.session_id
           , sqlserver.username )
    WHERE  ( sqlserver.is_system = 0 AND duration >= 3000000 )
)
ADD TARGET package0.event_file (
    SET filename           = N'X:\SQL_XEL\xe_slow_query.xel'
      , max_file_size      = 128      --  MB
      , max_rollover_files = 10
)
WITH ( MAX_MEMORY              = 8MB
     , EVENT_RETENTION_MODE    = ALLOW_SINGLE_EVENT_LOSS
     , MAX_DISPATCH_LATENCY    = 30 SECONDS
     , TRACK_CAUSALITY         = OFF
     , STARTUP_STATE           = ON );
GO
ALTER EVENT SESSION [xe_slow_query] ON SERVER STATE = START;
GO
```

- **`sql_statement_completed`가 아니라 `sql_batch_completed`를 쓴다.** 문 단위 수집은
  이벤트 수가 한 자릿수 배로 늘어난다. 배치 단위로 범인을 좁힌 뒤 필요할 때만 문 단위로 내려간다
- `rpc_completed`를 함께 넣어야 저장 프로시저 호출이 잡힌다. 배치만 넣으면 앱 트래픽 상당수가 누락된다
- **3초는 출발점이지 표준값이 아니다.** 배포 후 하루치를 보고 파일이 하루 만에 롤오버되면
  임계를 올린다. [[sqlserver-operations]]의 "환경 종속 값" 분류에 해당한다

## 2. 블로킹 — `xe_blocked_process`

```sql
--  전제: 이 값이 0이면 blocked_process_report 이벤트 자체가 발생하지 않는다
EXEC sp_configure 'show advanced options', 1; RECONFIGURE WITH OVERRIDE;
EXEC sp_configure 'blocked process threshold (s)', 5; RECONFIGURE WITH OVERRIDE;
EXEC sp_configure 'show advanced options', 0; RECONFIGURE WITH OVERRIDE;
GO

CREATE EVENT SESSION [xe_blocked_process] ON SERVER
ADD EVENT sqlserver.blocked_process_report
ADD TARGET package0.event_file (
    SET filename           = N'X:\SQL_XEL\xe_blocked_process.xel'
      , max_file_size      = 64
      , max_rollover_files = 10
)
WITH ( MAX_MEMORY              = 4MB
     , EVENT_RETENTION_MODE    = ALLOW_SINGLE_EVENT_LOSS
     , MAX_DISPATCH_LATENCY    = 30 SECONDS
     , STARTUP_STATE           = ON );
GO
ALTER EVENT SESSION [xe_blocked_process] ON SERVER STATE = START;
GO
```

> [!warning] 구축 표준의 `blocked process threshold = 1`과 충돌한다
>
> 블로킹 모니터는 **임계값 주기마다 같은 블로킹을 반복 보고한다.**
> 임계 1초면 5분 지속된 블로킹 하나가 보고서 수백 건이 된다 — 파일이 순식간에 롤오버되고
> 정작 필요한 과거 기록이 밀려난다.^[inferred]
>
> 위 예시는 **5초**로 잡았다. [[sqlserver-operations]]의 구축 표준은 **1초**로 기재돼 있어
> 두 문서가 어긋난다 — 어느 쪽을 표준으로 할지 결정이 필요하다. ^[ambiguous]
> 1초를 유지한다면 `max_file_size`를 크게 잡고 보관 커버 시간을 별도로 감시해야 한다.

## 3. 오류 — `xe_error_reported`

```sql
CREATE EVENT SESSION [xe_error_reported] ON SERVER
ADD EVENT sqlserver.error_reported (
    ACTION ( sqlserver.client_app_name
           , sqlserver.client_hostname
           , sqlserver.database_name
           , sqlserver.session_id
           , sqlserver.sql_text
           , sqlserver.username )
    WHERE  (
            --  severity 17 이상: 리소스·내부 오류. 16 이하는 앱 오류라 노이즈가 크다
            severity >= 17
            --  severity 만으로는 놓치는 중요 오류를 번호로 명시 열거한다
            OR error_number = 823      --  I/O 오류
            OR error_number = 824      --  논리적 일관성 I/O 오류
            OR error_number = 825      --  read-retry 경고 — severity 10 이라 위 필터를 통과 못 한다
            OR error_number = 605      --  페이지 할당 불일치
            OR error_number = 1105     --  파일 그룹 공간 부족
            OR error_number = 9002     --  트랜잭션 로그 꽉 참
            OR error_number = 1205     --  데드락 희생자
           )
)
ADD TARGET package0.event_file (
    SET filename           = N'X:\SQL_XEL\xe_error_reported.xel'
      , max_file_size      = 64
      , max_rollover_files = 10
)
WITH ( MAX_MEMORY              = 4MB
     , EVENT_RETENTION_MODE    = ALLOW_SINGLE_EVENT_LOSS
     , MAX_DISPATCH_LATENCY    = 30 SECONDS
     , STARTUP_STATE           = ON );
GO
ALTER EVENT SESSION [xe_error_reported] ON SERVER STATE = START;
GO
```

- **825는 이 설계의 존재 이유다.** "read-retry 성공" 경고로 severity 10이라 모든 severity 필터를
  통과하지 못하지만, **디스크가 죽어가고 있다는 가장 이른 신호**다. 823/824가 뜬 뒤엔 이미 늦다
- severity ≥ 20 구간은 `system_health`와 의도적으로 겹친다 — 목적은 **보관 기간 연장**이다
- XEvent 조건절은 `IN`을 지원하지 않으므로 `OR`로 나열한다

## 4. 데드락 — 원칙적으로 만들지 않는다

`system_health`가 `xml_deadlock_report`를 이미 수집한다. **보관 기간 연장이 목적일 때만** 만든다.

```sql
CREATE EVENT SESSION [xe_deadlock] ON SERVER
ADD EVENT sqlserver.xml_deadlock_report
ADD TARGET package0.event_file (
    SET filename           = N'X:\SQL_XEL\xe_deadlock.xel'
      , max_file_size      = 32
      , max_rollover_files = 20   --  이벤트가 드물어 파일 수를 늘려도 부담이 없다
)
WITH ( MAX_MEMORY           = 4MB
     , EVENT_RETENTION_MODE = ALLOW_SINGLE_EVENT_LOSS
     , MAX_DISPATCH_LATENCY = 30 SECONDS
     , STARTUP_STATE        = ON );
GO
ALTER EVENT SESSION [xe_deadlock] ON SERVER STATE = START;
GO
```

구축 표준의 Trace flag 1204/1222도 데드락을 **에러로그**에 남긴다. 즉 데드락은
system_health · 에러로그 · (선택) 이 세션까지 **최대 3중으로 기록된다.**
1204/1222를 유지할지도 함께 정리 대상이다.^[inferred]

## 배포 후 확인

```sql
--  세션이 살아 있고 자동 시작으로 설정됐는지
SELECT  s.name
    ,   s.startup_state
    ,   CASE WHEN r.name IS NULL THEN '중지' ELSE '실행중' END AS run_state
FROM    sys.server_event_sessions AS s
LEFT JOIN sys.dm_xe_sessions      AS r ON r.name = s.name
WHERE   s.name LIKE 'xe[_]%';

--  수집된 이벤트 읽기 (파일명에 * 를 써서 롤오버 파일 전체를 본다)
SELECT  CAST(event_data AS XML) AS event_data
FROM    sys.fn_xe_file_target_read_file('X:\SQL_XEL\xe_slow_query*.xel', NULL, NULL, NULL);

--  버퍼 유실 여부 — dropped 가 계속 오르면 MAX_MEMORY 를 올리거나 필터를 조인다
SELECT  s.name, t.target_name, t.execution_count
FROM    sys.dm_xe_sessions AS s
JOIN    sys.dm_xe_session_targets AS t ON t.event_session_address = s.address
WHERE   s.name LIKE 'xe[_]%';
```

## Open Questions

- **`blocked process threshold` 값이 구축 표준(1초)과 이 페이지(5초)에서 다르다.** 결정 필요 ^[ambiguous]
- **임계값 3초·5초는 실측 근거가 없다.** 배포 후 하루치 파일 증가량을 보고 조정해야 하며,
  조정 근거를 이 페이지에 되먹여야 한다
- **알람 연동이 없다.** 현재 정의는 수집만 하고 아무도 알려주지 않는다.
  파일을 주기적으로 읽어 집계하는 Job 또는 에이전트가 있어야 [[monitoring-incident-runbook]]과 이어진다
- **세션 정의 자체가 실행 검증 전이다.** 특히 조건절 문법(`sqlserver.is_system`, `error_number` OR 나열)은
  개발 인스턴스에서 생성해 봐야 확정된다 → [[verbal-source-verification-policy]]

## Related

- [[sqlserver-operations]] — 이 세션들을 배포하는 신규 인스턴스 구축 표준.
  `blocked process threshold`·Trace flag 1204/1222가 여기서 정해진다
- [[sqlserver-backup-procedure]] — 폴더 생성에 `xp_cmdshell`을 쓰지 않는다는 같은 원칙을 공유
- [[operational-queries]] — 블로킹·대기 통계를 즉시 조회하는 쿼리. XEvent는 **사후**, 이쪽은 **현재**
- [[monitoring-incident-runbook]] — 수집된 이벤트가 실제 대응 절차로 이어지는 지점
- [[db-common-concepts]] — 3사에서 같은 목적을 어떤 도구로 푸는지 (MySQL slow log, PG `log_min_duration_statement`)
