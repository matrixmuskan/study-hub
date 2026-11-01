#!/usr/bin/env python3
"""Import the coaches' box error logs into study-hub-scores/G3/<Subject>/_error_log.csv (box only, never in CI).

Usage: python3 tools/migrate_error_logs.py [--dry-run] [SUBJECT=path.csv ...]
Default sources: SS=/workspace/ss/error_log.csv WW=/workspace/ww/error_log.csv
                 Noetic=/workspace/noetic/error_log.csv Kangaroo=/workspace/kangaroo/error_log.csv

No loss: every original column and value is kept (columns the shared format does not have are kept after the shared
ones). Missing shared columns are added: id (stable, made from the row when empty), resolved (default "no"),
correct_count (default "0"), last_correct_dates. The box logs are read only, never changed or deleted.
Re-running is safe: rows already in the score repo (same id) are kept as they are there.
"""
import csv, hashlib, io, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_provenance as P
import sh_scores as S

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
        for c in head:   # loss check: every original value is still there, in its own column
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


def main():
    dry = "--dry-run" in sys.argv
    srcs = dict(DEFAULT)
    for a in sys.argv[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            srcs[k] = v
    if not dry:
        S.check_access(write=True)
    total = 0
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
        text = to_csv(cols, rows)
        check = list(csv.DictReader(io.StringIO(text)))
        assert len(check) == len(rows) and len({r["id"] for r in check}) == len(check), "ids must be unique"
        how = "dry run" if dry else S.put(dst, text, "error log: import %s from the box log (%d rows)" % (subj, n_box))
        total += len(rows)
        print("%-8s box rows %3d -> %s rows %3d (kept %d, added %d, new ids %d, %d columns) [%s]"
              % (subj, n_box, dst, len(rows), kept, added, made, len(cols), how))
    print("done: %d rows in the score repo error logs" % total)


if __name__ == "__main__":
    try:
        main()
    except S.ScoresError as ex:
        sys.exit("MIGRATION FAILED: %s" % ex)
