/* static/js/tab_visual_battle.js */

// --- グローバル変数 ---
let visualScale = 1.0;
let visualOffsetX = 0;
let visualOffsetY = 0;
const GRID_SIZE = 96;
// テキストフィールド同様、デフォルトはall
window.currentVisualLogFilter = 'all';

// マウスイベントハンドラ管理
window.visualMapHandlers = window.visualMapHandlers || { move: null, up: null };

// --- 計算・ダイス関数 ---
function safeMathEvaluate(expression) {
    try {
        const sanitized = expression.replace(/[^-()\d/*+.]/g, '');
        return new Function('return ' + sanitized)();
    } catch (e) { console.error("Safe math eval error:", e); return 0; }
}

function rollDiceCommand(command) {
    let calculation = command.replace(/【.*?】/g, '').trim();
    calculation = calculation.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');

    let details = calculation;
    const diceRegex = /(\d+)d(\d+)/g;
    let match;
    const allDiceDetails = [];

    while ((match = diceRegex.exec(calculation)) !== null) {
        const numDice = parseInt(match[1]);
        const numFaces = parseInt(match[2]);
        let sum = 0;
        const rolls = [];
        for (let i = 0; i < numDice; i++) {
            const roll = Math.floor(Math.random() * numFaces) + 1;
            rolls.push(roll);
            sum += roll;
        }
        allDiceDetails.push({ original: match[0], details: `(${rolls.join('+')})`, sum: sum });
    }

    for (let i = allDiceDetails.length - 1; i >= 0; i--) {
        const roll = allDiceDetails[i];
        details = details.replace(roll.original, roll.details);
        calculation = calculation.replace(roll.original, String(roll.sum));
    }

    const total = safeMathEvaluate(calculation);
    return { total: total, details: details };
}

// 状態異常定義
const STATUS_CONFIG = {
    '出血': { icon: 'bleed.png', color: '#dc3545', borderColor: '#ff0000' },
    '破裂': { icon: 'rupture.png', color: '#28a745', borderColor: '#00ff00' },
    '亀裂': { icon: 'fissure.png', color: '#007bff', borderColor: '#0000ff' },
    '戦慄': { icon: 'fear.png', color: '#17a2b8', borderColor: '#00ffff' },
    '荊棘': { icon: 'thorns.png', color: '#155724', borderColor: '#0f0' }
};

let duelState = {
    attackerId: null, defenderId: null,
    attackerLocked: false, defenderLocked: false,
    isOneSided: false,
    attackerCommand: null, defenderCommand: null
};

// --- ★ログ描画用ヘルパー関数 (テキストフィールドの実装を移植) ---
function appendVisualLogLine(container, logData, filterType) {
    const isChat = logData.type === 'chat';

    // フィルタリング
    if (filterType === 'chat' && !isChat) return;
    if (filterType === 'system' && isChat) return;

    const logLine = document.createElement('div');
    let className = `log-line ${logData.type}`;

    // シークレットダイスの処理
    let displayMessage = logData.message;
    if (logData.secret) {
        className += ' secret-log';
        const isSender = (typeof currentUsername !== 'undefined' && logData.user === currentUsername);
        const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

        if (isGM || isSender) {
            displayMessage = `<span class="secret-mark">[SECRET]</span> ${logData.message}`;
        } else {
            displayMessage = `<span class="secret-masked">（シークレットダイスが振られました）</span>`;
        }
    }

    logLine.className = className;

    // チャットの場合の装飾
    if (logData.type === 'chat' && !logData.secret) {
         logLine.innerHTML = `<span class="chat-user">${logData.user}:</span> <span class="chat-message">${logData.message}</span>`;
    } else {
        logLine.innerHTML = displayMessage;
    }

    // スタイル適用
    logLine.style.borderBottom = "1px dotted #eee";
    logLine.style.padding = "2px 5px";
    logLine.style.fontSize = "0.9em";

    container.appendChild(logLine);
}

// --- ★ログ一括描画関数 ---
// --- 修正: ログ一括描画関数 ---
function renderVisualLogHistory(logs) {
    const logArea = document.getElementById('visual-log-area');
    if (!logArea) return;

    // ログエリアをクリア
    logArea.innerHTML = '';

    if (!logs || logs.length === 0) {
        logArea.innerHTML = '<div style="padding:10px; color:#999;">ログはありません</div>';
        return;
    }

    // 現在のフィルタ設定を使用
    const filter = window.currentVisualLogFilter || 'all';

    logs.forEach(log => {
        appendVisualLogLine(logArea, log, filter);
    });

    // 1. 要素追加直後に最下部へスクロール
    logArea.scrollTop = logArea.scrollHeight;

    setTimeout(() => {
        logArea.scrollTop = logArea.scrollHeight;
    }, 30); // 50ms後

    setTimeout(() => {
        logArea.scrollTop = logArea.scrollHeight;
    }, 80); // 200ms後 (念のため)
}

// --- タブ初期化関数 ---
async function setupVisualBattleTab() {
    console.log("Setting up Visual Battle Tab...");

    // 1. フィルタ状態の完全リセット
    window.currentVisualLogFilter = 'all';
    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        if (btn.dataset.filter === 'all') btn.classList.add('active');
        else btn.classList.remove('active');
    });

    // 2. ★ログの即時描画 (awaitなどの非同期処理の前に実行して表示遅延を防ぐ)
    if (typeof battleState !== 'undefined' && battleState.logs) {
        renderVisualLogHistory(battleState.logs);
    }

    // 3. マップコントロール等のセットアップ
    setupMapControls();
    setupVisualSidebarControls();

    // 4. マップやタイムラインの描画
    renderVisualMap();
    renderStagingArea();
    renderVisualTimeline();
    updateVisualRoundDisplay(battleState ? battleState.round : 0);

    // 5. スキルデータのロード (非同期)
    // ※ログ描画後に持ってくることで、通信待ち中もログが表示されるようにする
    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        try {
            const res = await fetch('/api/get_skill_data');
            if (res.ok) window.allSkillData = await res.json();
        } catch (e) { console.error("Failed to load skill data:", e); }
    }

    // 6. Socketリスナー登録 (初回のみ)
    if (typeof socket !== 'undefined' && !window.battleSocketHandlersRegistered) {
        console.log("Registering Battle Socket Listeners (One-time only / from Visual)");
        window.battleSocketHandlersRegistered = true;

        socket.on('state_updated', (state) => {
            if (document.getElementById('visual-battle-container')) {
                renderVisualMap();
                renderStagingArea();
                renderVisualTimeline();
                renderVisualLogHistory(state.logs);
                updateVisualRoundDisplay(state.round);
            }
            if (document.getElementById('battlefield-grid')) {
                if(typeof renderTimeline === 'function') renderTimeline();
                if(typeof renderTokenList === 'function') renderTokenList();
            }
            if (document.getElementById('log-area')) {
                if(typeof renderLogHistory === 'function') renderLogHistory(state.logs);
            }
        });

        socket.on('skill_declaration_result', (data) => {
            if (data.prefix && data.prefix.startsWith('visual_')) {
                if (data.is_instant_action && typeof closeDuelModal === 'function') {
                    closeDuelModal();
                    return;
                }
                const side = data.prefix.replace('visual_', '');
                if (typeof updateDuelUI === 'function') updateDuelUI(side, data);
                return;
            }
            if (data.prefix && data.prefix.startsWith('wide-def-')) {
                const charId = data.prefix.replace('wide-def-', '');
                const row = document.querySelector(`.wide-defender-row[data-row-id="wide-row-${charId}"]`);
                if (row) {
                    const resArea = row.querySelector('.wide-result-area');
                    const declBtn = row.querySelector('.wide-declare-btn');
                    const finalCmdInput = row.querySelector('.wide-final-command');
                    if (data.error) {
                        resArea.textContent = data.final_command;
                        resArea.style.color = "red";
                        declBtn.disabled = true;
                    } else {
                        resArea.textContent = `威力: ${data.min_damage}～${data.max_damage} (${data.final_command})`;
                        resArea.style.color = "blue";
                        finalCmdInput.value = data.final_command;
                        declBtn.disabled = false;
                    }
                }
                return;
            }
            const powerDisplay = document.getElementById(`power-display-${data.prefix}`);
            if (powerDisplay) {
                const prefix = data.prefix;
                const commandDisplay = document.getElementById(`command-display-${prefix}`);
                const hiddenCommand = document.getElementById(`hidden-command-${prefix}`);
                const declareBtn = document.getElementById(`declare-btn-${prefix}`);
                const generateBtn = document.getElementById(`generate-btn-${prefix}`);
                generateBtn.disabled = false;
                if (data.error) {
                    powerDisplay.value = data.final_command;
                    commandDisplay.value = "--- エラー ---";
                    powerDisplay.style.borderColor = "#dc3545";
                    declareBtn.disabled = true;
                    return;
                }
                powerDisplay.value = `威力: ${data.min_damage} ～ ${data.max_damage}`;
                commandDisplay.value = data.final_command;
                hiddenCommand.value = data.final_command;
                declareBtn.disabled = false;
                declareBtn.dataset.isImmediate = data.is_immediate_skill ? 'true' : 'false';
                powerDisplay.style.borderColor = "";
                if (prefix === 'attacker' && data.is_one_sided_attack) {
                    const defenderPower = document.getElementById('power-display-defender');
                    if (defenderPower) {
                        defenderPower.value = "--- (一方攻撃) ---";
                        document.getElementById('command-display-defender').value = '【一方攻撃（行動済）】';
                        document.getElementById('hidden-command-defender').value = '【一方攻撃（行動済）】';
                        document.getElementById('actor-defender').disabled = true;
                        document.getElementById('declare-btn-defender').disabled = true;
                        defenderPower.style.borderColor = "#4CAF50";
                    }
                }
            }
        });
    }
}

// --- サイドバー制御 ---
function setupVisualSidebarControls() {
    const nextBtn = document.getElementById('visual-next-turn-btn');
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');

    if (nextBtn) {
        const newBtn = nextBtn.cloneNode(true);
        nextBtn.parentNode.replaceChild(newBtn, nextBtn);
        newBtn.addEventListener('click', () => {
            if (confirm("手番を終了して次に回しますか？")) {
                socket.emit('request_next_turn', { room: currentRoomName });
            }
        });
    }

    if (currentUserAttribute === 'GM') {
        if(startRBtn) {
            startRBtn.style.display = 'inline-block';
            startRBtn.onclick = () => {
                if(confirm("次ラウンドを開始しますか？")) socket.emit('request_new_round', { room: currentRoomName });
            };
        }
        if(endRBtn) {
            endRBtn.style.display = 'inline-block';
            endRBtn.onclick = () => {
                if(confirm("ラウンドを終了しますか？")) socket.emit('request_end_round', { room: currentRoomName });
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
            if (!msg && isSecret) {
                alert("シークレットメッセージの内容を入力してください。");
                return;
            }
            if (msg) {
                socket.emit('request_chat', {
                    room: currentRoomName,
                    user: currentUsername,
                    message: msg,
                    secret: isSecret
                });
            }
        }
        chatInput.value = '';
    };

    if (chatSend) chatSend.onclick = sendChat;
    if (chatInput) {
        chatInput.onkeydown = (e) => {
            if(e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                sendChat();
            }
        };
    }

    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        btn.onclick = () => {
            filters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.currentVisualLogFilter = btn.dataset.filter;
            if(battleState && battleState.logs) renderVisualLogHistory(battleState.logs);
        };
    });

    const saveBtn = document.getElementById('visual-save-btn');
    const presetBtn = document.getElementById('visual-preset-btn');
    const resetBtn = document.getElementById('visual-reset-btn');
    const statusMsg = document.getElementById('visual-status-msg');

    if (saveBtn) saveBtn.onclick = async () => {
        statusMsg.textContent = "保存中...";
        try {
            await fetchWithSession('/save_room', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_name: currentRoomName, state: battleState })
            });
            statusMsg.textContent = "保存完了";
            setTimeout(() => statusMsg.textContent = "", 2000);
        } catch(e) { statusMsg.textContent = "保存失敗"; }
    };

    if (presetBtn) presetBtn.onclick = () => {
        if (typeof openPresetManagerModal === 'function') openPresetManagerModal();
    };

    if (resetBtn) resetBtn.onclick = () => {
        if (typeof openResetTypeModal === 'function') {
            openResetTypeModal((type) => {
                socket.emit('request_reset_battle', { room: currentRoomName, mode: type });
            });
        } else if(confirm("戦闘をリセットしますか？")) {
            socket.emit('request_reset_battle', { room: currentRoomName, mode: 'full' });
        }
    };
}

function updateVisualRoundDisplay(round) {
    const el = document.getElementById('visual-round-counter');
    if(el) el.textContent = round || 0;
}

// --- マップ位置更新 ---
function updateMapTransform() {
    const mapEl = document.getElementById('game-map');
    if (mapEl) {
        mapEl.style.transform = `translate(${visualOffsetX}px, ${visualOffsetY}px) scale(${visualScale})`;
    }
}

// --- マップ描画 ---
function renderVisualMap() {
    const tokenLayer = document.getElementById('map-token-layer');
    if (!tokenLayer) return;

    tokenLayer.innerHTML = '';
    renderVisualTimeline();
    updateMapTransform();

    if (typeof battleState === 'undefined' || !battleState.characters) return;
    const currentTurnId = battleState.turn_char_id || null;

    battleState.characters.forEach(char => {
        if (char.x >= 0 && char.y >= 0 && char.hp > 0) {
            const token = createMapToken(char);
            if (char.id === currentTurnId) {
                token.classList.add('active-turn');
            }
            tokenLayer.appendChild(token);
        }
    });
}

// --- マップ操作 ---
function setupMapControls() {
    const mapViewport = document.getElementById('map-viewport');
    const gameMap = document.getElementById('game-map');
    if (!mapViewport || !gameMap) return;

    if (window.visualMapHandlers.move) {
        window.removeEventListener('mousemove', window.visualMapHandlers.move);
    }
    if (window.visualMapHandlers.up) {
        window.removeEventListener('mouseup', window.visualMapHandlers.up);
    }

    mapViewport.ondragover = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; };
    mapViewport.ondrop = (e) => {
        e.preventDefault();
        if (e.target.closest('.map-token')) return;
        const charId = e.dataTransfer.getData('text/plain');
        if (!charId) return;
        const rect = gameMap.getBoundingClientRect();
        const mapX = (e.clientX - rect.left) / visualScale;
        const mapY = (e.clientY - rect.top) / visualScale;
        const gridX = Math.floor(mapX / GRID_SIZE);
        const gridY = Math.floor(mapY / GRID_SIZE);
        if (typeof socket !== 'undefined' && currentRoomName) {
            socket.emit('request_move_token', { room: currentRoomName, charId, x: gridX, y: gridY });
        }
    };

    const zIn = document.getElementById('zoom-in-btn');
    const zOut = document.getElementById('zoom-out-btn');
    const rView = document.getElementById('reset-view-btn');
    if(zIn) zIn.onclick = () => { visualScale = Math.min(visualScale + 0.1, 3.0); updateMapTransform(); };
    if(zOut) zOut.onclick = () => { visualScale = Math.max(visualScale - 0.1, 0.5); updateMapTransform(); };
    if(rView) rView.onclick = () => { visualScale = 1.0; visualOffsetX = 0; visualOffsetY = 0; updateMapTransform(); };

    let isPanning = false, startX, startY;
    mapViewport.onmousedown = (e) => {
        if (e.target.closest('.map-token')) return;
        isPanning = true;
        startX = e.clientX - visualOffsetX;
        startY = e.clientY - visualOffsetY;
    };
    const onMouseMove = (e) => {
        if (!isPanning) return;
        e.preventDefault();
        visualOffsetX = e.clientX - startX;
        visualOffsetY = e.clientY - startY;
        updateMapTransform();
    };
    const onMouseUp = () => { isPanning = false; };

    window.visualMapHandlers.move = onMouseMove;
    window.visualMapHandlers.up = onMouseUp;
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
}

function renderVisualTimeline() {
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
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.padding = "6px 8px";
        item.style.borderBottom = "1px solid #eee";
        item.style.cursor = "pointer";
        item.style.background = "#fff";
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
            <span class="speed" style="font-size:0.85em; color:#666;">SPD:${char.speedRoll}</span>
        `;
        item.addEventListener('click', () => showCharacterDetail(char.id));
        timelineEl.appendChild(item);
    });
}

function renderStagingArea() {
    const stagingEl = document.getElementById('staging-list');
    if (!stagingEl) return;
    stagingEl.innerHTML = '';

    if (typeof battleState === 'undefined' || !battleState.characters) return;

    battleState.characters.forEach(char => {
        // 配置されていない(x<0 または y<0) 生存キャラクターを表示
        if ((char.x < 0 || char.y < 0) && char.hp > 0) {
            const item = document.createElement('div');
            item.className = `staging-item ${char.type || 'NPC'}`;
            item.style.padding = "5px";
            item.style.margin = "2px 0";
            item.style.background = "#fff";
            item.style.border = "1px solid #ddd";
            item.style.borderRadius = "4px";
            item.style.cursor = "grab";
            item.style.fontSize = "0.9em";
            item.draggable = true;

            const typeColor = (char.type === 'ally') ? '#007bff' : '#dc3545';
            item.style.borderLeft = `3px solid ${typeColor}`;

            item.textContent = char.name;

            item.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', char.id);
                e.dataTransfer.effectAllowed = 'move';
            });

            item.addEventListener('click', () => showCharacterDetail(char.id));

            stagingEl.appendChild(item);
        }
    });
}

function createMapToken(char) {
    const token = document.createElement('div');
    token.className = `map-token ${char.color || 'NPC'}`;
    token.dataset.id = char.id;
    token.style.left = `${char.x * GRID_SIZE + 4}px`;
    token.style.top = `${char.y * GRID_SIZE + 4}px`;
    const maxHp = char.maxHp || 1; const hp = char.hp || 0;
    const hpPer = Math.max(0, Math.min(100, (hp / maxHp) * 100));
    const maxMp = char.maxMp || 1; const mp = char.mp || 0;
    const mpPer = Math.max(0, Math.min(100, (mp / maxMp) * 100));
    const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
    const fp = fpState ? fpState.value : 0;
    const fpPer = Math.min(100, (fp / 15) * 100);
    let iconsHtml = '';
    if (char.states) {
        char.states.forEach(s => {
            if (['HP', 'MP', 'FP'].includes(s.name)) return;
            if (s.value === 0) return;
            const config = STATUS_CONFIG[s.name];
            if (config) {
                iconsHtml += `
                    <div class="mini-status-icon" style="background-color: #fff; border-color: ${config.borderColor};">
                        <img src="images/${config.icon}" alt="${s.name}">
                        <div class="mini-status-badge" style="background-color: ${config.color};">${s.value}</div>
                    </div>`;
            } else {
                const arrow = s.value > 0 ? '▲' : '▼';
                const color = s.value > 0 ? '#28a745' : '#dc3545';
                iconsHtml += `
                    <div class="mini-status-icon" style="color:${color}; font-weight:bold; border-color:${color};">
                        ${arrow}
                        <div class="mini-status-badge" style="background:${color}; border-color:${color};">${s.value}</div>
                    </div>`;
            }
        });
    }
    token.innerHTML = `
        <div class="token-bars">
            <div class="token-bar" title="HP: ${hp}/${maxHp}">
                <div class="token-bar-fill hp" style="width: ${hpPer}%"></div>
            </div>
            <div class="token-bar" title="MP: ${mp}/${maxMp}">
                <div class="token-bar-fill mp" style="width: ${mpPer}%"></div>
            </div>
            <div class="token-bar" title="FP: ${fp}">
                <div class="token-bar-fill fp" style="width: ${fpPer}%"></div>
            </div>
        </div>
        <div class="token-body"><span>${char.name.charAt(0)}</span></div>
        <div class="token-label" title="${char.name}">${char.name}</div>
        <div class="token-status-overlay">${iconsHtml}</div>
    `;
    token.draggable = true;
    token.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', char.id);
        e.dataTransfer.effectAllowed = 'move';
        token.classList.add('dragging');
    });
    token.addEventListener('dragend', () => token.classList.remove('dragging'));
    token.addEventListener('click', (e) => {
        e.stopPropagation();
        selectVisualToken(char.id);
        showCharacterDetail(char.id);
    });
    token.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'link'; });
    token.addEventListener('drop', (e) => {
        e.preventDefault(); e.stopPropagation();
        const attackerId = e.dataTransfer.getData('text/plain');
        if (!attackerId || attackerId === char.id) return;
        const attackerChar = battleState.characters.find(c => c.id === attackerId);
        const attackerName = attackerChar ? attackerChar.name : "不明";
        if(confirm(`【攻撃確認】\n「${attackerName}」が「${char.name}」に攻撃を仕掛けますか？`)) {
            openDuelModal(attackerId, char.id);
        }
    });
    return token;
}

function showCharacterDetail(charId) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;
    const existing = document.getElementById('char-detail-modal-backdrop');
    if (existing) existing.remove();
    const backdrop = document.createElement('div');
    backdrop.id = 'char-detail-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';
    let paramsHtml = '';
    if (Array.isArray(char.params)) paramsHtml = char.params.map(p => `${p.label}:${p.value}`).join(' / ');
    else if (char.params && typeof char.params === 'object') paramsHtml = Object.entries(char.params).map(([k,v]) => `${k}:${v}`).join(' / ');
    else paramsHtml = 'なし';
    const fpVal = (char.states.find(s => s.name === 'FP') || {}).value || 0;
    let statesHtml = '';
    char.states.forEach(s => {
        if(['HP','MP','FP'].includes(s.name)) return;
        if(s.value === 0) return;
        const config = STATUS_CONFIG[s.name];
        const colorStyle = config ? `color: ${config.color}; font-weight:bold;` : '';
        statesHtml += `<div class="detail-buff-item" style="${colorStyle}">${s.name}: ${s.value}</div>`;
    });
    if (!statesHtml) statesHtml = '<span style="color:#999; font-size:0.9em;">なし</span>';
    let specialBuffsHtml = '';
    if (char.special_buffs && char.special_buffs.length > 0) {
        char.special_buffs.forEach((b, index) => {
            let buffInfo = { name: b.name, description: b.description || "" };
            if (window.BUFF_DATA && typeof window.BUFF_DATA.get === 'function') {
                const info = window.BUFF_DATA.get(b.name);
                if (info) {
                    buffInfo.name = info.name || b.name;
                    if (!buffInfo.description && info.description) buffInfo.description = info.description;
                }
            }
            if (buffInfo.name.includes('_')) buffInfo.name = buffInfo.name.split('_')[0];
            let durationVal = null;
            if (b.lasting !== undefined && b.lasting !== null) durationVal = b.lasting;
            else if (b.round !== undefined && b.round !== null) durationVal = b.round;
            else if (b.duration !== undefined && b.duration !== null) durationVal = b.duration;
            let durationHtml = "";
            if (durationVal !== null && !isNaN(durationVal) && durationVal < 99) {
                durationHtml = `<span class="buff-duration-badge" style="background:#666; color:#fff; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:8px; display:inline-block;">${durationVal}R</span>`;
            }
            const buffUniqueId = `buff-detail-${char.id}-${index}`;
            specialBuffsHtml += `
                <div style="width: 100%; margin-bottom: 4px;">
                    <div class="detail-buff-item special" onclick="toggleBuffDesc('${buffUniqueId}')" style="cursor: pointer; background: #f0f0f0; border-radius: 4px; padding: 6px 10px; display:flex; align-items:center;">
                        <span style="font-weight:bold; color:#333;">${buffInfo.name}</span>
                        ${durationHtml}
                        <span style="font-size:0.8em; opacity:0.7; margin-left:auto;">▼</span>
                    </div>
                    <div id="${buffUniqueId}" class="buff-desc-box" style="display:none; padding:8px; font-size:0.9em; background:#fff; border:1px solid #ddd; border-top:none; border-radius: 0 0 4px 4px; color:#555;">
                        ${buffInfo.description || "(説明文なし)"}
                    </div>
                </div>
            `;
        });
    }
    if (!specialBuffsHtml) specialBuffsHtml = '<span style="color:#999; font-size:0.9em;">なし</span>';
    backdrop.innerHTML = `
        <div class="char-detail-modal">
            <div class="detail-header">
                <h2>${char.name}</h2>
                <button class="detail-close-btn">&times;</button>
            </div>
            <div class="detail-stat-grid">
                <div class="detail-stat-box"><span class="detail-stat-label">HP</span><span class="detail-stat-val" style="color:#28a745;">${char.hp} / ${char.maxHp}</span></div>
                <div class="detail-stat-box"><span class="detail-stat-label">MP</span><span class="detail-stat-val" style="color:#007bff;">${char.mp} / ${char.maxMp}</span></div>
                <div class="detail-stat-box"><span class="detail-stat-label">FP</span><span class="detail-stat-val" style="color:#ffc107;">${fpVal}</span></div>
            </div>
            <div class="detail-section"><h4>Parameters</h4><div style="font-family:monospace; background:#f9f9f9; padding:8px; border-radius:4px; font-weight:bold;">${paramsHtml}</div></div>
            <div class="detail-section"><h4>状態異常 (Stack)</h4><div class="detail-buff-list">${statesHtml}</div></div>
            <div class="detail-section"><h4>特殊効果 / バフ (Click for Info)</h4><div class="detail-buff-list" style="display:block;">${specialBuffsHtml}</div></div>
            <div class="detail-section"><h4>Skills</h4><div style="font-size:0.9em; max-height:100px; overflow-y:auto; border:1px solid #eee; padding:5px; white-space: pre-wrap;">${char.commands || "なし"}</div></div>
        </div>
    `;
    document.body.appendChild(backdrop);
    const closeFunc = () => backdrop.remove();
    backdrop.querySelector('.detail-close-btn').onclick = closeFunc;
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closeFunc(); });
}

function toggleBuffDesc(elementId) {
    const el = document.getElementById(elementId);
    if (el) el.style.display = (el.style.display === 'none') ? 'block' : 'none';
}

function selectVisualToken(charId) {
    document.querySelectorAll('.map-token').forEach(el => el.classList.remove('selected'));
    const token = document.querySelector(`.map-token[data-id="${charId}"]`);
    if(token) token.classList.add('selected');
}

// --- 対決モーダル ---
function openDuelModal(attackerId, defenderId) {
    const attacker = battleState.characters.find(c => c.id === attackerId);
    const defender = battleState.characters.find(c => c.id === defenderId);
    if (!attacker || !defender) return;
    duelState = {
        attackerId, defenderId,
        attackerLocked: false, defenderLocked: false,
        isOneSided: false,
        attackerCommand: null, defenderCommand: null
    };
    resetDuelUI();
    document.getElementById('duel-attacker-name').textContent = attacker.name;
    document.getElementById('duel-defender-name').textContent = defender.name;
    populateCharSkillSelect(attacker, 'duel-attacker-skill');
    const hasReEvasion = defender.special_buffs && defender.special_buffs.some(b => b.name === '再回避ロック');
    if (defender.hasActed && !hasReEvasion) {
        duelState.isOneSided = true;
        duelState.defenderLocked = true;
        duelState.defenderCommand = "【一方攻撃（行動済）】";
        document.getElementById('duel-defender-controls').style.display = 'none';
        document.getElementById('duel-defender-lock-msg').style.display = 'block';
        document.getElementById('duel-defender-preview').querySelector('.preview-command').textContent = "No Guard";
    } else {
        document.getElementById('duel-defender-controls').style.display = 'block';
        document.getElementById('duel-defender-lock-msg').style.display = 'none';
        populateCharSkillSelect(defender, 'duel-defender-skill');
    }
    setupDuelListeners();
    document.getElementById('duel-modal-backdrop').style.display = 'flex';
}

function closeDuelModal() {
    document.getElementById('duel-modal-backdrop').style.display = 'none';
}

function resetDuelUI() {
    ['attacker', 'defender'].forEach(side => {
        const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
        const declBtn = document.getElementById(`duel-${side}-declare-btn`);
        const preview = document.getElementById(`duel-${side}-preview`);
        const skillSelect = document.getElementById(`duel-${side}-skill`);
        if(calcBtn) calcBtn.disabled = false;
        if(declBtn) {
            declBtn.disabled = true; declBtn.textContent = "Declare";
            declBtn.classList.remove('locked');
            declBtn.dataset.isImmediate = 'false';
        }
        if (skillSelect) skillSelect.disabled = false;
        if (preview) {
            preview.querySelector('.preview-command').textContent = "---";
            preview.querySelector('.preview-damage').textContent = "";
            preview.classList.remove('ready');
        }
    });
    const statusMsg = document.getElementById('duel-status-message');
    if (statusMsg) statusMsg.textContent = "Setup Phase";
}

function populateCharSkillSelect(char, elementId) {
    const select = document.getElementById(elementId);
    select.innerHTML = '';
    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        const opt = document.createElement('option');
        opt.value = ""; opt.text = "(Skill Data Loading...)";
        select.appendChild(opt);
        return;
    }
    let count = 0;
    const commandsStr = char.commands || "";
    const regex = /【(.*?)\s+(.*?)】/g;
    let match;
    while ((match = regex.exec(commandsStr)) !== null) {
        const skillId = match[1];
        const skillName = match[2];
        if (window.allSkillData && window.allSkillData[skillId]) {
            const opt = document.createElement('option');
            opt.value = skillId;
            opt.text = `${skillId}: ${skillName}`;
            select.appendChild(opt);
            count++;
        }
    }
    if (count === 0) {
        const opt = document.createElement('option');
        opt.value = ""; opt.text = "(有効なスキルがありません)";
        select.appendChild(opt);
    }
}

function setupDuelListeners() {
    document.getElementById('duel-cancel-btn').onclick = closeDuelModal;
    document.getElementById('duel-attacker-calc-btn').onclick = () => sendSkillDeclaration('attacker', false);
    document.getElementById('duel-defender-calc-btn').onclick = () => sendSkillDeclaration('defender', false);
    document.getElementById('duel-attacker-declare-btn').onclick = () => {
        const btn = document.getElementById('duel-attacker-declare-btn');
        const isImmediate = btn.dataset.isImmediate === 'true';
        sendSkillDeclaration('attacker', true);
        if (!isImmediate) lockSide('attacker');
    };
    document.getElementById('duel-defender-declare-btn').onclick = () => {
        const btn = document.getElementById('duel-defender-declare-btn');
        const isImmediate = btn.dataset.isImmediate === 'true';
        sendSkillDeclaration('defender', true);
        if (!isImmediate) lockSide('defender');
    };
}

function sendSkillDeclaration(side, isCommit) {
    const isAttacker = (side === 'attacker');
    const actorId = isAttacker ? duelState.attackerId : duelState.defenderId;
    const targetId = isAttacker ? duelState.defenderId : duelState.attackerId;
    const skillSelect = document.getElementById(`duel-${side}-skill`);
    const skillId = skillSelect ? skillSelect.value : "";
    if (!skillId) { alert("スキルを選択してください。"); return; }
    socket.emit('request_skill_declaration', {
        room: currentRoomName,
        actor_id: actorId, target_id: targetId,
        skill_id: skillId, modifier: 0,
        prefix: `visual_${side}`,
        commit: isCommit, custom_skill_name: ""
    });
}

function updateDuelUI(side, data) {
    const previewEl = document.getElementById(`duel-${side}-preview`);
    const cmdEl = previewEl.querySelector('.preview-command');
    const dmgEl = previewEl.querySelector('.preview-damage');
    const declareBtn = document.getElementById(`duel-${side}-declare-btn`);
    if (data.error) {
        cmdEl.textContent = "Error"; dmgEl.textContent = data.final_command; return;
    }
    cmdEl.innerHTML = data.final_command;
    if (data.min_damage !== undefined) dmgEl.textContent = `Range: ${data.min_damage} ~ ${data.max_damage}`;
    else dmgEl.textContent = "Ready";
    previewEl.classList.add('ready');
    if (declareBtn) {
        declareBtn.disabled = false;
        if (data.is_immediate_skill) {
            declareBtn.dataset.isImmediate = 'true';
            declareBtn.textContent = "Execute (Immediate)";
        } else {
            declareBtn.dataset.isImmediate = 'false';
            declareBtn.textContent = "Declare";
        }
    }
    if (side === 'attacker') duelState.attackerCommand = data.final_command;
    else duelState.defenderCommand = data.final_command;
}

function lockSide(side) {
    const btn = document.getElementById(`duel-${side}-declare-btn`);
    const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
    const select = document.getElementById(`duel-${side}-skill`);
    if(btn) { btn.textContent = "Locked"; btn.classList.add('locked'); btn.disabled = true; }
    if(calcBtn) calcBtn.disabled = true;
    if(select) select.disabled = true;
    if (side === 'attacker') duelState.attackerLocked = true;
    if (side === 'defender') duelState.defenderLocked = true;
    checkAndExecuteMatch();
}

function checkAndExecuteMatch() {
    const statusEl = document.getElementById('duel-status-message');
    if (duelState.isOneSided) {
        if (duelState.attackerLocked) {
            statusEl.textContent = "Executing One-sided Attack...";
            executeMatch();
        } else {
            statusEl.textContent = "Waiting for Attacker...";
        }
    } else {
        if (duelState.attackerLocked && duelState.defenderLocked) {
            statusEl.textContent = "Executing Duel...";
            executeMatch();
        } else if (duelState.attackerLocked) statusEl.textContent = "Waiting for Defender...";
        else if (duelState.defenderLocked) statusEl.textContent = "Waiting for Attacker...";
    }
}

function executeMatch() {
    setTimeout(() => {
        const attackerName = document.getElementById('duel-attacker-name').textContent;
        const defenderName = document.getElementById('duel-defender-name').textContent;
        const stripTags = (str) => str ? str.replace(/<[^>]*>?/gm, '') : "2d6";
        socket.emit('request_match', {
            room: currentRoomName,
            actorIdA: duelState.attackerId, actorIdD: duelState.defenderId,
            actorNameA: attackerName, actorNameD: defenderName,
            commandA: stripTags(duelState.attackerCommand),
            commandD: stripTags(duelState.defenderCommand),
            senritsuPenaltyA: 0, senritsuPenaltyD: 0
        });
        closeDuelModal();
        setTimeout(() => {
            socket.emit('request_next_turn', { room: currentRoomName });
        }, 1000);
    }, 500);
}