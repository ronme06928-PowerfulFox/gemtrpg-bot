(function () {
  const {h} = window.CatalogWorkspaceParts;
  const {field, select, grid, card, button, remove} = window.UnitForms;
  const {checked, numberField, errorNote, shareBar, sum, share} = window.UnitHollowFloors;
  const {reference} = window.UnitHollowRewards;
  const labels = {hollow_event:'イベント',treasure_chest:'宝箱',drop_table:'ドロップ表'};
  const effects = {'':'なし',buff:'一時バフ',item:'アイテム',relic:'淵遺物'};
  let skills = {};

  const supports = kind => Object.hasOwn(labels,kind);
  const configure = values => { skills = Object.fromEntries(values.map(value => [value,value])); };
  const defaults = kind => ({name:'', ...({
    hollow_event:{text:'',choices:[{label:''}]}, treasure_chest:{text:'',drop_table_id:''}, drop_table:{rows:[]},
  })[kind]});
  const refRows = (kind, masters, records) => [...(masters[kind] || []),
    ...records.filter(row => row.kind === (kind === 'relic' ? kind : 'hollow_' + kind))];
  const ref = (label,path,rows,value) => checked(path,reference(label,path,rows,value));

  function effectFields(choice, base, key, target, label, masters, records) {
    const value = choice[key] || {};
    const path = base + '.' + key;
    const type = checked(path + '.kind',select('種類',path + '.kind',effects,value.kind || ''));
    const id = value.kind ? ref('中身',path + '.id',refRows(value.kind,masters,records),value.id) : '';
    const extra = value.kind === 'buff' ? numberField('戦闘数',path + '.battles',value.battles,'min="1" step="1"') +
      checked(base + '.' + target,select('対象',base + '.' + target,{selected:'選んだ1人',all:'全員'},choice[target])) : '';
    return card(label, grid(type,id,extra));
  }

  function eventForm(p, edit, masters, records) {
    return checked('text',field('文章','text',p.text,'area')) + errorNote('choices') +
      p.choices.map((choice,index) => {
        const base = `choices.${index}`;
        const check = Object.hasOwn(choice,'difficulty');
        return card(`選択肢 ${index+1}`, grid(
          checked(base + '.label',field('ラベル',base + '.label',choice.label)),
          select('判定',base + '.check',{'no':'なし','yes':'あり'}, check ? 'yes' : 'no'),
          check ? checked(base + '.skill',select('技能',base + '.skill',skills,choice.skill)) : '',
          check ? numberField('難易度',base + '.difficulty',choice.difficulty,'min="0" step="1"') : ''
        ) + effectFields(choice,base,'effect','target',check ? '成功' : '効果',masters,records) +
          (check ? effectFields(choice,base,'failure_effect','failure_target','失敗',masters,records) : '') +
          (edit ? remove('choices',index) : ''));
      }).join('') + (edit && p.choices.length < 4 ? button('＋ 選択肢を追加','event-choice-add') : '');
  }

  function dropForm(p, edit, masters, records) {
    return `<section data-weight-path="rows" class="unit-encounter-group">
      <div class="unit-list-heading"><h4>中身と重み</h4>
        ${edit ? button('＋ 行を追加','weighted-add','data-path="rows" data-field="id"') : ''}</div>
      ${errorNote('rows')}
      ${p.rows.map((row,i) => `<div class="unit-drop-row">
        ${checked(`rows.${i}.kind`,select('種類',`rows.${i}.kind`,{item:effects.item,relic:effects.relic},row.kind))}
        ${ref('中身',`rows.${i}.id`,refRows(row.kind,masters,records),row.id)}
        ${numberField('重み',`rows.${i}.weight`,row.weight,'min="0" step="1"')}${shareBar()}
        ${edit ? remove('rows',i) : ''}</div>`).join('')}</section>`;
  }

  function chestForm(p, masters, records) {
    const tables = records.filter(row => row.kind === 'drop_table');
    const rows = tables.find(row => row.entry_id === p.drop_table_id)?.payload.rows || [];
    const total = sum(rows.map(row => row.weight));
    return checked('text',field('文章','text',p.text,'area')) + ref('ドロップ表','drop_table_id',tables,p.drop_table_id) +
      card('中身の割合', rows.length ? `<ul>${rows.map(row => {
        const item = refRows(row.kind,masters,records).find(entry => entry.entry_id === row.id);
        return `<li>${h(item?.payload.name || row.id)} · ${share(row.weight,total)}</li>`;
      }).join('')}</ul>` : '<p>中身なし</p>');
  }

  function render(kind,p,edit,masters,records) {
    const contents = kind === 'hollow_event' ? eventForm(p,edit,masters,records)
      : kind === 'treasure_chest' ? chestForm(p,masters,records) : dropForm(p,edit,masters,records);
    return checked('name',field('名前','name',p.name)) + contents;
  }

  function change(kind,p,path,value) {
    if (kind === 'drop_table' && /^rows\.\d+\.kind$/.test(path)) {
      const row = p.rows[path.split('.')[1]];
      if (row.kind !== value) Object.assign(row,{kind:value,id:''});
      return true;
    }
    if (kind !== 'hollow_event') return false;
    const [,index,part,leaf] = path.split('.');
    const choice = p.choices[index];
    if (part === 'check') {
      if (value === 'yes') Object.assign(choice, {skill:Object.keys(skills)[0] || '',difficulty:7});
      else for (const key of ['skill','difficulty','failure_effect','failure_target']) delete choice[key];
      return true;
    }
    if ((part === 'effect' || part === 'failure_effect') && leaf === 'kind') {
      const target = part === 'effect' ? 'target' : 'failure_target';
      if (choice[part]?.kind === value) return true;
      delete choice[target];
      if (!value) delete choice[part];
      else if (value === 'buff') {
        choice[part] = {kind:value,id:'',battles:1};
        choice[target] = 'selected';
      } else choice[part] = {kind:value,id:''};
      return true;
    }
    return false;
  }

  function preview(kind,p) {
    const info = kind === 'hollow_event' ? `選択肢 ${p.choices.length}件`
      : kind === 'drop_table' ? `中身 ${p.rows.length}件` : `ドロップ表 ${h(p.drop_table_id || '未選択')}`;
    return card(labels[kind],`<p>${info}</p>`);
  }

  window.UnitHollowEventForms = {supports,configure,defaults,render,change,preview};
})();
