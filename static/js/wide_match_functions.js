
// ============================================================
// ★ Wide Match Functions (Phase 11.2)
// ============================================================

// --- Wide Match Panel Control ---
function expandWideMatchPanel() {
    const panel = document.getElementById('wide-match-panel');
    if (panel) {
        panel.classList.remove('collapsed');
        panel.classList.add('expanded');
        const toggleBtn = document.getElementById('wide-panel-toggle-btn');
        if (toggleBtn) toggleBtn.textContent = '▼';
    }
}

function collapseWideMatchPanel() {
    const panel = document.getElementById('wide-match-panel');
    if (panel) {
        panel.classList.remove('expanded');
        panel.classList.add('collapsed');
        const toggleBtn = document.getElementById('wide-panel-toggle-btn');
        if (toggleBtn) toggleBtn.textContent = '▶';
    }
}

function toggleWideMatchPanel() {
    const panel = document.getElementById('wide-match-panel');
    if (panel && panel.classList.contains('collapsed')) {
        expandWideMatchPanel();
    } else {
        collapseWideMatchPanel();
    }
}

// --- openWideMatchPanel ---
function openWideMatchPanel(attackerId, defenderIds, emitSync = true) {
    if (!battleState || !battleState.characters) return;

    const attacker = battleState.characters.find(c => c.id === attackerId);
    if (!attacker) return;

    // Expand panel
    expandWideMatchPanel();

    // Initialize if needed
    if (!battleState.active_match || battleState.active_match.match_type !== 'wide') {
        battleState.active_match = {
            is_active: true,
            match_type: 'wide',
            attacker_id: attackerId,
            defender_ids: defenderIds,
            attacker_data: {},
            attacker_declared: false,
            defenders: []
        };
    }

    // Emit to server if requested
    if (emitSync) {
        socket.emit('open_wide_match_modal', {
            room: currentRoomName,
            attacker_id: attackerId,
            defender_ids: defenderIds
        });
    }

    // Render from state
    if (battleState.active_match) {
        renderWideMatchPanelFromState(battleState.active_match);
    }

    // Update action dock
    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }
}

// --- renderWideMatchPanelFromState (Stateless) ---
function renderWideMatchPanelFromState(matchData) {
    if (!matchData || matchData.match_type !== 'wide') {
        return;
    }

    // Attacker section
    const attackerId = matchData.attacker_id;
    let attacker = battleState.characters?.find(c => c.id === attackerId);
    if (!attacker && matchData.attacker_snapshot) {
        attacker = matchData.attacker_snapshot;
    }

    if (attacker) {
        const nameEl = document.getElementById('wide-attacker-name');
        if (nameEl) nameEl.textContent = attacker.name;

        const statusEl = document.getElementById('wide-attacker-status');
        if (statusEl) statusEl.innerHTML = generateStatusIconsHTML(attacker);

        populateWideSkillSelect(attacker, 'wide-attacker-skill');

        // Restore attacker data
        if (matchData.attacker_data && matchData.attacker_data.skill_id) {
            const skillSelect = document.getElementById('wide-attacker-skill');
            if (skillSelect) {
                skillSelect.value = matchData.attacker_data.skill_id;

                if (matchData.attacker_data.final_command) {
                    const previewEl = document.getElementById('wide-attacker-preview');
                    if (previewEl) {
                        previewEl.querySelector('.preview-command').textContent = matchData.attacker_data.final_command;

                        // ★ Phase 3: 補正内訳を改行形式で表示
                        // Format: Range: X~Y (Command)
                        // [Corrections...]
                        let damageText = "";
                        if (matchData.attacker_data.damage_range_text) {
                            damageText = `Range: ${matchData.attacker_data.damage_range_text}`;
                        } else {
                            damageText = `Range: ${matchData.attacker_data.min_damage} ~ ${matchData.attacker_data.max_damage}`;
                        }

                        damageText += ` (${matchData.attacker_data.final_command})`;

                        const pb = matchData.attacker_data.power_breakdown;
                        if (pb) {
                            if (pb.base_power_mod && pb.base_power_mod !== 0) {
                                damageText += `\n[基礎威力 ${pb.base_power_mod > 0 ? '+' : ''}${pb.base_power_mod}]`;
                            }
                        }
                        if (matchData.attacker_data.senritsu_dice_reduction && matchData.attacker_data.senritsu_dice_reduction > 0) {
                            damageText += `\n(戦慄: ダイス-${matchData.attacker_data.senritsu_dice_reduction})`;
                        }

                        // ★追加: 物理/魔法/威力補正の内訳を表示
                        if (matchData.attacker_data.correction_details && matchData.attacker_data.correction_details.length > 0) {
                            matchData.attacker_data.correction_details.forEach(d => {
                                const sign = d.value > 0 ? '+' : '';
                                damageText += `\n[${d.source} ${sign}${d.value}]`;
                            });
                        }

                        const dmgEl = previewEl.querySelector('.preview-damage');
                        if (dmgEl) {
                            dmgEl.style.whiteSpace = 'pre-line';
                            dmgEl.textContent = damageText;
                        }
                    }

                    // Show skill details if calculated
                    const descEl = document.getElementById('wide-attacker-skill-desc');
                    if (descEl && matchData.attacker_data.skill_details) {
                        descEl.innerHTML = formatSkillDetailHTML(matchData.attacker_data.skill_details);
                    }
                }
            }
        }

        // Update buttons
        const calcBtn = document.getElementById('wide-attacker-calc-btn');
        const declBtn = document.getElementById('wide-attacker-declare-btn');
        const canControl = canControlCharacter(attackerId);

        if (calcBtn) calcBtn.disabled = !canControl || matchData.attacker_declared;
        if (declBtn) {
            declBtn.disabled = !(matchData.attacker_data?.final_command && canControl && !matchData.attacker_declared);
            if (matchData.attacker_declared) {
                declBtn.textContent = 'Locked';
                declBtn.classList.add('locked');
            } else {
                declBtn.textContent = 'Declare';
                declBtn.classList.remove('locked');
            }
        }
    }

    // Defenders section
    renderWideDefendersList(matchData);
}

// --- renderWideDefendersList ---
function renderWideDefendersList(matchData) {
    const listEl = document.getElementById('wide-defenders-list');
    if (!listEl) return;

    listEl.innerHTML = ''; // Clear

    const defenders = matchData.defenders || [];
    const defenderSnapshots = matchData.defender_snapshots || {};

    defenders.forEach((defData, index) => {
        const defId = defData.id;
        let defChar = battleState.characters?.find(c => c.id === defId);
        if (!defChar && defenderSnapshots[defId]) {
            defChar = defenderSnapshots[defId];
        }

        if (!defChar) return;

        const card = document.createElement('div');
        card.className = 'wide-defender-card';
        card.dataset.defenderId = defId;
        card.dataset.defenderIndex = index;

        // Is locked (already acted)?
        const isLocked = defData.is_locked || false;

        card.innerHTML = `
            <div class="wide-defender-header">
                <div class="wide-char-name">${defChar.name}</div>
                ${isLocked ? '<span class="locked-badge">行動済み</span>' : ''}
            </div>
            <div class="wide-form-group">
                <label>Skill:</label>
                <select class="wide-select wide-defender-skill" ${isLocked ? 'disabled' : ''}></select>
            </div>
            <div class="wide-control-btns">
                <button class="wide-btn calc wide-defender-calc" ${isLocked ? 'disabled' : ''}>Calc</button>
                <button class="wide-btn declare wide-defender-declare" disabled>Declare</button>
            </div>
            <div class="wide-preview-area wide-defender-preview">
                <div class="preview-command">---</div>
                <div class="preview-damage">---</div>
            </div>
            <div class="skill-detail-display wide-defender-skill-desc"></div>
        `;

        listEl.appendChild(card);

        // Populate skill select
        const selectEl = card.querySelector('.wide-defender-skill');
        populateWideSkillSelect(defChar, null, selectEl);

        // Restore data
        if (defData.data && defData.data.skill_id) {
            selectEl.value = defData.data.skill_id;

            if (defData.data.final_command) {
                const previewEl = card.querySelector('.wide-defender-preview');
                previewEl.querySelector('.preview-command').textContent = defData.data.final_command;

                // ★ Phase 3: 補正内訳を改行形式で表示
                // Format: Range: X~Y (Command)
                let damageText = "";
                if (defData.data.damage_range_text) {
                    damageText = `Range: ${defData.data.damage_range_text}`;
                } else {
                    damageText = `Range: ${defData.data.min_damage} ~ ${defData.data.max_damage}`;
                }

                damageText += ` (${defData.data.final_command})`;

                // correction_detailsがあればそちらを使用
                const corrections = defData.data.correction_details;
                const pb = defData.data.power_breakdown;

                if (!corrections || corrections.length === 0) {
                    if (pb) {
                        if (pb.base_power_mod && pb.base_power_mod !== 0) {
                            damageText += `\n[基礎威力 ${pb.base_power_mod > 0 ? '+' : ''}${pb.base_power_mod}]`;
                        }
                    }
                }

                if (defData.data.senritsu_dice_reduction && defData.data.senritsu_dice_reduction > 0) {
                    damageText += `\n(戦慄: ダイス-${defData.data.senritsu_dice_reduction})`;
                }

                // ★追加: 物理/魔法/威力補正の内訳を表示
                if (corrections && corrections.length > 0) {
                    corrections.forEach(d => {
                        const sign = d.value > 0 ? '+' : '';
                        damageText += `\n[${d.source} ${sign}${d.value}]`;
                    });
                }

                const dmgEl = previewEl.querySelector('.preview-damage');
                if (dmgEl) {
                    dmgEl.style.whiteSpace = 'pre-line';
                    dmgEl.textContent = damageText;
                }

                const descEl = card.querySelector('.wide-defender-skill-desc');
                if (descEl && defData.data.skill_details) {
                    descEl.innerHTML = formatSkillDetailHTML(defData.data.skill_details);
                }
            }
        }

        // Update buttons based on permissions and lock status
        const canControl = canControlCharacter(defId);
        const calcBtn = card.querySelector('.wide-defender-calc');
        const declBtn = card.querySelector('.wide-defender-declare');

        if (calcBtn) calcBtn.disabled = isLocked || !canControl || defData.declared;
        if (declBtn) {
            declBtn.disabled = isLocked || !(defData.data?.final_command && canControl && !defData.declared);
            if (defData.declared) {
                declBtn.textContent = 'Locked';
                declBtn.classList.add('locked');
            } else {
                declBtn.textContent = 'Declare';
                declBtn.classList.remove('locked');
            }
        }
    });
}

// --- populateWideSkillSelect ---
function populateWideSkillSelect(char, elementId = null, element = null) {
    const selectEl = element || (elementId ? document.getElementById(elementId) : null);
    if (!selectEl || !char.commands) return;

    selectEl.innerHTML = '';
    const regex = /【(.*?)\s+(.*?)】/g;

    // ★ Phase 10: 混乱(Confusion)判定
    // 混乱バフがある場合、スキル選択肢を「混乱 (行動不能)」のみにする
    let isConfused = false;
    if (char.special_buffs && Array.isArray(char.special_buffs)) {
        isConfused = char.special_buffs.some(b =>
            (b.buff_id === 'Bu-02' || b.name === '混乱' || b.buff_id === 'Bu-03' || b.name.includes('混乱')) &&
            (b.lasting > 0)
        );
    }

    if (isConfused) {
        selectEl.innerHTML = '';
        const option = document.createElement('option');
        option.value = 'S-Confusion';
        option.textContent = '混乱 (行動不能)';
        selectEl.appendChild(option);
        return;
    }

    let match;
    while ((match = regex.exec(char.commands)) !== null) {
        const skillId = match[1];
        const skillName = match[2];

        // ★ Phase 9.2: 再回避ロックフィルタ (UIフィルタリング - 広域攻撃共通)
        // ループ外で判定するのが効率的だが、char変数はループ外にあるのでここで判定
        if (char.special_buffs && Array.isArray(char.special_buffs)) {
            const lockBuff = char.special_buffs.find(b =>
                (b.buff_id === 'Bu-05' || b.name === '再回避ロック') &&
                (b.delay === 0 || b.delay === '0') &&
                (b.lasting > 0 || b.lasting === '1')
            );
            if (lockBuff && lockBuff.skill_id && skillId !== lockBuff.skill_id) {
                continue;
            }
        }

        // Skip wide-area skills in wide match (they should use normal skills)
        const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
        if (skillData && isWideSkillData(skillData)) {
            continue;
        }

        const option = document.createElement('option');
        option.value = skillId;
        option.textContent = `${skillId}: ${skillName}`;
        selectEl.appendChild(option);
    }

    if (selectEl.options.length === 0) {
        const placeholder = document.createElement('option');
        placeholder.textContent = '(スキルなし)';
        placeholder.disabled = true;
        selectEl.appendChild(placeholder);
    }
}

// --- sendWideSkillDeclaration (Stateless) ---
function sendWideSkillDeclaration(side, defenderIndex, isCommit) {
    if (!battleState || !battleState.active_match || battleState.active_match.match_type !== 'wide') {
        return;
    }

    const match = battleState.active_match;
    const isAttacker = (side === 'attacker');

    let actorId, targetId, skillId, prefix;

    if (isAttacker) {
        actorId = match.attacker_id;
        // For attacker, target can be first defender (or null for wide attacks)
        targetId = match.defender_ids && match.defender_ids.length > 0 ? match.defender_ids[0] : null;

        const skillSelect = document.getElementById('wide-attacker-skill');
        skillId = skillSelect ? skillSelect.value : '';
        prefix = 'wide_attacker';
    } else {
        // Defender
        const defender = match.defenders[defenderIndex];
        if (!defender) return;

        actorId = defender.id;
        targetId = match.attacker_id;

        const card = document.querySelector(`.wide-defender-card[data-defender-index="${defenderIndex}"]`);
        if (!card) return;

        const skillSelect = card.querySelector('.wide-defender-skill');
        skillId = skillSelect ? skillSelect.value : '';
        prefix = `wide_defender_${actorId}`;
    }

    if (!skillId) {
        alert("スキルを選択してください。");
        return;
    }

    socket.emit('request_skill_declaration', {
        room: currentRoomName,
        prefix: prefix,
        actor_id: actorId,
        target_id: targetId,
        skill_id: skillId,
        commit: isCommit
    });
}

// --- setupWideMatchListeners (Robust Polling Compatible) ---
function setupWideMatchListeners() {
    // Panel toggle
    const toggleBtn = document.getElementById('wide-panel-toggle-btn');
    if (toggleBtn) {
        toggleBtn.onclick = toggleWideMatchPanel;
    }

    // Panel reload
    const reloadBtn = document.getElementById('wide-panel-reload-btn');
    if (reloadBtn) {
        reloadBtn.onclick = () => {
            if (battleState && battleState.active_match && battleState.active_match.match_type === 'wide') {
                renderWideMatchPanelFromState(battleState.active_match);
            }
        };
    }

    // Attacker buttons
    const attCalcBtn = document.getElementById('wide-attacker-calc-btn');
    if (attCalcBtn) {
        attCalcBtn.onclick = () => sendWideSkillDeclaration('attacker', null, false);
    }

    const attDeclBtn = document.getElementById('wide-attacker-declare-btn');
    if (attDeclBtn) {
        attDeclBtn.onclick = () => sendWideSkillDeclaration('attacker', null, true);
    }

    // Defender buttons (event delegation)
    const defendersList = document.getElementById('wide-defenders-list');
    if (defendersList) {
        defendersList.onclick = (e) => {
            const card = e.target.closest('.wide-defender-card');
            if (!card) return;

            const defenderIndex = parseInt(card.dataset.defenderIndex);

            if (e.target.classList.contains('wide-defender-calc')) {
                sendWideSkillDeclaration('defender', defenderIndex, false);
            } else if (e.target.classList.contains('wide-defender-declare')) {
                sendWideSkillDeclaration('defender', defenderIndex, true);
            }
        };
    }
}

// Export (if needed)
if (typeof window !== 'undefined') {
    window.openWideMatchPanel = openWideMatchPanel;
    window.renderWideMatchPanelFromState = renderWideMatchPanelFromState;
    window.sendWideSkillDeclaration = sendWideSkillDeclaration;
    window.setupWideMatchListeners = setupWideMatchListeners;
}
