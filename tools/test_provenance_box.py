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

# The B1-B6 fixtures below test the cumulative B5 (contest mode). The school-mode window is tested at the end.
P.L.CFG["subject_modes"] = dict(P.L.CFG.get("subject_modes") or {}, Sci="contest", Math="contest")
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

# attach: a record for a page that existed before the rules (no B3/B4/B5 rotation; B1, B2, retests ids and B6 apply)
frag = {"page": "G3/Sci/Old/", "provenance": {"sources": [{"id": "file:" + src, "kind": "word_list", "sha256": SRC_SHA}]},
        "questions": [{"id": "Q1", "q": "What does melt mean?", "src": "file:%s#row=2" % src, "retests": ["Sci-2"]},
                      {"id": "Q2", "q": "Which is a solid?", "src": "file:%s#row=2" % src}]}
OLD = {"path": "G3/Sci/Old/", "grade": "G3", "subject": "Sci", "added_by": "fixture"}
raw, pr = P.attach_record(frag, OLD, S, "2026-10-31T10:00:00-07:00")
rec = json.loads(raw)
check("attach: an old page with sourced questions attaches (B3/B4/B5 rotation do not apply)",
      pr + ([] if rec["attached"] and P.manifest_fields(raw)["n_questions"] == 2 and rec["questions"][0]["id"] == "Q1" else ["bad record"]))
bad = copy.deepcopy(frag); bad["questions"][1]["src"] = "file:/nope.csv#row=1"
pr = P.attach_record(bad, OLD, S, "2026-10-31T10:00:00-07:00")[1]
check("attach: a question whose src is not a listed source fails", [] if any("src" in m for m in pr) else ["no problem found: %s" % pr])
bad = copy.deepcopy(frag); bad["questions"][0]["retests"] = ["Sci-77"]
pr = P.attach_record(bad, OLD, S, "2026-10-31T10:00:00-07:00")[1]
check("attach: retests must name real error-log rows", [] if any("Sci-77" in m for m in pr) else ["no problem found: %s" % pr])

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
# the same with a privacy v3 attempt: no question text, only the item id (W2 question 3 re-tests M-18)
w(AM, {"lesson": "W2", "clientTime": "2026-10-29T17:00:00.000-07:00", "missed": [{"n": 3, "id": "q1-3", "picked": "B", "correct": "A", "blank": False, "typed": False}]})
pr = P.box_problems(publish(mpage("W3", need3, weak=(AM,)), "2026-10-31T10:00:00-07:00"), S)
check("B5 (c): a v3 attempt (item id, no text) that missed the row's question is found", [] if b5(pr) and all("(c) row M-18" in m for _, m in b5(pr)) else ["got %s" % pr])
w(AM, {"lesson": "W2", "clientTime": "2026-10-29T17:00:00.000-07:00", "missed": [{"n": 16, "id": "q1-16", "picked": "B", "correct": "A", "blank": False, "typed": False}]})
check("B5 (c): a v3 attempt that missed only the warm-up (no retests) does not count", P.box_problems(publish(mpage("W3", need3, weak=(AM,)), "2026-10-31T10:00:00-07:00"), S))

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
P.L.CFG["subject_modes"]["Sci"] = "school"
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

# ---------- school mode: closed rows and the prep window (fixture subject 'Grammar') ----------
GR1, GR2 = "1a00000000000g01", "1a00000000000g02"
for rid, d in ((GR1, "2026-10-10"), (GR2, "2026-10-24")):
    w("G3/_receipts/%s.json" % rid, {"id": "gmail:" + rid, "subject": "Grammar", "date": d, "datetime": d + "T09:00:00-07:00",
                                      "kind": "form_receipt", "title": "Grammar test " + d, "items": [{"q": "Pick one?", "options": ["a", "b"], "picked": "a"}]})


def glog(rows):
    b = io.StringIO(); x = csv.DictWriter(b, fieldnames=COLS, lineterminator="\n"); x.writeheader()
    for r in rows:
        x.writerow({c: r.get(c, "") for c in COLS})
    w("G3/Grammar/_error_log.csv", b.getvalue())


def gpage(lesson, retest_ids):
    qs = [{"q": "Item %s?" % i, "options": ["a", "b"], "answer": 0, "src": "file:%s#row=2" % MSRC, "retests": [i]} for i in retest_ids]
    qs.append({"q": "Warm up?", "options": ["a", "b"], "answer": 0, "src": "file:%s#row=2" % MSRC})
    return {"grade": "G3", "subject": "Grammar", "id": lesson, "title": lesson, "added_by": "fixture",
            "provenance": {"sources": [{"id": "file:" + MSRC, "kind": "study_guide", "sha256": MSHA}],
                           "results_ingested": ["gmail:" + GR1, "gmail:" + GR2], "weak_spots_from": [], "patterns_from": ["gmail:" + GR2]},
            "sections": [{"id": "q", "label": "Quiz", "blocks": [{"type": "quiz", "kind": "mock", "questions": qs}]}]}


GROWS = [{"id": "G-1", "date": "2026-10-10", "round": "school", "resolved": "closed", "error_type": "look-alike word", "skill": "fill in the blank"},
         {"id": "G-2", "date": "2026-10-10", "round": "school", "resolved": "closed", "error_type": "look-alike word", "skill": "pick the meaning"},
         {"id": "G-3", "date": "2026-10-24", "round": "school", "resolved": "no"},
         {"id": "G-4", "date": "2026-10-27", "round": "mock round 1", "resolved": "no"},
         {"id": "G-5", "date": "2026-10-28", "round": "game", "resolved": "no"}]
glog(GROWS)
GB = "2026-10-31T10:00:00-07:00"
pl = P.b5_plan(S, "G3", "Grammar", P.read_log(S.get("G3/Grammar/_error_log.csv").decode()), datetime.fromisoformat(GB))
check("school mode: window starts at the last real test (10-24); only open rows after it count; closed rows are patterns",
      [] if (pl["mode"], pl["window_from"], pl["open"], pl["outside"], pl["patterns"]) == ("school", "2026-10-24", ["G-4", "G-5"], ["G-3"], ["G-1", "G-2"])
      else ["got %s" % pl])
check("school mode: a page that re-tests the 2 rows in the window passes (closed and pre-window rows are not needed)",
      P.box_problems(publish(gpage("U1", ["G-4", "G-5"]), GB), S))
check("school mode: a page that re-tests only closed rows fails B5", P.box_problems(publish(gpage("U1", ["G-1", "G-2"]), GB), S), "B5")
P.L.CFG["subject_modes"]["Grammar"] = "contest"
check("contest mode: the same log is cumulative (G-3 must be re-tested too)", P.box_problems(publish(gpage("U1", ["G-4", "G-5"]), GB), S), "B5")
P.L.CFG["subject_modes"]["Grammar"] = "school"
glog(GROWS + [{"id": "G-6", "date": "2026-10-29", "resolved": "done"}])
check("an unknown resolved status fails", P.box_problems(publish(gpage("U1", ["G-4", "G-5", "G-6"]), GB), S), "B5")
glog(GROWS)
rec = json.loads(S.get(P.scores_path(publish(gpage("U1", ["G-4", "G-5"]), GB)["path"])))
check("F1 lists the closed rows as pattern input (trap types, question styles)",
      [] if any("patterns from 2 closed rows" in x and "look-alike word (2)" in x for x in P.f1_report(rec, S)[0]) else ["got %s" % (P.f1_report(rec, S),)])
frag = {"page": "G3/Grammar/Old/", "provenance": {"sources": [{"id": "file:" + MSRC, "kind": "study_guide", "sha256": MSHA}]},
        "questions": [{"id": "Q1", "q": "Item?", "src": "file:%s#row=2" % MSRC, "retests": ["G-1", "G-4"]}]}
raw, pr = P.attach_record(frag, {"path": "G3/Grammar/Old/", "grade": "G3", "subject": "Grammar"}, S, GB)
rec = json.loads(raw)
check("attach drops closed rows from retests (school test already happened)",
      pr + ([] if rec["questions"][0]["retests"] == ["G-4"] and rec["dropped_closed_retests"] == ["G-1"] else ["got %s" % rec["questions"][0]]))

# ---------- Kangaroo chapter pages: open rows of OTHER chapters do not block B5 (Muskan's rule via Aussie, Nov 11) ----------
KROWS = [{"id": "KG-Ch1-q9-1-20261111", "date": "2026-11-11", "unit": "Ch1-Mirrors-v2", "round": "game", "resolved": "no"},
         {"id": "KG-Ch1-q10-1-20261111", "date": "2026-11-11", "unit": "Ch1-Mirrors-v2", "round": "game", "resolved": "no"},
         {"id": "KG-Ch2-q3-1-20261111", "date": "2026-11-11", "unit": "Ch2-Number-Sense", "round": "game", "resolved": "no"}]
b = io.StringIO(); x = csv.DictWriter(b, fieldnames=COLS, lineterminator="\n"); x.writeheader()
for r in KROWS:
    x.writerow({c: r.get(c, "") for c in COLS})
KLOG = b.getvalue().encode()
w("G3/Kangaroo/_error_log.csv", KLOG)


def kpage(lesson, retest_ids):
    c = gpage(lesson, retest_ids)
    c["subject"] = "Kangaroo"
    c["provenance"]["results_ingested"], c["provenance"]["patterns_from"] = [], []
    return c


KB = "2026-11-11T22:00:00-08:00"
kw = []
pr = P.box_problems(publish(kpage("Ch2-Number-Sense", ["KG-Ch2-q3-1-20261111"]), KB), S, warns=kw)
check("Kangaroo chapter page: re-tests only its own chapter's open row; Ch1 rows do not block", pr)
check("Kangaroo chapter page: a WARNING lists the 2 open rows of other chapters",
      [] if len(kw) == 1 and "KG-Ch1-q9-1-20261111" in kw[0] and "KG-Ch1-q10-1-20261111" in kw[0] and "do not block" in kw[0]
      else ["got %s" % kw])
check("Kangaroo chapter page: its own chapter's open row still blocks when it is not re-tested",
      P.box_problems(publish(kpage("Ch2-Number-Sense", []), KB), S), "B5")
check("Kangaroo Syllabus keeps the full B5: the Ch1 rows must be re-tested",
      P.box_problems(publish(kpage("Syllabus", ["KG-Ch2-q3-1-20261111"]), KB), S), "B5")
check("Kangaroo Syllabus passes when it re-tests every open row",
      P.box_problems(publish(kpage("Syllabus", [r["id"] for r in KROWS]), KB), S))
check("Kangaroo: a non-chapter page (team mock) keeps the full B5",
      P.box_problems(publish(kpage("team-mock-1", ["KG-Ch2-q3-1-20261111"]), KB), S), "B5")
check("Kangaroo: the error log is not changed by the check (other-chapter rows stay open)",
      [] if S.get("G3/Kangaroo/_error_log.csv") == KLOG else ["error log changed"])
check("row_chapter reads the unit, then the id", [] if (P.row_chapter({"unit": "Ch1-Mirrors-v2"}), P.row_chapter({"id": "KG-Ch12-q4-1"}),
      P.row_chapter({"unit": "team-mock-1", "id": "KG-M1-q3"})) == (1, 12, None) else ["bad row_chapter"])
check("other_chapter_rows: empty for a non-Kangaroo or non-chapter page",
      [] if P.other_chapter_rows("G3/Noetic/Ch2-Logic/", KROWS) == [] and P.other_chapter_rows("G3/Kangaroo/Syllabus/", KROWS) == []
      else ["not empty"])

import shutil
shutil.rmtree(T)
print("provenance box-rule tests passed (%d)" % n)
