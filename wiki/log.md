---
title: Wiki Log
category: 색인
tags: [log]
summary: 위키에 대한 모든 쓰기 작업의 시간순 기록. 최신이 위.
sources: [작업 수행 기록]
status: reviewed
created: 2026-08-04
updated: 2026-08-15
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **모든 쓰기 작업 후 여기에 한 줄 남긴다.** 지식 자체보다 "언제 무엇이 왜 바뀌었나"가 나중에 더 자주 필요하다
> - 최신 항목이 맨 위. 연산은 `INGEST` / `QUERY` / `LINT` / `SYNC_NOTION` / `UPDATE` / `MIGRATE` / `FIX`
> - 이 로그가 건강검진의 입력이다 — 마지막 LINT 이후 쌓인 변경분이 다음 점검 범위

# Wiki Log

- [2026-08-15T21:38:04+09:00] QUERY query="SQL Server 설정 방법 정리" result_pages=1 note="공식 문서 대조 후 메모리·MAXDOP·TempDB·설치 및 운영 인수 기준 갱신"

## 2026-08

- [2026-08-15T16:48:00+09:00] QUERY query="DSQL에 대해 정리해줘" result_pages=1 note="기존 [[aurora-dsql]]로 답변. 신규 정보 없어 페이지 변경 없음"
- [2026-08-15] MIGRATE source="llm-wiki/second-brain" pages=29 raw_archived=19 note="플랫 구조로 이전. 폴더 계층(dba/career/personal/references/synthesis) 제거하고 `category` 프론트매터로 분류 전환. 전 페이지 프론트매터 신 스키마 변환 + Takeaway callout 신규 작성. wikilink 경로 접두어 전면 제거. `_hub.md` 2개·`ROUTING.md`·`hot.md` 폐지(index.md와 CLAUDE.md가 대체)"
- [2026-08-15] FIX note="교차참조 보강 — 비어버린 Related 절 12개 작성, 역방향 링크 34건 추가. 결과: 깨진 링크 0 / 고아 페이지 0 / 단방향 링크 0"
- [2026-08-15] UPDATE page="vault-governance-decisions" note="구조 변경 반영 — 플랫 적재, CLAUDE.md 실체 + AGENTS.md 심볼릭 링크로 단일 소스 반전, 충돌 원격 우선 결정 추가. 이전 결정은 '변경 이력'에 보존"
- [2026-08-15] UPDATE page="obsidian-wiki-tooling-gotchas" note="wikilink 경로 접두어 함정이 플랫 구조에서 소멸함을 기록"
- [2026-08-15] INIT repo="muto-wiki" note="CLAUDE.md 스키마 작성, AGENTS.md 심볼릭 링크, scripts/sync.sh(원격 우선), SessionStart/Stop 훅 등록, Obsidian 볼트를 저장소 루트로 승격"

## 이전 이력 (llm-wiki/second-brain)

- [2026-08-12T12:56:15+09:00] INGEST source="_raw/2026-08-12-claude-code-gcal-mcp-blocked.md" pages_updated=1 pages_created=0
- [2026-08-12T10:51:00+09:00] CAPTURE page="aurora-vs-mysql-replication-architecture" title="Community MySQL 복제와 Aurora Reader 아키텍처 비교"
- [2026-08-12T10:49:23+09:00] INGEST_URL url="https://github.com/obra/superpowers" page="superpowers-agentic-development-methodology" pages_updated=1
- [2026-08-12T10:10:24+09:00] INGEST source="_raw/2026-08-12-aidlc-superpowers-brainstorming-comparison-request.md" pages_updated=2
- [2026-08-12T09:00:31+09:00] INGEST_URL url="https://github.com/awslabs/aidlc-workflows" page="aws-aidlc-workflows-v2-study"
- [2026-08-12T08:08:26+09:00] INGEST source="_raw/2026-08-11-wiki-bot-automation-tradeoffs.md" pages_updated=3 pages_created=1
- [2026-08-10T00:00:00+09:00] CAPTURE page="todo" title="서울숲 데이트" due="2026-09-05"
- [2026-08-07T19:23:30+09:00] CAPTURE page="todo" title="DBGW 성능 개선 및 DBGWS 승인 절차" due="2026-08-10T10:00:00+09:00"
- [2026-08-06T22:58:55+09:00] QUERY query="내일 할 작업에 대해 정리해줘" result_pages=1
- [2026-08-06T22:14:49+09:00] CAPTURE page="dba-agent-work-plan" title="DBA Agent 구조 개편 및 주간 분석 작업 계획"
- [2026-08-06T22:12:45+09:00] QUERY query="AWS Aurora DSQL 관련한 내용 찾아줘" result_pages=2
- [2026-08-06] CAPTURE page="vault-governance-decisions" title="볼트 거버넌스 결정 — career 회사 라우팅·에이전트 규칙 단일화·브랜치 금지"
- [2026-08-06] CAPTURE page="verbal-source-verification-policy" title="구술·사내 출처는 공식 문서 대조 전까지 승격하지 않는다"
- [2026-08-06] CAPTURE page="dbgw-queries" title="dbgw 메타DB 운영 쿼리" note="원본 그대로 보관"
- [2026-08-06] UPDATE page="mysql-partition-pruning-prepared-stmt-bug" note="리포트 재확인 — 최소 재현 케이스·내부 함수명·SP 포함 추가. 사내 문서의 8.0.41 표기 정정(실제 8.0.42), Reorganize는 재발 방지가 아닌 리셋임을 명시"
- [2026-08-06] UPDATE page="obsidian-wiki-tooling-gotchas" note="obsidian-git askpass chmod +x 반복 diff 함정 섹션 추가"
- [2026-08-06] QUERY query="MySQL 버전 업그레이드 관련 버그 내용 찾아서 보여줘" result_pages=2
- [2026-08-06] QUERY query="aws aurora dsql 설명들은거 알려줘" result_pages=1
- [2026-08-06] FIX note="세션 날짜 오기 정정 — 페이지 3곳, 로그 5줄"
- [2026-08-05] CAPTURE page="mysql-partition-pruning-prepared-stmt-bug" title="MySQL 8.0.42 파티션 pruning 캐시 회귀 (Bug #119309)" note="공식 버그 리포트 + 자체 재현 테스트"
- [2026-08-04] EXPORT target="Notion 🗃️ DBA" pages=14 source="dba/*.md" direction=vault→notion
- [2026-08-04] UPDATE page="aurora-dsql" lifecycle=draft→verified note="AWS 공식 문서 대조. 스토리지 무제한 주장 정정, 공식 한도표·미지원 기능·DPU 과금 추가"
- [2026-08-04] CAPTURE page="operational-queries" title="운영 진단 쿼리 모음 (MySQL·PostgreSQL·SQL Server)" note="표준 시스템 뷰 기반, 실행 검증 전(draft)"
- [2026-08-04] LINT issues_found=4 broken_links=2 missing_summary=2 links_fixed=2
- [2026-08-04] INGEST source="_raw/ (15 files)" pages_created=15
- [2026-08-04] INIT vault="second-brain" categories=concepts,entities,skills,references,synthesis,journal topics=dba,career
