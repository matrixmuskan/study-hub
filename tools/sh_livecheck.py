#!/usr/bin/env python3
"""Crawl the LIVE Study Hub site and fail loudly when something is broken.

Usage: sh_livecheck.py [--url https://matrixmuskan.github.io/study-hub] [--repo DIR] [--wait-for SHA]

Without the password (CI default):
  - every hub page and every manifest page answers HTTP 200 (3 tries), is StatiCrypt output with the sh-2 login,
    and carries the template marker;
  - with --repo, every live page is byte-identical to the committed file (the deploy is current);
  - manifest.json on the site matches the repo.
With $STATICRYPT_PASSWORD (env or ~/.study-hub.env): every page is also decrypted in memory and gets the full
static link, anchor, media, video-codec, and design checks from tools/sh_checks.py.
The password is never printed. Exit code 1 when anything is broken.
"""
import argparse, json, os, sys, tempfile, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "study-hub-livecheck/1", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as ex:
            last = (ex.code, b"")
            if ex.code == 404:
                break
        except Exception as ex:
            last = ("ERR " + type(ex).__name__, b"")
        time.sleep(3 * (i + 1))
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://matrixmuskan.github.io/study-hub")
    ap.add_argument("--repo", help="compare live bytes with this checkout")
    ap.add_argument("--wait-for", help="wait (up to 15 min) until the live manifest.json matches the repo at this commit")
    a = ap.parse_args()
    base = a.url.rstrip("/") + "/"
    rows = []

    def add(page, link, kind, ok, cause=""):
        rows.append((page, link, kind, "ok" if ok else "BROKEN", cause))

    repo_manifest = None
    if a.repo:
        repo_manifest = open(os.path.join(a.repo, "manifest.json"), "rb").read()
    if a.wait_for and repo_manifest is not None:
        t0 = time.time()
        while time.time() - t0 < 900:
            st, body = get(base + "manifest.json?nocache=%d" % time.time(), tries=1)
            if st == 200 and body == repo_manifest:
                break
            time.sleep(20)
    st, body = get(base + "manifest.json")
    if st != 200:
        print("LIVE CHECK FAILED: manifest.json is HTTP %s" % st)
        sys.exit(1)
    items = json.loads(body)
    if repo_manifest is not None:
        add("manifest.json", base + "manifest.json", "deploy", body == repo_manifest, "" if body == repo_manifest else "live manifest.json differs from the repo")
    pages = ["index.html"]
    for it in items:
        g, s = it["path"].split("/")[:2]
        for p in (g + "/index.html", g + "/" + s + "/index.html", it["path"] + "index.html"):
            if p not in pages:
                pages.append(p)
    pw = None
    try:
        import sh_decrypt
        pw = sh_decrypt.password() or None
    except Exception:
        pw = None
    tmp = tempfile.mkdtemp(prefix="sh-live-") if pw else None
    if tmp:
        os.chmod(tmp, 0o700)
    hashed = {}
    for p in pages:
        url = base + (p[: -len("index.html")] if p.endswith("index.html") else p)
        st, body = get(url)
        if st != 200:
            add(p, url, "page", False, "HTTP %s" % st)
            continue
        text = body.decode("utf-8", "replace")
        enc = "staticryptConfig" in text
        add(p, url, "page", enc, "" if enc else "not StatiCrypt output (plaintext on the live site)")
        if not enc:
            continue
        if 'name="study-hub-login" content="sh-2"' not in text:
            add(p, url, "login", False, "old login template")
        if "<!-- study-hub-template: sh-" not in text[-300:]:
            add(p, url, "template", False, "no sh-2 template marker")
        if a.repo:
            fs = os.path.join(a.repo, p)
            same = os.path.exists(fs) and open(fs, "rb").read() == body
            add(p, url, "deploy", same, "" if same else "live page differs from the committed file (deploy stale or failed)")
        if pw:
            cfg = json.loads(sh_decrypt.CFG_RE.search(text).group(1))
            salt = cfg["staticryptSaltUniqueVariableName"]
            if salt not in hashed:
                hashed[salt] = sh_decrypt.hash_password(pw, salt)
            try:
                plain = sh_decrypt.decrypt_html(text, hashed[salt])
            except Exception as ex:
                add(p, url, "decrypt", False, "does not decrypt with the site password: %s" % ex)
                continue
            dst = os.path.join(tmp, p)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(plain)
    if tmp:
        import shutil, sh_checks as C
        for rel, link, kind, cause in C.check_links(tmp):
            add(rel, link, kind, False, cause)
        for f, pr in C.lint_paths([tmp], strict=False):
            add(os.path.relpath(f, tmp), "", "design", False, pr)
        for it in items:
            hub = os.path.join(tmp, "/".join(it["path"].split("/")[:2]), "index.html")
            if os.path.exists(hub) and ('href="../../%s"' % it["path"]) not in open(hub, encoding="utf-8").read():
                add(os.path.relpath(hub, tmp), it["path"], "hub", False, "hub page has no link to this page")
        print("decrypted and checked %d pages" % len([r for r in rows if r[2] == "page"]))
        if os.environ.get("SH_LIVE_KEEP"):
            print("plaintext kept in", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    broken = [r for r in rows if r[3] != "ok"]
    print("live check %s: %d pages, %d checks, %d broken%s" % (base, len(pages), len(rows), len(broken), "" if pw else " (no password: decrypt checks skipped)"))
    for r in broken:
        print("  BROKEN | %s | %s | %s | %s" % (r[0], r[1][:90], r[2], r[4]))
    if broken:
        print("LIVE CHECK FAILED")
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
