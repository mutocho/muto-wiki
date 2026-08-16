---
title: DB 문서 보안 검토에서 반복 발견된 위험 패턴
category: db운영
tags: [dba, security, gotcha, checklist]
summary: Notion 지식베이스 보안 검토(1~6차)에서 반복 발견된 위험 패턴 목록 — 고정 비밀번호, Database Mail 자격증명, 무조건 인덱스 리빌드, TDE 해제 단계 혼입, 백업 절차 내 xp_cmdshell 토글, TRUSTWORTHY 권한 상승 등.
sources:
  - "Notion: 정리 및 보안 검토 보고서 (2026-07-30)"
  - "사내 SQL Server 구축 표준 메모 검토 (2026-08-15) — SP_DB_BACKUP·TRUSTWORTHY"
status: reviewed
created: 2026-08-04
updated: 2026-08-16
notion_page_id: "3bdfb969-b8be-8149-b60c-c66dd89d11cb"
notion_synced: "2026-08-15T23:20:00+0900"
---

> [!tip] 핵심 Takeaway
> - **이 페이지는 읽을 문서가 아니라 실행할 체크리스트다.** DB 문서·스크립트를 검토하는 에이전트의 룰셋으로 그대로 옮긴다
> - **가장 위험한 패턴은 "일상 절차에 보안 상태를 바꾸는 단계가 섞여 있는 것"** — 백업 절차에 TDE 해제·암호화 키 삭제가 들어있던 사례, 백업 프로시저가 `xp_cmdshell`을 켰다 끄는 사례. **2건 모두 백업 절차에서 나왔다** — 백업 스크립트를 검토 1순위로 둔다. **되돌리는 코드가 있어도 안전한 게 아니다** — 판정 기준은 "끄는 코드가 있는가"가 아니라 **"비정상 종료해도 꺼지는가"**
> - **자리표시자 비밀번호(`1234`, `change-me`, 빈 문자열)도 실제 유출과 같은 등급으로 취급한다.** 복사돼 그대로 운영에 반영되는 경로가 실재한다 → `<INJECT_FROM_SECRET_STORE>`로 통일
> - **자격증명이 노출되면 문서 수정이 아니라 폐기·재발급이 조치다** — [[db-access-control]]과 같은 원칙
> - **자동 실행 금지로 분류할 스크립트 유형이 정해져 있다**: 조건 없는 인덱스 리빌드, Docker 전체 강제 삭제, TRUNCATE 일괄 생성기
> - 미해결 과제: 1~6차 검토가 하루에 몰려 있어 **재검증 주기 규칙이 없다.** "마지막 검증일 + N개월" 기준을 세우지 않으면 일회성 대청소로 끝난다 ^[inferred]

# DB 문서 보안 검토에서 반복 발견된 위험 패턴

문서·스크립트 감사 시 체크리스트로 재사용할 것.

## 자격증명·비밀정보

- 실제 비밀번호 형태 문자열이 계정 설정 문서에 그대로 저장됨 → 발견 즉시 제거 + **해당 자격증명 폐기·재발급** (문서에서 지우는 것만으로는 불충분).
- `1234`, `password`, `change-me` 같은 자리표시자도 위험: 복사 후 그대로 운영 반영될 수 있음 → `<INJECT_FROM_SECRET_STORE>` 또는 환경변수 표기로 통일.
- SMTP·복제·Slack Webhook·클라우드 자격증명은 값이 비어 있는 템플릿만 유지.
- 개인 계정명, 사내 호스트명, 로컬 키 경로, 개인 이메일도 내부정보 노출 — placeholder로 치환.
- OS 명령 예제: 생성된 비밀번호의 화면 출력 금지, 프로세스 인자·내부 포트는 공유 전 마스킹.

## 위험한 절차·스크립트 패턴

- **일반 백업 절차에 TDE 해제·암호화 키 삭제 단계가 섞여 있던 사례** — 보안통제 약화 단계가 일상 절차에 혼입되는 전형적 위험. 절차 문서는 보안 상태를 바꾸는 단계를 분리·격리할 것.
- SQL Server 인덱스 리빌드 스크립트: 조각화율만으로 전체 대상에 `REBUILD WITH (MAXDOP=0, SORT_IN_TEMPDB=ON)` 생성 → **자동 실행 금지** 분류. 페이지 수·워크로드·에디션(온라인 리빌드 가능 여부) 고려 필요.
- SQL Server Database Mail: `public` 기본 프로필, `RECONFIGURE WITH OVERRIDE`, SMTP 자격증명 직접 입력 패턴은 교정 대상.
- **백업 프로시저가 `xp_cmdshell`을 활성화했다가 마지막에 비활성화하는 패턴** — 폴더 생성 한 줄 때문에 백업 구간 전체에 걸쳐 인스턴스 전역 셸 실행이 열린다. **비정상 종료 시 켜진 채로 남는다.** 폴더 사전 생성 또는 Agent CmdExec 스텝 분리로 교정 → [[sqlserver-operations]]의 `SP_DB_BACKUP`
- **`TRUSTWORTHY ON`** — `EXECUTE AS OWNER`를 위해 켜지만, DB 소유자가 sysadmin이면 db_owner가 인스턴스 전체 권한을 획득하는 **권한 상승 경로**가 된다. 켜져 있는 DB 목록과 각 소유자를 함께 확인해야 판정이 된다.
- **보관 정책의 삭제 조건에 대상 식별자가 빠진 스크립트** — 파일 확장자·날짜만으로 백업 파일을 지우면 다른 DB의 백업까지 삭제된다. 삭제를 수행하는 스크립트는 **"무엇을 남기는가"가 아니라 "무엇에 매칭되는가"로** 검토한다.
- **오류를 `SELECT`으로만 반환하는 운영 프로시저** — Agent Job에서 호출하면 실패해도 성공으로 끝나 알람이 뜨지 않는다. 백업·정리 작업에서는 무알람 실패가 곧 데이터 손실이다. `THROW`/`RAISERROR` 승격이 검토 항목.
- **식별자를 `LIKE`에 그대로 넣은 삭제 조건** — DB·테이블명에 흔한 `_`가 LIKE에서 임의의 한 글자로 동작해 **대상 범위가 조용히 넓어진다.** 삭제·정리 스크립트에서는 `ESCAPE` 처리 여부를 확인 항목으로 둔다.

> 위 4개 패턴을 실제로 고친 사례가 [[sqlserver-backup-procedure]]다 — 검토 지적이 어떤 코드
> 변경으로 이어지는지의 참조 구현으로 쓴다.
- MySQL 인증 해시를 추출해 사용자 생성문을 재구성하는 스크립트는 제한된 절차로 격리.
- Docker 전체 컨테이너 강제 삭제·볼륨 삭제 명령은 고위험 격리 + 안전한 prune 기준 별도 문서화.
- 비밀번호 정책 비활성화, 상시 `sysadmin` 부여 예제 → 최소 권한·시크릿 저장소 기준으로 교정.

## 버전·환경 분리 기준 (검증된 사실)

- MySQL `mysql_native_password`: 8.0.34 deprecated → 8.4 기본 비활성 → 9.0 제거.
- Kafka 4.x는 KRaft 전용, ZooKeeper 문서는 3.x 레거시 마이그레이션 자료로만 유지.
- PostgreSQL: OSS / RDS / Aurora의 superuser·extension·parameter·스토리지 차이를 항상 분리 기술.

## 보완 사항 (분석 결과)

- **[보완] 검토 주기 부재**: 1~6차 검토가 모두 2026-07-30 하루에 몰려 있음. "마지막 검증일 + N개월" 형태의 재검증 주기 규칙(예: 운영 Runbook 6개월, 버전 의존 문서는 메이저 릴리스 시)을 정해야 일회성 대청소로 끝나지 않는다. ^[inferred]

## Related

- [[notion-remediation-backlog]] — 이 패턴들이 실제로 발견된 교정 대상 20건
- [[db-access-control]] — 계정·권한 설계 표준. 여기서 금지한 권한이 검토 기준이 된다
- [[cloud-platform-knowledge]] — 백업 절차에 TDE 해제가 혼입된 원 사례
- [[notion-kb-consolidation-worklog]] — 이 체크리스트가 만들어진 프로젝트
- [[dev-tooling-standards]] — 코드·CI 쪽 자격증명 관리 기준
- [[db-change-safe-patterns]] — DDL·DML 변경 명령이 이 검토의 1차 대상. 조각화율 단독 판단 REBUILD·`TRUNCATE` 생성기를 배제한 근거가 여기 체크리스트다
- [[db-permission-queries]] — 권한 부여 명령. 자리표시자 비밀번호·과다 권한을 여기서 걸러낸다
- [[operational-queries]] — 읽기 전용 진단 쿼리. 검토 등급이 가장 낮은 대신, 해시 컬럼 조회 혼입만 확인한다
- [[sqlserver-operations]] — 인덱스 리빌드·Database Mail 위험의 엔진 맥락
- [[mysql-dump-load]] — MySQL 쪽의 같은 유형. `--add-drop-*`와 `--databases` 누락이 파괴적 단계가 일상 절차에 섞인 사례
