#!/usr/bin/env python3
"""Build rule F2 (decided by Gilfoy, effective 2026-11-03; coach duty split from the child's attempt the same day).

The COACH's duty: at least 24 hours before each real test (by F2_TEST_TIME, 08:00 Pacific, the day before), publish a
full mock page that logs, and record a predicted score for it (in the page metadata, sh-data, or as a 'prediction'
record in study-hub-scores). A missing or late page or prediction is a coach failure (MISSING or LATE).
The CHILD's attempt of the mock is not a coach duty. check_f2.py reports it as INFO (attempted: yes/no) only.

Shared by tools/validate.py (static part, with --src) and tools/check_f2.py (logs in study-hub-scores, box only).

A "test" is one (grade, subject, test_date) group of manifest entries. Pages of the same test share it, so one full
mock on any page of the test covers the test.

Static part (validate.py --src, also in publish.sh). For every manifest entry with a test_date on or after F2_CUTOFF:
  - ok:   the page has a full mock that logs: a quiz with kind 'mock', mode 'test', at least F2_MIN_QUESTIONS
          questions (or "full": true on the quiz block when the real test is shorter), sh-data 'log' true, and the
          score logger (var SHLog=) on the page. This is the page the coach must publish.
  - warn: the page has no full logging mock, but another page of the same test has one (the test is covered),
          or every page of the test is an older page with no sh-data (the quizzes cannot be read).
  - fail: no page of the test has a full logging mock.
Tests dated before F2_CUTOFF are exempt (no back-dated failures).
"""
import datetime as dt
import json, re

F2_CUTOFF = "2026-11-05"        # Gilfoy: F2 counts for real tests from Thu 2026-11-05 on; on or before 2026-11-04 exempt
F2_MIN_QUESTIONS = 10           # a mock with fewer questions is a mini check, not a full mock
F2_TEST_TIME = "08:00"          # assumed start of a real test (America/Los_Angeles) when the manifest has only a date
F2_LEAD_HOURS = 24
TZ_NAME = "America/Los_Angeles"
SH_DATA_RE = re.compile(r'<script type="application/json" id="sh-data">(.*?)</script>', re.S)


def sh_data(html):
    """The page's sh-data dict, or None for an older page without sh-data."""
    m = SH_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        d = json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def is_full_mock(q):
    if not isinstance(q, dict) or q.get("kind") != "mock":
        return False
    if (q.get("mode") or "test") != "test":
        return False
    if q.get("full") is False:
        return False
    return q.get("full") is True or len(q.get("questions") or []) >= F2_MIN_QUESTIONS


def full_logging_mocks(html):
    """Number of full mocks on the page that log to study-hub-scores. None when the page has no sh-data."""
    d = sh_data(html)
    if d is None:
        return None
    if not d.get("log") or "var SHLog=" not in html:
        return 0
    return sum(1 for q in d.get("quizzes") or [] if is_full_mock(q))


def prediction_value(obj):
    """(predicted, out_of) from a prediction object, else None. Reads only the numbers: {"total": n, "of": m} or
    {"score": n, "total": m}, on the object itself or on one of its dict values. No key name for free text is read,
    so a coach may rename or drop a text key without breaking the check."""
    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def one(d):
        if not isinstance(d, dict):
            return None
        if num(d.get("total")) and num(d.get("of")) and 0 <= d["total"] <= d["of"] and d["of"] > 0:
            return (d["total"], d["of"])
        if num(d.get("score")) and num(d.get("total")) and 0 <= d["score"] <= d["total"] and d["total"] > 0:
            return (d["score"], d["total"])
        return None
    if not isinstance(obj, dict):
        return None
    v = one(obj)
    if v:
        return v
    for x in obj.values():
        v = one(x)
        if v:
            return v
    return None


def page_prediction(html):
    """True when the page metadata (sh-data) holds a predicted score: sh-data 'prediction', or 'prediction' on a full
    mock quiz. The page must also have a full mock that logs."""
    d = sh_data(html)
    if not d or not full_logging_mocks(html):
        return False
    if prediction_value(d.get("prediction")):
        return True
    return any(is_full_mock(q) and prediction_value(q.get("prediction")) for q in d.get("quizzes") or [])


def in_scope(test_date, cutoff=F2_CUTOFF):
    return bool(test_date) and bool(re.match(r"^\d{4}-\d{2}-\d{2}$", test_date)) and test_date >= cutoff


def tests(items, cutoff=F2_CUTOFF):
    """{(grade, subject, test_date): [manifest paths]} for the tests F2 covers."""
    out = {}
    for it in items:
        if in_scope(it.get("test_date", ""), cutoff) and it.get("path"):
            out.setdefault((it.get("grade", ""), it.get("subject", ""), it["test_date"]), []).append(it["path"])
    return out


def static_problems(items, page_html, cutoff=F2_CUTOFF):
    """page_html(path) -> plaintext html or None. Returns (errors, warnings) as lists of strings."""
    errs, warns = [], []
    for (g, s, day), paths in sorted(tests(items, cutoff).items()):
        counts = {}
        for p in paths:
            h = page_html(p)
            if h is not None:
                counts[p] = full_logging_mocks(h)
        if not counts:
            continue    # pages not staged: R3 / R10 report that
        covered = [p for p, n in counts.items() if n]
        name = "%s %s test %s" % (g, s, day)
        if not covered:
            if all(n is None for n in counts.values()):
                warns.append("F2: %s: only older pages with no sh-data, so the full mock cannot be checked (%s)"
                             % (name, ", ".join(sorted(counts))))
            else:
                errs.append("F2: %s has no full mock that logs (kind mock, mode test, %d+ questions or \"full\": true, "
                            "log on), so the coach cannot publish the F2 mock page. Pages: %s"
                            % (name, F2_MIN_QUESTIONS, ", ".join(sorted(counts))))
            continue
        for p, n in sorted(counts.items()):
            if not n:
                warns.append("F2: %s has no full logging mock; %s is covered by %s" % (p, name, ", ".join(sorted(covered))))
    return errs, warns


# ---- log timing (check_f2.py) ----

def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ_NAME)
    except Exception:       # no tz database: fixed PST (UTC-8), the season of the first F2 tests
        return dt.timezone(dt.timedelta(hours=-8))


def test_start(test_date, test_time=F2_TEST_TIME):
    y, m, d = map(int, test_date.split("-"))
    hh, mm = map(int, test_time.split(":"))
    return dt.datetime(y, m, d, hh, mm, tzinfo=_tz())


NAME_RE = re.compile(r"(?:^|/)(\d{4}-\d{2}-\d{2})T(\d{6})-([a-z0-9_-]+?)(?:-[a-z0-9]{4})?\.json$")


def _iso(v):
    if isinstance(v, str):
        try:
            t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if t.tzinfo:
                return t
        except ValueError:
            pass
    return None


def attempt_time(path, payload=None):
    """When the file was logged (aware datetime): clientTime or created_at (with offset) from the file, else the file
    name stamp read as America/Los_Angeles. None when neither can be read."""
    if isinstance(payload, dict):
        for k in ("clientTime", "created_at"):
            t = _iso(payload.get(k))
            if t:
                return t
    m = NAME_RE.search(path)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M%S").replace(tzinfo=_tz())
    except ValueError:
        return None


def name_kind(path):
    m = NAME_RE.search(path)
    return m.group(3) if m else None


def is_full_mock_log(path, payload):
    """A logged attempt of the full mock by the child (INFO only, not a coach duty): kind mock, a first (full) round,
    and a score out of a full mock total."""
    if not isinstance(payload, dict):
        return False
    kind = payload.get("kind") or name_kind(path)
    if kind != "mock":
        return False
    if payload.get("attempt_kind") == "retry" or (isinstance(payload.get("round"), int) and payload["round"] > 1):
        return False
    sc, tot = payload.get("score"), payload.get("total")
    if not isinstance(sc, (int, float)) or isinstance(sc, bool) or not isinstance(tot, (int, float)) or isinstance(tot, bool):
        return False
    return tot >= F2_MIN_QUESTIONS or payload.get("full") is True


def is_prediction_record(path, payload):
    """A 'prediction' record in study-hub-scores: kind prediction (in the file or its name) and a predicted score."""
    if not isinstance(payload, dict):
        return False
    if (payload.get("kind") or name_kind(path)) != "prediction":
        return False
    return prediction_value(payload) is not None


BUILD_RE = re.compile(r"^(G\d+/[A-Za-z0-9_-]+)/_builds/(\d{8}T\d{6})-(.+)\.json$")


def build_times(files):
    """{page path: [build times]} from the build history files G<g>/<Subject>/_builds/<stamp>-<Lesson>.json (the
    stamp is Pacific time)."""
    out = {}
    for f in files:
        m = BUILD_RE.match(f)
        if not m:
            continue
        try:
            t = dt.datetime.strptime(m.group(2), "%Y%m%dT%H%M%S").replace(tzinfo=_tz())
        except ValueError:
            continue
        out.setdefault("%s/%s/" % (m.group(1), m.group(3)), []).append(t)
    return out


def judge(test_date, ready_times, now, test_time=F2_TEST_TIME, lead_hours=F2_LEAD_HOURS):
    """PASS, LATE, MISSING or PENDING for the coach duty of one test. ready_times: for each full mock page of the
    test, the time when both the page was published and its prediction was recorded."""
    start = test_start(test_date, test_time)
    deadline = start - dt.timedelta(hours=lead_hours)
    if any(t <= deadline for t in ready_times):
        return "PASS"
    if any(deadline < t < start for t in ready_times):
        return "LATE"
    if now < deadline:
        return "PENDING"
    return "MISSING"
