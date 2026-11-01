/* Study Hub page runtime (sh-2): segmented tabs, reveal motion, filters, quizzes with score logging.
   Shared by every page. Never throws into the page. */
var SH=(function(){
  'use strict';
  function $(s,r){return (r||document).querySelector(s)}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))}
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function reduced(){try{return window.matchMedia('(prefers-reduced-motion: reduce)').matches}catch(e){return false}}

  /* Segmented tabs: <div class="sh-seg" role="tablist" data-sh-tabs> <button role="tab" aria-controls="p-learn">  */
  function tabs(){
    $$('[data-sh-tabs]').forEach(function(bar){
      var btns=$$('[role="tab"]',bar);
      function show(id,push){
        btns.forEach(function(b){var on=b.getAttribute('aria-controls')===id;b.setAttribute('aria-selected',on?'true':'false');b.tabIndex=on?0:-1;
          var p=document.getElementById(b.getAttribute('aria-controls'));if(p)p.hidden=!on});
        if(push){try{history.replaceState(null,'','#'+id.replace(/^p-/,''))}catch(e){}}
        var cur=btns.filter(function(b){return b.getAttribute('aria-selected')==='true'})[0];
        if(cur&&cur.scrollIntoView&&push)try{cur.scrollIntoView({block:'nearest',inline:'center',behavior:reduced()?'auto':'smooth'})}catch(e){}
        reveal();
      }
      btns.forEach(function(b,i){
        b.addEventListener('click',function(){show(b.getAttribute('aria-controls'),true);var t=$('.sh-tabsbar');if(t&&window.scrollY>t.offsetTop)window.scrollTo({top:t.offsetTop-52,behavior:reduced()?'auto':'smooth'})});
        b.addEventListener('keydown',function(e){var k=e.key,j=-1;if(k==='ArrowRight')j=(i+1)%btns.length;if(k==='ArrowLeft')j=(i-1+btns.length)%btns.length;
          if(j>=0){e.preventDefault();btns[j].focus();btns[j].click()}});
      });
      var h=(location.hash||'').slice(1),first=btns[0]&&btns[0].getAttribute('aria-controls');
      var want=h&&document.getElementById('p-'+h)?'p-'+h:first;if(want)show(want,false);
      window.addEventListener('hashchange',function(){var x=(location.hash||'').slice(1);if(x&&document.getElementById('p-'+x)&&btns.some(function(b){return b.getAttribute('aria-controls')==='p-'+x}))show('p-'+x,false)});
    });
  }
  /* Filters on hub pages: <div class="sh-seg" data-sh-filter="list-id"> <button data-f="all"> ; rows carry data-when="soon|past|none" */
  function filters(){
    $$('[data-sh-filter]').forEach(function(bar){
      var list=document.getElementById(bar.getAttribute('data-sh-filter'));if(!list)return;
      $$('button',bar).forEach(function(b){b.addEventListener('click',function(){
        $$('button',bar).forEach(function(x){x.setAttribute('aria-selected',x===b?'true':'false')});
        var f=b.getAttribute('data-f'),n=0;
        $$('[data-when]',list).forEach(function(r){var ok=f==='all'||r.getAttribute('data-when')===f;r.hidden=!ok;if(ok)n++});
        var em=list.parentNode.querySelector('.sh-empty');if(em)em.hidden=n>0;
      })});
    });
  }
  /* Dates: mark rows as soon or past from data-date (YYYY-MM-DD), using the device date */
  function dates(){
    var t=new Date();t.setHours(0,0,0,0);
    $$('[data-date]').forEach(function(r){var d=r.getAttribute('data-date');if(!d){r.setAttribute('data-when','none');return}
      var x=new Date(d+'T00:00:00');var past=x<t;r.setAttribute('data-when',past?'past':'soon');
      var c=$('.sh-chip',r);if(c&&!past){c.classList.add('sh-chip--soon')}});
    $$('.sh-hide-past').forEach(function(l){var any=$$('[data-when="soon"]',l).length>0;var em=l.parentNode.querySelector('[data-sh-empty]');if(em)em.hidden=any});
  }
  var io=null;
  function reveal(){
    var els=$$('.sh-reveal:not(.is-in)');
    if(reduced()||!('IntersectionObserver' in window)){els.forEach(function(e){e.classList.add('is-in')});return}
    if(!io)io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('is-in');io.unobserve(e.target)}})},{rootMargin:'0px 0px -6% 0px'});
    els.forEach(function(e){io.observe(e)});
  }

  /* Quiz. data: {kind:'game'|'mock'|'retest', mode:'practice'|'test', title, questions:[{q, options[], answer(index) | answer_text(string or list), explain, word, sense, topic, trap}]} */
  var LET='ABCDEFGH';
  function norm(s){return String(s==null?'':s).trim().toLowerCase().replace(/\s+/g,' ').replace(/[.,!]$/,'')}
  function quiz(root,data,page){
    try{
      var qs=data.questions||[],mode=data.mode||(data.kind==='game'?'practice':'test'),state=qs.map(function(){return {pick:null,done:false}});
      root.classList.add('sh-quiz');
      function optText(q,i){return q.options[i]}
      function isRight(q,st){if(q.options)return st.pick===q.answer;var a=[].concat(q.answer_text);return a.some(function(x){return norm(x)===norm(st.pick)})}
      function rightText(q){return q.options?LET[q.answer]+'. '+q.options[q.answer]:[].concat(q.answer_text)[0]}
      var html=qs.map(function(q,i){
        var body=q.options?'<div class="sh-opts" role="group">'+q.options.map(function(o,k){return '<button type="button" class="sh-opt" data-q="'+i+'" data-k="'+k+'"><span class="sh-opt__k">'+LET[k]+'</span><span>'+esc(o)+'</span></button>'}).join('')+'</div>'
          :'<input class="sh-input" data-q="'+i+'" autocomplete="off" inputmode="'+(q.numeric?'numeric':'text')+'" aria-label="Your answer">'+(mode==='practice'?' <button type="button" class="sh-btn" data-check="'+i+'">Check</button>':'');
        return '<div class="sh-q" id="'+esc(root.id)+'-q'+i+'"><div class="sh-q__n">Question '+(i+1)+' of '+qs.length+'</div><p class="sh-q__text">'+esc(q.q)+'</p>'+body+'<div class="sh-fb" hidden></div></div>';
      }).join('');
      html+=mode==='test'?'<div class="sh-actions"><button type="button" class="sh-btn" data-finish>Mark my test</button></div>':'';
      html+='<div class="sh-card sh-score" hidden></div>';
      root.innerHTML=html;
      var fbOf=function(i){return $('#'+root.id+'-q'+i+' .sh-fb',root)};
      function feedback(i){var q=qs[i],st=state[i],ok=isRight(q,st),fb=fbOf(i);
        fb.hidden=false;fb.className='sh-fb '+(ok?'is-right':'is-wrong');
        fb.innerHTML=(ok?'<b>Correct.</b> ':'<b>Not this time.</b> The answer is '+esc(rightText(q))+'. ')+(q.explain?esc(q.explain):'');
        if(q.options)$$('.sh-opt[data-q="'+i+'"]',root).forEach(function(b){var k=+b.getAttribute('data-k');b.disabled=true;
          if(k===q.answer)b.classList.add('is-right');else if(k===st.pick)b.classList.add('is-wrong')});
        else{var inp=$('.sh-input[data-q="'+i+'"]',root);if(inp)inp.disabled=true;var cb=$('[data-check="'+i+'"]',root);if(cb)cb.disabled=true}
        st.done=true;
        if(mode==='practice'&&state.every(function(s){return s.done}))finish();
      }
      root.addEventListener('click',function(e){
        var b=e.target.closest&&e.target.closest('.sh-opt');
        if(b&&!b.disabled){var i=+b.getAttribute('data-q');state[i].pick=+b.getAttribute('data-k');
          $$('.sh-opt[data-q="'+i+'"]',root).forEach(function(x){x.classList.toggle('is-picked',x===b)});
          if(mode==='practice')feedback(i);return}
        var c=e.target.closest&&e.target.closest('[data-check]');
        if(c){var j=+c.getAttribute('data-check'),inp=$('.sh-input[data-q="'+j+'"]',root);state[j].pick=inp.value;if(String(inp.value).trim())feedback(j);return}
        if(e.target.closest&&e.target.closest('[data-finish]')){
          $$('.sh-input',root).forEach(function(inp){state[+inp.getAttribute('data-q')].pick=inp.value});
          qs.forEach(function(q,i){if(!state[i].done)feedback(i)});finish()}
      });
      root.addEventListener('keydown',function(e){if(e.key==='Enter'&&e.target.classList.contains('sh-input')&&mode==='practice'){var c=$('[data-check="'+e.target.getAttribute('data-q')+'"]',root);if(c)c.click()}});
      var finished=false;
      function finish(){
        if(finished)return;finished=true;
        var f=$('[data-finish]',root);if(f)f.disabled=true;
        var score=0,missed=[];
        qs.forEach(function(q,i){var st=state[i];if(isRight(q,st))score++;else missed.push({n:i+1,id:q.id||('q'+(i+1)),
          picked:q.options&&st.pick!=null?LET[st.pick]:null,correct:q.options?LET[q.answer]:null,
          blank:st.pick==null||String(st.pick).trim()==='',typed:!q.options})});
        var sc=$('.sh-score',root);sc.hidden=false;
        var pct=qs.length?Math.round(100*score/qs.length):0;
        sc.innerHTML='<div class="sh-score__big">'+score+' / '+qs.length+'</div><div class="sh-score__text">'+(pct>=90?'Excellent work.':pct>=70?'Good work. Look again at the red ones.':'Keep going. Read the red ones, then try again.')+'</div><div class="sh-actions" style="justify-content:center"><button type="button" class="sh-btn sh-btn--ghost" data-again>Try again</button></div>';
        $('[data-again]',sc).addEventListener('click',function(){quiz(root,data,page);root.scrollIntoView({behavior:reduced()?'auto':'smooth'})});
        try{if(page&&page.log&&window.SHLog)SHLog.record({kind:data.kind||'game',score:score,total:qs.length,missed:missed,
          details:{section:data.section||'',answered:state.filter(function(s){return s.pick!=null&&String(s.pick).trim()!==''}).length}})}catch(e){}
        try{root.dispatchEvent(new CustomEvent('sh:finish',{bubbles:true,detail:{score:score,total:qs.length,missed:missed}}))}catch(e){}
      }
    }catch(e){try{root.textContent='This quiz could not load.'}catch(_){}}
  }
  function boot(){
    try{
      var page=null,el=document.getElementById('sh-data');
      if(el){try{page=JSON.parse(el.textContent)}catch(e){page=null}}
      if(page&&page.log&&window.SHLog){try{SHLog.init({grade:page.grade,subject:page.subject,lesson:page.id,token:page.token})}catch(e){}}
      $$('[data-sh-quiz]').forEach(function(q){var i=+q.getAttribute('data-sh-quiz');if(page&&page.quizzes&&page.quizzes[i])quiz(q,page.quizzes[i],page)});
      tabs();dates();filters();reveal();
    }catch(e){}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
  return {quiz:quiz,tabs:tabs,reveal:reveal,esc:esc};
})();
