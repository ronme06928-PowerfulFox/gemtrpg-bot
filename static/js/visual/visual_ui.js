/* static/js/visual/visual_ui.js */

// --- Log Rendering ---

window.appendVisualLogLine = function (container, logData, filterType) {
    const isChat = logData.type === 'chat';
    if (filterType === 'chat' && !isChat) return;
    if (filterType === 'system' && isChat) return;

    const logLine = document.createElement('div');
    let className = `log-line ${logData.type}`;
    let displayMessage = logData.message;

    if (logData.secret) {
        className += ' secret-log';
        const isSender = (typeof currentUsername !== 'undefined' && logData.user === currentUsername);
        const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
        if (isGM || isSender) displayMessage = `<span class="secret-mark">[SECRET]</span> ${logData.message}`;
        else displayMessage = `<span class="secret-masked">（シークレットダイス）</span>`;
    }

    logLine.className = className;
    if (logData.type === 'chat' && !logData.secret) {
        logLine.innerHTML = `<span class="chat-user">${logData.user}:</span> <span class="chat-message">${logData.message}</span>`;
    } else {
        logLine.innerHTML = displayMessage;
    }
    logLine.style.borderBottom = "1px dotted #eee";
    logLine.style.padding = "2px 5px";
    logLine.style.fontSize = "0.9em";
    container.appendChild(logLine);

    while (container.children.length > VISUAL_MAX_LOG_ITEMS) {
        container.removeChild(container.firstElementChild);
    }
}

window.renderVisualLogHistory = function (logs) {
    const logArea = document.getElementById('visual-log-area');
    if (!logArea) return;
    logArea.innerHTML = '';
    if (!logs || logs.length === 0) {
        logArea.innerHTML = '<div style="padding:10px; color:#999;">ログはありません</div>';
        return;
    }
    const filter = window.currentVisualLogFilter || 'all';
    logs.forEach(log => appendVisualLogLine(logArea, log, filter));
    logArea.scrollTop = logArea.scrollHeight;
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 30);
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 80);
}

// --- Round Display ---

window.updateVisualRoundDisplay = function (round) {
    const el = document.getElementById('visual-round-counter');
    if (el) el.textContent = round || 0;
}

// --- Sidebar Controls ---

window.setupVisualSidebarControls = function () {
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');

    if (currentUserAttribute === 'GM') {
        if (startRBtn) {
            startRBtn.style.display = 'inline-block';
            startRBtn.onclick = () => {
                if (confirm("次ラウンドを開始しますか？")) socket.emit('request_new_round', { room: currentRoomName });
            };
        }
        if (endRBtn) {
            endRBtn.style.display = 'inline-block';
            endRBtn.onclick = () => {
                if (confirm("ラウンドを終了しますか？")) socket.emit('request_end_round', { room: currentRoomName });
            };
        }
    }

    const chatInput = document.getElementById('visual-chat-input');
    const chatSend = document.getElementById('visual-chat-send');
    const diceCommandRegex = /^((\/sroll|\/sr|\/roll|\/r)\s+)?((\d+)?d\d+([\+\-]\d+)?(\s*[\+\-]\s*(\d+)?d\d+([\+\-]\d+)?)*)/i;

    const sendChat = () => {
        let msg = chatInput.value.trim();
        if (!msg) return;
        let isSecret = false;
        if (/^(\/sroll|\/sr)(\s+|$)/i.test(msg)) isSecret = true;

        if (diceCommandRegex.test(msg)) {
            const result = rollDiceCommand(msg);
            const cleanCmd = msg.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');
            const resultHtml = `${cleanCmd} = ${result.details} = <span class="dice-result-total">${result.total}</span>`;
            socket.emit('request_log', {
                room: currentRoomName,
                message: `[${currentUsername}] ${resultHtml}`,
                type: 'dice',
                secret: isSecret,
                user: currentUsername
            });
        } else {
            msg = msg.replace(/^(\/roll|\/r)(\s+|$)/i, '');
            if (isSecret) msg = msg.replace(/^(\/sroll|\/sr)(\s+|$)/i, '');
            if (!msg && isSecret) { alert("シークレットメッセージの内容を入力してください。"); return; }
            if (msg) {
                socket.emit('request_chat', {
                    room: currentRoomName, user: currentUsername, message: msg, secret: isSecret
                });
            }
        }
        chatInput.value = '';
    };

    if (chatSend) chatSend.onclick = sendChat;
    if (chatInput) {
        chatInput.onkeydown = (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); }
        };
    }

    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        btn.onclick = () => {
            filters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.currentVisualLogFilter = btn.dataset.filter;
            if (battleState && battleState.logs) renderVisualLogHistory(battleState.logs);
        };
    });

    const vHistoryBtn = document.getElementById('visual-show-history-btn');
    if (vHistoryBtn) {
        vHistoryBtn.onclick = () => {
            if (typeof openVisualLogHistoryModal === 'function') {
                openVisualLogHistoryModal();
            } else {
                console.warn('openVisualLogHistoryModal not defined');
            }
        };
    }

    const saveBtn = document.getElementById('visual-save-btn');
    const presetBtn = document.getElementById('visual-preset-btn');
    const resetBtn = document.getElementById('visual-reset-btn');
    const statusMsg = document.getElementById('visual-status-msg');

    if (currentUserAttribute === 'GM') {
        if (saveBtn) {
            saveBtn.style.display = 'inline-block';
            saveBtn.onclick = async () => {
                statusMsg.textContent = "保存中...";
                try {
                    await fetchWithSession('/save_room', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ room_name: currentRoomName, state: battleState })
                    });
                    statusMsg.textContent = "保存完了";
                    setTimeout(() => statusMsg.textContent = "", 2000);
                } catch (e) { statusMsg.textContent = "保存失敗"; }
            };
        }
        if (presetBtn) {
            presetBtn.style.display = 'inline-block';
            presetBtn.onclick = () => { if (typeof openPresetManagerModal === 'function') openPresetManagerModal(); };
        }
        if (resetBtn) {
            resetBtn.style.display = 'inline-block';
            resetBtn.onclick = () => {
                if (typeof openResetTypeModal === 'function') {
                    openResetTypeModal((type, options) => { socket.emit('request_reset_battle', { room: currentRoomName, mode: type, options: options }); });
                } else if (confirm("戦闘をリセットしますか？")) {
                    socket.emit('request_reset_battle', { room: currentRoomName, mode: 'full' });
                }
            };
        }
    } else {
        if (saveBtn) saveBtn.style.display = 'none';
        if (presetBtn) presetBtn.style.display = 'none';
        if (resetBtn) resetBtn.style.display = 'none';
    }
}

// --- Timeline Controls ---

window.initializeTimelineToggle = function () {
    const timelineArea = document.getElementById('visual-timeline-area');
    const header = timelineArea ? timelineArea.querySelector('.sidebar-header') : null;

    if (!header) return;

    const isCollapsed = localStorage.getItem('visual-timeline-collapsed') === 'true';
    if (isCollapsed) {
        timelineArea.classList.add('collapsed');
    }

    header.addEventListener('click', () => {
        const nowCollapsed = timelineArea.classList.toggle('collapsed');
        localStorage.setItem('visual-timeline-collapsed', nowCollapsed);
    });
}


/**
 * Legacy Timeline Renderer (Use Timeline.js component usually)
 */
window.renderVisualTimeline = function () {
    const timelineEl = document.getElementById('visual-timeline-list');
    if (!timelineEl) return;
    timelineEl.innerHTML = '';
    if (!battleState.timeline || battleState.timeline.length === 0) {
        timelineEl.innerHTML = '<div style="color:#888; padding:5px;">No Data</div>';
        return;
    }
    const currentTurnId = battleState.turn_char_id;
    battleState.timeline.forEach(charId => {
        const char = battleState.characters.find(c => c.id === charId);
        if (!char) return;
        const item = document.createElement('div');
        item.className = `timeline-item ${char.type || 'NPC'}`;
        item.style.cssText = "display:flex; justify-content:space-between; padding:6px 8px; border-bottom:1px solid #eee; cursor:pointer; background:#fff;";
        const typeColor = (char.type === 'ally') ? '#007bff' : '#dc3545';
        item.style.borderLeft = `3px solid ${typeColor}`;
        if (char.id === currentTurnId) {
            item.style.background = "#fff8e1";
            item.style.fontWeight = "bold";
            item.style.borderLeft = `6px solid ${typeColor}`;
            item.style.borderTop = "1px solid #ff9800";
            item.style.borderBottom = "1px solid #ff9800";
            item.style.borderRight = "1px solid #ff9800";
        }
        if (char.hasActed) {
            item.style.opacity = "0.5";
            item.style.textDecoration = "line-through";
        }
        if (char.hp <= 0) {
            item.style.opacity = "0.3";
            item.style.background = "#ccc";
        }
        item.innerHTML = `
            <span class="name">${char.name}</span>
            <span class="speed" style="font-size:0.85em; color:#666;">SPD:${char.totalSpeed || char.speedRoll || 0}</span>
        `;
        // Use Global Helper for Detail
        item.addEventListener('click', () => {
            if (typeof showCharacterDetail === 'function') showCharacterDetail(char.id)
        });
        timelineEl.appendChild(item);
    });
}

console.log('[visual_ui] Loaded.');
