/* static/js/visual/visual_wide.js */

// ============================================
// Wide Match Logic (Visual)
// ============================================

window.visualWideState = {
    attackerId: null,
    isDeclared: false
};

/**
 * 広域宣言モーダル (Visual版)
 * 誰が広域攻撃を行うかを予約する画面
 */
window.openVisualWideDeclarationModal = function () {
    const existing = document.getElementById('visual-wide-decl-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'visual-wide-decl-modal';
    backdrop.className = 'modal-backdrop';

    let listHtml = '';
    battleState.characters.forEach(char => {
        if (char.hp <= 0) return;
        // 未配置キャラクターは除外
        if (char.x < 0 || char.y < 0) return;

        // hasWideSkill check (Assumed Global or Utility)
        if (typeof hasWideSkill === 'function' && !hasWideSkill(char)) return;

        const typeColor = char.type === 'ally' ? '#007bff' : '#dc3545';
        listHtml += `
            <div style="padding: 10px; border-bottom: 1px solid #eee; display:flex; align-items:center;">
                <input type="checkbox" class="visual-wide-check" value="${char.id}" style="transform:scale(1.3); margin-right:15px;">
                <span style="font-weight:bold; color:${typeColor}; font-size:1.1em;">${char.name}</span>
                <span style="margin-left:auto; color:#666;">SPD: ${char.totalSpeed || char.speedRoll || 0}</span>
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
                <p>今ラウンド、広域攻撃を行うキャラクターを選択してください。<br>
                ※GMまたは全員が確認ボタンを押すと確定します。</p>
                <div style="border: 1px solid #ddd; border-radius: 4px;">${listHtml}</div>
            </div>
            <div style="padding: 15px; background: #f8f9fa; text-align: right; border-radius: 0 0 8px 8px;">
                <button id="visual-wide-confirm" class="duel-btn primary" style="width:100%;">決定 (確認)</button>
            </div>
        </div>
    `;

    document.body.appendChild(backdrop);
    const confirmBtn = document.getElementById('visual-wide-confirm');
    confirmBtn.onclick = () => {
        const checks = backdrop.querySelectorAll('.visual-wide-check');
        const ids = Array.from(checks).filter(c => c.checked).map(c => c.value);

        socket.emit('request_wide_modal_confirm', { room: currentRoomName, wideUserIds: ids });

        confirmBtn.disabled = true;
        confirmBtn.textContent = "確認済み: 他プレイヤー待機中...";
        confirmBtn.classList.remove('primary');
        confirmBtn.classList.add('secondary');
    };
}

/**
 * 広域攻撃実行モーダル (Visual版) - 抜本修正版
 * 攻撃側がスキルを選択し、各防御側が対応を宣言する画面
 */
window.openVisualWideMatchModal = function (attackerId) {
    const char = battleState.characters.find(c => c.id === attackerId);
    if (!char) return;

    window.visualWideState.attackerId = attackerId;
    window.visualWideState.isDeclared = false;

    const existing = document.getElementById('visual-wide-match-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'visual-wide-match-modal';
    backdrop.className = 'modal-backdrop';

    let skillOptions = '<option value="">-- スキルを選択 --</option>';

    let lockedSkillId = null;
    if (char.special_buffs && Array.isArray(char.special_buffs)) {
        const lockBuff = char.special_buffs.find(b =>
            (b.buff_id === 'Bu-05' || b.name === '再回避ロック') &&
            (b.delay === 0 || b.delay === '0') &&
            (b.lasting > 0 || b.lasting === '1')
        );
        if (lockBuff && lockBuff.skill_id) {
            lockedSkillId = lockBuff.skill_id;
        }
    }

    if (char.commands && window.allSkillData) {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        while ((match = regex.exec(char.commands)) !== null) {
            const sId = match[1];
            const sName = match[2];

            if (lockedSkillId && sId !== lockedSkillId) continue;

            const sData = window.allSkillData[sId];
            // isWideSkillData check (Assumed Global or Utility)
            if (sData && typeof isWideSkillData === 'function' && isWideSkillData(sData)) {
                skillOptions += `<option value="${sId}">${sId}: ${sName}</option>`;
            }
        }
    }

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

    calcBtn.onclick = () => {
        const skillId = skillSelect.value;
        if (!skillId) return alert("スキルを選択してください");

        attackerCmdInput.value = "計算中...";
        attackerCmdInput.style.color = "#888";
        attackerCmdInput.dataset.raw = "";
        if (attackerDescArea) attackerDescArea.innerHTML = "";

        window.visualWideState.isDeclared = false;
        if (declareBtn) {
            declareBtn.disabled = true;
            declareBtn.textContent = "宣言";
            declareBtn.classList.remove('locked', 'btn-danger');
            declareBtn.classList.add('btn-outline-danger');
        }
        executeBtn.disabled = true;

        socket.emit('request_skill_declaration', {
            room: currentRoomName,
            prefix: 'visual_wide_attacker',
            actor_id: attackerId,
            target_id: attackerId,
            skill_id: skillId,
            commit: false
        });

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

    declareBtn.onclick = () => {
        if (!attackerCmdInput.value || attackerCmdInput.value.includes("計算中") || attackerCmdInput.value.startsWith("エラー")) {
            return;
        }

        window.visualWideState.isDeclared = true;

        skillSelect.disabled = true;
        calcBtn.disabled = true;
        declareBtn.disabled = true;
        declareBtn.textContent = "宣言済";
        declareBtn.classList.add('locked');
        attackerCmdInput.style.backgroundColor = "#e8f0fe";

        executeBtn.disabled = false;
    };

    executeBtn.onclick = () => {
        if (!window.visualWideState.isDeclared) {
            return alert("攻撃側の宣言が完了していません");
        }

        const defenderRows = defendersArea.querySelectorAll('.wide-defender-row');
        const defendersData = [];
        defenderRows.forEach(row => {
            const defId = row.dataset.id;
            const cmdInput = row.querySelector('.v-wide-def-cmd');
            const skillId = row.querySelector('.v-wide-def-skill').value;
            const rawCmd = cmdInput.dataset.raw || "";
            defendersData.push({ id: defId, skillId: skillId || "", command: rawCmd });
        });

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
                commandActor: attackerRawCmd,
                defenders: defendersData
            });
            backdrop.remove();

            setTimeout(() => {
                socket.emit('request_next_turn', { room: currentRoomName });
            }, 1000);
        }
    };
}

/**
 * 防御側カード生成
 */
window.renderVisualWideDefenders = function (attackerId, mode) {
    const area = document.getElementById('v-wide-defenders-area');
    area.innerHTML = '';
    const attacker = battleState.characters.find(c => c.id === attackerId);
    const targetType = attacker.type === 'ally' ? 'enemy' : 'ally';
    const targets = battleState.characters.filter(c => c.type === targetType && c.hp > 0 && c.x >= 0 && c.y >= 0);

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
                    const skillId = m[1];
                    const skillName = m[2];

                    if (window.allSkillData && window.allSkillData[skillId]) {
                        const skillData = window.allSkillData[skillId];
                        if (skillData.tags && skillData.tags.includes('即時発動')) continue;
                        if (skillData.tags && (skillData.tags.includes('広域-個別') || skillData.tags.includes('広域-合算'))) continue;
                    }
                    opts += `<option value="${skillId}">${skillId}: ${skillName}</option>`;
                }
            }
        }

        const row = document.createElement('div');
        row.className = 'wide-defender-row';
        row.dataset.id = tgt.id;
        if (isDefenseLocked) row.style.background = "#f0f0f0";

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

        btnCalc.onclick = () => {
            const sId = skillSel.value;
            statusSpan.textContent = "計算中...";
            btnDeclare.disabled = true;
            btnDeclare.classList.remove('btn-success');
            btnDeclare.classList.add('btn-outline-success');
            btnDeclare.textContent = "宣言";
            cmdInput.style.backgroundColor = "";
            cmdInput.dataset.raw = "";
            if (descArea) descArea.innerHTML = "";

            socket.emit('request_skill_declaration', {
                room: currentRoomName,
                prefix: `visual_wide_def_${tgt.id}`,
                actor_id: tgt.id,
                target_id: attackerId,
                skill_id: sId,
                commit: false
            });
        };

        btnDeclare.onclick = () => {
            skillSel.disabled = true;
            btnCalc.disabled = true;
            btnDeclare.disabled = true;
            btnDeclare.textContent = "宣言済";
            btnDeclare.classList.remove('btn-outline-success');
            btnDeclare.classList.add('btn-success');
            cmdInput.style.backgroundColor = "#e0ffe0";
            statusSpan.textContent = "宣言済";
        };
    });
}

console.log('[visual_wide] Loaded.');
