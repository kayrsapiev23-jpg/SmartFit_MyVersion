/* SmartFit UI shell + free on-device AI (WebLLM). No paid requests. */
(() => {
  'use strict';
  const body=document.body;
  const loggedIn=body.classList.contains('logged-in');
  const path=location.pathname.split('/')[1] || 'dashboard';
  document.querySelectorAll('[data-nav]').forEach(link => {
    if (link.dataset.nav===path) {link.classList.add('active'); link.setAttribute('aria-current','page');}
  });
  if (!loggedIn) return;
  const drawer=document.getElementById('agentDrawer');
  const backdrop=document.getElementById('drawerBackdrop');
  const pageMessages=document.getElementById('pageMessages');
  const drawerMessages=document.getElementById('drawerMessages');
  const containers=[pageMessages,drawerMessages].filter(Boolean);
  const forms=[document.getElementById('pageChatForm'),document.getElementById('drawerChatForm')].filter(Boolean);
  const starts=[...document.querySelectorAll('[data-start-coach]')];
  const status=[...document.querySelectorAll('[data-coach-status]')];
  const progressAreas=[...document.querySelectorAll('[data-coach-progress-wrap]')];
  const modelPicker=document.querySelector('[data-coach-model]');
  const csrf=body.dataset.csrf;
  let history=[];
  let context={};
  let busy=false;
  let engineReady=false;
  let engineModule=null;
  let loadBusy=false;
  const choose=()=>modelPicker?.value || 'lite';
  const showStatus=text=>status.forEach(el=>{el.textContent=text;});
  const setOpen=open=>{
    if (!drawer) return;
    drawer.classList.toggle('open',open);
    drawer.setAttribute('aria-hidden',String(!open));
    if(backdrop) backdrop.hidden=!open;
    if(open) document.getElementById('coachQuestion')?.focus();
  };
  document.querySelectorAll('.agent-trigger').forEach(b=>b.addEventListener('click',()=>setOpen(true)));
  document.getElementById('closeDrawer')?.addEventListener('click',()=>setOpen(false));
  backdrop?.addEventListener('click',()=>setOpen(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false);});
  function bubble(role,content){
    const el=document.createElement('div');
    el.className='coach-msg '+(role==='user'?'user':role==='error'?'error':'assistant');
    el.textContent=content;
    return el;
  }
  function paint(){
    containers.forEach(el=>{
      el.replaceChildren();
      if(history.length===0){
        const placeholder=document.createElement('div');placeholder.className='coach-placeholder';
        const mark=document.createElement('span');mark.className='coach-placeholder-mark';mark.textContent='✦';
        const title=document.createElement('b');title.textContent=engineReady?'Your coach is ready':'Start the free AI to begin';
        const desc=document.createElement('p');desc.textContent=engineReady?'Ask about safe workouts and recovery.':'No API key or monthly subscription needed.';
        placeholder.append(mark,title,desc);el.append(placeholder);
      } else history.forEach(item=>el.append(bubble(item.role,item.content)));
      el.scrollTop=el.scrollHeight;
    });
  }
  function notice(text){
    containers.forEach(el=>{el.append(bubble('error',text));el.scrollTop=el.scrollHeight;});
  }
  function blockSending(state){
    busy=state;
    forms.forEach(form=>{form.querySelectorAll('button,textarea,input[name="message"]').forEach(el=>el.disabled=state);});
  }
  function updateProgress(update){
    const pct=Number.isFinite(update?.progress) ? Math.min(100,Math.max(0,Math.round(update.progress*100))) : 0;
    const raw=String(update?.text||'Downloading the model…');
    showStatus(pct?`Loading local AI · ${pct}%`:'Loading local AI…');
    progressAreas.forEach(area=>{
      area.hidden=false;
      const fill=area.querySelector('[data-coach-progress-fill]');
      const text=area.querySelector('[data-coach-progress-text]');
      if(fill)fill.style.width=pct+'%';
      if(text)text.textContent=raw.slice(0,140);
    });
  }
  async function startModel(){
    if(engineReady || loadBusy)return;
    if(!window.isSecureContext || !navigator.gpu){
      showStatus('WebGPU is not available');
      notice('Your browser does not support WebGPU. Try updated Chrome or Edge with hardware acceleration enabled.');
      return;
    }
    loadBusy=true;
    starts.forEach(button=>{button.disabled=true;button.textContent='Loading…';});
    if(modelPicker)modelPicker.disabled=true;
    try{
      const adapter=await navigator.gpu.requestAdapter();
      if(!adapter)throw new Error('WebGPU adapter is unavailable. Check the graphics driver and browser hardware acceleration.');
      updateProgress({text:'Checking hardware and loading library…',progress:0});
      engineModule=await import('/static/js/coach-browser.js?v=webllm1');
      await engineModule.loadLocalModel(choose(),updateProgress);
      engineReady=true;
      showStatus('Ready · Local AI · 0 ₸ per message');
      progressAreas.forEach(area=>area.hidden=true);
      starts.forEach(button=>{button.textContent='AI ready ✓';});
      paint();
    }catch(error){
      console.error('SmartFit WebLLM load failed',error);
      showStatus('Could not start model');
      notice('Could not load the model. Check WebGPU support, graphics driver, memory and internet connection. '+(error?.message||''));
      starts.forEach(button=>{button.disabled=false;button.textContent='Retry free AI';});
      if(modelPicker)modelPicker.disabled=false;
    }finally{loadBusy=false;}
  }
  starts.forEach(button=>button.addEventListener('click',startModel));
  async function loadHistory(){
    try{
      const response=await fetch('/api/coach/history',{credentials:'same-origin',headers:{'Accept':'application/json'}});
      if(!response.ok)throw new Error('Could not load saved chat. Sign in again.');
      const payload=await response.json();
      history=Array.isArray(payload.messages)?payload.messages:[];
      context=payload.context&&typeof payload.context==='object'?payload.context:{};
      paint();
    }catch(e){notice(e.message);}
  }
  async function send(question){
    question=question.trim();if(!question||busy)return;
    if(!engineReady){notice('First click “Start free AI” and let the model load.');return;}
    if(question.length>700){notice('Use no more than 700 characters.');return;}
    const earlier=history.slice();
    blockSending(true);
    history.push({role:'user',content:question});paint();
    containers.forEach(el=>{const pending=bubble('assistant','Thinking on your device…');pending.classList.add('pending');el.append(pending);el.scrollTop=el.scrollHeight;});
    try{
      const answer=await engineModule.createLocalAnswer(question,earlier,context);
      history.push({role:'assistant',content:answer});paint();
      try{
        const response=await fetch('/api/coach/turn',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/json','x-csrf-token':csrf},body:JSON.stringify({question,answer})});
        if(!response.ok)throw new Error('This answer was generated locally but could not be saved to Supabase.');
      }catch(e){notice(e.message);}
    }catch(e){
      history.pop();paint();
      notice('Local AI could not complete your answer. '+(e?.message||''));
    }finally{blockSending(false);}
  }
  forms.forEach(form=>form.addEventListener('submit',e=>{
    e.preventDefault();const input=form.elements.message;if(!input)return;
    const message=input.value;
    if(!engineReady){notice('Click “Start free AI” above or in the AI Coach window first.');return;}
    input.value='';send(message);
  }));
  document.querySelectorAll('[data-prompt]').forEach(button=>button.addEventListener('click',()=>{
    const input=pageMessages?document.getElementById('agentPageQuestion'):document.getElementById('coachQuestion');
    if(!input){setOpen(true);return;}
    input.value=button.dataset.prompt||'';input.focus();
  }));
  document.querySelectorAll('[data-clear-chat]').forEach(button=>button.addEventListener('click',async()=>{
    if(busy||!confirm('Delete your saved SmartFit Coach chat history?'))return;
    try{
      const response=await fetch('/api/coach/history',{method:'DELETE',credentials:'same-origin',headers:{'x-csrf-token':csrf}});
      if(!response.ok)throw new Error('Could not clear saved chat.');
      history=[];paint();
    }catch(e){notice(e.message);}
  }));
  paint();loadHistory();
})();
