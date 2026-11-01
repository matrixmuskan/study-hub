#!/usr/bin/env python3
"""The files GitHub Pages serves: G<n>/ pages, the hub index.html, assets/ and manifest.json. Nothing else (no
tools/, *.md, templates/, docs/, .staticrypt.json). Used by .github/workflows/pages.yml (upload-pages-artifact) and by
sh_livecheck.py (byte-identical deploy, non-site paths must be 404).

Usage: site_files.py [--out DIR]   (prints the list, or copies the files into DIR)"""
import argparse, os, re, shutil, subprocess, sys

SITE_RE = re.compile(r"^(?:index\.html|manifest\.json|assets/.+|G\d+/.+)$")
# repo-only paths that must answer 404 on the live site
NOT_SERVED = ["README.md", "CONTRIBUTING-BOTS.md", "tools/sh_config.json", "tools/publish.sh", ".staticrypt.json",
              "templates/page.example.json", "docs/screenshots/login_phone390.png", ".github/workflows/pages.yml"]


def site_files(repo):
    out = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    return sorted(f for f in out.split("\0") if f and SITE_RE.match(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--out")
    a = ap.parse_args()
    fs = site_files(a.repo)
    if not a.out:
        print("\n".join(fs))
        return
    for f in fs:
        dst = os.path.join(a.out, f)
        os.makedirs(os.path.dirname(dst) or a.out, exist_ok=True)
        shutil.copyfile(os.path.join(a.repo, f), dst)
    print("site: %d files copied to %s" % (len(fs), a.out))


if __name__ == "__main__":
    sys.exit(main())
