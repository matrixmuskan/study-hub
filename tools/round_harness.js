#!/usr/bin/env node
// Used by tools/sh_rounds.py (rule R14). Runs a logger source (assets/js/shlog.js or a page's SHLog copy) with fetch
// stubbed, records the attempts given as JSON, and prints the queued payloads as JSON. Nothing is sent.
// Usage: node tools/round_harness.js <logger.js or page.html> <subject> '<JSON list of SHLog.record arguments>'
'use strict';
const fs = require('fs'), vm = require('vm');
const [file, subject, recs] = process.argv.slice(2);
const h = fs.readFileSync(file, 'utf8'), i = h.indexOf('var SHLog=');
if (i < 0) { console.log(JSON.stringify({ nologger: true })); process.exit(0); }
const code = h.slice(i, h.indexOf('})();', h.indexOf('return {init:init', i)) + 5);
const store = {}, sent = [];
const ctx = { document: { getElementById: () => null, querySelector: () => null },
  localStorage: { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = String(v) } },
  setTimeout: () => 0, navigator: { onLine: true }, location: { protocol: 'https:', pathname: '/t/' },
  fetch: (u, o) => { sent.push(JSON.parse(o.body)); return Promise.resolve({ status: 201 }) },
  btoa: s => Buffer.from(s, 'binary').toString('base64'), TextEncoder, Intl, Uint8Array, crypto: require('crypto').webcrypto,
  JSON, Math, Date, String, Array, Object, RegExp, Promise, isFinite, unescape, escape, encodeURIComponent, decodeURIComponent };
vm.createContext(ctx);
(async () => {
  vm.runInContext(code + '\nthis.SHLog=SHLog;', ctx);
  if (ctx.SHLog.allow) ctx.SHLog.allow({ ids: ['q1-1', 'q1-2', 'q1-3', 'q1-4', 'q1-5'], traps: ['opposite'] });
  ctx.SHLog.init({ grade: 'G3', subject: subject, lesson: 'T', token: 'test-token' });
  for (const r of JSON.parse(recs)) ctx.SHLog.record(r);
  await ctx.SHLog.flush();
  console.log(JSON.stringify({ payloads: sent.map(b => JSON.parse(Buffer.from(b.content, 'base64').toString('utf8'))),
    messages: sent.map(b => b.message) }));
})().catch(e => console.log(JSON.stringify({ error: String(e && e.message || e) })));
