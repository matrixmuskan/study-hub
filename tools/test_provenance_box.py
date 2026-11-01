#!/usr/bin/env python3
"""Box-rule tests (B1-B6) with a fixture subject 'Sci' in a temp folder that stands in for study-hub-scores.
Run on the box: python3 tools/test_provenance_box.py   (no token, no network, nothing real is touched)."""
import copy, csv, hashlib, io, json, os, sys, tempfile
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
                                  "datetime": "2026-10-20T09:00:00-07:00", "kind": "form_receipt", "title": "Sci quiz 1", "items": []})


def content(lesson, retests, results=("gmail:" + RID,), weak=()):
    return {"grade": "G3", "subject": "Sci", "id": lesson, "title": lesson, "added_by": "fixture",
            "provenance": {"sources": [{"id": "file:" + src, "kind": "word_list", "sha256": SRC_SHA},
                                       {"id": "gmail:" + RID, "kind": "form_receipt"}],
                           "results_ingested": list(results), "weak_spots_from": list(weak)},
            "sections": [{"id": "q", "label": "Quiz", "blocks": [{"type": "quiz", "kind": "mock", "questions": [
                {"q": "What does melt mean?", "options": ["turn to liquid", "freeze"], "answer": 0, "src": "file:%s#row=2" % src,
                 "retests": list(retests)},
                {"q": "Which is a solid?", "options": ["ice", "steam"], "answer": 0, "src": "gmail:%s#Q3" % RID}]}]}]}


def publish(c, built):
    path = "G3/Sci/%s/" % c["id"]
    rec = P.record_bytes(c, path, built)
    w(P.scores_path(path), rec)
    return dict({"path": path, "grade": "G3", "subject": "Sci"}, **P.manifest_fields(rec))


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
check("B5: unresolved row with no retest question", P.box_problems(publish(c, BUILT), S), "B5")
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
import shutil
shutil.rmtree(T)
print("provenance box-rule tests passed (%d)" % n)
