#!/usr/bin/env python3
"""Which pages does this publish have to encrypt and check? (used by tools/publish.sh)

Usage: sh_changed.py plan <src> <repo> <out_plan> <out_keys> [--force]

CHANGED is decided per page from the page's OWN input, the plaintext in the mirror, never from a whole-site re-render:
  key = sha256 of the mirror page with these parts blanked:
        - the scores token slots (a token renewal is its own class, "token", below);
        - the inlined design-system blocks (sh-css, sh-js, sh-log, sh-legacy-*, sh-vars) that sh_stage.py replaces from
          assets/ on every run, the template version in the study-hub-template marker, and the sh-build meta;
        plus the page's manifest title (an older page gets its breadcrumb from it).
  So a change in assets/, sh_lib.py, the renderer or the template version does NOT make a page CHANGED. Re-encrypting
  every page after such a change is a separate, explicit mode: FORCE=1 tools/publish.sh (or --rerender-all).
Classes (one line per page in <out_plan>: class<TAB>path<TAB>reason):
  unchanged  key and token as at the last successful publish: keeps its committed encrypted file, no checks
  new        no committed encrypted file yet
  content    the page's own content changed
  rebuilt    sh_page.py or attach left a pending provenance record for it (rebuilt with the same content)
  token      only the scores token changed: re-encrypted and browser-checked, but B1-B6 are skipped (TOKEN-ONLY)
  force      FORCE=1 / --rerender-all
  hub        a hub page whose own content changed (or is new); encrypted and link/browser-checked, never provenance
Hub pages (index.html, G<n>/, G<n>/<Subject>/) come from manifest.json (build_index.py writes them every run); they
follow the same rule and are never provenance-checked.
State: <src>/_state/page_keys.txt (key token path), written by publish.sh only after a successful commit. When a page
has no line yet (first run after this change), its raw mirror hash in <src>/_state/plaintext_sha256.txt (written
after each successful publish) decides: same hash = unchanged.
"""
import hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_lib as L

TOKEN_SLOT_RE = re.compile(r"(?<![A-Za-z0-9_])(?:github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}|__SH_SCORES_TOKEN__)(?![A-Za-z0-9_])")
_BLOCK_RES = [re.compile(r'(<%s id="%s">)(.*?)(</%s>)' % (tag, bid, tag), re.S) for bid, (tag, _) in L.BLOCKS.items()]
_VARS_RE = re.compile(r'(<style id="sh-vars">)(.*?)(</style>)', re.S)
_MARK_RE = re.compile(r'(<meta name="study-hub-template" content=")sh-[0-9]+((?:-legacy)?">)')


def page_key(h, title=""):
    """(key, token) for a mirror page: key ignores token slots and everything the renderer/template owns."""
    slots = TOKEN_SLOT_RE.findall(h)
    t = TOKEN_SLOT_RE.sub("__SH_SCORES_TOKEN__", h)
    for r in _BLOCK_RES:
        t = r.sub(lambda m: m.group(1) + m.group(3), t)
    t = _VARS_RE.sub(lambda m: m.group(1) + ("L" if "--o:" in m.group(2) else "") + m.group(3), t)
    t = _MARK_RE.sub(lambda m: m.group(1) + "sh-N" + m.group(2), t)
    t = L.BUILD_META_RE.sub("", t)
    key = hashlib.sha256(("title:%s\n" % (title or "")).encode() + t.encode("utf-8")).hexdigest()
    tok = hashlib.sha256("\n".join(slots).encode()).hexdigest()[:16] if slots else "-"
    return key, tok


def mirror_pages(src):
    """Same walk as sh_stage.py: every .html, skipping folders that start with '_' or '.'."""
    out = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if not d.startswith("_") and not d.startswith(".")]
        out += [os.path.relpath(os.path.join(root, f), src).replace(os.sep, "/") for f in files if f.endswith(".html")]
    return sorted(out)


def read_keys(p):
    d = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.split()
            if len(parts) == 3:
                d[parts[2]] = (parts[0], parts[1])
    return d


def read_plain(p):
    d = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("  ", 1)
            if len(parts) == 2:
                d[parts[1]] = parts[0]
    return d


def pending_pages(manifest):
    try:
        import sh_scores as S
        return {json.loads(v).get("page", "") + "index.html" for v in S.pending(manifest).values()}
    except Exception:
        return set()


def plan(src, repo, force=False):
    titles = {}
    manifest = os.path.join(repo, "manifest.json")
    try:
        for it in json.load(open(manifest, encoding="utf-8")):
            titles[it["path"].rstrip("/") + "/index.html"] = it["title"]
    except Exception:
        pass
    keys = read_keys(os.path.join(src, "_state", "page_keys.txt"))
    plain = read_plain(os.path.join(src, "_state", "plaintext_sha256.txt"))
    pend = pending_pages(manifest)
    rows, newkeys = [], {}
    for rel in mirror_pages(src):
        raw = open(os.path.join(src, rel), "rb").read()
        key, tok = page_key(raw.decode("utf-8"), titles.get(rel))
        newkeys[rel] = (key, tok)
        hub = bool(L.HUB_RE.match(rel))
        prev = keys.get(rel)
        if force:
            c, why = "force", "FORCE=1 (re-render all)"
        elif not os.path.exists(os.path.join(repo, rel)):
            c, why = "new", "no committed page yet"
        elif rel in pend and not hub:
            c, why = "rebuilt", "pending provenance record from sh_page.py or attach"
        elif prev is None:
            if plain.get(rel) == hashlib.sha256(raw).hexdigest():
                c, why = "unchanged", "same as the last publish (first run with page keys)"
            else:
                c, why = "content", "changed since the last publish (first run with page keys)"
        elif prev[0] != key:
            c, why = "content", "own content changed"
        elif prev[1] != tok:
            c, why = "token", "only the scores token changed"
        else:
            c, why = "unchanged", ""
        if hub and c in ("content", "new"):
            c = "hub"
        rows.append((c, rel, why))
    return rows, newkeys


def main():
    a = [x for x in sys.argv[1:] if x != "--force"]
    if len(a) != 5 or a[0] != "plan":
        sys.exit(__doc__)
    _, src, repo, out_plan, out_keys = a
    rows, newkeys = plan(src, repo, force="--force" in sys.argv)
    with open(out_plan, "w", encoding="utf-8") as f:
        for c, rel, why in rows:
            f.write("%s\t%s\t%s\n" % (c, rel, why))
    with open(out_keys, "w", encoding="utf-8") as f:
        for rel in sorted(newkeys):
            f.write("%s %s %s\n" % (newkeys[rel][0], newkeys[rel][1], rel))
    ch = [(c, rel, why) for c, rel, why in rows if c != "unchanged"]
    for c, rel, why in ch:
        if c == "token":
            print("TOKEN-ONLY: %s: %s; learning-loop check (B1-B6) skipped" % (rel[: -len("index.html")], why))
        print("CHANGED (%s) %s%s" % (c, rel, (": " + why) if why else ""))
    print("changed %d of %d pages; %d unchanged keep their committed encrypted file (not re-encrypted, not checked)"
          % (len(ch), len(rows), len(rows) - len(ch)))


if __name__ == "__main__":
    main()
