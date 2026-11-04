#!/usr/bin/env python3
"""Rule F2 log check (box only, never in public CI: it reads the private study-hub-scores repo).

Usage: python3 tools/check_f2.py [--strict] [--now ISO] [--test-time HH:MM] [--manifest PATH]

For every real test in manifest.json (one grade, subject and test_date; test_date on or after F2_CUTOFF in
tools/sh_f2.py), it lists the attempt files under study-hub-scores G3/<Subject>/<Lesson>/ for the lessons of that test
and reports one status per test:
  PASS     a full mock (kind mock, first round, score out of a full total) was logged >= 24 hours before the test
  LATE     a full mock was logged, but less than 24 hours before the test
  MISSING  no full mock was logged before the test, and the 24-hour deadline has passed (a loop failure: Basy escalates
           it to Gilfoy)
  PENDING  the deadline is still ahead and no full mock is logged yet
The test start is test_date at F2_TEST_TIME (America/Los_Angeles) unless --test-time is given.
Output: counts and attempt paths only (never scores, names or file contents).
Exit: 0, or 1 with --strict when any test is MISSING or LATE. 2 when study-hub-scores cannot be read (no token,
no network): the checker says so and does not guess.

Token: STUDY_HUB_SCORES_TOKEN (env or ~/.study-hub.env), never printed. Tests: STUDY_HUB_SCORES_DIR=<folder>.
"""
import argparse, datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_f2 as F
import sh_scores as S

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(items, now, test_time=F.F2_TEST_TIME, out=print):
    """Returns {status: [test names]}. Raises S.ScoresError when the scores repo cannot be read."""
    S.check_access(write=False)
    groups = F.tests(items)
    files = S.tree("") if groups else []
    res = {"PASS": [], "LATE": [], "MISSING": [], "PENDING": []}
    exempt = sum(1 for it in items if it.get("test_date") and not F.in_scope(it["test_date"]))
    for (g, s, day), paths in sorted(groups.items(), key=lambda kv: (kv[0][2], kv[0][1])):
        prefixes = tuple(p if p.endswith("/") else p + "/" for p in paths)
        cands = [f for f in files if f.startswith(prefixes) and f.endswith(".json") and not f.rsplit("/", 1)[-1].startswith("_")
                 and F.name_kind(f) == "mock"]
        start = F.test_start(day, test_time)
        good = []
        for f in cands:
            raw = S.get(f)
            try:
                pl = json.loads(raw) if raw else None
            except ValueError:
                pl = None
            t = F.attempt_time(f, pl)
            if t is not None and t < start and F.is_full_mock_log(f, pl):
                good.append((t, f))
        st = F.judge(day, [t for t, _ in good], now, test_time)
        name = "%s %s %s" % (g, s, day)
        res[st].append(name)
        out("%-8s %s (%d page%s, %d mock file%s, %d full before the test)" % (
            st, name, len(paths), "" if len(paths) == 1 else "s", len(cands), "" if len(cands) == 1 else "s", len(good)))
        for t, f in sorted(good):
            out("           %s" % f)
        if st == "MISSING":
            out("           loop failure for the coach of %s: Basy escalates to Gilfoy" % ", ".join(sorted(paths)))
    out("F2 totals: %s; exempt (before %s): %d manifest entries" % (
        ", ".join("%s %d" % (k, len(v)) for k, v in res.items()), F.F2_CUTOFF, exempt))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rule F2: a full mock logged >= 24 hours before each real test")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any test is MISSING or LATE")
    ap.add_argument("--now", help="ISO time to judge at (default: now)")
    ap.add_argument("--test-time", default=F.F2_TEST_TIME, help="test start HH:MM, America/Los_Angeles")
    ap.add_argument("--manifest", default=os.path.join(REPO, "manifest.json"))
    a = ap.parse_args(argv)
    now = dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=F._tz())
    try:
        items = json.load(open(a.manifest, encoding="utf-8"))
    except (OSError, ValueError) as ex:
        print("F2 CHECK FAILED: cannot read the manifest (%s)" % ex.__class__.__name__)
        return 2
    try:
        res = run(items, now, a.test_time)
    except S.ScoresError as ex:
        print("F2 CHECK DID NOT RUN: %s" % ex)
        return 2
    except Exception as ex:   # network trouble outside sh_scores' own handling
        print("F2 CHECK DID NOT RUN: cannot reach study-hub-scores (%s)" % ex.__class__.__name__)
        return 2
    if a.strict and (res["MISSING"] or res["LATE"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
