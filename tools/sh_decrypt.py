#!/usr/bin/env python3
"""Decrypt StatiCrypt 3.5.x pages in-process, for checks only (never commit the output).

Usage: sh_decrypt.py <encrypted_root> <out_root>
The password comes from $STATICRYPT_PASSWORD or ~/.study-hub.env. It is never printed.
The output folder is created private (0700) and holds live plaintext: delete it after the checks.
"""
import hashlib, hmac, json, os, re, sys

CFG_RE = re.compile(r"staticryptConfig\s*=\s*(\{.*?\})\s*;", re.S)


def password():
    pw = os.environ.get("STATICRYPT_PASSWORD", "")
    env = os.path.expanduser("~/.study-hub.env")
    if not pw and os.path.exists(env):
        for line in open(env):
            if line.startswith("STATICRYPT_PASSWORD="):
                pw = line.split("=", 1)[1].strip().strip("'\"")
    return pw


def hash_password(pw, salt):
    s = salt.encode()
    h = hashlib.pbkdf2_hmac("sha1", pw.encode(), s, 1000, 32).hex()
    h = hashlib.pbkdf2_hmac("sha256", h.encode(), s, 14000, 32).hex()
    return hashlib.pbkdf2_hmac("sha256", h.encode(), s, 585000, 32).hex()


def decrypt_html(text, hashed):
    """Return the plaintext page, or None when the file is not StatiCrypt output. Raises on a wrong password."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    m = CFG_RE.search(text)
    if not m:
        return None
    cfg = json.loads(m.group(1))
    signed = cfg["staticryptEncryptedMsgUniqueVariableName"]
    mac, msg = signed[:64], signed[64:]
    key = bytes.fromhex(hashed)
    if not hmac.compare_digest(hmac.new(key, msg.encode(), hashlib.sha256).hexdigest(), mac):
        raise ValueError("signature mismatch (wrong password or salt)")
    iv, ct = bytes.fromhex(msg[:32]), bytes.fromhex(msg[32:])
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    raw = d.update(ct) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    return (u.update(raw) + u.finalize()).decode("utf-8")


def decrypt_tree(src, out, pw=None):
    pw = pw or password()
    if not pw:
        raise SystemExit("sh_decrypt: no STATICRYPT_PASSWORD (env or ~/.study-hub.env)")
    old = os.umask(0o077)
    cache, n = {}, 0
    try:
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("tools", "node_modules")]
            for f in files:
                if not f.endswith(".html"):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, src)
                text = open(p, encoding="utf-8").read()
                m = CFG_RE.search(text)
                if not m:
                    continue
                salt = json.loads(m.group(1)).get("staticryptSaltUniqueVariableName", "")
                if salt not in cache:
                    cache[salt] = hash_password(pw, salt)
                plain = decrypt_html(text, cache[salt])
                dst = os.path.join(out, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "w", encoding="utf-8").write(plain)
                n += 1
    finally:
        os.umask(old)
    return n


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print("decrypted", decrypt_tree(sys.argv[1], sys.argv[2]), "pages")
