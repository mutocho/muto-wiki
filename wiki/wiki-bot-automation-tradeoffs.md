---
title: 위키 봇 자동화 — 미승격 초안 검색과 ingest·lint 운영 기준
category: db운영
tags: [automation, slack-bot, knowledge-management, agent]
summary: 승격 전 초안의 검색 누락을 막는 방법, ingest와 lint의 서로 다른 비용 축, 무인 실행 시 허용할 안전한 작업 범위.
sources: [작업 세션 기록 (2026-08-11)]
status: draft
created: 2026-08-12
updated: 2026-08-12
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **미승격 초안이 검색에서 빠지는 문제는 적재 주기를 줄여서 풀지 않는다.** 질의 시 원본 폴더(`raw/`)를 직접 grep하게 하는 것이 정답 — 초안 단계에도 정보 자체는 이미 존재한다
> - **ingest 비용은 원본 파일 수에 비례하고, lint 비용은 위키 크기 × 실행 횟수에 비례한다.** 축이 다르므로 정책도 달라야 한다 — **적재는 자주, 전수 점검은 배치로**
> - **무인 자동 수정은 되돌릴 필요가 없는 것만 허용한다** (깨진 링크 수정, 고아 페이지 링크 추가, 태그 정규화). 상태 승격·등급 강등·모순 콜아웃 삽입은 사람 판단 — 자동화하면 **그 값이 검토 결과인지 자동 판정인지 구분할 수 없게 된다**
> - 이 원칙들이 [[vault-governance-decisions]]와 이 위키의 건강검진 절차(리포트 먼저, 승인 후 수정)의 근거다

# 위키 봇 자동화 — 미승격 초안 검색과 ingest·lint 운영 기준

Slack 위키 봇이 새 캡처를 놓치지 않으면서도 유지보수 비용과 자동 변경 위험을 통제하기 위한 운영 기준이다.

## 승격 전 `_raw` 초안도 검색한다

`slack-bot/runner.py`의 query 프롬프트는 `second-brain/index.md`에서 후보 페이지를 고른 뒤 grep으로 범위를 좁힌다. `index.md`에는 `_raw` 항목이 없으므로, 적재 직후 생성된 초안은 정식 페이지로 승격될 때까지 조회 대상에서 빠진다.

해결책은 ingest 주기를 무조건 줄이는 것이 아니라 query 프롬프트가 `_raw/`도 직접 grep하도록 하는 것이다. 초안 단계에도 정보 자체는 존재하며, ingest는 frontmatter·위키링크·색인 같은 구조를 더한다. 여러 페이지를 연결해야 하는 질문일수록 이 구조의 가치가 커진다. ^[inferred]

## ingest와 lint의 비용 축을 분리한다

- **ingest 비용은 `_raw` 파일 수에 비례한다.** 같은 10건을 한 번에 처리하거나 여러 번 나눠 처리해도 처리할 원문 총량은 같다.
- **lint 비용은 볼트 전체 크기와 실행 횟수의 곱에 비례한다.** 매 실행에서 링크 그래프와 frontmatter를 전수 검사하므로 실행 횟수가 고정비를 반복시킨다.

따라서 새 캡처를 빠르게 검색 가능하게 해야 한다면 ingest는 자주 수행할 수 있지만, lint는 충분한 변경분을 모아 배치로 실행하는 편이 효율적이다.

## `wiki-lint --consolidate` 무인 실행 범위를 제한한다

`wiki-lint --consolidate`에는 다음처럼 사람의 판단이 필요한 변경이 포함될 수 있다.

- 생성 후 30일이 지나고 confidence가 0.7을 넘은 페이지의 `lifecycle: draft → reviewed` 승격
- tier 강등
- 180일이 지난 페이지에 stale 배너 삽입
- 모순 콜아웃 삽입

이 작업들은 신규 페이지가 아니라 볼트 전체에 영향을 주며, 원래 절차도 dry-run 뒤 사용자 확인을 전제로 한다. 무인 스케줄에서는 깨진 링크 수정, 고아 페이지 크로스링크 추가, 태그 별칭 정규화처럼 되돌릴 필요가 거의 없는 작업만 화이트리스트로 허용하고 나머지는 리포트만 생성해야 한다. 그렇지 않으면 lifecycle 값이 사람의 검토 결과인지 자동화 판단인지 구분하기 어려워진다. ^[inferred]

## Related

- [[obsidian-wiki-tooling-gotchas|obsidian-wiki 도구 동작 함정]]
- [[notion-llm-wiki-governance|Muto DBA LLM Wiki 운영 거버넌스]]
- [[dev-automation-detail|개발·자동화 상세]]
