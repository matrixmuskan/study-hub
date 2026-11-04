#!/usr/bin/env bash
# Build the hub pages from manifest.json, stage every plaintext page from the source mirror in the
# sh-2 design (tools/sh_stage.py), encrypt changed pages into this repo with StatiCrypt, validate, commit.
# Does NOT push.
# Needs: STATICRYPT_PASSWORD in the environment (or in ~/.study-hub.env, which this sources).
# Mirror: $STUDY_HUB_SRC or ../study-hub-src next to the repo. FORCE=1 re-encrypts every page.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${STUDY_HUB_SRC:-$(dirname "$REPO")/study-hub-src}"
export STUDY_HUB_SRC="$SRC"
# R15 (Gilfoy's R14, 2026-11-03): the shared checkout always stays on main, so it never commits or pushes another branch.
# Worktrees (any other folder) are not affected. The check uses real paths (symlinks and a trailing slash do not
# matter) and runs before the lock and the build. /workspace/study-hub is always checked; STUDY_HUB_SHARED_CHECKOUT
# (tests) adds one more path, it never turns the check off for /workspace/study-hub.
REPO_REAL="$(CDPATH= cd -P "$REPO" && pwd -P)"
for SHARED in /workspace/study-hub "${STUDY_HUB_SHARED_CHECKOUT:-}"; do
  [ -n "$SHARED" ] || continue
  SHARED_REAL="$(CDPATH= cd -P "$SHARED" 2>/dev/null && pwd -P || true)"
  [ -n "$SHARED_REAL" ] && [ "$REPO_REAL" = "$SHARED_REAL" ] || continue
  BR="$(env -u GIT_DIR -u GIT_WORK_TREE git -C "$REPO_REAL" branch --show-current 2>/dev/null || echo "?")"
  if [ "$BR" != "main" ]; then
    echo "WRONG BRANCH: $REPO is the shared checkout and is on '${BR:-detached HEAD}', not main (rule R15). Nothing was built, committed or pushed." >&2
    echo "Switch it back to main, and do branch work in a worktree: git -C $REPO worktree add /workspace/study-hub-wt/<name> -b <branch> origin/main" >&2
    exit 1
  fi
done
# One session per mirror: publish runs under tools/sh_lock.sh (the same lock as sh_page.py and attach).
if [ -n "${SH_LOCK_HELD:-}" ]; then   # inside a session: check it is real (right lock, held by this process tree)
  "$REPO/tools/sh_lock.sh" true || exit 77
else
  exec "$REPO/tools/sh_lock.sh" "$0" "$@"
fi
STATICRYPT_VERSION="3.5.4"   # pinned: tools/password_template.html is from this version
if { [ -z "${STATICRYPT_PASSWORD:-}" ] || [ -z "${STUDY_HUB_KID_FIRST_NAME:-}" ]; } && [ -f "$HOME/.study-hub.env" ]; then set -a; . "$HOME/.study-hub.env"; set +a; fi
: "${STATICRYPT_PASSWORD:?Set STATICRYPT_PASSWORD (ask Muskan) or create ~/.study-hub.env}"
# The child's first name (hub title, private-word scrub) lives only in ~/.study-hub.env, never in the repo. Fail closed.
: "${STUDY_HUB_KID_FIRST_NAME:?Set STUDY_HUB_KID_FIRST_NAME in ~/.study-hub.env (mode 600, never in the repo)}"
export STATICRYPT_PASSWORD STUDY_HUB_KID_FIRST_NAME

# tools/sh_config.json: attach (sh_provenance.py) takes pages out of legacy_provenance. That change is committed with
# the manifest below; any other uncommitted config change stops the publish (it goes through a PR).
CFG_STATE=$(python3 "$REPO/tools/sh_provenance.py" config-diff) || { echo "$CFG_STATE"; echo "Nothing was encrypted or committed."; exit 1; }
echo "$CFG_STATE"
python3 "$REPO/tools/build_index.py"

# House rules check on plaintext before encrypting
if grep -rlI $'\u2014' "$SRC" --include='*.html' >/dev/null 2>&1; then echo "Em dash found in $SRC, fix it first"; exit 1; fi
# Private words (school, teacher names, etc.) come from STUDY_HUB_BLOCKLIST in ~/.study-hub.env
# (a regex like 'word1|word2'), so they are never written into this public repo.
if [ -n "${STUDY_HUB_BLOCKLIST:-}" ]; then
  hits=$(grep -rlwE "$STUDY_HUB_BLOCKLIST" "$SRC" --include='*.html' || true)
  if [ -n "$hits" ]; then echo "Private words found, scrub first:"; echo "$hits"; exit 1; fi
fi

# Stage: plaintext with live tokens, so private (0700) and always deleted
umask 077
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/sh-stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
python3 "$REPO/tools/sh_stage.py" "$SRC" "$STAGE" >/dev/null

mapfile -t PAGES < <(cd "$STAGE" && find . -name '*.html' -type f | sed 's|^\./||' | sort)
cd "$REPO"   # staticrypt resolves -c and -d relative to the working directory
# Only re-encrypt pages whose staged plaintext changed (StatiCrypt output is random each run,
# so re-encrypting unchanged big pages would bloat git history). Hashes live in the mirror and are
# written only after a successful commit, so they always match what is committed.
HASHES="$SRC/_state/staged_sha256.txt"; mkdir -p "$SRC/_state"; touch "$HASHES"
NEWHASHES="$STAGE/.hashes"; cp "$HASHES" "$NEWHASHES"
TPL_HASH=$(sha256sum "$REPO/tools/password_template.html" | cut -c1-12)
CHANGED=()
for p in "${PAGES[@]}"; do
  h=$( (sha256sum "$STAGE/$p" | cut -d' ' -f1; echo "$TPL_HASH") | sha256sum | cut -d' ' -f1)
  if [ -f "$p" ] && grep -qx "$h  $p" "$HASHES" && [ "${FORCE:-0}" != 1 ]; then echo "unchanged $p"; continue; fi
  CHANGED+=("$p")
  grep -v "  $p\$" "$NEWHASHES" > "$NEWHASHES.tmp" || true; echo "$h  $p" >> "$NEWHASHES.tmp"; mv "$NEWHASHES.tmp" "$NEWHASHES"
done

# Checks on the plaintext BEFORE anything is encrypted: links, anchors, media, video codecs, design standard.
fail() { echo "CHECK FAILED: $1. Nothing was encrypted or committed."; exit 1; }
python3 "$REPO/tools/sh_checks.py" links "$STAGE" || fail "broken links or media (see above)"
python3 "$REPO/tools/sh_checks.py" design "$STAGE" || fail "design standard (see above)"
# Provenance and learning loop (B1-B6) for every changed page that is not in legacy_provenance. Reads
# study-hub-scores with STUDY_HUB_SCORES_TOKEN (or STUDY_HUB_SCORES_DIR in tests). P1, P2, B7 run in validate.py below.
PROV_PAGES=()
for p in "${CHANGED[@]}"; do [[ "$p" =~ ^G[0-9]+/[^/]+/[^/]+/index\.html$ ]] && PROV_PAGES+=("${p%index.html}"); done
if [ "${#PROV_PAGES[@]}" -gt 0 ]; then
  python3 "$REPO/tools/sh_provenance.py" check --pages "${PROV_PAGES[@]}" || fail "provenance or learning-loop rules (see above)"
fi
if [ "${#CHANGED[@]}" -gt 0 ]; then
  # Browser: Playwright's Chromium first, then a system Chrome (sh_browsercheck.py finds it). No browser = no commit
  # on the box; in CI (CI=true) the browser check is skipped with a warning.
  if python3 "$REPO/tools/sh_browsercheck.py" --probe; then
    python3 "$REPO/tools/sh_browsercheck.py" --root "$STAGE" --pages "${CHANGED[@]}" || fail "browser check: links, images, or videos do not work in Chrome"
  else
    echo "WARNING: no browser could start (see NO BROWSER above), so the browser check did not run."
    [ "${CI:-}" = "true" ] || fail "browser check is required on the box: install Playwright's Chromium or google-chrome"
  fi
fi

restore() {  # put back the committed ciphertext for every page this run touched
  for p in "${CHANGED[@]}"; do
    if git ls-files --error-unmatch "$p" >/dev/null 2>&1; then git checkout -q -- "$p"; else rm -f "$p"; fi
  done
}
for p in "${CHANGED[@]}"; do
  out_dir="$(dirname "$p")"
  mkdir -p "$out_dir"
  npx -y "staticrypt@$STATICRYPT_VERSION" "$STAGE/$p" \
    -c .staticrypt.json \
    -d "$out_dir" \
    --remember 30 --short \
    -t "$REPO/tools/password_template.html" \
    --template-title "Study Hub" \
    --template-instructions "Enter the family password. Ask Muskan if you forgot." \
    --template-button "Open" \
    --template-remember "Remember me for 30 days" \
    --template-color-primary "#0066cc" --template-color-secondary "#e8f1fb" >/dev/null || { restore; fail "StatiCrypt failed on $p"; }
  # Mark the encrypted file as built from an sh-2 staged page (validate.py checks this)
  tv=$(grep -o '<meta name="study-hub-template" content="[^"]*">' "$STAGE/$p" | head -1 | sed 's/.*content="\([^"]*\)".*/\1/')
  [ -n "$tv" ] || { restore; fail "staged page has no template marker: $p"; }
  printf '\n<!-- study-hub-template: %s -->\n' "$tv" >> "$p"
  echo "encrypted $p"
done

# Safety: validate the repo (encryption, manifest, folders, template, secrets, links, design). A failure stops
# here, puts the old ciphertext back, and commits nothing; the trailer is added only when validation passed.
VALIDATED=""
if python3 "$REPO/tools/validate.py" --src "$STAGE"; then
  VALIDATED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["template_version"])' "$REPO/tools/sh_config.json")
else
  restore; fail "validation"
fi

git add -A -- ':(glob)G*/**' index.html manifest.json  # only publish outputs; tools/assets changes go through a PR
case "$CFG_STATE" in *"publish.sh commits it"*) git add -- tools/sh_config.json ;; esac  # attach's legacy_provenance shrink only
if git diff --cached --quiet; then echo "nothing to commit"
else
  msg=(-m "${1:-Publish study hub pages}")
  [ -n "$VALIDATED" ] && msg+=(-m "Validated: $VALIDATED")
  git commit -q "${msg[@]}" || { restore; fail "git commit"; }
  git log --oneline -1
fi
cp "$NEWHASHES" "$HASHES"
# Plaintext hashes of every mirror page (content and hub pages), so the next run can see what changed in the mirror.
(cd "$SRC" && find . -name '*.html' -type f -not -path './_*' | sed 's|^\./||' | sort | xargs -r sha256sum) > "$SRC/_state/plaintext_sha256.txt"
echo "Done. Push with: git push origin main (inside the same tools/sh_lock.sh session; never git pull --rebase onto a rewritten main)"
