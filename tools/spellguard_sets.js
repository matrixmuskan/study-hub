// Test sets for assets/js/spellguard.js (shared by tools/test_spellguard.js and local private runs).
// attack(terms, words): every term glued onto or into every word in 8 ways: before the word, after the word, and
//   inside it after letter 1, 2, a third, the middle, and before the last 2 and the last letter.
// leaks(G, pairs): pairs the guard keeps whose typed text still holds the whole term (and the word itself does not).
// misspellings(words): kid-like misspellings at Levenshtein distance 1 or 2: every 1-edit (letter left out, letters
//   swapped, letter doubled, vowel changed) plus, per word, up to 12 two-edit ones (two of those), chosen in a fixed order.
'use strict';
function mid(w) { return Math.floor(w.length / 2); }
function glue(t, w) {
  const at = [0, 1, 2, Math.floor(w.length / 3), mid(w), w.length - 2, w.length - 1, w.length];
  return at.map(k => w.slice(0, k) + t + w.slice(k));
}
function attack(terms, words) {
  const out = [];
  for (const t of terms) for (const w of words) for (const typed of glue(t, w)) out.push({ term: t, word: w, typed });
  return out;
}
function leaks(G, pairs) {
  return pairs.filter(p => p.typed !== p.word && G.keep(p.typed, p.word) && G.norm(p.typed).includes(G.norm(p.term)) && !G.norm(p.word).includes(G.norm(p.term)));
}
const V = 'aeiou';
function one(w) {
  const s = new Set();
  for (let i = 0; i < w.length; i++) {
    s.add(w.slice(0, i) + w.slice(i + 1));
    s.add(w.slice(0, i) + w[i] + w.slice(i));
    if (i < w.length - 1 && w[i] !== w[i + 1]) s.add(w.slice(0, i) + w[i + 1] + w[i] + w.slice(i + 2));
    if (V.includes(w[i])) for (const v of V) if (v !== w[i]) s.add(w.slice(0, i) + v + w.slice(i + 1));
  }
  s.delete(w);
  return [...s].sort();
}
function misspellings(words, lev) {
  const out = [];
  for (const w of words) {
    const a = one(w).filter(x => lev(x, w) <= 2);
    a.forEach(x => out.push({ word: w, typed: x }));
    const seen = new Set(a.concat([w])), two = [];
    for (const x of a) for (const y of one(x)) if (!seen.has(y) && lev(y, w) === 2) { seen.add(y); two.push(y); }
    two.sort();
    const step = Math.max(1, Math.floor(two.length / 12));
    for (let i = 0, n = 0; i < two.length && n < 12; i += step, n++) out.push({ word: w, typed: two[i] });
  }
  return out;
}
module.exports = { glue, attack, leaks, one, misspellings };
