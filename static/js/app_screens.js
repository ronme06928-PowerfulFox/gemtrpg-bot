// static/js/app_screens.js
// ログイン後の画面（メインメニューとその下の画面）の切り替えと、URL の # の扱い（計画62、E02 Part 18）。
// main.js のグローバル（showRoomPortal・leaveCurrentSocketRoom など）を使う。

(function () {
  const SCREENS = ['menu', 'sessions', 'dungeon', 'help', 'characters', 'units', 'master', 'hollow-data', 'users', 'encyclopedia', 'drill'];
  const unitScreen = domain => domain === 'hollow' ? 'hollow-data' : 'units';
  const mountUnits = domain => (host, options) => mountUnitManagement(host, {...options, domain});
  // 全幅の画面に描く部品。戻り値は {destroy, allowLeave?}。
  const WORKSPACES = {
    drill: (host, options) => mountDrill(host, options),
    encyclopedia: (host, options) => mountEncyclopedia(host, options),
    characters: host => mountOwnedCharacters(host),
    units: mountUnits('session'),
    'hollow-data': mountUnits('hollow'),
    dungeon: host => mountDungeon(host),
    master: (host, options) => mountCatalogWorkspace(host, { onOpenUnit: openReferencedUnit, ...options }),
  };
  const HELP_LINKS = [
    ['/manuals/rulebook.pdf', '基本ルールブック', 'PDF'],
    ['/manuals/guide.pdf', 'セッション操作ガイド', 'PDF'],
    ['/static/help/master_data.html', 'マスターデータの使い方', '管理画面'],
  ];
  const MENU_CARDS = [
    ['sessions', 'sapphire', 'セッション', 'ルーム一覧'],
    ['dungeon', 'ruby', 'ダンジョン', 'ホロウの部屋'],
    ['characters', 'topaz', 'マイキャラクター', '作成・管理'],
    ['encyclopedia', 'emerald', '図鑑', '世界の理・技能と魔物'],
    ['drill', 'citrine', '演習場', '模擬戦闘'],
    ['help', 'quartz', '使い方', 'ルールブック・ガイド'],
  ];
  const DATA_CARDS = [
    ['units', 'emerald', 'ユニット管理'],
    ['master', 'amethyst', 'マスターデータ'],
    ['hollow-data', 'emerald', 'ホロウデータ', 'abyss'],
  ];

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));

  function screenFromHash(hash) {
    const name = String(hash || '').replace(/^#/, '');
    return SCREENS.includes(name) ? name : 'menu';
  }

  function backBar() {
    return '<div class="screen-back-bar"><button type="button" class="screen-back" data-screen-back="menu">← メインメニュー</button></div>';
  }

  function menuHtml({name, isAppAdmin} = {}) {
    const cards = MENU_CARDS.map(([key, gem, title, summary]) => {
      return `<button type="button" class="menu-card" data-screen-card="${key}" data-gem="${gem}">
        <span class="menu-card__copy"><strong>${title}</strong><span>${summary}</span></span>
        <span class="menu-card__arrow" aria-hidden="true">›</span></button>`;
    }).join('');
    const data = DATA_CARDS.map(([key, gem, title, theme]) =>
      `<button type="button" class="menu-data-button" data-screen-card="${key}" data-gem="${gem}"${theme ? ` data-theme="${theme}"` : ''}>${title}</button>`).join('');
    const adminItem = isAppAdmin ? '<li><button type="button" data-account-action="users">ユーザー管理</button></li>' : '';
    return `<header class="menu-head">
        <span class="menu-head__brand">ジェムリアTRPG</span>
        <div class="menu-account">
          <button type="button" class="menu-account__toggle" aria-haspopup="true" aria-expanded="false">${escapeHtml(name)} ▾</button>
          <ul class="menu-account__list" hidden>
            <li><button type="button" data-account-action="settings">ユーザー設定</button></li>
            ${adminItem}
            <li><button type="button" data-account-action="logout">ログアウト</button></li>
          </ul>
        </div>
      </header>
      <section class="main-menu">
        <h1>メインメニュー</h1>
        <nav class="menu-grid" aria-label="移動先">${cards}</nav>
        <nav class="menu-data" aria-label="データ管理"><h2>データ管理</h2>${data}</nav>
      </section>`;
  }

  function helpHtml() {
    const rows = HELP_LINKS.map(([href, title, kind]) =>
      `<li><a class="help-link" href="${href}" target="_blank" rel="noopener"><strong>${title}</strong><span>${kind}</span></a></li>`).join('');
    return `${backBar()}<section class="main-menu help-screen"><h1>使い方</h1><ul class="help-list">${rows}</ul></section>`;
  }

  const portal = () => document.getElementById('menu-portal');
  const visible = id => document.getElementById(id)?.style.display === 'block';
  let mounted = null;  // {name, controller}

  function releaseWorkspace() {
    mounted?.controller.destroy();
    mounted = null;
  }

  function hideMenuScreens() {
    releaseWorkspace();
    const menu = portal();
    if (menu) menu.style.display = 'none';
    const users = document.getElementById('user-management-portal');
    if (users) users.style.display = 'none';
  }

  function showPortal(html, theme = 'paper') {
    setRoomVisible(false);
    for (const id of ['entry-portal', 'room-portal']) {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    }
    hideMenuScreens();
    const menu = portal();
    menu.dataset.theme = theme;
    menu.innerHTML = html;
    menu.style.display = 'block';
  }

  function showMainMenu() {
    showPortal(menuHtml({name: window.currentUsername, isAppAdmin: window.currentUserIsAppAdmin}));
  }

  function showHelp() {
    showPortal(helpHtml());
  }

  function showWorkspace(name, options) {
    showPortal(`${backBar()}<div class="screen-workspace" data-screen="${name}"></div>`,
      ['hollow-data','dungeon'].includes(name) ? 'abyss' : 'paper');
    mounted = {name, controller: WORKSPACES[name](portal().querySelector('.screen-workspace'), options)};
  }

  window.openMenuEncyclopedia = async entryId => {
    if (!(await canLeaveWorkspace())) return;
    if (mounted?.name === 'encyclopedia') return mounted.controller.openEntry(entryId);
    followWorkspaceLink('encyclopedia', { entryId });
  };
  function followWorkspaceLink(name, options) {
    history.replaceState(null, '', '#' + name);
    showWorkspace(name, options);
  }

  function openReferencedUnit(entryId, origin, trail, domain) {
    followWorkspaceLink(unitScreen(domain), { entryId, originName: origin.name,
      onReferenceBack: () => followWorkspaceLink('master', { origin, trail }) });
  }

  function showUsers() {
    if (!window.currentUserIsAppAdmin) { goScreen('menu'); return; }
    setRoomVisible(false);
    for (const id of ['entry-portal', 'room-portal']) {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    }
    hideMenuScreens();
    showUserManagement();
  }

  async function showScreen(name) {
    try {
      if (name === 'sessions') await showRoomPortal();
      else if (name === 'help') showHelp();
      else if (name === 'users') showUsers();
      else if (WORKSPACES[name]) showWorkspace(name);
      else showMainMenu();
    } finally {
      window.AppLoading.end();
    }
  }

  let leaveApproved = false;  // 画面の中の操作で確認を済ませたとき、hashchange で聞き直さない。

  async function canLeaveWorkspace(target) {
    if (!mounted || mounted.name === target || !mounted.controller.allowLeave) return true;
    return mounted.controller.allowLeave();
  }

  async function goScreen(name) {
    if (!await canLeaveWorkspace(name)) return;
    if (screenFromHash(location.hash) === name && location.hash) { showScreen(name); return; }
    leaveApproved = !!mounted;
    location.hash = name;
  }

  function showStartScreen() {
    showScreen(screenFromHash(location.hash));
  }

  function clearScreenHash() {
    if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  }

  // ルームでは # を付けない。入るときに履歴を1つ足し、「戻る」で退出の確認を出せるようにする。
  function enterRoomHistory() {
    if (location.hash) history.pushState(null, '', location.pathname + location.search);
  }

  async function leaveRoomTo(name) {
    if (window.PracticeRoom?.active) return window.PracticeRoom.leave(name==='sessions'?'menu':name);
    const hollow = window.currentRoomPlayMode === 'hollow';
    if (hollow) name = 'dungeon';
    const destination = hollow ? 'ダンジョン' : 'ルーム一覧';
    const ok = await showAppConfirm(`${destination}に戻りますか？\n（保存していない変更は失われます）`, {
      defaultFocus: 'cancel', title: `${destination}へ戻る`, confirmText: '戻る',
    });
    if (!ok) return false;
    window.AppLoading.begin({title: typeof currentRoomName === 'string' ? currentRoomName : '', step: 'ルームを出ています'});
    const leaveResult = await leaveCurrentSocketRoom();
    if (!leaveResult?.ok) {
      window.AppLoading.end();
      console.warn('Socket room leave acknowledgement timed out.', leaveResult);
      window.showAppNotice('ルームからの退出を確認できませんでした。接続を確認して、もう一度お試しください。', {kind: 'error'});
      return false;
    }
    exitRoomTo(name);
    return true;
  }

  function exitRoomTo(name) {
    window.HollowParty?.close();
    window.HollowMap?.close();
    window.resetRoomEncyclopedia?.();
    window.currentRoomPlayMode = null;
    window.currentRoomRole = null;
    setRoomVisible(false);
    goScreen(name);
  }

  async function onHashChange() {
    if (visible('entry-portal') || !window.currentUsername) return;
    const target = screenFromHash(location.hash);
    // ブラウザーの「戻る」などで移るとき、保存していない変更があればその画面の確認を通す。
    // 取り消したら今の画面の # を積み直して留まる（もう一度「戻る」を押せば、また確認が出る）。
    const approved = leaveApproved;
    leaveApproved = false;
    if (!approved && mounted) {
      const leaving = mounted;
      if (!await canLeaveWorkspace(target)) {
        if (mounted === leaving) history.pushState(null, '', '#' + leaving.name);
        return;
      }
    }
    if (!visible('main-app-container')) {
      showScreen(target);
      return;
    }
    // ルームの中で「戻る」を押したとき。取り消したら # の無い状態に戻す。
    const left = await leaveRoomTo(target);
    if (!left) history.pushState(null, '', location.pathname + location.search);
  }

  async function logout() {
    const yes = await showAppConfirm('この端末からログアウトします。よろしいですか？', {
      title: 'ログアウト', confirmText: 'ログアウト', cancelText: 'キャンセル',
    });
    if (!yes) return;
    try {
      // device モード: 端末トークンを失効し、自動復旧を止める。
      await fetch(API_BASE_URL + '/api/logout', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify({mode: 'device'}),
      });
    } catch (_e) { /* 失効はベストエフォート */ }
    clearSavedRecoveryToken();
    window.PracticeRoom?.clear();
    showEntryPortal();  // 先にログインの画面へ移し、切断の知らせを出さない（main.js の disconnect）。
    try { if (socket && socket.connected) socket.disconnect(); } catch (_e) {}
  }

  function setAccountOpen(open) {
    const toggle = portal()?.querySelector('.menu-account__toggle');
    if (!toggle) return;
    toggle.setAttribute('aria-expanded', String(open));
    portal().querySelector('.menu-account__list').hidden = !open;
  }

  const ACCOUNT_ACTIONS = {
    settings: () => openUserSettingsModal(true),
    users: () => goScreen('users'),
    logout,
  };

  document.addEventListener('click', event => {
    const back = event.target.closest('[data-screen-back]');
    if (back) { goScreen(back.dataset.screenBack); return; }
    const card = event.target.closest('#menu-portal [data-screen-card]');
    if (card) { goScreen(card.dataset.screenCard); return; }
    const toggle = event.target.closest('#menu-portal .menu-account__toggle');
    if (toggle) { setAccountOpen(toggle.getAttribute('aria-expanded') !== 'true'); return; }
    const account = event.target.closest('#menu-portal [data-account-action]');
    setAccountOpen(false);
    if (account) ACCOUNT_ACTIONS[account.dataset.accountAction]();
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const toggle = portal()?.querySelector('.menu-account__toggle[aria-expanded="true"]');
    if (!toggle) return;
    setAccountOpen(false);
    toggle.focus();
  });
  addEventListener('hashchange', onHashChange);

  // --- 切断と再接続（E02 Part 18 §1、OPS-RECONNECT 案A） ---
  // ルームの中で切れたら、ルーム名と役割をこのタブに覚え、読み込み直した後に同じルームへ入り直す。
  const RECONNECT_KEY = 'gemRoomReconnect';

  function rememberReconnectRoom(room, role) {
    try { sessionStorage.setItem(RECONNECT_KEY, JSON.stringify({room, role})); } catch (_e) { /* 覚えられなければメニューへ */ }
  }

  function forgetReconnectRoom() {
    try { sessionStorage.removeItem(RECONNECT_KEY); } catch (_e) { /* 何もしない */ }
  }

  function takeReconnectRoom() {
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(RECONNECT_KEY) || 'null'); } catch (_e) { saved = null; }
    forgetReconnectRoom();
    return saved && typeof saved.room === 'string' && saved.room
      ? {room: saved.room, role: saved.role === 'GM' ? 'GM' : 'Player'} : null;
  }

  // 覚えたルームがあれば入り直して true を返す。入り直せなければメインメニューを開いて知らせる。
  function resumeRoomAfterReconnect() {
    const saved = takeReconnectRoom();
    if (!saved) return false;
    (async () => {
      try {
        const response = await fetchWithSession('/load_room?name=' + encodeURIComponent(saved.room));
        if (!response.ok) throw new Error('room unavailable');
        await joinRoom(saved.room, await response.json(), {role: saved.role, gmPin: ''});
      } catch (_e) {
        showStartScreen();
        window.showAppNotice?.(`ルーム「${saved.room}」に戻れませんでした。ルーム一覧から入り直してください。`, {kind: 'error'});
      }
    })();
    return true;
  }

  Object.assign(window, {
    AppScreens: {screenFromHash, menuHtml, helpHtml},
    showStartScreen, goScreen, hideMenuScreens, clearScreenHash, enterRoomHistory, leaveRoomTo, exitRoomTo,
    rememberReconnectRoom, forgetReconnectRoom, takeReconnectRoom, resumeRoomAfterReconnect,
  });
})();
