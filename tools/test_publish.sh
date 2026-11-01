#!/usr/bin/env bash
# End-to-end test of tools/publish.sh (runs in CI and on the box). It uses a throwaway git worktree, a temp mirror,
# and a dummy password, so it never touches the real pages or the real password.
#   1. a good sample page (text + image + video) must publish and commit, with the 'Validated: sh-2' trailer;
#   2. a page with a purple gradient must be refused (no commit);
#   3. a page with a broken link must be refused (no commit);
#   5. a page with no provenance is refused by sh_page.py, and P1 fails in validate.py;
#   6. a page that ignores a school receipt (B4) is refused by publish.sh;
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
# Browser: sh_browsercheck.py tries Playwright's Chromium, then /usr/bin/google-chrome. Say which one up front.
python3 "$REPO/tools/sh_browsercheck.py" --probe || { [ "${CI:-}" = "true" ] || { echo "FAIL: no browser for the publish test"; exit 1; }; }
export HOME="$T/home"; mkdir -p "$HOME"            # no ~/.study-hub.env: only the dummy password below
export STATICRYPT_PASSWORD="ci-dummy-$RANDOM-$RANDOM-pw" STUDY_HUB_SRC="$T/src" STUDY_HUB_BLOCKLIST=""
# The private score repo is a local folder here (provenance records, error logs, receipts), and the token is a dummy.
export STUDY_HUB_SCORES_DIR="$T/scores" STUDY_HUB_SCORES_TOKEN="ci-dummy-scores-token"
mkdir -p "$STUDY_HUB_SCORES_DIR"
mkdir -p "$STUDY_HUB_SRC" "$T/content"
# CI has no plaintext of the real pages, so the test site starts empty: no pages and an empty manifest.
git rm -rq --ignore-unmatch -- 'G*' index.html >/dev/null
echo "[]" > manifest.json
python3 - <<'PY'   # no pages, so no grandfathered pages either
import json
p = "tools/sh_config.json"; c = json.load(open(p)); c["legacy_provenance"] = []; json.dump(c, open(p, "w"), indent=2)
PY
git add manifest.json tools/sh_config.json && git commit -qm "test: empty site" --no-verify
python3 - "$T/content" <<'PY'
import base64, json, os, sys, zlib, struct
d = sys.argv[1]
def png(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    c = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(raw)) + c(b"IEND", b"")
open(os.path.join(d, "pic.png"), "wb").write(png(32, 18, (0, 102, 204)))
import hashlib
src = os.path.join(d, "facts.csv"); open(src, "w").write("fact\nThe compass rose shows directions.\n")
prov = {"sources": [{"id": "file:" + src, "kind": "study_guide", "sha256": hashlib.sha256(open(src, "rb").read()).hexdigest()}],
        "results_ingested": [], "weak_spots_from": []}
quiz = {"type": "quiz", "kind": "mock", "questions": [
    {"q": "What shows directions?", "options": ["The key", "The compass rose"], "answer": 1, "src": "file:%s#row=2" % src}]}
base = {"grade": "G3", "subject": "SS", "added_by": "CI", "provenance": prov}
good = dict(base, id="CI-Sample", title="CI sample page", sections=[{"id": "learn", "label": "Learn", "blocks": [
    {"type": "text", "title": "Hello", "md": "A sample page for the publish test."},
    {"type": "image", "src": "pic.png", "alt": "A blue box"}, quiz]}])
if os.path.exists(os.path.join(d, "clip.mp4")):
    good["sections"][0]["blocks"].append({"type": "video", "src": "clip.mp4", "title": "Clip"})
purple = dict(base, id="CI-Purple", title="CI purple page", sections=[{"id": "learn", "label": "Learn", "blocks": [
    {"type": "html", "html": "<div style=\"background:linear-gradient(90deg,#7b5cff,#ff5fa2,#22c55e)\">rainbow</div>"}, quiz]}])
broken = dict(base, id="CI-Broken", title="CI broken link page", sections=[{"id": "learn", "label": "Learn", "blocks": [
    {"type": "html", "html": "<a href=\"../Does-Not-Exist/\">missing page</a> <a href=\"#nowhere\">missing anchor</a>"}, quiz]}])
noprov = dict(good, id="CI-NoProv", title="CI page with no provenance"); noprov.pop("provenance")
for name, c in (("good", good), ("purple", purple), ("broken", broken), ("noprov", noprov)):
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
python3 - "$WT" <<'PY' || die "provenance: manifest counts or the private record are wrong"
import hashlib, json, os, sys
m = [i for i in json.load(open(os.path.join(sys.argv[1], "manifest.json"))) if i["path"] == "G3/SS/CI-Sample/"][0]
rec = open(os.path.join(os.environ["STUDY_HUB_SCORES_DIR"], "G3/SS/CI-Sample/_provenance.json"), "rb").read()
assert m["provenance_sha256"] == hashlib.sha256(rec).hexdigest() and m["n_sources"] == 1 and m["n_questions"] == 1
assert "facts.csv" not in json.dumps(m), "source path leaked into the public manifest"
PY
ok "good page published, committed with trailer, and decrypts; provenance hash and counts in manifest, record in the score repo"

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

# 5. a new page with no provenance block is refused at build time, and a manifest entry without the hash fails P1
if python3 tools/sh_page.py "$T/content/noprov.json" > "$T/out5.txt" 2>&1; then die "sh_page.py built a page with no provenance"; fi
grep -q "provenance" "$T/out5.txt" || { cat "$T/out5.txt"; die "no clear provenance message"; }
python3 - <<'PY' || die "validate.py did not fail P1 for a manifest entry with no provenance"
import json, subprocess
m = json.load(open("manifest.json")); m.append({"grade": "G3", "subject": "SS", "title": "x", "path": "G3/SS/CI-Sample-Copy/",
     "added_by": "CI", "template": "sh-2"})
json.dump(m, open("manifest.json", "w"))
r = subprocess.run(["python3", "tools/validate.py"], capture_output=True, text=True)
assert r.returncode == 1 and "P1: G3/SS/CI-Sample-Copy/" in r.stdout, r.stdout[-500:]
PY
git checkout -q manifest.json
ok "page with no provenance refused (sh_page.py), and P1 fails in validate.py"

# 4. logger page: private words are redacted by the page's own logger, and the page holds only hashes
# The two dummy private words are built at run time, so this file does not hold them (R7 scans tools/ too).
export STUDY_HUB_BLOCKLIST="Zorb""laxion|Quint""aviusz"
python3 - "$T/content" <<'PY2'
import json, os, sys
g = json.load(open(os.path.join(sys.argv[1], "good.json")))
sid = g["provenance"]["sources"][0]["id"]
c = {"grade": "G3", "subject": "SS", "id": "CI-Logger", "title": "CI logger page", "added_by": "CI", "provenance": g["provenance"],
     "sections": [{"id": "quiz", "label": "Quiz", "blocks": [{"type": "quiz", "kind": "mock", "questions": [
       {"q": "Pick B.", "options": ["A", "B"], "answer": 1, "topic": "t", "src": sid + "#row=2"},
       {"q": "Type a word.", "answer_text": ["yes"], "topic": "t", "src": sid + "#row=2"}]}]}]}
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

# 6. a learning-loop rule (B4) blocks publish: a school receipt for SS that the new page did not ingest
mkdir -p "$STUDY_HUB_SCORES_DIR/G3/_receipts"
echo '{"id": "gmail:1a00000000c1c1c1", "subject": "SS", "kind": "form_receipt", "title": "CI school test", "date": "2026-10-01", "datetime": "2026-10-01T09:00:00-07:00", "items": []}' \
  > "$STUDY_HUB_SCORES_DIR/G3/_receipts/1a00000000c1c1c1.json"
python3 - "$T/content" <<'PY2'
import json, os, sys
c = json.load(open(os.path.join(sys.argv[1], "good.json"))); c["id"] = "CI-Loop"; c["title"] = "CI loop page"
json.dump(c, open(os.path.join(sys.argv[1], "loop.json"), "w"))
PY2
python3 tools/sh_page.py "$T/content/loop.json" >/dev/null
before=$(git rev-parse HEAD)
if tools/publish.sh "CI: loop page" > "$T/out6.txt" 2>&1; then cat "$T/out6.txt"; die "publish.sh accepted a page that ignores a school receipt (B4)"; fi
[ "$(git rev-parse HEAD)" = "$before" ] || die "publish.sh committed the B4 page"
grep -q "B4: G3/SS/CI-Loop/" "$T/out6.txt" && grep -q "CHECK FAILED" "$T/out6.txt" || { cat "$T/out6.txt"; die "no clear B4 failure"; }
git checkout -q manifest.json
ok "page that ignores a school receipt refused by publish.sh (B4)"
echo "publish end-to-end test passed"
