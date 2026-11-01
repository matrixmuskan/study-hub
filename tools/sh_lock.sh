#!/usr/bin/env bash
# One build-and-publish session at a time per mirror. Runs a command while holding an exclusive flock on
# <mirror>/.publish.lock, so no other bot can run sh_page.py, sh_provenance.py attach or publish.sh on the same
# mirror until the command ends. Use it for the whole window, from the build to the push:
#   tools/sh_lock.sh bash -c 'python3 tools/sh_page.py page.json && tools/publish.sh "msg" && git push origin main'
# publish.sh, sh_page.py and attach take the same lock on their own when they run outside sh_lock.sh.
# It also refuses a second clone or a worktree that points at a mirror another clone owns (<mirror>/_state/repo).
# Waits up to SH_LOCK_WAIT seconds (default 900), then exits 75 and names the holder.
set -uo pipefail
[ $# -ge 1 ] || { echo "usage: tools/sh_lock.sh <command> [args...]"; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
SRC="${STUDY_HUB_SRC:-$(dirname "$REPO")/study-hub-src}"
if [ -n "${SH_LOCK_HELD:-}" ]; then exec "$@"; fi
mkdir -p "$SRC/_state"
OWNER="$SRC/_state/repo"
if [ -s "$OWNER" ] && [ "$(cat "$OWNER")" != "$REPO" ]; then
  echo "WRONG CLONE: the mirror $SRC belongs to $(cat "$OWNER"). Build and publish only from there."
  echo "Branch work goes in a worktree with its own STUDY_HUB_SRC (never the shared mirror)."
  exit 76
fi
[ -s "$OWNER" ] || echo "$REPO" > "$OWNER"
LOCK="$SRC/.publish.lock"
exec 9>>"$LOCK"
if ! flock -w "${SH_LOCK_WAIT:-900}" 9; then
  echo "LOCKED: another bot holds $LOCK: $(cat "$LOCK" 2>/dev/null). Try again when it is done."
  exit 75
fi
: > "$LOCK"; echo "${SH_BOT:-unknown bot} pid $$ since $(date -Iseconds): $*" >> "$LOCK"
export SH_LOCK_HELD="$LOCK" STUDY_HUB_SRC="$SRC"
"$@"; rc=$?
: > "$LOCK"
exit $rc
