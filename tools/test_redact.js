#!/usr/bin/env node
// Headless test of the score logger's privacy code (privacy v4) inside real (decrypted or staged) pages.
// Usage: STUDY_HUB_BLOCKLIST='word1|word2' node tools/test_redact.js page1.html [page2.html ...]
// For each page it runs the page's own SHLog copy, records an attempt full of free text (question text, typed answers,
// option text, notes in details, and every private term in plain, Capitalized, UPPER and possessive form), sends it to a
// stub fetch, and checks:
//   - the file holds no private term and no free text: a missed item has only n, id, picked/correct option letters,
//     value (a number or a known trap key), trap (a known trap key), blank, typed and item; details hold only the fixed
//     keys, with numbers, booleans and known ids (a private word in details.who or details.section is dropped);
//   - ids and trap keys the page did not list are dropped, and the useful facts stay: the trap key, a typed number,
//     the picked letter, and blank only for a blank answer;
//   - the PUT sets author and committer to Study Hub Bot;
//   - the page has no sh-redact element (no private-word list in any form);
//   - the one exception: subject SpellingBee with SHLog.allow({spelling:true}) sends typed as letters a-z (max 40) and
//     a trap key only from the fixed spelling list; any other subject asking for it gets the boolean only;
//   - SpellingBee pages: the page's SpellGuard runs on each private term (and the child's first name) typed as a near
//     try at a word, then the spelling path of the logger; none of them may be sent (0 hits).
// Prints counts only, never the terms. The blocklist is optional: without it, the free-text checks still run.
'use strict';
const fs = require('fs'), vm = require('vm');
const terms = (process.env.STUDY_HUB_BLOCKLIST || '').split('|').map(s => s.replace(/\\b|[()^$?*+\[\]{}\\]/g, '').trim()).filter(s => s.length >= 2);
const ID = /^[A-Za-z0-9_.:-]{1,40}$/, LET = /^[A-H]$/;
const TOP = new Set(['v', 'grade', 'subject', 'lesson', 'kind', 'score', 'total', 'pct', 'missed', 'details', 'clientTime', 'tz', 'page', 'build']);
const MISS = new Set(['n', 'id', 'picked', 'correct', 'value', 'trap', 'blank', 'typed', 'item']);
function onlyFacts(d, depth) {
  if (Array.isArray(d)) return depth < 4 && d.every(x => onlyFacts(x, depth + 1));
  if (d && typeof d === 'object') return depth < 4 && Object.keys(d).every(k => ID.test(k) && onlyFacts(d[k], depth + 1));
  return typeof d === 'number' || typeof d === 'boolean' || (typeof d === 'string' && ID.test(d));
}
let bad = 0, pages = 0, spellGuardRuns = 0, spellGuardTerms = 0;
for (const file of process.argv.slice(2)) {
  const h = fs.readFileSync(file, 'utf8');
  const i = h.indexOf('var SHLog=');
  if (i < 0) continue;
  pages++;
  const j = h.indexOf('})();', h.indexOf('return {init:init', i));
  const code = h.slice(i, j + 5);
  const store = {}, sent = [];
  const ctx = {
    document: { getElementById: () => null, querySelector: () => null },
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
    if (typeof ctx.SHLog.allow !== 'function') throw new Error('logger has no allow()');
    ctx.SHLog.allow({ ids: ['q1-1', 'q1-2', 'q1-3', 'q2-1'], traps: ['opposite'], sections: ['mock'], values: ['90'], build: 'abcdef0123456789' });
    ctx.SHLog.init({ grade: 'G3', subject: 'T', lesson: 'T', token: 'test-token' });
    const forms = [];
    terms.forEach(t => forms.push(t.toLowerCase(), t[0].toUpperCase() + t.slice(1).toLowerCase(), t.toUpperCase(), t + "'s"));
    const words = forms.join(', ') || 'Some free text here';
    const w0 = (terms[0] || 'someone').toLowerCase();
    ctx.SHLog.record({ kind: 'mock', score: 1, total: 10, missed: [
      { n: 1, q: 'Who wrote this? ' + words, word: words, sense: words, topic: words, trap: words, picked: 'B. ' + words, correct: 'C. ' + words },
      { n: 2, id: 'q1-2', q: 'Typed', picked: words + ' did it', correct: 'the answer ' + words, typed: true, blank: false },
      { n: 3, id: 'q1-3 ' + words, picked: '(blank)', correct: 'A. x' },
      { n: 4, id: 'q2-1', picked: null, value: '90', trap: 'opposite', typed: true, blank: false },
      { n: 5, id: w0, picked: null, value: w0, trap: w0, typed: true, blank: false },
      { n: 6, k: 2, picked: 'Option text ' + words, correct: 'Other text', type: 'trap' },
      { n: 7, q: 'Checklist item ' + words, type: 'checklist', sense: w0 },
      { n: 8, id: 'q1-1', picked: 'C', trap: 'opposite', blank: false },
      { n: 9, id: 'q1-2', picked: null, trap: 'opposite', type: 'trap', blank: true },
      { n: 10, id: 'q1-3', picked: null, value: '85', trap: 'opposite', typed: true, blank: false }],
      details: { note: words, who: w0, scorer: w0, section: w0, mode: 'test', answered: 3, ok: true, round: 2,
                 rubric: { organization: 2, who: words }, partScores: [{ part: 1, score: 2, total: 3, who: w0 }], list: [1, words, 'ab'] } });
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
    const M = p.missed;
    if (M[0].picked !== 'B' || M[0].correct !== 'C' || M[0].id !== 'mock-1' || M[0].blank !== false || M[0].trap !== undefined) fails.push('item 1: option letter, made id, or free-text trap wrong');
    if (M[1].typed !== true || M[1].picked !== undefined || M[1].value !== undefined || M[1].blank !== false) fails.push('item 2: a typed word must be dropped, not marked blank');
    if (M[2].blank !== true || M[2].id !== 'mock-3') fails.push('item 3: blank or unknown id not handled');
    if (M[3].value !== '90' || M[3].trap !== 'opposite' || M[3].blank !== false || M[3].id !== 'q2-1') fails.push('item 4: listed typed number and its trap key not logged');
    if (M[4].id !== 'mock-5' || M[4].value !== undefined || M[4].trap !== undefined) fails.push('item 5: an unknown word passed as id, value or trap');
    if (M[5].picked !== 'C' || M[5].trap !== 'trap' || M[5].blank !== false || M[5].typed !== false) fails.push('item 6: option index k not mapped to a letter, or fixed trap key lost');
    if (M[6].blank !== false || M[6].typed !== false || M[6].item !== 'checklist') fails.push('item 7: a checklist item is not a blank answer');
    if (M[7].picked !== 'C' || M[7].trap !== 'opposite') fails.push('item 8: picked letter and trap key not logged');
    if (M[8].blank !== true || M[8].trap !== undefined) fails.push('item 9: a blank item got a trap key');
    if (M[9].value !== '85' || M[9].trap !== undefined) fails.push('item 10: a typed answer the page does not list got a trap key');
    if (p.build !== 'abcdef0123456789') fails.push('no build id');
    const D = p.details;
    if (!onlyFacts(D, 0) || D.answered !== 3 || D.round !== 2 || D.mode !== 'test' || D.rubric.organization !== 2 || D.partScores[0].score !== 2) fails.push('allowed details lost');
    if ('who' in D || 'scorer' in D || 'note' in D || 'ok' in D || 'list' in D || 'section' in D || 'who' in D.rubric || 'who' in D.partScores[0]) fails.push('details let an unknown key or word through');
    const bot = 'study-hub-bot@users.noreply.github.com';
    if (!sent[0].committer || sent[0].committer.email !== bot || !sent[0].author || sent[0].author.email !== bot) fails.push('PUT does not set author and committer to Study Hub Bot');
    if (/id="sh-redact"/.test(h)) fails.push('page still has an sh-redact element');
    // Spelling exception: only subject SpellingBee with SHLog.allow({spelling:true}) sends the typed letters and a
    // trap key from the fixed spelling list. Any other subject that asks for it still sends the boolean only.
    const SPELL = new Set(['double_letter', 'silent_letter', 'vowel_swap', 'ending', 'homophone', 'other']);
    const spellRun = async (subject) => {
      const st = {}, out2 = [];
      const c2 = Object.assign({}, ctx, { localStorage: { getItem: k => st[k] || null, setItem: (k, v) => { st[k] = String(v) } },
        fetch: (url, o) => { out2.push(JSON.parse(o.body)); return Promise.resolve({ status: 201 }) } });
      vm.createContext(c2);
      vm.runInContext(code + '\nthis.SHLog=SHLog;', c2);
      c2.SHLog.allow({ ids: ['q1-1', 'q1-2', 'q1-3', 'q1-4'], spelling: true });
      c2.SHLog.init({ grade: 'G3', subject: subject, lesson: 'T', token: 'test-token' });
      c2.SHLog.record({ kind: 'game', score: 1, total: 5, missed: [
        { n: 1, id: 'q1-1', value: 3, text: ' Preclaim! ', trap: 'vowel_swap', blank: false, typed: true },
        { n: 2, id: 'q1-2', value: 1, text: 'the answer ' + words + ' ' + 'x'.repeat(60), trap: 'opposite', blank: false, typed: true },
        { n: 3, id: 'q1-3', value: null, text: '', trap: 'other', blank: true, typed: true },
        { n: 4, id: 'q1-4', value: 2, text: 'eliet', trap: words, blank: false, typed: true }] });
      await c2.SHLog.flush();
      return out2.length ? JSON.parse(Buffer.from(out2[0].content, 'base64').toString('utf8')) : null;
    };
    const sp = await spellRun('SpellingBee');
    if (!sp) fails.push('spelling: no PUT');
    else {
      const S = sp.missed;
      S.forEach((m, k) => {
        if (!Object.keys(m).every(x => MISS.has(x))) fails.push('spelling item ' + (k + 1) + ' has an unexpected field');
        if (typeof m.typed !== 'string' || !/^[a-z]{0,40}$/.test(m.typed)) fails.push('spelling item ' + (k + 1) + ' typed is not letters a-z, max 40');
        if (m.trap !== undefined && !SPELL.has(m.trap)) fails.push('spelling item ' + (k + 1) + ' trap is not in the fixed spelling list');
      });
      if (S[0].typed !== 'preclaim' || S[0].trap !== 'vowel_swap' || S[0].value !== '3') fails.push('spelling item 1: typed letters, trap or letter position lost');
      if (S[1].typed.length !== 40 || S[1].trap !== undefined) fails.push('spelling item 2: not cut to 40 letters, or a trap key outside the list passed');
      if (S[2].typed !== '' || S[2].trap !== undefined || S[2].blank !== true) fails.push('spelling item 3: a blank item got text or a trap key');
      if (S[3].typed !== 'eliet' || S[3].trap !== undefined) fails.push('spelling item 4: free-text trap passed');
    }
    // SpellingBee pages: the page's own SpellGuard (src/spellguard.js) runs before the record is queued. Run the
    // spelling path with each private term and the child's first name typed as a near try at a word: 0 hits expected.
    if (/G\d+\/SpellingBee\//.test(file.replace(/\\/g, '/')) && h.includes('SpellGuard')) {
      const gs = h.indexOf('/* SpellGuard'), ge = h.indexOf('</script>', gs);
      const dm = /<script type="application\/json" id="sp-data">([\s\S]*?)<\/script>/.exec(h);
      const guard = dm ? JSON.parse(dm[1]).guard : null;
      const kid = (process.env.STUDY_HUB_KID_FIRST_NAME || '').trim();
      const all = terms.concat(kid ? [kid] : []);
      if (gs < 0 || !guard) fails.push('spelling page has no SpellGuard code or guard data');
      else if (all.length) {
        const gx = { module: { exports: {} }, TextEncoder, Uint8Array, Promise, Math, String, Array, parseInt };
        vm.createContext(gx); vm.runInContext(h.slice(gs, ge), gx);
        const SG = gx.module.exports;
        const items = all.map((t, k) => ({ n: k + 1, id: 'q1-' + (k + 1), value: 1, blank: false, typed: true, text: t, trap: 'other', word: t.toLowerCase() + 'x' }));
        const kept = await SG.filter(items, guard, require('crypto').webcrypto);
        const st = {}, out3 = [];
        const c3 = Object.assign({}, ctx, { localStorage: { getItem: k => st[k] || null, setItem: (k, v) => { st[k] = String(v) } },
          fetch: (url, o) => { out3.push(JSON.parse(o.body)); return Promise.resolve({ status: 201 }) } });
        vm.createContext(c3); vm.runInContext(code + '\nthis.SHLog=SHLog;', c3);
        c3.SHLog.allow({ ids: items.map(x => x.id), spelling: true });
        c3.SHLog.init({ grade: 'G3', subject: 'SpellingBee', lesson: 'T', token: 'test-token' });
        c3.SHLog.record({ kind: 'game', score: 0, total: items.length, missed: kept });
        await c3.SHLog.flush();
        const o3 = out3.length ? Buffer.from(out3[0].content, 'base64').toString('utf8') : '';
        const norm = t => t.normalize('NFD').toLowerCase().replace(/[^a-z]/g, '');
        const typedOut = o3 ? JSON.parse(o3).missed.map(m => m.typed) : [];
        const hits = all.filter(t => typedOut.includes(norm(t)) || new RegExp('(^|[^A-Za-z])' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '($|[^A-Za-z])', 'i').test(o3)).length;
        if (!o3) fails.push('spelling guard run: no PUT');
        else if (hits) fails.push('spelling guard: ' + hits + ' of ' + all.length + ' private terms sent as typed text');
        else spellGuardRuns++, spellGuardTerms = all.length;
      }
    }
    const ns = await spellRun('WW');
    if (!ns || ns.missed.some(m => m.typed !== true || 'trap' in m)) fails.push('a non-SpellingBee page that asks for spelling still got typed text or a spelling trap');
  })().catch(e => fails.push('logger did not run: ' + e.message)).then(() => {
    if (fails.length) { bad++; console.log('FAIL ' + file.split('/').slice(-4).join('/') + ': ' + fails.join('; ')); }
    else console.log('ok   ' + file.split('/').slice(-4).join('/') + ': no free text, 0 of ' + terms.length + ' terms, bot identity');
  });
}
process.on('beforeExit', () => {
  if (process.exitCode === undefined) {
    console.log('privacy test: ' + pages + ' logger pages, ' + bad + ' failed' + (spellGuardRuns ? '; spelling guard: ' + spellGuardRuns + ' page(s), ' + spellGuardTerms + ' private terms typed, 0 sent' : ''));
    process.exitCode = bad || !pages ? 1 : 0;
  }
});
