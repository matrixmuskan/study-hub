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
                       "results_ingested": ["gmail:1a164970d5ea012b"], "weak_spots_from": [],
                       "patterns_from": ["gmail:1a164970d5ea012b"]},
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
c = copy.deepcopy(GOOD); del c["provenance"]["patterns_from"]
check("F1: school-subject mock without patterns_from fails", any(x.startswith("F1:") for x in P.content_problems(c)))
c["subject"] = "Noetic"
check("F1: a contest subject (Noetic) does not need patterns_from", not any(x.startswith("F1:") for x in P.content_problems(c)))
c = copy.deepcopy(GOOD); c["provenance"]["patterns_from"] = ["1a164970d5ea012b"]
check("F1: patterns_from must be gmail:<id>", any("gmail:<id>" in x for x in P.content_problems(c)))
c = copy.deepcopy(GOOD); c["sections"][0]["blocks"][0]["kind"] = "game"; del c["provenance"]["patterns_from"]
check("F1: a page with no mock does not need patterns_from", not any(x.startswith("F1:") for x in P.content_problems(c)))
rc = {"items": [{"q": "Q%d" % i, "options": ["a", "b"], "picked": "a"} for i in range(10)]}
qs = P.questions_of(GOOD)
lines, probs = P.format_compare(qs, [rc])
check("F1 compare: same count, types, options and length is in range", probs == [] and "questions" in lines[1])
rc4 = {"items": [{"q": "Q%d" % i, "options": ["a", "b", "c", "d"], "picked": "a"} for i in range(30)]}
lines, probs = P.format_compare(qs, [rc4])
check("F1 compare: 10 vs 30 questions and 2 vs 4 options are out of range",
      any("question count" in x for x in probs) and any("options per question" in x for x in probs))
rct = {"items": [{"q": "Q%d word word" % i, "options": [], "picked": "x"} for i in range(10)]}
check("F1 compare: multiple choice vs written answers is out of range", any("multiple choice" in x for x in P.format_compare(qs, [rct])[1]))
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
# subject modes: school subjects end their prep window at a real test; contest subjects are cumulative
check("subject modes: SS, WW, LA, Math, Sci, Grammar are school; Noetic, Kangaroo, MOEMS are contest",
      all(P.subject_mode(x) == "school" for x in ("SS", "WW", "LA", "Math", "Sci", "Grammar"))
      and all(P.subject_mode(x) == "contest" for x in ("Noetic", "Kangaroo", "MOEMS")))
check("closed is a valid status, separate from yes", "closed" in P.STATUSES and "yes" in P.STATUSES)
# every Contents API write is made as Study Hub Bot (never the token owner)
import sh_scores as SC
_sent = []
_saved = (SC.local_dir, SC.get, SC._req)
SC.local_dir = lambda: None
SC.get = lambda path: None
SC._req = lambda method, url, body=None, tries=3: (_sent.append((method, body)) or (201, {}))
try:
    SC.put("G3/T/x.json", b"{}", "test")
finally:
    SC.local_dir, SC.get, SC._req = _saved
bot = {"name": "Study Hub Bot", "email": "study-hub-bot@users.noreply.github.com"}
check("sh_scores.put sets author and committer to Study Hub Bot",
      len(_sent) == 1 and _sent[0][0] == "PUT" and _sent[0][1].get("committer") == bot and _sent[0][1].get("author") == bot)

# school-app:<id> is a valid neutral source id; a source that names a private word fails (dummy word, not a real term)
c = copy.deepcopy(GOOD); c["provenance"]["sources"].append({"id": "school-app:95000001", "kind": "teacher_notice"})
check("school-app:<id> source id is accepted", P.content_problems(c) == [])
c = copy.deepcopy(GOOD); c["provenance"]["sources"].append({"id": "url:https://www.dummyapp.example/feeds/1", "kind": "teacher_notice"})
check("a source url that names a blocklist word fails, and the word is not printed",
      P.private_source_problems(c["provenance"]["sources"], bl="dummyapp") and
      not any("dummyapp" in x for x in P.private_source_problems(c["provenance"]["sources"], bl="dummyapp")))
check("no blocklist (CI): no private-source check", P.private_source_problems(c["provenance"]["sources"], bl="") == [])

# config-diff (publish.sh): attach's legacy_provenance shrink is staged; any other config change stops the publish
import subprocess, tempfile, shutil
td = tempfile.mkdtemp()
try:
    os.makedirs(os.path.join(td, "tools"))
    cfg = {"template_version": "sh-2", "legacy_provenance": ["G3/A/One/", "G3/A/Two/"]}
    man = [{"path": "G3/A/One/"}, {"path": "G3/A/Two/"}]
    w = lambda f, o: open(os.path.join(td, f), "w").write(json.dumps(o, indent=2))
    w("tools/sh_config.json", cfg); w("manifest.json", man)
    g = lambda *a: subprocess.run(["git", "-C", td] + list(a), capture_output=True, check=True)
    g("init", "-q"); g("add", "-A"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    check("config-diff: unchanged config is clean", P.config_diff(td)[0] == "clean")
    w("tools/sh_config.json", dict(cfg, legacy_provenance=["G3/A/One/"]))
    check("config-diff: shrink without a manifest hash stops the publish", P.config_diff(td)[0] == "dirty")
    w("manifest.json", [{"path": "G3/A/One/"}, {"path": "G3/A/Two/", "provenance_sha256": SHA}])
    check("config-diff: attach shrink with a manifest hash is staged", P.config_diff(td)[0] == "stage")
    w("tools/sh_config.json", dict(cfg, legacy_provenance=["G3/A/One/"], template_version="sh-3"))
    check("config-diff: any other config change stops the publish", P.config_diff(td)[0] == "dirty")
    w("tools/sh_config.json", dict(cfg, legacy_provenance=["G3/A/One/", "G3/A/Two/", "G3/A/Three/"]))
    check("config-diff: a grown legacy list stops the publish", P.config_diff(td)[0] == "dirty")
finally:
    shutil.rmtree(td)

# attach maps fragment questions to the ids the logger sends (q<quiz>-<n>), by text, as sh_page.py numbers them
page = [(0, 1, "q1-1", "[Sample A] How many even numbers?", "game"), (0, 2, "q1-2", "What is 2 + 2?", "game"),
        (1, 1, "q2-1", "Pick the odd one out.", "mock")]
ids, pr, qz = P.map_logger_ids([{"id": "practice-1", "q": "How many even numbers?"}, {"id": "mastery-1", "q": "Pick the odd one out."},
                                {"id": "practice-2", "q": "What is 2 + 2?"}], page)
check("attach maps fragment ids to logger ids by question text", ids == ["q1-1", "q2-1", "q1-2"] and pr == [])
check("attach writes the real quiz number (q2-n is quiz 1)", qz == [0, 1, 0])
ids, pr, qz = P.map_logger_ids([{"id": "mock-9", "q": "A question that is not on the page"}], page)
check("attach refuses a question that is not on the page", pr and "no logger id" in pr[0])
import sh_lib as LL
h = '<script type="application/json" id="sh-data">' + json.dumps({"quizzes": [{"kind": "game", "questions": [{"q": "a"}, {"q": "b", "id": "w-7"}]}, {"kind": "mock", "questions": [{"q": "c"}]}]}) + "</script>"
check("logger_ids reads sh-data like sh.js (q.id or q<quiz>-<n>)", [x[2] for x in LL.logger_ids(h)] == ["q1-1", "w-7", "q2-1"] and LL.logger_ids("<p>old page</p>") is None)
print("provenance public-rule tests passed (%d)" % n)
