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

  /* Quiz. data: {kind:'game'|'mock'|'retest', mode:'practice'|'test', title, questions:[{id, q, img{src,alt,caption}, options[], answer(index) | answer_text(string or list), explain, word, sense, topic, trap, traps}]}
     trap: a trap key for the question (lowercase, a-z 0-9 _ -). traps: {option letter or typed answer: trap key}.
     The logger gets, for each missed question: n, id, the picked letter, a value (a typed number, or the trap key of a
     known wrong answer), the trap key, blank and typed. Never the question text or a typed word. */
  var LET='ABCDEFGH';
  // trap key from page text: 'Other-sense lure' -> 'other-sense-lure' (page content, never the child's input)
  function tkey(s){s=String(s==null?'':s).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,32).replace(/-+$/,'');return /^[a-z0-9]/.test(s)?s:''}
  function norm(s){return String(s==null?'':s).trim().toLowerCase().replace(/\s+/g,' ').replace(/[.,!]$/,'')}
  /* Retry loop (wrong-only): after "Mark my test" (or the last answer in practice mode), Retry shows only the questions
     missed in that round. The questions already right stay on the page, grayed out and locked (disabled, inert,
     aria-disabled, tabindex -1, so keyboard focus skips them). Each round is its own logged attempt: attempt_kind
     'first' (round 1) or 'retry' (round 2 and on), round N, and the score of that round's questions only. When every
     question is right the page says "All correct in N rounds". "Start over" is a full reset to round 1. Nothing is
     kept on the device: a reload mid-loop starts over. */
  function plural(n,w){return n+' '+w+(n===1?'':'s')}
  function quiz(root,data,page){
    try{
      // a rebuild (Start over) drops the listeners of the earlier build, so old state never acts on the new questions
      if(root.__shOff){try{root.__shOff()}catch(e){}root.__shOff=null}
      var qi=+(root.getAttribute&&root.getAttribute('data-sh-quiz'))||0;
      var qs=data.questions||[],mode=data.mode||(data.kind==='game'?'practice':'test'),state=qs.map(function(){return {pick:null,done:false}});
      var round=1,active=qs.map(function(q,i){return i}),locked={};
      root.classList.add('sh-quiz');
      function isRight(q,st){if(q.options)return st.pick===q.answer;var a=[].concat(q.answer_text);return a.some(function(x){return norm(x)===norm(st.pick)})}
      function rightText(q){return q.options?LET[q.answer]+'. '+q.options[q.answer]:[].concat(q.answer_text)[0]}
      var html=qs.map(function(q,i){
        var body=q.options?'<div class="sh-opts" role="group">'+q.options.map(function(o,k){return '<button type="button" class="sh-opt" data-q="'+i+'" data-k="'+k+'"><span class="sh-opt__k">'+LET[k]+'</span><span>'+esc(o)+'</span></button>'}).join('')+'</div>'
          :'<input class="sh-input" data-q="'+i+'" autocomplete="off" inputmode="'+(q.numeric?'numeric':'text')+'" aria-label="Your answer">'+(mode==='practice'?' <button type="button" class="sh-btn" data-check="'+i+'">Check</button>':'');
        var im=q.img&&q.img.src&&/^data:image\//.test(q.img.src)?'<figure class="sh-q__fig"><img src="'+esc(q.img.src)+'" alt="'+esc(q.img.alt)+'" decoding="async">'+(q.img.caption?'<figcaption>'+esc(q.img.caption)+'</figcaption>':'')+'</figure>':'';
        return '<div class="sh-q" id="'+esc(root.id)+'-q'+i+'" data-qi="'+i+'"><div class="sh-q__n">Question '+(i+1)+' of '+qs.length+'</div>'+im+'<p class="sh-q__text">'+esc(q.q)+'</p>'+body+'<div class="sh-fb" hidden></div></div>';
      }).join('');
      html='<div class="sh-round" data-round role="status" hidden></div>'+html;
      html+=mode==='test'?'<div class="sh-actions"><button type="button" class="sh-btn" data-finish>Mark my test</button></div>':'';
      html+='<div class="sh-card sh-score" hidden aria-live="polite"></div>';
      root.innerHTML=html;
      var qOf=function(i){return $('#'+root.id+'-q'+i,root)};
      var fbOf=function(i){return $('.sh-fb',qOf(i))};
      function controls(i){return $$('button,input,select,textarea,a[href],[tabindex]',qOf(i))}
      function feedback(i){var q=qs[i],st=state[i],ok=isRight(q,st),fb=fbOf(i);
        fb.hidden=false;fb.className='sh-fb '+(ok?'is-right':'is-wrong');
        fb.innerHTML=(ok?'<b>Correct.</b> ':'<b>Not this time.</b> The answer is '+esc(rightText(q))+'. ')+(q.explain?esc(q.explain):'');
        if(q.options)$$('.sh-opt[data-q="'+i+'"]',root).forEach(function(b){var k=+b.getAttribute('data-k');b.disabled=true;
          if(k===q.answer)b.classList.add('is-right');else if(k===st.pick)b.classList.add('is-wrong')});
        else{var inp=$('.sh-input[data-q="'+i+'"]',root);if(inp)inp.disabled=true;var cb=$('[data-check="'+i+'"]',root);if(cb)cb.disabled=true}
        st.done=true;
        if(mode==='practice'&&active.every(function(k){return state[k].done}))finish();
      }
      // a question that is right: grayed out, locked, out of the tab order and hidden from assistive tech as inactive
      function lock(i){var el=qOf(i);if(!el||locked[i])return;locked[i]=1;
        el.classList.add('is-locked');el.setAttribute('aria-disabled','true');el.setAttribute('inert','');try{el.inert=true}catch(e){}
        controls(i).forEach(function(c){c.disabled=true;c.tabIndex=-1;c.setAttribute('aria-disabled','true')})}
      // a missed question, fresh for the next round: no pick, no answer shown, enabled
      function reopen(i){var el=qOf(i);state[i]={pick:null,done:false};
        el.classList.remove('is-locked');el.classList.add('is-retry');
        $$('.sh-opt',el).forEach(function(b){b.disabled=false;b.classList.remove('is-picked','is-right','is-wrong')});
        var inp=$('.sh-input',el);if(inp){inp.disabled=false;inp.value=''}
        var cb=$('[data-check]',el);if(cb)cb.disabled=false;
        var fb=fbOf(i);fb.hidden=true;fb.className='sh-fb';fb.innerHTML='';
        var n=$('.sh-q__n',el);if(n)n.textContent='Question '+(i+1)+' of '+qs.length+' (try again)'}
      function onClick(e){
        var b=e.target.closest&&e.target.closest('.sh-opt');
        if(b&&!b.disabled){var i=+b.getAttribute('data-q');if(locked[i])return;state[i].pick=+b.getAttribute('data-k');
          $$('.sh-opt[data-q="'+i+'"]',root).forEach(function(x){x.classList.toggle('is-picked',x===b)});
          if(mode==='practice')feedback(i);return}
        var c=e.target.closest&&e.target.closest('[data-check]');
        if(c&&!c.disabled){var j=+c.getAttribute('data-check'),inp=$('.sh-input[data-q="'+j+'"]',root);state[j].pick=inp.value;if(String(inp.value).trim())feedback(j);return}
        if(e.target.closest&&e.target.closest('[data-retry]')){retry();return}
        if(e.target.closest&&e.target.closest('[data-again]')){quiz(root,data,page);try{root.scrollIntoView({behavior:reduced()?'auto':'smooth'})}catch(_){}return}
        var f=e.target.closest&&e.target.closest('[data-finish]');
        if(f&&!f.disabled){
          active.forEach(function(k){var inp=$('.sh-input[data-q="'+k+'"]',root);if(inp)state[k].pick=inp.value});
          active.forEach(function(k){if(!state[k].done)feedback(k)});finish()}
      }
      function onKey(e){if(e.key==='Enter'&&e.target.classList.contains('sh-input')&&mode==='practice'){var c=$('[data-check="'+e.target.getAttribute('data-q')+'"]',root);if(c)c.click()}}
      root.addEventListener('click',onClick);root.addEventListener('keydown',onKey);
      root.__shOff=function(){root.removeEventListener('click',onClick);root.removeEventListener('keydown',onKey)};
      var finished=false;
      function retry(){
        if(!finished)return;
        var wrong=active.filter(function(k){return !isRight(qs[k],state[k])});
        if(!wrong.length)return;
        qs.forEach(function(q,i){if(wrong.indexOf(i)<0)lock(i)});
        round++;active=wrong;finished=false;
        wrong.forEach(reopen);
        var sc=$('.sh-score',root);sc.hidden=true;sc.innerHTML='';
        var rb=$('[data-round]',root);rb.hidden=false;
        rb.textContent='Round '+round+': '+plural(wrong.length,'question')+' to fix. The ones you got right are grayed out.';
        var f=$('[data-finish]',root);if(f){f.disabled=false;f.textContent='Mark round '+round}
        var first=qOf(wrong[0]),ctl=first&&$('.sh-opt,.sh-input',first);
        try{if(first)first.scrollIntoView({block:'center',behavior:reduced()?'auto':'smooth'});if(ctl)ctl.focus({preventScroll:true})}catch(_){}
      }
      function finish(){
        if(finished)return;finished=true;
        var f=$('[data-finish]',root);if(f)f.disabled=true;
        active.forEach(function(k){var inp=$('.sh-input[data-q="'+k+'"]',root);if(inp&&(state[k].pick==null||state[k].pick===''))state[k].pick=inp.value});
        var score=0,missed=[];
        // only this round's questions count: a retry round scores its own questions (for example 1 / 2)
        active.forEach(function(i){var q=qs[i],st=state[i];if(isRight(q,st))score++;else{
          var blank=st.pick==null||String(st.pick).trim()==='',L=q.options&&!blank?LET[st.pick]:null,tm=q.traps||{};
          // a known wrong answer: the page lists it in traps (option letter or typed answer)
          var hit=blank?null:(q.options?(L in tm?L:null):(Object.keys(tm).filter(function(k){return norm(k)===norm(st.pick)})[0]||null));
          // trap key only for a wrong pick (option) or a typed answer the page lists; never a default for blank or other typed answers
          var tk=blank?null:hit!=null?(/^[a-z0-9-]{1,24}$/.test(tm[hit])?tm[hit]:(tkey(q.trap)||'known-wrong')):(q.options&&L?(tkey(q.trap)||null):null);
          var raw=String(st.pick==null?'':st.pick).trim();
          var v=q.options||blank?null:(/^-?\d{1,9}(?:[.,]\d{1,4})?(?:\/\d{1,6})?$/.test(raw)?raw:(hit!=null?norm(hit):null));
          missed.push({n:i+1,id:q.id||('q'+(qi+1)+'-'+(i+1)),picked:L,value:v,trap:tk,
            correct:q.options?LET[q.answer]:null,blank:blank,typed:!q.options})}});
        var total=active.length,sc=$('.sh-score',root);sc.hidden=false;
        if(missed.length===0){var rb0=$('[data-round]',root);if(rb0)rb0.hidden=true}
        var pct=total?Math.round(100*score/total):0,done=missed.length===0;
        var msg=done?(round===1?'Excellent work. All correct in 1 round.':'All correct in '+plural(round,'round')+'.')
          :(round===1?(pct>=90?'Excellent work.':pct>=70?'Good work. Look again at the red ones.':'Keep going. Read the red ones, then try again.'):'Good. Read the red ones, then retry them.');
        var btns=(done?'':'<button type="button" class="sh-btn" data-retry>Retry the '+plural(missed.length,'wrong one').replace(/^\d+ /,'')+' ('+missed.length+')</button>')
          +'<button type="button" class="sh-btn sh-btn--ghost" data-again>Start over</button>';
        sc.innerHTML=(round>1?'<div class="sh-score__round">Round '+round+'</div>':'')+'<div class="sh-score__big">'+score+' / '+total+'</div><div class="sh-score__text" data-result>'+esc(msg)+'</div><div class="sh-actions" style="justify-content:center">'+btns+'</div>';
        try{if(page&&page.log&&window.SHLog)SHLog.record({kind:data.kind||'game',score:score,total:total,missed:missed,
          attempt_kind:round===1?'first':'retry',round:round,
          details:{section:data.section||'',answered:active.filter(function(k){var s=state[k];return s.pick!=null&&String(s.pick).trim()!==''}).length}})}catch(e){}
        try{root.dispatchEvent(new CustomEvent('sh:finish',{bubbles:true,detail:{score:score,total:total,missed:missed,round:round,allCorrect:done}}))}catch(e){}
      }
    }catch(e){try{root.textContent='This quiz could not load.'}catch(_){}}
  }
  function boot(){
    try{
      var page=null,el=document.getElementById('sh-data');
      if(el){try{page=JSON.parse(el.textContent)}catch(e){page=null}}
      if(page&&page.log&&window.SHLog){try{
        var ids=[],traps=[],secs=[],vals=[];
        (page.quizzes||[]).forEach(function(z,zi){if(z.section)secs.push(z.section);(z.questions||[]).forEach(function(q,i){ids.push(q.id||('q'+(zi+1)+'-'+(i+1)));
          if(tkey(q.trap))traps.push(tkey(q.trap));var t=q.traps||{};Object.keys(t).forEach(function(k){if(/^[a-z0-9-]{1,24}$/.test(t[k]))traps.push(t[k]);
            if(!q.options)vals.push(norm(k))})})});
        traps.push('known-wrong');
        if(SHLog.allow)SHLog.allow({ids:ids,traps:traps,sections:secs,values:vals,build:page.build});
        SHLog.init({grade:page.grade,subject:page.subject,lesson:page.id,token:page.token})}catch(e){}}
      $$('[data-sh-quiz]').forEach(function(q){var i=+q.getAttribute('data-sh-quiz');if(page&&page.quizzes&&page.quizzes[i])quiz(q,page.quizzes[i],page)});
      tabs();dates();filters();reveal();
    }catch(e){}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
  return {quiz:quiz,tabs:tabs,reveal:reveal,esc:esc};
})();
