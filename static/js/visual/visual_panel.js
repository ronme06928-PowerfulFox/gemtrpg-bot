/* static/js/visual/visual_panel.js */

// ============================================
// Render Match Panel from Server State
// ============================================

let _lastRenderedMatchStateStr = "";

window.renderMatchPanelFromState = function (matchData) {
    if (!matchData || !matchData.is_active) {
        const panel = document.getElementById('match-panel');
        if (panel && !panel.classList.contains('collapsed')) {
            // Close logic if needed
        }
        document.getElementById('wide-match-container').style.display = 'none';
        const duelContainer = document.querySelector('.duel-container');
        if (duelContainer) duelContainer.style.display = 'none';

        _lastRenderedMatchStateStr = "";
        return;
    }

    const currentMatchStr = JSON.stringify(matchData);
    if (currentMatchStr === _lastRenderedMatchStateStr) {
        return;
    }
    _lastRenderedMatchStateStr = currentMatchStr;
    console.log("🔄 Rendering Match Panel (State Changed)");

    const panel = document.getElementById('match-panel');
    if (panel) panel.classList.remove('collapsed');

    if (matchData.match_type === 'wide') {
        const duelContainer = document.querySelector('.duel-container');
        if (duelContainer) duelContainer.style.display = 'none';
        if (typeof populateWideMatchPanel === 'function') {
            populateWideMatchPanel(matchData);
        }
    } else {
        document.getElementById('wide-match-container').style.display = 'none';
        const duelContainer = document.querySelector('.duel-container');
        if (duelContainer) duelContainer.style.display = 'flex';
    }

    const shouldAutoExpand = !window._matchPanelAutoExpanded;
    if (shouldAutoExpand && panel.classList.contains('collapsed')) {
        let attacker = battleState.characters?.find(c => c.id === matchData.attacker_id);
        let defender = battleState.characters?.find(c => c.id === matchData.defender_id);

        if (matchData.attacker_snapshot) {
            if (!attacker) {
                attacker = matchData.attacker_snapshot;
            } else {
                attacker = { ...attacker, name: matchData.attacker_snapshot.name, commands: matchData.attacker_snapshot.commands };
            }
        }
        if (matchData.defender_snapshot) {
            if (!defender) {
                defender = matchData.defender_snapshot;
            } else {
                defender = { ...defender, name: matchData.defender_snapshot.name, commands: matchData.defender_snapshot.commands };
            }
        }

        if (!attacker || !defender) {
            console.warn('renderMatchPanelFromState: Character data not ready yet');
            return;
        }

        if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
            console.log('📋 Loading skill data before expanding panel...');
            fetch('/api/get_skill_data')
                .then(res => res.json())
                .then(data => {
                    window.allSkillData = data;
                    renderMatchPanelFromState(matchData);
                })
                .catch(e => console.error('Failed to load skill data:', e));
            return;
        }

        openDuelModal(matchData.attacker_id, matchData.defender_id, false, false, attacker, defender);
        window._matchPanelAutoExpanded = true;
    }

    if (matchData.is_active && matchData.attacker_id && matchData.defender_id) {
        if (!duelState.attackerId || !duelState.defenderId) {
            duelState.attackerId = matchData.attacker_id;
            duelState.defenderId = matchData.defender_id;
            duelState.isOneSided = matchData.is_one_sided || false;
        }
    }

    updateMatchPanelContent(matchData);

    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }

    const existingBtn = document.getElementById('force-end-match-btn');
    if (existingBtn) existingBtn.remove();
    const existingWideBtn = document.getElementById('wide-force-end-match-btn');
    if (existingWideBtn) existingWideBtn.remove();

    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

    if (isGM) {
        const headerButtons = document.querySelector('.panel-header-buttons');
        const reloadBtn = document.getElementById('panel-reload-btn');

        if (headerButtons && reloadBtn && !document.getElementById('force-end-match-btn')) {
            const btn = document.createElement('button');
            btn.id = 'force-end-match-btn';
            btn.className = 'panel-reload-btn';
            btn.innerHTML = '⚠️';
            btn.title = 'GM権限でマッチを強制終了します';
            btn.style.cssText = 'background-color:#dc3545; color:white; border:1px solid #bd2130;';

            btn.onclick = function (e) {
                e.stopPropagation();
                if (confirm('【GM権限】マッチを強制終了しますか？\n現在行われているマッチ、または意図せず開いているマッチ画面を閉じます。\nこの操作は元に戻せません。')) {
                    clearMatchPanelContent();
                    collapseMatchPanel();
                    document.getElementById('wide-match-container').style.display = 'none';
                    document.querySelector('.duel-container').style.display = '';

                    if (socket) socket.emit('request_force_end_match', { room: currentRoomName });
                }
            };
            headerButtons.insertBefore(btn, reloadBtn);
        }
    }
}

window.renderCharacterStatsBar = function (char, containerOrId, options = {}) {
    const container = (typeof containerOrId === 'string') ? document.getElementById(containerOrId) : containerOrId;
    if (!container) return;
    if (!char) { container.innerHTML = ''; return; }

    const hp = char.hp || 0;
    const maxHp = char.maxHp || 1;
    const mp = char.mp || 0;
    const maxMp = char.maxMp || 1;
    const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
    const fp = fpState ? fpState.value : 0;

    const isCompact = options.compact || false;
    const theme = options.theme || 'dark';

    const wrapperDisplay = isCompact ? "inline-flex" : "flex";
    const wrapperMargin = isCompact ? "margin-left: 10px;" : "margin-bottom: 8px;";

    let wrapperBg, hpColor, mpColor, fpColor, textColor, textShadow;
    const borderColor = (theme === 'light') ? "rgba(0,0,0,0.1)" : "rgba(255,255,255,0.2)";

    if (theme === 'light') {
        wrapperBg = "rgba(0, 0, 0, 0.05)";
        hpColor = "#28a745";
        mpColor = "#007bff";
        fpColor = "#d39e00";
        textColor = "#555";
        textShadow = "none";
    } else {
        wrapperBg = isCompact ? "rgba(0, 0, 0, 0.7)" : "rgba(0, 0, 0, 0.4)";
        hpColor = "#76ff93";
        mpColor = "#76cfff";
        fpColor = "#ffe676";
        textColor = "#ccc";
        textShadow = "1px 1px 0 #000";
    }

    const fontSizeVal = isCompact ? "0.95em" : "1.1em";
    const fontSizeLabel = isCompact ? "0.6em" : "0.7em";
    const padding = isCompact ? "1px 6px" : "2px 5px";
    const barStyle = `flex: 1; padding: ${padding}; text-align: center; border-right: 1px solid ${borderColor}; display: flex; align-items: baseline; justify-content: center; gap: 3px;`;
    const labelStyle = `font-size: ${fontSizeLabel}; color: ${textColor}; font-weight: normal; line-height: 1; opacity: 0.8;`;
    const valStyle = `font-weight: bold; font-size: ${fontSizeVal}; line-height: 1; text-shadow: ${textShadow};`;
    const wrapperStyle = `display: ${wrapperDisplay}; align-items: center; gap: 0; ${wrapperMargin} background: ${wrapperBg}; border-radius: 4px; border: 1px solid ${borderColor}; overflow: hidden; vertical-align: middle; min-width: max-content;`;

    const makeBlock = (label, val, max, color, isLast) => {
        const borderStyle = isLast ? "border-right: none;" : "";
        const maxPart = max ? `<span style="font-size: 0.7em; color: #888; margin-left: 2px;">/${max}</span>` : "";
        if (isCompact) {
            return `<div style="${barStyle} ${borderStyle} flex-direction: row; align-items: baseline;">
                        <span style="${labelStyle} margin-right: 2px;">${label}</span>
                        <span style="${valStyle} color: ${color};">${val}${maxPart}</span>
                    </div>`;
        } else {
            return `<div style="${barStyle} ${borderStyle} flex-direction: column;">
                        <span style="${labelStyle} margin-bottom: 2px;">${label}</span>
                        <span style="${valStyle} color: ${color};">${val}${maxPart}</span>
                    </div>`;
        }
    };

    container.innerHTML = `<div style="${wrapperStyle}">
        ${makeBlock("HP", hp, maxHp, hpColor, false)}
        ${makeBlock("MP", mp, maxMp, mpColor, false)}
        ${makeBlock("FP", fp, null, fpColor, true)}
    </div>`;
}

window.updateMatchPanelContent = function (matchData) {
    console.log('[MatchPanel] Updating content:', matchData);

    ['attacker', 'defender'].forEach(side => {
        const sideData = matchData[`${side}_data`];
        const isDeclared = matchData[`${side}_declared`] || false;
        const charId = side === 'attacker' ? matchData.attacker_id : matchData.defender_id;

        if (sideData) {
            const nameEl = document.getElementById(`duel-${side}-name`);
            const currentName = nameEl ? nameEl.textContent : "";
            let correctName = "";
            let correctChar = null;
            if (side === 'attacker') {
                if (matchData.attacker_snapshot) {
                    correctName = matchData.attacker_snapshot.name;
                    correctChar = matchData.attacker_snapshot;
                }
            } else {
                if (matchData.defender_snapshot) {
                    correctName = matchData.defender_snapshot.name;
                    correctChar = matchData.defender_snapshot;
                }
            }

            if (correctName && (!currentName || currentName.startsWith('Character') || currentName !== correctName)) {
                if (nameEl) nameEl.textContent = correctName;
                const statusEl = document.getElementById(`duel-${side}-status`);
                if (statusEl && correctChar) {
                    statusEl.innerHTML = generateStatusIconsHTML(correctChar);
                }
                renderCharacterStatsBar(correctChar, `duel-${side}-stats`);
                const skillSelect = document.getElementById(`duel-${side}-skill`);
                if (skillSelect && skillSelect.options.length <= 1 && correctChar && correctChar.commands) {
                    populateCharSkillSelect(correctChar, `duel-${side}-skill`);
                }
                if (skillSelect && sideData && sideData.skill_id) {
                    if (skillSelect.value !== sideData.skill_id) {
                        skillSelect.value = sideData.skill_id;
                    }
                }
            }

            const targetId = side === 'attacker' ? matchData.attacker_id : matchData.defender_id;
            const charObj = battleState.characters.find(c => c.id === targetId);
            if (charObj) {
                renderCharacterStatsBar(charObj, `duel-${side}-stats`);
            }

            if (nameEl && targetId) {
                nameEl.style.cursor = "pointer";
                nameEl.title = "クリックで詳細を表示";
                nameEl.onclick = (e) => {
                    e.stopPropagation();
                    showCharacterDetail(targetId);
                };
            }

            if (sideData.final_command) {
                const previewEl = document.getElementById(`duel-${side}-preview`);
                if (previewEl) {
                    const cmdEl = previewEl.querySelector('.preview-command');
                    const rangeEl = previewEl.querySelector('.preview-damage');

                    if (cmdEl) cmdEl.textContent = sideData.final_command;
                    if (rangeEl) {
                        if (sideData.min_damage !== undefined && sideData.max_damage !== undefined) {
                            let damageText = `Range: ${sideData.min_damage} ~ ${sideData.max_damage}`;
                            let basePowerMod = 0;
                            if (sideData.power_breakdown && sideData.power_breakdown.base_power_mod) {
                                basePowerMod = sideData.power_breakdown.base_power_mod;
                            } else if (sideData.skill_details && sideData.skill_details.base_power_mod) {
                                basePowerMod = sideData.skill_details.base_power_mod;
                            }

                            if (basePowerMod !== 0) {
                                damageText += `\n[基礎威力 ${basePowerMod > 0 ? '+' : ''}${basePowerMod}]`;
                            }

                            if (sideData.senritsu_dice_reduction && sideData.senritsu_dice_reduction > 0) {
                                damageText += `\n(戦慄: ダイス-${sideData.senritsu_dice_reduction})`;
                            }
                            if (sideData.correction_details && sideData.correction_details.length > 0) {
                                sideData.correction_details.forEach(d => {
                                    const sign = d.value > 0 ? '+' : '';
                                    damageText += `\n[${d.source} ${sign}${d.value}]`;
                                });
                            }
                            rangeEl.style.whiteSpace = 'pre-line';
                            rangeEl.textContent = damageText;
                        } else {
                            rangeEl.textContent = "";
                        }
                    }
                    previewEl.classList.add('ready');
                }
                if (side === 'attacker') duelState.attackerCommand = sideData.final_command;
                else duelState.defenderCommand = sideData.final_command;
            }

            if (sideData.skill_id) {
                const skillSelect = document.getElementById(`duel-${side}-skill`);
                if (skillSelect) {
                    if (skillSelect.value !== sideData.skill_id) {
                        skillSelect.value = sideData.skill_id;
                    }
                    let skillDataToUse = null;
                    if (sideData.skill_details) {
                        skillDataToUse = sideData.skill_details;
                    } else if (window.allSkillData && sideData.skill_id) {
                        skillDataToUse = window.allSkillData[sideData.skill_id];
                    }
                    if (skillDataToUse) {
                        if (sideData.final_command) {
                            const descArea = document.getElementById(`duel-${side}-skill-desc`);
                            if (descArea) descArea.innerHTML = formatSkillDetailHTML(skillDataToUse);
                        } else {
                            updateSkillDescription(side, skillDataToUse);
                        }
                    }
                }
            }
        }

        const declareBtn = document.getElementById(`duel-${side}-declare-btn`);
        const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
        const skillSelect = document.getElementById(`duel-${side}-skill`);

        if (isDeclared) {
            if (declareBtn) {
                declareBtn.textContent = 'Locked';
                declareBtn.classList.add('locked');
                declareBtn.disabled = true;
            }
            if (calcBtn) calcBtn.disabled = true;
            if (skillSelect) skillSelect.disabled = true;
            if (side === 'attacker') duelState.attackerLocked = true;
            else duelState.defenderLocked = true;
        } else {
            const canControl = canControlCharacter(charId);

            const sSelect = document.getElementById(`duel-${side}-skill`);
            const currentSkillId = sSelect ? sSelect.value : "";
            let hasCalcResult = !!(sideData && sideData.final_command);

            if (!hasCalcResult && canControl && window._duelLocalCalcCache && window._duelLocalCalcCache[side]) {
                const cached = window._duelLocalCalcCache[side];
                if (cached.char_id === charId && cached.skill_id === currentSkillId) {
                    updateDuelUI(side, { ...cached.data, enableButton: true });
                    hasCalcResult = true;
                }
            }

            if (declareBtn) {
                declareBtn.textContent = '宣言';
                declareBtn.classList.remove('locked');
                declareBtn.disabled = !(hasCalcResult && canControl);
            }
            if (calcBtn) {
                calcBtn.disabled = !canControl;
            }
            if (skillSelect) {
                skillSelect.disabled = !canControl;
            }
            if (side === 'attacker') duelState.attackerLocked = false;
            else duelState.defenderLocked = false;
        }
    });
}

window.openDuelModal = function (attackerId, defenderId, isOneSided = false, emitSync = true, attackerObj = null, defenderObj = null) {
    let attacker = attackerObj || battleState.characters.find(c => c.id === attackerId);
    let defender = defenderObj || battleState.characters.find(c => c.id === defenderId);

    if (!attacker && battleState.active_match?.attacker_snapshot?.id === attackerId) {
        attacker = battleState.active_match.attacker_snapshot;
    }
    if (!defender && battleState.active_match?.defender_snapshot?.id === defenderId) {
        defender = battleState.active_match.defender_snapshot;
    }

    if (!attacker || !defender) return;

    if (emitSync) {
        socket.emit('open_match_modal', {
            room: currentRoomName,
            match_type: 'duel',
            attacker_id: attackerId,
            defender_id: defenderId
        });
        return;
    }

    duelState = {
        attackerId, defenderId,
        attackerLocked: false, defenderLocked: false,
        isOneSided: false,
        attackerCommand: null, defenderCommand: null
    };

    window._duelLocalCalcCache = { attacker: null, defender: null };

    if (!battleState.active_match) {
        battleState.active_match = {
            is_active: false,
            match_type: 'duel',
            attacker_id: null,
            defender_id: null,
            targets: [],
            attacker_data: {},
            defender_data: {}
        };
    }
    battleState.active_match.is_active = true;
    battleState.active_match.match_type = 'duel';
    battleState.active_match.attacker_id = attackerId;
    battleState.active_match.defender_id = defenderId;

    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }

    resetDuelUI();
    duelState.isOneSided = isOneSided;
    document.getElementById('duel-attacker-name').textContent = attacker.name;
    document.getElementById('duel-attacker-status').innerHTML = generateStatusIconsHTML(attacker);
    populateCharSkillSelect(attacker, 'duel-attacker-skill');
    if (isOneSided) {
        document.getElementById('duel-defender-name').textContent = `${defender.name} (行動済み)`;
        document.getElementById('duel-defender-status').innerHTML = generateStatusIconsHTML(defender);
    } else {
        document.getElementById('duel-defender-name').textContent = defender.name;
        document.getElementById('duel-defender-status').innerHTML = generateStatusIconsHTML(defender);
    }

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
    expandMatchPanel();

    if (duelState.attackerLocked) lockSide('attacker');
    if (duelState.defenderLocked) lockSide('defender');

    // Add AI Suggest Button for GM (Attacker Side)
    if (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM') {
        const attackerSide = document.getElementById('duel-attacker-controls');
        const btnContainer = attackerSide ? attackerSide.querySelector('.duel-control-btns') : null;
        if (btnContainer && !document.getElementById('duel-ai-suggest-btn')) {
            const aiBtn = document.createElement('button');
            aiBtn.id = 'duel-ai-suggest-btn';
            aiBtn.textContent = 'AI Suggest';
            aiBtn.className = 'duel-btn'; // Reuse base class
            aiBtn.style.cssText = 'background: #17a2b8; color: white; margin-left: 5px; font-size: 0.8em; padding: 2px 8px;';
            aiBtn.onclick = () => {
                socket.emit('request_ai_suggest_skill', {
                    room: currentRoomName,
                    charId: attackerId // Server expects 'charId'
                });
                aiBtn.textContent = 'Thinking...';
                aiBtn.disabled = true;
                setTimeout(() => {
                    aiBtn.textContent = 'AI Suggest';
                    aiBtn.disabled = false;
                }, 1000);
            };
            btnContainer.appendChild(aiBtn);
        }

        // Ensure button is not duplicated if re-opened
        // The check !document.getElementById('duel-ai-suggest-btn') handles it globally,
        // but if modal content is reset/cleared, it might be gone.
        // resetDuelUI doesn't clear buttons, but openDuelModal might rely on static HTML.
        // Actually, renderMatchPanelFromState might clear things? No, it updates content.
        // If the button persists, we are good. If not, we re-add.
        // But since ID is unique, if we switch match, we might need to remove old button?
        // Actually, openDuelModal is called when match opens.
        // If we close and open another match, the previous button might still be there if we don't clear it.
        // But wait, the button is added to 'duel-attacker-controls' in the DOM.
        // Does closeMatchPanel clear DOM? No, just hides/resets values.
        // So the button persists.
        // We should remove it first to be safe (or check if it exists).
        // Since we check ID, it won't duplicate.
    }
}

window.expandMatchPanel = function () {
    const panel = document.getElementById('match-panel');
    if (!panel) return;
    panel.classList.remove('collapsed');
    panel.classList.add('expanded');
    if (typeof updateActionDock === 'function') updateActionDock();
}

window.collapseMatchPanel = function () {
    const panel = document.getElementById('match-panel');
    if (!panel) return;
    panel.classList.remove('expanded');
    panel.classList.add('collapsed');
    if (typeof updateActionDock === 'function') updateActionDock();
}

window.toggleMatchPanel = function () {
    const panel = document.getElementById('match-panel');
    if (!panel) return;
    if (panel.classList.contains('collapsed')) expandMatchPanel();
    else collapseMatchPanel();
}

window.reloadMatchPanel = function () {
    console.log('🔄 Reloading match panel from current state');
    if (!battleState || !battleState.active_match) return;
    const matchData = battleState.active_match;
    if (matchData.is_active) {
        window._matchPanelAutoExpanded = false;
        renderMatchPanelFromState(matchData);
    }
}

window.closeMatchPanel = function (emitSync = false) {
    if (window._permissionEnforcerInterval) {
        clearInterval(window._permissionEnforcerInterval);
        window._permissionEnforcerInterval = null;
    }
    clearMatchPanelContent();
    collapseMatchPanel();
    if (battleState.active_match) {
        battleState.active_match.is_active = false;
    }
    if (emitSync) {
        socket.emit('close_match_modal', { room: currentRoomName });
    }
}

window.clearMatchPanelContent = function () {
    resetDuelUI();
    document.getElementById('duel-attacker-name').textContent = 'Character A';
    document.getElementById('duel-defender-name').textContent = 'Character B';
    duelState = {
        attackerId: null, defenderId: null,
        attackerLocked: false, defenderLocked: false,
        isOneSided: false,
        attackerCommand: null, defenderCommand: null
    };
}

window.resetDuelUI = function () {
    ['attacker', 'defender'].forEach(side => {
        const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
        const declBtn = document.getElementById(`duel-${side}-declare-btn`);
        const preview = document.getElementById(`duel-${side}-preview`);
        const skillSelect = document.getElementById(`duel-${side}-skill`);
        const descArea = document.getElementById(`duel-${side}-skill-desc`);

        if (descArea) descArea.innerHTML = "";
        if (calcBtn) calcBtn.disabled = false;
        if (declBtn) {
            declBtn.disabled = true; declBtn.textContent = "宣言";
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

window.populateCharSkillSelect = function (char, elementId) {
    const selectEl = document.getElementById(elementId);
    if (!selectEl || !char.commands) return;
    selectEl.innerHTML = '';
    const regex = /【(.*?)\s+(.*?)】/g;
    let match;

    let isConfused = false;
    if (char.special_buffs && Array.isArray(char.special_buffs)) {
        isConfused = char.special_buffs.some(b =>
            (b.buff_id === 'Bu-02' || b.name === '混乱' || b.buff_id === 'Bu-03' || b.name.includes('混乱')) &&
            (b.lasting > 0)
        );
    }

    if (isConfused) {
        const option = document.createElement('option');
        option.value = 'S-Confusion';
        option.textContent = '混乱 (行動不能)';
        selectEl.appendChild(option);
        selectEl.onchange = () => {
            updateSkillDescription(elementId.includes('attacker') ? 'attacker' : 'defender', {
                name: '混乱 (行動不能)',
                description: '行動不能です。ターンをスキップします。'
            });
        };
        return;
    }

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

    while ((match = regex.exec(char.commands)) !== null) {
        const skillId = match[1];
        const skillName = match[2];
        if (lockedSkillId && skillId !== lockedSkillId) continue;

        const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
        if (skillData) {
            // Include explicit tag checks
            const tags = skillData.tags || [];
            if (tags.includes('広域') || tags.includes('広域攻撃') || tags.includes('即時発動') || tags.includes('宝石の加護')) continue;

            // Legacy check
            if (typeof isWideSkillData === 'function' && isWideSkillData(skillData)) continue;
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

    selectEl.onchange = () => {
        const skillId = selectEl.value;
        const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
        if (skillData) {
            updateSkillDescription(elementId.includes('attacker') ? 'attacker' : 'defender', skillData);
        }
    };
}

window.updateSkillDescription = function (side, skillData) {
    const descArea = document.getElementById(`duel-${side}-skill-desc`);
    if (descArea) descArea.innerHTML = "";
}

window.setupDuelListeners = function () {
    const attCalcBtn = document.getElementById('duel-attacker-calc-btn');
    if (attCalcBtn) attCalcBtn.onclick = () => sendSkillDeclaration('attacker', false);

    const defCalcBtn = document.getElementById('duel-defender-calc-btn');
    if (defCalcBtn) defCalcBtn.onclick = () => sendSkillDeclaration('defender', false);

    const attDeclBtn = document.getElementById('duel-attacker-declare-btn');
    if (attDeclBtn) attDeclBtn.onclick = () => {
        const btn = document.getElementById('duel-attacker-declare-btn');
        const isImmediate = btn.dataset.isImmediate === 'true';
        sendSkillDeclaration('attacker', true);
        if (!isImmediate) lockSide('attacker');
    };

    const defDeclBtn = document.getElementById('duel-defender-declare-btn');
    if (defDeclBtn) defDeclBtn.onclick = () => {
        const btn = document.getElementById('duel-defender-declare-btn');
        const isImmediate = btn.dataset.isImmediate === 'true';
        sendSkillDeclaration('defender', true);
        if (!isImmediate) lockSide('defender');
    };
}

window.sendSkillDeclaration = function (side, isCommit) {
    if (!battleState || !battleState.active_match) return;
    const match = battleState.active_match;
    const isAttacker = (side === 'attacker');
    const actorId = isAttacker ? match.attacker_id : match.defender_id;
    const targetId = isAttacker ? match.defender_id : match.attacker_id;

    const skillSelect = document.getElementById(`duel-${side}-skill`);
    const skillId = skillSelect ? skillSelect.value : "";
    if (!skillId) { alert("スキルを選択してください。"); return; }

    const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
    const actor = battleState.characters.find(c => c.id === actorId);

    if (skillData && actor && skillData['特記処理']) {
        try {
            const rule = JSON.parse(skillData['特記処理']);
            const tags = skillData.tags || [];
            if (rule.cost && !tags.includes('即時発動')) {
                const findStatusValue = (obj, targetKey) => {
                    if (obj.states) {
                        const state = obj.states.find(s => s.name && targetKey && s.name.toUpperCase() === targetKey.toUpperCase());
                        if (state) return parseInt(state.value);
                    }
                    if (obj[targetKey] !== undefined) return parseInt(obj[targetKey]);
                    if (obj[targetKey.toLowerCase()] !== undefined) return parseInt(obj[targetKey.toLowerCase()]);
                    if (obj.params) {
                        const param = obj.params.find(p => p.label === targetKey);
                        if (param) return parseInt(param.value);
                    }
                    return 0;
                };

                for (const c of rule.cost) {
                    const type = c.type;
                    const val = parseInt(c.value || 0);
                    if (val > 0 && type) {
                        const current = findStatusValue(actor, type);
                        if (current < val) {
                            const previewEl = document.getElementById(`duel-${side}-preview`);
                            const cmdEl = previewEl ? previewEl.querySelector('.preview-command') : null;
                            const dmgEl = previewEl ? previewEl.querySelector('.preview-damage') : null;
                            const descEl = document.getElementById(`duel-${side}-skill-desc`);

                            if (cmdEl && dmgEl) {
                                cmdEl.textContent = "Cost Error";
                                dmgEl.textContent = `${type}不足 (必要:${val})`;
                                previewEl.classList.add('ready');
                            } else if (previewEl) {
                                previewEl.textContent = "Cost Error";
                            }
                            if (descEl) {
                                descEl.innerHTML = `<div style="color: #ff4444; font-weight: bold; padding: 5px; border: 1px solid #ff4444; background: rgba(255,0,0,0.1); border-radius: 4px;">${type}が不足しています<br>(必要: ${val}, 現在: ${current})</div>`;
                            }

                            socket.emit('sync_match_data', {
                                room: currentRoomName,
                                side: side,
                                data: {
                                    skill_id: skillId,
                                    final_command: `${type}不足`,
                                    error: true,
                                    enableButton: false,
                                    declared: false
                                }
                            });
                            const declareBtn = document.getElementById(`duel-${side}-declare-btn`);
                            if (declareBtn) declareBtn.disabled = true;
                            return;
                        }
                    }
                }
            }
        } catch (e) { console.error("Cost check error:", e); }
    }

    socket.emit('request_skill_declaration', {
        room: currentRoomName,
        actor_id: actorId, target_id: targetId,
        skill_id: skillId, modifier: 0,
        prefix: `visual_${side}`,
        commit: isCommit, custom_skill_name: ""
    });
}

window.updateDuelUI = function (side, data) {
    const previewEl = document.getElementById(`duel-${side}-preview`);
    const cmdEl = previewEl.querySelector('.preview-command');
    const dmgEl = previewEl.querySelector('.preview-damage');
    const declareBtn = document.getElementById(`duel-${side}-declare-btn`);
    const descArea = document.getElementById(`duel-${side}-skill-desc`);

    if (data.skill_id) {
        const skillSelect = document.getElementById(`duel-${side}-skill`);
        if (skillSelect && skillSelect.value !== data.skill_id) {
            skillSelect.value = data.skill_id;
        }
    }

    if (data.error) {
        cmdEl.textContent = "Error";
        dmgEl.textContent = data.final_command;
        if (descArea) descArea.innerHTML = "<div style='color:red;'>計算エラー</div>";
        return;
    }

    cmdEl.innerHTML = data.final_command;
    if (data.min_damage !== undefined) {
        let damageText = `Range: ${data.min_damage} ~ ${data.max_damage}`;
        if (data.skill_details && data.skill_details.base_power_mod) {
            const mod = data.skill_details.base_power_mod;
            damageText += `\n[基礎威力 ${mod > 0 ? '+' : ''}${mod}]`;
        }
        if (data.correction_details && data.correction_details.length > 0) {
            data.correction_details.forEach(d => {
                const sign = d.value > 0 ? '+' : '';
                damageText += `\n[${d.source} ${sign}${d.value}]`;
            });
        }
        if (data.senritsu_dice_reduction && data.senritsu_dice_reduction > 0) {
            damageText += `\n[ダイス威力 -${data.senritsu_dice_reduction}] (戦慄)`;
        }
        dmgEl.style.whiteSpace = 'pre-line';
        dmgEl.textContent = damageText;
    } else {
        dmgEl.textContent = "Ready";
    }
    previewEl.classList.add('ready');

    if (descArea && data.skill_details) {
        descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
    }

    if (declareBtn && data.is_immediate) {
        declareBtn.dataset.isImmediate = 'true';
        declareBtn.textContent = '即時発動 (Execute)';
        declareBtn.classList.add('immediate-btn');
    } else if (declareBtn) {
        declareBtn.dataset.isImmediate = 'false';
        declareBtn.textContent = '宣言';
        declareBtn.classList.remove('immediate-btn');
    }

    const shouldEnable = data.enableButton !== undefined ? data.enableButton : true;
    const isLocked = (side === 'attacker' && duelState.attackerLocked) || (side === 'defender' && duelState.defenderLocked);

    if (declareBtn) {
        if (isLocked) {
            declareBtn.disabled = true;
            declareBtn.textContent = "Locked";
        } else if (shouldEnable) {
            declareBtn.disabled = false;
        } else {
            declareBtn.disabled = true;
            declareBtn.title = '相手が計算したスキルです';
        }
    }

    if (previewEl && data.senritsu_penalty !== undefined) {
        previewEl.dataset.senritsuPenalty = data.senritsu_penalty;
    }
    if (data.enableButton) {
        if (!window._duelLocalCalcCache) window._duelLocalCalcCache = { attacker: null, defender: null };
        window._duelLocalCalcCache[side] = {
            data: data,
            skill_id: data.skill_id,
            char_id: side === 'attacker' ? duelState.attackerId : duelState.defenderId
        };
    }

    if (side === 'attacker') duelState.attackerCommand = data.final_command;
    else duelState.defenderCommand = data.final_command;
}

window.canControlCharacter = function (charId) {
    if (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM') return true;
    if (typeof battleState === 'undefined' || !battleState.characters) return false;
    const char = battleState.characters.find(c => c.id === charId);
    const idMatch = (typeof currentUserId !== 'undefined' && char && char.owner_id && char.owner_id === currentUserId);
    const nameMatch = (char && char.owner === currentUsername);
    return idMatch || nameMatch;
}

window.applyMatchDataSync = function (side, data) {
    if (data.skill_id !== undefined) {
        const skillSelect = document.getElementById(`duel-${side}-skill`);
        if (skillSelect && skillSelect.value !== data.skill_id) {
            skillSelect.value = data.skill_id;
        }
    }

    if (data.final_command !== undefined) {
        const isError = data.error === true;
        updateDuelUI(side, {
            prefix: `visual_${side}`,
            final_command: data.final_command,
            min_damage: data.min_damage,
            max_damage: data.max_damage,
            is_immediate: data.is_immediate,
            skill_details: data.skill_details,
            senritsu_penalty: data.senritsu_penalty,
            correction_details: data.correction_details,
            enableButton: isError ? false : (data.declared ? false : canControlCharacter(side === 'attacker' ? duelState.attackerId : duelState.defenderId)),
            error: isError
        });

        if (side === 'attacker') duelState.attackerCommand = data.final_command;
        else duelState.defenderCommand = data.final_command;

        if (data.declared) {
            lockSide(side);
        }
    }
}

window.lockSide = function (side) {
    const btn = document.getElementById(`duel-${side}-declare-btn`);
    const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
    const select = document.getElementById(`duel-${side}-skill`);
    if (btn) { btn.textContent = "Locked"; btn.classList.add('locked'); btn.disabled = true; }
    if (calcBtn) calcBtn.disabled = true;
    if (select) select.disabled = true;
    if (side === 'attacker') duelState.attackerLocked = true;
    if (side === 'defender') duelState.defenderLocked = true;
}

window.executeMatch = function () {
    setTimeout(() => {
        if (!battleState || !battleState.active_match) return;
        const match = battleState.active_match;
        const attackerName = document.getElementById('duel-attacker-name').textContent;
        const defenderName = document.getElementById('duel-defender-name').textContent;
        const stripTags = (str) => str ? str.replace(/<[^>]*>?/gm, '') : "2d6";

        socket.emit('request_match', {
            room: currentRoomName,
            actorIdA: match.attacker_id, actorIdD: match.defender_id,
            actorNameA: attackerName, actorNameD: defenderName,
            commandA: stripTags(duelState.attackerCommand),
            commandD: stripTags(duelState.defenderCommand),
            senritsuPenaltyA: parseInt(document.getElementById('duel-attacker-preview')?.dataset?.senritsuPenalty || 0),
            senritsuPenaltyD: parseInt(document.getElementById('duel-defender-preview')?.dataset?.senritsuPenalty || 0)
        });

        setTimeout(() => { closeDuelModal(); }, 500);
        setTimeout(() => { socket.emit('request_next_turn', { room: currentRoomName }); }, 1000);
    }, 300);
}

console.log('[visual_panel] Loaded.');
