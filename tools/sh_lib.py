"""Shared helpers for the Study Hub sh-2 template. Used by build_index.py, sh_page.py, sh_stage.py, validate.py."""
import html, json, os, re

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
CFG = json.load(open(os.path.join(TOOLS, "sh_config.json"), encoding="utf-8"))
VERSION = CFG["template_version"]                      # "sh-2"
MARKER_RE = re.compile(r'<meta name="study-hub-template" content="(sh-[0-9]+(?:-legacy)?)">')
CONTENT_RE = re.compile(r"^G\d+/[A-Za-z]+/[A-Za-z0-9][A-Za-z0-9._-]*/index\.html$")
HUB_RE = re.compile(r"^(index\.html|G\d+/index\.html|G\d+/[A-Za-z]+/index\.html)$")
e = html.escape


def default_src():
    return os.environ.get("STUDY_HUB_SRC", os.path.join(os.path.dirname(REPO), "study-hub-src"))


def asset(name):
    return open(os.path.join(REPO, "assets", name), encoding="utf-8").read()


def subject(code):
    s = CFG["subjects"].get(code)
    if s:
        return s
    return {"name": code, "mono": code[:2].title(), "accent": "#0066cc", "soft": "#e8f1fb"}


def grade_name(g):
    return CFG["grades"].get(g, "Grade " + g.lstrip("G"))


def short_title(t):
    """Short title for breadcrumbs and tiles: text before the first '(' ."""
    return t.split("(")[0].strip().rstrip(":").strip() or t


def vars_css(code):
    s = subject(code) if code else {"accent": "#0066cc", "soft": "#e8f1fb"}
    return ":root{--sh-accent:%s;--sh-accent-soft:%s}" % (s["accent"], s["soft"])


def head_assets(code, legacy=False):
    """Inline style blocks. publish refreshes the content of these ids from assets/ on every run."""
    out = ['<style id="sh-css">%s</style>' % asset("css/sh.css")]
    if legacy:
        out.append('<style id="sh-legacy-css">%s</style>' % asset("css/sh-legacy.css"))
    v = vars_css(code)
    if legacy:  # map the old pages' brand colors to the subject accent; keep green, red and yellow
        s = subject(code)
        v += ":root{--o:%s;--p:%s;--pink:%s;--blue:%s;--orange:%s}" % ((s["accent"],) * 5)
    out.append('<style id="sh-vars">%s</style>' % v)
    return "\n".join(out)


def crumbs(rel_path, title=None):
    """Breadcrumb for a page at rel_path (e.g. 'G3/SS/Ch1/index.html'). All links are relative."""
    parts = rel_path.split("/")[:-1]
    depth = len(parts)
    up = lambda n: "../" * n or "./"
    items = []
    if depth == 0:
        items.append('<li><span aria-current="page">Home</span></li>')
    else:
        items.append('<li><a href="%s">Home</a></li>' % up(depth))
    if depth >= 1:
        g = parts[0]
        items.append(('<li><span aria-current="page">%s</span></li>' if depth == 1 else '<li><a href="%s">%%s</a></li>' % up(depth - 1)) % e(grade_name(g)))
    if depth >= 2:
        s = subject(parts[1])["name"]
        items.append(('<li><span aria-current="page">%s</span></li>' if depth == 2 else '<li><a href="%s">%%s</a></li>' % up(depth - 2)) % e(s))
    if depth >= 3:
        items.append('<li><span aria-current="page">%s</span></li>' % e(short_title(title or parts[2])))
    return items, up(depth)


def appbar(rel_path, title=None, static=False):
    items, home = crumbs(rel_path, title)
    cls = "sh-appbar sh-appbar--static" if static else "sh-appbar"
    return ('<div class="%s" data-sh-appbar><div class="sh-appbar__in"><a class="sh-brand" href="%s">%s</a>'
            '<div class="sh-nav" role="navigation" aria-label="You are here"><ol class="sh-crumbs">%s</ol></div></div></div>') % (cls, home, e(CFG["site_title"]), "".join(items))


def segmented(tabs, label="Sections"):
    """tabs: list of (id, label). One segmented control pattern for every page."""
    b = "".join('<button type="button" role="tab" id="t-%s" aria-controls="p-%s" aria-selected="false">%s</button>' % (e(i), e(i), e(l)) for i, l in tabs)
    return '<div class="sh-tabsbar"><div class="sh-wrap"><div class="sh-seg" role="tablist" aria-label="%s" data-sh-tabs>%s</div></div></div>' % (e(label), b)


def page(rel_path, title, body, code=None, data=None, log=False, crumb_title=None):
    """Full sh-2 page skeleton. data is embedded as JSON for sh.js."""
    scripts = '<script id="sh-js">%s</script>' % asset("js/sh.js")
    if log:
        scripts = '<script id="sh-log">%s</script>\n' % asset("js/shlog.js") + scripts
    data_tag = ""
    if data is not None:
        data_tag = '<script type="application/json" id="sh-data">%s</script>' % json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="study-hub-template" content="%s">
<title>%s</title>
<meta name="theme-color" content="#f5f5f7">
%s
</head><body class="sh">
%s
<main class="sh-main">
%s
</main>
<footer class="sh-wrap"><div class="sh-foot">Study Hub. Private family study pages.</div></footer>
%s
%s
</body></html>
""" % (VERSION, e(title), head_assets(code), appbar(rel_path, crumb_title or title), body, data_tag, scripts)


# ---------- refresh and legacy wrap ----------
BLOCKS = {"sh-css": ("style", "css/sh.css"), "sh-legacy-css": ("style", "css/sh-legacy.css"),
          "sh-js": ("script", "js/sh.js"), "sh-log": ("script", "js/shlog.js"), "sh-legacy-js": ("script", "js/sh-legacy.js")}


def refresh(h, rel_path=None):
    """Replace the content of inlined design-system blocks with the current assets/ files.
    With rel_path, the subject color block (sh-vars) is also rebuilt from tools/sh_config.json."""
    for bid, (tag, name) in BLOCKS.items():
        pat = re.compile(r'(<%s id="%s">)(.*?)(</%s>)' % (tag, bid, tag), re.S)
        if pat.search(h):
            new = asset(name)
            h = pat.sub(lambda m: m.group(1) + new + m.group(3), h, count=1)
    if rel_path:
        code = rel_path.split("/")[1] if rel_path.count("/") >= 2 else None
        pat = re.compile(r'(<style id="sh-vars">)(.*?)(</style>)', re.S)
        m = pat.search(h)
        if m:
            legacy = "--o:" in m.group(2)
            new = head_assets(code, legacy=legacy).rsplit('<style id="sh-vars">', 1)[1].rsplit("</style>", 1)[0]
            h = h[:m.start(2)] + new + h[m.end(2):]
    mk = MARKER_RE.search(h)
    # Older pages get the palette applied for them. Pages from sh_page.py must pass the design check as written.
    return neutralize(h) if mk and mk.group(1).endswith("-legacy") else h


def wrap_legacy(h, rel_path, title=None):
    """Give a pre-sh-2 page the sh-2 skin and breadcrumb. Content and scripts stay the same."""
    m = MARKER_RE.search(h)
    if m:
        return refresh(h, rel_path)
    code = rel_path.split("/")[1] if rel_path.count("/") >= 2 else None
    i = h.lower().find("</head>")
    j = h.lower().find("<body")
    if i < 0 or j < 0 or i > j:
        raise ValueError("no </head> before <body> in " + rel_path)
    inject = '<meta name="study-hub-template" content="%s-legacy">\n%s\n' % (VERSION, head_assets(code, legacy=True))
    h = h[:i] + inject + h[i:]
    m = re.compile(r"<body([^>]*)>", re.I).search(h)
    attrs = m.group(1)
    if re.search(r'class\s*=\s*"', attrs):
        attrs = re.sub(r'class\s*=\s*"', 'class="sh-legacy ', attrs, count=1)
    else:
        attrs += ' class="sh-legacy"'
    bar = appbar(rel_path, title, static=True)
    h = h[:m.start()] + "<body%s>\n%s" % (attrs, bar) + h[m.end():]
    k = h.lower().rfind("</body>")
    tag = '<script id="sh-legacy-js">%s</script>\n' % asset("js/sh-legacy.js")
    h = (h[:k] + tag + h[k:]) if k >= 0 else h + tag
    return neutralize(h)


# ---------- neutral palette (design standard) ----------
# The only colors a page may use in its styles: neutrals, one accent, and the three status colors.
PALETTE = {
    "ink": "#1d1d1f", "ink2": "#515154", "ink3": "#6e6e73", "line": "#d2d2d7", "bg": "#f5f5f7", "white": "#ffffff",
    "accent": "#0066cc", "accent_soft": "#e8f1fb",
    "good": "#1d7d3f", "good_soft": "#e7f5ec", "bad": "#c9182b", "bad_soft": "#fdecee", "warn": "#9a6200", "warn_soft": "#fff5e0",
}
PALETTE_HEX = set(PALETTE.values()) | {"#fff", "#000", "#000000", "#a1a1a6", "#7f1d1d", "#14532d"}
COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|rgba?\(\s*[\d.]+%?\s*[, ]\s*[\d.]+%?\s*[, ]\s*[\d.]+%?\s*(?:[,/]\s*[\d.]+%?\s*)?\)|hsla?\([^)]*\)")
GRAD_RE = re.compile(r"(?:repeating-)?(?:linear|radial|conic)-gradient\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)")
NAMED = {"purple": "#800080", "violet": "#ee82ee", "magenta": "#ff00ff", "fuchsia": "#ff00ff", "indigo": "#4b0082",
         "orchid": "#da70d6", "plum": "#dda0dd", "lavender": "#e6e6fa", "pink": "#ffc0cb", "hotpink": "#ff69b4", "orange": "#ffa500",
         "gold": "#ffd700", "cyan": "#00ffff", "aqua": "#00ffff", "teal": "#008080", "lime": "#00ff00", "blueviolet": "#8a2be2",
         "mediumpurple": "#9370db", "darkviolet": "#9400d3", "rebeccapurple": "#663399", "deeppink": "#ff1493"}
NAMED_RE = re.compile(r"(?<![\w-])(%s)(?![\w-])" % "|".join(sorted(NAMED, key=len, reverse=True)), re.I)


def parse_color(c):
    """Return (r, g, b, a) with r, g, b in 0..255, or None."""
    import colorsys
    c = c.strip().lower()
    if c in NAMED:
        c = NAMED[c]
    if c.startswith("#"):
        x = c[1:]
        if len(x) in (3, 4):
            x = "".join(ch * 2 for ch in x)
        try:
            r, g, b = int(x[0:2], 16), int(x[2:4], 16), int(x[4:6], 16)
        except ValueError:
            return None
        return r, g, b, (int(x[6:8], 16) / 255 if len(x) == 8 else 1.0)
    nums = re.findall(r"[\d.]+%?", c)
    if c.startswith("rgb") and len(nums) >= 3:
        v = [float(n[:-1]) * 2.55 if n.endswith("%") else float(n) for n in nums[:3]]
        a = nums[3] if len(nums) > 3 else "1"
        return v[0], v[1], v[2], float(a[:-1]) / 100 if a.endswith("%") else float(a)
    if c.startswith("hsl") and len(nums) >= 3:
        hh, ss, ll = float(nums[0].rstrip("%")), float(nums[1].rstrip("%")) / 100, float(nums[2].rstrip("%")) / 100
        r, g, b = colorsys.hls_to_rgb(hh / 360, ll, ss)
        a = nums[3] if len(nums) > 3 else "1"
        return r * 255, g * 255, b * 255, float(a[:-1]) / 100 if a.endswith("%") else float(a)
    return None


def hsl(rgb):
    import colorsys
    h, l, s = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return h * 360, s, l


def is_neutral(rgb):
    h, s, l = hsl(rgb)
    return s < 0.12 or l < 0.06 or l > 0.97


def is_purple(rgb):
    """Purple, violet, magenta, and pink-violet hues that are visibly colored."""
    h, s, l = hsl(rgb)
    return 255 <= h <= 335 and s >= 0.2 and 0.08 < l < 0.96


def family(rgb):
    h, s, l = hsl(rgb)
    if is_neutral(rgb):
        return "neutral"
    if 80 <= h < 170:
        return "good"
    if h >= 345 or h < 12:
        return "bad"
    if 36 <= h < 62:
        return "warn"
    return "accent"


def map_color(c, kind="auto"):
    """Map any color to the neutral palette. kind: 'bg' (backgrounds), 'fg' (text, borders), or 'auto'."""
    rgb = parse_color(c)
    if rgb is None:
        return c
    a = rgb[3]
    fam = family(rgb)
    h, s, l = hsl(rgb)
    if fam == "neutral":
        return c
    if fam == "warn" and kind != "bg" and l >= 0.5 and l < 0.86:
        fam = "accent"     # bright yellow dots, stars, and icons become the accent; dark amber text stays a warning
    if l <= 0.22:
        out = PALETTE["ink"]
    else:
        soft = l >= 0.86 or (kind == "bg" and l >= 0.6) or (kind == "auto" and l >= 0.8)
        out = PALETTE[fam + "_soft"] if soft else PALETTE[fam]
    if a < 1:
        r, g, b = int(out[1:3], 16), int(out[3:5], 16), int(out[5:7], 16)
        return "rgba(%d,%d,%d,%s)" % (r, g, b, ("%.2f" % a).rstrip("0").rstrip("."))
    return out


def _grad(m, kind):
    """Replace a gradient with one flat palette color (its first real color stop)."""
    cols = [x.group(0) for x in COLOR_RE.finditer(m.group(0))] + [x.group(0) for x in NAMED_RE.finditer(m.group(0))]
    cols = [c for c in cols if parse_color(c) and parse_color(c)[3] > 0.05]
    if not cols:
        return m.group(0)
    hues = {family(parse_color(c)) for c in cols}
    if len(cols) <= 2 and hues <= {"neutral"}:
        return m.group(0)      # a plain neutral fade (for example a sticky bar) is fine
    first = map_color(cols[0], kind)
    return "linear-gradient(%s,%s)" % (first, first)


BG_PROPS = re.compile(r"^(background(-color|-image)?|--[\w-]*(bg|soft|light|tint|back|paper|card|panel)[\w-]*)$", re.I)
SKIP_PROPS = re.compile(r"^(fill|stroke|stop-color|flood-color|lighting-color)$", re.I)
DECL_RE = re.compile(r"(?<![\w-])(--[\w-]+|[a-zA-Z-]+)\s*:\s*([^;{}\"'`]*(?:\$\{[^}]*\}[^;{}\"'`]*)*)")
CSS_PROPS = re.compile(r"^(color|background(-color|-image)?|border(-(top|right|bottom|left))?(-color)?|outline(-color)?|box-shadow|text-shadow|"
                       r"accent-color|caret-color|text-decoration-color|column-rule-color|--[\w-]+)$", re.I)


def neutralize_css(css, js=False):
    """Rewrite colors in CSS text (or CSS inside JS strings) to the palette. Leaves fill/stroke (diagrams) alone."""
    def decl(m):
        prop, val = m.group(1), m.group(2)
        if SKIP_PROPS.match(prop) or not CSS_PROPS.match(prop):
            return m.group(0)
        if js and not prop.startswith("--") and prop.lower() not in ("color", "background", "background-color", "border", "border-color",
                                                                   "border-left", "border-top", "border-bottom", "border-right",
                                                                   "box-shadow", "outline", "text-shadow", "accent-color"):
            return m.group(0)
        kind = "bg" if BG_PROPS.match(prop) else ("auto" if prop.startswith("--") else "fg")
        v = GRAD_RE.sub(lambda g: _grad(g, kind), val)
        v = COLOR_RE.sub(lambda c: map_color(c.group(0), kind), v)
        v = NAMED_RE.sub(lambda c: map_color(c.group(0), kind), v)
        return m.group(0)[: m.start(2) - m.start(0)] + v
    return DECL_RE.sub(decl, css)


JS_COLOR_PROP = re.compile(r"""(\b(?:col|color|colour|bg|accent|tint|hue|c1|c2|fg|light|dark|soft)\s*:\s*)(["'])(#[0-9a-fA-F]{3,8})\2""")
CONFETTI_ARR = re.compile(r"""\[\s*(?:["']#[0-9a-fA-F]{3,8}["']\s*,\s*){3,}["']#[0-9a-fA-F]{3,8}["']\s*\]""")


def neutralize(h):
    """Apply the neutral palette to a page's own styles: <style> blocks, style="" attributes, and CSS or color values
    inside its scripts. Never touches the shared sh-* blocks, data: URIs, or inline <svg> diagrams."""
    keep = []

    def hold(m):
        keep.append(m.group(0))
        return "\x00%d\x00" % (len(keep) - 1)
    h = re.sub(r"data:[^\"'()\s]+", hold, h)
    h = re.sub(r'<(style|script) id="sh-[\w-]+">.*?</\1>', hold, h, flags=re.S)
    h = re.sub(r"<svg\b.*?</svg>", hold, h, flags=re.S | re.I)
    h = re.sub(r"(<style\b[^>]*>)(.*?)(</style>)", lambda m: m.group(1) + neutralize_css(m.group(2)) + m.group(3), h, flags=re.S | re.I)
    h = re.sub(r"""(\sstyle\s*=\s*)(["'])(.*?)\2""", lambda m: m.group(1) + m.group(2) + neutralize_css(m.group(3), js=True) + m.group(2), h, flags=re.S)

    def script(m):
        body = neutralize_css(m.group(2), js=True)
        body = JS_COLOR_PROP.sub(lambda c: c.group(1) + c.group(2) + map_color(c.group(3), "auto") + c.group(2), body)
        body = CONFETTI_ARR.sub(lambda c: re.sub(r"#[0-9a-fA-F]{3,8}", lambda x: map_color(x.group(0), "fg"), c.group(0)), body)
        return m.group(1) + body + m.group(3)
    h = re.sub(r"(<script\b(?![^>]*\bid=\"sh-)[^>]*>)(.*?)(</script>)", script, h, flags=re.S | re.I)
    for _ in range(3):   # nested holds (an svg inside a held block) unwind in a few passes
        h = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], h)
    return h


# ---------- tiny Markdown ----------
def md(text):
    """Small safe Markdown: paragraphs, '- ' lists, '1. ' lists, '### ' headings, **bold**, *italic*."""
    def inline(s):
        s = e(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s)
        return s
    out, lst = [], None
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l.rstrip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if all(re.match(r"^\s*[-*] ", l) for l in lines):
            out.append("<ul>" + "".join("<li>%s</li>" % inline(re.sub(r"^\s*[-*] ", "", l)) for l in lines) + "</ul>")
        elif all(re.match(r"^\s*\d+[.)] ", l) for l in lines):
            out.append("<ol>" + "".join("<li>%s</li>" % inline(re.sub(r"^\s*\d+[.)] ", "", l)) for l in lines) + "</ol>")
        elif lines[0].startswith("### "):
            out.append("<h3>%s</h3>" % inline(lines[0][4:]))
            if lines[1:]:
                out.append("<p>%s</p>" % inline(" ".join(lines[1:])))
        else:
            out.append("<p>%s</p>" % inline(" ".join(lines)))
    return '<div class="sh-prose">%s</div>' % "".join(out)


# ---------- score logger privacy (applied at publish time to every page that logs) ----------
# Privacy v3: the logger sends no free text. A missed item is its number, item id, option letters and 2 booleans;
# details keep numbers, booleans and short ids. No private-word list (plain, hashed or encoded) is on any page.
_CLEAN_RE = re.compile(r"function clean\(m\)\{m=m\|\|\{\};var o=\{\};\[[^\]]*\]\.forEach\(function\(k\)\{if\(m\[k\]!==undefined\)o\[k\]=m\[k\]\}\);(?:\s*if\(typeof o\.picked[^\n]*?)?return o\}")
_REDACT_RE = re.compile(r"function redact\(t\)\{.*?return t\}", re.S)
_CUT_RE = re.compile(r"function cut\(v\)\{[^\n]*?\}\s*")
_PRIV_RE = re.compile(r"/\*sh-privacy v\d+\*/.*?/\*sh-privacy end\*/", re.S)
_OLD_COMMENT_RE = re.compile(r"[ \t]*// Privacy:[^\n]*\n(?:[ \t]*//[^\n]*\n)*")
REDACT_ELEM_RE = re.compile(r'[ \t]*<script type="application/json" id="sh-redact">(.*?)</script>\n?', re.S)
PRIVACY_VERSION = "/*sh-privacy v3*/"
STAGE_MARK = ".sh-staged"
_PUT_OLD = "body:JSON.stringify({message:item.message,content:item.content})"
_PUT_NEW = "body:JSON.stringify({message:item.message,content:item.content,committer:BOT,author:BOT})"
_REC_OLD = ("content:b64(redact(JSON.stringify(payload,null,1))+'\\n')", "content:b64(JSON.stringify(payload,null,1)+'\\n')")
BOT_IDENTITY = {"name": "Study Hub Bot", "email": "study-hub-bot@users.noreply.github.com"}


def redact_terms(blocklist=""):
    """Lowercase private terms: every alternative of STUDY_HUB_BLOCKLIST plus kid_first_name from tools/sh_config.json.
    Used by the plaintext scans (R7, the error-log scan), never written to a page."""
    terms = set()
    for t in re.split(r"\|", blocklist or ""):
        t = re.sub(r"\\b|[()^$?*+\[\]{}\\]", "", t).strip().lower()
        t = re.sub(r"\s+", " ", t)
        if len(t) >= 2:
            terms.add(t)
    if CFG.get("kid_first_name"):
        terms.add(CFG["kid_first_name"].strip().lower())
    return sorted(terms)


def _privacy_block():
    return _PRIV_RE.search(asset("js/shlog.js")).group(0)


def patch_logger(h, blocklist="", rel_path=""):
    """Bring every inline copy of SHLog up to privacy v3 (no free text, bot commit identity) and remove the old
    sh-redact hash list. blocklist and rel_path are unused (kept for callers)."""
    if "var SHLog=" not in h:
        return h
    start = h.find("var SHLog=")
    end = h.find("return {init:init", start)
    if end < 0:
        return h
    body = h[start:end]
    block = _privacy_block()
    if _PRIV_RE.search(body):
        body = _PRIV_RE.sub(lambda m: block, body, count=1)
    else:   # older inline copies: drop their cut/clean/redact (and comments), insert the current block
        body = _OLD_COMMENT_RE.sub("", body)
        body = _CUT_RE.sub("", body, count=1)
        body = _REDACT_RE.sub("", body, count=1)
        body = _CLEAN_RE.sub("", body, count=1)
        body = body.replace("function record(r){", block.strip() + "\n  function record(r){", 1)
    body = body.replace(*_REC_OLD)
    body = body.replace("details:r.details||{}", "details:facts(r.details)")
    body = body.replace(_PUT_OLD, _PUT_NEW)
    h = h[:start] + body + h[end:]
    return REDACT_ELEM_RE.sub("", h)


def logger_problems(h, blocklist=""):
    """Empty list when the page's SHLog copy has privacy v3: clean() and facts() on everything sent, no redact code,
    bot commit identity, and no sh-redact element."""
    if "var SHLog=" not in h:
        return []
    out = []
    if h.count("var SHLog=") != 1:
        out.append("more than one SHLog copy")
    i = h.find("var SHLog=")
    body = h[i:h.find("return {init:init", i)]
    need = [PRIVACY_VERSION, "function clean(m)", "function facts(d,depth)", "missed:(r.missed||[]).map(clean)",
            "details:facts(r.details)", _PUT_NEW, _REC_OLD[1]]
    if not all(x in body for x in need) or "redact(" in body or "function sha256(" in body:
        out.append("logger does not have the current privacy code (sh-privacy v3: no free text, bot identity)")
    if REDACT_ELEM_RE.search(h):
        out.append("page still has an sh-redact element (privacy v3 has no private-word list)")
    return out


def logger_ok(h, blocklist=""):
    return not logger_problems(h, blocklist)


def encoded_forms(term):
    """Strings that show a private term hidden as base64 (any byte offset) or hex. Used by validate R7."""
    import base64
    out = set()
    for v in {term, term.lower(), term.upper(), term.capitalize()}:
        b = v.encode("utf-8")
        out.add(b.hex()); out.add(b.hex().upper())
        for pad in range(3):
            enc = base64.b64encode(b"\0" * pad + b).decode().rstrip("=")
            lead = {0: 0, 1: 2, 2: 3}[pad]          # chars that depend on the padding bytes
            tail = (len(b) + pad) % 3             # last char depends on bytes after the term
            frag = enc[lead: len(enc) - (1 if tail else 0)]
            if len(frag) >= 6:
                out.add(frag)
            for url in (frag.replace("+", "-").replace("/", "_"),):
                if len(url) >= 6:
                    out.add(url)
    return out
