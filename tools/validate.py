#!/usr/bin/env python3
"""Validate the Study Hub repo. Exit code 1 when a rule fails. Runs in GitHub Actions and before every push.

Usage: python3 tools/validate.py [--src STAGE_OR_MIRROR]

Rules (repo):
  R1  Every .html outside tools/ is StatiCrypt output and carries the sh-2 login marker.
  R2  Every .html is in an allowed place: index.html, G<n>/index.html, G<n>/<Subject>/index.html (hub pages),
      or G<n>/<Subject>/<Chapter-or-test>/index.html (content pages). Subject codes come from tools/sh_config.json.
  R3  manifest.json is valid: required keys, path matches folder, grade and subject match path, date format,
      exactly one entry per content page and one content page per entry.
  R4  Every encrypted page was built from the shared template (marker comment written by publish.sh).
  R5  No secrets: no GitHub tokens in any file; the site password (if in env) is in no file.
  R6  No em dashes in plaintext files. .nojekyll exists. .staticrypt.json salt is unchanged from origin/main.
  R7  Private words from STUDY_HUB_BLOCKLIST (env, never in the repo) are in no plaintext file.
  R8  Content folders hold only index.html.
  R9  Design standard (tools/sh_checks.py): shared CSS/JS and the login template use only the palette (no purple,
      no multi-color gradients); every subject uses the one site accent.
Provenance (tools/sh_provenance.py; CI, no secrets). Pages in tools/sh_config.json "legacy_provenance" get a warning.
  P1  Every other manifest page has provenance_sha256, n_sources >= 1, n_questions >= 1. legacy_provenance may only shrink.
  P2  n_inferred / n_questions <= 0.20.
  B7  (with --src) a non-legacy page with a quiz has the score logger (data.log true and SHLog), not only localStorage.
  B1-B6 need the private score repo, so publish.sh runs them (tools/sh_provenance.py check), never CI.
With --src: the staged or mirror plaintext pages also must carry the template marker, and the blocklist runs on them.
  R9  (pages) no purple/violet, no multi-color gradients, no non-palette colors in a page's own styles.
  R10 Links (tools/sh_checks.py): every internal href/src/poster resolves, every '#id' anchor exists, every data: URI
      decodes with the right MIME type, every video has playable H.264/VP9/AV1 + AAC/Opus streams (ffprobe), and
      every manifest page is linked from its subject hub page.
  R7  (also) no base64 (any offset) or hex encoding of a private word in any plaintext file or page.
  R11 Every page that logs scores has privacy v3: the logger sends no free text (a missed item is its number, item id,
      option letters, blank and typed; details are numbers, booleans and short ids), it commits as Study Hub Bot, and
      the page has no sh-redact element (no private-word list in any form).
--src must be a folder made by tools/sh_stage.py (publish.sh does this). The raw mirror is refused: older pages there
are skinned and patched only at stage time, so they would fail R4, R9 and R11 for no real reason.
"""
import argparse, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L
import sh_checks as C
import sh_provenance as P

REPO = L.REPO
SKIP_DIRS = {".git", "node_modules"}
TOKEN_RE = re.compile(r"(github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,})")
TPL_RE = re.compile(r"<!-- study-hub-template: (sh-\d+(?:-legacy)?) -->\s*$")
errors = []
warnings = []


def err(rule, msg):
    errors.append(f"{rule}: {msg}")


def files():
    for root, dirs, fs in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            p = os.path.join(root, f)
            yield os.path.relpath(p, REPO).replace(os.sep, "/"), p


def is_encrypted(text):
    return "staticryptEncryptedMsgUniqueVariableName" in text or ("staticryptConfig" in text and "staticrypt_content" in text)


def b7_problems(t):
    """A page with a quiz must log every attempt to study-hub-scores, not only to the device."""
    m = re.search(r'<script type="application/json" id="sh-data">(.*?)</script>', t, re.S)
    data = {}
    if m:
        try:
            data = json.loads(m.group(1).replace("<\\/", "</"))
        except ValueError:
            data = {}
    own = re.sub(r'<script id="sh-(?:js|log|legacy-js)">.*?</script>', "", t, flags=re.S)   # the page's own code
    has_quiz = bool(data.get("quizzes")) or bool(re.search(r"""\b(?:answer|ans|correct|key)["']?\s*:\s*["'\d\[]""", own))
    if not has_quiz:
        return []
    out = []
    if "var SHLog=" not in t or (data.get("quizzes") and not data.get("log")):
        out.append("has a quiz but no score logger, so results never reach study-hub-scores")
        if "localStorage" in own:
            out.append("keeps results only in localStorage")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="staged or mirror folder with plaintext pages (local only, never in CI)")
    a = ap.parse_args()
    subjects = set(L.CFG["subjects"])
    pw = os.environ.get("STATICRYPT_PASSWORD", "")
    bl = os.environ.get("STUDY_HUB_BLOCKLIST", "")
    bl_re = re.compile(r"\b(?:%s)\b" % bl, re.I) if bl else None
    enc = sorted({f for t in L.redact_terms(bl) if bl and t != (L.CFG.get("kid_first_name") or "").lower() for f in L.encoded_forms(t)})
    enc_re = re.compile("|".join(re.escape(f) for f in enc)) if enc else None
    if a.src and not os.path.exists(os.path.join(a.src, L.STAGE_MARK)):
        print("validate.py --src runs only on staged output (a folder made by tools/sh_stage.py), not on the raw mirror.\n"
              "Use tools/publish.sh, or stage first: python3 tools/sh_stage.py <mirror> <tmpdir> && "
              "python3 tools/validate.py --src <tmpdir>")
        sys.exit(2)

    content_pages = set()
    for rel, p in files():
        try:
            text = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            text = None
        is_html = rel.endswith(".html")
        if text is not None:
            if TOKEN_RE.search(text):
                err("R5", f"{rel}: looks like a GitHub token. Remove it and rotate the token")
            if pw and len(pw) >= 6 and pw in text:
                err("R5", f"{rel}: holds the site password")
        if is_html and not rel.startswith("tools/"):
            if not is_encrypted(text or ""):
                err("R1", f"{rel}: not StatiCrypt output (plaintext page). Publish it with tools/publish.sh")
                continue
            if 'name="study-hub-login" content="sh-2"' not in text:
                err("R1", f"{rel}: encrypted with the old login template. Re-publish with tools/publish.sh")
            if not TPL_RE.search(text[-300:]):
                err("R4", f"{rel}: not built from the shared template (no sh-2 marker). Re-publish with tools/publish.sh")
            if L.CONTENT_RE.match(rel):
                parts = rel.split("/")
                if parts[1] not in subjects:
                    err("R2", f"{rel}: unknown subject code '{parts[1]}'. Add it to tools/sh_config.json")
                content_pages.add(rel)
            elif L.HUB_RE.match(rel):
                parts = rel.split("/")
                if len(parts) == 3 and parts[1] not in subjects:
                    err("R2", f"{rel}: unknown subject code '{parts[1]}'")
            else:
                err("R2", f"{rel}: wrong folder. Use G<grade>/<Subject>/<Chapter-or-test>/index.html")
        elif not is_html and text is not None and not rel.startswith(".git"):
            if "\u2014" in text:
                err("R6", f"{rel}: em dash found")
            if bl_re and bl_re.search(re.sub(r"data:[^\"')\s]+", "", text)):
                err("R7", f"{rel}: private word found")
            if enc_re and enc_re.search(text):
                err("R7", f"{rel}: a private word is hidden in base64 or hex")
        if re.match(r"^G\d+/", rel) and not rel.endswith("/index.html"):
            err("R8", f"{rel}: only index.html belongs in page folders (no sources, notes, images, or PDFs)")

    # Manifest
    try:
        items = json.load(open(os.path.join(REPO, "manifest.json"), encoding="utf-8"))
        assert isinstance(items, list)
    except Exception as ex:
        err("R3", f"manifest.json is not a valid JSON list: {ex}")
        items = []
    seen = {}
    for i, it in enumerate(items):
        for k in ("grade", "subject", "title", "path", "added_by"):
            if not it.get(k):
                err("R3", f"manifest entry {i}: missing '{k}'")
        path = it.get("path", "")
        if not re.match(r"^G\d+/[A-Za-z]+/[A-Za-z0-9][A-Za-z0-9._-]*/$", path):
            err("R3", f"manifest entry {i}: path '{path}' must look like G3/SS/Chapter-id/")
            continue
        g, s, _ = path.split("/", 2)
        if it.get("grade") != g or it.get("subject") != s:
            err("R3", f"manifest entry {i}: grade or subject does not match path '{path}'")
        if it.get("test_date") and not re.match(r"^\d{4}-\d{2}-\d{2}$", it["test_date"]):
            err("R3", f"manifest entry {i}: test_date must be YYYY-MM-DD or empty")
        page = path + "index.html"
        if page in seen:
            err("R3", f"manifest entries {seen[page]} and {i} have the same path")
        seen[page] = i
        if page not in content_pages:
            err("R3", f"manifest entry {i}: no encrypted page at {page}")
    for pg in sorted(content_pages - set(seen)):
        err("R3", f"{pg}: no manifest.json entry")

    # Provenance, public part (P1, P2); legacy pages only warn
    base_legacy = None
    try:
        b = subprocess.run(["git", "-C", REPO, "show", os.environ.get("SH_BASE_REF", "origin/main") + ":tools/sh_config.json"],
                           capture_output=True, text=True)
        if b.returncode == 0:
            base_legacy = json.loads(b.stdout).get("legacy_provenance")
    except Exception:
        pass
    perrs, pwarns = P.public_problems(items, base_legacy)
    for r, m in perrs:
        err(r, m)
    warnings.extend(pwarns)

    # Repo files
    if not os.path.exists(os.path.join(REPO, ".nojekyll")):
        err("R6", ".nojekyll is missing")
    try:
        base = subprocess.run(["git", "-C", REPO, "show", "origin/main:.staticrypt.json"], capture_output=True, text=True)
        if base.returncode == 0:
            if json.loads(base.stdout).get("salt") != json.load(open(os.path.join(REPO, ".staticrypt.json"))).get("salt"):
                err("R6", ".staticrypt.json salt changed. This breaks 'remember me' on every page")
    except Exception:
        pass

    # Design standard for shared files (no password needed, runs in CI)
    for f, pr in C.lint_paths([os.path.join(REPO, "assets"), os.path.join(REPO, "tools", "password_template.html")], strict=True) + C.lint_config():
        err("R9", "%s: %s" % (os.path.relpath(f, REPO) if os.path.isabs(f) else f, pr))

    # Plaintext (local only)
    if a.src:
        for rel, link, kind, cause in C.check_links(a.src, also=(REPO,)):
            err("R10", "plaintext %s: %s %s: %s" % (rel, kind, link[:80], cause))
        for it in items:
            path = it.get("path", "")
            hub = os.path.join(a.src, "/".join(path.split("/")[:2]), "index.html")
            if os.path.exists(hub):
                leaf = path.rstrip("/").split("/")[-1] + "/"
                if ('href="../../%s"' % path) not in open(hub, encoding="utf-8").read() and ('href="%s"' % leaf) not in open(hub, encoding="utf-8").read():
                    err("R10", "plaintext %s: hub page has no link to %s" % (os.path.relpath(hub, a.src), path))
            else:
                err("R10", "plaintext: no subject hub page for %s" % path)
        for root, dirs, fs in os.walk(a.src):
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            for f in fs:
                if not f.endswith(".html"):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, a.src).replace(os.sep, "/")
                t = open(p, encoding="utf-8").read()
                if not L.MARKER_RE.search(t):
                    err("R4", f"plaintext {rel}: no study-hub-template marker. Build it with tools/sh_page.py")
                if "\u2014" in t:
                    err("R6", f"plaintext {rel}: em dash found")
                if bl_re and bl_re.search(re.sub(r"data:[^\"')\s]+", "", t)):
                    err("R7", f"plaintext {rel}: private word found")
                if enc_re and enc_re.search(t):
                    err("R7", f"plaintext {rel}: a private word is hidden in base64 or hex")
                if pw and len(pw) >= 6 and pw in t:
                    err("R5", f"plaintext {rel}: holds the site password")
                for pr in L.logger_problems(t, bl):
                    err("R11", f"plaintext {rel}: score logger privacy: {pr}")
                for pr in C.design_problems(t, is_html=True):
                    err("R9", f"plaintext {rel}: {pr}")
                if L.CONTENT_RE.match(rel):
                    for pr in b7_problems(t):
                        if P.is_legacy(rel[: -len("index.html")]):
                            warnings.append(f"{rel}: legacy page, B7 not met: {pr}")
                        else:
                            err("B7", f"plaintext {rel}: {pr}")

    for w in warnings:
        print("WARNING: " + w)
    if errors:
        print("VALIDATION FAILED (%d problems):" % len(errors))
        for x in errors:
            print("  " + x)
        sys.exit(1)
    print(f"validation passed: {len(content_pages)} content pages, {len(items)} manifest entries")


if __name__ == "__main__":
    main()
