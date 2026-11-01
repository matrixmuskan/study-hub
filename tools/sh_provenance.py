#!/usr/bin/env python3
"""Provenance and learning-loop rules for Study Hub pages (content-audit.md section 5).

A content file has a "provenance" block, and each quiz question has "src" (or "inferred": true) and "retests".
sh_page.py writes the full record to the PRIVATE repo study-hub-scores at G3/<Subject>/<Lesson>/_provenance.json
and puts only counts and a hash in the public manifest.json.

Rules
  Public (validate.py, CI, no secrets), for every manifest page not in tools/sh_config.json "legacy_provenance":
    P1  provenance_sha256 (64 hex), n_sources >= 1, n_questions >= 1.
    P2  n_inferred / n_questions <= 0.20.
  Box (publish.sh, needs STUDY_HUB_SCORES_TOKEN; read-only on study-hub-scores):
    B1  _provenance.json exists in study-hub-scores and its sha256 equals provenance_sha256.
    B2  every question has src or inferred: true; every src id is a listed source; every file: source exists on the box
        and its sha256 matches; every gmail: id has a receipt in G3/_receipts/<id>.json.
    B3  every score file under G3/<Subject>/ older than the build is in weak_spots_from or in an error-log note
        "attempt=<path>".
    B4  every receipt for the subject (G3/_receipts/*.json) dated before the build is in results_ingested.
    B5  every error-log row with resolved=no is in some question's retests (and every retests id is a real row).
    B6  a row is resolved=yes only when its notes cite 2 attempt files ("correct=<path>") on different PT days, and
        in each of them a question that retests the row was answered right (it is not in "missed").
    B7  (validate.py --src) a page with a quiz has the score logger; a page that keeps results only in localStorage fails.

CLI (box):  python3 tools/sh_provenance.py check [--pages G3/WW/Lesson10/ ...]   (default: every non-legacy page)
"""
import csv, hashlib, io, json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L

PT = ZoneInfo("America/Los_Angeles")
MAX_INFERRED = 0.20
SOURCE_KINDS = ("form_receipt", "score_released", "word_list", "book_page", "study_guide", "past_paper", "past_form",
                "teacher_notice", "handoff", "web", "other")
LOG_COLUMNS = ["id", "date", "unit", "topic", "skill", "question", "kid_answer", "correct_answer", "error_type", "round",
               "resolved", "correct_count", "last_correct_dates", "source", "notes"]
STAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{6})-[a-z]+-[a-z0-9]{4}\.json$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,80}$")


def legacy_pages():
    return set(L.CFG.get("legacy_provenance", []))


def is_legacy(path):
    return path in legacy_pages()


def now_pt():
    return datetime.now(PT).replace(microsecond=0)


# ---------- content file -> provenance record ----------
def questions_of(c):
    out, qi = [], 0
    for sec in c.get("sections", []):
        for b in sec.get("blocks", []):
            if b.get("type") != "quiz":
                continue
            for n, q in enumerate(b.get("questions") or [], 1):
                out.append({"quiz": qi, "kind": b.get("kind", "game"), "section": sec.get("id") or sec.get("label"), "n": n,
                            "q": q.get("q", ""), "topic": q.get("topic", ""), "src": q.get("src", ""),
                            "inferred": q.get("inferred") is True, "retests": list(q.get("retests") or [])})
            qi += 1
    return out


def content_problems(c):
    """Rules a new page must meet at build time (before anything is written). Returns a list of problems."""
    out = []
    p = c.get("provenance")
    qs = questions_of(c)
    if not isinstance(p, dict):
        return ["no 'provenance' block (see CONTRIBUTING-BOTS.md section 11)"]
    srcs = p.get("sources")
    if not isinstance(srcs, list) or not srcs:
        out.append("provenance.sources needs at least 1 source")
        srcs = []
    ids = set()
    for i, s in enumerate(srcs):
        sid = s.get("id", "") if isinstance(s, dict) else ""
        if not re.match(r"^(file|gmail|paper|url|handoff|sheet):\S+$", sid):
            out.append("source %d: id must start with file:, gmail:, paper:, url:, sheet: or handoff:" % (i + 1))
            continue
        if s.get("kind") not in SOURCE_KINDS:
            out.append("source %s: kind must be one of %s" % (sid, ", ".join(SOURCE_KINDS)))
        if sid.startswith("file:") and not re.fullmatch(r"[0-9a-f]{64}", str(s.get("sha256", ""))):
            out.append("source %s: a file: source needs its sha256 (sha256sum <file>)" % sid)
        if sid in ids:
            out.append("source %s is listed twice" % sid)
        ids.add(sid)
    for k in ("results_ingested", "weak_spots_from"):
        if not isinstance(p.get(k, []), list):
            out.append("provenance.%s must be a list" % k)
    if not qs:
        out.append("the page has no quiz questions (n_questions must be 1 or more)")
    for q in qs:
        where = "quiz %d question %d" % (q["quiz"] + 1, q["n"])
        if q["src"] and q["inferred"]:
            out.append(where + ": has both src and inferred")
        elif not q["src"] and not q["inferred"]:
            out.append(where + ": needs 'src' (source id + locator) or \"inferred\": true")
        elif q["src"] and q["src"].split("#")[0] not in ids:
            out.append(where + ": src '%s' is not a listed source id" % q["src"].split("#")[0])
        if not all(isinstance(r, str) and ID_RE.match(r) for r in q["retests"]):
            out.append(where + ": retests must be a list of error-log row ids")
    if qs:
        inf = sum(q["inferred"] for q in qs)
        if inf / len(qs) > MAX_INFERRED:
            out.append("%d of %d questions are inferred (%.0f%%); the limit is 20%%" % (inf, len(qs), 100.0 * inf / len(qs)))
    if qs and c.get("log", True) is False:
        out.append("a page with a quiz must log scores (remove \"log\": false)")
    return out


def record_bytes(c, rel_dir, built_at, error_log_sha256=""):
    p = dict(c["provenance"])
    p.setdefault("results_ingested", [])
    p.setdefault("weak_spots_from", [])
    p["error_log"] = "scores:%s/%s/_error_log.csv" % (c["grade"], c["subject"])
    p["error_log_sha256"] = error_log_sha256
    rec = {"v": 1, "page": rel_dir, "built_at": built_at, "added_by": c.get("added_by", ""), "provenance": p,
           "questions": questions_of(c)}
    return (json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def manifest_fields(rec_bytes):
    rec = json.loads(rec_bytes)
    qs = rec["questions"]
    return {"provenance_sha256": hashlib.sha256(rec_bytes).hexdigest(), "n_sources": len(rec["provenance"]["sources"]),
            "n_inferred": sum(1 for q in qs if q["inferred"]), "n_questions": len(qs),
            "n_retests": len({r for q in qs for r in q["retests"]}), "built_at": rec["built_at"]}


def scores_path(rel_dir):
    return rel_dir.rstrip("/") + "/_provenance.json"


# ---------- public rules ----------
def public_problems(items, base_legacy=None):
    """P1, P2 for every non-legacy manifest page, plus: the legacy list may only shrink (base_legacy = list on main)."""
    errs, warns = [], []
    legacy = legacy_pages()
    paths = {it.get("path") for it in items}
    for it in items:
        path = it.get("path", "")
        if path in legacy:
            warns.append("%s: legacy page, no provenance record (grandfathered in legacy_provenance)" % path)
            continue
        h = str(it.get("provenance_sha256", ""))
        nq, ns, ni = it.get("n_questions"), it.get("n_sources"), it.get("n_inferred")
        if not re.fullmatch(r"[0-9a-f]{64}", h):
            errs.append(("P1", "%s: no provenance_sha256. Build the page with tools/sh_page.py and a provenance block" % path))
        if not isinstance(ns, int) or ns < 1:
            errs.append(("P1", "%s: n_sources must be 1 or more" % path))
        if not isinstance(nq, int) or nq < 1:
            errs.append(("P1", "%s: n_questions must be 1 or more" % path))
        elif not isinstance(ni, int) or ni < 0 or ni / nq > MAX_INFERRED:
            errs.append(("P2", "%s: %s of %s questions are inferred; the limit is 20%%" % (path, ni, nq)))
    for pth in sorted(legacy - paths):
        errs.append(("P1", "legacy_provenance lists %s, which is not in manifest.json. Remove it" % pth))
    if base_legacy is not None:
        for pth in sorted(legacy - set(base_legacy)):
            errs.append(("P1", "legacy_provenance gained %s. New pages must have provenance; the list may only shrink" % pth))
    return errs, warns


# ---------- box rules ----------
def read_log(text):
    rows = list(csv.DictReader(io.StringIO(text))) if text else []
    return rows


def _attempt_day(path, payload=None):
    if payload and payload.get("clientTime"):
        try:
            return datetime.fromisoformat(payload["clientTime"]).astimezone(PT).date().isoformat()
        except ValueError:
            pass
    m = STAMP_RE.search(path)
    return m.group(1) if m else None


def _attempt_dt(path):
    m = STAMP_RE.search(path)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M%S").replace(tzinfo=PT)


def _norm_q(s):
    s = re.sub(r"\[name\]", "", s or "", flags=re.I)
    fn = (L.CFG.get("kid_first_name") or "").lower()
    s = s.lower().replace(fn, "") if fn else s.lower()
    return re.sub(r"[^a-z0-9]+", "", s)[:40]


def box_problems(entry, S, check_files=True):
    """B1 to B6 for one manifest entry. S is the sh_scores module (GitHub or local fixture folder)."""
    out = []
    path = entry["path"]
    grade, subj = path.split("/")[:2]
    raw = S.get(scores_path(path))
    if raw is None:
        return [("B1", "%s: no %s in study-hub-scores" % (path, scores_path(path)))]
    if hashlib.sha256(raw).hexdigest() != entry.get("provenance_sha256"):
        out.append(("B1", "%s: _provenance.json hash does not match manifest provenance_sha256 (rebuild with sh_page.py)" % path))
    rec = json.loads(raw)
    p, qs = rec["provenance"], rec["questions"]
    built = datetime.fromisoformat(rec["built_at"])
    files = S.tree(grade + "/")
    receipts = {}
    for f in files:
        if f.startswith(grade + "/_receipts/") and f.endswith(".json"):
            try:
                receipts[f.rsplit("/", 1)[1][:-5]] = json.loads(S.get(f))
            except ValueError:
                out.append(("B2", "receipt %s is not JSON" % f))
    # B2
    ids = {s["id"] for s in p["sources"]}
    for q in qs:
        if not q.get("src") and not q.get("inferred"):
            out.append(("B2", "%s: quiz %d question %d has no src and is not inferred" % (path, q["quiz"] + 1, q["n"])))
        elif q.get("src") and q["src"].split("#")[0] not in ids:
            out.append(("B2", "%s: quiz %d question %d src is not a listed source" % (path, q["quiz"] + 1, q["n"])))
    gm = [s["id"] for s in p["sources"] if s["id"].startswith("gmail:")] + [x for x in p.get("results_ingested", []) if x.startswith("gmail:")]
    for g in sorted(set(gm)):
        if g[6:].split("#")[0] not in receipts:
            out.append(("B2", "%s: %s has no receipt in %s/_receipts/ (run tools/ingest_receipts.py)" % (path, g, grade)))
    if check_files:
        for s in p["sources"]:
            if s["id"].startswith("file:"):
                fp = s["id"][5:].split("#")[0]
                if not os.path.isfile(fp):
                    out.append(("B2", "%s: source file is missing on the box: %s" % (path, fp)))
                elif hashlib.sha256(open(fp, "rb").read()).hexdigest() != s.get("sha256"):
                    out.append(("B2", "%s: source file changed since the build (sha256 differs): %s" % (path, fp)))
    # error log
    log_text = (S.get("%s/%s/_error_log.csv" % (grade, subj)) or b"").decode("utf-8")
    rows = read_log(log_text)
    if log_text and rows is not None:
        head = next(csv.reader(io.StringIO(log_text)), [])
        miss = [c for c in LOG_COLUMNS if c not in head]
        if miss:
            out.append(("B5", "%s/%s/_error_log.csv lacks columns: %s" % (grade, subj, ", ".join(miss))))
    notes_attempts = set()
    for r in rows:
        notes_attempts.update(re.findall(r"(?:attempt|correct)=(\S+?\.json)", r.get("notes", "")))
    # B3
    listed = set(p.get("weak_spots_from", [])) | notes_attempts
    for f in files:
        if not f.startswith("%s/%s/" % (grade, subj)) or "/_" in f[len(grade) + 1:]:
            continue
        dt = _attempt_dt(f)
        if dt and dt < built and f not in listed:
            out.append(("B3", "%s: score file %s is not in weak_spots_from or the error log" % (path, f)))
    # B4
    ing = set(p.get("results_ingested", []))
    for rid, rc in sorted(receipts.items()):
        if rc.get("subject") != subj:
            continue
        when = rc.get("datetime")
        before = (datetime.fromisoformat(when) < built) if when else (rc.get("date", "9999") < built.date().isoformat())
        if before and "gmail:" + rid not in ing:
            out.append(("B4", "%s: receipt gmail:%s (%s, %s) is not in results_ingested" % (path, rid, rc.get("title", ""), rc.get("date"))))
    # B5
    retested = {r for q in qs for r in q.get("retests", [])}
    row_ids = {r.get("id") for r in rows}
    for r in rows:
        if (r.get("resolved") or "").strip().lower() == "no" and r.get("id") not in retested:
            out.append(("B5", "%s: error-log row %s is unresolved and no question retests it" % (path, r.get("id"))))
    for rid in sorted(retested - row_ids):
        out.append(("B5", "%s: retests names %s, which is not an error-log row id" % (path, rid)))
    # B6
    prov_cache = {}
    for r in rows:
        if (r.get("resolved") or "").strip().lower() != "yes":
            continue
        rid = r.get("id")
        cites = re.findall(r"correct=(\S+?\.json)", r.get("notes", ""))
        days = {}
        for a in cites:
            body = S.get(a)
            if body is None:
                out.append(("B6", "row %s: cited attempt %s is not in study-hub-scores" % (rid, a)))
                continue
            pay = json.loads(body)
            lesson_dir = "/".join(a.split("/")[:3]) + "/"
            if lesson_dir not in prov_cache:
                pr = S.get(scores_path(lesson_dir))
                prov_cache[lesson_dir] = json.loads(pr)["questions"] if pr else None
            pq = prov_cache[lesson_dir]
            if pq is None:
                out.append(("B6", "row %s: attempt %s comes from a page with no provenance record, so the fact cannot be traced" % (rid, a)))
                continue
            targets = [_norm_q(q["q"]) for q in pq if rid in q.get("retests", [])]
            missed = {_norm_q(m.get("q", "")) for m in pay.get("missed", [])}
            if not targets:
                out.append(("B6", "row %s: attempt %s is from a page with no question that retests this row" % (rid, a)))
            elif all(t in missed for t in targets):
                out.append(("B6", "row %s: attempt %s missed the question for this row" % (rid, a)))
            else:
                days.setdefault(_attempt_day(a, pay), a)
        if len(days) < 2:
            out.append(("B6", "row %s is resolved=yes but has %d correct answer(s) on different PT days (needs 2, cited as correct=<attempt path>)" % (rid, len(days))))
        else:
            try:
                cc = int(r.get("correct_count") or 0)
            except ValueError:
                cc = 0
            if cc < 2:
                out.append(("B6", "row %s: correct_count must be 2 or more" % rid))
            lcd = set(re.findall(r"\d{4}-\d{2}-\d{2}", r.get("last_correct_dates", "")))
            if len(set(days) & lcd) < 2:
                out.append(("B6", "row %s: last_correct_dates must list the PT days of the cited attempts" % rid))
    return out


def main():
    import argparse
    import sh_scores as S
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--pages", nargs="*", help="manifest paths (default: every page not in legacy_provenance)")
    ap.add_argument("--no-files", action="store_true", help="skip the file: sha256 check")
    a = ap.parse_args()
    items = json.load(open(os.path.join(L.REPO, "manifest.json"), encoding="utf-8"))
    errs, warns = public_problems(items)
    for w in warns:
        print("WARNING: " + w)
    todo = [it for it in items if not is_legacy(it.get("path")) and (not a.pages or it.get("path") in a.pages)]
    if todo:
        try:
            S.check_access(write=False)
        except S.ScoresError as ex:
            print("PROVENANCE CHECK FAILED: %s" % ex)
            sys.exit(1)
    for it in todo:
        errs += box_problems(it, S, check_files=not a.no_files)
    if errs:
        print("PROVENANCE CHECK FAILED (%d problems):" % len(errs))
        for r, m in errs:
            print("  %s: %s" % (r, m))
        sys.exit(1)
    print("provenance check passed: %d new pages checked (B1-B6), %d legacy pages" % (len(todo), len(warns)))


if __name__ == "__main__":
    main()
