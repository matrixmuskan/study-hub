#!/usr/bin/env python3
"""Stage plaintext pages for encryption (used by publish.sh).

Usage: sh_stage.py <src> <stage>
For every .html in <src>:
  - sh-2 page: refresh the inlined design system from assets/ (so a design fix reaches every page).
  - older page: add the sh-2 skin and breadcrumb (looks only; content and scripts stay the same).
The stage folder holds live plaintext: publish.sh makes it private and deletes it.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L


def main():
    src, stage = sys.argv[1], sys.argv[2]
    titles = {}
    try:
        for it in json.load(open(os.path.join(L.REPO, "manifest.json"), encoding="utf-8")):
            titles[it["path"].rstrip("/") + "/index.html"] = it["title"]
    except Exception:
        pass
    os.umask(0o077)
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if not d.startswith("_") and not d.startswith(".")]
        for f in files:
            if not f.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(root, f), src).replace(os.sep, "/")
            h = open(os.path.join(root, f), encoding="utf-8").read()
            m = L.MARKER_RE.search(h)
            if m and m.group(1) == L.VERSION:
                out, how = L.refresh(h, rel), "refresh"
            elif m:
                out, how = L.refresh(h, rel), "refresh-legacy"
            else:
                out, how = L.wrap_legacy(h, rel, titles.get(rel)), "skin"
            out = L.patch_logger(out, os.environ.get("STUDY_HUB_BLOCKLIST", ""), rel)
            dst = os.path.join(stage, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "w", encoding="utf-8").write(out)
            n += 1
            print(f"{how:15s} {rel}")
    # Marker: validate.py --src runs only on a folder made here (the raw mirror is not staged output).
    open(os.path.join(stage, L.STAGE_MARK), "w").write(L.VERSION + "\n")
    print(f"staged {n} pages")


if __name__ == "__main__":
    main()
