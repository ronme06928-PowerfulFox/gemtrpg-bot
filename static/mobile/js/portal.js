/**
 * portal.js
 * Handles Login and Room Selection for Mobile View
 */

export const Portal = {
    mobileEntryPortal: null,
    mobileRoomPortal: null,
    mobileMapContainer: null,

    init() {
        console.log("🚪 Portal Module Initialized");
        this.mobileEntryPortal = document.getElementById('mobile-entry-portal');
        this.mobileRoomPortal = document.getElementById('mobile-room-portal');
        this.mobileMapContainer = document.getElementById('mobile-map-container');

        this.setupPortalEvents();
    },

    async checkSession() {
        try {
            const response = await fetch('/api/get_session_user');
            if (response.ok) {
                const data = await response.json();
                if (data.username) {
                    window.currentUsername = data.username;
                    window.currentUserAttribute = data.attribute;
                    return true;
                }
            }
            this.showScreen('entry');
            return false;
        } catch (e) {
            console.error("Session check failed", e);
            this.showScreen('entry');
            return false;
        }
    },

    showScreen(screenName) {
        this.mobileEntryPortal.classList.add('hidden');
        this.mobileRoomPortal.classList.add('hidden');
        this.mobileMapContainer.classList.add('hidden');

        if (screenName === 'entry') {
            this.mobileEntryPortal.classList.remove('hidden');
        } else if (screenName === 'room') {
            this.mobileRoomPortal.classList.remove('hidden');
        } else if (screenName === 'map') {
            this.mobileMapContainer.classList.remove('hidden');
            // Trigger visual battle init if available
            if (typeof window.setupVisualBattleTab === 'function') {
                window.setupVisualBattleTab();
            }
            if (window.initializeActionDock) {
                window.initializeActionDock(); // Patched version
            }
        }
    },

    setupPortalEvents() {
        // Entry
        const entryBtn = document.getElementById('entry-btn');
        if (entryBtn) {
            entryBtn.addEventListener('click', async () => {
                const username = document.getElementById('entry-username').value;
                const attribute = document.getElementById('entry-attribute').value;
                if (!username) return alert("名前を入力してください");

                try {
                    const res = await fetch('/api/entry', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, attribute })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        window.currentUsername = data.username;
                        window.currentUserAttribute = data.attribute;
                        window.initializeMobileSocket(); // Defined in main.js or socket manager
                    } else {
                        alert("ログインに失敗しました");
                    }
                } catch (e) { console.error(e); }
            });
        }

        // Room Refresh
        const refreshBtn = document.getElementById('mobile-refresh-rooms-btn');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.fetchRoomList());

        // Create Room
        const createBtn = document.getElementById('mobile-create-room-btn');
        if (createBtn) {
            createBtn.addEventListener('click', async () => {
                const name = prompt("新規ルーム名:");
                if (!name) return;
                try {
                    const res = await fetch('/create_room', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ room_name: name })
                    });
                    if (res.ok) {
                        this.joinRoom(name);
                    } else {
                        alert("作成に失敗しました (重複など)");
                    }
                } catch (e) { console.error(e); }
            });
        }

        // Logout
        const logoutBtn = document.getElementById('mobile-logout-btn');
        if (logoutBtn) {
            logoutBtn.onclick = () => location.reload();
        }

        // Profile Settings
        const settingsBtn = document.getElementById('mobile-settings-btn');
        if (settingsBtn) {
            settingsBtn.onclick = () => {
                document.getElementById('mobile-profile-modal').classList.remove('hidden');
                document.getElementById('profile-username').value = window.currentUsername || '';
                document.getElementById('profile-attribute').value = window.currentUserAttribute || 'PL';
            };
        }

        const saveProfileBtn = document.getElementById('profile-save-btn');
        if (saveProfileBtn) {
            saveProfileBtn.onclick = async () => {
                const newName = document.getElementById('profile-username').value;
                const newAttr = document.getElementById('profile-attribute').value;
                if (!newName) return alert("名前を入力してください");

                try {
                    // Update session via existing /api/entry (it updates session if called)
                    // Or implement specific update if needed. Usually entry overwrites session.
                    const res = await fetch('/api/entry', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username: newName, attribute: newAttr })
                    });

                    if (res.ok) {
                        const data = await res.json();
                        window.currentUsername = data.username;
                        window.currentUserAttribute = data.attribute;

                        // Update UI
                        const display = document.getElementById('mobile-user-display');
                        if (display) display.textContent = `${data.username} (${data.attribute})`;

                        // Update socket if connected
                        if (window.socket && window.currentRoomName) {
                            window.socket.emit('join_room', {
                                room: window.currentRoomName,
                                username: data.username,
                                attribute: data.attribute
                            });
                        }

                        document.getElementById('mobile-profile-modal').classList.add('hidden');
                        alert("プロフィールを更新しました");
                    } else {
                        alert("更新に失敗しました");
                    }
                } catch (e) { console.error(e); alert("エラーが発生しました"); }
            };
        }
    },

    async fetchRoomList() {
        try {
            const res = await fetch('/list_rooms');
            if (res.ok) {
                const data = await res.json();
                const list = document.getElementById('mobile-room-list');
                list.innerHTML = '';
                const display = document.getElementById('mobile-user-display');
                if (display) display.textContent = `${window.currentUsername} (${window.currentUserAttribute})`;

                if (data.rooms.length === 0) {
                    list.innerHTML = '<li style="padding:15px; color:#aaa;">ルームが見つかりません</li>';
                }

                data.rooms.forEach(room => {
                    const li = document.createElement('li');
                    li.className = 'mobile-list-item';
                    li.innerHTML = `
                        <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                            <span class="room-name" style="font-weight:bold; font-size:16px;">${room.name}</span>
                            <button class="join-btn mobile-btn small accent">参加</button>
                        </div>
                    `;
                    li.querySelector('.join-btn').onclick = () => this.joinRoom(room.name);
                    list.appendChild(li);
                });
            }
        } catch (e) { console.error(e); }
    },

    async joinRoom(roomName) {
        try {
            const res = await fetch(`/load_room?name=${encodeURIComponent(roomName)}`);
            if (res.ok) {
                window.battleState = await res.json();
                window.currentRoomName = roomName;

                if (window.socket) {
                    window.socket.emit('join_room', {
                        room: window.currentRoomName,
                        username: window.currentUsername,
                        attribute: window.currentUserAttribute
                    });
                }

                const roomLabel = document.getElementById('current-room-name');
                if (roomLabel) roomLabel.textContent = roomName;

                this.showScreen('map');
            }
        } catch (e) { alert("入室エラー"); }
    }
};
