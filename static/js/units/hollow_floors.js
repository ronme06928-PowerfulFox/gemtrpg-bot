(function () {
  const {h} = window.CatalogWorkspaceParts;
  const {button, field, select, grid, card, remove, imageField} = window.UnitForms;
  const labels = {tier:'Tier',hollow_map:'マップ',fixed_floor:'固定階',hollow_event:'イベント',treasure_chest:'宝箱',drop_table:'ドロップ表'};
  const types = {town:'町',camp:'キャンプ'};
  const events = {normal:'通常戦闘',elite:'精鋭戦闘',chest:'宝箱',miasma:'魔素だまり'};
  const grades = {'鉄級':'iron','銅級':'copper','銀級':'silver','金級':'gold','特異級':'exceptional'};
  const supports = kind => Object.hasOwn(labels, kind);
  const tierOf = floor => Math.ceil(floor / 10);
  const floorLabel = floor => 'T' + tierOf(floor) + ' · ' + floor + 'F';
  const number = row => row.payload[row.kind === 'fixed_floor' ? 'floor' : 'tier'] ?? Infinity;

  let categories = [];
  const configureCategories = values => { categories = values; };

  function defaults(kind, records) {
    if (window.UnitHollowEventForms.supports(kind)) return window.UnitHollowEventForms.defaults(kind);
    if (kind === 'fixed_floor') return {name:'',floor:10,type:'town',text:''};
    if (kind === 'hollow_map') return {name:'',tier:1,description:'',image:'',event_weights:{},
      encounters:{normal:[],elite:[]},events:[],chests:[],category_weights:{},boss_formation_id:'',boss_stage_id:''};
    const used = new Set(records.filter(row => row.kind === 'tier' && !row.deprecated).map(number));
    return {name:'',tier:[1,2,3,4,5].find(value => !used.has(value)) ?? 1,description:'',
      hp_multiplier:1,attack_multiplier:1};
  }

  function checked(path, control) {
    return `<div class="unit-checked-field">${control}<span class="cat-field-error" data-unit-field-error="${path}" id="unit-error-${path}" hidden></span></div>`;
  }

  function numberField(label, path, value, attributes) {
    return checked(path, field(label,path,value,'number',attributes));
  }

  function reference(label, path, kind, value, records) {
    const choices = Object.fromEntries(records.filter(row => row.kind === kind && row.payload.domain === 'hollow' &&
      (kind !== 'formation' || row.payload.type === 'enemy') && (!row.deprecated || row.entry_id === value))
      .map(row => [row.entry_id,row.payload.name]));
    if (value && !Object.hasOwn(choices,value)) choices[value] = value;
    return checked(path, select(label,path,{'':'選択',...choices},value));
  }

  function membersOf(formationId, records) {
    const formation = records.find(row => row.kind === 'formation' && row.entry_id === formationId);
    return (formation?.payload.members || []).map(({unit_id,count}) => {
      const unit = records.find(row => row.kind === 'unit' && row.entry_id === unit_id)?.payload;
      const grade = (unit?.tags || []).find(tag => typeof tag === 'string' && tag.startsWith('等級:'))?.slice(3);
      const badge = Object.hasOwn(grades,grade)
        ? `<span class="cat-badge unit-grade" data-grade="${grades[grade]}">${grade}</span>` : '';
      return `<span>${badge}${h(unit?.name || unit_id)}×${count}</span>`;
    }).join('');
  }

  function weightedTable(path, label, rows, records, edit, kind, idField) {
    const name = kind === 'formation' ? '編成' : kinds[kind];
    const addLabel = kind === 'formation' ? label : name;
    return `<section class="unit-encounter-group" data-weight-path="${path}">
      <div class="unit-list-heading"><h4>${label}</h4>${edit ? button(`＋ ${addLabel}を追加`,'weighted-add',`data-path="${path}" data-field="${idField}"`) : ''}</div>
      ${errorNote(path)}
      <div class="unit-encounter-head" aria-hidden="true"><span>${name}</span><span>重み</span><span>割合</span></div>
      ${rows.map((row,i) => `<div class="unit-encounter-row">
        <div>${reference(name,`${path}.${i}.${idField}`,kind,row[idField],records)}
          ${kind === 'formation' ? `<div class="unit-encounter-members">${membersOf(row[idField],records)}</div>` : ''}</div>
        ${numberField('重み',`${path}.${i}.weight`,row.weight,'min="0" step="1"')}
        ${shareBar()}
        ${edit ? remove(path,i) : ''}</div>`).join('')}
    </section>`;
  }

  const kinds = {hollow_event:'魔素だまり',treasure_chest:'宝箱'};
  const errorNote = path => `<span class="cat-field-error" data-unit-field-error="${path}" id="unit-error-${path}" hidden></span>`;
  const shareBar = () => '<div class="unit-encounter-share"><output data-encounter-share></output><span aria-hidden="true"><i></i></span></div>';

  function render(section, {kind,row,edit,records,masters}) {
    if (window.UnitHollowEventForms.supports(kind)) return window.UnitHollowEventForms.render(kind,row.payload,edit,masters,records);
    const p = row.payload;
    const name = checked('name', field('名前','name',p.name));
    if (kind === 'fixed_floor') {
      return name + grid(numberField('階','floor',p.floor,'min="1" max="50" step="1"'),
        checked('type',select('種類','type',types,p.type))) +
        checked('text',field('文章','text',p.text,'area'));
    }
    if (section === 'events') {
      return `<div class="unit-event-strip" aria-label="イベントの割合">
        ${Object.keys(events).map(key => `<span data-event-share="${key}" data-event="${key}"></span>`).join('')}</div>
        <div class="unit-event-fields">${Object.entries(events).map(([key,label]) =>
          `<div data-event="${key}">${numberField(label,`event_weights.${key}`,p.event_weights?.[key] ?? 0,'min="0" step="1"')}</div>`
        ).join('')}</div>`
        + weightedTable('events','イベントの表',p.events || [],records,edit,'hollow_event','event_id')
        + weightedTable('chests','宝箱の表',p.chests || [],records,edit,'treasure_chest','chest_id');
    }
    if (section === 'encounters') {
      return weightedTable('encounters.normal','通常',p.encounters?.normal || [],records,edit,'formation','formation_id') +
        weightedTable('encounters.elite','精鋭',p.encounters?.elite || [],records,edit,'formation','formation_id');
    }
    if (section === 'categories') {
      return grid(...categories.map(label =>
        numberField(label,`category_weights.${label}`,p.category_weights?.[label] ?? 0,'min="0" step="1"')));
    }
    const tier = numberField('区切りの番号','tier',p.tier,'min="1" max="5" step="1"');
    const details = kind === 'hollow_map'
      ? grid(tier, reference('ボス編成','boss_formation_id','formation',p.boss_formation_id,records),
        reference('ボスステージ','boss_stage_id','stage',p.boss_stage_id,records))
      : grid(tier, numberField('HP係数','hp_multiplier',p.hp_multiplier,'step="any"'),
        numberField('攻撃係数','attack_multiplier',p.attack_multiplier,'step="any"'));
    return name + details + checked('description',field('説明','description',p.description,'area')) +
      (kind === 'hollow_map' ? imageField(p.image, edit) : '');
  }

  const weight = value => Number.isInteger(value) && value >= 0 ? value : 0;
  const sum = values => values.reduce((total,value) => total + weight(value),0);
  const percent = (value,total) => total ? weight(value) * 100 / total : 0;
  const share = (value,total) => total ? `${Math.round(percent(value,total)*10)/10}%` : '—';

  function update(section, payload, errors) {
    section.querySelectorAll('[data-unit-field-error]').forEach(note => {
      const path = note.dataset.unitFieldError;
      const key = path.replace(/\.(\d+)(?=\.|$)/g,'[$1]');
      const message = errors[key] || '';
      note.hidden = !message;
      note.textContent = message;
      const input = note.closest('.unit-checked-field')?.querySelector('[data-path]');
      if (message) {
        input?.setAttribute('aria-invalid','true');
        input?.setAttribute('aria-describedby',note.id);
      } else {
        input?.removeAttribute('aria-invalid');
        input?.removeAttribute('aria-describedby');
      }
    });

    const eventWeights = payload.event_weights || {};
    const eventTotal = sum(Object.values(eventWeights));
    section.querySelectorAll('[data-event-share]').forEach(segment => {
      const key = segment.dataset.eventShare;
      const ratio = share(eventWeights[key],eventTotal);
      segment.style.setProperty('--unit-share', eventTotal ? percent(eventWeights[key],eventTotal) : 100 / Object.keys(events).length);
      segment.toggleAttribute('data-empty',!eventTotal);
      segment.textContent = ratio;
      segment.title = `${events[key]} ${ratio}`;
      segment.setAttribute('aria-label',segment.title);
    });
    section.querySelectorAll('[data-weight-path]').forEach(group => {
      const rows = group.dataset.weightPath.split('.').reduce((obj,key) => obj?.[key],payload) || [];
      const total = sum(rows.map(row => row.weight));
      group.querySelectorAll('[data-encounter-share]').forEach((output,i) => {
        output.textContent = share(rows[i].weight,total);
        output.parentElement.style.setProperty('--unit-share', `${percent(rows[i].weight,total)}%`);
      });
    });
  }

  function preview(kind,payload) {
    if (window.UnitHollowEventForms.supports(kind)) return window.UnitHollowEventForms.preview(kind,payload);
    if (kind === 'fixed_floor') {
      return card('固定階',`<p>${payload.floor ? floorLabel(payload.floor) : '階未設定'} · ${h(types[payload.type])}</p>`);
    }
    if (kind === 'hollow_map') {
      return card('マップ', `<p>T${h(payload.tier || '—')} · 通常 ${payload.encounters?.normal?.length || 0}件 · 精鋭 ${payload.encounters?.elite?.length || 0}件</p>`);
    }
    return card('Tier',`<p>T${h(payload.tier || '—')} · HP ×${h(payload.hp_multiplier)} · 攻撃 ×${h(payload.attack_multiplier)}</p>`);
  }

  window.UnitHollowFloors = {labels,types,supports,floorLabel,number,defaults,configureCategories,render,update,preview,checked,numberField,errorNote,shareBar,sum,share};
})();
