---
title: 개발·자동화 상세 — Ruff 설정·CLAUDE.md 계층·Slack Bot
category: db운영
tags: [dev, tooling, slack-bot, ci, ruff]
summary: Ruff pyproject 상세 설정과 pre-commit, CLAUDE.md 5계층 관리 원칙, Slack Bot Socket Mode 채택 근거와 OAuth scope 목록. dev-tooling-standards의 상세판.
sources: ["Notion: 개발 및 자동화 트리 (2026-07-30)"]
status: draft
created: 2026-08-04
updated: 2026-08-04
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **Slack Bot은 Socket Mode가 정답이다** — Slash Command/Shortcuts를 Request URL로 받으면 Public IP를 노출해야 한다. DB 운영 봇을 사내에 놓는 이상 인바운드 노출은 선택지가 아니다
> - **현재 Slack scope 12개는 과다 가능성이 있다.** `chat:write.customize`, `users:write`, `files:write`의 실사용 근거를 확인하고 축소해야 한다. 토큰 회전 절차 문서도 없다 — 미처리 과제
> - **"같은 실수를 2회 반복하면 규칙을 추가한다"** — CLAUDE.md를 키우는 유일한 기준. 이 위키의 `CLAUDE.md`에도 같은 기준을 적용한다
> - 근거 없이 복사하면 안 되는 설정이 예시에 섞여 있다: `B904` ignore는 예외 체이닝 규칙 해제다

# 개발·자동화 상세

관련: [[dev-tooling-standards]] (요약판)

## Ruff 상세 설정

- pyproject.toml: `target-version="py311"`, `line-length=88`, lint select `E,W,F,I,B,UP` (FastAPI는 `ASYNC` 추가), formatter 충돌 `E501` ignore, FastAPI `Depends()`용 `B008`은 `per-file-ignores`로 `app/api/**/*.py` 한정, `known-first-party=["app","core"]`.
- VS Code: `charliermarsh.ruff` defaultFormatter + `source.fixAll.ruff`/`source.organizeImports.ruff` codeActionsOnSave "explicit".
- pre-commit: `astral-sh/ruff-pre-commit`, hooks `ruff-check --fix` → `ruff-format` 순.
- 주의: 예시의 `B904` ignore는 예외 체이닝 규칙 해제 — 근거 없이 복사 금지.

## CLAUDE.md 계층 관리

조직 정책 → 사용자 공통(`~/.claude/CLAUDE.md`) → 프로젝트 공유(`./CLAUDE.md`) → 프로젝트 개인(`CLAUDE.local.md`, .gitignore) → 경로별(`.claude/rules/`).
- 포함: 빌드/테스트/lint/type check 명령, 반복 실수 함정, 코드로 알 수 없는 불변 규칙, 우선순위 충돌 시 결정 기준.
- 제외: README 중복, 폴더 구조 나열, 비밀정보, 추상 표현.
- 원칙: 200줄 이내, 긴 절차는 skill/rules로 분리, "같은 실수 2회 반복 시 규칙 추가", `/memory`로 로드 확인.

## Slack Bot (DBA 봇)

- **Socket Mode 채택 근거**: Slash Command/Shortcuts는 Request URL(Public IP) 노출 필요 → Socket Mode로 인바운드 노출 없이 이벤트 수신. 프레임워크는 Bolt.
- Event Subscriptions(`message.channels` 등)은 각각 대응 `*:history` scope 필요.
- 현재 scope 목록(channels:history, chat:write, chat:write.customize, commands, files:write, groups:history, im:history, im:write, incoming-webhook, mpim:history, users:read, users:write)은 **최소권한 관점에서 과다 가능성** — `chat:write.customize`, `users:write`, `files:write`의 실사용 근거 확인 후 축소 필요. 토큰 회전 절차 문서도 부재.

## 레거시 판정

- 2023 Django 메모(`pip freeze` 방식)는 현행 표준(uv·pyproject·잠금 파일)과 충돌 — 보관.
- "NextJS" 페이지는 실제로는 JS 문법 메모(`??` vs `||` 등) — 오분류 확인됨, 보관.

## Related

- [[dev-tooling-standards]] — 이 페이지의 요약판. 새 저장소 셋업 시 먼저 본다
- [[wiki-bot-automation-tradeoffs]] — 봇 자동화의 비용·안전 범위 판단 기준
- [[claude-code-permission-guardrails]] — 에이전트가 설정 파일을 못 고치는 지점
