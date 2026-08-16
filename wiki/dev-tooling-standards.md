---
title: 개발 도구 운영 기준 — Ruff·CLAUDE.md·자격증명
category: db운영
tags: [dev, tooling, ci, ruff]
summary: "정제된 핵심 가이드에서 추출한 개발 표준: Ruff check/format 분리, CLAUDE.md 배치 규칙, 자격증명 주입 원칙, CI 검사 분리."
sources: ["Notion: 정제된 핵심 가이드 (2026-07-30)", "Notion: 개발 및 자동화 (2026-07-30)"]
status: draft
created: 2026-08-04
updated: 2026-08-15
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - DB 툴·에이전트 저장소를 새로 만들 때 **여기가 기본 셋업이다** — `ruff check`/`ruff format` CI 분리, pre-commit 순서 고정, 잠금 파일 기준 버전 관리
> - **토큰·Webhook URL을 코드나 문서에 두지 않는다.** env 주입이 원칙이고 로컬 실습도 예외가 아니다 — 고정 비밀번호 예시가 그대로 운영에 흘러간 사례가 [[db-access-control]]에 있다
> - CLAUDE.md는 **빌드·테스트·린트 명령과 불변 규칙만.** 비대해지면 오히려 안 지켜진다. 긴 절차는 별도 규칙 파일로 뺀다

# 개발 도구 운영 기준

## Ruff

- `ruff check`와 `ruff format`을 CI에서 분리 실행. pre-commit은 `ruff-check` → `ruff-format` 순서.
- hook 버전은 문서에 고정하지 않고 프로젝트 의존성 갱신 정책(잠금 파일)으로 관리.
- `B008` 같은 규칙은 프레임워크 패턴(예: FastAPI `Depends`) 확인 후 파일·경로 단위 예외 사용.

## CLAUDE.md / AI 지침 파일

- 팀 공유: 저장소 `CLAUDE.md` 또는 `.claude/CLAUDE.md` / 사용자 공통: `~/.claude/CLAUDE.md` / 개인 프로젝트: `CLAUDE.local.md` (+ `.gitignore`).
- 경로·파일 유형별 규칙은 `.claude/rules/`로 분리.
- 내용은 빌드·테스트·린트·타입 검사 명령과 프로젝트 불변 규칙만 유지 (비대해지면 효과 하락).

## CI·자격증명

- CI에서 `format --check`, lint, test, type check를 분리된 단계로 실행.
- 토큰·Webhook URL은 환경변수 또는 시크릿 저장소에서 주입. 로컬 실습도 고정 비밀번호 대신 env 파일(+버전 관리 제외).
- Slack Bot: OAuth scope 최소 권한 분리, Socket Mode, token rotation 기준 적용.
- 설치 버전은 문서의 고정값이 아니라 프로젝트 잠금 파일 기준으로 관리.

## Related

- [[dev-automation-detail]] — Ruff 설정·Slack Bot scope 등 상세판
- [[db-access-control]] — 자격증명을 코드·문서에 두지 않는 원칙의 DB 쪽 대응
- [[db-security-review-patterns]] — 자리표시자 비밀번호가 실제 위험이 된 사례
- [[aws-aidlc-workflows-v2-study]] — 에이전트 워크플로 도구 도입 시의 판단 기준
- [[superpowers-agentic-development-methodology]] — 개발 규율을 스킬로 강제하는 접근
- [[obsidian-wiki-tooling-gotchas]] — 이 기준을 적용한 볼트 쪽 도구 함정(wikilink 해석, 실행 권한 diff)
