#!/usr/bin/env python3
"""notion-sync.py 단위 테스트. HTTP 호출은 하지 않는다.

실행: python3 -m unittest discover -s scripts -p 'test_*.py' -v
"""
import importlib.util
import pathlib
import unittest
import unittest.mock

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

    def test_rejects_env_tracked_by_git(self):
        import subprocess
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self._write_env("NOTION_API_KEY=x\n")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", ".env"], check=True)
        with self.assertRaises(ns.AuthError) as cm:
            ns.load_token(self.root)
        self.assertIn("추적", str(cm.exception))


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


class TestFetchMarkdown(unittest.TestCase):
    def test_returns_markdown_field(self):
        with unittest.mock.patch.object(
                ns, "api", lambda *a, **kw: {"markdown": "## 절\n본문\n"}):
            self.assertEqual(ns.fetch_markdown("tok", "abc"), "## 절\n본문\n")

    def test_falls_back_to_content_field(self):
        with unittest.mock.patch.object(
                ns, "api", lambda *a, **kw: {"content": "## 절\n"}):
            self.assertEqual(ns.fetch_markdown("tok", "abc"), "## 절\n")

    def test_raises_when_no_body_field(self):
        with unittest.mock.patch.object(
                ns, "api", lambda *a, **kw: {"object": "page", "id": "abc"}):
            with self.assertRaises(ns.ApiError) as cm:
                ns.fetch_markdown("tok", "abc")
        # 실패 메시지가 실제 응답 키를 드러내야 다음 사람이 필드명을 고칠 수 있다
        self.assertIn("id", str(cm.exception))
        self.assertIn("object", str(cm.exception))


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


if __name__ == "__main__":
    unittest.main()
