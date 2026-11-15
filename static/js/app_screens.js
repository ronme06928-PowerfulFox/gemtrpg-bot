// static/js/app_screens.js
// ログイン後の画面（メインメニューとその下の画面）の切り替えと、URL の # の扱い（計画62、E02 Part 18）。
// main.js のグローバル（showRoomPortal・leaveCurrentSocketRoom など）を使う。

(function () {
  const SCREENS = ['menu', 'sessions', 'help', 'characters', 'units', 'master', 'users'];
  // 全幅の画面に描く部品。戻り値は {destroy, allowLeave?}。
  const WORKSPACES = {
    characters: host => mountOwnedCharacters(host),
    units: host => mountUnitManagement(host),
    master: host => mountCatalogWorkspace(host),
  };
  const HELP_LINKS = [
    ['/manuals/rulebook.pdf', '基本ルールブック', 'PDF'],
    ['/manuals/guide.pdf', 'セッション操作ガイド', 'PDF'],
    ['/static/help/master_data.html', 'マスターデータの使い方', '管理画面'],
  ];
  const MENU_CARDS = [
    ['sessions', 'sapphire', 'セッション', 'ルーム一覧'],
    ['dungeon', 'ruby', 'ダンジョン', '準備中'],
    ['characters', 'topaz', 'マイキャラクター', '作成・管理'],
    ['help', 'quartz', '使い方', 'ルールブック・ガイド'],
  ];
  const DATA_CARDS = [
    ['units', 'emerald', 'ユニット管理'],
    ['master', 'amethyst', 'マスターデータ'],
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
      const disabled = key === 'dungeon';
      return `<button type="button" class="menu-card" data-screen-card="${key}" data-gem="${gem}"${disabled ? ' disabled' : ''}>
        <span class="menu-card__copy"><strong>${title}</strong><span>${summary}</span></span>
        ${disabled ? '' : '<span class="menu-card__arrow" aria-hidden="true">›</span>'}</button>`;
    }).join('');
    const data = DATA_CARDS.map(([key, gem, title]) =>
      `<button type="button" class="menu-data-button" data-screen-card="${key}" data-gem="${gem}">${title}</button>`).join('');
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

  function showPortal(html) {
    for (const id of ['entry-portal', 'room-portal', 'main-app-container']) {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    }
    hideMenuScreens();
    const menu = portal();
    menu.innerHTML = html;
    menu.style.display = 'block';
  }

  function showMainMenu() {
    showPortal(menuHtml({name: window.currentUsername, isAppAdmin: window.currentUserIsAppAdmin}));
  }

  function showHelp() {
    showPortal(helpHtml());
  }

  function showWorkspace(name) {
    showPortal(`${backBar()}<div class="screen-workspace" data-screen="${name}"></div>`);
    mounted = {name, controller: WORKSPACES[name](portal().querySelector('.screen-workspace'))};
  }

  function showUsers() {
    if (!window.currentUserIsAppAdmin) { goScreen('menu'); return; }
    for (const id of ['entry-portal', 'room-portal', 'main-app-container']) {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    }
    hideMenuScreens();
    showUserManagement();
  }

  function showScreen(name) {
    if (name === 'sessions') showRoomPortal();
    else if (name === 'help') showHelp();
    else if (name === 'users') showUsers();
    else if (WORKSPACES[name]) showWorkspace(name);
    else showMainMenu();
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
    const ok = await showAppConfirm('ルーム一覧に戻りますか？\n（保存していない変更は失われます）', {
      defaultFocus: 'cancel', title: 'ルーム一覧へ戻る', confirmText: '戻る',
    });
    if (!ok) return false;
    const leaveResult = await leaveCurrentSocketRoom();
    if (!leaveResult?.ok) {
      console.warn('Socket room leave acknowledgement timed out.', leaveResult);
      showAppAlert('ルームからの退出を確認できませんでした。接続を確認して、もう一度お試しください。', { title: 'エラー' });
      return false;
    }
    exitRoomTo(name);
    return true;
  }

  function exitRoomTo(name) {
    document.getElementById('main-app-container').style.display = 'none';
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

  Object.assign(window, {
    AppScreens: {screenFromHash, menuHtml, helpHtml},
    showStartScreen, goScreen, hideMenuScreens, clearScreenHash, enterRoomHistory, leaveRoomTo, exitRoomTo,
  });
})();
