#!/usr/bin/env python3
"""CI tests for rule F2 (tools/sh_f2.py, the validate.py static part, tools/check_f2.py on a local fixture folder).
Made-up pages and score files only. No secrets, no network."""
import datetime as dt, io, json, os, shutil, subprocess, sys, tempfile
from contextlib import redirect_stdout
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_f2 as F

n = 0


def check(name, cond):
    global n
    n += 1
    if not cond:
        sys.exit("FAIL: " + name)
    print("ok   " + name)


def page(quizzes, log=True, logger=True):
    d = {"grade": "G3", "subject": "XX", "id": "T", "log": log, "quizzes": quizzes}
    return ('<html><script type="application/json" id="sh-data">%s</script>%s</html>'
            % (json.dumps(d), "<script>var SHLog={}</script>" if logger else ""))


def quiz(kind="mock", nq=20, mode=None, **kw):
    q = {"kind": kind, "section": "mock", "questions": [{"q": "Q%d" % i} for i in range(nq)]}
    if mode:
        q["mode"] = mode
    q.update(kw)
    return q


# --- full mock definition ---
check("mock, mode test, 20 questions, logging page counts as a full mock", F.full_logging_mocks(page([quiz(mode="test")])) == 1)
check("mock with no mode defaults to test", F.full_logging_mocks(page([quiz()])) == 1)
check("game is not a mock", F.full_logging_mocks(page([quiz("game", mode="practice")])) == 0)
check("mock in practice mode is not a full mock", F.full_logging_mocks(page([quiz(mode="practice")])) == 0)
check("6-question mini mock is not full", F.full_logging_mocks(page([quiz(nq=6)])) == 0)
check("short mock marked full: true counts", F.full_logging_mocks(page([quiz(nq=6, full=True)])) == 1)
check("long mock marked full: false does not count", F.full_logging_mocks(page([quiz(full=False)])) == 0)
check("log false: no predicted score can be recorded", F.full_logging_mocks(page([quiz()], log=False)) == 0)
check("no SHLog logger on the page: does not count", F.full_logging_mocks(page([quiz()], logger=False)) == 0)
check("older page without sh-data is unknown (None)", F.full_logging_mocks("<html>old page</html>") is None)

# --- static part (validate.py --src) ---
def items(*rows):
    return [{"grade": "G3", "subject": s, "path": "G3/%s/%s/" % (s, p), "test_date": d, "title": "t", "added_by": "Coach"}
            for s, p, d in rows]


def static(rows, pages):
    return F.static_problems(items(*rows), lambda p: pages.get(p))


e, w = static([("XX", "A", "2026-11-05")], {"G3/XX/A/": page([quiz()])})
check("test on the cutoff day with a full logging mock passes", e == [] and w == [])
e, w = static([("XX", "A", "2026-11-05")], {"G3/XX/A/": page([quiz("game")])})
check("test on the cutoff day with no mock fails F2", len(e) == 1 and e[0].startswith("F2:") and "G3/XX/A/" in e[0])
e, w = static([("XX", "A", "2026-11-04")], {"G3/XX/A/": page([quiz("game")])})
check("test the day before the cutoff (2026-11-04) is exempt", e == [] and w == [])
e, w = static([("XX", "A", "")], {"G3/XX/A/": page([quiz("game")])})
check("entry with no test date is not a real test", e == [] and w == [])
e, w = static([("YY", "Q1", "2026-11-19"), ("YY", "Mock", "2026-11-19")],
              {"G3/YY/Q1/": page([quiz("game"), quiz(nq=6)]), "G3/YY/Mock/": page([quiz()])})
check("chapter quiz without a full mock warns when another page of the same test has one",
      e == [] and len(w) == 1 and "G3/YY/Q1/" in w[0] and "covered by G3/YY/Mock/" in w[0])
e, w = static([("YY", "Q1", "2026-11-19"), ("YY", "Q2", "2026-11-12")],
              {"G3/YY/Q1/": page([quiz("game")]), "G3/YY/Q2/": page([quiz()])})
check("a mock for a different test date does not cover the test", len(e) == 1 and "2026-11-19" in e[0])
e, w = static([("ZZ", "Old", "2026-11-19")], {"G3/ZZ/Old/": "<html>older page</html>"})
check("a test with only older pages (no sh-data) warns, not fails", e == [] and len(w) == 1)
e, w = static([("ZZ", "Old", "2026-11-19"), ("ZZ", "New", "2026-11-19")],
              {"G3/ZZ/Old/": "<html>older page</html>", "G3/ZZ/New/": page([quiz("game")])})
check("older page plus a new page with no full mock fails", len(e) == 1)
e, w = static([("XX", "A", "2026-11-05")], {})
check("a page that is not staged is left to R3/R10", e == [] and w == [])

# --- timing ---
day = "2026-11-05"
start = F.test_start(day)
check("test start is 08:00 America/Los_Angeles (16:00 UTC in November)",
      start.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M") == "2026-11-05 16:00")
now = start + dt.timedelta(days=1)
check("mock 25h before is PASS", F.judge(day, [start - dt.timedelta(hours=25)], now) == "PASS")
check("mock exactly 24h before is PASS", F.judge(day, [start - dt.timedelta(hours=24)], now) == "PASS")
check("mock 23h before is LATE", F.judge(day, [start - dt.timedelta(hours=23)], now) == "LATE")
check("no mock after the deadline is MISSING", F.judge(day, [], now) == "MISSING")
check("no mock yet, deadline ahead is PENDING", F.judge(day, [], start - dt.timedelta(hours=30)) == "PENDING")
check("no mock, inside the last 24h is MISSING", F.judge(day, [], start - dt.timedelta(hours=2)) == "MISSING")
t = F.attempt_time("G3/XX/A/2026-11-03T171500-mock-ab12.json", {"clientTime": "2026-11-03T17:15:00.000-08:00"})
check("clientTime with offset is read", t == dt.datetime(2026, 11, 4, 1, 15, tzinfo=dt.timezone.utc))
t = F.attempt_time("G3/XX/A/2026-11-03T171500-mock.json", {})
check("file name stamp is read as Pacific time", t.astimezone(dt.timezone.utc).hour == 1)
check("kind from file name, with and without rand4",
      F.name_kind("a/2026-11-03T171500-mock-ab12.json") == "mock" and F.name_kind("a/2026-11-03T171500-game.json") == "game")
full = {"kind": "mock", "score": 15, "total": 20}
check("first-round mock with score and full total counts", F.is_full_mock_log("x-mock.json", full))
check("retry round does not count", not F.is_full_mock_log("x", dict(full, attempt_kind="retry", round=2)))
check("first round 1 counts", F.is_full_mock_log("x", dict(full, attempt_kind="first", round=1)))
check("mini mock (total 6) does not count", not F.is_full_mock_log("x", dict(full, total=6)))
check("game does not count", not F.is_full_mock_log("x", dict(full, kind="game")))
check("no score does not count", not F.is_full_mock_log("x", {"kind": "mock", "total": 20}))

# --- check_f2.py on a fixture folder ---
import check_f2 as C
tmp = tempfile.mkdtemp(prefix="f2test.")
try:
    def log(path, kind="mock", total=20, **kw):
        p = os.path.join(tmp, "scores", path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(dict({"kind": kind, "score": 12, "total": total}, **kw), open(p, "w"))
    man = items(("XX", "Pass", "2026-11-05"), ("XX", "Pass2", "2026-11-05"), ("XX", "Late", "2026-11-06"),
                ("XX", "Gone", "2026-11-07"), ("XX", "Mini", "2026-11-09"), ("XX", "Future", "2026-11-30"),
                ("XX", "Exempt", "2026-11-04"), ("XX", "NoDate", ""))
    log("G3/XX/Pass2/2026-11-03T200000-mock-aaaa.json", clientTime="2026-11-03T20:00:00.000-08:00")
    log("G3/XX/Pass2/2026-11-04T200000-mock-aaab.json", attempt_kind="retry", round=2)
    log("G3/XX/Late/2026-11-05T190000-mock-bbbb.json")
    log("G3/XX/Gone/2026-11-04T100000-game-cccc.json", kind="game")
    log("G3/XX/Gone/2026-11-07T120000-mock-cccd.json")     # after the test: does not count
    log("G3/XX/Mini/2026-11-01T100000-mock-dddd.json", total=6)
    log("G3/XX/Exempt/_provenance.json")
    os.environ["STUDY_HUB_SCORES_DIR"] = os.path.join(tmp, "scores")
    buf = io.StringIO()
    res = C.run(man, F.test_start("2026-11-10"), out=lambda s: buf.write(s + "\n"))
    txt = buf.getvalue()
    check("check_f2: shared test passes from a sibling page's mock", res["PASS"] == ["G3 XX 2026-11-05"])
    check("check_f2: mock logged 13h before is LATE", res["LATE"] == ["G3 XX 2026-11-06"])
    check("check_f2: game only, or mock after the test, is MISSING; mini mock is MISSING",
          res["MISSING"] == ["G3 XX 2026-11-07", "G3 XX 2026-11-09"])
    check("check_f2: future test with no mock is PENDING", res["PENDING"] == ["G3 XX 2026-11-30"])
    check("check_f2: exempt and undated entries are not judged", "2026-11-04" not in txt.replace("2026-11-04T", "") and "exempt (before 2026-11-05): 1" in txt)
    check("check_f2: prints the qualifying attempt path and an escalation line",
          "G3/XX/Pass2/2026-11-03T200000-mock-aaaa.json" in txt and "Basy escalates to Gilfoy" in txt)
    check("check_f2: never prints scores", "12/20" not in txt and '"score"' not in txt)
    mp = os.path.join(tmp, "manifest.json")
    json.dump(man, open(mp, "w"))
    with redirect_stdout(io.StringIO()):
        rc_strict = C.main(["--strict", "--manifest", mp, "--now", "2026-11-10T00:00:00-08:00"])
        rc_plain = C.main(["--manifest", mp, "--now", "2026-11-10T00:00:00-08:00"])
    check("check_f2 --strict exits 1 on MISSING/LATE; without --strict exits 0", rc_strict == 1 and rc_plain == 0)
    ok_man = os.path.join(tmp, "ok.json")
    json.dump(items(("XX", "Pass2", "2026-11-05")), open(ok_man, "w"))
    with redirect_stdout(io.StringIO()):
        rc_ok = C.main(["--strict", "--manifest", ok_man, "--now", "2026-11-10T00:00:00-08:00"])
    check("check_f2 --strict exits 0 when every test passes", rc_ok == 0)
    # no token, no network: a clean exit 2 with a message, run in a child with an empty HOME
    env = {k: v for k, v in os.environ.items() if k not in ("STUDY_HUB_SCORES_DIR", "STUDY_HUB_SCORES_TOKEN")}
    env["HOME"] = os.path.join(tmp, "home")
    os.makedirs(env["HOME"])
    r = subprocess.run([sys.executable, C.__file__, "--manifest", mp], env=env, capture_output=True, text=True, timeout=60)
    check("check_f2 without a token exits 2 with 'DID NOT RUN' and no traceback",
          r.returncode == 2 and "DID NOT RUN" in r.stdout and "Traceback" not in r.stderr)
finally:
    os.environ.pop("STUDY_HUB_SCORES_DIR", None)
    shutil.rmtree(tmp, ignore_errors=True)

print("all %d F2 checks passed" % n)
