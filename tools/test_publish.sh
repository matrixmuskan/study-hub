#!/usr/bin/env bash
# End-to-end test of tools/publish.sh (runs in CI and on the box). It uses a throwaway git worktree, a temp mirror,
# and a dummy password, so it never touches the real pages or the real password.
#   1. a good sample page (text + image + video) must publish and commit, with the 'Validated: sh-2' trailer;
#   2. a page with a purple gradient must be refused (no commit);
#   3. a page with a broken link must be refused (no commit);
#   4. an sh-2 page with the score logger must publish with a hashed private-word list, and its own logger must turn
#      each private word into [name] (node, tools/test_redact.js) with no base64 or plain copy of the words in the page.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/sh-e2e.XXXXXX")"
WT="$T/study-hub"
cleanup() { git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true; rm -rf "$T"; }
trap cleanup EXIT
git -C "$REPO" worktree add -q --detach "$WT" HEAD
cd "$WT"
git config user.name "Study Hub Bot"; git config user.email "study-hub-bot@users.noreply.github.com"
export PYTHONUSERBASE="${PYTHONUSERBASE:-$HOME/.local}" npm_config_cache="${npm_config_cache:-$HOME/.npm}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
export HOME="$T/home"; mkdir -p "$HOME"            # no ~/.study-hub.env: only the dummy password below
export STATICRYPT_PASSWORD="ci-dummy-$RANDOM-$RANDOM-pw" STUDY_HUB_SRC="$T/src" STUDY_HUB_BLOCKLIST=""
unset STUDY_HUB_SCORES_TOKEN || true
mkdir -p "$STUDY_HUB_SRC" "$T/content"
# CI has no plaintext of the real pages, so the test site starts empty: no pages and an empty manifest.
git rm -rq --ignore-unmatch -- 'G*' index.html >/dev/null
echo "[]" > manifest.json
git add manifest.json && git commit -qm "test: empty site" --no-verify
python3 - "$T/content" <<'PY'
import base64, json, os, sys, zlib, struct
d = sys.argv[1]
def png(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    c = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(raw)) + c(b"IEND", b"")
open(os.path.join(d, "pic.png"), "wb").write(png(32, 18, (0, 102, 204)))
base = {"grade": "G3", "subject": "SS", "added_by": "CI", "log": False}
good = dict(base, id="CI-Sample", title="CI sample page", sections=[{"id": "learn", "label": "Learn", "blocks": [
    {"type": "text", "title": "Hello", "md": "A sample page for the publish test."},
    {"type": "image", "src": "pic.png", "alt": "A blue box"}]}])
if os.path.exists(os.path.join(d, "clip.mp4")):
    good["sections"][0]["blocks"].append({"type": "video", "src": "clip.mp4", "title": "Clip"})
purple = dict(base, id="CI-Purple", title="CI purple page", sections=[{"id": "learn", "label": "Learn", "blocks": [
    {"type": "html", "html": "<div style=\"background:linear-gradient(90deg,#7b5cff,#ff5fa2,#22c55e)\">rainbow</div>"}]}])
broken = dict(base, id="CI-Broken", title="CI broken link page", sections=[{"id": "learn", "label": "Learn", "blocks": [
    {"type": "html", "html": "<a href=\"../Does-Not-Exist/\">missing page</a> <a href=\"#nowhere\">missing anchor</a>"}]}])
for name, c in (("good", good), ("purple", purple), ("broken", broken)):
    json.dump(c, open(os.path.join(d, name + ".json"), "w"))
PY
if command -v ffmpeg >/dev/null; then
  ffmpeg -loglevel error -f lavfi -i testsrc2=size=320x180:rate=12 -f lavfi -i sine=frequency=440 -t 1 \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 64k -movflags +faststart "$T/content/clip.mp4"
  python3 - "$T/content" <<'PY'
import json, os, sys
p = os.path.join(sys.argv[1], "good.json"); c = json.load(open(p))
c["sections"][0]["blocks"].append({"type": "video", "src": "clip.mp4", "title": "Clip"}); json.dump(c, open(p, "w"))
PY
fi

ok() { echo "PASS: $1"; }
die() { echo "FAIL: $1"; exit 1; }

# 1. good page
python3 tools/sh_page.py "$T/content/good.json" >/dev/null
before=$(git rev-parse HEAD)
tools/publish.sh "CI: sample page" > "$T/out1.txt" 2>&1 || { cat "$T/out1.txt"; die "publish.sh failed on a good page"; }
after=$(git rev-parse HEAD)
[ "$before" != "$after" ] || { cat "$T/out1.txt"; die "publish.sh made no commit"; }
git log -1 --format=%B | grep -qx "Validated: sh-2" || die "commit has no 'Validated: sh-2' trailer"
git show --name-only --format= HEAD | grep -qx "G3/SS/CI-Sample/index.html" || die "the new page is not in the commit"
bad=$(git show --name-only --format= HEAD | grep -vE '^(G[0-9]+/.*index\.html|index\.html|manifest\.json)$' || true)
[ -z "$bad" ] || die "commit holds files other than pages and manifest.json: $bad"
grep -q "staticryptConfig" G3/SS/CI-Sample/index.html || die "page is not encrypted"
python3 - "$WT" <<'PY' || die "the committed page does not decrypt back to the sample"
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "tools")); import sh_decrypt as D, re, json
t = open(os.path.join(sys.argv[1], "G3/SS/CI-Sample/index.html")).read()
salt = json.loads(D.CFG_RE.search(t).group(1))["staticryptSaltUniqueVariableName"]
plain = D.decrypt_html(t, D.hash_password(os.environ["STATICRYPT_PASSWORD"], salt))
assert "A sample page for the publish test." in plain and "data:image/png;base64," in plain
PY
ok "good page published, committed with trailer, and decrypts"

# 2 and 3. bad pages must be refused
for bad in purple broken; do
  git checkout -q manifest.json 2>/dev/null || true
  python3 tools/sh_page.py "$T/content/$bad.json" >/dev/null
  before=$(git rev-parse HEAD)
  if tools/publish.sh "CI: $bad page" > "$T/out-$bad.txt" 2>&1; then cat "$T/out-$bad.txt"; die "publish.sh accepted the $bad page"; fi
  [ "$(git rev-parse HEAD)" = "$before" ] || die "publish.sh committed the $bad page"
  grep -q "CHECK FAILED" "$T/out-$bad.txt" || { cat "$T/out-$bad.txt"; die "no clear failure message for the $bad page"; }
  rm -rf "$STUDY_HUB_SRC/G3/SS/CI-${bad^}"
  ok "$bad page refused ($(grep -m1 -E 'BROKEN|DESIGN' "$T/out-$bad.txt" | cut -c1-110))"
done
git checkout -q manifest.json

# 4. logger page: private words are redacted by the page's own logger, and the page holds only hashes
export STUDY_HUB_BLOCKLIST="Zorblaxion|Quintaviusz" STUDY_HUB_SCORES_TOKEN="ci-dummy-scores-token"
python3 - "$T/content" <<'PY2'
import json, os, sys
c = {"grade": "G3", "subject": "SS", "id": "CI-Logger", "title": "CI logger page", "added_by": "CI", "sections": [
     {"id": "quiz", "label": "Quiz", "blocks": [{"type": "quiz", "kind": "mock", "questions": [
       {"q": "Pick B.", "options": ["A", "B"], "answer": 1, "topic": "t"},
       {"q": "Type a word.", "answer_text": ["yes"], "topic": "t"}]}]}]}
json.dump(c, open(os.path.join(sys.argv[1], "logger.json"), "w"))
PY2
python3 tools/sh_page.py "$T/content/logger.json" >/dev/null
tools/publish.sh "CI: logger page" > "$T/out4.txt" 2>&1 || { cat "$T/out4.txt"; die "publish.sh failed on the logger page"; }
git log -1 --format=%B | grep -qx "Validated: sh-2" || die "logger page commit has no trailer"
python3 - "$WT" "$T/logger-plain.html" <<'PY2' || die "logger page: hash list missing, or private words in plain/base64 form"
import os, sys, json
sys.path.insert(0, os.path.join(sys.argv[1], "tools")); import sh_decrypt as D, sh_lib as L
t = open(os.path.join(sys.argv[1], "G3/SS/CI-Logger/index.html")).read()
salt = json.loads(D.CFG_RE.search(t).group(1))["staticryptSaltUniqueVariableName"]
plain = D.decrypt_html(t, D.hash_password(os.environ["STATICRYPT_PASSWORD"], salt))
open(sys.argv[2], "w").write(plain)
bl = os.environ["STUDY_HUB_BLOCKLIST"]
assert L.logger_problems(plain, bl) == [], L.logger_problems(plain, bl)
assert len(L.REDACT_ELEM_RE.findall(plain)) == 1
for w in bl.split("|"):
    assert w.lower() not in plain.lower(), "plain word in page"
    assert not any(f in plain for f in L.encoded_forms(w)), "encoded word in page"
# the old trap: comment text that names the element must not count as the element
fake = "<body><script>var SHLog=(function(){ // <script id=\"sh-redact\"> \n function record(r){}\n return {init:init}})();</script></body>"
assert L.logger_problems(fake, bl), "logger_ok passed a page with no real sh-redact element"
assert len(L.REDACT_ELEM_RE.findall(L.patch_logger(fake, bl, "x"))) == 1, "patch_logger did not insert the element"
PY2
node tools/test_redact.js "$T/logger-plain.html" > "$T/out4b.txt" || { cat "$T/out4b.txt"; die "logger page leaks a private word"; }
ok "logger page: $(tail -1 "$T/out4b.txt")"
echo "publish end-to-end test passed"
