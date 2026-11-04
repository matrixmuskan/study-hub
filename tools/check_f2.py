#!/usr/bin/env python3
"""Rule F2 log check (box only, never in public CI: it reads the private study-hub-scores repo and the plaintext mirror).

Usage: python3 tools/check_f2.py [--strict] [--now ISO] [--test-time HH:MM] [--manifest PATH] [--src MIRROR]

For every real test in manifest.json (one grade, subject and test_date; test_date on or after F2_CUTOFF in
tools/sh_f2.py) it checks the COACH's duty: a full mock page that logs is published, and a predicted score for it is
recorded, at least 24 hours before the test (by 08:00 Pacific the day before, F2_TEST_TIME).
  - Full mock page: a manifest page of the test whose plaintext page (mirror, --src) has a full mock that logs.
  - Published: the first build of the page in study-hub-scores G<g>/<Subject>/_builds/, else manifest built_at.
  - Prediction: a record G<g>/<Subject>/<Lesson>/<stamp>-prediction.json (kind prediction, a predicted score
    {"total", "of"}; time from created_at, else the file name stamp), or a 'prediction' in the page metadata (sh-data;
    its time is the page's latest build, manifest built_at).
  - The page and its prediction are ready at the later of the two times.
Status per test (coach duty):
  PASS     a full mock page and its prediction were ready >= 24 hours before the test
  LATE     ready, but less than 24 hours before the test (a coach failure: Basy escalates it to Gilfoy)
  MISSING  not ready before the test, and the 24-hour deadline has passed (a coach failure: Basy escalates it)
  PENDING  the deadline is still ahead and the page or the prediction is not ready yet
INFO per test (not a coach failure): attempted: yes/no, from the child's full mock attempt logs before the test. A mock
with no attempt still lets Basy compare the real result with the prediction.
Output: counts, times and paths only (never scores, names or file contents).
Exit: 0, or 1 with --strict when any test is MISSING or LATE (never for attempted: no). 2 when study-hub-scores or the
mirror cannot be read (no token, no network), or the scores folder has no prediction records at all (the path is
likely wrong): the checker says so and does not guess.

Token: STUDY_HUB_SCORES_TOKEN (env or ~/.study-hub.env), never printed. Tests: STUDY_HUB_SCORES_DIR=<folder>.
"""
import argparse, datetime as dt, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_f2 as F
import sh_scores as S

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSES = ("PASS", "LATE", "MISSING", "PENDING")
PRED_RE = re.compile(r"^G[0-9]+/[^/]+/[^/]+/[^/]*-prediction\.json$")


def scores_folder():
    """The scores folder in use, for messages: the local test folder or the GitHub repo."""
    return S.local_dir() or "study-hub-scores on GitHub (%s)" % S.REPO


def n_prediction_files(files):
    """How many G<g>/<Subject>/<Lesson>/*-prediction.json files the scores folder has in total."""
    return sum(1 for f in files if PRED_RE.match(f))


def mirror_reader(src):
    def page_html(path):
        fp = os.path.join(src, path, "index.html")
        return open(fp, encoding="utf-8").read() if os.path.isfile(fp) else None
    return page_html


def _load(f):
    raw = S.get(f)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _fmt(t):
    return t.astimezone(F._tz()).strftime("%Y-%m-%d %H:%M PT")


def run(items, now, test_time=F.F2_TEST_TIME, out=print, page_html=None):
    """Returns {status: [test names], "attempted": {test name: "yes"/"no"}}. page_html(path) -> plaintext html or None.
    Raises S.ScoresError when the scores repo cannot be read."""
    page_html = page_html or mirror_reader(os.environ.get("STUDY_HUB_SRC") or os.path.join(os.path.dirname(REPO), "study-hub-src"))
    S.check_access(write=False)
    groups = F.tests(items)
    files = S.tree("") if groups else []
    builds = F.build_times(files)
    built_at = {it.get("path"): F._iso(it.get("built_at")) for it in items if it.get("path")}
    res = {k: [] for k in STATUSES}
    res["attempted"] = {}
    exempt = sum(1 for it in items if it.get("test_date") and not F.in_scope(it["test_date"]))
    for (g, s, day), paths in sorted(groups.items(), key=lambda kv: (kv[0][2], kv[0][1])):
        start = F.test_start(day, test_time)
        name = "%s %s %s" % (g, s, day)
        ready, lines, n_full, n_pred = [], [], 0, 0
        attempts = []
        for p in sorted(paths):
            pre = p if p.endswith("/") else p + "/"
            mine = [f for f in files if f.startswith(pre) and f.endswith(".json") and "/" not in f[len(pre):]
                    and not f.rsplit("/", 1)[-1].startswith("_")]
            for f in mine:
                if F.name_kind(f) == "mock":
                    pl = _load(f)
                    t = F.attempt_time(f, pl)
                    if t is not None and t < start and F.is_full_mock_log(f, pl):
                        attempts.append(f)
            html = page_html(p)
            if html is None or not F.full_logging_mocks(html):
                continue
            n_full += 1
            bt = builds.get(pre) or []
            pub = min(bt) if bt else built_at.get(p)
            preds = []
            for f in mine:
                if F.name_kind(f) == "prediction":
                    pl = _load(f)
                    t = F.attempt_time(f, pl)
                    if t is not None and t < start and F.is_prediction_record(f, pl):
                        preds.append((t, f))
            if F.page_prediction(html) and built_at.get(p) and built_at[p] < start:
                preds.append((built_at[p], "%s sh-data prediction" % p))
            n_pred += len(preds)
            if pub is None or pub >= start or not preds:
                continue
            t_pred, f_pred = min(preds)
            ready.append(max(pub, t_pred))
            lines.append("           page %s published %s; prediction %s (%s)" % (p, _fmt(pub), f_pred, _fmt(t_pred)))
        st = F.judge(day, ready, now, test_time)
        res[st].append(name)
        att = "yes" if attempts else "no"
        res["attempted"][name] = att
        out("%-8s %s (%d page%s, %d full mock page%s, %d prediction%s before the test)" % (
            st, name, len(paths), "" if len(paths) == 1 else "s", n_full, "" if n_full == 1 else "s",
            n_pred, "" if n_pred == 1 else "s"))
        for x in lines:
            out(x)
        if st in ("MISSING", "LATE"):
            why = "no full mock page that logs" if not n_full else ("no prediction" if not n_pred else "not ready 24 hours before")
            out("           coach failure (%s) for the coach of %s: Basy escalates to Gilfoy" % (why, ", ".join(sorted(paths))))
        out("INFO     %s attempted: %s (%d full mock attempt file%s before the test; not a coach failure)%s" % (
            name, att, len(attempts), "" if len(attempts) == 1 else "s",
            "" if attempts or not ready else "; compare the real result with the prediction"))
    out("F2 totals: %s; attempted no %d; exempt (before %s): %d manifest entries" % (
        ", ".join("%s %d" % (k, len(res[k])) for k in STATUSES),
        sum(1 for v in res["attempted"].values() if v == "no"), F.F2_CUTOFF, exempt))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rule F2: a full mock page and its prediction ready >= 24 hours before each real test")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any test is MISSING or LATE")
    ap.add_argument("--now", help="ISO time to judge at (default: now)")
    ap.add_argument("--test-time", default=F.F2_TEST_TIME, help="test start HH:MM, America/Los_Angeles")
    ap.add_argument("--manifest", default=os.path.join(REPO, "manifest.json"))
    ap.add_argument("--src", default=os.environ.get("STUDY_HUB_SRC") or os.path.join(os.path.dirname(REPO), "study-hub-src"),
                    help="plaintext mirror (default $STUDY_HUB_SRC or ../study-hub-src)")
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
        S.check_access(write=False)
        if not os.path.isdir(a.src):
            print("F2 CHECK DID NOT RUN: no plaintext mirror at --src (the full mock pages cannot be read)")
            return 2
        # Zero prediction files in the whole folder: the path is likely wrong, so do not report MISSING for every test.
        d = S.local_dir()
        if d and not os.path.isdir(d):
            print("F2 CHECK DID NOT RUN: the scores folder %s does not exist (STUDY_HUB_SCORES_DIR is likely wrong)" % d, file=sys.stderr)
            return 2
        if n_prediction_files(S.tree("")) == 0:
            print("F2 CHECK DID NOT RUN: no prediction records (G3/*/*/*-prediction.json) were found in %s. "
                  "The scores folder path is likely wrong" % scores_folder(), file=sys.stderr)
            return 2
        res = run(items, now, a.test_time, page_html=mirror_reader(a.src))
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
