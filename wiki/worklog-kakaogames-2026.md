---
title: 2026년 작업 내역 (카카오게임즈)
category: 업무기록
tags: [worklog, kakaogames, 2026]
summary: 2026년 회사에서 수행한 작업의 월별 집계. 성과 평가·포트폴리오 원천 페이지.
sources: [본인 업무 기록]
status: draft
created: 2026-08-04
updated: 2026-08-15
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **이 페이지가 성과 평가·포트폴리오의 단일 원천이다.** 작업이 끝난 시점에 바로 한 줄 남기지 않으면 연말에 복원 비용이 몇 배로 든다
> - 각 항목은 "무엇을 했다"가 아니라 **"무엇을 규명했고 무엇이 바뀌었나"**로 쓴다. 8월 Bug #119309 항목이 좋은 예 — 공식 리포트에 없는 조건을 찾아 영향 범위 판정 기준을 정정한 것이 성과다
> - 기술 상세는 `db운영` 페이지로 빼고 여기에는 맥락·판단·임팩트만 남긴다. 그래야 이직 후에도 양쪽이 각자 쓸모를 유지한다

# 2026년 작업 내역

성과 평가 및 포트폴리오 작성용 연간 집계 페이지. 업무 로그가 쌓이면 여기에 월별로 요약.

## 1H

*아직 없음.*

## 2H

- **7월**: [[notion-kb-consolidation-worklog|DBA 지식베이스 통합 정리 프로젝트]] — 산재 문서를 Notion 통합 포털로 재구축, 대표 문서 31개 등록, 6차 보안·사실 검증, 원본 무손실 정리.
- **8월**: 로컬 세컨드 브레인(Obsidian 볼트) 구축 및 Notion 포털 전체 뎁스(~140페이지) 지식 이관·감사, 교정 백로그 20건 도출.
- **8월**: MySQL 8.0.42 파티션 pruning 회귀(Bug #119309) 영향 조사 — `SET TIMESTAMP`으로 파티션 경계를 앞당겨 재현 테스트 수행. **INSERT 이력이 없는 테이블은 pruning 캐시가 형성되지 않아 증상이 나타나지 않는다**는 점을 확인해, 정상 동작하던 에러 로그 테이블이 "안전"이 아니라 "미노출"이었음을 규명. 버그 리포트에 없는 조건이라 영향 범위 판정 기준을 정정. 기술 상세는 [[mysql-partition-pruning-prepared-stmt-bug|Bug #119309 상세]].
- **8월**: PostgreSQL forum DB — 단일 스키마 사용 환경에서 스키마 명시 없이 쿼리 가능하도록 dbadmin/forum_user 롤에 `search_path = forum, extensions` 설정 (`ALTER ROLE ... IN DATABASE forum SET search_path`). 기술 상세는 [[postgresql-operations|PostgreSQL 운영 지식]] 참고.
- **8월**: [[aws-aidlc-workflows-v2-study|AWS AI-DLC Workflows 2.0 공식 저장소 분석]] — 5개 phase·32개 stage·14개 agent, 결정론적 상태 엔진, 승인 게이트, 학습 루프를 정리하고 Codex 및 사내 DBA Agent 적용을 위한 실습·평가 항목을 도출.

## Related
- [[notion-kb-consolidation-worklog]] — 7월 프로젝트 상세와 포트폴리오 어필 포인트
- [[dba-agent-work-plan]] — 8월 이후 진행 중인 에이전트 개편 계획
- [[aws-aidlc-workflows-v2-study]] — 8월 분석 노트 상세
- [[dbgw-queries]] — 업무 중 작성해 사용한 쿼리 원본
- [[mysql-partition-pruning-prepared-stmt-bug]] · [[postgresql-operations]] — 각 항목의 기술 상세
