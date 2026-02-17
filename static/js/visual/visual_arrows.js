/* static/js/visual/visual_arrows.js */

window.VISUAL_SHOW_ARROWS = (typeof window.VISUAL_SHOW_ARROWS !== 'undefined')
    ? window.VISUAL_SHOW_ARROWS
    : true;

(function () {
    const SVG_NS = 'http://www.w3.org/2000/svg';
    const ACTIVE_PHASES = new Set(['select', 'resolve_mass', 'resolve_single']);
    const RESOLVE_PHASES = new Set(['resolve_mass', 'resolve_single']);

    const runtime = {
        rafPending: false,
        lastRenderDigest: null,
        freezeKey: null,
        frozenGraph: null,
        resizeBound: false,
        highlightKey: null,
        highlightUntil: 0,
        highlightFromSlotId: null,
        highlightToSlotId: null
    };

    function getCurrentState() {
        if (window.BattleStore && window.BattleStore.state) return window.BattleStore.state;
        if (typeof window.battleState !== 'undefined') return window.battleState;
        return null;
    }

    function normalizeTargetType(raw) {
        const t = String(raw || '').trim();
        if (t === 'single_slot' || t === 'mass_individual' || t === 'mass_summation' || t === 'none') {
            return t;
        }
        return 'single_slot';
    }

    function isMassTargetType(type) {
        const t = normalizeTargetType(type);
        return t === 'mass_individual' || t === 'mass_summation';
    }

    function inferTargetTypeFromSkill(skillId) {
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
            const t = normalizeTargetType(raw);
            if (isMassTargetType(t)) return t;
        }

        const tags = []
            .concat(Array.isArray(skill.tags) ? skill.tags : [])
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
            || merged.includes('広域')
        ) {
            return 'mass_individual';
        }

        return 'single_slot';
    }

    function toSlotArray(rawSlots) {
        if (Array.isArray(rawSlots)) {
            return rawSlots.map((slot) => ({
                ...(slot || {}),
                slot_id: (slot && (slot.slot_id || slot.id)) || null
            })).filter((slot) => !!slot.slot_id);
        }
        const map = rawSlots || {};
        return Object.entries(map).map(([sid, slot]) => ({
            ...(slot || {}),
            slot_id: (slot && (slot.slot_id || slot.id)) || sid
        })).filter((slot) => !!slot.slot_id);
    }

    function canonicalSide(raw) {
        const v = String(raw || '').toLowerCase();
        if (!v) return null;
        if (v === 'ally' || v === 'player' || v === 'friend' || v === 'friends') return 'ally';
        if (v === 'enemy' || v === 'boss' || v === 'foe' || v === 'opponent' || v === 'npc') return 'enemy';
        return null;
    }

    function getActorSide(actorId, slot, charById) {
        const slotSide = canonicalSide(slot?.team || slot?.side || slot?.faction);
        if (slotSide) return slotSide;
        const char = charById.get(String(actorId || ''));
        const charSide = canonicalSide(char?.team || char?.side || char?.faction || char?.type);
        return charSide || null;
    }

    function isSlotUsable(slot) {
        if (!slot) return false;
        return !(
            slot.disabled
            || slot.spent
            || slot.consumed
            || slot.done
            || slot.removed
            || slot.locked
        );
    }

    function pickRepresentativeSlot(slots) {
        if (!Array.isArray(slots) || slots.length === 0) return null;
        const usable = slots.filter(isSlotUsable);
        const pool = usable.length > 0 ? usable : slots.slice();
        pool.sort((a, b) => {
            const ai = Number(a?.initiative ?? 0);
            const bi = Number(b?.initiative ?? 0);
            if (ai !== bi) return bi - ai;
            return String(a?.slot_id || '').localeCompare(String(b?.slot_id || ''));
        });
        return pool[0] || null;
    }

    function parseRedirect(record) {
        if (!record || typeof record !== 'object') return null;
        const from = record.from_slot || record.from_slot_id || record.slot_id || record.source_slot || null;
        const oldTo = record.old_target_slot || record.old_slot || record.prev_target_slot || null;
        const newTo = record.new_target_slot || record.target_slot || record.to_slot || record.redirect_to_slot || null;
        if (!from || !newTo) return null;
        return {
            from: String(from),
            oldTo: oldTo ? String(oldTo) : null,
            newTo: String(newTo),
            reason: String(record.reason || record.kind || 'redirect')
        };
    }

    function buildLatestRedirectMap(redirects) {
        const latest = new Map();
        const arr = Array.isArray(redirects) ? redirects : [];
        for (const raw of arr) {
            const parsed = parseRedirect(raw);
            if (!parsed) continue;
            latest.set(parsed.from, parsed);
        }
        return latest;
    }

    function applyDeclareOverlay(state, intentBySource) {
        const declare = state?.declare || {};
        const sourceSlotId = declare?.sourceSlotId || null;
        if (!sourceSlotId) return;

        const skillId = declare?.skillId || null;
        const inferredType = inferTargetTypeFromSkill(skillId);
        let targetType = normalizeTargetType(declare?.targetType || 'single_slot');
        if (!isMassTargetType(targetType) && isMassTargetType(inferredType)) {
            targetType = inferredType;
        }

        const targetSlotId = isMassTargetType(targetType) ? null : (declare?.targetSlotId || null);
        const hasLocalIntent = !!(skillId || targetSlotId || isMassTargetType(targetType));
        if (!hasLocalIntent) return;

        intentBySource.set(String(sourceSlotId), {
            sourceSlotId: String(sourceSlotId),
            skillId: skillId || null,
            targetType,
            targetSlotId: targetSlotId ? String(targetSlotId) : null,
            committed: false,
            isLocalOverlay: true
        });
    }

    function normalizeIntents(state) {
        const raw = state?.intents || {};
        const bySource = new Map();
        const entries = Array.isArray(raw)
            ? raw.map((v, idx) => [String(v?.slot_id || idx), v])
            : Object.entries(raw);

        for (const [sid, intent] of entries) {
            if (!intent || typeof intent !== 'object') continue;
            const sourceSlotId = String(intent.slot_id || sid || '');
            if (!sourceSlotId) continue;

            const skillId = intent.skill_id || intent.skillId || null;
            const targetObj = intent.target || {};
            let targetType = normalizeTargetType(
                targetObj.type
                || intent.target_type
                || intent.targetType
                || 'single_slot'
            );

            const inferredType = inferTargetTypeFromSkill(skillId);
            if (!isMassTargetType(targetType) && isMassTargetType(inferredType)) {
                targetType = inferredType;
            }

            let targetSlotId = targetObj.slot_id || intent.target_slot_id || intent.targetSlotId || null;
            if (isMassTargetType(targetType)) {
                targetSlotId = null;
            } else if (targetType === 'none') {
                targetSlotId = null;
            }

            bySource.set(sourceSlotId, {
                sourceSlotId,
                skillId,
                targetType,
                targetSlotId: targetSlotId ? String(targetSlotId) : null,
                committed: !!intent.committed,
                isLocalOverlay: false
            });
        }

        if (String(state?.phase || '') === 'select') {
            applyDeclareOverlay(state, bySource);
        }

        return bySource;
    }

    function getOpponentActorIds(sourceSlot, actorSlotsByActorId, charById) {
        const sourceActorId = String(sourceSlot?.actor_id ?? sourceSlot?.actor_char_id ?? '');
        const sourceSide = getActorSide(sourceActorId, sourceSlot, charById);

        const actorIds = Array.from(actorSlotsByActorId.keys())
            .filter((id) => String(id) !== sourceActorId);
        if (!sourceSide) return actorIds;

        return actorIds.filter((actorId) => {
            const slots = actorSlotsByActorId.get(actorId) || [];
            const sample = slots[0] || null;
            const side = getActorSide(actorId, sample, charById);
            if (!side) return true;
            return side !== sourceSide;
        });
    }

    function computeArrowGraph(stateInput) {
        const state = stateInput || getCurrentState() || {};
        const slots = toSlotArray(state.slots || {});
        const slotsById = new Map(slots.map((slot) => [String(slot.slot_id), slot]));
        const chars = Array.isArray(state.characters) ? state.characters : [];
        const charById = new Map(chars.map((c) => [String(c?.id || ''), c]));
        const actorSlotsByActorId = new Map();

        for (const slot of slots) {
            const actorId = String(slot?.actor_id ?? slot?.actor_char_id ?? '');
            if (!actorId) continue;
            if (!actorSlotsByActorId.has(actorId)) actorSlotsByActorId.set(actorId, []);
            actorSlotsByActorId.get(actorId).push(slot);
        }

        const intentBySource = normalizeIntents(state);
        const redirectMap = buildLatestRedirectMap(state.redirects || []);
        const singleFinalTargetBySource = new Map();
        const massTargetsBySourceSlot = new Map();
        const arrows = [];

        const resolveTargetSlot = (sourceSlotId, targetSlotId) => {
            const redirect = redirectMap.get(String(sourceSlotId));
            if (!redirect) return { finalTargetSlotId: targetSlotId, redirect: null };
            return {
                finalTargetSlotId: redirect.newTo || targetSlotId,
                redirect
            };
        };

        for (const intent of intentBySource.values()) {
            const sourceSlotId = String(intent.sourceSlotId || '');
            const sourceSlot = slotsById.get(sourceSlotId);
            if (!sourceSlot) continue;

            const targetType = normalizeTargetType(intent.targetType);
            if (isMassTargetType(targetType)) {
                const opponentActorIds = getOpponentActorIds(sourceSlot, actorSlotsByActorId, charById);
                const targetActorSet = new Set();
                for (const actorId of opponentActorIds) {
                    const rep = pickRepresentativeSlot(actorSlotsByActorId.get(actorId) || []);
                    if (!rep || !rep.slot_id) continue;
                    targetActorSet.add(String(actorId));
                    arrows.push({
                        id: `intent:${sourceSlotId}:${actorId}`,
                        kind: 'intent',
                        fromSlotId: sourceSlotId,
                        toSlotId: String(rep.slot_id),
                        status: 'pending',
                        meta: {
                            massType: targetType,
                            actorId: String(actorId),
                            skillId: intent.skillId || null,
                            reason: 'mass_representative'
                        }
                    });
                }
                massTargetsBySourceSlot.set(sourceSlotId, targetActorSet);
                continue;
            }

            if (targetType === 'none') continue;
            if (!intent.targetSlotId) continue;

            const requestedTarget = String(intent.targetSlotId);
            const resolved = resolveTargetSlot(sourceSlotId, requestedTarget);
            const finalTargetSlotId = String(resolved.finalTargetSlotId || requestedTarget);
            if (!slotsById.has(finalTargetSlotId)) continue;

            singleFinalTargetBySource.set(sourceSlotId, finalTargetSlotId);
            arrows.push({
                id: `intent:${sourceSlotId}`,
                kind: 'intent',
                fromSlotId: sourceSlotId,
                toSlotId: finalTargetSlotId,
                status: resolved.redirect ? 'redirected' : 'pending',
                meta: {
                    skillId: intent.skillId || null,
                    prevToSlotId: resolved.redirect?.oldTo || (resolved.redirect ? requestedTarget : null),
                    reason: resolved.redirect?.reason || null
                }
            });
        }

        for (const arrow of arrows) {
            const fromSlot = slotsById.get(String(arrow.fromSlotId));
            const fromActorId = String(fromSlot?.actor_id ?? fromSlot?.actor_char_id ?? '');
            let matched = false;
            let matchedBySlot = null;

            if (arrow.meta?.massType) {
                const defendActorId = String(arrow.meta.actorId || '');
                const defenderSlots = actorSlotsByActorId.get(defendActorId) || [];
                for (const s of defenderSlots) {
                    const sid = String(s?.slot_id || '');
                    if (!sid) continue;
                    if (singleFinalTargetBySource.get(sid) === String(arrow.fromSlotId)) {
                        matched = true;
                        matchedBySlot = sid;
                        break;
                    }
                }
            } else {
                const reverseTarget = singleFinalTargetBySource.get(String(arrow.toSlotId));
                if (reverseTarget && String(reverseTarget) === String(arrow.fromSlotId)) {
                    matched = true;
                    matchedBySlot = String(arrow.toSlotId);
                } else {
                    const massSet = massTargetsBySourceSlot.get(String(arrow.toSlotId));
                    if (massSet && fromActorId && massSet.has(fromActorId)) {
                        matched = true;
                        matchedBySlot = String(arrow.toSlotId);
                    }
                }
            }

            if (matched) {
                arrow.kind = 'match';
                arrow.status = 'matched';
                arrow.meta = {
                    ...(arrow.meta || {}),
                    matchedBySlot
                };
            }
        }

        return {
            arrows,
            meta: {
                phase: String(state?.phase || ''),
                slotCount: slots.length,
                intentCount: intentBySource.size
            }
        };
    }

    function getGraphDigest(graph) {
        const list = (graph?.arrows || []).map((a) => [
            a.id,
            a.kind,
            a.fromSlotId,
            a.toSlotId,
            a.status,
            a.meta?.prevToSlotId || '',
            a.meta?.reason || '',
            a.meta?.massType || '',
            a.meta?.matchedBySlot || ''
        ].join(':'));
        list.sort();
        return list.join('|');
    }

    function buildStateSubset(state) {
        const slots = toSlotArray(state?.slots || {}).map((slot) => ({
            slot_id: String(slot?.slot_id || ''),
            actor_id: String(slot?.actor_id ?? slot?.actor_char_id ?? ''),
            team: String(slot?.team || ''),
            initiative: Number(slot?.initiative ?? 0),
            disabled: !!slot?.disabled,
            spent: !!slot?.spent || !!slot?.consumed || !!slot?.done
        })).sort((a, b) => a.slot_id.localeCompare(b.slot_id));

        const rawIntents = state?.intents || {};
        const intents = Object.entries(rawIntents).map(([sid, intent]) => ({
            slot_id: String(intent?.slot_id || sid || ''),
            skill_id: String(intent?.skill_id || intent?.skillId || ''),
            target_type: normalizeTargetType(intent?.target?.type || intent?.target_type || intent?.targetType || 'single_slot'),
            target_slot: String(intent?.target?.slot_id || intent?.target_slot_id || intent?.targetSlotId || ''),
            committed: !!intent?.committed
        })).sort((a, b) => a.slot_id.localeCompare(b.slot_id));

        const redirects = (Array.isArray(state?.redirects) ? state.redirects : [])
            .map((r) => parseRedirect(r))
            .filter(Boolean)
            .map((r) => ({
                from: r.from,
                oldTo: r.oldTo || '',
                newTo: r.newTo,
                reason: r.reason || ''
            }))
            .sort((a, b) => a.from.localeCompare(b.from));

        const chars = (Array.isArray(state?.characters) ? state.characters : [])
            .map((c) => ({
                id: String(c?.id || ''),
                x: Number(c?.x ?? 0),
                y: Number(c?.y ?? 0)
            }))
            .sort((a, b) => a.id.localeCompare(b.id));

        const declare = state?.declare || {};
        const resolveView = state?.resolveView || {};
        const currentStep = resolveView?.currentStep || {};
        const stepIndex = Number.isFinite(Number(currentStep?.stepIndex))
            ? Number(currentStep.stepIndex)
            : (Number.isFinite(Number(currentStep?.step_index)) ? Number(currentStep.step_index) : null);
        const stepKey = [
            stepIndex !== null ? `idx:${stepIndex}` : '',
            String(currentStep?.attackerSlotId || currentStep?.attacker_slot_id || currentStep?.attacker_slot || ''),
            String(currentStep?.defenderSlotId || currentStep?.defender_slot_id || currentStep?.defender_slot || ''),
            String(currentStep?.kind || '')
        ].join('|');

        return {
            battle_id: String(state?.battle_id || ''),
            round: Number(state?.round ?? 0),
            phase: String(state?.phase || ''),
            selectedSlotId: String(state?.selectedSlotId || ''),
            slots,
            intents,
            redirects,
            declare: {
                sourceSlotId: String(declare?.sourceSlotId || ''),
                targetSlotId: String(declare?.targetSlotId || ''),
                targetType: normalizeTargetType(declare?.targetType || 'single_slot'),
                skillId: String(declare?.skillId || '')
            },
            resolveView: {
                status: String(resolveView?.status || ''),
                phase: String(resolveView?.phase || ''),
                stepKey
            },
            chars
        };
    }

    function clearLayer(layer) {
        while (layer && layer.firstChild) {
            layer.removeChild(layer.firstChild);
        }
    }

    function createMarker(defs, id, color) {
        const marker = document.createElementNS(SVG_NS, 'marker');
        marker.setAttribute('id', id);
        marker.setAttribute('markerWidth', '10');
        marker.setAttribute('markerHeight', '10');
        marker.setAttribute('refX', '8');
        marker.setAttribute('refY', '4');
        marker.setAttribute('orient', 'auto');
        marker.setAttribute('markerUnits', 'strokeWidth');

        const path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('d', 'M0,0 L0,8 L9,4 z');
        path.setAttribute('fill', color);
        marker.appendChild(path);
        defs.appendChild(marker);
    }

    function buildDefs(layer) {
        const defs = document.createElementNS(SVG_NS, 'defs');
        defs.setAttribute('id', 'arrow-defs');
        createMarker(defs, 'arrowhead-pending', '#7a7f8a');
        createMarker(defs, 'arrowhead-match', '#ffb020');
        createMarker(defs, 'arrowhead-redirected', '#d58a1a');
        createMarker(defs, 'arrowhead-mass', '#6a7bff');
        layer.appendChild(defs);
    }

    function getArrowStyle(arrow, highlighted = false) {
        const isMass = !!arrow?.meta?.massType;
        let baseStyle = null;
        if (arrow.kind === 'match') {
            baseStyle = {
                stroke: '#ffb020',
                width: 4,
                opacity: 0.98,
                dash: '',
                markerId: 'arrowhead-match'
            };
        } else if (arrow.status === 'redirected') {
            baseStyle = {
                stroke: '#d58a1a',
                width: 3,
                opacity: 0.95,
                dash: '9 5',
                markerId: 'arrowhead-redirected'
            };
        } else if (isMass) {
            baseStyle = {
                stroke: '#6a7bff',
                width: 2.8,
                opacity: 0.9,
                dash: '7 5',
                markerId: 'arrowhead-mass'
            };
        } else {
            baseStyle = {
                stroke: '#8a93a3',
                width: 2.8,
                opacity: 0.9,
                dash: '7 5',
                markerId: 'arrowhead-pending'
            };
        }
        if (!highlighted) return baseStyle;
        return {
            ...baseStyle,
            stroke: '#ffe066',
            width: baseStyle.width + 1.8,
            opacity: 1,
            dash: '',
            markerId: 'arrowhead-match'
        };
    }

    function getSlotActorId(slot) {
        return String(slot?.actor_id ?? slot?.actor_char_id ?? '');
    }

    function getCenterViaOffset(el, rootEl) {
        if (!el || !rootEl) return null;
        let x = el.offsetWidth / 2;
        let y = el.offsetHeight / 2;
        let cur = el;
        while (cur && cur !== rootEl) {
            x += cur.offsetLeft || 0;
            y += cur.offsetTop || 0;
            cur = cur.offsetParent;
        }
        if (cur !== rootEl) return null;
        return { x, y };
    }

    function toLocalCenter(layer, el) {
        if (!layer || !el) return null;

        const mapRoot = document.getElementById('game-map') || layer.parentElement;
        const offsetCenter = getCenterViaOffset(el, mapRoot);
        if (offsetCenter) {
            if (window.VISUAL_DEBUG_ARROWS) {
                const layerRect = layer.getBoundingClientRect();
                const rect = el.getBoundingClientRect();
                const scale = Number(window.visualScale || 1) || 1;
                const rectCenter = {
                    x: (rect.left - layerRect.left + (rect.width / 2)) / scale,
                    y: (rect.top - layerRect.top + (rect.height / 2)) / scale
                };
                const dx = Math.abs(rectCenter.x - offsetCenter.x);
                const dy = Math.abs(rectCenter.y - offsetCenter.y);
                if (dx > 2 || dy > 2) {
                    console.debug(
                        `[arrow_anchor_probe] el=${el.className || el.tagName} scale=${scale} offset=(${offsetCenter.x.toFixed(1)},${offsetCenter.y.toFixed(1)}) rect=(${rectCenter.x.toFixed(1)},${rectCenter.y.toFixed(1)}) delta=(${dx.toFixed(1)},${dy.toFixed(1)})`
                    );
                }
            }
            return offsetCenter;
        }

        // Fallback: convert transformed viewport coordinates to map-local coordinates.
        const layerRect = layer.getBoundingClientRect();
        const rect = el.getBoundingClientRect();
        const scale = Number(window.visualScale || 1) || 1;
        const x = (rect.left - layerRect.left + (rect.width / 2)) / scale;
        const y = (rect.top - layerRect.top + (rect.height / 2)) / scale;

        if (window.VISUAL_DEBUG_ARROWS) {
            console.debug(
                `[arrow_anchor_fallback] scale=${scale} layer=(${layerRect.left.toFixed(1)},${layerRect.top.toFixed(1)}) center=(${x.toFixed(1)},${y.toFixed(1)})`
            );
        }
        return { x, y };
    }

    function getSlotAnchor(layer, slotId, slotsById) {
        if (!layer || !slotId) return null;
        const selectorId = String(slotId).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        const badge = document.querySelector(`.slot-badge[data-slot-id="${selectorId}"]`);
        if (badge) {
            return toLocalCenter(layer, badge);
        }

        const slot = slotsById.get(String(slotId));
        if (!slot) return null;
        const actorId = getSlotActorId(slot);
        if (!actorId) return null;

        const actorSelector = actorId.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        const token = document.querySelector(`.map-token[data-id="${actorSelector}"]`);
        if (!token) return null;
        return toLocalCenter(layer, token);
    }

    function buildCurve(start, end, laneIndex, laneTotal) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const dist = Math.max(Math.hypot(dx, dy), 0.001);
        if (dist < 6) return null;

        const dirX = dx / dist;
        const dirY = dy / dist;
        const startOffset = 18;
        const endOffset = 18;
        const sx = start.x + dirX * startOffset;
        const sy = start.y + dirY * startOffset;
        const tx = end.x - dirX * endOffset;
        const ty = end.y - dirY * endOffset;

        const midX = (sx + tx) / 2;
        const midY = (sy + ty) / 2;
        const arcHeight = Math.max(20, Math.min(96, dist * 0.22));
        const lane = (laneIndex - ((laneTotal - 1) / 2)) * 14;
        const cx = midX + lane;
        const cy = midY - arcHeight;

        return `M ${sx.toFixed(2)} ${sy.toFixed(2)} Q ${cx.toFixed(2)} ${cy.toFixed(2)} ${tx.toFixed(2)} ${ty.toFixed(2)}`;
    }

    function drawGraph(layer, graph, state) {
        clearLayer(layer);
        buildDefs(layer);

        const slots = toSlotArray(state?.slots || {});
        const slotsById = new Map(slots.map((slot) => [String(slot.slot_id), slot]));
        const arrows = Array.isArray(graph?.arrows) ? graph.arrows : [];
        if (arrows.length === 0) return;

        const lanesBySource = new Map();
        for (const arrow of arrows) {
            const key = String(arrow.fromSlotId || '');
            if (!lanesBySource.has(key)) lanesBySource.set(key, []);
            lanesBySource.get(key).push(arrow);
        }
        for (const list of lanesBySource.values()) {
            list.sort((a, b) => String(a.toSlotId || '').localeCompare(String(b.toSlotId || '')));
        }

        const now = Date.now();
        const highlightActive = (
            runtime.highlightUntil > 0
            && now < runtime.highlightUntil
            && !!runtime.highlightFromSlotId
        );

        for (const arrow of arrows) {
            const from = getSlotAnchor(layer, arrow.fromSlotId, slotsById);
            const to = getSlotAnchor(layer, arrow.toSlotId, slotsById);
            if (!from || !to) continue;

            const laneList = lanesBySource.get(String(arrow.fromSlotId || '')) || [];
            const laneIndex = Math.max(0, laneList.findIndex((a) => String(a.id) === String(arrow.id)));
            const laneTotal = Math.max(1, laneList.length);
            const d = buildCurve(from, to, laneIndex, laneTotal);
            if (!d) continue;

            const arrowFrom = String(arrow.fromSlotId || '');
            const arrowTo = String(arrow.toSlotId || '');
            const isHighlighted = (
                highlightActive
                && arrowFrom === String(runtime.highlightFromSlotId || '')
                && (
                    !runtime.highlightToSlotId
                    || arrowTo === String(runtime.highlightToSlotId || '')
                )
            );
            const style = getArrowStyle(arrow, isHighlighted);
            const path = document.createElementNS(SVG_NS, 'path');
            path.setAttribute('d', d);
            path.setAttribute('fill', 'none');
            path.setAttribute('stroke', style.stroke);
            path.setAttribute('stroke-width', String(style.width));
            path.setAttribute('stroke-linecap', 'round');
            path.setAttribute('stroke-linejoin', 'round');
            path.setAttribute('opacity', String(style.opacity));
            if (style.dash) path.setAttribute('stroke-dasharray', style.dash);
            path.setAttribute('marker-end', `url(#${style.markerId})`);
            path.setAttribute('data-arrow-id', String(arrow.id));
            path.setAttribute('data-arrow-kind', String(arrow.kind || 'intent'));
            path.setAttribute('data-arrow-status', String(arrow.status || 'pending'));

            layer.appendChild(path);
        }
    }

    function renderArrowsNow() {
        const layer = document.getElementById('map-arrow-layer');
        if (!layer) return;

        const state = getCurrentState();
        if (!state) {
            clearLayer(layer);
            runtime.lastRenderDigest = 'empty-state';
            return;
        }

        const visible = !!window.VISUAL_SHOW_ARROWS;
        const phase = String(state.phase || 'select');
        if (!visible || !ACTIVE_PHASES.has(phase)) {
            const hiddenDigest = `hidden:${visible ? 'phase' : 'toggle'}:${phase}`;
            if (runtime.lastRenderDigest !== hiddenDigest) {
                clearLayer(layer);
                runtime.lastRenderDigest = hiddenDigest;
            }
            if (!RESOLVE_PHASES.has(phase)) {
                runtime.frozenGraph = null;
            }
            return;
        }

        const freezeKey = `${state.battle_id || ''}|${state.round || ''}`;
        if (runtime.freezeKey !== freezeKey) {
            runtime.freezeKey = freezeKey;
            runtime.frozenGraph = null;
        }

        const subset = buildStateSubset(state);
        const resolveStep = state?.resolveView?.currentStep || null;
        if (resolveStep) {
            const stepIndex = Number.isFinite(Number(resolveStep?.stepIndex))
                ? Number(resolveStep.stepIndex)
                : (Number.isFinite(Number(resolveStep?.step_index)) ? Number(resolveStep.step_index) : null);
            const nextKey = [
                stepIndex !== null ? `idx:${stepIndex}` : '',
                String(resolveStep?.attackerSlotId || resolveStep?.attacker_slot_id || resolveStep?.attacker_slot || ''),
                String(resolveStep?.defenderSlotId || resolveStep?.defender_slot_id || resolveStep?.defender_slot || ''),
                String(resolveStep?.kind || '')
            ].join('|');
            if (nextKey && nextKey !== runtime.highlightKey) {
                runtime.highlightKey = nextKey;
                runtime.highlightUntil = Date.now() + 800;
                runtime.highlightFromSlotId = String(resolveStep?.attackerSlotId || resolveStep?.attacker_slot_id || resolveStep?.attacker_slot || '') || null;
                runtime.highlightToSlotId = String(resolveStep?.defenderSlotId || resolveStep?.defender_slot_id || resolveStep?.defender_slot || '') || null;
            }
        }
        const subsetHash = JSON.stringify(subset);
        let graph;

        if (phase === 'select') {
            graph = computeArrowGraph(state);
            runtime.frozenGraph = graph;
        } else if (RESOLVE_PHASES.has(phase)) {
            graph = runtime.frozenGraph || computeArrowGraph(state);
            runtime.frozenGraph = graph;
        } else {
            graph = computeArrowGraph(state);
        }

        const graphDigest = getGraphDigest(graph);
        const renderDigest = `${phase}|${subsetHash}|${graphDigest}|${layer.clientWidth}x${layer.clientHeight}`;
        if (runtime.lastRenderDigest === renderDigest) return;

        drawGraph(layer, graph, state);
        runtime.lastRenderDigest = renderDigest;
    }

    function scheduleArrowRender() {
        if (runtime.rafPending) return;
        runtime.rafPending = true;
        window.requestAnimationFrame(() => {
            runtime.rafPending = false;
            renderArrowsNow();
        });
    }

    if (!runtime.resizeBound) {
        window.addEventListener('resize', scheduleArrowRender);
        runtime.resizeBound = true;
    }

    window.computeArrowGraph = computeArrowGraph;
    window.renderArrows = scheduleArrowRender;
})();
