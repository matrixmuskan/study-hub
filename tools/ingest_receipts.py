#!/usr/bin/env python3
"""Turn already-downloaded Google Forms receipts into study-hub-scores/G3/_receipts/<gmail-id>.json (BOX ONLY).

This script never calls Gmail. Each coach fetches receipts with its own personal-Gmail connector
(read_email, messageFormat FULL_CONTENT) and saves the JSON result to a file, then runs:

    python3 tools/ingest_receipts.py [--dry-run] [--out DIR] <file or folder> ...

Input: the saved read_email JSON (text around the JSON is fine), or a bare HTML body with --id and --date.
It reads the HTML body (the plain-text body has no marks): the picked option has an inner filled
<div style="background-color:...">. "Score released" mails give the score.
Output (no names): {"id": "gmail:<id>", "kind", "subject" (site code), "title", "date" (PT), "datetime" (PT),
"items": [{"n", "q", "options", "picked"}], "score"}. Name, email and code-name questions are dropped; private
words (STUDY_HUB_BLOCKLIST, the first name) and email addresses become [name] / [email].
"""
import argparse, glob, html as H, json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L

PT = ZoneInfo("America/Los_Angeles")
VERSION = 1
IDENTITY_Q = re.compile(r"(?i)^\s*(e-?mail|name|first name|last name|full name|student( name)?|code ?name|teacher|class|"
                        r"parent|phone|school)\s*\*?\s*$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def load(path, gid=None, date=None):
    raw = open(path, encoding="utf-8", errors="replace").read()
    i, j = raw.find("{"), raw.rfind("}")
    d = None
    if i >= 0 and j > i:
        try:
            d = json.loads(raw[i:j + 1])
        except ValueError:
            d = None
    if isinstance(d, dict) and (d.get("htmlBody") or d.get("body")):
        return d
    if "<" in raw and gid and date:
        return {"id": gid, "date": date, "subject": "", "htmlBody": raw, "body": "", "from": ""}
    return None


def parse_items(h):
    """Reference parser (study-hub-qa/receipts/parse_receipt.py), kept the same."""
    out = []
    for b in re.split(r"<h2[^>]*>", h)[1:]:
        title = H.unescape(re.sub(r"<[^>]+>", "", b.split("</h2>")[0])).strip().rstrip("*").strip()
        body = b.split("</h2>", 1)[1] if "</h2>" in b else ""
        picked, options = None, []
        for o in re.findall(r"<table[^>]*>(.*?)</table>", body, re.S):
            txt = H.unescape(re.sub(r"<[^>]+>", "", o)).strip()
            if not txt:
                continue
            options.append(txt)
            if "background-color" in o:
                picked = txt
        if not options:
            m = re.findall(r"<div[^>]*>([^<]{1,80})</div>", body)
            picked = H.unescape(m[0]).strip() if m else None
        out.append({"q": title, "options": options, "picked": picked})
    return out


def scrubber():
    terms = L.redact_terms(os.environ.get("STUDY_HUB_BLOCKLIST", ""))
    rx = re.compile(r"\b(?:%s)(?:'s)?\b" % "|".join(re.escape(t) for t in terms), re.I) if terms else None

    def s(v):
        if not isinstance(v, str):
            return v
        v = EMAIL_RE.sub("[email]", v)
        return rx.sub("[name]", v) if rx else v
    return s, rx


def subject_code(title):
    for rx, code in L.CFG.get("receipt_subjects", []):
        if re.search(rx, title):
            return code
    return ""


def convert(d):
    clean, rx = scrubber()
    subj_line = d.get("subject", "")
    title = re.sub(r"^.*?(?:this form|released)\s*:\s*", "", subj_line).strip() or subj_line
    kind = "score_released" if re.search(r"(?i)score (is )?released|released.*score", subj_line) else "form_receipt"
    when = datetime.fromisoformat(d["date"].replace("Z", "+00:00")).astimezone(PT)
    items = []
    n = 0
    for it in parse_items(d.get("htmlBody", "")):
        if IDENTITY_Q.match(it["q"] or ""):
            continue
        n += 1
        items.append({"n": n, "q": clean(it["q"]), "options": [clean(o) for o in it["options"]], "picked": clean(it["picked"])})
    score = None
    text = d.get("body", "") + " " + re.sub(r"<[^>]+>", " ", d.get("htmlBody", ""))
    m = re.search(r"(?i)(?:score|points)[^0-9]{0,40}(\d{1,3})\s*/\s*(\d{1,3})", text)
    if m:
        score = {"points": int(m.group(1)), "total": int(m.group(2))}
    rec = {"v": VERSION, "id": "gmail:" + d["id"], "kind": kind, "subject": subject_code(title), "title": clean(title),
           "date": when.date().isoformat(), "datetime": when.isoformat(), "n_items": len(items), "items": items, "score": score}
    blob = json.dumps(rec, ensure_ascii=False)
    if rx and rx.search(blob) or EMAIL_RE.search(blob):
        raise ValueError("private word left in the output")   # never write it
    return rec


def main():
    if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS"):
        sys.exit("ingest_receipts.py runs on the box only, never in CI")
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", help="write JSON files to this folder instead of study-hub-scores (tests)")
    ap.add_argument("--id", help="Gmail id (only for a bare HTML body)")
    ap.add_argument("--date", help="ISO date-time of the mail (only for a bare HTML body)")
    a = ap.parse_args()
    if not os.environ.get("STUDY_HUB_BLOCKLIST") and os.path.exists(os.path.expanduser("~/.study-hub.env")):
        for line in open(os.path.expanduser("~/.study-hub.env")):
            if line.startswith("STUDY_HUB_BLOCKLIST="):
                os.environ["STUDY_HUB_BLOCKLIST"] = line.split("=", 1)[1].strip().strip("'\"")
    files = []
    for x in a.inputs:
        files += sorted(glob.glob(os.path.join(x, "*"))) if os.path.isdir(x) else [x]
    import sh_scores as S
    if not a.dry_run and not a.out:
        S.check_access(write=True)
    seen, n_ok, n_skip = {}, 0, 0
    for f in files:
        d = load(f, a.id, a.date)
        if not d or not d.get("id") or not d.get("date"):
            print("skip  %s: not a saved receipt (no id, date, or HTML body)" % os.path.basename(f))
            n_skip += 1
            continue
        if "forms-receipts" not in d.get("from", "forms-receipts") and "released" not in d.get("subject", "").lower():
            print("skip  %s: not a Google Forms receipt or a score mail" % os.path.basename(f))
            n_skip += 1
            continue
        if d["id"] in seen:
            continue
        rec = convert(d)
        seen[d["id"]] = rec
        data = json.dumps(rec, indent=1, ensure_ascii=False) + "\n"
        dst = "G3/_receipts/%s.json" % d["id"]
        if a.dry_run:
            how = "dry run"
        elif a.out:
            os.makedirs(os.path.join(a.out, "G3/_receipts"), exist_ok=True)
            open(os.path.join(a.out, dst), "w", encoding="utf-8").write(data)
            how = "written"
        else:
            how = S.put(dst, data, "receipt: %s %s %s" % (rec["subject"] or "?", rec["date"], rec["kind"]))
        picked = sum(1 for i in rec["items"] if i["picked"])
        print("%-7s %s %-8s %s %-45s %2d items, %2d picked%s" % (how, rec["id"], rec["subject"] or "?", rec["date"], rec["title"][:45],
              rec["n_items"], picked, (", score %d/%d" % (rec["score"]["points"], rec["score"]["total"])) if rec["score"] else ""))
        n_ok += 1
    print("receipts: %d ingested, %d skipped" % (n_ok, n_skip))


if __name__ == "__main__":
    main()
