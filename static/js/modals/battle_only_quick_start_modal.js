(function initBattleOnlyQuickStartModal(global) {
    'use strict';

    function getSocketRef() {
        if (typeof socket !== 'undefined' && socket) return socket;
        return global.socket || null;
    }

    function getRoomNameRef() {
        if (typeof currentRoomName !== 'undefined' && currentRoomName) return String(currentRoomName);
        return String(global.currentRoomName || '');
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (ch) => (
            {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;',
            }[ch]
        ));
    }

    function safeInt(value, fallback = 0) {
        const n = Number.parseInt(value, 10);
        return Number.isFinite(n) ? n : fallback;
    }

    function downloadTextFile(filename, content) {
        const blob = new Blob([String(content || '')], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = String(filename || 'battle_only_records.json');
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function normalizeRuleRows(profile) {
        const p = (profile && typeof profile === 'object') ? profile : {};
        const rules = Array.isArray(p.rules) ? p.rules : [];
        return rules.filter((row) => row && typeof row === 'object');
    }

    function normalizeAvatarProfile(raw) {
        const src = (raw && typeof raw === 'object') ? raw : {};
        return {
            enabled: !!src.enabled,
            name: String(src.name || '').trim(),
            description: String(src.description || '').trim(),
            icon: String(src.icon || '').trim(),
        };
    }

    if (typeof global.openStageFieldEffectDetailModal !== 'function') {
        global.openStageFieldEffectDetailModal = function openStageFieldEffectDetailModal(payload) {
            const data = (payload && typeof payload === 'object') ? payload : {};
            const stageId = String(data.stage_id || '').trim();
            const stageName = String(data.stage_name || '').trim() || stageId || 'Stage';
            const rules = normalizeRuleRows(data.stage_field_effect_profile);
            const avatar = normalizeAvatarProfile(data.stage_avatar_profile);
            const effectEnabled = !!data.stage_field_effect_enabled;
            const avatarEnabled = !!data.stage_avatar_enabled;

            const existing = document.getElementById('stage-field-effect-modal-backdrop');
            if (existing) existing.remove();

            const backdrop = document.createElement('div');
            backdrop.id = 'stage-field-effect-modal-backdrop';
            backdrop.className = 'modal-backdrop';
            const modal = document.createElement('div');
            modal.className = 'modal-content';
            modal.style.cssText = 'max-width:760px; width:94vw; max-height:80vh; overflow:auto; padding:18px;';

            const avatarTitle = avatar.name || stageName;
            const avatarDesc = avatar.description || 'No description.';
            const avatarIcon = avatar.icon || 'STAGE';
            const rulesHtml = rules.length
                ? `<ul style="margin:8px 0 0 0; padding-left:18px;">${rules.map((row, idx) => {
                    const type = String(row.type || '').trim() || 'UNKNOWN';
                    const scope = String(row.scope || 'ALL').trim().toUpperCase() || 'ALL';
                    const value = (row.value === undefined || row.value === null) ? '-' : String(row.value);
                    const stateName = String(row.state_name || '').trim();
                    const rid = String(row.rule_id || '').trim() || `rule_${idx + 1}`;
                    const cond = (row.condition && typeof row.condition === 'object') ? ` / cond: ${escapeHtml(JSON.stringify(row.condition))}` : '';
                    const statePart = stateName ? ` / state: ${escapeHtml(stateName)}` : '';
                    return `<li style="margin-bottom:6px;"><code>${escapeHtml(rid)}</code> <strong>${escapeHtml(type)}</strong> / scope:${escapeHtml(scope)} / value:${escapeHtml(value)}${statePart}${cond}</li>`;
                }).join('')}</ul>`
                : '<div style="margin-top:8px; color:#6b7280;">No stage rules configured.</div>';

            modal.innerHTML = `
                <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
                    <div>
                        <div style="font-size:18px; font-weight:700; color:#111827;">Stage Field Effects</div>
                        <div style="font-size:12px; color:#4b5563; margin-top:3px;">${escapeHtml(stageName)}${stageId ? ` (ID: ${escapeHtml(stageId)})` : ''}</div>
                    </div>
                    <button type="button" id="stage-field-effect-modal-close" class="bo-btn bo-btn--sm">Close</button>
                </div>
                <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap; font-size:12px;">
                    <span style="padding:4px 8px; border-radius:999px; border:1px solid #d1d5db; background:${effectEnabled ? '#ecfdf5' : '#f9fafb'}; color:${effectEnabled ? '#166534' : '#6b7280'};">
                        Stage Effect: ${effectEnabled ? 'Enabled' : 'Disabled'}
                    </span>
                    <span style="padding:4px 8px; border-radius:999px; border:1px solid #d1d5db; background:${avatarEnabled ? '#eff6ff' : '#f9fafb'}; color:${avatarEnabled ? '#1d4ed8' : '#6b7280'};">
                        Stage Avatar: ${avatarEnabled ? 'Enabled' : 'Disabled'}
                    </span>
                    <span style="padding:4px 8px; border-radius:999px; border:1px solid #d1d5db; background:#fff; color:#374151;">
                        Rules: ${rules.length}
                    </span>
                </div>
                <div style="margin-top:14px; border:1px solid #e5e7eb; border-radius:10px; padding:12px; background:#f8fafc;">
                    <div style="font-size:12px; color:#6b7280;">Stage Avatar (Display-only)</div>
                    <div style="margin-top:6px; display:flex; gap:10px; align-items:flex-start;">
                        <div style="min-width:54px; height:54px; border-radius:10px; border:1px solid #d1d5db; display:flex; align-items:center; justify-content:center; font-weight:700; background:#fff; color:#1f2937;">
                            ${escapeHtml(avatarIcon)}
                        </div>
                        <div style="min-width:0;">
                            <div style="font-size:15px; font-weight:700; color:#111827;">${escapeHtml(avatarTitle)}</div>
                            <div style="font-size:13px; color:#374151; margin-top:4px;">${escapeHtml(avatarDesc)}</div>
                        </div>
                    </div>
                </div>
                <div style="margin-top:14px; border:1px solid #e5e7eb; border-radius:10px; padding:12px; background:#fff;">
                    <div style="font-size:14px; font-weight:700; color:#111827;">Rules</div>
                    ${rulesHtml}
                </div>
            `;

            backdrop.appendChild(modal);
            document.body.appendChild(backdrop);

            const close = () => backdrop.remove();
            modal.querySelector('#stage-field-effect-modal-close')?.addEventListener('click', close);
            backdrop.addEventListener('click', (e) => {
                if (e.target === backdrop) close();
            });
        };
    }

    function toStatusLabel(status) {
        const key = String(status || '').trim().toLowerCase();
        if (key === 'lobby') return '待機';
        if (key === 'draft') return '編成中';
        if (key === 'in_battle') return '戦闘中';
        return key || '不明';
    }

    function toResultLabel(result) {
        const key = String(result || '').trim().toLowerCase();
        if (key === 'ally_win') return '味方勝利';
        if (key === 'enemy_win') return '敵勝利';
        if (key === 'draw') return '引き分け';
        if (key === 'aborted') return '中断';
        if (key === 'unknown') return '不明';
        if (key === 'in_progress') return '進行中';
        return key || '-';
    }

    function collectBattleMapCenterAnchor() {
        const viewport = document.getElementById('map-viewport');
        const gameMap = document.getElementById('game-map');
        const scale = Number(global.visualScale || 1);
        const gridSize = Number(global.GRID_SIZE || 90);
        if (!viewport || !gameMap || !Number.isFinite(scale) || scale <= 0 || !Number.isFinite(gridSize) || gridSize <= 0) {
            return null;
        }
        const viewportRect = viewport.getBoundingClientRect();
        const mapRect = gameMap.getBoundingClientRect();
        if (!viewportRect.width || !viewportRect.height) {
            return null;
        }

        const centerX = viewportRect.left + (viewportRect.width / 2);
        const centerY = viewportRect.top + (viewportRect.height / 2);
        const mapX = (centerX - mapRect.left) / scale;
        const mapY = (centerY - mapRect.top) / scale;
        const gridX = mapX / gridSize;
        const gridY = mapY / gridSize;
        if (!Number.isFinite(gridX) || !Number.isFinite(gridY)) {
            return null;
        }
        return {
            x: Math.round(gridX * 10000) / 10000,
            y: Math.round(gridY * 10000) / 10000,
        };
    }

    function openBattleOnlyQuickStartModal() {
        const socketRef = getSocketRef();
        const roomName = getRoomNameRef();
        if (!socketRef || !roomName) {
            alert('ルーム情報の取得前です。');
            return;
        }
        if (typeof global.removeBattleOnlyCenterCta === 'function') {
            try { global.removeBattleOnlyCenterCta(); } catch (_e) {}
        }

        const existing = document.getElementById('bo-quick-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-quick-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--draft';
        panel.style.maxWidth = '960px';
        panel.style.width = '96vw';
        panel.innerHTML = `
            <h3 class="bo-modal-title">戦闘専用 かんたん戦闘突入</h3>
            <div id="bo-quick-msg" class="bo-msg">ステージを選ぶだけで戦闘突入できます。</div>
            <div id="bo-quick-summary" class="bo-summary"></div>
            <div style="display:grid; grid-template-columns: 1fr; gap: 10px;">
                <div class="bo-card">
                    <h4 class="bo-card-title">1. ステージを選ぶ</h4>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <input id="bo-quick-stage-search" class="bo-input" style="min-width:240px; flex:1 1 320px;" placeholder="ID / 名前 / コンセプトで検索" />
                        <select id="bo-quick-stage-sort" class="bo-input" style="min-width:170px;">
                            <option value="sort_key_asc">表示順</option>
                            <option value="updated_desc">更新順（新しい順）</option>
                            <option value="name_asc">名前 昇順</option>
                            <option value="name_desc">名前 降順</option>
                        </select>
                        <button id="bo-quick-refresh" class="bo-btn bo-btn--sm">再読込</button>
                    </div>
                    <div id="bo-quick-stage-list" style="display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:8px; margin-top:10px;"></div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">2. 味方の参加方法</h4>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <select id="bo-quick-ally-mode" class="bo-input">
                            <option value="preset">ステージ設定の味方編成を使う</option>
                            <option value="room_existing">現在ルームの味方を使う</option>
                        </select>
                    </div>
                    <div id="bo-quick-ally-hint" style="margin-top:6px; font-size:12px; color:#555;"></div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">3. 操作モード</h4>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <select id="bo-quick-control-mode" class="bo-input">
                            <option value="all">みんなで操作する</option>
                            <option value="starter_only">戦闘突入した人だけ操作する</option>
                        </select>
                    </div>
                    <div id="bo-quick-control-hint" style="margin-top:6px; font-size:12px; color:#555;"></div>
                    <div style="margin-top:10px; display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <label style="display:flex; align-items:center; gap:6px;">
                            <input id="bo-quick-stage-effect-enabled" type="checkbox" />
                            <span>Stage Field Effect Enabled</span>
                        </label>
                        <label style="display:flex; align-items:center; gap:6px;">
                            <input id="bo-quick-stage-avatar-enabled" type="checkbox" />
                            <span>Stage Avatar Enabled</span>
                        </label>
                        <button id="bo-quick-stage-detail" class="bo-btn bo-btn--sm">効果詳細を見る</button>
                    </div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">4. 突入可否チェック</h4>
                    <div id="bo-quick-validation" class="bo-validation"></div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">5. 戦績</h4>
                    <div id="bo-quick-records" class="bo-validation"></div>
                    <div style="margin-top:8px;">
                        <button id="bo-quick-export-records" class="bo-btn bo-btn--sm bo-btn--accent">戦績JSON出力</button>
                    </div>
                </div>
            </div>
            <div style="display:flex; justify-content:space-between; gap:8px; margin-top:12px; flex-wrap:wrap;">
                <div>
                    <button id="bo-quick-open-full" class="bo-btn bo-btn--sm">詳細編成を開く</button>
                </div>
                <div>
                    <button id="bo-quick-start" class="bo-btn bo-btn--sm bo-btn--success">戦闘突入</button>
                    <button id="bo-quick-close" class="bo-btn bo-btn--sm">閉じる</button>
                </div>
            </div>
        `;
        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-quick-msg');
        const summaryEl = panel.querySelector('#bo-quick-summary');
        const validationEl = panel.querySelector('#bo-quick-validation');
        const recordsEl = panel.querySelector('#bo-quick-records');
        const stageListEl = panel.querySelector('#bo-quick-stage-list');
        const stageSearchEl = panel.querySelector('#bo-quick-stage-search');
        const stageSortEl = panel.querySelector('#bo-quick-stage-sort');
        const allyModeSel = panel.querySelector('#bo-quick-ally-mode');
        const allyHintEl = panel.querySelector('#bo-quick-ally-hint');
        const controlModeSel = panel.querySelector('#bo-quick-control-mode');
        const controlHintEl = panel.querySelector('#bo-quick-control-hint');
        const stageEffectEnabledEl = panel.querySelector('#bo-quick-stage-effect-enabled');
        const stageAvatarEnabledEl = panel.querySelector('#bo-quick-stage-avatar-enabled');
        const stageDetailBtn = panel.querySelector('#bo-quick-stage-detail');
        const startBtn = panel.querySelector('#bo-quick-start');
        const listeners = [];

        const model = {
            battle_only: {},
            stage_presets: {},
            sorted_stage_preset_ids: [],
            enemy_formations: {},
            ally_formations: {},
            validation: { ready: false, issues: [] },
            can_manage: false,
            records: [],
            active_record_id: null,
        };
        let pendingStart = false;

        function setMsg(text, color = '#444') {
            if (!msgEl) return;
            msgEl.textContent = String(text || '');
            msgEl.style.color = color;
        }

        function requestDraftState() {
            socketRef.emit('request_bo_draft_state', { room: roomName });
        }

        function requestRecordState() {
            socketRef.emit('request_bo_record_state', { room: roomName });
        }

        function requestValidate() {
            socketRef.emit('request_bo_validate_entry', { room: roomName });
        }

        function getSelectedStageId() {
            return String((model.battle_only && model.battle_only.selected_stage_id) || '').trim();
        }

        function getStageRecord(stageId) {
            const id = String(stageId || '').trim();
            if (!id) return null;
            return (model.stage_presets && typeof model.stage_presets === 'object')
                ? (model.stage_presets[id] || null)
                : null;
        }

        function getStageRequiredAllyCount(stage) {
            const rec = (stage && typeof stage === 'object') ? stage : {};
            return Math.max(0, safeInt(rec.required_ally_count, safeInt((model.battle_only || {}).required_ally_count, 0)));
        }

        function applyStageSelection(stageId) {
            const id = String(stageId || '').trim();
            if (!id) {
                setMsg('ステージを選択してください。', '#b45309');
                return false;
            }
            socketRef.emit('request_bo_select_stage_preset', { room: roomName, stage_id: id });
            return true;
        }

        function applyAllyMode() {
            const mode = String(allyModeSel && allyModeSel.value || 'preset').trim().toLowerCase();
            const stage = getStageRecord(getSelectedStageId());
            const required = getStageRequiredAllyCount(stage);
            socketRef.emit('request_bo_set_ally_mode', {
                room: roomName,
                ally_mode: (mode === 'room_existing' ? 'room_existing' : 'preset'),
                required_ally_count: required,
            });
            return true;
        }

        function getControlModeValue() {
            const mode = String(controlModeSel && controlModeSel.value || 'all').trim().toLowerCase();
            return mode === 'starter_only' ? 'starter_only' : 'all';
        }

        function applyControlMode() {
            const mode = getControlModeValue();
            socketRef.emit('request_bo_set_control_mode', {
                room: roomName,
                intent_control_mode: mode,
            });
            return mode;
        }

        function applyStageFieldEffectEnabled() {
            const enabled = !!(stageEffectEnabledEl && stageEffectEnabledEl.checked);
            socketRef.emit('request_bo_set_stage_field_effect_enabled', {
                room: roomName,
                enabled,
            });
            return enabled;
        }

        function applyStageAvatarEnabled() {
            const enabled = !!(stageAvatarEnabledEl && stageAvatarEnabledEl.checked);
            socketRef.emit('request_bo_set_stage_avatar_enabled', {
                room: roomName,
                enabled,
            });
            return enabled;
        }

        function openStageFieldEffectDetailFromCurrent() {
            const bo = model.battle_only || {};
            const selectedId = getSelectedStageId();
            const stage = getStageRecord(selectedId) || {};
            const stageProfile = (stage.field_effect_profile && typeof stage.field_effect_profile === 'object')
                ? stage.field_effect_profile
                : ((bo.stage_field_effect_profile && typeof bo.stage_field_effect_profile === 'object') ? bo.stage_field_effect_profile : {});
            const avatarProfile = (stage.stage_avatar && typeof stage.stage_avatar === 'object')
                ? stage.stage_avatar
                : ((bo.stage_avatar_profile && typeof bo.stage_avatar_profile === 'object') ? bo.stage_avatar_profile : {});
            global.openStageFieldEffectDetailModal({
                stage_id: selectedId,
                stage_name: String(stage.name || selectedId || '').trim(),
                stage_field_effect_enabled: !!bo.stage_field_effect_enabled,
                stage_avatar_enabled: !!bo.stage_avatar_enabled,
                stage_field_effect_profile: stageProfile,
                stage_avatar_profile: avatarProfile,
            });
        }

        function stageIds() {
            const ids = (Array.isArray(model.sorted_stage_preset_ids) && model.sorted_stage_preset_ids.length)
                ? model.sorted_stage_preset_ids.slice()
                : Object.keys(model.stage_presets || {}).sort();
            const keyword = String(stageSearchEl && stageSearchEl.value || '').trim().toLowerCase();
            const sortType = String(stageSortEl && stageSortEl.value || 'sort_key_asc').trim();
            const filtered = ids.filter((id) => {
                if (!keyword) return true;
                const rec = model.stage_presets[id] || {};
                const hay = [
                    id,
                    rec.name || '',
                    rec.concept || '',
                ].join('\n').toLowerCase();
                return hay.includes(keyword);
            });
            filtered.sort((a, b) => {
                const ra = model.stage_presets[a] || {};
                const rb = model.stage_presets[b] || {};
                if (sortType === 'updated_desc') {
                    return safeInt(rb.updated_at, 0) - safeInt(ra.updated_at, 0);
                }
                if (sortType === 'name_desc') {
                    return String(rb.name || b).localeCompare(String(ra.name || a), 'ja');
                }
                if (sortType === 'name_asc') {
                    return String(ra.name || a).localeCompare(String(rb.name || b), 'ja');
                }
                const sa = safeInt(ra.sort_key, 0);
                const sb = safeInt(rb.sort_key, 0);
                if (sa !== sb) return sa - sb;
                return String(ra.name || a).localeCompare(String(rb.name || b), 'ja');
            });
            return filtered;
        }

        function renderStageList() {
            const selectedId = getSelectedStageId();
            const ids = stageIds();
            if (!ids.length) {
                stageListEl.innerHTML = '<div class="bo-empty">表示できるステージがありません。</div>';
                return;
            }
            stageListEl.innerHTML = ids.map((id) => {
                const rec = model.stage_presets[id] || {};
                const selected = (id === selectedId);
                const required = getStageRequiredAllyCount(rec);
                return `
                    <button type="button" class="bo-stage-pick-btn" data-stage-id="${escapeHtml(id)}" style="
                        text-align:left;
                        border:2px solid ${selected ? '#2563eb' : '#d1d5db'};
                        background:${selected ? '#eff6ff' : '#fff'};
                        border-radius:10px;
                        padding:10px 12px;
                        cursor:pointer;
                        min-height:110px;">
                        <div style="font-size:15px; font-weight:700; color:#111827;">${escapeHtml(rec.name || id)}</div>
                        <div style="font-size:12px; color:#374151; margin-top:2px;">ID: ${escapeHtml(id)} / 必要味方: ${required}</div>
                        <div style="font-size:12px; color:#6b7280; margin-top:5px;">${escapeHtml(rec.concept || 'コンセプト未設定')}</div>
                    </button>
                `;
            }).join('');

            stageListEl.querySelectorAll('.bo-stage-pick-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = String(btn.getAttribute('data-stage-id') || '').trim();
                    if (!id) return;
                    applyStageSelection(id);
                    setMsg('ステージを反映しました。', '#444');
                });
            });
        }

        function renderSummary() {
            const bo = model.battle_only || {};
            const selectedId = getSelectedStageId();
            const stage = getStageRecord(selectedId);
            const status = toStatusLabel(bo.status || 'lobby');
            const roomAllies = safeInt((model.validation || {}).room_ally_count, 0);
            const enemyCount = safeInt((model.validation || {}).enemy_entry_count, 0);
            const allyMode = String(bo.ally_mode || 'preset').trim().toLowerCase();
            const modeLabel = allyMode === 'room_existing' ? '現在ルーム利用' : 'ステージ味方編成';
            summaryEl.innerHTML = `
                <div><strong>状態:</strong> ${escapeHtml(status)} / <strong>味方モード:</strong> ${escapeHtml(modeLabel)} / <strong>現在ルーム味方数:</strong> ${roomAllies} / <strong>敵数:</strong> ${enemyCount}</div>
                <div style="margin-top:4px;">
                    <strong>選択ステージ:</strong> ${escapeHtml((stage && (stage.name || selectedId)) || '未選択')}
                    ${stage ? `<span style="color:#4b5563;">（必要味方: ${getStageRequiredAllyCount(stage)}）</span>` : ''}
                </div>
                ${stage ? `<div style="margin-top:4px; color:#4b5563;">${escapeHtml(stage.description || stage.concept || '')}</div>` : ''}
            `;
        }

        function renderAllyMode() {
            const bo = model.battle_only || {};
            const allyMode = String(bo.ally_mode || 'preset').trim().toLowerCase();
            allyModeSel.value = (allyMode === 'room_existing' ? 'room_existing' : 'preset');
            const stage = getStageRecord(getSelectedStageId());
            const required = getStageRequiredAllyCount(stage);
            if (allyHintEl) {
                if (allyModeSel.value === 'room_existing') {
                    allyHintEl.textContent = `現在ルーム利用時は味方人数 ${required} 人で一致させる必要があります。`;
                } else {
                    const allyFormationId = String((stage && stage.ally_formation_id) || bo.ally_formation_id || '').trim();
                    allyHintEl.textContent = allyFormationId
                        ? `味方編成プリセット ${allyFormationId} を使います。`
                        : 'ステージに味方編成が設定されていません。';
                }
            }
        }

        function renderControlMode() {
            const bo = model.battle_only || {};
            const options = (bo.options && typeof bo.options === 'object') ? bo.options : {};
            const mode = String(options.intent_control_mode || 'all').trim().toLowerCase();
            if (controlModeSel) {
                controlModeSel.value = mode === 'starter_only' ? 'starter_only' : 'all';
                controlModeSel.disabled = !model.can_manage;
            }
            if (controlHintEl) {
                const hint = (controlModeSel && controlModeSel.value === 'starter_only')
                    ? '戦闘突入を実行した1人（+GM）のみが宣言操作できます。'
                    : '参加者全員（+GM）が宣言操作できます。';
                controlHintEl.textContent = model.can_manage ? hint : `${hint}（設定変更はGMのみ）`;
            }
        }

        function renderStageFieldEffectEnabled() {
            if (!stageEffectEnabledEl) return;
            const bo = model.battle_only || {};
            stageEffectEnabledEl.checked = !!bo.stage_field_effect_enabled;
            stageEffectEnabledEl.disabled = !model.can_manage;
        }

        function renderStageAvatarEnabled() {
            if (!stageAvatarEnabledEl) return;
            const bo = model.battle_only || {};
            stageAvatarEnabledEl.checked = !!bo.stage_avatar_enabled;
            stageAvatarEnabledEl.disabled = !model.can_manage;
        }

        function renderValidation() {
            const validation = (model.validation && typeof model.validation === 'object') ? model.validation : {};
            const issues = Array.isArray(validation.issues) ? validation.issues : [];
            if (!issues.length) {
                validationEl.innerHTML = '<div class="bo-validation-title" style="color:#166534;">準備完了です。戦闘突入できます。</div>';
            } else {
                validationEl.innerHTML = `
                    <div class="bo-validation-title">確認事項 ${issues.length}件</div>
                    <ul class="bo-validation-list">${issues.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
                `;
            }
            const ready = !!validation.ready && !issues.length;
            startBtn.disabled = !ready;
            startBtn.style.opacity = ready ? '1' : '0.65';
            if (ready) {
                setMsg('準備完了です。', '#166534');
            }
        }

        function renderRecords() {
            const rows = Array.isArray(model.records) ? model.records.slice().reverse() : [];
            const activeId = String(model.active_record_id || '').trim();
            if (!recordsEl) return;
            if (!rows.length) {
                recordsEl.innerHTML = '<div class="bo-validation-title">戦績はまだありません。</div>';
                return;
            }
            const listHtml = rows.slice(0, 8).map((rec) => {
                const id = String(rec?.id || '');
                const status = toStatusLabel(rec?.status || '');
                const result = toResultLabel(rec?.result || '');
                const counts = `${safeInt(rec?.ally_count, 0)} / ${safeInt(rec?.enemy_count, 0)}`;
                const startedAt = String(rec?.started_at || '-');
                const rowClass = (activeId && id === activeId) ? ' style="font-weight:700;"' : '';
                return `<li${rowClass}>${escapeHtml(id)} | ${escapeHtml(status)} | ${escapeHtml(result)} | 人数(味方/敵): ${escapeHtml(counts)} | ${escapeHtml(startedAt)}</li>`;
            }).join('');
            recordsEl.innerHTML = `
                <div class="bo-validation-title">最新戦績 ${Math.min(rows.length, 8)} / ${rows.length} 件</div>
                <ul class="bo-validation-list">${listHtml}</ul>
            `;
        }

        function renderAll() {
            renderStageList();
            renderAllyMode();
            renderControlMode();
            renderStageFieldEffectEnabled();
            renderStageAvatarEnabled();
            renderSummary();
            renderValidation();
            renderRecords();
        }

        function onSocket(eventName, fn) {
            socketRef.on(eventName, fn);
            listeners.push([eventName, fn]);
        }

        onSocket('bo_draft_state', (data) => {
            model.battle_only = (data && typeof data.battle_only === 'object') ? data.battle_only : {};
            model.stage_presets = (data && typeof data.stage_presets === 'object') ? data.stage_presets : {};
            model.sorted_stage_preset_ids = Array.isArray(data && data.sorted_stage_preset_ids)
                ? data.sorted_stage_preset_ids
                : Object.keys(model.stage_presets).sort();
            model.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            model.ally_formations = (data && typeof data.ally_formations === 'object') ? data.ally_formations : {};
            model.can_manage = !!(data && data.can_manage);
            model.records = Array.isArray(data && data.records) ? data.records : (Array.isArray(model.records) ? model.records : []);
            model.active_record_id = data ? (data.active_record_id || null) : model.active_record_id;
            renderAll();
            requestValidate();
        });
        onSocket('bo_stage_preset_selected', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            const stage = (data && data.stage_preset && typeof data.stage_preset === 'object') ? data.stage_preset : null;
            const stageId = String((data && data.stage_id) || (stage && stage.id) || '').trim();
            if (stage && stageId) model.stage_presets[stageId] = stage;
            renderAll();
            requestValidate();
        });
        onSocket('bo_ally_mode_updated', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            renderAll();
            requestValidate();
        });
        onSocket('bo_control_mode_updated', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            renderAll();
            requestValidate();
        });
        onSocket('bo_stage_field_effect_updated', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            renderAll();
            requestValidate();
        });
        onSocket('bo_stage_avatar_updated', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            renderAll();
            requestValidate();
        });
        onSocket('bo_entry_validated', (data) => {
            model.validation = (data && typeof data === 'object') ? data : { ready: false, issues: ['検証結果の取得に失敗しました。'] };
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            renderAll();
            if (pendingStart) {
                pendingStart = false;
                if (model.validation.ready) {
                    socketRef.emit('request_bo_start_battle', {
                        room: roomName,
                        anchor: collectBattleMapCenterAnchor(),
                        intent_control_mode: getControlModeValue(),
                    });
                    setMsg('戦闘突入を送信しました。', '#444');
                } else {
                    setMsg((Array.isArray(model.validation.issues) && model.validation.issues[0]) || '未設定項目があります。', '#b91c1c');
                }
            }
        });
        onSocket('bo_battle_started', () => {
            setMsg('戦闘に突入しました。', '#166534');
            setTimeout(() => { closeModal(); }, 120);
        });
        onSocket('bo_record_state', (data) => {
            model.records = Array.isArray(data && data.records) ? data.records : [];
            model.active_record_id = data ? (data.active_record_id || null) : null;
            renderRecords();
        });
        onSocket('bo_record_updated', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || '').trim();
                const rows = Array.isArray(model.records) ? model.records.slice() : [];
                const idx = rows.findIndex((row) => row && String(row.id || '').trim() === id);
                if (idx >= 0) rows[idx] = rec;
                else rows.push(rec);
                model.records = rows;
            }
            model.active_record_id = data ? (data.active_record_id || null) : model.active_record_id;
            renderRecords();
        });
        onSocket('bo_record_export', (data) => {
            const filename = String((data && data.filename) || 'battle_only_records.json');
            const content = String((data && data.content) || '');
            downloadTextFile(filename, content);
            setMsg(`戦績を出力しました（${safeInt(data && data.record_count, 0)}件）`, '#166534');
        });
        ['bo_draft_error', 'bo_catalog_error', 'bo_preset_error', 'bo_enemy_formation_error', 'bo_ally_formation_error', 'bo_stage_preset_error'].forEach((eventName) => {
            onSocket(eventName, (data) => {
                const msg = String((data && data.message) || 'エラーが発生しました。');
                setMsg(msg, '#b91c1c');
                pendingStart = false;
            });
        });

        panel.querySelector('#bo-quick-refresh')?.addEventListener('click', () => {
            requestDraftState();
            requestValidate();
        });
        allyModeSel?.addEventListener('change', () => {
            applyAllyMode();
            setMsg('味方の参加方法を反映しました。', '#444');
        });
        controlModeSel?.addEventListener('change', () => {
            applyControlMode();
            setMsg('操作モードを反映しました。', '#444');
        });
        stageEffectEnabledEl?.addEventListener('change', () => {
            const enabled = applyStageFieldEffectEnabled();
            setMsg(enabled ? 'Stage field effect を有効化しました。' : 'Stage field effect を無効化しました。', '#444');
        });
        stageAvatarEnabledEl?.addEventListener('change', () => {
            const enabled = applyStageAvatarEnabled();
            setMsg(enabled ? 'Stage avatar enabled.' : 'Stage avatar disabled.', '#444');
        });
        stageDetailBtn?.addEventListener('click', () => {
            openStageFieldEffectDetailFromCurrent();
        });
        panel.querySelector('#bo-quick-open-full')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyDraftModal === 'function') {
                global.openBattleOnlyDraftModal();
            } else {
                setMsg('詳細編成モーダルを読み込めませんでした。', '#b91c1c');
            }
        });
        panel.querySelector('#bo-quick-start')?.addEventListener('click', () => {
            const selectedStageId = getSelectedStageId();
            if (!selectedStageId) {
                setMsg('先にステージを選択してください。', '#b91c1c');
                return;
            }
            applyAllyMode();
            pendingStart = true;
            requestValidate();
        });
        panel.querySelector('#bo-quick-export-records')?.addEventListener('click', () => {
            socketRef.emit('request_bo_record_export', { room: roomName });
            setMsg('戦績出力を送信しました。', '#444');
        });
        stageSearchEl?.addEventListener('input', renderStageList);
        stageSortEl?.addEventListener('change', renderStageList);

        function closeModal() {
            while (listeners.length) {
                const [eventName, fn] = listeners.pop();
                socketRef.off(eventName, fn);
            }
            overlay.remove();
            if (global.__boQuickStartCleanup === closeModal) {
                global.__boQuickStartCleanup = null;
            }
        }

        panel.querySelector('#bo-quick-close')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });
        global.__boQuickStartCleanup = closeModal;

        requestDraftState();
        requestRecordState();
        requestValidate();
        renderAll();
    }

    global.openBattleOnlyQuickStartModal = openBattleOnlyQuickStartModal;
})(window);
