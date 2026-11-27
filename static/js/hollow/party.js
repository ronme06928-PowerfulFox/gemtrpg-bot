(function () {
  const escape = value => window.CatalogWorkspaceParts.h(value ?? '');
  const sortieSize = 4;
  const capacity = 6;
  let partyDialog;
  let dragId;
  let lastMarkup;
  let ownedPicker;

  function currentParty(state = battleState) {
    const members = state?.hollow?.members || [];
    const host = state?.hollow?.host_user_id;
    const owner = members.some(member => member.id === currentUserId && member.role === 'owner');
    const manage = owner || (host && host === currentUserId);
    const locked = state?.hollow?.run?.status !== 'forming';
    const allies = (state?.characters || []).filter(char => char.type === 'ally');
    const byId = new Map(allies.map(char => [char.id, char]));
    const order = (state?.party?.order || []).filter(id => byId.has(id));
    return {members, host, owner, manage, locked, byId, order};
  }

  function button(action, label, id = '', disabled = false) {
    return `<button type="button" class="btn-set" data-party-action="${action}" data-id="${escape(id)}"${disabled ? ' disabled' : ''}>${label}</button>`;
  }

  function statusLine(char) {
    const fp = char.states?.find(state => state.name === 'FP')?.value ?? 0;
    return `HP ${escape(char.hp ?? '–')}/${escape(char.maxHp ?? '–')} · MP ${escape(char.mp ?? '–')}/${escape(char.maxMp ?? '–')} · FP ${escape(fp)}`;
  }

  function characterRow(char, index, party) {
    const canEdit = party.manage && !party.locked;
    const canUseItem = party.manage || (char.owner_id ? char.owner_id === currentUserId : char.owner === currentUsername);
    return `<li class="hollow-party-row" data-party-row="${escape(char.id)}">
      ${canEdit ? `<button type="button" class="btn-set hollow-party-grip" data-party-action="move" data-id="${escape(char.id)}"
        draggable="true" aria-label="${escape(char.name)}を並べ替え（上下キー）" title="並べ替え">⠿</button>` : ''}
      <span class="hollow-party-number">${index + 1}</span>
      ${char.image ? `<img class="hollow-party-face" src="${escape(char.image)}" alt="">`
        : `<span class="hollow-party-face" aria-hidden="true">${escape(Array.from(char.name || '？')[0])}</span>`}
      <div class="hollow-party-character"><strong>${escape(char.name)}</strong>
        <span>${escape(char.owner || party.members.find(member => member.id === char.owner_id)?.name || '—')}</span>
        <span>${statusLine(char)}</span></div>
      <div class="hollow-party-actions">
        ${button('item', 'アイテム', char.id, !canUseItem)}
        ${button('detail', '詳細', char.id)}
        ${canEdit ? button('remove', '外す', char.id) : ''}
      </div></li>`;
  }

  function render(state) {
    renderOwnedPicker(state);
    if (!partyDialog?.open) return;
    const party = currentParty(state);
    const rows = party.order.map((id, index) => characterRow(party.byId.get(id), index, party));
    const markup = `<div class="hollow-party-columns">
      <section aria-label="パーティ編成">
        <p class="hollow-party-note">番号＝淵遺物の「N番目」 ${party.locked ? '<strong>🔒 並び固定</strong>' : ''}</p>
        <h3>出撃 <small>${Math.min(rows.length, sortieSize)} / ${sortieSize}</small></h3>
        <ol class="hollow-party-list" data-party-group="sortie">${rows.slice(0, sortieSize).join('') || '<li class="hollow-party-note">—</li>'}</ol>
        <h3>控え <small>${Math.max(0, rows.length - sortieSize)} / ${capacity - sortieSize}</small></h3>
        <ol class="hollow-party-list" data-party-group="reserve" start="5">${rows.slice(sortieSize).join('') || '<li class="hollow-party-note">—</li>'}</ol>
      </section>
      <section aria-label="参加者"><h3>参加者</h3><ol class="hollow-party-list">
        ${party.members.map(member => `<li class="hollow-party-member">
          <strong>${escape(member.name)}</strong>
          <span class="hollow-party-tags">${[
            member.id === party.host && 'ホスト', member.role === 'owner' && 'オーナー',
            member.id === currentUserId && '自分'
          ].filter(Boolean).map(tag => `<span>${tag}</span>`).join('')}</span>
          ${party.manage && member.id !== currentUserId && member.id !== party.host
            ? button('transfer', 'ホストを譲る', member.id) : ''}
        </li>`).join('')}</ol>
        ${!party.owner ? `<div class="hollow-party-actions hollow-party-leave">${button('leave', '部屋を退出')}</div>` : ''}
      </section></div>`;
    if (lastMarkup === markup) return;
    lastMarkup = markup;
    const body = partyDialog.querySelector('[data-party-body]');
    const focus = document.activeElement;
    body.innerHTML = markup;
    if (focus?.dataset.partyAction) {
      [...body.querySelectorAll('[data-party-action]')].find(control =>
        control.dataset.partyAction === focus.dataset.partyAction && control.dataset.id === focus.dataset.id)?.focus();
    }
  }

  function notify(error) {
    const status = partyDialog?.open && partyDialog.querySelector('[role="alert"]');
    if (status) status.textContent = error || '';
    else if (error) window.showAppNotice(error, {kind: 'error'});
  }

  function send(event, payload) {
    notify('');
    window.socket.timeout(5000).emit(event, payload, (error, result) => {
      if (error || !result?.ok) notify(result?.error || '通信に失敗しました');
    });
  }

  function move(id, index) {
    const order = currentParty().order;
    if (index >= 0 && index < order.length && order.indexOf(id) !== index) {
      send('hollow_party_change', {action: 'move', char_id: id, index});
    }
  }

  async function post(url, room) {
    const response = await fetchWithSession(url, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({room_name: room})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '通信に失敗しました');
    return result;
  }

  async function confirmAction(message, label) {
    const room = currentRoomName;
    partyDialog.close();
    const confirmed = await window.showAppConfirm(message, {title: label, confirmText: label, defaultFocus: 'cancel'});
    if (currentRoomName !== room || window.currentRoomPlayMode !== 'hollow') return false;
    open();
    return confirmed;
  }

  async function handleAction(event) {
    const control = event.target.closest('[data-party-action]');
    if (!control) return;
    const {partyAction, id} = control.dataset;
    if (partyAction === 'close') partyDialog.close();
    if (partyAction === 'item' || partyAction === 'detail') {
      partyDialog.close();
      if (partyAction === 'item') openItemModal(id);
      else window.showCharacterDetail(id);
    }
    if (partyAction === 'remove') send('hollow_party_change', {action: 'remove', char_id: id});
    if (partyAction === 'transfer') {
      const member = currentParty().members.find(row => row.id === id);
      if (member && await confirmAction(`「${member.name}」にホストを譲りますか？`, 'ホストを譲る')) {
        send('hollow_transfer_host', {user_id: id});
      }
    }
    if (partyAction === 'leave' && await confirmAction('部屋を退出しますか？', '部屋を退出')) {
      const room = currentRoomName;
      try {
        await post('/api/hollow/leave', room);
        revoked({room});
      } catch (error) { notify(error.message); }
    }
  }

  function createDialog(id, title, content) {
    const dialog = document.createElement('dialog');
    dialog.id = id;
    dialog.className = 'hollow-window';
    dialog.dataset.theme = 'abyss';
    dialog.setAttribute('aria-labelledby', `${id}-title`);
    dialog.innerHTML = `<header><h2 id="${id}-title">${title}</h2></header>${content}`;
    document.body.append(dialog);
    return dialog;
  }

  function open() {
    if (!partyDialog) {
      partyDialog = createDialog('hollow-party-window', 'パーティ', `
        <div data-party-body></div><p role="alert" class="hollow-party-error"></p>
        <footer>${button('close', '閉じる')}</footer>`);
      partyDialog.addEventListener('click', handleAction);
      partyDialog.addEventListener('keydown', event => {
        const id = event.target.closest('.hollow-party-grip')?.dataset.id;
        if (!id || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        move(id, currentParty().order.indexOf(id) + (event.key === 'ArrowUp' ? -1 : 1));
      });
      partyDialog.addEventListener('dragstart', event => {
        dragId = event.target.closest('.hollow-party-grip')?.dataset.id;
        if (dragId) {
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', dragId);
        }
      });
      partyDialog.addEventListener('dragend', () => { dragId = null; });
      partyDialog.addEventListener('dragover', event => {
        if (dragId && event.target.closest('[data-party-group]')) event.preventDefault();
      });
      partyDialog.addEventListener('drop', event => {
        const group = event.target.closest('[data-party-group]');
        if (!dragId || !group) return;
        event.preventDefault();
        const order = currentParty().order;
        const target = event.target.closest('[data-party-row]')?.dataset.partyRow;
        const index = target ? order.indexOf(target) : group.dataset.partyGroup === 'sortie'
          ? Math.min(sortieSize, order.length) - 1 : order.length - 1;
        move(dragId, index);
        dragId = null;
      });
    }
    if (!partyDialog.open) {
      partyDialog.showModal();
      notify('');
    }
    render();
  }

  function showCode(room, code, {created = false} = {}) {
    document.getElementById('hollow-code-window')?.remove();
    const dialog = createDialog('hollow-code-window', created ? '部屋を作りました' : '参加コード', `
      <dl><dt>部屋名</dt><dd>${escape(room)}</dd><dt>参加コード</dt><dd class="hollow-code">${escape(code)}</dd></dl>
      <footer><span role="status"></span>${button('copy', 'まとめて写す')}${button('close', '閉じる')}</footer>`);
    dialog.addEventListener('click', async event => {
      const action = event.target.closest('[data-party-action]')?.dataset.partyAction;
      if (action === 'close') dialog.close();
      if (action === 'copy') {
        const message = dialog.querySelector('[role="status"]');
        try {
          await navigator.clipboard.writeText(`部屋：${room}　参加コード：${code}`);
          message.textContent = 'コピーしました';
        } catch { message.textContent = 'コピーできませんでした'; }
      }
    });
    dialog.addEventListener('close', () => dialog.remove(), {once: true});
    dialog.showModal();
  }

  async function reviewCode() {
    const room = currentRoomName;
    try {
      const result = await post('/api/hollow/join_code', room);
      if (room === currentRoomName && window.currentRoomPlayMode === 'hollow') showCode(result.room_name, result.join_code);
    } catch (error) { notify(error.message); }
  }

  function renderOwnedPicker(state = battleState) {
    const picker = ownedPicker;
    if (!picker) return;
    if (state?.hollow?.run?.status !== 'forming') { picker.dialog.close(); return; }
    const {byId, order} = currentParty(state);
    const inParty = new Set(order.map(id => byId.get(id)?.owned_character_id));
    const available = Math.max(0, capacity - order.length);
    for (const key of [...picker.selected]) {
      if (inParty.has(key) || picker.selected.size > available) picker.selected.delete(key);
    }
    const root = picker.dialog.querySelector('.hollow-owned-list');
    const focus = root.contains(document.activeElement) ? document.activeElement.value : null;
    const scroll = root.scrollTop;
    picker.dialog.querySelector('[data-owned-count]').textContent =
      available ? `空き ${available}人 · 選択 ${picker.selected.size}人` : '空きがありません';
    if (picker.rows) {
      root.innerHTML = picker.rows.map(row => {
        const data = row.data || {};
        const tags = Array.isArray(data.tag_ids) ? data.tag_ids : [];
        const status = Array.isArray(data.status) ? data.status : [];
        const origin = tags.find(tag => tag.startsWith('出身:'))?.slice(3) || '—';
        const stat = label => status.find(item => item?.label === label || item?.name === label)?.value ??
          data[label.toLowerCase()] ?? '—';
        const joined = inParty.has(row.id);
        const checked = picker.selected.has(row.id);
        const disabled = joined || !available || (!checked && picker.selected.size >= available) || picker.busy;
        const image = window.UnitForms.image(data.image);
        return `<label class="hollow-owned-row">
          <input type="checkbox" value="${escape(row.id)}"${checked ? ' checked' : ''}${disabled ? ' disabled' : ''}>
          <span class="hollow-party-face">${image || escape(Array.from(row.name || '？')[0])}</span>
          <span><strong>${escape(row.name)}</strong><small>出身 ${escape(origin)}</small></span>
          <span class="hollow-owned-stats">HP ${escape(stat('HP'))} · MP ${escape(stat('MP'))}
          ${joined ? '<b>パーティにいます</b>' : ''}</span>
        </label>`;
      }).join('') || '<p>持ちキャラがありません。</p>';
    }
    root.scrollTop = scroll;
    if (focus) [...root.querySelectorAll('input')].find(input => input.value === focus)?.focus({preventScroll: true});
    picker.dialog.querySelector('[data-owned-submit]').disabled = picker.busy || !picker.selected.size;
  }

  async function openOwnedPicker() {
    if (ownedPicker || battleState?.hollow?.run?.status !== 'forming') return;
    const dialog = createDialog('hollow-owned-window', 'パーティメンバーを追加', `
      <div class="hollow-owned-content"><p data-owned-count></p><div class="hollow-owned-list">読み込み中…</div>
      <p role="alert" class="hollow-party-error"></p></div>
      <footer><button type="button" class="btn-set" data-owned-close>閉じる</button>
      <button type="button" class="btn-set" data-owned-submit>追加</button></footer>`);
    const picker = {dialog, selected: new Set(), rows: null, busy: false};
    ownedPicker = picker;
    const alert = dialog.querySelector('[role="alert"]');
    dialog.addEventListener('close', () => {
      if (ownedPicker === picker) ownedPicker = null;
      dialog.remove();
    }, {once: true});
    dialog.querySelector('[data-owned-close]').onclick = () => dialog.close();
    dialog.querySelector('[data-owned-submit]').onclick = () => {
      if (picker.busy || !picker.selected.size || battleState?.hollow?.run?.status !== 'forming') return;
      picker.busy = true;
      alert.textContent = '';
      const ids = [...picker.selected];
      renderOwnedPicker();
      window.socket.timeout(7000).emit('hollow_party_add_owned', {owned_ids: ids}, (error, result) => {
        if (!dialog.open) return;
        if (!error && result?.ok) { dialog.close(); return; }
        picker.busy = false;
        alert.textContent = result?.error || '通信に失敗しました';
        renderOwnedPicker();
      });
    };
    dialog.addEventListener('change', event => {
      if (!event.target.matches('input[type="checkbox"]')) return;
      const {value, checked} = event.target;
      if (checked) picker.selected.add(value);
      else picker.selected.delete(value);
      renderOwnedPicker();
    });
    dialog.showModal();
    renderOwnedPicker();
    try {
      const response = await fetchWithSession('/api/owned_characters');
      if (!response.ok) throw new Error('一覧の取得に失敗しました。');
      const {characters} = await response.json();
      if (dialog.open) {
        picker.rows = characters || [];
        renderOwnedPicker();
      }
    } catch (error) {
      if (dialog.open) {
        dialog.querySelector('.hollow-owned-list').textContent = '';
        alert.textContent = error.message;
      }
    }
  }

  function mountDock(dock, state) {
    if (!dock) return;
    const hollow = state?.play_mode === 'hollow';
    dock.classList.toggle('is-hollow-dock', hollow);
    let add = dock.querySelector('#dock-hollow-add');
    const party = dock.querySelector('#dock-hollow-party');
    if (!hollow) {
      window.HollowRelics?.mountDock(dock,state);
      add?.remove();
      party?.remove();
      return;
    }
    const dockButton = (id, label, icon, action) => {
      const control = document.createElement('button');
      control.type = 'button';
      control.id = id;
      control.className = 'dock-icon';
      control.title = label;
      control.setAttribute('aria-label', label);
      control.textContent = icon;
      control.onclick = action;
      return control;
    };
    if (!party) dock.prepend(dockButton('dock-hollow-party', 'パーティ', '👥', open));
    window.HollowRelics?.mountDock(dock,state);
    if (!add) {
      add = dockButton('dock-hollow-add', 'パーティメンバーを追加', '➕', openOwnedPicker);
      const original = dock.querySelector('#dock-add-char-icon');
      if (original) original.before(add);
      else dock.append(add);
    }
    add.disabled = state.hollow?.run?.status !== 'forming';
    add.classList.toggle('disabled', add.disabled);
  }

  function renderRibbon(root, state) {
    const party = currentParty(state);
    const run = state.hollow.run;
    const tier = run.map?.tier;
    const status = run.reward ? `ラン中 · T${tier} · ${run.floor}F 報酬`
      : run.fusion ? 'ラン中 · 虚夢変転'
      : run.map_candidates ? 'ラン中 · マップ選択待ち' : run.status === 'in_progress' && tier ? `ラン中 · T${tier} · ${run.floor}F`
      : {forming: 'パーティ編成中', in_progress: 'ラン中', finished: '遠征終了'}[run.status] || '—';
    const host = party.members.find(member => member.id === party.host)?.name || '—';
    root.innerHTML = `<div class="hollow-ribbon" data-theme="abyss">
      <strong>${status}</strong><span>ホスト ${escape(host)}</span><span>${party.order.length} / ${capacity} 人</span>
      ${party.owner ? button('code', '参加コード') : ''}</div>`;
    root.querySelector('[data-party-action="code"]')?.addEventListener('click', reviewCode);
  }

  function close() {
    partyDialog?.close();
    ownedPicker?.dialog.close();
    lastMarkup = null;
    document.getElementById('hollow-code-window')?.close();
  }

  function isOwner() {
    return battleState?.hollow?.members ? currentParty().owner : window.currentRoomRole === 'owner';
  }

  function canReset(state = battleState) {
    return canProgress(state) && state?.combat_phase === 'active';
  }

  function canProgress(state = battleState) {
    return state?.play_mode === 'hollow' && !!currentUserId && (
      state.hollow?.host_user_id === currentUserId ||
      state.hollow?.members?.some(member => member.id === currentUserId && member.role === 'owner')
    );
  }

  function canControlCharacter(charId, state = battleState) {
    if (canProgress(state)) return true;
    const char = state?.characters?.find(row => row.id === charId);
    if (!char) return false;
    if (char.owner_id) return !!currentUserId && char.owner_id === currentUserId;
    return (char.owner || state.character_owners?.[charId]) === currentUsername;
  }

  function revoked({room}) {
    if (room === currentRoomName && window.currentRoomPlayMode === 'hollow') {
      close();
      exitRoomTo('dungeon');
    }
  }

  window.HollowParty = {
    render, mountDock, renderRibbon, showCode, reviewCode, close, isOwner, revoked, canProgress, canReset, canControlCharacter
  };
})();
