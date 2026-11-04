#!/usr/bin/env python3
"""Headless test of the retry loop in the shared quiz runtime (assets/js/sh.js + assets/js/shlog.js).

Builds a throwaway sh-2 page from tools/fixtures/retry5.json (made-up questions, fake token, fetch stubbed: nothing is
sent) and plays it in headless Chromium:
  mock quiz, 5 questions: round 1 with 2 wrong, round 2 with 1 wrong, round 3 with 0 wrong. Expects logged rounds 1, 2,
  3 (attempt_kind first, retry, retry; kind stays 'mock'), each round scored on its own questions (3/5, 1/2, 1/1), the
  same missed ids and v4 trap keys as before, typed a boolean, the questions already right grayed out, disabled,
  inert, aria-disabled and skipped by Tab, the message 'All correct in 3 rounds', no new device storage keys, a reload
  mid-loop that starts over, and 'Start over' back to round 1.
  practice quiz (game, answers shown at once): 1 wrong, then a retry round with only that question.
Also: rule R13 and rule R14 on the fixture page, and R14 payload cases (older score files without the fields pass).
Browser: Playwright's Chromium, else /usr/bin/google-chrome. Usage: python3 tools/test_retry_loop.py
"""
import base64, json, os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L
import sh_typed as T
import sh_rounds as RD

HERE = os.path.dirname(os.path.abspath(__file__))
STUB = """(() => { window.__puts = []; window.fetch = (url, o) => { if (o && o.method === 'PUT') { window.__puts.push(JSON.parse(o.body));
  return Promise.resolve({status: 201}); } return Promise.resolve({status: 404}); }; })();"""
bad = 0


def check(name, ok, info=""):
    global bad
    bad += not ok
    print("%s %s%s" % ("ok  " if ok else "FAIL", name, (": " + info) if info and not ok else ""))


def build(d):
    data = json.load(open(os.path.join(HERE, "fixtures", "retry5.json"), encoding="utf-8"))
    body = ('<section class="sh-wrap"><h2>Mock</h2><div id="quiz-0" data-sh-quiz="0"></div></section>'
            '<section class="sh-wrap"><h2>Practice</h2><div id="quiz-1" data-sh-quiz="1"></div></section>'
            '<p><a id="after" href="#quiz-0">Back to the top</a></p>')
    rel = "G3/WW/RetryFixture/index.html"
    h = L.page(rel, "Retry loop fixture", body, code="WW", data=data, log=True)
    p = os.path.join(d, "index.html")
    open(p, "w", encoding="utf-8").write(h)
    return p, rel


def payloads(page):
    page.wait_for_timeout(300)
    page.evaluate("() => window.SHLog && SHLog.flush()")
    page.wait_for_timeout(300)
    return [json.loads(base64.b64decode(b["content"]).decode("utf-8")) for b in page.evaluate("() => window.__puts")]


PICK = """([qz, i, k]) => document.querySelector('#quiz-' + qz + ' .sh-opt[data-q="' + i + '"][data-k="' + k + '"]').click()"""
TYPE = """([i, v]) => { const x = document.querySelector('#quiz-0 .sh-input[data-q="' + i + '"]'); x.value = v; }"""
CLICK = """(sel) => { const b = document.querySelector(sel); if (!b) return false; b.click(); return true; }"""
LOCKS = """(qz) => Array.from(document.querySelectorAll('#quiz-' + qz + ' .sh-q')).map(q => ({
  locked: q.classList.contains('is-locked'), aria: q.getAttribute('aria-disabled'), inert: q.hasAttribute('inert') && q.inert === true,
  ctl: Array.from(q.querySelectorAll('button,input')).map(c => ({dis: c.disabled, ti: c.tabIndex})),
  fb: q.querySelector('.sh-fb').hidden, picked: q.querySelectorAll('.is-picked,.is-right,.is-wrong').length,
  val: (q.querySelector('.sh-input') || {}).value || '' }))"""
RESULT = """(qz) => { const t = document.querySelector('#quiz-' + qz + ' [data-result]'); return t ? t.textContent : null; }"""


def tab_walk(page, n=40):
    """Press Tab n times from the top of the page; return the data-q of each focused quiz control in quiz 0."""
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); }")
    out = []
    for _ in range(n):
        page.keyboard.press("Tab")
        out.append(page.evaluate("""() => { const a = document.activeElement; if (!a || !a.closest('#quiz-0')) return null;
            const q = a.closest('.sh-q'); return q ? +q.getAttribute('data-qi') : 'other'; }"""))
    return out


def round_fields(p):
    return (p.get("kind"), p.get("attempt_kind"), p.get("round"), p.get("score"), p.get("total"),
            [m.get("id") for m in p.get("missed", [])])


def main():
    from playwright.sync_api import sync_playwright
    d = tempfile.mkdtemp(prefix="sh-retry.")
    try:
        path, rel = build(d)
        check("R13 passes on the fixture page", not T.page_problems(path, rel), "; ".join(T.page_problems(path, rel)))
        pr = RD.logger_problems(path, "WW")
        check("R14 passes on the fixture page's logger copy", not pr, "; ".join(pr))
        url = "file://" + path
        with sync_playwright() as pw:
            try:
                br = pw.chromium.launch()
            except Exception:
                br = pw.chromium.launch(executable_path="/usr/bin/google-chrome")
            pg = br.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.add_init_script(STUB)
            pg.goto(url)
            pg.wait_for_selector("#quiz-0 .sh-opt", state="attached")

            # ---- round 1: 2 wrong (Q2 picks the listed trap A, Q5 types the listed wrong 9) ----
            for i, k in ((0, 1), (1, 0), (2, 0), (3, 2)):
                pg.evaluate(PICK, [0, i, k])
            pg.evaluate(TYPE, [4, "9"])
            pg.evaluate(CLICK, "#quiz-0 [data-finish]")
            pl = payloads(pg)
            check("round 1 logs one attempt", len(pl) == 1, str(len(pl)))
            r1 = pl[0]
            check("round 1: kind mock, attempt_kind first, round 1, score 3/5, missed q1-2 q1-5",
                  round_fields(r1) == ("mock", "first", 1, 3, 5, ["q1-2", "q1-5"]), str(round_fields(r1)))
            m = {x["id"]: x for x in r1["missed"]}
            check("round 1: v4 trap keys and values (q1-2 picked A trap opposite; q1-5 value 9 trap off-by-one)",
                  m["q1-2"].get("picked") == "A" and m["q1-2"].get("trap") == "opposite"
                  and m["q1-5"].get("value") == "9" and m["q1-5"].get("trap") == "off-by-one", json.dumps(r1["missed"]))
            check("round 1: typed is a boolean in every missed item", all(isinstance(x.get("typed"), bool) for x in r1["missed"]))
            check("round 1 passes R14", not RD.payload_problems(r1), "; ".join(RD.payload_problems(r1)))
            check("round 1 shows Retry and Start over",
                  pg.evaluate("() => !!document.querySelector('#quiz-0 [data-retry]') && !!document.querySelector('#quiz-0 [data-again]')"))

            # ---- retry -> round 2 ----
            pg.evaluate(CLICK, "#quiz-0 [data-retry]")
            st = pg.evaluate(LOCKS, 0)
            locked = [i for i, q in enumerate(st) if q["locked"]]
            check("round 2: the 3 right questions are locked (Q1, Q3, Q4)", locked == [0, 2, 3], str(locked))
            check("round 2: locked questions are aria-disabled, inert, disabled and tabindex -1",
                  all(st[i]["aria"] == "true" and st[i]["inert"] and all(c["dis"] and c["ti"] == -1 for c in st[i]["ctl"]) for i in locked))
            check("round 2: locked questions keep their feedback visible (grayed, not hidden)", all(not st[i]["fb"] for i in locked))
            check("round 2: only the 2 missed questions are open, fresh (no pick, no answer shown, empty input)",
                  all(not st[i]["locked"] and st[i]["fb"] and st[i]["picked"] == 0 and st[i]["val"] == "" and not any(c["dis"] for c in st[i]["ctl"]) for i in (1, 4)))
            walk = tab_walk(pg)
            hit = sorted({x for x in walk if isinstance(x, int)})
            check("round 2: Tab reaches only the open questions (Q2, Q5)", hit == [1, 4], str(hit))
            # a click on a locked option does nothing
            pg.evaluate("() => document.querySelector('#quiz-0 .sh-opt[data-q=\"0\"][data-k=\"0\"]').click()")
            check("round 2: a click on a locked question changes nothing", pg.evaluate(LOCKS, 0)[0]["picked"] == st[0]["picked"])

            # reload mid-loop = start over, no new device storage keys
            keys = pg.evaluate("() => ({local: Object.keys(localStorage), session: Object.keys(sessionStorage)})")
            check("no new storage keys (only the logger queue shlog_queue; no sessionStorage)",
                  set(keys["local"]) <= {"shlog_queue"} and not keys["session"], json.dumps(keys))
            pg2 = br.new_page(); pg2.add_init_script(STUB); pg2.goto(url)
            pg2.wait_for_selector("#quiz-0 .sh-opt", state="attached")
            st2 = pg2.evaluate(LOCKS, 0)
            check("reload mid-loop starts over (round 1, nothing locked, nothing picked)",
                  not any(q["locked"] or q["picked"] for q in st2) and pg2.evaluate("() => document.querySelector('#quiz-0 [data-finish]').textContent") == "Mark my test")
            pg2.close()

            # ---- round 2: 1 wrong (Q2 again), Q5 right ----
            pg.evaluate(PICK, [0, 1, 2])
            pg.evaluate(TYPE, [4, "12"])
            pg.evaluate(CLICK, "#quiz-0 [data-finish]")
            pl = payloads(pg)
            check("round 2 logs its own attempt", len(pl) == 2, str(len(pl)))
            r2 = pl[-1]
            check("round 2: kind mock, attempt_kind retry, round 2, score 1/2, missed q1-2",
                  round_fields(r2) == ("mock", "retry", 2, 1, 2, ["q1-2"]), str(round_fields(r2)))
            check("round 2: trap key for the wrong pick (opposite, from the question)", r2["missed"][0].get("trap") == "opposite" and r2["missed"][0].get("picked") == "C", json.dumps(r2["missed"]))
            check("round 2 passes R14", not RD.payload_problems(r2))
            pg.evaluate(CLICK, "#quiz-0 [data-retry]")
            st = pg.evaluate(LOCKS, 0)
            check("round 3: Q5 is now locked too; only Q2 is open", [i for i, q in enumerate(st) if not q["locked"]] == [1])

            # ---- round 3: 0 wrong ----
            pg.evaluate(PICK, [0, 1, 1])
            pg.evaluate(CLICK, "#quiz-0 [data-finish]")
            pl = payloads(pg)
            r3 = pl[-1]
            check("round 3: kind mock, attempt_kind retry, round 3, score 1/1, nothing missed",
                  len(pl) == 3 and round_fields(r3) == ("mock", "retry", 3, 1, 1, []), str(round_fields(r3)))
            check("logged rounds are 1, 2, 3", [p.get("round") for p in pl] == [1, 2, 3])
            res = pg.evaluate(RESULT, 0) or ""
            check("message 'All correct in 3 rounds'", "All correct in 3 rounds" in res, res)
            check("no Retry button when all are right; Start over is there",
                  pg.evaluate("() => !document.querySelector('#quiz-0 [data-retry]') && !!document.querySelector('#quiz-0 [data-again]')"))

            # ---- Start over: full reset to round 1 ----
            pg.evaluate(CLICK, "#quiz-0 [data-again]")
            st = pg.evaluate(LOCKS, 0)
            check("Start over: nothing locked, nothing picked, all enabled",
                  not any(q["locked"] or q["picked"] or q["aria"] for q in st) and all(not c["dis"] for q in st for c in q["ctl"]))
            for i, k in ((0, 1), (1, 1), (2, 0), (3, 2)):
                pg.evaluate(PICK, [0, i, k])
            pg.evaluate(TYPE, [4, "12"])
            pg.evaluate(CLICK, "#quiz-0 [data-finish]")
            pl = payloads(pg)
            check("Start over: next attempt is round 1 again (attempt_kind first), 5/5, logged once",
                  len(pl) == 4 and round_fields(pl[-1]) == ("mock", "first", 1, 5, 5, []), str([round_fields(p) for p in pl[3:]]))
            res = pg.evaluate(RESULT, 0) or ""
            check("all right in round 1 says 'All correct in 1 round'", "All correct in 1 round" in res and "rounds" not in res, res)

            # ---- practice (game) quiz: answers shown at once, retry the wrong one ----
            pg.evaluate(PICK, [1, 0, 0])
            pg.evaluate(PICK, [1, 1, 0])   # wrong
            pl = payloads(pg)
            g1 = pl[-1]
            check("game round 1: kind game, first, round 1, 1/2, missed q2-2 trap off-by-one",
                  round_fields(g1) == ("game", "first", 1, 1, 2, ["q2-2"]) and g1["missed"][0].get("trap") == "off-by-one", str(round_fields(g1)))
            pg.evaluate(CLICK, "#quiz-1 [data-retry]")
            st = pg.evaluate(LOCKS, 1)
            check("game round 2: Q1 locked, Q2 open", st[0]["locked"] and not st[1]["locked"] and st[1]["picked"] == 0)
            pg.evaluate(PICK, [1, 1, 1])
            pl = payloads(pg)
            check("game round 2: kind game, retry, round 2, 1/1", round_fields(pl[-1]) == ("game", "retry", 2, 1, 1, []), str(round_fields(pl[-1])))
            res = pg.evaluate(RESULT, 1) or ""
            check("game: message 'All correct in 2 rounds'", "All correct in 2 rounds" in res, res)
            check("all logged attempts pass R14 and are made as Study Hub Bot",
                  all(not RD.payload_problems(p) for p in pl)
                  and all(b.get("committer", {}).get("name") == "Study Hub Bot" for b in pg.evaluate("() => window.__puts")))
            check("no script errors", not errs, "; ".join(errs[:3]))
            br.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # ---- R14 payload rules ----
    old = {"v": 2, "subject": "WW", "kind": "mock", "score": 1, "total": 2, "missed": [{"n": 1, "id": "q1-1", "blank": False, "typed": False}]}
    check("R14: an older score file without the new fields passes", not RD.payload_problems(old))
    for rec in RD.BAD:
        p = dict(old, **{k: rec[k] for k in ("attempt_kind", "round") if k in rec})
        check("R14: refuses %s" % json.dumps({k: rec[k] for k in ("attempt_kind", "round") if k in rec}), bool(RD.payload_problems(p)))
    check("R14: refuses a typed string on a WW score file",
          bool(RD.payload_problems(dict(old, missed=[{"n": 1, "typed": "word"}]))))
    check("R14: a SpellingBee score file may carry typed text", not RD.payload_problems(dict(old, subject="SpellingBee", missed=[{"n": 1, "typed": "word"}])))
    print("retry loop tests: %d failed" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
