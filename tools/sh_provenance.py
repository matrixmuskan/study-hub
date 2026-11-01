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
    B5  (school subjects: only open rows after the last real school test, the current prep window; closed rows never
        count. Contest subjects: every open row.) Re-test rotation over the open rows (resolved=no) of the error log, using the build history in
        study-hub-scores (G3/<Subject>/_builds/):
        (a) the page re-tests at least min(15, open rows), chosen oldest-first: the open rows that were re-tested
            least recently (never first), then by row date, then by id;
        (b) every open row is re-tested at least once in any 3 consecutive builds of the subject: a row that was open
            in the last 2 builds and re-tested in neither must be re-tested now;
        (c) a row that was missed again since the last build (a later attempt missed a question that re-tests it, or
            an "attempt=" note after the last build) must be re-tested now;
        and every retests id is a real row. "python3 tools/sh_provenance.py plan G3/<Subject>" prints what to re-test.
    F1  school subjects (tools/sh_config.json "subject_modes" = school): a page with a mock cites patterns_from (past school
        receipts of that teacher and subject, as gmail:<id>). sh_page.py prints a format and difficulty comparison of
        the mock with those receipts (question count, question types, option count, stem length), and publish.sh
        warns when it is out of range (F1_TOL). Citing is required (sh_page.py, B2); the range is a warning.
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
B5_MIN = 15        # (a) at least min(B5_MIN, open rows) re-tests per page
B5_WINDOW = 3      # (b) every open row re-tested at least once in any B5_WINDOW consecutive builds
# F1 tolerance: the mock against the mean of the cited receipts
F1_TOL = {"count_rel": 0.20, "count_abs": 3,     # question count within 20% or 3 questions, whichever is larger
          "mc_share": 0.15,                      # share of multiple-choice questions within 15 points
          "options": 0.5,                        # mean options per multiple-choice question within 0.5
          "stem_rel": 0.40}                      # mean words per question within 40% (difficulty proxy)
STAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{6})-[a-z]+-[a-z0-9]{4}\.json$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,80}$")
# Source ids. school-app:<message id> is the neutral label for a message from the school's parent app: the record
# never holds that app's URL or name (they are private words, see STUDY_HUB_BLOCKLIST).
SRC_ID_RE = re.compile(r"^(file|gmail|paper|url|handoff|sheet|school-app):\S+$")


def blocklist():
    """STUDY_HUB_BLOCKLIST from the environment, else from ~/.study-hub.env (box). Empty in CI."""
    bl = os.environ.get("STUDY_HUB_BLOCKLIST", "")
    envf = os.path.expanduser("~/.study-hub.env")
    if not bl and os.path.exists(envf):
        for line in open(envf, encoding="utf-8"):
            if line.startswith("STUDY_HUB_BLOCKLIST="):
                bl = line.split("=", 1)[1].strip().strip("'\"")
    return bl


def private_source_problems(srcs, qsrcs=(), bl=None):
    """A source id or question src must not name a private word (for example the school app's domain). The word itself
    is never printed. Use school-app:<message id> instead of the app's URL."""
    terms = [t for t in (blocklist() if bl is None else bl).split("|") if t.strip()]
    if not terms:
        return []
    rx = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(t.strip()) for t in terms), re.I)
    out = []
    for i, s in enumerate(srcs, 1):
        sid = s.get("id", "") if isinstance(s, dict) else ""
        if rx.search(sid) or (isinstance(s, dict) and rx.search(str(s.get("title", "")))):
            out.append("source %d: its id or title names a private word (STUDY_HUB_BLOCKLIST). For a school-app message "
                       "use school-app:<message id> (see CONTRIBUTING-BOTS.md 11.1)" % i)
    if any(rx.search(x or "") for x in qsrcs):
        out.append("a question src names a private word (STUDY_HUB_BLOCKLIST); use the school-app:<message id> source id")
    return out


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
                            "id": q.get("id") or "q%d-%d" % (qi + 1, n),
                            "q": q.get("q", ""), "topic": q.get("topic", ""), "src": q.get("src", ""),
                            "inferred": q.get("inferred") is True, "retests": list(q.get("retests") or []),
                            "type": "mc" if q.get("options") else "text", "n_options": len(q.get("options") or [])})
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
        if not SRC_ID_RE.match(sid):
            out.append("source %d: id must start with file:, gmail:, paper:, url:, sheet:, handoff: or school-app:" % (i + 1))
            continue
        if s.get("kind") not in SOURCE_KINDS:
            out.append("source %s: kind must be one of %s" % (sid, ", ".join(SOURCE_KINDS)))
        if sid.startswith("file:") and not re.fullmatch(r"[0-9a-f]{64}", str(s.get("sha256", ""))):
            out.append("source %s: a file: source needs its sha256 (sha256sum <file>)" % sid)
        if sid in ids:
            out.append("source %s is listed twice" % sid)
        ids.add(sid)
    out += private_source_problems(srcs, [q["src"] for q in qs])
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
    if subject_mode(c.get("subject")) == "school" and any(q["kind"] == "mock" for q in qs):
        pf = p.get("patterns_from")
        if not isinstance(pf, list) or not pf:
            out.append("F1: a school-subject mock needs provenance.patterns_from: past school receipts of this teacher and "
                       "subject (gmail:<id>), so the mock can match their format")
        elif not all(isinstance(x, str) and re.match(r"^gmail:[0-9a-f]{8,}$", x) for x in pf):
            out.append("F1: patterns_from entries must look like gmail:<id>")
    if qs and c.get("log", True) is False:
        out.append("a page with a quiz must log scores (remove \"log\": false)")
    return out


def record_bytes(c, rel_dir, built_at, error_log_sha256="", open_rows=None, build_id=""):
    p = dict(c["provenance"])
    p.setdefault("results_ingested", [])
    p.setdefault("weak_spots_from", [])
    p["error_log"] = "scores:%s/%s/_error_log.csv" % (c["grade"], c["subject"])
    p["error_log_sha256"] = error_log_sha256
    rec = {"v": 1, "page": rel_dir, "built_at": built_at, "added_by": c.get("added_by", ""), "provenance": p,
           "questions": questions_of(c), "open_rows": sorted(open_rows or []), "build_id": build_id}
    return (json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def format_stats(items):
    """items: list of {"type": "mc"|"text", "n_options": n, "q": text}."""
    n = len(items)
    mc = [i for i in items if i["type"] == "mc"]
    words = [len(re.findall(r"[A-Za-z0-9']+", i.get("q") or "")) for i in items]
    return {"n": n, "mc_share": (len(mc) / n) if n else 0.0,
            "options": (sum(i["n_options"] for i in mc) / len(mc)) if mc else 0.0,
            "stem_words": (sum(words) / n) if n else 0.0}


def receipt_items(rc):
    out = []
    for it in rc.get("items", []):
        if it.get("options"):
            out.append({"type": "mc", "n_options": len(it["options"]), "q": it.get("q", "")})
        elif it.get("picked") is not None:
            out.append({"type": "text", "n_options": 0, "q": it.get("q", "")})
    return out


def format_compare(questions, receipts):
    """Mock questions (from questions_of) against the cited receipts. Returns (lines, problems)."""
    mock = [q for q in questions if q.get("kind") == "mock"]
    mine = format_stats([{"type": q.get("type") or ("mc" if q.get("n_options") else "text"), "n_options": q.get("n_options", 0),
                          "q": q.get("q", "")} for q in mock])
    real = [format_stats(receipt_items(r)) for r in receipts if receipt_items(r)]
    if not real:
        return ["format: no cited receipt has questions to compare"], ["no cited receipt has questions"]
    avg = {k: sum(r[k] for r in real) / len(real) for k in real[0]}
    t = F1_TOL
    probs = []
    if abs(mine["n"] - avg["n"]) > max(t["count_abs"], t["count_rel"] * avg["n"]):
        probs.append("question count %d, school tests %.0f" % (mine["n"], avg["n"]))
    if abs(mine["mc_share"] - avg["mc_share"]) > t["mc_share"]:
        probs.append("multiple choice %.0f%%, school tests %.0f%%" % (100 * mine["mc_share"], 100 * avg["mc_share"]))
    if avg["options"] and abs(mine["options"] - avg["options"]) > t["options"]:
        probs.append("options per question %.1f, school tests %.1f" % (mine["options"], avg["options"]))
    if avg["stem_words"] and abs(mine["stem_words"] - avg["stem_words"]) > t["stem_rel"] * avg["stem_words"]:
        probs.append("words per question %.0f, school tests %.0f" % (mine["stem_words"], avg["stem_words"]))
    lines = ["format vs %d school test(s): %-22s mock  school" % (len(real), ""),
             "  questions               %5d  %6.0f" % (mine["n"], avg["n"]),
             "  multiple choice         %4.0f%%  %5.0f%%" % (100 * mine["mc_share"], 100 * avg["mc_share"]),
             "  options per question    %5.1f  %6.1f" % (mine["options"], avg["options"]),
             "  words per question      %5.0f  %6.0f   (difficulty proxy)" % (mine["stem_words"], avg["stem_words"])]
    return lines, probs


def f1_report(rec, S, grade="G3"):
    """(lines, problems) for a record of a school subject with a mock, or ([], []) when F1 does not apply."""
    subj = rec["page"].split("/")[1]
    if rec.get("attached") or subject_mode(subj) != "school" or not any(q.get("kind") == "mock" for q in rec["questions"]):
        return [], []
    rcs = []
    for g in rec["provenance"].get("patterns_from", []):
        b = S.get("%s/_receipts/%s.json" % (grade, g[6:]))
        if b:
            rcs.append(json.loads(b))
    lines, probs = format_compare(rec["questions"], rcs)
    # closed rows (school tests that already happened) are the pattern input: their trap types and question styles
    log = S.get("%s/%s/_error_log.csv" % (grade, subj))
    if log:
        pr, traps, styles = pattern_summary(read_log(log.decode("utf-8")))
        if pr:
            lines.append("patterns from %d closed rows (past school tests): traps %s; styles %s"
                         % (len(pr), ", ".join("%s (%d)" % t for t in traps[:5]), ", ".join("%s (%d)" % t for t in styles[:5])))
    return lines, probs


def manifest_fields(rec_bytes):
    rec = json.loads(rec_bytes)
    qs = rec["questions"]
    return {"provenance_sha256": hashlib.sha256(rec_bytes).hexdigest(), "n_sources": len(rec["provenance"]["sources"]),
            "n_inferred": sum(1 for q in qs if q["inferred"]), "n_questions": len(qs),
            "n_retests": len({r for q in qs for r in q["retests"]}), "built_at": rec["built_at"]}


def scores_path(rel_dir):
    return rel_dir.rstrip("/") + "/_provenance.json"


def build_copy_path(rel_dir, built_at):
    """Immutable copy of each build, so the B5 history survives a rebuild of the same lesson."""
    g, subj, lesson = rel_dir.strip("/").split("/")[:3]
    stamp = re.sub(r"[^0-9T]", "", datetime.fromisoformat(built_at).astimezone(PT).strftime("%Y-%m-%dT%H%M%S"))
    return "%s/%s/_builds/%s-%s.json" % (g, subj, stamp, lesson)


STATUSES = ("no", "yes", "void", "closed")


def subject_mode(subj):
    """'school' or 'contest' (tools/sh_config.json subject_modes). An unknown subject counts as school."""
    return (L.CFG.get("subject_modes") or {}).get(subj, "school")


def status(r):
    return (r.get("resolved") or "").strip().lower()


def last_school_test(S, grade, subj, rows, built, files=None):
    """Date (YYYY-MM-DD) of the last real school test of the subject on or before 'built': the newest ingested
    receipt of the subject, or the newest error-log row from a school test (round=school). None if there is none."""
    day = built.date().isoformat() if hasattr(built, "date") else str(built)[:10]
    dates = [(r.get("date") or "")[:10] for r in rows if (r.get("round") or "").strip().lower() == "school"]
    files = files if files is not None else S.tree(grade + "/")
    for f in files:
        if f.startswith(grade + "/_receipts/") and f.endswith(".json"):
            try:
                rc = json.loads(S.get(f))
            except (ValueError, TypeError):
                continue
            if rc.get("subject") == subj:
                dates.append((rc.get("date") or "")[:10])
    dates = [d for d in dates if d and d <= day]
    return max(dates) if dates else None


def b5_rows(S, grade, subj, rows, built, files=None):
    """(rows B5 counts, window start date or None). School: open rows dated after the last real test (the current
    prep window); closed rows never count. Contest: every open row (cumulative)."""
    opened = [r for r in rows if status(r) == "no" and r.get("id")]
    if subject_mode(subj) != "school":
        return opened, None
    lt = last_school_test(S, grade, subj, rows, built, files)
    if lt is None:
        return opened, None
    return [r for r in opened if (r.get("date") or "")[:10] > lt], lt


def pattern_rows(rows):
    """Closed rows (school test already happened): pattern input for F1 and patterns_from, never re-practice."""
    return [r for r in rows if status(r) == "closed" and r.get("id")]


def pattern_summary(rows):
    """Trap types and question styles of the closed rows, most common first."""
    from collections import Counter
    pr = pattern_rows(rows)
    traps = Counter((r.get("error_type") or "").strip() or "(no error_type)" for r in pr)
    styles = Counter((r.get("skill") or "").strip() or "(no skill)" for r in pr)
    return pr, traps.most_common(), styles.most_common()


def open_row_ids(rows):
    return [r.get("id") for r in rows if (r.get("resolved") or "").strip().lower() == "no" and r.get("id")]


def history(S, grade, subj, files=None):
    """Every recorded build of the subject (from _builds copies and the current _provenance.json files), oldest first."""
    files = files if files is not None else S.tree("%s/%s/" % (grade, subj))
    recs = {}
    for f in files:
        if not f.startswith("%s/%s/" % (grade, subj)):
            continue
        if not ((f.startswith("%s/%s/_builds/" % (grade, subj)) and f.endswith(".json")) or f.endswith("/_provenance.json")):
            continue
        try:
            r = json.loads(S.get(f))
            recs[(r["page"], r["built_at"])] = r
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(recs.values(), key=lambda r: datetime.fromisoformat(r["built_at"]))


def _missed_rows(S, files, grade, subj, after, before, prov_cache):
    """Row ids missed in attempts between two build times: the attempt's page has a question that re-tests the row,
    and the attempt lists that question in 'missed'."""
    out = {}
    for f in files:
        if not f.startswith("%s/%s/" % (grade, subj)) or "/_" in f[len(grade) + 1:]:
            continue
        dt = _attempt_dt(f)
        if not dt or not (after < dt < before):
            continue
        try:
            pay = json.loads(S.get(f))
        except (ValueError, TypeError):
            continue
        lesson_dir = "/".join(f.split("/")[:3]) + "/"
        if lesson_dir not in prov_cache:
            pr = S.get(scores_path(lesson_dir))
            prov_cache[lesson_dir] = json.loads(pr)["questions"] if pr else []
        keys = _missed_keys(pay)
        for q in prov_cache[lesson_dir]:
            if _q_missed(q, keys):
                for rid in q.get("retests", []):
                    out.setdefault(rid, f)
    return out


def b5_plan(S, grade, subj, rows, built, page=None, files=None):
    """What B5 needs from a build at time 'built' (datetime). Returns a dict with the open rows, the oldest-first
    list (a), the rows due by the 3-build window (b), and the rows missed again since the last build (c)."""
    files = files if files is not None else S.tree(grade + "/")
    prior = [r for r in history(S, grade, subj, files)
             if datetime.fromisoformat(r["built_at"]) < built and not (page and r["page"] == page and r["built_at"] == built.isoformat())]
    opened, window_from = b5_rows(S, grade, subj, rows, built, files)
    all_open = [r["id"] for r in rows if status(r) == "no" and r.get("id")]
    last = {}
    for rec in prior:
        for q in rec.get("questions", []):
            for rid in q.get("retests", []):
                last[rid] = max(last.get(rid, ""), rec["built_at"])
    order = sorted(opened, key=lambda r: (last.get(r["id"], ""), r.get("date") or "", r["id"]))
    k = min(B5_MIN, len(opened))
    oldest = [r["id"] for r in order[:k]]
    due = []
    win = prior[-(B5_WINDOW - 1):] if B5_WINDOW > 1 else []
    if len(win) == B5_WINDOW - 1:
        for r in opened:
            present = all((r["id"] in rec["open_rows"]) if "open_rows" in rec else ((r.get("date") or "") <= rec["built_at"][:10])
                          for rec in win)
            hit = any(r["id"] in q.get("retests", []) for rec in win for q in rec.get("questions", []))
            if present and not hit:
                due.append(r["id"])
    again = {}
    if prior:
        lb = datetime.fromisoformat(prior[-1]["built_at"])
        again = _missed_rows(S, files, grade, subj, lb, built, {})
        for r in opened:
            for a in re.findall(r"attempt=(\S+?\.json)", r.get("notes", "")):
                dt = _attempt_dt(a)
                if dt and lb < dt < built:
                    again.setdefault(r["id"], a)
        open_ids = {r["id"] for r in opened}
        again = {k2: v for k2, v in again.items() if k2 in open_ids}
    return {"open": [r["id"] for r in order], "k": k, "oldest": oldest, "due": due, "again": again,
            "builds": len(prior), "last_build": prior[-1]["built_at"] if prior else None,
            "mode": subject_mode(subj), "window_from": window_from,
            "outside": [x for x in all_open if x not in {r["id"] for r in opened}],
            "patterns": [r["id"] for r in pattern_rows(rows)]}


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


def _missed_keys(pay):
    """What an attempt lists as missed: item ids (privacy v3 logger) and, for older attempts, normalized question text."""
    out = set()
    for m in pay.get("missed", []):
        if m.get("id"):
            out.add("id:" + str(m["id"]))
        if m.get("q"):
            out.add("q:" + _norm_q(m["q"]))
    return out


def _q_missed(q, keys):
    return ("id:" + q["id"]) in keys if q.get("id") and any(k.startswith("id:") for k in keys) else ("q:" + _norm_q(q["q"])) in keys


def _norm_q(s):
    s = re.sub(r"\[name\]", "", s or "", flags=re.I)
    fn = L.kid_first_name().lower()
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
    for g in p.get("patterns_from", []):
        rc = receipts.get(g[6:].split("#")[0]) if g.startswith("gmail:") else None
        if rc is not None and rc.get("subject") != subj:
            out.append(("B2", "%s: patterns_from %s is a %s receipt, not %s" % (path, g, rc.get("subject") or "?", subj)))
    gm = [s["id"] for s in p["sources"] if s["id"].startswith("gmail:")] + [x for x in p.get("results_ingested", []) if x.startswith("gmail:")] \
        + [x for x in p.get("patterns_from", []) if x.startswith("gmail:")]
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
    # An attached record (sh_provenance.py attach) describes a page that existed before the rules: B3, B4 and the B5
    # rotation are rules for new builds, so they do not apply. B1, B2, the retests ids and B6 still do.
    retested = {r for q in qs for r in q.get("retests", [])}
    row_ids = {r.get("id") for r in rows}
    if not rec.get("attached"):
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
        # B5 (rotation)
        retested = {r for q in qs for r in q.get("retests", [])}
        row_ids = {r.get("id") for r in rows}
        plan = b5_plan(S, grade, subj, rows, built, page=path, files=files)
        hit = retested & set(plan["open"])
        if len(hit) < plan["k"]:
            out.append(("B5", "%s: re-tests %d of %d open rows; needs at least %d (min(%d, open rows))"
                        % (path, len(hit), len(plan["open"]), plan["k"], B5_MIN)))
        miss_a = [x for x in plan["oldest"] if x not in retested]
        if miss_a:
            out.append(("B5", "%s: (a) the %d most overdue open rows must be re-tested (oldest-first); missing: %s"
                        % (path, plan["k"], ", ".join(miss_a[:10]) + (" ..." if len(miss_a) > 10 else ""))))
        for x in plan["due"]:
            if x not in retested:
                out.append(("B5", "%s: (b) row %s was open in the last %d builds and re-tested in neither; re-test it now"
                            % (path, x, B5_WINDOW - 1)))
        for x, a in sorted(plan["again"].items()):
            if x not in retested:
                out.append(("B5", "%s: (c) row %s was missed again since the last build (%s); re-test it now" % (path, x, a)))
    for r in rows:
        if status(r) not in STATUSES:
            out.append(("B5", "%s/%s/_error_log.csv row %s: resolved must be one of %s" % (grade, subj, r.get("id"), ", ".join(STATUSES))))
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
            targets = [q for q in pq if rid in q.get("retests", [])]
            keys = _missed_keys(pay)
            if not targets:
                out.append(("B6", "row %s: attempt %s is from a page with no question that retests this row" % (rid, a)))
            elif all(_q_missed(t, keys) for t in targets):
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


def _qnorm(s):
    s = re.sub(r"^\s*\[[^\]]*\]\s*", "", s or "")            # page prefix like "[Spring 2024 paper, Question 1]"
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def map_logger_ids(questions, page_ids):
    """Logger id (q<quiz>-<n>, as sh_page.py and sh.js make it) for each fragment question, matched to the page's
    sh-data questions by text, in order. (ids, problems). A question that already has a page id keeps it."""
    known = {x[2] for x in page_ids}
    used, ids, out = set(), [], []
    for k, q in enumerate(questions, 1):
        if q.get("id") in known and q["id"] not in used:
            used.add(q["id"]); ids.append(q["id"]); continue
        t = _qnorm(q.get("q", ""))
        hit = next((x for x in page_ids if x[2] not in used and t and _qnorm(x[3]) == t), None) or \
            next((x for x in page_ids if x[2] not in used and len(t) >= 12 and (t in _qnorm(x[3]) or _qnorm(x[3]) in t)), None)
        if hit is None:
            out.append("question %s: its text matches no question on the page, so it has no logger id" % q.get("id", k))
            ids.append(str(q.get("id") or ""))
            continue
        used.add(hit[2]); ids.append(hit[2])
    return ids, out


def attach_record(frag, entry, S, built_at, check_files=True, drop_closed=True, page_ids=None):
    """(record bytes, problems) for a provenance fragment of a page that already exists (not built by sh_page.py).
    frag: {"page", "provenance": {sources, results_ingested, weak_spots_from}, "questions": [{id, q, src | inferred,
    retests}], optional "prompts"}. page_ids: L.logger_ids() of the page; each question then gets the id the logger
    sends (q<quiz>-<n>), so logged misses join to their sources."""
    path = frag.get("page", "")
    grade, subj = path.split("/")[:2]
    p = dict(frag.get("provenance") or {})
    out = []
    srcs = p.get("sources") or []
    if not srcs:
        out.append("provenance.sources needs at least 1 source")
    ids = set()
    for k, x in enumerate(srcs, 1):
        sid = x.get("id", "")
        if not SRC_ID_RE.match(sid):
            out.append("source %d: bad id" % k)
        if sid.startswith("file:") and not re.fullmatch(r"[0-9a-f]{64}", x.get("sha256", "")):
            out.append("source %d: a file: source needs its sha256" % k)
        ids.add(sid)
    out += private_source_problems(srcs, [q.get("src", "") for q in frag.get("questions") or []])
    log0 = S.get("%s/%s/_error_log.csv" % (grade, subj)) or b""
    closed = {r.get("id") for r in (read_log(log0.decode("utf-8")) or []) if status(r) == "closed"} if drop_closed else set()
    dropped = set()
    qs = []
    lids = None
    if page_ids:
        lids, mp = map_logger_ids(frag.get("questions") or [], page_ids)
        out += mp
    for n, q in enumerate(frag.get("questions") or [], 1):
        inf = q.get("inferred") is True
        src = q.get("src", "")
        if not inf and (not src or src.split("#")[0] not in ids):
            out.append("question %s: src is missing or not a listed source" % q.get("id", n))
        qs.append({"quiz": 0, "kind": "mock", "section": "", "n": n, "id": lids[n - 1] if lids else str(q.get("id") or "q1-%d" % n), "q": q.get("q", ""),
                   "topic": q.get("fact", ""), "src": "" if inf else src, "inferred": inf,
                   "retests": [x for x in (q.get("retests") or []) if x not in closed], "type": "unknown", "n_options": 0})
        dropped |= {x for x in (q.get("retests") or []) if x in closed}
    if not qs:
        out.append("no questions")
    elif sum(q["inferred"] for q in qs) > 0.2 * len(qs):
        out.append("more than 20%% of the questions are inferred (P2)")
    p.setdefault("results_ingested", [])
    p.setdefault("weak_spots_from", [])
    log = S.get("%s/%s/_error_log.csv" % (grade, subj)) or b""
    rows = read_log(log.decode("utf-8")) or []
    p["error_log"] = "scores:%s/%s/_error_log.csv" % (grade, subj)
    p["error_log_sha256"] = hashlib.sha256(log).hexdigest() if log else ""
    rec = {"v": 1, "page": path, "built_at": built_at, "attached": True, "dropped_closed_retests": sorted(dropped), "added_by": entry.get("added_by", ""),
           "provenance": p, "questions": qs, "prompts": frag.get("prompts") or [],
           "open_rows": sorted(r["id"] for r in rows if (r.get("resolved") or "").strip().lower() == "no")}
    raw = (json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    if not out:
        tmp = dict(entry, **manifest_fields(raw))
        orig_get = S.get
        S.get = lambda f, _o=orig_get: raw if f == scores_path(path) else _o(f)
        try:
            out += ["%s: %s" % (r, m) for r, m in box_problems(tmp, S, check_files=check_files)]
        finally:
            S.get = orig_get
    return raw, out


def main():
    import argparse
    import sh_scores as S
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "plan", "attach", "config-diff"])
    ap.add_argument("subject", nargs="?", help="for plan: G3/<Subject>; for attach: the fragment .json")
    ap.add_argument("--pages", nargs="*", help="manifest paths (default: every page not in legacy_provenance)")
    ap.add_argument("--no-files", action="store_true", help="skip the file: sha256 check")
    a = ap.parse_args()
    if a.cmd == "config-diff":
        r, msg = config_diff()
        print(msg)
        sys.exit(0 if r in ("clean", "stage") else 1)
    if a.cmd == "plan":
        if not a.subject or a.subject.count("/") != 1:
            sys.exit("usage: sh_provenance.py plan G3/<Subject>")
        grade, subj = a.subject.split("/")
        try:
            S.check_access(write=False)
            rows = read_log((S.get("%s/%s/_error_log.csv" % (grade, subj)) or b"").decode("utf-8"))
            pl = b5_plan(S, grade, subj, rows, now_pt())
        except S.ScoresError as ex:
            sys.exit("PLAN FAILED: %s" % ex)
        need = list(dict.fromkeys(pl["oldest"] + pl["due"] + sorted(pl["again"])))
        if pl["mode"] == "school":
            print("%s: school subject; prep window after the last real test (%s): %d open rows count for B5, %d earlier builds (last %s)"
                  % (a.subject, pl["window_from"] or "none yet", len(pl["open"]), pl["builds"], pl["last_build"] or "none"))
            if pl["outside"]:
                print("open rows from before the window (B5 ignores them; set closed if their test happened): %s" % ", ".join(pl["outside"]))
        else:
            print("%s: contest subject (cumulative): %d open rows, %d earlier builds (last %s)"
                  % (a.subject, len(pl["open"]), pl["builds"], pl["last_build"] or "none"))
        print("(a) oldest-first, at least %d: %s" % (pl["k"], ", ".join(pl["oldest"]) or "none"))
        print("(b) due by the %d-build window: %s" % (B5_WINDOW, ", ".join(pl["due"]) or "none"))
        print("(c) missed again since the last build: %s" % (", ".join(sorted(pl["again"])) or "none"))
        print("put these ids in 'retests' (%d): %s" % (len(need), json.dumps(need)))
        pr, traps, styles = pattern_summary(rows)
        print("patterns (closed rows: school test already happened; pattern input for the mock and patterns_from, not re-practice): %d" % len(pr))
        if pr:
            print("  trap types: %s" % ", ".join("%s (%d)" % t for t in traps))
            print("  question styles: %s" % ", ".join("%s (%d)" % t for t in styles))
            print("  rows: %s" % ", ".join(r["id"] for r in pr))
        return
    if a.cmd == "attach":
        return attach_main(a, S)
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
        raw = S.get(scores_path(it["path"]))
        if raw:
            lines, probs = f1_report(json.loads(raw), S)
            for pr in probs:
                print("WARNING: F1 %s: mock format is out of range: %s" % (it["path"], pr))
    if errs:
        print("PROVENANCE CHECK FAILED (%d problems):" % len(errs))
        for r, m in errs:
            print("  %s: %s" % (r, m))
        sys.exit(1)
    print("provenance check passed: %d new pages checked (B1-B6), %d legacy pages" % (len(todo), len(warns)))


def config_diff(repo=None):
    """For publish.sh: compare tools/sh_config.json with HEAD. ("clean", msg) if it is unchanged; ("stage", msg) if the
    only change is pages taken out of legacy_provenance (what attach does) and each of them has provenance_sha256 in the
    working manifest.json, so publish.sh commits it with the manifest; ("dirty", msg) for any other change, which must
    go through a PR."""
    import subprocess
    repo = repo or L.REPO
    cp = os.path.join(repo, "tools", "sh_config.json")
    head = subprocess.run(["git", "-C", repo, "show", "HEAD:tools/sh_config.json"], capture_output=True, text=True)
    if head.returncode != 0:
        return "clean", "config: tools/sh_config.json is not in HEAD yet"
    old, new = json.loads(head.stdout), json.load(open(cp, encoding="utf-8"))
    if old == new:
        return "clean", "config: tools/sh_config.json unchanged"
    lo, ln = old.get("legacy_provenance", []), new.get("legacy_provenance", [])
    rest_o = {k: v for k, v in old.items() if k != "legacy_provenance"}
    rest_n = {k: v for k, v in new.items() if k != "legacy_provenance"}
    if rest_o != rest_n or [x for x in lo if x in ln] != ln or len(ln) >= len(lo):
        return "dirty", ("CONFIG CHANGED: tools/sh_config.json has uncommitted changes other than pages taken out of "
                         "legacy_provenance. Those go through a PR (git diff tools/sh_config.json)")
    gone = [x for x in lo if x not in ln]
    man = {it.get("path"): it for it in json.load(open(os.path.join(repo, "manifest.json"), encoding="utf-8"))}
    bad = [x for x in gone if not re.fullmatch(r"[0-9a-f]{64}", str((man.get(x) or {}).get("provenance_sha256", "")))]
    if bad:
        return "dirty", ("CONFIG CHANGED: %s left legacy_provenance but has no provenance_sha256 in manifest.json "
                         "(run sh_provenance.py attach again)" % ", ".join(bad))
    return "stage", "config: legacy_provenance shrank by %s (attach); publish.sh commits it" % ", ".join(gone)


def attach_main(a, S):
    """Write the record of an existing page to study-hub-scores, add the hash and counts to its manifest entry, and take
    it out of legacy_provenance. Box only. The page HTML does not change."""
    if not a.subject or not os.path.isfile(a.subject):
        sys.exit("usage: sh_provenance.py attach <fragment.json>")
    _lock = L.mirror_lock(L.default_src(), "sh_provenance.py attach " + a.subject)   # attach edits manifest and config
    frag = json.load(open(a.subject, encoding="utf-8"))
    mp = os.path.join(L.REPO, "manifest.json")
    items = json.load(open(mp, encoding="utf-8"))
    ent = [it for it in items if it.get("path") == frag.get("page")]
    if len(ent) != 1:
        sys.exit("ATTACH FAILED: %s is not one manifest page" % frag.get("page"))
    old = S.get(scores_path(frag["page"]))
    re_attach = bool(old) and json.loads(old).get("attached") is True
    if not is_legacy(frag["page"]) and not re_attach:
        sys.exit("ATTACH FAILED: %s is not in legacy_provenance; attach is only for pages built before the rules "
                 "(a new page is built with sh_page.py)" % frag["page"])
    try:
        S.check_access(write=True)
        pf = os.path.join(L.default_src(), frag["page"], "index.html")
        page_ids = L.logger_ids(open(pf, encoding="utf-8").read()) if os.path.exists(pf) else None
        if page_ids is None:
            print("attach: WARNING: %s has no sh-data in the mirror, so the fragment ids are kept as they are" % frag["page"])
        raw, probs = attach_record(frag, ent[0], S, now_pt().isoformat(timespec="seconds"), check_files=not a.no_files,
                                   page_ids=page_ids)
        if probs:
            print("ATTACH FAILED (%d problems):" % len(probs))
            for m in probs:
                print("  " + m)
            sys.exit(1)
        how = S.put(scores_path(frag["page"]), raw, "provenance (attached): %s" % frag["page"])
    except S.ScoresError as ex:
        sys.exit("ATTACH FAILED: %s" % ex)
    ent[0].update(manifest_fields(raw))
    open(mp, "w", encoding="utf-8").write(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
    cp = os.path.join(L.REPO, "tools", "sh_config.json")   # text edit, so the file keeps its layout
    t = open(cp, encoding="utf-8").read()
    t2 = re.sub(r'\n[ \t]*"%s",?(?=\n)' % re.escape(frag["page"]), "", t, count=1)
    t2 = re.sub(r',(\n[ \t]*\])', r"\1", t2)
    if json.loads(t2).get("legacy_provenance") != [x for x in json.loads(t).get("legacy_provenance", []) if x != frag["page"]]:
        sys.exit("ATTACH FAILED: could not edit legacy_provenance in tools/sh_config.json")
    open(cp, "w", encoding="utf-8").write(t2)
    f = manifest_fields(raw)
    print("attached %s: record %s in study-hub-scores; %d sources, %d questions, %d inferred, %d retests; manifest updated, "
          "removed from legacy_provenance" % (frag["page"], how, f["n_sources"], f["n_questions"], f["n_inferred"], f.get("n_retests", 0)))
    print("  next: tools/publish.sh commits manifest.json and the legacy_provenance change in tools/sh_config.json together")
    dr = json.loads(raw).get("dropped_closed_retests") or []
    if dr:
        print("  closed rows taken out of retests (school test already happened): %d: %s" % (len(dr), ", ".join(dr)))


if __name__ == "__main__":
    main()
