#!/usr/bin/env python3
"""Make a Study Hub page (sh-2 layout) from a content file, write it into the plaintext mirror,
and add or update its manifest.json entry.

Usage:  python3 tools/sh_page.py <content.json | content.md> [--src DIR] [--no-manifest] [--out FILE]

- Output goes to <src>/G<grade>/<Subject>/<id>/index.html  (src = $STUDY_HUB_SRC or ../study-hub-src).
- When the page has a quiz and "log" is not false, score logging is added and the token placeholder is
  replaced from $STUDY_HUB_SCORES_TOKEN (the token is never printed). Without the token the build stops.
- image and video blocks read local files and inline them as data: URIs (a page folder holds only index.html).
  One file over 15 MB stops the build; more than 40 MB of media on one page gives a warning.
- Then run tools/publish.sh to encrypt and commit.
See templates/page.example.json and CONTRIBUTING-BOTS.md.
"""
import argparse, base64, json, mimetypes, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L
import sh_provenance as P
import sh_f2 as F2

e = L.e
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$")
KINDS = ("game", "mock", "retest")
PLACEHOLDER = "__SH_SCORES_TOKEN__"
KIT_INJECT = "/workspace/study-hub-scores-kit/inject_token.sh"
MAX_FILE_MB = 15        # one media file larger than this stops the build
WARN_TOTAL_MB = 40      # a page with more inlined media than this gets a warning
IMAGE_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
             ".webp": "image/webp", ".avif": "image/avif", ".svg": "image/svg+xml"}
VIDEO_EXT = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm"}
VTT_EXT = {".vtt": "text/vtt"}
MEDIA = {"bytes": 0, "files": 0}   # inlined media payload of the page being built


def fail(msg):
    sys.exit("sh_page: " + msg)


def parse_md(text):
    """Markdown input: front matter (key: value), then '# <Section label>' starts a section.
    A fenced block ```quiz ... ``` holds quiz JSON; ```image ... ``` and ```video ... ``` hold the JSON
    fields of an image or video block (paths are relative to the .md file). Everything else is Markdown text."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        fail("Markdown file needs front matter between --- lines")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            meta[k.strip()] = {"true": True, "false": False}.get(v, v)
    sections = []
    parts = re.split(r"^# (.+)$", m.group(2), flags=re.M)
    for i in range(1, len(parts), 2):
        label, body = parts[i].strip(), parts[i + 1]
        blocks = []
        pm = re.search(r"^```provenance\s*\n(.*?)^```\s*$", body, flags=re.M | re.S)
        if pm:
            try:
                meta["provenance"] = json.loads(pm.group(1))
            except ValueError as ex:
                fail(f"bad JSON in ```provenance block: {ex}")
            body = body[:pm.start()] + body[pm.end():]
        pieces = re.split(r"^```(quiz|image|video)\s*\n(.*?)^```\s*$", body, flags=re.M | re.S)
        for j in range(0, len(pieces), 3):
            if pieces[j].strip():
                blocks.append({"type": "text", "md": pieces[j].strip()})
            if j + 2 < len(pieces):
                try:
                    q = json.loads(pieces[j + 2])
                except ValueError as ex:
                    fail(f"section '{label}': bad JSON in ```{pieces[j + 1]} block: {ex}")
                q["type"] = pieces[j + 1]
                blocks.append(q)
        sections.append({"id": re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"), "label": label, "blocks": blocks})
    meta["sections"] = sections
    return meta


def data_uri(path, base, what="image", types=None):
    """Read a local file and return it as a data: URI. Stops the build on a missing, wrong-type, or too-big file."""
    if not isinstance(path, str) or not path.strip():
        fail(f"{what}: 'src' (a local file path) is missing")
    p = os.path.expanduser(path)
    p = p if os.path.isabs(p) else os.path.join(base, p)
    if not os.path.isfile(p):
        fail(f"{what} file not found: {p}")
    ext = os.path.splitext(p)[1].lower()
    if types is not None and ext not in types:
        fail(f"{what} file must be one of {', '.join(sorted(types))}: {p}")
    size = os.path.getsize(p)
    if size > MAX_FILE_MB * 1024 * 1024:
        fail(f"{what} file is {size / 1048576:.1f} MB, the limit is {MAX_FILE_MB} MB per file: {p}. "
             "Compress it first (see CONTRIBUTING-BOTS.md, section 4)")
    mt = (types or {}).get(ext) or mimetypes.guess_type(p)[0] or "application/octet-stream"
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    MEDIA["bytes"] += len(b64)
    MEDIA["files"] += 1
    return "data:%s;base64,%s" % (mt, b64)


def render_block(b, base, quizzes, sec_id):
    t = b.get("type")
    if t == "text":
        return '<div class="sh-card sh-reveal">%s%s</div>' % (("<h2>%s</h2>" % e(b["title"])) if b.get("title") else "", L.md(b.get("md", "")))
    if t == "callout":
        return '<div class="sh-callout sh-reveal"><b>%s</b> %s</div>' % (e(b.get("title", "Tip")), L.md(b.get("md", "")))
    if t == "cards":
        items = "".join('<div class="sh-term"><b>%s</b><span>%s</span></div>' % (e(c.get("title", "")), e(c.get("body", ""))) for c in b.get("items", []))
        head = ("<h2>%s</h2>" % e(b["title"])) if b.get("title") else ""
        return '<div class="sh-section sh-reveal">%s<div class="sh-terms">%s</div></div>' % (head, items)
    if t == "image":
        if not str(b.get("alt", "")).strip():
            fail(f"image block in section '{sec_id}' needs 'alt' text (what the picture shows)")
        src = b.get("src", "")
        src = src if isinstance(src, str) and src.startswith("data:image/") else data_uri(src, base, "image", IMAGE_EXT)
        cap = ("<figcaption>%s</figcaption>" % e(b["caption"])) if b.get("caption") else ""
        return ('<figure class="sh-figure sh-reveal"><img src="%s" alt="%s" loading="lazy" decoding="async">%s</figure>'
                % (src, e(b["alt"]), cap))
    if t == "video":
        src = data_uri(b.get("src"), base, "video", VIDEO_EXT)
        title = b.get("title") or ""
        poster = (' poster="%s"' % data_uri(b["poster"], base, "video poster", IMAGE_EXT)) if b.get("poster") else ""
        track = ""
        if b.get("captions"):
            track = ('<track kind="captions" src="%s" srclang="en" label="English" default>'
                     % data_uri(b["captions"], base, "video captions", VTT_EXT))
        label = (' aria-label="%s"' % e(title)) if title else ""
        cap = ("<figcaption>%s</figcaption>" % e(title)) if title else ""
        return ('<figure class="sh-figure sh-video sh-reveal"><video controls playsinline preload="metadata"%s%s>'
                '<source src="%s" type="%s">%s'
                '<p>Your browser cannot play this video.</p></video>%s</figure>'
                % (poster, label, src, src[5:src.index(";")], track, cap))
    if t == "html":
        return '<div class="sh-reveal">%s</div>' % b["html"]
    if t == "quiz":
        kind = b.get("kind", "game")
        if kind not in KINDS:
            fail(f"quiz kind must be one of {KINDS}")
        qs = b.get("questions") or fail("quiz has no questions")
        for n, q in enumerate(qs, 1):
            if "q" not in q:
                fail(f"quiz question {n} has no 'q'")
            if "options" in q:
                if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(q["options"]):
                    fail(f"quiz question {n}: 'answer' must be the index of the right option")
            elif "answer_text" not in q:
                fail(f"quiz question {n} needs 'options' plus 'answer', or 'answer_text'")
            tm = q.get("traps")
            if tm is not None and (not isinstance(tm, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in tm.items())):
                fail(f"quiz question {n}: 'traps' must map an option letter or a typed wrong answer to a short text or trap key")
        for n, q in enumerate(qs, 1):   # item id: what the logger sends for a missed question (privacy v3, no text)
            q["id"] = q.get("id") or "q%d-%d" % (len(quizzes) + 1, n)
        quizzes.append({"kind": kind, "mode": b.get("mode", "practice" if kind == "game" else "test"), "section": sec_id,
                        "questions": qs})
        if isinstance(b.get("full"), bool):     # rule F2: mark a short mock as the full mock (or a long one as not full)
            quizzes[-1]["full"] = b["full"]
        pv = F2.prediction_value(b.get("prediction")) if isinstance(b.get("prediction"), dict) else None
        if b.get("prediction") is not None and not pv:
            fail("rule F2: quiz 'prediction' must be {\"total\": <predicted>, \"of\": <full total>}")
        if pv:                                  # rule F2: the coach's predicted score in the page metadata (numbers only)
            quizzes[-1]["prediction"] = {"total": pv[0], "of": pv[1]}
        head = ("<h2>%s</h2>" % e(b["title"])) if b.get("title") else ""
        sub = ('<p class="sh-sub">%s</p>' % e(b["intro"])) if b.get("intro") else ""
        return '<div class="sh-section">%s%s<div id="quiz-%d" data-sh-quiz="%d"></div></div>' % (head, sub, len(quizzes) - 1, len(quizzes) - 1)
    fail(f"unknown block type: {t}")


def build(c, base):
    for k in ("grade", "subject", "id", "title", "added_by", "sections"):
        if not c.get(k):
            fail(f"missing '{k}'")
    if not re.match(r"^G\d+$", c["grade"]):
        fail("grade must look like G3")
    if c["subject"] not in L.CFG["subjects"]:
        fail(f"unknown subject '{c['subject']}'. Known: {', '.join(L.CFG['subjects'])}. Add new codes to tools/sh_config.json")
    if not ID_RE.match(c["id"]):
        fail("id: letters, digits, dot, dash, underscore only, no spaces")
    if c.get("test_date") and not re.match(r"^\d{4}-\d{2}-\d{2}$", c["test_date"]):
        fail("test_date must be YYYY-MM-DD")
    rel = f'{c["grade"]}/{c["subject"]}/{c["id"]}/index.html'
    s = L.subject(c["subject"])
    quizzes, tabs, panels = [], [], []
    seen = set()
    for sec in c["sections"]:
        sid = re.sub(r"[^a-z0-9-]+", "-", (sec.get("id") or sec["label"]).lower()).strip("-")
        if sid in seen:
            fail(f"duplicate section id {sid}")
        seen.add(sid)
        tabs.append((sid, sec["label"]))
        inner = "".join(render_block(b, base, quizzes, sid) for b in sec.get("blocks", []))
        panels.append(f'<section class="sh-panel sh-wrap" id="p-{sid}" role="tabpanel" aria-labelledby="t-{sid}">{inner}</section>')
    chips = ""
    if c.get("test_date"):
        chips += f'<span class="sh-chip sh-chip--accent">Test day: {e(c["test_date"])}</span>'
    hero = (f'<header class="sh-wrap sh-hero"><p class="sh-eyebrow"><span class="sh-mono sh-mono--sm">{e(s["mono"])}</span>'
            f'{e(s["name"])} &middot; {e(L.grade_name(c["grade"]))}</p><h1>{e(c["title"])}</h1>'
            + (f'<p class="sh-lead">{e(c["subtitle"])}</p>' if c.get("subtitle") else "")
            + (f'<div class="sh-meta">{chips}</div>' if chips else "") + "</header>")
    body = hero + L.segmented(tabs) + "".join(panels)
    log = bool(quizzes) and c.get("log", True) is not False
    data = {"grade": c["grade"], "subject": c["subject"], "id": c["id"], "log": log, "quizzes": quizzes}
    if log:
        data["token"] = PLACEHOLDER
    return rel, L.page(rel, c["title"], body, code=c["subject"], data=data, log=log, crumb_title=c.get("short_title") or c["title"]), log


def checks(html_text):
    if "\u2014" in html_text:
        fail("em dash found. Use a comma, a colon, or a new sentence")
    bl = os.environ.get("STUDY_HUB_BLOCKLIST", "")
    if bl:
        txt = re.sub(r"data:[^\"')\s]+", "", html_text)
        if re.search(r"\b(?:%s)\b" % bl, txt, re.I):
            fail("private word found (STUDY_HUB_BLOCKLIST). Scrub the content first")


def upsert_manifest(c, rel, extra=None):
    mp = os.path.join(L.REPO, "manifest.json")
    items = json.load(open(mp, encoding="utf-8"))
    path = rel[: -len("index.html")]
    entry = {"grade": c["grade"], "subject": c["subject"], "title": c["title"], "path": path,
             "test_date": c.get("test_date", ""), "added_by": c["added_by"], "template": L.VERSION}
    entry.update(extra or {})
    for i, it in enumerate(items):
        if it.get("path") == path:
            items[i] = {**it, **entry}
            break
    else:
        items.append(entry)
    open(mp, "w", encoding="utf-8").write(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
    print("manifest.json: entry for", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("content")
    ap.add_argument("--src", default=L.default_src())
    ap.add_argument("--no-manifest", action="store_true")
    ap.add_argument("--out", help="write here instead of the mirror (for previews; placeholder token kept)")
    ap.add_argument("--no-provenance", action="store_true", help="do not write _provenance.json (legacy pages and tests only)")
    a = ap.parse_args()
    _lock = None if a.out else L.mirror_lock(a.src, "sh_page.py " + a.content)   # held until this process ends
    if os.path.exists(os.path.expanduser("~/.study-hub.env")) and not os.environ.get("STUDY_HUB_BLOCKLIST"):
        for line in open(os.path.expanduser("~/.study-hub.env")):
            if line.startswith("STUDY_HUB_BLOCKLIST="):
                os.environ["STUDY_HUB_BLOCKLIST"] = line.split("=", 1)[1].strip().strip("'\"")
    raw = open(a.content, encoding="utf-8").read()
    c = parse_md(raw) if a.content.endswith(".md") else json.loads(raw)
    rel, html_text, log = build(c, os.path.dirname(os.path.abspath(a.content)))
    if MEDIA["files"]:
        mb = MEDIA["bytes"] / 1048576
        print(f"media: {MEDIA['files']} files inlined, {mb:.1f} MB as base64")
        if mb > WARN_TOTAL_MB:
            print(f"sh_page: WARNING: inlined media is {mb:.1f} MB (over {WARN_TOTAL_MB} MB). The page will be slow to "
                  "open on a phone. Compress the videos or split the lesson into two pages", file=sys.stderr)
    checks(html_text)
    path = rel[: -len("index.html")]
    legacy = P.is_legacy(path)
    if legacy:
        print("sh_page: WARNING: %s is a legacy page (legacy_provenance); provenance is not required" % path, file=sys.stderr)
        if c.get("provenance"):
            print("sh_page: it has a provenance block, so remove it from legacy_provenance in tools/sh_config.json", file=sys.stderr)
    else:
        probs = P.content_problems(c)
        if probs:
            fail("provenance rules (P1, P2, B2, B7) failed:\n  " + "\n  ".join(probs))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(html_text)
        print("preview written to", a.out)
        return
    dst = os.path.join(a.src, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    old = os.umask(0o077)
    try:
        if log:
            if not os.environ.get("STUDY_HUB_SCORES_TOKEN"):
                fail("this page logs scores: set STUDY_HUB_SCORES_TOKEN (or add \"log\": false)")
            with tempfile.TemporaryDirectory() as td:
                tmp = os.path.join(td, "page.html")
                open(tmp, "w", encoding="utf-8").write(html_text)
                inj = KIT_INJECT if os.path.exists(KIT_INJECT) else os.path.join(L.TOOLS, "inject_token.sh")
                subprocess.run([inj, tmp, dst], check=True)
        else:
            open(dst, "w", encoding="utf-8").write(html_text)
    finally:
        os.umask(old)
    print("page written to", dst)
    extra = None
    if c.get("provenance") and not a.no_provenance:
        extra = write_provenance(c, path, L.build_id(html_text))
    elif not legacy and not a.no_provenance:
        fail("internal: no provenance written")
    if not a.no_manifest:
        upsert_manifest(c, rel, extra)


def write_provenance(c, path, build_id=""):
    """Write the full provenance record to study-hub-scores (private) and return the public counts and hash."""
    import hashlib
    import sh_scores as S
    try:
        where = S.check_access(write=True)
        log = S.get("%s/%s/_error_log.csv" % (c["grade"], c["subject"])) or b""
        built = P.now_pt().isoformat()
        rec = P.record_bytes(c, path, built, hashlib.sha256(log).hexdigest() if log else "",
                             P.open_row_ids(P.read_log(log.decode("utf-8"))), build_id=build_id)
        how = S.put(P.scores_path(path), rec, "provenance: %s" % path)
        S.put(P.build_copy_path(path, built), rec, "build history: %s" % path)   # B5 history
    except S.ScoresError as ex:
        fail("provenance not written: %s" % ex)
    f = P.manifest_fields(rec)
    try:
        lines, probs = P.f1_report(json.loads(rec), S)
    except S.ScoresError as ex:
        lines, probs = ["format: cannot read the cited receipts: %s" % ex], []
    for ln in lines:
        print(ln)
    for pr in probs:
        print("sh_page: WARNING: F1 mock format is out of range: %s" % pr, file=sys.stderr)
    print("provenance: %s %s (%s); %d sources, %d questions, %d inferred, %d error-log rows retested"
          % (how, P.scores_path(path), where, f["n_sources"], f["n_questions"], f["n_inferred"], f["n_retests"]))
    return f


if __name__ == "__main__":
    main()
