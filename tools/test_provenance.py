#!/usr/bin/env python3
"""CI tests for the public provenance rules (P1, P2, legacy list, build-time rules, B7). No secrets, no network."""
import copy, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_provenance as P
import validate as V

SHA = "0" * 64
GOOD = {"grade": "G3", "subject": "SS", "id": "T-Page", "title": "T", "added_by": "CI",
        "provenance": {"sources": [{"id": "file:/x/words.csv", "kind": "word_list", "sha256": SHA},
                                   {"id": "gmail:1a164970d5ea012b", "kind": "form_receipt", "what": "school test"}],
                       "results_ingested": ["gmail:1a164970d5ea012b"], "weak_spots_from": []},
        "sections": [{"id": "q", "label": "Quiz", "blocks": [{"type": "quiz", "kind": "mock", "questions": [
            {"q": "Q%d" % i, "options": ["a", "b"], "answer": 0, "src": "file:/x/words.csv#row=%d" % i,
             "retests": ["SS-2026-10-08-ch8-q1"] if i == 1 else []} for i in range(1, 10)] +
            [{"q": "Q10", "options": ["a", "b"], "answer": 1, "inferred": True}]}]}]}
n = 0


def check(name, cond):
    global n
    n += 1
    if not cond:
        sys.exit("FAIL: " + name)
    print("ok   " + name)


check("good content passes build rules", P.content_problems(GOOD) == [])
c = copy.deepcopy(GOOD); del c["provenance"]
check("no provenance block fails", P.content_problems(c))
c = copy.deepcopy(GOOD); c["provenance"]["sources"] = []
check("no sources fails", any("at least 1 source" in x for x in P.content_problems(c)))
c = copy.deepcopy(GOOD); c["sections"][0]["blocks"][0]["questions"][0].pop("src")
check("question with no src and not inferred fails", any("needs 'src'" in x for x in P.content_problems(c)))
c = copy.deepcopy(GOOD); c["sections"][0]["blocks"][0]["questions"][0]["src"] = "paper:2024S#Q3"
check("src that is not a listed source fails", any("not a listed source" in x for x in P.content_problems(c)))
c = copy.deepcopy(GOOD); c["provenance"]["sources"][0].pop("sha256")
check("file: source without sha256 fails", any("sha256" in x for x in P.content_problems(c)))
c = copy.deepcopy(GOOD)
for q in c["sections"][0]["blocks"][0]["questions"][:2]:
    q.pop("src"); q["inferred"] = True
check("3 of 10 inferred (30%) fails P2 at build", any("limit is 20%" in x for x in P.content_problems(c)))
c = copy.deepcopy(GOOD); c["log"] = False
check("quiz page with log false fails (B7)", any("must log" in x for x in P.content_problems(c)))

rec = P.record_bytes(GOOD, "G3/SS/T-Page/", "2026-11-01T10:00:00-08:00")
f = P.manifest_fields(rec)
check("manifest fields: hash of the private record, counts", f["provenance_sha256"] == hashlib.sha256(rec).hexdigest()
      and (f["n_sources"], f["n_questions"], f["n_inferred"], f["n_retests"]) == (2, 10, 1, 1))
check("manifest fields hold no source ids or question text", "words.csv" not in json.dumps(f) and "Q1" not in json.dumps(f))

legacy = sorted(P.legacy_pages())
items = [{"path": p} for p in legacy] + [dict({"path": "G3/SS/T-Page/", "template": "sh-2"}, **f)]
errs, warns = P.public_problems(items, legacy)
check("P1/P2 pass for a new page with counts; one warning per legacy page", errs == [] and len(warns) == len(legacy))
bad = dict(items[-1]); bad.pop("provenance_sha256")
check("P1 fails without provenance_sha256", any(r == "P1" for r, _ in P.public_problems(items[:-1] + [bad], legacy)[0]))
bad = dict(items[-1], n_sources=0)
check("P1 fails with n_sources 0", any(r == "P1" for r, _ in P.public_problems(items[:-1] + [bad], legacy)[0]))
bad = dict(items[-1], n_questions=0)
check("P1 fails with n_questions 0", any(r == "P1" for r, _ in P.public_problems(items[:-1] + [bad], legacy)[0]))
bad = dict(items[-1], n_inferred=3)
check("P2 fails with 3 of 10 inferred", any(r == "P2" for r, _ in P.public_problems(items[:-1] + [bad], legacy)[0]))
bad = dict(items[-1], n_inferred=2)
check("P2 passes with 2 of 10 inferred", P.public_problems(items[:-1] + [bad], legacy)[0] == [])
check("legacy list may not grow", any("may only shrink" in m for _, m in P.public_problems(items, legacy[:-1])[0]))
check("legacy list must name real pages", any("not in manifest" in m for _, m in P.public_problems(items[1:], legacy)[0]))

page_nolog = '<script type="application/json" id="sh-data">{"quizzes":[{"questions":[]}],"log":false}</script>'
check("B7: quiz page without logger fails", V.b7_problems(page_nolog))
page_ls = '<script>var answer: 1; localStorage.setItem("x","y")</script>'.replace("var answer: 1", "var Q={answer: 1}")
check("B7: localStorage-only quiz fails", any("localStorage" in x for x in V.b7_problems(page_ls)))
page_ok = '<script type="application/json" id="sh-data">{"quizzes":[{"questions":[]}],"log":true}</script><script>var SHLog=1</script>'
check("B7: quiz page with logger passes", V.b7_problems(page_ok) == [])
check("B7: page with no quiz passes", V.b7_problems("<p>hello</p>") == [])
print("provenance public-rule tests passed (%d)" % n)
