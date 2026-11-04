#!/usr/bin/env python3
"""CI tests for rule F2 (tools/sh_f2.py, the validate.py static part, tools/check_f2.py on a local fixture folder).
Made-up pages and score files only. No secrets, no network."""
import datetime as dt, io, json, os, shutil, subprocess, sys, tempfile
from contextlib import redirect_stderr, redirect_stdout
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

# --- timing (coach duty: page and prediction ready 24 hours before) ---
day = "2026-11-05"
start = F.test_start(day)
check("test start is 08:00 America/Los_Angeles (16:00 UTC in November)",
      start.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M") == "2026-11-05 16:00")
now = start + dt.timedelta(days=1)
check("ready 25h before is PASS", F.judge(day, [start - dt.timedelta(hours=25)], now) == "PASS")
check("ready exactly 24h before is PASS", F.judge(day, [start - dt.timedelta(hours=24)], now) == "PASS")
check("ready 23h before is LATE", F.judge(day, [start - dt.timedelta(hours=23)], now) == "LATE")
check("not ready after the deadline is MISSING", F.judge(day, [], now) == "MISSING")
check("not ready yet, deadline ahead is PENDING", F.judge(day, [], start - dt.timedelta(hours=30)) == "PENDING")
check("not ready, inside the last 24h is MISSING", F.judge(day, [], start - dt.timedelta(hours=2)) == "MISSING")
t = F.attempt_time("G3/XX/A/2026-11-03T171500-mock-ab12.json", {"clientTime": "2026-11-03T17:15:00.000-08:00"})
check("clientTime with offset is read", t == dt.datetime(2026, 11, 4, 1, 15, tzinfo=dt.timezone.utc))
t = F.attempt_time("G3/XX/A/2026-11-03T171500-mock.json", {})
check("file name stamp is read as Pacific time", t.astimezone(dt.timezone.utc).hour == 1)
check("kind from file name, with and without rand4",
      F.name_kind("a/2026-11-03T171500-mock-ab12.json") == "mock" and F.name_kind("a/2026-11-03T171500-game.json") == "game")
full = {"kind": "mock", "score": 15, "total": 20}
check("attempt (INFO): first-round mock with score and full total counts", F.is_full_mock_log("x-mock.json", full))
check("retry round does not count", not F.is_full_mock_log("x", dict(full, attempt_kind="retry", round=2)))
check("first round 1 counts", F.is_full_mock_log("x", dict(full, attempt_kind="first", round=1)))
check("mini mock (total 6) does not count", not F.is_full_mock_log("x", dict(full, total=6)))
check("game does not count", not F.is_full_mock_log("x", dict(full, kind="game")))
check("no score does not count", not F.is_full_mock_log("x", {"kind": "mock", "total": 20}))

# --- prediction (coach duty) ---
check("prediction {total, of} is read", F.prediction_value({"total": 16, "of": 20}) == (16, 20))
check("prediction {score, total} is read", F.prediction_value({"score": 9, "total": 10}) == (9, 10))
check("prediction nested under any key, with any text key, is read (no key name is hard-coded)",
      F.prediction_value({"kind": "prediction", "pred_x": {"total": 27, "of": 32, "renamed_text": "t"}}) == (27, 32))
check("prediction with no numbers is not read", F.prediction_value({"kind": "prediction", "note": "about 15"}) is None)
check("prediction above the total is not read", F.prediction_value({"total": 25, "of": 20}) is None)
check("boolean is not a number", F.prediction_value({"total": True, "of": 20}) is None)
check("prediction record: kind from the file name", F.is_prediction_record("G3/XX/A/2026-11-03T232708-prediction.json",
                                                                          {"p": {"total": 5, "of": 10}}))
check("prediction record: a mock attempt is not a prediction", not F.is_prediction_record("x", {"kind": "mock", "score": 5, "total": 10}))
check("page metadata prediction on the full mock quiz", F.page_prediction(page([quiz(prediction={"total": 15, "of": 20})])))
check("page metadata prediction in sh-data", F.page_prediction(page([quiz()]).replace('"log": true', '"log": true, "prediction": {"total": 15, "of": 20}')))
check("page metadata prediction on a mini mock only does not count", not F.page_prediction(page([quiz(nq=6, prediction={"total": 5, "of": 6})])))
check("build history stamps are read as Pacific time",
      F.build_times(["G3/XX/_builds/20261101T112818-Lesson9.json", "G3/XX/A/x.json"]) ==
      {"G3/XX/Lesson9/": [dt.datetime(2026, 11, 1, 11, 28, 18, tzinfo=F._tz())]})

# --- check_f2.py on a fixture folder ---
import check_f2 as C
tmp = tempfile.mkdtemp(prefix="f2test.")
try:
    def put(path, obj):
        p = os.path.join(tmp, "scores", path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(obj, open(p, "w"))

    def log(path, kind="mock", total=20, **kw):
        put(path, dict({"kind": kind, "score": 12, "total": total}, **kw))

    def pred(path, created, **kw):
        put(path, dict({"kind": "prediction", "predicted_score": {"total": 14, "of": 20, "any_text_key": "x"},
                        "created_at": created}, **kw))

    rows = [("XX", "Pass", "2026-11-05"), ("XX", "Pass2", "2026-11-05"), ("XX", "Late", "2026-11-06"),
            ("XX", "NoPred", "2026-11-07"), ("XX", "Meta", "2026-11-08"), ("XX", "Mini", "2026-11-09"),
            ("XX", "LatePage", "2026-11-12"), ("XX", "EarlyBuild", "2026-11-13"), ("XX", "Future", "2026-11-30"),
            ("XX", "Exempt", "2026-11-04"), ("XX", "NoDate", "")]
    man = items(*rows)
    built = {"Pass": "2026-11-01T10:00:00-07:00", "Pass2": "2026-11-01T10:00:00-07:00", "Late": "2026-11-01T10:00:00-07:00",
             "NoPred": "2026-11-01T10:00:00-07:00", "Meta": "2026-11-06T09:00:00-08:00", "Mini": "2026-11-01T10:00:00-07:00",
             "LatePage": "2026-11-11T10:00:00-08:00", "EarlyBuild": "2026-11-12T09:00:00-08:00",
             "Future": "2026-11-20T10:00:00-08:00"}
    for it in man:
        lesson = it["path"].split("/")[2]
        if lesson in built:
            it["built_at"] = built[lesson]
    pages = {"G3/XX/%s/" % k: page([quiz()]) for k in ("Pass2", "Late", "NoPred", "LatePage", "EarlyBuild", "Future")}
    pages["G3/XX/Pass/"] = page([quiz("game")])
    pages["G3/XX/Meta/"] = page([quiz(prediction={"total": 14, "of": 20})])
    pages["G3/XX/Mini/"] = page([quiz(nq=6)])
    pred("G3/XX/Pass2/2026-11-03T200000-prediction.json", "2026-11-03T20:00:00-08:00")
    pred("G3/XX/Late/2026-11-05T190000-prediction.json", "2026-11-05T19:00:00-08:00")      # 13h before the test
    log("G3/XX/Late/2026-11-05T200000-mock-bbbb.json")                                       # the child took it
    log("G3/XX/NoPred/2026-11-05T100000-mock-cccc.json")                                     # attempt, but no prediction
    pred("G3/XX/NoPred/2026-11-07T120000-prediction.json", "2026-11-07T12:00:00-08:00")    # after the test: no
    put("G3/XX/NoPred/2026-11-04T120000-prediction.json", {"kind": "prediction", "note": "no numbers"})
    pred("G3/XX/Mini/2026-11-01T100000-prediction.json", "2026-11-01T10:00:00-07:00")      # mini mock page only
    pred("G3/XX/LatePage/2026-11-01T100000-prediction.json", "2026-11-01T10:00:00-07:00")
    put("G3/XX/_builds/20261111T090000-LatePage.json", {"page": "G3/XX/LatePage/"})          # page first built 23h before
    put("G3/XX/_builds/20261101T090000-EarlyBuild.json", {"page": "G3/XX/EarlyBuild/"})      # first build early ...
    put("G3/XX/_builds/20261112T090000-EarlyBuild.json", {"page": "G3/XX/EarlyBuild/"})      # ... a later rebuild is ok
    pred("G3/XX/EarlyBuild/2026-11-02T100000-prediction.json", "2026-11-02T10:00:00-08:00")
    put("G3/XX/Exempt/_provenance.json", {})
    os.environ["STUDY_HUB_SCORES_DIR"] = os.path.join(tmp, "scores")
    buf = io.StringIO()
    res = C.run(man, F.test_start("2026-11-14"), out=lambda s: buf.write(s + "\n"), page_html=lambda p: pages.get(p))
    txt = buf.getvalue()
    check("check_f2: full mock page + prediction record 24h+ before is PASS (sibling page without a mock is fine)",
          "G3 XX 2026-11-05" in res["PASS"])
    check("check_f2: PASS with no attempt is attempted: no (INFO), not a failure",
          res["attempted"]["G3 XX 2026-11-05"] == "no" and "INFO     G3 XX 2026-11-05 attempted: no" in txt
          and "compare the real result with the prediction" in txt)
    check("check_f2: prediction 13h before is LATE; the attempt is INFO attempted: yes",
          res["LATE"][:1] == ["G3 XX 2026-11-06"] and res["attempted"]["G3 XX 2026-11-06"] == "yes")
    check("check_f2: a child attempt with no prediction is still MISSING (coach duty)",
          "G3 XX 2026-11-07" in res["MISSING"] and res["attempted"]["G3 XX 2026-11-07"] == "yes")
    check("check_f2: prediction in the page metadata counts (page built 2 days before)", "G3 XX 2026-11-08" in res["PASS"])
    check("check_f2: only a mini mock page is MISSING, even with a prediction", "G3 XX 2026-11-09" in res["MISSING"])
    check("check_f2: page first published 23h before is LATE, even with an early prediction", "G3 XX 2026-11-12" in res["LATE"])
    check("check_f2: publish time is the first build; a later rebuild does not make it late", "G3 XX 2026-11-13" in res["PASS"])
    check("check_f2: future test with no prediction is PENDING", res["PENDING"] == ["G3 XX 2026-11-30"])
    check("check_f2: exact status sets",
          sorted(res["PASS"]) == ["G3 XX 2026-11-05", "G3 XX 2026-11-08", "G3 XX 2026-11-13"]
          and sorted(res["LATE"]) == ["G3 XX 2026-11-06", "G3 XX 2026-11-12"]
          and sorted(res["MISSING"]) == ["G3 XX 2026-11-07", "G3 XX 2026-11-09"])
    check("check_f2: attempted is never a status", all(k in ("PASS", "LATE", "MISSING", "PENDING") for k in
                                                       (l.split()[0] for l in txt.splitlines() if l and not l.startswith((" ", "INFO", "F2 totals")))))
    check("check_f2: exempt and undated entries are not judged",
          "2026-11-04 " not in txt and "exempt (before 2026-11-05): 1" in txt)
    check("check_f2: prints the page, the prediction path and an escalation line naming the cause",
          "G3/XX/Pass2/2026-11-03T200000-prediction.json" in txt and "coach failure (no prediction)" in txt
          and "coach failure (no full mock page that logs)" in txt and "Basy escalates to Gilfoy" in txt)
    check("check_f2: never prints scores, predictions or text", "14/20" not in txt and "12/20" not in txt
          and '"total"' not in txt and "any_text_key" not in txt)
    mirror = os.path.join(tmp, "mirror")
    for pth, h in pages.items():
        os.makedirs(os.path.join(mirror, pth), exist_ok=True)
        open(os.path.join(mirror, pth, "index.html"), "w").write(h)
    mp = os.path.join(tmp, "manifest.json")
    json.dump(man, open(mp, "w"))
    with redirect_stdout(io.StringIO()):
        rc_strict = C.main(["--strict", "--manifest", mp, "--src", mirror, "--now", "2026-11-14T00:00:00-08:00"])
        rc_plain = C.main(["--manifest", mp, "--src", mirror, "--now", "2026-11-14T00:00:00-08:00"])
    check("check_f2 --strict exits 1 on MISSING/LATE; without --strict exits 0", rc_strict == 1 and rc_plain == 0)
    ok_man = os.path.join(tmp, "ok.json")
    json.dump([it for it in man if it["test_date"] == "2026-11-05"], open(ok_man, "w"))
    with redirect_stdout(io.StringIO()):
        rc_ok = C.main(["--strict", "--manifest", ok_man, "--src", mirror, "--now", "2026-11-14T00:00:00-08:00"])
    check("check_f2 --strict exits 0 when every test passes, even with attempted: no", rc_ok == 0)
    with redirect_stdout(io.StringIO()) as o:
        rc_nosrc = C.main(["--manifest", ok_man, "--src", os.path.join(tmp, "nope")])
    check("check_f2 with no mirror exits 2 with 'DID NOT RUN'", rc_nosrc == 2 and "DID NOT RUN" in o.getvalue())
    # scores folder with no prediction records at all: the path is likely wrong, exit 2 with a clear message
    def rc_err(folder):
        os.environ["STUDY_HUB_SCORES_DIR"] = folder
        try:
            e = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(e):
                rc = C.main(["--manifest", mp, "--src", mirror, "--now", "2026-11-14T00:00:00-08:00"])
            return rc, e.getvalue()
        finally:
            os.environ["STUDY_HUB_SCORES_DIR"] = os.path.join(tmp, "scores")
    empty = os.path.join(tmp, "empty-scores")
    os.makedirs(os.path.join(empty, "G3", "XX", "Pass2"))
    open(os.path.join(empty, "G3", "XX", "Pass2", "2026-11-05T100000-mock-aaaa.json"), "w").write("{}")
    rc, err = rc_err(empty)
    check("check_f2: a scores folder with no prediction records exits 2 and names the folder",
          rc == 2 and "no prediction records" in err and empty in err and "likely wrong" in err)
    one = os.path.join(tmp, "one-scores")
    os.makedirs(os.path.join(one, "G3", "YY", "Other"))
    json.dump({"kind": "prediction"}, open(os.path.join(one, "G3", "YY", "Other", "2026-11-01T100000-prediction.json"), "w"))
    rc, err = rc_err(one)
    check("check_f2: one unrelated prediction file does not trigger it (tests stay MISSING, not exit 2)",
          rc == 0 and "no prediction records" not in err)
    rc, err = rc_err(os.path.join(tmp, "no-such-scores"))
    check("check_f2: a missing scores folder exits 2 and names it",
          rc == 2 and "no-such-scores" in err and "does not exist" in err)
    # no token, no network: a clean exit 2 with a message, run in a child with an empty HOME
    env = {k: v for k, v in os.environ.items() if k not in ("STUDY_HUB_SCORES_DIR", "STUDY_HUB_SCORES_TOKEN")}
    env["HOME"] = os.path.join(tmp, "home")
    os.makedirs(env["HOME"])
    r = subprocess.run([sys.executable, C.__file__, "--manifest", mp, "--src", mirror], env=env, capture_output=True, text=True, timeout=60)
    check("check_f2 without a token exits 2 with 'DID NOT RUN' and no traceback",
          r.returncode == 2 and "DID NOT RUN" in r.stdout and "Traceback" not in r.stderr)
finally:
    os.environ.pop("STUDY_HUB_SCORES_DIR", None)
    shutil.rmtree(tmp, ignore_errors=True)

print("all %d F2 checks passed" % n)
