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
STATICRYPT_VERSION="3.5.4"   # pinned: tools/password_template.html is from this version
if [ -z "${STATICRYPT_PASSWORD:-}" ] && [ -f "$HOME/.study-hub.env" ]; then set -a; . "$HOME/.study-hub.env"; set +a; fi
: "${STATICRYPT_PASSWORD:?Set STATICRYPT_PASSWORD (ask Muskan) or create ~/.study-hub.env}"
export STATICRYPT_PASSWORD

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
# so re-encrypting unchanged big pages would bloat git history). Hashes live in the mirror.
HASHES="$SRC/_state/staged_sha256.txt"; mkdir -p "$SRC/_state"; touch "$HASHES"
TPL_HASH=$(sha256sum "$REPO/tools/password_template.html" | cut -c1-12)
for p in "${PAGES[@]}"; do
  h=$( (sha256sum "$STAGE/$p" | cut -d' ' -f1; echo "$TPL_HASH") | sha256sum | cut -d' ' -f1)
  if [ -f "$p" ] && grep -qx "$h  $p" "$HASHES" && [ "${FORCE:-0}" != 1 ]; then echo "unchanged $p"; continue; fi
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
    --template-color-primary "#0066cc" --template-color-secondary "#e8f1fb" >/dev/null
  # Mark the encrypted file as built from an sh-2 staged page (validate.py checks this)
  tv=$(grep -o '<meta name="study-hub-template" content="[^"]*">' "$STAGE/$p" | head -1 | sed 's/.*content="\([^"]*\)".*/\1/')
  [ -n "$tv" ] || { echo "Staged page has no template marker: $p"; exit 1; }
  printf '\n<!-- study-hub-template: %s -->\n' "$tv" >> "$p"
  grep -v "  $p\$" "$HASHES" > "$HASHES.tmp" || true; echo "$h  $p" >> "$HASHES.tmp"; mv "$HASHES.tmp" "$HASHES"
  echo "encrypted $p"
done

# Safety: validate the repo (encryption, manifest, folders, template, secrets)
python3 "$REPO/tools/validate.py" --src "$STAGE"

git add -A -- 'G*/' index.html manifest.json  # only publish outputs; tools/assets changes go through a PR
if git diff --cached --quiet; then echo "nothing to commit"; else git commit -q -m "${1:-Publish study hub pages}" && git log --oneline -1; fi
echo "Done. Review, then push with: git pull --rebase && git push origin main"
