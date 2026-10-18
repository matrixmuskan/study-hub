#!/usr/bin/env bash
# Rebuild the hub home page from manifest.json, encrypt every plaintext page in the
# source mirror into this repo with StatiCrypt, and commit. Does NOT push.
# Needs: STATICRYPT_PASSWORD in the environment (or in ~/.study-hub.env, which this sources).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${STUDY_HUB_SRC:-$(dirname "$REPO")/study-hub-src}"
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

mapfile -t PAGES < <(cd "$SRC" && find . -name '*.html' -type f | sed 's|^\./||' | sort)
cd "$REPO"   # staticrypt resolves -c and -d relative to the working directory
# Only re-encrypt pages whose plaintext changed (StatiCrypt output is random each run,
# so re-encrypting unchanged big pages would bloat git history). Hashes live in the mirror.
HASHES="$SRC/_state/plaintext_sha256.txt"; mkdir -p "$SRC/_state"; touch "$HASHES"
for p in "${PAGES[@]}"; do
  h=$(sha256sum "$SRC/$p" | cut -d' ' -f1)
  if [ -f "$p" ] && grep -qx "$h  $p" "$HASHES" && [ "${FORCE:-0}" != 1 ]; then echo "unchanged $p"; continue; fi
  out_dir="$(dirname "$p")"
  mkdir -p "$out_dir"
  npx -y "staticrypt@$STATICRYPT_VERSION" "$SRC/$p" \
    -c .staticrypt.json \
    -d "$out_dir" \
    --remember 30 --short \
    -t "$REPO/tools/password_template.html" \
    --template-title "Krishiv's Study Hub" \
    --template-instructions "Enter the family password. Ask Muskan if you forgot." \
    --template-button "Let's go!" \
    --template-remember "Remember me for 30 days" \
    --template-color-primary "#2f6fed" --template-color-secondary "#dbe7ff" >/dev/null
  grep -v "  $p\$" "$HASHES" > "$HASHES.tmp" || true; echo "$h  $p" >> "$HASHES.tmp"; mv "$HASHES.tmp" "$HASHES"
  echo "encrypted $p"
done

# Safety: every page in the repo must be a StatiCrypt page
while IFS= read -r f; do
  if ! grep -q 'staticrypt' "$f"; then echo "NOT ENCRYPTED: $f"; exit 1; fi
done < <(find . -path ./.git -prune -o -name '*.html' -type f -not -path './tools/*' -print)

git add -A
if git diff --cached --quiet; then echo "nothing to commit"; else git commit -q -m "${1:-Publish study hub pages}" && git log --oneline -1; fi
echo "Done. Review, then push with: git push origin main"
