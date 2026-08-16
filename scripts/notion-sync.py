#!/usr/bin/env python3
"""wiki/ -> Notion 단방향 동기화 (CLAUDE.md §6).

wiki가 항상 진실이다. Notion에서 직접 편집한 내용은 회수하지 않는다.

사용:
  python3 scripts/notion-sync.py                    증분 동기화
  python3 scripts/notion-sync.py --dry-run          계획만 출력 (HTTP 호출 0)
  python3 scripts/notion-sync.py --only <slug>...   지정 페이지만
"""
import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
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
        if field in result and isinstance(result[field], str):
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


def write_log(created, updated, skipped, held, failed=0, log_path=None):
    """wiki/log.md 맨 위에 SYNC_NOTION 한 줄을 넣는다. 최신이 위."""
    path = log_path or (WIKI / "log.md")
    text = path.read_text(encoding="utf-8")
    line = (f"- [{now_iso()}] SYNC_NOTION pages={created + updated} "
            f"created={created} updated={updated} skipped={skipped} held={held} "
            f"failed={failed} "
            f'target="DBA"')
    marker = "# Wiki Log\n"
    index = text.index(marker) + len(marker)
    path.write_text(text[:index] + "\n" + line + "\n" + text[index:].lstrip("\n"),
                    encoding="utf-8")


# --------------------------------------------------------------------------
# 컨테이너 트리 (§6.1)
# --------------------------------------------------------------------------

TREE_FILE = SCRIPTS / "notion-tree.json"

# (컨테이너, 부모). 부모가 먼저 오도록 정렬돼 있다.
TREE_SPEC = [
    ("db운영", "DBA"),
    ("MySQL", "db운영"),
    ("PostgreSQL", "db운영"),
    ("SQL Server", "db운영"),
    ("Aurora DSQL", "db운영"),
    ("엔진 공통", "db운영"),
    ("엔진 비교", "엔진 공통"),
    ("진단·운영 표준", "엔진 공통"),
    ("보안·권한", "엔진 공통"),
    ("개발·자동화", "엔진 공통"),
    ("지식 운영", "엔진 공통"),
    ("업무기록", "DBA"),
    ("kakaogames", "업무기록"),
    ("개인", "DBA"),
    ("참고자료", "DBA"),
    ("종합원칙", "DBA"),
]


def load_tree():
    if not TREE_FILE.exists():
        return {"DBA": DBA_PAGE_ID}
    tree = json.loads(TREE_FILE.read_text(encoding="utf-8"))
    tree.setdefault("DBA", DBA_PAGE_ID)
    return tree


def save_tree(tree):
    TREE_FILE.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def init_tree(token):
    """없는 컨테이너만 만든다. 이미 있는 것은 건드리지 않는다."""
    tree = load_tree()
    for name, parent in TREE_SPEC:
        if name in tree:
            continue
        parent_id = tree[parent]
        tree[name] = create_page(token, parent_id, name, "")
        print(f"[create-container] {name} -> {parent}")
        save_tree(tree)          # 중간 실패해도 진행분이 남도록 매번 쓴다
    save_tree(tree)
    return tree


def refresh_tree(token):
    """DBA 아래 자식 페이지를 훑어 이름 -> id를 재구성한다."""
    tree = {"DBA": DBA_PAGE_ID}
    known = {name for name, _ in TREE_SPEC}

    def walk(page_id):
        cursor = None
        while True:
            path = f"/blocks/{page_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={cursor}"
            result = api("GET", path, token)
            for block in result.get("results", []):
                if block.get("type") != "child_page":
                    continue
                title = block["child_page"]["title"]
                if title in known:
                    tree[title] = block["id"]
                    walk(block["id"])
            if not result.get("has_more"):
                return
            cursor = result.get("next_cursor")
            if not cursor:
                return

    walk(DBA_PAGE_ID)
    save_tree(tree)
    return tree


# --------------------------------------------------------------------------
# 1회성 초기화
# --------------------------------------------------------------------------

def reset_stamps(wiki_dir=None, dry_run=False):
    """notion_page_id·notion_synced를 null로 되돌린다.

    Notion에서 페이지를 삭제한 뒤 반드시 먼저 실행한다. 휴지통의 페이지는
    여전히 유효한 id로 조회되므로, 리셋하지 않으면 휴지통 페이지를 되살린다.

    dry_run=True면 바뀔 개수만 세고 파일에는 쓰지 않는다 — 되돌릴 수 없는
    1회성 조작이므로 미리보기 없이 실행하면 위험하다.
    """
    directory = wiki_dir or WIKI
    count = 0
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            continue
        fm = m.group(1)
        new_fm = re.sub(r"^notion_page_id:.*$", "notion_page_id: null", fm, flags=re.M)
        new_fm = re.sub(r"^notion_synced:.*$", "notion_synced: null", new_fm, flags=re.M)
        if new_fm == fm:
            continue
        count += 1
        if not dry_run:
            path.write_text(f"---\n{new_fm}\n---\n" + text[m.end():], encoding="utf-8")
    return count


# --------------------------------------------------------------------------
# 계획
# --------------------------------------------------------------------------

def build_plan(only=None):
    """무엇을 어떻게 할지 먼저 전부 정한다. HTTP 호출은 하지 않는다."""
    sections = index_sections()
    pages = knowledge_pages()
    slugs = sorted(only) if only is not None else sorted(pages)

    plan = []
    for slug in slugs:
        fm = pages.get(slug)
        if fm is None:
            plan.append({"slug": slug, "action": "hold", "parent": None,
                         "page_id": None, "reason": "wiki에 없는 페이지"})
            continue

        page_id = fm.get("notion_page_id", "null")
        page_id = None if page_id in ("null", "") else page_id

        if only is None and not is_target(fm):
            plan.append({"slug": slug, "action": "skip", "parent": None,
                         "page_id": page_id, "reason": "updated <= notion_synced"})
            continue

        try:
            parent = placement(slug, fm, sections)
        except HoldError as e:
            plan.append({"slug": slug, "action": "hold", "parent": None,
                         "page_id": page_id, "reason": str(e)})
            continue

        plan.append({
            "slug": slug,
            "action": "update" if page_id else "create",
            "parent": parent,
            "page_id": page_id,
            "reason": "",
        })
    return plan


def print_plan(plan):
    counts = {"create": 0, "update": 0, "skip": 0, "hold": 0}
    for item in plan:
        counts[item["action"]] += 1
    for item in plan:
        if item["action"] == "skip":
            continue
        if item["action"] == "hold":
            print(f"[HOLD]   {item['slug']}\n         └─ {item['reason']}")
        else:
            print(f"[{item['action']}] {item['slug']} -> {item['parent']}")
    print(f"\n계획: create={counts['create']} update={counts['update']} "
          f"skip={counts['skip']} hold={counts['hold']}")
    return counts


# --------------------------------------------------------------------------
# 실행
# --------------------------------------------------------------------------

def run(args):
    if args.reset_stamps:
        count = reset_stamps(dry_run=args.dry_run)
        if args.dry_run:
            print(f"--dry-run: notion_page_id·notion_synced를 되돌릴 페이지 {count}개 "
                  "(파일 변경 없음)")
        else:
            print(f"notion_page_id·notion_synced를 null로 되돌렸다: {count}개")
        return 0

    plan = build_plan(only=args.only)
    print_plan(plan)

    if args.dry_run:
        print("\n--dry-run: HTTP 호출 없음")
        return 0

    try:
        token = load_token()
    except AuthError as e:
        print(f"\n{e}", file=sys.stderr)
        return 2

    if args.init_tree:
        init_tree(token)
        print("컨테이너 트리 준비 완료")
        return 0
    if args.refresh_tree:
        refresh_tree(token)
        print("컨테이너 트리 재탐색 완료")
        return 0

    tree = load_tree()
    forced = set(args.force_replace or [])
    created = updated = held = failed = 0
    skipped = sum(1 for item in plan if item["action"] == "skip")
    held += sum(1 for item in plan if item["action"] == "hold")

    for item in plan:
        if item["action"] in ("skip", "hold"):
            continue
        slug = item["slug"]
        try:
            fm, md = convert_page(slug)

            if item["action"] == "update" and slug not in forced:
                remote = fetch_markdown(token, item["page_id"])
                extra = notion_only_sections(remote, md)
                if extra:
                    print(f"[HOLD]   {slug}\n         └─ Notion 전용 절 {len(extra)}개: "
                          + ", ".join(extra))
                    held += 1
                    continue

            parent_id = tree.get(item["parent"])
            if parent_id is None:
                print(f"[HOLD]   {slug}\n         └─ 컨테이너 '{item['parent']}' 없음. "
                      "--init-tree 먼저 실행")
                held += 1
                continue

            if item["action"] == "create":
                page_id = create_page(token, parent_id, fm["title"], md)
            else:
                page_id = item["page_id"]
                replace_page(token, page_id, md)

            # 성공 즉시 페이지 단위로 기록한다. 마지막에 몰아 쓰면 중간 실패 시
            # 어디까지 올렸는지 알 수 없어 다음 실행이 전량 재업로드가 된다 (§6.3).
            status = stamp_mod.stamp(slug, page_id, now_iso())
            if not status.startswith("OK"):
                # 업로드는 됐지만 프론트매터에 기록하지 못했다 — 다음 실행이
                # 같은 페이지를 또 만든다. 성공으로 세면 안 된다 (§6.3).
                print(f"[FAIL]   {slug}: {status}", file=sys.stderr)
                failed += 1
                continue

            if item["action"] == "create":
                created += 1
            else:
                updated += 1
            print(f"[ok]     {slug} -> {page_id}")

        except (ApiError, KeyError, urllib.error.URLError) as e:
            print(f"[FAIL]   {slug}: {e}", file=sys.stderr)
            failed += 1

    write_log(created=created, updated=updated, skipped=skipped, held=held, failed=failed)
    print(f"\n완료: created={created} updated={updated} skipped={skipped} held={held} "
          f"failed={failed}")
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="wiki/ -> Notion 단방향 동기화")
    parser.add_argument("--dry-run", action="store_true", help="계획만 출력, HTTP 호출 0")
    parser.add_argument("--only", nargs="+", metavar="SLUG",
                        help="지정 페이지만 (강제 재업로드는 사용자가 페이지를 명시한다)")
    parser.add_argument("--force-replace", nargs="+", metavar="SLUG",
                        help="HOLD를 무시하고 덮어쓴다")
    parser.add_argument("--init-tree", action="store_true", help="컨테이너 생성 (1회성)")
    parser.add_argument("--refresh-tree", action="store_true", help="컨테이너 id 재탐색")
    parser.add_argument("--reset-stamps", action="store_true",
                        help="notion_page_id·notion_synced를 null로 (1회성)")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
