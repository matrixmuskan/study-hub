#!/usr/bin/env python3
"""Static checks for Study Hub pages: links, anchors, media (data URIs, video codecs), and the design standard.

Used by tools/validate.py (CI and publish.sh). Run alone:
  python3 tools/sh_checks.py links  <plaintext_site_root> [page ...]
  python3 tools/sh_checks.py design <file_or_dir> [...]          (CSS, JS, or plaintext HTML)
"""
import base64, binascii, json, os, re, shutil, subprocess, sys, tempfile, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L

MAX_MEDIA = 15 * 1024 * 1024
MAGIC = {
    "image/png": lambda b: b[:8] == b"\x89PNG\r\n\x1a\n",
    "image/jpeg": lambda b: b[:3] == b"\xff\xd8\xff",
    "image/jpg": lambda b: b[:3] == b"\xff\xd8\xff",
    "image/gif": lambda b: b[:4] == b"GIF8",
    "image/webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
    "image/avif": lambda b: b[4:12] in (b"ftypavif", b"ftypavis"),
    "image/svg+xml": lambda b: b"<svg" in b[:2000].lower(),
    "video/mp4": lambda b: b[4:8] == b"ftyp",
    "audio/mp4": lambda b: b[4:8] == b"ftyp",
    "video/webm": lambda b: b[:4] == b"\x1a\x45\xdf\xa3",
    "audio/webm": lambda b: b[:4] == b"\x1a\x45\xdf\xa3",
    "audio/mpeg": lambda b: b[:3] == b"ID3" or b[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
    "text/vtt": lambda b: b.lstrip(b"\xef\xbb\xbf")[:6] == b"WEBVTT",
    "font/ttf": lambda b: b[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO"),
    "font/otf": lambda b: b[:4] == b"OTTO",
    "font/woff": lambda b: b[:4] == b"wOFF",
    "font/woff2": lambda b: b[:4] == b"wOF2",
    "application/pdf": lambda b: b[:5] == b"%PDF-",
}
PLAY_VIDEO = {"h264", "vp8", "vp9", "av1"}
PLAY_AUDIO = {"aac", "mp3", "opus", "vorbis"}
DATA_RE = re.compile(r"data:([a-z0-9.+/-]+)((?:;(?!base64[,;])[a-z0-9.+=-]+)*)(;base64)?,([^\"'()\s<>`\\]*)", re.I)
ATTR_RE = re.compile(r"""<([a-z][a-z0-9]*)\b([^>]*)>""", re.I | re.S)
ATTR_VAL = re.compile(r"""\b(href|src|poster|data)\s*=\s*(["'])(.*?)\2""", re.I | re.S)
ID_RE = re.compile(r"""\b(?:id|name)\s*=\s*(["'])([^"']+)\1""", re.I)


def strip_scripts(h):
    return re.sub(r"<script\b.*?</script>", "", h, flags=re.S | re.I)


def check_data_uri(mt, params, b64, payload, probe=True):
    """Return '' when the data URI is good, else the cause."""
    mt = mt.lower()
    if not b64:
        if mt.startswith(("video/", "audio/")) or mt in ("image/png", "image/jpeg", "image/webp", "image/gif", "font/ttf"):
            return "binary data URI without ;base64"
        return ""
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as ex:
        return "base64 does not decode (%s)" % str(ex)[:60]
    if not raw:
        return "empty data URI"
    test = MAGIC.get(mt)
    if test and not test(raw):
        return "bytes are not %s (wrong MIME type or broken file)" % mt
    if len(raw) > MAX_MEDIA and mt.startswith(("video/", "audio/", "image/")):
        return "one media file is %.1f MB (limit 15 MB)" % (len(raw) / 1048576)
    if probe and mt.startswith(("video/", "audio/")) and shutil.which("ffprobe"):
        with tempfile.NamedTemporaryFile(suffix=".bin") as f:
            f.write(raw); f.flush()
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name:format=duration",
                                "-of", "json", f.name], capture_output=True, text=True)
        try:
            j = json.loads(r.stdout or "{}")
        except ValueError:
            j = {}
        st = j.get("streams") or []
        if r.returncode or not st:
            return "ffprobe cannot read the media (%s)" % (r.stderr.strip().splitlines() or ["no streams"])[-1][:80]
        v = [s.get("codec_name") for s in st if s.get("codec_type") == "video"]
        a = [s.get("codec_name") for s in st if s.get("codec_type") == "audio"]
        if mt.startswith("video/") and not v:
            return "video has no video stream"
        bad = [c for c in v if c not in PLAY_VIDEO] + [c for c in a if c not in PLAY_AUDIO]
        if bad:
            return "codec %s does not play in all browsers (use H.264 + AAC)" % ",".join(bad)
        try:
            if float((j.get("format") or {}).get("duration") or 0) <= 0:
                return "media has no duration"
        except ValueError:
            pass
    return ""


def page_links(root, rel, h, probe=True, also=()):
    """Yield (link, type, cause) for each problem in one plaintext page."""
    page_url = "/" + rel
    static = strip_scripts(h)
    ids = set(m.group(2) for m in ID_RE.finditer(h))
    seen = set()
    for m in ATTR_RE.finditer(static):
        tag = m.group(1).lower()
        for a in ATTR_VAL.finditer(m.group(2)):
            attr, val = a.group(1).lower(), a.group(3).strip()
            kind = {"a": "href", "link": "link"}.get(tag, tag) if attr == "href" else ("%s %s" % (tag, attr))
            if val.startswith("data:") or (attr == "href" and val.startswith(("mailto:", "tel:", "javascript:"))):
                continue
            if "${" in val or val == "undefined":
                continue  # a script fills it in; the browser check covers it
            if val.startswith(("http://", "https://", "//")):
                continue  # external; the live check covers it
            if (kind, val) in seen:
                continue
            seen.add((kind, val))
            if val in ("", "#"):
                if attr != "href":
                    yield (val or "(empty)", kind, "empty %s" % attr)
                continue
            if val.startswith("#"):
                frag = urllib.parse.unquote(val[1:])
                if frag not in ids:
                    yield (val, "anchor", "no element with id '%s' on the page" % frag)
                continue
            target = urllib.parse.urljoin(page_url, val.split("#")[0].split("?")[0])
            path = urllib.parse.unquote(target).lstrip("/")
            fs = os.path.join(root, path)
            if target.endswith("/") or os.path.isdir(fs):
                fs = os.path.join(fs, "index.html")
            if not os.path.isfile(fs) and not any(os.path.isfile(os.path.join(r, os.path.relpath(fs, root))) for r in also):
                yield (val, kind if attr == "href" else "media", "target missing: /%s" % os.path.relpath(fs, root))
    nvid = 0
    for d in DATA_RE.finditer(h):
        mt = d.group(1)
        cause = check_data_uri(mt, d.group(2), bool(d.group(3)), d.group(4), probe=probe)
        nvid += mt.startswith("video/")
        if cause:
            yield ("data:%s (%d chars)" % (mt, len(d.group(4))), "data-uri", cause)


def check_links(root, pages=None, probe=True, also=()):
    """Static link and media check over a plaintext site folder. 'also': more roots where a link target may exist
    (for example the repo with the encrypted pages, when the stage holds only some pages)."""
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))]
        for f in files:
            if not f.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/")
            if pages and rel not in pages:
                continue
            h = open(os.path.join(dirpath, f), encoding="utf-8").read()
            for link, kind, cause in page_links(root, rel, h, probe=probe, also=also):
                out.append((rel, link, kind, cause))
    return out


# ---------- design lint ----------
def _css_contexts(text, is_html):
    """Yield (where, css_text) for the parts of a file that hold styles."""
    if not is_html:
        yield ("file", text)
        return
    t = re.sub(r"data:[^\"'()\s]+", "", text)
    t = re.sub(r"<svg\b.*?</svg>", "", t, flags=re.S | re.I)
    for m in re.finditer(r"<style\b([^>]*)>(.*?)</style>", t, re.S | re.I):
        yield ("<style%s>" % m.group(1)[:30], m.group(2))
    for m in re.finditer(r"""\sstyle\s*=\s*(["'])(.*?)\1""", t, re.S):
        yield ("style=\"\"", m.group(2))
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", t, re.S | re.I):
        yield ("<script%s>" % m.group(1)[:30], m.group(2))


def design_problems(text, is_html=False, strict=False):
    """Design standard. Fails on purple/violet/magenta hues, gradients with more than two hues (or any colored gradient),
    and (strict, for shared assets) any non-palette color. Diagram fills (fill, stroke, svg) are not checked."""
    probs = []
    for where, css in _css_contexts(text, is_html):
        decls = L.DECL_RE.finditer(css)
        for d in decls:
            prop, val = d.group(1), d.group(2)
            if L.SKIP_PROPS.match(prop) or not L.CSS_PROPS.match(prop):
                continue
            for g in L.GRAD_RE.finditer(val):
                cols = [c.group(0) for c in L.COLOR_RE.finditer(g.group(0))] + [c.group(0) for c in L.NAMED_RE.finditer(g.group(0))]
                rgbs = [L.parse_color(c) for c in cols]
                rgbs = [r for r in rgbs if r and r[3] > 0.05]
                fams = {L.family(r) for r in rgbs}
                hues = {round(L.hsl(r)[0] / 30) for r in rgbs if L.family(r) != "neutral"}
                if len(hues) > 1 or len(rgbs) > 2 or (fams - {"neutral"} and len({c.lower() for c in cols}) > 1):
                    probs.append("%s %s: gradient with several colors: %s" % (where, prop, g.group(0)[:70]))
            for c in list(L.COLOR_RE.finditer(val)) + list(L.NAMED_RE.finditer(val)):
                rgb = L.parse_color(c.group(0))
                if not rgb or rgb[3] <= 0.05:
                    continue
                if L.is_purple(rgb):
                    probs.append("%s %s: purple/violet color %s" % (where, prop, c.group(0)))
                elif L.family(rgb) != "neutral":
                    hx = "#%02x%02x%02x" % tuple(int(round(x)) for x in rgb[:3])
                    if hx not in L.PALETTE_HEX and (strict or is_html):
                        probs.append("%s %s: color %s is not in the palette (use var(--sh-accent) or a status color)" % (where, prop, c.group(0)))
        if where.startswith("<script") or where == "file":
            for m in L.JS_COLOR_PROP.finditer(css):
                rgb = L.parse_color(m.group(3))
                if rgb and not L.is_neutral(rgb) and "#%02x%02x%02x" % tuple(int(x) for x in rgb[:3]) not in L.PALETTE_HEX:
                    probs.append("%s: script color %s" % (where, m.group(0)[:50]))
    return sorted(set(probs))


def lint_paths(paths, strict=True):
    out = []
    for p in paths:
        files = [p] if os.path.isfile(p) else [os.path.join(r, f) for r, _, fs in os.walk(p) for f in fs]
        for f in files:
            if not f.endswith((".css", ".js", ".html")):
                continue
            t = open(f, encoding="utf-8").read()
            for pr in design_problems(t, is_html=f.endswith(".html"), strict=strict):
                out.append((f, pr))
    return out


def lint_config():
    out = []
    for code, s in L.CFG["subjects"].items():
        for k in ("accent", "soft"):
            rgb = L.parse_color(s.get(k, ""))
            if rgb and s[k].lower() not in L.PALETTE_HEX:
                out.append(("tools/sh_config.json", "subject %s %s %s is not the site accent (one accent color for every subject)" % (code, k, s[k])))
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("links", "design"):
        sys.exit(__doc__)
    if sys.argv[1] == "links":
        probs = check_links(sys.argv[2], set(sys.argv[3:]) or None)
        for p in probs:
            print("BROKEN %s | %s | %s | %s" % p)
    else:
        probs = lint_paths(sys.argv[2:], strict=False) + lint_config()
        for p in probs:
            print("DESIGN %s: %s" % p)
    print("%d problems" % len(probs))
    sys.exit(1 if probs else 0)
