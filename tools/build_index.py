#!/usr/bin/env python3
"""Build the plaintext hub pages (sh-2 design) from manifest.json.

Reads  <repo>/manifest.json  (array of {grade, subject, title, path, test_date, added_by})
Writes <src>/index.html             home
       <src>/G<n>/index.html        grade page
       <src>/G<n>/<Subject>/index.html  subject page
All are plaintext; publish.sh encrypts them into the repo.
Default src dir: ../study-hub-src next to the repo, or $STUDY_HUB_SRC.
"""
import json, os, re, sys
from collections import OrderedDict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L

e = L.e
REQ = ("grade", "subject", "title", "path")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_manifest(src):
    items = json.load(open(os.path.join(L.REPO, "manifest.json"), encoding="utf-8"))
    errs = []
    for i, it in enumerate(items):
        for k in REQ:
            if not it.get(k):
                errs.append(f"entry {i}: missing {k}")
        p = it.get("path", "")
        if p and not os.path.exists(os.path.join(src, p.rstrip("/"), "index.html")):
            errs.append(f"entry {i}: no plaintext page at {os.path.join(src, p)}")
        if it.get("test_date") and not DATE_RE.match(it["test_date"]):
            errs.append(f"entry {i}: test_date must be YYYY-MM-DD or empty")
        for k, v in it.items():
            if isinstance(v, str) and "\u2014" in v:
                errs.append(f"entry {i}: em dash in {k}")
    if errs:
        sys.exit("manifest problems:\n  " + "\n  ".join(errs))
    return items


def nice_date(d):
    if not d:
        return ""
    import datetime
    x = datetime.date.fromisoformat(d)
    return x.strftime("%a, %b ") + str(x.day)


def row(it, base, show_subject=False):
    s = L.subject(it["subject"])
    sub = L.short_title(it["title"])
    rest = it["title"][len(sub):].strip().strip("()").strip()
    chip = f'<span class="sh-chip">Test {e(nice_date(it["test_date"]))}</span>' if it.get("test_date") else ""
    lead = f'<span class="sh-mono sh-mono--sm" style="--sh-accent:{s["accent"]};--sh-accent-soft:{s["soft"]}">{e(s["mono"])}</span>' if show_subject else ""
    subline = (e(s["name"]) + (" &middot; " if rest else "") if show_subject else "") + e(rest)
    return (f'<li><a class="sh-row sh-reveal" href="{e(base + it["path"])}" data-date="{e(it.get("test_date") or "")}">{lead}'
            f'<div class="sh-row__main"><div class="sh-row__title">{e(sub)}</div>'
            f'{"<div class=sh-row__sub>" + subline + "</div>" if subline else ""}</div>{chip}</a></li>')


def subject_tiles(g, subs, base):
    out = []
    for code, lst in subs.items():
        s = L.subject(code)
        dates = sorted(x["test_date"] for x in lst if x.get("test_date"))
        n = len(lst)
        out.append(f'<a class="sh-tile sh-reveal" href="{e(base + g + "/" + code + "/")}" style="--sh-accent:{s["accent"]};--sh-accent-soft:{s["soft"]}">'
                   f'<span class="sh-mono">{e(s["mono"])}</span><span class="sh-tile__title">{e(s["name"])}</span>'
                   f'<span class="sh-tile__text">{n} {"page" if n == 1 else "pages"}</span>'
                   f'<span class="sh-tile__foot">Open</span></a>')
    return '<div class="sh-grid">' + "".join(out) + "</div>"


def soon_list(items, base):
    dated = sorted([x for x in items if x.get("test_date")], key=lambda x: x["test_date"])
    return ('<ul class="sh-list sh-hide-past" id="soon">' + "".join(row(x, base, True) for x in dated) + "</ul>"
            '<p class="sh-empty" hidden data-sh-empty>No tests coming up. Nice.</p>')


def hero(eyebrow, title, lead, mono=None):
    m = f'<span class="sh-mono sh-mono--sm">{e(mono)}</span>' if mono else ""
    return (f'<header class="sh-wrap sh-hero"><p class="sh-eyebrow">{m}{e(eyebrow)}</p>'
            f'<h1>{e(title)}</h1><p class="sh-lead">{e(lead)}</p></header>')


def panels(tabs):
    """tabs: list of (id, label, html)."""
    seg = L.segmented([(i, l) for i, l, _ in tabs])
    body = "".join(f'<section class="sh-panel sh-wrap" id="p-{i}" role="tabpanel" aria-labelledby="t-{i}">{h}</section>' for i, l, h in tabs)
    return seg + body


def main():
    src = L.default_src()
    items = load_manifest(src)
    tree = OrderedDict()
    for it in sorted(items, key=lambda x: (x["grade"], x["subject"], x.get("test_date") or "9999", x["title"])):
        tree.setdefault(it["grade"], OrderedDict()).setdefault(it["subject"], []).append(it)
    os.makedirs(src, exist_ok=True)
    kid = L.kid_first_name(required=not os.environ.get("CI"))   # fail closed on the box
    written = []

    # Home
    subj_html = ""
    for g, subs in tree.items():
        subj_html += (f'<div class="sh-section"><div class="sh-grade-head"><h2>{e(L.grade_name(g))}</h2><a href="{e(g)}/">See all</a></div>'
                      + subject_tiles(g, subs, "") + "</div>")
    all_html = ""
    for g, subs in tree.items():
        for code, lst in subs.items():
            all_html += f'<div class="sh-section"><h3>{e(L.grade_name(g))} &middot; {e(L.subject(code)["name"])}</h3><ul class="sh-list">' + "".join(row(x, "") for x in lst) + "</ul></div>"
    body = hero(f"{kid}'s Study Hub" if kid else "Study Hub", "What will we learn today?",
                "Pick a subject. Learn the ideas, practice, then try a mock test.")
    body += panels([("subjects", "Subjects", subj_html or '<p class="sh-empty">No pages yet.</p>'),
                    ("soon", "Coming up", '<div class="sh-section">' + soon_list(items, "") + "</div>"),
                    ("all", "All pages", all_html)])
    open(os.path.join(src, "index.html"), "w", encoding="utf-8").write(L.page("index.html", L.CFG["site_title"], body))
    written.append("index.html")

    for g, subs in tree.items():
        gi = [x for x in items if x["grade"] == g]
        body = hero("Study Hub", L.grade_name(g), "Choose a subject.")
        body += panels([("subjects", "Subjects", '<div class="sh-section">' + subject_tiles(g, subs, "../") + "</div>"),
                        ("soon", "Coming up", '<div class="sh-section">' + soon_list(gi, "../") + "</div>")])
        os.makedirs(os.path.join(src, g), exist_ok=True)
        open(os.path.join(src, g, "index.html"), "w", encoding="utf-8").write(L.page(f"{g}/index.html", L.grade_name(g), body))
        written.append(f"{g}/index.html")
        for code, lst in subs.items():
            s = L.subject(code)
            n = len(lst)
            lid = "list"
            seg = ('<div class="sh-tabsbar"><div class="sh-wrap"><div class="sh-seg" role="group" aria-label="Show" data-sh-filter="%s">'
                   '<button type="button" data-f="all" aria-selected="true">All</button>'
                   '<button type="button" data-f="soon" aria-selected="false">Coming up</button>'
                   '<button type="button" data-f="past" aria-selected="false">Done</button>'
                   '<button type="button" data-f="none" aria-selected="false">Any time</button></div></div></div>') % lid
            body = hero(L.grade_name(g), s["name"], f"{n} {'page' if n == 1 else 'pages'}. Open one to learn, practice, and test yourself.", s["mono"])
            body += seg + (f'<section class="sh-wrap sh-section"><ul class="sh-list" id="{lid}">' + "".join(row(x, "../../") for x in lst)
                           + '</ul><p class="sh-empty" hidden>Nothing here.</p></section>')
            os.makedirs(os.path.join(src, g, code), exist_ok=True)
            open(os.path.join(src, g, code, "index.html"), "w", encoding="utf-8").write(L.page(f"{g}/{code}/index.html", s["name"], body, code=code))
            written.append(f"{g}/{code}/index.html")
    print(f"wrote {len(written)} hub pages into {src} from {len(items)} manifest entries")


if __name__ == "__main__":
    main()
