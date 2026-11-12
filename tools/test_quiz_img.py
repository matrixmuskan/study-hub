#!/usr/bin/env python3
"""Test of the per-question picture ("img" on a quiz question) in tools/sh_page.py and assets/js/sh.js, plus rule R16.

Builds throwaway pages with sh_page.build() (made-up questions, two tiny generated PNGs, no token, nothing is sent) and:
  build: 'img' is inlined once as a data: URI (the base64 is in the page exactly once, in sh-data); a missing 'alt',
    a non-object 'img' and an unknown 'img' field stop the build.
  renderer (headless Chromium): the picture of question 1 is inside question 1, directly above its text and options,
    and decodes; a question without 'img' has no picture; after 'Mark my test' with question 1 wrong, Retry keeps the
    picture on question 1 (same element, still decoded) and question 2 is locked.
  R16 (tools/sh_checks.py qimg_problems, qimg_report): an old-style page (image blocks 'Question 1 ...' above the quiz)
    is found and is a WARNING; the new page passes; a captioned picture in a section without a quiz passes; a page that
    has 'img' on a question AND a leftover question picture block above the quiz FAILS.
  browsercheck: tools/sh_browsercheck.py on the new page reports every question picture as loaded (exit 0).
Browser: Playwright's Chromium, else /usr/bin/google-chrome. Usage: python3 tools/test_quiz_img.py
"""
import base64, json, os, struct, subprocess, sys, tempfile, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L
import sh_page as SP
import sh_checks as C

HERE = os.path.dirname(os.path.abspath(__file__))
bad = 0


def check(name, ok, info=""):
    global bad
    bad += not ok
    print("%s %s%s" % ("ok  " if ok else "FAIL", name, (": " + info) if info and not ok else ""))


def png(path, rgb, w=40, h=24):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def content(d, old_style=False):
    qs = [{"q": "Question 1. Which shape is the mirror image?", "options": ["A", "B", "C", "D", "E"], "answer": 2,
           "img": {"src": "q1.png", "alt": "Picture for question 1", "caption": "Question 1 (3 points)"}},
          {"q": "Question 2. How many dots in all?", "options": ["3", "4", "5", "6", "7"], "answer": 1}]
    blocks = [{"type": "quiz", "kind": "mock", "mode": "test", "full": False, "questions": qs}]
    if old_style:
        qs[0].pop("img")
        blocks.insert(0, {"type": "image", "src": "q1.png", "alt": "Picture for question 1", "caption": "Question 1 (3 points)"})
    return {"grade": "G3", "subject": sorted(L.CFG["subjects"])[0], "id": "QimgFixture", "title": "Question picture fixture",
            "added_by": "test", "log": False,
            "sections": [{"id": "learn", "label": "Learn", "blocks": [
                             {"type": "image", "src": "q2.png", "alt": "Example", "caption": "Question 5 (4 points)"}]},
                         {"id": "mastery", "label": "Mastery", "blocks": blocks}]}


def build(d, c):
    SP.MEDIA.update(bytes=0, files=0)
    return SP.build(json.loads(json.dumps(c)), d)


def fails(d, c):
    try:
        build(d, c)
    except SystemExit as ex:
        return str(ex)
    return ""


def main():
    d = tempfile.mkdtemp(prefix="sh-qimg-")
    png(os.path.join(d, "q1.png"), (200, 30, 30))
    png(os.path.join(d, "q2.png"), (30, 30, 200))
    b64 = base64.b64encode(open(os.path.join(d, "q1.png"), "rb").read()).decode()

    rel, h, _ = build(d, content(d))
    check("build: question picture inlined exactly once (in sh-data)", h.count(b64) == 1, "count %d" % h.count(b64))
    data = json.loads(h.split('id="sh-data">', 1)[1].split("</script>", 1)[0].replace("<\\/", "</"))
    im = data["quizzes"][0]["questions"][0].get("img") or {}
    check("build: img is {src: data URI, alt, caption}", im.get("src", "").startswith("data:image/png;base64,")
          and im.get("alt") == "Picture for question 1" and im.get("caption") == "Question 1 (3 points)", str(im)[:120])
    c = content(d); c["sections"][1]["blocks"][0]["questions"][0]["img"].pop("alt")
    check("build: img without alt fails", "needs 'alt'" in fails(d, c))
    c = content(d); c["sections"][1]["blocks"][0]["questions"][0]["img"] = "q1.png"
    check("build: img as a string fails", "must be an object" in fails(d, c))
    c = content(d); c["sections"][1]["blocks"][0]["questions"][0]["img"]["width"] = 3
    check("build: unknown img field fails", "unknown 'img' field" in fails(d, c))
    c = content(d); c["sections"][1]["blocks"][0]["questions"][0]["img"]["src"] = "missing.png"
    check("build: missing img file fails", "not found" in fails(d, c))

    # R16
    _, old, _ = build(d, content(d, old_style=True))
    po, pn = C.qimg_problems(old), C.qimg_problems(h)
    check("R16: old layout (picture block above the quiz) fails", len(po) == 1 and "mastery" in po[0], str(po))
    check("R16: new layout passes (captioned picture in a section without a quiz is fine)", pn == [], str(pn))
    fo, wo = C.qimg_report(old)
    check("R16 report: older layout only (no 'img' anywhere) is a WARNING, not a FAIL", fo == [] and len(wo) == 1, str((fo, wo)))
    fn, wn = C.qimg_report(h)
    check("R16 report: new layout has no FAIL and no WARNING", fn == [] and wn == [], str((fn, wn)))
    mixed = content(d)
    mixed["sections"][1]["blocks"].insert(0, {"type": "image", "src": "q2.png", "alt": "Picture for question 2",
                                              "caption": "Question 2 (3 points)"})
    _, mx, _ = build(d, mixed)
    fm, wm = C.qimg_report(mx)
    check("R16 report: a page with 'img' AND a leftover question picture block above the quiz FAILS",
          len(fm) == 1 and "mixes" in fm[0] and wm == [], str((fm, wm)))

    site = os.path.join(d, "site")
    page_path = os.path.join(site, rel)
    os.makedirs(os.path.dirname(page_path))
    open(page_path, "w", encoding="utf-8").write(h)

    # renderer
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except Exception:
            br = pw.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = br.new_page(viewport={"width": 390, "height": 844})
        pg.goto("file://" + page_path)
        pg.wait_for_timeout(400)
        st = pg.evaluate("""() => { const q = document.getElementById('quiz-0-q0'), q2 = document.getElementById('quiz-0-q1');
          const im = q && q.querySelector(':scope > .sh-q__fig img'), t = q && q.querySelector(':scope > .sh-q__text'),
                o = q && q.querySelector(':scope > .sh-opts');
          const fol = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
          const prev = im && im.closest('figure').previousElementSibling;
          return {img: !!im, decoded: !!(im && im.complete && im.naturalWidth > 0), alt: im && im.alt,
                  cap: im && (im.closest('figure').querySelector('figcaption') || {}).textContent,
                  aboveText: fol(im, t), aboveOpts: fol(im, o), afterHeader: !!(prev && prev.classList.contains('sh-q__n')),
                  nextIsText: !!(im && im.closest('figure').nextElementSibling === t),
                  q2img: !!(q2 && q2.querySelector('img')), figs: document.querySelectorAll('#quiz-0 img').length}; }""")
        check("render: question 1 picture is inside question 1", st["img"], str(st))
        check("render: picture sits directly above the question text and options",
              st["aboveText"] and st["aboveOpts"] and st["nextIsText"] and st["afterHeader"], str(st))
        check("render: picture decodes, alt and caption shown", st["decoded"] and st["alt"] == "Picture for question 1"
              and st["cap"] == "Question 1 (3 points)", str(st))
        check("render: question 2 (no img) has no picture, quiz has 1 picture", not st["q2img"] and st["figs"] == 1, str(st))
        pg.evaluate("() => { window.__im = document.querySelector('#quiz-0-q0 .sh-q__fig img'); }")
        pg.evaluate("() => document.querySelector('#quiz-0 .sh-opt[data-q=\"0\"][data-k=\"0\"]').click()")   # wrong
        pg.evaluate("() => document.querySelector('#quiz-0 .sh-opt[data-q=\"1\"][data-k=\"1\"]').click()")   # right
        pg.evaluate("() => document.querySelector('#quiz-0 [data-finish]').click()")
        pg.wait_for_timeout(200)
        ok = pg.evaluate("() => { const b = document.querySelector('#quiz-0 [data-retry]'); if (!b) return false; b.click(); return true; }")
        pg.wait_for_timeout(300)
        rt = pg.evaluate("""() => { const q = document.getElementById('quiz-0-q0'), q2 = document.getElementById('quiz-0-q1');
          const im = q.querySelector(':scope > .sh-q__fig img'), t = q.querySelector(':scope > .sh-q__text');
          return {img: !!im, same: im === window.__im, decoded: !!(im && im.complete && im.naturalWidth > 0),
                  above: !!(im && t && (im.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING)),
                  retry: q.classList.contains('is-retry'), q2locked: q2.classList.contains('is-locked'),
                  open: !q.querySelector('.sh-opt').disabled, imgs: document.querySelectorAll('#quiz-0 img').length}; }""")
        check("retry: Retry button shown and clicked", ok)
        check("retry: question 1 keeps its picture above its text (same element, decoded)",
              rt["img"] and rt["same"] and rt["decoded"] and rt["above"], str(rt))
        check("retry: question 1 is open again, question 2 is locked, still 1 picture", rt["retry"] and rt["open"]
              and rt["q2locked"] and rt["imgs"] == 1, str(rt))
        if os.environ.get("SH_QIMG_SHOT"):
            pg.screenshot(path=os.environ["SH_QIMG_SHOT"])
        br.close()

    # browsercheck
    r = subprocess.run([sys.executable, os.path.join(HERE, "sh_browsercheck.py"), "--root", site, "--pages", rel,
                        "--json", os.path.join(d, "bc.json")], capture_output=True, text=True, timeout=300)
    rows = json.load(open(os.path.join(d, "bc.json"))) if os.path.exists(os.path.join(d, "bc.json")) else []
    q = [x for x in rows if x["type"] == "qimg"]
    check("browsercheck: exit 0 and the question picture is checked as loaded",
          r.returncode == 0 and len(q) == 1 and q[0]["status"] == "ok", (r.stdout + r.stderr)[-400:] + str(q))
    print("%s: %d failed" % ("test_quiz_img", bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
