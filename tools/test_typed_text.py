#!/usr/bin/env python3
"""Tests for rule R13 (tools/sh_typed.py): only SpellingBee pages may send typed text or spelling trap keys.
CI: fake pages built around the real assets/js/shlog.js. Box: --stage DIR also checks every real staged page.
Usage: python3 tools/test_typed_text.py [--stage DIR]"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L
import sh_typed as T

LOG = L.asset("js/shlog.js")
bad = 0


def page(js, log=LOG):
    return ('<!doctype html><html><head></head><body><main></main>\n<script id="sh-log">%s</script>\n'
            '<script>%s</script></body></html>' % (log, js))


def case(name, rel, html, want_fail):
    global bad
    d = tempfile.mkdtemp()
    p = os.path.join(d, "index.html")
    open(p, "w", encoding="utf-8").write(html)
    pr = T.page_problems(p, rel)
    ok = bool(pr) == want_fail
    bad += not ok
    print("%s %s: %s" % ("ok  " if ok else "FAIL", name, "; ".join(pr) if pr else "passes"))


GOOD_JS = "SHLog.record({kind:'game',score:1,total:2,missed:[{n:1,id:'q1-1',blank:false,typed:!q.options}]});"
case("normal WW page (typed is a boolean)", "G3/WW/Fake/index.html", page(GOOD_JS), False)
case("WW page turns on the exception", "G3/WW/Fake/index.html", page("SHLog.allow({spelling:true});" + GOOD_JS), True)
case("SS page turns it on with !0", "G3/SS/Fake/index.html", page("SHLog.allow({ids:[],spelling:!0});"), True)
case("WW page puts the typed string in typed", "G3/WW/Fake/index.html",
     page("SHLog.record({kind:'game',score:0,total:1,missed:[{n:1,id:'q1-1',typed:String(val).slice(0,40)}]});"), True)
case("Noetic page puts a quoted string in typed", "G3/Noetic/Fake/index.html", page("var m={n:1,typed:'eliet'};"), True)
case("WW page sends a spelling trap key", "G3/WW/Fake/index.html", page("var m={n:1,id:'q1-1',trap:'vowel_swap',typed:true};"), True)
case("WW page uses the SpellTrap classifier", "G3/WW/Fake/index.html", page("var t=SpellTrap.classify(a,b);"), True)
case("hub page turns on the exception", "G3/index.html", page("SHLog.allow({spelling:true});"), True)
ungated = LOG.replace("cfg.subject==='SpellingBee'", "true")
case("WW page whose logger copy lost the subject gate", "G3/WW/Fake/index.html", page(GOOD_JS, ungated), True)
case("SpellingBee page uses the exception (allowed)", "G3/SpellingBee/Fake/index.html",
     page("SHLog.allow({spelling:true});var m={n:1,typed:'eliet',trap:'vowel_swap'};var t=SpellTrap.classify(a,b);"), False)
case("WW page says spelling:false (allowed)", "G3/WW/Fake/index.html", page("var o={spelling:false};" + GOOD_JS), False)

# asset gate (CI)
pr = T.asset_problems(L.REPO)
bad += bool(pr)
print("%s shlog.js keeps the subject gate: %s" % ("FAIL" if pr else "ok  ", "; ".join(pr) or "passes"))
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "assets", "js"))
open(os.path.join(d, "assets", "js", "shlog.js"), "w").write(ungated)
pr = T.asset_problems(d)
bad += not pr
print("%s shlog.js without the gate fails: %s" % ("ok  " if pr else "FAIL", "; ".join(pr) or "passes (wrong)"))

# real staged pages (box)
if "--stage" in sys.argv:
    st = sys.argv[sys.argv.index("--stage") + 1]
    n = nlog = 0
    for root, dirs, fs in os.walk(st):
        for f in fs:
            if f != "index.html":
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, st).replace(os.sep, "/")
            h = open(p, encoding="utf-8").read()
            n += 1
            nlog += "var SHLog=" in h and L.CONTENT_RE.match(rel) is not None
            pr = T.page_problems(p, rel)
            bad += bool(pr)
            if pr:
                print("FAIL real page %s: %s" % (rel, "; ".join(pr)))
    print("real pages: %d staged pages (%d content pages with a logger) checked" % (n, nlog))
print("typed-text rule tests: %d failed" % bad)
sys.exit(1 if bad else 0)
