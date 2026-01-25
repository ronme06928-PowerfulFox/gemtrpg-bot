import { MobileActions } from './actions.js';

export const MobileUI = {
    init() {
        console.log("🎨 MobileUI Module Initialized");
        this.setupToggles();
        this.setupChat();
        this.patchActionDock();

        // Initialize Actions Module
        if (MobileActions && typeof MobileActions.init === 'function') {
            MobileActions.init();
        }
    },

    setupChat() {
        const input = document.getElementById('visual-chat-input');
        const sendBtn = document.getElementById('visual-chat-send');

        const sendMessage = () => {
            const msg = input.value.trim();
            if (!msg) return;

            // Check if socket is available
            if (window.socket) {
                // Correct Event: request_chat
                // Params: room, user, message, secret
                window.socket.emit('request_chat', {
                    room: window.currentRoomName,
                    user: window.currentUsername, // Required by server
                    message: msg,
                    secret: false // Default to public
                });
                input.value = '';
            } else {
                console.error("Socket not connected");
                alert("サーバーに接続されていません");
            }
        };

        if (sendBtn) {
            sendBtn.onclick = sendMessage;
        }

        if (input) {
            input.onkeydown = (e) => {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            };
        }
    },

    setupToggles() {
        // Log Toggle
        const logBtn = document.getElementById('mobile-log-toggle');
        const logOverlay = document.getElementById('mobile-log-overlay');
        const closeOverlayBtn = logOverlay ? logOverlay.querySelector('.close-overlay') : null;

        if (logBtn && logOverlay) {
            logBtn.onclick = () => {
                logOverlay.classList.remove('hidden');
                // Scroll to bottom
                const logArea = document.getElementById('visual-log-area');
                if (logArea) {
                    setTimeout(() => {
                        logArea.scrollTop = logArea.scrollHeight;
                    }, 50);
                }
            };
        }

        if (closeOverlayBtn && logOverlay) {
            closeOverlayBtn.onclick = () => {
                logOverlay.classList.add('hidden');
            };
        }

        // Menu Toggle
        const menuBtn = document.getElementById('mobile-menu-toggle');
        if (menuBtn) {
            menuBtn.onclick = () => {
                if (confirm("ルーム選択に戻りますか？")) {
                    location.reload();
                }
            };
        }
    },

    // ... setupToggles (skipped in replacement below if targeting carefully) ...

    patchActionDock() {
        // Override global initializeActionDock to target mobile dock
        window.initializeActionDock = () => {
            console.log("📱 Mobile Action Dock Initializing...");
            const dock = document.getElementById('mobile-action-dock');
            if (!dock) return;
            dock.innerHTML = ''; // Clear

            const isGM = (window.currentUserAttribute === 'GM');

            // Define Actions
            const actions = [];

            // 1. Dice Log (Always)
            actions.push({
                id: 'dice', icon: '🎲', label: 'Log',
                action: () => document.getElementById('mobile-log-toggle').click()
            });

            // 2. Immediate Skills (If any owned char has one)
            // But checking hasImmediateSkill implies iteration. MobileActions handles this check inside modal open?
            // Or visual cue? PC shows disabled state.
            // Simplified: Always show button, alert if empty inside.
            actions.push({
                id: 'immediate', icon: '⚡', label: 'Quick',
                action: () => MobileActions.openImmediateModal()
            });

            // 3. Match Toggle (If match active)
            if (window.battleState && window.battleState.active_match && window.battleState.active_match.is_active) {
                actions.push({
                    id: 'match-toggle', icon: '⚔️', label: 'Match',
                    action: () => MobileActions.toggleMatchModal()
                });
            }

            // 4. Items
            actions.push({
                id: 'items', icon: '🎒', label: 'Item',
                action: () => MobileActions.openItemModal()
            });

            // 5. Add Character
            actions.push({
                id: 'add-char', icon: '➕', label: 'Add',
                action: () => MobileActions.openLoadCharacterModal()
            });

            // 6. Unplaced (Staging) - Show count?
            const unplacedCount = (window.battleState && window.battleState.characters)
                ? window.battleState.characters.filter(c => c.x < 0).length
                : 0;

            if (unplacedCount > 0 || isGM) {
                actions.push({
                    id: 'staging', icon: '📦', label: 'Box',
                    action: () => MobileActions.openStagingModal()
                });
            }

            // GM Actions
            if (isGM) {
                actions.push({
                    id: 'start-round', icon: '▶️', label: 'Start R', action: () => {
                        if (confirm("Start New Round?")) window.socket.emit('request_new_round', { room: window.currentRoomName });
                    }
                });
                actions.push({
                    id: 'end-round', icon: '🏁', label: 'End R', action: () => {
                        if (confirm("End Round?")) window.socket.emit('request_end_round', { room: window.currentRoomName });
                    }
                });
                actions.push({
                    id: 'reset', icon: '🔄', label: 'Reset', action: () => {
                        if (confirm("Reset Battle? (Full)")) {
                            window.socket.emit('request_reset_battle', { room: window.currentRoomName, mode: 'full' });
                        }
                    }
                });
            }

            actions.forEach(act => {
                const btn = document.createElement('div');
                btn.className = 'dock-icon';
                btn.innerHTML = `${act.icon}`; // Icon only for now to fit
                // Optional: Label tooltip or small text?
                btn.onclick = act.action;

                if (act.id === 'match-toggle') btn.classList.add('active'); // Highlight match

                dock.appendChild(btn);
            });
        };
    }, // Added comma here

    appendLog(log) {
        const logArea = document.getElementById('visual-log-area');
        if (!logArea) return;

        // Remove "No Logs" message if it exists
        const emptyMsg = logArea.querySelector('.empty-msg');
        if (emptyMsg) emptyMsg.remove();

        const line = document.createElement('div');
        line.className = `log-line ${log.type || ''}`;

        // Handle secret
        if (log.secret) {
            line.style.borderLeft = '3px solid #663399'; // Visual cue
            const isSender = (log.user === window.currentUsername);
            const isGM = (window.currentUserAttribute === 'GM');
            if (isGM || isSender) {
                line.innerHTML = `<span style="color:var(--accent-color)">[SECRET]</span> <span class="chat-user">${log.user}:</span> ${log.message}`;
            } else {
                line.innerHTML = `<span style="color:#888; font-style:italic;">(Secret Dice)</span>`;
            }
        } else {
            if (log.type === 'chat') {
                line.innerHTML = `<span class="chat-user">${log.user}:</span> <span class="chat-message">${log.message}</span>`;
            } else {
                line.innerHTML = log.message;
            }
        }
        logArea.appendChild(line);

        // Auto-scroll logic
        requestAnimationFrame(() => {
            logArea.scrollTop = logArea.scrollHeight;
        });
    },

    renderLogs(logs) {
        const logArea = document.getElementById('visual-log-area');
        if (!logArea) return;

        logArea.innerHTML = '';
        if (!logs || !logs.length) {
            logArea.innerHTML = '<div class="empty-msg" style="color:#888; text-align:center; padding:10px;">No Logs</div>';
            return;
        }

        logs.forEach(log => {
            this.appendLog(log);
        });
    }
};
