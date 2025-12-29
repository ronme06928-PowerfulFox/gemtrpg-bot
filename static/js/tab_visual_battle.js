/* static/js/tab_visual_battle.js */

// --- グローバル変数 ---
let visualScale = 1.0;
let visualOffsetX = 0;
let visualOffsetY = 0;
const GRID_SIZE = 96;

// 状態異常定義 (ファイル名とCSSクラス)
const STATUS_CONFIG = {
    '出血': { icon: 'bleed.png', css: 'status-bleed' },     // 赤
    '破裂': { icon: 'rupture.png', css: 'status-rupture' }, // 黄緑
    '亀裂': { icon: 'fissure.png', css: 'status-fissure' }, // 青
    '戦慄': { icon: 'fear.png', css: 'status-fear' },       // 空色
    '荊棘': { icon: 'thorns.png', css: 'status-thorns' }    // 濃い緑
};

// --- 対決(Duel)用状態管理 ---
let duelState = {
    attackerId: null, defenderId: null,
    attackerLocked: false, defenderLocked: false,
    isOneSided: false,
    attackerCommand: null, defenderCommand: null
};

// --- タブ初期化関数 ---
async function setupVisualBattleTab() {
    console.log("Setting up Visual Battle Tab...");

    // スキルデータの読み込み
    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        try {
            const res = await fetch('/api/get_skill_data');
            if (res.ok) {
                window.allSkillData = await res.json();
                console.log("Skill data loaded:", Object.keys(window.allSkillData).length);
            }
        } catch (e) {
            console.error("Failed to load skill data:", e);
        }
    }

    setupMapControls();

    const nextBtn = document.getElementById('visual-next-turn-btn');
    if (nextBtn) {
        const newBtn = nextBtn.cloneNode(true);
        nextBtn.parentNode.replaceChild(newBtn, nextBtn);
        newBtn.addEventListener('click', () => {
            if (confirm("手番を終了して次に回しますか？")) {
                socket.emit('request_next_turn', { room: currentRoomName });
            }
        });
    }

    renderVisualMap();
    renderStagingArea();

    if (typeof socket !== 'undefined') {
        if (window.visualBattleStateListener) socket.off('state_updated', window.visualBattleStateListener);
        window.visualBattleStateListener = (state) => {
            if (document.getElementById('visual-battle-container')) {
                renderVisualMap();
                renderStagingArea();
            }
        };
        socket.on('state_updated', window.visualBattleStateListener);

        if (window.visualBattleSkillListener) socket.off('skill_declaration_result', window.visualBattleSkillListener);
        window.visualBattleSkillListener = (data) => {
            if (!data.prefix || !data.prefix.startsWith('visual_')) return;
            const side = data.prefix.replace('visual_', '');
            updateDuelUI(side, data);
        };
        socket.on('skill_declaration_result', window.visualBattleSkillListener);
    }
}

// --- マップ描画 & タイムライン ---
function renderVisualMap() {
    const mapEl = document.getElementById('game-map');
    const tokenLayer = document.getElementById('map-token-layer');
    if (!mapEl || !tokenLayer) return;

    tokenLayer.innerHTML = '';
    renderTimeline();

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

// --- タイムライン描画 ---
function renderTimeline() {
    const timelineEl = document.getElementById('visual-timeline-area');
    if (!timelineEl) return;
    timelineEl.innerHTML = '';

    if (!battleState.timeline || battleState.timeline.length === 0) {
        timelineEl.innerHTML = '<div style="color:#888; padding:10px;">No Timeline</div>';
        return;
    }

    const header = document.createElement('div');
    header.className = 'sidebar-header';
    header.innerHTML = `<span>TimeLine</span> <span>R: ${battleState.round || 0}</span>`;
    timelineEl.appendChild(header);

    const currentTurnId = battleState.turn_char_id;

    battleState.timeline.forEach(charId => {
        const char = battleState.characters.find(c => c.id === charId);
        if (!char) return;

        const item = document.createElement('div');
        item.className = `timeline-item ${char.type || 'NPC'}`;
        if (char.id === currentTurnId) item.classList.add('active-turn');
        if (char.hasActed) item.classList.add('acted');
        if (char.hp <= 0) item.style.opacity = '0.4';

        item.innerHTML = `
            <span class="name">${char.name}</span>
            <span class="speed">SPD: ${char.speedRoll}</span>
        `;
        item.addEventListener('click', () => showCharacterDetail(char.id));
        timelineEl.appendChild(item);
    });
}

// --- トークン作成 ---
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

    // FP
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
                // 画像あり (指定の色クラスを適用)
                iconsHtml += `
                    <div class="mini-status-icon ${config.css}">
                        <img src="images/${config.icon}" alt="${s.name}">
                        <div class="mini-status-badge">${s.value}</div>
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

        <div class="token-body">
            <span>${char.name.charAt(0)}</span>
        </div>

        <div class="token-label" title="${char.name}">${char.name}</div>

        <div class="token-status-overlay">
            ${iconsHtml}
        </div>
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

/* static/js/tab_visual_battle.js 内の showCharacterDetail 関数を修正 */

function showCharacterDetail(charId) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    // 既存モーダル削除
    const existing = document.getElementById('char-detail-modal-backdrop');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'char-detail-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';

    // パラメータ表示
    let paramsHtml = '';
    if (Array.isArray(char.params)) {
        paramsHtml = char.params.map(p => `${p.label}:${p.value}`).join(' / ');
    } else if (char.params && typeof char.params === 'object') {
        paramsHtml = Object.entries(char.params).map(([k,v]) => `${k}:${v}`).join(' / ');
    } else {
        paramsHtml = 'なし';
    }

    const fpVal = (char.states.find(s => s.name === 'FP') || {}).value || 0;

    // 状態異常(States)
    let statesHtml = '';
    char.states.forEach(s => {
        if(['HP','MP','FP'].includes(s.name)) return;
        if(s.value === 0) return;
        statesHtml += `<div class="detail-buff-item">${s.name}: ${s.value}</div>`;
    });
    if (!statesHtml) statesHtml = '<span style="color:#999; font-size:0.9em;">なし</span>';

    // ★修正: 特殊効果 / バフ表示ロジック
    let specialBuffsHtml = '';
    if (char.special_buffs && char.special_buffs.length > 0) {
        char.special_buffs.forEach((b, index) => {
            // 1. 名称の整形: アンダースコア区切りでベース名を取得 (例: "そこが弱いの？_Crack1" -> "そこが弱いの？")
            let displayName = b.name;
            if (displayName.includes('_')) {
                displayName = displayName.split('_')[0];
            }

            // 2. 残りラウンド数 (duration または round プロパティを確認)
            // 99以上の場合は「永続」扱いとして表示しない場合が多いですが、必要なら表示条件を変えてください
            let durationVal = (b.duration !== undefined) ? b.duration : b.round;
            let durationHtml = "";

            if (durationVal !== undefined && durationVal !== null && durationVal < 99) {
                durationHtml = `<span class="buff-duration-badge">${durationVal}R</span>`;
            }

            // 3. 説明文の取得 (カタログ参照)
            let desc = b.description || ""; // サーバーから来ていればそれを使う

            // サーバーになければカタログ (BUFF_DATA) を検索
            // ※ buff_data.js がロードされている必要があります
            if (!desc && typeof window.BUFF_DATA !== 'undefined') {
                const buffInfo = window.BUFF_DATA[displayName];
                if (buffInfo && buffInfo.description) {
                    desc = buffInfo.description;
                }
            }

            // ユニークID
            const buffUniqueId = `buff-detail-${char.id}-${index}`;

            specialBuffsHtml += `
                <div style="width: 100%;">
                    <div class="detail-buff-item special" onclick="toggleBuffDesc('${buffUniqueId}')">
                        <span style="flex-grow:1; font-weight:bold;">${displayName}</span>
                        ${durationHtml}
                        <span style="font-size:0.8em; opacity:0.7;">▼</span>
                    </div>
                    <div id="${buffUniqueId}" class="buff-desc-box" style="display:none;">
                        ${desc || "(説明文なし)"}
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
                <div class="detail-stat-box">
                    <span class="detail-stat-label">HP</span>
                    <span class="detail-stat-val" style="color:#28a745;">${char.hp} / ${char.maxHp}</span>
                </div>
                <div class="detail-stat-box">
                    <span class="detail-stat-label">MP</span>
                    <span class="detail-stat-val" style="color:#007bff;">${char.mp} / ${char.maxMp}</span>
                </div>
                <div class="detail-stat-box">
                    <span class="detail-stat-label">FP</span>
                    <span class="detail-stat-val" style="color:#ffc107;">${fpVal}</span>
                </div>
            </div>

            <div class="detail-section">
                <h4>Parameters</h4>
                <div style="font-family:monospace; background:#f9f9f9; padding:8px; border-radius:4px; font-weight:bold;">
                    ${paramsHtml}
                </div>
            </div>

            <div class="detail-section">
                <h4>状態異常 (Stack)</h4>
                <div class="detail-buff-list">
                    ${statesHtml}
                </div>
            </div>

            <div class="detail-section">
                <h4>特殊効果 / バフ (Click for Info)</h4>
                <div class="detail-buff-list" style="display:block;">
                    ${specialBuffsHtml}
                </div>
            </div>

            <div class="detail-section">
                <h4>Skills</h4>
                <div style="font-size:0.9em; max-height:100px; overflow-y:auto; border:1px solid #eee; padding:5px; white-space: pre-wrap;">${char.commands || "なし"}</div>
            </div>
        </div>
    `;

    document.body.appendChild(backdrop);
    const closeFunc = () => backdrop.remove();
    backdrop.querySelector('.detail-close-btn').onclick = closeFunc;
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeFunc();
    });
}

// ★追加: バフ説明文の開閉トグル関数
function toggleBuffDesc(elementId) {
    const el = document.getElementById(elementId);
    if (el) {
        el.style.display = (el.style.display === 'none') ? 'block' : 'none';
    }
}

// --- 待機所 (変更なし) ---
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
            item.draggable = true;
            item.addEventListener('dragstart', (e) => e.dataTransfer.setData('text/plain', char.id));
            listEl.appendChild(item);
        }
    });
}

// --- マップ操作 (変更なし) ---
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

// --- 対決モーダル (変更なし) ---
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
        sendSkillDeclaration('attacker', true);
        lockSide('attacker');
    };
    document.getElementById('duel-defender-declare-btn').onclick = () => {
        sendSkillDeclaration('defender', true);
        lockSide('defender');
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
    if (data.min_damage !== undefined) {
        dmgEl.textContent = `Range: ${data.min_damage} ~ ${data.max_damage}`;
    } else {
        dmgEl.textContent = "Ready";
    }
    previewEl.classList.add('ready');
    if (declareBtn) declareBtn.disabled = false;

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
        } else if (duelState.attackerLocked) {
            statusEl.textContent = "Waiting for Defender...";
        } else if (duelState.defenderLocked) {
            statusEl.textContent = "Waiting for Attacker...";
        }
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