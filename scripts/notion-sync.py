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
