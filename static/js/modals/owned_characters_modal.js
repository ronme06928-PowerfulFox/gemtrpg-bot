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

    // キャラ名から決定的に色を選ぶ（アバター用）。見た目だけの要素なのでハッシュは単純でよい。
    const AVATAR_PALETTE = ['#6366f1', '#0ea5e9', '#16a34a', '#ea580c', '#db2777', '#7c3aed', '#0d9488', '#ca8a04'];
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
        panel.className = 'modal-content';
        panel.style.maxWidth = '640px';

        panel.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <h3 style="margin:0;">🧑‍🎨 マイキャラクター</h3>
                <button id="owned-chars-new-btn" class="bo-btn bo-btn--sm bo-btn--accent">＋ 新規作成</button>
            </div>
            <div id="owned-chars-list" style="max-height:360px; overflow-y:auto; margin-bottom:14px;">
                <div style="color:#666;">読み込み中...</div>
            </div>
            <div class="bo-subcard">
                <div class="bo-subcard-title">📋 JSONから追加</div>
                <textarea id="owned-chars-import-text" rows="3" style="width:100%; box-sizing:border-box; font-family:inherit;"
                    placeholder='キャラ作成ツールの出力JSON（{"kind":"character","data":{...}}）を貼り付け'></textarea>
                <div style="margin-top:6px;">
                    <button id="owned-chars-import-btn" class="bo-btn bo-btn--sm">保存</button>
                    <span id="owned-chars-import-msg" style="margin-left:8px; font-size:0.85em;"></span>
                </div>
            </div>
            <div class="bo-actions-end" style="margin-top:14px;">
                <button id="owned-chars-close-btn" class="bo-btn bo-btn--sm bo-btn--neutral">閉じる</button>
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
                    <div style="text-align:center; padding:28px 12px; color:#666;">
                        <div style="font-size:2rem; margin-bottom:8px;">🗡️</div>
                        <div style="margin-bottom:12px;">持ちキャラはまだありません。</div>
                        <button id="owned-chars-empty-new-btn" class="bo-btn bo-btn--sm bo-btn--accent">＋ 最初のキャラクターを作成</button>
                    </div>
                `;
                listEl.querySelector('#owned-chars-empty-new-btn')?.addEventListener('click', () => openCharaCreator());
                return;
            }
            listEl.innerHTML = characters.map((c) => {
                const updated = c.updated_at ? new Date(c.updated_at).toLocaleString() : '-';
                const remaining = Number.isFinite(c.remaining_exp) ? c.remaining_exp : (c.exp_total ?? 0);
                const initial = escapeHtml(String(c.name || '?').trim().charAt(0) || '?');
                const avatarColor = avatarColorFor(c.name);
                return `
                    <div class="bo-card" style="margin-bottom:8px;" data-id="${escapeHtml(c.id)}">
                        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
                            <div style="display:flex; align-items:center; gap:10px; min-width:0;">
                                <div style="flex:0 0 auto; width:36px; height:36px; border-radius:50%; background:${avatarColor};
                                    color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700;">${initial}</div>
                                <div style="min-width:0;">
                                    <div style="font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(c.name)}</div>
                                    <div style="font-size:0.78em; color:#666;">残り経験値 <strong>${escapeHtml(remaining)}</strong> / 累計 ${escapeHtml(c.exp_total ?? 0)} ・ 更新 ${escapeHtml(updated)}</div>
                                </div>
                            </div>
                            <div style="flex:0 0 auto; display:flex; gap:4px;">
                                <button class="bo-btn bo-btn--xs bo-btn--neutral owned-chars-growth-btn" data-id="${escapeHtml(c.id)}" title="成長（スキル追加・パラメータ上昇）">🌱</button>
                                <button class="bo-btn bo-btn--xs bo-btn--neutral owned-chars-edit-btn" data-id="${escapeHtml(c.id)}" title="キャラ作成ツールで編集">📝</button>
                                <button class="bo-btn bo-btn--xs bo-btn--neutral owned-chars-export-btn" data-id="${escapeHtml(c.id)}" title="JSONを出力">📤</button>
                                <button class="bo-btn bo-btn--xs owned-chars-delete-btn" data-id="${escapeHtml(c.id)}" title="削除">🗑️</button>
                            </div>
                        </div>
                        <div class="owned-chars-growth-panel" data-id="${escapeHtml(c.id)}" style="display:none; margin-top:8px; padding:8px; background:#f0fdf4; border-radius:4px; border:1px solid #bbf7d0;">
                            <div style="font-size:0.8em; color:#166534; margin-bottom:4px;">残り経験値: <span class="owned-chars-growth-remaining">${escapeHtml(remaining)}</span></div>
                            <label style="display:block; font-size:0.8em; color:#166534; margin-bottom:2px;">追加するスキルID（カンマ区切り）</label>
                            <input type="text" class="owned-chars-growth-skills" placeholder="例: B-05, Ps-03" style="width:100%; box-sizing:border-box; padding:4px; border:1px solid #bbf7d0; border-radius:4px; margin-bottom:6px;">
                            <label style="display:block; font-size:0.8em; color:#166534; margin-bottom:2px;">パラメータ上昇（例: 筋力:1, 生命力:1）</label>
                            <input type="text" class="owned-chars-growth-params" placeholder="ラベル:上昇量, ..." style="width:100%; box-sizing:border-box; padding:4px; border:1px solid #bbf7d0; border-radius:4px; margin-bottom:6px;">
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
                    if (panelEl) panelEl.style.display = (panelEl.style.display === 'none') ? 'block' : 'none';
                });
            });

            listEl.querySelectorAll('.owned-chars-growth-apply-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const id = btn.getAttribute('data-id');
                    const panelEl = listEl.querySelector(`.owned-chars-growth-panel[data-id="${CSS.escape(id)}"]`);
                    const skillsInput = panelEl.querySelector('.owned-chars-growth-skills');
                    const paramsInput = panelEl.querySelector('.owned-chars-growth-params');
                    const msgEl = panelEl.querySelector('.owned-chars-growth-msg');

                    const addSkillIds = (skillsInput.value || '').split(',').map((s) => s.trim()).filter(Boolean);
                    const paramIncreases = {};
                    (paramsInput.value || '').split(',').forEach((entry) => {
                        const [label, rawDelta] = entry.split(':').map((s) => (s || '').trim());
                        const delta = parseInt(rawDelta, 10) || 0;
                        if (label && delta > 0) paramIncreases[label] = delta;
                    });

                    if (!addSkillIds.length && !Object.keys(paramIncreases).length) {
                        msgEl.textContent = 'スキルIDかパラメータ上昇のどちらかを入力してください。';
                        msgEl.style.color = '#b91c1c';
                        return;
                    }

                    try {
                        const resp = await fetchJson(`/api/owned_characters/${encodeURIComponent(id)}/growth`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ add_skill_ids: addSkillIds, param_increases: paramIncreases }),
                        });
                        const body = await resp.json().catch(() => ({}));
                        if (!resp.ok) throw new Error(body.error || '成長に失敗しました。');
                        msgEl.textContent = '成長を適用しました。';
                        msgEl.style.color = '#15803d';
                        skillsInput.value = '';
                        paramsInput.value = '';
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
