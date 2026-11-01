#!/usr/bin/env bash
# CI: every commit in the range that carries the 'Validated: sh-<n>' trailer must pass tools/validate.py at that
# commit. Usage: check_trailers.sh <base> <head>   (base may be empty or all zeros: then the last 30 commits)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
base="${1:-}"; head="${2:-HEAD}"
if [ -z "$base" ] || [ "$base" = "0000000000000000000000000000000000000000" ] || ! git -C "$REPO" cat-file -e "$base^{commit}" 2>/dev/null; then
  range=(-n 30 "$head")
else
  range=("$base..$head")
fi
fails=0; n=0
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
for c in $(git -C "$REPO" log --format=%H "${range[@]}"); do
  tv=$(git -C "$REPO" log -1 --format='%(trailers:key=Validated,valueonly)' "$c" | tr -d '[:space:]')
  [ -n "$tv" ] || continue
  n=$((n+1))
  wt="$T/$c"
  git -C "$REPO" worktree add -q --detach "$wt" "$c"
  # The legacy_provenance list may only shrink compared with the commit's own parent (not with today's main, which
  # has already shrunk it further).
  pref="origin/main"; git -C "$REPO" cat-file -e "$c^" 2>/dev/null && pref="$c^"
  if (cd "$wt" && SH_BASE_REF="$pref" python3 tools/validate.py >"$T/out.txt" 2>&1); then
    echo "ok   $(git -C "$REPO" log -1 --format='%h %s' "$c") (Validated: $tv)"
  else
    echo "FAIL $(git -C "$REPO" log -1 --format='%h %s' "$c"): it says 'Validated: $tv' but validate.py fails there:"
    sed 's/^/     /' "$T/out.txt"; fails=$((fails+1))
  fi
  git -C "$REPO" worktree remove --force "$wt"
done
echo "trailer check: $n commits with a Validated trailer, $fails false"
[ "$fails" -eq 0 ]
