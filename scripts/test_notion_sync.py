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


if __name__ == "__main__":
    unittest.main()
