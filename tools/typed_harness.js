#!/usr/bin/env node
// Used by tools/sh_typed.py (rule R13). Runs a page's own SHLog copy with the given subject, turns on the spelling
// exception (SHLog.allow({spelling:true})) and records missed items that carry typed text and spelling trap keys.
// Prints the payload's missed list as JSON (or {"error": ...}). Usage: node tools/typed_harness.js <page.html> <subject>
'use strict';
const fs = require('fs'), vm = require('vm');
const [file, subject] = process.argv.slice(2);
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
  if (ctx.SHLog.allow) ctx.SHLog.allow({ ids: ['q1-1', 'q1-2', 'q1-3'], spelling: true });
  ctx.SHLog.init({ grade: 'G3', subject: subject, lesson: 'T', token: 'test-token' });
  ctx.SHLog.record({ kind: 'game', score: 0, total: 3, missed: [
    { n: 1, id: 'q1-1', value: 2, text: 'preclaim', trap: 'vowel_swap', blank: false, typed: true },
    { n: 2, id: 'q1-2', value: 1, text: 'eliet', trap: 'other', blank: false, typed: 'eliet' },
    { n: 3, id: 'q1-3', picked: 'B', trap: 'double_letter', blank: false }] });
  await ctx.SHLog.flush();
  if (!sent.length) throw new Error('no PUT');
  console.log(JSON.stringify({ missed: JSON.parse(Buffer.from(sent[0].content, 'base64').toString('utf8')).missed }));
})().catch(e => console.log(JSON.stringify({ error: String(e && e.message || e) })));
