const scanStatus=t=>$('scan-status').textContent=t;
let rotation={x:-15,y:15};let dragging=false,last={x:0,y:0};
function orient(){ $('universe').style.transform=`rotateX(${rotation.x}deg) rotateY(${rotation.y}deg)`; }
const view=$('viewport');view.onpointerdown=e=>{dragging=true;last={x:e.clientX,y:e.clientY};view.setPointerCapture(e.pointerId);};view.onpointerup=()=>dragging=false;view.onpointercancel=()=>dragging=false;view.onpointermove=e=>{if(!dragging)return;rotation.y+=(e.clientX-last.x)*.5;rotation.x-=(e.clientY-last.y)*.5;last={x:e.clientX,y:e.clientY};orient();};
$('reset-view').onclick=()=>{rotation={x:-15,y:15};orient();};
// Future hardware adapters supply degrees after pairing/authentication. No Bluetooth connection is claimed here.
window.jarvisOrientation=({pitch,roll})=>{if(!Number.isFinite(pitch)||!Number.isFinite(roll))return;rotation.x=Math.max(-80,Math.min(80,pitch));rotation.y=roll%360;orient();};
function draw(hosts,target){const world=$('universe');world.replaceChildren();$('results').replaceChildren();const center=document.createElement('div');center.className='node host';center.textContent=target||'IP를 입력하세요';world.append(center);const ports=hosts.flatMap(h=>h.ports);ports.forEach((p,i)=>{const angle=i*Math.PI*2/Math.max(1,ports.length);const ring=Math.floor(i/16);const node=document.createElement('div');node.className='node'+(p.state==='open'?'':' other');node.style.transform=`translate3d(${Math.cos(angle)*(170+ring*45)}px,${Math.sin(angle)*(100+ring*25)}px,${Math.sin(angle*2)*110}px)`;node.textContent=`${p.port}/${p.protocol}\n${p.service.name||'unknown'} · ${p.state}`;world.append(node);const row=document.createElement('div');row.className='result-row';row.textContent=`${p.port}/${p.protocol} · ${p.state} · ${p.service.name||'unknown'} ${p.service.product||''} ${p.service.version||''}`;$('results').append(row);});orient();}
let active=false,lastSignature='';
async function poll(){try{const data=await api('scan');const signature=JSON.stringify(data);if(signature!==lastSignature){lastSignature=signature;active=data.status==='running';$('scan').disabled=active;$('cancel-scan').disabled=!active;if(data.status==='running')scanStatus('Nmap 점검 중… 최대 150초\n'+data.command+(data.notice?'\n'+data.notice:''));else if(data.status==='done'){draw(data.hosts,data.target);const ports=data.hosts.flatMap(h=>h.ports);scanStatus(data.hosts.some(h=>h.timed_out)?'대상 응답 시간 초과. 결과가 불완전합니다.':`점검 완료 · 열린 포트 ${ports.filter(p=>p.state==='open').length}개. 포트가 열려 있다는 사실만으로 취약점이 확인된 것은 아닙니다.`);}else if(data.status==='error')scanStatus(data.error);else if(data.status==='cancelled')scanStatus('점검을 중단했어요.');}}catch(e){scanStatus('앱 연결을 확인해 주세요. '+e.message);}setTimeout(poll,1500);}
$('scan').onclick=async()=>{try{$('scan').disabled=true;await api('scan',{target:$('target').value.trim(),terminal:$('terminal').checked});lastSignature='';}catch(e){scanStatus(e.message);$('scan').disabled=false;}};
$('cancel-scan').onclick=async()=>{try{await api('scan/cancel',{});}catch(e){scanStatus(e.message);}};
const Speech=window.SpeechRecognition||window.webkitSpeechRecognition;
$('dictate').onclick=()=>{if(!Speech){scanStatus('이 브라우저는 음성 입력을 지원하지 않아요. IP를 직접 입력해 주세요.');return;}const recognition=new Speech();recognition.lang='ko-KR';recognition.onresult=e=>{let text=e.results[0][0].transcript.trim().replace(/점|닷/g,'.').replace(/\s/g,'');$('target').value=text;scanStatus('인식된 IP를 확인하고 점검 시작을 눌러 주세요.');};recognition.onerror=e=>scanStatus('음성 입력 실패: '+e.error);try{recognition.start();}catch(e){scanStatus(e.message);}};
$('quit').onclick=async()=>{try{await api('quit',{});document.body.textContent='JARVIS를 종료했어요. 이 창을 닫아도 됩니다.';}catch(e){scanStatus(e.message);}};
draw([],null);poll();

let phoneOffset={pitch:0,roll:0},phoneLatest=null,devicesKey='';
$('phone-enable').onclick=async()=>{try{await api('phone/enable',{});}catch(e){$('phone-status').textContent=e.message;}};
$('phone-connect').onclick=async()=>{try{await api('phone/connect',{device:$('phone-device').value,pin:$('phone-pin').value.trim()});}catch(e){$('phone-status').textContent=e.message;}};
$('phone-disable').onclick=async()=>{try{await api('phone/disable',{});}catch(e){$('phone-status').textContent=e.message;}};
$('phone-center').onclick=()=>{if(phoneLatest)phoneOffset={pitch:phoneLatest.pitch,roll:phoneLatest.roll};};
async function phonePoll(){try{const d=await api('phone');const key=JSON.stringify(d.devices||[]);if(key!==devicesKey){devicesKey=key;$('phone-device').replaceChildren();for(const device of d.devices||[]){const option=document.createElement('option');option.value=device.id;option.textContent=device.name+' · '+device.id.slice(-5);$('phone-device').append(option);}}if(d.connected){phoneLatest=d;const wrap=n=>((n+180)%360+360)%360-180;window.jarvisOrientation({pitch:wrap(d.pitch-phoneOffset.pitch),roll:wrap(d.roll-phoneOffset.roll)});$('phone-status').textContent='Bluetooth 연결됨 · 휴대폰을 기울여 보세요.';}else{$('phone-status').textContent=d.error||({scanning:'검색 중… 휴대폰 전송을 켜 두세요.',ready:(d.devices||[]).length?'휴대폰을 선택하고 화면에 표시된 코드를 입력하세요.':'휴대폰을 찾지 못했어요. Bluetooth 권한과 전송 상태를 확인하세요.',connecting:'Bluetooth 연결 중…',streaming:'연결됨 · 센서 데이터 대기 중',idle:'휴대폰 미연결 · 마우스 회전 가능'}[d.status]||'대기 중');}}catch(e){}setTimeout(phonePoll,100);}phonePoll();

// ---- 소리로 깨우기 -----------------------------------------------------
// 특정 단어가 아니라 "소리"를 감지하는 기능이라, 음성 인식(STT) 대신 마이크
// 입력의 음량(RMS) 변화를 직접 관찰해서 '짧고 날카로운 소리 두 번'이 일정한
// 간격으로 들어오면 반응한다. (예: 혀 차는 소리, 손가락 스냅, 더블 클릭음)
// 아래 네 숫자가 패턴의 정의다 — 녹음해 둔 소리의 간격이 다르면 이 값들만
// 바꾸면 된다.
const WAKE_SPIKE_RATIO=6;     // 평소 소음(바닥값)보다 몇 배 커야 '소리'로 볼지
const WAKE_MIN_RMS=0.02;      // 그리고 절대적으로 이 정도는 커야 함 (완전 무음 방지)
const WAKE_MIN_GAP_MS=400;    // 두 소리가 이보다 가까우면 같은 소리로 간주(디바운스)
const WAKE_MAX_GAP_MS=1300;   // 두 소리가 이보다 멀면 '패턴'으로 보지 않음
const WAKE_COOLDOWN_MS=2500;  // 한 번 인식되면 이 시간 동안은 다시 인식하지 않음
let wakeCtx=null,wakeStream=null,wakeRAF=null,wakeFloor=0.001,wakeOnsets=[],wakeLastTrigger=0,wakeArmedAt=0;
function wakeSetStatus(t){const el=$('wake-status');if(el)el.textContent=t;}
async function wakeStart(){
  if(wakeCtx)return;
  if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){wakeSetStatus('이 브라우저는 마이크 입력을 지원하지 않아요.');return;}
  try{
    wakeStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
  }catch(e){wakeSetStatus('마이크 권한이 필요해요: '+e.message);return;}
  wakeCtx=new (window.AudioContext||window.webkitAudioContext)();
  const source=wakeCtx.createMediaStreamSource(wakeStream);
  const analyser=wakeCtx.createAnalyser();
  analyser.fftSize=2048;
  source.connect(analyser);
  const buf=new Float32Array(analyser.fftSize);
  wakeOnsets=[];wakeFloor=0.001;wakeArmedAt=performance.now()+300;// 시작 직후 잠깐은 무시(마이크 켜지는 소리 등 오탐 방지)
  $('wake-toggle').textContent='소리 감지 끄기';
  wakeSetStatus('듣고 있어요 · 등록한 소리를 내 보세요.');
  (function loop(){
    wakeRAF=requestAnimationFrame(loop);
    analyser.getFloatTimeDomainData(buf);
    let sum=0;for(let i=0;i<buf.length;i++)sum+=buf[i]*buf[i];
    const rms=Math.sqrt(sum/buf.length);
    const now=performance.now();
    const isSpike=rms>Math.max(WAKE_MIN_RMS,wakeFloor*WAKE_SPIKE_RATIO);
    if(isSpike&&now>=wakeArmedAt){
      const lastOnset=wakeOnsets[wakeOnsets.length-1];
      if(!lastOnset||now-lastOnset>WAKE_MIN_GAP_MS){
        wakeOnsets.push(now);
        if(wakeOnsets.length>2)wakeOnsets.shift();
        if(wakeOnsets.length===2){
          const gap=wakeOnsets[1]-wakeOnsets[0];
          if(gap>=WAKE_MIN_GAP_MS&&gap<=WAKE_MAX_GAP_MS&&now-wakeLastTrigger>WAKE_COOLDOWN_MS){
            wakeLastTrigger=now;wakeOnsets=[];wakeArmedAt=now+WAKE_COOLDOWN_MS;
            wakeTriggered();
          }
        }
      }
    }else if(!isSpike){
      wakeFloor=wakeFloor*0.98+rms*0.02;// 조용할 때만 바닥 소음 수준을 천천히 갱신
    }
  })();
}
function wakeStop(){
  if(wakeRAF)cancelAnimationFrame(wakeRAF);wakeRAF=null;
  if(wakeStream)wakeStream.getTracks().forEach(t=>t.stop());wakeStream=null;
  if(wakeCtx)wakeCtx.close();wakeCtx=null;
  $('wake-toggle').textContent='소리로 깨우기';
  wakeSetStatus('꺼져 있어요.');
}
async function wakeTriggered(){
  wakeSetStatus('소리 감지! 자비스를 부릅니다.');
  try{await api('speak',{text:'네, 듣고 있습니다.'});}catch(e){}
  setTimeout(()=>{if(Speech)$('dictate').click();},900);
}
$('wake-toggle').onclick=()=>{wakeCtx?wakeStop():wakeStart();};
