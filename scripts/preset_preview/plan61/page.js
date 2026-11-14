// 計画61の試作：ユニット管理（ユニット・編成・ステージを、ゲーム全体で共通の資源として管理する画面）。
// DATA（build.mjs が埋める）：skills・passives・items・radiance・presets・enemyFormations・allyFormations・stages・collections（data/cache/ の本物のデータ）。
(function () {
  'use strict';
  const root = document.documentElement;
  const app = document.getElementById('app');
  const h = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const STATES = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘'];
  const TARGETS = { target_enemy_random: '敵ランダム', target_enemy_fastest: '敵最速', target_enemy_slowest: '敵最遅', target_ally_random: '味方ランダム', target_self: '自身' };
  const RULE_TYPES = { SPEED_ROLL_MOD: '速度ロール補正', DAMAGE_DEALT_MOD: '与ダメージ補正', APPLY_STATE_ON_CONDITION: '条件付き状態異常付与' };
  const SCOPES = { ALL: '全員', ALLY: '味方のみ', ENEMY: '敵のみ' };
  const TABS = [['unit', 'ユニット'], ['formation', '編成'], ['stage', 'ステージ']];
  const SECTIONS = {
    unit: [['basic', '基本情報'], ['status', 'ステータス'], ['params', 'パラメータ'], ['skills', 'スキル'], ['gear', 'パッシブ・輝化スキル・アイテム'], ['behavior', '行動設定'], ['patterns', '行動パターン'], ['history', '履歴']],
    formation: [['basic', '基本情報'], ['members', 'メンバー'], ['history', '履歴']],
    stage: [['basic', '基本情報'], ['battle', '編成'], ['field', 'フィールド効果'], ['avatar', 'ステージアバター'], ['history', '履歴']],
  };
  const USED = new Set(['name', 'image', 'status', 'params', 'states', 'commands', 'SPassive', 'inventory', 'radiance_skills', 'hidden_skills', 'special_buffs', 'tag_ids', 'disabled_tag_ids', 'flags', 'hp', 'maxHp', 'mp', 'maxMp', 'characterType', 'isNPC', 'gmOnly']);
  const SKILL_RE = /【\s*([A-Za-z]+-\d+)\s*([^】]*)】/;

  // ---- 今の JSON → ユニットの項目（JSONインポートと起動時の移行で同じ読み取り） ----
  function readCharacter(json) {
    const data = json && json.data ? json.data : (json || {});
    const status = Array.isArray(data.status) ? data.status : [];
    const stat = label => status.find(row => (row.label || row.name) === label);
    const skills = [], other = [];
    for (const line of String(data.commands || '').split('\n').map(text => text.trim()).filter(Boolean)) {
      const match = line.match(SKILL_RE);
      if (match && DATA.skills[match[1]]) {
        const name = match[2].trim();
        skills.push({ id: match[1], name: name && name !== DATA.skills[match[1]].name ? name : '', hidden: (data.hidden_skills || []).includes(match[1]) });
      } else other.push(line);
    }
    const flags = data.flags || {};
    const profile = flags.behavior_profile;
    const discarded = Object.keys(data).filter(key => !USED.has(key));
    for (const key of Object.keys(flags)) if (!['behavior_profile', 'auto_target_select', 'auto_skill_select', 'show_planned_skill', 'action_slot_mode', 'skill_constraints', 'immediate_action_used'].includes(key)) discarded.push(`flags.${key}`);
    return {
      fields: {
        name: data.name || '', image: data.image || '',
        scenario: ['scenario', 'npc', 'enemy'].includes(String(data.characterType || '').toLowerCase()) || data.isNPC === true, gm_only: !!data.gmOnly,
        hp: Number(stat('HP')?.max ?? data.maxHp ?? 0), mp: Number(stat('MP')?.max ?? data.maxMp ?? 0),
        states: Object.fromEntries(STATES.map(label => [label, Number(stat(label)?.value ?? 0)])),
        params: (data.params || []).map(row => ({ label: row.label, value: Number(row.value) || 0 })),
        skills, other,
        passives: Array.isArray(data.SPassive) ? [...data.SPassive] : [],
        radiance: Array.isArray(data.radiance_skills) ? data.radiance_skills.map(row => row.id || row) : [],
        items: Object.entries(data.inventory || {}).map(([id, count]) => ({ id, count })),
        tags: [...(data.tag_ids || [])],
        behavior: { auto_target: !!flags.auto_target_select, auto_skill: !!flags.auto_skill_select, show_planned: !!flags.show_planned_skill, slot_mode: flags.action_slot_mode === 'none' ? 'none' : 'normal', constraints: flags.skill_constraints || [] },
        patterns: [],
      },
      profile: profile && profile.loops ? profile : null,
      discarded,
    };
  }
  const stepsOf = profile => Object.values(profile.loops || {}).flatMap(loop => loop.steps || []).map(step => ({ actions: step.actions || [], target: (step.targets || [])[0] || 'target_enemy_random' }));
  const pad = (n, w = 3) => String(n).padStart(w, '0');
  const meta = (extra = {}) => ({ visibility: 'public', collection: '', deprecated: false, revision: 1, ...extra });
  const historyOf = (name, revision) => Array.from({ length: revision }, (_, i) => ({ rev: revision - i, at: `2026-11-${pad(14 - i, 2)} 2${i}:10`, by: i % 2 ? 'ろんめ' : 'RONME', note: i === revision - 1 ? '作成（プリセットから移行）' : i === 0 ? 'スキル・パターンを更新' : 'ステータスを調整' }));

  // ---- 試作の中のデータ（起動時の移行の結果のつもり：ID を振り直し、参照も付け替える） ----
  const collections = [{ id: 'SC-01', name: DATA.collections[0]?.name || 'シナリオ02', description: DATA.collections[0]?.description || '' }, { id: 'SC-02', name: 'テスト用', description: '動作確認用のユニット' }];
  const unitIdOf = {};
  const units = DATA.presets.map((row, index) => {
    const id = `U-${pad(index + 1)}`; unitIdOf[row.id] = id;
    return { id, allow_ally: row.allow_ally, allow_enemy: row.allow_enemy, ...readCharacter(row.json).fields, ...meta({ collection: 'SC-02', revision: 2 }) };
  });
  const mantis = units.find(row => row.name === 'マンティス・ヨールド');
  if (mantis) {
    Object.assign(mantis, { visibility: 'staff', collection: 'SC-01', revision: 4 });
    mantis.patterns = [
      { id: 'BP-1', name: '通常', note: '坑道入口の通常戦闘', default: true, steps: [['E-26'], ['E-28'], ['E-27'], ['E-28'], ['E-30']].map(actions => ({ actions, target: 'target_enemy_random' })) },
      { id: 'BP-2', name: 'ボス戦', note: '最深部。HP50%未満で「本気」ループへ移行', default: false, steps: [{ actions: ['E-29'], target: 'target_enemy_fastest' }, { actions: ['E-23', 'E-30'], target: 'target_enemy_random' }, { actions: ['E-26'], target: 'target_enemy_slowest' }] },
    ];
  }
  const formationIdOf = {};
  const formations = [
    ...DATA.enemyFormations.map(row => ({ type: 'enemy', src: row, members: row.members.map(m => ({ unit: unitIdOf[m.preset_id], count: m.count || 1, pattern: '' })) })),
    ...DATA.allyFormations.map(row => ({ type: 'ally', src: row, members: row.members.map(m => ({ unit: unitIdOf[m.preset_id], count: 1, pattern: '' })) })),
  ].map(({ type, src, members }, index) => {
    const id = `F-${pad(index + 1)}`; formationIdOf[src.id] = id;
    return { id, type, name: src.name, recommended: src.recommended_ally_count || 0, members, ...meta({ collection: 'SC-02', revision: 2 }) };
  });
  if (mantis) formations.push({ id: `F-${pad(formations.length + 1)}`, type: 'enemy', name: '最深部のボス', recommended: 3, members: [{ unit: mantis.id, count: 1, pattern: 'BP-2' }], ...meta({ visibility: 'staff', collection: 'SC-01', revision: 3 }) });
  const stages = DATA.stages.map((row, index) => ({
    id: `ST-${pad(index + 1)}`, name: row.name, concept: row.concept || '', description: row.description || '', tags: row.tags || [],
    enemy: formationIdOf[row.enemy_formation_id] || '', ally: formationIdOf[row.ally_formation_id] || '', required: row.required_ally_count || 0,
    rules: clone(row.field_effect_profile?.rules || []), avatar: { enabled: false, name: '', description: '', ...(row.stage_avatar || {}) },
    ...meta({ collection: 'SC-02', revision: 3 }),
  }));
  const tables = { unit: units, formation: formations, stage: stages };
  const sample = (() => {
    const base = clone(DATA.presets.find(row => row.name === 'マンティス・ヨールド')?.json || { data: {} });
    Object.assign(base.data, { memo: 'CharaCreator のメモ', color: '#888888', iconUrl: 'https://example.com/icon.png' });
    base.data.commands += '\n1d100 【幸運の判定】';
    base.data.flags = { behavior_profile: { enabled: true, initial_loop_id: 'loop_1', loops: { loop_1: { repeat: true, steps: [{ actions: ['E-26'], targets: ['target_enemy_random'] }, { actions: ['E-30'], targets: ['target_enemy_random'] }] } } } };
    return JSON.stringify(base, null, 2);
  })();

  const state = {
    tab: 'unit', scene: 'edit', selected: { unit: mantis?.id || units[0].id, formation: formations[formations.length - 1].id, stage: stages[0]?.id },
    section: { unit: 'basic', formation: 'members', stage: 'basic' },
    filter: { collection: '', q: '', deprecated: false }, imported: null, importText: sample, io: { scope: 'SC-01', deprecated: false, file: null },
  };
  const viewer = () => root.dataset.viewer; // author（制作者）・roomgm（ルームから開いた制作者でない GM）・player（ロビーから開いた一般）
  const canEdit = () => viewer() === 'author';
  const canSeeStaff = () => viewer() !== 'player';
  const inRoom = () => viewer() === 'roomgm';
  const current = () => tables[state.tab].find(row => row.id === state.selected[state.tab]);
  const unitOf = id => units.find(row => row.id === id);
  const formationOf = id => formations.find(row => row.id === id);
  const skillName = id => DATA.skills[id]?.name || '（マスター未登録）';
  const defaultPattern = unit => unit?.patterns.find(p => p.default) || null;
  const collectionName = id => collections.find(row => row.id === id)?.name || '未分類';
  const usedBy = record => state.tab === 'unit' || record.id.startsWith('U-')
    ? formations.filter(f => f.members.some(m => m.unit === record.id)).map(f => ({ kind: '編成', row: f }))
    : record.id.startsWith('F-') ? stages.filter(s => s.enemy === record.id || s.ally === record.id).map(s => ({ kind: 'ステージ', row: s })) : [];
  const usedByPattern = (unit, patternId) => formations.filter(f => f.members.some(m => m.unit === unit.id && (m.pattern || defaultPattern(unit)?.id) === patternId));

  // ---- 保存前チェック ----
  function problems(record) {
    const out = [];
    if (state.tab === 'unit') {
      const own = new Set(record.skills.map(row => row.id));
      for (const row of record.skills) if (!DATA.skills[row.id]) out.push(['error', `スキル ${row.id}：マスター未登録`]);
      for (const id of record.passives) if (!DATA.passives[id]) out.push(['error', `パッシブ ${id}：マスター未登録`]);
      for (const pattern of record.patterns) pattern.steps.forEach((step, index) => step.actions.forEach(id => {
        if (!own.has(id)) out.push(['error', `パターン「${pattern.name}」ステップ${index + 1}：未所持スキル ${id}`]);
      }));
      if (record.allow_enemy && !record.patterns.length && record.skills.length) out.push(['note', '行動パターン未設定：使用可能スキルから自動選択']);
    } else if (state.tab === 'formation') {
      record.members.forEach((m, i) => {
        const unit = unitOf(m.unit);
        if (!unit) out.push(['error', `メンバー${i + 1}：ユニット未選択`]);
        else if (unit.deprecated) out.push(['note', `メンバー${i + 1}：${unit.name} は廃止済み`]);
        else if (record.type === 'enemy' && !unit.allow_enemy) out.push(['error', `メンバー${i + 1}：${unit.name} は敵キャラクターではない`]);
        else if (record.type === 'ally' && !unit.allow_ally) out.push(['error', `メンバー${i + 1}：${unit.name} は味方キャラクターではない`]);
        if (unit && m.pattern && !unit.patterns.some(p => p.id === m.pattern)) out.push(['error', `メンバー${i + 1}：パターン ${m.pattern} が無い`]);
        if (unit && record.visibility === 'public' && unit.visibility === 'staff') out.push(['note', `メンバー${i + 1}：${unit.name} は非公開（一般には中身が見えない）`]);
      });
      if (!record.members.length) out.push(['error', 'メンバーが0人']);
    } else {
      if (!record.enemy) out.push(['error', '敵編成が未選択']);
      for (const [key, label] of [['enemy', '敵編成'], ['ally', '味方編成']]) if (record[key] && formationOf(record[key])?.deprecated) out.push(['note', `${label}は廃止済み`]);
    }
    return out;
  }
  const paletteLine = row => {
    const master = DATA.skills[row.id];
    if (!master) return `【${row.id}】`;
    return row.name ? master.palette.replace(SKILL_RE, `【${row.id} ${row.name}】`) : master.palette;
  };

  // ---- 描く：部品 ----
  const button = (label, action, extra = '', attrs = '') => `<button type="button" class="btn ${extra}" data-action="${action}" ${attrs}>${label}</button>`;
  const chips = (ids, table, kind) => `<div class="chips">${ids.map((id, index) => `<span class="chip"><code>${h(id)}</code>${h(table[id]?.name || '（マスター未登録）')}<button type="button" aria-label="${h(id)} を削除" data-action="remove-${kind}" data-index="${index}">×</button></span>`).join('') || '<span class="muted">なし</span>'}
    <label class="adder"><input list="list-${kind}" placeholder="追加（ID・名称で検索）" data-add="${kind}"><datalist id="list-${kind}">${Object.entries(table).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}</option>`).join('')}</datalist></label></div>`;
  const badges = row => `${row.allow_ally ? '<span class="tag">味方</span>' : ''}${row.allow_enemy ? '<span class="tag tag-enemy">敵</span>' : ''}${row.type ? `<span class="tag ${row.type === 'enemy' ? 'tag-enemy' : ''}">${row.type === 'enemy' ? '敵編成' : '味方編成'}</span>` : ''}${row.visibility === 'staff' ? '<span class="tag tag-staff">非公開</span>' : ''}${row.deprecated ? '<span class="tag tag-dep">廃止</span>' : ''}`;
  const commonBasic = record => `<div class="grid2">
      <label class="field">分類<select data-field="collection"><option value="">未分類</option>${collections.map(c => `<option value="${c.id}" ${record.collection === c.id ? 'selected' : ''}>${h(c.name)}</option>`).join('')}</select></label>
      <fieldset class="field"><legend>公開範囲</legend><label class="check"><input type="radio" name="vis" ${record.visibility === 'public' ? 'checked' : ''} data-vis="public">公開</label><label class="check"><input type="radio" name="vis" ${record.visibility === 'staff' ? 'checked' : ''} data-vis="staff">制作者・GMのみ</label></fieldset></div>`;
  const historyBody = record => `<ol class="history">${historyOf(record.name, record.revision).map((row, i) => `<li><strong>版 ${row.rev}</strong><span class="muted small">${row.at}・${h(row.by)}</span><span>${h(row.note)}</span>${i === 0 ? '<span class="tag">現在</span>' : button('この版に戻す', 'restore', 'btn-sm')}</li>`).join('')}</ol>
      <p class="muted small">戻すと、その版の内容で新しい版として保存。</p>`;

  // ---- ユニット ----
  function unitSection(key, unit) {
    if (key === 'basic') return `<div class="grid2">
      <label class="field">キャラクター名<input value="${h(unit.name)}" data-field="name"></label>
      <div class="field"><span>画像</span><div class="image-pick"><span class="thumb">${unit.image ? `<img src="${h(unit.image)}" alt="">` : '未設定'}</span>${button('画像を選択', 'pick-image')}${unit.image ? button('解除', 'clear-image') : ''}</div></div></div>
      <fieldset class="field"><legend>キャラ区分</legend><label class="check"><input type="checkbox" ${unit.allow_ally ? 'checked' : ''} data-field="allow_ally">味方キャラクター</label><label class="check"><input type="checkbox" ${unit.allow_enemy ? 'checked' : ''} data-field="allow_enemy">敵キャラクター</label></fieldset>
      <label class="check"><input type="checkbox" ${unit.scenario ? 'checked' : ''} data-field="scenario">シナリオキャラクター（輝化予算・タグ制限の対象外）</label>
      <label class="check"><input type="checkbox" ${unit.gm_only ? 'checked' : ''} data-field="gm_only">GM限定表示</label>
      ${commonBasic(unit)}
      <div class="field"><span>タグ</span><div class="chips">${unit.tags.map(t => `<span class="chip">${h(t)}</span>`).join('') || '<span class="muted">なし</span>'}<span class="muted">（既存タグから選択）</span></div></div>`;
    if (key === 'status') return `<div class="grid2">
      <label class="field">最大HP<input type="number" value="${unit.hp}" data-field="hp"></label>
      <label class="field">最大MP<input type="number" value="${unit.mp}" data-field="mp"></label></div>
      <h4>初期状態</h4><div class="grid6">${STATES.map(label => `<label class="field">${label}<input type="number" value="${unit.states[label]}" data-state="${label}"></label>`).join('')}</div>
      <p class="muted small">戦闘開始時の値。HP・MPは最大値で開始。</p>`;
    if (key === 'params') {
      const groups = [['能力値', row => !/補正$/.test(row.label) && unit.params.indexOf(row) < 8], ['補正', row => /補正$/.test(row.label)], ['技能・その他', row => !/補正$/.test(row.label) && unit.params.indexOf(row) >= 8]];
      return groups.map(([title, test]) => `<h4>${title}</h4><div class="grid6">${unit.params.filter(test).map(row => `<label class="field">${h(row.label)}<input type="number" value="${row.value}" data-param="${h(row.label)}"></label>`).join('') || '<span class="muted">なし</span>'}</div>`).join('');
    }
    if (key === 'skills') return `<div class="skill-cards">${unit.skills.map((row, index) => { const m = DATA.skills[row.id]; return `<article class="skill-card ${m ? '' : 'is-bad'}">
        <header><code>${h(row.id)}</code><strong>${h(m?.name || '（マスター未登録）')}</strong><span class="tag">${h(m?.category || '')}</span>${button('×', 'remove-skill', 'btn-icon', `data-index="${index}" aria-label="${h(row.id)} を削除"`)}</header>
        <label class="field">固有名称<input value="${h(row.name)}" placeholder="${h(m?.name || '')}" data-skill-name="${index}"></label>
        <p class="palette">${h(paletteLine(row))}</p>
        <p class="muted small">${h(m?.cost || '')} ${h((m?.text || '').replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1').slice(0, 60))}</p>
        <label class="check small"><input type="checkbox" ${row.hidden ? 'checked' : ''} data-skill-hidden="${index}">非公開</label></article>`; }).join('')}</div>
      <label class="adder wide"><input list="list-skill" placeholder="スキル追加（ID・名称で検索。例：E-29）" data-add="skill"><datalist id="list-skill">${Object.entries(DATA.skills).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}（${h(row.category)}）</option>`).join('')}</datalist></label>
      <p class="muted small">チャットパレットは保存せず、配置時にマスターから生成。固有名称が空欄ならマスター名称。</p>
      <h4>その他のパレット行</h4><textarea rows="3" data-field="other" placeholder="1d100 【幸運の判定】">${h(unit.other.join('\n'))}</textarea>`;
    if (key === 'gear') return `<h4>パッシブ</h4>${chips(unit.passives, DATA.passives, 'passive')}
      <h4>輝化スキル</h4>${chips(unit.radiance, DATA.radiance, 'radiance')}
      <h4>アイテム</h4><div class="chips">${unit.items.map((row, index) => `<span class="chip"><code>${h(row.id)}</code>${h(DATA.items[row.id]?.name || '（マスター未登録）')}<input type="number" min="1" value="${row.count}" data-item-count="${index}" aria-label="個数">個<button type="button" aria-label="削除" data-action="remove-item" data-index="${index}">×</button></span>`).join('') || '<span class="muted">なし</span>'}
        <label class="adder"><input list="list-item" placeholder="追加（ID・名称で検索）" data-add="item"><datalist id="list-item">${Object.entries(DATA.items).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}</option>`).join('')}</datalist></label></div>`;
    if (key === 'behavior') {
      const b = unit.behavior;
      return `<p class="muted small">敵キャラクター時のみ有効。</p>
        <label class="check"><input type="checkbox" ${b.auto_target ? 'checked' : ''} data-behavior="auto_target">対象の自動選択</label>
        <label class="check"><input type="checkbox" ${b.auto_skill ? 'checked' : ''} data-behavior="auto_skill">スキルの自動選択</label>
        <label class="check"><input type="checkbox" ${b.show_planned ? 'checked' : ''} data-behavior="show_planned">予定スキルの公開</label>
        <fieldset class="field"><legend>行動スロット</legend><label class="check"><input type="radio" name="slot" ${b.slot_mode === 'normal' ? 'checked' : ''} data-slot="normal">通常</label><label class="check"><input type="radio" name="slot" ${b.slot_mode === 'none' ? 'checked' : ''} data-slot="none">行動なし（瓦礫などの設置物）</label></fieldset>
        <div class="field"><span>スキルの制約</span><div class="muted small">${b.constraints.length ? `${b.constraints.length}件` : 'なし'}　<em>（仕様はPR詳細で決定）</em></div></div>`;
    }
    if (key === 'patterns') {
      if (!unit.allow_enemy) return '<p class="muted">キャラ区分で「敵キャラクター」を選択すると作成可能。</p>';
      const own = new Set(unit.skills.map(row => row.id));
      return `${unit.patterns.map((p, index) => `<article class="pattern ${p.default ? 'is-default' : ''}">
        <header><strong>${h(p.name)}</strong>${p.default ? '<span class="badge">既定</span>' : ''}<span class="muted small">${h(p.id)}</span></header>
        <p class="muted small">${h(p.note || '')}</p>
        <ol class="steps">${p.steps.map(step => `<li>${step.actions.map(id => `<span class="step-skill ${own.has(id) ? '' : 'is-bad'}"><code>${h(id)}</code>${h(skillName(id))}</span>`).join('<span class="plus">＋</span>')}<span class="muted small">→ ${h(TARGETS[step.target] || step.target)}</span></li>`).join('')}</ol>
        <p class="small">使用中の編成：${usedByPattern(unit, p.id).map(f => h(f.name)).join('・') || '<span class="muted">なし</span>'}</p>
        <footer>${button('チャート編集', 'open-chart')}${button('複製', 'copy-pattern', '', `data-index="${index}"`)}${p.default ? '' : button('既定に設定', 'make-default', '', `data-index="${index}"`)}${button('他ユニットへ複製…', 'copy-other')}${button('削除', 'delete-pattern', 'btn-danger', `data-index="${index}" ${p.default && unit.patterns.length > 1 ? 'disabled title="他のパターンを既定に設定してから削除"' : ''}`)}</footer>
      </article>`).join('') || '<p class="muted">パターン未作成。使用可能スキルから自動選択で行動。</p>'}
      ${button('＋ パターン追加', 'new-pattern', 'btn-primary')}
      <p class="muted small">最初のパターンが既定。編成で未指定の場合に使用。</p>`;
    }
    if (key === 'history') return historyBody(unit);
    return '';
  }

  // ---- 編成 ----
  function formationSection(key, f) {
    if (key === 'basic') return `<div class="grid2">
      <label class="field">編成名<input value="${h(f.name)}" data-field="name"></label>
      <div class="field"><span>種類</span><div>${f.type === 'enemy' ? '敵編成' : '味方編成'} <span class="muted small">（作成時に選択）</span></div></div>
      <label class="field">推奨人数（味方）<input type="number" min="0" value="${f.recommended}" data-field="recommended"></label></div>
      ${commonBasic(f)}`;
    if (key === 'members') {
      const pool = units.filter(u => !u.deprecated && (f.type === 'enemy' ? u.allow_enemy : u.allow_ally));
      return `<table class="members"><thead><tr><th>ユニット</th><th>数</th>${f.type === 'enemy' ? '<th>行動パターン</th>' : ''}<th></th></tr></thead><tbody>${f.members.map((m, mi) => {
        const unit = unitOf(m.unit);
        const patterns = unit?.patterns || [];
        const options = patterns.length
          ? `<option value="" ${m.pattern ? '' : 'selected'}>既定（${h(defaultPattern(unit).name)}）</option>${patterns.map(p => `<option value="${p.id}" ${m.pattern === p.id ? 'selected' : ''}>${h(p.name)}</option>`).join('')}`
          : '<option>パターンなし（自動選択）</option>';
        return `<tr><td><select data-member-unit="${mi}"><option value="">（選択）</option>${[...new Set([unit, ...pool].filter(Boolean))].map(u => `<option value="${u.id}" ${u.id === m.unit ? 'selected' : ''}>${h(u.id)} ${h(u.name)}${u.visibility === 'staff' ? '（非公開）' : ''}${u.deprecated ? '（廃止）' : ''}</option>`).join('')}</select></td>
          <td><input type="number" min="1" value="${m.count}" data-member-count="${mi}" aria-label="数" class="num"></td>
          ${f.type === 'enemy' ? `<td><select data-member-pattern="${mi}" ${patterns.length ? '' : 'disabled'}>${options}</select></td>` : ''}
          <td>${f.type === 'enemy' && patterns.length ? button('複製して編集', 'member-copy', 'btn-sm', `data-index="${mi}"`) : ''}${button('×', 'remove-member', 'btn-icon', `data-index="${mi}" aria-label="メンバー${mi + 1}を削除"`)}</td></tr>`;
      }).join('')}</tbody></table>
      ${button('＋ メンバー追加', 'add-member', 'btn-primary')}
      ${f.type === 'enemy' ? '<p class="muted small">パターンの変更は、使用中のすべての編成に反映。編成固有の調整は「複製して編集」で別パターンとして作成。</p>' : ''}`;
    }
    if (key === 'history') return historyBody(f);
    return '';
  }

  // ---- ステージ ----
  function stageSection(key, s) {
    if (key === 'basic') return `<label class="field">ステージ名<input value="${h(s.name)}" data-field="name"></label>
      <label class="field">コンセプト<input value="${h(s.concept)}" data-field="concept"></label>
      <label class="field">説明<textarea rows="4" data-field="description">${h(s.description)}</textarea></label>
      ${commonBasic(s)}
      <div class="field"><span>タグ</span><div class="chips">${s.tags.map(t => `<span class="chip">${h(t)}</span>`).join('') || '<span class="muted">なし</span>'}</div></div>`;
    if (key === 'battle') {
      const pick = (type, field) => `<select data-field="${field}"><option value="">（なし）</option>${formations.filter(f => f.type === type && (!f.deprecated || f.id === s[field])).map(f => `<option value="${f.id}" ${s[field] === f.id ? 'selected' : ''}>${h(f.id)} ${h(f.name)}${f.visibility === 'staff' ? '（非公開）' : ''}</option>`).join('')}</select>`;
      return `<div class="grid2"><label class="field">敵編成${pick('enemy', 'enemy')}</label><label class="field">味方編成（任意）${pick('ally', 'ally')}</label>
        <label class="field">必要人数（味方）<input type="number" min="0" value="${s.required}" data-field="required"></label></div>`;
    }
    if (key === 'field') return `${s.rules.map((r, i) => `<article class="rule"><div class="grid2">
        <label class="field">種類<select data-rule="${i}:type">${Object.entries(RULE_TYPES).map(([v, l]) => `<option value="${v}" ${r.type === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
        <label class="field">対象<select data-rule="${i}:scope">${Object.entries(SCOPES).map(([v, l]) => `<option value="${v}" ${r.scope === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
        <label class="field">値<input type="number" value="${r.value ?? 0}" data-rule="${i}:value"></label>
        <label class="field">表示名<input value="${h(r.display_name || '')}" data-rule="${i}:display_name"></label></div>
        <label class="field">説明<input value="${h(r.description || '')}" data-rule="${i}:description"></label>
        ${button('削除', 'remove-rule', 'btn-danger btn-sm', `data-index="${i}"`)}</article>`).join('') || '<p class="muted">フィールド効果なし</p>'}
      ${button('＋ フィールド効果追加', 'add-rule', 'btn-primary')}`;
    if (key === 'avatar') return `<label class="check"><input type="checkbox" ${s.avatar.enabled ? 'checked' : ''} data-avatar="enabled">ステージアバターを使用</label>
      <div class="grid2"><label class="field">名前<input value="${h(s.avatar.name)}" data-avatar="name"></label><label class="field">説明<input value="${h(s.avatar.description)}" data-avatar="description"></label></div>`;
    if (key === 'history') return historyBody(s);
    return '';
  }

  // ---- 右側の確認 ----
  function preview(record) {
    const list = problems(record);
    const checks = `<section><h4>保存前チェック</h4>${list.length ? `<ul class="problems">${list.map(([kind, text]) => `<li class="is-${kind}">${h(text)}</li>`).join('')}</ul>` : '<p class="ok">問題なし</p>'}</section>`;
    const used = usedBy(record);
    const usedList = `<section><h4>使用中</h4>${used.map(({ kind, row }) => `<p class="small">${kind}：<code>${h(row.id)}</code>${h(row.name)}${row.deprecated ? '（廃止）' : ''}</p>`).join('') || '<p class="muted small">なし（削除できる）</p>'}</section>`;
    if (state.tab === 'unit') return `<h3>確認</h3>
      <section><h4>チャットパレット（配置時）</h4><pre class="palette-box">${h([...record.skills.map(paletteLine), ...record.other].join('\n') || '（なし）')}</pre></section>${checks}${usedList}`;
    if (state.tab === 'formation') return `<h3>確認</h3>
      <section><h4>メンバー</h4>${record.members.map(m => { const u = unitOf(m.unit); return `<p class="small">${h(u?.name || '（未選択）')} ×${m.count}　<span class="muted">HP ${u?.hp ?? '-'}${record.type === 'enemy' ? `・${h(u?.patterns.find(p => p.id === m.pattern)?.name || defaultPattern(u)?.name || '自動選択')}` : ''}</span></p>`; }).join('')}</section>${checks}${usedList}`;
    const enemy = formationOf(record.enemy), ally = formationOf(record.ally);
    return `<h3>確認</h3>
      <section class="stage-card"><h4>${h(record.name)}</h4><p class="small">${h(record.concept)}</p>
        <p class="small"><strong>敵：</strong>${enemy ? enemy.members.map(m => `${h(unitOf(m.unit)?.name || '?')} ×${m.count}`).join('、') : '未選択'}</p>
        <p class="small"><strong>味方：</strong>${ally ? ally.members.map(m => h(unitOf(m.unit)?.name || '?')).join('、') : 'ルームの参加者'}（必要 ${record.required}人）</p>
        ${record.rules.map(r => `<p class="small field-effect">◆ ${h(r.display_name || RULE_TYPES[r.type])}：${h(r.description || '')}</p>`).join('')}</section>${checks}${usedList}`;
  }

  // ---- 画面 ----
  function editScene() {
    const record = current();
    if (!record) return '<p class="muted pad">一覧から選択。</p>';
    const sections = SECTIONS[state.tab];
    const section = sections.some(([key]) => key === state.section[state.tab]) ? state.section[state.tab] : sections[0][0];
    const body = { unit: unitSection, formation: formationSection, stage: stageSection }[state.tab](section, record);
    const bad = key => (key === 'skills' || key === 'patterns' || key === 'members' || key === 'battle') && problems(record).some(([k]) => k === 'error');
    const nav = `<nav class="toc" aria-label="セクション">${sections.map(([key, label]) => `<button type="button" data-section="${key}" aria-current="${section === key}">${label}${key === 'patterns' && record.allow_enemy ? ` <small>${record.patterns.length}</small>` : ''}${key === 'members' ? ` <small>${record.members.length}</small>` : ''}${bad(key) ? ' <span class="dot" title="エラーあり">●</span>' : ''}</button>`).join('')}
      ${state.tab === 'unit' && canEdit() ? `<hr><button type="button" data-action="go-import">JSONインポート</button>` : ''}</nav>`;
    const used = usedBy(record).length;
    const foot = canEdit()
      ? `<div class="foot-left">${record.deprecated ? button('廃止を取り消す', 'undeprecate') : button('廃止', 'deprecate', '', used ? '' : 'title="未使用なので削除もできる"')}${button('削除', 'delete', 'btn-danger', used ? `disabled title="使用中（${used}件）のため削除不可。廃止を使用"` : '')}</div><small class="muted">版 ${record.revision}・制作者が直接保存（承認不要）</small>${button('保存', 'save', 'btn-primary')}`
      : inRoom() ? `<small class="muted">閲覧のみ（制作者でない GM）</small>${button('ルームへ配置', 'deploy', 'btn-primary')}`
        : '<small class="muted">閲覧のみ</small>';
    return `<div class="editor"><div class="editbar"><strong><code>${h(record.id)}</code> ${h(record.name)}</strong>${badges(record)}<span class="muted small">${h(collectionName(record.collection))}</span></div>
      <div class="edit-grid">${nav}<fieldset class="edit-input ro" ${canEdit() ? '' : 'disabled'}><section class="sec"><h3>${sections.find(([key]) => key === section)[1]}</h3>${body}</section></fieldset><aside class="edit-preview">${preview(record)}</aside></div>
      <footer class="editfoot">${foot}</footer></div>`;
  }

  function importScene() {
    const result = state.imported;
    return `<div class="editor"><div class="editbar">${button('← 編集', 'go-edit')}<strong>JSONインポート</strong></div>
      <div class="import-grid"><section class="sec"><h3>JSON入力</h3><p class="muted small">CharaCreator出力・旧プリセットの書き出しに対応。</p>${button('ファイル読込', 'noop')}
        <textarea rows="20" class="mono" data-field="import">${h(state.importText)}</textarea>${button('解析', 'read-import', 'btn-primary')}</section>
      <section class="sec">${result ? `<h3>解析結果</h3>
        <table class="result"><tbody>
        <tr><th>キャラクター名</th><td>${h(result.fields.name)}</td></tr>
        <tr><th>HP・MP</th><td>${result.fields.hp}・${result.fields.mp}</td></tr>
        <tr><th>スキル</th><td>${result.fields.skills.length}件：${result.fields.skills.map(row => `<code>${h(row.id)}</code>${row.name ? `（${h(row.name)}）` : ''}`).join('、')}</td></tr>
        <tr><th>その他のパレット行</th><td>${result.fields.other.map(line => `<code>${h(line)}</code>`).join('<br>') || 'なし'}</td></tr>
        <tr><th>パッシブ</th><td>${result.fields.passives.map(id => `<code>${h(id)}</code>${h(DATA.passives[id]?.name || '')}`).join('、') || 'なし'}</td></tr>
        <tr><th>行動パターン</th><td>${result.profile ? `あり（${stepsOf(result.profile).length}ステップ）：既定パターンとして登録` : 'なし'}</td></tr>
        <tr class="is-drop"><th>破棄する項目</th><td>${result.discarded.map(key => `<code>${h(key)}</code>`).join('、') || 'なし'}<div class="muted small">配置時に未使用のため破棄</div></td></tr>
        </tbody></table>
        <div class="row">${button('新規作成', 'create-import', 'btn-primary')}${button('選択中のユニットを上書き', 'noop')}</div>` : '<p class="muted">「解析」で各項目への割り当てを表示。</p>'}</section></div></div>`;
  }

  function ioScene() {
    const scope = state.io.scope;
    const pickRows = list => list.filter(row => (scope === 'all' || row.collection === scope) && (state.io.deprecated || !row.deprecated));
    const counts = { unit: pickRows(units).length, formation: pickRows(formations).length, stage: pickRows(stages).length };
    const file = state.io.file;
    return `<div class="editor"><div class="editbar">${button('← 一覧', 'go-edit')}<strong>書き出し・取り込み</strong><span class="muted small">本番と手元の間の移動用（旧・移送JSON）</span></div>
      <div class="import-grid"><section class="sec"><h3>書き出し</h3>
        <fieldset class="field"><legend>範囲</legend>${collections.map(c => `<label class="check"><input type="radio" name="scope" ${scope === c.id ? 'checked' : ''} data-io-scope="${c.id}">${h(c.name)}</label>`).join('')}<label class="check"><input type="radio" name="scope" ${scope === 'all' ? 'checked' : ''} data-io-scope="all">全件</label></fieldset>
        <label class="check"><input type="checkbox" ${state.io.deprecated ? 'checked' : ''} data-io-deprecated>廃止済みも含める</label>
        <p class="small">ユニット ${counts.unit}件・編成 ${counts.formation}件・ステージ ${counts.stage}件（非公開も含む）。参照先が範囲外なら一緒に書き出す。</p>
        ${button('JSONを書き出し', 'export', 'btn-primary')}</section>
      <section class="sec"><h3>取り込み</h3>${button('ファイルを選択', 'pick-io-file')}
        ${file ? `<table class="result"><tbody>
          <tr><th>ファイル</th><td><code>unit_export_SC-01.json</code></td></tr>
          <tr><th>新規</th><td>ユニット 1件（<code>U-101</code> 坑道の見張り）</td></tr>
          <tr><th>上書き</th><td>ユニット 1件（<code>${h(mantis?.id || 'U-006')}</code> ${h(mantis?.name || '')}：版 ${mantis?.revision || 1} → ${(mantis?.revision || 1) + 1}）・編成 1件</td></tr>
          <tr><th>参照の確認</th><td>スキル・パッシブはすべてマスターに登録済み</td></tr>
          <tr class="is-drop"><th>同じIDで内容が新しい物</th><td>手元の方が新しい版：なし</td></tr></tbody></table>
          <div class="row">${button('取り込み', 'run-import', 'btn-primary')}</div>` : '<p class="muted small">書き出したJSONを選択すると、新規・上書きの件数を表示。</p>'}</section></div></div>`;
  }

  function render() {
    const scene = state.scene;
    const rows = tables[state.tab].filter(row => (canSeeStaff() || row.visibility === 'public') && (state.filter.deprecated || !row.deprecated) && (!state.filter.collection || row.collection === state.filter.collection) && (!state.filter.q || `${row.id} ${row.name}`.includes(state.filter.q)));
    if (!rows.some(row => row.id === state.selected[state.tab]) && rows[0]) state.selected[state.tab] = rows[0].id;
    const roomBand = inRoom() ? '<span class="room-band">ルーム「テスト卓」から表示中</span>' : '';
    app.innerHTML = `<div class="ws"><header class="ws-head"><div><h2>ユニット管理</h2><p class="muted small">計画61 試作：ユニット・編成・ステージ（ゲーム全体で共通の資源）</p></div>${roomBand}
        <div class="head-actions">${canEdit() ? button('書き出し・取り込み', 'go-io') : ''}${button('閉じる', 'noop')}</div></header>
      <nav class="ws-tabs">${TABS.map(([key, label]) => `<button type="button" data-tab="${key}" aria-selected="${state.tab === key && scene !== 'io'}">${label} <small>${tables[key].filter(row => !row.deprecated && (canSeeStaff() || row.visibility === 'public')).length}</small></button>`).join('')}</nav>
      <div class="ws-body">${scene === 'io' ? '' : `<aside class="ws-list">
          ${canEdit() ? (state.tab === 'unit' ? `<details class="new-menu"><summary class="btn btn-primary">＋ 新規作成</summary><div>${button('空のユニット', 'new-blank')}${button('JSONインポート', 'go-import')}</div></details>` : button(state.tab === 'formation' ? '＋ 新規作成（敵編成）' : '＋ 新規作成', 'new-record', 'btn-primary')) : ''}
          <input type="search" placeholder="ID・名前で検索" value="${h(state.filter.q)}" data-filter="q">
          <select data-filter="collection"><option value="">すべての分類</option>${collections.map(c => `<option value="${c.id}" ${state.filter.collection === c.id ? 'selected' : ''}>${h(c.name)}</option>`).join('')}</select>
          <label class="check small"><input type="checkbox" ${state.filter.deprecated ? 'checked' : ''} data-filter="deprecated">廃止済みも表示</label>
          ${rows.map(row => `<button type="button" class="rec" data-select="${row.id}" aria-current="${row.id === state.selected[state.tab]}"><code>${h(row.id)}</code><strong>${h(row.name)}</strong><span>${badges(row)}${state.tab === 'unit' && row.allow_enemy ? `<span class="muted small">パターン ${row.patterns.length}</span>` : ''}${state.tab === 'formation' ? `<span class="muted small">${row.members.length}人</span>` : ''}</span></button>`).join('') || '<p class="muted small">該当なし</p>'}
        </aside>`}
      <main class="ws-main">${scene === 'io' ? ioScene() : scene === 'import' ? importScene() : editScene()}</main></div></div>`;
  }

  // ---- 操作 ----
  const update = fn => { fn(current()); render(); };
  app.addEventListener('click', event => {
    const target = event.target.closest('button');
    if (!target || target.disabled) return;
    const index = Number(target.dataset.index);
    if (target.dataset.tab) { state.tab = target.dataset.tab; state.scene = 'edit'; render(); return; }
    if (target.dataset.select) { state.selected[state.tab] = target.dataset.select; state.scene = 'edit'; render(); return; }
    if (target.dataset.section) { state.section[state.tab] = target.dataset.section; render(); return; }
    const newId = prefix => `${prefix}-${pad(tables[state.tab].length + 101)}`;
    const actions = {
      'remove-skill': () => update(c => c.skills.splice(index, 1)),
      'remove-passive': () => update(c => c.passives.splice(index, 1)),
      'remove-radiance': () => update(c => c.radiance.splice(index, 1)),
      'remove-item': () => update(c => c.items.splice(index, 1)),
      'make-default': () => update(c => c.patterns.forEach((p, i) => { p.default = i === index; })),
      'delete-pattern': () => update(c => { const [gone] = c.patterns.splice(index, 1); if (gone.default && c.patterns[0]) c.patterns[0].default = true; }),
      'copy-pattern': () => update(c => c.patterns.push({ ...clone(c.patterns[index]), id: `BP-${c.patterns.length + 1}`, name: `${c.patterns[index].name}（コピー）`, default: false })),
      'new-pattern': () => update(c => c.patterns.push({ id: `BP-${c.patterns.length + 1}`, name: `パターン${c.patterns.length + 1}`, note: '', default: !c.patterns.length, steps: c.skills.slice(0, 2).map(row => ({ actions: [row.id], target: 'target_enemy_random' })) })),
      'open-chart': () => alert('既存の行動チャートエディター（behavior_flow_editor_modal.js）でこのパターンを編集。'),
      'copy-other': () => alert('複製先ユニットを選択。未所持スキルがあれば一覧表示し、置換か削除を選択。'),
      'go-import': () => { state.tab = 'unit'; state.scene = 'import'; render(); },
      'go-edit': () => { state.scene = 'edit'; render(); },
      'go-io': () => { state.scene = 'io'; render(); },
      'pick-image': () => update(c => { alert('既存の画像選択モーダル（ギャラリー／新規アップロード／デフォルト素材）を表示。試作では既定素材を設定。'); c.image = 'https://res.cloudinary.com/demo/image/upload/w_160/sample.jpg'; }),
      'clear-image': () => update(c => { c.image = ''; }),
      'new-blank': () => { const id = newId('U'); units.push({ ...readCharacter({ data: { name: '新規ユニット' } }).fields, id, allow_ally: false, allow_enemy: true, ...meta({ collection: state.filter.collection, visibility: 'staff' }) }); state.selected.unit = id; state.section.unit = 'basic'; state.scene = 'edit'; render(); },
      'new-record': () => {
        if (state.tab === 'formation') { const id = newId('F'); formations.push({ id, type: 'enemy', name: '新規編成', recommended: 3, members: [], ...meta({ collection: state.filter.collection, visibility: 'staff' }) }); state.selected.formation = id; state.section.formation = 'members'; }
        else { const id = newId('ST'); stages.push({ id, name: '新規ステージ', concept: '', description: '', tags: [], enemy: '', ally: '', required: 3, rules: [], avatar: { enabled: false, name: '', description: '' }, ...meta({ collection: state.filter.collection, visibility: 'staff' }) }); state.selected.stage = id; state.section.stage = 'basic'; }
        render();
      },
      'read-import': () => { try { state.imported = readCharacter(JSON.parse(state.importText)); } catch (error) { alert(`JSON解析エラー：${error.message}`); } render(); },
      'create-import': () => {
        const { fields, profile } = state.imported;
        const id = newId('U');
        if (profile) fields.patterns = [{ id: 'BP-1', name: 'インポートしたパターン', note: '', default: true, steps: stepsOf(profile) }];
        units.push({ id, allow_ally: false, allow_enemy: true, ...fields, ...meta({ visibility: 'staff' }) });
        state.selected.unit = id; state.imported = null; state.scene = 'edit'; state.section.unit = 'basic'; render();
      },
      'member-copy': () => update(f => { const m = f.members[index]; const u = unitOf(m.unit); const src = u.patterns.find(p => p.id === m.pattern) || defaultPattern(u); const copy = { ...clone(src), id: `BP-${u.patterns.length + 1}`, name: `${src.name}（${f.name}）`, default: false }; u.patterns.push(copy); m.pattern = copy.id; alert(`「${copy.name}」を${u.name}のパターンとして作成し、この枠に設定。続けてチャートエディターを表示。`); }),
      'add-member': () => update(f => f.members.push({ unit: '', count: 1, pattern: '' })),
      'remove-member': () => update(f => f.members.splice(index, 1)),
      'add-rule': () => update(s => s.rules.push({ type: 'SPEED_ROLL_MOD', scope: 'ALLY', value: 0, display_name: '', description: '' })),
      'remove-rule': () => update(s => s.rules.splice(index, 1)),
      save: () => update(r => { r.revision += 1; }),
      restore: () => update(r => { r.revision += 1; alert('選んだ版の内容で、新しい版として保存。'); }),
      deprecate: () => update(r => { r.deprecated = true; }),
      undeprecate: () => update(r => { r.deprecated = false; }),
      delete: () => { if (confirm('削除すると元に戻せない。削除する？')) { const list = tables[state.tab]; list.splice(list.indexOf(current()), 1); render(); } },
      deploy: () => alert(`「${current().name}」をルーム「テスト卓」へ配置。${state.tab === 'stage' ? 'ステージの敵編成・フィールド効果を一括で設定。' : state.tab === 'formation' ? '編成のメンバーを、選択中のパターンで配置。' : 'ユニット1体を配置（敵なら既定パターン）。'}`),
      export: () => alert('選んだ範囲を unit_export_*.json として保存。'),
      'pick-io-file': () => { state.io.file = true; render(); },
      'run-import': () => { state.io.file = null; if (mantis) mantis.revision += 1; alert('取り込み完了：新規1件・上書き2件'); render(); },
    };
    actions[target.dataset.action]?.();
  });
  app.addEventListener('change', event => {
    const el = event.target, d = el.dataset;
    if (d.filter) { state.filter[d.filter] = el.type === 'checkbox' ? el.checked : el.value; render(); return; }
    if (d.ioScope) { state.io.scope = d.ioScope; render(); return; }
    if (d.ioDeprecated !== undefined) { state.io.deprecated = el.checked; render(); return; }
    if (d.add) {
      const id = el.value.trim().split(/\s/)[0];
      const table = { skill: DATA.skills, passive: DATA.passives, radiance: DATA.radiance, item: DATA.items }[d.add];
      if (!table[id]) { el.setCustomValidity('マスター未登録のIDです'); el.reportValidity(); return; }
      update(c => {
        if (d.add === 'skill') { if (!c.skills.some(row => row.id === id)) c.skills.push({ id, name: '', hidden: false }); }
        else if (d.add === 'item') c.items.push({ id, count: 1 });
        else { const list = d.add === 'passive' ? c.passives : c.radiance; if (!list.includes(id)) list.push(id); }
      });
      return;
    }
    if (d.field === 'import') { state.importText = el.value; return; }
    if (d.field === 'other') return update(c => { c.other = el.value.split('\n').map(t => t.trim()).filter(Boolean); });
    if (d.field) return update(c => { c[d.field] = el.type === 'checkbox' ? el.checked : el.type === 'number' ? Number(el.value) : el.value; });
    if (d.vis) return update(c => { c.visibility = d.vis; });
    if (d.state) return update(c => { c.states[d.state] = Number(el.value); });
    if (d.param) return update(c => { c.params.find(row => row.label === d.param).value = Number(el.value); });
    if (d.skillName !== undefined) return update(c => { c.skills[Number(d.skillName)].name = el.value.trim(); });
    if (d.skillHidden !== undefined) return update(c => { c.skills[Number(d.skillHidden)].hidden = el.checked; });
    if (d.itemCount !== undefined) return update(c => { c.items[Number(d.itemCount)].count = Number(el.value); });
    if (d.behavior) return update(c => { c.behavior[d.behavior] = el.checked; });
    if (d.slot) return update(c => { c.behavior.slot_mode = d.slot; });
    if (d.memberUnit !== undefined) return update(f => { Object.assign(f.members[Number(d.memberUnit)], { unit: el.value, pattern: '' }); });
    if (d.memberCount !== undefined) return update(f => { f.members[Number(d.memberCount)].count = Number(el.value); });
    if (d.memberPattern !== undefined) return update(f => { f.members[Number(d.memberPattern)].pattern = el.value; });
    if (d.rule) { const [i, key] = d.rule.split(':'); return update(s => { s.rules[Number(i)][key] = el.type === 'number' ? Number(el.value) : el.value; }); }
    if (d.avatar) return update(s => { s.avatar[d.avatar] = el.type === 'checkbox' ? el.checked : el.value; });
  });
  app.addEventListener('input', event => {
    if (event.target.dataset.field === 'import') state.importText = event.target.value;
  });

  // ---- 見比べの切り替え：誰が開いたか ----
  const panel = document.createElement('aside');
  panel.className = 'proto-panel';
  panel.innerHTML = `<details open><summary>試作の切替</summary><div>
    <label>閲覧者<select data-proto="viewer"><option value="author">制作者（ロビーから）</option><option value="roomgm">ルームのGM（制作者でない・ルームから）</option><option value="player">一般（ロビーから）</option></select></label></div></details>`;
  document.body.appendChild(panel);
  for (const select of panel.querySelectorAll('select')) {
    root.dataset[select.dataset.proto] = select.value;
    select.addEventListener('change', () => { root.dataset[select.dataset.proto] = select.value; state.scene = 'edit'; render(); });
  }
  render();
})();
