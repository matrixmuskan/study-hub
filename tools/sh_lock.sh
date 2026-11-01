#!/usr/bin/env bash
# One build-and-publish session at a time per mirror. Runs a command while holding an exclusive flock on
# <mirror>/.publish.lock, so no other bot can run sh_page.py, sh_provenance.py attach or publish.sh on the same
# mirror until the command ends. Use it for the whole window, from the build to the push:
#   SH_BOT=<name> tools/sh_lock.sh bash -c 'python3 tools/sh_page.py page.json && tools/publish.sh "msg" && git push origin main'
# publish.sh, sh_page.py and attach take the same lock on their own when they run outside sh_lock.sh.
# Inside a session (SH_LOCK_HELD set) it checks that SH_LOCK_HELD is this mirror's lock file AND that the flock is
# really held by SH_LOCK_PID, an ancestor of this process with the lock file open; otherwise it refuses (exit 77).
# One clone per mirror (<mirror>/_state/repo). If the owner clone no longer exists, the mirror is reclaimed (logged
# in <mirror>/_state/lock.log). Waits up to SH_LOCK_WAIT seconds (default 900), then exits 75 and names the holder.
set -uo pipefail
[ $# -ge 1 ] || { echo "usage: tools/sh_lock.sh <command> [args...]"; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
SRC="${STUDY_HUB_SRC:-$(dirname "$REPO")/study-hub-src}"
mkdir -p "$SRC/_state"
LOCK="$SRC/.publish.lock"
LOG="$SRC/_state/lock.log"

is_ancestor() {  # is pid $1 this shell or one of its ancestors?
  local p=$$
  while [ -n "$p" ] && [ "$p" -gt 1 ]; do
    [ "$p" = "$1" ] && return 0
    p=$(awk '/^PPid:/{print $2}' "/proc/$p/status" 2>/dev/null)
  done
  return 1
}

holds_fd() {  # does process $1 have an open fd on the lock file?
  local f t; t=$(readlink -f "$LOCK")
  for f in /proc/"$1"/fd/*; do [ "$(readlink -f "$f" 2>/dev/null)" = "$t" ] && return 0; done
  return 1
}

owner_check() {  # one clone per mirror; a gone owner is reclaimed (logged)
  local OWNER="$SRC/_state/repo" old
  if [ -s "$OWNER" ] && [ "$(cat "$OWNER")" != "$REPO" ]; then
    old="$(cat "$OWNER")"
    if [ -e "$old/.git" ]; then
      echo "WRONG CLONE: the mirror $SRC belongs to $old. Build and publish only from there."
      echo "Branch work goes in a worktree with its own STUDY_HUB_SRC (never the shared mirror)."
      exit 76
    fi
    echo "$(date -Iseconds) RECLAIM: owner $old no longer exists; mirror now owned by $REPO (${SH_BOT:-unknown bot})" | tee -a "$LOG" >&2
    echo "$REPO" > "$OWNER"
  fi
  [ -s "$OWNER" ] || echo "$REPO" > "$OWNER"
}

owner_check
if [ -n "${SH_LOCK_HELD:-}" ]; then
  # (b) only a real session of this mirror counts: right lock file, the flock is held, and the SH_LOCK_PID process
  # is an ancestor of this one that really has the lock file open (/proc/<pid>/fd). The pid text in the lock file
  # is only for people; it is not trusted.
  if [ "$SH_LOCK_HELD" != "$LOCK" ]; then
    echo "LOCK NOT HELD: SH_LOCK_HELD is $SH_LOCK_HELD, not this mirror's lock ($LOCK). Run inside tools/sh_lock.sh."; exit 77
  fi
  if ( flock -n 8 ) 8>>"$LOCK"; then
    echo "LOCK NOT HELD: SH_LOCK_HELD is set but nobody holds $LOCK. Run inside tools/sh_lock.sh."; exit 77
  fi
  if [ -z "${SH_LOCK_PID:-}" ] || ! is_ancestor "$SH_LOCK_PID" || ! holds_fd "$SH_LOCK_PID"; then
    echo "LOCK NOT HELD: the lock on $LOCK belongs to another session ($(cat "$LOCK" 2>/dev/null)), not to this process tree."; exit 77
  fi
  exec "$@"
fi

exec 9>>"$LOCK"
if ! flock -w "${SH_LOCK_WAIT:-900}" 9; then
  echo "LOCKED: another bot holds $LOCK: $(cat "$LOCK" 2>/dev/null). Try again when it is done."
  exit 75
fi
: > "$LOCK"; echo "${SH_BOT:-unknown bot} pid $$ since $(date -Iseconds): $*" >> "$LOCK"
export SH_LOCK_HELD="$LOCK" SH_LOCK_PID="$$" STUDY_HUB_SRC="$SRC"
"$@"; rc=$?
: > "$LOCK"
exit $rc
