#!/usr/bin/env python3
"""위키 마크다운 -> Notion-flavored Markdown 변환.

변환 대상:
  frontmatter      -> 제거하고 메타 정보를 상단 인용으로
  > [!tip] ...     -> <callout>
  GFM 파이프 테이블 -> <table> XML
  [[wikilink]]     -> `백틱` (Notion에 링크 대상이 없으므로)
  ^[inferred]      -> *(inferred)*  ('^' '[' ']'는 Notion에서 이스케이프 문자)
  들여쓰기 공백     -> 탭 (Notion은 탭으로 중첩을 표현)

코드블록 안은 어떤 변환도 하지 않는다.
"""
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
    """코드블록을 자리표시자로 치환해 변환에서 제외한다."""
    blocks = []

    def keep(m):
        blocks.append(m.group(0))
        return f"\x00CODE{len(blocks)-1}\x00"

    return re.sub(r"```.*?```", keep, text, flags=re.S), blocks


def unmask_code(text, blocks):
    for i, b in enumerate(blocks):
        text = text.replace(f"\x00CODE{i}\x00", b)
    return text


def conv_inline(s):
    s = re.sub(r"\[\[([^\]\|]+)\|([^\]]+)\]\]", lambda m: f"`{m.group(2)}`", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", lambda m: f"`{m.group(1)}`", s)
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
        for b in body:
            if b.strip() == "":
                continue
            if b.startswith(("- ", "1.", "* ")) or not merged:
                merged.append(b)
            else:
                merged[-1] = merged[-1].rstrip() + " " + b.strip()
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
