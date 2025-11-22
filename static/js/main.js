// (バフの内部名 -> 表示名・説明 の辞書)
const BUFF_DEFINITIONS = {
    // (B-01)
    "攻撃威力+5(1R)": {
        name: "猛攻の輝き",
        description: "このラウンド中、自分の使用する攻撃スキルの威力+5。"
    },
    // (B-02)
    "守備威力+5(1R)": {
        name: "守護の輝き",
        description: "このラウンド中、自分の使用する守備スキルの威力+5。"
    },
    // (Pb-06)
    "挑発中": {
        name: "挑発",
        description: "次のラウンド、全ての相手側キャラの攻撃対象を自分に固定する。"
    },
    // (Pp-06)
    "破裂威力減少無効": {
        name: "破裂威力減少無効",
        description: "このラウンドでこのキャラに誘発する破裂爆発は、破裂の値を消費しない。"
    },
    // (Mp-05)
    "亀裂ラウンドボーナス": {
        name: "亀裂付与ボーナス",
        description: "このラウンドで自分が付与する亀裂の値に+1。"
    },
    // (D-04)
    "再回避ロック": {
        name: "再回避",
        description: "回避に成功したため、行動回数が回復した。このラウンド中、このスキルでしか回避できない。"
    },
    // (E-06)
    "行動不能": {
        name: "行動不能",
        description: "次のラウンド、行動できない。"
    },
    // (E-09)
    "魔法補正UP(1R)": {
        name: "魔法補正アップ",
        description: "次のラウンド、魔法補正+1。"
    },
    "魔法補正DOWN(1R)": {
        name: "魔法補正ダウン",
        description: "次のラウンド、魔法補正-1。"
    }
};

// --- グローバル設定 ---
const API_BASE_URL = 'http://127.0.0.1:5000';
let socket = null;
let battleState = { characters: [], timeline: [], round: 0 };
let currentRoomName = null;
let currentUsername = null;
let currentUserAttribute = null;
let currentRoomUserList = [];

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
        const roomNames = await response.json();
        renderRoomPortal(roomNames);
    } catch (error) {
        console.error('Error fetching room list:', error);
        if (error.message !== '認証が必要です。') {
             roomPortal.innerHTML = `<h2 style="color: red;">エラー</h2><p>${error.message}</p>`;
        }
    }
}

function renderRoomPortal(roomNames) {
    roomPortal.innerHTML = `
        <div class="portal-user-band">
            <span class="portal-welcome-message">
                ようこそ, <strong>${currentUsername}</strong> (${currentUserAttribute}) さん
            </span>
            <button id="portal-user-settings-btn" class="portal-settings-button" title="ユーザー情報変更">
                ⚙️ ユーザー設定
            </button>
        </div>
        <div class="room-portal-header">
            <h2>⚔️ ジェムリアTRPGダイスボット</h2>
            <p>参加するルームを選択するか、新しいルームを作成してください。</p>
        </div>
        <div class="room-controls">
            <input type="text" id="room-search-input" placeholder="ルームを検索...">
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
    const emptyMsg = document.getElementById('room-list-empty');
    const settingsBtn = document.getElementById('portal-user-settings-btn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => openUserSettingsModal(true));
    }

    function populateList(filter = '') {
        roomList.innerHTML = '';
        let count = 0;
        const normalizedFilter = filter.toLowerCase();

        roomNames.forEach(name => {
            if (name.toLowerCase().includes(normalizedFilter)) {
                const li = document.createElement('li');
                li.className = 'room-list-item';
                li.innerHTML = `
                    <span>${name}</span>
                    <div class="room-list-buttons">
                        <button class="room-join-btn" data-room-name="${name}">参加</button>
                        <button class="room-delete-btn" data-room-name="${name}">削除</button>
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
    console.log(`Joining room: ${roomName}`);
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

        // === ▼▼▼ 修正点: デフォルトタブをバトルフィールドに変更 ▼▼▼
        loadTabContent('tab-battlefield');
        tabButtons.forEach(btn => btn.classList.remove('active'));
        const defaultTab = document.querySelector('.tab-button[data-tab="tab-battlefield"]');
        if (defaultTab) {
            defaultTab.classList.add('active');
        }
        // === ▲▲▲ 修正ここまで ▲▲▲ ===

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
        console.log("Socket.IO is already connected.");
        return;
    }
    socket = io(API_BASE_URL, { withCredentials: true });
    socket.on('connect', () => {
        console.log('✅ WebSocket サーバーに接続しました (ID:', socket.id, ')');
        showRoomPortal();
    });
    socket.on('disconnect', () => {
        console.warn('WebSocket サーバーから切断されました。');
        alert('サーバーとの接続が切れました。ページをリロードします。');
        location.reload();
    });
    socket.on('state_updated', (newState) => {
        console.log('Received state update (for my room):', newState);
        battleState = newState;
        // バトルフィールドタブが開いている場合のみ再描画
        if (document.getElementById('battlefield-grid')) {
            renderTokenList();

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
    });
    socket.on('new_log', (logData) => {
        logToBattleLog(logData);
    });
    socket.on('user_info_updated', (data) => {
        console.log('User info updated by server:', data);
        currentUsername = data.username;
        currentUserAttribute = data.attribute;
        updateHeaderUserInfo();
    });
    socket.on('user_list_updated', (userList) => {
        console.log('Received user list update:', userList);
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

    // === ▼▼▼ 修正点: スキル検索タブの参照を削除 ▼▼▼
    if (tabId === 'tab-battlefield') {
        partialHtmlFile = '3_battlefield.html';
    } else {
        // ★ 存在しないタブはエラーではなく、単にコンテンツなしにする (安全のため)
        mainContent.innerHTML = '<h2>このタブは利用できなくなりました。</h2>';
        return;
    }
    // === ▲▲▲ 修正ここまで ▲▲▲ ===

    try {
        const response = await fetch(partialHtmlFile, {credentials: 'omit'});
        if (!response.ok) throw new Error(`Network response was not ok (${response.status})`);
        mainContent.innerHTML = await response.text();

        // 各タブの初期化処理
        if (tabId === 'tab-battlefield') {
            setupBattlefieldTab();
            renderTokenList();
            renderTimeline();
        }
    } catch (error) {
        console.error('Error loading tab content:', error);
        mainContent.innerHTML = `<p>コンテンツの読み込みに失敗しました: ${error.message}</p>`;
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
            console.log('Found active session:', currentUsername);
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

    const homeBtn = document.getElementById('home-portal-btn');
    if (homeBtn) {
        homeBtn.addEventListener('click', () => {
            if (confirm('ルーム一覧に戻りますか？\n（保存していない変更は失われます）')) {
                if(socket) socket.emit('leave_room', {room: currentRoomName});
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