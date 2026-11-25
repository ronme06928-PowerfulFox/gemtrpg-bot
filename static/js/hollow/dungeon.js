(function () {
  const {h} = window.CatalogWorkspaceParts;
  const roomsUrl = '/api/hollow/rooms';
  const actions = '<button type="button" class="dungeon-primary" data-action="create">新しく作る</button>' +
    '<button type="button" data-action="join">参加コードで入る</button>';

  function roomCard(room, index) {
    const floor = room.run?.floor;
    const running = room.run?.status === 'in_progress';
    const tier = running && Number.isInteger(floor) && floor >= 1 && floor <= 50 ? Math.ceil(floor / 10) : 0;
    const status = running
      ? `<span class="room-recruit-badge">ラン中</span>${tier ? `<strong>${floor}F · T${tier}</strong>` : ''}`
      : '<span>パーティを組んでいる</span>';
    const tiers = [1,2,3,4,5].map(value => `<span class="dungeon-tier"${value === tier ? ' aria-current="step"' : ''}>
      T${value}${value === tier ? ' <span aria-hidden="true">●</span>' : ''}</span>`).join('');
    const party = (room.party_names || []).slice(0,6);
    return `<li class="room-list-item dungeon-room" data-dungeon-room="${index}">
      <div class="room-list-main"><strong class="room-list-name">${h(room.name)}</strong>
        <div class="room-list-meta room-list-desc"><span>オーナー ${h(room.owner_name || '—')}</span><span>ホスト ${h(room.host_name || '—')}</span></div></div>
      <div class="dungeon-run">${status}</div><div class="dungeon-tiers" role="group" aria-label="区切り">${tiers}</div>
      <div class="dungeon-party"><span>パーティ</span>${party.length
        ? `<ul>${party.map(name => `<li>${h(name)}</li>`).join('')}</ul>` : '—'}</div>
      <div class="room-list-buttons">${room.your_role === 'owner' ? '<button type="button" class="dungeon-danger" data-action="delete">削除</button>' : ''}
        <button type="button" class="dungeon-primary" data-action="enter">入る</button></div>
    </li>`;
  }

  async function request(url, payload) {
    const response = await fetchWithSession(url, payload ? {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
    } : undefined);
    if (response.status === 404 && payload) throw new Error('ホロウの部屋が見つかりません。');
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || '通信に失敗しました。');
    return body;
  }

  function mountDungeon(host) {
    host.innerHTML = `<header class="dungeon-hero"><div><p>ホロウダンジョン</p><h1>虚夢の辺縁</h1></div></header>
      <main class="main-menu paper-panel dungeon-panel"><header class="dungeon-heading"><h2>参加中の部屋</h2>
        <div class="room-controls" data-dungeon-actions></div></header>
        <div data-dungeon-list aria-live="polite"><p>読み込み中…</p></div>
        <dialog class="paper-dialog dungeon-dialog" aria-labelledby="dungeon-dialog-title">
          <header class="user-settings-panel-header"><h2 class="user-settings-panel-title" id="dungeon-dialog-title"></h2></header>
          <form class="user-settings-panel-body auth-form">
            <div class="auth-pane">
              <label for="dungeon-room-name">部屋名</label><input id="dungeon-room-name" name="room_name" type="text" required maxlength="100" autocomplete="off">
              <label for="dungeon-join-code">参加コード</label><input id="dungeon-join-code" name="join_code" type="text" maxlength="32" autocomplete="off">
              <p class="screen-error" role="alert" hidden></p>
            </div>
            <div class="paper-dialog__actions room-list-buttons"><button type="button" data-action="cancel">戻る</button>
              <button class="dungeon-primary" type="submit"></button></div>
          </form>
        </dialog>
      </main>`;
    const list = host.querySelector('[data-dungeon-list]');
    const controls = host.querySelector('[data-dungeon-actions]');
    const dialog = host.querySelector('.dungeon-dialog');
    const form = dialog.querySelector('form');
    const code = form.elements.join_code;
    const error = form.querySelector('[role="alert"]');
    const submit = form.querySelector('[type="submit"]');
    let rooms = [];
    let creating = false;
    let busy = false;

    async function refresh() {
      try {
        ({rooms} = await request(roomsUrl));
        controls.innerHTML = rooms.length ? actions : '';
        list.innerHTML = rooms.length ? `<ul class="room-list dungeon-rooms">${rooms.map(roomCard).join('')}</ul>`
          : `<div class="owned-chars-empty dungeon-empty"><p>参加中の部屋はありません</p><div class="room-controls">${actions}</div></div>`;
      } catch (failure) {
        list.innerHTML = `<p class="screen-error">${h(failure.message)}</p><button type="button" data-action="reload">再読み込み</button>`;
      }
    }

    function showError(message) {
      error.hidden = !message;
      error.textContent = message;
    }

    function openDialog(action) {
      creating = action === 'create';
      form.reset();
      showError('');
      dialog.querySelector('h2').textContent = creating ? '部屋を作成' : '参加コードで入る';
      submit.textContent = creating ? '作成' : '参加';
      code.hidden = code.labels[0].hidden = creating;
      code.required = !creating;
      dialog.showModal();
      form.elements.room_name.focus();
    }

    form.addEventListener('input', () => showError(''));
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy) return;
      busy = submit.disabled = true;
      const room_name = form.elements.room_name.value.trim();
      const join_code = code.value.trim();
      let result;
      try {
        result = creating ? await request(roomsUrl,{room_name})
          : await request('/api/join_room_by_code',{room_name,join_code,play_mode:'hollow'});
      } catch (failure) {
        showError(failure.message);
        return;
      } finally {
        busy = submit.disabled = false;
      }
      if (!host.isConnected) return;
      dialog.close();
      await refresh();
      if (!host.isConnected) return;
      if (result.join_code) await showRoomJoinCode(result.join_code);
      else window.showAppNotice(`「${room_name}」に参加しました。`, {kind:'success'});
    });

    host.addEventListener('click', async event => {
      const button = event.target.closest('[data-action]');
      if (!button || busy) return;
      const action = button.dataset.action;
      if (action === 'create' || action === 'join') openDialog(action);
      if (action === 'cancel') dialog.close();
      if (action === 'reload') await refresh();
      const card = button.closest('[data-dungeon-room]');
      if (!card) return;
      busy = true;
      try {
        const room = rooms[Number(card.dataset.dungeonRoom)];
        if (action === 'enter') await joinRoom(room.name, null, {role:'Player', gmPin:''});
        if (action === 'delete') await deleteRoom(room.name, {hollow:true, refresh});
      } finally {
        busy = false;
      }
    });

    refresh();
    return {destroy() { if (dialog.open) dialog.close(); }};
  }

  window.mountDungeon = mountDungeon;
})();
