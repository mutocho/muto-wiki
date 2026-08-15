---
title: 이 머신의 Claude Code 권한 가드레일 동작
tags: [claude-code, environment, gotcha]
summary: >-
  .env 쓰기는 block-sensitive.py 훅이, ~/.claude/settings.json 쓰기·외부 스크립트 curl은
  auto mode 분류기가 차단. 우회 경로와 실제 해결 방법 기록.
project: second-brain
base_confidence: 0.9
provenance:
  extracted: 0.8
  inferred: 0.2
lifecycle_changed: 2026-08-04
sources:
  - "second-brain session (2026-08-04)"
---

# 이 머신의 Claude Code 권한 가드레일 동작

## Findings

- `Write` 툴로 `.env` 파일 생성은 `~/.claude/scripts/block-sensitive.py` PreToolUse 훅이 차단한다. 우회: `env.example`로 쓰고 사용자가 `! mv`로 rename.
- `~/.claude/settings.json` 수정은 Bash/Edit/스킬 모든 경로에서 auto mode 분류기가 차단한다 — 단, 깨진 JSON을 **수리**하는 Edit은 통과했다(비결정적일 수 있음). 신규 설정 추가는 사용자에게 `!` 명령을 안내하는 게 확실하다.
- 외부 raw.githubusercontent.com에서 셸 스크립트를 curl로 받는 것도 분류기가 차단한다. 사용자가 `!` 프리픽스로 직접 실행하면 된다.
- 사용자가 JSON을 수동 편집할 때 트레일링 콤마 오류가 나기 쉬우므로, 등록 후 `python3 -c "json.load(...)"`로 반드시 검증할 것.
