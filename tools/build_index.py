#!/usr/bin/env python3
"""Build the plaintext hub home page from manifest.json.

Reads  <repo>/manifest.json  (array of {grade, subject, title, path, test_date, added_by})
Writes <src>/index.html      (plaintext; publish.sh encrypts it into the repo)
Default src dir: ../study-hub-src next to the repo, or $STUDY_HUB_SRC.
"""
import html, json, os, sys
from collections import OrderedDict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("STUDY_HUB_SRC", os.path.join(os.path.dirname(REPO), "study-hub-src"))
SUBJECTS = {"SS": ("Social Studies", "🌎"), "WW": ("Wordly Wise", "📚"), "Math": ("Math", "➗"),
            "Sci": ("Science", "🔬"), "LA": ("Language Arts", "✏️"), "Grammar": ("Grammar", "📝")}
COLORS = ["#2f6fed", "#16a34a", "#f97316", "#9333ea", "#0891b2", "#db2777"]
REQ = ("grade", "subject", "title", "path")

def main():
    items = json.load(open(os.path.join(REPO, "manifest.json")))
    errs = []
    for i, it in enumerate(items):
        for k in REQ:
            if not it.get(k):
                errs.append(f"entry {i}: missing {k}")
        p = it.get("path", "")
        if p and not os.path.exists(os.path.join(SRC, p.rstrip("/"), "index.html")) and not os.path.exists(os.path.join(SRC, p)):
            errs.append(f"entry {i}: no plaintext page at {os.path.join(SRC, p)}")
        for k, v in it.items():
            if isinstance(v, str) and "\u2014" in v:
                errs.append(f"entry {i}: em dash in {k}")
    if errs:
        sys.exit("manifest problems:\n  " + "\n  ".join(errs))
    tree = OrderedDict()
    for it in sorted(items, key=lambda x: (x["grade"], x["subject"], x.get("test_date") or "", x["title"])):
        tree.setdefault(it["grade"], OrderedDict()).setdefault(it["subject"], []).append(it)
    e = html.escape
    parts = []
    for gi, (g, subs) in enumerate(tree.items()):
        gnum = g[1:] if g.startswith("G") else g
        parts.append(f'<section class="grade"><h2>Grade {e(gnum)}</h2>')
        for si, (s, lst) in enumerate(subs.items()):
            name, emo = SUBJECTS.get(s, (s, "⭐"))
            col = COLORS[(gi * 3 + si) % len(COLORS)]
            parts.append(f'<div class="subj" style="--c:{col}"><h3><span class="emo">{emo}</span> {e(name)}</h3><ul>')
            for it in lst:
                date = f'<span class="date">Test: {e(it["test_date"])}</span>' if it.get("test_date") else ""
                parts.append(f'<li><a href="{e(it["path"])}">{e(it["title"])}</a> {date}</li>')
            parts.append("</ul></div>")
        parts.append("</section>")
    page = TEMPLATE.replace("__BODY__", "\n".join(parts) or "<p>No pages yet.</p>")
    os.makedirs(SRC, exist_ok=True)
    open(os.path.join(SRC, "index.html"), "w").write(page)
    print(f"wrote {os.path.join(SRC, 'index.html')} with {len(items)} entries")

TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Krishiv's Study Hub</title><style>
body{margin:0;font:18px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:#26214a;background:#f4f8ff}
header{background:linear-gradient(90deg,#1e3a8a,#2f6fed,#06b6d4);color:#fff;padding:22px 18px;text-align:center}
header h1{margin:0;font-size:32px}header p{margin:4px 0 0;opacity:.9}
main{max-width:900px;margin:0 auto;padding:18px 14px 50px}
.grade h2{font-size:26px;margin:18px 0 10px}
.subj{background:#fff;border-radius:20px;border-top:7px solid var(--c);box-shadow:0 10px 26px rgba(30,40,90,.08);padding:14px 18px;margin-bottom:14px}
.subj h3{margin:0 0 6px;color:var(--c);font-size:22px}
ul{margin:0;padding-left:20px}li{margin:8px 0}
a{color:#1d4ed8;font-weight:700;text-decoration:none}a:hover{text-decoration:underline}
.date{display:inline-block;font-size:14px;background:#fff7d6;border:1px solid #fde68a;border-radius:999px;padding:1px 10px;margin-left:6px;color:#854d0e}
.emo{font-family:"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif}
</style></head><body><header><h1><span class="emo">🚀</span> Krishiv's Study Hub</h1><p>Pick a subject and let's learn!</p></header>
<main>
__BODY__
</main></body></html>
"""

if __name__ == "__main__":
    main()
