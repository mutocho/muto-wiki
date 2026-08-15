#!/usr/bin/env python3
"""동기화된 페이지의 frontmatter에 notion_page_id / notion_synced를 기록한다.

사용: python3 stamp.py <ISO타임스탬프> <slug>=<page_id> [<slug>=<page_id> ...]
"""
import re
import sys
import pathlib

WIKI = pathlib.Path(__file__).resolve().parent.parent / "wiki"


def stamp(slug, page_id, ts):
    p = WIKI / f"{slug}.md"
    if not p.exists():
        return f"SKIP  {slug} (파일 없음)"
    t = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    if not m:
        return f"SKIP  {slug} (frontmatter 없음)"
    fm = m.group(1)
    if not re.search(r"^notion_page_id:", fm, re.M):
        return f"SKIP  {slug} (notion_page_id 필드 없음)"
    fm2 = re.sub(r"^notion_page_id:.*$", f'notion_page_id: "{page_id}"', fm, flags=re.M)
    fm2 = re.sub(r"^notion_synced:.*$", f'notion_synced: "{ts}"', fm2, flags=re.M)
    p.write_text(f"---\n{fm2}\n---\n" + t[m.end():], encoding="utf-8")
    return f"OK    {slug}"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ts = sys.argv[1]
    for arg in sys.argv[2:]:
        slug, _, pid = arg.partition("=")
        print(stamp(slug, pid, ts))
