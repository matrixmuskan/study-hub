#!/usr/bin/env node
// Regression test for assets/js/spellguard.js (the SpellingBee typed-text drop). CI, no secrets, made-up data only.
// The repo is public: the fixture uses made-up 3-letter terms and a public list of everyday words (not a school list,
// not the child's name, not private terms, no hashes). A local run with the real word list and the private terms from
// ~/.study-hub.env is done on the box and never committed (counts only).
//   attack: 10 terms x 50 words x 8 ways = 4,000 pairs; at most 14 may leak (kept with the term still in typed).
//   real misspellings: every kid-like 1- and 2-edit misspelling of the words must be kept (100%).
'use strict';
const G = require('../assets/js/spellguard.js'), S = require('./spellguard_sets.js');
const TERMS = ['zov', 'qux', 'jeb', 'vik', 'pom', 'lur', 'dax', 'fen', 'tib', 'wom'];   // made up
const WORDS = ['garden', 'pencil', 'window', 'basket', 'ladder', 'rocket', 'puzzle', 'button', 'carpet', 'helmet',
  'jacket', 'kitten', 'lemon', 'magnet', 'napkin', 'orange', 'parrot', 'rabbit', 'saddle', 'tunnel', 'velvet', 'wagon',
  'yellow', 'zipper', 'anchor', 'bridge', 'candle', 'dragon', 'engine', 'forest', 'giant', 'hammer', 'island', 'jungle',
  'kettle', 'lantern', 'meadow', 'needle', 'ocean', 'planet', 'quilt', 'river', 'silver', 'turtle', 'umbrella',
  'village', 'whistle', 'blanket', 'chimney', 'thunder'];
let bad = 0;
const ok = (c, m) => { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) bad++; };
// rule
ok(G.keep('eliet', 'elite') && G.keep('preclaim', 'proclaim'), 'near misses kept (eliet, preclaim)');
ok(!G.keep('zzzzzzz', 'proclaim'), 'far-off answer dropped');
ok(G.keep('responsibilty', 'responsibility') && G.keep('rsponsibilty', 'responsibility') && G.keep('rsponsiblty', 'responsibility') && !G.keep('rsponsblty', 'responsibility'),
  'limit max(2, floor(len/4)): a 14-letter word keeps distance 3, drops 4');
ok(G.keep('ladderxy', 'ladder') && !G.keep('ladderxyz', 'ladder'), 'at most 2 letters longer than the target');
ok(!G.keep('', 'ladder') && !G.keep('ladder', ''), 'blank typed or no target: dropped');
// sets
const A = S.attack(TERMS, WORDS), L = S.leaks(G, A);
ok(A.length === 4000, 'attack set has 4,000 pairs (' + A.length + ')');
ok(L.length <= 14, 'attack leaks: ' + L.length + ' of ' + A.length + ' (limit 14)');
const M = S.misspellings(WORDS, G.lev), kept = M.filter(p => G.keep(p.typed, p.word)).length;
ok(M.length > 0 && kept === M.length, 'real 1- and 2-edit misspellings kept: ' + kept + ' of ' + M.length + ' (100% needed)');
console.log('spellguard regression: ' + bad + ' failed');
process.exitCode = bad ? 1 : 0;
