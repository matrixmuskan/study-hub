#!/usr/bin/env python3
"""Rule R13: typed text and spelling trap keys only on SpellingBee pages.

Only a page of subject SpellingBee may use the logger's spelling exception (shlog.js: SHLog.allow({spelling:true})
makes 'typed' the typed letters a-z, max 40, and allows a trap key from SPELL). Any other page fails when:
  (a) its own scripts turn the exception on (a 'spelling' key that is not false),
  (b) its own scripts put a non-boolean in 'typed': any string, even '' (typed must be true, false, !x, Boolean(x) or a
      comparison, with no string literal in it). Real non-SpellingBee pages send typed as a boolean (sh.js: !q.options),
      so this keys on the field's value, not on the field: a rule against any 'typed' field would fail every real page,
  (c) second check: its own scripts use a spelling trap key (SPELL) or the SpellTrap classifier,
  (d) its logger copy, run with the page's subject and the exception turned on, sends a string 'typed' or a spelling
      trap key (node tools/typed_harness.js), so a changed logger copy cannot leak typed text either.
asset_problems() checks the SpellingBee logger (sh_lib.logger_src) keeps the subject gate and that every other page
keeps assets/js/shlog.js unchanged (CI, no plaintext needed).
"""
import json, os, re, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SPELL = ["double_letter", "silent_letter", "vowel_swap", "ending", "homophone", "other"]
SUBJECT = "SpellingBee"
_PATH_RE = re.compile(r"^G\d+/([A-Za-z]+)/")
_SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
_ON_RE = re.compile(r"""["']?\bspelling["']?\s*:\s*(?!\s*(?:false|0|!1|null)\b)""")
_TYPED_RE = re.compile(r"""["']?\btyped["']?\s*:\s*([^,}\n]{0,80})""")
_BOOL_RE = re.compile(r"""^\s*(?:true|false|!0|!1|!+[\w$.()\[\]'"]+|Boolean\(.*|.*(?:===|!==|==|!=|<=|>=|<|>).*)\s*$""")
_SPELLKEY_RE = re.compile(r"""["'`](?:%s)["'`]|\bSpellTrap\b""" % "|".join(SPELL))


def subject_of(rel):
    m = _PATH_RE.match(rel)
    return m.group(1) if m else None


def own_scripts(h):
    """The page's scripts without the logger copy (the sh-log block or an inline var SHLog=... copy)."""
    out = []
    for attrs, body in _SCRIPT_RE.findall(h):
        if 'id="sh-log"' in attrs:
            continue
        i = body.find("var SHLog=")
        if i >= 0:
            j = body.find("})();", body.find("return {init:init", i))
            body = body[:i] + (body[j + 5:] if j >= 0 else "")
        out.append(body)
    return "\n".join(out)


def run_logger(path, subject):
    node = shutil.which("node")
    if not node:
        return {"error": "node is needed for rule R13 (logger run)"}
    r = subprocess.run([node, os.path.join(HERE, "typed_harness.js"), path, subject], capture_output=True, text=True, timeout=60)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "logger run failed: %s" % (r.stderr.strip()[:200] or "no output")}


def page_problems(path, rel):
    """Problems for one plaintext page (empty for SpellingBee pages)."""
    subj = subject_of(rel) or "(hub)"
    if subj == SUBJECT:
        return []
    h = open(path, encoding="utf-8").read()
    s = own_scripts(h)
    out = []
    if _ON_RE.search(s):
        out.append("subject %s turns on the spelling exception (only %s pages may send typed text)" % (subj, SUBJECT))
    for v in _TYPED_RE.findall(s):
        if re.search(r"[\"'`]", v) or not _BOOL_RE.match(v):
            out.append("subject %s puts a non-boolean in 'typed' (%s): only %s pages may send typed text" % (subj, v.strip()[:40], SUBJECT))
            break
    if _SPELLKEY_RE.search(s):
        out.append("subject %s uses a spelling trap key or SpellTrap (only %s pages)" % (subj, SUBJECT))
    if "var SHLog=" in h:
        res = run_logger(path, subj)
        if "error" in res:
            out.append("logger check did not run: %s" % res["error"])
        else:
            for m in res.get("missed", []):
                if not isinstance(m.get("typed"), bool):
                    out.append("subject %s: the logger sent typed text (typed=%r)" % (subj, m.get("typed"))); break
            for m in res.get("missed", []):
                if m.get("trap") in SPELL:
                    out.append("subject %s: the logger sent a spelling trap key (%s)" % (subj, m["trap"])); break
    return out


def asset_problems(sb=None, other=None):
    """The SpellingBee logger (sh_lib.logger_src) keeps the subject gate and the fixed spelling list, and every other
    page's logger is assets/js/shlog.js unchanged, with no spelling code."""
    import sh_lib as L
    sb = L.logger_src("G3/%s/X/index.html" % SUBJECT) if sb is None else sb
    other = L.logger_src("G3/WW/X/index.html") if other is None else other
    need = ["function spelling(){return !!(REG.spelling&&cfg&&cfg.subject==='%s')}" % SUBJECT,
            "if(spelling()&&!item){",
            "var SPELL=[%s];" % ",".join("'%s'" % k for k in SPELL)]
    out = ["SpellingBee logger: the spelling exception lost its gate (%s)" % n[:60] for n in need if n not in sb]
    if other != L.asset("js/shlog.js") or "spelling()" in other or "REG.spelling" in other:
        out.append("the logger of non-SpellingBee pages is not assets/js/shlog.js unchanged, or has spelling code")
    if "spelling" in L.asset("js/shlog.js"):
        out.append("assets/js/shlog.js has spelling code (it belongs only in sh_lib.SPELL_PATCHES)")
    return out
