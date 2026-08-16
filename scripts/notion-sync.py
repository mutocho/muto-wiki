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
