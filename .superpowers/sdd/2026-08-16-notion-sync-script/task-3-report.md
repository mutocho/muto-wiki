# Task 3 Report: 네트워크 경계 — 토큰 로드 · API 호출 · 재시도

## TDD Process

### RED: Tests Fail Before Implementation

```bash
$ python3 -m unittest discover -s scripts -p 'test_*.py' -v 2>&1 | grep -E "(ERROR|FAILED)"
```

Output (8 errors):
```
ERROR: test_env_var_wins (test_notion_sync.TestLoadToken.test_env_var_wins)
AttributeError: module 'notion_sync' has no attribute 'load_token'

ERROR: test_missing_key_raises (test_notion_sync.TestLoadToken.test_missing_key_raises)
AttributeError: module 'notion_sync' has no attribute 'AuthError'

ERROR: test_no_env_file_raises (test_notion_sync.TestLoadToken.test_no_env_file_raises)
AttributeError: module 'notion_sync' has no attribute 'AuthError'

ERROR: test_reads_dotenv (test_notion_sync.TestLoadToken.test_reads_dotenv)
AttributeError: module 'notion_sync' has no attribute 'load_token'

ERROR: test_rejects_loose_permissions (test_notion_sync.TestLoadToken.test_rejects_loose_permissions)
AttributeError: module 'notion_sync' has no attribute 'AuthError'

(more similar errors...)

Ran 28 tests in 0.026s
FAILED (errors=8)
```

### GREEN: Tests Pass After Implementation

```bash
$ python3 -m unittest discover -s scripts -p 'test_*.py' -v 2>&1 | tail -5
```

Output:
```
test_three_engine_tags_is_comparison (test_notion_sync.TestRouteEngine.test_three_engine_tags_is_comparison) ... ok

----------------------------------------------------------------------
Ran 28 tests in 0.066s

OK
```

## Changes Made

### 1. `scripts/notion-sync.py`

**Added imports:**
- `json` — JSON serialization with `ensure_ascii=False`
- `os` — Environment variable access
- `subprocess` — Git tracking validation
- `time` — Delay management in retries
- `urllib.error`, `urllib.request` — HTTP API calls

**Added module constants:**
- `NOTION_VERSION = "2026-03-11"` — Notion API version
- `API_ROOT = "https://api.notion.com/v1"` — Notion API endpoint
- `DBA_PAGE_ID = "3aefb969b8be801280b8dc2ff35fbefb"` — Target parent page ID

**Added exception classes:**
- `AuthError(Exception)` — Token cannot be loaded safely
- `ApiError(Exception)` — Notion API call failed

**Added `load_token(root=ROOT) -> str`:**
- Checks `NOTION_API_KEY` environment variable first (takes precedence)
- Falls back to reading `.env` file in repository root
- **Safety guards:**
  - Raises `AuthError` if neither env var nor file exists
  - Raises `AuthError` if `.env` is tracked by git (prevents token commit)
  - Raises `AuthError` if `.env` permissions are not exactly `0o600`
- Parses `.env` format: `KEY=value` with quote stripping
- Token value is never printed in any error message

**Added `api(method, path, token, body=None, retries=3, sleep=time.sleep) -> dict`:**
- Constructs HTTP request with proper Notion headers
- JSON body serialized with `ensure_ascii=False` (preserves Korean, no 2.24x bloat)
- Exponential backoff retry strategy:
  - Retries on HTTP 429 (rate limit) or 5xx errors
  - Does NOT retry on 4xx client errors
  - Sleep durations: 1, 2, 4, 8... seconds (doubling)
- Returns parsed JSON response
- Raises `ApiError` on non-retryable errors or retry exhaustion
- Sleep function is injectable for testing

### 2. `scripts/test_notion_sync.py`

**Added import:**
- `import unittest.mock` — For mocking HTTP calls

**Added test class `TestLoadToken`:**
- `test_env_var_wins` — Environment variable takes precedence over `.env`
- `test_reads_dotenv` — Reads quoted value from `.env` file
- `test_rejects_loose_permissions` — Raises `AuthError` if permissions != 0o600
- `test_missing_key_raises` — Raises `AuthError` if `.env` lacks `NOTION_API_KEY`
- `test_no_env_file_raises` — Raises `AuthError` if no `.env` exists

**Added test class `TestApiRetry`:**
- `test_retries_on_429_then_succeeds` — Retries on HTTP 429, succeeds on 3rd attempt
  - Verifies exponential backoff: `slept == [1, 2]`
  - Uses injected sleep function (no actual waiting)
- `test_does_not_retry_on_400` — No retry on HTTP 400; raises `ApiError` immediately
- `test_body_is_raw_utf8_not_escaped` — Verifies JSON uses `ensure_ascii=False`
  - Korean characters are UTF-8 bytes, not `\uXXXX` escapes
  - Confirms payload size efficiency (§6.4 ① of CLAUDE.md)

## Test Coverage

**All 28 tests passing:**
- 20 existing tests (Tasks 1–2) continue to pass
- 8 new tests for network boundary (Task 3)

## Commit

```
commit 19c3731
Author: Muto <muto@...local>

feat(notion-sync): 토큰 로드 가드와 API 호출 재시도

.env가 git에 추적 중이거나 퍼미션이 600이 아니면 실행을 거부한다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
```

## Interfaces Ready for Task 4+

- `NOTION_VERSION`, `API_ROOT`, `DBA_PAGE_ID` — Module constants
- `class AuthError(Exception)` — Token load failed
- `class ApiError(Exception)` — API call failed
- `load_token(root=ROOT) -> str` — Secure token retrieval with guards
- `api(method, path, token, body=None, retries=3, sleep=time.sleep) -> dict` — HTTP with exponential backoff

All required for Tasks 4–7 (page batch fetch, transformation, upload, CLI orchestration).

---

## Fix Report: Git Tracking Guard Coverage (Review Finding)

**Finding:** The security-critical guard that prevents `.env` from being tracked by git had zero test coverage. All five original `TestLoadToken` tests used non-git tempdirs.

### Solution

Added one test to `TestLoadToken`: `test_rejects_env_tracked_by_git`

**Test code:**
```python
def test_rejects_env_tracked_by_git(self):
    import subprocess
    subprocess.run(["git", "init", "-q", str(self.root)], check=True)
    self._write_env("NOTION_API_KEY=x\n")
    subprocess.run(["git", "-C", str(self.root), "add", "-f", ".env"], check=True)
    with self.assertRaises(ns.AuthError) as cm:
        ns.load_token(self.root)
    self.assertIn("추적", str(cm.exception))
```

**What it does:**
1. Initializes a real git repo in the tempdir with `-q` (quiet)
2. Writes `.env` with test credentials
3. Stages `.env` in git with `-f` (force, ignoring any `.gitignore`)
4. Calls `load_token()` and verifies it raises `AuthError` mentioning "추적" (tracking)

### Guard Inversion Verification

**Inverted guard line 194 from:**
```python
if tracked.returncode == 0:  # If file IS tracked
```
**to:**
```python
if tracked.returncode != 0:  # If file is NOT tracked (WRONG)
```

**Test results with inverted guard:**
```
Ran 29 tests in 0.115s
FAILED (failures=2, errors=1)

FAIL: test_rejects_env_tracked_by_git (test_notion_sync.TestLoadToken.test_rejects_env_tracked_by_git)
AssertionError: AuthError not raised  ← Guard failed to detect tracked .env

FAIL: test_reads_dotenv (test_notion_sync.TestLoadToken.test_reads_dotenv)
AssertionError: '퍼미션' not found in '중단: .env가 git에 추적되고 있다...'
```

The new test **correctly failed** when the guard was inverted, proving it exercises the security-critical branch.

**Guard restored to correct condition:**
```python
if tracked.returncode == 0:  # Correct: returncode 0 means file IS tracked
```

### All Tests Passing After Fix

```bash
$ python3 -m unittest discover -s scripts -p 'test_*.py' -v 2>&1 | tail -5
```

Output:
```
Ran 29 tests in 0.118s

OK
```

**Coverage status:**
- 20 existing tests (Tasks 1–2)
- 8 network boundary tests (Task 3 original)
- 1 git tracking guard test (Task 3 fix) ← **NEW**
- **Total: 29 tests, all passing**

### Commit

Auto-committed by `.claude/settings.json` hooks:
```
commit 144850e
    wiki: 2026-08-16 17:54:01 동기화
    
    scripts/test_notion_sync.py | 9 +++++++++
```

The test now guards the most security-sensitive branch: preventing a Notion API token from being committed to git.
