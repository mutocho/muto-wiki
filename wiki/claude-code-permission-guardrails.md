---
title: 이 머신의 Claude Code 권한 가드레일 동작
category: 참고자료
tags: [claude-code, environment, gotcha, mcp]
summary: 로컬 파일·설정 변경을 막는 훅과 auto mode 분류기, 그리고 서버 feature flag로 Claude 호스팅 MCP의 로컬 OAuth가 차단되는 양상과 진단·대안.
sources: [작업 세션 기록 (2026-08-04), 작업 세션 기록 (2026-08-12)]
status: draft
created: 2026-08-04
updated: 2026-08-12
notion_page_id: "3bdfb969-b8be-8150-ab1e-d714bf78b67e"
notion_synced: "2026-08-15T19:11:17+0900"
---

> [!tip] 핵심 Takeaway
> - **MCP 도구가 안 보이면 로컬 등록 실패부터 의심하지 말 것.** `~/.claude.json`의 `cachedGrowthBookFeatures > tengu_mcp_local_oauth_blocked_hosts`를 먼저 본다. 증상이 명시적 OAuth 오류가 아니라 "도구 없음/취소"로 나타나 오진하기 쉽다
> - 이 flag는 **서버에서 다시 받아오는 캐시**다. 로컬을 지워도 다음 실행에 덮어써지므로 로컬 편집은 해결책이 아니다 — 자체 호스트 MCP 서버가 유일한 지속 대안 ^[inferred]
> - **에이전트가 막히는 지점은 미리 알고 설계한다** — `.env` 생성, `~/.claude/settings.json` 수정, 외부 스크립트 curl은 차단된다. DB 툴 설치 절차를 자동화할 때 이 세 가지는 사용자 `!` 명령으로 넘기는 것을 전제로 만든다
> - 사용자가 손으로 고친 JSON은 반드시 `python3 -c "json.load(...)"`로 검증한다. 트레일링 콤마가 흔하다

# 이 머신의 Claude Code 권한 가드레일 동작

## Findings

- `Write` 툴로 `.env` 파일 생성은 `~/.claude/scripts/block-sensitive.py` PreToolUse 훅이 차단한다. 우회: `env.example`로 쓰고 사용자가 `! mv`로 rename.
- `~/.claude/settings.json` 수정은 Bash/Edit/스킬 모든 경로에서 auto mode 분류기가 차단한다 — 단, 깨진 JSON을 **수리**하는 Edit은 통과했다(비결정적일 수 있음). 신규 설정 추가는 사용자에게 `!` 명령을 안내하는 게 확실하다.
- 외부 raw.githubusercontent.com에서 셸 스크립트를 curl로 받는 것도 분류기가 차단한다. 사용자가 `!` 프리픽스로 직접 실행하면 된다.
- 사용자가 JSON을 수동 편집할 때 트레일링 콤마 오류가 나기 쉬우므로, 등록 후 `python3 -c "json.load(...)"`로 반드시 검증할 것.

## Claude 호스팅 Google Calendar MCP의 OAuth 차단

- `~/.claude.json`의 `cachedGrowthBookFeatures` 안에 있는 `tengu_mcp_local_oauth_blocked_hosts`에는 `microsoft365.mcp.claude.com`, `gmail.mcp.claude.com`, `gcal.mcp.claude.com`이 포함돼 있었다. Claude Code CLI는 이 호스트들의 로컬 OAuth를 거부하므로 세션에 `google-calendar` MCP 도구가 나타나지 않는다.
- 이 값은 시작 시 서버에서 다시 받아오는 feature-flag cache다. 로컬 항목을 수정하거나 지워도 다음 실행에서 덮어써지므로 로컬 편집만으로 차단을 지속 해제할 수 없다. ^[inferred]
- 대표 증상은 명시적인 OAuth 오류보다 MCP 호출의 취소·도구 없음으로 나타난다. 등록 요청을 수행하기 전에 세션의 실제 도구 목록과 blocked-hosts flag를 함께 확인한다.
- 대안은 자체 Google Cloud OAuth client를 쓰는 별도 호스트의 로컬 Google Calendar MCP 서버를 등록하는 것이다. 차단이 capability가 아니라 호스트 목록 기준이라면 다른 호스트는 영향을 받지 않는다. ^[inferred]
- macOS `Calendar.app`을 `osascript`로 제어하는 우회는 시스템 설정의 인터넷 계정에 Google 계정이 연결돼 있을 때만 Google Calendar에 반영된다. 로컬 캘린더만 보이는 상태에서는 Google 동기화 대안이 아니다.

## Related

- [[index|Wiki Index]]
- [[obsidian-wiki-tooling-gotchas|obsidian-wiki 도구 동작 함정]]
- [[dev-automation-detail]] — 에이전트가 다루는 개발 환경 설정 상세
