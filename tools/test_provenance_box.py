#!/usr/bin/env python3
"""Box-rule tests (B1-B6) with a fixture subject 'Sci' in a temp folder that stands in for study-hub-scores.
Run on the box: python3 tools/test_provenance_box.py   (no token, no network, nothing real is touched)."""
import copy, csv, hashlib, io, json, os, sys, tempfile
from datetime import datetime
T = tempfile.mkdtemp(prefix="sh-prov-box.")
os.environ["STUDY_HUB_SCORES_DIR"] = os.path.join(T, "scores")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_provenance as P
import sh_scores as S

n = 0


def check(name, probs, rule=None):
    global n
    n += 1
    ok = (probs == []) if rule is None else any(r == rule for r, _ in probs)
    if not ok:
        print("FAIL: %s\n  got: %s" % (name, probs))
        sys.exit(1)
    print("ok   %s%s" % (name, "" if rule is None else "  -> %s" % next(m for r, m in probs if r == rule)[:110]))


def w(path, data):
    S.put(path, data if isinstance(data, (bytes, str)) else json.dumps(data), "fixture")


src = os.path.join(T, "words.csv")
open(src, "w").write("word,meaning\nmelt,turn to liquid\n")
SRC_SHA = hashlib.sha256(open(src, "rb").read()).hexdigest()
RID = "1a0000000000beef"
w("G3/_receipts/%s.json" % RID, {"id": "gmail:" + RID, "subject": "Sci", "date": "2026-10-20",
                                  "datetime": "2026-10-20T09:00:00-07:00", "kind": "form_receipt", "title": "Sci quiz 1",
                                  "items": [{"q": "What does melt mean?", "options": ["a", "b"], "picked": "a"},
                                            {"q": "Which is a solid?", "options": ["a", "b"], "picked": "a"}]})


def content(lesson, retests, results=("gmail:" + RID,), weak=()):
    return {"grade": "G3", "subject": "Sci", "id": lesson, "title": lesson, "added_by": "fixture",
            "provenance": {"sources": [{"id": "file:" + src, "kind": "word_list", "sha256": SRC_SHA},
                                       {"id": "gmail:" + RID, "kind": "form_receipt"}],
                           "results_ingested": list(results), "weak_spots_from": list(weak), "patterns_from": ["gmail:" + RID]},
            "sections": [{"id": "q", "label": "Quiz", "blocks": [{"type": "quiz", "kind": "mock", "questions": [
                {"q": "What does melt mean?", "options": ["turn to liquid", "freeze"], "answer": 0, "src": "file:%s#row=2" % src,
                 "retests": list(retests)},
                {"q": "Which is a solid?", "options": ["ice", "steam"], "answer": 0, "src": "gmail:%s#Q3" % RID}]}]}]}


def publish(c, built, history=False):
    """What sh_page.py does: the record (with the open-row snapshot), and with history=True also the build copy."""
    path = "%s/%s/%s/" % (c["grade"], c["subject"], c["id"])
    logb = S.get("%s/%s/_error_log.csv" % (c["grade"], c["subject"])) or b""
    rec = P.record_bytes(c, path, built, "", P.open_row_ids(P.read_log(logb.decode())))
    w(P.scores_path(path), rec)
    if history:
        w(P.build_copy_path(path, built), rec)
    return dict({"path": path, "grade": "G3", "subject": c["subject"]}, **P.manifest_fields(rec))


# An older page (Unit1) that re-tests row Sci-1, and three attempts on it.
publish(content("Unit1", ["Sci-1"]), "2026-10-20T12:00:00-07:00")
A1 = "G3/Sci/Unit1/2026-10-21T100000-mock-aa11.json"     # missed the row's question
A2 = "G3/Sci/Unit1/2026-10-23T100000-retest-bb22.json"   # right
A3 = "G3/Sci/Unit1/2026-10-23T180000-retest-cc33.json"   # right, same day as A2
A4 = "G3/Sci/Unit1/2026-10-25T100000-retest-dd44.json"   # right, another day
w(A1, {"lesson": "Unit1", "clientTime": "2026-10-21T10:00:00.000-07:00", "missed": [{"q": "What does melt mean?", "picked": "freeze"}]})
for a, t in ((A2, "2026-10-23T10:00:00.000-07:00"), (A3, "2026-10-23T18:00:00.000-07:00"), (A4, "2026-10-25T10:00:00.000-07:00")):
    w(a, {"lesson": "Unit1", "clientTime": t, "missed": []})
COLS = P.LOG_COLUMNS


def log(rows):
    b = io.StringIO(); x = csv.DictWriter(b, fieldnames=COLS, lineterminator="\n"); x.writeheader()
    for r in rows:
        x.writerow({c: r.get(c, "") for c in COLS})
    w("G3/Sci/_error_log.csv", b.getvalue())


ROW1 = {"id": "Sci-1", "date": "2026-10-21", "topic": "melt", "resolved": "yes", "correct_count": "2",
        "last_correct_dates": "2026-10-23;2026-10-25", "notes": "attempt=%s; correct=%s; correct=%s" % (A1, A2, A4)}
ROW2 = {"id": "Sci-2", "date": "2026-10-20", "topic": "solids", "resolved": "no", "notes": "school quiz Q3"}
log([ROW1, ROW2])

# The new page (Unit2) re-tests the open row Sci-2 and lists every score file and receipt.
BUILT = "2026-11-01T09:00:00-08:00"
GOOD = content("Unit2", ["Sci-2"], weak=(A3,))
entry = publish(GOOD, BUILT)
check("fixture subject passes B1-B6", P.box_problems(entry, S))

check("B1: hash in manifest does not match _provenance.json", P.box_problems(dict(entry, provenance_sha256="f" * 64), S), "B1")
check("B1: no _provenance.json", P.box_problems(dict(entry, path="G3/Sci/Missing/"), S), "B1")

open(src, "a").write("freeze,turn to solid\n")
check("B2: source file changed after the build", P.box_problems(entry, S), "B2")
open(src, "w").write("word,meaning\nmelt,turn to liquid\n")
c = content("Unit2", ["Sci-2"], results=("gmail:" + RID, "gmail:1a00000000000bad"), weak=(A3,))
check("B2: gmail id with no ingested receipt", P.box_problems(publish(c, BUILT), S), "B2")

w("G3/Sci/Unit1/2026-10-30T100000-game-ee55.json", {"lesson": "Unit1", "missed": []})
check("B3: score file not in weak_spots_from or the error log", P.box_problems(publish(GOOD, BUILT), S), "B3")
c = content("Unit2", ["Sci-2"], weak=(A3, "G3/Sci/Unit1/2026-10-30T100000-game-ee55.json"))
check("B3: passes once the file is listed in weak_spots_from", P.box_problems(publish(c, BUILT), S))
GOOD = c

c = copy.deepcopy(GOOD); c["provenance"]["results_ingested"] = []
c["provenance"]["sources"] = [s for s in c["provenance"]["sources"] if not s["id"].startswith("gmail:")]
c["sections"][0]["blocks"][0]["questions"][1]["src"] = "file:%s#row=2" % src
check("B4: receipt for the subject not in results_ingested", P.box_problems(publish(c, BUILT), S), "B4")

c = content("Unit2", [], weak=GOOD["provenance"]["weak_spots_from"])
check("B5: the only open row is not re-tested (needs min(15, 1) = 1)", P.box_problems(publish(c, BUILT), S), "B5")
c = content("Unit2", ["Sci-2", "Sci-99"], weak=GOOD["provenance"]["weak_spots_from"])
check("B5: retests names a row that does not exist", P.box_problems(publish(c, BUILT), S), "B5")
entry = publish(GOOD, BUILT)

log([dict(ROW1, notes="attempt=%s; correct=%s; correct=%s" % (A1, A2, A3), last_correct_dates="2026-10-23"), ROW2])
check("B6: 2 correct answers on the same PT day do not resolve a row", P.box_problems(entry, S), "B6")
log([dict(ROW1, notes="attempt=%s; correct=%s; correct=%s" % (A1, A1, A4)), ROW2])
check("B6: a cited attempt that missed the question does not count", P.box_problems(entry, S), "B6")
log([dict(ROW1, notes="attempt=%s; correct=%s" % (A1, A4), correct_count="1"), ROW2])
check("B6: only 1 correct answer", P.box_problems(entry, S), "B6")
log([dict(ROW1, last_correct_dates=""), ROW2])
check("B6: last_correct_dates must list the days", P.box_problems(entry, S), "B6")
log([ROW1, ROW2])
check("fixture passes again after the fixes", P.box_problems(entry, S))

# ---------- B5 rotation: fixture subject 'Math' with 20 open rows ----------
MSRC = os.path.join(T, "math.csv"); open(MSRC, "w").write("fact\n1+1=2\n")
MSHA = hashlib.sha256(open(MSRC, "rb").read()).hexdigest()
IDS = ["M-%02d" % i for i in range(1, 21)]
MRID = "1a00000000000ma1"
w("G3/_receipts/%s.json" % MRID, {"id": "gmail:" + MRID, "subject": "Math", "date": "2026-10-01", "datetime": "2026-10-01T09:00:00-07:00",
                                   "kind": "form_receipt", "title": "Math test 1", "items": [{"q": "Fact?", "options": ["yes", "no"], "picked": "yes"}] * 16})


def mlog(ids_open, extra_notes=None):
    rows = [{"id": i, "date": "2026-10-%02d" % int(i[2:]), "topic": "fact " + i, "resolved": "no" if i in ids_open else "void",
             "notes": (extra_notes or {}).get(i, "")} for i in IDS]
    b = io.StringIO(); x = csv.DictWriter(b, fieldnames=COLS, lineterminator="\n"); x.writeheader()
    for r in rows:
        x.writerow({c: r.get(c, "") for c in COLS})
    w("G3/Math/_error_log.csv", b.getvalue())


def mpage(lesson, retest_ids, weak=()):
    qs = [{"q": "Fact %s?" % i, "options": ["yes", "no"], "answer": 0, "src": "file:%s#row=2" % MSRC, "retests": [i]} for i in retest_ids]
    qs.append({"q": "Warm up?", "options": ["yes", "no"], "answer": 0, "src": "file:%s#row=2" % MSRC})
    return {"grade": "G3", "subject": "Math", "id": lesson, "title": lesson, "added_by": "fixture",
            "provenance": {"sources": [{"id": "file:" + MSRC, "kind": "study_guide", "sha256": MSHA}],
                           "results_ingested": ["gmail:" + MRID], "weak_spots_from": list(weak), "patterns_from": ["gmail:" + MRID]},
            "sections": [{"id": "q", "label": "Quiz", "blocks": [{"type": "quiz", "kind": "mock", "questions": qs}]}]}


def b5(probs):
    return [(r, m) for r, m in probs if r == "B5"]


mlog(IDS)
check("B5 (a): 20 open rows, first build re-tests the 15 oldest", P.box_problems(publish(mpage("W1", IDS[:15]), "2026-10-25T10:00:00-07:00"), S))
check("B5 (a): only 10 re-tests fails (needs min(15, open))", P.box_problems(publish(mpage("W1", IDS[:10]), "2026-10-25T10:00:00-07:00"), S), "B5")
check("B5 (a): 15 re-tests that skip the oldest rows fail", P.box_problems(publish(mpage("W1", IDS[5:20]), "2026-10-25T10:00:00-07:00"), S), "B5")
publish(mpage("W1", IDS[:15]), "2026-10-25T10:00:00-07:00", history=True)            # build 1 is recorded
# build 2: oldest-first now starts with the 5 rows that were never re-tested, then the oldest of the rest
need2 = IDS[15:] + IDS[:10]
check("B5 (a): second build re-tests never-re-tested rows first", P.box_problems(publish(mpage("W2", need2), "2026-10-28T10:00:00-07:00"), S))
check("B5 (a): second build that repeats build 1 fails", P.box_problems(publish(mpage("W2", IDS[:15]), "2026-10-28T10:00:00-07:00"), S), "B5")
publish(mpage("W2", need2), "2026-10-28T10:00:00-07:00", history=True)               # build 2 is recorded
plan = P.b5_plan(S, "G3", "Math", P.read_log(S.get("G3/Math/_error_log.csv").decode()), datetime.fromisoformat("2026-10-31T10:00:00-07:00"))
check("B5 plan: history has 2 builds, (a) list starts with M-11", [] if plan["builds"] == 2 and plan["oldest"][0] == "M-11" else ["bad plan %s" % plan])

# (c) an attempt on W2 after build 2 missed the question for M-18. M-18 is not in build 3's oldest-first 15
# (M-11..M-15 were last re-tested in build 1, then M-01..M-10 by date), so only rule (c) asks for it.
AM = "G3/Math/W2/2026-10-29T170000-mock-mm01.json"
w(AM, {"lesson": "W2", "clientTime": "2026-10-29T17:00:00.000-07:00", "missed": [{"q": "Fact M-18?", "picked": "no"}]})
need3 = IDS[10:15] + IDS[:10]
pr = P.box_problems(publish(mpage("W3", need3, weak=(AM,)), "2026-10-31T10:00:00-07:00"), S)
check("B5 (c): a row missed again since the last build must be re-tested", [] if b5(pr) and all("(c) row M-18" in m for _, m in b5(pr)) else ["got %s" % pr])
check("B5 (c): passes when it is re-tested", P.box_problems(publish(mpage("W3", need3 + ["M-18"], weak=(AM,)), "2026-10-31T10:00:00-07:00"), S))

# (b) with a smaller minimum, so the 3-build window bites on its own
P.B5_MIN = 1
try:
    mlog(IDS[:5])
    for f in S.tree("G3/Math/"):
        if "/_builds/" in f or f.endswith("_provenance.json") or f == AM:
            os.remove(os.path.join(os.environ["STUDY_HUB_SCORES_DIR"], f))
    publish(mpage("V1", ["M-01"]), "2026-11-02T10:00:00-08:00", history=True)
    publish(mpage("V2", ["M-02"]), "2026-11-04T10:00:00-08:00", history=True)
    pr = P.box_problems(publish(mpage("V3", ["M-03"]), "2026-11-06T10:00:00-08:00"), S)
    check("B5 (b): rows open in the last 2 builds and re-tested in neither must be re-tested now (only M-04, M-05)",
          [] if sorted(m.split("row ")[1].split()[0] for _, m in b5(pr)) == ["M-04", "M-05"] and all("(b)" in m for _, m in b5(pr)) else ["got %s" % pr])
    check("B5 (b): passes when they are re-tested", P.box_problems(publish(mpage("V3", ["M-03", "M-04", "M-05"]), "2026-11-06T10:00:00-08:00"), S))
finally:
    P.B5_MIN = 15
# ---------- F1: patterns_from receipts ----------
c = content("Unit2", ["Sci-2"], weak=(A3, "G3/Sci/Unit1/2026-10-30T100000-game-ee55.json"))
c["provenance"]["patterns_from"] = ["gmail:1a00000000000ma1"]
check("F1/B2: patterns_from must be a receipt of the same subject", P.box_problems(publish(c, BUILT), S), "B2")
c["provenance"]["patterns_from"] = ["gmail:" + RID]
rec = json.loads(S.get(P.scores_path(publish(c, BUILT)["path"])))
lines, probs = P.f1_report(rec, S)
check("F1: Sci mock (2 questions, 2 options) matches its school test", [] if (lines and probs == []) else ["got %s %s" % (lines, probs)])
big = copy.deepcopy(c); big["sections"][0]["blocks"][0]["questions"] *= 6
rec = json.loads(S.get(P.scores_path(publish(big, BUILT)["path"])))
check("F1: a 12-question mock against a 2-question school test is out of range (warning)",
      [] if any("question count" in x for x in P.f1_report(rec, S)[1]) else ["no warning"])
import shutil
shutil.rmtree(T)
print("provenance box-rule tests passed (%d)" % n)
