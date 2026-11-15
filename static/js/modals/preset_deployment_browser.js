// The queue and all placement previews belong to the current GM session.
(() => {
  const labels = {stage: 'ステージ', enemy_formation: '敵編成', character: 'ユニット', ally_formation: '味方編成'};
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
  const button = (action, text, extra = '') => `<button type="button" data-action="${action}" ${extra}>${text}</button>`;
  const field = (label, input) => `<label>${label} ${input}</label>`;
  const names = values => (values || []).map(escape).join('、') || 'なし';
  const actorNames = tokens => {
    const counts = new Map();
    for (const {name} of tokens || []) counts.set(name, (counts.get(name) || 0) + 1);
    return [...counts].map(([name, count]) => count > 1 ? `${name} ×${count}` : name);
  };
  let active = null;

  function summaryHtml(summary) {
    const stage = summary.stage_changes || {};
    const counts = side => Object.values(summary[side] || {}).reduce((sum, n) => sum + n, 0);
    const detail = summary.target_mode === 'battle_only'
      ? `<p>味方 ${summary.ally_entry_count} / 必要 ${summary.required_ally_count || '—'}　敵 ${summary.enemy_entry_count}</p>`
      : `<dl class="rq-summary">
        <dt>維持 ${summary.maintained_names.length}</dt><dd>${names(summary.maintained_names)}</dd>
        <dt>除外 ${summary.removed_names.length}</dt><dd>${names(summary.removed_names)}</dd>
        <dt>追加 ${counts('added')}</dt><dd>${names(actorNames(summary.new_tokens))}</dd>
        <dt>背景</dt><dd>${stage.background ? `差し替え · ${escape(stage.background)}` : '変更なし'}</dd>
        <dt>フィールド効果</dt><dd>${stage.field_effects ? `差し替え · ${stage.field_effects.before} → ${stage.field_effects.names.length}件 · ${names(stage.field_effects.names)}` : '変更なし'}</dd>
        </dl>`;
    return detail + (summary.placement?.unplaced ? `<p class="rq-warn">空き不足 · ${summary.placement.unplaced}体は未配置</p>` : '')
      + [...summary.issues || [], ...summary.warnings || []].map(issue => `<p class="rq-warn">${escape(issue)}</p>`).join('');
  }

  function open(options = {}) {
    if (active || !window.socket || !currentRoomName) return;
    const connection = window.socket;
    const room = currentRoomName;
    const mode = options.targetMode || (battleState?.play_mode === 'battle_only' ? 'battle_only' : 'normal');
    const battleOnly = mode === 'battle_only';
    const modal = document.createElement('dialog');
    modal.className = 'rq-theme rq-dialog';
    modal.setAttribute('aria-label', '待機列');
    modal.innerHTML = `<header><h2>待機列</h2><div>${battleOnly ? '' : button('reinforce', '＋ 予定外の増援')} ${button('close', '閉じる')}</div></header>
      <p class="rq-status" role="status"></p><div class="rq-body"></div>`;
    document.body.append(modal);
    modal.showModal();
    const body = modal.querySelector('.rq-body');
    const status = modal.querySelector('.rq-status');
    const listeners = [];
    let catalog = {records: {}, users: []};
    let entries = [];
    let draft = null;
    let tab = 'stage';
    let query = '';
    let screen = 'queue';
    let encounter = null;
    let preview = null;
    let placement = null;
    let requestVersion = 0;
    let operationId = null;
    let center = null;
    let pending = false;
    let saveCheck = null;
    let removing = null;

    const emit = (event, payload = {}) => connection.emit(event, {...payload, room});
    const on = (event, listener) => {
      const handler = data => {
        if (!data.room || room === data.room) listener(data);
      };
      connection.on(event, handler);
      listeners.push([event, handler]);
    };
    const setStatus = message => { status.textContent = message; };
    const find = (kind, id) => catalog.records[kind]?.[id];
    const title = (kind, id) => find(kind, id)?.name || id;
    const checked = value => value ? 'checked' : '';
    const selected = value => value ? 'selected' : '';
    const statusBody = () => screen === 'queue' || screen === 'reinforce';

    function showModal() {
      if (!modal.open) modal.showModal();
    }

    function close(returnToCaller = false) {
      placement?.close();
      listeners.forEach(([event, handler]) => connection.off(event, handler));
      modal.remove();
      active = null;
      if (returnToCaller) options.onClose?.();
    }
    active = close;

    function ownerSelect(value, attributes) {
      return `<select ${attributes}><option value="">GM</option>${catalog.users.map(user =>
        `<option value="${escape(user.user_id)}" ${selected(user.user_id === value)}>${escape(user.username)}</option>`).join('')}
        ${value && !catalog.users.some(user => user.user_id === value) ? `<option value="${escape(value)}" selected>不在 · ${escape(value)}</option>` : ''}
        </select>`;
    }

    function edit(entry) {
      draft = entry ? structuredClone(entry) : {name: '', memo: '', deployment: {
        stage: null, enemy_mode: 'replace', formations: {ally: null, enemy: null}, characters: [],
      }};
      saveCheck = null;
      screen = 'queue';
      render();
    }

    function renderList() {
      return `<aside class="rq-pane rq-entries"><div class="rq-heading"><h3>遭遇一覧</h3>${button('new', '＋ 新規')}</div>
        ${entries.map(row => `<article class="rq-card"><strong>${escape(row.name)}</strong> ${row.done ? '<span class="rq-done">済</span>' : ''}
          ${row.memo ? `<p>${escape(row.memo)}</p>` : ''}
          <div class="rq-actions">
            ${button('deploy', battleOnly ? '下書きへ反映' : '登場', `data-id="${escape(row.id)}"`)}
            ${button('edit', '編集', `data-id="${escape(row.id)}"`)}
            ${button('delete', '外す', `data-id="${escape(row.id)}" class="rq-danger"`)}
          </div></article>`).join('') || '<p>遭遇なし</p>'}</aside>`;
    }

    function renderDraft() {
      const d = draft.deployment;
      const stage = d.stage;
      const format = (kind, record) => `<div class="rq-reference"><span>${labels[kind]} · <strong>${escape(title(kind, record.record_id))}</strong></span>
        ${button('remove-reference', '外す', `data-kind="${kind}" class="rq-danger"`)}</div>`;
      return `<section class="rq-pane rq-edit"><h3>${draft.id ? '遭遇を編集' : '遭遇を準備'}</h3>
        <div class="rq-form">
          ${field('遭遇名', `<input data-field="name" maxlength="120" value="${escape(draft.name)}">`)}
          ${field('メモ', `<textarea data-field="memo" maxlength="2000" rows="2">${escape(draft.memo)}</textarea>`)}
        </div>
        ${stage ? `${format('stage', stage)}<fieldset class="rq-options"><legend>ステージ設定</legend>
          ${Object.entries({enemy_formation: '敵編成', ally_formation: '味方編成', background: '背景', field_effects: 'フィールド効果', stage_avatar: 'ステージアバター'}).map(([key, name]) =>
            field(name, `<input type="checkbox" data-stage="${key}" ${checked(stage.apply[key])}>`)).join('')}</fieldset>` : ''}
        ${d.formations.enemy ? format('enemy_formation', d.formations.enemy) : ''}
        ${d.formations.ally ? format('ally_formation', d.formations.ally) : ''}
        ${d.characters.map((row, index) => {
          const record = find('character', row.record_id);
          return `<div class="rq-reference"><strong>${escape(title('character', row.record_id))}</strong>
            ${field('陣営', `<select data-unit="${index}" data-key="side">
              ${record?.allow_enemy || row.side === 'enemy' ? `<option value="enemy" ${selected(row.side === 'enemy')}>敵</option>` : ''}
              ${record?.allow_ally || row.side === 'ally' ? `<option value="ally" ${selected(row.side === 'ally')}>味方</option>` : ''}
            </select>`)}
            ${field('数量', `<input type="number" min="1" max="100" data-unit="${index}" data-key="count" value="${escape(row.count)}">`)}
            ${row.side === 'ally' ? field('担当', ownerSelect(row.user_id, `data-unit="${index}" data-key="user_id"`)) : ''}
            ${button('remove-reference', '外す', `data-kind="character" data-index="${index}" class="rq-danger"`)}</div>`;
        }).join('')}
        <div class="rq-options">
          ${field('既存の敵', `<select data-setting="enemy_mode"><option value="replace">置換</option><option value="append" ${selected(d.enemy_mode === 'append')}>追加</option></select>`)}
          ${field('味方編成の担当', ownerSelect(d.ally_user_id, 'data-setting="ally_user_id"'))}
        </div>
        <div class="rq-actions">
          ${button('check', '保存前チェック', pending ? 'disabled' : 'class="rq-primary"')}
          ${button('discard', '編集を終了')}
        </div></section>`;
    }

    function renderResources() {
      const tabs = Object.entries(labels).filter(([key]) =>
        screen !== 'reinforce' || key === 'character' || key === 'enemy_formation');
      return `<section class="rq-pane rq-resources"><h3>${screen === 'reinforce' ? '予定外の増援' : '資源を追加'}</h3>
        <div class="rq-actions">${tabs.map(([key, label]) => button('tab', label, `data-kind="${key}" aria-pressed="${tab === key}"`)).join('')}</div>
        <input data-search aria-label="資源検索" placeholder="名前・IDで検索" value="${escape(query)}">
        <div class="rq-results"></div></section>`;
    }

    function renderResults() {
      const container = body.querySelector('.rq-results');
      if (!container) return;
      const results = Object.values(catalog.records[tab] || {}).filter(record => {
        const searchable = [record.name, record.id, ...(record.tag_ids || record.tags || [])].join(' ').toLowerCase();
        return searchable.includes(query.trim().toLowerCase())
          && (screen !== 'reinforce' || tab !== 'character' || record.allow_enemy);
      });
      container.innerHTML = results.map(record => `<div class="rq-resource">
        <div><small>${escape(record.id)}</small> <strong>${escape(record.name)}</strong>
          ${record.member_count ? `<small> · ${record.member_count}体</small>` : ''}
          ${record.description ? `<p>${escape(record.description)}</p>` : ''}</div>
        ${button('select', screen === 'reinforce' ? '登場' : '追加', `data-id="${escape(record.id)}"`)}
        </div>`).join('') || '<p>該当する資源なし</p>';
    }

    function render() {
      modal.classList.toggle('rq-dialog--review', !statusBody());
      modal.querySelector('[data-action="reinforce"]')?.toggleAttribute('hidden', !statusBody());
      if (screen === 'queue') {
        body.innerHTML = `<div class="rq-layout">${renderList()}${draft ? renderDraft() + renderResources() : ''}</div>`;
      } else if (screen === 'reinforce') {
        body.innerHTML = renderResources() + button('queue', '待機列に戻る');
      } else if (screen === 'save-check') {
        body.innerHTML = `<h3>保存前チェック</h3>${summaryHtml(saveCheck)}<div class="rq-actions">
          ${button('save', '保存確定', 'class="rq-primary"')} ${button('queue', '編集に戻る')}</div>`;
      } else if (screen === 'confirm') {
        body.innerHTML = `<h3>${battleOnly ? '下書きへ反映' : '登場を確認'} · ${escape(encounter.name)}</h3>${summaryHtml(preview)}
          <div class="rq-actions">${button('apply', '確定', 'class="rq-primary"')} ${button('cancel-placement', '取り消し')}</div>`;
      } else if (screen === 'remove') {
        body.innerHTML = `<h3>遭遇を外す</h3><p>${escape(removing.name)}を待機列から外しますか？</p>
          <div class="rq-actions">${button('confirm-delete', '外す', 'class="rq-danger"')} ${button('queue', '取り消し')}</div>`;
      } else if (screen === 'battle-start') {
        body.innerHTML = `<h3>戦闘突入を確認</h3>${summaryHtml(preview)}<div class="rq-actions">
          ${button('enter-battle', '戦闘突入', 'class="rq-primary"')} ${button('back-to-result', '取り消し')}</div>`;
      } else if (screen === 'battle-result') {
        body.innerHTML = `<h3>下書きに反映しました</h3>${summaryHtml(preview)}<div class="rq-actions">
          ${button('start', '戦闘突入を確認', preview.ready ? 'class="rq-primary"' : 'disabled')}
          ${button('details', '詳細調整', preview.ready ? '' : 'class="rq-primary"')}
          ${button('queue', '待機列に戻る')}</div>`;
      }
      renderResults();
    }

    function selectResource(record) {
      if (screen === 'reinforce') {
        const deployment = {enemy_mode: 'append'};
        if (tab === 'character') deployment.characters = [{record_id: record.id, side: 'enemy', count: 1}];
        else deployment.formations = {enemy: {record_id: record.id, mode: 'append'}};
        begin({name: record.name, deployment});
        return;
      }
      const d = draft.deployment;
      if (!draft.name) draft.name = record.name;
      if (tab === 'character') {
        const side = record.allow_enemy ? 'enemy' : 'ally';
        const existing = d.characters.find(row => row.record_id === record.id && row.side === side);
        if (existing) existing.count = Math.min(100, Number(existing.count) + 1);
        else d.characters.push({record_id: record.id, side, count: 1});
      } else if (tab === 'stage') {
        d.stage = {record_id: record.id, apply: {enemy_formation: !!record.enemy_formation_id,
          ally_formation: battleOnly && !!record.ally_formation_id, background: true, field_effects: true, stage_avatar: true}};
      } else {
        const side = tab.split('_')[0];
        d.formations[side] = {record_id: record.id, mode: side === 'enemy' ? d.enemy_mode : battleOnly ? 'replace' : 'append'};
      }
      render();
    }

    function save(checkOnly) {
      const name = draft.name.trim();
      if (!name) return setStatus('遭遇名を入力してください。');
      pending = true;
      setStatus('検査中…');
      render();
      emit('request_encounter_save', {encounter_id: draft.id, name, memo: draft.memo, deployment: draft.deployment, check_only: checkOnly});
    }

    function deploymentPayload() {
      return encounter.id ? {encounter_id: encounter.id, center}
        : {deployment: {...encounter.deployment, target_mode: mode, center}};
    }

    function requestPreview() {
      pending = true;
      emit('request_preset_deployment_preview', {...deploymentPayload(), request_version: ++requestVersion});
    }

    function begin(row) {
      center = null;
      encounter = row;
      operationId = crypto.randomUUID();
      screen = battleOnly ? 'confirm-loading' : 'placement-loading';
      setStatus('資源を検査中…');
      requestPreview();
    }

    function cancelPlacement() {
      requestVersion++;
      pending = false;
      placement?.close();
      placement = null;
      screen = encounter?.id ? 'queue' : 'reinforce';
      setStatus('');
      showModal();
      render();
    }

    modal.addEventListener('cancel', event => {
      event.preventDefault();
      if (pending) return;
      if (screen === 'confirm') cancelPlacement();
      else if (screen === 'battle-start') { screen = 'battle-result'; render(); }
      else if (screen === 'save-check' || screen === 'remove') { screen = 'queue'; render(); }
      else close(true);
    });

    modal.addEventListener('input', event => {
      const input = event.target;
      if (input.hasAttribute('data-search')) {
        query = input.value;
        renderResults();
        return;
      }
      if (!draft) return;
      if (input.dataset.field) draft[input.dataset.field] = input.value;
      const d = draft.deployment;
      if (input.dataset.stage) d.stage.apply[input.dataset.stage] = input.checked;
      if (input.dataset.setting) {
        d[input.dataset.setting] = input.value;
        if (input.dataset.setting === 'enemy_mode' && d.formations.enemy) d.formations.enemy.mode = input.value;
      }
      if (input.dataset.unit !== undefined) {
        const key = input.dataset.key;
        d.characters[input.dataset.unit][key] = key === 'count' ? Number(input.value) : input.value;
        if (key === 'side') render();
      }
    });

    modal.addEventListener('click', event => {
      const control = event.target.closest('[data-action]');
      if (!control || pending) return;
      const {action, id, kind, index} = control.dataset;
      const row = entries.find(entry => entry.id === id);
      setStatus('');
      if (action === 'close') return close(true);
      if (action === 'new') return edit();
      if (action === 'edit') return edit(row);
      if (action === 'deploy') return begin(row);
      if (action === 'select') return selectResource(find(tab, id));
      if (action === 'check' || action === 'save') return save(action === 'check');
      if (action === 'cancel-placement') return cancelPlacement();
      if (action === 'delete') {
        removing = row;
        screen = 'remove';
        render();
        body.querySelector('[data-action="queue"]').focus();
        return;
      }
      if (action === 'confirm-delete') {
        if (draft?.id === removing.id) draft = null;
        screen = 'queue';
        emit('request_encounter_delete', {encounter_id: removing.id});
        render();
        return;
      }
      if (action === 'tab') { tab = kind; }
      if (action === 'reinforce') { screen = 'reinforce'; tab = 'character'; query = ''; }
      if (action === 'queue') screen = 'queue';
      if (action === 'discard') draft = null;
      if (action === 'remove-reference') {
        const d = draft.deployment;
        if (kind === 'stage') d.stage = null;
        else if (kind === 'character') d.characters.splice(Number(index), 1);
        else d.formations[kind.split('_')[0]] = null;
      }
      if (action === 'apply') {
        pending = true;
        control.disabled = true;
        setStatus('適用中…');
        emit('request_preset_deployment_apply', {...deploymentPayload(), operation_id: operationId,
          expected_unplaced: preview.placement?.unplaced});
        return;
      }
      if (action === 'start') screen = 'battle-start';
      if (action === 'back-to-result') screen = 'battle-result';
      if (action === 'enter-battle') {
        pending = true;
        control.disabled = true;
        setStatus('戦闘突入を検査中…');
        emit('request_bo_start_battle');
        return;
      }
      if (action === 'details') {
        close();
        window.openBattleOnlyDraftModal?.();
        return;
      }
      render();
    });

    on('preset_deployment_catalog', data => { catalog = data; if (statusBody()) render(); });
    on('encounter_queue', data => {
      entries = data.entries;
      if (data.summary) {
        draft = null;
        pending = false;
        screen = 'queue';
        setStatus('待機列に保存しました。');
      }
      if (statusBody()) render();
    });
    on('encounter_checked', data => {
      pending = false;
      saveCheck = data.summary;
      screen = 'save-check';
      setStatus('');
      render();
    });
    on('preset_deployment_preview', data => {
      if (data.request_version !== requestVersion) return;
      pending = false;
      preview = data.summary;
      if (screen === 'placement-loading' && preview.added.enemy) {
        modal.close();
        screen = 'placement';
        placement = window.openEncounterPlacement(preview, {
          confirm(position) {
            center = position;
            screen = 'confirm-loading';
            requestPreview();
          },
          cancel: cancelPlacement,
        });
        if (placement) return;
      }
      screen = 'confirm';
      showModal();
      setStatus('');
      render();
      modal.querySelector('[data-action="cancel-placement"]')?.focus();
    });
    on('preset_deployment_applied', data => {
      if (data.operation_id !== operationId) return;
      pending = false;
      preview = data.summary;
      if (battleOnly) {
        screen = 'battle-result';
        setStatus('');
        render();
      } else if (placement) {
        modal.close();
        placement.finish(encounter.name, () => {
          placement = null;
          screen = 'queue';
          showModal();
          setStatus('登場が完了しました。');
          render();
        });
      } else {
        screen = 'queue';
        setStatus('登場が完了しました。');
        render();
      }
    });
    on('preset_deployment_error', data => {
      if (data.request_version !== undefined && data.request_version !== requestVersion) return;
      pending = false;
      if (data.code === 'placement_changed') {
        setStatus(data.message);
        requestPreview();
        return;
      }
      if (!statusBody() && screen !== 'save-check') cancelPlacement();
      setStatus(data.message);
      if (data.refresh_required) emit('request_preset_deployment_catalog');
      render();
    });
    on('bo_battle_started', () => { if (screen === 'battle-start') close(); });
    on('bo_draft_error', data => {
      if (screen !== 'battle-start') return;
      pending = false;
      setStatus(data.message);
      render();
    });
    on('disconnect', () => close());
    render();
    emit('request_encounter_queue');
    emit('request_preset_deployment_catalog');
  }

  window.openRoomEncounterQueue = open;
})();
