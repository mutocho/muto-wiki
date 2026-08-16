# Notion 동기화 스크립트 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `wiki/` → Notion 단방향 동기화를 Claude MCP 호출에서 독립 실행 가능한 Python 스크립트로 옮긴다.

**Architecture:** 단일 진입점 `scripts/notion-sync.py`가 증분 판정 → 배치 결정 → 변환 → HOLD 검사 → 업로드 → 스탬프 → 로그를 수행한다. 기존 `notion-convert.py`의 출력이 그대로 공식 API의 `markdown` 필드 입력이므로 변환기는 손대지 않고 재사용한다. 판단이 필요한 건은 업로드하지 않고 HOLD로 보고한다.

**Tech Stack:** Python 3.11 표준 라이브러리만 (`urllib.request`, `json`, `re`, `argparse`, `unittest`). 외부 패키지 없음.

**Spec:** `docs/superpowers/specs/2026-08-16-notion-sync-script-design.md`

## Global Constraints

- **외부 의존성 금지.** `requests` 등 설치가 필요한 패키지를 쓰지 않는다. 이 저장소는 개인 위키이며 가상환경·빌드 설정이 없다.
- **테스트는 stdlib `unittest`.** pytest는 설치돼 있지 않다. 실행은 `python3 -m unittest discover -s scripts -p 'test_*.py' -v`.
- **JSON 직렬화는 항상 `ensure_ascii=False`.** 한글을 `\uXXXX`로 이스케이프하면 문자 수가 2.24배로 부푼다 (`CLAUDE.md` §6.4 ①).
- **Notion API 헤더 고정**: `Notion-Version: 2026-03-11`, `Authorization: Bearer <token>`, `Content-Type: application/json`. API 루트는 `https://api.notion.com/v1`.
- **DBA 부모 페이지 ID**: `3aefb969b8be801280b8dc2ff35fbefb` (확정, 재질문 금지 — `CLAUDE.md` §6).
- **토큰을 출력하지 않는다.** 로그·에러 메시지·계획 출력 어디에도 토큰 값을 찍지 않는다.
- **전 페이지를 대상으로 만드는 플래그를 만들지 않는다.** §6.3 "전체 재업로드 금지"를 코드로 강제한다.
- **브랜치를 만들지 않는다.** 모든 커밋은 `main`에서 직접 한다 (`CLAUDE.md` §8).
- **`git commit` 메시지 말미에 다음 줄을 넣는다:**
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

## File Structure

| 파일 | 상태 | 책임 |
|---|---|---|
| `scripts/notion-sync.py` | 생성 | 단일 진입점. 판정·배치·HOLD·업로드·스탬프·로그·CLI |
| `scripts/test_notion_sync.py` | 생성 | HTTP 없는 순수 함수 단위 테스트 |
| `scripts/notion-tree.json` | 생성(Task 7 실행 시) | 컨테이너 이름 → page_id |
| `scripts/notion-convert.py` | 변경 없음 | `convert()`·`mask_code()`·`load_page_ids()` 재사용 |
| `scripts/notion-stamp.py` | 변경 없음 | `stamp()` 재사용 |
| `CLAUDE.md` | 수정 | §6 전면 개정 (Task 8) |

`notion-sync.py`는 한 파일이지만 절 경계를 주석으로 명확히 나눈다. 이 저장소의 `scripts/`는 독립 실행 스크립트를 평평하게 두는 구조이며, 패키지 디렉터리를 새로 만드는 것은 이 작업의 범위를 넘는다.

**하이픈 파일명 import.** `notion-convert.py`·`notion-stamp.py`는 하이픈이라 일반 `import`가 불가능하다. `importlib.util.spec_from_file_location`으로 로드한다. 파일명을 바꾸면 `CLAUDE.md` §6.4의 스크립트 참조가 깨지므로 이쪽을 택한다. `notion-sync.py` 자신도 같은 이유로 하이픈을 유지하며, 테스트도 같은 방식으로 로드한다.

---

### Task 1: 스켈레톤 · 프론트매터 읽기 · 증분 판정

**Files:**
- Create: `scripts/notion-sync.py`
- Test: `scripts/test_notion_sync.py`

**Interfaces:**
- Consumes: 없음 (최초 태스크)
- Produces:
  - `ROOT: pathlib.Path`, `WIKI: pathlib.Path`, `SCRIPTS: pathlib.Path`
  - `read_fm(path: pathlib.Path) -> dict[str, str]` — frontmatter의 스칼라 필드만. 값의 감싸는 따옴표를 벗긴다
  - `parse_tags(fm: dict) -> list[str]` — `tags: [a, b]`를 `["a","b"]`로
  - `is_target(fm: dict) -> bool` — §6.3 증분 판정
  - `knowledge_pages() -> dict[str, dict]` — slug → fm. `category: 색인`(index·log) 제외

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`scripts/test_notion_sync.py` 생성:

```python
#!/usr/bin/env python3
"""notion-sync.py 단위 테스트. HTTP 호출은 하지 않는다.

실행: python3 -m unittest discover -s scripts -p 'test_*.py' -v
"""
import importlib.util
import pathlib
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent


def load(name, filename):
    """하이픈 파일명 모듈을 로드한다."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ns = load("notion_sync", "notion-sync.py")


class TestReadFrontmatter(unittest.TestCase):
    def test_scalar_fields_and_quote_stripping(self):
        p = pathlib.Path(self.tmp) / "x.md"
        p.write_text(
            '---\n'
            'title: 제목\n'
            'category: db운영\n'
            'tags: [mysql, aurora]\n'
            'status: draft\n'
            'updated: 2026-08-16\n'
            'notion_page_id: "3bdf-abc"\n'
            'notion_synced: null\n'
            '---\n\n본문\n',
            encoding="utf-8",
        )
        fm = ns.read_fm(p)
        self.assertEqual(fm["title"], "제목")
        self.assertEqual(fm["category"], "db운영")
        self.assertEqual(fm["notion_page_id"], "3bdf-abc")  # 따옴표가 벗겨짐
        self.assertEqual(fm["notion_synced"], "null")

    def setUp(self):
        import tempfile
        self._d = tempfile.TemporaryDirectory()
        self.tmp = self._d.name

    def tearDown(self):
        self._d.cleanup()


class TestParseTags(unittest.TestCase):
    def test_inline_array(self):
        self.assertEqual(ns.parse_tags({"tags": "[mysql, aurora, backup]"}),
                         ["mysql", "aurora", "backup"])

    def test_missing_tags_is_empty(self):
        self.assertEqual(ns.parse_tags({}), [])


class TestIsTarget(unittest.TestCase):
    def test_never_synced_is_target(self):
        self.assertTrue(ns.is_target({"updated": "2026-08-16", "notion_synced": "null"}))

    def test_same_day_is_target(self):
        # '>' 로 비교하면 같은 날 수정분이 영원히 누락된다 — 2026-08-15에 13개 중 12개가 실제로 빠졌다
        self.assertTrue(ns.is_target(
            {"updated": "2026-08-16", "notion_synced": "2026-08-16T19:21:54+0900"}))

    def test_updated_after_sync_is_target(self):
        self.assertTrue(ns.is_target(
            {"updated": "2026-08-16", "notion_synced": "2026-08-15T19:21:54+0900"}))

    def test_updated_before_sync_is_skipped(self):
        self.assertFalse(ns.is_target(
            {"updated": "2026-08-14", "notion_synced": "2026-08-15T19:21:54+0900"}))


class TestKnowledgePages(unittest.TestCase):
    def test_excludes_index_category(self):
        pages = ns.knowledge_pages()
        self.assertNotIn("index", pages)
        self.assertNotIn("log", pages)
        self.assertIn("aurora-dsql", pages)

    def test_counts_35_knowledge_pages(self):
        self.assertEqual(len(ns.knowledge_pages()), 35)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: FAIL — `FileNotFoundError` 또는 `notion-sync.py` 없음

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/notion-sync.py` 생성:

```python
#!/usr/bin/env python3
"""wiki/ -> Notion 단방향 동기화 (CLAUDE.md §6).

wiki가 항상 진실이다. Notion에서 직접 편집한 내용은 회수하지 않는다.

사용:
  python3 scripts/notion-sync.py                    증분 동기화
  python3 scripts/notion-sync.py --dry-run          계획만 출력 (HTTP 호출 0)
  python3 scripts/notion-sync.py --only <slug>...   지정 페이지만
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
SCRIPTS = ROOT / "scripts"


# --------------------------------------------------------------------------
# 프론트매터
# --------------------------------------------------------------------------

def read_fm(path):
    """frontmatter의 스칼라 필드를 dict로 읽는다.

    여러 줄 리스트(sources 등)는 이 동기화에 필요 없으므로 키만 남고 값은 빈 문자열이 된다.
    """
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split("\n"):
        km = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if km:
            fm[km.group(1)] = km.group(2).strip().strip('"')
    return fm


def parse_tags(fm):
    """tags: [a, b] -> ['a', 'b']"""
    m = re.match(r"^\[(.*)\]$", fm.get("tags", "").strip())
    if not m:
        return []
    return [t.strip() for t in m.group(1).split(",") if t.strip()]


def knowledge_pages():
    """slug -> frontmatter. category: 색인(index·log)은 동기화 대상이 아니다 (§6)."""
    out = {}
    for p in sorted(WIKI.glob("*.md")):
        fm = read_fm(p)
        if fm.get("category") == "색인":
            continue
        out[p.stem] = fm
    return out


# --------------------------------------------------------------------------
# 증분 판정 (§6.3)
# --------------------------------------------------------------------------

def is_target(fm):
    """올릴 대상인가.

    비교는 날짜 10자로 자른 문자열이며 '>' 가 아니라 '>=' 다.
    '>' 로 하면 같은 날 동기화한 뒤 수정한 페이지가 영원히 누락된다.
    누락보다 중복이 낫다 — 누락은 조용하지만 중복은 눈에 보인다.
    """
    synced = fm.get("notion_synced", "null")
    if synced in ("null", ""):
        return True
    return fm.get("updated", "")[:10] >= synced[:10]
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: PASS — 8개 테스트 전부

- [ ] **Step 5: 커밋한다**

```bash
git add scripts/notion-sync.py scripts/test_notion_sync.py
git commit -m "feat(notion-sync): 프론트매터 읽기와 증분 판정

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 배치 결정 — index 절 파싱 + 엔진 분기

**Files:**
- Modify: `scripts/notion-sync.py` (Task 1 끝에 이어 붙인다)
- Test: `scripts/test_notion_sync.py` (클래스 추가)

**Interfaces:**
- Consumes: `WIKI`, `parse_tags(fm)`, `knowledge_pages()` (Task 1)
- Produces:
  - `SECTION_TO_PARENT: dict[str, str]` — index 절 제목 → Notion 컨테이너 이름
  - `ENGINE_SECTION: str` = `"엔진별 운영"`
  - `index_sections() -> dict[str, str]` — slug → 분류 절 제목
  - `route_engine(tags: list[str]) -> str` — 엔진 컨테이너 이름
  - `placement(slug, fm, sections) -> str` — 컨테이너 이름. 판정 불가 시 `HoldError`
  - `class HoldError(Exception)` — 사람 판단이 필요해 업로드하지 않는 경우

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`scripts/test_notion_sync.py`의 `if __name__` 앞에 추가:

```python
class TestRouteEngine(unittest.TestCase):
    def test_dsql_wins_over_aurora(self):
        # aurora-dsql은 tags에 aurora와 dsql이 함께 있다. dsql이 이겨야 한다.
        self.assertEqual(
            ns.route_engine(["dba", "aws", "aurora", "dsql", "architecture"]),
            "Aurora DSQL")

    def test_three_engine_tags_is_comparison(self):
        # db-common-concepts — 3사 대조 페이지
        self.assertEqual(
            ns.route_engine(["dba", "sql", "comparison", "mysql", "postgresql", "sqlserver"]),
            "엔진 비교")

    def test_single_engine_tag(self):
        self.assertEqual(ns.route_engine(["dba", "mysql", "backup"]), "MySQL")
        self.assertEqual(ns.route_engine(["dba", "postgresql", "vacuum"]), "PostgreSQL")
        self.assertEqual(ns.route_engine(["dba", "sqlserver", "ha"]), "SQL Server")

    def test_aurora_alone_is_not_a_routing_key(self):
        # cloud-platform-knowledge — aurora 태그가 있지만 엔진 태그가 없다.
        # aurora를 키로 쓰면 MySQL로 오배치된다.
        self.assertEqual(
            ns.route_engine(["dba", "aws", "aurora", "docker", "azure", "linux"]),
            "엔진 비교")

    def test_aurora_mysql_page_goes_to_mysql(self):
        # aurora-vs-mysql-replication-architecture — mysql 태그가 원 엔진을 표현한다
        self.assertEqual(
            ns.route_engine(["dba", "mysql", "aurora", "replication", "performance"]),
            "MySQL")


class TestIndexSections(unittest.TestCase):
    def setUp(self):
        self.sections = ns.index_sections()

    def test_engine_section_has_12_pages(self):
        engine = [s for s, sec in self.sections.items() if sec == ns.ENGINE_SECTION]
        self.assertEqual(len(engine), 12)

    def test_ignores_open_tasks_section(self):
        # '미완 과제' 절은 17개 링크를 갖고 있다. 여기서 잡히면 대부분이 오배치된다.
        # notion-remediation-backlog는 '지식 운영' 절 소속이면서 '미완 과제'에도 링크된다 —
        # 둘 중 분류 절이 이겨야 한다.
        self.assertEqual(self.sections.get("notion-remediation-backlog"), "지식 운영")
        for sec in self.sections.values():
            self.assertNotIn("미완 과제", sec)

    def test_every_knowledge_page_is_classified(self):
        missing = sorted(set(ns.knowledge_pages()) - set(self.sections))
        self.assertEqual(missing, [], f"분류 절에 없는 페이지: {missing}")


class TestPlacement(unittest.TestCase):
    def test_all_35_pages_resolve(self):
        sections = ns.index_sections()
        pages = ns.knowledge_pages()
        for slug, fm in pages.items():
            with self.subTest(slug=slug):
                parent = ns.placement(slug, fm, sections)
                self.assertIn(parent, ns.CONTAINER_NAMES)

    def test_known_placements(self):
        sections = ns.index_sections()
        pages = ns.knowledge_pages()
        expected = {
            "aurora-dsql": "Aurora DSQL",
            "cloud-platform-knowledge": "엔진 비교",
            "db-common-concepts": "엔진 비교",
            "mysql-operations": "MySQL",
            "postgresql-operations": "PostgreSQL",
            "sqlserver-operations": "SQL Server",
            "operational-queries": "진단·운영 표준",
            "db-access-control": "보안·권한",
            "worklog-kakaogames-2026": "kakaogames",
            "todo": "개인",
            "verbal-source-verification-policy": "종합원칙",
        }
        for slug, want in expected.items():
            with self.subTest(slug=slug):
                self.assertEqual(ns.placement(slug, pages[slug], sections), want)

    def test_unknown_page_raises_hold(self):
        with self.assertRaises(ns.HoldError):
            ns.placement("존재하지-않는-페이지", {"tags": "[]"}, ns.index_sections())
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: FAIL with `AttributeError: module 'notion_sync' has no attribute 'route_engine'`

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/notion-sync.py` 끝에 추가:

```python
# --------------------------------------------------------------------------
# 배치 (§6.1) — index.md에서 파생한다
# --------------------------------------------------------------------------

class HoldError(Exception):
    """사람 판단이 필요해 업로드하지 않는다."""


# index.md 절 제목 -> Notion 컨테이너 이름.
# 두 곳의 이름이 일부 다르다(업무 기록/kakaogames, 종합·원칙/종합원칙).
SECTION_TO_PARENT = {
    "진단·운영 표준": "진단·운영 표준",
    "보안·권한": "보안·권한",
    "개발·자동화": "개발·자동화",
    "지식 운영": "지식 운영",
    "업무 기록": "kakaogames",
    "개인": "개인",
    "참고자료": "참고자료",
    "종합·원칙": "종합원칙",
}

ENGINE_SECTION = "엔진별 운영"

# 페이지를 받는 부모 13개 + 중간 노드 3개 = 컨테이너 16개
CONTAINER_NAMES = [
    "db운영", "MySQL", "PostgreSQL", "SQL Server", "Aurora DSQL", "엔진 공통",
    "엔진 비교", "진단·운영 표준", "보안·권한", "개발·자동화", "지식 운영",
    "업무기록", "kakaogames", "개인", "참고자료", "종합원칙",
]

# aurora는 라우팅 키가 아니다 — 호스팅 변종 표식일 뿐이며,
# 원 엔진은 항상 함께 붙는 mysql/postgresql 태그가 표현한다.
ENGINE_TAGS = {"mysql": "MySQL", "postgresql": "PostgreSQL", "sqlserver": "SQL Server"}


def index_sections():
    """slug -> 분류 절 제목. 분류 절 밖의 링크는 무시한다.

    '미완 과제' 절과 Takeaway·부제의 링크를 세면 대부분의 페이지가 오배치된다.
    """
    out = {}
    cur = None
    for line in (WIKI / "index.md").read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^#{2,3}\s+(.*)$", line)
        if m:
            cur = m.group(1).strip()
            continue
        if cur != ENGINE_SECTION and cur not in SECTION_TO_PARENT:
            continue
        for target in re.findall(r"\[\[([^\]\|]+)", line):
            out.setdefault(target.strip(), cur)
    return out


def route_engine(tags):
    """'엔진별 운영' 절 안에서만 쓰는 엔진 분기 (§6.1)."""
    if "dsql" in tags:
        return "Aurora DSQL"
    hits = {ENGINE_TAGS[t] for t in tags if t in ENGINE_TAGS}
    if len(hits) == 1:
        return hits.pop()
    return "엔진 비교"


def placement(slug, fm, sections):
    """이 페이지가 들어갈 Notion 컨테이너 이름."""
    section = sections.get(slug)
    if section is None:
        raise HoldError(f"{slug}: index.md의 분류 절에서 찾을 수 없다")
    if section == ENGINE_SECTION:
        return route_engine(parse_tags(fm))
    parent = SECTION_TO_PARENT.get(section)
    if parent is None:
        raise HoldError(f"{slug}: 알 수 없는 절 '{section}'")
    return parent
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: PASS — 전부. 특히 `test_all_35_pages_resolve`가 35개 subTest 전부 통과

- [ ] **Step 5: 커밋한다**

```bash
git add scripts/notion-sync.py scripts/test_notion_sync.py
git commit -m "feat(notion-sync): index.md 기반 배치 결정과 엔진 분기

aurora는 라우팅 키에서 제외한다. 키로 쓰면 aurora-dsql이 MySQL로,
cloud-platform-knowledge가 MySQL로 오배치된다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 네트워크 경계 — 토큰 로드 · API 호출 · 재시도

**Files:**
- Modify: `scripts/notion-sync.py`
- Test: `scripts/test_notion_sync.py`

**Interfaces:**
- Consumes: `ROOT` (Task 1)
- Produces:
  - `NOTION_VERSION: str` = `"2026-03-11"`, `API_ROOT: str`, `DBA_PAGE_ID: str`
  - `class AuthError(Exception)`, `class ApiError(Exception)`
  - `load_token(root: pathlib.Path = ROOT) -> str` — 환경변수 우선, 없으면 `.env`. 가드 위반 시 `AuthError`
  - `api(method, path, token, body=None, retries=3, sleep=time.sleep) -> dict`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
class TestLoadToken(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self._d = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._d.name)
        self._saved = os.environ.pop("NOTION_API_KEY", None)

    def tearDown(self):
        import os
        if self._saved is not None:
            os.environ["NOTION_API_KEY"] = self._saved
        self._d.cleanup()

    def _write_env(self, text, mode=0o600):
        p = self.root / ".env"
        p.write_text(text, encoding="utf-8")
        p.chmod(mode)
        return p

    def test_env_var_wins(self):
        import os
        os.environ["NOTION_API_KEY"] = "from-env-var"
        self._write_env("NOTION_API_KEY=from-file\n")
        self.assertEqual(ns.load_token(self.root), "from-env-var")

    def test_reads_dotenv(self):
        self._write_env('NOTION_API_KEY="ntn_secret"\n')
        self.assertEqual(ns.load_token(self.root), "ntn_secret")

    def test_rejects_loose_permissions(self):
        self._write_env("NOTION_API_KEY=x\n", mode=0o644)
        with self.assertRaises(ns.AuthError) as cm:
            ns.load_token(self.root)
        self.assertIn("퍼미션", str(cm.exception))

    def test_missing_key_raises(self):
        self._write_env("OTHER=1\n")
        with self.assertRaises(ns.AuthError):
            ns.load_token(self.root)

    def test_no_env_file_raises(self):
        with self.assertRaises(ns.AuthError):
            ns.load_token(self.root)


class TestApiRetry(unittest.TestCase):
    def test_retries_on_429_then_succeeds(self):
        import io, json, urllib.error
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            if len(calls) < 3:
                raise urllib.error.HTTPError(req.full_url, 429, "rate limited", {}, None)
            return io.BytesIO(json.dumps({"id": "ok"}).encode("utf-8"))

        slept = []
        with unittest.mock.patch.object(ns.urllib.request, "urlopen", fake_urlopen):
            out = ns.api("GET", "/pages/x", "tok", sleep=slept.append)
        self.assertEqual(out, {"id": "ok"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(slept, [1, 2])  # 지수 백오프

    def test_does_not_retry_on_400(self):
        import io
        import urllib.error
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            raise urllib.error.HTTPError(
                req.full_url, 400, "bad", {}, io.BytesIO(b'{"message":"nope"}'))

        with unittest.mock.patch.object(ns.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(ns.ApiError):
                ns.api("POST", "/pages", "tok", {"a": 1}, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)

    def test_body_is_raw_utf8_not_escaped(self):
        import io, json
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["data"] = req.data
            return io.BytesIO(json.dumps({}).encode("utf-8"))

        with unittest.mock.patch.object(ns.urllib.request, "urlopen", fake_urlopen):
            ns.api("POST", "/pages", "tok", {"markdown": "한글"}, sleep=lambda s: None)
        # ensure_ascii=False — \uXXXX 이스케이프는 문자 수를 2.24배로 부풀린다
        self.assertIn("한글".encode("utf-8"), seen["data"])
        self.assertNotIn(b"\\u", seen["data"])
```

테스트 파일 상단 import에 `unittest.mock`을 추가한다:

```python
import unittest
import unittest.mock
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: FAIL with `AttributeError: module 'notion_sync' has no attribute 'load_token'`

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/notion-sync.py` 상단 import에 추가:

```python
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
```

파일 끝에 추가:

```python
# --------------------------------------------------------------------------
# 네트워크 경계
# --------------------------------------------------------------------------

NOTION_VERSION = "2026-03-11"
API_ROOT = "https://api.notion.com/v1"
DBA_PAGE_ID = "3aefb969b8be801280b8dc2ff35fbefb"


class AuthError(Exception):
    """토큰을 안전하게 얻을 수 없다."""


class ApiError(Exception):
    """Notion API 호출 실패."""


def load_token(root=ROOT):
    """NOTION_API_KEY. 환경변수 우선, 없으면 볼트 루트의 .env.

    토큰 값은 어떤 출력에도 찍지 않는다.
    """
    from_env = os.environ.get("NOTION_API_KEY")
    if from_env:
        return from_env

    path = root / ".env"
    if not path.exists():
        raise AuthError(
            "NOTION_API_KEY가 없다. 환경변수로 주거나 볼트 루트에 .env를 만든다:\n"
            "  printf 'NOTION_API_KEY=<토큰>\\n' > .env && chmod 600 .env")

    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", ".env"],
        capture_output=True)
    if tracked.returncode == 0:
        raise AuthError(
            "중단: .env가 git에 추적되고 있다. 토큰이 커밋될 수 있다.\n"
            "  git rm --cached .env  후 재실행")

    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        raise AuthError(f"중단: .env 퍼미션이 {oct(mode)}이다.\n  chmod 600 .env  후 재실행")

    for line in path.read_text(encoding="utf-8").split("\n"):
        key, _, value = line.partition("=")
        if key.strip() == "NOTION_API_KEY":
            return value.strip().strip('"').strip("'")
    raise AuthError(".env에 NOTION_API_KEY가 없다")


def api(method, path, token, body=None, retries=3, sleep=time.sleep):
    """Notion API 호출. 429/5xx는 지수 백오프로 재시도, 4xx는 즉시 실패."""
    data = None
    if body is not None:
        # ensure_ascii=False — 원시 UTF-8을 그대로 보낸다 (CLAUDE.md §6.4 ①)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(API_ROOT + path, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Notion-Version", NOTION_VERSION)
    request.add_header("Content-Type", "application/json")

    delay = 1
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            retryable = e.code == 429 or e.code >= 500
            if not retryable or attempt == retries - 1:
                detail = ""
                if e.fp is not None:
                    detail = e.read().decode("utf-8", "replace")[:300]
                raise ApiError(f"{method} {path} -> HTTP {e.code} {detail}") from None
            sleep(delay)
            delay *= 2
    raise ApiError(f"{method} {path} -> 재시도 {retries}회 소진")
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add scripts/notion-sync.py scripts/test_notion_sync.py
git commit -m "feat(notion-sync): 토큰 로드 가드와 API 호출 재시도

.env가 git에 추적 중이거나 퍼미션이 600이 아니면 실행을 거부한다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: HOLD 검사 — Notion 전용 절 감지

**Files:**
- Modify: `scripts/notion-sync.py`
- Test: `scripts/test_notion_sync.py`

**Interfaces:**
- Consumes: `SCRIPTS` (Task 1), `api()` (Task 3)
- Produces:
  - `convert_mod` — `notion-convert.py` 모듈 객체
  - `stamp_mod` — `notion-stamp.py` 모듈 객체
  - `section_titles(md: str) -> list[str]` — `^##+` 제목. 코드블록 안은 세지 않는다
  - `notion_only_sections(remote_md: str, local_md: str) -> list[str]`
  - `convert_page(slug: str) -> tuple[dict, str]` — `(frontmatter, Notion 마크다운)`. 매 호출 전 `PAGE_IDS`를 갱신한다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
class TestSectionTitles(unittest.TestCase):
    def test_extracts_h2_and_deeper(self):
        md = "# 제목\n본문\n## 첫 절\n내용\n### 하위\n## 둘째 절\n"
        self.assertEqual(ns.section_titles(md), ["첫 절", "하위", "둘째 절"])

    def test_ignores_headings_inside_code_blocks(self):
        # SQL에서 #은 MySQL 주석이다. 코드블록 안을 세면 없는 절이 잡힌다.
        md = "## 진짜 절\n```sql\n## 이건 주석\nSELECT 1;\n```\n## 또 진짜\n"
        self.assertEqual(ns.section_titles(md), ["진짜 절", "또 진짜"])


class TestNotionOnlySections(unittest.TestCase):
    def test_identical_returns_empty(self):
        md = "## A\n내용\n## B\n내용\n"
        self.assertEqual(ns.notion_only_sections(md, md), [])

    def test_detects_section_only_in_notion(self):
        remote = "## A\n## 사내 에스컬레이션 경로\n## B\n"
        local = "## A\n## B\n"
        self.assertEqual(ns.notion_only_sections(remote, local),
                         ["사내 에스컬레이션 경로"])

    def test_section_removed_from_notion_is_not_a_hold(self):
        # wiki에만 있는 절은 새로 추가되는 것이므로 HOLD 사유가 아니다
        remote = "## A\n"
        local = "## A\n## 새 절\n"
        self.assertEqual(ns.notion_only_sections(remote, local), [])


class TestConvertPage(unittest.TestCase):
    def test_returns_frontmatter_and_markdown(self):
        fm, md = ns.convert_page("aurora-dsql")
        self.assertEqual(fm["category"], "db운영")
        self.assertIn("<callout", md)      # Takeaway가 callout으로 변환됨
        self.assertNotIn("[[", md)          # wikilink가 전부 처리됨
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: FAIL with `AttributeError: module 'notion_sync' has no attribute 'section_titles'`

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/notion-sync.py` 상단 import에 추가:

```python
import importlib.util
```

파일 끝에 추가:

```python
# --------------------------------------------------------------------------
# 변환기·스탬프 재사용 (하이픈 파일명이라 importlib로 로드한다)
# --------------------------------------------------------------------------

def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


convert_mod = _load_module("notion_convert", "notion-convert.py")
stamp_mod = _load_module("notion_stamp", "notion-stamp.py")


def convert_page(slug):
    """(frontmatter, Notion 마크다운).

    notion-convert.py는 import 시점에 PAGE_IDS를 한 번 읽는다. 한 실행에서 여러
    페이지를 새로 만들면 뒤 페이지가 앞 페이지를 mention으로 걸 수 없으므로
    매 변환 직전에 갱신한다.
    """
    convert_mod.PAGE_IDS.update(convert_mod.load_page_ids())
    return convert_mod.convert(WIKI / f"{slug}.md")


# --------------------------------------------------------------------------
# HOLD 검사 (§6.2 대체)
# --------------------------------------------------------------------------

def section_titles(md):
    """^##+ 절 제목. 코드블록 안은 세지 않는다 — SQL의 #은 MySQL 주석이다."""
    masked, _ = convert_mod.mask_code(md)
    return [m.group(1).strip() for m in re.finditer(r"^#{2,}\s+(.*)$", masked, re.M)]


def notion_only_sections(remote_md, local_md):
    """Notion에만 있고 위키에는 없는 절 제목.

    비어 있지 않으면 업로드하지 않는다. wiki로 옮겨 적고 재실행하거나
    --force-replace로 폐기하는 것은 사람이 정한다.
    """
    local = set(section_titles(local_md))
    return [t for t in section_titles(remote_md) if t not in local]
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add scripts/notion-sync.py scripts/test_notion_sync.py
git commit -m "feat(notion-sync): Notion 전용 절 감지로 데이터 손실 차단

replace_content는 페이지를 통째로 덮으므로, 위키에 없는 절이 Notion에
있으면 업로드하지 않고 보고한다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 업로드 · 스탬프 · 로그

**Files:**
- Modify: `scripts/notion-sync.py`
- Test: `scripts/test_notion_sync.py`

**Interfaces:**
- Consumes: `api()` (Task 3), `stamp_mod` (Task 4)
- Produces:
  - `title_property(title: str) -> dict`
  - `create_page(token, parent_id, title, md) -> str` — 새 page_id
  - `replace_page(token, page_id, md) -> None`
  - `fetch_markdown(token, page_id) -> str`
  - `now_iso() -> str` — `2026-08-16T17:40:00+09:00` 형태
  - `write_log(created, updated, skipped, held) -> None` — `wiki/log.md` 맨 위에 한 줄

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
class TestTitleProperty(unittest.TestCase):
    def test_rich_text_shape(self):
        self.assertEqual(
            ns.title_property("제목"),
            {"title": {"title": [{"type": "text", "text": {"content": "제목"}}]}})


class TestUploadCalls(unittest.TestCase):
    def test_create_page_posts_markdown_field(self):
        seen = {}

        def fake_api(method, path, token, body=None, **kw):
            seen.update(method=method, path=path, body=body)
            return {"id": "new-page-id"}

        with unittest.mock.patch.object(ns, "api", fake_api):
            page_id = ns.create_page("tok", "parent-id", "제목", "## 본문\n")
        self.assertEqual(page_id, "new-page-id")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["path"], "/pages")
        self.assertEqual(seen["body"]["parent"], {"page_id": "parent-id"})
        self.assertEqual(seen["body"]["markdown"], "## 본문\n")
        self.assertNotIn("children", seen["body"])  # markdown과 상호 배타

    def test_replace_page_uses_replace_content(self):
        seen = {}

        def fake_api(method, path, token, body=None, **kw):
            seen.update(method=method, path=path, body=body)
            return {}

        with unittest.mock.patch.object(ns, "api", fake_api):
            ns.replace_page("tok", "abc", "## 새 본문\n")
        self.assertEqual(seen["method"], "PATCH")
        self.assertEqual(seen["path"], "/pages/abc/markdown")
        self.assertEqual(seen["body"]["type"], "replace_content")
        self.assertEqual(seen["body"]["replace_content"]["new_str"], "## 새 본문\n")


class TestNowIso(unittest.TestCase):
    def test_offset_has_colon(self):
        # log.md는 +09:00 형태를 쓴다
        value = ns.now_iso()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


class TestWriteLog(unittest.TestCase):
    def test_inserts_line_at_top_of_entries(self):
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as d:
            log = pathlib.Path(d) / "log.md"
            log.write_text(
                "---\ntitle: Wiki Log\n---\n\n# Wiki Log\n\n- [2026-08-15T10:00:00+09:00] LINT issues=0\n",
                encoding="utf-8")
            ns.write_log(created=2, updated=3, skipped=30, held=1, log_path=log)
            lines = [l for l in log.read_text(encoding="utf-8").split("\n") if l.startswith("- [")]
            self.assertIn("SYNC_NOTION", lines[0])
            self.assertIn("pages=5", lines[0])       # created + updated
            self.assertIn("created=2", lines[0])
            self.assertIn("skipped=30", lines[0])
            self.assertIn("held=1", lines[0])
            self.assertIn("LINT", lines[1])          # 기존 항목이 아래로 밀림
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: FAIL with `AttributeError: module 'notion_sync' has no attribute 'title_property'`

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/notion-sync.py` 상단 import에 추가:

```python
import datetime
```

파일 끝에 추가:

```python
# --------------------------------------------------------------------------
# 업로드
# --------------------------------------------------------------------------

def title_property(title):
    """페이지 제목 property. 위키 frontmatter의 title을 그대로 쓴다.

    아이콘은 설정하지 않는다 — 위키 스키마에 대응 필드가 없다 (설계 §6.6).
    """
    return {"title": {"title": [{"type": "text", "text": {"content": title}}]}}


def create_page(token, parent_id, title, md):
    """신규 페이지 생성. 새 page_id를 반환한다."""
    result = api("POST", "/pages", token, {
        "parent": {"page_id": parent_id},
        "properties": title_property(title),
        "markdown": md,
    })
    return result["id"]


def replace_page(token, page_id, md):
    """기존 페이지 본문 전체 교체. wiki가 진실이다."""
    api("PATCH", f"/pages/{page_id}/markdown", token, {
        "type": "replace_content",
        "replace_content": {"new_str": md},
    })


def fetch_markdown(token, page_id):
    """현재 Notion 본문을 마크다운으로 받는다. HOLD 검사용.

    응답 필드명이 공식 문서에 명시돼 있지 않다. 'markdown'과 'content' 둘 다
    받아보고, 어느 쪽도 없으면 응답 키를 그대로 드러내 실패시킨다 —
    조용히 빈 문자열을 반환하면 HOLD 검사가 항상 통과해 검사 자체가 무력해진다.
    """
    result = api("GET", f"/pages/{page_id}/markdown", token)
    for field in ("markdown", "content"):
        if field in result:
            return result[field]
    raise ApiError(
        f"GET /pages/{page_id}/markdown 응답에 본문 필드가 없다. 키: {sorted(result)}")


# --------------------------------------------------------------------------
# 로그 (§7)
# --------------------------------------------------------------------------

def now_iso():
    """2026-08-16T17:40:00+09:00 — log.md 형식."""
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    return stamp[:-2] + ":" + stamp[-2:]


def write_log(created, updated, skipped, held, log_path=None):
    """wiki/log.md 맨 위에 SYNC_NOTION 한 줄을 넣는다. 최신이 위."""
    path = log_path or (WIKI / "log.md")
    text = path.read_text(encoding="utf-8")
    line = (f"- [{now_iso()}] SYNC_NOTION pages={created + updated} "
            f"created={created} updated={updated} skipped={skipped} held={held} "
            f'target="DBA"')
    marker = "# Wiki Log\n"
    index = text.index(marker) + len(marker)
    path.write_text(text[:index] + "\n" + line + "\n" + text[index:].lstrip("\n"),
                    encoding="utf-8")
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add scripts/notion-sync.py scripts/test_notion_sync.py
git commit -m "feat(notion-sync): 페이지 생성·교체·조회와 log.md 기록

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 컨테이너 트리 — `--init-tree` / `--refresh-tree`

**Files:**
- Modify: `scripts/notion-sync.py`
- Test: `scripts/test_notion_sync.py`

**Interfaces:**
- Consumes: `api()`, `create_page()`, `CONTAINER_NAMES`, `DBA_PAGE_ID`
- Produces:
  - `TREE_FILE: pathlib.Path` = `SCRIPTS / "notion-tree.json"`
  - `TREE_SPEC: list[tuple[str, str]]` — `(컨테이너, 부모)`. 부모가 먼저 오도록 정렬돼 있다
  - `load_tree() -> dict[str, str]`
  - `save_tree(tree: dict) -> None`
  - `init_tree(token, dry_run=False) -> dict[str, str]` — 없는 컨테이너만 만든다
  - `refresh_tree(token) -> dict[str, str]` — 자식 페이지를 훑어 이름→id 재구성

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
class TestTreeSpec(unittest.TestCase):
    def test_covers_all_container_names(self):
        named = {name for name, _ in ns.TREE_SPEC}
        self.assertEqual(named, set(ns.CONTAINER_NAMES))

    def test_parent_appears_before_child(self):
        seen = {"DBA"}
        for name, parent in ns.TREE_SPEC:
            self.assertIn(parent, seen, f"{name}의 부모 {parent}가 아직 만들어지지 않았다")
            seen.add(name)

    def test_has_16_containers(self):
        self.assertEqual(len(ns.TREE_SPEC), 16)


class TestInitTree(unittest.TestCase):
    def test_creates_only_missing_containers(self):
        created = []

        def fake_create(token, parent_id, title, md):
            created.append((title, parent_id))
            return f"id-{title}"

        existing = {"DBA": ns.DBA_PAGE_ID, "db운영": "id-db운영"}
        with unittest.mock.patch.object(ns, "create_page", fake_create):
            with unittest.mock.patch.object(ns, "load_tree", lambda: dict(existing)):
                with unittest.mock.patch.object(ns, "save_tree", lambda t: None):
                    tree = ns.init_tree("tok")

        names = [title for title, _ in created]
        self.assertNotIn("db운영", names)          # 이미 있으므로 만들지 않는다
        self.assertIn("MySQL", names)
        self.assertEqual(len(created), 15)          # 16 - 이미 있는 db운영
        self.assertEqual(tree["MySQL"], "id-MySQL")
        # 자식은 방금 만든 부모의 id 아래로 간다
        self.assertIn(("엔진 비교", "id-엔진 공통"), created)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: FAIL with `AttributeError: module 'notion_sync' has no attribute 'TREE_SPEC'`

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/notion-sync.py` 끝에 추가:

```python
# --------------------------------------------------------------------------
# 컨테이너 트리 (§6.1)
# --------------------------------------------------------------------------

TREE_FILE = SCRIPTS / "notion-tree.json"

# (컨테이너, 부모). 부모가 먼저 오도록 정렬돼 있다.
TREE_SPEC = [
    ("db운영", "DBA"),
    ("MySQL", "db운영"),
    ("PostgreSQL", "db운영"),
    ("SQL Server", "db운영"),
    ("Aurora DSQL", "db운영"),
    ("엔진 공통", "db운영"),
    ("엔진 비교", "엔진 공통"),
    ("진단·운영 표준", "엔진 공통"),
    ("보안·권한", "엔진 공통"),
    ("개발·자동화", "엔진 공통"),
    ("지식 운영", "엔진 공통"),
    ("업무기록", "DBA"),
    ("kakaogames", "업무기록"),
    ("개인", "DBA"),
    ("참고자료", "DBA"),
    ("종합원칙", "DBA"),
]


def load_tree():
    if not TREE_FILE.exists():
        return {"DBA": DBA_PAGE_ID}
    tree = json.loads(TREE_FILE.read_text(encoding="utf-8"))
    tree.setdefault("DBA", DBA_PAGE_ID)
    return tree


def save_tree(tree):
    TREE_FILE.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def init_tree(token):
    """없는 컨테이너만 만든다. 이미 있는 것은 건드리지 않는다."""
    tree = load_tree()
    for name, parent in TREE_SPEC:
        if name in tree:
            continue
        parent_id = tree[parent]
        tree[name] = create_page(token, parent_id, name, "")
        print(f"[create-container] {name} -> {parent}")
        save_tree(tree)          # 중간 실패해도 진행분이 남도록 매번 쓴다
    save_tree(tree)
    return tree


def refresh_tree(token):
    """DBA 아래 자식 페이지를 훑어 이름 -> id를 재구성한다."""
    tree = {"DBA": DBA_PAGE_ID}
    known = {name for name, _ in TREE_SPEC}

    def walk(page_id):
        cursor = None
        while True:
            path = f"/blocks/{page_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={cursor}"
            result = api("GET", path, token)
            for block in result.get("results", []):
                if block.get("type") != "child_page":
                    continue
                title = block["child_page"]["title"]
                if title in known:
                    tree[title] = block["id"]
                    walk(block["id"])
            if not result.get("has_more"):
                return
            cursor = result.get("next_cursor")

    walk(DBA_PAGE_ID)
    save_tree(tree)
    return tree
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add scripts/notion-sync.py scripts/test_notion_sync.py
git commit -m "feat(notion-sync): 컨테이너 트리 생성과 재탐색

컨테이너 16개 중 페이지를 받는 부모는 13개다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: CLI 조립 — 계획 출력 · dry-run · `--reset-stamps`

**Files:**
- Modify: `scripts/notion-sync.py`
- Test: `scripts/test_notion_sync.py`

**Interfaces:**
- Consumes: Task 1~6 전부
- Produces:
  - `reset_stamps() -> int` — 되돌린 페이지 수
  - `build_plan(only=None) -> list[dict]` — 각 항목 `{"slug","action","parent","page_id","reason"}`. `action`은 `create`/`update`/`skip`/`hold`
  - `run(args) -> int` — 종료 코드
  - `main(argv=None) -> int`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
class TestResetStamps(unittest.TestCase):
    def test_nulls_both_fields(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            wiki = pathlib.Path(d)
            (wiki / "a.md").write_text(
                '---\ncategory: db운영\nnotion_page_id: "abc"\n'
                'notion_synced: "2026-08-15T22:55:00+0900"\n---\n\n본문\n',
                encoding="utf-8")
            count = ns.reset_stamps(wiki_dir=wiki)
            text = (wiki / "a.md").read_text(encoding="utf-8")
        self.assertEqual(count, 1)
        self.assertIn("notion_page_id: null", text)
        self.assertIn("notion_synced: null", text)


class TestBuildPlan(unittest.TestCase):
    def test_skips_up_to_date_pages(self):
        plan = ns.build_plan()
        actions = {item["slug"]: item["action"] for item in plan}
        self.assertEqual(len(plan), 35)
        self.assertIn(actions["aurora-dsql"], ("create", "update", "skip"))

    def test_only_filters_to_named_slugs(self):
        plan = ns.build_plan(only=["aurora-dsql"])
        self.assertEqual([item["slug"] for item in plan], ["aurora-dsql"])

    def test_plan_items_carry_parent(self):
        plan = ns.build_plan(only=["aurora-dsql"])
        self.assertEqual(plan[0]["parent"], "Aurora DSQL")


class TestDryRunMakesNoHttpCalls(unittest.TestCase):
    def test_dry_run_does_not_touch_network(self):
        def explode(*a, **kw):
            raise AssertionError("dry-run에서 HTTP를 호출했다")

        with unittest.mock.patch.object(ns.urllib.request, "urlopen", explode):
            with unittest.mock.patch.object(ns, "load_token", lambda root=None: "tok"):
                code = ns.main(["--dry-run"])
        self.assertEqual(code, 0)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: FAIL with `AttributeError: module 'notion_sync' has no attribute 'reset_stamps'`

- [ ] **Step 3: 최소 구현을 쓴다**

`scripts/notion-sync.py` 상단 import에 추가:

```python
import argparse
import sys
```

파일 끝에 추가:

```python
# --------------------------------------------------------------------------
# 1회성 초기화
# --------------------------------------------------------------------------

def reset_stamps(wiki_dir=None):
    """notion_page_id·notion_synced를 null로 되돌린다.

    Notion에서 페이지를 삭제한 뒤 반드시 먼저 실행한다. 휴지통의 페이지는
    여전히 유효한 id로 조회되므로, 리셋하지 않으면 휴지통 페이지를 되살린다.
    """
    directory = wiki_dir or WIKI
    count = 0
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            continue
        fm = m.group(1)
        new_fm = re.sub(r"^notion_page_id:.*$", "notion_page_id: null", fm, flags=re.M)
        new_fm = re.sub(r"^notion_synced:.*$", "notion_synced: null", new_fm, flags=re.M)
        if new_fm == fm:
            continue
        path.write_text(f"---\n{new_fm}\n---\n" + text[m.end():], encoding="utf-8")
        count += 1
    return count


# --------------------------------------------------------------------------
# 계획
# --------------------------------------------------------------------------

def build_plan(only=None):
    """무엇을 어떻게 할지 먼저 전부 정한다. HTTP 호출은 하지 않는다."""
    sections = index_sections()
    pages = knowledge_pages()
    slugs = sorted(only) if only else sorted(pages)

    plan = []
    for slug in slugs:
        fm = pages.get(slug)
        if fm is None:
            plan.append({"slug": slug, "action": "hold", "parent": None,
                         "page_id": None, "reason": "wiki에 없는 페이지"})
            continue

        page_id = fm.get("notion_page_id", "null")
        page_id = None if page_id in ("null", "") else page_id

        if only is None and not is_target(fm):
            plan.append({"slug": slug, "action": "skip", "parent": None,
                         "page_id": page_id, "reason": "updated <= notion_synced"})
            continue

        try:
            parent = placement(slug, fm, sections)
        except HoldError as e:
            plan.append({"slug": slug, "action": "hold", "parent": None,
                         "page_id": page_id, "reason": str(e)})
            continue

        plan.append({
            "slug": slug,
            "action": "update" if page_id else "create",
            "parent": parent,
            "page_id": page_id,
            "reason": "",
        })
    return plan


def print_plan(plan):
    counts = {"create": 0, "update": 0, "skip": 0, "hold": 0}
    for item in plan:
        counts[item["action"]] += 1
    for item in plan:
        if item["action"] == "skip":
            continue
        if item["action"] == "hold":
            print(f"[HOLD]   {item['slug']}\n         └─ {item['reason']}")
        else:
            print(f"[{item['action']}] {item['slug']} -> {item['parent']}")
    print(f"\n계획: create={counts['create']} update={counts['update']} "
          f"skip={counts['skip']} hold={counts['hold']}")
    return counts


# --------------------------------------------------------------------------
# 실행
# --------------------------------------------------------------------------

def run(args):
    if args.reset_stamps:
        count = reset_stamps()
        print(f"notion_page_id·notion_synced를 null로 되돌렸다: {count}개")
        return 0

    plan = build_plan(only=args.only)
    print_plan(plan)

    if args.dry_run:
        print("\n--dry-run: HTTP 호출 없음")
        return 0

    try:
        token = load_token()
    except AuthError as e:
        print(f"\n{e}", file=sys.stderr)
        return 2

    if args.init_tree:
        init_tree(token)
        print("컨테이너 트리 준비 완료")
        return 0
    if args.refresh_tree:
        refresh_tree(token)
        print("컨테이너 트리 재탐색 완료")
        return 0

    tree = load_tree()
    forced = set(args.force_replace or [])
    created = updated = held = 0
    skipped = sum(1 for item in plan if item["action"] == "skip")
    held += sum(1 for item in plan if item["action"] == "hold")

    for item in plan:
        if item["action"] in ("skip", "hold"):
            continue
        slug = item["slug"]
        try:
            fm, md = convert_page(slug)

            if item["action"] == "update" and slug not in forced:
                remote = fetch_markdown(token, item["page_id"])
                extra = notion_only_sections(remote, md)
                if extra:
                    print(f"[HOLD]   {slug}\n         └─ Notion 전용 절 {len(extra)}개: "
                          + ", ".join(extra))
                    held += 1
                    continue

            parent_id = tree.get(item["parent"])
            if parent_id is None:
                print(f"[HOLD]   {slug}\n         └─ 컨테이너 '{item['parent']}' 없음. "
                      "--init-tree 먼저 실행")
                held += 1
                continue

            if item["action"] == "create":
                page_id = create_page(token, parent_id, fm["title"], md)
                created += 1
            else:
                page_id = item["page_id"]
                replace_page(token, page_id, md)
                updated += 1

            # 성공 즉시 페이지 단위로 기록한다. 마지막에 몰아 쓰면 중간 실패 시
            # 어디까지 올렸는지 알 수 없어 다음 실행이 전량 재업로드가 된다 (§6.3).
            stamp_mod.stamp(slug, page_id, now_iso())
            print(f"[ok]     {slug} -> {page_id}")

        except (ApiError, KeyError) as e:
            print(f"[FAIL]   {slug}: {e}", file=sys.stderr)

    write_log(created=created, updated=updated, skipped=skipped, held=held)
    print(f"\n완료: created={created} updated={updated} skipped={skipped} held={held}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="wiki/ -> Notion 단방향 동기화")
    parser.add_argument("--dry-run", action="store_true", help="계획만 출력, HTTP 호출 0")
    parser.add_argument("--only", nargs="+", metavar="SLUG",
                        help="지정 페이지만 (강제 재업로드는 사용자가 페이지를 명시한다)")
    parser.add_argument("--force-replace", nargs="+", metavar="SLUG",
                        help="HOLD를 무시하고 덮어쓴다")
    parser.add_argument("--init-tree", action="store_true", help="컨테이너 생성 (1회성)")
    parser.add_argument("--refresh-tree", action="store_true", help="컨테이너 id 재탐색")
    parser.add_argument("--reset-stamps", action="store_true",
                        help="notion_page_id·notion_synced를 null로 (1회성)")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
Expected: PASS

- [ ] **Step 5: dry-run을 실제로 돌려 눈으로 확인한다**

Run: `python3 scripts/notion-sync.py --dry-run`
Expected: 35개 항목이 출력되고 `HTTP 호출 없음`으로 끝난다. `hold=0`이어야 한다 — HOLD가 있으면 배치 규칙에 구멍이 있는 것이므로 Task 2로 돌아간다.

- [ ] **Step 6: 커밋한다**

```bash
git add scripts/notion-sync.py scripts/test_notion_sync.py
git commit -m "feat(notion-sync): CLI 조립과 계획 출력

전 페이지를 대상으로 만드는 플래그는 두지 않는다 — 전체 재업로드 금지를
코드로 강제한다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `CLAUDE.md` §6 개정

**Files:**
- Modify: `CLAUDE.md:278-465` (§6 Notion 동기화 전체. §7은 467행에서 시작한다)

**Interfaces:**
- Consumes: Task 1~7의 CLI 인터페이스
- Produces: 없음 (문서)

- [ ] **Step 1: 현재 §6을 읽는다**

Run: `sed -n '278,465p' CLAUDE.md`
목적: 개정 전 원문을 확인한다. 특히 §6.4의 4개 비용 규칙과 §6.1의 `기술 문서` 문장 위치.

- [ ] **Step 2: 절별로 고친다**

| 절 | 조치 |
|---|---|
| §6 서두 | 절차를 `python3 scripts/notion-sync.py` 한 줄로 대체 |
| §6 제약 | **"Notion MCP가 연결된 Claude 세션에서만 가능" 삭제.** 토큰이 있으면 어느 에이전트에서도 된다 |
| §6.1 | 유지. **태그 분기 규칙을 명문화**하고 `aurora`가 라우팅 키가 아닌 이유를 적는다. **`기술 문서` 문장 삭제**(대상이 삭제됐다) |
| §6.2 | 병합 규칙을 HOLD 방식으로 교체. "Notion 전용 절은 남긴다" → "감지하면 업로드하지 않고 보고한다" |
| §6.3 | 유지. 판정식이 코드로 옮겨졌을 뿐 규칙은 동일 |
| §6.4 | 4개 비용 규칙은 에이전트가 본문을 출력하지 않으므로 무효. **삭제하지 않고 "왜 스크립트로 갔는가"의 근거로 축약 보존.** "부모는 12개뿐"을 **13개**로 정정 |

- [ ] **Step 3: 스크립트 표를 갱신한다**

§6.4의 보조 스크립트 표에 항목을 추가한다:

```markdown
| `scripts/notion-sync.py` | **동기화 진입점.** 증분 판정·배치·HOLD·업로드·스탬프·로그를 전부 수행한다. `--dry-run`으로 먼저 계획을 본다 |
```

- [ ] **Step 4: 개정 결과를 검증한다**

Run: `rg -n "MCP가 연결된|기술 문서|부모는 12개" CLAUDE.md`
Expected: 세 문자열 모두 0건

Run: `rg -n "notion-sync.py" CLAUDE.md`
Expected: 최소 2건 (절차, 스크립트 표)

- [ ] **Step 5: 커밋한다**

```bash
git add CLAUDE.md
git commit -m "docs: §6 Notion 동기화를 스크립트 방식으로 개정

MCP 세션 제약을 삭제하고 병합 규칙을 HOLD 방식으로 교체한다.
§6.4의 '부모는 12개'는 실제 13개로 정정.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## 전환 실행 절차 (코드 완성 후 · 사용자 개입 필요)

구현 태스크가 아니다. Task 1~8이 끝난 뒤 사람이 순서대로 수행한다.

- [ ] **0. 토큰 준비 (사용자)**

Notion integration을 만들고 **DBA 페이지에 연결**한 뒤:

```bash
printf 'NOTION_API_KEY=<토큰>\n' > .env && chmod 600 .env
```

`.env`는 이미 `.gitignore`에 있다. 스크립트가 추적 여부와 퍼미션을 실행 전에 확인한다.

- [ ] **1. 스탬프 리셋**

```bash
python3 scripts/notion-sync.py --reset-stamps
```
Expected: `32개`. **이 단계를 건너뛰면 휴지통의 페이지를 되살린다.**

- [ ] **2. 컨테이너 생성**

```bash
python3 scripts/notion-sync.py --init-tree
```
Expected: 16개 생성, `scripts/notion-tree.json` 기록. Notion에서 트리 모양을 눈으로 확인한다.

- [ ] **3. 카나리 1건**

```bash
python3 scripts/notion-sync.py --only aurora-dsql
```
Expected: `[ok] aurora-dsql -> <id>`. Notion에서 **callout·표·코드블록·제목**이 제대로 렌더링되는지 확인한다.
여기서 문제가 나오면 34개를 올리기 전에 잡는다 — 올린 뒤 발견하면 34개를 다시 손봐야 한다.

**`properties.title` 형식 실패 시**: `HTTP 400`이 나면 `title_property()`를 순수 rich-text
배열(`{"title": [{"text": {"content": title}}]}`) 형태로 바꿔 재시도한다. 공식 문서가 두 형태
중 어느 쪽인지 명시하지 않아 카나리에서 확정한다.

- [ ] **4. 나머지 전량**

```bash
python3 scripts/notion-sync.py
```
성공 신호는 **`hold=0`이고 `create`가 카나리를 뺀 나머지 전부**라는 것이다. 고정 숫자로 적지
않는다 — 1단계에서 `notion_synced`를 `null`로 만든 페이지는 날짜와 무관하게 전부 대상이 되지만,
**카나리가 `update`로 잡힐지 `skip`으로 잡힐지는 실행 날짜에 달렸다.**

- 카나리의 `updated`와 **같은 날** 재구축하면 → §6.3의 `>=` 규칙으로 다시 대상이 되어 `update=1`
- **하루라도 지난 뒤** 재구축하면 → `updated < notion_synced`라 `skip=1`

둘 다 정상이다. `hold`가 0이 아니거나 `create`가 예상보다 적으면 그때 원인을 본다.

**`fetch_markdown()`과 HOLD 검사가 처음 실제로 도는 지점은 카나리가 `update`로 잡히는 경우다.**
1~3단계는 전부 `create`라 `GET /markdown`을 부르지 않는다. 응답 본문 필드명을 문서가 명시하지
않아 `markdown`·`content` 순으로 시도하도록 짰으니, `본문 필드가 없다` 에러가 나면 출력된 키
목록을 보고 `fetch_markdown()`을 고친다. 이건 문제가 아니라 API 불확실성이 전량이 아니라
**카나리 1건에서 먼저** 드러나는 바람직한 결과다.

> 카나리가 `skip`으로 잡히는 날짜에 재구축한다면 이 조기 노출이 일어나지 않고, `fetch_markdown()`은
> 5단계 2차 패스에서 전 페이지에 대해 한꺼번에 처음 실행된다. 그게 싫으면 4단계 전에
> `--only <카나리>`를 한 번 더 돌려 `update` 경로를 의도적으로 태운다.

- [ ] **5. 교차참조 2차 패스**

1~4단계 중에는 아직 `notion_page_id`가 없는 페이지가 백틱으로 남는다. 전부 생성된 뒤
한 번 더 올려야 mention 링크로 바뀐다. `updated`가 그대로면 §6.3이 건너뛰므로 `--only`로 명시한다.

```bash
python3 scripts/notion-sync.py --only $(ls wiki/*.md | xargs -n1 basename | sed 's/\.md$//' | grep -vE '^(index|log)$' | tr '\n' ' ')
```

- [ ] **6. 검증**

```bash
python3 scripts/notion-sync.py --dry-run
```
6단계의 성공 신호는 **`create=0`과 `hold=0`**이다. `update`는 0이 아닐 수 있다 —
**재구축을 수행한 날짜와 `updated`가 같은 페이지는 §6.3의 `>=` 규칙에 의해 다시 대상이 된다.**
며칠 뒤에 재구축하면 전부 `skip`이 되고, 당일에 하면 그날 수정한 페이지 수만큼 `update`로
잡힌다. 둘 다 정상이다. `create`가 0이 아니면 스탬프가 기록되지 않은 것이고, `hold`가 0이
아니면 절 제목이 어긋난 것이다.

Notion에서 임의의 페이지 2~3개를 열어 mention 링크가 클릭 가능한지 확인한다.

- [ ] **7. 커밋**

```bash
git add wiki/ scripts/notion-tree.json
git commit -m "chore: Notion 재구축 — 컨테이너 16개, 페이지 35개

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## 남는 것

- **휴지통 정리**: 삭제된 32개가 Notion 휴지통에 남아 검색에 나타난다. 영구 삭제는 사용자 판단이며 스크립트는 관여하지 않는다.
- **대용량 페이지**: `allow_async: true`가 필요한 임계가 문서에 없다. 최대 페이지(`operational-queries` 23.2 KB)가 카나리 이후 정상 통과하면 추가하지 않는다.
- **`.env` 평문 보관**: 볼트 안에 평문 토큰이 생긴다. 스크립트가 git 추적·퍼미션을 막지만 Obsidian 동기화·백업 경로로 새어나갈 여지는 남는다. 사용자가 방식을 택했고, macOS Keychain으로 옮기려면 `load_token()`만 고치면 된다.
