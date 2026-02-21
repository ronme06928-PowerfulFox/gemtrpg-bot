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
let currentUserId = null; // ★追加: ユーザーID (UUID)

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
function showEntryPortal() {
    roomPortal.style.display = 'none';
    mainAppContainer.style.display = 'none';
    entryPortal.style.display = 'block';

    const entryBtn = document.getElementById('entry-btn');
    const entryMsg = document.getElementById('entry-message');

    if (!entryBtn.dataset.listenerAttached) {
        entryBtn.dataset.listenerAttached = 'true';
        entryBtn.addEventListener('click', async () => {
            const username = document.getElementById('entry-username').value.trim();
            const attribute = document.getElementById('entry-attribute').value;
            if (!username) {
                entryMsg.textContent = '「あなたの名前」を入力してください。';
                entryMsg.className = 'auth-message error';
                return;
            }
            try {
                const response = await fetchWithSession('/api/entry', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, attribute })
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || '入室に失敗しました');

                currentUsername = data.username;
                currentUserAttribute = data.attribute;
                currentUserId = data.user_id; // ★追加: IDを保存
                initializeSocketIO();
            } catch (error) {
                entryMsg.textContent = error.message;
                entryMsg.className = 'auth-message error';
            }
        });
    }
}

async function showRoomPortal() {
    entryPortal.style.display = 'none';
    mainAppContainer.style.display = 'none';
    roomPortal.style.display = 'block';
    roomPortal.innerHTML = '<h2>ルーム一覧を読み込み中...</h2>';

    try {
        const response = await fetchWithSession('/list_rooms');
        if (!response.ok) throw new Error('サーバーからルーム一覧を取得できませんでした。');
        const data = await response.json();
        // data: { rooms: [{name, owner_id}, ...], current_user_id, is_gm }
        renderRoomPortal(data.rooms, data.current_user_id, data.is_gm);
    } catch (error) {
        console.error('Error fetching room list:', error);
        if (error.message !== '認証が必要です。') {
            roomPortal.innerHTML = `<h2 style="color: red;">エラー</h2><p>${error.message}</p>`;
        }
    }
}

function renderRoomPortal(rooms, currentUserId, isGm) {
    // ★追加: GMの場合のみボタンを表示
    const gmButton = (currentUserAttribute === 'GM')
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
                ${gmButton}
            </div>
        </div>
        <div class="room-portal-header">
            <h2>⚔️ ジェムリアTRPGダイスボット</h2>
            <p>参加するルームを選択するか、新しいルームを作成してください。</p>
        </div>
        <div class="room-controls">
            <input type="text" id="room-search-input" placeholder="ルームを検索...">
            <button id="refresh-room-list-btn" title="ルーム一覧を更新" style="background-color: #007bff; color: white;">更新</button>
            <button id="create-room-btn">＋ 新規ルーム作成</button>
        </div>
        <div id="room-list-container">
            <h3>既存のルーム</h3>
            <ul id="room-list" class="room-list"></ul>
            <p id="room-list-empty" style="display: none;">該当するルームはありません。</p>
        </div>
    `;

    const roomList = document.getElementById('room-list');
    const searchInput = document.getElementById('room-search-input');
    const createBtn = document.getElementById('create-room-btn');
    const refreshBtn = document.getElementById('refresh-room-list-btn');
    const emptyMsg = document.getElementById('room-list-empty');
    const settingsBtn = document.getElementById('portal-user-settings-btn');

    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => openUserSettingsModal(true));
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

    function populateList(filter = '') {
        roomList.innerHTML = '';
        let count = 0;
        const normalizedFilter = filter.toLowerCase();

        rooms.forEach(roomInfo => {
            const name = roomInfo.name;
            const ownerId = roomInfo.owner_id;
            if (name.toLowerCase().includes(normalizedFilter)) {
                const li = document.createElement('li');
                li.className = 'room-list-item';

                // 削除ボタン: オーナーまたはGMのみ表示
                const canDelete = (ownerId === currentUserId) || isGm;
                const deleteBtn = canDelete
                    ? `<button class="room-delete-btn" data-room-name="${name}">削除</button>`
                    : '';

                li.innerHTML = `
                    <span>${name}</span>
                    <div class="room-list-buttons">
                        <button class="room-join-btn" data-room-name="${name}">参加</button>
                        ${deleteBtn}
                    </div>
                `;
                roomList.appendChild(li);
                count++;
            }
        });
        emptyMsg.style.display = (count === 0) ? 'block' : 'none';
    }
    populateList('');

    searchInput.addEventListener('input', (e) => populateList(e.target.value));
    createBtn.addEventListener('click', createNewRoom);
    roomList.addEventListener('click', (e) => {
        const target = e.target;
        const roomName = target.dataset.roomName;
        if (target.classList.contains('room-join-btn')) {
            joinRoom(roomName);
        }
        if (target.classList.contains('room-delete-btn')) {
            deleteRoom(roomName);
        }
    });
}

async function createNewRoom() {
    const roomName = prompt('作成する新しいルーム名を入力してください:');
    if (!roomName || roomName.trim() === '') {
        alert('ルーム名が入力されていません。');
        return;
    }
    try {
        const response = await fetchWithSession('/create_room', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room_name: roomName })
        });
        const result = await response.json();
        if (response.status === 201) {
            joinRoom(roomName, result.state);
        } else if (response.status === 409) {
            alert(`エラー: ルーム名「${roomName}」は既に使用されています。`);
        } else {
            throw new Error(result.error || '登録に失敗しました');
        }
    } catch (error) {
        console.error('Error creating room:', error);
        alert(`ルームの作成に失敗しました: ${error.message}`);
    }
}

async function deleteRoom(roomName) {
    if (!confirm(`本当にルーム「${roomName}」を削除しますか？\nこの操作は取り消せません。`)) {
        return;
    }
    try {
        const response = await fetchWithSession('/delete_room', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ room_name: roomName })
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

async function joinRoom(roomName, initialState = null) {
    // Reset DOM initialization flag so dock re-initializes on room change
    // NOTE: Do NOT reset visualBattleSocketHandlersRegistered - socket handlers must only be registered once
    window.actionDockInitialized = false;
    // Debug log removed for production

    try {
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
            attribute: currentUserAttribute
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
    if (socket && socket.connected) {

        return;
    }
    socket = io(API_BASE_URL, { withCredentials: true });
    window.socket = socket; // ★追加: グローバルに公開（SocketClient用）

    socket.on('connect', () => {
        // ★追加: SocketClient の初期化（Phase 2 モジュール）
        if (window.SocketClient && typeof window.SocketClient.initialize === 'function') {
            window.SocketClient.initialize();
        }
        showRoomPortal();
    });
    socket.on('disconnect', () => {
        console.warn('WebSocket サーバーから切断されました。');
        alert('サーバーとの接続が切れました。ページをリロードします。');
        location.reload();
    });
    // match_error is handled in tab_visual_battle.js
    socket.on('state_updated', (newState) => {

        battleState = newState;

        // ★ Mode Switching Logic
        const mode = newState.mode || 'battle';
        console.log(`[Main] state_updated received. Mode: ${mode}`); // ★ ADDED DEBUG LOG
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

        // バトルフィールドタブが開いている場合のみ再描画
        if (document.getElementById('battlefield-grid')) {
            renderTokenList();

            // Battle Mode Only Logic
            if (mode === 'battle') {
                // === ▼▼▼ 修正点 (フェーズ4c) ▼▼▼ ===
                // (ドロップダウンのキャラクターリストを更新するために、この呼び出しは必須)
                // (★ window.xxx を使って、グローバル関数を安全に参照する)
                if (window.setupActionColumn) {
                    window.attackerCol = setupActionColumn('attacker');
                    window.defenderCol = setupActionColumn('defender');
                }
                // === ▲▲▲ 修正ここまで ▲▲▲ ===

                renderTimeline();
            }
        }

        // Trigger Dock Update
        if (typeof updateActionDock === 'function') {
            updateActionDock();
        }
    });
    socket.on('new_log', (logData) => {
        logToBattleLog(logData);
    });
    socket.on('user_info_updated', (data) => {

        currentUsername = data.username;
        currentUserAttribute = data.attribute;
        updateHeaderUserInfo();
    });
    socket.on('user_list_updated', (userList) => {

        currentRoomUserList = userList;
        if (document.getElementById('user-list-modal-backdrop')) {
            openUserListModal();
        }
    });
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
    if (tabId === 'tab-battlefield') {
        partialHtmlFile = '3_battlefield.html';
    } else if (tabId === 'visual') {
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
        if (tabId === 'tab-battlefield') {
            setupBattlefieldTab();
            renderTokenList();
            renderTimeline();
        } else if (tabId === 'visual' || tabId === 'tab-visual') {
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
            currentUsername = data.username;
            currentUserAttribute = data.attribute;
            currentUserId = data.user_id; // ★追加: IDを保存

            initializeSocketIO();
        }
    } catch (error) {
        console.error('Failed to check session status:', error.message);
        if (error.message !== '認証が必要です。') {
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

    const homeBtn = document.getElementById('home-portal-btn');
    if (homeBtn) {
        homeBtn.addEventListener('click', () => {
            if (confirm('ルーム一覧に戻りますか？\n（保存していない変更は失われます）')) {
                if (socket) socket.emit('leave_room', { room: currentRoomName });
                currentRoomName = null;
                showRoomPortal();
            }
        });
    }
    const settingsBtn = document.getElementById('user-settings-btn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => openUserSettingsModal(false));
    }
    const userListBtn = document.getElementById('user-list-btn');
    if (userListBtn) {
        userListBtn.addEventListener('click', openUserListModal);
    }
});
