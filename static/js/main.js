// --- グローバル設定 ---
const API_BASE_URL = (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost')
    ? 'http://127.0.0.1:5000'
    : window.location.origin;
let socket = null;
let battleState = { characters: [], timeline: [], round: 0 };
let currentRoomName = null;
let currentUsername = null;
let currentUserAttribute = null;
let currentRoomUserList = [];
let socketInitInFlight = false;
let entryRequestInFlight = false;
let currentUserId = null; // ★追加: ユーザーID (UUID)
let currentUserIsAppAdmin = false;
const receivedLogIds = new Set();
const RECOVERY_STORAGE_KEY = 'gem_dicebot_recovery_v1';

function applySessionUserData(data) {
    currentUsername = data.username;
    currentUserAttribute = data.attribute;
    currentUserId = data.user_id;
    currentUserIsAppAdmin = !!data.is_app_admin;
    window.currentUsername = currentUsername;
    window.currentUserAttribute = currentUserAttribute;
    window.currentUserId = currentUserId;
    window.currentUserIsAppAdmin = currentUserIsAppAdmin;
}

function saveRecoveryTokenFromResponse(data) {
    if (!data || !data.user_id || !data.recovery_token) return;
    try {
        localStorage.setItem(RECOVERY_STORAGE_KEY, JSON.stringify({
            user_id: data.user_id,
            recovery_token: data.recovery_token,
        }));
    } catch (_e) {}
}

function clearSavedRecoveryToken() {
    try { localStorage.removeItem(RECOVERY_STORAGE_KEY); } catch (_e) {}
}

async function showRecoveryCodeOnce(code) {
    if (!code) return;
    await showAppConfirm(`この復旧コードを控えてください。\n\n${code}\n\nブラウザを変えた時やセッションが切れた時に、同じユーザーへ戻るために使います。再表示はできません。`, {
        title: '復旧コード',
        confirmText: '控えました',
    });
}

function escapeDialogText(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function openAppDialog({ title = '確認', message = '', mode = 'confirm', defaultValue = '', placeholder = '', confirmText = 'OK', cancelText = 'キャンセル', required = false } = {}) {
    return new Promise((resolve) => {
        document.getElementById('app-dialog-backdrop')?.remove();

        const overlay = document.createElement('div');
        overlay.id = 'app-dialog-backdrop';
        overlay.className = 'modal-backdrop app-dialog-backdrop';
        overlay.innerHTML = `
            <div class="modal-content app-dialog-modal" role="dialog" aria-modal="true" aria-labelledby="app-dialog-title">
                <style>
                    .app-dialog-modal {
                        width: min(420px, calc(100vw - 28px));
                        padding: 22px;
                        border-radius: 16px;
                        border: 1px solid rgba(30, 45, 54, 0.18);
                        box-shadow: 0 24px 70px rgba(0, 0, 0, 0.22);
                    }
                    .app-dialog-title {
                        margin: 0 0 10px;
                        font-size: 1.18rem;
                        color: #173f36;
                    }
                    .app-dialog-message {
                        white-space: pre-wrap;
                        line-height: 1.65;
                        color: #34443f;
                    }
                    .app-dialog-input {
                        width: 100%;
                        box-sizing: border-box;
                        margin-top: 14px;
                        padding: 10px 12px;
                        border: 1px solid #b8c9c2;
                        border-radius: 10px;
                        font-size: 1rem;
                    }
                    .app-dialog-error {
                        min-height: 1.2em;
                        margin-top: 8px;
                        color: #b42318;
                        font-size: 0.9rem;
                    }
                    .app-dialog-actions {
                        display: flex;
                        justify-content: flex-end;
                        gap: 10px;
                        margin-top: 18px;
                    }
                    .app-dialog-actions button {
                        border: none;
                        border-radius: 999px;
                        padding: 9px 18px;
                        cursor: pointer;
                        font-weight: 700;
                    }
                    .app-dialog-cancel {
                        background: #e6ece9;
                        color: #25352f;
                    }
                    .app-dialog-confirm {
                        background: #d97732;
                        color: white;
                    }
                </style>
                <h3 id="app-dialog-title" class="app-dialog-title">${escapeDialogText(title)}</h3>
                <div class="app-dialog-message">${escapeDialogText(message)}</div>
                ${mode === 'prompt' ? `<input id="app-dialog-input" class="app-dialog-input" value="${escapeDialogText(defaultValue)}" placeholder="${escapeDialogText(placeholder)}">` : ''}
                <div id="app-dialog-error" class="app-dialog-error"></div>
                <div class="app-dialog-actions">
                    <button id="app-dialog-cancel" class="app-dialog-cancel" type="button">${escapeDialogText(cancelText)}</button>
                    <button id="app-dialog-confirm" class="app-dialog-confirm" type="button">${escapeDialogText(confirmText)}</button>
                </div>
            </div>
        `;

        const input = overlay.querySelector('#app-dialog-input');
        const error = overlay.querySelector('#app-dialog-error');
        const cancelValue = mode === 'prompt' ? null : false;
        const cleanup = (value) => {
            document.removeEventListener('keydown', onKeyDown);
            overlay.remove();
            resolve(value);
        };
        const submit = () => {
            if (mode === 'prompt') {
                const value = String(input?.value || '').trim();
                if (required && !value) {
                    if (error) error.textContent = '入力してください。';
                    input?.focus();
                    return;
                }
                cleanup(value || null);
                return;
            }
            cleanup(true);
        };
        function onKeyDown(event) {
            if (event.key === 'Escape') cleanup(cancelValue);
            if (event.key === 'Enter' && (mode !== 'prompt' || document.activeElement === input)) submit();
        }

        overlay.querySelector('#app-dialog-cancel')?.addEventListener('click', () => cleanup(cancelValue));
        overlay.querySelector('#app-dialog-confirm')?.addEventListener('click', submit);
        overlay.addEventListener('click', (event) => {
            if (event.target === overlay) cleanup(cancelValue);
        });
        document.addEventListener('keydown', onKeyDown);
        document.body.appendChild(overlay);
        setTimeout(() => (input || overlay.querySelector('#app-dialog-confirm'))?.focus(), 0);
    });
}

function showAppConfirm(message, options = {}) {
    return openAppDialog({
        title: options.title || '確認',
        message,
        mode: 'confirm',
        confirmText: options.confirmText || '実行',
        cancelText: options.cancelText || 'キャンセル',
    });
}

function showAppPrompt(message, options = {}) {
    return openAppDialog({
        title: options.title || '入力',
        message,
        mode: 'prompt',
        defaultValue: options.defaultValue || '',
        placeholder: options.placeholder || '',
        confirmText: options.confirmText || '作成',
        cancelText: options.cancelText || 'キャンセル',
        required: !!options.required,
    });
}

window.showAppConfirm = showAppConfirm;
window.showAppPrompt = showAppPrompt;

function getLogDedupeKey(logData) {
    if (!logData || typeof logData !== 'object') return '';
    const hasId = (logData.log_id !== undefined && logData.log_id !== null);
    if (!hasId) return '';
    const id = String(logData.log_id);
    const hasTs = (logData.timestamp !== undefined && logData.timestamp !== null);
    if (!hasTs) return id;
    return `${id}:${String(logData.timestamp)}`;
}

// Battle debug logs are OFF by default.
// Enable:
//   localStorage.setItem('battle_debug_verbose', '1'); location.reload();
// Disable:
//   localStorage.removeItem('battle_debug_verbose'); location.reload();
if (typeof window !== 'undefined' && typeof window.BATTLE_DEBUG_VERBOSE === 'undefined') {
    try {
        window.BATTLE_DEBUG_VERBOSE = localStorage.getItem('battle_debug_verbose') === '1';
    } catch (_e) {
        window.BATTLE_DEBUG_VERBOSE = false;
    }
}

function battleDebugLog(...args) {
    if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
        console.log(...args);
    }
}

function rememberLogIdsFromState(state) {
    if (!state || !Array.isArray(state.logs)) return;
    state.logs.forEach((logData) => {
        const key = getLogDedupeKey(logData);
        if (!key) return;
        receivedLogIds.add(key);
    });
    if (receivedLogIds.size > 4000) {
        const keep = Array.from(receivedLogIds).slice(-2500);
        receivedLogIds.clear();
        keep.forEach((id) => receivedLogIds.add(id));
    }
}

// --- 1. UIコンテナの参照 ---
const entryPortal = document.getElementById('entry-portal');
const roomPortal = document.getElementById('room-portal');
const mainAppContainer = document.getElementById('main-app-container');
const mainContent = document.getElementById('main-content');
const tabButtons = document.querySelectorAll('.tab-button');

// --- 2. APIフェッチ ---
async function fetchWithSession(url, options = {}) {
    options.credentials = 'include';
    const response = await fetch(API_BASE_URL + url, options);
    if (response.status === 401) {
        console.warn('Authentication error (401). Redirecting to entry portal.');
        showEntryPortal();
        throw new Error('認証が必要です。');
    }
    return response;
}

// --- 3. エントリー/ポータル機能 ---
// 通常ログイン(login_name+password)を主導線とし、新規登録・復旧を補助導線へ分ける。
function showEntryPortal() {
    roomPortal.style.display = 'none';
    mainAppContainer.style.display = 'none';
    entryPortal.style.display = 'block';

    const entryMsg = document.getElementById('entry-message');
    const setMsg = (text, ok) => {
        entryMsg.textContent = text || '';
        entryMsg.className = 'auth-message' + (text ? (ok ? ' success' : ' error') : '');
    };

    const portal = document.getElementById('entry-portal');
    if (portal.dataset.listenerAttached) {
        setMsg('');
        return;
    }
    portal.dataset.listenerAttached = 'true';

    const panes = { login: 'auth-pane-login', register: 'auth-pane-register', recover: 'auth-pane-recover' };
    const tabs = { login: 'auth-tab-login', register: 'auth-tab-register', recover: 'auth-tab-recover' };
    function showTab(name) {
        for (const k in panes) {
            const pane = document.getElementById(panes[k]);
            const tab = document.getElementById(tabs[k]);
            if (pane) pane.style.display = (k === name ? 'block' : 'none');
            if (tab) tab.classList.toggle('active', k === name);
        }
        setMsg('');
    }
    document.getElementById('auth-tab-login').addEventListener('click', () => showTab('login'));
    document.getElementById('auth-tab-register').addEventListener('click', () => showTab('register'));
    document.getElementById('auth-tab-recover').addEventListener('click', () => showTab('recover'));
    showTab('login');

    async function postJson(url, body) {
        const r = await fetch(API_BASE_URL + url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(body),
        });
        let d = {};
        try { d = await r.json(); } catch (_e) { d = {}; }
        return { ok: r.ok, status: r.status, data: d };
    }
    function onSuccess(data) {
        applySessionUserData(data);
        saveRecoveryTokenFromResponse(data);
        initializeSocketIO();
    }
    async function withLock(fn) {
        if (entryRequestInFlight) return;
        try { entryRequestInFlight = true; await fn(); }
        catch (e) { setMsg(e.message || String(e)); }
        finally { entryRequestInFlight = false; }
    }

    // ログイン
    document.getElementById('login-btn').addEventListener('click', () => withLock(async () => {
        const login_name = document.getElementById('login-name').value.trim();
        const password = document.getElementById('login-password').value;
        if (!login_name || !password) { setMsg('ログインIDとパスワードを入力してください'); return; }
        const { ok, data } = await postJson('/api/login', { login_name, password });
        if (!ok) throw new Error(data.error || 'ログインに失敗しました');
        onSuccess(data);
    }));

    // 新規登録
    document.getElementById('register-btn').addEventListener('click', () => withLock(async () => {
        const login_name = document.getElementById('register-name').value.trim();
        const display_name = document.getElementById('register-display').value.trim();
        const password = document.getElementById('register-password').value;
        if (!login_name || !password) { setMsg('ログインIDとパスワードを入力してください'); return; }
        const { ok, data } = await postJson('/api/register', { login_name, display_name, password });
        if (!ok) throw new Error(data.error || '登録に失敗しました');
        onSuccess(data);
    }));

    // 復旧コードでログイン → 任意でログインID/パスワード設定
    document.getElementById('recover-code-btn').addEventListener('click', () => withLock(async () => {
        const username = document.getElementById('recover-name').value.trim();
        if (!username) { setMsg('名前を入力してください'); return; }
        const recovery_code = await showAppPrompt('復旧コードを入力してください。', {
            title: 'ユーザー復旧', placeholder: 'GEM-XXXX-XXXX', confirmText: '復旧', required: true,
        });
        if (!recovery_code) return;
        const { ok, data } = await postJson('/api/recover_user', { username, recovery_code });
        if (!ok) throw new Error(data.error || '復旧に失敗しました');
        onSuccess(data);
        await _offerPasswordSetup();
    }));

    // 管理者発行ワンタイムコードで再設定
    document.getElementById('redeem-code-btn').addEventListener('click', () => withLock(async () => {
        const login_name = await showAppPrompt('ログインIDを入力してください。', { title: 'ワンタイムコード再設定', required: true });
        if (!login_name) return;
        const code = await showAppPrompt('管理者発行のコードを入力してください。', { title: 'ワンタイムコード', required: true });
        if (!code) return;
        const { ok, data } = await postJson('/api/redeem_login_code', { login_name, code });
        if (!ok) throw new Error(data.error || 'コードが正しくありません');
        const res = await _setPasswordFlow(login_name);
        if (res && res.ok) onSuccess(res.data);
    }));

    async function _offerPasswordSetup() {
        const yes = await showAppConfirm('ログインID・パスワードを設定すると、次回からログインで入れます。設定しますか？', {
            title: 'パスワード設定', confirmText: '設定する', cancelText: 'あとで',
        });
        if (!yes) return;
        await _setPasswordFlow();
    }
    async function _setPasswordFlow(prefillLogin) {
        const login_name = prefillLogin || await showAppPrompt('ログインIDを設定してください。', { title: 'ログインID', required: true });
        if (!login_name) return { ok: false };
        const password = await showAppPrompt('新しいパスワード（10文字以上）を入力してください。', { title: 'パスワード設定', required: true });
        if (!password) return { ok: false };
        const { ok, data } = await postJson('/api/set_password', { login_name, password });
        if (!ok) { setMsg(data.error || 'パスワード設定に失敗しました'); return { ok: false }; }
        setMsg('パスワードを設定しました', true);
        return { ok: true, data };
    }
}

async function showRoomPortal() {
    if (typeof window.removeBattleOnlyCenterCta === 'function') {
        try { window.removeBattleOnlyCenterCta(); } catch (_e) {}
    }
    if (typeof window.__boQuickStartCleanup === 'function') {
        try { window.__boQuickStartCleanup(); } catch (_e) {}
    }
    entryPortal.style.display = 'none';
    mainAppContainer.style.display = 'none';
    roomPortal.style.display = 'block';
    roomPortal.innerHTML = '<h2>ルーム一覧を読み込み中...</h2>';

    try {
        const shouldClearRoomRole = !!currentRoomName || currentUserAttribute === 'GM';
        if (shouldClearRoomRole) {
            await fetchWithSession('/api/leave_room_context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            currentUserAttribute = 'Player';
            window.currentUserAttribute = currentUserAttribute;
            currentRoomName = null;
        }
    } catch (error) {
        console.warn('Failed to clear room context:', error);
    }

    try {
        const response = await fetchWithSession('/list_rooms');
        if (!response.ok) throw new Error('サーバーからルーム一覧を取得できませんでした。');
        const data = await response.json();
        // data: { rooms: [{name, owner_id, play_mode, battle_only_stage_id}, ...], current_user_id, is_gm }
        currentUserIsAppAdmin = !!data.is_app_admin;
        window.currentUserIsAppAdmin = currentUserIsAppAdmin;
        renderRoomPortal(data.rooms, data.current_user_id, data.is_gm);
    } catch (error) {
        console.error('Error fetching room list:', error);
        if (error.message !== '認証が必要です。') {
            roomPortal.innerHTML = `<h2 style="color: red;">エラー</h2><p>${error.message}</p>`;
        }
    }
}

function renderRoomPortal(rooms, currentUserId, isGm) {
    // ユーザー管理は app admin 限定（/api/admin/users が 403 になるため、
    // 非管理者にはボタン自体を出さない）。
    const manageUsersButton = currentUserIsAppAdmin
        ? `<button id="manage-users-btn" class="portal-settings-button" style="margin-left:10px; background:#e0e0ff;">👥 ユーザー管理</button>`
        : '';

    roomPortal.innerHTML = `
        <div class="portal-user-band">
            <span class="portal-welcome-message">
                ようこそ, <strong>${currentUsername}</strong> (${currentUserAttribute}) さん
            </span>
            <div>
                <button id="portal-user-settings-btn" class="portal-settings-button" title="ユーザー情報変更">
                    ⚙️ ユーザー設定
                </button>
                ${manageUsersButton}
                <button id="portal-logout-btn" class="portal-settings-button" style="margin-left:10px; background:#ffe0e0;" title="ログアウト">
                    🚪 ログアウト
                </button>
            </div>
        </div>
        <div class="room-portal-header">
            <h2>⚔️ ジェムリアTRPGダイスボット</h2>
            <p>参加するルームを選択するか、新しいルームを作成してください。</p>
        </div>
        <div class="room-controls">
            <input type="text" id="room-search-input" placeholder="ルームを検索...">
            <button id="refresh-room-list-btn" title="ルーム一覧を更新">更新</button>
            <button id="create-room-btn">＋ 新規ルーム作成</button>
            <button id="create-battle-only-room-btn">戦闘専用ルーム作成</button>
        </div>
        <div id="room-list-container">
            <h3>既存のルーム</h3>
            <ul id="room-list" class="room-list"></ul>
            <p id="room-list-empty" style="display: none;">該当するルームはありません。</p>
        </div>
        <button id="open-bo-preset-portal-btn" class="portal-floating-bo-btn">
            戦闘専用設定
        </button>
        <button id="open-owned-chars-btn" class="portal-floating-owned-chars-btn">
            マイキャラクター
        </button>
    `;

    const roomList = document.getElementById('room-list');
    const searchInput = document.getElementById('room-search-input');
    const createBtn = document.getElementById('create-room-btn');
    const createBattleOnlyBtn = document.getElementById('create-battle-only-room-btn');
    const refreshBtn = document.getElementById('refresh-room-list-btn');
    const emptyMsg = document.getElementById('room-list-empty');
    const settingsBtn = document.getElementById('portal-user-settings-btn');
    const boPresetPortalBtn = document.getElementById('open-bo-preset-portal-btn');
    const ownedCharsBtn = document.getElementById('open-owned-chars-btn');

    if (ownedCharsBtn) {
        ownedCharsBtn.addEventListener('click', () => {
            if (typeof openOwnedCharactersModal === 'function') openOwnedCharactersModal();
        });
    }

    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => openUserSettingsModal(true));
    }

    const logoutBtn = document.getElementById('portal-logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            const yes = await showAppConfirm('この端末からログアウトします。よろしいですか？', {
                title: 'ログアウト', confirmText: 'ログアウト', cancelText: 'キャンセル',
            });
            if (!yes) return;
            try {
                // device モード: 端末トークンを失効し、自動復旧を止める。
                await fetch(API_BASE_URL + '/api/logout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ mode: 'device' }),
                });
            } catch (_e) { /* 失効はベストエフォート */ }
            clearSavedRecoveryToken();
            try { if (socket && socket.connected) socket.disconnect(); } catch (_e) {}
            showEntryPortal();
        });
    }
    if (boPresetPortalBtn) {
        boPresetPortalBtn.addEventListener('click', () => {
            if (typeof openBattleOnlyCatalogModal === 'function') {
                openBattleOnlyCatalogModal({ room: null, fromLobby: true });
            } else {
                alert('戦闘専用設定画面を読み込めませんでした。');
            }
        });
    }

    // ★追加: ユーザー管理ボタンのイベントリスナー
    const manageUsersBtn = document.getElementById('manage-users-btn');
    if (manageUsersBtn) {
        manageUsersBtn.addEventListener('click', () => {
            if (typeof showUserManagement === 'function') {
                showUserManagement();
            } else {
                alert('機能読み込み中...');
            }
        });
    }

    // ★追加: 更新ボタンのイベントリスナー
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            showRoomPortal();
        });
    }

    function escapeRoomText(value) {
        return String(value ?? '').replace(/[&<>"']/g, (ch) => (
            {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;',
            }[ch]
        ));
    }

    function populateList(filter = '') {
        roomList.innerHTML = '';
        let count = 0;
        const normalizedFilter = filter.toLowerCase();

        const ROLE_LABEL = { owner: 'オーナー', gm: 'GM', player: '参加者' };
        rooms.forEach(roomInfo => {
            const name = String(roomInfo.name || '');
            if (!name.toLowerCase().includes(normalizedFilter)) return;

            const li = document.createElement('li');
            li.className = 'room-list-item';

            const isBattleOnly = String(roomInfo.play_mode || 'normal').toLowerCase() === 'battle_only';
            const modeBadge = isBattleOnly
                ? '<span class="room-mode-badge battle-only">戦闘専用</span>'
                : '<span class="room-mode-badge normal">通常</span>';

            const role = roomInfo.your_role;
            const isMember = !!roomInfo.is_member;
            // 個別カードのDTOが古くても、全体管理者には管理操作を表示する。
            const adminAccess = currentUserIsAppAdmin || !!roomInfo.admin_access;
            const roleBadge = adminAccess
                ? '<span class="room-role-badge">管理者</span>'
                : (role ? `<span class="room-role-badge">${ROLE_LABEL[role] || role}</span>` : '');
            const recruitBadge = roomInfo.recruitment_status
                ? `<span class="room-recruit-badge">${escapeRoomText(roomInfo.recruitment_status)}</span>` : '';
            const descHtml = roomInfo.description
                ? `<div class="room-list-desc">${escapeRoomText(roomInfo.description)}</div>` : '';

            let joinHtml;
            if (adminAccess || isMember) {
                joinHtml = '<button class="room-join-btn" data-action="enter">入室</button>';
            } else if (roomInfo.joinable) {
                joinHtml = '<button class="room-join-btn" data-action="join">参加</button>';
            } else {
                joinHtml = '<button class="room-join-btn" data-action="enter" disabled style="opacity:.5; cursor:not-allowed;">参加不可</button>';
            }
            const deleteBtn = (adminAccess || role === 'owner') ? '<button class="room-delete-btn">削除</button>' : '';
            const canManage = adminAccess || role === 'owner' || role === 'gm';
            const settingsBtn = canManage ? '<button class="room-settings-btn">⚙️設定</button>' : '';

            li.innerHTML = `
                <div class="room-list-main">
                    <span class="room-list-name">${escapeRoomText(name)}</span>
                    <div class="room-list-meta">${modeBadge}${roleBadge}${recruitBadge}</div>
                    ${descHtml}
                </div>
                <div class="room-list-buttons">
                    ${joinHtml}
                    ${settingsBtn}
                    ${deleteBtn}
                </div>
            `;
            const joinBtn = li.querySelector('.room-join-btn');
            if (joinBtn) {
                joinBtn.dataset.roomName = name;
                joinBtn.dataset.requiresCode = roomInfo.requires_code ? '1' : '0';
                joinBtn.dataset.role = adminAccess ? 'admin' : (role || '');
            }
            const deleteBtnEl = li.querySelector('.room-delete-btn');
            if (deleteBtnEl) deleteBtnEl.dataset.roomName = name;
            const settingsBtnEl = li.querySelector('.room-settings-btn');
            if (settingsBtnEl) settingsBtnEl.dataset.roomName = name;

            roomList.appendChild(li);
            count++;
        });
        emptyMsg.style.display = (count === 0) ? 'block' : 'none';
    }
    populateList('');

    searchInput.addEventListener('input', (e) => populateList(e.target.value));
    createBtn.addEventListener('click', createNewRoom);
    if (createBattleOnlyBtn) {
        createBattleOnlyBtn.addEventListener('click', createBattleOnlyRoom);
    }
    roomList.addEventListener('click', (e) => {
        const target = e.target;
        const roomName = target.dataset.roomName;
        if (target.classList.contains('room-join-btn')) {
            if (target.disabled) return;
            if (target.dataset.action === 'join') {
                joinRoomWithCode(roomName, target.dataset.requiresCode === '1');
            } else {
                joinRoom(roomName, null, null, target.dataset.role || null);
            }
        }
        if (target.classList.contains('room-delete-btn')) {
            deleteRoom(roomName);
        }
        if (target.classList.contains('room-settings-btn')) {
            const info = rooms.find(r => r.name === roomName);
            if (info) openRoomSettingsModal(info);
        }
    });
}

// ルーム内ヘッダー⚙️: まず「ユーザー設定 / ルーム設定」の2択を出す。
// ルーム設定は GM 相当（owner/gm = currentUserAttribute==='GM'）のみ表示。
function openInRoomSettingsChooser() {
    document.getElementById('settings-chooser-backdrop')?.remove();
    const isGm = currentUserAttribute === 'GM';
    const backdrop = document.createElement('div');
    backdrop.id = 'settings-chooser-backdrop';
    backdrop.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.45); display:flex; align-items:center; justify-content:center; z-index:9999;';
    backdrop.innerHTML = `
        <div style="background:#fff; border-radius:10px; padding:20px; width:min(320px,92vw); box-shadow:0 8px 24px rgba(0,0,0,0.2);">
            <h3 style="margin:0 0 14px;">設定</h3>
            <button id="chooser-user" class="portal-settings-button" style="display:block; width:100%; margin-bottom:10px;">⚙️ ユーザー設定</button>
            ${isGm ? '<button id="chooser-room" class="portal-settings-button" style="display:block; width:100%; margin-bottom:10px; background:#e0e0ff;">🏠 ルーム設定</button>' : ''}
            <button id="chooser-cancel" class="portal-settings-button" style="display:block; width:100%; background:#eee; color:#333;">閉じる</button>
        </div>`;
    document.body.appendChild(backdrop);
    const close = () => backdrop.remove();
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });
    backdrop.querySelector('#chooser-cancel').addEventListener('click', close);
    backdrop.querySelector('#chooser-user').addEventListener('click', () => { close(); openUserSettingsModal(false); });
    const roomBtn = backdrop.querySelector('#chooser-room');
    if (roomBtn) roomBtn.addEventListener('click', async () => { close(); await openCurrentRoomSettings(); });
}

// 現在入室中のルームのルーム設定モーダルを開く（ロビーへは戻らない）。
async function openCurrentRoomSettings() {
    if (!currentRoomName) { alert('ルーム情報を取得できませんでした。'); return; }
    try {
        const response = await fetchWithSession('/list_rooms');
        const data = await response.json();
        const info = (data.rooms || []).find(r => r.name === currentRoomName);
        if (!info) { alert('ルーム情報が見つかりませんでした。'); return; }
        openRoomSettingsModal(info, { refreshLobby: false });
    } catch (error) {
        alert(error.message);
    }
}

// ルーム情報・参加コード管理モーダル（owner: 全項目, gm: 募集状態のみ）
// opts.refreshLobby=false のときは保存後にロビーへ遷移しない（ルーム内から開いた場合）。
function openRoomSettingsModal(info, opts = {}) {
    const isOwner = currentUserIsAppAdmin || !!info.admin_access || info.your_role === 'owner';
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    document.getElementById('room-settings-modal-backdrop')?.remove();
    const backdrop = document.createElement('div');
    backdrop.id = 'room-settings-modal-backdrop';
    backdrop.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.45); display:flex; align-items:center; justify-content:center; z-index:9999;';

    const visOptions = ['hidden', 'listed', 'closed'].map(v => {
        const label = { hidden: '非公開(hidden)', listed: '公開(listed)', closed: '締切(closed)' }[v];
        const sel = (info.visibility || 'hidden') === v ? ' selected' : '';
        return `<option value="${v}"${sel}>${label}</option>`;
    }).join('');

    backdrop.innerHTML = `
        <div style="background:#fff; border-radius:10px; padding:20px; width:min(460px,92vw); max-height:88vh; overflow:auto; box-shadow:0 8px 24px rgba(0,0,0,0.2);">
            <h3 style="margin:0 0 12px;">ルーム情報: ${esc(info.name)}</h3>
            <label style="display:block; font-weight:bold; margin:8px 0 2px;">説明</label>
            <textarea id="rs-description" rows="3" style="width:100%; box-sizing:border-box;" ${isOwner ? '' : 'disabled'}>${esc(info.description)}</textarea>
            <label style="display:block; font-weight:bold; margin:10px 0 2px;">募集状態</label>
            <input id="rs-recruitment" type="text" maxlength="20" style="width:100%; box-sizing:border-box;" value="${esc(info.recruitment_status)}" placeholder="例: 募集中 / 締切">
            <label style="display:block; font-weight:bold; margin:10px 0 2px;">公開設定 ${isOwner ? '' : '(オーナー・管理者のみ変更可)'}</label>
            <select id="rs-visibility" style="width:100%; box-sizing:border-box;" ${isOwner ? '' : 'disabled'}>${visOptions}</select>
            ${isOwner ? `
            <div style="margin-top:14px; padding-top:12px; border-top:1px solid #eee;">
                <div style="font-weight:bold; margin-bottom:6px;">参加コード <span style="font-weight:normal; color:#888;">(${info.requires_code ? '設定済み' : '未設定'})</span></div>
                <button id="rs-set-code" type="button" style="margin-right:6px;">設定 / 再発行</button>
                <button id="rs-clear-code" type="button" ${info.requires_code ? '' : 'disabled'}>失効</button>
            </div>` : ''}
            <div id="rs-message" class="auth-message" style="margin-top:10px;"></div>
            <div style="margin-top:14px; text-align:right;">
                <button id="rs-cancel" type="button" style="margin-right:6px;">閉じる</button>
                <button id="rs-save" type="button">保存</button>
            </div>
        </div>`;
    document.body.appendChild(backdrop);

    const msg = backdrop.querySelector('#rs-message');
    const setMsg = (t, ok) => { msg.textContent = t || ''; msg.className = 'auth-message' + (t ? (ok ? ' success' : ' error') : ''); };
    const close = () => backdrop.remove();
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });
    backdrop.querySelector('#rs-cancel').addEventListener('click', close);

    backdrop.querySelector('#rs-save').addEventListener('click', async () => {
        const payload = { room_name: info.name };
        payload.recruitment_status = backdrop.querySelector('#rs-recruitment').value.trim();
        if (isOwner) {
            payload.description = backdrop.querySelector('#rs-description').value.trim();
            payload.lobby_visibility = backdrop.querySelector('#rs-visibility').value;
        }
        try {
            const r = await fetchWithSession('/api/room/update_settings', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
            });
            const d = await r.json();
            if (!r.ok) { setMsg(d.error || '更新に失敗しました'); return; }
            setMsg('保存しました', true);
            setTimeout(() => {
                close();
                if (opts.refreshLobby !== false) showRoomPortal();
            }, 600);
        } catch (e) { setMsg(e.message); }
    });

    if (isOwner) {
        backdrop.querySelector('#rs-set-code').addEventListener('click', async () => {
            const pin = await showAppPrompt('参加コードを入力してください（空欄なら自動生成）。', {
                title: '参加コード設定', placeholder: '4〜32文字 / 空欄で自動', confirmText: '設定',
            });
            if (pin === null) return; // キャンセル
            const body = { room_name: info.name };
            if (pin && pin.trim()) body.join_code = pin.trim();
            try {
                const r = await fetchWithSession('/api/room/set_join_code', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
                });
                const d = await r.json();
                if (!r.ok) { setMsg(d.error || 'コード設定に失敗しました'); return; }
                info.requires_code = true;
                await showAppConfirm(`参加コードを設定しました。\n\n${d.join_code}\n\nこのコードを参加者へ共有してください。`, { title: '参加コード', confirmText: 'OK' });
                setMsg('参加コードを設定しました', true);
            } catch (e) { setMsg(e.message); }
        });
        backdrop.querySelector('#rs-clear-code').addEventListener('click', async () => {
            try {
                const r = await fetchWithSession('/api/room/clear_join_code', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ room_name: info.name }),
                });
                const d = await r.json();
                if (!r.ok) { setMsg(d.error || '失効に失敗しました'); return; }
                info.requires_code = false;
                backdrop.querySelector('#rs-clear-code').disabled = true;
                setMsg('参加コードを失効しました', true);
            } catch (e) { setMsg(e.message); }
        });
    }
}

// 非メンバーが参加コードで参加 → membership作成 → 入室
async function joinRoomWithCode(roomName, requiresCode) {
    let join_code = '';
    if (requiresCode) {
        join_code = await showAppPrompt('参加コードを入力してください。', {
            title: 'ルームに参加', placeholder: '参加コード', confirmText: '参加', required: true,
        });
        if (!join_code) return;
    }
    try {
        const response = await fetchWithSession('/api/join_room_by_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room_name: roomName, join_code }),
        });
        const data = await response.json();
        if (!response.ok) {
            alert(data.error || 'ルーム参加に失敗しました');
            return;
        }
        joinRoom(roomName, null, null, data.role || 'player');
    } catch (error) {
        alert(error.message);
    }
}

async function createNewRoom() {
    await createRoomByMode('normal');
}

async function createBattleOnlyRoom() {
    await createRoomByMode('battle_only');
}

async function createRoomByMode(playMode) {
    const isBattleOnly = playMode === 'battle_only';
    const roomName = await showAppPrompt(isBattleOnly
        ? '戦闘専用ルーム名を入力してください'
        : 'ルーム名を入力してください',
        {
            title: isBattleOnly ? '戦闘専用ルーム作成' : '通常ルーム作成',
            placeholder: isBattleOnly ? '戦闘専用ルーム名' : 'ルーム名',
            confirmText: '作成',
            required: true,
        }
    );
    if (!roomName || roomName.trim() === '') {
        alert('ルーム名は必須です。');
        return;
    }

    const gmPin = await showAppPrompt('GM PINとして使う4桁の数字を入力してください。', {
        title: 'GM PIN設定',
        placeholder: '例: 1234',
        confirmText: '作成',
        required: true,
    });
    if (!/^\d{4}$/.test(String(gmPin || '').trim())) {
        alert('GM PINは4桁の数字で入力してください。');
        return;
    }

    const payload = { room_name: roomName.trim(), gm_pin: String(gmPin).trim() };
    if (isBattleOnly) {
        payload.play_mode = 'battle_only';
    }

    try {
        const response = await fetchWithSession('/create_room', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (response.status === 201) {
            currentUserAttribute = result.attribute || 'GM';
            window.currentUserAttribute = currentUserAttribute;
            joinRoom(payload.room_name, result.state, { role: 'GM', gmPin: payload.gm_pin });
        } else if (response.status === 409) {
            alert(`エラー: ルーム名「${payload.room_name}」は既に使用されています。`);
        } else {
            throw new Error(result.error || 'ルームの作成に失敗しました');
        }
    } catch (error) {
        console.error('Error creating room:', error);
        alert(`ルーム作成に失敗しました: ${error.message}`);
    }
}

async function deleteRoom(roomName) {
    const ok = await showAppConfirm(`本当にルーム「${roomName}」を削除しますか？\nこの操作は取り消せません。`, {
        title: 'ルーム削除',
        confirmText: '削除',
    });
    if (!ok) {
        return;
    }
    let gmPin = '';
    if (!currentUserIsAppAdmin) {
        gmPin = await showAppPrompt('このルームのGM PIN、または8桁のマスターキーを入力してください。', {
            title: '削除認証',
            placeholder: '4桁PIN / 8桁マスターキー',
            confirmText: '削除',
            required: true,
        });
        if (!/^\d{4}$|^\d{8}$/.test(String(gmPin || '').trim())) {
            alert('GM PINは4桁、マスターキーは8桁の数字で入力してください。');
            return;
        }
    }
    try {
        const response = await fetchWithSession('/delete_room', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room_name: roomName, gm_pin: String(gmPin).trim() })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '不明なエラー');
        alert(`ルーム「${roomName}」を削除しました。`);
        showRoomPortal();
    } catch (error) {
        console.error('Error deleting room:', error);
        alert(`ルームの削除に失敗しました: ${error.message}`);
    }
}

async function joinRoom(roomName, initialState = null, entryOptions = null, knownRole = null) {
    // Reset DOM initialization flag so dock re-initializes on room change
    // NOTE: Do NOT reset visualBattleSocketHandlersRegistered - socket handlers must only be registered once
    window.actionDockInitialized = false;
    // Debug log removed for production

    try {
        let roomEntry = entryOptions;
        if (!roomEntry && (knownRole === 'owner' || knownRole === 'gm' || knownRole === 'admin')) {
            // owner/gmメンバーまたはアプリ管理者は、入室種別を尋ねずGMとして入る。
            roomEntry = { role: 'GM', gmPin: '' };
        }
        if (!roomEntry) {
            const asGm = await showAppConfirm('GMとして入室しますか？', {
                title: '入室種別',
                confirmText: 'GM',
                cancelText: 'プレイヤー',
            });
            roomEntry = { role: asGm ? 'GM' : 'Player', gmPin: '' };
            if (asGm && !currentUserIsAppAdmin) {
                const gmPin = await showAppPrompt('GM PIN、または8桁のマスターキーを入力してください。', {
                    title: 'GM認証',
                    placeholder: '4桁PIN / 8桁マスターキー',
                    confirmText: '入室',
                    required: true,
                });
                if (!/^\d{4}$|^\d{8}$/.test(String(gmPin || '').trim())) {
                    alert('GM PINは4桁、マスターキーは8桁の数字で入力してください。');
                    return;
                }
                roomEntry.gmPin = String(gmPin).trim();
            }
        }

        const entryResponse = await fetchWithSession('/api/enter_room', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                room_name: roomName,
                role: roomEntry.role || 'Player',
                gm_pin: roomEntry.gmPin || '',
            })
        });
        const entryResult = await entryResponse.json();
        if (!entryResponse.ok) {
            throw new Error(entryResult.error || '入室認証に失敗しました');
        }
        currentUserAttribute = entryResult.attribute || 'Player';
        window.currentUserAttribute = currentUserAttribute;

        if (!initialState) {
            const response = await fetchWithSession(`/load_room?name=${encodeURIComponent(roomName)}`);
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'ルームのロードに失敗しました');
            }
            initialState = await response.json();
        }
        battleState = initialState;
        currentRoomName = roomName;
        socket.emit('join_room', {
            room: currentRoomName,
            username: currentUsername,
            role: roomEntry.role || currentUserAttribute,
            gm_pin: roomEntry.gmPin || ''
        });
        entryPortal.style.display = 'none';
        roomPortal.style.display = 'none';
        mainAppContainer.style.display = 'block';
        document.getElementById('current-room-name').textContent = `現在のルーム: ${currentRoomName}`;
        updateHeaderUserInfo();

        // === ▼▼▼ 修正点: デフォルトタブをビジュアルバトルフィールドに変更 ▼▼▼
        loadTabContent('visual');
        tabButtons.forEach(btn => btn.classList.remove('active'));
        const defaultTab = document.querySelector('.tab-button[data-tab="visual"]');
        if (defaultTab) {
            defaultTab.classList.add('active');
        }
        // === ▲▲▲ 修正ここまで ▲▲▲

    } catch (error) {
        console.error('Error joining room:', error);
        alert(`ルーム「${roomName}」への参加に失敗しました: ${error.message}`);
        showRoomPortal();
    }
}

function updateHeaderUserInfo() {
    const userEl = document.getElementById('header-username');
    const attrEl = document.getElementById('header-attribute');
    if (userEl) userEl.textContent = currentUsername;
    if (attrEl) attrEl.textContent = currentUserAttribute;
}

// --- 4. SocketIO初期化 ---
function initializeSocketIO() {
    if (socket) {
        if (!socket.connected && typeof socket.connect === 'function') {
            try { socket.connect(); } catch (_e) {}
        }
        return;
    }
    if (socketInitInFlight) {
        return;
    }
    socketInitInFlight = true;
    socket = io(API_BASE_URL, { withCredentials: true });
    window.socket = socket; // ★追加: グローバルに公開（SocketClient用）

    const registerAppSocketHandler = (eventName, handler) => {
        if (
            window.SocketClient
            && typeof window.SocketClient.on === 'function'
            && window.SocketClient.on(eventName, handler)
        ) {
            return true;
        }
        socket.on(eventName, handler);
        return true;
    };

    socket.on('connect', () => {
        socketInitInFlight = false;
        if (window.SocketClient && typeof window.SocketClient.initialize === 'function') {
            window.SocketClient.initialize();
        }
        showRoomPortal();
    });
    socket.on('disconnect', () => {
        socketInitInFlight = false;
        console.warn('WebSocket サーバーから切断されました。');
        alert('サーバーとの接続が切れました。ページをリロードします。');
        location.reload();
    });
    // match_error is handled in tab_visual_battle.js
    registerAppSocketHandler('state_updated', (newState) => {

        battleState = newState;
        rememberLogIdsFromState(newState);

        // ★ Mode Switching Logic
        const mode = newState.mode || 'battle';
        battleDebugLog(`[Main] state_updated received. Mode: ${mode}`);
        const mapViewport = document.getElementById('map-viewport');
        const expViewport = document.getElementById('exploration-viewport');

        if (mode === 'exploration') {
            if (mapViewport) mapViewport.style.display = 'none';
            if (expViewport) expViewport.style.display = 'block';

            // Render Exploration View
            if (window.ExplorationView && typeof window.ExplorationView.render === 'function') {
                // Check if setup is needed
                if (!document.getElementById('exploration-bg')) window.ExplorationView.setup();
                window.ExplorationView.render(newState);
            } else {
                console.warn('window.ExplorationView not found');
            }

            // Render Exploration Dock via action_dock.js hook or direct call
            // We'll trust updateActionDock to handle this via mode check
        } else {
            if (mapViewport) mapViewport.style.display = 'block';
            if (expViewport) expViewport.style.display = 'none';
        }

        // Trigger Dock Update
        if (typeof updateActionDock === 'function') {
            updateActionDock();
        }
    });
    registerAppSocketHandler('new_log', (logData) => {
        // Play SE before log-id dedupe. state_updated/new_log ordering can differ.
        const phaseNow = String(
            (window.BattleStore && window.BattleStore.state && window.BattleStore.state.phase)
            || (battleState && battleState.phase)
            || ''
        );
        const hasResolvePanel = !!document.getElementById('resolve-flow-panel');
        const inResolvePlayback = (
            phaseNow === 'resolve_mass'
            || phaseNow === 'resolve_single'
            || (phaseNow === 'round_end' && hasResolvePanel)
        );
        const logType = String(logData?.type || '').toLowerCase();
        const shouldPlayFromLog = !(inResolvePlayback && logType !== 'chat');
        if (shouldPlayFromLog && window.SoundFx && typeof window.SoundFx.maybePlayForLog === 'function') {
            window.SoundFx.maybePlayForLog(logData);
        }

        const key = getLogDedupeKey(logData);
        if (key) {
            if (receivedLogIds.has(key)) {
                return;
            }
            receivedLogIds.add(key);
        }
        logToBattleLog(logData);
    });
    registerAppSocketHandler('user_info_updated', (data) => {

        currentUsername = data.username;
        currentUserAttribute = data.attribute;
        window.currentUsername = currentUsername;
        window.currentUserAttribute = currentUserAttribute;
        updateHeaderUserInfo();
        if (typeof setupVisualSidebarControls === 'function') {
            try { setupVisualSidebarControls(); } catch (_e) { }
        }
    });
    registerAppSocketHandler('user_list_updated', (userList) => {

        currentRoomUserList = userList;
        if (document.getElementById('user-list-modal-backdrop')) {
            openUserListModal();
        }
    });
}

async function attemptLocalTokenRecovery() {
    let saved = null;
    try {
        saved = JSON.parse(localStorage.getItem(RECOVERY_STORAGE_KEY) || 'null');
    } catch (_e) {
        saved = null;
    }
    if (!saved || !saved.user_id || !saved.recovery_token) return false;

    try {
        const response = await fetch(API_BASE_URL + '/api/recover_from_local_token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(saved)
        });
        const data = await response.json();
        if (!response.ok) {
            clearSavedRecoveryToken();
            return false;
        }
        applySessionUserData(data);
        initializeSocketIO();
        return true;
    } catch (_e) {
        return false;
    }
}

// --- 6. タブ切り替え機能 ---
tabButtons.forEach(button => {
    button.addEventListener('click', () => {
        tabButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        loadTabContent(button.dataset.tab);
    });
});

async function loadTabContent(tabId) {
    let partialHtmlFile = '';

    // HTMLの data-tab 属性と一致させる
    // 旧テキスト戦闘タブ（tab-battlefield / 3_battlefield.html）は計画書32で廃止済み。
    if (tabId === 'visual') {
        partialHtmlFile = '4_visual_battle.html';
        // Flag reset is done AFTER innerHTML is set (see below)
    } else {
        // コンテンツエリアの取得 (main-content に統一)
        const contentArea = document.getElementById('main-content');
        if (contentArea) {
            contentArea.innerHTML = '<h2>このタブは利用できなくなりました。</h2>';
        }
        return;
    }

    try {
        const response = await fetch(partialHtmlFile, { credentials: 'omit' });
        if (!response.ok) throw new Error(`Network response was not ok (${response.status})`);

        const htmlText = await response.text();

        // コンテンツエリアの取得と書き込み
        // (グローバル変数の mainContent があれば使い、なければ取得する)
        const contentArea = (typeof mainContent !== 'undefined')
            ? mainContent
            : document.getElementById('main-content');

        if (contentArea) {
            contentArea.innerHTML = htmlText;
        }

        // === 各タブの初期化処理 ===
        if (tabId === 'visual' || tabId === 'tab-visual') {
            // Reset DOM initialization flag AFTER HTML is loaded (DOM elements are now new)
            window.actionDockInitialized = false;
            // Debug log removed for production

            // ビジュアルバトルタブ: setupVisualBattleTab()を呼び出す
            if (typeof setupVisualBattleTab === 'function') {
                setupVisualBattleTab();
            } else {
                console.error('setupVisualBattleTab is not defined');
            }
        }

    } catch (error) {
        console.error('Error loading tab content:', error);
        const contentArea = document.getElementById('main-content');
        if (contentArea) {
            contentArea.innerHTML = `<p>コンテンツの読み込みに失敗しました: ${error.message}</p>`;
        }
    }
}

// --- 9. 初期ロード ---
async function checkSessionStatus() {
    try {
        const response = await fetchWithSession('/api/get_session_user');
        if (response.ok) {
            const data = await response.json();
            applySessionUserData(data);
            saveRecoveryTokenFromResponse(data);
            // socket初期化(=ロビー遷移)を復旧コードモーダルでブロックしない。
            // 復旧コードは初回発行時のみ返るため、表示は非同期・非ブロッキングで行う。
            initializeSocketIO();
            showRecoveryCodeOnce(data.recovery_code);
        }
    } catch (error) {
        console.error('Failed to check session status:', error.message);
        if (error.message === '認証が必要です。') {
            const recovered = await attemptLocalTokenRecovery();
            if (!recovered) showEntryPortal();
        } else {
            entryPortal.innerHTML = `<h2 style="color: red;">サーバー接続エラー</h2><p>${error.message}</p><p>app.py を起動してください。</p>`;
            entryPortal.style.display = 'block';
        }
    }
}

window.addEventListener('DOMContentLoaded', () => {
    checkSessionStatus();

    if (window.Glossary && typeof window.Glossary.initOnce === 'function') {
        window.Glossary.initOnce();
    }

    // ★ Phase 5: アイテムデータを読み込み
    if (typeof loadItemData === 'function') {
        loadItemData();
    }

    // ★追加: 全スキルデータを読み込み (フィルタリング用)
    fetch('/api/get_skill_data')
        .then(res => res.json())
        .then(data => {
            window.allSkillData = data;
            console.log('[OK] 全スキルデータを読み込みました:', Object.keys(data).length + '件');
        })
        .catch(err => {
            console.error('[ERROR] スキルデータの読み込みに失敗:', err);
            window.allSkillData = {};
        });

    // ★ Phase 6: 輝化スキルデータをグローバルに読み込み
    fetch('/api/get_radiance_data')
        .then(res => res.json())
        .then(data => {
            window.radianceSkillData = data;
            console.log('[OK] 輝化スキルデータを読み込みました:', data);
        })
        .catch(err => {
            console.error('[ERROR] 輝化スキルデータの読み込みに失敗:', err);
            window.radianceSkillData = {};
        });

    // ★ Phase 7: 特殊パッシブデータをグローバルに読み込み
    fetch('/api/get_passive_data')
        .then(res => res.json())
        .then(data => {
            window.allPassiveData = data;
            console.log('[OK] 特殊パッシブデータを読み込みました:', data);
        })
        .catch(err => {
            console.error('[ERROR] 特殊パッシブデータの読み込みに失敗:', err);
            window.allPassiveData = {};
        });

    fetch('/api/get_buff_data')
        .then(res => res.json())
        .then(data => {
            window.buffCatalogData = data;
            console.log('[OK] バフ図鑑データを読み込みました:', data);
        })
        .catch(err => {
            console.error('[ERROR] バフ図鑑データの読み込みに失敗:', err);
            window.buffCatalogData = {};
        });

    const homeBtn = document.getElementById('home-portal-btn');
    if (homeBtn) {
        homeBtn.addEventListener('click', async () => {
            const ok = await showAppConfirm('ルーム一覧に戻りますか？\n（保存していない変更は失われます）', {
                title: 'ルーム一覧へ戻る',
                confirmText: '戻る',
            });
            if (!ok) return;
            if (socket) socket.emit('leave_room', { room: currentRoomName });
            currentRoomName = null;
            showRoomPortal();
        });
    }
    const settingsBtn = document.getElementById('user-settings-btn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => openInRoomSettingsChooser());
    }
    const userListBtn = document.getElementById('user-list-btn');
    if (userListBtn) {
        userListBtn.addEventListener('click', openUserListModal);
    }
});
