/* SHLog v1: study-hub score logger. Dependency-free. Paste inside the page's <script>.
   SHLog.init({grade:'G3', subject:'WW', lesson:'Lesson8', token:'(build-time placeholder, see README)'})
   SHLog.record({kind:'mock'|'game'|'retest', score, total, missed:[{q,word,sense,picked,correct,trap}], details:{}})
   Writes one JSON file per attempt to matrixmuskan/study-hub-scores via the GitHub contents API.
   Queue first (localStorage 'shlog_queue'), then PUT. Never throws, never blocks the page. */
var SHLog=(function(){
  'use strict';
  var API='https://api.github.com/repos/matrixmuskan/study-hub-scores/contents/';
  var QKEY='shlog_queue', MAXQ=200, PLACEHOLDER='__SH_SCORES'+'_TOKEN__'; // split so build injection never touches it
  var cfg=null, busy=false, again=false, mem=[]; // mem: fallback queue when localStorage is unavailable
  function p2(n){return (n<10?'0':'')+n}
  function p3(n){return n<10?'00'+n:n<100?'0'+n:''+n}
  function isoLocal(d){var o=-d.getTimezoneOffset(),s=o>=0?'+':'-',a=Math.abs(o);
    return d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate())+'T'+p2(d.getHours())+':'+p2(d.getMinutes())+':'+p2(d.getSeconds())+'.'+p3(d.getMilliseconds())+s+p2(Math.floor(a/60))+':'+p2(a%60)}
  function stamp(d){return d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate())+'T'+p2(d.getHours())+p2(d.getMinutes())+p2(d.getSeconds())}
  function rand4(){var c='abcdefghijklmnopqrstuvwxyz0123456789',s='',i,r=null;
    try{r=new Uint8Array(4);crypto.getRandomValues(r)}catch(e){r=null}
    for(i=0;i<4;i++)s+=c[(r?r[i]:Math.floor(Math.random()*256))%36];return s}
  function b64(str){ // UTF-8 safe base64
    if(typeof TextEncoder!=='undefined'){var by=new TextEncoder().encode(str),bin='',i,C=0x8000;
      for(i=0;i<by.length;i+=C)bin+=String.fromCharCode.apply(null,by.subarray(i,i+C));return btoa(bin)}
    return btoa(unescape(encodeURIComponent(str)))}
  function seg(s){return String(s==null?'':s).replace(/[^A-Za-z0-9_-]/g,'')||'x'}
  function pagePath(){try{var l=location;
    if(l.protocol==='http:'||l.protocol==='https:')return l.pathname;
    return 'local:'+l.pathname.split('/').slice(-4).join('/') // file:// paths can hold a home folder name; keep the tail only
  }catch(e){return ''}}
  function load(){try{var q=JSON.parse(localStorage.getItem(QKEY)||'[]');return Array.isArray(q)?q:[]}catch(e){return mem.slice()}}
  function store(q){if(q.length>MAXQ)q=q.slice(q.length-MAXQ);mem=q.slice();try{localStorage.setItem(QKEY,JSON.stringify(q))}catch(e){}}
  function drop(path){store(load().filter(function(x){return x.path!==path}))}
  function bump(path,status){var q=load();q.forEach(function(x){if(x.path===path){x.tries=(x.tries||0)+1;x.last=status}});store(q)}
  function ready(){return !!(cfg&&cfg.token&&cfg.token!==PLACEHOLDER&&typeof fetch==='function')}
  function put(item){
    return fetch(API+item.path.split('/').map(encodeURIComponent).join('/'),{method:'PUT',
      headers:{'Authorization':'Bearer '+cfg.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},
      body:JSON.stringify({message:item.message,content:item.content})})
    .then(function(r){return r.status},function(){return 0})}
  function flush(){
    try{
      if(busy){again=true;return Promise.resolve({sent:0,left:load().length,busy:true})}
      if(!ready())return Promise.resolve({sent:0,left:load().length});
      if(typeof navigator!=='undefined'&&navigator.onLine===false)return Promise.resolve({sent:0,left:load().length});
      busy=true;var q=load(),sent=0,i=0;
      function next(){
        if(i>=q.length){busy=false;if(again){again=false;setTimeout(flush,0)}return {sent:sent,left:load().length}}
        var it=q[i++];
        return put(it).then(function(st){
          // 201 created. 422 means the path already exists (an earlier try landed, or another tab sent it): also done.
          if(st===201||st===422){drop(it.path);sent++;return next()}
          bump(it.path,st);
          if(st===0||st===401||st===403||st===429||st>=500){busy=false;return {sent:sent,left:load().length,stopped:st}} // offline or token/rate issue: stop, retry later
          return next()})
      }
      return Promise.resolve(next()).catch(function(){busy=false;return {sent:sent,left:load().length}});
    }catch(e){busy=false;return Promise.resolve({sent:0,left:-1})}}
  // Privacy: a typed (free-text) answer is logged as its first 40 characters only. Option picks ('B. ...') stay whole.
  function cut(v){v=String(v);return v.length>40?v.slice(0,40)+'...':v}
  function clean(m){m=m||{};var o={};['n','part','q','word','sense','topic','picked','correct','trap','type'].forEach(function(k){if(m[k]!==undefined)o[k]=m[k]});
    if(typeof o.picked==='string'&&!/^[A-H][.)] /.test(o.picked))o.picked=cut(o.picked);return o}
  // Privacy: names are replaced with [name] before anything leaves the page. The private word list comes from the
  // encrypted page itself (<script id="sh-redact">, base64, written at publish time from STUDY_HUB_BLOCKLIST), never from the repo.
  function redact(t){var res=[];((cfg&&cfg.redact)||['Krishiv']).forEach(function(n){if(n)res.push(String(n).replace(/[.*+?^${}()|[\]\\]/g,'\\$&'))});
    try{var el=document.getElementById('sh-redact');var b=el?JSON.parse(el.textContent):'';if(b)res.push(decodeURIComponent(escape(atob(b))))}catch(e){}
    res.forEach(function(r){try{t=t.replace(new RegExp('\\b(?:'+r+')\\b','gi'),'[name]')}catch(e){}});return t}
  function record(r){
    try{
      if(!cfg)return null;r=r||{};
      var d=new Date(),kind=seg(r.kind||'attempt').toLowerCase();
      var score=+r.score||0,total=+r.total||0;
      var path=[seg(cfg.grade),seg(cfg.subject),seg(cfg.lesson),stamp(d)+'-'+kind+'-'+rand4()+'.json'].join('/');
      var payload={v:1,grade:cfg.grade,subject:cfg.subject,lesson:cfg.lesson,kind:kind,score:score,total:total,
        pct:total?Math.round(score*1000/total)/10:null,
        missed:(r.missed||[]).map(clean),details:r.details||{},
        clientTime:isoLocal(d),tz:(function(){try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch(e){return ''}})(),
        page:pagePath()};
      var item={path:path,message:cfg.grade+' '+cfg.subject+' '+cfg.lesson+' '+kind+' '+score+'/'+total,content:b64(redact(JSON.stringify(payload,null,1))+'\n'),tries:0};
      var q=load();q.push(item);store(q);
      setTimeout(flush,0);
      return {path:path,payload:payload};
    }catch(e){return null}}
  function init(c){
    try{cfg={grade:c.grade||'G3',subject:c.subject,lesson:c.lesson,token:c.token};
      if(!init.bound&&typeof window!=='undefined'&&window.addEventListener){window.addEventListener('online',function(){flush()});init.bound=1}
      setTimeout(flush,1500); // retry anything left from earlier visits, after the page has settled
    }catch(e){}
    return SHLog}
  return {init:init,record:record,flush:flush,queue:load,_b64:b64};
})();
