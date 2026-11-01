#!/usr/bin/env python3
"""Read and write the PRIVATE score repo matrixmuskan/study-hub-scores (box only, never in CI).

Token: STUDY_HUB_SCORES_TOKEN (env or ~/.study-hub.env). It is never printed.
Test mode: STUDY_HUB_SCORES_DIR=<folder> uses a local folder instead of GitHub (fixtures, no network).
"""
import base64, json, os, sys, time, urllib.error, urllib.request

REPO = "matrixmuskan/study-hub-scores"
API = "https://api.github.com/repos/" + REPO


class ScoresError(Exception):
    pass


def _token():
    t = os.environ.get("STUDY_HUB_SCORES_TOKEN", "").strip()
    if not t:
        p = os.path.expanduser("~/.study-hub.env")
        if os.path.exists(p):
            for line in open(p):
                if line.startswith("STUDY_HUB_SCORES_TOKEN="):
                    t = line.split("=", 1)[1].strip().strip("'\"")
    return t


def local_dir():
    return os.environ.get("STUDY_HUB_SCORES_DIR") or None


def _req(method, url, body=None, tries=3):
    tok = _token()
    if not tok:
        raise ScoresError("STUDY_HUB_SCORES_TOKEN is not set (needed to read and write study-hub-scores)")
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        r = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "study-hub-tools"})
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as ex:
            if ex.code in (404, 409, 422) or ex.code < 500 or i == tries - 1:
                return ex.code, None
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise ScoresError("network error talking to GitHub")
        time.sleep(2 * (i + 1))


def check_access(write=True):
    """Make sure the token reaches the private repo (and may push). Raises ScoresError with a clear message."""
    if local_dir():
        return "local folder " + local_dir()
    st, d = _req("GET", API)
    if st != 200 or not d:
        raise ScoresError("STUDY_HUB_SCORES_TOKEN cannot read %s (HTTP %s). Ask Muskan for a token scoped to it" % (REPO, st))
    if not d.get("private"):
        raise ScoresError("%s is not private. Stop: provenance and error logs must not be public" % REPO)
    if write and not (d.get("permissions") or {}).get("push"):
        raise ScoresError("STUDY_HUB_SCORES_TOKEN cannot write to %s" % REPO)
    return "github " + REPO


def get(path):
    """Return the file bytes, or None when it does not exist."""
    if local_dir():
        p = os.path.join(local_dir(), path)
        return open(p, "rb").read() if os.path.isfile(p) else None
    st, d = _req("GET", API + "/contents/" + urllib.request.quote(path))
    if st == 404:
        return None
    if st != 200 or not isinstance(d, dict):
        raise ScoresError("cannot read %s from %s (HTTP %s)" % (path, REPO, st))
    if d.get("content") is None or d.get("encoding") != "base64" or (d.get("size", 0) > 900000 and not d.get("content")):
        st, b = _req("GET", API + "/git/blobs/" + d["sha"])
        return base64.b64decode(b["content"])
    return base64.b64decode(d["content"])


def _sha(path):
    st, d = _req("GET", API + "/contents/" + urllib.request.quote(path))
    return d.get("sha") if st == 200 and isinstance(d, dict) else None


def put(path, data, message):
    """Create or update one file. Returns 'created', 'updated' or 'same'."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    old = get(path)
    if old == data:
        return "same"
    if local_dir():
        p = os.path.join(local_dir(), path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
        return "updated" if old is not None else "created"
    body = {"message": message, "content": base64.b64encode(data).decode()}
    sha = _sha(path) if old is not None else None
    if sha:
        body["sha"] = sha
    st, _ = _req("PUT", API + "/contents/" + urllib.request.quote(path), body)
    if st not in (200, 201):
        raise ScoresError("cannot write %s to %s (HTTP %s)" % (path, REPO, st))
    return "updated" if old is not None else "created"


def tree(prefix=""):
    """All file paths under prefix."""
    if local_dir():
        out = []
        base = local_dir()
        for root, dirs, fs in os.walk(os.path.join(base, prefix)):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in fs:
                out.append(os.path.relpath(os.path.join(root, f), base).replace(os.sep, "/"))
        return sorted(out)
    st, d = _req("GET", API + "/git/trees/main?recursive=1")
    if st != 200 or not d:
        raise ScoresError("cannot list %s (HTTP %s)" % (REPO, st))
    return sorted(x["path"] for x in d["tree"] if x["type"] == "blob" and x["path"].startswith(prefix))


if __name__ == "__main__":
    try:
        print("scores access ok:", check_access(write="--read" not in sys.argv))
    except ScoresError as ex:
        sys.exit("SCORES ACCESS FAILED: %s" % ex)
