(function initBattleOnlyCatalogModal(global) {
    'use strict';

    function getSocketRef() {
        if (typeof socket !== 'undefined' && socket) return socket;
        return global.socket || null;
    }

    function getRoomNameRef() {
        if (typeof currentRoomName !== 'undefined' && currentRoomName) return currentRoomName;
        return global.currentRoomName || '';
    }

    function getCurrentUserAttribute() {
        if (typeof currentUserAttribute !== 'undefined' && currentUserAttribute) return String(currentUserAttribute);
        return String(global.currentUserAttribute || 'Player');
    }

    function safeInt(value, fallback) {
        const n = Number.parseInt(value, 10);
        return Number.isFinite(n) ? n : fallback;
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

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function getBehaviorProfileTemplate() {
        return {
            enabled: true,
            version: 1,
            initial_loop_id: 'loop_1',
            loops: {
                loop_1: {
                    repeat: true,
                    steps: [
                        {
                            actions: ['__RANDOM_USABLE__'],
                            targets: ['target_enemy_random'],
                            next_loop_id: null,
                            next_reset_step_index: true,
                        }
                    ],
                    transitions: [],
                }
            },
        };
    }

    function parseCharacterJsonText(rawText) {
        const text = String(rawText || '').trim();
        if (!text) {
            return { ok: false, message: 'キャラクターJSONを入力してください。' };
        }
        try {
            const parsed = JSON.parse(text);
            if (!parsed || typeof parsed !== 'object') {
                return { ok: false, message: 'JSONの最上位がオブジェクトではありません。' };
            }
            const data = (parsed.kind === 'character' && parsed.data && typeof parsed.data === 'object')
                ? parsed.data
                : (parsed.data && typeof parsed.data === 'object')
                    ? parsed.data
                    : parsed;
            if (!data || typeof data !== 'object') {
                return { ok: false, message: 'character.data が見つかりません。' };
            }
            return { ok: true, parsed };
        } catch (e) {
            return { ok: false, message: `JSON解析に失敗しました: ${e.message}` };
        }
    }

    function stripRuntimeCharacterFields(src) {
        const c = clone(src || {});
        delete c.id;
        delete c.owner;
        delete c.owner_id;
        delete c.baseName;
        delete c.x;
        delete c.y;
        delete c.hasActed;
        delete c.speedRoll;
        delete c.used_skills_this_round;
        delete c.active_round;
        delete c.last_move_ts;
        delete c.targetLocked;
        return c;
    }

    function normalizeStatusRows(rawStatuses, fallbackStates) {
        const result = [];
        if (Array.isArray(rawStatuses)) {
            rawStatuses.forEach((row) => {
                if (!row || typeof row !== 'object') return;
                const label = String(row.label || row.name || '').trim();
                if (!label) return;
                const value = safeInt(row.value, 0);
                const max = safeInt((row.max !== undefined ? row.max : row.value), value);
                result.push({ label, value, max });
            });
        }

        const hasLabel = (name) => result.some((row) => row.label === name);
        ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘'].forEach((name) => {
            if (hasLabel(name)) return;
            const states = Array.isArray(fallbackStates) ? fallbackStates : [];
            const found = states.find((s) => s && String(s.name || '').trim() === name);
            result.push({ label: name, value: safeInt(found && found.value, 0), max: safeInt(found && found.max, 0) });
        });
        return result;
    }

    function buildStatesFromStatusRows(statusRows) {
        const rows = Array.isArray(statusRows) ? statusRows : [];
        return rows
            .filter((row) => row && row.label !== 'HP' && row.label !== 'MP')
            .map((row) => ({
                name: String(row.label || '').trim(),
                value: safeInt(row.value, 0),
                max: safeInt((row.max !== undefined ? row.max : row.value), safeInt(row.value, 0)),
            }))
            .filter((row) => !!row.name);
    }

    function buildCharacterJsonFromRoomChar(src, snapshotMode) {
        const base = stripRuntimeCharacterFields(src);
        const mode = String(snapshotMode || 'current').trim().toLowerCase();
        if (mode === 'initial') {
            const initialData = (src.initial_data && typeof src.initial_data === 'object') ? src.initial_data : null;
            const initialState = (src.initial_state && typeof src.initial_state === 'object') ? src.initial_state : null;
            const initialStatus = Array.isArray(src.initial_status) ? src.initial_status : null;

            if (initialData && Array.isArray(base.params)) {
                const done = new Set();
                base.params = base.params.map((p) => {
                    if (!p || typeof p !== 'object') return p;
                    const label = String(p.label || '').trim();
                    if (!label || !Object.prototype.hasOwnProperty.call(initialData, label)) return p;
                    done.add(label);
                    return { ...p, value: initialData[label] };
                });
                Object.keys(initialData).forEach((label) => {
                    if (done.has(label)) return;
                    base.params.push({ label, value: initialData[label] });
                });
            }

            if (initialState) {
                const maxHp = safeInt(initialState.maxHp, safeInt(base.maxHp, safeInt(base.hp, 0)));
                const maxMp = safeInt(initialState.maxMp, safeInt(base.maxMp, safeInt(base.mp, 0)));
                base.maxHp = maxHp;
                base.hp = maxHp;
                base.maxMp = maxMp;
                base.mp = maxMp;
                if (initialState.inventory && typeof initialState.inventory === 'object') base.inventory = clone(initialState.inventory);
                if (Array.isArray(initialState.special_buffs)) base.special_buffs = clone(initialState.special_buffs);
            }

            if (initialStatus) {
                const statusRows = normalizeStatusRows(initialStatus, base.states);
                base.status = statusRows;
                base.initial_status = clone(statusRows);
                const hpRow = statusRows.find((r) => r.label === 'HP');
                const mpRow = statusRows.find((r) => r.label === 'MP');
                if (hpRow) {
                    base.hp = safeInt(hpRow.value, base.hp);
                    base.maxHp = safeInt(hpRow.max, base.maxHp);
                }
                if (mpRow) {
                    base.mp = safeInt(mpRow.value, base.mp);
                    base.maxMp = safeInt(mpRow.max, base.maxMp);
                }
                base.states = buildStatesFromStatusRows(statusRows);
            }
        }

        return { kind: 'character', data: base };
    }

    function summarizeCharacterJson(characterJson) {
        const root = (characterJson && typeof characterJson === 'object') ? characterJson : {};
        const data = (root.kind === 'character' && root.data && typeof root.data === 'object')
            ? root.data
            : (root.data && typeof root.data === 'object')
                ? root.data
                : root;
        const statusRows = Array.isArray(data.status) ? data.status : [];
        const hpRow = statusRows.find((r) => String((r && (r.label || r.name)) || '').trim() === 'HP');
        const mpRow = statusRows.find((r) => String((r && (r.label || r.name)) || '').trim() === 'MP');
        const commands = String(data.commands || '').split('\n').map((x) => x.trim()).filter((x) => !!x);
        return {
            name: String(data.name || '').trim() || '(名前なし)',
            hp: hpRow ? `${safeInt(hpRow.value, 0)}/${safeInt(hpRow.max, safeInt(hpRow.value, 0))}` : '-',
            mp: mpRow ? `${safeInt(mpRow.value, 0)}/${safeInt(mpRow.max, safeInt(mpRow.value, 0))}` : '-',
            statusCount: statusRows.length,
            commandCount: commands.length,
            passiveCount: Array.isArray(data.SPassive) ? data.SPassive.length : 0,
        };
    }

    function extractCharacterData(characterJson) {
        const root = (characterJson && typeof characterJson === 'object') ? characterJson : {};
        const data = (root.kind === 'character' && root.data && typeof root.data === 'object')
            ? root.data
            : (root.data && typeof root.data === 'object')
                ? root.data
                : root;
        return (data && typeof data === 'object') ? data : {};
    }

    function buildBehaviorEditorCharForPreset(rec, overrideProfile) {
        const preset = (rec && typeof rec === 'object') ? rec : {};
        const charData = extractCharacterData(preset.character_json || {});
        const name = String(charData.name || preset.name || '(敵)').trim();
        const commands = String(charData.commands || '').trim();
        const granted = Array.isArray(charData.granted_skills) ? charData.granted_skills : [];
        return {
            id: `bo_enemy_override_${String(preset.id || '').trim() || Date.now()}`,
            name,
            commands,
            granted_skills: granted,
            flags: {
                behavior_profile: (overrideProfile && typeof overrideProfile === 'object') ? overrideProfile : {},
            },
        };
    }

    function listCharacterStatusRows(characterData) {
        const rows = [];
        const pushStatus = (rawLabel, rawValue, rawMax) => {
            const label = String(rawLabel || '').trim();
            if (!label) return;
            if (rows.some((x) => x.label === label)) return;
            const value = safeInt(rawValue, 0);
            const max = safeInt((rawMax !== undefined ? rawMax : rawValue), value);
            rows.push({ label, value, max });
        };

        const status = Array.isArray(characterData.status) ? characterData.status : [];
        status.forEach((s) => {
            if (!s || typeof s !== 'object') return;
            pushStatus(s.label || s.name, s.value, s.max);
        });

        pushStatus('HP', characterData.hp, characterData.maxHp);
        pushStatus('MP', characterData.mp, characterData.maxMp);

        const states = Array.isArray(characterData.states) ? characterData.states : [];
        states.forEach((s) => {
            if (!s || typeof s !== 'object') return;
            pushStatus(s.name || s.label, s.value, s.max);
        });
        return rows;
    }

    function listCharacterParamRows(characterData) {
        if (Array.isArray(characterData.params)) {
            return characterData.params
                .filter((p) => p && typeof p === 'object')
                .map((p) => ({
                    label: String(p.label || '').trim(),
                    value: p.value,
                }))
                .filter((p) => !!p.label);
        }
        if (characterData.params && typeof characterData.params === 'object') {
            return Object.entries(characterData.params).map(([label, value]) => ({
                label: String(label || '').trim(),
                value,
            })).filter((p) => !!p.label);
        }
        return [];
    }

    function listCharacterCommands(characterData) {
        return String(characterData.commands || '')
            .split('\n')
            .map((x) => x.trim())
            .filter((x) => !!x);
    }

    function listCharacterPassives(characterData) {
        const src = Array.isArray(characterData.SPassive) ? characterData.SPassive : [];
        return src.map((id) => {
            const key = String(id || '').trim();
            if (!key) return null;
            const passive = (global.allPassiveData && global.allPassiveData[key]) ? global.allPassiveData[key] : null;
            const radiance = (global.radianceSkillData && global.radianceSkillData[key]) ? global.radianceSkillData[key] : null;
            const name = String((passive && passive.name) || (radiance && radiance.name) || '').trim();
            return {
                id: key,
                name,
            };
        }).filter((row) => !!row);
    }

    function closePresetDetailModal() {
        const existing = document.getElementById('bo-preset-detail-backdrop');
        if (existing) existing.remove();
    }

    function openPresetDetailModal(record) {
        const rec = (record && typeof record === 'object') ? record : {};
        const charData = extractCharacterData(rec.character_json || {});
        const statusRows = listCharacterStatusRows(charData);
        const paramRows = listCharacterParamRows(charData);
        const commandRows = listCharacterCommands(charData);
        const passiveRows = listCharacterPassives(charData);
        const name = String(charData.name || rec.name || '(名前未設定)').trim();

        const hpRow = statusRows.find((x) => x.label === 'HP') || { value: safeInt(charData.hp, 0), max: safeInt(charData.maxHp, safeInt(charData.hp, 0)) };
        const mpRow = statusRows.find((x) => x.label === 'MP') || { value: safeInt(charData.mp, 0), max: safeInt(charData.maxMp, safeInt(charData.mp, 0)) };
        const fpRow = statusRows.find((x) => x.label === 'FP') || { value: 0, max: 0 };

        closePresetDetailModal();

        const overlay = document.createElement('div');
        overlay.id = 'bo-preset-detail-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'char-detail-modal bo-preset-detail-modal';
        panel.innerHTML = `
            <div class="bo-preset-detail-head">
                <h3 class="bo-preset-detail-title">${escapeHtml(name)}</h3>
                <button class="bo-preset-detail-close" aria-label="閉じる">×</button>
            </div>
            <div class="bo-preset-detail-meta">ID: ${escapeHtml(String(rec.id || ''))} / プリセット: ${escapeHtml(String(rec.name || '-'))}</div>
            <div class="bo-preset-detail-stat-grid">
                <div class="bo-preset-detail-stat">
                    <span class="bo-preset-detail-stat-label">HP</span>
                    <strong class="bo-preset-detail-stat-value">${safeInt(hpRow.value, 0)}<span> / ${safeInt(hpRow.max, safeInt(hpRow.value, 0))}</span></strong>
                </div>
                <div class="bo-preset-detail-stat">
                    <span class="bo-preset-detail-stat-label">MP</span>
                    <strong class="bo-preset-detail-stat-value">${safeInt(mpRow.value, 0)}<span> / ${safeInt(mpRow.max, safeInt(mpRow.value, 0))}</span></strong>
                </div>
                <div class="bo-preset-detail-stat">
                    <span class="bo-preset-detail-stat-label">FP</span>
                    <strong class="bo-preset-detail-stat-value">${safeInt(fpRow.value, 0)}</strong>
                </div>
            </div>

            <section class="bo-preset-detail-section">
                <h4>ステータス</h4>
                <div class="bo-preset-detail-kv-grid">
                    ${statusRows.length
                        ? statusRows.map((s) => `
                            <div class="bo-preset-detail-kv">
                                <span>${escapeHtml(s.label)}</span>
                                <strong>${safeInt(s.value, 0)} / ${safeInt(s.max, safeInt(s.value, 0))}</strong>
                            </div>
                        `).join('')
                        : '<div class="bo-preset-detail-empty">ステータスがありません。</div>'}
                </div>
            </section>

            <section class="bo-preset-detail-section">
                <h4>パラメータ</h4>
                <div class="bo-preset-detail-kv-grid">
                    ${paramRows.length
                        ? paramRows.map((p) => `
                            <div class="bo-preset-detail-kv">
                                <span>${escapeHtml(p.label)}</span>
                                <strong>${escapeHtml(String(p.value ?? ''))}</strong>
                            </div>
                        `).join('')
                        : '<div class="bo-preset-detail-empty">パラメータがありません。</div>'}
                </div>
            </section>

            <section class="bo-preset-detail-section">
                <h4>コマンド</h4>
                ${commandRows.length
                    ? `<ol class="bo-preset-detail-list">${commandRows.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ol>`
                    : '<div class="bo-preset-detail-empty">コマンドがありません。</div>'}
            </section>

            <section class="bo-preset-detail-section">
                <h4>SPassive</h4>
                ${passiveRows.length
                    ? `<ul class="bo-preset-detail-list">${passiveRows.map((x) => `<li>${escapeHtml(x.name ? `${x.name} [${x.id}]` : x.id)}</li>`).join('')}</ul>`
                    : '<div class="bo-preset-detail-empty">SPassiveがありません。</div>'}
            </section>
        `;

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const closeBtn = panel.querySelector('.bo-preset-detail-close');
        closeBtn?.addEventListener('click', closePresetDetailModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closePresetDetailModal();
        });
    }

    function roomCharactersByType(type) {
        const rows = (typeof battleState !== 'undefined' && Array.isArray(battleState.characters))
            ? battleState.characters
            : [];
        const t = String(type || '').trim().toLowerCase();
        return rows.filter((c) => c && typeof c === 'object' && String(c.type || '').trim().toLowerCase() === t);
    }

    function openBattleOnlyCatalogModal(options = {}) {
        const socketRef = getSocketRef();
        if (!socketRef) {
            alert('Socket接続がありません。');
            return;
        }
        const roomName = (options && Object.prototype.hasOwnProperty.call(options, 'room'))
            ? (options.room || '')
            : getRoomNameRef();
        const isGm = String(getCurrentUserAttribute()).toUpperCase() === 'GM';

        if (typeof global.__boCatalogModalCleanup === 'function') {
            try { global.__boCatalogModalCleanup(); } catch (_e) {}
        }

        const existing = document.getElementById('bo-catalog-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-catalog-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--catalog';

        panel.innerHTML = `
            <h3 class="bo-modal-title">キャラクタープリセット編集</h3>
            <div class="bo-modal-lead">
                キャラクターJSON（<code>{"kind":"character","data":...}</code>）をそのまま保存します。<br>
                公開範囲（GMのみ/全員公開）と、味方専用・敵専用を保存時に設定できます。
            </div>
            <div class="bo-toolbar bo-toolbar--between">
                <div class="bo-toolbar-group">
                    <button id="bo-cat-refresh-btn" class="bo-btn bo-btn--sm bo-btn--neutral">再読み込み</button>
                    <button id="bo-cat-clear-btn" class="bo-btn bo-btn--sm bo-btn--neutral">新規入力</button>
                </div>
                <span id="bo-cat-msg" class="bo-inline-msg"></span>
            </div>
            <div class="bo-layout bo-layout--catalog">
                <section class="bo-card">
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">ID（編集時のみ）</span>
                            <input id="bo-cat-id" class="bo-input" placeholder="新規時は空欄" />
                        </label>
                        <label class="bo-field"><span class="bo-field-label">プリセット名</span>
                            <input id="bo-cat-name" class="bo-input" placeholder="例: バグ取りの翁" />
                        </label>
                    </div>
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">公開範囲</span>
                            <select id="bo-cat-visibility" class="bo-select">
                                <option value="public">全員に公開</option>
                                <option value="gm">GMのみ</option>
                            </select>
                        </label>
                        <div class="bo-field">
                            <div class="bo-field-label">用途</div>
                            <div class="bo-check-group">
                                <label class="bo-check-item"><input type="checkbox" id="bo-cat-ally" checked /> 味方専用として利用可</label>
                                <label class="bo-check-item"><input type="checkbox" id="bo-cat-enemy" checked /> 敵専用として利用可</label>
                            </div>
                        </div>
                    </div>
                    <label class="bo-field"><span class="bo-field-label">キャラクターJSON（無変換で保存）</span>
                        <textarea id="bo-cat-json" class="bo-textarea bo-textarea--mono" placeholder='{"kind":"character","data":{...}}'></textarea>
                    </label>
                    <div class="bo-toolbar bo-toolbar--between">
                        <button id="bo-cat-validate-btn" class="bo-btn bo-btn--sm bo-btn--neutral">JSON検証</button>
                        <div class="bo-toolbar-group">
                            <button id="bo-cat-save-btn" class="bo-btn bo-btn--sm bo-btn--success">保存</button>
                            <button id="bo-cat-delete-btn" class="bo-btn bo-btn--sm bo-btn--danger">削除</button>
                        </div>
                    </div>
                    <div id="bo-cat-preview" class="bo-preview-box">JSON検証で内容を表示します。</div>

                    <section id="bo-cat-room-import-section" class="bo-subcard">
                        <div class="bo-subcard-title">現在ルームのキャラから取込（任意）</div>
                        <div id="bo-cat-room-import-note" class="bo-subcard-note">ルーム外（ロビー）では使えません。</div>
                        <div class="bo-field-grid bo-field-grid--import">
                            <label class="bo-field"><span class="bo-field-label">対象</span>
                                <select id="bo-cat-room-type" class="bo-select">
                                    <option value="ally">味方</option>
                                    <option value="enemy">敵</option>
                                </select>
                            </label>
                            <label class="bo-field"><span class="bo-field-label">キャラ</span>
                                <select id="bo-cat-room-char" class="bo-select"></select>
                            </label>
                            <label class="bo-field"><span class="bo-field-label">取込形式</span>
                                <select id="bo-cat-room-snapshot" class="bo-select">
                                    <option value="current">現在値で保存</option>
                                    <option value="initial">初期値で保存</option>
                                </select>
                            </label>
                            <button id="bo-cat-room-import-btn" class="bo-btn bo-btn--sm bo-btn--neutral">取込</button>
                        </div>
                    </section>
                </section>
                <section class="bo-card">
                    <div class="bo-toolbar bo-toolbar--compact bo-toolbar--wrap">
                        <input id="bo-cat-search" class="bo-input" style="min-width:220px; flex:1 1 260px;" placeholder="ID / 名前で検索" />
                        <select id="bo-cat-sort" class="bo-select bo-select--compact" style="min-width:160px;">
                            <option value="name_asc">名前 昇順</option>
                            <option value="name_desc">名前 降順</option>
                            <option value="id_asc">ID 昇順</option>
                            <option value="id_desc">ID 降順</option>
                            <option value="updated_desc">更新順（新しい順）</option>
                            <option value="updated_asc">更新順（古い順）</option>
                        </select>
                        <select id="bo-cat-filter" class="bo-select bo-select--fill">
                            <option value="all">すべて</option>
                            <option value="ally">味方利用可</option>
                            <option value="enemy">敵利用可</option>
                            <option value="public">全員公開</option>
                            <option value="gm">GMのみ</option>
                        </select>
                    </div>
                    <div id="bo-cat-list" class="bo-list-box bo-list-box--tall"></div>
                    <section class="bo-subcard" style="margin-top:12px;">
                        <div class="bo-subcard-title">編成プリセット管理</div>
                        <div id="bo-cat-formation-hub-summary" class="bo-subcard-note">敵:0件 / 味方:0件 / ステージ:0件</div>
                        <div class="bo-subcard-note">敵編成・味方編成・ステージの編集とJSON入出力は専用画面で行います。</div>
                        <button id="bo-cat-open-formation-hub-btn" class="bo-btn bo-btn--sm bo-btn--primary">編成プリセット管理を開く</button>
                    </section>
                </section>
            </div>
            <div class="bo-footer-actions">
                <button id="bo-cat-close-btn" class="bo-btn bo-btn--neutral">閉じる</button>
            </div>
        `;

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-cat-msg');
        const idInput = panel.querySelector('#bo-cat-id');
        const nameInput = panel.querySelector('#bo-cat-name');
        const visibilitySelect = panel.querySelector('#bo-cat-visibility');
        const allyCheck = panel.querySelector('#bo-cat-ally');
        const enemyCheck = panel.querySelector('#bo-cat-enemy');
        const jsonInput = panel.querySelector('#bo-cat-json');
        const previewEl = panel.querySelector('#bo-cat-preview');
        const listEl = panel.querySelector('#bo-cat-list');
        const filterEl = panel.querySelector('#bo-cat-filter');
        const searchEl = panel.querySelector('#bo-cat-search');
        const sortEl = panel.querySelector('#bo-cat-sort');
        const formationHubSummaryEl = panel.querySelector('#bo-cat-formation-hub-summary');
        const openFormationHubBtn = panel.querySelector('#bo-cat-open-formation-hub-btn');
        const formIdInput = panel.querySelector('#bo-form-id');
        const formNameInput = panel.querySelector('#bo-form-name');
        const formVisibilitySelect = panel.querySelector('#bo-form-visibility');
        const formRecommendedInput = panel.querySelector('#bo-form-recommended');
        const formMembersEl = panel.querySelector('#bo-form-members');
        const formListEl = panel.querySelector('#bo-form-list');

        const state = {
            presets: {},
            sorted_ids: [],
            enemy_formations: {},
            sorted_enemy_formation_ids: [],
            ally_formations: {},
            sorted_ally_formation_ids: [],
            stage_presets: {},
            sorted_stage_preset_ids: [],
            selected_id: null,
            selected_formation_id: null,
            formation_members: [],
            can_manage: isGm,
        };

        const listeners = [];
        function onSocket(eventName, fn) {
            socketRef.on(eventName, fn);
            listeners.push([eventName, fn]);
        }

        function setMsg(text, color) {
            if (!msgEl) return;
            msgEl.textContent = text || '';
            msgEl.style.color = color || '#666';
        }

        function setEditorEnabled(enabled) {
            [idInput, nameInput, visibilitySelect, allyCheck, enemyCheck, jsonInput,
             panel.querySelector('#bo-cat-save-btn'), panel.querySelector('#bo-cat-delete-btn'),
             panel.querySelector('#bo-cat-validate-btn'), panel.querySelector('#bo-cat-room-type'),
             panel.querySelector('#bo-cat-room-char'), panel.querySelector('#bo-cat-room-snapshot'),
             panel.querySelector('#bo-cat-room-import-btn'),
             formIdInput, formNameInput, formVisibilitySelect, formRecommendedInput,
             panel.querySelector('#bo-form-add-member-btn'),
             panel.querySelector('#bo-form-save-btn'),
             panel.querySelector('#bo-form-delete-btn')]
                .forEach((el) => {
                    if (!el) return;
                    el.disabled = !enabled;
                    el.style.opacity = enabled ? '1' : '0.7';
                });
            if (!enabled) {
                setMsg('この画面は閲覧専用です。保存・編集はGMのみ可能です。', '#6b7280');
            }
        }

        function renderPreview(characterJson) {
            if (!previewEl) return;
            const summary = summarizeCharacterJson(characterJson);
            previewEl.innerHTML = `
                <div><strong>名前:</strong> ${escapeHtml(summary.name)}</div>
                <div><strong>HP:</strong> ${escapeHtml(summary.hp)} / <strong>MP:</strong> ${escapeHtml(summary.mp)}</div>
                <div><strong>status件数:</strong> ${summary.statusCount} / <strong>コマンド行数:</strong> ${summary.commandCount}</div>
                <div><strong>SPassive件数:</strong> ${summary.passiveCount}</div>
            `;
        }

        function listFilteredIds() {
            const filterKey = String(filterEl?.value || 'all');
            const searchKey = String(searchEl?.value || '').trim().toLowerCase();
            const sortKey = String(sortEl?.value || 'name_asc').trim().toLowerCase();
            const ids = (Array.isArray(state.sorted_ids) && state.sorted_ids.length)
                ? state.sorted_ids.slice()
                : Object.keys(state.presets).sort();
            const filtered = ids.filter((id) => {
                const rec = state.presets[id] || {};
                if (filterKey === 'ally') return !!rec.allow_ally;
                if (filterKey === 'enemy') return !!rec.allow_enemy;
                if (filterKey === 'public') return String(rec.visibility || 'public') === 'public';
                if (filterKey === 'gm') return String(rec.visibility || 'public') === 'gm';
                return true;
            }).filter((id) => {
                if (!searchKey) return true;
                const rec = state.presets[id] || {};
                const idText = String(id || '').toLowerCase();
                const nameText = String(rec.name || '').toLowerCase();
                return idText.includes(searchKey) || nameText.includes(searchKey);
            });
            const getName = (id) => String((state.presets[id] || {}).name || '').toLowerCase();
            const getUpdated = (id) => safeInt((state.presets[id] || {}).updated_at, 0);
            filtered.sort((a, b) => {
                if (sortKey === 'name_desc') return getName(b).localeCompare(getName(a)) || String(b).localeCompare(String(a));
                if (sortKey === 'id_asc') return String(a).localeCompare(String(b));
                if (sortKey === 'id_desc') return String(b).localeCompare(String(a));
                if (sortKey === 'updated_desc') return getUpdated(b) - getUpdated(a) || String(a).localeCompare(String(b));
                if (sortKey === 'updated_asc') return getUpdated(a) - getUpdated(b) || String(a).localeCompare(String(b));
                return getName(a).localeCompare(getName(b)) || String(a).localeCompare(String(b));
            });
            return filtered;
        }

        function loadRecordToEditor(recId) {
            const rec = state.presets[recId];
            if (!rec || typeof rec !== 'object') return;
            state.selected_id = recId;
            idInput.value = String(rec.id || recId);
            nameInput.value = String(rec.name || '');
            visibilitySelect.value = String(rec.visibility || 'public');
            allyCheck.checked = !!rec.allow_ally;
            enemyCheck.checked = !!rec.allow_enemy;
            jsonInput.value = JSON.stringify(rec.character_json || {}, null, 2);
            renderPreview(rec.character_json || {});
            renderList();
        }

        function clearEditor() {
            state.selected_id = null;
            idInput.value = '';
            nameInput.value = '';
            visibilitySelect.value = 'public';
            allyCheck.checked = true;
            enemyCheck.checked = true;
            jsonInput.value = '';
            previewEl.textContent = 'JSON検証で内容を表示します。';
            renderList();
        }

        function renderList() {
            const ids = listFilteredIds();
            listEl.innerHTML = '';
            if (!ids.length) {
                listEl.innerHTML = '<div class="bo-empty">該当プリセットがありません。</div>';
                return;
            }
            ids.forEach((id) => {
                const rec = state.presets[id] || {};
                const row = document.createElement('div');
                row.className = `bo-list-row${state.selected_id === id ? ' is-selected' : ''}`;

                const usage = [];
                if (rec.allow_ally) usage.push('味方');
                if (rec.allow_enemy) usage.push('敵');
                const vis = String(rec.visibility || 'public') === 'gm' ? 'GMのみ' : '全員公開';

                row.innerHTML = `
                    <div class="bo-list-main bo-cat-detail-trigger" data-id="${escapeHtml(id)}" role="button" tabindex="0" aria-label="プリセット詳細を表示">
                        <div class="bo-list-name">${escapeHtml(rec.name || '(名前未設定)')}</div>
                        <div class="bo-list-meta">[${escapeHtml(id)}] / ${escapeHtml(vis)} / ${escapeHtml(usage.join('・') || '用途未設定')}</div>
                    </div>
                    <div class="bo-list-actions">
                        <button class="bo-cat-detail-btn bo-btn bo-btn--xs bo-btn--neutral" data-id="${escapeHtml(id)}">詳細</button>
                        <button class="bo-cat-load-btn bo-btn bo-btn--xs bo-btn--neutral" data-id="${escapeHtml(id)}">読込</button>
                    </div>
                `;
                listEl.appendChild(row);
            });

            listEl.querySelectorAll('.bo-cat-load-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = String(btn.getAttribute('data-id') || '').trim();
                    loadRecordToEditor(id);
                });
            });
            listEl.querySelectorAll('.bo-cat-detail-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = String(btn.getAttribute('data-id') || '').trim();
                    if (!id || !state.presets[id]) return;
                    openPresetDetailModal(state.presets[id]);
                });
            });
            listEl.querySelectorAll('.bo-cat-detail-trigger').forEach((el) => {
                el.addEventListener('click', () => {
                    const id = String(el.getAttribute('data-id') || '').trim();
                    if (!id || !state.presets[id]) return;
                    openPresetDetailModal(state.presets[id]);
                });
                el.addEventListener('keydown', (e) => {
                    if (e.key !== 'Enter' && e.key !== ' ') return;
                    e.preventDefault();
                    const id = String(el.getAttribute('data-id') || '').trim();
                    if (!id || !state.presets[id]) return;
                    openPresetDetailModal(state.presets[id]);
                });
            });
        }

        function renderFormationHubSummary() {
            if (!formationHubSummaryEl) return;
            const enemyCount = (Array.isArray(state.sorted_enemy_formation_ids) && state.sorted_enemy_formation_ids.length)
                ? state.sorted_enemy_formation_ids.length
                : Object.keys(state.enemy_formations || {}).length;
            const allyCount = (Array.isArray(state.sorted_ally_formation_ids) && state.sorted_ally_formation_ids.length)
                ? state.sorted_ally_formation_ids.length
                : Object.keys(state.ally_formations || {}).length;
            const stageCount = (Array.isArray(state.sorted_stage_preset_ids) && state.sorted_stage_preset_ids.length)
                ? state.sorted_stage_preset_ids.length
                : Object.keys(state.stage_presets || {}).length;
            formationHubSummaryEl.textContent = `敵:${enemyCount}件 / 味方:${allyCount}件 / ステージ:${stageCount}件`;
        }

        function enemyPresetIds() {
            const ids = (Array.isArray(state.sorted_ids) && state.sorted_ids.length)
                ? state.sorted_ids.slice()
                : Object.keys(state.presets).sort();
            return ids.filter((id) => {
                const rec = state.presets[id] || {};
                return !!rec.allow_enemy;
            });
        }

        function buildEnemyPresetOptions(selectedId) {
            const ids = enemyPresetIds();
            const rows = ids.map((id) => {
                const rec = state.presets[id] || {};
                const selected = (String(selectedId || '') === id) ? 'selected' : '';
                return `<option value="${escapeHtml(id)}" ${selected}>${escapeHtml(rec.name || id)} [${escapeHtml(id)}]</option>`;
            }).join('');
            return `<option value="">（敵プリセット）</option>${rows}`;
        }

        function ensureFormationMembers() {
            if (!Array.isArray(state.formation_members)) state.formation_members = [];
        }

        function renderFormationMembers() {
            ensureFormationMembers();
            if (!formMembersEl) return;
            const rows = state.formation_members.map((row, idx) => `
                <div class="bo-subcard" data-idx="${idx}" style="margin:8px 0; padding:10px;">
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">敵プリセット</span>
                            <select class="bo-form-member-preset bo-select">
                                ${buildEnemyPresetOptions(row && row.preset_id)}
                            </select>
                        </label>
                        <label class="bo-field"><span class="bo-field-label">体数</span>
                            <input class="bo-form-member-count bo-input" type="number" min="1" value="${Math.max(1, safeInt(row && row.count, 1))}" />
                        </label>
                    </div>
                    <label class="bo-field"><span class="bo-field-label">行動チャート上書きJSON（任意）</span>
                        <textarea class="bo-form-member-behavior bo-textarea bo-textarea--compact bo-textarea--mono" placeholder='{"enabled":true,"initial_loop_id":"loop_1","loops":{...}}'>${escapeHtml(JSON.stringify((row && row.behavior_profile_override) || {}, null, 2))}</textarea>
                    </label>
                    <div class="bo-toolbar bo-toolbar--between">
                        <div class="bo-toolbar-group">
                            <span class="bo-subcard-note">未入力または <code>{}</code> の場合は上書きなし。</span>
                            <button class="bo-form-member-behavior-flow bo-btn bo-btn--xs bo-btn--primary">フロー編集</button>
                            <button class="bo-form-member-behavior-template bo-btn bo-btn--xs bo-btn--neutral">テンプレート</button>
                            <button class="bo-form-member-behavior-format bo-btn bo-btn--xs bo-btn--neutral">整形</button>
                            <button class="bo-form-member-behavior-clear bo-btn bo-btn--xs bo-btn--neutral">クリア</button>
                        </div>
                        <button class="bo-form-member-del bo-btn bo-btn--xs bo-btn--neutral">削除</button>
                    </div>
                </div>
            `).join('');
            formMembersEl.innerHTML = rows || '<div class="bo-empty">敵メンバーが未設定です。</div>';

            formMembersEl.querySelectorAll('.bo-form-member-del').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const idx = safeInt(card && card.getAttribute('data-idx'), -1);
                    if (idx < 0) return;
                    state.formation_members.splice(idx, 1);
                    renderFormationMembers();
                });
            });
            formMembersEl.querySelectorAll('.bo-form-member-behavior-flow').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const presetSelect = card?.querySelector('.bo-form-member-preset');
                    const area = card?.querySelector('.bo-form-member-behavior');
                    const presetId = String(presetSelect?.value || '').trim();
                    if (!presetId) {
                        setMsg('先に敵プリセットを選択してください。', 'red');
                        return;
                    }
                    const preset = state.presets[presetId];
                    if (!preset || typeof preset !== 'object') {
                        setMsg(`敵プリセットが見つかりません: ${presetId}`, 'red');
                        return;
                    }
                    let currentProfile = {};
                    const text = String(area?.value || '').trim();
                    if (text && text !== '{}') {
                        try {
                            const parsed = JSON.parse(text);
                            if (parsed && typeof parsed === 'object') currentProfile = parsed;
                        } catch (_e) {
                            currentProfile = {};
                        }
                    }
                    const editorChar = buildBehaviorEditorCharForPreset(preset, currentProfile);
                    if (typeof global.openBehaviorFlowEditorModal !== 'function') {
                        setMsg('行動チャート編集UIを読み込めませんでした。', 'red');
                        return;
                    }
                    const rowIndex = Math.max(0, safeInt(card && card.getAttribute('data-idx'), -1));
                    const selectedFormationId = String(state.selected_formation_id || '').trim();
                    const selectedFormation = (selectedFormationId && state.enemy_formations && state.enemy_formations[selectedFormationId])
                        ? state.enemy_formations[selectedFormationId]
                        : null;
                    const formationName = String(
                        (formNameInput && formNameInput.value) ||
                        (selectedFormation && selectedFormation.name) ||
                        selectedFormationId ||
                        '未保存の敵編成'
                    ).trim();
                    global.openBehaviorFlowEditorModal(editorChar, {
                        title: '敵行動チャート上書き編集',
                        subtitle: `敵編成プリセット内の「${String(preset.name || presetId)}」にだけ適用されます。`,
                        contextRows: [
                            `編成: ${formationName}`,
                            `敵行: #${rowIndex + 1}`,
                            `敵プリセット: ${String(preset.name || presetId)}`,
                        ],
                        saveLabel: 'この敵に反映',
                        onSave: (normalizedProfile) => {
                            if (rowIndex >= 0 && Array.isArray(state.formation_members) && state.formation_members[rowIndex]) {
                                state.formation_members[rowIndex].behavior_profile_override = (normalizedProfile && typeof normalizedProfile === 'object')
                                    ? normalizedProfile
                                    : {};
                            }
                            if (area) {
                                area.value = JSON.stringify(normalizedProfile || {}, null, 2);
                            }
                            setMsg('行動チャート上書きを反映しました。', 'green');
                            renderFormationMembers();
                            return true;
                        },
                    });
                });
            });
            formMembersEl.querySelectorAll('.bo-form-member-behavior-template').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const area = card?.querySelector('.bo-form-member-behavior');
                    if (!area) return;
                    area.value = JSON.stringify(getBehaviorProfileTemplate(), null, 2);
                    setMsg('行動チャートのテンプレートを挿入しました。', 'green');
                });
            });
            formMembersEl.querySelectorAll('.bo-form-member-behavior-format').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const area = card?.querySelector('.bo-form-member-behavior');
                    if (!area) return;
                    const text = String(area.value || '').trim();
                    if (!text) return;
                    try {
                        const parsed = JSON.parse(text);
                        if (!parsed || typeof parsed !== 'object') {
                            setMsg('行動チャートJSONはオブジェクト形式で入力してください。', 'red');
                            return;
                        }
                        area.value = JSON.stringify(parsed, null, 2);
                        setMsg('行動チャートJSONを整形しました。', 'green');
                    } catch (e) {
                        setMsg(`行動チャートJSON解析に失敗しました: ${e.message}`, 'red');
                    }
                });
            });
            formMembersEl.querySelectorAll('.bo-form-member-behavior-clear').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const area = card?.querySelector('.bo-form-member-behavior');
                    if (!area) return;
                    area.value = '{}';
                    setMsg('行動チャート上書きをクリアしました。', '#444');
                });
            });
        }

        function collectFormationMembersFromEditor() {
            const cards = Array.from(formMembersEl?.querySelectorAll('[data-idx]') || []);
            const members = [];
            for (const card of cards) {
                const presetId = String(card.querySelector('.bo-form-member-preset')?.value || '').trim();
                const count = Math.max(0, safeInt(card.querySelector('.bo-form-member-count')?.value, 0));
                const behaviorText = String(card.querySelector('.bo-form-member-behavior')?.value || '').trim();
                if (!presetId || count <= 0) continue;
                let behaviorProfileOverride = {};
                if (behaviorText && behaviorText !== '{}') {
                    try {
                        const parsed = JSON.parse(behaviorText);
                        if (parsed && typeof parsed === 'object') {
                            behaviorProfileOverride = parsed;
                        } else {
                            setMsg(`敵メンバー(${presetId})の行動チャートJSONが不正です。`, 'red');
                            return null;
                        }
                    } catch (e) {
                        setMsg(`敵メンバー(${presetId})の行動チャートJSON解析に失敗しました: ${e.message}`, 'red');
                        return null;
                    }
                }
                members.push({
                    preset_id: presetId,
                    count,
                    behavior_profile_override: behaviorProfileOverride,
                });
            }
            return members;
        }

        function clearFormationEditor() {
            state.selected_formation_id = null;
            if (formIdInput) formIdInput.value = '';
            if (formNameInput) formNameInput.value = '';
            if (formVisibilitySelect) formVisibilitySelect.value = 'public';
            if (formRecommendedInput) formRecommendedInput.value = '0';
            state.formation_members = [];
            renderFormationMembers();
            renderFormationList();
        }

        function loadFormationToEditor(formationId) {
            const rec = state.enemy_formations[formationId];
            if (!rec || typeof rec !== 'object') return;
            state.selected_formation_id = formationId;
            if (formIdInput) formIdInput.value = String(rec.id || formationId);
            if (formNameInput) formNameInput.value = String(rec.name || '');
            if (formVisibilitySelect) formVisibilitySelect.value = String(rec.visibility || 'public');
            if (formRecommendedInput) formRecommendedInput.value = String(Math.max(0, safeInt(rec.recommended_ally_count, 0)));
            state.formation_members = (Array.isArray(rec.members) ? rec.members : []).map((row) => ({
                preset_id: String((row && row.preset_id) || '').trim(),
                count: Math.max(1, safeInt(row && row.count, 1)),
                behavior_profile_override: (row && typeof row.behavior_profile_override === 'object') ? row.behavior_profile_override : {},
            }));
            renderFormationMembers();
            renderFormationList();
        }

        function renderFormationList() {
            if (!formListEl) return;
            const ids = (Array.isArray(state.sorted_enemy_formation_ids) && state.sorted_enemy_formation_ids.length)
                ? state.sorted_enemy_formation_ids.slice()
                : Object.keys(state.enemy_formations || {}).sort();
            formListEl.innerHTML = '';
            if (!ids.length) {
                formListEl.innerHTML = '<div class="bo-empty">敵編成プリセットがありません。</div>';
                return;
            }
            ids.forEach((id) => {
                const rec = state.enemy_formations[id] || {};
                const vis = String(rec.visibility || 'public') === 'gm' ? 'GMのみ' : '全員公開';
                const memberCount = Array.isArray(rec.members) ? rec.members.length : 0;
                const row = document.createElement('div');
                row.className = `bo-list-row${state.selected_formation_id === id ? ' is-selected' : ''}`;
                row.innerHTML = `
                    <div class="bo-list-main">
                        <div class="bo-list-name">${escapeHtml(rec.name || '(名前未設定)')}</div>
                        <div class="bo-list-meta">[${escapeHtml(id)}] / ${escapeHtml(vis)} / 推奨味方:${Math.max(0, safeInt(rec.recommended_ally_count, 0))} / 敵種:${memberCount}</div>
                    </div>
                    <div class="bo-list-actions">
                        <button class="bo-form-load-btn bo-btn bo-btn--xs bo-btn--neutral" data-id="${escapeHtml(id)}">読込</button>
                    </div>
                `;
                formListEl.appendChild(row);
            });
            formListEl.querySelectorAll('.bo-form-load-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = String(btn.getAttribute('data-id') || '').trim();
                    loadFormationToEditor(id);
                });
            });
        }

        function refreshCatalog() {
            socketRef.emit('request_bo_catalog_list', {});
        }

        function updateRoomCharOptions() {
            const typeEl = panel.querySelector('#bo-cat-room-type');
            const selectEl = panel.querySelector('#bo-cat-room-char');
            const snapshotEl = panel.querySelector('#bo-cat-room-snapshot');
            const importBtn = panel.querySelector('#bo-cat-room-import-btn');
            const sectionEl = panel.querySelector('#bo-cat-room-import-section');
            const noteEl = panel.querySelector('#bo-cat-room-import-note');
            if (!typeEl || !selectEl || !importBtn) return;

            const hasRoom = !!String(roomName || '').trim();
            if (!hasRoom) {
                selectEl.innerHTML = '<option value="">（ルーム外では利用不可）</option>';
                typeEl.disabled = true;
                if (snapshotEl) snapshotEl.disabled = true;
                importBtn.disabled = true;
                if (sectionEl) sectionEl.style.opacity = '0.72';
                if (noteEl) noteEl.textContent = '現在はロビー表示中のため、この取込機能は利用できません。JSON貼り付けで保存してください。';
                return;
            }
            typeEl.disabled = false;
            if (snapshotEl) snapshotEl.disabled = false;
            if (sectionEl) sectionEl.style.opacity = '';
            if (noteEl) noteEl.textContent = '現在ルームのキャラクターを、現在値または初期値で取り込めます。';

            const type = String(typeEl.value || 'ally');
            const rows = roomCharactersByType(type);
            const opts = rows.map((c, i) => `<option value="${i}">${escapeHtml(String(c.name || '名前不明'))} [${i + 1}]</option>`).join('');
            selectEl.innerHTML = opts ? opts : '<option value="">（該当キャラなし）</option>';
            importBtn.disabled = !opts;
        }

        panel.querySelector('#bo-cat-refresh-btn')?.addEventListener('click', refreshCatalog);
        panel.querySelector('#bo-cat-clear-btn')?.addEventListener('click', clearEditor);
        openFormationHubBtn?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyFormationHubModal !== 'function') {
                setMsg('編成プリセット管理モーダルを読み込めませんでした。', 'red');
                return;
            }
            global.openBattleOnlyFormationHubModal({
                room: roomName || null,
                presets: state.presets,
                sorted_ids: state.sorted_ids,
                enemy_formations: state.enemy_formations,
                sorted_enemy_formation_ids: state.sorted_enemy_formation_ids,
                ally_formations: state.ally_formations,
                sorted_ally_formation_ids: state.sorted_ally_formation_ids,
                stage_presets: state.stage_presets,
                sorted_stage_preset_ids: state.sorted_stage_preset_ids,
                can_manage: state.can_manage,
            });
        });
        panel.querySelector('#bo-cat-validate-btn')?.addEventListener('click', () => {
            const parsed = parseCharacterJsonText(jsonInput.value);
            if (!parsed.ok) {
                setMsg(parsed.message, 'red');
                return;
            }
            renderPreview(parsed.parsed);
            setMsg('JSONは有効です。', 'green');
        });

        panel.querySelector('#bo-cat-save-btn')?.addEventListener('click', () => {
            const parsed = parseCharacterJsonText(jsonInput.value);
            if (!parsed.ok) {
                setMsg(parsed.message, 'red');
                return;
            }
            const name = String(nameInput.value || '').trim();
            if (!name) {
                setMsg('プリセット名は必須です。', 'red');
                return;
            }
            const payload = {
                id: String(idInput.value || '').trim() || undefined,
                name,
                visibility: String(visibilitySelect.value || 'public'),
                allow_ally: !!allyCheck.checked,
                allow_enemy: !!enemyCheck.checked,
                character_json: parsed.parsed,
            };
            socketRef.emit('request_bo_preset_save', { payload, overwrite: true });
            setMsg('保存を送信しました。', '#444');
        });

        panel.querySelector('#bo-cat-delete-btn')?.addEventListener('click', () => {
            const id = String(idInput.value || '').trim();
            if (!id) {
                setMsg('削除するにはIDが必要です。一覧から読込してください。', 'red');
                return;
            }
            if (!confirm(`プリセット ${id} を削除しますか？`)) return;
            socketRef.emit('request_bo_preset_delete', { id });
            setMsg('削除を送信しました。', '#444');
        });

        panel.querySelector('#bo-cat-room-type')?.addEventListener('change', updateRoomCharOptions);
        panel.querySelector('#bo-cat-room-import-btn')?.addEventListener('click', () => {
            const type = String(panel.querySelector('#bo-cat-room-type')?.value || 'ally');
            const idx = safeInt(panel.querySelector('#bo-cat-room-char')?.value, -1);
            const mode = String(panel.querySelector('#bo-cat-room-snapshot')?.value || 'current');
            const rows = roomCharactersByType(type);
            if (idx < 0 || !rows[idx]) {
                setMsg('取込対象キャラを選択してください。', 'red');
                return;
            }
            const converted = buildCharacterJsonFromRoomChar(rows[idx], mode);
            jsonInput.value = JSON.stringify(converted, null, 2);
            if (!nameInput.value.trim()) nameInput.value = String(rows[idx].name || '').trim();
            renderPreview(converted);
            setMsg(`ルームキャラを${mode === 'initial' ? '初期値' : '現在値'}で取込みました。`, 'green');
        });
        panel.querySelector('#bo-form-add-member-btn')?.addEventListener('click', () => {
            ensureFormationMembers();
            state.formation_members.push({ preset_id: '', count: 1, behavior_profile_override: {} });
            renderFormationMembers();
        });
        panel.querySelector('#bo-form-save-btn')?.addEventListener('click', () => {
            const name = String(formNameInput?.value || '').trim();
            if (!name) {
                setMsg('敵編成名は必須です。', 'red');
                return;
            }
            const members = collectFormationMembersFromEditor();
            if (!members) return;
            if (!members.length) {
                setMsg('敵編成メンバーを1件以上設定してください。', 'red');
                return;
            }
            const payload = {
                id: String(formIdInput?.value || '').trim() || undefined,
                name,
                visibility: String(formVisibilitySelect?.value || 'public'),
                recommended_ally_count: Math.max(0, safeInt(formRecommendedInput?.value, 0)),
                members,
            };
            socketRef.emit('request_bo_enemy_formation_save', { payload, overwrite: true });
            setMsg('敵編成の保存を送信しました。', '#444');
        });
        panel.querySelector('#bo-form-delete-btn')?.addEventListener('click', () => {
            const id = String(formIdInput?.value || '').trim();
            if (!id) {
                setMsg('削除するには敵編成IDが必要です。一覧から読込してください。', 'red');
                return;
            }
            if (!confirm(`敵編成 ${id} を削除しますか？`)) return;
            socketRef.emit('request_bo_enemy_formation_delete', { id });
            setMsg('敵編成の削除を送信しました。', '#444');
        });

        filterEl?.addEventListener('change', renderList);
        sortEl?.addEventListener('change', renderList);
        searchEl?.addEventListener('input', renderList);

        onSocket('receive_bo_catalog_list', (data) => {
            state.presets = (data && typeof data.presets === 'object') ? data.presets : {};
            state.sorted_ids = (data && Array.isArray(data.sorted_ids)) ? data.sorted_ids : Object.keys(state.presets).sort();
            state.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            state.sorted_enemy_formation_ids = (data && Array.isArray(data.sorted_enemy_formation_ids))
                ? data.sorted_enemy_formation_ids
                : Object.keys(state.enemy_formations).sort();
            state.ally_formations = (data && typeof data.ally_formations === 'object') ? data.ally_formations : {};
            state.sorted_ally_formation_ids = (data && Array.isArray(data.sorted_ally_formation_ids))
                ? data.sorted_ally_formation_ids
                : Object.keys(state.ally_formations).sort();
            state.stage_presets = (data && typeof data.stage_presets === 'object') ? data.stage_presets : {};
            state.sorted_stage_preset_ids = (data && Array.isArray(data.sorted_stage_preset_ids))
                ? data.sorted_stage_preset_ids
                : Object.keys(state.stage_presets).sort();
            state.can_manage = !!(data && data.can_manage);
            renderList();
            renderFormationHubSummary();
            renderFormationList();
            renderFormationMembers();
            setEditorEnabled(state.can_manage);
            setMsg('プリセット一覧を更新しました。', 'green');
        });

        onSocket('bo_preset_saved', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || data.id || '').trim();
                if (id) {
                    state.presets[id] = rec;
                    if (!state.sorted_ids.includes(id)) state.sorted_ids.push(id);
                    state.sorted_ids.sort();
                    loadRecordToEditor(id);
                }
            }
            renderList();
            setMsg('保存しました。', 'green');
            refreshCatalog();
        });

        onSocket('bo_preset_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (id && state.presets[id]) delete state.presets[id];
            state.sorted_ids = state.sorted_ids.filter((x) => x !== id);
            if (state.selected_id === id) clearEditor();
            renderList();
            setMsg('削除しました。', 'green');
            refreshCatalog();
        });
        onSocket('bo_enemy_formation_saved', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || data.id || '').trim();
                if (id) {
                    state.enemy_formations[id] = rec;
                    if (!state.sorted_enemy_formation_ids.includes(id)) state.sorted_enemy_formation_ids.push(id);
                    state.sorted_enemy_formation_ids.sort();
                    loadFormationToEditor(id);
                }
            }
            renderFormationList();
            renderFormationHubSummary();
            setMsg('敵編成を保存しました。', 'green');
            refreshCatalog();
        });
        onSocket('bo_enemy_formation_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (id && state.enemy_formations[id]) delete state.enemy_formations[id];
            state.sorted_enemy_formation_ids = state.sorted_enemy_formation_ids.filter((x) => x !== id);
            if (state.selected_formation_id === id) clearFormationEditor();
            renderFormationList();
            renderFormationHubSummary();
            setMsg('敵編成を削除しました。', 'green');
            refreshCatalog();
        });
        onSocket('bo_ally_formation_saved', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || data.id || '').trim();
                if (id) {
                    state.ally_formations[id] = rec;
                    if (!state.sorted_ally_formation_ids.includes(id)) state.sorted_ally_formation_ids.push(id);
                    state.sorted_ally_formation_ids.sort();
                }
            }
            renderFormationHubSummary();
            setMsg('味方編成を保存しました。', 'green');
            refreshCatalog();
        });
        onSocket('bo_ally_formation_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (id && state.ally_formations[id]) delete state.ally_formations[id];
            state.sorted_ally_formation_ids = state.sorted_ally_formation_ids.filter((x) => x !== id);
            renderFormationHubSummary();
            setMsg('味方編成を削除しました。', 'green');
            refreshCatalog();
        });
        onSocket('bo_stage_preset_saved', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || data.id || '').trim();
                if (id) {
                    state.stage_presets[id] = rec;
                    if (!state.sorted_stage_preset_ids.includes(id)) state.sorted_stage_preset_ids.push(id);
                    state.sorted_stage_preset_ids.sort();
                }
            }
            renderFormationHubSummary();
            setMsg('ステージを保存しました。', 'green');
            refreshCatalog();
        });
        onSocket('bo_stage_preset_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (id && state.stage_presets[id]) delete state.stage_presets[id];
            state.sorted_stage_preset_ids = state.sorted_stage_preset_ids.filter((x) => x !== id);
            renderFormationHubSummary();
            setMsg('ステージを削除しました。', 'green');
            refreshCatalog();
        });
        ['bo_preset_error', 'bo_catalog_error', 'bo_enemy_formation_error', 'bo_ally_formation_error', 'bo_stage_preset_error'].forEach((eventName) => {
            onSocket(eventName, (data) => {
                const msg = String((data && data.message) || '操作に失敗しました。');
                setMsg(msg, 'red');
            });
        });

        function closeModal() {
            closePresetDetailModal();
            while (listeners.length) {
                const [eventName, fn] = listeners.pop();
                socketRef.off(eventName, fn);
            }
            overlay.remove();
            if (global.__boCatalogModalCleanup === closeModal) {
                global.__boCatalogModalCleanup = null;
            }
        }
        global.__boCatalogModalCleanup = closeModal;
        panel.querySelector('#bo-cat-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        clearEditor();
        clearFormationEditor();
        renderFormationHubSummary();
        updateRoomCharOptions();
        setEditorEnabled(isGm);
        refreshCatalog();
    }

    global.BattleOnlyCatalogModal = {
        open: openBattleOnlyCatalogModal,
    };
    global.openBattleOnlyCatalogModal = openBattleOnlyCatalogModal;
    global.openBattleOnlyPresetDetailModal = openPresetDetailModal;
    global.closeBattleOnlyPresetDetailModal = closePresetDetailModal;
})(window);
