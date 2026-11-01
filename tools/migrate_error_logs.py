#!/usr/bin/env python3
"""Import the coaches' box error logs into study-hub-scores/G3/<Subject>/_error_log.csv (box only, never in CI).

Usage: python3 tools/migrate_error_logs.py [--dry-run] [SUBJECT=path.csv ...]
       python3 tools/migrate_error_logs.py --scan        (read only: every G3/*/_error_log.csv, counts only)
       python3 tools/migrate_error_logs.py --close-school [--dry-run]
           On each school-subject log (subject_modes in tools/sh_config.json), set resolved=closed on every open row
           that comes from a real school test that already happened (round=school, dated today or earlier). Practice
           rows (mock, game, retest) stay open. Prints the per-subject counts before and after.
Default sources: SS=/workspace/ss/error_log.csv WW=/workspace/ww/error_log.csv
                 Noetic=/workspace/noetic/error_log.csv Kangaroo=/workspace/kangaroo/error_log.csv

No loss: every original column and value is kept (columns the shared format does not have are kept after the shared
ones). Missing shared columns are added: id (stable, made from the row when empty), resolved (default "no"),
correct_count (default "0"), last_correct_dates. The box logs are read only, never changed or deleted.
Re-running is safe: rows already in the score repo (same id) are kept as they are there.

Privacy: every field of every row (box rows, rows already in the score repo, and every other subject's log in the
repo) is scrubbed before it is written: e-mail addresses become [email], and each term of STUDY_HUB_BLOCKLIST and the
first name becomes [name]. The id column is never rewritten (other files cite it); an id with a private term is
reported. --scan reports, per log, how many fields still hold a private term (never the values) and exits 1 if any.
"""
import csv, hashlib, io, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_provenance as P
import sh_scores as S
import sh_lib as L

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def scrubber():
    terms = L.redact_terms(os.environ.get("STUDY_HUB_BLOCKLIST", ""))
    rx = re.compile(r"(?<![A-Za-z0-9])(?:%s)(?:['\u2019]s)?(?![A-Za-z0-9])" % "|".join(re.escape(t) for t in terms), re.I) if terms else None

    def scrub(v):
        v = EMAIL_RE.sub("[email]", v or "")
        return rx.sub("[name]", v) if rx else v
    return scrub, rx


SCRUB, PRIV_RX = scrubber()


def scrub_rows(rows):
    """Scrub every field but id. Returns the number of fields changed."""
    n = 0
    for r in rows:
        for k, v in list(r.items()):
            if k == "id" or not isinstance(v, str):
                continue
            nv = SCRUB(v)
            if nv != v:
                r[k] = nv
                n += 1
    return n


def private_hits(rows):
    """(fields with a private term or an e-mail, ids with one). Counts only."""
    f = i = 0
    for r in rows:
        for k, v in r.items():
            if isinstance(v, str) and ((PRIV_RX and PRIV_RX.search(v)) or EMAIL_RE.search(v)):
                if k == "id":
                    i += 1
                else:
                    f += 1
    return f, i

DEFAULT = {"SS": "/workspace/ss/error_log.csv", "WW": "/workspace/ww/error_log.csv",
           "Noetic": "/workspace/noetic/error_log.csv", "Kangaroo": "/workspace/kangaroo/error_log.csv"}
FILL = {"kid_answer": "picked", "correct_answer": "correct", "question": "question_id", "unit": "chapter",
        "last_correct_dates": "last_correct_date"}


def stable_id(subj, r):
    key = "|".join(r.get(k, "") for k in ("date", "unit", "topic", "skill", "question", "round", "source"))
    d = re.sub(r"[^0-9-]", "", r.get("date", ""))[:10] or "nodate"
    return "%s-%s-%s" % (subj, d, hashlib.sha1(key.encode("utf-8")).hexdigest()[:6])


def convert(subj, text):
    rd = csv.DictReader(io.StringIO(text))
    head = rd.fieldnames or []
    rows = list(rd)
    cols = P.LOG_COLUMNS + [c for c in head if c not in P.LOG_COLUMNS]
    out, seen, made = [], set(), 0
    for r in rows:
        o = {c: (r.get(c) or "") for c in cols}
        for dst, src in FILL.items():
            if not o.get(dst) and r.get(src):
                o[dst] = r[src]
        if not o["id"]:
            o["id"] = stable_id(subj, r)
            made += 1
        base, k = o["id"], 2
        while o["id"] in seen:
            o["id"] = "%s-%d" % (base, k)
            k += 1
        seen.add(o["id"])
        o["resolved"] = o["resolved"] or "no"
        o["correct_count"] = o["correct_count"] or "0"
        for c in head:   # loss check: every original value is still there (scrubbed later), in its own column
            assert (r.get(c) or "") == o[c] or (c == "id" and not r.get(c)) or (c in ("resolved", "correct_count") and not r.get(c)), (subj, c)
        out.append(o)
    return cols, out, made, len(rows)


def to_csv(cols, rows):
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return b.getvalue()


def scan():
    if not PRIV_RX:
        sys.exit("SCAN FAILED: STUDY_HUB_BLOCKLIST is empty (source ~/.study-hub.env)")
    logs = sorted(f for f in S.tree("G3/") if f.endswith("/_error_log.csv"))
    bad = 0
    for f in logs:
        rows = list(csv.DictReader(io.StringIO((S.get(f) or b"").decode("utf-8"))))
        nf, ni = private_hits(rows)
        bad += nf + ni
        print("%-28s rows %3d, fields with a private term or e-mail: %d, ids with one: %d" % (f, len(rows), nf, ni))
    print("scan: %d logs, %d hits" % (len(logs), bad))
    return 1 if bad else 0


def counts(rows):
    from collections import Counter
    c = Counter(P.status(r) or "(empty)" for r in rows)
    return ", ".join("%s %d" % (k, c[k]) for k in sorted(c))


def close_school(dry):
    today = P.now_pt().date().isoformat()
    logs = sorted(f for f in S.tree("G3/") if f.endswith("/_error_log.csv"))
    for f in logs:
        subj = f.split("/")[1]
        rd = csv.DictReader(io.StringIO((S.get(f) or b"").decode("utf-8")))
        rows = list(rd)
        before = counts(rows)
        if P.subject_mode(subj) != "school":
            print("%-8s contest subject, unchanged: %d rows (%s)" % (subj, len(rows), before or "none"))
            continue
        n = 0
        for r in rows:
            d = (r.get("date") or "")[:10]
            if P.status(r) == "no" and (r.get("round") or "").strip().lower() == "school" and d and d <= today:
                r["resolved"] = "closed"
                note = "closed %s: school test %s already happened (pattern input, no re-practice)" % (today, d)
                r["notes"] = (r.get("notes") or "").rstrip("; ") + ("; " if r.get("notes") else "") + note
                n += 1
        how = "dry run" if dry or not n else S.put(f, to_csv(rd.fieldnames, rows), "error log: %s, %d rows closed (school test already happened)" % (subj, n))
        print("%-8s school: %d rows; before: %s; after: %s; closed %d [%s]" % (subj, len(rows), before or "none", counts(rows) or "none", n, how))


def main():
    if "--scan" in sys.argv:
        sys.exit(scan())
    if "--close-school" in sys.argv:
        if "--dry-run" not in sys.argv:
            S.check_access(write=True)
        return close_school("--dry-run" in sys.argv)
    if not PRIV_RX:
        sys.exit("MIGRATION FAILED: STUDY_HUB_BLOCKLIST is empty (source ~/.study-hub.env), so rows cannot be scrubbed")
    dry = "--dry-run" in sys.argv
    srcs = dict(DEFAULT)
    for a in sys.argv[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            srcs[k] = v
    if not dry:
        S.check_access(write=True)
    total, done = 0, set()
    for subj, path in srcs.items():
        if not os.path.exists(path):
            print("%-8s %s: missing, skipped" % (subj, path))
            continue
        cols, rows, made, n_box = convert(subj, open(path, encoding="utf-8").read())
        dst = "G3/%s/_error_log.csv" % subj
        old = S.get(dst) if not dry else None
        kept = added = 0
        if old:
            rd = csv.DictReader(io.StringIO(old.decode("utf-8")))
            have = list(rd)
            cols = list(rd.fieldnames) + [c for c in cols if c not in rd.fieldnames]
            ids = {r["id"] for r in have}
            new = [r for r in rows if r["id"] not in ids]
            kept, added = len(have), len(new)
            rows = have + new
        else:
            added = len(rows)
        scrubbed = scrub_rows(rows)
        text = to_csv(cols, rows)
        check = list(csv.DictReader(io.StringIO(text)))
        assert len(check) == len(rows) and len({r["id"] for r in check}) == len(check), "ids must be unique"
        assert private_hits(check)[0] == 0, "a private term is still in a field"
        how = "dry run" if dry else S.put(dst, text, "error log: import %s from the box log (%d rows)" % (subj, n_box))
        total += len(rows)
        done.add(dst)
        print("%-8s box rows %3d -> %s rows %3d (kept %d, added %d, new ids %d, %d columns, %d fields scrubbed) [%s]"
              % (subj, n_box, dst, len(rows), kept, added, made, len(cols), scrubbed, how))
    # every other error log in the score repo gets the same scrub
    for dst in ([] if dry else sorted(f for f in S.tree("G3/") if f.endswith("/_error_log.csv") and f not in done)):
        rd = csv.DictReader(io.StringIO((S.get(dst) or b"").decode("utf-8")))
        rows = list(rd)
        scrubbed = scrub_rows(rows)
        how = S.put(dst, to_csv(rd.fieldnames or P.LOG_COLUMNS, rows), "error log: scrub private terms (%d fields)" % scrubbed) if scrubbed else "same"
        total += len(rows)
        print("%-8s %s rows %3d (%d fields scrubbed) [%s]" % ("", dst, len(rows), scrubbed, how))
    print("done: %d rows in the score repo error logs" % total)


if __name__ == "__main__":
    try:
        main()
    except S.ScoresError as ex:
        sys.exit("MIGRATION FAILED: %s" % ex)
