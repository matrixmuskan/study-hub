#!/usr/bin/env python3
"""Check Study Hub pages in headless Chrome: links, anchors, images, videos, script errors, screenshots.

Usage:
  sh_browsercheck.py --root DIR [--shots OUT] [--json REPORT]   serve DIR (decrypted plaintext site) locally
  sh_browsercheck.py --live URL [--shots OUT] [--json REPORT]   crawl the live site; log in with $STATICRYPT_PASSWORD
                                                                  (or ~/.study-hub.env). Without a password, only the
                                                                  login pages and their HTTP status are checked.
What it does on every page: opens every tab (nav#nav, [role=tab], nav.map), then checks
  - every <a href>: internal targets exist (HTTP 200), '#id' anchors exist in the DOM, no 'undefined' or '${'
  - every <img>, <video>, <audio>, <source>, <track>, <iframe>, poster: loads (img decoded, video readyState >= 1)
  - every quiz question with an "img" shows that picture inside its own question, above its text, and it decodes
  - no uncaught script errors, no failed requests (4xx/5xx) to the site
Exit code 1 when anything is broken. The password is never printed.
"""
import argparse, functools, http.server, json, os, re, socketserver, sys, threading, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TABS = "nav#nav button, nav#nav a[href^='#'], [role=tab], nav.map a[href^='#']"

COLLECT_JS = r"""async (seenList) => {
  const seen = new Set(seenList || []);
  const out = {links: [], media: [], ids: []};
  document.querySelectorAll('[id]').forEach(e => out.ids.push(e.id));
  document.querySelectorAll('a[name]').forEach(e => out.ids.push(e.getAttribute('name')));
  document.querySelectorAll('a[href]').forEach(a => out.links.push({raw: a.getAttribute('href'), abs: a.href, text: (a.textContent||'').trim().slice(0,40)}));
  const until = async (cond, ms) => { const t0 = Date.now(); while (!cond() && Date.now() - t0 < ms) await new Promise(r => setTimeout(r, 100)); };
  const short = s => { s = s || ''; if (!s.startsWith('data:')) return s;
      const c = s.indexOf(','); return s.slice(0, c > 0 ? Math.min(c, 40) : 40) + ',...' + s.length + ':' + s.slice(-12); };
  for (const img of document.querySelectorAll('img')) {
    const src = img.getAttribute('src') || '';
    if (seen.has('img ' + short(src))) continue;
    if (img.loading === 'lazy') img.loading = 'eager';   // hidden tabs: lazy images would never load
    if (!img.complete || img.naturalWidth === 0) await until(() => img.complete && img.naturalWidth > 0, 8000);
    let ok = img.complete && img.naturalWidth > 0;
    out.media.push({tag: 'img', src: short(src), ok, why: ok ? '' : (src ? 'image did not decode' : 'empty src')});
  }
  for (const v of document.querySelectorAll('video, audio')) {
    const src = v.currentSrc || v.getAttribute('src') || (v.querySelector('source')||{}).src || '';
    if (seen.has(v.tagName.toLowerCase() + ' ' + short(src))) continue;
    if (v.readyState < 1 && !v.error) { if (v.networkState === 0 || v.preload === 'none') { try { v.preload = 'metadata'; v.load(); } catch (e) {} }
      await until(() => v.readyState >= 1 || v.error, 15000); }
    const ok = v.readyState >= 1 && !v.error && (v.tagName === 'AUDIO' || v.videoWidth > 0);
    out.media.push({tag: v.tagName.toLowerCase(), src: short(src), ok, readyState: v.readyState, duration: v.duration,
                    why: ok ? '' : (v.error ? 'media error ' + v.error.code : (src ? 'no metadata (readyState ' + v.readyState + ')' : 'empty src'))});
    const poster = v.getAttribute('poster');
    if (poster !== null) {
      const ok2 = seen.has('poster ' + short(poster)) ? true : await new Promise(r => { const i = new Image(); i.onload = () => r(i.naturalWidth > 0); i.onerror = () => r(false); i.src = poster; setTimeout(() => r(false), 8000); });
      out.media.push({tag: 'poster', src: short(poster), ok: ok2, why: ok2 ? '' : (poster ? 'poster did not load' : 'empty poster')});
    }
    for (const t of v.querySelectorAll('track')) {
      const ok3 = await new Promise(r => { if (t.readyState === 2) return r(true); t.track.mode = 'hidden';
          t.addEventListener('load', () => r(true)); t.addEventListener('error', () => r(false)); setTimeout(() => r(t.readyState === 2), 8000); });
      out.media.push({tag: 'track', src: short(t.getAttribute('src')), ok: ok3, why: ok3 ? '' : 'captions did not load'});
    }
  }
  // question pictures (sh_page "img" on a quiz question): each one renders inside its own question and decodes
  let shd = null; try { shd = JSON.parse((document.getElementById('sh-data') || {}).textContent || 'null'); } catch (e) {}
  const qz = (shd && shd.quizzes) || [];
  for (let zi = 0; zi < qz.length; zi++) for (let i = 0; i < (qz[zi].questions || []).length; i++) {
    const q = qz[zi].questions[i];
    if (!q.img) continue;
    const key = 'qimg quiz-' + zi + ' Q' + (i + 1);
    if (seen.has(key)) continue;
    const qel = document.getElementById('quiz-' + zi + '-q' + i);
    const im = qel && qel.querySelector(':scope > .sh-q__fig img');
    const txt = qel && qel.querySelector(':scope > .sh-q__text');
    const above = !!(im && txt && (im.compareDocumentPosition(txt) & Node.DOCUMENT_POSITION_FOLLOWING));
    if (im && !(im.complete && im.naturalWidth > 0)) await until(() => im.complete && im.naturalWidth > 0, 8000);
    const ok = !!im && above && im.complete && im.naturalWidth > 0;
    out.media.push({tag: 'qimg', src: 'quiz-' + zi + ' Q' + (i + 1), ok,
      why: ok ? '' : (!qel ? 'question not rendered' : !im ? 'question picture missing' : !above ? 'picture is not above the question text' : 'question picture did not decode')});
  }
  for (const f of document.querySelectorAll('iframe, embed, object')) {
    const src = f.getAttribute('src') || f.getAttribute('data') || '';
    out.media.push({tag: f.tagName.toLowerCase(), src: short(src), abs: f.src || '', ok: !!src, why: src ? '' : 'empty src'});
  }
  return out;
}"""


def password():
    import sh_decrypt
    return sh_decrypt.password()


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    h.log_message = lambda *a, **k: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), h)
    srv.daemon_threads = True
    srv.handle_error = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d/" % srv.server_address[1], srv


def status(url, cache={}, tries=3):
    if url in cache:
        return cache[url]
    import time
    for i in range(tries):
        code = _status(url)
        if code in (200, 206, 404, 410):
            break
        time.sleep(2 * (i + 1))
    cache[url] = code
    return code


def _status(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "study-hub-linkcheck/1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            code = r.status
    except urllib.error.HTTPError as ex:
        code = ex.code
    except Exception as ex:
        code = "ERR " + type(ex).__name__
    return code


def external(url):
    """Status for an external link; YouTube and Drive also get an embeddability check."""
    u = urllib.parse.urlparse(url)
    host = u.netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        code = status("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe=""))
        return code == 200, "youtube oembed %s%s" % (code, " (private, removed, or embedding disabled)" if code != 200 else "")
    if "drive.google.com" in host or "docs.google.com" in host:
        m = re.search(r"/d/([\w-]+)", url) or re.search(r"[?&]id=([\w-]+)", url)
        if m:
            code = status("https://drive.google.com/file/d/%s/preview" % m.group(1))
            return code == 200, "drive preview %s%s" % (code, " (not shared publicly or missing)" if code != 200 else "")
    code = status(url)
    return code in (200, 206), "HTTP %s" % code


CHROME_CANDIDATES = ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser")


def launch(p, chrome=None):
    """Start Chrome: the given binary, else Playwright's own Chromium, else a system Chrome. Exit 3 with a clear
    message when none starts."""
    args = ["--autoplay-policy=no-user-gesture-required"]
    tried = []
    if chrome:
        try:
            return p.chromium.launch(executable_path=chrome, args=args), chrome
        except Exception as ex:
            tried.append("%s: %s" % (chrome, str(ex).splitlines()[0][:120]))
    else:
        try:
            return p.chromium.launch(args=args), "playwright chromium"
        except Exception as ex:
            tried.append("playwright chromium: %s" % str(ex).splitlines()[0][:120])
        import shutil
        for c in CHROME_CANDIDATES + tuple(filter(None, (shutil.which("google-chrome"), shutil.which("chromium")))):
            if os.path.exists(c):
                try:
                    return p.chromium.launch(executable_path=c, args=args), c
                except Exception as ex:
                    tried.append("%s: %s" % (c, str(ex).splitlines()[0][:120]))
    print("NO BROWSER: no Chrome could start. Tried:\n  " + "\n  ".join(tried or ["nothing found"]) +
          "\nFix: python3 -m playwright install chromium, or install google-chrome, or set CHROME_PATH", file=sys.stderr)
    sys.exit(3)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--root")
    g.add_argument("--live")
    ap.add_argument("--shots")
    ap.add_argument("--json")
    ap.add_argument("--external", action="store_true", help="also check external links over the network")
    ap.add_argument("--pages", nargs="*", help="check only these pages (paths relative to the root, e.g. G3/WW/Lesson9/index.html)")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"),
                    help="Chrome binary. Default: Playwright's own Chromium, then google-chrome/chromium on PATH")
    ap.add_argument("--probe", action="store_true", help="only check that a browser starts (exit 0), else exit 3")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("NO BROWSER: the playwright Python package is missing. Install: pip install playwright", file=sys.stderr)
        sys.exit(3)
    if a.probe:
        with sync_playwright() as p:
            b, how = launch(p, a.chrome)
            b.close()
        print("browser:", how)
        return
    if not (a.root or a.live):
        ap.error("one of --root or --live is required")

    if a.root:
        base, srv = serve(os.path.abspath(a.root))
        pw = None
    else:
        base = a.live.rstrip("/") + "/"
        pw = password()
        if not pw:
            print("sh_browsercheck: no password; checking login pages and HTTP status only", file=sys.stderr)
    rows, seen, queue = [], set(), [base]
    only = None
    if a.pages:
        only = set()
        for pg in a.pages:
            u = base + (pg[:-len("index.html")] if pg.endswith("index.html") else pg)
            only.add(u)
        queue = sorted(only)

    def add(page, link, kind, ok, cause=""):
        rows.append({"page": page, "link": link, "type": kind, "status": "ok" if ok else "BROKEN", "cause": cause})

    with sync_playwright() as p:
        b, how = launch(p, a.chrome)
        print("browser:", how, file=sys.stderr)
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        while queue:
            url = queue.pop(0)
            key = url.split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            rel = key[len(base):] or "index.html"
            page = ctx.new_page()
            errors, bad = [], []
            page.on("pageerror", lambda ex: errors.append(str(ex)[:160]))
            page.on("response", lambda r: bad.append((r.status, r.url)) if r.status >= 400 and r.url.startswith(base) and not r.url.endswith("/favicon.ico") else None)
            page.on("requestfailed", lambda r: bad.append(("failed " + (r.failure or ""), r.url)) if r.url.startswith(base) and not r.url.startswith("data:") else None)
            try:
                resp = page.goto(key, wait_until="load", timeout=120000)
            except Exception as ex:
                add(rel, key, "page", False, "did not load: %s" % str(ex)[:120]); page.close(); continue
            if not resp or resp.status != 200:
                add(rel, key, "page", False, "HTTP %s" % (resp.status if resp else "none")); page.close(); continue
            if pw is not None and page.query_selector("#staticrypt-password, input[type=password]") and page.evaluate("!!window.staticrypt || !!document.querySelector('#staticrypt-form')"):
                page.fill("#staticrypt-password", pw)
                rm = page.query_selector("#staticrypt-remember")
                if rm and not rm.is_checked():
                    rm.check()
                page.click("#staticrypt-form [type=submit], #staticrypt-decrypt-button, button[type=submit]")
                try:
                    page.wait_for_function("!document.querySelector('#staticrypt-password')", timeout=120000)
                    page.wait_for_load_state("load")
                except Exception:
                    pass
            page.wait_for_timeout(600)
            if page.query_selector("#staticrypt-password"):
                add(rel, key, "page", pw is None, "login page (no password given)" if pw is None else "wrong password or page did not decrypt")
                page.close(); continue
            add(rel, key, "page", True)
            for e in errors:
                add(rel, "(script)", "js", False, "uncaught error: " + e)
            # open every tab so lazy sections render
            print("checking", rel, file=sys.stderr, flush=True)
            checked = []

            def collect():
                d = page.evaluate(COLLECT_JS, checked)
                checked.extend(m["tag"] + " " + m["src"] for m in d["media"])
                return d
            data = [collect()]
            tabs = page.query_selector_all(TABS)
            for i in range(len(tabs)):
                t = page.query_selector_all(TABS)
                if i < len(t):
                    try:
                        t[i].click(timeout=3000); page.wait_for_timeout(250); data.append(collect())
                    except Exception:
                        pass
            if a.shots:
                os.makedirs(a.shots, exist_ok=True)
                name = rel.replace("/index.html", "").replace("/", "_").replace("index.html", "home") or "home"
                if tabs:
                    try: page.query_selector_all(TABS)[0].click(timeout=3000); page.wait_for_timeout(300)
                    except Exception: pass
                page.screenshot(path=os.path.join(a.shots, name + "_1280.png"))
                page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(300)
                page.screenshot(path=os.path.join(a.shots, name + "_390.png"))
            for st, u in bad:
                add(rel, u, "request", False, "%s" % st)
            ids = set(x for d in data for x in d["ids"])
            done = set()
            for d in data:
                for l in d["links"]:
                    raw, absu = l["raw"], l["abs"]
                    if (raw, absu) in done:
                        continue
                    done.add((raw, absu))
                    if "${" in raw or "undefined" in raw or raw.strip() == "":
                        add(rel, raw, "href", False, "template text or empty href in the page"); continue
                    if raw.startswith(("javascript:", "mailto:", "tel:")):
                        continue
                    if raw == "#":
                        continue
                    if raw.startswith("#"):
                        frag = urllib.parse.unquote(raw[1:])
                        add(rel, raw, "anchor", frag in ids, "" if frag in ids else "no element with id '%s'" % frag); continue
                    if absu.startswith(base):
                        target = absu.split("#")[0]
                        code = status(target)
                        ok = code == 200
                        add(rel, raw, "internal", ok, "" if ok else "HTTP %s for %s" % (code, target[len(base):] or "/"))
                        if ok and only is None and target not in seen and (target.endswith("/") or target.endswith(".html")):
                            queue.append(target)
                    elif absu.startswith("http"):
                        if a.external:
                            ok, why = external(absu)
                            add(rel, absu, "external", ok, why)
                    else:
                        add(rel, raw, "href", False, "unsupported link")
                for m in d["media"]:
                    k = (m["tag"], m["src"])
                    if k in done:
                        continue
                    done.add(k)
                    if m["tag"] in ("iframe", "embed", "object") and m.get("abs", "").startswith("http") and not m["abs"].startswith(base):
                        ok, why = external(m["abs"]) if a.external else (m["ok"], "")
                        add(rel, m["abs"], m["tag"], ok, why); continue
                    if "${" in m["src"] or "undefined" in m["src"]:
                        add(rel, m["src"], m["tag"], False, "template text in src"); continue
                    add(rel, m["src"], m["tag"], m["ok"], m.get("why", ""))
            page.close()
        b.close()
    if a.root:
        srv.shutdown()
    broken = [r for r in rows if r["status"] != "ok"]
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=1)
    pages = len([r for r in rows if r["type"] == "page"])
    print("browsercheck: %d pages, %d checks, %d broken" % (pages, len(rows), len(broken)))
    for r in broken:
        print("  BROKEN %-45s %-9s %-60s %s" % (r["page"][:45], r["type"], r["link"][:60], r["cause"]))
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
