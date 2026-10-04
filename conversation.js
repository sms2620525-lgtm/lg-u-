(() => {
  let provider='chatgpt', assistantSettings=null, routerModels=[], routerLoaded=false, settingsBusy=false;
  let dashboard=false, accountId=null, accountReady=false, modelLoadedFor=null;
  let wakeEnabled=false, micMode='off', micRunning=false, micSeq=0, waitingUntil=0;
  let sending=false, chatBusy=false, lastTurn=-1, historyKey='', readTurn=-1;
  let speechQueue=[], speaking=false,speechPending=false, voiceEpoch=0, micOperation=0;
  const error=t=>$('chat-error').textContent=t;
  const listen=t=>{$('listen-status').textContent=t;$('wake-status').textContent=t;};
  const state=t=>{$('conversation-state').textContent=t;document.querySelector('.conversation-core').className='conversation-core '+t.toLowerCase();};
  function toggleDashboard(){dashboard=!dashboard;$('dashboard').hidden=!dashboard;$('conversation-view').hidden=dashboard;document.body.classList.toggle('conversation-mode',!dashboard);$('dashboard-toggle').setAttribute('aria-pressed',String(dashboard));$('dashboard-toggle').textContent=dashboard?'대화로 돌아가기 · Ctrl+M':'대시보드 · Ctrl+M';}
  $('dashboard-toggle').onclick=toggleDashboard;
  window.addEventListener('keydown',e=>{if(e.ctrlKey&&!e.altKey&&e.key.toLowerCase()==='m'){e.preventDefault();if(!e.repeat)toggleDashboard();}});
  async function startMic(mode){
    if(micRunning&&micMode===mode)return;
    const op=++micOperation;micMode=mode;
    try{const d=await api('microphone/start',{});if(op!==micOperation)return;micSeq=d.seq;micRunning=true;state('LISTENING');listen(mode==='ip'?'IP 주소를 말씀하세요.':mode==='direct'?'듣고 있어요. 말씀을 마치면 전송됩니다.':'호출 대기 중 · “자비스”라고 불러 주세요.');}
    catch(e){micRunning=false;micMode='off';wakeEnabled=false;updateWakeButton();error(e.message);listen('마이크를 시작하지 못했어요.');}
  }
  async function pauseMic(){await api('wake/pause',{});++micOperation;micRunning=false;micMode='off';await api('microphone/stop',{});}
  function updateWakeButton(){$('chat-wake').textContent=wakeEnabled?'호출 대기 끄기':'호출 대기 켜기';$('wake-toggle').textContent=wakeEnabled?'호출 대기 끄기':'자비스 호출 대기';}
  async function resumeWake(){if(wakeEnabled&&!speaking&&!chatBusy&&!sending)await api('wake/resume',{});else if(!speaking&&!chatBusy)state('STANDBY');}
  window.stopConversationMic=async()=>{wakeEnabled=false;updateWakeButton();await api('wake/disable',{});await pauseMic();};
  window.listenForIP=async()=>{if(speaking||chatBusy){error('응답을 중지한 뒤 IP를 입력하세요.');return;}error('');await startMic('ip');};
  $('chat-wake').onclick=async()=>{try{const d=await api(wakeEnabled?'wake/disable':'wake/enable',{});wakeEnabled=d.enabled;updateWakeButton();error('');}catch(e){error(e.message);}};
  $('chat-mic').onclick=async()=>{if(!accountReady){error('AI 연결과 모델 선택을 먼저 완료해 주세요.');return;}if(micRunning&&micMode==='direct'){await pauseMic();await resumeWake();return;}if(chatBusy||speaking){error('응답을 중지한 뒤 말씀해 주세요.');return;}await startMic('direct');};
  async function stopAll(){voiceEpoch++;speechQueue=[];speaking=false;chatBusy=false;sending=false;await pauseMic();await api('chat/cancel',{});await api('stop',{});state('STANDBY');}
  $('chat-stop').onclick=async()=>{try{await stopAll();await resumeWake();}catch(e){error(e.message);}};
  async function send(text){text=text.trim();if(!text||sending||chatBusy)return;if(!accountReady){error('AI 연결과 모델 선택을 먼저 완료해 주세요.');return;}sending=true;error('');$('chat-send').disabled=true;
    try{await pauseMic();voiceEpoch++;speechQueue=[];speaking=false;await api('stop',{});state('THINKING');listen('답변을 준비하고 있어요.');const r=await api('chat',{text});lastTurn=r.turn;chatBusy=true;$('chat-input').value='';}
    catch(e){error(e.message);state('STANDBY');}
    finally{sending=false;$('chat-send').disabled=chatBusy;if(!chatBusy)await resumeWake();}
  }
  $('chat-send').onclick=()=>send($('chat-input').value);
  $('chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('chat-input').value);}};
  $('chat-clear').onclick=async()=>{try{await stopAll();await api('chat/clear',{});historyKey='';error('');await resumeWake();}catch(e){error(e.message);}};
  function render(d){const key=JSON.stringify([d.messages,d.draft,d.status]);if(key===historyKey)return;historyKey=key;const list=$('chat-messages');const nearBottom=list.scrollHeight-list.scrollTop-list.clientHeight<80;list.replaceChildren();
    const add=(role,text,draft=false)=>{const el=document.createElement('div');el.className='chat-message '+role+(draft?' draft':'');const who=document.createElement('span');who.className='speaker';who.textContent=role==='user'?'YOU':'J.A.R.V.I.S.';el.append(who,document.createTextNode(text));list.append(el);};
    for(const m of d.messages)add(m.role,m.text);if(d.draft)add('assistant',d.draft,true);if(nearBottom)list.scrollTop=list.scrollHeight;
  }
  async function nextSpeech(){if(!speechQueue.length){speaking=false;await resumeWake();return;}const epoch=voiceEpoch;const text=speechQueue.shift();speaking=true;speechPending=true;state('SPEAKING');await pauseMic();try{await api('speak',{text});if(epoch!==voiceEpoch)return;}catch(e){if(epoch!==voiceEpoch)return;speechQueue=[];speaking=false;error('답변은 완료됐지만 음성을 재생하지 못했어요: '+e.message);await resumeWake();}finally{speechPending=false;}}
  async function chatPoll(){try{const d=await api('chat');render(d);chatBusy=d.status==='thinking';$('chat-send').disabled=chatBusy||sending;
    if(chatBusy)state('THINKING');
    if(!d.background&&d.status==='done'&&d.turn!==readTurn){readTurn=d.turn;if(d.turn===lastTurn&&$('auto-speak').checked){const text=d.messages.filter(m=>m.role==='assistant').at(-1)?.text||'';speechQueue=text.match(/[\s\S]{1,1800}/g)||[];await nextSpeech();}else await resumeWake();}
    if(!d.background&&d.status==='error'&&d.turn!==readTurn){readTurn=d.turn;error(d.error);state('STANDBY');await resumeWake();}
  }catch(e){error(e.message);}setTimeout(chatPoll,500);}
  async function voicePoll(){try{if(speaking&&!speechPending){const d=await api('voice');if(d.status==='idle')await nextSpeech();else if(d.status==='error'){speechQueue=[];speaking=false;error(d.error);await resumeWake();}}}catch(e){error(e.message);}setTimeout(voicePoll,500);}
  async function micPoll(){try{if(micRunning){const d=await api('microphone');if(d.status==='error'){micRunning=false;wakeEnabled=false;micMode='off';updateWakeButton();error(d.error);listen('마이크 연결을 확인하세요.');state('STANDBY');}
    for(const event of d.events){if(event.seq<=micSeq)continue;micSeq=event.seq;if(!micRunning)break;
      if(event.type==='partial'&&(micMode!=='wake'||waitingUntil>Date.now()))listen(event.text);
      if(event.type!=='utterance')continue;const text=event.text.trim();if(!text)continue;
      if(micMode==='ip'){$('target').value=text.replace(/점|닷/g,'.').replace(/\s/g,'');scanStatus('인식된 IP를 확인하고 점검 시작을 누르세요.');await pauseMic();await resumeWake();break;}
      if(micMode==='direct'){await send(text);break;}
      const match=/(?:자비스|쟈비스|jarvis)[야아]?[,.!?:\s]*/i.exec(text);
      if(match){const command=text.slice(match.index+match[0].length).trim();if(command){waitingUntil=0;await send(command);break;}waitingUntil=Date.now()+20000;state('LISTENING');listen('네, 듣고 있어요. 무엇을 도와드릴까요?');}
      else if(waitingUntil>Date.now()){waitingUntil=0;await send(text);break;}
    }
  }}catch(e){error(e.message);}setTimeout(micPoll,250);}
  async function updateAccount(d){accountReady=provider==='openrouter'?Boolean(assistantSettings?.configured&&assistantSettings?.model):d.connected&&d.plan_enabled;const changed=d.active!==accountId;accountId=d.active;$('account-status').textContent=provider==='openrouter'?(accountReady?'OpenRouter 연결 준비 완료 · '+assistantSettings.model:'OpenRouter 키를 저장하고 모델을 선택해 주세요.'):d.pending?'공식 로그인 페이지에서 인증을 마치세요.':d.connected?(d.email+(d.plan_enabled?' · ChatGPT 연결됨':' · 요금제 사용 권한이 필요해요.')):'ChatGPT 계정을 연결하면 대화할 수 있어요.';if(provider==='chatgpt'&&d.error)error(d.error);
    const options=JSON.stringify(d.accounts);if($('account-picker').dataset.options!==options){$('account-picker').dataset.options=options;$('account-picker').replaceChildren(new Option('새 ChatGPT 계정 연결',''));for(const a of d.accounts)$('account-picker').add(new Option(a.label,a.id));$('account-picker').value=d.active||'';}
    if(changed){historyKey='';modelLoadedFor=null;}
    if(provider==='chatgpt'&&accountReady&&modelLoadedFor!==d.active){modelLoadedFor=d.active;try{const m=await api('account/models',{});$('chat-model').replaceChildren();for(const x of m.models)$('chat-model').add(new Option(x.name,x.id));$('chat-model').value=m.model;}catch(e){error(e.message);}}
  }
  $('chatgpt-login').onclick=async()=>{try{error('');await api('account/login',{client:$('account-picker').value||null});$('account-status').textContent='공식 로그인 페이지에서 인증을 마치세요.';}catch(e){error(e.message);}};
  $('account-switch').onclick=async()=>{try{await stopAll();modelLoadedFor=null;const client=$('account-picker').value;if(client)await updateAccount(await api('account/switch',{client}));else $('chatgpt-login').click();}catch(e){error(e.message);}};
  $('chatgpt-logout').onclick=async()=>{try{wakeEnabled=false;updateWakeButton();await stopAll();const d=await api('account/logout',{});error(d.notice||'ChatGPT에서 로그아웃했어요.');modelLoadedFor=null;}catch(e){error(e.message);}};
  $('account-usage').onclick=()=>api('account/usage',{}).catch(e=>error(e.message));
  $('chat-model').onchange=async()=>{try{if(provider==='openrouter'){await saveAssistant({model:$('chat-model').value});}else await api('account/model',{model:$('chat-model').value});}catch(e){error(e.message);}};
  function renderRouterModels(){const query=$('model-search').value.trim().toLowerCase();$('chat-model').replaceChildren(new Option('OpenRouter 모델을 선택하세요',''));for(const m of routerModels){if(query&&!`${m.name} ${m.id}`.toLowerCase().includes(query)&&m.id!==assistantSettings?.model)continue;const p=m.pricing||{};const free=Number(p.prompt)===0&&Number(p.completion)===0;const cost=free?' · 무료':Number.isFinite(Number(p.prompt))&&Number.isFinite(Number(p.completion))?` · 입력 $${(Number(p.prompt)*1e6).toFixed(2)} / 출력 $${(Number(p.completion)*1e6).toFixed(2)} (100만 토큰)` : ''; $('chat-model').add(new Option(m.name+' · '+m.id+cost,m.id));}if(assistantSettings?.model&&!routerModels.some(m=>m.id===assistantSettings.model))$('chat-model').add(new Option(assistantSettings.model+' · 저장된 모델',assistantSettings.model));$('chat-model').value=assistantSettings?.model||'';}
  async function loadRouterModels(){const d=await api('openrouter/models',{});routerModels=d.models;routerLoaded=true;renderRouterModels();}
  async function applyAssistant(d){const changed=provider!==d.provider;assistantSettings=d;provider=d.provider;$('ai-provider').value=provider;$('ai-tone').value=d.tone;$('openrouter-settings').hidden=provider!=='openrouter';$('chatgpt-controls').hidden=provider!=='chatgpt';$('openrouter-status').textContent=d.configured?'API 키가 키체인에 저장되어 있습니다.':'저장된 API 키가 없습니다.';if(changed){historyKey='';modelLoadedFor=null;readTurn=-1;lastTurn=-1;$('chat-model').replaceChildren(new Option('모델을 선택하세요',''));}if(provider==='openrouter'){accountReady=Boolean(d.configured&&d.model);if(!routerLoaded)await loadRouterModels();else if(changed)renderRouterModels();}}
  async function saveAssistant(payload){settingsBusy=true;try{await stopAll();await applyAssistant(await api('assistant',payload));wakeEnabled=false;updateWakeButton();$('assistant-status').textContent='설정이 저장되었습니다. 박수 대기는 다시 켜 주세요.';}finally{settingsBusy=false;}}
  $('ai-provider').onchange=()=>saveAssistant({provider:$('ai-provider').value}).catch(e=>{error(e.message);$('ai-provider').value=provider;});
  $('ai-tone').onchange=()=>saveAssistant({tone:$('ai-tone').value}).catch(e=>error(e.message));
  $('model-search').oninput=renderRouterModels;
  $('models-refresh').onclick=()=>loadRouterModels().catch(e=>error(e.message));
  $('openrouter-save').onclick=async()=>{const key=$('openrouter-key').value;$('openrouter-key').value='';settingsBusy=true;$('openrouter-save').disabled=true;try{await stopAll();await applyAssistant(await api('openrouter/key',{key}));error('');$('assistant-status').textContent='키 확인과 저장을 완료했습니다. 모델을 선택하세요.';}catch(e){error(e.message);}finally{settingsBusy=false;$('openrouter-save').disabled=false;}};
  $('openrouter-delete').onclick=async()=>{settingsBusy=true;try{await stopAll();await applyAssistant(await api('openrouter/delete-key',{}));}catch(e){error(e.message);}finally{settingsBusy=false;}};
  async function accountPoll(){try{if(!settingsBusy)await applyAssistant(await api('assistant'));await updateAccount(await api('account'));}catch(e){error(e.message);}setTimeout(accountPoll,2000);}
  async function wakePoll(){try{const d=await api('wake');wakeEnabled=d.enabled;updateWakeButton();if(provider==='chatgpt'&&d.error)error(d.error);if(d.enabled&&d.phase!=='manual'){const labels={waiting:'박수 두 번으로 깨우세요 · 창을 닫아도 대기합니다.',greeting:'네, 듣고 있어요.',listening:'듣고 있어요. 말씀해 주세요.',thinking:'답변을 준비하고 있어요.',speaking:'답변을 읽고 있어요.'};listen(labels[d.phase]||'');state(({waiting:'STANDBY',greeting:'SPEAKING',listening:'LISTENING',thinking:'THINKING',speaking:'SPEAKING'})[d.phase]||'STANDBY');}}catch(e){error(e.message);}setTimeout(wakePoll,500);}
  chatPoll();voicePoll();micPoll();accountPoll();wakePoll();
})();
