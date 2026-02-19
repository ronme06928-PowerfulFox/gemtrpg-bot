/* static/js/visual/visual_map.js */

/**
 * Updates the CSS transform of the map container based on current scale and offset.
 */
window.updateMapTransform = function () {
    const mapEl = document.getElementById('game-map');
    if (mapEl) mapEl.style.transform = `translate(${visualOffsetX}px, ${visualOffsetY}px) scale(${visualScale})`;
}

/**
 * Main Map Rendering Function
 * Handles background updates and token rendering (differential update).
 */
window.renderVisualMap = function () {
    const tokenLayer = document.getElementById('map-token-layer');
    if (!tokenLayer) return;

    updateMapTransform();

    // Background Image Handling
    const mapEl = document.getElementById('game-map');
    if (mapEl && battleState.battle_map_data) {
        const bgData = battleState.battle_map_data;
        if (bgData.background_image) {
            const newBg = `url('${bgData.background_image}')`;
            if (mapEl.style.backgroundImage !== newBg.replace(/'/g, '"') && mapEl.style.backgroundImage !== newBg) {
                mapEl.style.backgroundImage = newBg;
            }
            mapEl.style.backgroundSize = 'contain';
            mapEl.style.backgroundRepeat = 'no-repeat';
            mapEl.style.backgroundPosition = 'center';
        } else {
            mapEl.style.backgroundImage = '';
        }
    }

    if (typeof battleState === 'undefined' || !battleState.characters) return;
    const srStateForTurn = _getSelectResolveStateRef();
    const srPhaseForTurn = srStateForTurn?.phase || null;
    const suppressLegacyTurnHighlight = ['select', 'resolve_mass', 'resolve_single'].includes(srPhaseForTurn);
    const currentTurnId = suppressLegacyTurnHighlight ? null : (battleState.turn_char_id || null);

    // 1. Map existing tokens
    const existingTokens = {};
    document.querySelectorAll('#map-token-layer .map-token').forEach(el => {
        if (el.dataset.id) {
            existingTokens[el.dataset.id] = el;
        }
    });

    // 2. Identify valid character IDs
    const validCharIds = new Set();

    battleState.characters.forEach(char => {
        if (char.x >= 0 && char.y >= 0 && char.hp > 0) {
            validCharIds.add(char.id);



            // Global Local State Override (Optimistic UI)
            if (window._localCharPositions && window._localCharPositions[char.id]) {
                const localMove = window._localCharPositions[char.id];
                const serverTS = char.last_move_ts || 0;

                if (serverTS < localMove.ts) {
                    char.x = localMove.x;
                    char.y = localMove.y;
                }
            }

            let token = existingTokens[char.id];

            if (token) {
                // Update Existing Token
                if (char.id === currentTurnId) {
                    if (!token.classList.contains('active-turn')) token.classList.add('active-turn');

                    // Check and Add Wide Button if missing
                    const isWideMatchExecuting = battleState.active_match && battleState.active_match.is_active && battleState.active_match.match_type === 'wide';
                    let wideBtn = token.querySelector('.wide-attack-trigger-btn');

                    if (char.isWideUser && !isWideMatchExecuting) {
                        if (!wideBtn) {
                            // Create button
                            const btnHtml = '<button class="wide-attack-trigger-btn" style="transform: scale(1.2); top: -40px; font-size: 1.1em;" onclick="event.stopPropagation(); window._dragBlockClick = true; setTimeout(() => { window._dragBlockClick = false; }, 100); openSyncedWideMatchModal(\'' + char.id + '\');">⚡ 広域</button>';
                            // Prepend to token (similar to createMapToken)
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = btnHtml;
                            const newBtn = tempDiv.firstElementChild;
                            token.insertBefore(newBtn, token.firstChild);
                        }
                    } else {
                        // Remove if exists but shouldn't (e.g. executed)
                        if (wideBtn) wideBtn.remove();
                    }
                } else {
                    if (token.classList.contains('active-turn')) token.classList.remove('active-turn');
                    // Cleanup Wide Button if not turn char
                    const wideBtn = token.querySelector('.wide-attack-trigger-btn');
                    if (wideBtn) wideBtn.remove();
                }

                // Update Position (Skip if dragging)
                const isDragging = token.classList.contains('dragging');
                const inCooldown = window._dragEndTime && (Date.now() - window._dragEndTime < 100);

                if (!isDragging && !inCooldown) {
                    const left = char.x * GRID_SIZE + TOKEN_OFFSET;
                    const top = char.y * GRID_SIZE + TOKEN_OFFSET;
                    const newLeft = `${left}px`;
                    const newTop = `${top}px`;

                    if (token.style.left !== newLeft || token.style.top !== newTop) {
                        token.style.left = newLeft;
                        token.style.top = newTop;
                    }
                }

                // Update internals
                updateTokenVisuals(token, char);

            } else {
                // Create New Token
                token = createMapToken(char);
                if (char.id === currentTurnId) token.classList.add('active-turn');
                tokenLayer.appendChild(token);
            }
        }
    });

    // 3. Remove invalid tokens
    Object.keys(existingTokens).forEach(id => {
        if (!validCharIds.has(id)) {
            const el = existingTokens[id];
            el.remove();
        }
    });

    // Inject GM Background Settings Button
    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
    if (isGM && !document.getElementById('battle-bg-settings-btn')) {
        const zIn = document.getElementById('zoom-in-btn');
        if (zIn && zIn.parentElement) {
            const btn = document.createElement('button');
            btn.id = 'battle-bg-settings-btn';
            btn.innerHTML = '🖼️'; // Image Icon
            btn.title = '戦闘背景設定';
            btn.className = 'map-control-btn';
            btn.style.marginLeft = '5px';
            btn.onclick = () => {
                if (typeof openImagePicker === 'function') {
                    openImagePicker((selectedImage) => {
                        socket.emit('request_update_battle_background', {
                            room: currentRoomName,
                            imageUrl: selectedImage.url,
                            scale: 1.0,
                            offsetX: 0,
                            offsetY: 0
                        });
                    }, 'background');
                } else {
                    const url = prompt("背景画像のURLを入力してください:", battleState.battle_map_data?.background_image || "");
                    if (url) {
                        socket.emit('request_update_battle_background', {
                            room: currentRoomName,
                            imageUrl: url
                        });
                    }
                }
            };
            zIn.parentElement.appendChild(btn);
        }
    }

    // 4. Render Select/Resolve slot badges on tokens (select phase)
    if (typeof window.renderSlotBadgesForAllTokens === 'function') {
        window.renderSlotBadgesForAllTokens();
    }

    // 5. Render Arrows (depends on slot badge anchors in select phase)
    if (typeof window.renderArrows === 'function') {
        window.renderArrows();
    }
}

window.renderSlotBadgesForAllTokens = function () {
    const tokenLayer = document.getElementById('map-token-layer');
    if (!tokenLayer) return;

    const storeState = (window.BattleStore && window.BattleStore.state) ? window.BattleStore.state : null;
    const legacyState = window.battleState || {};
    const storeChars = Array.isArray(storeState?.characters) ? storeState.characters.length : 0;
    const storeSlots = storeState?.slots
        ? (Array.isArray(storeState.slots) ? storeState.slots.length : Object.keys(storeState.slots).length)
        : 0;
    const legacyChars = Array.isArray(legacyState?.characters) ? legacyState.characters.length : 0;
    const legacySlots = legacyState?.slots
        ? (Array.isArray(legacyState.slots) ? legacyState.slots.length : Object.keys(legacyState.slots).length)
        : 0;

    const preferStore = !!(storeState && (storeChars > 0 || storeSlots > 0));
    const phase = (preferStore ? storeState?.phase : legacyState?.phase) || 'select';
    const characters = (storeChars > 0 ? storeState.characters : (legacyState.characters || []));
    const rawSlots = (storeSlots > 0 ? storeState.slots : (legacyState.slots || {}));
    const intents = (() => {
        const s = storeState?.intents || {};
        const l = legacyState?.intents || {};
        const sLen = Array.isArray(s) ? s.length : Object.keys(s).length;
        const lLen = Array.isArray(l) ? l.length : Object.keys(l).length;
        return sLen >= lLen ? s : l;
    })();
    const selectedSlotId = storeState?.selectedSlotId || legacyState?.selectedSlotId || null;
    const slots = Array.isArray(rawSlots)
        ? rawSlots
        : Object.entries(rawSlots).map(([sid, slot]) => ({
            ...(slot || {}),
            slot_id: (slot && slot.slot_id) ? slot.slot_id : sid
        }));
    const stateRef = preferStore ? (storeState || {}) : (legacyState || {});
    const declare = stateRef?.declare || {};
    const declareMode = declare.mode || 'idle';
    const declareSourceSlotId = declare.sourceSlotId || null;
    const declareTargetSlotId = declare.targetSlotId || null;
    const declareTargetType = _normalizeDeclareTargetType(declare.targetType || 'single_slot');
    const isMassDeclare = _isMassDeclareTargetType(declareTargetType);
    const isTargetPending = !!(
        declareSourceSlotId
        && !isMassDeclare
        && !declareTargetSlotId
        && (declareMode === 'choose_target' || declareMode === 'ready')
    );
    const slotsById = {};
    slots.forEach((slot) => {
        const sid = String(slot?.slot_id ?? slot?.id ?? '');
        if (!sid) return;
        slotsById[sid] = slot || {};
    });
    const sourceSlot = declareSourceSlotId ? (slotsById[String(declareSourceSlotId)] || null) : null;
    const sourceActorId = sourceSlot?.actor_id ?? sourceSlot?.actor_char_id ?? null;
    const sourceTeam = sourceSlot?.team ?? null;

    tokenLayer.querySelectorAll('.slot-badge-container').forEach(el => el.remove());
    _ensureSelectResolveClickAwayHandler();
    _renderSelectResolveModeHint(phase, stateRef);

    const now = Date.now();
    if (!window._slotBadgeLogAt || now - window._slotBadgeLogAt > 600) {
        const perActor = {};
        for (const slot of slots) {
            const actorId = slot?.actor_id ?? slot?.actor_char_id;
            if (!actorId) continue;
            const key = String(actorId);
            perActor[key] = (perActor[key] || 0) + 1;
        }
        const source = preferStore ? 'BattleStore' : 'battleState';
        console.log(`[slot_badges] source=${source} phase=${phase} chars=${characters.length} slots=${slots.length} per_actor=${JSON.stringify(perActor)}`);
        window._slotBadgeLogAt = now;
    }

    if (phase !== 'select' || slots.length === 0) {
        return;
    }

    const tokenEls = tokenLayer.querySelectorAll('.map-token[data-id]');
    tokenEls.forEach(token => {
        const charId = String(token.dataset.id || '');
        if (!charId) return;

        const actorSlots = slots
            .filter(slot => String(slot?.actor_id ?? slot?.actor_char_id ?? '') === charId)
            .sort((a, b) => {
                const ai = Number(a?.index_in_actor ?? 9999);
                const bi = Number(b?.index_in_actor ?? 9999);
                if (ai !== bi) return ai - bi;
                const ain = Number(a?.initiative ?? 0);
                const bin = Number(b?.initiative ?? 0);
                return bin - ain;
            });

        if (actorSlots.length === 0) return;

        const container = document.createElement('div');
        container.className = 'slot-badge-container';

        actorSlots.forEach(slot => {
            const slotId = slot?.slot_id ?? slot?.id;
            const actorId = slot?.actor_id ?? slot?.actor_char_id ?? null;
            const intent = (slotId && intents) ? (intents[slotId] || {}) : {};
            const committed = !!intent?.committed;
            const lockedTarget = !!slot?.locked_target || !!intent?.locked_target;
            const initiative = Number(slot?.initiative ?? 0);

            const badge = document.createElement('div');
            const isSelected = selectedSlotId && String(selectedSlotId) === String(slotId);
            const isSource = !!(declareSourceSlotId && String(declareSourceSlotId) === String(slotId));
            const isCurrentTarget = !!(declareTargetSlotId && String(declareTargetSlotId) === String(slotId));
            const sameActorAsSource = !!(sourceActorId && actorId && String(sourceActorId) === String(actorId));
            const sameTeamAsSource = !!(sourceTeam && slot?.team && String(sourceTeam) === String(slot.team));
            const isTargetCandidate = !!(
                isTargetPending
                && !isSource
                && !sameActorAsSource
                && !sameTeamAsSource
                && !slot?.disabled
            );

            badge.className = `slot-badge${committed ? ' is-committed' : ''}${lockedTarget ? ' is-locked' : ''}${isSelected ? ' is-selected' : ''}${isSource ? ' is-source' : ''}${isTargetCandidate ? ' is-target-candidate' : ''}${isCurrentTarget ? ' is-target-selected' : ''}`;
            badge.title = _buildSlotBadgeTitle(slotId, initiative, stateRef);
            if (slotId) badge.dataset.slotId = String(slotId);
            if (actorId) badge.dataset.actorId = String(actorId);

            const num = document.createElement('span');
            num.className = 'slot-badge-num';
            num.textContent = String(initiative);
            badge.appendChild(num);

            badge.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();

                if (!slotId) return;
                if (phase !== 'select') return;
                _scheduleSlotBadgeSingleClick(() => {
                    console.log(`[slot_badges] clicked slot=${slotId} actor=${actorId || 'unknown'}`);
                    _handleDeclareSlotClick(String(slotId), String(actorId || ''));
                });
            });

            badge.addEventListener('dblclick', (e) => {
                e.preventDefault();
                e.stopPropagation();

                if (!slotId) return;
                if (phase !== 'select') return;
                _cancelSlotBadgeSingleClick();
                console.log(`[slot_badges] dblclick slot=${slotId} actor=${actorId || 'unknown'}`);
                _handleDeclareSlotDoubleClick(String(slotId), String(actorId || ''));
            });

            container.appendChild(badge);
        });

        token.appendChild(container);
    });
};

function _cancelSlotBadgeSingleClick() {
    if (window._slotBadgeSingleClickTimer) {
        clearTimeout(window._slotBadgeSingleClickTimer);
        window._slotBadgeSingleClickTimer = null;
    }
}

function _scheduleSlotBadgeSingleClick(handler) {
    _cancelSlotBadgeSingleClick();
    window._slotBadgeSingleClickTimer = setTimeout(() => {
        window._slotBadgeSingleClickTimer = null;
        try {
            handler();
        } catch (e) {
            console.error('[slot_badges] single-click handler failed', e);
        }
    }, 190);
}

function _getSelectResolveStateRef() {
    if (window.BattleStore && window.BattleStore.state) {
        return window.BattleStore.state;
    }
    if (typeof battleState !== 'undefined' && battleState) {
        return battleState;
    }
    return {};
}

function _resolveTargetSlotIdForActor(actorId, stateRef) {
    if (!actorId || !stateRef) return null;
    const slotsMap = stateRef.slots || {};
    const timeline = Array.isArray(stateRef.timeline) ? stateRef.timeline : [];

    const candidates = Object.entries(slotsMap)
        .map(([sid, slot]) => ({
            slot_id: (slot && slot.slot_id) ? slot.slot_id : sid,
            ...(slot || {})
        }))
        .filter(slot => String(slot.actor_id || slot.actor_char_id || '') === String(actorId));

    if (candidates.length === 0) return null;

    if (timeline.length > 0) {
        for (const timelineSlotId of timeline) {
            const found = candidates.find(s => String(s.slot_id) === String(timelineSlotId));
            if (found) return found.slot_id;
        }
    }

    candidates.sort((a, b) => {
        const ai = Number(a.initiative ?? 0);
        const bi = Number(b.initiative ?? 0);
        if (ai !== bi) return bi - ai;
        return String(a.slot_id).localeCompare(String(b.slot_id));
    });
    return candidates[0].slot_id;
}

function _pickPreviewSkillId(stateRef, slotId) {
    const intentSkill = stateRef?.intents?.[slotId]?.skill_id;
    if (intentSkill) return intentSkill;

    const all = window.allSkillData || {};
    const preferred = 'basic_attack';
    if (all[preferred]) return preferred;

    const ids = Object.keys(all);
    if (ids.length === 0) return preferred;

    for (const id of ids) {
        const skill = all[id] || {};
        const text = [
            skill.name,
            skill.description,
            skill.summary,
            skill.type,
            skill.category
        ].filter(Boolean).join(' ').toLowerCase();
        if (/attack|atk|攻撃|斬/.test(text)) {
            return id;
        }
    }

    return ids[0];
}

function _getSkillTooltipMeta(skillId) {
    const all = window.allSkillData || {};
    const skill = (skillId && all[skillId]) ? all[skillId] : null;
    if (!skill) return null;
    const name = skill.name || skill.default_name || skill.skill_name || skillId;
    const description = skill.description || skill.desc || skill.summary || '';
    const shortDesc = String(description || '').replace(/\s+/g, ' ').slice(0, 80);
    return { name, shortDesc };
}

function _formatSlotLabelForTooltip(stateRef, slotId) {
    if (!slotId) return '-';
    const slot = stateRef?.slots?.[slotId];
    if (!slot) return '-';

    const actorId = slot.actor_id ?? slot.actor_char_id ?? null;
    const actor = (stateRef?.characters || []).find((c) => String(c.id) === String(actorId));
    const actorName = actor?.name || actorId || 'unknown';
    const indexRaw = Number(slot.index_in_actor ?? 0);
    const index = Number.isFinite(indexRaw) ? (indexRaw + 1) : 1;
    return `${actorName} #${index}`;
}

function _formatIntentTargetForTooltip(stateRef, targetRaw) {
    const target = (targetRaw && typeof targetRaw === 'object') ? targetRaw : {};
    const targetType = _normalizeDeclareTargetType(target.type || 'none');
    if (targetType === 'single_slot') {
        const targetSlotId = target.slot_id || target.slotId || null;
        return targetSlotId ? _formatSlotLabelForTooltip(stateRef, targetSlotId) : '-';
    }
    if (targetType === 'mass_individual') return 'mass_individual';
    if (targetType === 'mass_summation') return 'mass_summation';
    return '-';
}

function _buildSlotBadgeTitle(slotId, initiative, stateRef) {
    const actorId = _getActorIdBySlotId(stateRef, slotId);
    const slot = stateRef?.slots?.[slotId];
    const index = Number(slot?.index_in_actor ?? 0) + 1;
    const actor = (stateRef?.characters || []).find((c) => String(c.id) === String(actorId));
    const actorName = actor?.name || 'actor';
    const base = `${actorName} #${index} / SPD:${initiative}`;
    const intent = stateRef?.intents?.[slotId] || null;
    if (!intent?.committed) return base;

    const skillId = intent?.skill_id || null;
    const targetSummary = _formatIntentTargetForTooltip(stateRef, intent?.target || {});
    if (!skillId) {
        return `${base}\nskill_id: -\ntarget: ${targetSummary}`;
    }

    const meta = _getSkillTooltipMeta(skillId);
    const lines = [
        base,
        `skill_id: ${skillId}`,
        `skill: ${meta?.name || skillId}`,
        `target: ${targetSummary}`
    ];
    if (meta?.shortDesc) {
        lines.push(meta.shortDesc);
    }
    return lines.join('\n');
}

function _isTargetSelectionPendingState(stateRef) {
    if (!stateRef || stateRef.phase !== 'select') return false;
    const declare = stateRef.declare || {};
    const sourceSlotId = declare.sourceSlotId || null;
    if (!sourceSlotId) return false;
    const targetType = _normalizeDeclareTargetType(declare.targetType || 'single_slot');
    if (_isMassDeclareTargetType(targetType)) return false;
    const targetSlotId = declare.targetSlotId || null;
    if (targetSlotId) return false;
    const mode = declare.mode || 'idle';
    return mode === 'choose_target' || mode === 'ready';
}

function _resetDeclareSelectionState(reason = 'outside_click') {
    if (window.BattleStore && typeof window.BattleStore.resetDeclare === 'function') {
        window.BattleStore.resetDeclare();
        if (typeof window.BattleStore.setSelectedSlotId === 'function') {
            window.BattleStore.setSelectedSlotId(null);
        }
        console.log(`[declare] selection_cleared reason=${reason}`);
        return true;
    }

    if (typeof battleState !== 'undefined' && battleState) {
        battleState.selectedSlotId = null;
        battleState.declare = {
            sourceSlotId: null,
            targetSlotId: null,
            targetType: 'single_slot',
            lastSingleTargetSlotId: null,
            skillId: null,
            mode: 'idle',
            calc: null
        };
        console.log(`[declare] selection_cleared_legacy reason=${reason}`);
        return true;
    }
    return false;
}

function _ensureSelectResolveClickAwayHandler() {
    if (window._selectResolveClickAwayBound) return;
    window._selectResolveClickAwayBound = true;

    document.addEventListener('click', (e) => {
        const stateRef = _getSelectResolveStateRef();
        if (!_isTargetSelectionPendingState(stateRef)) return;

        const target = e.target;
        if (!target || typeof target.closest !== 'function') return;

        const mapViewport = document.getElementById('map-viewport');
        if (mapViewport && !mapViewport.contains(target)) return;

        if (
            target.closest('.slot-badge')
            || target.closest('.slot-badge-container')
            || target.closest('.declare-panel')
            || target.closest('#select-resolve-declare-panel')
        ) {
            return;
        }

        _resetDeclareSelectionState('click_away');
    }, true);
}

function _renderSelectResolveModeHint(phase, stateRef) {
    const viewport = document.getElementById('map-viewport');
    if (!viewport) return;

    let hint = document.getElementById('select-resolve-mode-hint');
    if (!hint) {
        hint = document.createElement('div');
        hint.id = 'select-resolve-mode-hint';
        hint.className = 'select-resolve-mode-hint';
        hint.style.display = 'none';
        viewport.appendChild(hint);
    }

    if (phase !== 'select' || !_isTargetSelectionPendingState(stateRef)) {
        hint.style.display = 'none';
        return;
    }

    const sourceLabel = _formatSlotLabelForTooltip(stateRef, stateRef?.declare?.sourceSlotId || null);
    hint.textContent = `対象選択中: ${sourceLabel} の対象を選択してください（空き領域クリックで解除）`;
    hint.style.display = 'block';
}

function _getActorIdBySlotId(stateRef, slotId) {
    if (!stateRef || !slotId) return null;
    const slotsMap = stateRef.slots || {};

    if (Array.isArray(slotsMap)) {
        const found = slotsMap.find(s => String(s?.slot_id ?? s?.id ?? '') === String(slotId));
        return found ? (found.actor_id ?? found.actor_char_id ?? null) : null;
    }

    const slot = slotsMap[slotId];
    if (!slot) return null;
    return slot.actor_id ?? slot.actor_char_id ?? null;
}

function _normalizeDeclareTargetType(type) {
    const t = String(type || '').trim();
    if (t === 'single_slot' || t === 'mass_individual' || t === 'mass_summation' || t === 'none') {
        return t;
    }
    return 'single_slot';
}

function _isMassDeclareTargetType(type) {
    const t = _normalizeDeclareTargetType(type);
    return t === 'mass_individual' || t === 'mass_summation';
}

function _emitDeclarePreview(stateRef, sourceSlotId, skillId, targetSlotId, targetType = 'single_slot') {
    const sourceIntent = stateRef?.intents?.[sourceSlotId] || null;
    // Keep committed declaration stable until explicit re-commit.
    if (sourceIntent?.committed) {
        console.log(`[emit] battle_intent_preview skip: source committed slot=${sourceSlotId}`);
        return;
    }

    const roomId = stateRef?.room_id || stateRef?.room_name || window.currentRoomName || null;
    const battleId = stateRef?.battle_id || null;
    const effectiveSkillId = skillId || null;
    const normalizedTargetType = _normalizeDeclareTargetType(targetType);
    const target = _isMassDeclareTargetType(normalizedTargetType)
        ? { type: normalizedTargetType, slot_id: null }
        : (targetSlotId ? { type: 'single_slot', slot_id: targetSlotId } : { type: 'none', slot_id: null });

    if (!roomId || !battleId) {
        console.log(`[emit] battle_intent_preview source_slot=${sourceSlotId} skill=${effectiveSkillId} target_type=${target.type} target_slot=${target.slot_id || 'null'} (skip: missing room/battle)`);
        return;
    }
    if (!window.SocketClient || typeof window.SocketClient.sendIntentPreview !== 'function') {
        console.log(`[emit] battle_intent_preview source_slot=${sourceSlotId} skill=${effectiveSkillId} target_type=${target.type} target_slot=${target.slot_id || 'null'} (skip: socket client unavailable)`);
        return;
    }

    console.log(`[emit] battle_intent_preview source_slot=${sourceSlotId} skill=${effectiveSkillId} target_type=${target.type} target_slot=${target.slot_id || 'null'}`);
    window.SocketClient.sendIntentPreview(roomId, battleId, sourceSlotId, effectiveSkillId, target);
}

function _handleDeclareSlotDoubleClick(clickedSlotId, clickedActorId) {
    const stateRef = _getSelectResolveStateRef();
    if ((stateRef.phase || 'select') !== 'select') return;

    const clickedIntent = (stateRef.intents || {})[clickedSlotId] || null;
    let sourceSlotId = clickedSlotId;
    let targetSlotId = null;
    let targetType = 'single_slot';
    let skillId = null;
    let lastSingleTargetSlotId = null;

    if (clickedIntent && clickedIntent.committed) {
        targetType = _normalizeDeclareTargetType(clickedIntent?.target?.type || 'single_slot');
        skillId = clickedIntent?.skill_id || null;
        if (_isMassDeclareTargetType(targetType)) {
            targetSlotId = null;
        } else {
            targetSlotId = clickedIntent?.target?.slot_id || null;
            lastSingleTargetSlotId = targetSlotId || null;
        }
    }

    // Keep panel open on dblclick even when single target is not selected yet.
    const mode = 'ready';
    if (window.BattleStore && typeof window.BattleStore.setDeclare === 'function') {
        window.BattleStore.setDeclare({
            sourceSlotId,
            targetSlotId,
            targetType,
            lastSingleTargetSlotId,
            skillId,
            mode
        });
    } else if (window.BattleStore && typeof window.BattleStore.setSelectedSlotId === 'function') {
        window.BattleStore.setSelectedSlotId(sourceSlotId);
    } else if (typeof battleState !== 'undefined') {
        battleState.selectedSlotId = sourceSlotId;
    }

    console.log(`[declare] mode=dblclick source=${sourceSlotId || 'null'} target_type=${targetType} target=${targetSlotId || 'null'} skill=${skillId || 'null'}`);
    _emitDeclarePreview(stateRef, sourceSlotId, skillId, targetSlotId, targetType);
}

function _handleDeclareSlotClick(clickedSlotId, clickedActorId) {
    const stateRef = _getSelectResolveStateRef();
    if ((stateRef.phase || 'select') !== 'select') return;

    const currentDeclare = stateRef.declare || {};
    const intents = stateRef.intents || {};
    const clickedIntent = intents[clickedSlotId] || null;
    let mode = currentDeclare.mode || 'idle';
    let sourceSlotId = currentDeclare.sourceSlotId || null;
    let targetSlotId = currentDeclare.targetSlotId || null;
    let targetType = _normalizeDeclareTargetType(currentDeclare.targetType || 'single_slot');
    let skillId = currentDeclare.skillId || null;
    let lastSingleTargetSlotId = currentDeclare.lastSingleTargetSlotId || null;
    const effectiveClickedActorId = clickedActorId || _getActorIdBySlotId(stateRef, clickedSlotId);
    const sourceActorId = sourceSlotId ? _getActorIdBySlotId(stateRef, sourceSlotId) : null;
    const isMassMode = _isMassDeclareTargetType(targetType);
    const isTargetChoosing = !!sourceSlotId && !isMassMode && (mode === 'choose_target' || mode === 'ready');
    const isDifferentActorClick = (
        !!sourceActorId
        && !!effectiveClickedActorId
        && String(sourceActorId) !== String(effectiveClickedActorId)
    );

    // In mass mode, keep click UX but suppress target changes on enemy slot click.
    if (isMassMode && sourceSlotId && isDifferentActorClick) {
        console.log(`[declare] mass_target_locked source=${sourceSlotId} clicked=${clickedSlotId}`);
        if (window.BattleStore && typeof window.BattleStore.setDeclare === 'function') {
            window.BattleStore.setDeclare({
                sourceSlotId,
                targetSlotId: null,
                targetType,
                lastSingleTargetSlotId,
                skillId,
                mode: 'ready'
            });
        }
        _emitDeclarePreview(stateRef, sourceSlotId, skillId, null, targetType);
        return;
    }

    // If clicked slot is already committed, enter re-edit mode with current declared values.
    // During target choosing, committed enemy slots must remain selectable as target.
    if (clickedIntent && clickedIntent.committed && !(isTargetChoosing && isDifferentActorClick)) {
        sourceSlotId = clickedSlotId;
        targetSlotId = clickedIntent?.target?.slot_id || null;
        targetType = _normalizeDeclareTargetType(clickedIntent?.target?.type || 'single_slot');
        skillId = clickedIntent?.skill_id || null;
        if (targetSlotId) {
            lastSingleTargetSlotId = targetSlotId;
        }
        mode = _isMassDeclareTargetType(targetType)
            ? 'ready'
            : (targetSlotId ? 'ready' : 'choose_target');

        if (window.BattleStore && typeof window.BattleStore.setDeclare === 'function') {
            window.BattleStore.setDeclare({ sourceSlotId, targetSlotId, targetType, lastSingleTargetSlotId, skillId, mode });
        } else if (window.BattleStore && typeof window.BattleStore.setSelectedSlotId === 'function') {
            window.BattleStore.setSelectedSlotId(sourceSlotId);
        } else if (typeof battleState !== 'undefined') {
            battleState.selectedSlotId = sourceSlotId;
        }

        console.log(`[declare] mode=reedit source=${sourceSlotId || 'null'} target_type=${targetType} target=${targetSlotId || 'null'} skill=${skillId || 'null'}`);
        return;
    }

    const switchSource = () => {
        sourceSlotId = clickedSlotId;
        targetSlotId = null;
        skillId = null;
        targetType = 'single_slot';
        mode = 'choose_target';
    };

    if (mode === 'idle' || !sourceSlotId) {
        switchSource();
    } else if (mode === 'locked') {
        switchSource();
    } else if (mode === 'choose_target') {
        if (
            sourceActorId
            && effectiveClickedActorId
            && String(sourceActorId) !== String(effectiveClickedActorId)
        ) {
            targetSlotId = clickedSlotId;
            lastSingleTargetSlotId = clickedSlotId;
            mode = 'ready';
        } else {
            switchSource();
        }
    } else if (mode === 'ready') {
        if (
            sourceActorId
            && effectiveClickedActorId
            && String(sourceActorId) !== String(effectiveClickedActorId)
        ) {
            targetSlotId = clickedSlotId;
            lastSingleTargetSlotId = clickedSlotId;
            mode = 'ready';
        } else {
            switchSource();
        }
    } else {
        switchSource();
    }

    if (window.BattleStore && typeof window.BattleStore.setDeclare === 'function') {
        window.BattleStore.setDeclare({
            sourceSlotId,
            targetSlotId,
            targetType,
            lastSingleTargetSlotId,
            skillId,
            mode
        });
    } else if (window.BattleStore && typeof window.BattleStore.setSelectedSlotId === 'function') {
        window.BattleStore.setSelectedSlotId(sourceSlotId);
    } else if (typeof battleState !== 'undefined') {
        battleState.selectedSlotId = sourceSlotId;
    }

    console.log(`[declare] mode=${mode} source=${sourceSlotId || 'null'} target_type=${targetType} target=${targetSlotId || 'null'} skill=${skillId || 'null'}`);
    _emitDeclarePreview(stateRef, sourceSlotId, skillId, targetSlotId, targetType);
}

// Helper: Update token visual contents (bars, badges, etc)
function updateTokenVisuals(token, char) {
    // Keep token size in sync when tokenScale changes after initial creation.
    const tokenScale = char.tokenScale || 1.0;
    const baseSize = 132;
    const scaledSize = baseSize * tokenScale;
    token.style.width = `${scaledSize}px`;
    token.style.height = `${scaledSize}px`;

    const nameLabelTop = token.querySelector('.token-name-label');
    if (nameLabelTop) {
        nameLabelTop.style.top = `${scaledSize + 6}px`;
    }

    // HP Bar
    const hpRow = token.querySelector('.token-stat-row[data-stat="HP"]');
    if (hpRow) {
        const bar = hpRow.querySelector('.token-bar-fill.hp');
        const val = hpRow.querySelector('.token-bar-value');
        if (bar) bar.style.width = `${Math.min(100, Math.max(0, (char.hp / char.maxHp) * 100))}%`;
        if (val) val.textContent = char.hp;
    }

    // MP Bar
    const mpRow = token.querySelector('.token-stat-row[data-stat="MP"]');
    if (mpRow) {
        const bar = mpRow.querySelector('.token-bar-fill.mp');
        const val = mpRow.querySelector('.token-bar-value');
        if (bar) bar.style.width = `${Math.min(100, Math.max(0, (char.mp / char.maxMp) * 100))}%`;
        if (val) val.textContent = char.mp;
    }

    // FP Badge Update
    const fpBadge = token.querySelector('.fp-badge');
    if (fpBadge) {
        let fpVal = char.fp;
        if (fpVal === undefined && char.states) {
            const s = char.states.find(st => st.name === 'FP');
            fpVal = s ? s.value : 0;
        }
        if (fpVal === undefined) fpVal = 0;

        const currentText = fpBadge.textContent.trim();
        if (currentText != fpVal) {
            fpBadge.textContent = fpVal;
            fpBadge.title = `FP: ${fpVal}`;
        }
    }

    // Image Update
    const bodyEl = token.querySelector('.token-body');
    if (bodyEl) {
        const currentImg = bodyEl.querySelector('img');
        if (char.image) {
            if (currentImg) {
                if (!currentImg.src.includes(char.image)) {
                    currentImg.src = char.image;
                }
            } else {
                const span = bodyEl.querySelector('span');
                if (span) span.remove();
                const img = document.createElement('img');
                img.src = char.image;
                img.loading = "lazy";
                img.style.width = "100%";
                img.style.height = "100%";
                img.style.objectFit = "cover";
                bodyEl.prepend(img);
            }
        } else {
            if (currentImg) currentImg.remove();
            let span = bodyEl.querySelector('span');
            if (!span) {
                span = document.createElement('span');
                span.style.cssText = "font-size: 3em; font-weight: bold; color: #555; display: flex; align-items: center; justify-content: center; height: 100%;";
                bodyEl.prepend(span);
            }
            if (span.textContent !== char.name.charAt(0)) {
                span.textContent = char.name.charAt(0);
            }
        }
    }

    // Badge Update
    const badgesContainer = token.querySelector('.token-badges');
    if (badgesContainer) {
        badgesContainer.innerHTML = generateMapTokenBadgesHTML(char);
    }

    // Name Label
    const nameLabel = token.querySelector('.token-name-label');
    if (nameLabel && nameLabel.textContent !== char.name) {
        nameLabel.textContent = char.name;
    }

    token.style.filter = 'none';
}

/**
 * Partial Update for Token Visuals (Stat Change Event)
 */
window.updateCharacterTokenVisuals = function (data) {
    console.log('[updateCharacterTokenVisuals] Called with data:', data);

    if (!data || !data.char_id) {
        console.warn('[updateCharacterTokenVisuals] Invalid data:', data);
        return;
    }

    const { char_id, stat, new_value, old_value, max_value, source } = data;
    console.log(`[updateCharacterTokenVisuals] Extracted: char_id=${char_id}, stat=${stat}, new=${new_value}, old=${old_value}, max=${max_value}, source=${source}`);

    const token = document.querySelector(`.map-token[data-id="${char_id}"]`);
    if (!token) {
        console.debug(`[updateCharacterTokenVisuals] Token not found for char_id: ${char_id}`);
        return;
    }

    const _toNumberOrNull = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
    };
    const _upsertCharState = (char, stateName, rawValue) => {
        if (!char || !stateName) return;
        if (!Array.isArray(char.states)) char.states = [];
        const idx = char.states.findIndex((s) => s && s.name === stateName);
        const n = _toNumberOrNull(rawValue);
        const nextVal = n !== null ? n : rawValue;
        const shouldDelete = (n !== null && n <= 0);

        if (idx >= 0) {
            if (shouldDelete) char.states.splice(idx, 1);
            else char.states[idx].value = nextVal;
            return;
        }
        if (!shouldDelete) {
            char.states.push({ name: stateName, value: nextVal });
        }
    };

    let battleChar = null;
    if (typeof battleState !== 'undefined' && Array.isArray(battleState.characters)) {
        battleChar = battleState.characters.find(c => c.id === char_id) || null;
        if (battleChar) {
            if (stat === 'HP') battleChar.hp = new_value;
            else if (stat === 'MP') battleChar.mp = new_value;
            else _upsertCharState(battleChar, stat, new_value);
        }
    }

    if (stat === 'HP' || stat === 'MP') {
        const barClass = stat === 'HP' ? 'hp' : 'mp';
        const barFill = token.querySelector(`.token-bar-fill.${barClass}`);
        const barContainer = token.querySelector(`.token-bar[title^="${stat}:"]`);

        if (barFill && max_value) {
            const percentage = Math.max(0, Math.min(100, (new_value / max_value) * 100));
            barFill.style.width = `${percentage}%`;
            if (barContainer) {
                barContainer.title = `${stat}: ${new_value}/${max_value}`;
            }
        }

        if (old_value !== undefined && old_value !== new_value) {
            const diff = new_value - old_value;
            showFloatingText(token, diff, stat, source);
        }
    } else {
        const internalStats = ['hidden_skills', 'gmOnly', 'color', 'image', 'imageOriginal', 'owner', 'commands', 'params'];
        if (internalStats.includes(stat)) return;

        if (old_value !== undefined && old_value !== new_value) {
            const diff = new_value - old_value;
            showFloatingText(token, diff, stat, source);
        }

        // Immediately refresh status/debuff badges for state changes.
        const badgesContainer = token.querySelector('.token-badges');
        if (badgesContainer && battleChar) {
            badgesContainer.innerHTML = generateMapTokenBadgesHTML(battleChar);
        }

        // FP badge is a dedicated top-left circle; keep it in sync.
        const fpBadge = token.querySelector('.fp-badge');
        if (fpBadge && battleChar) {
            const fpState = Array.isArray(battleChar.states)
                ? battleChar.states.find((s) => s && s.name === 'FP')
                : null;
            const fpVal = fpState ? Number(fpState.value || 0) : 0;
            fpBadge.textContent = String(Math.max(0, fpVal));
            fpBadge.title = `FP: ${Math.max(0, fpVal)}`;
        }
        console.debug(`[updateCharacterTokenVisuals] State change detected: ${stat}, badges refreshed`);
    }
}

/**
 * Show Floating Text for Damage/Heal
 */
window.showFloatingText = function (token, diff, stat, source = null) {
    const mapViewport = document.getElementById('map-viewport');
    if (!mapViewport) return;

    const charId = token.dataset.id;
    if (!window.floatingTextCounters) window.floatingTextCounters = {};
    if (!window.floatingTextCounters[charId]) window.floatingTextCounters[charId] = 0;

    const currentOffset = window.floatingTextCounters[charId];
    window.floatingTextCounters[charId]++;

    const floatingText = document.createElement('div');
    floatingText.className = 'floating-damage-text';

    const isDamage = diff < 0;
    const absValue = Math.abs(diff);

    let displayText = '';
    if (stat === 'HP') {
        if (source === 'rupture') {
            displayText = isDamage ? `破裂爆発！ -${absValue}` : `破裂爆発！ +${absValue}`;
        } else if (source === 'fissure') {
            displayText = isDamage ? `亀裂崩壊！ -${absValue}` : `亀裂崩壊！ +${absValue}`;
        } else {
            displayText = isDamage ? `-${absValue}` : `+${absValue}`;
        }
    } else if (stat === 'MP') {
        displayText = isDamage ? `-${absValue}` : `+${absValue}`;
    } else {
        displayText = isDamage ? `${stat} -${absValue}` : `${stat} +${absValue}`;
        floatingText.classList.add('state-change');
    }
    floatingText.textContent = displayText;

    if (!source) {
        if (stat === 'HP') {
            floatingText.classList.add(isDamage ? 'damage' : 'heal');
        } else if (stat === 'MP') {
            floatingText.classList.add(isDamage ? 'mp-cost' : 'mp-heal');
        }
    } else {
        floatingText.classList.add(`src-${source}`);
    }

    const tokenRect = token.getBoundingClientRect();
    const viewportRect = mapViewport.getBoundingClientRect();

    const relativeLeft = tokenRect.left - viewportRect.left + mapViewport.scrollLeft + (tokenRect.width / 2);
    const verticalOffset = currentOffset * 25;
    const relativeTop = tokenRect.top - viewportRect.top + mapViewport.scrollTop + (tokenRect.height / 2) - verticalOffset;

    floatingText.style.left = `${relativeLeft}px`;
    floatingText.style.top = `${relativeTop}px`;

    mapViewport.appendChild(floatingText);

    setTimeout(() => {
        if (floatingText.parentNode) floatingText.parentNode.removeChild(floatingText);
        if (window.floatingTextCounters && window.floatingTextCounters[charId] > 0) {
            window.floatingTextCounters[charId]--;
        }
    }, 3000);
}

/**
 * Generates badge HTML for map tokens
 */
window.generateMapTokenBadgesHTML = function (char) {
    let iconsHtml = '';
    if (char.states) {
        let badgeCount = 0;
        const badgesPerRow = 3;

        char.states.forEach(s => {
            if (['HP', 'MP', 'FP'].includes(s.name)) return;
            if (s.value === 0) return;

            const config = STATUS_CONFIG[s.name];
            const row = Math.floor(badgeCount / badgesPerRow);
            const col = badgeCount % badgesPerRow;

            const rightPos = -10 + (col * 30);
            const topPos = -25 - (row * 36);

            const badgeStyle = `
                width: 34px; height: 34px;
                display: flex; align-items: center; justify-content: center;
                border-radius: 50%; box-shadow: 0 3px 5px rgba(0,0,0,0.5);
                background: #fff; border: 2px solid #ccc;
                position: absolute; right: ${rightPos}px; top: ${topPos}px; z-index: ${5 + row};
            `;
            const countStyle = `
                position: absolute; bottom: -5px; right: -5px;
                background: ${config ? config.color : (s.value > 0 ? '#28a745' : '#dc3545')};
                color: white; font-size: 12px; font-weight: bold;
                padding: 0 3px; border-radius: 44px; border: 1px solid white;
            `;

            if (config) {
                iconsHtml += `
                    <div class="status-badge" style="${badgeStyle} border-color: ${config.borderColor};" title="${s.name}: ${s.value}">
                        <img src="images/${config.icon}" loading="lazy" style="width:100%; height:100%; border-radius:50%;">
                        <div style="${countStyle}">${s.value}</div>
                    </div>`;
            } else {
                const arrow = s.value > 0 ? '▲' : '▼';
                const color = s.value > 0 ? '#28a745' : '#dc3545';
                iconsHtml += `
                    <div class="status-badge" style="${badgeStyle} color:${color}; border-color:${color}; font-weight:bold; background:#fff; font-size:20px;" title="${s.name}: ${s.value}">
                        ${arrow}
                        <div style="${countStyle}">${s.value}</div>
                    </div>`;
            }
            badgeCount++;
        });
    }
    return iconsHtml;
}

/**
 * Creates the DOM element for a map token
 */
window.createMapToken = function (char) {
    const token = document.createElement('div');

    let colorClass = 'NPC';
    let borderColor = '#999';

    if (char.name && char.name.includes('味方')) {
        colorClass = 'PC';
        borderColor = '#007bff';
    } else if (char.name && char.name.includes('敵')) {
        colorClass = 'Enemy';
        borderColor = '#dc3545';
    } else if (char.color) {
        colorClass = char.color;
        borderColor = char.color;
    }

    token.className = `map-token ${colorClass}`;
    token.dataset.id = char.id;

    const tokenScale = char.tokenScale || 1.0;
    const baseSize = 132;
    const scaledSize = baseSize * tokenScale;

    token.style.width = `${scaledSize}px`;
    token.style.height = `${scaledSize}px`;
    token.style.borderRadius = "18px 18px 0 0";
    token.style.border = `4px solid ${borderColor}`;
    token.style.boxShadow = "0 4px 8px rgba(0,0,0,0.4)";
    token.style.overflow = "visible";
    token.style.left = `${char.x * GRID_SIZE + TOKEN_OFFSET}px`;
    token.style.top = `${char.y * GRID_SIZE + TOKEN_OFFSET}px`;
    token.style.position = 'absolute';

    const maxHp = char.maxHp || 1; const hp = char.hp || 0;
    const hpPer = Math.max(0, Math.min(PERCENTAGE_MAX, (hp / maxHp) * PERCENTAGE_MAX));

    const maxMp = char.maxMp || 1; const mp = char.mp || 0;
    const mpPer = Math.max(0, Math.min(PERCENTAGE_MAX, (mp / maxMp) * PERCENTAGE_MAX));

    const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
    const fp = fpState ? fpState.value : 0;

    let iconsHtml = generateMapTokenBadgesHTML(char);
    const isCurrentTurn = (battleState.turn_char_id === char.id);

    // Wide Match Button
    let wideBtnHtml = '';
    const isWideMatchExecuting = battleState.active_match && battleState.active_match.is_active && battleState.active_match.match_type === 'wide';
    if (isCurrentTurn && char.isWideUser && !isWideMatchExecuting) {
        wideBtnHtml = '<button class="wide-attack-trigger-btn" style="transform: scale(1.2); top: -40px; font-size: 1.1em;" onclick="event.stopPropagation(); window._dragBlockClick = true; setTimeout(() => { window._dragBlockClick = false; }, 100); openSyncedWideMatchModal(\'' + char.id + '\');">⚡ 広域</button>';
    }

    let tokenBodyStyle = `width: 100%; height: 100%; border-radius: 14px 14px 0 0; overflow: hidden; position: relative; background: #eee;`;
    let tokenBodyContent = `<span style="font-size: 3em; font-weight: bold; color: #555; display: flex; align-items: center; justify-content: center; height: 100%;">${char.name.charAt(0)}</span>`;

    if (char.image) {
        tokenBodyContent = `<img src="${char.image}" loading="lazy" style="width:100%; height:100%; object-fit:cover;">`;
    }

    const statusOverlayStyle = `
        position: absolute; bottom: 0; left: 0; width: 100%;
        background: rgba(0, 0, 0, 0.75);
        padding: 5px; box-sizing: border-box;
        border-bottom-left-radius: 0; border-bottom-right-radius: 0;
        display: flex; flex-direction: column; gap: 4px;
        pointer-events: none;
    `;

    const nameLabelStyle = `
        position: absolute;
        top: ${scaledSize + 6}px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0,0,0,0.7);
        color: white;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 16px;
        font-weight: bold;
        white-space: nowrap;
        z-index: 101;
        text-shadow: 1px 1px 2px black;
        pointer-events: none;
    `;
    const nameLabelHtml = `<div class="token-name-label" style="${nameLabelStyle}">${char.name}</div>`;

    const createBar = (cls, per, val, max, label) => `
        <div class="token-stat-row" data-stat="${label}" style="display:flex; align-items:center; height: 14px; gap: 4px;">
            <div style="font-size:14px; font-weight:bold; color:#ccc; width:22px; text-align:left; line-height:1;">${label}</div>
            <div style="flex-grow:1; background:#444; height:100%; border-radius:3px; position:relative; overflow:hidden;">
                <div class="${cls}" style="width:${per}%; height:100%; position:absolute; left:0; top:0; border-radius:3px;"></div>
            </div>
            <div class="token-bar-value" style="font-size:18px; color:white; font-weight:bold; text-shadow:1px 1px 1px #000; min-width:30px; text-align:right; line-height:1;">${val}</div>
        </div>
    `;

    const statusHtml = `
        <div style="${statusOverlayStyle}">
            ${createBar('token-bar-fill hp', hpPer, hp, maxHp, 'HP')}
            ${createBar('token-bar-fill mp', mpPer, mp, maxMp, 'MP')}
        </div>
    `;

    const fpBadgeHtml = `
        <div class="fp-badge" style="
            position: absolute; top: -12px; left: -12px;
            width: 32px; height: 32px;
            background: #ff9800;
            border-radius: 50%;
            border: 3px solid white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.5);
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: bold; font-size: 16px;
            z-index: 20;
        " title="FP: ${fp}">
            ${fp}
        </div>
    `;

    token.innerHTML = `
        ${wideBtnHtml}
        ${fpBadgeHtml}
        <div class="token-body" style="${tokenBodyStyle}">
            ${tokenBodyContent}
            ${statusHtml}
        </div>
        ${nameLabelHtml}
        <div class="token-badges" style="position: absolute; top:0; right:0; width:0; height:0;">
            ${iconsHtml}
        </div>
    `;

    token.draggable = false;
    token.style.cursor = 'grab';

    token.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        exitAttackTargetingMode();
        showCharacterDetail(char.id);
    });

    token.addEventListener('click', (e) => {
        e.stopPropagation();
        console.log(`[Click] Token clicked: ${char.name} (${char.id})`);

        if (window._dragBlockClick) {
            console.log('[Click] blocked due to recent drag');
            return;
        }

        document.querySelectorAll('.map-token').forEach(t => t.style.zIndex = '');
        token.style.zIndex = 500;

        // Select/Resolve target selection mode: pick target slot from clicked token actor.
        const srState = _getSelectResolveStateRef();
        if (srState.phase === 'select' && srState.targetSelectMode) {
            const selectedSlotId = srState.selectedSlotId;
            if (!selectedSlotId) {
                console.log('[slot_badges] target click ignored: no selectedSlotId');
                return;
            }

            const targetSlotId = _resolveTargetSlotIdForActor(char.id, srState);
            if (!targetSlotId) {
                console.log(`[slot_badges] target click ignored: no slot for actor=${char.id}`);
                return;
            }

            if (window.EventBus && typeof window.EventBus.emit === 'function') {
                window.EventBus.emit('timeline:target-slot-clicked', {
                    targetSlotId,
                    actorId: char.id
                });
                console.log(`[slot_badges] target selected slot=${targetSlotId} actor=${char.id}`);
            }
            return;
        }

        // Disable legacy turn-based token-click match flow while Select/Resolve pipeline is active.
        if (['select', 'resolve_mass', 'resolve_single'].includes(srState.phase)) {
            console.log(`[Click] legacy turn-match flow blocked in phase=${srState.phase}`);
            return;
        }

        // Active Match Expansion
        if (battleState.active_match && battleState.active_match.is_active) {
            const am = battleState.active_match;
            if (am.attacker_id === char.id || am.defender_id === char.id) {
                if (typeof expandMatchPanel === 'function') expandMatchPanel();
                return;
            }
        }

        // Targeting Mode
        if (window.attackTargetingState.isTargeting && window.attackTargetingState.attackerId) {
            const attackerId = window.attackTargetingState.attackerId;
            if (attackerId === char.id) return; // Self target

            const attackerChar = battleState.characters.find(c => c.id === attackerId);
            const attackerName = attackerChar ? attackerChar.name : "不明";
            const isOwner = attackerChar && attackerChar.owner === currentUsername;
            const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

            if (!isOwner && !isGM) {
                alert("キャラクターの所有者またはGMのみがマッチを開始できます。");
                exitAttackTargetingMode();
                return;
            }

            if (confirm(`【攻撃確認】\n「${attackerName}」が「${char.name}」に攻撃を仕掛けますか？`)) {
                openDuelModal(attackerId, char.id);
            }
            exitAttackTargetingMode();
            return;
        }

        // Activate Targeting Mode (Turn Player)
        const currentTurnCharId = battleState.turn_char_id;
        const isNowTurn = (currentTurnCharId === char.id);

        if (isNowTurn) {
            const isOwner = char.owner === currentUsername;
            const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

            if (!isOwner && !isGM) return;

            if (window.matchActionInitiated) {
                alert("1ターンに1回のみマッチを開始できます。\n次のターンまでお待ちください。");
                return;
            }

            const isWideMatchExecuting = battleState.active_match && battleState.active_match.is_active && battleState.active_match.match_type === 'wide';
            if (char.isWideUser && !isWideMatchExecuting) {
                if (typeof openSyncedWideMatchModal === 'function') {
                    openSyncedWideMatchModal(char.id);
                }
                return;
            }

            enterAttackTargetingMode(char.id);
        }
    });

    return token;
}

window.selectVisualToken = function (charId) {
    document.querySelectorAll('.map-token').forEach(el => el.classList.remove('selected'));
    const token = document.querySelector(`.map-token[data-id="${charId}"]`);
    if (token) token.classList.add('selected');
}

/**
 * Generate Status Icons (Used by Duel Panel as well)
 */
window.generateStatusIconsHTML = function (char) {
    if (!char.states) return '';
    let iconsHtml = '';
    char.states.forEach(s => {
        if (['HP', 'MP', 'FP'].includes(s.name)) return;
        if (s.value === 0) return;
        const config = STATUS_CONFIG[s.name];
        if (config) {
            iconsHtml += `
                <div class="duel-status-icon">
                    <img src="images/${config.icon}" alt="${s.name}">
                    <div class="duel-status-badge" style="background-color: ${config.color};">${s.value}</div>
                </div>`;
        }
    });
    return iconsHtml;
}

// --- Menu Functions ---

window.toggleCharSettingsMenu = function (charId, btnElement) {
    let menu = document.getElementById('char-settings-menu');
    if (menu) {
        menu.remove();
        return;
    }

    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    menu = document.createElement('div');
    menu.id = 'char-settings-menu';
    menu.style.cssText = 'position:absolute; background:white; border:1px solid #ccc; border-radius:4px; box-shadow:0 2px 10px rgba(0,0,0,0.2); z-index:10000; min-width:180px;';

    const rect = btnElement.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 5}px`;
    menu.style.left = `${rect.left + window.scrollX - 100}px`;

    const ownerName = char.owner || '不明';
    const ownerDisplay = document.createElement('div');
    ownerDisplay.style.cssText = 'padding:8px 12px; margin-bottom:4px; background:#f0f0f0; font-size:0.85em; border-bottom:1px solid #ddd;';
    ownerDisplay.innerHTML = `<strong>所有者:</strong> ${ownerName}`;
    menu.appendChild(ownerDisplay);

    const tokenScale = char.tokenScale || 1.0;
    const sizeSection = document.createElement('div');
    sizeSection.style.cssText = 'padding:8px 12px; margin-bottom:4px; border-bottom:1px solid #ddd;';
    sizeSection.innerHTML = `
        <div style="margin-bottom:5px; font-size:0.9em; font-weight:bold;">駒のサイズ</div>
        <div style="display:flex; align-items:center; gap:8px;">
            <input type="range" id="settings-token-scale-slider" min="0.5" max="2.0" step="0.1" value="${tokenScale}" style="flex:1;">
            <span id="settings-token-scale-display" style="min-width:35px; font-size:0.85em;">${tokenScale.toFixed(1)}x</span>
        </div>
    `;
    menu.appendChild(sizeSection);

    const scaleSlider = sizeSection.querySelector('#settings-token-scale-slider');
    const scaleDisplay = sizeSection.querySelector('#settings-token-scale-display');
    if (scaleSlider && scaleDisplay) {
        scaleSlider.oninput = () => {
            const newScale = parseFloat(scaleSlider.value);
            scaleDisplay.textContent = `${newScale.toFixed(1)}x`;
            if (typeof socket !== 'undefined' && currentRoomName) {
                socket.emit('request_update_token_scale', {
                    room: currentRoomName,
                    charId: charId,
                    scale: newScale
                });
            }
        };
    }

    const imageSection = document.createElement('div');
    imageSection.style.cssText = 'padding:8px 12px; margin-bottom:4px; border-bottom:1px solid #ddd;';
    imageSection.innerHTML = `
        <div style="margin-bottom:5px; font-size:0.9em; font-weight:bold;">立ち絵画像</div>
        <button id="settings-image-picker-btn" style="width:100%; padding:8px; background:#007bff; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">画像を変更</button>
    `;
    menu.appendChild(imageSection);

    const imagePickerBtn = imageSection.querySelector('#settings-image-picker-btn');
    if (imagePickerBtn) {
        imagePickerBtn.onclick = () => {
            openImagePicker((selectedImage) => {
                const battleImage = selectedImage.croppedUrl || selectedImage.url;
                const explorationImage = selectedImage.originalUrl || selectedImage.url;
                socket.emit('request_state_update', {
                    room: currentRoomName,
                    charId: charId,
                    changes: {
                        image: battleImage,
                        imageOriginal: explorationImage
                    }
                });
                menu.remove();
            });
        };
    }

    const styleMenuButton = (btn) => {
        btn.style.cssText = 'display:block; width:100%; padding:8px 12px; border:none; background:none; text-align:left; cursor:pointer;';
        btn.onmouseover = () => btn.style.background = '#f5f5f5';
        btn.onmouseout = () => btn.style.background = 'none';
        return btn;
    };

    const withdrawBtn = document.createElement('button');
    withdrawBtn.textContent = '未配置に戻す';
    styleMenuButton(withdrawBtn);
    withdrawBtn.onclick = () => {
        if (confirm('このキャラクターを未配置状態に戻しますか？')) {
            withdrawCharacter(charId);
            menu.remove();
            const backdrop = document.getElementById('char-detail-modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    };
    menu.appendChild(withdrawBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'キャラクターを削除';
    styleMenuButton(deleteBtn);
    deleteBtn.style.color = '#dc3545';
    deleteBtn.onclick = () => {
        if (confirm(`本当に「${char.name}」を削除しますか？`)) {
            socket.emit('request_delete_character', { room: currentRoomName, charId: charId });
            menu.remove();
            const backdrop = document.getElementById('char-detail-modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    };
    menu.appendChild(deleteBtn);

    const transferBtn = document.createElement('button');
    transferBtn.textContent = '所有権を譲渡 ▶';
    styleMenuButton(transferBtn);
    transferBtn.onclick = (e) => {
        e.stopPropagation();
        showTransferSubMenu(charId, menu, transferBtn);
    };
    menu.appendChild(transferBtn);

    document.body.appendChild(menu);

    setTimeout(() => {
        const closeHandler = (e) => {
            if (!menu.contains(e.target) && e.target !== btnElement) {
                menu.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        document.addEventListener('click', closeHandler);
    }, 0);
}

window.withdrawCharacter = function (charId) {
    if (!charId || !currentRoomName) return;
    socket.emit('request_move_character', {
        room: currentRoomName,
        character_id: charId,
        x: -1,
        y: -1
    });
}

window.showTransferSubMenu = function (charId, parentMenu, parentBtn) {
    const existingSubMenu = document.getElementById('transfer-sub-menu');
    if (existingSubMenu) { existingSubMenu.remove(); return; }

    const subMenu = document.createElement('div');
    subMenu.id = 'transfer-sub-menu';
    subMenu.style.cssText = 'position:absolute; background:white; border:1px solid #ccc; border-radius:4px; box-shadow:0 2px 10px rgba(0,0,0,0.2); z-index:10001; min-width:200px;';

    const rect = parentBtn.getBoundingClientRect();
    subMenu.style.top = `${rect.top + window.scrollY}px`;
    subMenu.style.left = `${rect.right + window.scrollX + 5}px`;

    const styleSubMenuItem = (item) => {
        item.style.cssText = 'display:block; width:100%; padding:8px 12px; border:none; background:none; text-align:left; cursor:pointer;';
        item.onmouseover = () => item.style.background = '#f5f5f5';
        item.onmouseout = () => item.style.background = 'none';
        return item;
    };

    const allUsersBtn = document.createElement('button');
    allUsersBtn.textContent = '全ユーザーから選択';
    styleSubMenuItem(allUsersBtn);
    allUsersBtn.onclick = () => {
        openTransferOwnershipModal(charId, 'all');
        subMenu.remove();
        parentMenu.remove();
    };
    subMenu.appendChild(allUsersBtn);

    const roomUsersBtn = document.createElement('button');
    roomUsersBtn.textContent = '同じルームのユーザーから選択';
    styleSubMenuItem(roomUsersBtn);
    roomUsersBtn.onclick = () => {
        openTransferOwnershipModal(charId, 'room');
        subMenu.remove();
        parentMenu.remove();
    };
    subMenu.appendChild(roomUsersBtn);

    document.body.appendChild(subMenu);

    setTimeout(() => {
        const closeHandler = (e) => {
            if (!subMenu.contains(e.target) && e.target !== parentBtn) {
                subMenu.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        document.addEventListener('click', closeHandler);
    }, 0);
}

window.openTransferOwnershipModal = function (charId, mode) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    const existing = document.getElementById('transfer-modal-backdrop');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'transfer-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';
    modalContent.style.cssText = 'max-width:400px; width:90%; padding:20px;';

    const title = mode === 'all' ? '全ユーザーから選択' : '同じルームのユーザーから選択';

    modalContent.innerHTML = `
        <h3 style="margin-top:0;">所有権譲渡: ${title}</h3>
        <p style="font-size:0.9em; color:#666;">「${char.name}」の所有権を譲渡するユーザーを選択してください。</p>
        <div id="user-list-container" style="max-height:300px; overflow-y:auto; border:1px solid #ddd; border-radius:4px; margin:15px 0;">
            <div style="padding:20px; text-align:center; color:#999;">読み込み中...</div>
        </div>
        <div style="text-align:right; margin-top:15px;">
            <button id="transfer-cancel-btn" style="padding:8px 16px; margin-right:10px;">キャンセル</button>
        </div>
    `;

    backdrop.appendChild(modalContent);
    document.body.appendChild(backdrop);

    modalContent.querySelector('#transfer-cancel-btn').onclick = () => backdrop.remove();
    backdrop.onclick = (e) => { if (e.target === backdrop) backdrop.remove(); };

    const userListContainer = modalContent.querySelector('#user-list-container');
    let fetchUrl = (mode === 'all') ? '/api/admin/users' : `/api/get_room_users?room=${encodeURIComponent(currentRoomName)}`;

    fetchWithSession(fetchUrl)
        .then(res => res.json())
        .then(users => {
            if (!users || users.length === 0) {
                userListContainer.innerHTML = '<div style="padding:20px; text-align:center; color:#999;">ユーザーが見つかりません。</div>';
                return;
            }
            userListContainer.innerHTML = '';
            users.forEach(user => {
                const userItem = document.createElement('div');
                userItem.style.cssText = 'padding:10px 15px; border-bottom:1px solid #eee; cursor:pointer; display:flex; justify-content:space-between; align-items:center;';
                userItem.onmouseover = () => userItem.style.background = '#f5f5f5';
                userItem.onmouseout = () => userItem.style.background = 'white';

                const userName = mode === 'all' ? user.name : user.username;
                const userId = user.id || user.user_id;

                userItem.innerHTML = `
                    <span style="font-weight:bold;">${userName}</span>
                    <span style="font-size:0.85em; color:#666;">${user.attribute || '不明'}</span>
                `;

                userItem.onclick = () => {
                    if (confirm(`「${char.name}」の所有権を「${userName}」に譲渡しますか？`)) {
                        socket.emit('request_transfer_character_ownership', {
                            room: currentRoomName,
                            character_id: charId,
                            new_owner_id: userId,
                            new_owner_name: userName
                        });
                        backdrop.remove();
                    }
                };
                userListContainer.appendChild(userItem);
            });
        })
        .catch(err => {
            console.error('Failed to fetch users:', err);
            userListContainer.innerHTML = '<div style="padding:20px; text-align:center; color:#dc3545;">ユーザー一覧の取得に失敗しました。</div>';
        });
}

window.toggleBuffDesc = function (elementId) {
    const el = document.getElementById(elementId);
    if (el) el.style.display = (el.style.display === 'none') ? 'block' : 'none';
}

console.log('[visual_map] Loaded.');

