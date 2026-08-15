#!/bin/bash
# muto-wiki git 동기화. 충돌 시 원격(origin/main)이 항상 우선한다.
#
#   bash scripts/sync.sh pull   # 세션 시작 시 — 최신 상태를 내려받는다
#   bash scripts/sync.sh push   # 세션/작업 종료 시 — 로컬 변경을 올린다
#
# 안전 규칙:
#   - main 브랜치에서만 동작한다. 다른 브랜치면 조용히 종료한다.
#   - 브랜치를 생성하지 않는다.
#   - 네트워크/인증 실패는 조용히 넘어간다 (작업을 막지 않는다).

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 0

# 이 저장소는 개인 위키로 main에서만 동기화한다.
[ "$(git branch --show-current 2>/dev/null)" = "main" ] || exit 0

# 원격이 없으면 로컬 커밋만 수행한다.
has_remote() { git remote get-url origin >/dev/null 2>&1; }

# 충돌 잔여분을 원격 우선으로 강제 해소한다.
resolve_theirs() {
  git diff --name-only --diff-filter=U | grep -q . || return 0
  git checkout --theirs -- . >/dev/null 2>&1 || true
  git add -A
  if git diff --name-only --diff-filter=U | grep -q .; then
    git merge --abort >/dev/null 2>&1 || true
    return 1
  fi
  git commit -qm "wiki: 충돌 자동 해소 (원격 우선)" || true
}

pull() {
  has_remote || exit 0

  # 로컬 변경이 있으면 병합 전에 먼저 커밋해 보존한다.
  git add -A
  git diff --cached --quiet || git commit -qm "wiki: 동기화 전 로컬 변경 보존 $(date +%F' '%T)"

  if ! git pull --no-rebase -X theirs -q; then
    # 인증·네트워크·권한 실패는 병합 충돌이 아니다.
    [ -f .git/MERGE_HEAD ] || exit 0
    resolve_theirs || exit 0
  fi
}

push() {
  git add -A
  if git diff --cached --quiet; then
    # 올릴 변경이 없어도 앞선 커밋이 밀려 있을 수 있다.
    has_remote && git push -q >/dev/null 2>&1
    exit 0
  fi
  git commit -qm "wiki: $(date +%F' '%T) 동기화" || exit 0

  has_remote || exit 0
  if ! git push -q >/dev/null 2>&1; then
    # 원격이 앞서 있으면 원격 우선으로 병합 후 1회 재시도한다.
    git pull --no-rebase -X theirs -q || { resolve_theirs || exit 0; }
    git push -q >/dev/null 2>&1 || exit 0
  fi
}

case "${1:-}" in
  pull) pull ;;
  push) push ;;
  *) echo "사용법: bash scripts/sync.sh {pull|push}" >&2; exit 2 ;;
esac

exit 0
