#!/usr/bin/env python3
"""Token-only rebuild exemption (sh_provenance.token_only_change / token_only_rebuild). Made-up pages and made-up
tokens built at run time (no real token, no network). A throwaway git repo holds a page encrypted the StatiCrypt
3.5.x way with a dummy password. Run: python3 tools/test_token_only.py"""
import atexit, hashlib, hmac, json, os, random, shutil, string, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh_provenance as P
import sh_decrypt as D

rnd = random.SystemRandom()
an = string.ascii_letters + string.digits
def fake():  # same shape as a fine-grained token; built here so no token-like text is in this file
    return "github" + "_pat_" + "".join(rnd.choice(an) for _ in range(22)) + "_" + "".join(rnd.choice(an) for _ in range(59))
PH = "__SH_SCORES" + "_TOKEN__"
T1, T2, T3 = fake(), fake(), fake()
n = 0
def check(name, got, want):
    global n
    n += 1
    if got != want:
        print("FAIL: %s (got %r, want %r)" % (name, got, want)); sys.exit(1)
    print("ok   " + name)

def page(tok, body="Q1. Pick the noun.", extra=""):
    return ('<html><body><h1>Lesson</h1><p>%s</p><script type="application/json" id="sh-data">'
            '{"questions": [{"id": "q1-1"}], "token": "%s"}</script>%s</body></html>' % (body, tok, extra))

# 1. pure text rule
C = P.token_only_change
check("pass: old token -> new token, everything else identical", C(page(T2), page(T1)), True)
check("pass: placeholder -> token", C(page(T1), page(PH)), True)
check("pass: token -> placeholder", C(page(PH), page(T1)), True)
check("fail: identical pages (nothing to exempt)", C(page(T1), page(T1)), False)
check("fail: token plus a content change", C(page(T2, body="Q1. Pick the verb."), page(T1)), False)
check("fail: token plus one added byte at the end", C(page(T2) + " ", page(T1)), False)
check("fail: token plus a change right after the token (boundary)", C(page(T2 + "x"), page(T1)), False)
check("fail: token plus a change right before the token (boundary)", C(page("x" + T2), page(T1)), False)
check("fail: token plus an extra token slot added", C(page(T2, extra="<i>%s</i>" % T3), page(T1)), False)
check("fail: a token slot removed", C(page(""), page(T1)), False)
check("fail: content change only (same token)", C(page(T1, body="Q1. Pick the verb."), page(T1)), False)
check("fail: content change only, no token slot at all", C("<p>a</p>", "<p>b</p>"), False)
check("fail: token swapped for a non-token value", C(page("ci-dummy"), page(T1)), False)
check("fail: classic-shape value is not a slot", C(page("ghp_" + "a" * 36), page(T1)), False)

# 2. against a committed, encrypted page (what publish.sh does)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
def encrypt(plain, pw, salt):
    key = bytes.fromhex(D.hash_password(pw, salt)); iv = os.urandom(16)
    pd = padding.PKCS7(128).padder(); raw = pd.update(plain.encode()) + pd.finalize()
    e = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor(); ct = e.update(raw) + e.finalize()
    msg = iv.hex() + ct.hex(); mac = hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()
    cfg = {"staticryptEncryptedMsgUniqueVariableName": mac + msg, "staticryptSaltUniqueVariableName": salt}
    return "<html><script>var staticryptConfig = %s;</script></html>\n<!-- study-hub-template: sh-2 -->\n" % json.dumps(cfg)

old_umask = os.umask(0o077)
W = tempfile.mkdtemp(prefix="sh-tokonly.")
atexit.register(shutil.rmtree, W, True)  # throwaway temp folder made by this test
repo, stage = os.path.join(W, "repo"), os.path.join(W, "stage")
PW, SALT, rel = "dummy-%d" % rnd.randrange(10**9), "b93bbaf35459951c47721d1f3eaeb5b9", "G3/WW/LessonX/"
os.makedirs(os.path.join(repo, rel)); os.makedirs(os.path.join(stage, rel))
open(os.path.join(repo, rel, "index.html"), "w").write(encrypt(page(T1), PW, SALT))
g = lambda *a: subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t"] + list(a), check=True, capture_output=True)
g("init", "-q"); g("add", "-A"); g("commit", "-qm", "page")
def staged(text):
    open(os.path.join(stage, rel, "index.html"), "w").write(text)
R = lambda pw=PW, path=rel: P.token_only_rebuild(path, stage, repo, pw)[0]
staged(page(T2)); check("pass: staged page differs from the committed page only at the token", R(), True)
staged(page(PH)); check("pass: staged page has the placeholder where the committed page had the token", R(), True)
staged(page(T2, body="Q1. Pick the verb.")); check("fail: staged page has a new token AND a content change", R(), False)
staged(page(T1, body="Q1. Pick the verb.")); check("fail: staged page has a content change only", R(), False)
staged(page(T1)); check("fail: staged page is identical to the committed page", R(), False)
staged(page(T2)); check("fail closed: wrong password", R(pw="wrong-" + PW), False)
check("fail closed: no password", R(pw=""), False)
os.makedirs(os.path.join(stage, "G3/WW/New/")); open(os.path.join(stage, "G3/WW/New/index.html"), "w").write(page(T2))
check("fail closed: page not committed at HEAD (new page)", R(path="G3/WW/New/"), False)
open(os.path.join(repo, rel, "index.html"), "w").write(page(T1)); g("commit", "-qam", "plaintext")
check("fail closed: committed page is not StatiCrypt output", R(), False)
os.umask(old_umask)
print("token-only rebuild tests passed (%d)" % n)
