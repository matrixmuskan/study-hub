#!/usr/bin/env python3
"""Rule R14: the retry loop's attempt fields in a score file (privacy v4 logger, assets/js/shlog.js).

sh.js logs each round of a quiz as its own attempt. 'kind' stays the quiz kind (game, mock, retest, ...), as before, so
the file name and every older reader keep working. Two fields are added:
  attempt_kind  'first' (round 1) or 'retry' (round 2 and on)
  round         an int >= 1 (not a boolean); 'first' goes with round 1, 'retry' with round 2 or more
Both are sent together or not at all. Older score files without them pass. On a page of any subject except
SpellingBee, 'typed' in each missed item must stay a boolean (rule R13).
payload_problems() checks one score file. logger_problems() runs the logger under node (tools/round_harness.js) and
checks that it sends the fields for good input and drops them for bad input (CI, no secrets).
Usage: python3 tools/sh_rounds.py <score file or folder> ...   (exit 1 when a file fails)
"""
import json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ATTEMPT_KINDS = ("first", "retry")
SPELLING = "SpellingBee"


def payload_problems(p):
    """Problems for one score-file payload (a dict). Empty list when it passes."""
    if not isinstance(p, dict):
        return ["not a JSON object"]
    out = []
    has_k, has_r = "attempt_kind" in p, "round" in p
    k, r = p.get("attempt_kind"), p.get("round")
    if has_k and k not in ATTEMPT_KINDS:
        out.append("attempt_kind must be one of %s (got %r)" % (", ".join(ATTEMPT_KINDS), k))
    if has_r and (isinstance(r, bool) or not isinstance(r, int) or r < 1):
        out.append("round must be an int >= 1 (got %r)" % (r,))
    if has_k != has_r:
        out.append("attempt_kind and round go together (one of them is missing)")
    elif has_k and not out:
        if k == "first" and r != 1:
            out.append("attempt_kind 'first' must have round 1 (got %d)" % r)
        if k == "retry" and r < 2:
            out.append("attempt_kind 'retry' must have round 2 or more (got %d)" % r)
    if p.get("subject") != SPELLING:
        for m in p.get("missed") or []:
            if isinstance(m, dict) and "typed" in m and not isinstance(m["typed"], bool):
                out.append("typed must be a boolean on a %s page (R13)" % (p.get("subject") or "non-SpellingBee"))
                break
    return out


def run_logger(path, subject, records):
    node = shutil.which("node")
    if not node:
        return {"error": "node is needed for rule R14 (logger run)"}
    r = subprocess.run([node, os.path.join(HERE, "round_harness.js"), path, subject, json.dumps(records)],
                       capture_output=True, text=True, timeout=60)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "logger run failed: %s" % (r.stderr.strip()[:200] or "no output")}


_MISS = {"n": 2, "id": "q1-2", "picked": "B", "trap": "opposite", "blank": False, "typed": False}
GOOD = [
    {"kind": "mock", "score": 3, "total": 5, "missed": [_MISS], "attempt_kind": "first", "round": 1},
    {"kind": "mock", "score": 1, "total": 2, "missed": [_MISS], "attempt_kind": "retry", "round": 2},
    {"kind": "mock", "score": 4, "total": 5, "missed": [_MISS]},   # an older page: no round fields
]
BAD = [
    {"kind": "mock", "score": 1, "total": 1, "attempt_kind": "again", "round": 2},
    {"kind": "mock", "score": 1, "total": 1, "attempt_kind": "retry", "round": 0},
    {"kind": "mock", "score": 1, "total": 1, "attempt_kind": "retry", "round": "2"},
    {"kind": "mock", "score": 1, "total": 1, "attempt_kind": "retry", "round": True},
    {"kind": "mock", "score": 1, "total": 1, "attempt_kind": "first", "round": 3},
    {"kind": "mock", "score": 1, "total": 1, "attempt_kind": "retry", "round": 1},
    {"kind": "mock", "score": 1, "total": 1, "attempt_kind": "retry"},
    {"kind": "mock", "score": 1, "total": 1, "round": 2},
]


def logger_problems(path=None, subject="WW"):
    """The logger sends attempt_kind and round for good input (kind unchanged), and neither for bad input.
    For a page's own logger copy (path given), an older copy that sends neither field also passes."""
    strict = path is None
    path = path or os.path.join(os.path.dirname(HERE), "assets", "js", "shlog.js")
    res = run_logger(path, subject, GOOD + BAD)
    if "error" in res:
        return ["logger check did not run: %s" % res["error"]]
    if res.get("nologger"):
        return []
    pl = res.get("payloads", [])
    if len(pl) != len(GOOD) + len(BAD):
        return ["logger queued %d files for %d attempts" % (len(pl), len(GOOD) + len(BAD))]
    out = []
    want = [("first", 1), ("retry", 2), (None, None)]
    for (k, r), p in zip(want, pl[:len(GOOD)]):
        older = not strict and "attempt_kind" not in p and "round" not in p
        if p.get("kind") != "mock" or (not older and (p.get("attempt_kind") != k or p.get("round") != r)):
            out.append("logger sent kind=%r attempt_kind=%r round=%r (want mock, %r, %r)" % (p.get("kind"), p.get("attempt_kind"), p.get("round"), k, r))
        out += ["logger output: %s" % x for x in payload_problems(p)]
    for rec, p in zip(BAD, pl[len(GOOD):]):
        if "attempt_kind" in p or "round" in p:
            out.append("logger sent bad round fields for %r: attempt_kind=%r round=%r" % ({k: rec.get(k) for k in ("attempt_kind", "round")}, p.get("attempt_kind"), p.get("round")))
    return out


def files(paths):
    for a in paths:
        if os.path.isdir(a):
            for root, dirs, fs in os.walk(a):
                for f in sorted(fs):
                    if f.endswith(".json") and not f.startswith("_"):
                        yield os.path.join(root, f)
        else:
            yield a


def main(argv):
    bad = n = 0
    for f in files(argv):
        n += 1
        try:
            pr = payload_problems(json.load(open(f, encoding="utf-8")))
        except ValueError as e:
            pr = ["not JSON (%s)" % e]
        if pr:
            bad += 1
            print("R14 %s: %s" % (f, "; ".join(pr)))
    print("round fields: %d score files, %d failed" % (n, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
