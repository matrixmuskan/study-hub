#!/usr/bin/env bash
# CI and box test for rule R15 (tools/publish.sh branch guard). It uses a throwaway clone as the "shared checkout"
# (STUDY_HUB_SHARED_CHECKOUT) and a stub sh_lock.sh, so nothing is built, encrypted, committed or pushed.
# The guard must fire before the lock: the stub prints LOCK REACHED, which a blocked run must never show.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/sh-r15.XXXXXX")"
trap 'rm -rf "$T"' EXIT
S="$T/shared"
git clone -q --no-checkout "$REPO" "$S"
git -C "$S" checkout -q -B main "$(git -C "$REPO" rev-parse HEAD)"
git -C "$S" config user.name "Study Hub Bot"; git -C "$S" config user.email "study-hub-bot@users.noreply.github.com"
cp "$REPO/tools/publish.sh" "$S/tools/publish.sh"     # the version under test
printf '#!/usr/bin/env bash\necho "LOCK REACHED"\nexit 0\n' > "$S/tools/sh_lock.sh"; chmod +x "$S/tools/sh_lock.sh"
ln -s "$S" "$T/link"
n=0; fails=0
run() {   # run <name> <expect: blocked|passes> <script path> [override]
  local name="$1" want="$2" script="$3" ov="${4-$S}" out rc
  set +e; out="$(env -u SH_LOCK_HELD STUDY_HUB_SHARED_CHECKOUT="$ov" STUDY_HUB_SRC="$T/src" bash "$script" 2>&1)"; rc=$?; set -e
  n=$((n+1))
  if [ "$want" = blocked ]; then
    if [ $rc -eq 1 ] && grep -q "WRONG BRANCH" <<<"$out" && ! grep -q "LOCK REACHED" <<<"$out"; then echo "PASS: $name"
    else echo "FAIL: $name (rc=$rc)"; echo "$out" | sed 's/^/     /'; fails=$((fails+1)); fi
  else
    if [ $rc -eq 0 ] && grep -q "LOCK REACHED" <<<"$out" && ! grep -q "WRONG BRANCH" <<<"$out"; then echo "PASS: $name"
    else echo "FAIL: $name (rc=$rc)"; echo "$out" | sed 's/^/     /'; fails=$((fails+1)); fi
  fi
}
run "shared checkout on main reaches the lock" passes "$S/tools/publish.sh"
git -C "$S" checkout -q -b feat/x
run "shared checkout on a branch: WRONG BRANCH before the lock" blocked "$S/tools/publish.sh"
run "override with a trailing slash still blocks" blocked "$S/tools/publish.sh" "$S/"
run "override with a trailing /. still blocks" blocked "$S/tools/publish.sh" "$S/."
run "script run through a symlink to the shared checkout still blocks" blocked "$T/link/tools/publish.sh"
run "override given as a symlink still blocks" blocked "$S/tools/publish.sh" "$T/link"
pushd "$S/tools" >/dev/null; run "relative script path (cwd tools/) still blocks" blocked "./publish.sh"; popd >/dev/null
GIT_DIR="$(git -C "$REPO" rev-parse --absolute-git-dir)" run "GIT_DIR pointing at another repo does not hide the branch" blocked "$S/tools/publish.sh"
git -C "$S" checkout -q --detach
run "shared checkout with a detached HEAD: WRONG BRANCH" blocked "$S/tools/publish.sh"
git -C "$S" checkout -q main
git -C "$S" worktree add -q "$T/wt" -b feat/y
cp "$S/tools/publish.sh" "$T/wt/tools/publish.sh"; cp "$S/tools/sh_lock.sh" "$T/wt/tools/sh_lock.sh"
run "a worktree on a branch is not blocked" passes "$T/wt/tools/publish.sh"
git -C "$T/wt" checkout -q --detach
run "a worktree with a detached HEAD is not blocked" passes "$T/wt/tools/publish.sh"
run "a worktree is not blocked when the override is unset" passes "$T/wt/tools/publish.sh" ""
# The real shared checkout is always checked: the override adds a path, it cannot replace /workspace/study-hub.
n=$((n+1))
if grep -qE '^for SHARED in /workspace/study-hub "\$\{STUDY_HUB_SHARED_CHECKOUT:-\}"; do' "$REPO/tools/publish.sh"; then
  echo "PASS: /workspace/study-hub is always checked (the override cannot turn it off)"
else echo "FAIL: publish.sh does not always check /workspace/study-hub"; fails=$((fails+1)); fi
# The guard comes before the lock and the build in publish.sh.
n=$((n+1))
g=$(grep -n 'WRONG BRANCH' "$REPO/tools/publish.sh" | head -1 | cut -d: -f1)
l=$(grep -n 'sh_lock.sh' "$REPO/tools/publish.sh" | grep -v '^ *#' | grep -v ':#' | head -1 | cut -d: -f1)
b=$(grep -n 'build_index.py' "$REPO/tools/publish.sh" | head -1 | cut -d: -f1)
if [ -n "$g" ] && [ "$g" -lt "$l" ] && [ "$g" -lt "$b" ]; then echo "PASS: the guard is before the lock (line $l) and the build (line $b)"
else echo "FAIL: guard line $g, lock line $l, build line $b"; fails=$((fails+1)); fi
echo "branch guard tests: $n run, $fails failed"
[ "$fails" -eq 0 ]
