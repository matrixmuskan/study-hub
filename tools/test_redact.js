#!/usr/bin/env node
// Headless test of the score logger's privacy code (privacy v3) inside real (decrypted or staged) pages.
// Usage: STUDY_HUB_BLOCKLIST='word1|word2' node tools/test_redact.js page1.html [page2.html ...]
// For each page it runs the page's own SHLog copy, records an attempt full of free text (question text, typed answers,
// option text, notes in details, and every private term in plain, Capitalized, UPPER and possessive form), sends it to a
// stub fetch, and checks:
//   - the file holds no private term and no free text: a missed item has only n, id, picked/correct option letters,
//     blank and typed; details hold only numbers, booleans and short ids;
//   - the PUT sets author and committer to Study Hub Bot;
//   - the page has no sh-redact element (no private-word list in any form).
// Prints counts only, never the terms. The blocklist is optional: without it, the free-text checks still run.
'use strict';
const fs = require('fs'), vm = require('vm');
const terms = (process.env.STUDY_HUB_BLOCKLIST || '').split('|').map(s => s.replace(/\\b|[()^$?*+\[\]{}\\]/g, '').trim()).filter(s => s.length >= 2);
const ID = /^[A-Za-z0-9_.:-]{1,40}$/, LET = /^[A-H]$/;
const TOP = new Set(['v', 'grade', 'subject', 'lesson', 'kind', 'score', 'total', 'pct', 'missed', 'details', 'clientTime', 'tz', 'page']);
const MISS = new Set(['n', 'id', 'picked', 'correct', 'blank', 'typed']);
function onlyFacts(d, depth) {
  if (Array.isArray(d)) return d.every(x => typeof x === 'number' || typeof x === 'boolean' || (typeof x === 'string' && ID.test(x)));
  if (d && typeof d === 'object') return depth < 4 && Object.keys(d).every(k => ID.test(k) && onlyFacts(d[k], depth + 1));
  return typeof d === 'number' || typeof d === 'boolean' || (typeof d === 'string' && ID.test(d));
}
let bad = 0, pages = 0;
for (const file of process.argv.slice(2)) {
  const h = fs.readFileSync(file, 'utf8');
  const i = h.indexOf('var SHLog=');
  if (i < 0) continue;
  pages++;
  const j = h.indexOf('})();', h.indexOf('return {init:init', i));
  const code = h.slice(i, j + 5);
  const store = {}, sent = [];
  const ctx = {
    document: { getElementById: () => null },
    localStorage: { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = String(v) } },
    setTimeout: () => 0, navigator: { onLine: true }, location: { protocol: 'https:', pathname: '/test/' },
    fetch: (url, o) => { sent.push(JSON.parse(o.body)); return Promise.resolve({ status: 201 }) },
    btoa: s => Buffer.from(s, 'binary').toString('base64'), atob: s => Buffer.from(s, 'base64').toString('binary'),
    TextEncoder, Intl, Uint8Array, crypto: require('crypto').webcrypto, JSON, Math, Date, String, Array, Object, RegExp,
    Promise, isFinite, unescape, escape, encodeURIComponent, decodeURIComponent,
  };
  vm.createContext(ctx);
  const fails = [];
  (async () => {
    vm.runInContext(code + '\nthis.SHLog=SHLog;', ctx);
    ctx.SHLog.init({ grade: 'G3', subject: 'T', lesson: 'T', token: 'test-token' });
    const forms = [];
    terms.forEach(t => forms.push(t.toLowerCase(), t[0].toUpperCase() + t.slice(1).toLowerCase(), t.toUpperCase(), t + "'s"));
    const words = forms.join(', ') || 'Some free text here';
    ctx.SHLog.record({ kind: 'mock', score: 1, total: 4, missed: [
      { n: 1, q: 'Who wrote this? ' + words, word: words, sense: words, topic: words, trap: words, picked: 'B. ' + words, correct: 'C. ' + words },
      { n: 2, id: 'q1-2', q: 'Typed', picked: words + ' did it', correct: 'the answer ' + words },
      { n: 3, id: 'q1-3 ' + words, picked: '(blank)', correct: 'A. x' }],
      details: { note: words, section: 'mock', answered: 3, ok: true, rubric: { org: 2, who: words }, list: [1, words, 'ab'] } });
    await ctx.SHLog.flush();
    if (sent.length !== 1) throw new Error('no PUT (' + sent.length + ')');
    const out = Buffer.from(sent[0].content, 'base64').toString('utf8');
    const p = JSON.parse(out);
    const leaked = terms.filter(t => new RegExp('(^|[^A-Za-z])' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '($|[^A-Za-z])', 'i').test(out)).length;
    if (leaked) fails.push(leaked + ' of ' + terms.length + ' terms leaked');
    if (/free text|wrote this|did it|the answer/i.test(out)) fails.push('free text in the file');
    if (!Object.keys(p).every(k => TOP.has(k))) fails.push('unexpected top-level field');
    p.missed.forEach((m, k) => {
      if (!Object.keys(m).every(x => MISS.has(x))) fails.push('missed ' + (k + 1) + ' has a field other than n, id, picked, correct, blank, typed');
      if (m.id !== undefined && !ID.test(m.id)) fails.push('missed ' + (k + 1) + ' id is not an id');
      ['picked', 'correct'].forEach(x => { if (m[x] !== undefined && !LET.test(m[x])) fails.push('missed ' + (k + 1) + ' ' + x + ' is not an option letter') });
      ['blank', 'typed'].forEach(x => { if (typeof m[x] !== 'boolean') fails.push('missed ' + (k + 1) + ' ' + x + ' is not a boolean') });
    });
    if (p.missed[0].picked !== 'B' || p.missed[0].correct !== 'C') fails.push('option letters lost');
    if (p.missed[1].typed !== true || p.missed[1].picked !== undefined) fails.push('typed answer not dropped');
    if (p.missed[2].blank !== true || p.missed[2].id !== undefined) fails.push('blank or bad id not handled');
    if (!onlyFacts(p.details, 0) || p.details.answered !== 3 || p.details.ok !== true || p.details.rubric.org !== 2) fails.push('details are not only numbers, booleans and ids');
    const bot = 'study-hub-bot@users.noreply.github.com';
    if (!sent[0].committer || sent[0].committer.email !== bot || !sent[0].author || sent[0].author.email !== bot) fails.push('PUT does not set author and committer to Study Hub Bot');
    if (/id="sh-redact"/.test(h)) fails.push('page still has an sh-redact element');
  })().catch(e => fails.push('logger did not run: ' + e.message)).then(() => {
    if (fails.length) { bad++; console.log('FAIL ' + file.split('/').slice(-4).join('/') + ': ' + fails.join('; ')); }
    else console.log('ok   ' + file.split('/').slice(-4).join('/') + ': no free text, 0 of ' + terms.length + ' terms, bot identity');
  });
}
process.on('beforeExit', () => {
  if (process.exitCode === undefined) {
    console.log('privacy test: ' + pages + ' logger pages, ' + bad + ' failed');
    process.exitCode = bad || !pages ? 1 : 0;
  }
});
