#!/usr/bin/env node
// Headless test of the score logger's privacy code inside real (decrypted or staged) pages.
// Usage: STUDY_HUB_BLOCKLIST='word1|word2' node tools/test_redact.js page1.html [page2.html ...]
// For each page it runs the page's own SHLog copy with its own sh-redact element, records an attempt whose
// question text and typed answer hold every private term (plain, Capitalized, UPPER, possessive), and checks that the
// queued file has [name] for each and none of the terms, and that a long typed answer is cut to 40 characters.
// Prints counts only, never the terms.
'use strict';
const fs = require('fs'), vm = require('vm');
const terms = (process.env.STUDY_HUB_BLOCKLIST || '').split('|').map(s => s.replace(/\\b|[()^$?*+\[\]{}\\]/g, '').trim()).filter(s => s.length >= 2);
if (!terms.length) { console.error('test_redact: STUDY_HUB_BLOCKLIST is empty'); process.exit(2); }
let bad = 0, pages = 0;
for (const file of process.argv.slice(2)) {
  const h = fs.readFileSync(file, 'utf8');
  const i = h.indexOf('var SHLog=');
  if (i < 0) continue;
  pages++;
  const j = h.indexOf('})();', h.indexOf('return {init:init', i));
  const code = h.slice(i, j + 5);
  const m = h.match(/<script type="application\/json" id="sh-redact">([\s\S]*?)<\/script>/);
  const store = {};
  const ctx = {
    document: { getElementById: id => (id === 'sh-redact' && m) ? { textContent: m[1] } : null },
    localStorage: { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = String(v) } },
    setTimeout: () => 0, navigator: { onLine: false }, location: { protocol: 'https:', pathname: '/test/' },
    btoa: s => Buffer.from(s, 'binary').toString('base64'), atob: s => Buffer.from(s, 'base64').toString('binary'),
    TextEncoder, Intl, Uint8Array, crypto: require('crypto').webcrypto, JSON, Math, Date, String, Array, RegExp, unescape, escape,
    encodeURIComponent, decodeURIComponent,
  };
  vm.createContext(ctx);
  let fails = [];
  try {
    vm.runInContext(code + '\nthis.SHLog=SHLog;', ctx);
    ctx.SHLog.init({ grade: 'G3', subject: 'T', lesson: 'T', token: '__SH_SCORES' + '_TOKEN__' });
    const forms = [];
    terms.forEach(t => forms.push(t.toLowerCase(), t[0].toUpperCase() + t.slice(1).toLowerCase(), t.toUpperCase(), t + "'s"));
    const long = 'x'.repeat(30) + ' ' + 'y'.repeat(30);
    ctx.SHLog.record({ kind: 'mock', score: 1, total: 2, missed: [
      { n: 1, q: 'Who wrote this? ' + forms.join(', ') + '.\nLine two ' + terms[0], picked: terms[0] + ' did', correct: 'B. ok' },
      { n: 2, q: 'Long answer', picked: long, correct: 'A. x' }], details: { note: forms.join(' ') } });
    const q = JSON.parse(store.shlog_queue || '[]');
    if (q.length !== 1) throw new Error('no queued attempt');
    const out = Buffer.from(q[0].content, 'base64').toString('utf8');
    const p = JSON.parse(out);
    const leaked = terms.filter(t => new RegExp('(^|[^A-Za-z])' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '($|[^A-Za-z])', 'i').test(out)).length;
    if (leaked) fails.push(leaked + ' of ' + terms.length + ' terms leaked');
    if (!/\[name\]/.test(out)) fails.push('no [name] in output');
    if (p.missed[1].picked.length > 43) fails.push('typed answer not cut to 40 characters');
  } catch (e) { fails.push('logger did not run: ' + e.message); }
  if (fails.length) { bad++; console.log('FAIL ' + file.split('/').slice(-4).join('/') + ': ' + fails.join('; ')); }
  else console.log('ok   ' + file.split('/').slice(-4).join('/') + ': 0 of ' + terms.length + ' terms leak, answers cut to 40');
}
console.log('redaction test: ' + pages + ' logger pages, ' + bad + ' failed');
process.exit(bad || !pages ? 1 : 0);
