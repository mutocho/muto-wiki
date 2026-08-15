---
title: Wiki Index
category: 색인
tags: [index]
summary: muto-wiki 전체 목차. 페이지가 추가·변경될 때마다 갱신된다.
sources: [wiki/*.md 프론트매터]
status: reviewed
created: 2026-08-15
updated: 2026-08-15
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **여기가 모든 탐색의 출발점이다.** 질문에 답할 때도, 자료를 넣을 때도 먼저 이 목차에서 관련 페이지를 찾는다 — 새 페이지를 만들기 전에 흡수할 곳이 있는지 확인하는 것이 원칙
> - **폴더는 없다. 분류는 이 파일에만 존재한다.** 분류를 바꾸고 싶으면 파일을 옮기지 말고 이 목차를 고친다
> - 현재 **31개 페이지 / 깨진 링크 0 / 고아 페이지 0**

# Wiki Index

*총 31개 페이지. 마지막 갱신: 2026-08-15*

전체 운영 규칙은 저장소 루트의 `CLAUDE.md`. 작업 이력은 [[log]].

---

## DB 운영 지식 (20)

재사용 가능한 기술 지식. 회사 맥락을 최소화해 이직 후에도 쓸 수 있는 형태로 유지한다.

### 엔진별 운영

- [[mysql-operations]] — 백업 표준, Undo·장기 트랜잭션, 락, 버전 이정표. **회수 릴리스와 8.0.42 회귀가 업그레이드 하드 필터** ( #mysql #aurora #backup)
- [[postgresql-operations]] — 계정·파라미터 베이스라인, CONCURRENTLY 원칙, XID wraparound 단계별 알람 ( #postgresql #vacuum #monitoring)
- [[sqlserver-xevent-sessions]] — XEvent 세션 3종 정의. **데드락은 `system_health`가 이미 잡으므로 만들지 않고, 블로킹은 없으므로 필수.** 825는 severity 10이라 번호로 열거 ( #sqlserver #xevent #monitoring)
- [[sqlserver-backup-procedure]] — `SP_DB_BACKUP` 결함 5건 수정본. **정리 조건에 DB 식별자가 없어 타 DB 백업을 지우던 것을 3중 한정으로 교정.** 실행 검증 전 ( #sqlserver #backup #retention)
- [[sqlserver-operations]] — **신규 인스턴스 구축 표준**(Collation·TempDB·sp_configure·Trace flag), 에러로그 순환 Job, 백업 프로시저와 결함 5건, VLF, Parameter Sniffing, AG vs FCI ( #sqlserver #provisioning #backup #ha)
- [[db-common-concepts]] — 3사 저장 단위·격리수준·MVCC·문법 비교표 + SQL 안티패턴 체크리스트 ( #comparison #sql)
- [[mysql-partition-pruning-prepared-stmt-bug]] — Bug #119309. **증상 없음 ≠ 안전**. 영향 범위 판정 기준을 뒤집은 자체 규명 ( #mysql #bug #partitioning)
- [[aurora-vs-mysql-replication-architecture]] — 독립 binlog apply와 공유 스토리지 redo apply의 성능·lag 차이 ( #aurora #replication)
- [[aurora-dsql]] — OCC 리트라이 필수, FK/Trigger/PL-pgSQL 미지원, 10 TiB 한도, DPU 과금 ( #aws #dsql #architecture)
- [[cloud-platform-knowledge]] — Aurora 스토리지 내부, Azure Blob 백업, Linux·Docker 표준 ( #aws #azure #docker)

### 진단·운영 표준

- [[operational-queries]] — 3사 대조 SQL 15개 카테고리. **1~12 읽기 전용 / 13~15 변경 명령**. 실행 검증 전 ( #snippet #troubleshooting)
- [[monitoring-incident-runbook]] — 시간박스형(5분/15분/근본) 대응, 점검 주기, 신규 클러스터 체크리스트 ( #monitoring #runbook)
- [[dba-ops-standards]] — 장애 대응 5단계, 계층형 모니터링, 문서 생명주기 ( #incident-response #runbook)

### 보안·권한

- [[db-access-control]] — Role 분리, break-glass, 엔진별 금지 권한, PG 계정 삭제 순서 ( #security #access-control)
- [[db-security-review-patterns]] — 문서·스크립트 감사 체크리스트. **일상 절차에 섞인 보안 완화 단계를 먼저 찾는다.** 백업 스크립트가 검토 1순위 ( #security #checklist)

### 개발·자동화

- [[dev-tooling-standards]] — Ruff CI 분리, CLAUDE.md 배치, 자격증명 주입 원칙. 새 저장소 셋업 기준 ( #tooling #ci)
- [[dev-automation-detail]] — Ruff 상세 설정, CLAUDE.md 5계층, Slack Bot Socket Mode 근거와 scope 과다 검토 ( #tooling #slack-bot)
- [[wiki-bot-automation-tradeoffs]] — 미승격 초안 검색, ingest·lint의 서로 다른 비용 축, 무인 자동 수정 허용 범위 ( #automation #agent)

### 지식 운영

- [[notion-llm-wiki-governance]] — Notion 포털 3계층·상태 모델. **포털과 로컬 위키의 역할 분담이 미결 과제** ( #governance #notion)
- [[notion-remediation-backlog]] — 전체 뎁스 감사 교정 대상 20건. **P1 6건은 보안 사고 대기 상태** ( #security #backlog)

---

## 업무 기록 (5)

언제·왜·내가 무엇을 했고 임팩트가 무엇인지. 성과 평가와 포트폴리오의 원천.

- [[worklog-kakaogames-2026]] — 2026년 월별 작업 집계. **연간 성과 정리의 단일 원천** ( #worklog #kakaogames)
- [[notion-kb-consolidation-worklog]] — DBA 지식베이스 통합 정리 (2026-07). 31개 문서, 6차 검증, 원본 삭제 0건 ( #achievement #knowledge-management)
- [[dba-agent-work-plan]] — dba-agent 구조 개편, single/pipe 책임 분리, DBMS 주간 점검 자동화 ( #agent #automation)
- [[aws-aidlc-workflows-v2-study]] — AI-DLC V2 분석. 상태 엔진·승인 게이트를 사내 에이전트에 적용하는 검토 ( #ai #workflow)
- [[dbgw-queries]] — dbgw 메타DB 인스턴스별 권한 목록 추출 쿼리 ( #snippet #dbgw)

---

## 개인 (1)

- [[todo]] — 날짜 있는 단발성 일정과 할 일. **상대 날짜는 절대 날짜로 변환해 기록** ( #personal #schedule)

---

## 참고자료 (3)

외부 소스 하나를 정리한 페이지.

- [[claude-code-permission-guardrails]] — 로컬 훅·분류기 차단 지점과 서버 feature flag 기반 MCP OAuth 차단 진단 ( #claude-code #mcp #gotcha)
- [[obsidian-wiki-tooling-gotchas]] — 폴디드 `summary` 파싱 실패, wikilink 경로 접두어, obsidian-git 실행 권한 반복 diff ( #obsidian #gotcha)
- [[superpowers-agentic-development-methodology]] — 설계 승인·TDD·이중 리뷰·완료 검증을 스킬로 강제하는 개발 방법론 ( #ai-agent #tdd)

---

## 종합·원칙 (2)

여러 자료와 경험을 관통하는 판단 기준. 위키가 스스로 학습한 결론.

- [[verbal-source-verification-policy]] — **구술·사내 출처의 오류는 수치·버전·한도에 몰린다.** 대조 전 `verified` 승격 금지. 실제 오류 5건이 근거 ( #verification #gotcha)
- [[vault-governance-decisions]] — 지식·업무기록 분리 적재, 규칙 파일 단일 소스, 브랜치 금지, 충돌 시 원격 우선 ( #governance #git)

---

## 미완 과제 (건강검진 추적 대상)

여러 페이지에 흩어져 있는 미해결 항목. 건강검진 때 진행 상태를 확인한다.

- **[[notion-remediation-backlog]] P1 6건** — 실 서비스 스키마명이 박힌 TRUNCATE 생성기, QA RDS 실호스트명, 개인 이메일 노출. 미착수
- **[[operational-queries]] 실행 검증** — 개발/QA 인스턴스 확인 후 현장 쿼리로 교체
- **[[notion-llm-wiki-governance]] 역할 분담** — Notion 포털 vs 로컬 위키. 정하지 않으면 이중 관리가 계속된다
- **[[db-security-review-patterns]] 재검증 주기** — "마지막 검증일 + N개월" 규칙 부재
- **[[sqlserver-operations]] 2016 잔존 인스턴스** — 연장 지원 2026-07-15 종료
- **[[sqlserver-backup-procedure]] 실행 검증** — 결함 5건 수정본 작성 완료, 개발/QA 미검증. **정리 단계 삭제 대상을 `SELECT`으로 확인한 뒤 운영 적용**. 원본은 그때까지 자동 스케줄 금지
- **[[sqlserver-xevent-sessions]] 임계값·알람** — 3초/5초는 실측 근거 없음. 수집만 하고 알람 연동이 없어 [[monitoring-incident-runbook]]과 끊겨 있다
- **[[sqlserver-operations]] Collation 적정성** — `Latin1_General_CI_AS_KS`가 한글 정렬에 맞는지 미확인
- **[[dev-automation-detail]] Slack scope 축소** — 12개 중 3개 실사용 근거 미확인, 토큰 회전 절차 부재
- **[[aurora-dsql]] 미확인 3건** — Firecracker 1:1, buffer pool 부재, v2 PG18. 세미나 발언만 존재
- **[[aws-aidlc-workflows-v2-study]] Superpowers 비교** — 항목별 상세 비교 미완 → [[todo]]
