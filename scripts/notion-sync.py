#!/usr/bin/env python3
"""wiki/ -> Notion 단방향 동기화 (CLAUDE.md §6).

wiki가 항상 진실이다. Notion에서 직접 편집한 내용은 회수하지 않는다.

사용:
  python3 scripts/notion-sync.py                    증분 동기화
  python3 scripts/notion-sync.py --dry-run          계획만 출력 (HTTP 호출 0)
  python3 scripts/notion-sync.py --only <slug>...   지정 페이지만
"""
import datetime
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request

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
