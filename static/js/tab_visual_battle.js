/* static/js/tab_visual_battle.js */

// --- グローバル変数 ---
let visualScale = 1.0;
let visualOffsetX = 0;
let visualOffsetY = 0;
const GRID_SIZE = 96;
window.currentVisualLogFilter = 'all';
window.visualMapHandlers = window.visualMapHandlers || { move: null, up: null };

// --- 広域攻撃用の一時変数 (状態管理) ---
let visualWideState = {
    attackerId: null,
    isDeclared: false
};

// --- ヘルパー: 広域スキル判定 ---
function isWideSkillData(skillData) {
    if (!skillData) return false;
    const tags = skillData['tags'] || [];
    const cat = skillData['分類'] || '';
    const dist = skillData['距離'] || '';
    return (tags.includes('広域-個別') || tags.includes('広域-合算') ||
            cat.includes('広域') || dist.includes('広域'));
}

function hasWideSkill(char) {
    if (!window.allSkillData || !char.commands) return false;
    const regex = /【(.*?)\s+(.*?)】/g;
    let match;
    while ((match = regex.exec(char.commands)) !== null) {
        const skillId = match[1];
        const skillData = window.allSkillData[skillId];
        if (skillData && isWideSkillData(skillData)) {
            return true;
        }
    }
    return false;
}

// --- ヘルパー: 結果表示フォーマット ---
function formatWideResult(data) {
    if (data.error) return data.final_command || "Error";
    const min = (data.min_damage != null) ? data.min_damage : '?';
    const max = (data.max_damage != null) ? data.max_damage : '?';
    // 表示用: Range: X~Y (Command)
    return `Range: ${min}～${max} (${data.final_command})`;
}

// --- ★ 追加: スキル詳細HTML生成ヘルパー ---
function formatSkillDetailHTML(details) {
    if (!details) return "";

    const category = details["分類"] || "---";
    const distance = details["距離"] || "---";
    const attribute = details["属性"] || "---";

    // バッジ部分
    let html = `
        <div class="skill-detail-header">
            <span class="skill-badge badge-category">${category}</span>
            <span class="skill-badge badge-distance">距離: ${distance}</span>
            <span class="skill-badge badge-attribute">属性: ${attribute}</span>
        </div>
    `;

    // 効果テキスト部分
    const addSection = (label, text) => {
        if (text && text !== "なし" && text !== "") {
            return `
                <div class="skill-desc-section">
                    <span class="skill-desc-label">【${label}】</span>
                    <span class="skill-desc-text">${text}</span>
                </div>`;
        }
        return "";
    };

    html += addSection("コスト", details["使用時効果"]);
    html += addSection("効果", details["発動時効果"]);
    html += addSection("特記", details["特記"]);

    return html;
}

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

// --- ログ描画ヘルパー ---
function appendVisualLogLine(container, logData, filterType) {
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
}

function renderVisualLogHistory(logs) {
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

// --- ★初期化関数 ---
async function setupVisualBattleTab() {
    console.log("Setting up Visual Battle Tab...");

    if (typeof socket !== 'undefined') {
        // 1. 重複防止: 一度だけ登録すればよいイベント (Map描画など)
        if (!window.visualBattleSocketHandlersRegistered) {
            console.log("Registering Visual Battle Base Listeners (Map/Log)");
            window.visualBattleSocketHandlersRegistered = true;

            socket.on('state_updated', (state) => {
                if (document.getElementById('visual-battle-container')) {
                    renderVisualMap();
                    renderStagingArea();
                    renderVisualTimeline();
                    renderVisualLogHistory(state.logs);
                    updateVisualRoundDisplay(state.round);
                }
            });

            socket.on('open_wide_declaration_modal', () => {
                openVisualWideDeclarationModal();
            });
        }

        // 2. 強制更新: 計算ロジックなどは修正を即時反映させるため毎回更新する
        socket.off('skill_declaration_result');

        // --- ★計算結果/宣言結果の受信 (統合ハンドラ) ---
        socket.on('skill_declaration_result', (data) => {
            if (!data.prefix) return;

            // A. 広域攻撃 (攻撃側)
            if (data.prefix === 'visual_wide_attacker') {
                const cmdInput = document.getElementById('v-wide-attacker-cmd');
                const declareBtn = document.getElementById('v-wide-declare-btn');
                const modeBadge = document.getElementById('v-wide-mode-badge');
                const descArea = document.getElementById('v-wide-attacker-desc');

                if (cmdInput && declareBtn) {
                    if (data.error) {
                        cmdInput.value = data.final_command || "エラー";
                        cmdInput.style.color = "red";
                        if (descArea) descArea.innerHTML = "<span style='color:red;'>エラー</span>";
                    } else {
                        // 表示用フォーマットをセット
                        cmdInput.value = formatWideResult(data);
                        // 計算用の生データを属性に保存
                        cmdInput.dataset.raw = data.final_command;

                        cmdInput.style.color = "black";
                        cmdInput.style.fontWeight = "bold";

                        if(modeBadge) modeBadge.style.display = 'inline-block';

                        // 宣言ボタン有効化
                        declareBtn.disabled = false;
                        declareBtn.textContent = "宣言";
                        declareBtn.classList.remove('locked');
                        declareBtn.classList.remove('btn-outline-danger');
                        declareBtn.classList.add('btn-danger');

                        // スキル詳細表示
                        if (descArea && data.skill_details) {
                            descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
                        }
                    }
                }
                return;
            }

            // B. 広域攻撃 (防御側個別)
            if (data.prefix.startsWith('visual_wide_def_')) {
                const charId = data.prefix.replace('visual_wide_def_', '');
                const row = document.querySelector(`.wide-defender-row[data-id="${charId}"]`);
                if (row) {
                    const cmdInput = row.querySelector('.v-wide-def-cmd');
                    const statusSpan = row.querySelector('.v-wide-status');
                    const declareBtn = row.querySelector('.v-wide-def-declare');
                    const descArea = row.querySelector('.v-wide-def-desc');

                    if (data.error) {
                        cmdInput.value = data.final_command;
                        cmdInput.style.color = "red";
                        statusSpan.textContent = "エラー";
                        statusSpan.style.color = "red";
                    } else {
                        // 表示用フォーマットと生データの分離
                        cmdInput.value = formatWideResult(data);
                        cmdInput.dataset.raw = data.final_command;

                        cmdInput.style.color = "green";
                        cmdInput.style.fontWeight = "bold";
                        statusSpan.textContent = "OK";
                        statusSpan.style.color = "green";

                        // 防御側の宣言ボタン有効化
                        if(declareBtn) {
                             declareBtn.disabled = false;
                             declareBtn.classList.remove('btn-outline-success');
                             declareBtn.classList.add('btn-success');
                        }

                        // スキル詳細表示
                        if (descArea && data.skill_details) {
                            descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
                        }
                    }
                }
                return;
            }

            // C. 即時発動スキル
            if (data.is_instant_action && data.prefix.startsWith('visual_')) {
                if (typeof closeDuelModal === 'function') closeDuelModal();
                return;
            }

            // D. 通常1vs1対決UI更新
            if (data.prefix === 'visual_attacker' || data.prefix === 'visual_defender') {
                const side = data.prefix.replace('visual_', '');
                if (typeof updateDuelUI === 'function') updateDuelUI(side, data);
            }
        });
    }

    // 2. DOM操作とイベント登録
    window.currentVisualLogFilter = 'all';
    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        btn.onclick = () => {
            filters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.currentVisualLogFilter = btn.dataset.filter;
            if(battleState && battleState.logs) renderVisualLogHistory(battleState.logs);
        };
    });

    if (typeof battleState !== 'undefined' && battleState.logs) renderVisualLogHistory(battleState.logs);

    setupMapControls();
    setupVisualSidebarControls();
    renderVisualMap();
    renderStagingArea();
    renderVisualTimeline();
    updateVisualRoundDisplay(battleState ? battleState.round : 0);

    // 3. スキルデータロード
    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        try {
            const res = await fetch('/api/get_skill_data');
            if (res.ok) window.allSkillData = await res.json();
        } catch (e) { console.error("Failed to load skill data:", e); }
    }
}

// --- サイドバー ---
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

    const controlsArea = document.getElementById('visual-controls-area');
    if (controlsArea && !document.getElementById('visual-wide-decl-btn')) {
        const btn = document.createElement('button');
        btn.id = 'visual-wide-decl-btn';
        btn.textContent = "⚡ 広域予約";
        btn.style.width = "100%";
        btn.style.marginTop = "5px";
        btn.style.background = "#6f42c1";
        btn.style.color = "white";
        btn.style.border = "none";
        btn.style.padding = "8px";
        btn.style.borderRadius = "4px";
        btn.style.fontWeight = "bold";
        btn.style.cursor = "pointer";
        btn.onclick = openVisualWideDeclarationModal;
        controlsArea.appendChild(btn);
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
            if(e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); }
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
    if (presetBtn) presetBtn.onclick = () => { if (typeof openPresetManagerModal === 'function') openPresetManagerModal(); };
    if (resetBtn) resetBtn.onclick = () => {
        if (typeof openResetTypeModal === 'function') {
            openResetTypeModal((type) => { socket.emit('request_reset_battle', { room: currentRoomName, mode: type }); });
        } else if(confirm("戦闘をリセットしますか？")) {
            socket.emit('request_reset_battle', { room: currentRoomName, mode: 'full' });
        }
    };
}

function updateVisualRoundDisplay(round) {
    const el = document.getElementById('visual-round-counter');
    if(el) el.textContent = round || 0;
}

function updateMapTransform() {
    const mapEl = document.getElementById('game-map');
    if (mapEl) mapEl.style.transform = `translate(${visualOffsetX}px, ${visualOffsetY}px) scale(${visualScale})`;
}

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
            if (char.id === currentTurnId) token.classList.add('active-turn');
            tokenLayer.appendChild(token);
        }
    });
}

function setupMapControls() {
    const mapViewport = document.getElementById('map-viewport');
    const gameMap = document.getElementById('game-map');
    if (!mapViewport || !gameMap) return;

    if (window.visualMapHandlers.move) window.removeEventListener('mousemove', window.visualMapHandlers.move);
    if (window.visualMapHandlers.up) window.removeEventListener('mouseup', window.visualMapHandlers.up);

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

    const isCurrentTurn = (battleState.turn_char_id === char.id);
    let wideBtnHtml = '';
    if (isCurrentTurn && char.isWideUser) {
        wideBtnHtml = `<button class="wide-attack-trigger-btn" onmousedown="event.stopPropagation(); openVisualWideMatchModal('${char.id}');">⚡ 広域攻撃</button>`;
    }

    token.innerHTML = `
        ${wideBtnHtml}
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

    const isDefenderWideUser = defender.isWideUser;
    const hasReEvasion = defender.special_buffs && defender.special_buffs.some(b => b.name === '再回避ロック');

    if ((defender.hasActed && !hasReEvasion) || isDefenderWideUser) {
        duelState.isOneSided = true;
        duelState.defenderLocked = true;
        if (isDefenderWideUser) {
            duelState.defenderCommand = "【広域待機（防御放棄）】";
            document.getElementById('duel-defender-lock-msg').textContent = "広域攻撃待機中のため防御スキル使用不可";
        } else {
            duelState.defenderCommand = "【一方攻撃（行動済）】";
            document.getElementById('duel-defender-lock-msg').textContent = "行動済みのため防御不可";
        }
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

function closeDuelModal() { document.getElementById('duel-modal-backdrop').style.display = 'none'; }

// --- 修正: resetDuelUI 関数 ---
function resetDuelUI() {
    ['attacker', 'defender'].forEach(side => {
        const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
        const declBtn = document.getElementById(`duel-${side}-declare-btn`);
        const preview = document.getElementById(`duel-${side}-preview`);
        const skillSelect = document.getElementById(`duel-${side}-skill`);

        // ★修正: 詳細エリアは隠さず、中身だけ空にする
        const descArea = document.getElementById(`duel-${side}-skill-desc`);
        if (descArea) {
            descArea.innerHTML = "";
            // descArea.classList.remove('visible'); // 削除
        }

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

// --- 修正: updateDuelUI 関数 ---
function updateDuelUI(side, data) {
    const previewEl = document.getElementById(`duel-${side}-preview`);
    const cmdEl = previewEl.querySelector('.preview-command');
    const dmgEl = previewEl.querySelector('.preview-damage');
    const declareBtn = document.getElementById(`duel-${side}-declare-btn`);

    // ★追加: 詳細表示エリアの更新処理
    const descArea = document.getElementById(`duel-${side}-skill-desc`);

    if (data.error) {
        cmdEl.textContent = "Error";
        dmgEl.textContent = data.final_command;

        // エラー時は枠を残しつつエラーメッセージ
        if (descArea) descArea.innerHTML = "<div style='color:red;'>計算エラー</div>";
        return;
    }

    cmdEl.innerHTML = data.final_command;
    if (data.min_damage !== undefined) dmgEl.textContent = `Range: ${data.min_damage} ~ ${data.max_damage}`;
    else dmgEl.textContent = "Ready";
    previewEl.classList.add('ready');

    // ★修正: スキル詳細の表示 (クラス操作なし)
    if (descArea && data.skill_details) {
        descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
    }

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
        setTimeout(() => { socket.emit('request_next_turn', { room: currentRoomName }); }, 1000);
    }, 500);
}

// --- 広域宣言モーダル (Visual版) ---
function openVisualWideDeclarationModal() {
    const existing = document.getElementById('visual-wide-decl-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'visual-wide-decl-modal';
    backdrop.className = 'modal-backdrop';

    let listHtml = '';
    battleState.characters.forEach(char => {
        if (char.hp <= 0) return;
        if (!hasWideSkill(char)) return;

        const typeColor = char.type === 'ally' ? '#007bff' : '#dc3545';
        listHtml += `
            <div style="padding: 10px; border-bottom: 1px solid #eee; display:flex; align-items:center;">
                <input type="checkbox" class="visual-wide-check" value="${char.id}" style="transform:scale(1.3); margin-right:15px;">
                <span style="font-weight:bold; color:${typeColor}; font-size:1.1em;">${char.name}</span>
                <span style="margin-left:auto; color:#666;">SPD: ${char.speedRoll}</span>
            </div>
        `;
    });

    if (!listHtml) listHtml = '<div style="padding:15px; color:#666;">広域スキルを所持するキャラクターがいません</div>';

    backdrop.innerHTML = `
        <div class="modal-content" style="width: 500px; padding: 0;">
            <div style="padding: 15px; background: #6f42c1; color: white; border-radius: 8px 8px 0 0;">
                <h3 style="margin:0;">⚡ 広域攻撃予約 (Visual)</h3>
            </div>
            <div style="padding: 20px; max-height: 60vh; overflow-y: auto;">
                <p>今ラウンド、広域攻撃を行うキャラクターを選択してください。<br>※広域タグを持つキャラのみ表示</p>
                <div style="border: 1px solid #ddd; border-radius: 4px;">${listHtml}</div>
            </div>
            <div style="padding: 15px; background: #f8f9fa; text-align: right; border-radius: 0 0 8px 8px;">
                <button id="visual-wide-cancel" class="duel-btn secondary">キャンセル</button>
                <button id="visual-wide-confirm" class="duel-btn primary">決定</button>
            </div>
        </div>
    `;

    document.body.appendChild(backdrop);
    document.getElementById('visual-wide-cancel').onclick = () => backdrop.remove();
    document.getElementById('visual-wide-confirm').onclick = () => {
        const checks = backdrop.querySelectorAll('.visual-wide-check');
        const ids = Array.from(checks).filter(c => c.checked).map(c => c.value);
        socket.emit('request_declare_wide_skill_users', { room: currentRoomName, wideUserIds: ids });
        backdrop.remove();
    };
}

// --- ★広域攻撃実行モーダル (Visual版) - 抜本修正版 ---
function openVisualWideMatchModal(attackerId) {
    const char = battleState.characters.find(c => c.id === attackerId);
    if (!char) return;

    // グローバル状態管理変数へのセット
    visualWideState.attackerId = attackerId;
    visualWideState.isDeclared = false;

    const existing = document.getElementById('visual-wide-match-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'visual-wide-match-modal';
    backdrop.className = 'modal-backdrop';

    // スキル選択肢作成
    let skillOptions = '<option value="">-- スキルを選択 --</option>';
    if (char.commands && window.allSkillData) {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        while ((match = regex.exec(char.commands)) !== null) {
            const sId = match[1];
            const sName = match[2];
            const sData = window.allSkillData[sId];
            if (sData && isWideSkillData(sData)) {
                skillOptions += `<option value="${sId}">${sId}: ${sName}</option>`;
            }
        }
    }

    // UI構築 (data-raw属性を追加)
    backdrop.innerHTML = `
        <div class="modal-content wide-visual-modal">
            <div class="wide-visual-header">
                <h3 style="margin:0;">⚡ 広域攻撃実行: ${char.name} <span style="opacity:0.5; margin:0 10px;">|</span> 対象キャラクター (Defenders)</h3>
                <button class="detail-close-btn" style="color:white;" onclick="document.getElementById('visual-wide-match-modal').remove()">×</button>
            </div>
            <div class="wide-visual-body">
                <div class="wide-col-attacker">
                    <div class="wide-attacker-section">
                        <div style="margin-bottom:5px;">
                            <label style="font-weight:bold; display:block;">使用スキル:</label>
                            <select id="v-wide-skill-select" class="duel-select" style="width:100%; margin-top:5px;">${skillOptions}</select>
                        </div>

                        <div style="display:flex; gap:10px; margin-top:10px; align-items:center;">
                            <button id="v-wide-calc-btn" class="duel-btn calc" style="width: 100px; flex-shrink:0;">威力計算</button>
                            <span id="v-wide-mode-badge" class="wide-mode-badge" style="display:none;">MODE</span>
                        </div>

                        <div style="margin-top:10px; font-weight:bold; font-size:1.1em; display:flex; align-items:center; gap:10px;">
                            <span style="flex-shrink:0;">結果: </span>
                            <input type="text" id="v-wide-attacker-cmd" class="duel-input" style="flex:1; min-width:0;" readonly placeholder="[計算結果]" data-raw="">
                            <button id="v-wide-declare-btn" class="duel-btn declare" disabled style="width: 100px; flex-shrink:0;">宣言</button>
                        </div>

                        <div id="v-wide-attacker-desc" class="skill-detail-display" style="margin-top:10px;"></div>
                    </div>
                </div>

                <div class="wide-col-defenders">
                    <div id="v-wide-defenders-area" class="wide-defenders-grid">
                        <div style="grid-column:1/-1; padding:20px; text-align:center; color:#999;">
                            スキルを選択して「威力計算」を行うと対象が表示されます
                        </div>
                    </div>
                </div>
            </div>
            <div style="padding:15px; background:#eee; text-align:right;">
                <button id="v-wide-execute-btn" class="duel-btn declare" disabled>広域攻撃を実行</button>
            </div>
        </div>
    `;

    document.body.appendChild(backdrop);

    const skillSelect = document.getElementById('v-wide-skill-select');
    const calcBtn = document.getElementById('v-wide-calc-btn');
    const declareBtn = document.getElementById('v-wide-declare-btn');
    const executeBtn = document.getElementById('v-wide-execute-btn');
    const defendersArea = document.getElementById('v-wide-defenders-area');
    const modeBadge = document.getElementById('v-wide-mode-badge');
    const attackerCmdInput = document.getElementById('v-wide-attacker-cmd');
    const attackerDescArea = document.getElementById('v-wide-attacker-desc');

    let currentMode = null;

    // --- 1. 威力計算ボタン ---
    calcBtn.onclick = () => {
        const skillId = skillSelect.value;
        if (!skillId) return alert("スキルを選択してください");

        // UIリセット
        attackerCmdInput.value = "計算中...";
        attackerCmdInput.style.color = "#888";
        attackerCmdInput.dataset.raw = ""; // リセット
        if (attackerDescArea) attackerDescArea.innerHTML = ""; // 詳細エリアリセット

        // 再計算時は宣言状態解除
        visualWideState.isDeclared = false;
        if(declareBtn) {
            declareBtn.disabled = true;
            declareBtn.textContent = "宣言";
            declareBtn.classList.remove('locked', 'btn-danger');
            declareBtn.classList.add('btn-outline-danger');
        }
        executeBtn.disabled = true;

        console.log("【送信】広域計算(1vs1流用):", skillId);
        // 重要: ターゲットに自分自身を指定して、TargetNotSelectedエラーを回避しつつ威力のみ計算させる
        socket.emit('request_skill_declaration', {
            room: currentRoomName,
            prefix: 'visual_wide_attacker',
            actor_id: attackerId,
            target_id: attackerId,
            skill_id: skillId,
            commit: false // 計算のみ
        });

        // モード表示と対象リスト更新 (ローカル処理)
        const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
        if (skillData) {
            const cat = skillData['分類'] || '';
            const dist = skillData['距離'] || '';
            const tags = skillData['tags'] || [];

            if ((cat.includes('合算') || dist.includes('合算') || tags.includes('広域-合算'))) {
                currentMode = 'combined';
                modeBadge.textContent = "合算 (Combined)";
                modeBadge.style.backgroundColor = "#28a745";
            } else {
                currentMode = 'individual';
                modeBadge.textContent = "個別 (Individual)";
                modeBadge.style.backgroundColor = "#17a2b8";
            }
            modeBadge.style.display = 'inline-block';
            renderVisualWideDefenders(attackerId, currentMode);
        }
    };

    // --- 2. 宣言ボタン (Socket受信後に有効化される) ---
    declareBtn.onclick = () => {
        if (!attackerCmdInput.value || attackerCmdInput.value.includes("計算中") || attackerCmdInput.value.startsWith("エラー")) {
            return;
        }

        // 状態更新
        visualWideState.isDeclared = true;

        // UIロック
        skillSelect.disabled = true;
        calcBtn.disabled = true;
        declareBtn.disabled = true;
        declareBtn.textContent = "宣言済";
        declareBtn.classList.add('locked');
        attackerCmdInput.style.backgroundColor = "#e8f0fe";

        // 実行ボタン有効化
        executeBtn.disabled = false;
    };

    // --- 3. 実行ボタン ---
    executeBtn.onclick = () => {
        if (!visualWideState.isDeclared) {
             return alert("攻撃側の宣言が完了していません");
        }

        // 修正: 新しい行クラスに対応
        const defenderRows = defendersArea.querySelectorAll('.wide-defender-row');
        const defendersData = [];
        defenderRows.forEach(row => {
            const defId = row.dataset.id;
            const cmdInput = row.querySelector('.v-wide-def-cmd');
            const skillId = row.querySelector('.v-wide-def-skill').value;

            // 重要: 防御側も生データを送信する
            // 生データがない(計算していない/防御放棄)場合は空文字
            const rawCmd = cmdInput.dataset.raw || "";

            // 防御側は宣言必須ではないが、計算結果があればそれを採用
            defendersData.push({ id: defId, skillId: skillId || "", command: rawCmd });
        });

        // 重要: 攻撃側も生データ(dataset.raw)を送信する
        const attackerRawCmd = attackerCmdInput.dataset.raw;
        if (!attackerRawCmd) {
            return alert("攻撃側の計算結果が不正です。再計算してください。");
        }

        if (confirm(`【${currentMode === 'combined' ? '合算' : '個別'}】広域攻撃を実行しますか？`)) {
            socket.emit('request_wide_match', {
                room: currentRoomName,
                actorId: attackerId,
                skillId: skillSelect.value,
                mode: currentMode,
                commandActor: attackerRawCmd, // 生データを送信
                defenders: defendersData
            });
            backdrop.remove();

            // 追加: 通常マッチと同様に、少し待ってからターン終了リクエストを送る
            setTimeout(() => {
                console.log("Auto-requesting next turn after Wide Match...");
                socket.emit('request_next_turn', { room: currentRoomName });
            }, 1000);
        }
    };
}

// --- ★防御側カード生成 (宣言ボタン追加版 + スキル名表示修正) ---
function renderVisualWideDefenders(attackerId, mode) {
    const area = document.getElementById('v-wide-defenders-area');
    area.innerHTML = '';
    const attacker = battleState.characters.find(c => c.id === attackerId);
    const targetType = attacker.type === 'ally' ? 'enemy' : 'ally';
    const targets = battleState.characters.filter(c => c.type === targetType && c.hp > 0);

    if (targets.length === 0) {
        area.innerHTML = '<div style="padding:20px;">対象がいません</div>';
        return;
    }

    targets.forEach(tgt => {
        const isWideUser = tgt.isWideUser;
        const hasActed = tgt.hasActed;
        const hasReEvasion = tgt.special_buffs && tgt.special_buffs.some(b => b.name === '再回避ロック');
        const isDefenseLocked = (hasActed && !hasReEvasion) || isWideUser;

        let opts = '';
        if (isDefenseLocked) {
             if (isWideUser) opts = '<option value="">(防御放棄:広域待機)</option>';
             else opts = '<option value="">(防御放棄:行動済)</option>';
        } else {
            opts = '<option value="">(防御なし)</option>';
            if (tgt.commands) {
                const r = /【(.*?)\s+(.*?)】/g;
                let m;
                while ((m = r.exec(tgt.commands)) !== null) {
                    // 修正: スキル名も表示する (ID: Name)
                    opts += `<option value="${m[1]}">${m[1]}: ${m[2]}</option>`;
                }
            }
        }

        // 修正: .wide-defender-row クラスを使用し、新しいレイアウトに刷新
        const row = document.createElement('div');
        row.className = 'wide-defender-row';
        row.dataset.id = tgt.id;
        if (isDefenseLocked) row.style.background = "#f0f0f0";

        // data-raw属性を追加
        row.innerHTML = `
            <div class="wide-def-info">
                <div>${tgt.name}</div>
                <div class="v-wide-status" style="font-size:0.8em; color:#999;">${isDefenseLocked ? '不可' : '未計算'}</div>
            </div>
            <div class="wide-def-controls">
                <select class="v-wide-def-skill duel-select" style="width:100%; margin-bottom:5px; font-size:12px;" ${isDefenseLocked ? 'disabled' : ''}>${opts}</select>
                <div style="display:flex; gap:5px; align-items:center;">
                    <button class="v-wide-def-calc duel-btn secondary" style="padding:4px 8px; font-size:12px;" ${isDefenseLocked ? 'disabled' : ''}>Calc</button>
                    <input type="text" class="v-wide-def-cmd duel-input" readonly placeholder="Result" style="flex:1; font-size:12px;" value="${isDefenseLocked ? (isWideUser ? '【防御放棄】' : '【一方攻撃（行動済）】') : ''}" data-raw="">
                    <button class="v-wide-def-declare duel-btn outline-success" style="padding:4px 8px; font-size:12px;" disabled>宣言</button>
                </div>
            </div>
            <div class="v-wide-def-desc wide-def-desc skill-detail-display" style="margin-top:0; min-height:80px;"></div>
        `;
        area.appendChild(row);

        const btnCalc = row.querySelector('.v-wide-def-calc');
        const btnDeclare = row.querySelector('.v-wide-def-declare');
        const skillSel = row.querySelector('.v-wide-def-skill');
        const cmdInput = row.querySelector('.v-wide-def-cmd');
        const statusSpan = row.querySelector('.v-wide-status');
        const descArea = row.querySelector('.v-wide-def-desc');

        // Calc Logic
        btnCalc.onclick = () => {
            const sId = skillSel.value;
            statusSpan.textContent = "計算中...";
            // 計算時には宣言状態をリセット
            btnDeclare.disabled = true;
            btnDeclare.classList.remove('btn-success');
            btnDeclare.classList.add('btn-outline-success');
            btnDeclare.textContent = "宣言";
            cmdInput.style.backgroundColor = "";
            cmdInput.dataset.raw = ""; // リセット
            if(descArea) descArea.innerHTML = ""; // 詳細リセット

            socket.emit('request_skill_declaration', {
                room: currentRoomName,
                prefix: `visual_wide_def_${tgt.id}`,
                actor_id: tgt.id,
                target_id: attackerId,
                skill_id: sId,
                commit: false
            });
        };

        // Declare Logic
        btnDeclare.onclick = () => {
             // UI Lock
             skillSel.disabled = true;
             btnCalc.disabled = true;
             btnDeclare.disabled = true;
             btnDeclare.textContent = "宣言済";
             btnDeclare.classList.remove('btn-outline-success');
             btnDeclare.classList.add('btn-success'); // 緑色確定
             cmdInput.style.backgroundColor = "#e0ffe0"; // 薄緑背景
             statusSpan.textContent = "宣言済";
        };
    });
}