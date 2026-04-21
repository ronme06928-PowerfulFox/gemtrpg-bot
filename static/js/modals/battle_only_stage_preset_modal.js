(function (global) {
    'use strict';

    const RULE_TYPES = [
        { value: 'SPEED_ROLL_MOD', label: '速度ロール補正' },
        { value: 'DAMAGE_DEALT_MOD', label: '与ダメージ補正' },
        { value: 'APPLY_STATE_ON_CONDITION', label: '条件付き状態異常付与' },
    ];
    const SCOPES = [
        { value: 'ALL', label: '全員' },
        { value: 'ALLY', label: '味方のみ' },
        { value: 'ENEMY', label: '敵のみ' },
    ];
    const OPS = [
        { value: 'GTE', label: '以上' }, { value: 'GT', label: 'より大きい' },
        { value: 'LTE', label: '以下' }, { value: 'LT', label: 'より小さい' },
        { value: 'EQ', label: '等しい' }, { value: 'NE', label: '等しくない' },
    ];

    const socketRef = () => ((typeof socket !== 'undefined' && socket) ? socket : (global.socket || null));
    const roomRef = () => ((typeof currentRoomName !== 'undefined' && currentRoomName) ? currentRoomName : (global.currentRoomName || ''));
    const isGm = () => String((typeof currentUserAttribute !== 'undefined' ? currentUserAttribute : global.currentUserAttribute) || 'Player').toUpperCase() === 'GM';
    const i = (v, d = 0) => { const n = Number.parseInt(v, 10); return Number.isFinite(n) ? n : d; };
    const h = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const c = (v) => JSON.parse(JSON.stringify(v));

    function openBattleOnlyStagePresetModal(options = {}) {
        const s = socketRef();
        if (!s) return alert('Socket接続がありません。');
        if (typeof global.__boStagePresetModalCleanup === 'function') { try { global.__boStagePresetModalCleanup(); } catch (_e) {} }
        document.getElementById('bo-stage-backdrop')?.remove();

        const state = {
            enemy_formations: (options.enemy_formations && typeof options.enemy_formations === 'object') ? c(options.enemy_formations) : {},
            sorted_enemy_formation_ids: Array.isArray(options.sorted_enemy_formation_ids) ? options.sorted_enemy_formation_ids.slice() : [],
            ally_formations: (options.ally_formations && typeof options.ally_formations === 'object') ? c(options.ally_formations) : {},
            sorted_ally_formation_ids: Array.isArray(options.sorted_ally_formation_ids) ? options.sorted_ally_formation_ids.slice() : [],
            stage_presets: (options.stage_presets && typeof options.stage_presets === 'object') ? c(options.stage_presets) : {},
            sorted_stage_preset_ids: Array.isArray(options.sorted_stage_preset_ids) ? options.sorted_stage_preset_ids.slice() : [],
            selected_stage_id: null,
            can_manage: (typeof options.can_manage === 'boolean') ? options.can_manage : isGm(),
        };

        const overlay = document.createElement('div');
        overlay.id = 'bo-stage-backdrop';
        overlay.className = 'modal-backdrop';
        overlay.innerHTML = `
<div class="modal-content bo-modal bo-modal--enemy-formation">
  <h3 class="bo-modal-title">ステージプリセット管理</h3>
  <div class="bo-modal-lead">敵編成・味方編成・ステージ効果をまとめて管理します。</div>
  <div class="bo-toolbar bo-toolbar--between"><div class="bo-toolbar-group">
    <button id="bo-sp-refresh-btn" class="bo-btn bo-btn--sm bo-btn--neutral">再読み込み</button>
    <button id="bo-sp-clear-btn" class="bo-btn bo-btn--sm bo-btn--neutral">新規作成</button>
    <button id="bo-sp-open-catalog-btn" class="bo-btn bo-btn--sm bo-btn--neutral">編成管理を開く</button>
    <button id="bo-sp-import-btn" class="bo-btn bo-btn--sm bo-btn--neutral">JSON読込</button>
    <button id="bo-sp-export-current-btn" class="bo-btn bo-btn--sm bo-btn--neutral">このステージJSON</button>
    <input id="bo-sp-import-file" type="file" accept=".json,application/json" style="display:none;" />
  </div><span id="bo-sp-msg" class="bo-inline-msg"></span></div>
  <div class="bo-layout bo-layout--catalog">
    <section class="bo-card">
      <div class="bo-field-grid bo-field-grid--2">
        <label class="bo-field"><span class="bo-field-label">ステージID（保存時のみ）</span><input id="bo-sp-id" class="bo-input" placeholder="新規時は空欄" /></label>
        <label class="bo-field"><span class="bo-field-label">ステージ名</span><input id="bo-sp-name" class="bo-input" /></label>
      </div>
      <div class="bo-field-grid bo-field-grid--2">
        <label class="bo-field"><span class="bo-field-label">敵編成</span><select id="bo-sp-enemy" class="bo-select"></select></label>
        <label class="bo-field"><span class="bo-field-label">味方編成（任意）</span><select id="bo-sp-ally" class="bo-select"></select></label>
      </div>
      <div class="bo-field-grid bo-field-grid--4">
        <label class="bo-field"><span class="bo-field-label">必要味方人数</span><input id="bo-sp-required" class="bo-input" type="number" min="0" value="0" /></label>
        <label class="bo-field"><span class="bo-field-label">公開範囲</span><select id="bo-sp-visibility" class="bo-select"><option value="public">全体公開</option><option value="gm">GMのみ</option></select></label>
        <label class="bo-field"><span class="bo-field-label">表示順</span><input id="bo-sp-sort-key" class="bo-input" type="number" min="0" value="0" /></label>
        <label class="bo-field"><span class="bo-field-label">タグ（カンマ区切り）</span><input id="bo-sp-tags" class="bo-input" /></label>
      </div>
      <label class="bo-field"><span class="bo-field-label">コンセプト</span><input id="bo-sp-concept" class="bo-input" /></label>
      <label class="bo-field"><span class="bo-field-label">説明文</span><textarea id="bo-sp-description" class="bo-textarea bo-textarea--compact"></textarea></label>
      <div class="bo-field"><div class="bo-field-label">ステージ効果（かんたん設定）</div>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
          <button id="bo-sp-add-rule-btn" class="bo-btn bo-btn--xs bo-btn--neutral" type="button">効果ルールを追加</button>
          <span style="font-size:12px;color:#666;">ルール単位で折りたたみ可能</span>
        </div>
        <div id="bo-sp-rules-list" style="display:flex;flex-direction:column;gap:8px;"></div>
      </div>
      <div class="bo-field"><div class="bo-field-label">ステージアバター（表示用）</div>
        <div class="bo-field-grid bo-field-grid--2">
          <label class="bo-field"><span class="bo-field-label">有効</span><select id="bo-sp-avatar-enabled" class="bo-select"><option value="true">有効</option><option value="false">無効</option></select></label>
          <label class="bo-field"><span class="bo-field-label">アイコン文字</span><input id="bo-sp-avatar-icon" class="bo-input" /></label>
        </div>
        <div class="bo-field-grid bo-field-grid--2">
          <label class="bo-field"><span class="bo-field-label">アバター名</span><input id="bo-sp-avatar-name" class="bo-input" /></label>
          <label class="bo-field"><span class="bo-field-label">説明</span><input id="bo-sp-avatar-description" class="bo-input" /></label>
        </div>
      </div>
      <details class="bo-field"><summary class="bo-field-label" style="cursor:pointer;">上級者向けJSON編集</summary>
        <label class="bo-field"><span class="bo-field-label">フィールド効果（JSON）</span><textarea id="bo-sp-field-effects-json" class="bo-textarea bo-textarea--compact"></textarea></label>
        <label class="bo-field"><span class="bo-field-label">ステージアバター（JSON）</span><textarea id="bo-sp-stage-avatar-json" class="bo-textarea bo-textarea--compact"></textarea></label>
      </details>
      <div class="bo-toolbar bo-toolbar--between"><button id="bo-sp-export-btn" class="bo-btn bo-btn--sm bo-btn--neutral">全ステージJSONダウンロード</button><div class="bo-toolbar-group">
        <button id="bo-sp-save-btn" class="bo-btn bo-btn--sm bo-btn--success">ステージを保存</button>
        <button id="bo-sp-delete-btn" class="bo-btn bo-btn--sm bo-btn--danger">ステージを削除</button>
      </div></div>
    </section>
    <section class="bo-card"><div class="bo-subcard-title">登録済みステージ</div><div class="bo-subcard-note">クリックでフォームに読み込みます。</div><div id="bo-sp-list" class="bo-list-box bo-list-box--tall"></div></section>
  </div>
  <div class="bo-footer-actions"><button id="bo-sp-close-btn" class="bo-btn bo-btn--neutral">閉じる</button></div>
</div>`;
        document.body.appendChild(overlay);

        const $ = (id) => overlay.querySelector(id);
        const el = {
            msg: $('#bo-sp-msg'), id: $('#bo-sp-id'), name: $('#bo-sp-name'), enemy: $('#bo-sp-enemy'), ally: $('#bo-sp-ally'),
            required: $('#bo-sp-required'), visibility: $('#bo-sp-visibility'), sort: $('#bo-sp-sort-key'), tags: $('#bo-sp-tags'),
            concept: $('#bo-sp-concept'), desc: $('#bo-sp-description'), rules: $('#bo-sp-rules-list'),
            avatarEnabled: $('#bo-sp-avatar-enabled'), avatarIcon: $('#bo-sp-avatar-icon'), avatarName: $('#bo-sp-avatar-name'), avatarDesc: $('#bo-sp-avatar-description'),
            effectJson: $('#bo-sp-field-effects-json'), avatarJson: $('#bo-sp-stage-avatar-json'), list: $('#bo-sp-list'), file: $('#bo-sp-import-file'),
        };
        const listeners = [];
        const on = (e, f) => { s.on(e, f); listeners.push([e, f]); };
        const msg = (t, color = '#666') => { el.msg.textContent = String(t || ''); el.msg.style.color = color; };
        const profile = () => ({ version: 1, rules: Array.from(el.rules.querySelectorAll('.bo-sp-rule-row')).map((row, idx) => {
            const out = { type: row.querySelector('.bo-sp-rule-type').value, scope: row.querySelector('.bo-sp-rule-scope').value, priority: i(row.querySelector('.bo-sp-rule-priority').value, 0), value: i(row.querySelector('.bo-sp-rule-value').value, 0), rule_id: row.querySelector('.bo-sp-rule-id').value.trim() || `rule_${idx + 1}` };
            const stateName = row.querySelector('.bo-sp-rule-state-name').value.trim(); if (stateName) out.state_name = stateName;
            const trigger = row.querySelector('.bo-sp-rule-trigger-state').value.trim(); if (trigger) out.trigger_state_name = trigger;
            const cp = row.querySelector('.bo-sp-rule-cond-param').value.trim(), cv = row.querySelector('.bo-sp-rule-cond-value').value.trim();
            if (cp || cv !== '') out.condition = { param: cp || 'HP', operator: row.querySelector('.bo-sp-rule-cond-op').value, value: i(cv, 0) };
            return out;
        }) });
        const avatar = () => ({ enabled: el.avatarEnabled.value !== 'false', name: el.avatarName.value.trim(), description: el.avatarDesc.value.trim(), icon: el.avatarIcon.value.trim() });
        const syncJson = () => { refreshRuleSummary(); ensureEmptyRuleState(); el.effectJson.value = JSON.stringify(profile(), null, 2); el.avatarJson.value = JSON.stringify(avatar(), null, 2); };
        const setAvatar = (a) => { const v = (a && typeof a === 'object') ? a : {}; el.avatarEnabled.value = v.enabled === false ? 'false' : 'true'; el.avatarName.value = String(v.name || ''); el.avatarDesc.value = String(v.description || ''); el.avatarIcon.value = String(v.icon || ''); };
        const ensureEmptyRuleState = () => { if (!el.rules.querySelector('.bo-sp-rule-row')) el.rules.innerHTML = '<div class="bo-empty" style="padding:8px;border:1px dashed #dbe4f0;border-radius:8px;color:#6b7280;">現在、効果ルールはありません。「効果ルールを追加」を押して作成してください。</div>'; };
        const refreshRuleSummary = () => Array.from(el.rules.querySelectorAll('.bo-sp-rule-row')).forEach((row, idx) => {
            const t = RULE_TYPES.find((x) => x.value === row.querySelector('.bo-sp-rule-type').value)?.label || row.querySelector('.bo-sp-rule-type').value;
            const sc = SCOPES.find((x) => x.value === row.querySelector('.bo-sp-rule-scope').value)?.label || row.querySelector('.bo-sp-rule-scope').value;
            row.querySelector('.bo-sp-rule-summary-text').textContent = `効果ルール ${idx + 1}: ${t} / ${sc} / 値 ${row.querySelector('.bo-sp-rule-value').value || 0}`;
        });
        const addRuleRow = (r = {}, open = true) => {
            if (!el.rules.querySelector('.bo-sp-rule-row')) el.rules.innerHTML = '';
            const type = String(r.type || 'SPEED_ROLL_MOD').toUpperCase(), scope = String(r.scope || 'ALL').toUpperCase(), cond = (r.condition && typeof r.condition === 'object') ? r.condition : {};
            const d = document.createElement('details'); d.className = 'bo-sp-rule-row'; if (open) d.open = true; d.style.cssText = 'border:1px solid #dbe4f0;border-radius:8px;background:#f8fbff;';
            d.innerHTML = `<summary style="cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid #dbe4f0;"><strong class="bo-sp-rule-summary-text">効果ルール</strong><span style="font-size:11px;color:#6b7280;">クリックで開閉</span></summary><div style="padding:8px;"><div style="display:flex;justify-content:flex-end;margin-bottom:6px;"><button type="button" class="bo-btn bo-btn--xs bo-btn--danger bo-sp-rule-remove">削除</button></div><div class="bo-field-grid bo-field-grid--4"><label class="bo-field"><span class="bo-field-label">種類</span><select class="bo-select bo-sp-rule-type">${RULE_TYPES.map((x) => `<option value="${h(x.value)}"${x.value === type ? ' selected' : ''}>${h(x.label)}</option>`).join('')}</select></label><label class="bo-field"><span class="bo-field-label">対象</span><select class="bo-select bo-sp-rule-scope">${SCOPES.map((x) => `<option value="${h(x.value)}"${x.value === scope ? ' selected' : ''}>${h(x.label)}</option>`).join('')}</select></label><label class="bo-field"><span class="bo-field-label">値</span><input class="bo-input bo-sp-rule-value" value="${h(r.value ?? '')}" /></label><label class="bo-field"><span class="bo-field-label">優先度</span><input class="bo-input bo-sp-rule-priority" type="number" value="${h(i(r.priority, 0))}" /></label></div><div class="bo-field-grid bo-field-grid--4"><label class="bo-field"><span class="bo-field-label">ルールID（任意）</span><input class="bo-input bo-sp-rule-id" value="${h(r.rule_id || '')}" /></label><label class="bo-field"><span class="bo-field-label">付与する状態</span><input class="bo-input bo-sp-rule-state-name" value="${h(r.state_name || '')}" /></label><label class="bo-field"><span class="bo-field-label">トリガー状態名</span><input class="bo-input bo-sp-rule-trigger-state" value="${h(r.trigger_state_name || '')}" /></label><label class="bo-field"><span class="bo-field-label">条件パラメータ</span><input class="bo-input bo-sp-rule-cond-param" value="${h(cond.param || '')}" /></label></div><div class="bo-field-grid bo-field-grid--2"><label class="bo-field"><span class="bo-field-label">条件演算子</span><select class="bo-select bo-sp-rule-cond-op">${OPS.map((x) => `<option value="${h(x.value)}"${x.value === String(cond.operator || 'GTE').toUpperCase() ? ' selected' : ''}>${h(x.label)}</option>`).join('')}</select></label><label class="bo-field"><span class="bo-field-label">条件値</span><input class="bo-input bo-sp-rule-cond-value" value="${h(cond.value ?? '')}" /></label></div></div>`;
            d.querySelector('.bo-sp-rule-remove').addEventListener('click', () => { d.remove(); syncJson(); });
            d.querySelectorAll('input,select').forEach((n) => { n.addEventListener('input', syncJson); n.addEventListener('change', syncJson); });
            el.rules.appendChild(d); syncJson();
        };
        const setRules = (rules) => { el.rules.innerHTML = ''; (Array.isArray(rules) ? rules : []).forEach((r) => addRuleRow(r, false)); syncJson(); };
        const formToPayload = () => ({
            id: el.id.value.trim() || undefined, name: el.name.value.trim(), enemy_formation_id: el.enemy.value.trim(), ally_formation_id: el.ally.value.trim() || null,
            required_ally_count: Math.max(0, i(el.required.value, 0)), visibility: el.visibility.value || 'public',
            sort_key: Math.max(0, i(el.sort.value, 0)), tags: el.tags.value.split(',').map((x) => x.trim()).filter(Boolean),
            concept: el.concept.value.trim(), description: el.desc.value.trim(), field_effect_profile: profile(), stage_avatar: avatar(),
        });
        const loadToForm = (rec, sid = null) => {
            state.selected_stage_id = sid; el.id.value = String(rec.id || sid || ''); el.name.value = String(rec.name || ''); el.enemy.value = String(rec.enemy_formation_id || '');
            el.ally.value = String(rec.ally_formation_id || ''); el.required.value = String(Math.max(0, i(rec.required_ally_count, 0))); el.visibility.value = (String(rec.visibility || 'public') === 'gm' ? 'gm' : 'public');
            el.sort.value = String(Math.max(0, i(rec.sort_key, 0))); el.tags.value = Array.isArray(rec.tags) ? rec.tags.join(', ') : ''; el.concept.value = String(rec.concept || ''); el.desc.value = String(rec.description || '');
            setRules(Array.isArray(rec?.field_effect_profile?.rules) ? rec.field_effect_profile.rules : []); setAvatar(rec.stage_avatar || {}); syncJson(); renderList();
        };
        const clearForm = () => loadToForm({}, null);
        const renderFormationOptions = () => {
            const enemyIds = (state.sorted_enemy_formation_ids.length ? state.sorted_enemy_formation_ids.slice() : Object.keys(state.enemy_formations || {}).sort());
            el.enemy.innerHTML = ['<option value="">- 敵編成を選択 -</option>'].concat(enemyIds.map((id) => `<option value="${h(id)}">${h(state.enemy_formations[id]?.name || id)} [${h(id)}]</option>`)).join('');
            const allyIds = (state.sorted_ally_formation_ids.length ? state.sorted_ally_formation_ids.slice() : Object.keys(state.ally_formations || {}).sort());
            el.ally.innerHTML = ['<option value="">- 味方編成なし -</option>'].concat(allyIds.map((id) => `<option value="${h(id)}">${h(state.ally_formations[id]?.name || id)} [${h(id)}]</option>`)).join('');
        };
        const renderList = () => {
            const ids = (state.sorted_stage_preset_ids.length ? state.sorted_stage_preset_ids.slice() : Object.keys(state.stage_presets || {}).sort()).sort((a, b) => {
                const sa = state.stage_presets[a] || {}, sb = state.stage_presets[b] || {}; const ka = i(sa.sort_key, 0), kb = i(sb.sort_key, 0); if (ka !== kb) return ka - kb;
                return String(sa.name || a).localeCompare(String(sb.name || b), 'ja');
            });
            if (!ids.length) { el.list.innerHTML = '<div class="bo-empty">ステージプリセットはまだありません。</div>'; return; }
            el.list.innerHTML = ids.map((id) => { const r = state.stage_presets[id] || {}, vis = (String(r.visibility || 'public') === 'gm' ? 'GMのみ' : '全体公開'), cnt = Array.isArray(r?.field_effect_profile?.rules) ? r.field_effect_profile.rules.length : 0;
                return `<div class="bo-list-row${state.selected_stage_id === id ? ' is-selected' : ''}" data-id="${h(id)}" style="cursor:pointer;"><div class="bo-list-main" style="cursor:pointer;"><div class="bo-list-title">${h(r.name || id)}</div><div class="bo-list-meta">ID:${h(id)} / ${h(vis)} / 必要味方:${Math.max(0, i(r.required_ally_count, 0))} / 表示順:${Math.max(0, i(r.sort_key, 0))}</div><div class="bo-list-meta">効果ルール:${cnt} / ${h(r.concept || '')}</div></div><div class="bo-list-actions"><button class="bo-sp-download-btn bo-btn bo-btn--xs bo-btn--neutral" data-id="${h(id)}">JSON</button></div></div>`;
            }).join('');
            el.list.querySelectorAll('.bo-list-main').forEach((n) => n.addEventListener('click', () => { const id = n.closest('.bo-list-row')?.getAttribute('data-id') || ''; if (id) loadToForm(state.stage_presets[id] || {}, id); }));
            el.list.querySelectorAll('.bo-sp-download-btn').forEach((n) => n.addEventListener('click', () => { const id = n.getAttribute('data-id') || ''; if (!id) return; const payload = { kind: 'bo_stage_preset', version: 1, exported_at: new Date().toISOString(), record: state.stage_presets[id] }; download(`bo_stage_preset_${id}.json`, JSON.stringify(payload, null, 2)); msg('ステージJSONをダウンロードしました。', 'green'); }));
        };
        const download = (name, content) => { const b = new Blob([String(content || '')], { type: 'application/json;charset=utf-8' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(u); a.remove(); }, 0); };
        const requestAll = () => { s.emit('request_bo_catalog_list', {}); s.emit('request_bo_stage_preset_list', {}); };

        $('#bo-sp-add-rule-btn').addEventListener('click', () => addRuleRow({}, true));
        [el.avatarEnabled, el.avatarIcon, el.avatarName, el.avatarDesc].forEach((n) => { n.addEventListener('input', syncJson); n.addEventListener('change', syncJson); });
        el.effectJson.addEventListener('change', () => { try { const p = JSON.parse(el.effectJson.value || '{}'); setRules(Array.isArray(p.rules) ? p.rules : []); msg('フィールド効果JSONをフォームへ反映しました。', 'green'); } catch (e) { msg(`JSON解析に失敗しました: ${e.message}`, 'red'); } });
        el.avatarJson.addEventListener('change', () => { try { setAvatar(JSON.parse(el.avatarJson.value || '{}')); syncJson(); msg('ステージアバターJSONをフォームへ反映しました。', 'green'); } catch (e) { msg(`JSON解析に失敗しました: ${e.message}`, 'red'); } });
        $('#bo-sp-refresh-btn').addEventListener('click', requestAll);
        $('#bo-sp-clear-btn').addEventListener('click', clearForm);
        $('#bo-sp-open-catalog-btn').addEventListener('click', () => { if (typeof global.openBattleOnlyCatalogModal === 'function') global.openBattleOnlyCatalogModal({ room: roomRef() || null }); });
        $('#bo-sp-import-btn').addEventListener('click', () => { el.file.value = ''; el.file.click(); });
        el.file.addEventListener('change', () => {
            const f = el.file.files?.[0]; if (!f) return; const r = new FileReader();
            r.onload = () => { try { const src = JSON.parse(String(r.result || '{}')); const rec = (src.record && typeof src.record === 'object') ? src.record : src; if (!rec || typeof rec !== 'object' || !String(rec.enemy_formation_id || '').trim()) return msg('ステージJSONとして読み込めませんでした。', 'red'); loadToForm(rec, null); msg('ステージJSONをフォームに読み込みました。', 'green'); } catch (e) { msg(`JSON解析に失敗しました: ${e.message}`, 'red'); } };
            r.readAsText(f, 'utf-8');
        });
        $('#bo-sp-export-current-btn').addEventListener('click', () => { const rec = formToPayload(); rec.id = rec.id || null; rec.name = rec.name || '(未保存ステージ)'; if (!rec.enemy_formation_id) return msg('敵編成が未設定のため書き出せません。', 'red'); download(`bo_stage_preset_${rec.id || 'new'}.json`, JSON.stringify({ kind: 'bo_stage_preset', version: 1, exported_at: new Date().toISOString(), record: rec }, null, 2)); msg('ステージJSONをダウンロードしました。', 'green'); });
        $('#bo-sp-save-btn').addEventListener('click', () => { const payload = formToPayload(); if (!payload.name) return msg('ステージ名は必須です。', 'red'); if (!payload.enemy_formation_id) return msg('敵編成は必須です。', 'red'); s.emit('request_bo_stage_preset_save', { payload, overwrite: true }); msg('保存を実行しました。', '#444'); });
        $('#bo-sp-delete-btn').addEventListener('click', () => { const id = String(el.id.value || '').trim(); if (!id) return msg('削除するにはステージIDが必要です。', 'red'); if (!confirm(`ステージ ${id} を削除しますか？`)) return; s.emit('request_bo_stage_preset_delete', { id }); msg('削除を実行しました。', '#444'); });
        $('#bo-sp-export-btn').addEventListener('click', () => s.emit('request_bo_export_stage_presets_json', {}));

        on('receive_bo_catalog_list', (d) => {
            state.enemy_formations = (d && typeof d.enemy_formations === 'object') ? d.enemy_formations : {};
            state.sorted_enemy_formation_ids = Array.isArray(d?.sorted_enemy_formation_ids) ? d.sorted_enemy_formation_ids : Object.keys(state.enemy_formations).sort();
            state.ally_formations = (d && typeof d.ally_formations === 'object') ? d.ally_formations : {};
            state.sorted_ally_formation_ids = Array.isArray(d?.sorted_ally_formation_ids) ? d.sorted_ally_formation_ids : Object.keys(state.ally_formations).sort();
            if (d && typeof d.stage_presets === 'object') { state.stage_presets = d.stage_presets; state.sorted_stage_preset_ids = Array.isArray(d.sorted_stage_preset_ids) ? d.sorted_stage_preset_ids : Object.keys(state.stage_presets).sort(); }
            state.can_manage = !!d?.can_manage; renderFormationOptions(); renderList();
        });
        on('bo_stage_preset_list', (d) => { state.stage_presets = (d && typeof d.stage_presets === 'object') ? d.stage_presets : {}; state.sorted_stage_preset_ids = Array.isArray(d?.sorted_stage_preset_ids) ? d.sorted_stage_preset_ids : Object.keys(state.stage_presets).sort(); state.can_manage = !!d?.can_manage; renderList(); });
        on('bo_stage_preset_saved', (d) => { const rec = d?.record; const id = String(rec?.id || d?.id || '').trim(); if (id && rec && typeof rec === 'object') { state.stage_presets[id] = rec; if (!state.sorted_stage_preset_ids.includes(id)) state.sorted_stage_preset_ids.push(id); loadToForm(rec, id); } renderList(); msg('ステージを保存しました。', 'green'); });
        on('bo_stage_preset_deleted', (d) => { const id = String(d?.id || '').trim(); if (id) delete state.stage_presets[id]; state.sorted_stage_preset_ids = state.sorted_stage_preset_ids.filter((x) => x !== id); if (state.selected_stage_id === id) clearForm(); renderList(); msg('ステージを削除しました。', 'green'); });
        on('bo_export_stage_presets_json', (d) => { download(String(d?.filename || `bo_stage_presets_${Date.now()}.json`), String(d?.content || '{}')); msg('ステージJSONをダウンロードしました。', 'green'); });
        ['bo_stage_preset_error', 'bo_catalog_error'].forEach((e) => on(e, (d) => msg(String(d?.message || 'エラーが発生しました。'), 'red')));

        const setEditable = (enabled) => {
            [el.id, el.name, el.enemy, el.ally, el.required, el.visibility, el.sort, el.tags, el.concept, el.desc, $('#bo-sp-add-rule-btn'), el.avatarEnabled, el.avatarIcon, el.avatarName, el.avatarDesc, el.effectJson, el.avatarJson, $('#bo-sp-save-btn'), $('#bo-sp-delete-btn')].forEach((n) => { if (n) n.disabled = !enabled; });
            if (!enabled) msg('この画面は閲覧専用です。保存・削除はGMのみ可能です。', '#6b7280');
        };
        const closeModal = () => { while (listeners.length) { const [e, f] = listeners.pop(); s.off(e, f); } overlay.remove(); if (global.__boStagePresetModalCleanup === closeModal) global.__boStagePresetModalCleanup = null; };
        $('#bo-sp-close-btn').addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(); });

        renderFormationOptions(); clearForm(); renderList(); requestAll(); setEditable(state.can_manage);
        global.__boStagePresetModalCleanup = closeModal;
    }

    global.openBattleOnlyStagePresetModal = openBattleOnlyStagePresetModal;
})(window);

