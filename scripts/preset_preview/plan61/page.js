// 計画61の試作：全プリセット管理のキャラの画面を、生の JSON の欄から項目のフォームに替えた形。
// DATA（build.mjs が埋める）：skills・passives・items・radiance・presets（data/cache/ の本物のデータ）。
(function () {
  'use strict';
  const root = document.documentElement;
  const app = document.getElementById('app');
  const h = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const STATES = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘'];
  const TARGETS = { target_enemy_random: '敵ランダム', target_enemy_fastest: '敵最速', target_enemy_slowest: '敵最遅', target_ally_random: '味方ランダム', target_self: '自身' };
  const SECTIONS = [['basic', '基本情報'], ['status', 'ステータス'], ['params', 'パラメータ'], ['skills', 'スキル'], ['gear', 'パッシブ・輝化スキル・アイテム'], ['behavior', '行動設定'], ['patterns', '行動パターン']];
  const USED = new Set(['name', 'image', 'status', 'params', 'states', 'commands', 'SPassive', 'inventory', 'radiance_skills', 'hidden_skills', 'special_buffs', 'tag_ids', 'disabled_tag_ids', 'flags', 'hp', 'maxHp', 'mp', 'maxMp', 'characterType', 'isNPC', 'gmOnly']);
  const SKILL_RE = /【\s*([A-Za-z]+-\d+)\s*([^】]*)】/;

  // ---- 今の JSON → 項目（「JSON から取り込む」の読み取りと同じ） ----
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

  // ---- 試作の中のデータ ----
  const characters = DATA.presets.map(row => ({ id: row.id, allow_ally: row.allow_ally, allow_enemy: row.allow_enemy, ...readCharacter(row.json).fields }));
  const mantis = characters.find(row => row.id === 'TEST_3');
  if (mantis) mantis.patterns = [
    { id: 'BP-1', name: '通常', note: '坑道入口の通常戦闘', default: true, steps: [['E-26'], ['E-28'], ['E-27'], ['E-28'], ['E-30']].map(actions => ({ actions, target: 'target_enemy_random' })) },
    { id: 'BP-2', name: 'ボス戦', note: '最深部。HP50%未満で「本気」ループへ移行', default: false, steps: [{ actions: ['E-29'], target: 'target_enemy_fastest' }, { actions: ['E-23', 'E-30'], target: 'target_enemy_random' }, { actions: ['E-26'], target: 'target_enemy_slowest' }] },
  ];
  const formations = [
    { id: 'EF-坑道', name: '坑道の番人', members: [{ char: 'TEST_3', count: 1, pattern: '' }, { char: 'TEST_2', count: 2, pattern: '' }] },
    { id: 'EF-最深部', name: '最深部のボス', members: [{ char: 'TEST_3', count: 1, pattern: 'BP-2' }] },
  ];
  const sample = (() => {
    const base = JSON.parse(JSON.stringify(DATA.presets.find(row => row.id === 'TEST_3')?.json || { data: {} }));
    base.data.memo = 'CharaCreator のメモ';
    base.data.color = '#888888';
    base.data.iconUrl = 'https://example.com/icon.png';
    base.data.commands += '\n1d100 【幸運の判定】\n:HP-{出血}';
    base.data.flags = { behavior_profile: { enabled: true, initial_loop_id: 'loop_1', loops: { loop_1: { repeat: true, steps: [{ actions: ['E-26'], targets: ['target_enemy_random'] }, { actions: ['E-30'], targets: ['target_enemy_random'] }] } } } };
    return JSON.stringify(base, null, 2);
  })();

  const state = { selected: mantis ? mantis.id : characters[0].id, section: 'skills', imported: null, importText: sample };
  const current = () => characters.find(row => row.id === state.selected);
  const skillName = id => DATA.skills[id]?.name || '（マスター未登録）';
  const usedBy = (char, patternId) => formations.filter(f => f.members.some(m => m.char === char.id && (patternId === undefined || (m.pattern || defaultPattern(char)?.id) === patternId)));
  const defaultPattern = char => char.patterns.find(p => p.default) || null;

  // ---- 検査（保存の前に出す） ----
  function problems(char) {
    const out = [];
    const own = new Set(char.skills.map(row => row.id));
    for (const row of char.skills) if (!DATA.skills[row.id]) out.push(['error', `スキル ${row.id}：マスター未登録`]);
    for (const id of char.passives) if (!DATA.passives[id]) out.push(['error', `パッシブ ${id}：マスター未登録`]);
    for (const pattern of char.patterns) pattern.steps.forEach((step, index) => step.actions.forEach(id => {
      if (!own.has(id)) out.push(['error', `パターン「${pattern.name}」ステップ${index + 1}：未所持スキル ${id}`]);
    }));
    if (char.allow_enemy && !char.patterns.length && char.skills.length) out.push(['note', '行動パターン未設定：使用可能スキルから自動選択']);
    return out;
  }
  const paletteLine = row => {
    const master = DATA.skills[row.id];
    if (!master) return `【${row.id}】`;
    return row.name ? master.palette.replace(SKILL_RE, `【${row.id} ${row.name}】`) : master.palette;
  };

  // ---- 描く ----
  const button = (label, action, extra = '', attrs = '') => `<button type="button" class="btn ${extra}" data-action="${action}" ${attrs}>${label}</button>`;
  const chips = (ids, table, kind) => `<div class="chips">${ids.map((id, index) => `<span class="chip"><code>${h(id)}</code>${h(table[id]?.name || '（マスター未登録）')}<button type="button" aria-label="${h(id)} を削除" data-action="remove-${kind}" data-index="${index}">×</button></span>`).join('') || '<span class="muted">なし</span>'}
    <label class="adder"><input list="list-${kind}" placeholder="追加（ID・名称で検索）" data-add="${kind}"><datalist id="list-${kind}">${Object.entries(table).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}</option>`).join('')}</datalist></label></div>`;

  function sectionBody(key, char) {
    if (key === 'basic') return `<div class="grid2">
      <label class="field">キャラクター名<input value="${h(char.name)}" data-field="name"></label>
      <label class="field">画像URL<input value="${h(char.image)}" placeholder="https://…" data-field="image"></label></div>
      <fieldset class="field"><legend>キャラ区分</legend><label class="check"><input type="checkbox" ${char.allow_ally ? 'checked' : ''} data-field="allow_ally">味方キャラクター</label><label class="check"><input type="checkbox" ${char.allow_enemy ? 'checked' : ''} data-field="allow_enemy">敵キャラクター</label></fieldset>
      <label class="check"><input type="checkbox" ${char.scenario ? 'checked' : ''} data-field="scenario">シナリオキャラクター（輝化予算・タグ制限の対象外）</label>
      <label class="check"><input type="checkbox" ${char.gm_only ? 'checked' : ''} data-field="gm_only">GM限定表示</label>
      <div class="field"><span>タグ</span><div class="chips">${char.tags.map(t => `<span class="chip">${h(t)}</span>`).join('') || '<span class="muted">なし</span>'}<span class="muted">（既存タグから選択）</span></div></div>
      <p class="muted small">公開範囲・コレクション・区分は既存の詳細欄で設定。</p>`;
    if (key === 'status') return `<div class="grid2">
      <label class="field">最大HP<input type="number" value="${char.hp}" data-field="hp"></label>
      <label class="field">最大MP<input type="number" value="${char.mp}" data-field="mp"></label></div>
      <h4>初期状態</h4><div class="grid6">${STATES.map(label => `<label class="field">${label}<input type="number" value="${char.states[label]}" data-state="${label}"></label>`).join('')}</div>
      <p class="muted small">戦闘開始時の値。HP・MPは最大値で開始。</p>`;
    if (key === 'params') {
      const groups = [['能力値', row => !/補正$/.test(row.label) && char.params.indexOf(row) < 8], ['補正', row => /補正$/.test(row.label)], ['技能・その他', row => !/補正$/.test(row.label) && char.params.indexOf(row) >= 8]];
      return groups.map(([title, test]) => `<h4>${title}</h4><div class="grid6">${char.params.filter(test).map(row => `<label class="field">${h(row.label)}<input type="number" value="${row.value}" data-param="${h(row.label)}"></label>`).join('') || '<span class="muted">なし</span>'}</div>`).join('');
    }
    if (key === 'skills') {
      const list = root.dataset.skills === 'card'
        ? `<div class="skill-cards">${char.skills.map((row, index) => { const m = DATA.skills[row.id]; return `<article class="skill-card ${m ? '' : 'is-bad'}">
            <header><code>${h(row.id)}</code><strong>${h(m?.name || '（マスター未登録）')}</strong><span class="tag">${h(m?.category || '')}</span>${button('×', 'remove-skill', 'btn-icon', `data-index="${index}" aria-label="${h(row.id)} を削除"`)}</header>
            <label class="field">固有名称<input value="${h(row.name)}" placeholder="${h(m?.name || '')}" data-skill-name="${index}"></label>
            <p class="palette">${h(paletteLine(row))}</p>
            <p class="muted small">${h(m?.cost || '')} ${h((m?.text || '').replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1').slice(0, 60))}</p>
            <label class="check small"><input type="checkbox" ${row.hidden ? 'checked' : ''} data-skill-hidden="${index}">非公開</label></article>`; }).join('')}</div>`
        : `<table class="skill-table"><thead><tr><th>ID</th><th>マスター名称</th><th>固有名称</th><th>チャットパレット（配置時）</th><th>非公開</th><th></th></tr></thead><tbody>${char.skills.map((row, index) => `<tr class="${DATA.skills[row.id] ? '' : 'is-bad'}">
            <td><code>${h(row.id)}</code></td><td>${h(skillName(row.id))}</td>
            <td><input value="${h(row.name)}" placeholder="マスター名称" data-skill-name="${index}" aria-label="${h(row.id)} の固有名称"></td>
            <td class="palette">${h(paletteLine(row))}</td>
            <td><input type="checkbox" ${row.hidden ? 'checked' : ''} data-skill-hidden="${index}" aria-label="${h(row.id)} を非公開"></td>
            <td>${button('×', 'remove-skill', 'btn-icon', `data-index="${index}" aria-label="${h(row.id)} を削除"`)}</td></tr>`).join('')}</tbody></table>`;
      return `${list}<label class="adder wide"><input list="list-skill" placeholder="スキル追加（ID・名称で検索。例：E-29）" data-add="skill"><datalist id="list-skill">${Object.entries(DATA.skills).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}（${h(row.category)}）</option>`).join('')}</datalist></label>
        <p class="muted small">チャットパレットは保存せず、配置時にマスターから生成。固有名称が空欄ならマスター名称。</p>
        <h4>その他のパレット行</h4><textarea rows="3" data-field="other" placeholder="1d100 【幸運の判定】">${h(char.other.join('\n'))}</textarea>`;
    }
    if (key === 'gear') return `<h4>パッシブ</h4>${chips(char.passives, DATA.passives, 'passive')}
      <h4>輝化スキル</h4>${chips(char.radiance, DATA.radiance, 'radiance')}
      <h4>アイテム</h4><div class="chips">${char.items.map((row, index) => `<span class="chip"><code>${h(row.id)}</code>${h(DATA.items[row.id]?.name || '（マスター未登録）')}<input type="number" min="1" value="${row.count}" data-item-count="${index}" aria-label="個数">個<button type="button" aria-label="削除" data-action="remove-item" data-index="${index}">×</button></span>`).join('') || '<span class="muted">なし</span>'}
        <label class="adder"><input list="list-item" placeholder="追加（ID・名称で検索）" data-add="item"><datalist id="list-item">${Object.entries(DATA.items).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}</option>`).join('')}</datalist></label></div>`;
    if (key === 'behavior') {
      const b = char.behavior;
      return `<p class="muted small">敵キャラクター時のみ有効。</p>
        <label class="check"><input type="checkbox" ${b.auto_target ? 'checked' : ''} data-behavior="auto_target">対象の自動選択</label>
        <label class="check"><input type="checkbox" ${b.auto_skill ? 'checked' : ''} data-behavior="auto_skill">スキルの自動選択</label>
        <label class="check"><input type="checkbox" ${b.show_planned ? 'checked' : ''} data-behavior="show_planned">予定スキルの公開</label>
        <fieldset class="field"><legend>行動スロット</legend><label class="check"><input type="radio" name="slot" ${b.slot_mode === 'normal' ? 'checked' : ''} data-slot="normal">通常</label><label class="check"><input type="radio" name="slot" ${b.slot_mode === 'none' ? 'checked' : ''} data-slot="none">行動なし（瓦礫などの設置物）</label></fieldset>
        <div class="field"><span>スキルの制約</span><div class="muted small">${b.constraints.length ? `${b.constraints.length}件` : 'なし'}　<em>（仕様はPR詳細で決定）</em></div></div>`;
    }
    if (key === 'patterns') return patternsBody(char);
    return '';
  }

  function patternsBody(char) {
    if (!char.allow_enemy) return '<p class="muted">キャラ区分で「敵キャラクター」を選択すると作成可能。</p>';
    const own = new Set(char.skills.map(row => row.id));
    const cards = char.patterns.map((p, index) => `<article class="pattern ${p.default ? 'is-default' : ''}">
      <header><strong>${h(p.name)}</strong>${p.default ? '<span class="badge">既定</span>' : ''}<span class="muted small">${h(p.id)}</span></header>
      <p class="muted small">${h(p.note || '')}</p>
      <ol class="steps">${p.steps.map(step => `<li>${step.actions.map(id => `<span class="step-skill ${own.has(id) ? '' : 'is-bad'}"><code>${h(id)}</code>${h(skillName(id))}</span>`).join('<span class="plus">＋</span>')}<span class="muted small">→ ${h(TARGETS[step.target] || step.target)}</span></li>`).join('')}</ol>
      <p class="small">使用中の編成：${usedBy(char, p.id).map(f => h(f.name)).join('・') || '<span class="muted">なし</span>'}</p>
      <footer>${button('チャート編集', 'open-chart')}${button('複製', 'copy-pattern', '', `data-index="${index}"`)}${p.default ? '' : button('既定に設定', 'make-default', '', `data-index="${index}"`)}${button('他キャラへ複製…', 'copy-other')}${button('削除', 'delete-pattern', 'btn-danger', `data-index="${index}" ${p.default && char.patterns.length > 1 ? 'disabled title="他のパターンを既定に設定してから削除"' : ''}`)}</footer>
    </article>`).join('');
    return `${cards || '<p class="muted">パターン未作成。使用可能スキルから自動選択で行動。</p>'}
      ${button('＋ パターン追加', 'new-pattern', 'btn-primary')}
      <p class="muted small">最初のパターンが既定。編成で未指定の場合に使用。</p>`;
  }

  function preview(char) {
    const list = problems(char);
    return `<h3>確認</h3>
      <section><h4>チャットパレット（配置時）</h4><pre class="palette-box">${h([...char.skills.map(paletteLine), ...char.other].join('\n') || '（なし）')}</pre></section>
      <section><h4>保存前チェック</h4>${list.length ? `<ul class="problems">${list.map(([kind, text]) => `<li class="is-${kind}">${h(text)}</li>`).join('')}</ul>` : '<p class="ok">問題なし</p>'}</section>
      <section><h4>使用中の編成</h4>${usedBy(char).map(f => `<p class="small">${h(f.name)}：${f.members.filter(m => m.char === char.id).map(m => h((char.patterns.find(p => p.id === m.pattern) || defaultPattern(char))?.name || '自動選択')).join('、')}</p>`).join('') || '<p class="muted small">なし</p>'}</section>
      <details><summary>保存データ（参考）</summary><pre class="json">${h(JSON.stringify({ ...char, patterns: char.patterns.map(p => ({ id: p.id, name: p.name, default: p.default })) }, null, 2))}</pre></details>`;
  }

  function editScene() {
    const char = current();
    const layout = root.dataset.layout;
    const nav = `<nav class="toc" aria-label="節">${SECTIONS.map(([key, label]) => {
      const bad = key === 'skills' && char.skills.some(row => !DATA.skills[row.id]) || key === 'patterns' && problems(char).some(([k, t]) => k === 'error' && t.startsWith('パターン'));
      return `<button type="button" data-section="${key}" aria-current="${layout === 'toc' && state.section === key}">${label}${key === 'patterns' && char.allow_enemy ? ` <small>${char.patterns.length}</small>` : ''}${bad ? ' <span class="dot" title="エラーあり">●</span>' : ''}</button>`;
    }).join('')}<hr><button type="button" data-action="go-import">JSONインポート</button></nav>`;
    const body = layout === 'toc'
      ? `<section class="sec"><h3>${SECTIONS.find(([key]) => key === state.section)[1]}</h3>${sectionBody(state.section, char)}</section>`
      : SECTIONS.map(([key, label]) => `<section class="sec" id="sec-${key}"><h3>${label}</h3>${sectionBody(key, char)}</section>`).join('');
    return `<div class="editor"><div class="editbar">${button('← 一覧', 'noop')}<strong><code>${h(char.id)}</code> ${h(char.name)}</strong>${char.allow_ally ? '<span class="tag">味方</span>' : ''}${char.allow_enemy ? '<span class="tag tag-enemy">敵</span>' : ''}</div>
      <div class="edit-grid">${nav}<div class="edit-input">${body}</div><aside class="edit-preview">${preview(char)}</aside></div>
      <footer class="editfoot"><small class="muted">所有者が直接保存（承認不要）</small>${button('保存', 'noop', 'btn-primary')}</footer></div>`;
  }

  function importScene() {
    const result = state.imported;
    return `<div class="editor"><div class="editbar">${button('← 編集', 'go-edit')}<strong>JSONインポート</strong></div>
      <div class="import-grid"><section class="sec"><h3>JSON入力</h3><p class="muted small">CharaCreator出力・既存プリセットの書き出しに対応。新規作成・移行共通の入口。</p>
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
        <div class="row">${button('新規作成', 'create-import', 'btn-primary')}${button('選択中のキャラクターを上書き', 'noop')}</div>` : '<p class="muted">「解析」で各項目への割り当てを表示。</p>'}</section></div></div>`;
  }

  function formationScene() {
    return `<div class="editor"><div class="editbar"><strong>敵編成</strong><span class="muted small">メンバーごとに行動パターンを選択（コピーは保持しない）</span></div>
      <div class="formations">${formations.map((f, fi) => `<section class="sec"><h3>${h(f.name)} <span class="muted small">${h(f.id)}</span></h3>
        <table class="members"><thead><tr><th>キャラクター</th><th>数</th><th>行動パターン</th><th></th></tr></thead><tbody>${f.members.map((m, mi) => {
          const char = characters.find(row => row.id === m.char);
          const options = char.patterns.length
            ? `<option value="" ${m.pattern ? '' : 'selected'}>既定（${h(defaultPattern(char).name)}）</option>${char.patterns.map(p => `<option value="${p.id}" ${m.pattern === p.id ? 'selected' : ''}>${h(p.name)}</option>`).join('')}`
            : '<option>パターンなし（自動選択）</option>';
          return `<tr><td><code>${h(char.id)}</code> ${h(char.name)}</td><td>${m.count}</td>
            <td><select data-member="${fi}:${mi}" ${char.patterns.length ? '' : 'disabled'}>${options}</select></td>
            <td>${char.patterns.length ? button('複製して編集', 'member-copy', '', `data-member="${fi}:${mi}"`) : button('パターン作成', 'member-new', '', `data-member="${fi}:${mi}"`)}</td></tr>`;
        }).join('')}</tbody></table></section>`).join('')}</div>
      <p class="muted small pad">パターンの変更は、使用中のすべての編成に反映。編成固有の調整は「複製して編集」で別パターンとして作成。</p></div>`;
  }

  function render() {
    const scene = root.dataset.scene;
    app.innerHTML = `<div class="ws"><header class="ws-head"><div><h2>プリセット管理</h2><p class="muted small">計画61 試作：キャラクター編集フォーム・行動パターン管理</p></div></header>
      <nav class="ws-tabs">${[['edit', 'キャラクター'], ['formation', '編成'], ['stage', 'ステージ']].map(([key, label]) => `<button type="button" data-scene="${key}" aria-selected="${scene === key || (key === 'edit' && scene === 'import')}" ${key === 'stage' ? 'disabled' : ''}>${label}</button>`).join('')}</nav>
      <div class="ws-body">${scene === 'formation' ? '' : `<aside class="ws-list">${characters.map(row => `<button type="button" class="rec" data-select="${row.id}" aria-current="${row.id === state.selected}"><code>${h(row.id)}</code><strong>${h(row.name)}</strong><span>${row.allow_ally ? '<span class="tag">味方</span>' : ''}${row.allow_enemy ? '<span class="tag tag-enemy">敵</span>' : ''}${row.allow_enemy ? `<span class="muted small">パターン ${row.patterns.length}</span>` : ''}</span></button>`).join('')}</aside>`}
      <main class="ws-main">${scene === 'import' ? importScene() : scene === 'formation' ? formationScene() : editScene()}</main></div></div>`;
  }

  // ---- 操作 ----
  const update = fn => { fn(current()); render(); };
  app.addEventListener('click', event => {
    const target = event.target.closest('button');
    if (!target || target.disabled) return;
    const char = current(), index = Number(target.dataset.index);
    if (target.dataset.scene) { root.dataset.scene = target.dataset.scene; render(); return; }
    if (target.dataset.select) { state.selected = target.dataset.select; if (root.dataset.scene === 'import') root.dataset.scene = 'edit'; render(); return; }
    if (target.dataset.section) {
      state.section = target.dataset.section;
      if (root.dataset.layout === 'toc') render(); else document.getElementById(`sec-${state.section}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const action = target.dataset.action;
    const actions = {
      'remove-skill': () => update(c => c.skills.splice(index, 1)),
      'remove-passive': () => update(c => c.passives.splice(index, 1)),
      'remove-radiance': () => update(c => c.radiance.splice(index, 1)),
      'remove-item': () => update(c => c.items.splice(index, 1)),
      'make-default': () => update(c => c.patterns.forEach((p, i) => { p.default = i === index; })),
      'delete-pattern': () => update(c => { const [gone] = c.patterns.splice(index, 1); if (gone.default && c.patterns[0]) c.patterns[0].default = true; }),
      'copy-pattern': () => update(c => c.patterns.push({ ...JSON.parse(JSON.stringify(c.patterns[index])), id: `BP-${Date.now() % 1000}`, name: `${c.patterns[index].name}（コピー）`, default: false })),
      'new-pattern': () => update(c => c.patterns.push({ id: `BP-${Date.now() % 1000}`, name: `パターン${c.patterns.length + 1}`, note: '', default: !c.patterns.length, steps: c.skills.slice(0, 2).map(row => ({ actions: [row.id], target: 'target_enemy_random' })) })),
      'open-chart': () => alert('既存の行動チャートエディター（behavior_flow_editor_modal.js）でこのパターンを編集。'),
      'copy-other': () => alert('複製先キャラクターを選択。未所持スキルがあれば一覧表示し、置換か削除を選択。'),
      'go-import': () => { root.dataset.scene = 'import'; render(); },
      'go-edit': () => { root.dataset.scene = 'edit'; render(); },
      'read-import': () => { try { state.imported = readCharacter(JSON.parse(state.importText)); } catch (error) { alert(`JSON解析エラー：${error.message}`); } render(); },
      'create-import': () => {
        const { fields, profile } = state.imported;
        const id = `NEW_${characters.length + 1}`;
        if (profile) fields.patterns = [{ id: 'BP-取込', name: 'インポートしたパターン', note: '', default: true, steps: stepsOf(profile) }];
        characters.push({ id, allow_ally: false, allow_enemy: true, ...fields });
        state.selected = id; state.imported = null; root.dataset.scene = 'edit'; state.section = 'skills'; render();
      },
      'member-copy': () => { const [fi, mi] = target.dataset.member.split(':').map(Number); const m = formations[fi].members[mi]; const c = characters.find(row => row.id === m.char); const src = c.patterns.find(p => p.id === m.pattern) || defaultPattern(c); const copy = { ...JSON.parse(JSON.stringify(src)), id: `BP-${Date.now() % 1000}`, name: `${src.name}（${formations[fi].name}）`, default: false }; c.patterns.push(copy); m.pattern = copy.id; render(); alert(`「${copy.name}」を${c.name}のパターンとして作成し、この枠に設定。続けてチャートエディターを表示。`); },
      'member-new': () => alert('キャラクター編集の「行動パターン」を表示。'),
    };
    actions[action]?.();
  });
  app.addEventListener('change', event => {
    const el = event.target, char = current(), d = el.dataset;
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
    if (d.member) { const [fi, mi] = d.member.split(':').map(Number); formations[fi].members[mi].pattern = el.value; render(); return; }
    if (d.field === 'import') { state.importText = el.value; return; }
    if (d.field === 'other') return update(c => { c.other = el.value.split('\n').map(t => t.trim()).filter(Boolean); });
    if (d.field) return update(c => { c[d.field] = el.type === 'checkbox' ? el.checked : el.type === 'number' ? Number(el.value) : el.value; });
    if (d.state) return update(c => { c.states[d.state] = Number(el.value); });
    if (d.param) return update(c => { c.params.find(row => row.label === d.param).value = Number(el.value); });
    if (d.skillName !== undefined) return update(c => { c.skills[Number(d.skillName)].name = el.value.trim(); });
    if (d.skillHidden !== undefined) return update(c => { c.skills[Number(d.skillHidden)].hidden = el.checked; });
    if (d.itemCount !== undefined) return update(c => { c.items[Number(d.itemCount)].count = Number(el.value); });
    if (d.behavior) return update(c => { c.behavior[d.behavior] = el.checked; });
    if (d.slot) return update(c => { c.behavior.slot_mode = d.slot; });
  });
  app.addEventListener('input', event => { if (event.target.dataset.field === 'import') state.importText = event.target.value; });

  // ---- 見比べの切り替え ----
  const panel = document.createElement('aside');
  panel.className = 'proto-panel';
  panel.innerHTML = `<details open><summary>試作の切替</summary><div>
    <label>レイアウト<select data-proto="layout"><option value="toc">目次＋1セクション（管理画面と同様）</option><option value="long">全セクションを縦に表示</option></select></label>
    <label>スキル表示<select data-proto="skills"><option value="table">表形式</option><option value="card">カード形式（コスト・効果つき）</option></select></label></div></details>`;
  document.body.appendChild(panel);
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('plan61-proto') || '{}'); } catch (e) { /* 覚えなくてよい */ }
  for (const select of panel.querySelectorAll('select')) {
    const key = select.dataset.proto;
    if (saved[key]) select.value = saved[key];
    root.dataset[key] = select.value;
    select.addEventListener('change', () => { root.dataset[key] = select.value; saved[key] = select.value; try { localStorage.setItem('plan61-proto', JSON.stringify(saved)); } catch (e) { /* 覚えなくてよい */ } render(); });
  }
  render();
})();
