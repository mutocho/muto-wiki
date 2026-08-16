#!/usr/bin/env python3
"""notion-sync.py 단위 테스트. HTTP 호출은 하지 않는다.

실행: python3 -m unittest discover -s scripts -p 'test_*.py' -v
"""
import argparse
import contextlib
import importlib.util
import io
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

    def test_create_page_omits_markdown_field_when_body_is_empty(self):
        # init_tree가 컨테이너를 만들 때 md=""를 넘긴다. 빈 문자열 필드를
        # API가 받아준다는 보장이 없으므로 필드 자체를 생략해야 한다 —
        # 생략된 optional 필드는 항상 안전하지만 빈 문자열은 그렇지 않다.
        seen = {}

        def fake_api(method, path, token, body=None, **kw):
            seen.update(body=body)
            return {"id": "container-id"}

        with unittest.mock.patch.object(ns, "api", fake_api):
            ns.create_page("tok", "parent-id", "컨테이너", "")
        self.assertNotIn("markdown", seen["body"])
        self.assertNotIn("children", seen["body"])

    def test_create_page_includes_markdown_field_when_body_is_non_empty(self):
        seen = {}

        def fake_api(method, path, token, body=None, **kw):
            seen.update(body=body)
            return {"id": "page-id"}

        with unittest.mock.patch.object(ns, "api", fake_api):
            ns.create_page("tok", "parent-id", "제목", "## 본문\n")
        self.assertIn("markdown", seen["body"])
        self.assertEqual(seen["body"]["markdown"], "## 본문\n")

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
            ns.write_log(created=2, updated=3, skipped=30, held=1, failed=4, log_path=log)
            lines = [l for l in log.read_text(encoding="utf-8").split("\n") if l.startswith("- [")]
            self.assertIn("SYNC_NOTION", lines[0])
            self.assertIn("pages=5", lines[0])       # created + updated
            self.assertIn("created=2", lines[0])
            self.assertIn("skipped=30", lines[0])
            self.assertIn("held=1", lines[0])
            self.assertIn("failed=4", lines[0])
            self.assertIn("LINT", lines[1])          # 기존 항목이 아래로 밀림

    def test_failed_defaults_to_zero(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = pathlib.Path(d) / "log.md"
            log.write_text("# Wiki Log\n\n", encoding="utf-8")
            ns.write_log(created=1, updated=0, skipped=0, held=0, log_path=log)
            text = log.read_text(encoding="utf-8")
        self.assertIn("failed=0", text)


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

    def test_raises_api_error_when_field_is_not_a_string(self):
        # Notion이 markdown을 중첩 객체로 돌려주면(예: {"markdown": {...}})
        # isinstance 가드가 없으면 그대로 반환돼 section_titles()가 비-str에
        # re.sub을 호출해 TypeError가 난다. TypeError는 run()의
        # except (ApiError, KeyError, urllib.error.URLError)에 없어 루프
        # 전체가 죽는다 — 이 응답 모양도 '필드 없음'과 같은 단일 페이지
        # ApiError로 격하돼야 한다.
        with unittest.mock.patch.object(
                ns, "api", lambda *a, **kw: {"markdown": {"nested": "object"}}):
            with self.assertRaises(ns.ApiError) as cm:
                ns.fetch_markdown("tok", "abc")
        self.assertIn("markdown", str(cm.exception))


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

    def test_saves_after_every_creation(self):
        saves = []

        def fake_create(token, parent_id, title, md):
            return f"id-{title}"

        def record_save(t):
            saves.append(dict(t))

        existing = {"DBA": ns.DBA_PAGE_ID, "db운영": "id-db운영"}
        with unittest.mock.patch.object(ns, "create_page", fake_create):
            with unittest.mock.patch.object(ns, "load_tree", lambda: dict(existing)):
                with unittest.mock.patch.object(ns, "save_tree", record_save):
                    tree = ns.init_tree("tok")

        # save_tree가 최소 15번 호출됨 (15개 컨테이너 생성)
        self.assertGreaterEqual(len(saves), 15)

        # 스냅샷이 단조 증가: N번째 스냅샷은 N개 이상의 컨테이너를 포함
        for i, snapshot in enumerate(saves):
            # i번째 save는 최소 i+2개 항목을 가져야 함 (DBA + db운영 + i개)
            self.assertGreaterEqual(len(snapshot), i + 2,
                f"save #{i}는 최소 {i + 2}개 항목을 가져야 하는데 {len(snapshot)}개만 있음")


class TestLoadTree(unittest.TestCase):
    def test_missing_file_returns_dba_only(self):
        with unittest.mock.patch.object(ns, "TREE_FILE") as mock_file:
            mock_file.exists.return_value = False
            tree = ns.load_tree()
        self.assertEqual(tree, {"DBA": ns.DBA_PAGE_ID})

    def test_file_without_dba_key_seeds_dba(self):
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "tree.json"
            path.write_text(json.dumps({"MySQL": "id-mysql"}), encoding="utf-8")
            with unittest.mock.patch.object(ns, "TREE_FILE", path):
                tree = ns.load_tree()
        self.assertEqual(tree["DBA"], ns.DBA_PAGE_ID)
        self.assertEqual(tree["MySQL"], "id-mysql")


class TestRefreshTree(unittest.TestCase):
    def test_handles_multi_page_results(self):
        pages_called = []

        def fake_api(method, path, token):
            pages_called.append(path)
            # 첫 페이지: db운영 직하 자식들, has_more=true
            if path == "/blocks/3aefb969b8be801280b8dc2ff35fbefb/children?page_size=100":
                return {
                    "results": [
                        {"type": "child_page", "id": "id-db-ops", "child_page": {"title": "db운영"}}
                    ],
                    "has_more": True,
                    "next_cursor": "cursor-1"
                }
            # 두 번째 페이지: 계속 db운영 직하 자식들
            elif path == "/blocks/3aefb969b8be801280b8dc2ff35fbefb/children?page_size=100&start_cursor=cursor-1":
                return {
                    "results": [
                        {"type": "child_page", "id": "id-mysql", "child_page": {"title": "MySQL"}}
                    ],
                    "has_more": False
                }
            # db운영 안쪽
            elif path == "/blocks/id-db-ops/children?page_size=100":
                return {"results": [], "has_more": False}
            # MySQL 안쪽
            elif path == "/blocks/id-mysql/children?page_size=100":
                return {"results": [], "has_more": False}
            return {"results": [], "has_more": False}

        saved = {}
        def fake_save(t):
            saved.update(t)

        with unittest.mock.patch.object(ns, "api", fake_api):
            with unittest.mock.patch.object(ns, "save_tree", fake_save):
                tree = ns.refresh_tree("tok")

        self.assertIn("db운영", tree)
        self.assertIn("MySQL", tree)
        self.assertEqual(tree["MySQL"], "id-mysql")
        # Assert save_tree was called with the final mapping including pagination results
        self.assertEqual(saved, tree, "save_tree should have been called with the complete tree")

    def test_ignores_non_container_pages(self):
        paths_called = []

        def fake_api(method, path, token):
            paths_called.append(path)
            # Only DBA has children; non-container and container children return empty
            if path == "/blocks/3aefb969b8be801280b8dc2ff35fbefb/children?page_size=100":
                return {
                    "results": [
                        {"type": "child_page", "id": "id-db-ops", "child_page": {"title": "db운영"}},
                        {"type": "child_page", "id": "id-other", "child_page": {"title": "Other Page"}},
                    ],
                    "has_more": False
                }
            else:
                return {"results": [], "has_more": False}

        with unittest.mock.patch.object(ns, "api", fake_api):
            with unittest.mock.patch.object(ns, "save_tree", lambda t: None):
                tree = ns.refresh_tree("tok")

        self.assertIn("db운영", tree)
        self.assertNotIn("Other Page", tree)
        # Non-container pages should not be recursed into
        self.assertNotIn("/blocks/id-other/children", "".join(paths_called),
                        "Should not have recursed into non-container page id-other")

    def test_recursive_descent(self):
        # walk() is called recursively on child containers.
        # Assert that it descends through multiple levels.
        calls = []

        def fake_api(method, path, token):
            calls.append(path)
            if path == "/blocks/3aefb969b8be801280b8dc2ff35fbefb/children?page_size=100":
                # DBA has two direct children: db운영, 업무기록
                return {
                    "results": [
                        {"type": "child_page", "id": "id-db-ops", "child_page": {"title": "db운영"}},
                        {"type": "child_page", "id": "id-worklog", "child_page": {"title": "업무기록"}},
                    ],
                    "has_more": False
                }
            elif path == "/blocks/id-db-ops/children?page_size=100":
                # db운영 has MySQL
                return {
                    "results": [
                        {"type": "child_page", "id": "id-mysql", "child_page": {"title": "MySQL"}}
                    ],
                    "has_more": False
                }
            elif path == "/blocks/id-worklog/children?page_size=100":
                # 업무기록 has kakaogames
                return {
                    "results": [
                        {"type": "child_page", "id": "id-kakaogames", "child_page": {"title": "kakaogames"}}
                    ],
                    "has_more": False
                }
            else:
                # All other paths (MySQL, kakaogames children) have no children
                return {"results": [], "has_more": False}

        with unittest.mock.patch.object(ns, "api", fake_api):
            with unittest.mock.patch.object(ns, "save_tree", lambda t: None):
                tree = ns.refresh_tree("tok")

        # Should have discovered: DBA, db운영, MySQL, 업무기록, kakaogames
        self.assertIn("db운영", tree)
        self.assertIn("MySQL", tree)
        self.assertIn("업무기록", tree)
        self.assertIn("kakaogames", tree)
        # Should have made recursive calls for each container found
        self.assertGreater(len(calls), 2, "Should have made multiple API calls due to recursion")

    def test_null_cursor_stops_pagination(self):
        def fake_api(method, path, token):
            if path == "/blocks/3aefb969b8be801280b8dc2ff35fbefb/children?page_size=100":
                # First page: has_more=true with next_cursor
                return {
                    "results": [
                        {"type": "child_page", "id": "id-db-ops", "child_page": {"title": "db운영"}}
                    ],
                    "has_more": True,
                    "next_cursor": "cursor-1"
                }
            elif path == "/blocks/3aefb969b8be801280b8dc2ff35fbefb/children?page_size=100&start_cursor=cursor-1":
                # Second page: has_more=true but cursor=null (edge case that should stop loop)
                return {
                    "results": [],
                    "has_more": True,
                    "next_cursor": None
                }
            else:
                # All other children return empty
                return {"results": [], "has_more": False}

        with unittest.mock.patch.object(ns, "api", fake_api):
            with unittest.mock.patch.object(ns, "save_tree", lambda t: None):
                # 무한 루프가 안 되고 정상 종료해야 함
                tree = ns.refresh_tree("tok")

        self.assertIn("db운영", tree)


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
    def test_plan_covers_every_knowledge_page(self):
        # 페이지 수는 wiki/에 새 페이지가 생길 때마다 바뀐다 — 개수를 고정값으로
        # 박지 않고 knowledge_pages()에서 파생해 위키가 자라도 이 테스트가
        # 무관하게 깨지지 않게 한다.
        plan = ns.build_plan()
        self.assertEqual(len(plan), len(ns.knowledge_pages()))

    def test_skips_pages_not_targeted_for_incremental_sync(self):
        # is_target()이 False인 모든 페이지는 action이 반드시 "skip"이어야
        # 한다 — 이전에는 "skip이 아닌 값이 아니다"만 확인해 실제로 skip이
        # 되는지는 검증하지 않았다.
        plan = ns.build_plan()
        pages = ns.knowledge_pages()
        plan_by_slug = {item["slug"]: item for item in plan}
        non_targets = [slug for slug, fm in pages.items() if not ns.is_target(fm)]
        self.assertGreater(len(non_targets), 0,
                            "이 wiki에는 skip 대상이 없어 이 속성을 검증할 수 없다")
        for slug in non_targets:
            self.assertEqual(plan_by_slug[slug]["action"], "skip")

    def test_only_filters_to_named_slugs(self):
        plan = ns.build_plan(only=["aurora-dsql"])
        self.assertEqual([item["slug"] for item in plan], ["aurora-dsql"])

    def test_empty_only_list_selects_nothing(self):
        # only=[] 는 "필터 없음"이 아니라 "지정한 게 하나도 없음"이다.
        # 예전 구현은 빈 리스트를 falsy로 취급해 전체 페이지를 골라 놓고도
        # is_target() 증분 필터를 건너뛰어 전부 create/update 대상으로
        # 만들었다.
        plan = ns.build_plan(only=[])
        self.assertEqual(plan, [])

    def test_plan_items_carry_parent(self):
        # 어떤 페이지가 어느 컨테이너로 가는지는 살아있는 wiki/index.md 배치에
        # 달려 있어 페이지가 늘면 바뀐다. 여기서는 배치 결과의 구체값이 아니라
        # "부모는 항상 알려진 컨테이너 중 하나"라는 성질만 확인한다. 구체적인
        # 배치 값 자체는 TestPlacement가 고정 fixture로 이미 검증한다.
        plan = ns.build_plan()
        for item in plan:
            if item["action"] in ("create", "update"):
                self.assertIn(item["parent"], ns.CONTAINER_NAMES,
                               f"{item['slug']}의 parent {item['parent']!r}가 "
                               "알려진 컨테이너가 아니다")

    def test_index_sections_called_once(self):
        """index_sections()는 wiki/index.md를 매번 재파싱하므로 슬러그마다
        부르면 35번 호출된다. build_plan은 루프 진입 전 한 번만 불러야 한다."""
        calls = []
        real_index_sections = ns.index_sections

        def counting():
            calls.append(1)
            return real_index_sections()

        with unittest.mock.patch.object(ns, "index_sections", counting):
            ns.build_plan()

        self.assertEqual(len(calls), 1)


class TestDryRunMakesNoHttpCalls(unittest.TestCase):
    def test_dry_run_does_not_touch_network(self):
        def explode(*a, **kw):
            raise AssertionError("dry-run에서 HTTP를 호출했다")

        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()), \
             unittest.mock.patch.object(ns.urllib.request, "urlopen", explode), \
             unittest.mock.patch.object(ns, "load_token", lambda root=None: "tok"):
            code = ns.main(["--dry-run"])
        self.assertEqual(code, 0)


class TestDryRunResetStampsMakesNoFileChanges(unittest.TestCase):
    def test_dry_run_reset_stamps_does_not_write(self):
        """--dry-run --reset-stamps는 1회성 파괴적 조작을 미리보기 없이
        실행하는 사고를 막아야 한다. reset_stamps 분기가 dry_run 검사보다
        먼저 있으면 --dry-run을 붙여도 35개 파일이 그대로 null로 바뀐다."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            wiki = pathlib.Path(d)
            original = ('---\ncategory: db운영\nnotion_page_id: "abc"\n'
                        'notion_synced: "2026-08-15T22:55:00+0900"\n---\n\n본문\n')
            (wiki / "a.md").write_text(original, encoding="utf-8")

            args = argparse.Namespace(
                reset_stamps=True, only=None, dry_run=True,
                force_replace=None, init_tree=False, refresh_tree=False)

            with contextlib.redirect_stdout(io.StringIO()) as out, \
                 unittest.mock.patch.object(ns, "WIKI", wiki):
                code = ns.run(args)

            text = (wiki / "a.md").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertEqual(text, original, "dry-run인데 파일이 바뀌었다")
        self.assertIn("1", out.getvalue())


class TestRunSurvivesUrlError(unittest.TestCase):
    def test_url_error_on_one_page_does_not_abort_run(self):
        """spec §6.5: 페이지 단위 독립 — 한 건 실패가 나머지를 막지 않는다.
        api()는 HTTPError만 감싸므로 DNS 실패 등 순수 URLError가 나면
        run() 루프가 이를 잡아 다음 페이지로 계속 진행해야 한다."""
        import urllib.error

        plan = [
            {"slug": "page-a", "action": "create", "parent": "MySQL",
             "page_id": None, "reason": ""},
            {"slug": "page-b", "action": "create", "parent": "MySQL",
             "page_id": None, "reason": ""},
        ]

        calls = []

        def fake_convert_page(slug):
            calls.append(slug)
            if slug == "page-a":
                raise urllib.error.URLError("network unreachable")
            return {"title": "Page B"}, "본문"

        args = argparse.Namespace(
            reset_stamps=False, only=None, dry_run=False,
            force_replace=None, init_tree=False, refresh_tree=False)

        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()), \
             unittest.mock.patch.object(ns, "build_plan", lambda only=None: plan), \
             unittest.mock.patch.object(ns, "load_token", lambda: "tok"), \
             unittest.mock.patch.object(ns, "load_tree", lambda: {"MySQL": "parent-id"}), \
             unittest.mock.patch.object(ns, "convert_page", fake_convert_page), \
             unittest.mock.patch.object(ns, "create_page", lambda *a, **kw: "new-page-id"), \
             unittest.mock.patch.object(ns.stamp_mod, "stamp",
                                        lambda slug, pid, ts: f"OK    {slug}"), \
             unittest.mock.patch.object(ns, "write_log", lambda **kw: None):
            code = ns.run(args)

        # page-a는 URLError로 실패했으므로 failed>=1 -> 종료 코드는 0이 아니다.
        # 그래도 page-b는 처리됐다 — 한 건 실패가 나머지를 막지 않는다는
        # 성질은 종료 코드가 아니라 calls로 검증한다.
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["page-a", "page-b"])


class TestRunHoldGate(unittest.TestCase):
    """run()이 실제로 HOLD 게이트를 지키는지 — fetch 후 replace 전에 검사해
    비어있지 않으면 건너뛰는지 — 를 검증한다. notion_only_sections 자체는
    이미 단위 테스트가 있지만, run() 안에서의 배선은 아무도 검증하지 않았다."""

    def _base_args(self, force_replace=None):
        return argparse.Namespace(
            reset_stamps=False, only=None, dry_run=False,
            force_replace=force_replace, init_tree=False, refresh_tree=False)

    def test_hold_honored_blocks_replace(self):
        plan = [{"slug": "page-a", "action": "update", "parent": "MySQL",
                 "page_id": "existing-id", "reason": ""}]

        def fake_convert_page(slug):
            return {"title": "Page A"}, "## 기존 절\n본문\n"

        def fake_fetch_markdown(token, page_id):
            return "## 기존 절\n본문\n## 여분 절\nNotion 전용 내용\n"

        replace_calls = []
        write_log_calls = []

        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()), \
             unittest.mock.patch.object(ns, "build_plan", lambda only=None: plan), \
             unittest.mock.patch.object(ns, "load_token", lambda: "tok"), \
             unittest.mock.patch.object(ns, "load_tree", lambda: {"MySQL": "parent-id"}), \
             unittest.mock.patch.object(ns, "convert_page", fake_convert_page), \
             unittest.mock.patch.object(ns, "fetch_markdown", fake_fetch_markdown), \
             unittest.mock.patch.object(
                 ns, "replace_page",
                 lambda *a, **kw: replace_calls.append(a)), \
             unittest.mock.patch.object(
                 ns, "write_log",
                 lambda **kw: write_log_calls.append(kw)):
            code = ns.run(self._base_args())

        self.assertEqual(replace_calls, [], "HOLD인데 replace_page가 호출됐다")
        self.assertEqual(code, 0)
        self.assertEqual(write_log_calls[0]["held"], 1)

    def test_force_replace_bypasses_hold_but_keeps_the_rest(self):
        plan = [{"slug": "page-a", "action": "update", "parent": "MySQL",
                 "page_id": "existing-id", "reason": ""}]

        def fake_convert_page(slug):
            return {"title": "Page A"}, "## 기존 절\n본문\n"

        def fake_fetch_markdown(token, page_id):
            # --force-replace 경로는 fetch_markdown을 아예 부르지 않아야
            # 하지만, 혹시 불렸더라도 HOLD 판정을 강제로 재현해 우회가
            # 실제로 일어나는지 확실히 확인한다.
            return "## 기존 절\n본문\n## 여분 절\nNotion 전용 내용\n"

        replace_calls = []
        stamp_calls = []
        write_log_calls = []

        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()), \
             unittest.mock.patch.object(ns, "build_plan", lambda only=None: plan), \
             unittest.mock.patch.object(ns, "load_token", lambda: "tok"), \
             unittest.mock.patch.object(ns, "load_tree", lambda: {"MySQL": "parent-id"}), \
             unittest.mock.patch.object(ns, "convert_page", fake_convert_page), \
             unittest.mock.patch.object(ns, "fetch_markdown", fake_fetch_markdown), \
             unittest.mock.patch.object(
                 ns, "replace_page",
                 lambda *a, **kw: replace_calls.append(a)), \
             unittest.mock.patch.object(
                 ns.stamp_mod, "stamp",
                 lambda slug, pid, ts: stamp_calls.append(slug) or f"OK    {slug}"), \
             unittest.mock.patch.object(
                 ns, "write_log",
                 lambda **kw: write_log_calls.append(kw)):
            code = ns.run(self._base_args(force_replace=["page-a"]))

        self.assertEqual(len(replace_calls), 1, "--force-replace인데 replace_page가 안 불렸다")
        self.assertIn("page-a", stamp_calls)
        self.assertEqual(code, 0)
        self.assertEqual(write_log_calls[0]["updated"], 1)
        self.assertEqual(write_log_calls[0]["held"], 0)


if __name__ == "__main__":
    unittest.main()
