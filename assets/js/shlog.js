/* SHLog v1: study-hub score logger. Dependency-free. Paste inside the page's <script>.
   SHLog.init({grade:'G3', subject:'WW', lesson:'Lesson8', token:'(build-time placeholder, see README)'})
   SHLog.record({kind:'mock'|'game'|'retest', score, total, missed:[{n,id,picked,value,trap,blank,typed}], details:{fixed keys}}); SHLog.allow({ids,traps,sections,build})
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
      body:JSON.stringify({message:item.message,content:item.content,committer:BOT,author:BOT})})
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
  /*sh-privacy v4*/
  // Privacy: the logger sends no free text. For each missed item it sends: n, a stable item id, the picked option
  // letter, a value (only a number, or a trap key the page lists for that question), a trap key, and the blank and
  // typed booleans. A value is a number or a wrong answer the page lists. A trap key is sent only for a wrong pick or a
  // listed typed answer: never for a blank item or an unlisted typed answer. Ids and trap keys must be known: listed by the page (SHLog.allow, from sh-data) or made here from
  // the quiz kind and n. details keep only a fixed list of keys with numbers, booleans and known ids. Every file is
  // committed as Study Hub Bot.
  var BOT={name:'Study Hub Bot',email:'study-hub-bot@users.noreply.github.com'};
  var REG={ids:{},traps:{},sections:{},values:{}};
  var TRAPS=['trap','confusion','opposite','near-miss','other-sense','look-alike','related-idea','careless','misread',
    'off-by-one','double-count','unit','sign','order','partial','reversed','distractor'];
  var MODES=['practice','test','mastery','game','mock','retest','all','fix-it','all questions'];
  var NUMK=['answered','blank','round','redoRound','practice','score','total','part','checklistDone','checklistTotal',
    'comprehensionPoints','writingPoints','words','sentences','timerMinutes','minutesUsed','planOpen','fixNextFilled',
    'allMastered','masteredTotal','wordsTotal','stars','seconds','readingComprehension','organization','wordChoice','conventions'];
  var OBJK=['rubric','partScores'];
  var GEN=/^(?:q\d{1,2}|mock|game|retest|quiz|test|attempt|check)-(?:p\d{1,2}-)?\d{1,3}$/;
  TRAPS.forEach(function(t){REG.traps[t]=1});
  function allow(o){try{o=o||{};(o.ids||[]).forEach(function(x){if(typeof x==='string'&&x.length<=40)REG.ids[x]=1});
    (o.traps||[]).forEach(function(x){if(typeof x==='string'&&/^[a-z0-9][a-z0-9_-]{0,31}$/.test(x))REG.traps[x]=1});
    (o.sections||[]).forEach(function(x){if(typeof x==='string'&&x.length<=40)REG.sections[x]=1});
    (o.values||[]).forEach(function(x){if(typeof x==='string'&&x.length<=24)REG.values[x]=1});
    if(o.build&&/^[0-9a-f]{8,64}$/.test(o.build))REG.build=o.build}catch(e){}}
  function known(id){id=id==null?'':String(id);return REG.ids[id]||GEN.test(id)?id:null}
  function num(v){v=v==null?'':String(v).trim();return /^-?\d{1,9}(?:[.,]\d{1,4})?(?:\/\d{1,6})?$/.test(v)?v.replace(',','.'):null}
  function letter(v){if(typeof v==='number')return v>=0&&v<8&&v%1===0?'ABCDEFGH'.charAt(v):null;
    var m=/^\s*([A-H])(?:[.)](?:\s|$)|\s*$)/.exec(v==null?'':String(v));return m?m[1]:null}
  function trapKey(v){v=v==null?'':String(v);return REG.traps[v]?v:null}
  function clean(m,kind){m=m||{};var o={},pk=m.picked,n=Math.floor(+m.n)>0?Math.floor(+m.n):0;
    if(n)o.n=n;
    var id=known(m.id)||(n?known(seg(kind||'attempt').toLowerCase()+'-'+(+m.part>0?'p'+Math.floor(+m.part)+'-':'')+n):null);
    if(id)o.id=id;
    var item=m.type==='checklist';
    var blank=typeof m.blank==='boolean'?m.blank:(!item&&(pk==null||String(pk).trim()===''||String(pk)==='(blank)')&&m.k==null&&m.value==null);
    var L=(typeof m.k==='number')?letter(m.k):letter(pk);
    if(!blank&&L)o.picked=L;
    var typed=typeof m.typed==='boolean'?m.typed:(!item&&!blank&&!L);
    var v0=m.value!=null?m.value:(typed?pk:null),v=num(v0)||(v0!=null&&REG.values[String(v0)]?String(v0):null)||trapKey(m.value);
    if(!blank&&v!=null)o.value=v;
    // a trap key only for a wrong pick, or a typed answer the page lists (REG.values); none for blank or checklist items
    var listed=typed&&v0!=null&&!!REG.values[String(v0).trim().toLowerCase()];
    var t=!blank&&!item&&(o.picked||listed)?(trapKey(m.trap)||trapKey(m.type)):null;
    if(t)o.trap=t;
    if(letter(m.correct))o.correct=letter(m.correct);
    o.blank=!!blank;o.typed=!!typed;if(item)o.item='checklist';return o}
  function cleanAll(list,kind){return (list||[]).slice(0,200).map(function(m){return clean(m,kind)})}
  function facts(d,depth){var o={};depth=depth||0;if(!d||typeof d!=='object'||depth>2)return o;
    Object.keys(d).forEach(function(k){var v=d[k];
      if(NUMK.indexOf(k)>=0&&(typeof v==='number'&&isFinite(v)||typeof v==='boolean'))o[k]=v;
      else if(k==='mode'&&MODES.indexOf(v)>=0)o[k]=v;
      else if(k==='section'&&typeof v==='string'&&(REG.sections[v]||v===''))o[k]=v;
      else if(OBJK.indexOf(k)>=0&&v&&typeof v==='object')o[k]=Array.isArray(v)?v.slice(0,20).map(function(x){return facts(x,depth+1)}):facts(v,depth+1)});
    return o}
  function buildId(){if(REG.build)return REG.build;
    try{var el=document.querySelector('meta[name="sh-build"]'),b=el&&el.getAttribute('content');return b&&/^[0-9a-f]{8,64}$/.test(b)?b:null}catch(e){return null}}
  /*sh-privacy end*/
  function record(r){
    try{
      if(!cfg)return null;r=r||{};
      var d=new Date(),kind=seg(r.kind||'attempt').toLowerCase();
      var score=+r.score||0,total=+r.total||0;
      var path=[seg(cfg.grade),seg(cfg.subject),seg(cfg.lesson),stamp(d)+'-'+kind+'-'+rand4()+'.json'].join('/');
      var payload={v:2,grade:cfg.grade,subject:cfg.subject,lesson:cfg.lesson,kind:kind,score:score,total:total,
        pct:total?Math.round(score*1000/total)/10:null,
        missed:cleanAll(r.missed,kind),details:facts(r.details),build:buildId(),
        clientTime:isoLocal(d),tz:(function(){try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch(e){return ''}})(),
        page:pagePath()};
      var item={path:path,message:cfg.grade+' '+cfg.subject+' '+cfg.lesson+' '+kind+' '+score+'/'+total,content:b64(JSON.stringify(payload,null,1)+'\n'),tries:0};
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
  return {init:init,record:record,flush:flush,queue:load,allow:allow,_b64:b64};
})();
