---
title: >-
  Claude Code CLI blocks gcal.mcp.claude.com OAuth via server-side feature flag
tags: [claude-code, mcp, troubleshooting]
summary: >-
  Google Calendar MCP fails silently in Claude Code CLI because gcal.mcp.claude.com is in a server-fetched blocked-hosts flag; editing the local cache does not help.
project: muto
base_confidence: 0.75
provenance:
  extracted: 0.8
  inferred: 0.2
lifecycle: draft
lifecycle_changed: 2026-08-12
sources:
  - muto session (2026-08-12)
---

# Findings

## Google Calendar MCP is blocked at the host level in Claude Code CLI

`~/.claude.json` contains `tengu_mcp_local_oauth_blocked_hosts` listing
`microsoft365.mcp.claude.com`, `gmail.mcp.claude.com`, `gcal.mcp.claude.com`.
Local OAuth for those hosts is refused, so no `google-calendar` MCP tool ever
appears in the session.

The flag lives inside the `cachedGrowthBookFeatures` key — a server-fetched
feature-flag cache refreshed on startup. Hand-editing or deleting the entry is
overwritten on the next launch, so the block cannot be lifted locally.^[inferred]

**Symptom shape:** a prompt that instructs the agent to "register via
google-calendar MCP" reports the tool call as cancelled/unavailable rather than
erroring loudly, because the tool simply is not present.

**Workarounds:**
- Register a *different* MCP host (a local google-calendar MCP server with your
  own Google Cloud OAuth client) — the blocklist matches hosts, not capability,
  so a self-hosted server is unaffected.
- Or bypass MCP entirely via `osascript` against macOS Calendar.app — but this
  only reaches Google if a Google account is linked under
  System Settings → Internet Accounts. A fresh Calendar.app shows only
  `캘린더 / 예정된 미리 알림 / 생일 / Siri 제안`, none of which sync to Google.

## Related
- [[claude-code]]
- [[mcp]]
