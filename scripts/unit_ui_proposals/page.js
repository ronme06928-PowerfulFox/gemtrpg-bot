(() => {
  const { records, catalogs } = JSON.parse(document.querySelector('#data').textContent);
  const app = document.querySelector('#app');
  const overlay = document.querySelector('#overlay');
  const comparison = document.querySelector('#comparison');
  const kinds = { unit: 'ユニット', formation: '編成', stage: 'ステージ' };
  const sources = { skills: 'スキル', passives: 'パッシブ', radiance: '輝化スキル', items: 'アイテム' };
  const sections = {
    unit: { basic: '基本情報', status: 'ステータス', params: 'パラメータ', skills: 'スキル', gear: 'パッシブ・装備', behavior: '行動設定' },
    formation: { basic: '基本情報', members: 'メンバー' },
    stage: { basic: '基本情報', battle: '編成', field: 'フィールド効果', avatar: 'アバター' },
  };
  const ruleTypes = { SPEED_ROLL_MOD: '速度ロール補正', DAMAGE_DEALT_MOD: '与ダメージ補正', APPLY_STATE_ON_CONDITION: '条件付き状態異常付与' };
  const scopes = { ALL: '全員', ENEMY: '敵', ALLY: '味方' };
  const indexes = {
    unit: { id: 'U-006', section: 'skills', query: '', filter: '', scroll: 0 },
    formation: { id: 'F-002', section: 'members', query: '', filter: '', scroll: 0 },
    stage: { id: 'ST-001', section: 'basic', query: '', filter: '', scroll: 0 },
  };
  const nextNumber = Object.fromEntries(Object.entries(records).map(([key, rows]) => [key, rows.length + 1]));
  const prefixes = { unit: 'U', formation: 'F', stage: 'ST' };
  const fixedParams = records.unit[0].params.map(({ label }) => ({ label, value: 0 }));
  const initialStates = Object.fromEntries(Object.keys(records.unit[0].states).map(key => [key, 0]));
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const matches = (query, ...parts) => parts.join(' ').toLowerCase().includes(query.trim().toLowerCase());
  const identity = row => `<code>${escape(row.id)}</code><strong>${escape(row.name) || '名称未設定'}</strong>`;
  const button = (label, action, key = '', classes = '', extra = '') =>
    `<button type="button" class="${classes}" data-action="${action}" data-key="${escape(key)}" ${extra}>${label}</button>`;
  const pressed = active => `aria-pressed="${active}"`;
  const badge = (label, tone = '') => `<span class="badge ${tone}">${escape(label)}</span>`;
  const badges = row => [
    (row.enemy || row.side === 'enemy') && badge('敵', 'enemy'),
    (row.ally || row.side === 'ally') && badge('味方', 'ally'),
    row.private && badge('非公開', 'private'), row.retired && badge('廃止', 'retired'),
  ].filter(Boolean).join('');
  const tags = row => String(row.tags || '').split(/[、,]/).map(tag => tag.trim()).filter(Boolean);
  const find = (kind, id) => records[kind].find(row => row.id === id);
  const dirty = new Set();
  const linked = (source, id) => catalogs[source].find(row => row.id === id) || { id, name: id };
  const rowName = (kind, id) => find(kind, id)?.name || '未設定';
  const primary = 'button primary';
  const outline = 'button outline';
  const destructive = 'button danger';
  let kind = 'unit';
  let proposal = 'ledger';
  let picker = null;
  let editStatus = '';
  let returnFocus = null;
  const current = () => indexes[kind];
  const record = () => find(kind, current().id);

  const field = (label, path, value, type = 'text') => {
    const attrs = `data-field="${escape(path)}"`;
    const control = type === 'textarea' ? `<textarea ${attrs} rows="3">${escape(value)}</textarea>`
      : `<input ${attrs} type="${type}" ${type === 'checkbox' ? (value ? 'checked' : '') : `value="${escape(value)}"`}>`;
    return type === 'checkbox'
      ? `<label class="check">${control}${label}</label>`
      : `<label class="field"><span>${label}</span>${control}</label>`;
  };
  const num = (label, path, value) => field(label, path, value, 'number');
  const check = (label, path, value) => field(label, path, value, 'checkbox');
  const grid = (...fields) => `<div class="fields">${fields.join('')}</div>`;
  const subhead = (title, body) => `<div class="subsection"><h4>${title}</h4>${body}</div>`;
  const choose = (label, key, choices, selected) => `<fieldset class="choice-field"><legend>${label}</legend>
    <div class="segments">${Object.entries(choices).map(([value, name]) =>
      button(name, 'choice', key, '', `data-value="${value}" ${pressed(value === selected)}`)).join('')}</div></fieldset>`;
  const open = (label, key, style = outline) => button(label, 'open-picker', key, style);
  const remove = (path, index) => button('外す', 'remove', path, destructive, `data-index="${index}"`);

  function renderIndex() {
    const { query, filter } = current();
    const filters = kind === 'stage' ? { '': '全件', private: '非公開', retired: '廃止' }
      : { '': '全件', enemy: '敵', ally: '味方', private: '非公開', retired: '廃止' };
    return `<aside class="index" aria-label="${kinds[kind]}一覧">
      <div class="index-tools"><div class="panel-heading"><h2>${kinds[kind]}一覧</h2><span class="count index-count"></span>
        ${button('＋ 新規', 'new-record', '', outline, 'aria-label="新規作成"')}</div>
      <label class="search"><span class="search-icon" aria-hidden="true"></span>
        <input type="search" id="index-query" aria-label="一覧を検索" placeholder="ID・名称・タグ" value="${escape(query)}"></label>
      <div class="segments index-filters" aria-label="一覧フィルター">${Object.entries(filters).map(([key, name]) =>
        button(name, 'filter', key, '', pressed(key === filter))).join('')}</div></div>
      <div class="index-list"></div>
    </aside>`;
  }

  function updateIndex() {
    const { id, query, filter, scroll } = current();
    const rows = records[kind].filter(row => (!filter || row[filter] || row.side === filter)
      && matches(query, row.id, row.name, row.tags));
    app.querySelector('.index-count').textContent = rows.length + ' / ' + records[kind].length;
    const list = app.querySelector('.index-list');
    list.innerHTML = rows.map(row => button(`<span class="record-ident">${identity(row)}</span>
      <span class="record-meta">${badges(row)}${tags(row).slice(0, 2).map(tag => badge(tag, 'tag')).join('')}</span>`,
    'record', row.id, 'index-record', pressed(id === row.id))).join('') || '<p class="empty">該当データなし</p>';
    list.scrollTop = scroll;
  }

  function basic(row) {
    const common = field('名称', 'name', row.name) + field('タグ', 'tags', row.tags);
    const visibility = check('非公開', 'private', row.private);
    if (kind === 'unit') return common + subhead('キャラ区分', `<div class="checks">
      ${check('味方キャラクター', 'ally', row.ally)}${check('敵キャラクター', 'enemy', row.enemy)}</div>`)
      + subhead('表示設定', `<div class="checks">${visibility}${check('GM限定表示', 'gmOnly', row.gmOnly)}
        ${check('シナリオキャラクター', 'scenario', row.scenario)}</div>`);
    if (kind === 'formation') return common + grid(num('推奨人数', 'recommended', row.recommended),
      `<div class="field"><span>種類</span><strong>${row.side === 'enemy' ? '敵編成' : '味方編成'}</strong></div>`) + visibility;
    return common + field('コンセプト', 'concept', row.concept) + field('説明', 'description', row.description, 'textarea') + visibility;
  }

  function params(row) {
    const groups = { '能力値': [], '補正': [], '技能・その他': [] };
    row.params.forEach(({ label, value }, index) => {
      const group = /補正|行動回数/.test(label) ? '補正'
        : /^(筋力|生命力|体格|精神力|敏捷|直感|経験|シナリオ経験)$/.test(label) ? '能力値' : '技能・その他';
      groups[group].push(field(escape(label), 'params.' + index + '.value', value));
    });
    return Object.entries(groups).map(([title, fields]) => subhead(title,
      `<div class="param-grid">${fields.join('')}</div>`)).join('');
  }

  function references(row, source) {
    return row[source].map((item, index) => {
      const master = linked(source, item.id);
      const path = source + '.' + index;
      const details = source === 'skills'
        ? grid(field('固有名称', path + '.name', item.name), check('非公開', path + '.hidden', item.hidden))
        : source === 'items' ? num('個数', path + '.count', item.count) : '';
      return `<article class="linked-row"><div class="linked-content">
        <header class="link-ident">${identity(master)}${source === 'skills' ? badge(master.category) : ''}</header>
        ${master.cost ? `<p class="cost">${escape(master.cost)}</p>` : ''}
        ${master.effect ? `<p class="effect">${escape(master.effect)}</p>` : ''}${details}
      </div><div class="row-actions">${remove(source, index)}</div></article>`;
    }).join('') || '<p class="empty">登録なし</p>';
  }

  const sectionBody = {
    basic,
    status: row => grid(num('最大HP', 'hp', row.hp), num('初期HP', 'initialHp', row.initialHp),
      num('最大MP', 'mp', row.mp), num('初期MP', 'initialMp', row.initialMp))
      + subhead('初期状態', `<div class="param-grid">${Object.entries(row.states).map(([name, value]) =>
        num(escape(name), 'states.' + name, value)).join('')}</div>`),
    params,
    skills: row => references(row, 'skills') + subhead('追加パレット', field('パレット行', 'other', row.other, 'textarea')),
    gear: row => ['passives', 'radiance', 'items'].map(source =>
      `<div class="subsection"><header class="section-heading"><h4>${sources[source]}</h4>
        ${open(sources[source] + 'を追加', source)}</header>${references(row, source)}</div>`).join(''),
    behavior: row => `<div class="checks">${check('対象の自動選択', 'autoTarget', row.autoTarget)}
      ${check('スキルの自動選択', 'autoSkill', row.autoSkill)}${check('予定スキルを公開', 'showPlanned', row.showPlanned)}</div>`,
    members: row => row.members.length ? `<div class="member-table"><div class="member-header"><span>ユニット</span><span>配置数</span><span></span></div>
      ${row.members.map((member, index) => `<div class="member-row"><span class="member-ident">
        <code>${escape(member.id)}</code><strong>${escape(rowName('unit', member.id))}</strong></span>
        <input type="number" min="1" value="${escape(member.count)}" data-field="members.${index}.count" aria-label="${escape(rowName('unit', member.id))}の配置数">
        <div class="row-actions">${remove('members', index)}</div></div>`).join('')}</div>` : '<p class="empty">メンバーなし</p>',
    battle: row => num('必要人数', 'required', row.required)
      + ['enemy', 'ally'].map(side => {
        const label = side === 'enemy' ? '敵編成' : '味方編成';
        const path = side + 'Formation';
        const source = find('formation', row[path]);
        return `<div class="assignment"><div><h4>${label}</h4><div class="link-ident">${source ? identity(source) : '未設定'}</div></div>
          ${open(label + 'を選択', path)}${source ? `<div class="row-actions">${button('外す', 'clear', path, destructive)}</div>` : ''}</div>`;
      }).join(''),
    field: row => row.rules.map((rule, index) => {
      const path = 'rules.' + index;
      return `<article class="linked-row"><div class="linked-content">
        ${field('効果名', path + '.display_name', rule.display_name)}
        ${choose('効果タイプ', path + '.type', ruleTypes, rule.type)}
        ${choose('対象', path + '.scope', scopes, rule.scope)}
        ${grid(num('補正値', path + '.value', rule.value), num('優先度', path + '.priority', rule.priority))}
        ${field('説明', path + '.description', rule.description, 'textarea')}
      </div><div class="row-actions">${button('削除', 'remove', 'rules', destructive, `data-index="${index}"`)}</div></article>`;
    }).join('') || '<p class="empty">効果なし</p>',
    avatar: row => check('アバターを表示', 'avatarEnabled', row.avatarEnabled)
      + field('名称', 'avatarName', row.avatarName) + field('説明', 'avatarDescription', row.avatarDescription, 'textarea'),
  };

  function sectionView(key, title, row) {
    const actions = {
      skills: open('スキルを追加', 'skills', primary),
      members: open('メンバーを追加', 'members', primary),
      field: button('効果を追加', 'new-rule', '', primary),
    };
    return `<section class="form-section" id="section-${key}">
      <header class="section-heading"><h3>${title}</h3>${actions[key] || ''}</header>${sectionBody[key](row)}</section>`;
  }

  function editor(row) {
    const active = current().section;
    const navigation = Object.entries(sections[kind]);
    const shown = proposal === 'sheet' ? navigation : navigation.filter(([key]) => key === active);
    return `<main class="editor" id="editor"><div class="editor-top"><header class="record-heading">
      <a class="narrow-jump" href="#inspector">確認へ ↓</a><div class="record-heading-meta"><code>${escape(row.id)}</code>${badges(row)}</div>
      <h2>${escape(row.name) || '名称未設定'}</h2></header>
      <nav class="editor-nav" aria-label="編集セクション">${navigation.map(([key, title]) =>
        button(title, 'section', key, '', pressed(key === active))).join('')}</nav></div>
      <div class="editor-content">${shown.map(([key, title]) => sectionView(key, title, row)).join('')}</div></main>`;
  }

  function inspector(row) {
    let preview = '';
    let used = [];
    if (kind === 'unit') {
      const palettes = row.skills.map(skill => {
        const { palette = '' } = linked('skills', skill.id);
        return skill.name ? palette.replace(/【[^】]+】/, '【' + skill.id + ' ' + skill.name + '】') : palette;
      }).filter(Boolean);
      preview = `<dl class="summary-metrics"><div><dt>HP</dt><dd>${escape(row.hp)}</dd></div>
        <div><dt>MP</dt><dd>${escape(row.mp)}</dd></div><div><dt>スキル</dt><dd>${row.skills.length}</dd></div></dl>
        ${subhead('配置時のパレット', `<div class="preview-palette">${[...palettes, row.other].filter(Boolean).map(line =>
          `<pre>${escape(line)}</pre>`).join('') || '<p class="empty">パレットなし</p>'}</div>`)}`;
      used = records.formation.filter(formation => formation.members.some(member => member.id === row.id));
    } else if (kind === 'formation') {
      preview = subhead('配置メンバー', row.members.map(member => `<div class="summary-row"><span>${escape(rowName('unit', member.id))}</span>
        <b>× ${escape(member.count)}</b></div>`).join('') || '<p class="empty">メンバーなし</p>');
      used = records.stage.filter(stage => [stage.enemyFormation, stage.allyFormation].includes(row.id));
    } else {
      preview = `<div class="stage-preview"><strong>${escape(row.name)}</strong><p>${escape(row.concept)}</p>
        <div class="record-meta">${tags(row).map(tag => badge(tag, 'tag')).join('')}</div></div>
        <dl class="stage-facts"><dt>敵編成</dt><dd>${escape(rowName('formation', row.enemyFormation))}</dd>
        <dt>味方編成</dt><dd>${escape(rowName('formation', row.allyFormation))}</dd>
        <dt>必要人数</dt><dd>${escape(row.required)}</dd><dt>フィールド効果</dt><dd>${row.rules.length} 件</dd></dl>
        ${row.avatarEnabled ? subhead('アバター', `<strong>${escape(row.avatarName)}</strong><p>${escape(row.avatarDescription)}</p>`) : ''}`;
    }
    const references = kind === 'stage' ? '' : subhead(kind === 'unit' ? '参照元の編成' : '参照元のステージ',
      used.length ? `<ul class="reference-list">${used.map(item => `<li>${identity(item)}</li>`).join('')}</ul>` : '<p class="empty">参照元なし</p>');
    return preview + references;
  }

  function updateSummary() {
    const row = record();
    app.querySelector('.inspector-content').innerHTML = inspector(row);
    app.querySelector('.record-heading h2').textContent = row.name || '名称未設定';
    app.querySelector('.edit-status').textContent = editStatus || '試作データ';
  }

  function render({ keepEditor = false } = {}) {
    const editorScroll = keepEditor ? app.querySelector('.editor')?.scrollTop || 0 : 0;
    const row = record();
    document.documentElement.dataset.proposal = proposal;
    app.innerHTML = `<header class="site-header"><div class="header-inner">
      <div class="app-icon" aria-hidden="true"><i></i><i></i><i></i><i></i></div><h1>ユニット管理</h1></div></header>
      <nav class="kind-tabs" aria-label="データ種別">${Object.entries(kinds).map(([key, label]) =>
        button(`${label}<span class="tab-count">${records[key].length}</span>`, 'kind', key, '', pressed(key === kind))).join('')}</nav>
      <div class="workspace">${renderIndex()}${row ? editor(row) : '<main class="editor"><p class="empty">登録なし</p></main>'}
        <aside class="inspector" id="inspector" aria-label="確認"><div class="panel-heading"><h2>確認</h2>
          ${row ? '<a class="narrow-jump" href="#editor">編集へ ↑</a>' : ''}</div>
          <div class="inspector-content">${row ? inspector(row) : ''}</div></aside></div>
      <footer class="action-bar">${row ? `<div class="record-actions">
        ${button(row.retired ? '廃止を解除' : '廃止', 'retire', '', destructive)}
        ${button('削除', 'open-picker', 'delete', destructive)}</div>
        <div class="save-actions"><span class="edit-status" role="status">${editStatus || '試作データ'}</span>
          <span class="revision">版 ${row.revision}</span>${button('保存', 'save', '', primary)}</div>` : ''}</footer>`;
    updateIndex();
    app.querySelector('.editor').scrollTop = editorScroll;
    for (const toggle of comparison.querySelectorAll('button')) toggle.setAttribute('aria-pressed', String(toggle.dataset.key === proposal));
  }

  function focusSection() {
    if (proposal !== 'sheet') return;
    const panel = app.querySelector('.editor');
    const section = panel.querySelector('#section-' + current().section);
    if (!section) return;
    const header = panel.querySelector('.editor-top');
    panel.scrollTop += section.getBoundingClientRect().top - header.getBoundingClientRect().bottom - 10;
  }

  function pickerData() {
    const { source } = picker;
    const row = record();
    if (catalogs[source]) {
      const used = new Set(row[source].map(item => item.id));
      return catalogs[source].filter(candidate => !used.has(candidate.id));
    }
    if (source === 'members') {
      return records.unit.filter(candidate => candidate[row.side] && !candidate.retired && !row.members.some(member => member.id === candidate.id));
    }
    const side = source === 'enemyFormation' ? 'enemy' : 'ally';
    return records.formation.filter(candidate => candidate.side === side && !candidate.retired && row[source] !== candidate.id);
  }

  function candidateDetails(candidate) {
    if (!catalogs[picker.source]) return tags(candidate).map(tag => badge(tag, 'tag')).join(' ');
    if (picker.source !== 'skills') return `<p class="effect">${escape(candidate.effect)}</p>`;
    return `<dl class="skill-data">
      <dt>パレット</dt><dd><pre>${escape(candidate.palette || '—')}</pre></dd>
      <dt>コスト</dt><dd>${escape(candidate.cost || '—')}</dd>
      <dt>効果</dt><dd>${escape(candidate.effect || '—')}</dd>
      <dt>特記</dt><dd>${escape(candidate.note || '—')}</dd></dl>`;
  }

  function updateCandidates(rows = pickerData()) {
    const shown = rows.filter(row => (!picker.category || row.category === picker.category)
      && matches(picker.query, row.id, row.name, row.category, row.palette, row.cost, row.effect, row.note, row.tags));
    const selected = shown.find(row => row.id === picker.selected) || shown[0];
    picker.selected = selected?.id;
    overlay.querySelector('.candidate-count').textContent = shown.length + ' 件';
    const candidateTitle = row => `${identity(row)}${row.category ? badge(row.category) : badges(row)}`;
    const list = overlay.querySelector('.candidate-list');
    if (!shown.length) list.innerHTML = '<p class="empty">該当候補なし</p>';
    else if (proposal === 'ledger') list.innerHTML = shown.map(row => `<article class="candidate-row">
      <header><div class="link-ident">${candidateTitle(row)}</div>${button('追加', 'add', row.id, outline)}</header>
      ${candidateDetails(row)}</article>`).join('');
    else list.innerHTML = shown.map(row => button(`<span class="link-ident">${candidateTitle(row)}</span>`,
      'inspect-candidate', row.id, 'candidate-select', pressed(row.id === picker.selected))).join('');
    const detail = overlay.querySelector('.candidate-detail');
    if (detail) detail.innerHTML = selected ? `<header><div class="link-ident">${candidateTitle(selected)}</div>
      ${button('追加', 'add', selected.id, primary)}</header>${candidateDetails(selected)}` : '';
  }

  function renderOverlay() {
    app.inert = !!picker;
    if (!picker) {
      overlay.innerHTML = '';
      return;
    }
    const headings = { members: 'メンバーを追加', enemyFormation: '敵編成を選択', allyFormation: '味方編成を選択' };
    const title = headings[picker.source] || sources[picker.source] + 'を追加';
    if (['delete', 'new-formation'].includes(picker.source)) {
      const isDelete = picker.source === 'delete';
      const title = isDelete ? 'データを削除' : '編成タイプ';
      const content = isDelete
        ? identity(record()) + button('削除', 'delete', '', destructive)
        : button('敵編成', 'create-formation', 'enemy', outline) + button('味方編成', 'create-formation', 'ally', outline);
      overlay.innerHTML = `<div class="scrim"></div><section class="picker confirm" role="dialog" aria-labelledby="picker-title">
        <header class="picker-header"><h2 id="picker-title">${title}</h2>${button('閉じる', 'close', '', outline)}</header>
        <div class="confirm-body">${content}</div></section>`;
      return;
    }
    const rows = pickerData();
    const categories = [...new Set(rows.map(row => row.category).filter(Boolean))];
    overlay.innerHTML = `<div class="scrim"></div><section class="picker" role="dialog" aria-labelledby="picker-title">
      <header class="picker-header"><h2 id="picker-title">${title}</h2>${button('閉じる', 'close', '', outline)}</header>
      <div class="picker-tools"><label class="search"><span class="search-icon" aria-hidden="true"></span>
        <input type="search" id="candidate-query" aria-label="候補を検索" placeholder="ID・名称・効果" value="${escape(picker.query)}"></label>
        <span class="count candidate-count" role="status"></span>
        ${categories.length > 1 ? `<div class="segments category-filters">${['', ...categories].map(name =>
          button(escape(name || '全分類'), 'category', name, '', pressed(name === picker.category))).join('')}</div>` : ''}</div>
      <div class="picker-body"><div class="candidate-list" aria-label="候補一覧"></div>
        ${proposal === 'sheet' ? '<div class="candidate-detail" aria-label="候補詳細"></div>' : ''}</div>
      </section>`;
    updateCandidates(rows);
  }

  function closePicker() {
    picker = null;
    renderOverlay();
    app.querySelector(returnFocus)?.focus({ preventScroll: true });
  }

  function setField(path, value) {
    const keys = path.split('.');
    const attribute = keys.pop();
    const parent = keys.reduce((object, key) => object[key], record());
    parent[attribute] = value;
    dirty.add(record().id);
    editStatus = '未保存';
  }

  function mutate(callback) {
    callback(record());
    dirty.add(record().id);
    editStatus = '未保存';
    render({ keepEditor: true });
  }

  function addCandidate(id) {
    const source = picker.source;
    mutate(row => {
      if (source === 'members' || source === 'items') row[source].push({ id, count: 1 });
      else if (catalogs[source]) row[source].push({ id });
      else row[source] = id;
    });
    closePicker();
  }

  function createRecord(side) {
    const defaults = {
      unit: {
        ally: true, enemy: true, hp: 0, mp: 0, initialHp: 0, initialMp: 0,
        states: { ...initialStates }, params: structuredClone(fixedParams), skills: [], other: '', passives: [],
        radiance: [], items: [], autoTarget: true, showPlanned: true,
      },
      formation: { side, recommended: 0, members: [] },
      stage: { required: 0, rules: [] },
    };
    const id = prefixes[kind] + '-' + String(nextNumber[kind]++).padStart(3, '0');
    records[kind].unshift({ id, name: '', tags: '', revision: 0, ...defaults[kind] });
    Object.assign(current(), { id, section: 'basic', query: '', filter: '', scroll: 0 });
    dirty.add(id);
    editStatus = '未保存';
    if (picker) closePicker();
    render();
    app.querySelector('[data-field="name"]')?.focus();
  }

  document.addEventListener('click', event => {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    const { action, key, value, index } = target.dataset;
    const actions = {
      proposal() {
        if (key === proposal) return;
        const previousPickerScroll = overlay.querySelector('.candidate-list')?.scrollTop || 0;
        proposal = key;
        render();
        if (picker) {
          renderOverlay();
          if (proposal === 'ledger') overlay.querySelector('.candidate-list')?.scrollTo(0, previousPickerScroll);
        }
        focusSection();
      },
      kind() {
        kind = key;
        editStatus = dirty.has(record()?.id) ? '未保存' : '';
        render();
        focusSection();
      },
      section() {
        current().section = key;
        if (proposal === 'ledger') render();
        else {
          for (const tab of app.querySelectorAll('.editor-nav button')) tab.setAttribute('aria-pressed', String(tab.dataset.key === key));
          focusSection();
        }
        app.querySelector(`.editor-nav button[data-key="${key}"]`)?.focus({ preventScroll: true });
      },
      record() {
        current().scroll = app.querySelector('.index-list').scrollTop;
        current().id = key;
        editStatus = dirty.has(key) ? '未保存' : '';
        render();
        focusSection();
        app.querySelector(`.index-record[data-key="${key}"]`)?.focus({ preventScroll: true });
      },
      filter() {
        current().filter = key;
        current().scroll = 0;
        for (const tab of app.querySelectorAll('.index-filters button')) tab.setAttribute('aria-pressed', String(tab.dataset.key === key));
        updateIndex();
      },
      'new-record'() {
        if (kind !== 'formation') return createRecord();
        returnFocus = '[data-action="new-record"]';
        picker = { source: 'new-formation' };
        renderOverlay();
        overlay.querySelector('[data-action="create-formation"]').focus();
      },
      'create-formation': () => createRecord(key),
      'open-picker'() {
        returnFocus = `[data-action="open-picker"][data-key="${key}"]`;
        picker = { source: key, query: '', category: '', selected: null };
        renderOverlay();
        (overlay.querySelector('#candidate-query') || overlay.querySelector('button')).focus({ preventScroll: true });
      },
      close: closePicker,
      category() {
        picker.category = key;
        for (const tab of overlay.querySelectorAll('.category-filters button')) tab.setAttribute('aria-pressed', String(tab.dataset.key === key));
        updateCandidates();
        overlay.querySelector('.candidate-list').scrollTop = 0;
      },
      'inspect-candidate'() {
        picker.selected = key;
        updateCandidates();
        overlay.querySelector('.candidate-select[aria-pressed="true"]')?.focus({ preventScroll: true });
      },
      add: () => addCandidate(key),
      remove: () => mutate(row => row[key].splice(Number(index), 1)),
      clear: () => mutate(row => { row[key] = ''; }),
      choice: () => mutate(() => setField(key, value)),
      'new-rule': () => mutate(row => row.rules.push({ display_name: '', type: 'SPEED_ROLL_MOD', scope: 'ALL', value: 0, priority: 0 })),
      retire: () => mutate(row => { row.retired = !row.retired; }),
      delete() {
        const rows = records[kind];
        if ((kind === 'unit' && records.formation.some(formation => formation.members.some(member => member.id === current().id)))
          || (kind === 'formation' && records.stage.some(stage => [stage.enemyFormation, stage.allyFormation].includes(current().id)))) {
          closePicker();
          editStatus = '参照元あり';
          updateSummary();
          return;
        }
        rows.splice(rows.indexOf(record()), 1);
        dirty.delete(current().id);
        current().id = rows[0]?.id;
        editStatus = dirty.has(current().id) ? '未保存' : '';
        closePicker();
        render();
      },
      save() {
        record().revision += 1;
        dirty.delete(record().id);
        editStatus = '試作内で保存済み';
        render({ keepEditor: true });
      },
    };
    actions[action]?.();
  });

  document.addEventListener('input', event => {
    const target = event.target;
    if (target.id === 'index-query') {
      current().query = target.value;
      current().scroll = 0;
      updateIndex();
    } else if (target.id === 'candidate-query') {
      picker.query = target.value;
      updateCandidates();
      overlay.querySelector('.candidate-list').scrollTop = 0;
    } else if (target.dataset.field) {
      const value = target.type === 'checkbox' ? target.checked
        : target.type === 'number' ? (target.value === '' ? '' : target.valueAsNumber) : target.value;
      setField(target.dataset.field, value);
      updateSummary();
      if (['name', 'tags', 'ally', 'enemy', 'private'].includes(target.dataset.field)) {
        const row = record();
        app.querySelector('.record-heading-meta').innerHTML = `<code>${escape(row.id)}</code>${badges(row)}`;
        current().scroll = app.querySelector('.index-list').scrollTop;
        updateIndex();
      }
    }
  });

  document.addEventListener('keydown', event => {
    if (picker && event.key === 'Escape') closePicker();
  });
  render();
})();
