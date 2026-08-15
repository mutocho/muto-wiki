---
title: 개발 도구 운영 기준 — Ruff·CLAUDE.md·자격증명
tags: [dev, tooling, ci]
topics: [dba]
summary: >-
  정제된 핵심 가이드에서 추출한 개발 표준: Ruff check/format 분리, CLAUDE.md 배치 규칙,
  자격증명 주입 원칙, CI 검사 분리.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: 정제된 핵심 가이드 (2026-07-30)"
  - "Notion: 개발 및 자동화 (2026-07-30)"
---

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
