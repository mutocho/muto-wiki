---
title: 개발·자동화 상세 — Ruff 설정·CLAUDE.md 계층·Slack Bot (Notion 심층 수집)
tags: [dev, tooling, slack-bot, ci]
topics: [dba]
summary: >-
  Ruff pyproject 상세 설정과 pre-commit, CLAUDE.md 5계층 관리 원칙,
  Slack Bot Socket Mode 채택 근거와 OAuth scope 목록. dev-tooling-standards의 상세판.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: 개발 및 자동화 트리 (https://app.notion.com/p/3adfb969b8be81d2abc7e0c9a5996b4d, 2026-07-30)"
---

# 개발·자동화 상세

관련: [[2026-08-04-dev-tooling-standards]] (요약판)

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
