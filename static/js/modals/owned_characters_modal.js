(function initOwnedCharactersModal(global) {
    'use strict';

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

    function fetchJson(url, options) {
        if (typeof global.fetchWithSession === 'function') {
            return global.fetchWithSession(url, options);
        }
        return fetch(url, Object.assign({ credentials: 'include' }, options || {}));
    }

    function openCharaCreator(ownedId) {
        const url = ownedId ? `/chara_creator?owned_id=${encodeURIComponent(ownedId)}` : '/chara_creator';
        window.open(url, '_blank');
    }

    // 通常スキル/輝化スキルのマスターデータ。ロビー読み込み時に main.js がグローバルへ
    // 格納する（window.allSkillData/window.radianceSkillData）が、未取得のタイミングで
    // モーダルを開いた場合に備えて自前でも一度だけ取得する。
    let _skillDataPromise = null;
    function ensureSkillData() {
        if (global.allSkillData && Object.keys(global.allSkillData).length > 0) {
            return Promise.resolve(global.allSkillData);
        }
        if (!_skillDataPromise) {
            _skillDataPromise = fetchJson('/api/get_skill_data')
                .then((r) => r.json())
                .then((data) => { global.allSkillData = data || {}; return global.allSkillData; })
                .catch(() => { global.allSkillData = global.allSkillData || {}; return global.allSkillData; });
        }
        return _skillDataPromise;
    }

    let _radianceDataPromise = null;
    function ensureRadianceData() {
        if (global.radianceSkillData && Object.keys(global.radianceSkillData).length > 0) {
            return Promise.resolve(global.radianceSkillData);
        }
        if (!_radianceDataPromise) {
            _radianceDataPromise = fetchJson('/api/get_radiance_data')
                .then((r) => r.json())
                .then((data) => { global.radianceSkillData = data || {}; return global.radianceSkillData; })
                .catch(() => { global.radianceSkillData = global.radianceSkillData || {}; return global.radianceSkillData; });
        }
        return _radianceDataPromise;
    }

    // 戦闘スキルのIDプレフィックス（CharaCreatorのシートタブ区分と同じ並び）からカテゴリを判定する。
    const _SKILL_CATEGORY_ORDER = ['B', 'C', 'D', 'E', 'Ps', 'Pb', 'Pp', 'Ms', 'Mb', 'Mp'];
    function skillCategoryOf(skillId) {
        const m = /^([A-Za-z]+)-/.exec(String(skillId || ''));
        return m ? m[1] : '他';
    }

    // キャラ名から決定的に色を選ぶ（アバター用）。見た目だけの要素なのでハッシュは単純でよい。
    const AVATAR_PALETTE = [
        '#6366f1', '#0ea5e9', '#16a34a', '#ea580c', '#db2777',
        '#7c3aed', '#0d9488', '#ca8a04', '#e11d48', '#2563eb',
    ];
    function avatarColorFor(name) {
        const str = String(name || '?');
        let hash = 0;
        for (let i = 0; i < str.length; i += 1) hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
        return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
    }

    async function openOwnedCharactersModal() {
        const existing = document.getElementById('owned-chars-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'owned-chars-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content owned-chars-modal-content';

        panel.innerHTML = `
            <div class="owned-chars-modal">
                <div class="owned-chars-banner">
                    <div>
                        <h3>🧑‍🎨 マイキャラクター</h3>
                        <div class="owned-chars-banner-sub">保存・成長・ルームへの投入をここから行えます</div>
                    </div>
                    <button id="owned-chars-new-btn" class="bo-btn bo-btn--sm bo-btn--accent">＋ 新規作成</button>
                </div>
                <div class="owned-chars-body">
                    <div class="owned-chars-layout">
                        <div id="owned-chars-list" class="owned-chars-list">
                            <div style="color:#666;">読み込み中...</div>
                        </div>
                        <div class="owned-chars-sidebar">
                            <div class="owned-chars-section owned-chars-section--import">
                                <div class="owned-chars-section-title">📋 JSONから追加</div>
                                <textarea id="owned-chars-import-text" rows="5" style="width:100%; box-sizing:border-box; font-family:inherit;"
                                    placeholder='キャラ作成ツールの出力JSON（{"kind":"character","data":{...}}）を貼り付け'></textarea>
                                <div style="margin-top:8px;">
                                    <button id="owned-chars-import-btn" class="bo-btn bo-btn--sm">保存</button>
                                </div>
                                <div id="owned-chars-import-msg" style="margin-top:6px; font-size:0.85em;"></div>
                            </div>
                            <div class="owned-chars-section owned-chars-section--tips">
                                💡 「編集」からキャラ作成ツールを開くと、残り経験値がツール側の上限表示に自動で反映されます。ルームへはキャラ追加ウィザードの「持ちキャラから選ぶ」で投入できます。
                            </div>
                        </div>
                    </div>
                </div>
                <div class="bo-actions-end" style="margin:16px 26px 0;">
                    <button id="owned-chars-close-btn" class="bo-btn bo-btn--sm bo-btn--neutral">閉じる</button>
                </div>
            </div>
        `;

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const listEl = panel.querySelector('#owned-chars-list');
        const importText = panel.querySelector('#owned-chars-import-text');
        const importBtn = panel.querySelector('#owned-chars-import-btn');
        const importMsg = panel.querySelector('#owned-chars-import-msg');

        panel.querySelector('#owned-chars-new-btn')?.addEventListener('click', () => openCharaCreator());

        async function loadList() {
            listEl.innerHTML = '<div style="color:#666;">読み込み中...</div>';
            try {
                const resp = await fetchJson('/api/owned_characters');
                if (!resp.ok) throw new Error('一覧の取得に失敗しました。');
                const body = await resp.json();
                renderList(Array.isArray(body.characters) ? body.characters : []);
            } catch (err) {
                listEl.innerHTML = `<div style="color:#b91c1c;">${escapeHtml(err.message || String(err))}</div>`;
            }
        }

        function renderList(characters) {
            if (!characters.length) {
                listEl.innerHTML = `
                    <div class="owned-chars-empty">
                        <div style="font-size:2.4rem; margin-bottom:8px;">🗡️</div>
                        <div style="margin-bottom:14px;">持ちキャラはまだありません。</div>
                        <button id="owned-chars-empty-new-btn" class="bo-btn bo-btn--sm bo-btn--accent">＋ 最初のキャラクターを作成</button>
                    </div>
                `;
                listEl.querySelector('#owned-chars-empty-new-btn')?.addEventListener('click', () => openCharaCreator());
                return;
            }
            listEl.innerHTML = characters.map((c) => {
                const updated = c.updated_at ? new Date(c.updated_at).toLocaleString() : '-';
                const remaining = Number.isFinite(c.remaining_exp) ? c.remaining_exp : (c.exp_total ?? 0);
                const radianceRemaining = Number.isFinite(c.radiance_remaining) ? c.radiance_remaining : 0;
                const initial = escapeHtml(String(c.name || '?').trim().charAt(0) || '?');
                const avatarColor = avatarColorFor(c.name);
                return `
                    <div class="owned-chars-card" style="border-left-color:${avatarColor};" data-id="${escapeHtml(c.id)}">
                        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
                            <div style="display:flex; align-items:center; gap:10px; min-width:0;">
                                <div class="owned-chars-avatar" style="background:${avatarColor};">${initial}</div>
                                <div style="min-width:0;">
                                    <div style="font-weight:700; font-size:1.02rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(c.name)}</div>
                                    <div style="font-size:0.8em; color:#666;">残り経験値 <strong style="color:#166534;">${escapeHtml(remaining)}</strong> ・ 残り通過点 <strong style="color:#7c3aed;">${escapeHtml(radianceRemaining)}</strong> ・ 更新 ${escapeHtml(updated)}</div>
                                </div>
                            </div>
                            <div style="flex:0 0 auto; display:flex; gap:6px;">
                                <button class="owned-chars-icon-btn owned-chars-icon-btn--growth owned-chars-growth-btn" data-id="${escapeHtml(c.id)}" title="成長（輝化スキル・戦闘スキルの習得）">🌱</button>
                                <button class="owned-chars-icon-btn owned-chars-icon-btn--edit owned-chars-edit-btn" data-id="${escapeHtml(c.id)}" title="キャラ作成ツールで編集">📝</button>
                                <button class="owned-chars-icon-btn owned-chars-icon-btn--export owned-chars-export-btn" data-id="${escapeHtml(c.id)}" title="JSONを出力">📤</button>
                                <button class="owned-chars-icon-btn owned-chars-icon-btn--delete owned-chars-delete-btn" data-id="${escapeHtml(c.id)}" title="削除">🗑️</button>
                            </div>
                        </div>
                        <div class="owned-chars-growth-panel" data-id="${escapeHtml(c.id)}" data-remaining-exp="${remaining}" data-remaining-radiance="${radianceRemaining}" style="display:none; margin-top:10px; padding:12px; background:#f0fdf4; border-radius:8px; border:1px solid #bbf7d0;">
                            <div style="font-size:0.8em; color:#166534; margin-bottom:8px;">
                                通過点・シナリオ経験を使って、輝化スキルや新たな戦闘スキルを習得できます。
                            </div>
                            <div style="display:flex; gap:6px; margin-bottom:8px; flex-wrap:wrap;">
                                <select class="owned-chars-growth-type" style="padding:4px;">
                                    <option value="normal">⚔️ 戦闘スキル</option>
                                    <option value="radiance">✨ 輝化スキル</option>
                                </select>
                                <select class="owned-chars-growth-category" style="padding:4px;"></select>
                                <select class="owned-chars-growth-skill-select" style="flex:1; min-width:160px; padding:4px;">
                                    <option value="">-- スキルを選択 --</option>
                                </select>
                                <button type="button" class="bo-btn bo-btn--xs owned-chars-growth-add-pending-btn">＋ 予定に追加</button>
                            </div>
                            <div class="owned-chars-growth-preview" style="background:#fff; border:1px solid #d1fae5; border-radius:6px; padding:8px; margin-bottom:8px; font-size:0.82em; line-height:1.6; color:#333;">
                                スキルを選択すると、ここに効果とコストが表示されます。
                            </div>
                            <div class="owned-chars-growth-pending" style="margin-bottom:8px; font-size:0.82em;">
                                <span style="color:#666;">習得予定のスキルはまだありません。</span>
                            </div>
                            <div class="owned-chars-growth-budget" style="font-size:0.82em; color:#166534; margin-bottom:8px;">
                                消費予定 経験値: 0 / 残り ${remaining} ・ 消費予定 通過点: 0 / 残り ${radianceRemaining}
                            </div>
                            <button class="bo-btn bo-btn--sm owned-chars-growth-apply-btn" data-id="${escapeHtml(c.id)}">成長を適用</button>
                            <span class="owned-chars-growth-msg" style="margin-left:8px; font-size:0.85em;"></span>
                        </div>
                    </div>
                `;
            }).join('');

            listEl.querySelectorAll('.owned-chars-growth-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = btn.getAttribute('data-id');
                    const panelEl = listEl.querySelector(`.owned-chars-growth-panel[data-id="${CSS.escape(id)}"]`);
                    if (!panelEl) return;
                    const willOpen = panelEl.style.display === 'none';
                    panelEl.style.display = willOpen ? 'block' : 'none';
                    if (willOpen && !panelEl.dataset.initialized) {
                        panelEl.dataset.initialized = '1';
                        initGrowthPicker(panelEl);
                    }
                });
            });

            // 成長パネル: 種別/カテゴリ変更でスキルselectを再構築する。
            function populateSkillSelect(panelEl) {
                const type = panelEl.querySelector('.owned-chars-growth-type').value;
                const categorySelect = panelEl.querySelector('.owned-chars-growth-category');
                const skillSelect = panelEl.querySelector('.owned-chars-growth-skill-select');
                const pending = panelEl._pending || { skills: [], radiance: [] };

                if (type === 'radiance') {
                    categorySelect.style.display = 'none';
                    const radianceData = global.radianceSkillData || {};
                    const entries = Object.values(radianceData).filter((s) => s && s.id);
                    entries.sort((a, b) => String(a.id).localeCompare(String(b.id)));
                    skillSelect.innerHTML = '<option value="">-- スキルを選択 --</option>' + entries
                        .filter((s) => !pending.radiance.includes(s.id))
                        .map((s) => `<option value="${escapeHtml(s.id)}">[${escapeHtml(s.id)}] ${escapeHtml(s.name)}（コスト:${escapeHtml(s.cost ?? 0)}）</option>`)
                        .join('');
                } else {
                    categorySelect.style.display = '';
                    const skillData = global.allSkillData || {};
                    const currentCategory = categorySelect.value || 'ALL';
                    const entries = Object.entries(skillData).map(([id, s]) => ({ id, ...s }));
                    if (!categorySelect.dataset.built) {
                        categorySelect.dataset.built = '1';
                        const present = new Set(entries.map((s) => skillCategoryOf(s.id)));
                        const categories = _SKILL_CATEGORY_ORDER.filter((cat) => present.has(cat))
                            .concat(Array.from(present).filter((cat) => !_SKILL_CATEGORY_ORDER.includes(cat)).sort());
                        categorySelect.innerHTML = '<option value="ALL">全カテゴリ</option>' + categories
                            .map((cat) => `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`).join('');
                    }
                    const filtered = entries.filter((s) => currentCategory === 'ALL' || skillCategoryOf(s.id) === currentCategory);
                    filtered.sort((a, b) => String(a.id).localeCompare(String(b.id)));
                    skillSelect.innerHTML = '<option value="">-- スキルを選択 --</option>' + filtered
                        .filter((s) => !pending.skills.includes(s.id))
                        .map((s) => `<option value="${escapeHtml(s.id)}">[${escapeHtml(s.id)}] ${escapeHtml(s['デフォルト名称'] || '')}（コスト:${escapeHtml(s['取得コスト'] ?? 0)}）</option>`)
                        .join('');
                }
                renderPreview(panelEl);
            }

            function renderPreview(panelEl) {
                const type = panelEl.querySelector('.owned-chars-growth-type').value;
                const skillId = panelEl.querySelector('.owned-chars-growth-skill-select').value;
                const previewEl = panelEl.querySelector('.owned-chars-growth-preview');
                if (!skillId) {
                    previewEl.innerHTML = 'スキルを選択すると、ここに効果とコストが表示されます。';
                    return;
                }
                if (type === 'radiance') {
                    const s = (global.radianceSkillData || {})[skillId];
                    if (!s) { previewEl.innerHTML = ''; return; }
                    previewEl.innerHTML = `
                        <div style="font-weight:700; margin-bottom:4px;">✨ ${escapeHtml(s.name)}（ID: ${escapeHtml(s.id)}）</div>
                        <div>コスト（通過点）: ${escapeHtml(s.cost ?? 0)}</div>
                        <div>効果: ${escapeHtml(s.description || '(記載なし)')}</div>
                        ${s.flavor ? `<div style="color:#666; font-style:italic;">${escapeHtml(s.flavor)}</div>` : ''}
                    `;
                } else {
                    const s = (global.allSkillData || {})[skillId];
                    if (!s) { previewEl.innerHTML = ''; return; }
                    previewEl.innerHTML = `
                        <div style="font-weight:700; margin-bottom:4px;">⚔️ ${escapeHtml(s['デフォルト名称'] || skillId)}（ID: ${escapeHtml(skillId)}）</div>
                        <div>分類/距離/属性: ${escapeHtml(s['分類'] || '-')} / ${escapeHtml(s['距離'] || '-')} / ${escapeHtml(s['属性'] || '-')}</div>
                        <div>コスト（経験値）: ${escapeHtml(s['取得コスト'] ?? 0)}</div>
                        ${s['使用時効果'] ? `<div>使用時効果: ${escapeHtml(s['使用時効果'])}</div>` : ''}
                        ${s['特記'] ? `<div>特記: ${escapeHtml(s['特記'])}</div>` : ''}
                        ${s['発動時効果'] ? `<div>発動時効果: ${escapeHtml(s['発動時効果'])}</div>` : ''}
                    `;
                }
            }

            function renderPending(panelEl) {
                const pending = panelEl._pending || { skills: [], radiance: [] };
                const pendingEl = panelEl.querySelector('.owned-chars-growth-pending');
                const budgetEl = panelEl.querySelector('.owned-chars-growth-budget');
                const remainingExp = parseInt(panelEl.getAttribute('data-remaining-exp'), 10) || 0;
                const remainingRadiance = parseInt(panelEl.getAttribute('data-remaining-radiance'), 10) || 0;

                const skillData = global.allSkillData || {};
                const radianceData = global.radianceSkillData || {};

                const skillCost = pending.skills.reduce((sum, id) => sum + (parseInt((skillData[id] || {})['取得コスト'], 10) || 0), 0);
                const radianceCost = pending.radiance.reduce((sum, id) => sum + (parseInt((radianceData[id] || {}).cost, 10) || 0), 0);

                const chips = [];
                pending.skills.forEach((id) => {
                    const name = (skillData[id] || {})['デフォルト名称'] || id;
                    chips.push(`<span class="owned-chars-growth-chip" data-kind="skill" data-id="${escapeHtml(id)}" style="display:inline-flex; align-items:center; gap:4px; background:#dbeafe; color:#1e40af; border-radius:12px; padding:3px 8px; margin:2px; font-size:0.85em;">⚔️ ${escapeHtml(name)}<button type="button" data-kind="skill" data-id="${escapeHtml(id)}" class="owned-chars-growth-chip-remove" style="border:none; background:none; cursor:pointer; color:inherit; font-weight:700;">×</button></span>`);
                });
                pending.radiance.forEach((id) => {
                    const name = (radianceData[id] || {}).name || id;
                    chips.push(`<span class="owned-chars-growth-chip" data-kind="radiance" data-id="${escapeHtml(id)}" style="display:inline-flex; align-items:center; gap:4px; background:#ede9fe; color:#5b21b6; border-radius:12px; padding:3px 8px; margin:2px; font-size:0.85em;">✨ ${escapeHtml(name)}<button type="button" data-kind="radiance" data-id="${escapeHtml(id)}" class="owned-chars-growth-chip-remove" style="border:none; background:none; cursor:pointer; color:inherit; font-weight:700;">×</button></span>`);
                });

                pendingEl.innerHTML = chips.length
                    ? chips.join('')
                    : '<span style="color:#666;">習得予定のスキルはまだありません。</span>';

                pendingEl.querySelectorAll('.owned-chars-growth-chip-remove').forEach((btn) => {
                    btn.addEventListener('click', () => {
                        const kind = btn.getAttribute('data-kind');
                        const id = btn.getAttribute('data-id');
                        if (kind === 'skill') {
                            panelEl._pending.skills = panelEl._pending.skills.filter((x) => x !== id);
                        } else {
                            panelEl._pending.radiance = panelEl._pending.radiance.filter((x) => x !== id);
                        }
                        populateSkillSelect(panelEl);
                        renderPending(panelEl);
                    });
                });

                const expColor = skillCost > remainingExp ? '#b91c1c' : '#166534';
                const radianceColor = radianceCost > remainingRadiance ? '#b91c1c' : '#166534';
                budgetEl.innerHTML = `消費予定 経験値: <strong style="color:${expColor};">${skillCost}</strong> / 残り ${remainingExp} ・ 消費予定 通過点: <strong style="color:${radianceColor};">${radianceCost}</strong> / 残り ${remainingRadiance}`;
            }

            async function initGrowthPicker(panelEl) {
                panelEl._pending = { skills: [], radiance: [] };
                await Promise.all([ensureSkillData(), ensureRadianceData()]);
                populateSkillSelect(panelEl);
                renderPending(panelEl);

                panelEl.querySelector('.owned-chars-growth-type').addEventListener('change', () => populateSkillSelect(panelEl));
                panelEl.querySelector('.owned-chars-growth-category').addEventListener('change', () => populateSkillSelect(panelEl));
                panelEl.querySelector('.owned-chars-growth-skill-select').addEventListener('change', () => renderPreview(panelEl));
                panelEl.querySelector('.owned-chars-growth-add-pending-btn').addEventListener('click', () => {
                    const type = panelEl.querySelector('.owned-chars-growth-type').value;
                    const skillSelect = panelEl.querySelector('.owned-chars-growth-skill-select');
                    const skillId = skillSelect.value;
                    if (!skillId) return;
                    if (type === 'radiance') {
                        panelEl._pending.radiance.push(skillId);
                    } else {
                        panelEl._pending.skills.push(skillId);
                    }
                    populateSkillSelect(panelEl);
                    renderPending(panelEl);
                });
            }

            listEl.querySelectorAll('.owned-chars-growth-apply-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const id = btn.getAttribute('data-id');
                    const panelEl = listEl.querySelector(`.owned-chars-growth-panel[data-id="${CSS.escape(id)}"]`);
                    const msgEl = panelEl.querySelector('.owned-chars-growth-msg');
                    const pending = panelEl._pending || { skills: [], radiance: [] };

                    if (!pending.skills.length && !pending.radiance.length) {
                        msgEl.textContent = '習得するスキルを1つ以上選んで「＋ 予定に追加」してください。';
                        msgEl.style.color = '#b91c1c';
                        return;
                    }

                    try {
                        const resp = await fetchJson(`/api/owned_characters/${encodeURIComponent(id)}/growth`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ add_skill_ids: pending.skills, add_radiance_ids: pending.radiance }),
                        });
                        const body = await resp.json().catch(() => ({}));
                        if (!resp.ok) throw new Error(body.error || '成長に失敗しました。');
                        msgEl.textContent = '成長を適用しました。';
                        msgEl.style.color = '#15803d';
                        await loadList();
                    } catch (err) {
                        msgEl.textContent = err.message || String(err);
                        msgEl.style.color = '#b91c1c';
                    }
                });
            });

            listEl.querySelectorAll('.owned-chars-edit-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = btn.getAttribute('data-id');
                    if (!id) return;
                    openCharaCreator(id);
                });
            });

            listEl.querySelectorAll('.owned-chars-delete-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const id = btn.getAttribute('data-id');
                    if (!id) return;
                    const confirmFn = (typeof global.showAppConfirm === 'function')
                        ? global.showAppConfirm
                        : async (msg) => window.confirm(msg);
                    const ok = await confirmFn('この持ちキャラを削除しますか？');
                    if (!ok) return;
                    try {
                        const resp = await fetchJson(`/api/owned_characters/${encodeURIComponent(id)}`, { method: 'DELETE' });
                        if (!resp.ok) throw new Error('削除に失敗しました。');
                        await loadList();
                    } catch (err) {
                        alert(err.message || String(err));
                    }
                });
            });

            listEl.querySelectorAll('.owned-chars-export-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const id = btn.getAttribute('data-id');
                    const character = characters.find((c) => c.id === id);
                    if (!character) return;
                    const blob = new Blob(
                        [JSON.stringify({ kind: 'character', data: character.data }, null, 2)],
                        { type: 'application/json' },
                    );
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${character.name || 'character'}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                });
            });
        }

        importBtn.addEventListener('click', async () => {
            const text = importText.value.trim();
            if (!text) {
                importMsg.textContent = 'JSONを貼り付けてください。';
                importMsg.style.color = '#b91c1c';
                return;
            }
            let payload;
            try {
                payload = JSON.parse(text);
            } catch (err) {
                importMsg.textContent = `JSONの形式が正しくありません: ${err.message}`;
                importMsg.style.color = '#b91c1c';
                return;
            }
            try {
                const resp = await fetchJson('/api/owned_characters', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const body = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(body.error || '保存に失敗しました。');
                importMsg.textContent = '保存しました。';
                importMsg.style.color = '#15803d';
                importText.value = '';
                await loadList();
            } catch (err) {
                importMsg.textContent = err.message || String(err);
                importMsg.style.color = '#b91c1c';
            }
        });

        function closeModal() {
            overlay.remove();
        }
        panel.querySelector('#owned-chars-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        await loadList();
    }

    global.OwnedCharactersModal = {
        open: openOwnedCharactersModal,
    };
    global.openOwnedCharactersModal = openOwnedCharactersModal;
})(window);
