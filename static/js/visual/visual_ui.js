/* static/js/visual/visual_ui.js */

// --- Log Rendering ---

const _escapeResolveLogHtml = (value) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const _toResolveNum = (value, fallback = 0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
};

const _signedResolveNum = (value) => {
    const n = _toResolveNum(value, 0);
    return (n >= 0) ? `+${n}` : `${n}`;
};

const _resolveSidePowerLines = (side) => {
    const snapshot = (side && typeof side.power_snapshot === 'object') ? side.power_snapshot : {};
    const breakdown = (side && typeof side.power_breakdown === 'object') ? side.power_breakdown : {};

    const hasSnapshot = Object.keys(snapshot).length > 0;
    const hasBreakdown = Object.keys(breakdown).length > 0;
    if (!hasSnapshot && !hasBreakdown) {
        return {
            line1: '計算データなし',
            line2: '補正: 基礎威力+0 / ダイス威力+0 / 最終威力+0'
        };
    }

    const base = _toResolveNum(snapshot.base_power_after_mod, 0);
    const dice = _toResolveNum(snapshot.dice_power_after_roll, 0);
    const physical = _toResolveNum(snapshot.physical_power, 0);
    const magical = _toResolveNum(snapshot.magical_power, 0);
    const attr = physical + magical;
    const flatBonus = _toResolveNum(snapshot.flat_power_bonus, 0);
    const final = _toResolveNum(snapshot.final_power, 0);
    const ruleBase = _toResolveNum(breakdown.rule_power_bonus, 0);

    const baseShown = base + ruleBase;
    const flatShown = flatBonus - ruleBase;
    const baseMod = _toResolveNum(breakdown.base_power_mod, 0) + ruleBase;
    const diceMod = _toResolveNum(breakdown.dice_bonus_power, 0);
    const finalMod = _toResolveNum(breakdown.final_power_mod, flatShown);

    return {
        line1: `基礎${baseShown} + ダイス${dice} + 属性${_signedResolveNum(attr)} + 定数${_signedResolveNum(flatShown)} = 合計${final}`,
        line2: `補正: 基礎威力${_signedResolveNum(baseMod)} / ダイス威力${_signedResolveNum(diceMod)} / 最終威力${_signedResolveNum(finalMod)}`
    };
};

window.openResolveTraceDetailModal = function (logData) {
    const detail = (logData && typeof logData.resolve_trace_detail === 'object') ? logData.resolve_trace_detail : null;
    if (!detail) return;

    const existing = document.getElementById('resolve-trace-detail-modal');
    if (existing) existing.remove();

    const attacker = (detail.attacker && typeof detail.attacker === 'object') ? detail.attacker : {};
    const defender = (detail.defender && typeof detail.defender === 'object') ? detail.defender : {};
    const attackerLines = _resolveSidePowerLines(attacker);
    const defenderLines = _resolveSidePowerLines(defender);
    const oneSided = !!detail.one_sided;

    const renderSide = (side, lines, roleClass) => {
        const name = _escapeResolveLogHtml(side?.name || '-');
        const command = _escapeResolveLogHtml(side?.command || '-');
        return `
            <div class="resolve-trace-side ${roleClass}">
                <div class="resolve-trace-side-name">${name}</div>
                <div class="resolve-trace-side-command">${command}</div>
                <div class="resolve-trace-side-power-main">${_escapeResolveLogHtml(lines.line1)}</div>
                <div class="resolve-trace-side-power-sub">${_escapeResolveLogHtml(lines.line2)}</div>
            </div>
        `;
    };

    const overlay = document.createElement('div');
    overlay.id = 'resolve-trace-detail-modal';
    overlay.className = 'resolve-trace-modal-backdrop';
    overlay.innerHTML = `
        <div class="resolve-trace-modal">
            <div class="resolve-trace-modal-header">
                <div class="resolve-trace-modal-title">${_escapeResolveLogHtml(detail.kind_label || '解決ログ詳細')}</div>
                <button type="button" class="resolve-trace-modal-close">×</button>
            </div>
            <div class="resolve-trace-modal-meta">
                <span>結果: ${_escapeResolveLogHtml(detail.outcome_label || '-')}</span>
                <span>総ダメージ: ${_escapeResolveLogHtml(String(_toResolveNum(detail.total_damage, 0)))}</span>
            </div>
            <div class="resolve-trace-modal-body">
                ${renderSide(attacker, attackerLines, 'attacker')}
                <div class="resolve-trace-side-vs">VS</div>
                ${oneSided
            ? `<div class="resolve-trace-side defender"><div class="resolve-trace-side-name">${_escapeResolveLogHtml(defender?.name || '-')}</div><div class="resolve-trace-side-command">一方攻撃のため対抗ロールなし</div><div class="resolve-trace-side-power-main">-</div><div class="resolve-trace-side-power-sub">-</div></div>`
            : renderSide(defender, defenderLines, 'defender')}
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const close = () => {
        document.removeEventListener('keydown', onKeydown, true);
        overlay.remove();
    };
    const onKeydown = (evt) => {
        if (evt.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKeydown, true);

    overlay.addEventListener('click', (evt) => {
        if (evt.target === overlay) close();
    });
    const closeBtn = overlay.querySelector('.resolve-trace-modal-close');
    if (closeBtn) closeBtn.addEventListener('click', close);
};

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
    } else if (!logData.secret && String(logData.source || '') === 'resolve_trace') {
        const detail = (logData && typeof logData.resolve_trace_detail === 'object')
            ? logData.resolve_trace_detail
            : null;
        const kindLabel = String(detail?.kind_label || '解決');
        const attackerName = String(detail?.attacker?.name || '攻撃側');
        const defenderName = String(detail?.defender?.name || (detail?.one_sided ? '対象' : '防御側'));
        const matchupLabel = detail?.one_sided
            ? `${attackerName} -> ${defenderName}`
            : `${attackerName} vs ${defenderName}`;
        const buttonLabel = `[${kindLabel}] ${matchupLabel} / 詳細を表示`;
        logLine.innerHTML = `<button type="button" class="resolve-trace-log-btn">${_escapeResolveLogHtml(buttonLabel)}</button>`;
        const btn = logLine.querySelector('.resolve-trace-log-btn');
        if (btn) {
            if (!detail) {
                btn.disabled = true;
            } else {
                btn.addEventListener('click', () => {
                    if (typeof window.openResolveTraceDetailModal === 'function') {
                        window.openResolveTraceDetailModal(logData);
                    }
                });
            }
        }
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
    window._lastLogCount = Array.isArray(logs) ? logs.length : 0;
    logArea.scrollTop = logArea.scrollHeight;
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 30);
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 80);
}

window.appendVisualLogBatch = function (logs) {
    const logArea = document.getElementById('visual-log-area');
    if (!logArea || !Array.isArray(logs) || logs.length === 0) return;

    const filter = window.currentVisualLogFilter || 'all';
    logs.forEach(log => appendVisualLogLine(logArea, log, filter));
    window._lastLogCount = Number(window._lastLogCount || 0) + logs.length;
    logArea.scrollTop = logArea.scrollHeight;
};

// --- Resolve Trace Modal Enhancement ---
;(() => {
    const sidePower = (side) => {
        const snapshot = (side && typeof side.power_snapshot === 'object') ? side.power_snapshot : {};
        const breakdown = (side && typeof side.power_breakdown === 'object') ? side.power_breakdown : {};
        const base = _toResolveNum(snapshot.base_power_after_mod, 0);
        const dice = _toResolveNum(snapshot.dice_power_after_roll, 0);
        const physical = _toResolveNum(snapshot.physical_power, 0);
        const magical = _toResolveNum(snapshot.magical_power, 0);
        const attr = physical + magical;
        const flatBonus = _toResolveNum(snapshot.flat_power_bonus, 0);
        const final = _toResolveNum(snapshot.final_power, 0);
        const ruleBase = _toResolveNum(breakdown.rule_power_bonus, 0);
        const baseShown = base + ruleBase;
        const flatShown = flatBonus - ruleBase;
        const baseMod = _toResolveNum(breakdown.base_power_mod, 0) + ruleBase;
        const diceMod = _toResolveNum(breakdown.dice_bonus_power, 0);
        const finalMod = _toResolveNum(breakdown.final_power_mod, flatShown);
        return {
            final,
            line1: `基礎${baseShown} + ダイス${dice} + 属性${_signedResolveNum(attr)} + 定数${_signedResolveNum(flatShown)} = 合計${final}`,
            line2: `補正: 基礎威力${_signedResolveNum(baseMod)} / ダイス威力${_signedResolveNum(diceMod)} / 最終威力${_signedResolveNum(finalMod)}`
        };
    };

    const winnerRole = (detail) => {
        const outcome = String(detail?.outcome || '');
        if (outcome === 'attacker_win') return 'attacker';
        if (outcome === 'defender_win') return 'defender';
        return null;
    };

    const outcomeClass = (detail) => {
        const outcome = String(detail?.outcome || '');
        if (outcome === 'draw') return 'is-draw';
        if (outcome === 'attacker_win' || outcome === 'defender_win') return 'is-win';
        return 'is-neutral';
    };

    const skillMeta = (side) => {
        const sideObj = (side && typeof side === 'object') ? side : {};
        const meta = (sideObj.skill_meta && typeof sideObj.skill_meta === 'object') ? sideObj.skill_meta : {};
        const all = (window.allSkillData && typeof window.allSkillData === 'object') ? window.allSkillData : {};
        const skillId = String(sideObj.skill_id || meta.id || '').trim();
        const fallback = (skillId && all[String(skillId)] && typeof all[String(skillId)] === 'object')
            ? all[String(skillId)]
            : {};

        const pick = (...keys) => {
            for (const key of keys) {
                const raw = meta[key] ?? fallback[key] ?? '';
                const s = String(raw || '').trim();
                if (s) return s;
            }
            return '';
        };

        const effects = [];
        const metaEffects = Array.isArray(meta.effects) ? meta.effects : [];
        metaEffects.forEach((e) => {
            if (!e || typeof e !== 'object') return;
            const label = String(e.label || '').trim() || '効果';
            const text = String(e.text || '').trim();
            if (!text) return;
            effects.push({ label, text });
        });

        if (effects.length <= 0) {
            [
                ['コスト', 'cost'],
                ['発動条件', 'activation_cost'],
                ['効果', 'effect'],
                ['発動時効果', 'activation_effect'],
                ['特殊', 'special']
            ].forEach(([label, key]) => {
                const text = String(fallback[key] || '').trim();
                if (!text) return;
                effects.push({ label, text });
            });
        }

        return {
            id: skillId,
            name: String(sideObj.skill_name || pick('name') || '').trim(),
            category: pick('category'),
            distance: pick('distance', 'range'),
            attribute: pick('attribute'),
            effects,
            raw: (fallback && typeof fallback === 'object' && Object.keys(fallback).length > 0) ? fallback : null
        };
    };

    const formatGlossaryText = (value) => {
        const text = String(value || '').trim();
        if (!text) return '';
        if (typeof window.formatGlossaryMarkupToHTML === 'function') {
            return window.formatGlossaryMarkupToHTML(text);
        }
        return _escapeResolveLogHtml(text).replace(/\n/g, '<br>');
    };

    const renderSkill = (meta) => {
        const hasMeta = !!meta?.id || !!meta?.name || !!meta?.category || !!meta?.distance || !!meta?.attribute || (Array.isArray(meta?.effects) && meta.effects.length > 0);
        if (!hasMeta) return '<div class="resolve-trace-skill-empty">スキル詳細なし</div>';

        const skillTitle = [meta.id ? `[${meta.id}]` : '', meta.name || ''].filter(Boolean).join(' ');

        if (meta.raw && typeof window.formatSkillDetailHTML === 'function') {
            const detailHtml = String(window.formatSkillDetailHTML(meta.raw) || '').trim();
            if (detailHtml) {
                return `
                    <details class="resolve-trace-skill-details">
                        <summary>スキル詳細: ${_escapeResolveLogHtml(skillTitle || '表示')}</summary>
                        <div class="resolve-trace-skill-card">
                            ${detailHtml}
                        </div>
                    </details>
                `;
            }
        }

        const chips = [];
        if (meta.category) chips.push(`<span class="resolve-trace-chip">${_escapeResolveLogHtml(meta.category)}</span>`);
        if (meta.distance) chips.push(`<span class="resolve-trace-chip">${_escapeResolveLogHtml(meta.distance)}</span>`);
        if (meta.attribute) chips.push(`<span class="resolve-trace-chip">${_escapeResolveLogHtml(meta.attribute)}</span>`);
        const effects = Array.isArray(meta.effects) ? meta.effects : [];
        const effectsHtml = effects.length > 0
            ? effects.map((e) => `<li><strong>${_escapeResolveLogHtml(e.label || '効果')}</strong>: ${formatGlossaryText(e.text || '')}</li>`).join('')
            : '<li>効果説明なし</li>';

        return `
            <details class="resolve-trace-skill-details">
                <summary>スキル詳細: ${_escapeResolveLogHtml(skillTitle || '表示')}</summary>
                <div class="resolve-trace-skill-card">
                    <div class="resolve-trace-skill-details-body">
                        <div class="resolve-trace-skill-chips">${chips.join('')}</div>
                        <ul class="resolve-trace-skill-effects">${effectsHtml}</ul>
                    </div>
                </div>
            </details>
        `;
    };

    const renderSide = (side, role, detail) => {
        const power = sidePower(side);
        const wRole = winnerRole(detail);
        const sideClass = (wRole === role) ? 'is-winner' : (wRole ? 'is-loser' : 'is-neutral');
        const sMeta = skillMeta(side);
        const slotIndex = _toResolveNum(side?.slot_index_in_actor, NaN);
        const spd = _toResolveNum(side?.slot_speed ?? side?.slot_initiative, NaN);
        return `
            <div class="resolve-trace-side ${role} ${sideClass}">
                <div class="resolve-trace-side-name">${_escapeResolveLogHtml(side?.name || '-')}</div>
                <div class="resolve-trace-side-meta">
                    <span class="resolve-trace-chip strong">合計威力: ${_escapeResolveLogHtml(String(power.final))}</span>
                    <span class="resolve-trace-chip">SPD: ${_escapeResolveLogHtml(Number.isFinite(spd) ? String(spd) : '-')}</span>
                    ${Number.isFinite(slotIndex) ? `<span class="resolve-trace-chip">スロット: #${slotIndex + 1}</span>` : ''}
                </div>
                <div class="resolve-trace-side-command">${_escapeResolveLogHtml(side?.command || '-')}</div>
                <div class="resolve-trace-side-power-main">${_escapeResolveLogHtml(power.line1)}</div>
                <div class="resolve-trace-side-power-sub">${_escapeResolveLogHtml(power.line2)}</div>
                ${renderSkill(sMeta)}
            </div>
        `;
    };

    window.openResolveTraceDetailModal = function (logData) {
        const detail = (logData && typeof logData.resolve_trace_detail === 'object') ? logData.resolve_trace_detail : null;
        if (!detail) return;

        const existing = document.getElementById('resolve-trace-detail-modal');
        if (existing) existing.remove();

        const attacker = (detail.attacker && typeof detail.attacker === 'object') ? detail.attacker : {};
        const defender = (detail.defender && typeof detail.defender === 'object') ? detail.defender : {};
        const oneSided = !!detail.one_sided;
        const attackerFinal = sidePower(attacker).final;
        const defenderFinal = sidePower(defender).final;

        const overlay = document.createElement('div');
        overlay.id = 'resolve-trace-detail-modal';
        overlay.className = 'resolve-trace-modal-backdrop';
        overlay.innerHTML = `
            <div class="resolve-trace-modal">
                <div class="resolve-trace-modal-header">
                    <div class="resolve-trace-modal-title">${_escapeResolveLogHtml(detail.kind_label || '解決ログ詳細')}</div>
                    <button type="button" class="resolve-trace-modal-close">×</button>
                </div>
                <div class="resolve-trace-modal-meta">
                    <span class="resolve-trace-pill ${outcomeClass(detail)}">結果: ${_escapeResolveLogHtml(detail.outcome_label || '-')}</span>
                    <span class="resolve-trace-pill">総ダメージ: ${_escapeResolveLogHtml(String(_toResolveNum(detail.total_damage, 0)))}</span>
                    <span class="resolve-trace-pill">攻撃側合計: ${_escapeResolveLogHtml(String(attackerFinal))}</span>
                    <span class="resolve-trace-pill">防御側合計: ${_escapeResolveLogHtml(String(defenderFinal))}</span>
                </div>
                <div class="resolve-trace-modal-body">
                    ${renderSide(attacker, 'attacker', detail)}
                    <div class="resolve-trace-side-vs">VS</div>
                    ${oneSided
            ? `<div class="resolve-trace-side defender is-neutral"><div class="resolve-trace-side-name">${_escapeResolveLogHtml(defender?.name || '-')}</div><div class="resolve-trace-side-command">一方攻撃のため対抗ロールなし</div><div class="resolve-trace-side-power-main">-</div><div class="resolve-trace-side-power-sub">-</div></div>`
            : renderSide(defender, 'defender', detail)}
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const skillPanels = Array.from(overlay.querySelectorAll('.resolve-trace-skill-details'));
        if (skillPanels.length > 1) {
            let syncing = false;
            skillPanels.forEach((panel) => {
                panel.addEventListener('toggle', () => {
                    if (syncing) return;
                    syncing = true;
                    const nextOpen = !!panel.open;
                    skillPanels.forEach((other) => {
                        if (other !== panel) other.open = nextOpen;
                    });
                    syncing = false;
                });
            });
        }

        const close = () => {
            document.removeEventListener('keydown', onKeydown, true);
            overlay.remove();
        };
        const onKeydown = (evt) => {
            if (evt.key === 'Escape') close();
        };
        document.addEventListener('keydown', onKeydown, true);
        overlay.addEventListener('click', (evt) => {
            if (evt.target === overlay) close();
        });
        const closeBtn = overlay.querySelector('.resolve-trace-modal-close');
        if (closeBtn) closeBtn.addEventListener('click', close);
    };
})();

// --- Round Display ---

window.updateVisualRoundDisplay = function (round) {
    const el = document.getElementById('visual-round-counter');
    if (el) el.textContent = round || 0;
}

// --- Sidebar Controls ---

window.setupVisualSidebarControls = function () {
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');
    const resolveIsGM = () => {
        const attr = (typeof currentUserAttribute !== 'undefined')
            ? currentUserAttribute
            : (typeof window !== 'undefined' ? window.currentUserAttribute : null);
        const role = (typeof window !== 'undefined') ? window.currentUserRole : null;
        const user = (typeof currentUsername !== 'undefined')
            ? currentUsername
            : (typeof window !== 'undefined' ? (window.currentUsername || window.currentUserName) : '');
        const attrNorm = String(attr || '').trim().toUpperCase();
        const roleNorm = String(role || '').trim().toUpperCase();
        return attrNorm === 'GM' || roleNorm === 'GM' || (typeof user === 'string' && /\(GM\)/i.test(user));
    };
    const isGM = resolveIsGM();
    const isBattleOnlyForRoundControls = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';

    if (isGM && !isBattleOnlyForRoundControls) {
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
    } else {
        if (startRBtn) startRBtn.style.display = 'none';
        if (endRBtn) endRBtn.style.display = 'none';
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
    const boBtn = document.getElementById('visual-bo-btn');
    const resetBtn = document.getElementById('visual-reset-btn');
    const statusMsg = document.getElementById('visual-status-msg');
    const isBattleOnlyMode = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
    const canUseResetInRoom = isGM || isBattleOnlyMode;
    const centerCtaId = 'visual-bo-center-cta';
    const runtimeGlobal = (typeof window !== 'undefined') ? window : globalThis;

    // 追加ボタンを表示できるよう、ルーム操作エリアのレイアウトを拡張
    const actionContainer = document.getElementById('visual-room-actions');
    if (actionContainer && !document.getElementById('visual-pve-btn')) {
        // 2カラム固定から折り返し可能なflexレイアウトに変更
        actionContainer.style.display = 'flex';
        actionContainer.style.flexWrap = 'wrap';
        actionContainer.style.gap = '5px';

        actionContainer.style.gap = '5px';

        // PvE/PvP切替はGMのみ表示
        if (isGM) {
            const pveBtn = document.createElement('button');
            pveBtn.id = 'visual-pve-btn';

            const updateBtnText = () => {
                const boMode = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
                const mode = boMode ? 'pve' : ((battleState && battleState.battle_mode) ? battleState.battle_mode : 'pvp');
                pveBtn.textContent = boMode
                    ? '戦闘モード: PvE（固定）'
                    : ((mode === 'pve') ? '戦闘モード: PvE' : '戦闘モード: PvP');
                pveBtn.style.background = (mode === 'pve') ? '#28a745' : '#6c757d'; // Green for PvE, Gray for PvP
                pveBtn.style.color = 'white';
                pveBtn.disabled = boMode;
                pveBtn.style.opacity = boMode ? '0.75' : '1';
                pveBtn.style.cursor = boMode ? 'not-allowed' : 'pointer';
            };

            // 初期表示を遅延反映
            setTimeout(updateBtnText, 500);
            // battleState更新を拾って表示を同期するため、簡易的に定期更新する

            pveBtn.style.cssText = "padding: 5px; font-size: 0.8em; cursor: pointer; border: none; border-radius: 3px; background: #6c757d; color: white; flex: 1; min-width: 60px;";
            pveBtn.onclick = () => {
                const boMode = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
                if (boMode) return;
                const currentMode = (battleState && battleState.battle_mode) ? battleState.battle_mode : 'pvp';
                const nextMode = (currentMode === 'pve') ? 'pvp' : 'pve';
                if (confirm(`戦闘モードを変更しますか？\n${currentMode.toUpperCase()} -> ${nextMode.toUpperCase()}`)) {
                    socket.emit('request_switch_battle_mode', { room: currentRoomName, mode: nextMode });
                    // Optimistic update
                    pveBtn.textContent = (nextMode === 'pve') ? '戦闘モード: PvE' : '戦闘モード: PvP';
                }
            };
            actionContainer.appendChild(pveBtn);

            // 状態変化を追従
            setInterval(updateBtnText, 2000);
        }
    }

    function removeBattleOnlyCenterCta() {
        const exists = document.getElementById(centerCtaId);
        if (exists) exists.remove();
    }
    runtimeGlobal.removeBattleOnlyCenterCta = removeBattleOnlyCenterCta;

    function isBattleOnlyPreparationView() {
        const bs = (battleState && typeof battleState === 'object') ? battleState : {};
        const boMode = String(bs.play_mode || 'normal').toLowerCase() === 'battle_only';
        const bo = (bs.battle_only && typeof bs.battle_only === 'object') ? bs.battle_only : {};
        const status = String(bo.status || 'lobby').trim().toLowerCase();
        const isPreparation = (status === 'lobby' || status === 'draft');
        return boMode && isPreparation;
    }

    function shouldShowBattleOnlyCenterCta() {
        const roomName = String((typeof currentRoomName !== 'undefined' ? currentRoomName : runtimeGlobal.currentRoomName) || '').trim();
        const roomPortal = document.getElementById('room-portal');
        const mainApp = document.getElementById('main-app-container');
        const inRoomView = !!(mainApp && mainApp.style.display !== 'none' && (!roomPortal || roomPortal.style.display === 'none'));
        const hasOpenModal = Array.from(document.querySelectorAll('.modal-backdrop')).some((el) => {
            if (!el || !el.isConnected) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const opacity = Number(style.opacity || '1');
            if (Number.isFinite(opacity) && opacity <= 0) return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        });
        const isVisualTab = !!document.querySelector('.tab-button.active[data-tab="visual"]');
        return !!roomName && inRoomView && isVisualTab && !isGM && isBattleOnlyPreparationView() && !hasOpenModal;
    }

    function openBattleOnlyDraftFromUi() {
        removeBattleOnlyCenterCta();
        const boModeNow = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
        if (boModeNow && !isGM && typeof openBattleOnlyQuickStartModal === 'function') {
            openBattleOnlyQuickStartModal();
            return;
        }
        if (typeof openBattleOnlyDraftModal === 'function') {
            openBattleOnlyDraftModal();
            return;
        }
        statusMsg.textContent = "戦闘専用モーダルを読み込めませんでした。";
    }

    function syncBattleOnlyCenterCta() {
        const exists = document.getElementById(centerCtaId);
        const shouldShow = shouldShowBattleOnlyCenterCta();
        if (!shouldShow) {
            removeBattleOnlyCenterCta();
            return;
        }

        const bo = (battleState && typeof battleState.battle_only === 'object') ? battleState.battle_only : {};
        const status = String(bo.status || 'lobby').trim();
        const statusLabel = (status === 'in_battle') ? '戦闘中' : (status === 'draft' ? '編成中' : '待機');
        const formationId = String(bo.enemy_formation_id || '').trim();

        const cta = exists || document.createElement('div');
        cta.id = centerCtaId;
        cta.style.position = 'fixed';
        cta.style.left = '50%';
        cta.style.top = '50%';
        cta.style.transform = 'translate(-50%, -50%)';
        cta.style.zIndex = '900';
        cta.style.background = 'rgba(17, 24, 39, 0.86)';
        cta.style.color = '#fff';
        cta.style.padding = '10px 12px';
        cta.style.borderRadius = '10px';
        cta.style.border = '1px solid rgba(255,255,255,0.18)';
        cta.style.boxShadow = '0 10px 24px rgba(0,0,0,0.30)';
        cta.style.backdropFilter = 'blur(2px)';
        cta.style.textAlign = 'center';
        cta.innerHTML = `
            <div style="font-size:12px; opacity:0.9; margin-bottom:6px;">戦闘専用モード / ${statusLabel}${formationId ? ` / 敵編成:${formationId}` : ''}</div>
            <button id="visual-bo-center-cta-btn" style="padding:7px 12px; font-size:13px; border:0; border-radius:8px; cursor:pointer; background:#2563eb; color:#fff;">
                かんたん戦闘突入
            </button>
        `;
        if (!exists) document.body.appendChild(cta);
        const btn = document.getElementById('visual-bo-center-cta-btn');
        if (btn) btn.onclick = openBattleOnlyDraftFromUi;
    }

    syncBattleOnlyCenterCta();
    if (runtimeGlobal.__boCenterCtaTimer) {
        clearInterval(runtimeGlobal.__boCenterCtaTimer);
    }
    runtimeGlobal.__boCenterCtaTimer = setInterval(syncBattleOnlyCenterCta, 1200);

    if (isGM) {
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
                    statusMsg.textContent = "保存しました。";
                    setTimeout(() => statusMsg.textContent = "", 2000);
                } catch (e) { statusMsg.textContent = "保存に失敗しました。"; }
            };
        }
        if (presetBtn) {
            presetBtn.style.display = 'inline-block';
            presetBtn.onclick = () => { if (typeof openPresetManagerModal === 'function') openPresetManagerModal(); };
        }
        if (boBtn) {
            boBtn.style.display = isBattleOnlyMode ? 'inline-block' : 'none';
            boBtn.textContent = '戦闘専用編成';
            boBtn.onclick = openBattleOnlyDraftFromUi;
        }
    } else {
        if (saveBtn) saveBtn.style.display = 'none';
        if (presetBtn) presetBtn.style.display = 'none';
        if (boBtn) {
            boBtn.style.display = isBattleOnlyMode ? 'inline-block' : 'none';
            boBtn.textContent = 'かんたん戦闘突入';
            boBtn.onclick = openBattleOnlyDraftFromUi;
        }
    }
    if (resetBtn) {
        if (canUseResetInRoom) {
            resetBtn.style.display = 'inline-block';
            resetBtn.onclick = () => {
                if (typeof openResetTypeModal === 'function') {
                    openResetTypeModal((type, options) => { socket.emit('request_reset_battle', { room: currentRoomName, mode: type, options: options }); });
                } else if (confirm("戦闘をリセットしますか？")) {
                    socket.emit('request_reset_battle', { room: currentRoomName, mode: 'full' });
                }
            };
        } else {
            resetBtn.style.display = 'none';
        }
    }
}

// --- Timeline Controls ---

const VISUAL_TIMELINE_COLLAPSED_KEY = 'visual-timeline-collapsed';
const VISUAL_TIMELINE_USER_SET_KEY = 'visual-timeline-collapsed-user-set';

window.initializeTimelineToggle = function () {
    const timelineArea = document.getElementById('visual-timeline-area');
    const header = timelineArea ? timelineArea.querySelector('.sidebar-header') : null;
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');

    if (!header) return;

    const currentState = (window.BattleStore && window.BattleStore.state)
        ? window.BattleStore.state
        : (typeof battleState !== 'undefined' ? battleState : {});
    const isSelectPhase = (currentState && currentState.phase === 'select');
    const userSet = localStorage.getItem(VISUAL_TIMELINE_USER_SET_KEY) === '1';
    let collapsedRaw = localStorage.getItem(VISUAL_TIMELINE_COLLAPSED_KEY);

    // Default behavior for Select phase: collapsed unless user explicitly chose otherwise.
    if (isSelectPhase && !userSet) {
        collapsedRaw = 'true';
        localStorage.setItem(VISUAL_TIMELINE_COLLAPSED_KEY, collapsedRaw);
    } else {
        if (startRBtn) startRBtn.style.display = 'none';
        if (endRBtn) endRBtn.style.display = 'none';
    }
    if (collapsedRaw === null) {
        collapsedRaw = 'true';
        localStorage.setItem(VISUAL_TIMELINE_COLLAPSED_KEY, collapsedRaw);
    }

    const isCollapsed = collapsedRaw === 'true';
    if (isCollapsed) {
        timelineArea.classList.add('collapsed');
    } else {
        timelineArea.classList.remove('collapsed');
    }

    header.addEventListener('click', () => {
        const nowCollapsed = timelineArea.classList.toggle('collapsed');
        localStorage.setItem(VISUAL_TIMELINE_COLLAPSED_KEY, String(nowCollapsed));
        localStorage.setItem(VISUAL_TIMELINE_USER_SET_KEY, '1');
    });
}


/**
 * Legacy Timeline Renderer (Use Timeline.js component usually)
 */
window.renderVisualTimeline = function () {
    const timelineEl = document.getElementById('visual-timeline-list');
    if (!timelineEl) return;

    // If Timeline Component is active, let it handle rendering
    if (window.TimelineComponent && typeof window.TimelineComponent.render === 'function') {
        const componentCtn = document.getElementById('visual-timeline-list');
        // Ensure component checks this container
        if (window.TimelineComponent._containerEl === componentCtn) {
            return;
        }
    }

    timelineEl.innerHTML = '';
    if (!battleState.timeline || battleState.timeline.length === 0) {
        timelineEl.innerHTML = '<div style="color:#888; padding:5px;">データなし</div>';
        return;
    }
    const slotMode = Array.isArray(battleState.timeline) &&
        battleState.timeline.length > 0 &&
        typeof battleState.timeline[0] === 'string' &&
        battleState.slots &&
        battleState.slots[battleState.timeline[0]];

    if (slotMode) {
        const selectedSlotId = battleState.selectedSlotId || null;
        battleState.timeline.forEach(slotId => {
            const slot = battleState.slots[slotId];
            if (!slot) return;
            const char = battleState.characters.find(c => String(c.id) === String(slot.actor_id));
            const intent = (battleState.intents || {})[slotId] || {};
            const item = document.createElement('div');
            item.className = `timeline-item ${slot.team || 'NPC'}`;
            item.style.cssText = "display:flex; justify-content:space-between; gap:8px; padding:6px 8px; border-bottom:1px solid #eee; cursor:pointer; background:#fff;";
            if (String(slotId) === String(selectedSlotId)) {
                item.style.background = '#e8f4ff';
                item.style.border = '1px solid #66a3ff';
            }
            const actorName = char ? char.name : slot.actor_id;
            item.innerHTML = `
                <span class="name">${actorName}</span>
                <span class="speed" style="font-size:0.85em; color:#666;">SPD:${slot.initiative}</span>
            `;
            item.addEventListener('click', () => {
                if (char && typeof showCharacterDetail === 'function') {
                    showCharacterDetail(char.id);
                }
            });
            timelineEl.appendChild(item);
        });
        return;
    }

    const currentTurnId = battleState.turn_char_id;
    battleState.timeline.forEach(entry => {
        let charId = entry;
        if (typeof entry === 'object' && entry !== null) {
            charId = entry.char_id;
        }
        const char = battleState.characters.find(c => String(c.id) === String(charId));
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


