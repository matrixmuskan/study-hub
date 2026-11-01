#!/usr/bin/env python3
"""Box-only headless test: the real logger on real pages logs the score plus each missed item with its trap and value,
and no private term. Stages the mirror (like publish.sh), opens 3 pages in headless Chromium with fetch stubbed (nothing
is sent), plays a quiz on each with the page's own code, and checks the queued file.

  Noetic Ch1-Quiz (sh-2, typed answers): types a known wrong answer (90) on question 1.
  WW Lesson9 (sh-2, options): picks a wrong option on question 1 of the first quiz.
  SS Final1 (older page): runs the page's own logRound() with a trap pick and a wrong pick.

Usage: (set -a; . ~/.study-hub.env; set +a; python3 tools/test_logger_pages.py)   Prints facts only, never terms.
"""
import base64, json, os, re, subprocess, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L

SRC = os.environ.get("STUDY_HUB_SRC") or os.path.join(os.path.dirname(L.REPO), "study-hub-src")
STUB = """(() => { window.__puts = []; const f = window.fetch;
  window.fetch = (url, o) => { if (o && o.method === 'PUT') { window.__puts.push(JSON.parse(o.body)); return Promise.resolve({status: 201}); }
    return Promise.resolve({status: 404}); }; })();"""


def terms():
    return L.redact_terms(os.environ.get("STUDY_HUB_BLOCKLIST", ""))


def payloads(page):
    page.wait_for_timeout(600)
    page.evaluate("() => window.SHLog && SHLog.flush()")
    page.wait_for_timeout(600)
    out = []
    for b in page.evaluate("() => window.__puts"):
        out.append((b, json.loads(base64.b64decode(b["content"]).decode("utf-8"))))
    return out


def main():
    from playwright.sync_api import sync_playwright
    if not terms():
        sys.exit("STUDY_HUB_BLOCKLIST is empty (source ~/.study-hub.env)")
    st = tempfile.mkdtemp(prefix="sh-logtest.")
    os.chmod(st, 0o700)
    bad = 0
    try:
        subprocess.run([sys.executable, os.path.join(L.TOOLS, "sh_stage.py"), SRC, st], check=True, stdout=subprocess.DEVNULL)
        rx = re.compile(r"(?<![a-z])(?:%s)(?![a-z])" % "|".join(re.escape(t) for t in terms()), re.I)
        with sync_playwright() as pw:
            try:
                br = pw.chromium.launch()
            except Exception:
                br = pw.chromium.launch(executable_path="/usr/bin/google-chrome")
            runs = []
            # Noetic: practice quiz with typed answers; Q1 gets the known wrong answer 90, the rest get 0
            p = br.new_page(); p.add_init_script(STUB)
            p.goto("file://" + os.path.join(st, "G3/Noetic/Ch1-Quiz/index.html"))
            p.wait_for_selector('[data-sh-quiz="0"] .sh-input', state="attached")
            p.evaluate("""() => { const r = document.querySelector('[data-sh-quiz="0"]');
                r.querySelectorAll('.sh-input').forEach((inp, i) => { inp.value = i === 0 ? '90' : '0';
                  const b = r.querySelector('[data-check="' + inp.getAttribute('data-q') + '"]'); if (b) b.click(); });
                const f = r.querySelector('[data-finish]'); if (f) f.click(); }""")
            runs.append(("Noetic Ch1-Quiz", payloads(p), lambda m: m.get("id") == "q1-1" and m.get("value") == "90" and m.get("trap") and m.get("blank") is False))
            # WW Lesson9: first quiz with options; wrong option on Q1, right on the rest
            p = br.new_page(); p.add_init_script(STUB)
            p.goto("file://" + os.path.join(st, "G3/WW/Lesson9/index.html"))
            p.wait_for_selector('[data-sh-quiz="0"] .sh-opt', state="attached")
            p.evaluate("""() => { const r = document.querySelector('[data-sh-quiz="0"]');
                const d = JSON.parse(document.getElementById('sh-data').textContent).quizzes[0].questions;
                d.forEach((q, i) => { const k = i === 0 ? (q.answer + 1) % q.options.length : q.answer;
                  r.querySelector('.sh-opt[data-q="' + i + '"][data-k="' + k + '"]').click(); });
                const f = r.querySelector('[data-finish]'); if (f) f.click(); }""")
            runs.append(("WW Lesson9", payloads(p), lambda m: m.get("n") == 1 and m.get("picked") and m.get("trap") and m.get("blank") is False))
            # SS Final1: the page's own round logger with a trap pick (Q1) and another wrong pick (Q2)
            p = br.new_page(); p.add_init_script(STUB)
            p.goto("file://" + os.path.join(st, "G3/SS/Final1-Ch1-2-8/index.html"))
            p.wait_for_timeout(800)
            p.evaluate("""() => { G = {mode: 'all', round: 1, queue: [0, 1, 2], rm: [{idx: 0, k: D.QUIZ[0].trap},
                {idx: 1, k: (D.QUIZ[1].a + 1) % D.QUIZ[1].o.length}], rc: [2], logged: null}; logRound(); }""")
            runs.append(("SS Final1", payloads(p), lambda m: m.get("n") == 1 and m.get("trap") == "trap" and m.get("picked")))
            br.close()
        for name, pls, want in runs:
            if len(pls) != 1:
                print("FAIL %-16s %d files queued (expected 1)" % (name, len(pls))); bad += 1; continue
            body, pay = pls[0]
            text = json.dumps(pay)
            leaks = len(rx.findall(text))
            ok = want(pay["missed"][0]) and leaks == 0 and body.get("committer", {}).get("name") == "Study Hub Bot" and pay.get("build")
            bad += 0 if ok else 1
            print("%s %-16s score %s/%s, build %s, missed[0] %s, %d missed, private terms %d"
                  % ("ok  " if ok else "FAIL", name, pay["score"], pay["total"], pay.get("build"), json.dumps(pay["missed"][0]), len(pay["missed"]), leaks))
    finally:
        shutil.rmtree(st, ignore_errors=True)
    print("logger page test: %d pages, %d failed" % (3, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
