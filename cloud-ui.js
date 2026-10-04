(() => {
  $('cloud-signout').onclick=async()=>{try{await api('cloud/logout',{});location.href='/login';}catch(e){$('cloud-status').textContent=e.message;}};
  $('cloud-migrate').onclick=async()=>{const b=$('cloud-migrate');b.disabled=true;$('cloud-status').textContent='기존 로컬 데이터를 가져오는 중…';try{const d=await api('cloud/migrate',{});$('cloud-status').textContent=`기억 ${d.memories}개 · 대화 ${d.messages}개 · 파일 ${d.files}개 가져옴. 원본 파일은 유지됩니다.`;await refresh();}catch(e){$('cloud-status').textContent=e.message;}finally{b.disabled=false;}};
  api('cloud/status').then(d=>{$('cloud-status').textContent=d.connected?d.email+' · Supabase 저장소 연결됨':'클라우드 미연결';}).catch(e=>{$('cloud-status').textContent=e.message;});
})();
