// 計画61の試作：全プリセット管理のキャラの画面を、生の JSON の欄から項目のフォームに替えた形。
// DATA（build.mjs が埋める）：skills・passives・items・radiance・presets（data/cache/ の本物のデータ）。
(function () {
  'use strict';
  const root = document.documentElement;
  const app = document.getElementById('app');
  const h = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const STATES = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘'];
  const TARGETS = { target_enemy_random: '敵をランダム', target_enemy_fastest: '敵の最速', target_enemy_slowest: '敵の最遅', target_ally_random: '味方をランダム', target_self: '自分' };
  const SECTIONS = [['basic', '基本'], ['status', 'ステータス'], ['params', 'パラメータ'], ['skills', 'スキル'], ['gear', 'パッシブ・輝化・アイテム'], ['behavior', '行動の設定'], ['patterns', '行動パターン']];
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
    { id: 'BP-1', name: '通常', note: '坑道の入口で出るとき', default: true, steps: [['E-26'], ['E-28'], ['E-27'], ['E-28'], ['E-30']].map(actions => ({ actions, target: 'target_enemy_random' })) },
    { id: 'BP-2', name: 'ボス戦・HP半分から本気', note: '最深部。HPが50%を切ると「本気」のループへ移る', default: false, steps: [{ actions: ['E-29'], target: 'target_enemy_fastest' }, { actions: ['E-23', 'E-30'], target: 'target_enemy_random' }, { actions: ['E-26'], target: 'target_enemy_slowest' }] },
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
  const skillName = id => DATA.skills[id]?.name || '（マスターに無い）';
  const usedBy = (char, patternId) => formations.filter(f => f.members.some(m => m.char === char.id && (patternId === undefined || (m.pattern || defaultPattern(char)?.id) === patternId)));
  const defaultPattern = char => char.patterns.find(p => p.default) || null;

  // ---- 検査（保存の前に出す） ----
  function problems(char) {
    const out = [];
    const own = new Set(char.skills.map(row => row.id));
    for (const row of char.skills) if (!DATA.skills[row.id]) out.push(['error', `スキル ${row.id} はマスターに無い`]);
    for (const id of char.passives) if (!DATA.passives[id]) out.push(['error', `パッシブ ${id} はマスターに無い`]);
    for (const pattern of char.patterns) pattern.steps.forEach((step, index) => step.actions.forEach(id => {
      if (!own.has(id)) out.push(['error', `パターン「${pattern.name}」の${index + 1}手目の ${id} を、このキャラが持っていない`]);
    }));
    if (char.allow_enemy && !char.patterns.length && char.skills.length) out.push(['note', '行動パターンが無いので、敵のときは使えるスキルから自動で選ぶ']);
    return out;
  }
  const paletteLine = row => {
    const master = DATA.skills[row.id];
    if (!master) return `【${row.id}】`;
    return row.name ? master.palette.replace(SKILL_RE, `【${row.id} ${row.name}】`) : master.palette;
  };

  // ---- 描く ----
  const button = (label, action, extra = '', attrs = '') => `<button type="button" class="btn ${extra}" data-action="${action}" ${attrs}>${label}</button>`;
  const chips = (ids, table, kind) => `<div class="chips">${ids.map((id, index) => `<span class="chip"><code>${h(id)}</code>${h(table[id]?.name || '（マスターに無い）')}<button type="button" aria-label="${h(id)} を外す" data-action="remove-${kind}" data-index="${index}">×</button></span>`).join('') || '<span class="muted">なし</span>'}
    <label class="adder"><input list="list-${kind}" placeholder="ID か名前で足す" data-add="${kind}"><datalist id="list-${kind}">${Object.entries(table).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}</option>`).join('')}</datalist></label></div>`;

  function sectionBody(key, char) {
    if (key === 'basic') return `<div class="grid2">
      <label class="field">名前<input value="${h(char.name)}" data-field="name"></label>
      <label class="field">画像の URL<input value="${h(char.image)}" placeholder="https://…" data-field="image"></label></div>
      <fieldset class="field"><legend>使い道</legend><label class="check"><input type="checkbox" ${char.allow_ally ? 'checked' : ''} data-field="allow_ally">味方に使う</label><label class="check"><input type="checkbox" ${char.allow_enemy ? 'checked' : ''} data-field="allow_enemy">敵に使う</label></fieldset>
      <label class="check"><input type="checkbox" ${char.scenario ? 'checked' : ''} data-field="scenario">シナリオのキャラ（輝化スキルの予算とタグの決まりを当てない）</label>
      <label class="check"><input type="checkbox" ${char.gm_only ? 'checked' : ''} data-field="gm_only">GM だけに見せる</label>
      <div class="field"><span>タグ</span><div class="chips">${char.tags.map(t => `<span class="chip">${h(t)}</span>`).join('') || '<span class="muted">なし</span>'}<span class="muted">（今のタグの候補から選ぶ）</span></div></div>
      <p class="muted small">公開範囲・コレクション・区分は、今の詳細の欄のまま。</p>`;
    if (key === 'status') return `<div class="grid2">
      <label class="field">HP（最大）<input type="number" value="${char.hp}" data-field="hp"></label>
      <label class="field">MP（最大）<input type="number" value="${char.mp}" data-field="mp"></label></div>
      <h4>初期の状態</h4><div class="grid6">${STATES.map(label => `<label class="field">${label}<input type="number" value="${char.states[label]}" data-state="${label}"></label>`).join('')}</div>
      <p class="muted small">戦闘の始めの値。HP・MP は最大の値から始まる。</p>`;
    if (key === 'params') {
      const groups = [['能力値', row => !/補正$/.test(row.label) && char.params.indexOf(row) < 8], ['補正', row => /補正$/.test(row.label)], ['技能・そのほか', row => !/補正$/.test(row.label) && char.params.indexOf(row) >= 8]];
      return groups.map(([title, test]) => `<h4>${title}</h4><div class="grid6">${char.params.filter(test).map(row => `<label class="field">${h(row.label)}<input type="number" value="${row.value}" data-param="${h(row.label)}"></label>`).join('') || '<span class="muted">なし</span>'}</div>`).join('');
    }
    if (key === 'skills') {
      const list = root.dataset.skills === 'card'
        ? `<div class="skill-cards">${char.skills.map((row, index) => { const m = DATA.skills[row.id]; return `<article class="skill-card ${m ? '' : 'is-bad'}">
            <header><code>${h(row.id)}</code><strong>${h(m?.name || '（マスターに無い）')}</strong><span class="tag">${h(m?.category || '')}</span>${button('×', 'remove-skill', 'btn-icon', `data-index="${index}" aria-label="${h(row.id)} を外す"`)}</header>
            <label class="field">このキャラでの名前<input value="${h(row.name)}" placeholder="${h(m?.name || '')}" data-skill-name="${index}"></label>
            <p class="palette">${h(paletteLine(row))}</p>
            <p class="muted small">${h(m?.cost || '')} ${h((m?.text || '').replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1').slice(0, 60))}</p>
            <label class="check small"><input type="checkbox" ${row.hidden ? 'checked' : ''} data-skill-hidden="${index}">相手に隠す</label></article>`; }).join('')}</div>`
        : `<table class="skill-table"><thead><tr><th>ID</th><th>マスターの名前</th><th>このキャラでの名前</th><th>配置したときのパレット</th><th>隠す</th><th></th></tr></thead><tbody>${char.skills.map((row, index) => `<tr class="${DATA.skills[row.id] ? '' : 'is-bad'}">
            <td><code>${h(row.id)}</code></td><td>${h(skillName(row.id))}</td>
            <td><input value="${h(row.name)}" placeholder="（マスターの名前）" data-skill-name="${index}" aria-label="${h(row.id)} のこのキャラでの名前"></td>
            <td class="palette">${h(paletteLine(row))}</td>
            <td><input type="checkbox" ${row.hidden ? 'checked' : ''} data-skill-hidden="${index}" aria-label="${h(row.id)} を相手に隠す"></td>
            <td>${button('×', 'remove-skill', 'btn-icon', `data-index="${index}" aria-label="${h(row.id)} を外す"`)}</td></tr>`).join('')}</tbody></table>`;
      return `${list}<label class="adder wide"><input list="list-skill" placeholder="スキルを ID か名前で足す（例：E-29）" data-add="skill"><datalist id="list-skill">${Object.entries(DATA.skills).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}（${h(row.category)}）</option>`).join('')}</datalist></label>
        <p class="muted small">パレットは保存しない。配置するときに、マスターの「チャットパレット」から作る。名前を空にするとマスターの名前。</p>
        <h4>スキル以外のパレットの行</h4><textarea rows="3" data-field="other" placeholder="1d100 【幸運の判定】">${h(char.other.join('\n'))}</textarea>`;
    }
    if (key === 'gear') return `<h4>パッシブ</h4>${chips(char.passives, DATA.passives, 'passive')}
      <h4>輝化スキル</h4>${chips(char.radiance, DATA.radiance, 'radiance')}
      <h4>アイテム</h4><div class="chips">${char.items.map((row, index) => `<span class="chip"><code>${h(row.id)}</code>${h(DATA.items[row.id]?.name || '（マスターに無い）')}<input type="number" min="1" value="${row.count}" data-item-count="${index}" aria-label="個数">個<button type="button" aria-label="外す" data-action="remove-item" data-index="${index}">×</button></span>`).join('') || '<span class="muted">なし</span>'}
        <label class="adder"><input list="list-item" placeholder="ID か名前で足す" data-add="item"><datalist id="list-item">${Object.entries(DATA.items).map(([id, row]) => `<option value="${h(id)}">${h(id)} ${h(row.name)}</option>`).join('')}</datalist></label></div>`;
    if (key === 'behavior') {
      const b = char.behavior;
      return `<p class="muted small">敵として動くときの設定。味方のときは使わない。</p>
        <label class="check"><input type="checkbox" ${b.auto_target ? 'checked' : ''} data-behavior="auto_target">目標を自動で選ぶ</label>
        <label class="check"><input type="checkbox" ${b.auto_skill ? 'checked' : ''} data-behavior="auto_skill">スキルを自動で選ぶ</label>
        <label class="check"><input type="checkbox" ${b.show_planned ? 'checked' : ''} data-behavior="show_planned">次に使うスキルを相手に見せる</label>
        <fieldset class="field"><legend>行動スロット</legend><label class="check"><input type="radio" name="slot" ${b.slot_mode === 'normal' ? 'checked' : ''} data-slot="normal">ふつうに行動する</label><label class="check"><input type="radio" name="slot" ${b.slot_mode === 'none' ? 'checked' : ''} data-slot="none">行動しない（瓦礫などの置物）</label></fieldset>
        <div class="field"><span>スキルの制約</span><div class="muted small">${b.constraints.length ? `${b.constraints.length}件` : 'なし'}　<em>（形は PR の詳細で決める）</em></div></div>`;
    }
    if (key === 'patterns') return patternsBody(char);
    return '';
  }

  function patternsBody(char) {
    if (!char.allow_enemy) return '<p class="muted">「敵に使う」に印を入れると、行動パターンを作れる。</p>';
    const own = new Set(char.skills.map(row => row.id));
    const cards = char.patterns.map((p, index) => `<article class="pattern ${p.default ? 'is-default' : ''}">
      <header><strong>${h(p.name)}</strong>${p.default ? '<span class="badge">既定</span>' : ''}<span class="muted small">${h(p.id)}</span></header>
      <p class="muted small">${h(p.note || '')}</p>
      <ol class="steps">${p.steps.map(step => `<li>${step.actions.map(id => `<span class="step-skill ${own.has(id) ? '' : 'is-bad'}"><code>${h(id)}</code>${h(skillName(id))}</span>`).join('<span class="plus">＋</span>')}<span class="muted small">→ ${h(TARGETS[step.target] || step.target)}</span></li>`).join('')}</ol>
      <p class="small">使っている編成：${usedBy(char, p.id).map(f => h(f.name)).join('・') || '<span class="muted">なし</span>'}</p>
      <footer>${button('チャートを開く', 'open-chart')}${button('複製', 'copy-pattern', '', `data-index="${index}"`)}${p.default ? '' : button('既定にする', 'make-default', '', `data-index="${index}"`)}${button('別のキャラへ複製…', 'copy-other')}${button('消す', 'delete-pattern', 'btn-danger', `data-index="${index}" ${p.default && char.patterns.length > 1 ? 'disabled title="別のパターンを既定にしてから消す"' : ''}`)}</footer>
    </article>`).join('');
    return `${cards || '<p class="muted">パターンはまだ無い。無いあいだは、使えるスキルから自動で選んで動く。</p>'}
      ${button('＋ 新しいパターン', 'new-pattern', 'btn-primary')}
      <p class="muted small">最初に作ったパターンが既定になる。既定は、編成でパターンを選ばなかったときに使う。</p>`;
  }

  function preview(char) {
    const list = problems(char);
    return `<h3>確かめる</h3>
      <section><h4>配置したときのチャットパレット</h4><pre class="palette-box">${h([...char.skills.map(paletteLine), ...char.other].join('\n') || '（なし）')}</pre></section>
      <section><h4>保存の前の検査</h4>${list.length ? `<ul class="problems">${list.map(([kind, text]) => `<li class="is-${kind}">${h(text)}</li>`).join('')}</ul>` : '<p class="ok">問題なし</p>'}</section>
      <section><h4>使っている編成</h4>${usedBy(char).map(f => `<p class="small">${h(f.name)}：${f.members.filter(m => m.char === char.id).map(m => h((char.patterns.find(p => p.id === m.pattern) || defaultPattern(char))?.name || '自動')).join('、')}</p>`).join('') || '<p class="muted small">なし</p>'}</section>
      <details><summary>保存される形（試作の参考）</summary><pre class="json">${h(JSON.stringify({ ...char, patterns: char.patterns.map(p => ({ id: p.id, name: p.name, default: p.default })) }, null, 2))}</pre></details>`;
  }

  function editScene() {
    const char = current();
    const layout = root.dataset.layout;
    const nav = `<nav class="toc" aria-label="節">${SECTIONS.map(([key, label]) => {
      const bad = key === 'skills' && char.skills.some(row => !DATA.skills[row.id]) || key === 'patterns' && problems(char).some(([k, t]) => k === 'error' && t.startsWith('パターン'));
      return `<button type="button" data-section="${key}" aria-current="${layout === 'toc' && state.section === key}">${label}${key === 'patterns' && char.allow_enemy ? ` <small>${char.patterns.length}</small>` : ''}${bad ? ' <span class="dot" title="問題あり">●</span>' : ''}</button>`;
    }).join('')}<hr><button type="button" data-action="go-import">JSON から取り込む</button></nav>`;
    const body = layout === 'toc'
      ? `<section class="sec"><h3>${SECTIONS.find(([key]) => key === state.section)[1]}</h3>${sectionBody(state.section, char)}</section>`
      : SECTIONS.map(([key, label]) => `<section class="sec" id="sec-${key}"><h3>${label}</h3>${sectionBody(key, char)}</section>`).join('');
    return `<div class="editor"><div class="editbar">${button('← 一覧', 'noop')}<strong><code>${h(char.id)}</code> ${h(char.name)}</strong>${char.allow_ally ? '<span class="tag">味方</span>' : ''}${char.allow_enemy ? '<span class="tag tag-enemy">敵</span>' : ''}</div>
      <div class="edit-grid">${nav}<div class="edit-input">${body}</div><aside class="edit-preview">${preview(char)}</aside></div>
      <footer class="editfoot"><small class="muted">保存は持ち主がそのまま行う（承認は無い）</small>${button('保存', 'noop', 'btn-primary')}</footer></div>`;
  }

  function importScene() {
    const result = state.imported;
    return `<div class="editor"><div class="editbar">${button('← 編集へ', 'go-edit')}<strong>JSON から取り込む</strong></div>
      <div class="import-grid"><section class="sec"><h3>貼り付け</h3><p class="muted small">CharaCreator の出力、今のプリセットの書き出しを貼る。新しく作るときも、今のキャラを移すときも、この口だけ。</p>
        <textarea rows="20" class="mono" data-field="import">${h(state.importText)}</textarea>${button('読み取る', 'read-import', 'btn-primary')}</section>
      <section class="sec">${result ? `<h3>読み取った結果</h3>
        <table class="result"><tbody>
        <tr><th>名前</th><td>${h(result.fields.name)}</td></tr>
        <tr><th>HP・MP</th><td>${result.fields.hp}・${result.fields.mp}</td></tr>
        <tr><th>スキル</th><td>${result.fields.skills.length}件：${result.fields.skills.map(row => `<code>${h(row.id)}</code>${row.name ? `（${h(row.name)}）` : ''}`).join('、')}</td></tr>
        <tr><th>スキル以外の行</th><td>${result.fields.other.map(line => `<code>${h(line)}</code>`).join('<br>') || 'なし'}</td></tr>
        <tr><th>パッシブ</th><td>${result.fields.passives.map(id => `<code>${h(id)}</code>${h(DATA.passives[id]?.name || '')}`).join('、') || 'なし'}</td></tr>
        <tr><th>行動パターン</th><td>${result.profile ? `あり（${stepsOf(result.profile).length}手）→「取り込んだパターン」として既定にする` : 'なし'}</td></tr>
        <tr class="is-drop"><th>捨てる項目</th><td>${result.discarded.map(key => `<code>${h(key)}</code>`).join('、') || 'なし'}<div class="muted small">配置のときに読まれていないので持たない</div></td></tr>
        </tbody></table>
        <div class="row">${button('この内容で新しく作る', 'create-import', 'btn-primary')}${button('選んでいるキャラを置き換える', 'noop')}</div>` : '<p class="muted">「読み取る」を押すと、ここに何がどの項目に入るかが出る。</p>'}</section></div></div>`;
  }

  function formationScene() {
    return `<div class="editor"><div class="editbar"><strong>編成</strong><span class="muted small">メンバーごとに、行動パターンを一覧から選ぶ（写しは持たない）</span></div>
      <div class="formations">${formations.map((f, fi) => `<section class="sec"><h3>${h(f.name)} <span class="muted small">${h(f.id)}</span></h3>
        <table class="members"><thead><tr><th>キャラ</th><th>数</th><th>行動パターン</th><th></th></tr></thead><tbody>${f.members.map((m, mi) => {
          const char = characters.find(row => row.id === m.char);
          const options = char.patterns.length
            ? `<option value="" ${m.pattern ? '' : 'selected'}>既定（${h(defaultPattern(char).name)}）</option>${char.patterns.map(p => `<option value="${p.id}" ${m.pattern === p.id ? 'selected' : ''}>${h(p.name)}</option>`).join('')}`
            : '<option>パターンなし（自動で選ぶ）</option>';
          return `<tr><td><code>${h(char.id)}</code> ${h(char.name)}</td><td>${m.count}</td>
            <td><select data-member="${fi}:${mi}" ${char.patterns.length ? '' : 'disabled'}>${options}</select></td>
            <td>${char.patterns.length ? button('このパターンを複製して編集', 'member-copy', '', `data-member="${fi}:${mi}"`) : button('パターンを作る', 'member-new', '', `data-member="${fi}:${mi}"`)}</td></tr>`;
        }).join('')}</tbody></table></section>`).join('')}</div>
      <p class="muted small pad">パターンの中身を直すと、そのパターンを選んでいる編成すべてに効く。編成だけで少し変えたいときは「複製して編集」で同じキャラの別のパターンにする。</p></div>`;
  }

  function render() {
    const scene = root.dataset.scene;
    app.innerHTML = `<div class="ws"><header class="ws-head"><div><h2>プリセット管理</h2><p class="muted small">計画61の試作：キャラの中身を項目のフォームにし、行動パターンをキャラから切り離す</p></div></header>
      <nav class="ws-tabs">${[['edit', 'キャラクター'], ['formation', '編成'], ['stage', 'ステージ']].map(([key, label]) => `<button type="button" data-scene="${key}" aria-selected="${scene === key || (key === 'edit' && scene === 'import')}" ${key === 'stage' ? 'disabled' : ''}>${label}</button>`).join('')}</nav>
      <div class="ws-body">${scene === 'formation' ? '' : `<aside class="ws-list">${characters.map(row => `<button type="button" class="rec" data-select="${row.id}" aria-current="${row.id === state.selected}"><code>${h(row.id)}</code><strong>${h(row.name)}</strong><span>${row.allow_ally ? '<span class="tag">味方</span>' : ''}${row.allow_enemy ? '<span class="tag tag-enemy">敵</span>' : ''}${row.allow_enemy ? `<span class="muted small">パターン${row.patterns.length}</span>` : ''}</span></button>`).join('')}</aside>`}
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
      'copy-pattern': () => update(c => c.patterns.push({ ...JSON.parse(JSON.stringify(c.patterns[index])), id: `BP-${Date.now() % 1000}`, name: `${c.patterns[index].name}の複製`, default: false })),
      'new-pattern': () => update(c => c.patterns.push({ id: `BP-${Date.now() % 1000}`, name: `パターン${c.patterns.length + 1}`, note: '', default: !c.patterns.length, steps: c.skills.slice(0, 2).map(row => ({ actions: [row.id], target: 'target_enemy_random' })) })),
      'open-chart': () => alert('今の行動チャートのエディター（behavior_flow_editor_modal.js）を、このパターンの中身で開く。'),
      'copy-other': () => alert('複製先のキャラを選ぶ。複製先に無いスキルがあれば、その場で一覧にして、別のスキルに替えるか外すかを選ばせる。'),
      'go-import': () => { root.dataset.scene = 'import'; render(); },
      'go-edit': () => { root.dataset.scene = 'edit'; render(); },
      'read-import': () => { try { state.imported = readCharacter(JSON.parse(state.importText)); } catch (error) { alert(`JSON として読めない：${error.message}`); } render(); },
      'create-import': () => {
        const { fields, profile } = state.imported;
        const id = `NEW_${characters.length + 1}`;
        if (profile) fields.patterns = [{ id: 'BP-取込', name: '取り込んだパターン', note: '', default: true, steps: stepsOf(profile) }];
        characters.push({ id, allow_ally: false, allow_enemy: true, ...fields });
        state.selected = id; state.imported = null; root.dataset.scene = 'edit'; state.section = 'skills'; render();
      },
      'member-copy': () => { const [fi, mi] = target.dataset.member.split(':').map(Number); const m = formations[fi].members[mi]; const c = characters.find(row => row.id === m.char); const src = c.patterns.find(p => p.id === m.pattern) || defaultPattern(c); const copy = { ...JSON.parse(JSON.stringify(src)), id: `BP-${Date.now() % 1000}`, name: `${src.name}（${formations[fi].name}用）`, default: false }; c.patterns.push(copy); m.pattern = copy.id; render(); alert(`「${copy.name}」を${c.name}のパターンとして作り、この枠で選んだ。続けてチャートのエディターが開く。`); },
      'member-new': () => alert('キャラの画面の「行動パターン」の節を開く。'),
    };
    actions[action]?.();
  });
  app.addEventListener('change', event => {
    const el = event.target, char = current(), d = el.dataset;
    if (d.add) {
      const id = el.value.trim().split(/\s/)[0];
      const table = { skill: DATA.skills, passive: DATA.passives, radiance: DATA.radiance, item: DATA.items }[d.add];
      if (!table[id]) { el.setCustomValidity('マスターに無い ID です'); el.reportValidity(); return; }
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
  panel.innerHTML = `<details open><summary>試作の切り替え</summary><div>
    <label>節の並べ方<select data-proto="layout"><option value="toc">左の目次で1節ずつ（管理画面と同じ）</option><option value="long">全部を縦に並べる</option></select></label>
    <label>スキルの見せ方<select data-proto="skills"><option value="table">表（1行に1スキル）</option><option value="card">カード（威力と説明つき）</option></select></label></div></details>`;
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
