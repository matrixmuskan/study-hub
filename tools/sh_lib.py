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
          "sh-js": ("script", "js/sh.js"), "sh-log": ("script", "js/shlog.js")}


def refresh(h):
    """Replace the content of inlined design-system blocks with the current assets/ files."""
    for bid, (tag, name) in BLOCKS.items():
        pat = re.compile(r'(<%s id="%s">)(.*?)(</%s>)' % (tag, bid, tag), re.S)
        if pat.search(h):
            new = asset(name)
            h = pat.sub(lambda m: m.group(1) + new + m.group(3), h, count=1)
    return h


def wrap_legacy(h, rel_path, title=None):
    """Give a pre-sh-2 page the sh-2 skin and breadcrumb. Content and scripts stay the same."""
    m = MARKER_RE.search(h)
    if m:
        return refresh(h)
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
