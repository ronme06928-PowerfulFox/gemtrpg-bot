(function () {
  let active=null, selection=null, dialog=null, controller=null;
  const resumeKey='gemPracticeRoom';
  function closeDetails() { if (dialog) dialog.close(); }
  function clear() {
    closeDetails(); active=null;
    sessionStorage.removeItem(resumeKey);
    document.body.classList.remove('practice-room');
    document.querySelector('.practice-controls')?.remove();
  }
  function sync(state) {
    if (!state?.practice) { if (active) clear(); return; }
    active=state.practice; selection=JSON.parse(JSON.stringify(active.selection));
    if (currentRoomName) sessionStorage.setItem(resumeKey,currentRoomName);
    document.body.classList.add('practice-room');
    const name=document.getElementById('current-room-name');
    if (!name) return;
    name.textContent='演習場';
    let bar=document.querySelector('.practice-controls');
    if (!bar) {
      bar=document.createElement('nav'); bar.className='practice-controls'; bar.dataset.theme='paper';
      bar.setAttribute('aria-label','練習の操作'); name.before(bar);
    }
    bar.innerHTML=`<span class="practice-mode">相手：<button type="button" data-practice="mode" data-mode="manual" aria-pressed="${active.opponent_mode==='manual'}">自分で</button><button type="button" data-practice="mode" data-mode="auto" aria-pressed="${active.opponent_mode==='auto'}">自動</button></span><button type="button" data-practice="reset">⟲ 最初に戻す</button><button type="button" data-practice="detail">詳しく見る</button><button type="button" data-practice="choose">キャラを選び直す</button>`;
  }
  function request(action,mode) {
    return new Promise((resolve,reject)=>socket.timeout(10000).emit('practice_control',{room:currentRoomName,action,mode},
      (error,response)=>error || response?.error ? reject(new Error(response?.error || '通信を確認してください。')) : resolve(response)));
  }
  function detail() {
    if (dialog || !active) return;
    const state=battleState, bs=window.BattleStore?.state || {};
    const actor=state.characters.find(char=>char.id==='practice_0'), target=state.characters.find(char=>char.id==='practice_1');
    if (!actor || !target) return;
    function skill(char) {
      const slot=Object.values(bs.slots || {}).find(row=>row.actor_id===char.id && bs.intents?.[row.slot_id]?.skill_id);
      return slot ? bs.intents[slot.slot_id].skill_id : null;
    }
    dialog=document.createElement('dialog'); dialog.className='practice-detail'; dialog.dataset.theme='paper';
    dialog.innerHTML='<button type="button" class="practice-detail-close">ルームへ戻る</button><div data-practice-detail></div>';
    document.body.appendChild(dialog);
    controller=window.mountDrill(dialog.querySelector('[data-practice-detail]'),{room:currentRoomName,
      snapshot:{actor,target,skill_id:skill(actor),target_skill_id:skill(target)}});
    dialog.querySelector('button').onclick=closeDetails;
    dialog.addEventListener('keydown',event=>{if(event.key==='Escape') event.stopPropagation();});
    dialog.addEventListener('close',()=>{controller?.destroy(); controller=null; dialog.remove(); dialog=null;},{once:true});
    dialog.showModal();
  }
  async function leave(destination='menu') {
    if (!active) return false;
    const result=await leaveCurrentSocketRoom();
    if (!result?.ok) { window.showAppNotice('退出を確認できませんでした。',{kind:'error'}); return false; }
    clear(); currentRoomName=null; currentUserAttribute='Player'; window.currentUserAttribute='Player';
    window.exitRoomTo(destination);
    return true;
  }
  function resume() {
    const room=sessionStorage.getItem(resumeKey);
    if (!room) return false;
    (async () => {
      try {
        const response=await fetchWithSession('/load_room?name='+encodeURIComponent(room));
        if (!response.ok) throw new Error('expired practice');
        await joinRoom(room,await response.json(),{role:'GM',gmPin:''});
      } catch (_) {
        clear(); currentRoomName=null; currentUserAttribute='Player'; window.currentUserAttribute='Player';
        showStartScreen();
      }
    })();
    return true;
  }
  function disconnected() {
    closeDetails();
    const bar=document.querySelector('.practice-controls');
    if (bar) bar.innerHTML='<span role="status">再接続しています…</span>';
  }
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-practice]');
    if (!button || !active) return;
    try {
      if (button.dataset.practice==='choose') return await leave('drill');
      if (button.dataset.practice==='detail') return detail();
      button.disabled=true;
      await request(button.dataset.practice,button.dataset.mode);
    } catch(error) { window.showAppNotice(error.message,{kind:'error'}); }
    finally { button.disabled=false; }
  });
  window.PracticeRoom={sync,clear,leave,resume,disconnected,get active(){return !!active;},getSelection:()=>selection};
})();
