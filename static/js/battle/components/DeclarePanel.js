import { store } from '../core/BattleStore.js';
import { socketClient } from '../core/SocketClient.js';

class DeclarePanel {
    constructor() {
        this._unsubscribe = null;
        this._initialized = false;
        this._panelRootId = 'select-resolve-declare-panels';
        this._leftPanelId = 'select-resolve-declare-panel-left';
        this._rightPanelId = 'select-resolve-declare-panel-right';
        this._lastCalcKey = null;
        this._lastCompareCalcKeyBySlot = {};
        this._sideUi = {
            ally: { minimized: false },
            enemy: { minimized: false }
        };
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

    _resolvePanelMountTarget() {
        const visualRoot = document.getElementById('visual-battle-container');
        if (visualRoot) {
            return { parent: visualRoot, variant: 'map' };
        }

        const mapViewport = document.getElementById('map-viewport');
        if (mapViewport) {
            return { parent: mapViewport, variant: 'map' };
        }

        const sidebarHost = document.getElementById('declare-panel-sidebar-host');
        if (sidebarHost) {
            return { parent: sidebarHost, variant: 'sidebar' };
        }

        const chatArea = document.getElementById('visual-chat-area');
        if (chatArea) {
            return { parent: chatArea, variant: 'sidebar' };
        }

        return { parent: null, variant: 'map' };
    }

    _ensurePanelEls() {
        const mountTarget = this._resolvePanelMountTarget();
        const parent = mountTarget.parent;
        if (!parent) return null;

        let root = document.getElementById(this._panelRootId);
        if (!root) {
            root = document.createElement('div');
            root.id = this._panelRootId;
            root.style.display = 'none';
        }
        if (root.parentElement !== parent) {
            parent.appendChild(root);
        }
        root.className = (mountTarget.variant === 'sidebar')
            ? 'declare-panels declare-panels--sidebar'
            : 'declare-panels declare-panels--map';

        let leftPanel = document.getElementById(this._leftPanelId);
        if (!leftPanel) {
            leftPanel = document.createElement('div');
            leftPanel.id = this._leftPanelId;
            leftPanel.style.display = 'none';
        }
        leftPanel.className = (mountTarget.variant === 'sidebar')
            ? 'declare-panel declare-panel--sidebar declare-panel--side-left'
            : 'declare-panel declare-panel--map declare-panel--side-left';

        let rightPanel = document.getElementById(this._rightPanelId);
        if (!rightPanel) {
            rightPanel = document.createElement('div');
            rightPanel.id = this._rightPanelId;
            rightPanel.style.display = 'none';
        }
        rightPanel.className = (mountTarget.variant === 'sidebar')
            ? 'declare-panel declare-panel--sidebar declare-panel--side-right'
            : 'declare-panel declare-panel--map declare-panel--side-right';

        if (leftPanel.parentElement !== root) root.appendChild(leftPanel);
        if (rightPanel.parentElement !== root) root.appendChild(rightPanel);

        leftPanel.dataset.mountVariant = mountTarget.variant;
        rightPanel.dataset.mountVariant = mountTarget.variant;
        return { root, leftPanel, rightPanel };
    }

    _render(state) {
        const panelSet = this._ensurePanelEls();
        if (!panelSet) return;
        const { root, leftPanel, rightPanel } = panelSet;

        const phase = state.phase;
        const declare = state.declare || {};
        const sourceSlotId = declare.sourceSlotId || null;
        const targetSlotId = declare.targetSlotId || null;
        const skillId = declare.skillId || '';
        const mode = declare.mode || 'idle';
        const calc = declare.calc || null;
        const sourceIntent = state?.intents?.[sourceSlotId] || null;
        const hasCommittedIntent = !!sourceIntent?.committed;
        const isDeclaredLocked = mode === 'locked';
        const canEditSource = this._canEditSourceSlot(state, sourceSlotId);
        const isUiReadOnly = isDeclaredLocked || !canEditSource;
        const declaredTargetType = this._normalizeTargetType(declare.targetType || sourceIntent?.target?.type);
        const effectiveTargetType = this._resolveEffectiveTargetType(skillId, declaredTargetType);
        const isMassTarget = this._isMassTargetType(effectiveTargetType);
        const effectiveTargetSlotId = isMassTarget ? null : targetSlotId;
        const declareDiff = (typeof store.compareDeclareWithCommitted === 'function')
            ? store.compareDeclareWithCommitted(sourceSlotId)
            : { hasDiff: true, diffSummary: '' };
        const hasDeclareDiff = !!declareDiff?.hasDiff;
        const isTargetPicking = !!(sourceSlotId && !isMassTarget && !effectiveTargetSlotId);
        const shouldShowPanel = !!sourceSlotId;
        const closeBtnTitle = hasDeclareDiff ? '閉じる（未確定の変更は破棄）' : '閉じる';

        if (phase !== 'select' || !shouldShowPanel) {
            root.style.display = 'none';
            leftPanel.style.display = 'none';
            rightPanel.style.display = 'none';
            // Re-opening the panel should trigger fresh calc request for same slot/skill.
            this._lastCalcKey = null;
            this._lastCompareCalcKeyBySlot = {};
            leftPanel.classList.remove('is-target-picking');
            rightPanel.classList.remove('is-target-picking');
            return;
        }
        root.style.display = 'block';
        leftPanel.style.display = 'block';
        rightPanel.style.display = 'block';

        const sourceSlot = state.slots?.[sourceSlotId] || null;
        const sourceActorId = sourceSlot?.actor_id || null;
        const sourceChar = (state.characters || []).find(c => String(c.id) === String(sourceActorId)) || null;
        const sourceTeam = this._normalizeTeam(sourceSlot?.team || sourceChar?.type || '');
        const targetTeam = effectiveTargetSlotId ? this._teamForSlot(state, effectiveTargetSlotId) : null;
        const sideSlots = {
            ally: null,
            enemy: null
        };
        const compareCalcMap = state?.compareCalcBySlot || {};
        if (sourceSlotId && (sourceTeam === 'ally' || sourceTeam === 'enemy')) {
            sideSlots[sourceTeam] = sourceSlotId;
        }
        if (effectiveTargetSlotId && (targetTeam === 'ally' || targetTeam === 'enemy')) {
            sideSlots[targetTeam] = effectiveTargetSlotId;
        }
        const visibleSide = {
            ally: !!sideSlots.ally,
            enemy: !!sideSlots.enemy
        };
        const interactivePanel = sourceTeam === 'enemy' ? rightPanel : leftPanel;
        const readonlyPanel = sourceTeam === 'enemy' ? leftPanel : rightPanel;
        const interactiveSide = sourceTeam === 'enemy' ? 'enemy' : 'ally';
        const readonlySide = sourceTeam === 'enemy' ? 'ally' : 'enemy';
        const interactiveMinimized = !!this._sideUi?.[interactiveSide]?.minimized;
        const readonlyMinimized = !!this._sideUi?.[readonlySide]?.minimized;
        interactivePanel.classList.toggle('is-target-picking', isTargetPicking);
        readonlyPanel.classList.remove('is-target-picking');

        const shouldClearIncompatibleSkill = (
            !isUiReadOnly
            && !isMassTarget
            && !!effectiveTargetSlotId
            && !!skillId
            && !this._isSkillCompatibleWithTarget(state, sourceSlotId, effectiveTargetSlotId, skillId)
        );
        if (shouldClearIncompatibleSkill) {
            const nextDeclare = { ...(declare || {}), skillId: null };
            store.setDeclare(nextDeclare);
            this._emitPreviewFromDeclare(state, nextDeclare);
            this._requestCalc(state, nextDeclare, true);
            return;
        }
        const targetOptions = this._buildTargetOptions(state, sourceSlotId, effectiveTargetSlotId, effectiveTargetType, skillId);
        const sourceLabel = this._formatSlotLabel(state, sourceSlotId);
        const targetLabel = isMassTarget
            ? this._getMassTargetLabel(sourceSlot)
            : (effectiveTargetSlotId ? this._formatSlotLabel(state, effectiveTargetSlotId) : '未選択');
        const skillOptions = this._buildSkillOptions(sourceChar, state, sourceSlotId, effectiveTargetSlotId);
        const meta = this._resolveDisplayMeta(skillId, calc);
        const commandText = this._resolveCommandText(calc);
        const powerAdjustRows = this._resolvePowerAdjustRows(calc);
        const powerSummary = this._resolvePowerSummaryText(calc, powerAdjustRows);
        const costCheck = this._evaluateCost(state, sourceActorId, skillId, calc);
        const canCommit = !!(
            sourceSlotId
            && skillId
            && !costCheck.insufficient
            && canEditSource
            && !isDeclaredLocked
            && (isMassTarget || !!effectiveTargetSlotId)
            && hasDeclareDiff
        );
        const commitButtonText = !canEditSource
            ? '閲覧'
            : (isDeclaredLocked ? '宣言済み' : (hasCommittedIntent ? '再宣言' : '宣言'));
        const calcErrorText = (calc && calc.error)
            ? (calc.message || calc.final_command || '計算エラー')
            : null;
        const flow = this._resolveFlowGuide({
            sourceSlotId,
            skillId,
            isMassTarget,
            effectiveTargetSlotId
        });

        Object.keys(sideSlots).forEach((side) => {
            const slotId = sideSlots?.[side];
            if (!slotId) return;
            if (String(slotId) === String(sourceSlotId || '')) return;
            const compareSkillId = String(state?.intents?.[slotId]?.skill_id || '').trim();
            if (!compareSkillId) return;
            const compareTargetSlotId = this._resolveCompareTargetSlotId(state, slotId);
            this._requestCompareCalc(state, slotId, compareSkillId, compareTargetSlotId, false);
        });

        const interactiveTitle = sourceTeam === 'enemy' ? '敵宣言' : '味方宣言';
        const interactiveRangeText = this._resolvePowerRangeText({
            meta,
            calc,
            actor: sourceChar,
            skillId
        });
        const interactiveSkillDisplay = this._resolveSkillDisplayName(skillId, meta.name, sourceChar);
        const interactiveSummaryHtml = this._buildMinimizedSummaryHtml(interactiveSkillDisplay, interactiveRangeText);
        const interactiveHtml = `
            <div class="declare-panel-header">
                <div class="declare-panel-title">${interactiveTitle}</div>
                <div class="declare-panel-header-right">
                    <button id="declare-commit-btn-header" class="declare-commit-btn declare-commit-btn-header" ${canCommit ? '' : 'disabled'}>${commitButtonText}</button>
                    <button id="declare-minimize-btn" class="declare-minimize-btn" title="${interactiveMinimized ? '展開' : '最小化'}">${interactiveMinimized ? '□' : '－'}</button>
                    <button id="declare-close-btn" class="declare-close-btn" title="${this._escapeHtml(closeBtnTitle)}">x</button>
                </div>
            </div>
            ${interactiveSummaryHtml}
            <div class="declare-flow-guide">
                <div class="declare-flow-steps">
                    <span class="declare-flow-chip ${flow.step1Class}">1 使用者</span>
                    <span class="declare-flow-chip ${flow.step2Class}">2 スキル</span>
                    <span class="declare-flow-chip ${flow.step3Class}">3 対象</span>
                </div>
                <div class="declare-flow-text">${this._escapeHtml(flow.message)}</div>
            </div>
            <div class="declare-panel-row">
                <span>使用者</span>
                <span class="declare-human-label" data-slot-id="${sourceSlotId}">${sourceLabel}</span>
            </div>
            <div class="declare-panel-row">
                <span>対象</span>
                <div class="declare-target-controls">
                    <span class="declare-human-label" data-slot-id="${effectiveTargetSlotId || ''}">${targetLabel}</span>
                    <select id="declare-target-select" class="declare-target-select" ${(isUiReadOnly || isMassTarget) ? 'disabled' : ''}>
                        ${targetOptions}
                    </select>
                </div>
            </div>
            ${isTargetPicking ? `<div class="declare-panel-row"><span></span><span class="declare-help-text">対象スロットをクリックしてください</span></div>` : ''}
            <div class="declare-panel-row">
                <span>スキル</span>
                <select id="declare-skill-select" class="declare-skill-select" ${isUiReadOnly ? 'disabled' : ''}>
                    ${skillOptions}
                </select>
            </div>
            <div class="declare-skill-meta">
                <div><strong>${this._escapeHtml(interactiveSkillDisplay)}</strong></div>
                <div>${meta.description || '-'}</div>
                <div>威力レンジ: ${this._escapeHtml(interactiveRangeText)}</div>
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

        const leftReadonly = this._buildReadonlyPanelHtml(
            state,
            sideSlots.ally,
            'ally',
            {
                sourceSlotId,
                skillId,
                calc,
                effectiveTargetSlotId,
                compareCalc: sideSlots.ally ? (compareCalcMap[String(sideSlots.ally)] || null) : null,
                isSourceSide: sourceTeam !== 'enemy'
            }
        );
        const rightReadonly = this._buildReadonlyPanelHtml(
            state,
            sideSlots.enemy,
            'enemy',
            {
                sourceSlotId,
                skillId,
                calc,
                effectiveTargetSlotId,
                compareCalc: sideSlots.enemy ? (compareCalcMap[String(sideSlots.enemy)] || null) : null,
                isSourceSide: sourceTeam === 'enemy'
            }
        );
        if (sourceTeam === 'enemy') {
            leftPanel.innerHTML = leftReadonly;
            rightPanel.innerHTML = interactiveHtml;
        } else {
            leftPanel.innerHTML = interactiveHtml;
            rightPanel.innerHTML = rightReadonly;
        }
        leftPanel.style.display = visibleSide.ally ? 'block' : 'none';
        rightPanel.style.display = visibleSide.enemy ? 'block' : 'none';
        root.style.display = (visibleSide.ally || visibleSide.enemy) ? 'block' : 'none';
        if (!visibleSide.ally && !visibleSide.enemy) return;

        leftPanel.classList.toggle('is-minimized', visibleSide.ally && !!this._sideUi.ally.minimized);
        rightPanel.classList.toggle('is-minimized', visibleSide.enemy && !!this._sideUi.enemy.minimized);

        const closeBtn = interactivePanel.querySelector('#declare-close-btn');
        if (closeBtn) {
            closeBtn.onclick = () => {
                store.resetDeclare();
                store.setSelectedSlotId(null);
            };
        }

        const interactiveMinBtn = interactivePanel.querySelector('#declare-minimize-btn');
        if (interactiveMinBtn) {
            interactiveMinBtn.onclick = () => {
                this._toggleSideMinimized(interactiveSide);
            };
        }
        const readonlyMinBtn = readonlyPanel.querySelector(`#declare-readonly-min-btn-${readonlySide}`);
        if (readonlyMinBtn) {
            readonlyMinBtn.onclick = () => {
                this._toggleSideMinimized(readonlySide);
            };
        }

        const skillSelect = interactivePanel.querySelector('#declare-skill-select');
        if (skillSelect) {
            skillSelect.value = skillId || '';
            skillSelect.disabled = isUiReadOnly;
            skillSelect.onchange = (e) => {
                if (isUiReadOnly) return;
                const nextSkillId = e.target.value || '';
                const current = store.get('declare') || {};
                const prevTargetType = this._normalizeTargetType(current.targetType || declaredTargetType);
                const nextTargetType = this._resolveEffectiveTargetType(nextSkillId, prevTargetType);
                let nextTargetSlotId = current.targetSlotId || null;
                let nextLastSingleTargetSlotId = current.lastSingleTargetSlotId || null;

                if (this._isMassTargetType(nextTargetType)) {
                    if (!this._isMassTargetType(prevTargetType) && nextTargetSlotId) {
                        nextLastSingleTargetSlotId = nextTargetSlotId;
                    }
                    nextTargetSlotId = null;
                } else {
                    if (this._isMassTargetType(prevTargetType)) {
                        nextTargetSlotId = current.lastSingleTargetSlotId || null;
                    }
                    if (nextTargetSlotId) {
                        nextLastSingleTargetSlotId = nextTargetSlotId;
                    }
                }

                const nextDeclare = {
                    ...current,
                    skillId: nextSkillId || null,
                    targetType: nextTargetType,
                    targetSlotId: nextTargetSlotId,
                    lastSingleTargetSlotId: nextLastSingleTargetSlotId,
                    mode: (
                        !this._isMassTargetType(nextTargetType)
                        && !nextTargetSlotId
                        && String(current.mode || '') === 'ready'
                    )
                        ? 'ready'
                        : this._resolveDeclareMode(nextTargetType, nextTargetSlotId)
                };
                store.setDeclare(nextDeclare);
                this._emitPreviewFromDeclare(store.state, nextDeclare);
                this._requestCalc(store.state, nextDeclare, true);
            };
        }

        const targetSelect = interactivePanel.querySelector('#declare-target-select');
        if (targetSelect) {
            targetSelect.value = effectiveTargetSlotId || '';
            targetSelect.disabled = isUiReadOnly || isMassTarget;
            targetSelect.onchange = (e) => {
                if (isUiReadOnly || isMassTarget) return;
                const nextTargetSlotId = e.target.value || null;
                const current = store.get('declare') || {};
                const currentTargetType = this._normalizeTargetType(current.targetType || effectiveTargetType);
                const nextSkillId = (
                    current.skillId
                    && nextTargetSlotId
                    && !this._isSkillCompatibleWithTarget(state, sourceSlotId, nextTargetSlotId, current.skillId)
                )
                    ? null
                    : current.skillId;
                const nextDeclare = {
                    ...current,
                    skillId: nextSkillId,
                    targetSlotId: nextTargetSlotId,
                    targetType: currentTargetType,
                    lastSingleTargetSlotId: nextTargetSlotId || current.lastSingleTargetSlotId || null,
                    mode: (
                        !this._isMassTargetType(currentTargetType)
                        && !nextTargetSlotId
                        && String(current.mode || '') === 'ready'
                    )
                        ? 'ready'
                        : this._resolveDeclareMode(currentTargetType, nextTargetSlotId)
                };
                store.setDeclare(nextDeclare);
                this._emitPreviewFromDeclare(store.state, nextDeclare);
                this._requestCalc(store.state, nextDeclare, true);
            };
        }

        const commitBtn = interactivePanel.querySelector('#declare-commit-btn-header') || interactivePanel.querySelector('#declare-commit-btn');
        if (commitBtn) {
            commitBtn.onclick = () => {
                if (!canEditSource || isDeclaredLocked) return;
                const latestState = store.state;
                const latestDeclare = latestState.declare || {};
                const src = latestDeclare.sourceSlotId;
                const tgt = latestDeclare.targetSlotId;
                const sk = latestDeclare.skillId;
                const targetType = this._resolveEffectiveTargetType(sk, latestDeclare.targetType || effectiveTargetType);
                const isMassCommit = this._isMassTargetType(targetType);
                const latestSourceActorId = latestState.slots?.[src]?.actor_id || null;
                const latestCostCheck = this._evaluateCost(latestState, latestSourceActorId, sk, latestDeclare.calc);
                if (!(latestState.phase === 'select' && src && sk) || latestCostCheck.insufficient) {
                    return;
                }
                if (!isMassCommit && !tgt) {
                    return;
                }

                const roomId = latestState.room_id || latestState.room_name || window.currentRoomName || null;
                const battleId = latestState.battle_id || null;
                if (!roomId || !battleId) {
                    console.warn(`[emit] battle_intent_commit skip slot=${src} skill=${sk} target_type=${targetType} target=${tgt} reason=missing_room_or_battle`);
                    return;
                }

                const target = isMassCommit
                    ? { type: targetType, slot_id: null }
                    : { type: 'single_slot', slot_id: tgt };
                console.log(`[emit] battle_intent_commit slot=${src} skill=${sk} target_type=${target.type} target=${target.slot_id || 'null'}`);
                socketClient.sendIntentCommit(roomId, battleId, src, sk, target);

                store.resetDeclare();
                store.setSelectedSlotId(null);
            };
        }

        this._requestCalc(state, declare, false);
    }

    _teamForSlot(state, slotId) {
        if (!state || !slotId) return null;
        const slot = state?.slots?.[slotId];
        if (!slot) return null;
        return this._normalizeTeam(slot.team || '');
    }

    _buildReadonlyPanelHtml(state, slotId, side, context = {}) {
        const sideTitle = side === 'enemy' ? '敵詳細' : '味方詳細';
        if (!slotId) {
            return `
                <div class="declare-panel-header">
                    <div class="declare-panel-title">${sideTitle}</div>
                    <div class="declare-panel-header-right">
                        <button id="declare-readonly-min-btn-${side}" class="declare-minimize-btn" title="${this._sideUi?.[side]?.minimized ? '展開' : '最小化'}">${this._sideUi?.[side]?.minimized ? '□' : '－'}</button>
                    </div>
                </div>
                <div class="declare-panel-row">
                    <span>状態</span>
                    <span class="declare-human-label">未選択</span>
                </div>
            `;
        }

        const slot = state?.slots?.[slotId] || null;
        if (!slot) {
            return `
                <div class="declare-panel-header">
                    <div class="declare-panel-title">${sideTitle}</div>
                    <div class="declare-panel-header-right">
                        <button id="declare-readonly-min-btn-${side}" class="declare-minimize-btn" title="${this._sideUi?.[side]?.minimized ? '展開' : '最小化'}">${this._sideUi?.[side]?.minimized ? '□' : '－'}</button>
                    </div>
                </div>
                <div class="declare-panel-row">
                    <span>状態</span>
                    <span class="declare-human-label">スロットなし</span>
                </div>
            `;
        }

        const actorId = slot.actor_id || null;
        const actor = (state.characters || []).find((c) => String(c.id) === String(actorId)) || null;
        const isSource = String(context.sourceSlotId || '') === String(slotId || '');
        const skillId = isSource
            ? (context.skillId || '')
            : String((state?.intents?.[slotId]?.skill_id || '') || '');
        const calc = isSource ? (context.calc || null) : (context.compareCalc || null);
        const meta = this._resolveDisplayMeta(skillId, calc);
        const commandText = this._resolveCommandText(calc) || '';
        const rangeText = this._resolveReadonlyRangeText(meta, calc, actor, skillId);
        const label = this._formatSlotLabel(state, slotId);
        const detailHtml = meta.detailHtml || '';
        const skillDisplay = this._resolveSkillDisplayName(skillId, meta.name, actor);
        const summaryHtml = this._buildMinimizedSummaryHtml(skillDisplay, rangeText);

        return `
            <div class="declare-panel-header">
                <div class="declare-panel-title">${sideTitle}</div>
                <div class="declare-panel-header-right">
                    <button id="declare-readonly-min-btn-${side}" class="declare-minimize-btn" title="${this._sideUi?.[side]?.minimized ? '展開' : '最小化'}">${this._sideUi?.[side]?.minimized ? '□' : '－'}</button>
                </div>
            </div>
            ${summaryHtml}
            <div class="declare-panel-row">
                <span>スロット</span>
                <span class="declare-human-label">${this._escapeHtml(label)}</span>
            </div>
            <div class="declare-panel-row">
                <span>状態</span>
                <span class="declare-human-label">${isSource ? '操作中' : '参照中'}</span>
            </div>
            <div class="declare-skill-meta">
                <div><strong>${this._escapeHtml(skillDisplay)}</strong></div>
                <div>${meta.description || '-'}</div>
                <div>威力レンジ: ${this._escapeHtml(rangeText)}</div>
                <div>コマンド: <code class="declare-command">${this._escapeHtml(commandText || '-')}</code></div>
                ${detailHtml ? `<div class="declare-skill-detail">${detailHtml}</div>` : ''}
            </div>
        `;
    }

    _resolveSkillDisplayName(skillId, metaName, actor) {
        const sid = String(skillId || '').trim();
        const nameFromMeta = String(metaName || '').trim();
        const isMetaUsable = !!(
            nameFromMeta
            && nameFromMeta !== '-'
            && nameFromMeta !== '(none)'
            && nameFromMeta !== sid
        );
        const nameFromCommands = this._findSkillNameFromActorCommands(actor, sid);
        const resolvedName = isMetaUsable ? nameFromMeta : nameFromCommands;
        if (sid && resolvedName && resolvedName !== sid) return `${sid} ${resolvedName}`;
        if (sid) return sid;
        if (resolvedName) return resolvedName;
        return '-';
    }

    _findSkillNameFromActorCommands(actor, skillId) {
        const sid = String(skillId || '').trim();
        if (!sid) return '';
        const commands = String(actor?.commands || '');
        if (!commands) return '';
        const regex = /[\u3010\[]([^ \]\u3011]+)\s+([^\u3011\]]+)[\u3011\]]/g;
        let match;
        while ((match = regex.exec(commands)) !== null) {
            const id = String(match[1] || '').trim();
            const name = String(match[2] || '').trim();
            if (id === sid && name) return name;
        }
        return '';
    }

    _toggleSideMinimized(side) {
        if (!side || !this._sideUi?.[side]) return;
        this._sideUi[side].minimized = !this._sideUi[side].minimized;
        this._render(store.state);
    }

    _buildMinimizedSummaryHtml(skillName, rangeText) {
        const safeSkillName = this._escapeHtml(skillName || '-');
        const safeRangeText = this._escapeHtml(rangeText || '-');
        return `
            <div class="declare-min-summary" aria-hidden="true">
                <div class="declare-min-summary-row"><span class="label">スキル</span><span class="value">${safeSkillName}</span></div>
                <div class="declare-min-summary-row"><span class="label">威力レンジ</span><span class="value">${safeRangeText}</span></div>
            </div>
        `;
    }

    _resolveReadonlyRangeText(meta, calc, actor, skillId) {
        return this._resolvePowerRangeText({ meta, calc, actor, skillId });
    }

    _resolvePowerRangeText({ meta, calc, actor, skillId }) {
        if (calc && calc.min_damage !== undefined && calc.max_damage !== undefined) {
            return `${calc.min_damage} ~ ${calc.max_damage}`;
        }
        const metaRangeText = String(meta?.rangeText || '').trim();
        if (/^-?\d+\s*~\s*-?\d+$/.test(metaRangeText)) {
            return metaRangeText;
        }
        const quick = this._buildQuickPreviewFromSkill(actor, skillId);
        const quickRangeText = String(quick?.rangeText || '').trim();
        if (/^-?\d+\s*~\s*-?\d+$/.test(quickRangeText)) {
            return quickRangeText;
        }
        return '-';
    }

    _resolveCompareTargetSlotId(state, slotId) {
        if (!state || !slotId) return null;
        const intent = state?.intents?.[slotId] || null;
        const target = intent?.target || null;
        const targetType = this._normalizeTargetType(target?.type || intent?.targetType || '');
        if (this._isMassTargetType(targetType)) return null;
        return target?.slot_id || intent?.target_slot_id || null;
    }

    _buildQuickPreviewFromSkill(actor, skillId) {
        const all = window.allSkillData || {};
        const skill = all[skillId];
        if (!skill || typeof skill !== 'object') return null;

        const basePowerRaw = this._firstValue(skill, ['基礎威力', 'base_power', 'power'], 0);
        let basePower = Number.parseInt(basePowerRaw, 10);
        if (!Number.isFinite(basePower)) basePower = 0;

        let palette = String(
            this._firstValue(skill, ['チャットパレット', 'chat_palette', 'command'], '')
        );
        palette = palette.replace(/【.*?】/g, '').trim();
        if (palette.includes(':')) {
            const parts = palette.split(':');
            palette = String(parts[parts.length - 1] || '').trim();
        }

        let dicePart = '';
        const matchBase = palette.match(/^(-?\d+)(.*)$/);
        if (matchBase) {
            if (!Number.isFinite(Number.parseInt(basePowerRaw, 10))) {
                basePower = Number.parseInt(matchBase[1], 10) || 0;
            }
            dicePart = String(matchBase[2] || '').trim();
        } else if (palette) {
            dicePart = palette;
        }
        if (!dicePart) {
            dicePart = String(this._firstValue(skill, ['ダイス威力', 'dice_power'], '2d6') || '2d6');
        }

        const resolvedDice = this._resolveCommandPlaceholders(dicePart, actor);
        const compactDice = String(resolvedDice || '').replace(/\s+/g, '');
        const finalCommand = compactDice
            ? (/^[+-]/.test(compactDice) ? `${basePower}${compactDice}` : `${basePower}+${compactDice}`)
            : String(basePower);
        const range = this._calcRangeFromCommand(finalCommand);
        return {
            finalCommand,
            rangeText: range ? `${range.min} ~ ${range.max}` : '-'
        };
    }

    _resolveCommandPlaceholders(commandText, actor) {
        const raw = String(commandText || '');
        return raw.replace(/\{([^}]+)\}/g, (_m, labelRaw) => {
            const label = String(labelRaw || '').trim();
            return String(this._readActorNumericParam(actor, label));
        });
    }

    _readActorNumericParam(actor, label) {
        if (!actor || !label) return 0;
        const direct = actor[label];
        if (direct !== undefined && direct !== null && direct !== '') {
            const n = Number.parseInt(direct, 10);
            return Number.isFinite(n) ? n : 0;
        }
        const lower = actor[String(label).toLowerCase()];
        if (lower !== undefined && lower !== null && lower !== '') {
            const n = Number.parseInt(lower, 10);
            return Number.isFinite(n) ? n : 0;
        }

        const states = Array.isArray(actor.states) ? actor.states : [];
        const stateRow = states.find((s) => String(s?.name || '').trim() === label);
        if (stateRow) {
            const n = Number.parseInt(stateRow.value, 10);
            return Number.isFinite(n) ? n : 0;
        }

        const params = Array.isArray(actor.params) ? actor.params : [];
        const paramRow = params.find((p) => String(p?.label || '').trim() === label);
        if (paramRow) {
            const n = Number.parseInt(paramRow.value, 10);
            return Number.isFinite(n) ? n : 0;
        }
        return 0;
    }

    _calcRangeFromCommand(commandText) {
        const clean = String(commandText || '')
            .replace(/【.*?】/g, '')
            .replace(/\s+/g, '')
            .trim();
        if (!clean) return null;

        const tokens = clean.split(/([+-])/).filter((t) => t !== '');
        let currentSign = 1;
        let min = 0;
        let max = 0;
        for (const tokenRaw of tokens) {
            const token = String(tokenRaw || '').trim();
            if (!token) continue;
            if (token === '+') {
                currentSign = 1;
                continue;
            }
            if (token === '-') {
                currentSign = -1;
                continue;
            }

            const diceMatch = token.match(/^(\d+)d(\d+)$/i);
            if (diceMatch) {
                const num = Number.parseInt(diceMatch[1], 10);
                const sides = Number.parseInt(diceMatch[2], 10);
                if (!Number.isFinite(num) || !Number.isFinite(sides) || num <= 0 || sides <= 0) continue;
                const tMin = num;
                const tMax = num * sides;
                if (currentSign >= 0) {
                    min += tMin;
                    max += tMax;
                } else {
                    min -= tMax;
                    max -= tMin;
                }
                continue;
            }

            const n = Number.parseInt(token, 10);
            if (Number.isFinite(n)) {
                min += currentSign * n;
                max += currentSign * n;
            }
        }
        return { min, max };
    }

    _resolveFlowGuide({ sourceSlotId, skillId, isMassTarget, effectiveTargetSlotId }) {
        const hasSource = !!sourceSlotId;
        const hasSkill = !!skillId;
        const hasTarget = !!(isMassTarget || effectiveTargetSlotId);

        const step1Class = hasSource ? 'done' : 'active';
        const step2Class = hasSkill ? 'done' : (hasSource ? 'active' : 'pending');
        const step3Class = hasTarget ? 'done' : (hasSkill ? 'active' : 'pending');

        let message = '使用者をクリックしてください。';
        if (hasSource && !hasSkill) {
            message = '使用スキルを選択してください。';
        } else if (hasSkill && !hasTarget) {
            message = isMassTarget
                ? '広域対象です。宣言ボタンで確定できます。'
                : '対象スロットをクリックしてください。';
        } else if (hasSkill && hasTarget) {
            message = '内容を確認して「宣言」を押してください。';
        }

        return { step1Class, step2Class, step3Class, message };
    }

    _normalizeTeam(value) {
        const t = String(value || '').trim().toLowerCase();
        if (['enemy', 'foe', 'opponent', 'npc', 'boss', '敵'].includes(t)) return 'enemy';
        if (['ally', 'friend', 'player', '味方'].includes(t)) return 'ally';
        return 'ally';
    }

    _canEditSourceSlot(state, sourceSlotId) {
        if (!state || !sourceSlotId) return false;
        if (typeof window !== 'undefined' && String(window.currentUserAttribute || '') === 'GM') {
            return true;
        }

        const sourceActorId = state?.slots?.[sourceSlotId]?.actor_id || null;
        if (!sourceActorId) return false;

        if (typeof window !== 'undefined' && typeof window.canControlCharacter === 'function') {
            try {
                return !!window.canControlCharacter(sourceActorId);
            } catch (_) {
                // fallback below
            }
        }

        const actor = (state.characters || []).find((c) => String(c.id) === String(sourceActorId)) || null;
        if (!actor) return false;

        const currentUserId = (typeof window !== 'undefined') ? window.currentUserId : null;
        const currentUsername = (typeof window !== 'undefined') ? window.currentUsername : null;
        const ownerId = actor.owner_id;
        const ownerName = actor.owner;

        if (currentUserId && ownerId && String(currentUserId) === String(ownerId)) return true;
        if (currentUsername && ownerName && String(currentUsername) === String(ownerName)) return true;
        return false;
    }

    _buildSkillOptions(actor, state = null, sourceSlotId = null, selectedTargetSlotId = null) {
        const all = window.allSkillData || {};
        const candidates = this._extractActorSkillCandidates(actor, all);
        const selectedSkillId = (store.get('declare') || {}).skillId || '';
        const options = ['<option value="">-- スキル --</option>'];
        candidates.slice(0, 400).forEach((item) => {
            const id = item.id;
            if (
                selectedTargetSlotId
                && !this._isSkillCompatibleWithTarget(state, sourceSlotId, selectedTargetSlotId, id)
            ) {
                return;
            }
            const meta = this._readSkillMeta(id);
            const displayName = item.name || meta.name || id;
            const costLabel = this._formatSkillCostLabel(this._extractCosts(id, null));
            const selected = (id === selectedSkillId) ? ' selected' : '';
            options.push(`<option value="${id}"${selected}>[${id}] ${displayName}${costLabel}</option>`);
        });
        return options.join('');
    }

    _isSkillCompatibleWithTarget(state, sourceSlotId, targetSlotId, skillId) {
        if (!state || !sourceSlotId || !targetSlotId || !skillId) return true;
        const slots = state?.slots || {};
        const sourceSlot = slots?.[sourceSlotId] || null;
        const targetSlot = slots?.[targetSlotId] || null;
        if (!sourceSlot || !targetSlot) return true;
        const sourceTeam = String(sourceSlot.team || '').toLowerCase();
        const targetTeam = String(targetSlot.team || '').toLowerCase();
        if (!sourceTeam || !targetTeam) return true;
        const scope = this._inferTargetScopeFromSkill(skillId);
        return this._isTargetTeamAllowedByScope(sourceTeam, targetTeam, scope);
    }

    _buildTargetOptions(state, sourceSlotId, selectedTargetSlotId, targetType = 'single_slot', skillId = null) {
        const normalizedType = this._normalizeTargetType(targetType);
        if (this._isMassTargetType(normalizedType)) {
            return `<option value="">${this._escapeHtml(this._getMassTargetLabel(state?.slots?.[sourceSlotId] || null))}</option>`;
        }
        const slots = state?.slots || {};
        const sourceSlot = sourceSlotId ? slots[sourceSlotId] : null;
        const sourceActorId = sourceSlot?.actor_id || null;
        const sourceChar = (state?.characters || []).find((c) => String(c.id) === String(sourceActorId)) || null;
        const sourceTeam = sourceSlot?.team || sourceChar?.type || null;
        const targetScope = this._inferTargetScopeFromSkill(skillId);
        const options = ['<option value="">-- 対象スロット --</option>'];
        const rows = [];

        Object.keys(slots).forEach((slotId) => {
            const slot = slots[slotId];
            if (!slot || String(slotId) === String(sourceSlotId)) return;

            const actorId = slot.actor_id;
            if (sourceActorId && actorId && String(actorId) === String(sourceActorId)) return;
            if (
                sourceTeam
                && slot.team
                && !this._isTargetTeamAllowedByScope(
                    String(sourceTeam).toLowerCase(),
                    String(slot.team).toLowerCase(),
                    targetScope
                )
            ) {
                return;
            }
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

        const power = this._firstValue(
            skill,
            ['power', 'base_power', '基礎威力', '威力'],
            this._findByKeyPattern(skill, /power|atk|威力|基礎/i) || '-'
        );
        const range = this._firstValue(
            skill,
            ['range', 'attack_range', 'target_range', 'distance', '射程', '距離'],
            this._findByKeyPattern(skill, /range|distance|target|射程|距離/i) || '-'
        );
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

        const pb = (calc?.power_breakdown && typeof calc.power_breakdown === 'object')
            ? calc.power_breakdown
            : {};
        const ruleBaseMod = Number(pb.rule_power_bonus || 0);
        const baseMod = Number(calc?.skill_details?.base_power_mod || 0) + ruleBaseMod;
        if (baseMod !== 0) rows.push(`[基礎威力 ${baseMod > 0 ? '+' : ''}${baseMod}]`);

        const correctionDetails = Array.isArray(calc?.correction_details) ? calc.correction_details : [];
        correctionDetails.forEach((detail) => {
            const source = String(detail?.source || '補正');
            if (source === '威力補正') return;
            const value = Number(detail?.value || 0);
            if (value !== 0) {
                rows.push(`[${source} ${value > 0 ? '+' : ''}${value}]`);
            }
        });

        const senritsuPenalty = Number(calc?.senritsu_dice_reduction || 0);
        if (senritsuPenalty > 0) {
            rows.push(`[ダイス威力 -${senritsuPenalty}] (戦慄)`);
        }

        if (pb && typeof pb === 'object') {
            const base = Number(pb.base_power ?? NaN);
            const finalBase = Number(pb.final_base_power ?? NaN);
            if (!Number.isNaN(base) && !Number.isNaN(finalBase) && base !== finalBase) {
                rows.push(`[基礎威力 ${base} -> ${finalBase}]`);
            }

            const keyRows = [
                ['dice_count_mod', 'ダイス個数'],
                ['dice_face_mod', 'ダイス面数'],
                ['dice_bonus_mod', 'ダイス固定値']
            ];
            keyRows.forEach(([key, label]) => {
                const val = Number(pb[key] || 0);
                if (val !== 0) rows.push(`[${label} ${val > 0 ? '+' : ''}${val}]`);
            });
        }
        const deduped = [];
        const seen = new Set();
        rows.forEach((row) => {
            const text = String(row || '').trim();
            if (!text || seen.has(text)) return;
            seen.add(text);
            deduped.push(text);
        });
        return deduped;
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
        const sourceIntent = state?.intents?.[sourceSlotId] || null;
        // Keep committed declaration stable until explicit re-commit.
        if (sourceIntent?.committed) return;

        const roomId = state.room_id || state.room_name || window.currentRoomName || null;
        const battleId = state.battle_id || null;
        if (!roomId || !battleId) return;

        const targetType = this._resolveEffectiveTargetType(skillId, declare?.targetType || 'single_slot');
        let target = { type: 'none', slot_id: null };
        if (this._isMassTargetType(targetType)) {
            target = { type: targetType, slot_id: null };
        } else if (declare?.targetSlotId) {
            target = { type: 'single_slot', slot_id: declare.targetSlotId };
        }

        socketClient.sendIntentPreview(roomId, battleId, sourceSlotId, skillId, target);
    }

    _requestCalc(state, declare, force = false) {
        const sourceSlotId = declare?.sourceSlotId || null;
        const skillId = declare?.skillId || null;
        if (!sourceSlotId || !skillId) return;
        if (state.phase !== 'select') return;

        const targetType = this._resolveEffectiveTargetType(skillId, declare?.targetType || 'single_slot');
        const targetSlotId = declare?.targetSlotId || null;
        const calcKey = `${sourceSlotId}|${skillId}|${targetType}|${targetSlotId || 'none'}`;
        if (!force && this._lastCalcKey === calcKey) return;
        this._lastCalcKey = calcKey;

        const sourceActorId = state.slots?.[sourceSlotId]?.actor_id || null;
        const targetActorId = (this._isMassTargetType(targetType) || !targetSlotId)
            ? null
            : (state.slots?.[targetSlotId]?.actor_id || null);
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

    _requestCompareCalc(state, slotId, skillId, targetSlotId = null, force = false) {
        const compareSlotId = slotId || null;
        const compareSkillId = skillId || null;
        if (!compareSlotId || !compareSkillId) return;
        if (state.phase !== 'select') return;

        const calcKey = `${compareSlotId}|${compareSkillId}|${targetSlotId || 'none'}`;
        const compareKeyMap = this._lastCompareCalcKeyBySlot || {};
        const hasCurrentCalc = Object.prototype.hasOwnProperty.call(
            (state?.compareCalcBySlot || {}),
            String(compareSlotId)
        );
        if (!force && compareKeyMap[compareSlotId] === calcKey && hasCurrentCalc) return;
        this._lastCompareCalcKeyBySlot[compareSlotId] = calcKey;

        const sourceActorId = state?.slots?.[compareSlotId]?.actor_id || null;
        const targetActorId = targetSlotId
            ? (state?.slots?.[targetSlotId]?.actor_id || null)
            : null;
        if (!sourceActorId) return;

        socketClient.declareSkill({
            actor_id: sourceActorId,
            target_id: targetActorId,
            skill_id: compareSkillId,
            modifier: 0,
            prefix: `declare_compare_${compareSlotId}`,
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
                const skillData = allSkillMap[id];
                if (skillData && !this._isInstantSkillData(skillData)) {
                    seen.add(id);
                    list.push({ id, name: name || this._readSkillMeta(id).name });
                }
            }
        }

        if (list.length > 0) return list;
        return idsAll
            .filter((id) => !this._isInstantSkillData(allSkillMap[id]))
            .map((id) => ({ id, name: this._readSkillMeta(id).name }));
    }

    _isInstantSkillData(skillData) {
        if (!skillData || typeof skillData !== 'object') return false;
        const tags = Array.isArray(skillData.tags) ? skillData.tags : [];
        if (tags.some((t) => String(t || '').trim() === '即時発動')) return true;

        const rule = this._extractRuleData(skillData) || {};
        const ruleTags = Array.isArray(rule.tags) ? rule.tags : [];
        if (ruleTags.some((t) => String(t || '').trim() === '即時発動')) return true;
        return false;
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
        const text = `コスト不足: ${shortages.map(s => `${s.type} ${s.required}必要 (現在 ${s.current})`).join(' / ')}`;
        return { insufficient: true, message: text };
    }

    _formatSkillCostLabel(costs) {
        if (!Array.isArray(costs) || costs.length === 0) return '';

        const normalized = [];
        for (const c of costs) {
            const type = String(c?.type || '').toUpperCase();
            const value = Number(c?.value || 0);
            if (!type || !Number.isFinite(value) || value <= 0) continue;
            normalized.push({ type, value: Math.trunc(value) });
        }
        if (normalized.length === 0) return '';

        const preferredOrder = ['FP', 'MP', 'HP'];
        normalized.sort((a, b) => {
            const ia = preferredOrder.indexOf(a.type);
            const ib = preferredOrder.indexOf(b.type);
            if (ia === -1 && ib === -1) return String(a.type).localeCompare(String(b.type), 'ja');
            if (ia === -1) return 1;
            if (ib === -1) return -1;
            return ia - ib;
        });

        const text = normalized.map((row) => `${row.type}:${row.value}`).join(', ');
        return `（${text}）`;
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
            const key = String(k || '');
            const lower = key.toLowerCase();
            return lower.includes('rule')
                || lower.includes('special')
                || key.includes('特記処理');
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

        // Fallback: parse any JSON-like field and pick one that looks like rule JSON.
        for (const key of Object.keys(skill)) {
            const raw = skill[key];
            if (typeof raw !== 'string') continue;
            const trimmed = raw.trim();
            if (!trimmed.startsWith('{')) continue;
            try {
                const parsed = JSON.parse(trimmed);
                if (
                    parsed
                    && typeof parsed === 'object'
                    && (
                        Array.isArray(parsed.cost)
                        || Array.isArray(parsed.effects)
                        || Array.isArray(parsed.tags)
                        || typeof parsed.deals_damage === 'boolean'
                        || parsed.target_scope !== undefined
                        || parsed.target_team !== undefined
                    )
                ) {
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

    _normalizeTargetType(type) {
        const t = String(type || '').trim();
        if (t === 'single_slot' || t === 'mass_individual' || t === 'mass_summation' || t === 'none') {
            return t;
        }
        return 'single_slot';
    }

    _normalizeTargetScope(scope) {
        const s = String(scope || '').trim().toLowerCase();
        if (['enemy', 'enemies', 'foe', 'opponent', 'opponents', '敵', '敵対', 'opposing_team', '相手陣営', '相手陣営対象', '相手陣営指定'].includes(s)) return 'enemy';
        if (['ally', 'allies', 'friend', 'friends', '味方', '味方対象', '味方指定', '同陣営', '同陣営対象', '同陣営指定', 'same_team'].includes(s)) return 'ally';
        if (['any', 'all', 'both', '全体', 'all_targets'].includes(s)) return 'any';
        return 'enemy';
    }

    _isTargetTeamAllowedByScope(sourceTeam, targetTeam, scope) {
        const normalizedScope = this._normalizeTargetScope(scope);
        if (normalizedScope === 'any') return true;
        if (normalizedScope === 'ally') return String(sourceTeam) === String(targetTeam);
        return String(sourceTeam) !== String(targetTeam);
    }

    _inferTargetScopeFromSkill(skillId) {
        if (!skillId) return 'enemy';
        const all = window.allSkillData || {};
        const skill = all[skillId] || {};
        const rule = this._extractRuleData(skill) || {};
        const candidates = [
            skill.target_scope,
            skill.targetScope,
            skill.target_team,
            skill.targetTeam,
            rule.target_scope,
            rule.targetScope,
            rule.target_team,
            rule.targetTeam
        ];
        for (const raw of candidates) {
            const text = String(raw || '').trim().toLowerCase();
            if (!text) continue;
            if (['enemy', 'enemies', 'foe', 'opponent', 'opponents', '敵', '敵対', 'opposing_team', '相手陣営', '相手陣営対象', '相手陣営指定'].includes(text)) return 'enemy';
            if (['ally', 'allies', 'friend', 'friends', '味方', '味方対象', '味方指定', '同陣営', '同陣営対象', '同陣営指定', 'same_team'].includes(text)) return 'ally';
            if (['any', 'all', 'both', '全体', 'all_targets'].includes(text)) return 'any';
        }

        const tags = []
            .concat(Array.isArray(skill.tags) ? skill.tags : [])
            .concat(Array.isArray(rule.tags) ? rule.tags : [])
            .map((t) => String(t || '').trim().toLowerCase())
            .filter(Boolean);
        if (tags.some((t) => ['any_target', 'target_any', '任意対象', '対象自由'].includes(t))) return 'any';
        if (tags.some((t) => ['ally_target', 'target_ally', '味方対象', '味方指定', '同陣営', '同陣営対象', '同陣営指定'].includes(t))) return 'ally';
        if (tags.some((t) => ['enemy_target', 'target_enemy', '敵対象', '相手陣営対象', '相手陣営指定'].includes(t))) return 'enemy';
        return 'enemy';
    }

    _isMassTargetType(type) {
        const t = this._normalizeTargetType(type);
        return t === 'mass_individual' || t === 'mass_summation';
    }

    _resolveEffectiveTargetType(skillId, currentType = 'single_slot') {
        const normalizedCurrent = this._normalizeTargetType(currentType);
        const inferred = this._inferTargetTypeFromSkill(skillId);
        if (!skillId) {
            return normalizedCurrent;
        }
        if (this._isMassTargetType(inferred)) return inferred;
        return 'single_slot';
    }

    _inferTargetTypeFromSkill(skillId) {
        if (!skillId) return 'single_slot';
        const all = window.allSkillData || {};
        const skill = all[skillId] || {};
        const directCandidates = [
            skill.mass_type,
            skill.target_type,
            skill.targeting,
            skill.targetType
        ];
        for (const raw of directCandidates) {
            const t = this._normalizeTargetType(raw);
            if (this._isMassTargetType(t)) return t;
        }

        const rule = this._extractRuleData(skill) || {};
        const ruleCandidates = [rule.mass_type, rule.target_type, rule.targeting, rule.targetType];
        for (const raw of ruleCandidates) {
            const t = this._normalizeTargetType(raw);
            if (this._isMassTargetType(t)) return t;
        }

        const tags = []
            .concat(Array.isArray(skill.tags) ? skill.tags : [])
            .concat(Array.isArray(rule.tags) ? rule.tags : [])
            .map((v) => String(v || '').toLowerCase());
        const cat = String(skill['category'] || skill['分類'] || skill['カテゴリ'] || '').toLowerCase();
        const dist = String(skill['distance'] || skill['距離'] || skill['射程'] || '').toLowerCase();
        const merged = `${tags.join(' ')} ${cat} ${dist}`;

        if (
            merged.includes('mass_summation')
            || merged.includes('広域-合算')
            || merged.includes('合算')
        ) {
            return 'mass_summation';
        }
        if (
            merged.includes('mass_individual')
            || merged.includes('広域-個別')
            || merged.includes('個別')
        ) {
            return 'mass_individual';
        }

        if (merged.includes('広域')) {
            return 'mass_individual';
        }

        if (typeof window.isWideSkillData === 'function' && window.isWideSkillData(skill)) {
            return 'mass_individual';
        }
        return 'single_slot';
    }

    _resolveDeclareMode(targetType, targetSlotId) {
        if (this._isMassTargetType(targetType)) return 'ready';
        return targetSlotId ? 'ready' : 'choose_target';
    }

    _getMassTargetLabel(sourceSlot) {
        const sourceTeam = String(sourceSlot?.team || '').toLowerCase();
        if (sourceTeam === 'ally') return '敵全体（固定）';
        if (sourceTeam === 'enemy') return '味方全体（固定）';
        return '対象陣営全体（固定）';
    }
}

export const declarePanel = new DeclarePanel();

if (typeof window !== 'undefined') {
    window.DeclarePanelComponent = declarePanel;
}




