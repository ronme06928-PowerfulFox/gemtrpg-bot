import { store } from '../core/BattleStore.js';
import { socketClient } from '../core/SocketClient.js';

class DeclarePanel {
    constructor() {
        this._unsubscribe = null;
        this._initialized = false;
        this._panelId = 'select-resolve-declare-panel';
        this._lastCalcKey = null;
    }

    initialize() {
        if (this._initialized) return true;
        this._unsubscribe = store.subscribe((state) => this._render(state));
        this._render(store.state);
        this._initialized = true;
        console.log('DeclarePanel initialized');
        return true;
    }

    destroy() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
        this._initialized = false;
    }

    _ensurePanelEl() {
        let panel = document.getElementById(this._panelId);
        if (panel) return panel;

        const parent = document.getElementById('map-viewport') || document.getElementById('visual-battle-container');
        if (!parent) return null;

        panel = document.createElement('div');
        panel.id = this._panelId;
        panel.className = 'declare-panel';
        panel.style.display = 'none';
        parent.appendChild(panel);
        return panel;
    }

    _render(state) {
        const panel = this._ensurePanelEl();
        if (!panel) return;

        const phase = state.phase;
        const declare = state.declare || {};
        const sourceSlotId = declare.sourceSlotId || null;
        const targetSlotId = declare.targetSlotId || null;
        const skillId = declare.skillId || '';
        const mode = declare.mode || 'idle';
        const calc = declare.calc || null;
        const sourceIntent = state?.intents?.[sourceSlotId] || null;
        const isDeclaredLocked = mode === 'locked' || !!sourceIntent?.committed;

        if (phase !== 'select' || !sourceSlotId) {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = 'block';

        const sourceSlot = state.slots?.[sourceSlotId] || null;
        const sourceActorId = sourceSlot?.actor_id || null;
        const sourceChar = (state.characters || []).find(c => String(c.id) === String(sourceActorId)) || null;
        const targetOptions = this._buildTargetOptions(state, sourceSlotId, targetSlotId);
        const sourceLabel = this._formatSlotLabel(state, sourceSlotId);
        const targetLabel = targetSlotId ? this._formatSlotLabel(state, targetSlotId) : '未選択';
        const skillOptions = this._buildSkillOptions(sourceChar);
        const meta = this._resolveDisplayMeta(skillId, calc);
        const commandText = this._resolveCommandText(calc);
        const powerAdjustRows = this._resolvePowerAdjustRows(calc);
        const powerSummary = this._resolvePowerSummaryText(calc, powerAdjustRows);
        const costCheck = this._evaluateCost(state, sourceActorId, skillId, calc);
        const canCommit = !!(sourceSlotId && skillId && targetSlotId && !costCheck.insufficient && !isDeclaredLocked);
        const calcErrorText = (calc && calc.error) ? (calc.final_command || '計算エラー') : null;

        panel.innerHTML = `
            <div class="declare-panel-header">
                <div class="declare-panel-title">スキル選択</div>
                <div class="declare-panel-header-right">
                    <button id="declare-commit-btn-header" class="declare-commit-btn declare-commit-btn-header" ${canCommit ? '' : 'disabled'}>${isDeclaredLocked ? '宣言済み' : '宣言'}</button>
                    <button id="declare-close-btn" class="declare-close-btn" title="閉じる">x</button>
                </div>
            </div>
            <div class="declare-panel-row">
                <span>使用者</span>
                <span class="declare-human-label" data-slot-id="${sourceSlotId}">${sourceLabel}</span>
            </div>
            <div class="declare-panel-row">
                <span>対象</span>
                <div class="declare-target-controls">
                    <span class="declare-human-label" data-slot-id="${targetSlotId || ''}">${targetLabel}</span>
                    <select id="declare-target-select" class="declare-target-select" ${isDeclaredLocked ? 'disabled' : ''}>
                        ${targetOptions}
                    </select>
                </div>
            </div>
            <div class="declare-panel-row">
                <span>スキル</span>
                <select id="declare-skill-select" class="declare-skill-select" ${isDeclaredLocked ? 'disabled' : ''}>
                    ${skillOptions}
                </select>
            </div>
            <div class="declare-skill-meta">
                <div><strong>${meta.name}</strong></div>
                <div>${meta.description || '-'}</div>
                <div>レンジ: ${meta.rangeText || meta.range}</div>
                <div>コマンド: <code class="declare-command">${this._escapeHtml(commandText || '-')}</code></div>
                <div>威力: ${this._escapeHtml(powerSummary)}</div>
                ${powerAdjustRows.length > 0 ? `
                <div class="declare-power-adjust">
                    <div class="declare-power-adjust-title">威力変化の内訳</div>
                    ${powerAdjustRows.map((row) => `<div class="declare-power-adjust-row">${this._escapeHtml(row)}</div>`).join('')}
                </div>` : ''}
                ${meta.detailHtml ? `<div class="declare-skill-detail">${meta.detailHtml}</div>` : ''}
            </div>
            ${costCheck.insufficient ? `<div class="declare-cost-warning">${costCheck.message}</div>` : ''}
            ${calcErrorText ? `<div class="declare-cost-warning">${calcErrorText}</div>` : ''}
        `;

        const closeBtn = panel.querySelector('#declare-close-btn');
        if (closeBtn) {
            closeBtn.onclick = () => {
                store.resetDeclare();
                store.setSelectedSlotId(null);
            };
        }

        const skillSelect = panel.querySelector('#declare-skill-select');
        if (skillSelect) {
            skillSelect.value = skillId || '';
            skillSelect.disabled = isDeclaredLocked;
            skillSelect.onchange = (e) => {
                if (isDeclaredLocked) return;
                const nextSkillId = e.target.value || '';
                const current = store.get('declare') || {};
                const nextDeclare = {
                    ...current,
                    skillId: nextSkillId || null,
                    mode: current.targetSlotId ? 'ready' : 'choose_target'
                };
                store.setDeclare(nextDeclare);
                this._emitPreviewFromDeclare(store.state, nextDeclare);
                this._requestCalc(store.state, nextDeclare, true);
            };
        }

        const targetSelect = panel.querySelector('#declare-target-select');
        if (targetSelect) {
            targetSelect.value = targetSlotId || '';
            targetSelect.disabled = isDeclaredLocked;
            targetSelect.onchange = (e) => {
                if (isDeclaredLocked) return;
                const nextTargetSlotId = e.target.value || null;
                const current = store.get('declare') || {};
                const nextDeclare = {
                    ...current,
                    targetSlotId: nextTargetSlotId,
                    mode: nextTargetSlotId ? 'ready' : 'choose_target'
                };
                store.setDeclare(nextDeclare);
                this._emitPreviewFromDeclare(store.state, nextDeclare);
                this._requestCalc(store.state, nextDeclare, true);
            };
        }

        const commitBtn = panel.querySelector('#declare-commit-btn-header') || panel.querySelector('#declare-commit-btn');
        if (commitBtn) {
            commitBtn.onclick = () => {
                if (isDeclaredLocked) return;
                const latestState = store.state;
                const latestDeclare = latestState.declare || {};
                const src = latestDeclare.sourceSlotId;
                const tgt = latestDeclare.targetSlotId;
                const sk = latestDeclare.skillId;
                const latestSourceActorId = latestState.slots?.[src]?.actor_id || null;
                const latestCostCheck = this._evaluateCost(latestState, latestSourceActorId, sk, latestDeclare.calc);
                if (!(latestState.phase === 'select' && src && sk && tgt) || latestCostCheck.insufficient) {
                    return;
                }

                const roomId = latestState.room_id || latestState.room_name || window.currentRoomName || null;
                const battleId = latestState.battle_id || null;
                if (!roomId || !battleId) {
                    console.warn(`[emit] battle_intent_commit skip slot=${src} skill=${sk} target=${tgt} reason=missing_room_or_battle`);
                    return;
                }

                const target = { type: 'single_slot', slot_id: tgt };
                console.log(`[emit] battle_intent_commit slot=${src} skill=${sk} target=${tgt}`);
                socketClient.sendIntentCommit(roomId, battleId, src, sk, target);

                store.resetDeclare();
                store.setSelectedSlotId(null);
            };
        }

        this._requestCalc(state, declare, false);
    }

    _buildSkillOptions(actor) {
        const all = window.allSkillData || {};
        const candidates = this._extractActorSkillCandidates(actor, all);
        const selectedSkillId = (store.get('declare') || {}).skillId || '';
        const options = ['<option value="">-- スキル --</option>'];
        candidates.slice(0, 400).forEach((item) => {
            const id = item.id;
            const meta = this._readSkillMeta(id);
            const displayName = item.name || meta.name || id;
            const selected = (id === selectedSkillId) ? ' selected' : '';
            options.push(`<option value="${id}"${selected}>[${id}] ${displayName}</option>`);
        });
        return options.join('');
    }

    _buildTargetOptions(state, sourceSlotId, selectedTargetSlotId) {
        const slots = state?.slots || {};
        const sourceSlot = sourceSlotId ? slots[sourceSlotId] : null;
        const sourceActorId = sourceSlot?.actor_id || null;
        const sourceTeam = sourceSlot?.team || null;
        const options = ['<option value="">-- 対象スロット --</option>'];
        const rows = [];

        Object.keys(slots).forEach((slotId) => {
            const slot = slots[slotId];
            if (!slot || String(slotId) === String(sourceSlotId)) return;

            const actorId = slot.actor_id;
            if (sourceActorId && actorId && String(actorId) === String(sourceActorId)) return;
            if (sourceTeam && slot.team && String(sourceTeam) === String(slot.team)) return;
            if (slot.disabled) return;

            const label = this._formatSlotLabel(state, slotId);
            const initiative = Number(slot.initiative ?? 0);
            rows.push({ slotId, label: `${label} (SPD:${initiative})` });
        });

        rows.sort((a, b) => String(a.label).localeCompare(String(b.label), 'ja'));
        rows.forEach((row) => {
            const selected = String(row.slotId) === String(selectedTargetSlotId || '') ? ' selected' : '';
            options.push(`<option value="${row.slotId}"${selected}>${this._escapeHtml(row.label)}</option>`);
        });

        if (
            selectedTargetSlotId
            && !rows.some((row) => String(row.slotId) === String(selectedTargetSlotId))
        ) {
            const selectedLabel = this._formatSlotLabel(state, selectedTargetSlotId);
            options.push(
                `<option value="${selectedTargetSlotId}" selected>${this._escapeHtml(selectedLabel)}</option>`
            );
        }

        return options.join('');
    }

    _readSkillMeta(skillId) {
        const all = window.allSkillData || {};
        const skill = (skillId && all[skillId]) ? all[skillId] : {};
        const name =
            skill.name ||
            skill.default_name ||
            this._findByKeyPattern(skill, /name|title/i) ||
            skillId ||
            '(none)';
        const description =
            skill.description ||
            skill.desc ||
            skill.summary ||
            this._findByKeyPattern(skill, /desc|effect|text|detail/i) ||
            '';

        const power = this._firstValue(skill, ['power', 'base_power'], this._findByKeyPattern(skill, /power|atk/i) || '-');
        const range = this._firstValue(skill, ['range', 'attack_range', 'target_range', 'distance'], this._findByKeyPattern(skill, /range|distance|target/i) || '-');
        return { name, description, power, range };
    }

    _resolveCommandText(calc) {
        if (!calc) return '';
        const raw = calc.final_command || calc.command || '';
        return this._stripTags(String(raw || '')).trim();
    }

    _resolvePowerAdjustRows(calc) {
        const rows = [];
        if (!calc || typeof calc !== 'object') return rows;

        const baseMod = Number(calc?.skill_details?.base_power_mod || 0);
        if (baseMod !== 0) rows.push(`[基礎威力 ${baseMod > 0 ? '+' : ''}${baseMod}]`);

        const correctionDetails = Array.isArray(calc?.correction_details) ? calc.correction_details : [];
        correctionDetails.forEach((detail) => {
            const source = String(detail?.source || '補正');
            const value = Number(detail?.value || 0);
            if (value !== 0) {
                rows.push(`[${source} ${value > 0 ? '+' : ''}${value}]`);
            }
        });

        const senritsuPenalty = Number(calc?.senritsu_dice_reduction || 0);
        if (senritsuPenalty > 0) {
            rows.push(`[ダイス威力 -${senritsuPenalty}] (戦慄)`);
        }

        const pb = calc?.power_breakdown;
        if (pb && typeof pb === 'object') {
            const base = Number(pb.base_power ?? NaN);
            const finalBase = Number(pb.final_base_power ?? NaN);
            if (!Number.isNaN(base) && !Number.isNaN(finalBase) && base !== finalBase) {
                rows.push(`[基礎威力 ${base} -> ${finalBase}]`);
            }

            const keyRows = [
                ['dice_count_mod', 'ダイス個数'],
                ['dice_face_mod', 'ダイス面数'],
                ['dice_bonus_mod', 'ダイス固定値'],
                ['base_power_mod', '基礎威力']
            ];
            keyRows.forEach(([key, label]) => {
                const val = Number(pb[key] || 0);
                if (val !== 0) rows.push(`[${label} ${val > 0 ? '+' : ''}${val}]`);
            });
        }

        return rows;
    }

    _resolvePowerSummaryText(calc, rows) {
        if (!calc || typeof calc !== 'object') return '-';
        if (rows.length > 0) return '変化あり';
        return '変化なし';
    }

    _stripTags(text) {
        return String(text || '').replace(/<[^>]*>/g, ' ');
    }

    _escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    _firstValue(obj, keys, fallback) {
        for (const key of keys) {
            if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== '') {
                return obj[key];
            }
        }
        return fallback;
    }

    _findByKeyPattern(obj, pattern) {
        if (!obj || typeof obj !== 'object') return null;
        for (const key of Object.keys(obj)) {
            if (!pattern.test(String(key))) continue;
            const v = obj[key];
            if (v === undefined || v === null || v === '') continue;
            return v;
        }
        return null;
    }

    _emitPreviewFromDeclare(state, declare) {
        const sourceSlotId = declare?.sourceSlotId;
        const skillId = declare?.skillId || null;
        if (!sourceSlotId) return;
        if (state.phase !== 'select') return;

        const roomId = state.room_id || state.room_name || window.currentRoomName || null;
        const battleId = state.battle_id || null;
        if (!roomId || !battleId) return;

        const target = declare?.targetSlotId
            ? { type: 'single_slot', slot_id: declare.targetSlotId }
            : { type: 'none', slot_id: null };

        socketClient.sendIntentPreview(roomId, battleId, sourceSlotId, skillId, target);
    }

    _requestCalc(state, declare, force = false) {
        const sourceSlotId = declare?.sourceSlotId || null;
        const skillId = declare?.skillId || null;
        if (!sourceSlotId || !skillId) return;
        if (state.phase !== 'select') return;

        const targetSlotId = declare?.targetSlotId || null;
        const calcKey = `${sourceSlotId}|${skillId}|${targetSlotId || 'none'}`;
        if (!force && this._lastCalcKey === calcKey) return;
        this._lastCalcKey = calcKey;

        const sourceActorId = state.slots?.[sourceSlotId]?.actor_id || null;
        const targetActorId = targetSlotId ? (state.slots?.[targetSlotId]?.actor_id || null) : null;
        if (!sourceActorId) return;

        console.log(`[declare] calc_request source_slot=${sourceSlotId} target_slot=${targetSlotId || 'none'} skill=${skillId}`);
        socketClient.declareSkill({
            actor_id: sourceActorId,
            target_id: targetActorId,
            skill_id: skillId,
            modifier: 0,
            prefix: `declare_panel_${sourceSlotId}`,
            commit: false,
            custom_skill_name: ''
        });
    }

    _extractActorSkillCandidates(actor, allSkillMap) {
        const idsAll = Object.keys(allSkillMap || {});
        const list = [];
        const seen = new Set();

        const commands = actor?.commands || '';
        if (commands) {
            const regex = /[\u3010\[]([^ \]\u3011]+)\s+([^\u3011\]]+)[\u3011\]]/g;
            let m;
            while ((m = regex.exec(commands)) !== null) {
                const id = m[1];
                const name = (m[2] || '').trim();
                if (!id || seen.has(id)) continue;
                if (allSkillMap[id]) {
                    seen.add(id);
                    list.push({ id, name: name || this._readSkillMeta(id).name });
                }
            }
        }

        if (list.length > 0) return list;
        return idsAll.map((id) => ({ id, name: this._readSkillMeta(id).name }));
    }

    _formatSlotLabel(state, slotId) {
        if (!slotId) return '-';
        const slot = state?.slots?.[slotId];
        if (!slot) return '不明';

        const actorId = slot.actor_id;
        const char = (state.characters || []).find(c => String(c.id) === String(actorId));
        const name = char?.name || '不明';
        const indexRaw = Number(slot.index_in_actor ?? 0);
        const index = Number.isFinite(indexRaw) ? (indexRaw + 1) : 1;
        return `${name} #${index}`;
    }

    _resolveDisplayMeta(skillId, calc) {
        const base = this._readSkillMeta(skillId);
        if (!calc || calc.error) {
            const baseSkill = (window.allSkillData || {})[skillId];
            const baseDetailHtml = (baseSkill && typeof window.formatSkillDetailHTML === 'function')
                ? window.formatSkillDetailHTML(baseSkill)
                : '';
            return { ...base, detailHtml: baseDetailHtml };
        }

        const min = (calc.min_damage !== undefined && calc.min_damage !== null) ? calc.min_damage : null;
        const max = (calc.max_damage !== undefined && calc.max_damage !== null) ? calc.max_damage : null;
        const rangeText = (min !== null && max !== null) ? `${min} ~ ${max}` : null;
        const detailHtml = (calc.skill_details && typeof window.formatSkillDetailHTML === 'function')
            ? window.formatSkillDetailHTML(calc.skill_details)
            : '';

        return { ...base, rangeText, detailHtml };
    }

    _evaluateCost(state, sourceActorId, skillId, calc) {
        if (!sourceActorId || !skillId) return { insufficient: false, message: '' };
        const actor = (state.characters || []).find(c => String(c.id) === String(sourceActorId));
        if (!actor) return { insufficient: false, message: '' };

        const costs = this._extractCosts(skillId, calc);
        if (!Array.isArray(costs) || costs.length === 0) return { insufficient: false, message: '' };

        const shortages = [];
        for (const c of costs) {
            const type = String(c?.type || '').toUpperCase();
            const required = Number(c?.value || 0);
            if (!type || required <= 0) continue;
            const current = this._readActorResource(actor, type);
            if (current < required) {
                shortages.push({ type, required, current });
            }
        }

        if (shortages.length === 0) return { insufficient: false, message: '' };
        const text = shortages.map(s => `${s.type} insufficient (need:${s.required} / current:${s.current})`).join(' / ');
        return { insufficient: true, message: text };
    }

    _extractCosts(skillId, calc) {
        const detailsCost = calc?.skill_details?.cost;
        if (Array.isArray(detailsCost) && detailsCost.length > 0) return detailsCost;

        const skill = (window.allSkillData || {})[skillId];
        if (!skill || typeof skill !== 'object') return [];

        if (Array.isArray(skill.cost)) return skill.cost;

        const ruleObj = this._extractRuleData(skill);
        if (ruleObj && Array.isArray(ruleObj.cost)) return ruleObj.cost;
        return [];
    }

    _extractRuleData(skill) {
        if (!skill || typeof skill !== 'object') return null;
        if (skill.rule_data && typeof skill.rule_data === 'object') return skill.rule_data;

        const ruleKeys = Object.keys(skill).filter((k) => {
            const lower = String(k).toLowerCase();
            return lower.includes('rule') || lower.includes('special');
        });
        for (const key of ruleKeys) {
            const raw = skill[key];
            if (!raw) continue;
            if (typeof raw === 'object') return raw;
            if (typeof raw === 'string' && raw.trim().startsWith('{')) {
                try {
                    return JSON.parse(raw);
                } catch (_) {
                    // no-op
                }
            }
        }

        // Fallback: parse any JSON-like field and pick one that has "cost".
        for (const key of Object.keys(skill)) {
            const raw = skill[key];
            if (typeof raw !== 'string') continue;
            const trimmed = raw.trim();
            if (!trimmed.startsWith('{')) continue;
            try {
                const parsed = JSON.parse(trimmed);
                if (parsed && typeof parsed === 'object' && Array.isArray(parsed.cost)) {
                    return parsed;
                }
            } catch (_) {
                // no-op
            }
        }
        return null;
    }

    _readActorResource(actor, type) {
        const key = String(type || '').toUpperCase();
        if (!actor) return 0;

        if (key === 'HP') return Number(actor.hp ?? 0);
        if (key === 'MP') return Number(actor.mp ?? 0);
        if (key === 'FP') {
            if (actor.fp !== undefined) return Number(actor.fp ?? 0);
            const fpState = (actor.states || []).find((s) => String(s?.name || '').toUpperCase() === 'FP');
            return Number(fpState?.value ?? 0);
        }
        if (key === 'SAN' || key === 'SANITY') {
            if (actor.sanity !== undefined) return Number(actor.sanity ?? 0);
            const sanityState = (actor.states || []).find((s) => String(s?.name || '').toUpperCase() === 'SAN');
            return Number(sanityState?.value ?? 0);
        }

        const direct = actor[key] ?? actor[key.toLowerCase()];
        if (direct !== undefined && direct !== null && direct !== '') {
            return Number(direct || 0);
        }

        const stateVal = (actor.states || []).find((s) => String(s?.name || '').toUpperCase() === key);
        return Number(stateVal?.value ?? 0);
    }
}

export const declarePanel = new DeclarePanel();

if (typeof window !== 'undefined') {
    window.DeclarePanelComponent = declarePanel;
}




