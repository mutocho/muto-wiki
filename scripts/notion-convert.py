#!/usr/bin/env python3
"""위키 마크다운 -> Notion-flavored Markdown 변환.

변환 대상:
  frontmatter      -> 제거하고 메타 정보를 상단 인용으로
  > [!tip] ...     -> <callout>
  GFM 파이프 테이블 -> <table> XML
  [[wikilink]]     -> <mention-page/>  (대상에 notion_page_id가 있을 때)
                      없으면 `백틱` (아직 Notion에 올라가지 않은 페이지)
  ^[inferred]      -> *(inferred)*  ('^' '[' ']'는 Notion에서 이스케이프 문자)
  들여쓰기 공백     -> 탭 (Notion은 탭으로 중첩을 표현)

코드블록 안은 어떤 변환도 하지 않는다.

wikilink는 self-closing <mention-page url="..."/> 로 낸다 — 제목은 Notion이
자동 표시하므로 위키 제목과 Notion 제목이 달라도 어긋나지 않는다.
"""
import glob
import os
import re
import sys
import pathlib

ADMONITION = {
    "tip":      ("\U0001F4A1", "blue_bg"),
    "warning":  ("\u26A0\uFE0F", "red_bg"),
    "note":     ("\U0001F4DD", "gray_bg"),
    "important": ("\u2757", "yellow_bg"),
    "caution":  ("\U0001F6D1", "orange_bg"),
}


def split_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    fm = {}
    key = None
    for line in m.group(1).split("\n"):
        if re.match(r"^\w[\w_]*:", line):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
        elif line.strip().startswith("- ") and key:
            fm[key] = (fm.get(key) or "") + ("; " if fm.get(key) else "") + line.strip()[2:].strip().strip('"')
    return fm, text[m.end():]


def mask_code(text):
    """코드·인라인코드를 자리표시자로 치환해 변환에서 제외한다.

    인라인 백틱도 가려야 한다. 위키는 `[[링크]]`·`^[세미나 발언]`처럼
    **표기법 자체를 인용**할 때 백틱으로 감싸는데(obsidian-wiki-tooling-gotchas
    참조), 가리지 않으면 conv_inline이 그 안까지 치환해 설명하려던 기호가
    사라진다 — 2026-08-16 재구축 카나리에서 실제로 발견했다.

    펜스를 먼저 매칭해야 ```가 인라인 패턴에 잘리지 않는다. 인라인 쪽이
    줄바꿈을 넘지 않게 [^`\\n]로 제한한다.
    """
    return _mask(text, r"```.*?```|`[^`\n]+`")


def mask_fences(text):
    """펜스 코드블록만 가린다. 인라인 백틱은 남긴다.

    절 제목 추출(notion-sync의 section_titles)이 쓴다. 거기서는 코드블록 안의
    `#`(MySQL 주석)만 걸러내면 되고, 인라인까지 가리면 제목 안의 인라인 코드가
    자리표시자로 바뀐다 — 자리표시자 번호는 원격·로컬이 서로 달라 절 제목이
    영원히 불일치하고 **모든 페이지가 거짓 HOLD**가 된다. 2026-08-16 재구축
    2차 패스에서 5개 페이지가 이렇게 막혔다.
    """
    return _mask(text, r"```.*?```")


def _mask(text, pattern):
    blocks = []

    def keep(m):
        blocks.append(m.group(0))
        return f"\x00CODE{len(blocks)-1}\x00"

    return re.sub(pattern, keep, text, flags=re.S), blocks


def unmask_code(text, blocks):
    for i, b in enumerate(blocks):
        text = text.replace(f"\x00CODE{i}\x00", b)
    return text


def load_page_ids():
    """wiki/*.md 프론트매터에서 slug -> notion_page_id 맵을 만든다.

    아직 동기화되지 않은(=id가 null인) 페이지는 맵에 없으므로 백틱으로 남는다.
    """
    wiki = pathlib.Path(__file__).resolve().parent.parent / "wiki"
    ids = {}
    for f in glob.glob(str(wiki / "*.md")):
        with open(f, encoding="utf-8") as fh:
            m = re.search(r'^notion_page_id:\s*"([^"]+)"', fh.read(), re.M)
        if m:
            ids[os.path.basename(f)[:-3]] = m.group(1).replace("-", "")
    return ids


PAGE_IDS = load_page_ids()


def link(target, label):
    """대상이 Notion에 있으면 mention, 없으면 백틱."""
    pid = PAGE_IDS.get(target.strip())
    if pid:
        return f'<mention-page url="https://app.notion.com/p/{pid}"/>'
    return f"`{label.strip()}`"


def conv_inline(s):
    s = re.sub(r"\[\[([^\]\|]+)\|([^\]]+)\]\]",
               lambda m: link(m.group(1), m.group(2)), s)
    s = re.sub(r"\[\[([^\]]+)\]\]",
               lambda m: link(m.group(1), m.group(1)), s)
    s = re.sub(r"\^\[([^\]]*)\]", lambda m: f" *({m.group(1)})*", s)
    return s


def conv_tables(lines):
    """GFM 파이프 테이블 -> Notion <table> XML."""
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        is_row = ln.strip().startswith("|") and ln.strip().endswith("|")
        sep = (i + 1 < len(lines)
               and re.match(r"^\s*\|[\s:\-\|]+\|\s*$", lines[i + 1] or ""))
        if is_row and sep:
            rows = []
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows.append(header)
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<table fit-page-width="true" header-row="true">')
            for r in rows:
                out.append("\t<tr>")
                for c in r:
                    # 셀 안에서는 파이프 이스케이프를 되돌리고 블록요소를 쓰지 않는다
                    cell = c.replace("\\|", "|")
                    out.append("\t\t<td>" + cell + "</td>")
                out.append("\t</tr>")
            out.append("</table>")
            continue
        out.append(ln)
        i += 1
    return out


def conv_callouts(lines):
    """> [!tip] Title / > - item  ->  <callout>."""
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^>\s*\[!(\w+)\]\s*(.*)$", lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        kind = m.group(1).lower()
        title = m.group(2).strip()
        icon, color = ADMONITION.get(kind, ("\U0001F4A1", "gray_bg"))
        body = []
        i += 1
        while i < len(lines) and lines[i].startswith(">"):
            body.append(re.sub(r"^>\s?", "", lines[i]))
            i += 1
        out.append(f'<callout icon="{icon}" color="{color}">')
        if title:
            out.append(f"\t**{title}**")
        # 인용 내부의 이어붙은 줄을 원래 항목으로 되돌린다
        merged = []
        blank_before = False
        for b in body:
            if b.strip() == "":
                # 빈 줄은 블록 경계다. 버리면 뒤 문단이 앞 항목에 붙는다
                blank_before = True
                continue
            # 순서 목록은 1. 뿐 아니라 2. 3. ... 전부 항목이다
            is_item = bool(re.match(r"^\s*(?:[-*]\s|\d+\.\s)", b))
            if is_item or blank_before or not merged:
                merged.append(b)
            else:
                merged[-1] = merged[-1].rstrip() + " " + b.strip()
            blank_before = False
        for b in merged:
            out.append("\t" + b)
        out.append("</callout>")
    return out


def conv_quotes(lines):
    """남은 여러 줄 인용을 <br>로 이어 한 블록으로 만든다."""
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith(">") and not lines[i].startswith(">>"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i]).rstrip())
                i += 1
            buf = [b for b in buf if b.strip()]
            out.append("> " + "<br>".join(buf))
            continue
        out.append(lines[i])
        i += 1
    return out


def indent_to_tabs(lines):
    res = []
    for ln in lines:
        m = re.match(r"^( +)(\S.*)$", ln)
        if m and re.match(r"^\s*[-*\d]", ln):
            res.append("\t" * (len(m.group(1)) // 2) + m.group(2))
        else:
            res.append(ln)
    return res


def convert(path):
    raw = pathlib.Path(path).read_text(encoding="utf-8")
    fm, body = split_frontmatter(raw)

    body, blocks = mask_code(body)
    lines = body.split("\n")
    lines = conv_callouts(lines)
    lines = conv_tables(lines)
    lines = conv_quotes(lines)
    lines = indent_to_tabs(lines)
    body = "\n".join(conv_inline(l) for l in lines)
    body = unmask_code(body, blocks)

    # 최상위 H1은 Notion 페이지 제목과 중복되므로 제거
    body = re.sub(r"^#\s+[^\n]*\n+", "", body, count=1, flags=re.M)

    meta = (
        f'<callout icon="\U0001F5C2\uFE0F" color="gray_bg">\n'
        f"\t**status** `{fm.get('status','?')}`  \u00b7  "
        f"**updated** `{fm.get('updated','?')}`  \u00b7  "
        f"**tags** `{fm.get('tags','')}`\n"
        f"\t{conv_inline(fm.get('summary',''))}\n"
        f"\t*\ub85c\uceec \uc704\ud0a4 `wiki/{pathlib.Path(path).stem}.md` \uc5d0\uc11c \ub3d9\uae30\ud654\ub428 \u2014 "
        f"\ud3b8\uc9d1\uc740 \ud56d\uc0c1 \uc704\ud0a4\uc5d0\uc11c \ud55c\ub2e4.*\n"
        f"</callout>"
    )
    return fm, meta + "\n\n" + body.strip() + "\n"


if __name__ == "__main__":
    fm, out = convert(sys.argv[1])
    sys.stdout.write(out)
