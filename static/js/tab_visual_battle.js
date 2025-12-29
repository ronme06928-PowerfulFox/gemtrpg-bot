/* static/js/tab_visual_battle.js */

// --- グローバル変数 ---
let visualScale = 1.0;
let visualOffsetX = 0;
let visualOffsetY = 0;
const GRID_SIZE = 96;

// --- 対決(Duel)用状態管理 ---
let duelState = {
    attackerId: null,
    defenderId: null,
    attackerLocked: false,
    defenderLocked: false,
    isOneSided: false,
    attackerCommand: null,
    defenderCommand: null
};

// --- タブ初期化関数 (main.jsから呼ばれる) ---
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

    // UIイベント設定
    setupMapControls();

    // ターン終了ボタンの設定
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

    // 初回描画
    renderVisualMap();
    renderStagingArea();

    // ★修正: ソケットイベント設定 (自己修復型に変更)
    if (typeof socket !== 'undefined') {

        // 1. 状態更新イベント (state_updated)
        // 重複登録を防ぐため、既存のリスナーがあれば解除してから登録する
        if (window.visualBattleStateListener) {
            socket.off('state_updated', window.visualBattleStateListener);
        }
        // リスナー関数を作成して保存
        window.visualBattleStateListener = (state) => {
            // このタブが表示されている時だけ処理する
            if (document.getElementById('visual-battle-container')) {
                renderVisualMap();
                renderStagingArea();
            }
        };
        // 登録
        socket.on('state_updated', window.visualBattleStateListener);


        // 2. スキル宣言結果イベント (skill_declaration_result)
        // 他のタブ（テキストバトル側）で全削除される可能性があるため、
        // タブを開くたびに必ず再登録を行うようにする。
        if (window.visualBattleSkillListener) {
            socket.off('skill_declaration_result', window.visualBattleSkillListener);
        }

        window.visualBattleSkillListener = (data) => {
            // ビジュアルバトルからのリクエスト結果だけを処理
            if (!data.prefix || !data.prefix.startsWith('visual_')) return;
            const side = data.prefix.replace('visual_', '');
            updateDuelUI(side, data);
        };

        socket.on('skill_declaration_result', window.visualBattleSkillListener);

        // フラグ管理 (window.visualBattleSocketInitialized) は廃止
    }
}

// --- マップ描画 ---
function renderVisualMap() {
    const mapEl = document.getElementById('game-map');
    const tokenLayer = document.getElementById('map-token-layer');
    if (!mapEl || !tokenLayer) return;

    tokenLayer.innerHTML = '';
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

// --- トークン作成 ---
function createMapToken(char) {
    const token = document.createElement('div');
    token.className = `map-token ${char.color || 'NPC'}`;
    token.dataset.id = char.id;

    token.style.left = `${char.x * GRID_SIZE + 4}px`;
    token.style.top = `${char.y * GRID_SIZE + 4}px`;

    const maxHp = char.maxHp || 1; const hp = char.hp || 0;
    const hpPercent = Math.max(0, Math.min(100, (hp / maxHp) * 100));
    const maxMp = char.maxMp || 1; const mp = char.mp || 0;
    const mpPercent = Math.max(0, Math.min(100, (mp / maxMp) * 100));

    token.innerHTML = `
        <div class="token-bars">
            <div class="token-bar" title="HP: ${hp}/${maxHp}">
                <div class="token-bar-fill hp" style="width: ${hpPercent}%"></div>
            </div>
            <div class="token-bar" title="MP: ${mp}/${maxMp}">
                <div class="token-bar-fill mp" style="width: ${mpPercent}%"></div>
            </div>
        </div>
        <div class="token-body"><span>${char.name.charAt(0)}</span></div>
        <div class="token-label" title="${char.name}">${char.name}</div>
    `;

    token.draggable = true;
    token.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', char.id);
        e.dataTransfer.effectAllowed = 'move';
        token.classList.add('dragging');
    });
    token.addEventListener('dragend', () => token.classList.remove('dragging'));
    token.addEventListener('click', (e) => { e.stopPropagation(); selectVisualToken(char.id); });

    token.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'link'; });

    token.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();

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

// --- 待機所描画 ---
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

// --- マップ操作 ---
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

// ==========================================
//   対決(Duel) モーダル関連ロジック
// ==========================================

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
    resetDuelUI(); // ロック解除

    document.getElementById('duel-attacker-name').textContent = attacker.name;
    document.getElementById('duel-defender-name').textContent = defender.name;

    // 全スキル表示
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
    document.getElementById('duel-status-message').textContent = "Setup Phase";
}

function populateCharSkillSelect(char, elementId) {
    const select = document.getElementById(elementId);
    select.innerHTML = '';

    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        const opt = document.createElement('option');
        opt.value = "";
        opt.text = "(Skill Data Loading...)";
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
        opt.value = "";
        opt.text = "(有効なスキルがありません)";
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

    if (!skillId) {
        alert("スキルを選択してください。");
        return;
    }

    socket.emit('request_skill_declaration', {
        room: currentRoomName,
        actor_id: actorId, target_id: targetId,
        skill_id: skillId,
        modifier: 0,
        prefix: `visual_${side}`,
        commit: isCommit,
        custom_skill_name: ""
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
            actorIdA: duelState.attackerId,
            actorIdD: duelState.defenderId,
            actorNameA: attackerName,
            actorNameD: defenderName,
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