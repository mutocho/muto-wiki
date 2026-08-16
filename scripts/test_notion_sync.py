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
