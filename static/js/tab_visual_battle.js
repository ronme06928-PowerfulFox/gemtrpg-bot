/* static/js/tab_visual_battle.js */

// --- グローバル変数 ---
let visualScale = 1.0;
let visualOffsetX = 0;
let visualOffsetY = 0;
const GRID_SIZE = 96;
let currentVisualLogFilter = 'all'; // ログフィルタ用

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

// --- タブ初期化関数 ---
async function setupVisualBattleTab() {
    console.log("Setting up Visual Battle Tab...");

    // スキルデータ読み込み
    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        try {
            const res = await fetch('/api/get_skill_data');
            if (res.ok) window.allSkillData = await res.json();
        } catch (e) { console.error("Failed to load skill data:", e); }
    }

    setupMapControls();
    setupVisualSidebarControls(); // ★追加: サイドバーのボタン設定

    // 初期描画
    renderVisualMap();
    renderStagingArea();
    renderVisualTimeline(); // ★追加: タイムライン描画

    // ログの初期表示 (テキスト側のログデータがあれば)
    if (typeof battleState !== 'undefined' && battleState.logs) {
        renderVisualLogHistory(battleState.logs);
    }

    if (typeof socket !== 'undefined') {
        // 状態更新リスナー
        if (window.visualBattleStateListener) socket.off('state_updated', window.visualBattleStateListener);
        window.visualBattleStateListener = (state) => {
            // タブが表示されている時のみ更新
            if (document.getElementById('visual-battle-container')) {
                renderVisualMap();
                renderStagingArea();
                renderVisualTimeline();
                renderVisualLogHistory(state.logs);
                updateVisualRoundDisplay(state.round);
            }
        };
        socket.on('state_updated', window.visualBattleStateListener);

        // スキル結果リスナー
        if (window.visualBattleSkillListener) socket.off('skill_declaration_result', window.visualBattleSkillListener);
        window.visualBattleSkillListener = (data) => {
            if (!data.prefix || !data.prefix.startsWith('visual_')) return;
            if (data.is_instant_action) {
                closeDuelModal();
                return;
            }
            const side = data.prefix.replace('visual_', '');
            updateDuelUI(side, data);
        };
        socket.on('skill_declaration_result', window.visualBattleSkillListener);
    }
}

// --- ★新規: サイドバーのコントロール設定 ---
function setupVisualSidebarControls() {
    // 1. ターン・ラウンド操作
    const nextBtn = document.getElementById('visual-next-turn-btn');
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');

    if (nextBtn) {
        // 重複登録防止のためクローン
        const newBtn = nextBtn.cloneNode(true);
        nextBtn.parentNode.replaceChild(newBtn, nextBtn);
        newBtn.addEventListener('click', () => {
            if (confirm("手番を終了して次に回しますか？")) {
                socket.emit('request_next_turn', { room: currentRoomName });
            }
        });
    }

    // GMのみ表示
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

    // 2. チャット送信
    const chatInput = document.getElementById('visual-chat-input');
    const chatSend = document.getElementById('visual-chat-send');

    const sendChat = () => {
        const msg = chatInput.value.trim();
        if (!msg) return;

        // ダイスロール判定 (簡易版)
        if (/^(\/roll|\/r|\/sroll|\/sr|\d+d\d+)/i.test(msg)) {
            // テキスト側のrollDiceCommandを使うか、ここでも実装するか。
            // 簡易的にサーバーへ送る (サーバー側で処理できるならベストだが、既存設計に合わせる)
            // ここではテキスト側のロジックを流用したいが、関数がないので簡易実装
            let isSecret = msg.startsWith('/sroll') || msg.startsWith('/sr');
            let content = msg.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');

            // 単純なチャットとして送信 (ダイス機能が必要なら rollDiceCommand を main.js に移動推奨)
            socket.emit('request_chat', {
                room: currentRoomName, user: currentUsername, message: msg, secret: isSecret
            });
        } else {
            socket.emit('request_chat', {
                room: currentRoomName, user: currentUsername, message: msg, secret: false
            });
        }
        chatInput.value = '';
    };

    if (chatSend) chatSend.onclick = sendChat;
    if (chatInput) chatInput.onkeydown = (e) => { if(e.key === 'Enter') sendChat(); };

    // 3. ログフィルタ
    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        btn.onclick = () => {
            filters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentVisualLogFilter = btn.dataset.filter;
            if(battleState && battleState.logs) renderVisualLogHistory(battleState.logs);
        };
    });

    // 4. ルーム操作
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

// --- ★新規: ログ描画 (ビジュアル用) ---
function renderVisualLogHistory(logs) {
    const logArea = document.getElementById('visual-log-area');
    if (!logArea || !logs) return;

    // 差分更新ではなく全更新 (簡易実装)
    // ※パフォーマンスが気になる場合は差分更新に書き換えてください
    logArea.innerHTML = '';

    logs.forEach(log => {
        const isChat = log.type === 'chat';
        if (currentVisualLogFilter === 'chat' && !isChat) return;
        if (currentVisualLogFilter === 'system' && isChat) return;

        const line = document.createElement('div');
        line.className = `log-line ${log.type}`;
        line.style.padding = "2px 0";
        line.style.borderBottom = "1px dotted #eee";

        let msg = log.message;
        if (log.secret) {
            line.classList.add('secret-log');
            line.style.background = "#fff0f5";
            if (log.user !== currentUsername && currentUserAttribute !== 'GM') {
                msg = "<span style='color:#999'>(シークレット)</span>";
            } else {
                msg = `<span style='color:#d63384'>[SECRET]</span> ${msg}`;
            }
        }

        if (isChat && !log.secret) {
            line.innerHTML = `<span style="color:#0056b3; font-weight:bold;">${log.user}:</span> ${msg}`;
        } else {
            line.innerHTML = msg;
        }
        logArea.appendChild(line);
    });
    logArea.scrollTop = logArea.scrollHeight;
}

function updateVisualRoundDisplay(round) {
    const el = document.getElementById('visual-round-counter');
    if(el) el.textContent = round || 0;
}

// --- マップ描画 (変更なし) ---
function renderVisualMap() {
    const mapEl = document.getElementById('game-map');
    const tokenLayer = document.getElementById('map-token-layer');
    if (!mapEl || !tokenLayer) return;

    tokenLayer.innerHTML = '';

    // ★ここでタイムラインも更新
    renderVisualTimeline();

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

    mapEl.style.transform = `translate(${visualOffsetX}px, ${visualOffsetY}px) scale(${visualScale})`;
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

        // 基本スタイル
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.padding = "6px 8px";
        item.style.borderBottom = "1px solid #eee";
        item.style.cursor = "pointer";
        item.style.background = "#fff";

        // 敵味方カラー定義
        const typeColor = (char.type === 'ally') ? '#007bff' : '#dc3545';

        // 通常時の帯
        item.style.borderLeft = `3px solid ${typeColor}`;

        // 現在の手番キャラ強調
        if (char.id === currentTurnId) {
            item.style.background = "#fff8e1"; // 薄いオレンジ
            item.style.fontWeight = "bold";
            // 帯を太くしつつ、他の枠線をオレンジに
            item.style.borderLeft = `6px solid ${typeColor}`;
            item.style.borderTop = "1px solid #ff9800";
            item.style.borderBottom = "1px solid #ff9800";
            item.style.borderRight = "1px solid #ff9800"; // 右側も閉じるなら追加
        }

        // 行動済み
        if (char.hasActed) {
            item.style.opacity = "0.5";
            item.style.textDecoration = "line-through";
        }

        // 戦闘不能
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

function createMapToken(char) {
    const token = document.createElement('div');
    token.className = `map-token ${char.color || 'NPC'}`;
    token.dataset.id = char.id;
    token.style.left = `${char.x * GRID_SIZE + 4}px`;
    token.style.top = `${char.y * GRID_SIZE + 4}px`;

    // ステータス
    const maxHp = char.maxHp || 1; const hp = char.hp || 0;
    const hpPer = Math.max(0, Math.min(100, (hp / maxHp) * 100));

    const maxMp = char.maxMp || 1; const mp = char.mp || 0;
    const mpPer = Math.max(0, Math.min(100, (mp / maxMp) * 100));

    const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
    const fp = fpState ? fpState.value : 0;
    const fpPer = Math.min(100, (fp / 15) * 100);

    // 状態異常アイコン生成 (枠外表示用)
    let iconsHtml = '';
    if (char.states) {
        char.states.forEach(s => {
            if (['HP', 'MP', 'FP'].includes(s.name)) return;
            if (s.value === 0) return;

            const config = STATUS_CONFIG[s.name];
            if (config) {
                // ★修正: 背景色を白(#fff)に固定して見やすくする
                iconsHtml += `
                    <div class="mini-status-icon" style="background-color: #fff; border-color: ${config.borderColor};">
                        <img src="images/${config.icon}" alt="${s.name}">
                        <div class="mini-status-badge" style="background-color: ${config.color};">${s.value}</div>
                    </div>`;
            } else {
                // 画像なし (矢印)
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

// --- 詳細モーダル (変更なし) ---
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
                durationHtml = `<span class="buff-duration-badge" style="background:#666; color:#fff; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:8px;">${durationVal}R</span>`;
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

function renderStagingArea() {
    const listEl = document.getElementById('staging-list');
    if (!listEl) return;
    listEl.innerHTML = '';
    if (typeof battleState === 'undefined' || !battleState.characters) return;
    battleState.characters.forEach(char => {
        const charX = (char.x !== undefined) ? char.x : -1;
        if (charX < 0) {
            const item = document.createElement('div');
            item.className = 'staging-item';
            item.textContent = char.name;
            item.style.padding = "5px 10px";
            item.style.border = "1px solid #ccc";
            item.style.borderRadius = "4px";
            item.style.cursor = "grab";
            item.style.background = "#fdfdfd";
            item.draggable = true;
            item.addEventListener('dragstart', (e) => e.dataTransfer.setData('text/plain', char.id));
            listEl.appendChild(item);
        }
    });
}

function setupMapControls() {
    const mapViewport = document.getElementById('map-viewport');
    const gameMap = document.getElementById('game-map');
    if (!mapViewport || !gameMap) return;

    mapViewport.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; });
    mapViewport.addEventListener('drop', (e) => {
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
    });

    const zIn = document.getElementById('zoom-in-btn');
    const zOut = document.getElementById('zoom-out-btn');
    const rView = document.getElementById('reset-view-btn');
    if(zIn) zIn.onclick = () => { visualScale = Math.min(visualScale + 0.1, 3.0); renderVisualMap(); };
    if(zOut) zOut.onclick = () => { visualScale = Math.max(visualScale - 0.1, 0.5); renderVisualMap(); };
    if(rView) rView.onclick = () => { visualScale = 1.0; visualOffsetX = 0; visualOffsetY = 0; renderVisualMap(); };

    let isPanning = false, startX, startY;
    mapViewport.addEventListener('mousedown', (e) => {
        if (e.target.closest('.map-token')) return;
        isPanning = true; startX = e.clientX - visualOffsetX; startY = e.clientY - visualOffsetY;
    });
    window.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        e.preventDefault();
        visualOffsetX = e.clientX - startX; visualOffsetY = e.clientY - startY;
        renderVisualMap();
    });
    window.addEventListener('mouseup', () => isPanning = false);
}

function selectVisualToken(charId) {
    document.querySelectorAll('.map-token').forEach(el => el.classList.remove('selected'));
    const token = document.querySelector(`.map-token[data-id="${charId}"]`);
    if(token) token.classList.add('selected');
}

// --- 対決モーダル等は既存のまま ---
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