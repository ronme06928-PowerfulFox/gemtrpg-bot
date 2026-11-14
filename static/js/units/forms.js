(function () {
  const h = window.CatalogGlossary.escape;
  const sections = {
    unit: [['basic','基本情報'], ['status','ステータス'], ['params','パラメータ'], ['skills','スキル'],
      ['gear','パッシブ・輝化スキル・アイテム'], ['behavior','行動設定'], ['history','履歴']],
    formation: [['basic','基本情報'], ['members','メンバー'], ['history','履歴']],
    stage: [['basic','基本情報'], ['battle','編成'], ['field','フィールド効果'], ['avatar','ステージアバター'], ['history','履歴']],
  };
  const rules = {SPEED_ROLL_MOD:'速度ロール補正', DAMAGE_DEALT_MOD:'与ダメージ補正', APPLY_STATE_ON_CONDITION:'条件付き状態異常付与'};
  const scopes = {ALL:'全員', ALLY:'味方のみ', ENEMY:'敵のみ'};
  const operators = {GTE:'以上', GT:'より大きい', LTE:'以下', LT:'より小さい', EQ:'等しい', NE:'等しくない'};
  const sides = {enemy:'敵編成', ally:'味方編成'};
  const states = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘'];
  // スキルの文章の用語リンク [[W-20|的中時]] は、カードでは表示名だけを見せる。
  const plain = text => String(text || '').replace(/\[\[[^|\]\n]+\|([^\]\n]+)\]\]/g, '$1');
  const button = (label, action, attrs = '', style = '') =>
    `<button type="button" class="cat-button ${style}" data-unit-action="${action}" ${attrs}>${label}</button>`;
  const options = (choices, value) => Object.entries(choices).map(([id, label]) =>
    `<option value="${h(id)}" ${id === String(value ?? '') ? 'selected' : ''}>${h(label)}</option>`).join('');
  const field = (label, path, value, type = 'text', attrs = '') => `<label class="cat-field">${h(label)}${type === 'area'
    ? `<textarea data-path="${h(path)}" rows="3">${h(value)}</textarea>`
    : `<input data-path="${h(path)}" type="${type}" ${type === 'checkbox' ? (value ? 'checked' : '') : `value="${h(value)}"`} ${attrs}>`}</label>`;
  const select = (label, path, choices, value) => `<label class="cat-field">${h(label)}<select data-path="${path}">${options(choices,value)}</select></label>`;
  const grid = (...fields) => `<div class="unit-fields">${fields.join('')}</div>`;
  const card = (title, body) => `<section class="bo-workspace__card unit-card"><h4>${h(title)}</h4>${body}</section>`;
  const remove = (path, index) => button('削除','remove-row', `data-path="${path}" data-index="${index}"`, 'cat-danger');
  const picker = (label, source, path, edit) => edit ? button(label,'picker',`data-source="${source}" data-path="${path}"`) : '';
  const badge = (label, style = '') => `<span class="cat-badge ${style}">${label}</span>`;
  const badges = row => {
    const p = row.payload;
    return [p.allow_ally && badge('味方'), p.allow_enemy && badge('敵','unit-enemy'),
      p.type && badge(sides[p.type], p.type === 'enemy' ? 'unit-enemy' : ''),
      row.visibility === 'staff' && badge('非公開','unit-staff'), row.deprecated && badge('廃止','unit-deprecated')].filter(Boolean).join(' ');
  };
  const textLines = value => Array.isArray(value) ? value.join('\n') : '';
  const nameOf = p => p?.デフォルト名称 || p?.display_name || p?.name || '';
  const url = value => /^(https?:\/\/|\/(?!\/))/i.test(value || '') ? h(value) : '';
  const image = value => url(value) ? `<img class="unit-image" src="${url(value)}" alt="">` : '';

  function defaults(kind, side) {
    if (kind === 'unit') return {name:'', image:'', allow_ally: true, allow_enemy: true, scenario:false,
      gm_only:false, hp:0, mp:0, states:{}, params:[], skills:[], other_lines:[], passives:[], radiance:[],
      items:[], tags:[], disabled_tags:[], behavior:{}, patterns:[], default_pattern_id:null};
    if (kind === 'formation') return {name:'', type:side, recommended_ally_count:0, members:[]};
    return {name:'', tags:[], required_ally_count:0, field_effect_profile:{version:1,rules:[]}, stage_avatar:{enabled:false}};
  }

  function overwriteUnit(previous, incoming) {
    const next = window.CatalogJson.clone(incoming);
    next.collection_id = previous.collection_id;
    if (!previous.patterns?.length) return next;
    next.patterns = window.CatalogJson.clone(previous.patterns);
    next.default_pattern_id = previous.default_pattern_id;
    const ids = new Set(next.patterns.map(pattern => pattern.id));
    for (const pattern of incoming.patterns || []) {
      let id = pattern.id;
      for (let index = 2; ids.has(id); index++) id = pattern.id + '-' + index;
      next.patterns.push({...window.CatalogJson.clone(pattern),id});
      ids.add(id);
    }
    return next;
  }

  function palette(unit, skills) {
    const lines = (unit.skills || []).map(row => {
      const source = skills.find(item => item.entry_id === row.id)?.payload['チャットパレット'] || '';
      return row.name ? source.replace(/【\s*([A-Za-z]+-\d+)\s*[^】]*】/g,
        (match, id) => id === row.id ? `【${id} ${row.name}】` : match) : source;
    });
    return [...lines.filter(Boolean), ...(unit.other_lines || [])].join('\n');
  }

  function render(section, ctx) {
    const {kind, row, edit, masters, records} = ctx;
    const p = row.payload;
    const items = (key, path, label) => (p[path] || []).map((item, i) => {
      const id = typeof item === 'string' ? item : item.id;
      const master = masters[key].find(r => r.entry_id === id);
      return card(`${id} ${nameOf(master?.payload)}`, (path === 'items' ? field('個数',`items.${i}.count`,item.count,'number','min="0"') : '') + (edit ? remove(path,i) : ''));
    }).join('') + picker(label,key,path,edit);
    const resource = id => records.find(item => item.entry_id === id)?.payload.name || id || '未設定';
    const num = (label, path, value = 0, attrs = '') => field(label,path,value,'number',attrs);
    const tags = () => field('タグ','tags', (p.tags || []).join('、'));
    if (section === 'basic') {
      const common = grid(select('分類','collection_id', {'':'未分類', ...Object.fromEntries(records.filter(r => r.kind === 'unit_collection').map(r => [r.entry_id,r.payload.name]))},p.collection_id),
        select('公開範囲','visibility',{public:'公開',staff:'制作者・GMのみ'},row.visibility));
      if (kind === 'unit') return field('キャラクター名','name',p.name) + grid(
        card('画像',image(p.image) + (edit ? button('画像を選択','image') + (p.image ? button('画像を解除','clear-image') : '') : '')),
        card('キャラ区分',field('味方キャラクター','allow_ally',p.allow_ally,'checkbox') + field('敵キャラクター','allow_enemy',p.allow_enemy,'checkbox')),
        field('シナリオキャラクター','scenario',p.scenario,'checkbox'), field('GM限定表示','gm_only',p.gm_only,'checkbox')) + common + tags();
      if (kind === 'formation') return field('編成名','name',p.name) +
        grid(`<p>種類 <strong>${h(sides[p.type])}</strong></p>`,num('推奨人数','recommended_ally_count',p.recommended_ally_count,'min="0"')) + common;
      return field('名前','name',p.name) + field('コンセプト','concept',p.concept) + field('説明','description',p.description,'area') + tags() + common;
    }
    if (section === 'status') return grid(num('最大HP','hp',p.hp,'min="0"'), num('最大MP','mp',p.mp,'min="0"'),
      num('初期HP','initial_hp',p.initial_hp ?? p.hp,'min="0"'), num('初期MP','initial_mp',p.initial_mp ?? p.mp,'min="0"')) +
      `<h4 class="unit-subhead">初期状態</h4><div class="unit-param-grid">${[...new Set([...states, ...Object.keys(p.states || {})])].map(key => num(key,`states.${encodeURIComponent(key).replaceAll('.', '%2E')}`,p.states?.[key])).join('')}</div>`;
    if (section === 'params') {
      const groups = {'能力値': /^(筋力|生命力|体格|精神力|敏捷|直感|経験|シナリオ経験)$/,
        '補正': /補正|行動回数|速度/, '技能': /技能|判定|^(五感|採取|本能|鑑定|対話|尋問|諜報|窃取|隠密|運動|制作|回避)$/};
      const categorise = label => Object.keys(groups).find(key => groups[key].test(label || '')) || 'その他';
      // パラメータの項目は決まっているので、項目名は固定の表示にし、値だけを直す（追加・削除はしない）。
      const cell = (param, i) => `<label class="cat-field">${h(param.label || '（名前なし）')}
        <input data-path="params.${i}.value" value="${h(param.value)}"></label>`;
      return [...Object.keys(groups), 'その他'].map(group => {
        const cells = (p.params || []).map((param,i) => categorise(param.label) === group ? cell(param,i) : '').join('');
        return cells ? `<h4 class="unit-subhead">${group}</h4><div class="unit-param-grid">${cells}</div>` : '';
      }).join('') || '<p class="cat-caption">パラメータはありません。JSONインポートで取り込めます。</p>';
    }
    if (section === 'skills') return '<p class="cat-caption">チャットパレットは配置時にマスターから生成します。</p><div class="unit-skill-grid">' +
      (p.skills || []).map((skill,i) => {
        const master = masters.skill.find(item => item.entry_id === skill.id)?.payload || {};
        return `<article class="unit-skill"><header><code>${h(skill.id)}</code><strong>${h(nameOf(master))}</strong>${master.分類 ? `<span class="cat-badge">${h(master.分類)}</span>` : ''}
          </header>
          ${field('固有名称',`skills.${i}.name`,skill.name,'text',`placeholder="${h(nameOf(master))}"`)}
          <p class="unit-skill-text">${h([plain(master.コスト), plain(master.発動時効果)].filter(Boolean).join(' ') || '効果なし')}</p>
          <footer>${field('非公開',`skills.${i}.hidden`,skill.hidden,'checkbox')}
          ${edit ? button('このスキルを外す','remove-row',`data-path="skills" data-index="${i}"`,'cat-danger unit-remove') : ''}</footer></article>`;
      }).join('') + '</div>' + picker('＋ スキルを追加','skill','skills',edit) + field('その他のパレット行','other_lines',textLines(p.other_lines),'area');
    if (section === 'gear') return card('パッシブ',items('passive','passives','＋ パッシブを追加')) +
      card('輝化スキル',items('radiance','radiance','＋ 輝化スキルを追加')) +
      card('アイテム',items('item','items','＋ アイテムを追加'));
    if (section === 'behavior') return grid(
      field('対象の自動選択','behavior.auto_target',p.behavior?.auto_target,'checkbox'),
      field('スキルの自動選択','behavior.auto_skill',p.behavior?.auto_skill,'checkbox'),
      field('予定スキルを公開','behavior.show_planned',p.behavior?.show_planned,'checkbox'),
      select('行動スロット','behavior.slot_mode',{normal:'通常',none:'なし'},p.behavior?.slot_mode || 'normal'))
      + field('スキルの制約（JSON）','behavior.constraints',window.CatalogJson.stringify(p.behavior?.constraints || []),'area');
    if (section === 'members') return `<table class="unit-members"><thead><tr><th>ユニット</th><th>数</th><th></th></tr></thead><tbody>${
      (p.members || []).map((member,i) => `<tr><td><code>${h(member.unit_id)}</code> ${h(resource(member.unit_id))}</td>
        <td><input type="number" min="1" data-path="members.${i}.count" value="${h(member.count)}" aria-label="${h(resource(member.unit_id))}の数"></td>
        <td>${edit ? button('外す','remove-row',`data-path="members" data-index="${i}" aria-label="${h(resource(member.unit_id))}を編成から外す"`,'cat-danger unit-remove') : ''}</td></tr>`).join('')
      || '<tr><td colspan="3" class="cat-caption">メンバーなし</td></tr>'}</tbody></table>` + picker('＋ メンバーを追加',p.type + '-unit','members',edit);
    if (section === 'battle') return ['enemy','ally'].map(side => {
      const path = side + '_formation_id';
      return card(sides[side], `<p>${h(resource(p[path]))}</p>` + picker('編成を選択',side + '-formation',path,edit)
        + (edit && p[path] ? button('選択を解除','clear-reference',`data-path="${path}"`) : ''));
    }).join('') + num('必要人数','required_ally_count',p.required_ally_count,'min="0"');
    if (section === 'field') return (p.field_effect_profile?.rules || []).map((rule,i) => {
      const path = `field_effect_profile.rules.${i}`;
      return card(rule.display_name || rule.name || rules[rule.type] || 'フィールド効果', grid(
        select('種類',path+'.type',rules,rule.type), select('対象',path+'.scope',scopes,rule.scope),
        num('値',path+'.value',rule.value), num('優先度',path+'.priority',rule.priority),
        field('表示名',path+'.display_name',rule.display_name || rule.name), field('ルールID',path+'.rule_id',rule.rule_id),
        field('付与する状態',path+'.state_name',rule.state_name), field('トリガー状態名',path+'.trigger_state_name',rule.trigger_state_name),
        field('説明',path+'.description',rule.description,'area'), field('フレーバーテキスト',path+'.flavor_text',rule.flavor_text,'area'),
        field('条件パラメータ',path+'.condition.param',rule.condition?.param),
        select('条件演算子',path+'.condition.operator',operators,rule.condition?.operator || 'GTE'),
        field('条件値',path+'.condition.value',rule.condition?.value,'number'))
        + (edit ? button('条件を解除','clear-reference',`data-path="${path}.condition"`) + remove('field_effect_profile.rules',i) : ''));
    }).join('') + (edit ? button('＋ 効果ルールを追加','add-rule') : '');
    if (section === 'avatar') return field('ステージアバターを表示','stage_avatar.enabled',p.stage_avatar?.enabled,'checkbox') +
      field('名前','stage_avatar.name',p.stage_avatar?.name) + field('説明','stage_avatar.description',p.stage_avatar?.description,'area') +
      field('アイコン','stage_avatar.icon',p.stage_avatar?.icon);
    return '';
  }

  window.UnitForms = {sections, sides, button, options, field, card, badges, defaults, overwriteUnit, palette, render, nameOf, image};
})();
