(function () {
  const {h} = window.CatalogWorkspaceParts;
  const {field, select, grid, card, imageField, button, remove} = window.UnitForms;
  const labels = {relic:'淵遺物',hollow_load_stage:'魔力負荷の段階',hollow_recipe:'特別な組み合わせ',
    hollow_buff:'バフ',hollow_item:'アイテム'};
  const models = {hollow_buff:window.CatalogBuff, hollow_item:window.CatalogResources.item};
  const ranks = {1:'Ⅰ',2:'Ⅱ',3:'Ⅲ',4:'Ⅳ',5:'Ⅴ'};
  let categories = [];
  const configure = values => { categories = values; };
  const supports = kind => Object.hasOwn(labels,kind);
  const choices = values => Object.fromEntries(values.map(value=>[value,value]));

  function defaults(kind) {
    if (models[kind]) return models[kind].defaults();
    if (kind === 'relic') return {name:'',category:categories[0] || '',rank:1,target:{type:'all'},buff_id:'',cost_buff_id:'',flavor:'',image:''};
    if (kind === 'hollow_load_stage') return {name:'魔力負荷の段階',threshold:0,buff_id:''};
    return {name:'特別な組み合わせ',material_ids:['',''],result_id:''};
  }

  function reference(label,path,rows,value,optional=false) {
    const names = Object.fromEntries(rows.filter(row=>!row.deprecated || row.entry_id === value).map(row=>
      [row.entry_id,`${row.entry_id} ${row.payload.display_name || row.payload.name}`]));
    if (value && !Object.hasOwn(names,value)) names[value] = value;
    return select(label,path,{'':optional ? 'なし' : '選択',...names},value);
  }

  function render(kind,row,edit,masters,records,rawEffect) {
    const p = row.payload;
    if (models[kind]) return `<div class="cat-field-grid">${models[kind].form(p,{}, {effectText:rawEffect ?? undefined})}</div>`;
    const name = field('名前','name',p.name);
    const buffs = [...(masters.buff || []),...records.filter(row=>row.kind === 'hollow_buff')];
    const buff = (label,path,optional) => reference(label,path,buffs,p[path],optional);
    if (kind === 'hollow_load_stage') return name + grid(field('区切りの値','threshold',p.threshold,'number','min="0" step="1"'),
      buff('代償のバフ','buff_id'));
    if (kind === 'hollow_recipe') {
      const relics = records.filter(row=>row.kind === 'relic');
      return name + card('材料の淵遺物',p.material_ids.map((id,i)=>grid(reference(`材料 ${i+1}`,`material_ids.${i}`,relics,id),
        edit && p.material_ids.length > 2 ? remove('material_ids',i) : '')).join('') +
        (edit && p.material_ids.length < 4 ? button('＋ 材料を追加','recipe-material') : '')) +
        reference('できる淵遺物','result_id',relics,p.result_id);
    }
    const target = p.target || {type:'all'};
    const tagged = target.condition?.startsWith('has_tag:');
    return name + grid(select('カテゴリ','category',choices(categories),p.category),
      select('ランク','rank',ranks,p.rank),select('対象','target.type',{all:'全員',condition:'条件',nth:'N番目'},target.type),
      target.type === 'nth' ? field('開始時の並び','target.n',target.n,'number','min="1" max="6" step="1"') : '',
      target.type === 'condition' ? select('条件','target.condition',{hp_lowest:'HPが最も低い味方',
        bled_last_round:'前ラウンドで出血した味方','has_tag:':'タグを持つ味方'},tagged ? 'has_tag:' : target.condition) : '',
      target.type === 'condition' && tagged ? field('タグ','target.tag',target.condition.slice(8)) : '',
      buff('効果のバフ','buff_id'),buff('個別の代償','cost_buff_id',true)) +
      field('フレーバー','flavor',p.flavor,'area') + imageField(p.image,edit);
  }

  function preview(kind,p,records,masters) {
    if (models[kind]) return models[kind].preview(p);
    const name = id => [...records,...(masters.buff || [])].find(row=>row.entry_id === id)?.payload.name || id || '未選択';
    if (kind === 'relic') return card(labels[kind],`<p>${h(p.category)} · ランク ${h(ranks[p.rank])}</p>
      <p>効果 ${h(name(p.buff_id))}</p>${p.cost_buff_id ? `<p>代償 ${h(name(p.cost_buff_id))}</p>` : ''}`);
    if (kind === 'hollow_load_stage') return card(labels[kind],`<p>${h(p.threshold)} · ${h(name(p.buff_id))}</p>`);
    return card(labels[kind],`<p>${p.material_ids.map(key=>h(name(key))).join(' ＋ ')} → ${h(name(p.result_id))}</p>`);
  }

  function compare(a,b) {
    if (a.kind === 'relic') return (categories.indexOf(a.payload.category) - categories.indexOf(b.payload.category)) ||
      a.payload.rank - b.payload.rank || a.entry_id.localeCompare(b.entry_id);
    if (a.kind === 'hollow_load_stage') return a.payload.threshold - b.payload.threshold;
    return 0;
  }
  window.UnitHollowRewards = {labels,models,reference,supports,configure,defaults,render,preview,compare,ranks};
})();
