/* SpellGuard (Study Hub, SpellingBee pages only): last privacy step before a run is logged.
   For each missed word, typed is dropped (sent as "" with no trap) when it is not a real try at the target word:
     (1) its edit distance (Levenshtein) to the target is more than max(2, floor(target length / 4)), or
     (2) it is more than 2 letters longer than the target.
   The first wrong letter position (value) is kept. No hashes and no word lists: only the distance to the target.
   Inlined into SpellingBee pages by their build (/workspace/spelling-bee/build2.py). Tests: tools/test_spellguard.js.
   SpellGuard.filter(missed) -> Promise of the same list (text/trap cleared on dropped items). */
(function(root){
'use strict';
function norm(s){s=String(s==null?'':s);if(s.normalize)s=s.normalize('NFD');return s.trim().toLowerCase().replace(/[^a-z]/g,'').slice(0,40)}
function lev(a,b){var m=a.length,n=b.length,p=[],q,i,j;for(j=0;j<=n;j++)p[j]=j;
  for(i=1;i<=m;i++){q=[i];for(j=1;j<=n;j++)q[j]=Math.min(p[j]+1,q[j-1]+1,p[j-1]+(a[i-1]===b[j-1]?0:1));p=q}return p[n]}
function far(t,w){return lev(t,w)>Math.max(2,Math.floor(w.length/4))||t.length>w.length+2}
function drop(m){m.text='';m.trap=null;return m}
function keep(text,word){var t=norm(text),w=norm(word);return !!(t&&w)&&!far(t,w)}
function filter(list){return Promise.resolve((list||[]).map(function(m){return keep(m.text,m.word)?m:drop(m)}))}
var api={filter:filter,keep:keep,lev:lev,far:far,norm:norm};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SpellGuard=api;
})(this);
