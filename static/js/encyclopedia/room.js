(function () {
  let savedRoom, position, current;
  const roomName = () => typeof currentRoomName === 'string' ? currentRoomName : '';
  function close() {
    if (!current) return;
    position = current.controller.getState();
    current.controller.destroy();
    current.dialog.remove();
    current = null;
  }
  window.closeRoomEncyclopedia = close;
  window.resetRoomEncyclopedia = () => { close(); savedRoom = null; position = null; };
  window.openRoomEncyclopedia = async entryId => {
    const room = roomName();
    if (!room) return window.openMenuEncyclopedia?.(entryId);
    if (savedRoom !== room) { window.resetRoomEncyclopedia(); savedRoom = room; }
    if (!current) {
      const dialog = document.createElement('dialog');
      dialog.className = 'encyclopedia-room';
      dialog.setAttribute('aria-label', '図鑑');
      dialog.innerHTML = '<header class="encyclopedia-room-header"><strong>図鑑</strong><button type="button">閉じる</button></header><div class="encyclopedia-room-content"></div>';
      document.body.append(dialog);
      dialog.showModal();
      const controller = window.mountEncyclopedia(dialog.querySelector('.encyclopedia-room-content'), { room, initialState:position });
      current = { dialog, controller };
      dialog.querySelector('button').addEventListener('click', close);
      dialog.addEventListener('cancel', event => { event.preventDefault(); event.stopPropagation(); close(); });
    }
    if (entryId) await current.controller.openEntry(entryId);
  };
  // 小さな窓を開くたびに全部を読み直さないよう、同じルームなら30秒は使い回す。
  let cached;
  const loadForLink = () => {
    const room = roomName();
    if (!cached || cached.room !== room || Date.now() - cached.at > 30000) {
      cached = { room, at:Date.now(), promise:window.EncyclopediaData.load({ room }) };
      cached.promise.catch(() => { cached = null; });
    }
    return cached.promise;
  };
  window.attachEncyclopediaLink = (container, entryId, closePopup) => {
    container.querySelector('.encyclopedia-link-slot')?.remove();
    const slot = document.createElement('div');
    slot.className = 'encyclopedia-link-slot';
    container.append(slot);
    loadForLink().then(({ masters, extra }) => {
      if (!slot.isConnected) return;
      const data = window.EncyclopediaData.build(masters, extra, false);
      if (!Object.values(data.rowsByKind).flat().some(row => row.id === entryId && row.met)) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'encyclopedia-open-link';
      button.textContent = '図鑑で見る';
      button.addEventListener('click', () => { closePopup(); window.openRoomEncyclopedia(entryId); });
      slot.append(button);
    }).catch(() => { /* 読み込めない間は入口を出さない。 */ });
  };
})();
