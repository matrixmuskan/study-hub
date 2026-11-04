#!/usr/bin/env python3
"""Build rule F2 (decided by Gilfoy, effective 2026-11-03): a full mock is logged at least 24 hours before each real test.

Shared by tools/validate.py (static part, with --src) and tools/check_f2.py (logs in study-hub-scores, box only).

A "test" is one (grade, subject, test_date) group of manifest entries. Pages of the same test share it, so one full
mock on any page of the test covers the test.

Static part (validate.py --src, also in publish.sh). For every manifest entry with a test_date on or after F2_CUTOFF:
  - ok:   the page has a full mock that logs: a quiz with kind 'mock', mode 'test', at least F2_MIN_QUESTIONS
          questions (or "full": true on the quiz block when the real test is shorter), sh-data 'log' true, and the
          score logger (var SHLog=) on the page.
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
                            "log on), so no predicted score can be recorded before the test. Pages: %s"
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


def attempt_time(path, payload=None):
    """When the attempt was logged (aware datetime): clientTime (with offset) from the file, else the file name
    stamp read as America/Los_Angeles. None when neither can be read."""
    ct = (payload or {}).get("clientTime") if isinstance(payload, dict) else None
    if isinstance(ct, str):
        try:
            t = dt.datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if t.tzinfo:
                return t
        except ValueError:
            pass
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
    """A logged attempt that counts for F2: kind mock, a first (full) round, and a score out of a full mock total."""
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


def judge(test_date, mock_times, now, test_time=F2_TEST_TIME, lead_hours=F2_LEAD_HOURS):
    """PASS, LATE, MISSING or PENDING for one test, from the times of its full mock logs."""
    start = test_start(test_date, test_time)
    deadline = start - dt.timedelta(hours=lead_hours)
    if any(t <= deadline for t in mock_times):
        return "PASS"
    if any(deadline < t < start for t in mock_times):
        return "LATE"
    if now < deadline:
        return "PENDING"
    return "MISSING"
