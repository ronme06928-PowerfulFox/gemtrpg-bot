(function () {
  const base = window.CatalogGlossary, effects = window.CatalogSkillEffects, h = base.escape;
  let schemas = {}, references = {};
  const groups = [['物理', [['Ps','斬撃'],['Pb','打撃'],['Pp','貫通']]], ['魔法', [['Ms','斬撃'],['Mb','打撃'],['Mp','貫通']]],
    ['防御・補助', [['D','防御・回避'],['B','宝石の加護'],['C','共通']]], ['敵', [['E','敵スキル']]]];
  const fields = [['デフォルト名称','名前'],['分類','分類'],['距離','距離'],['属性','属性'],['取得コスト','取得コスト'],
    ['基礎威力','基礎威力'],['ダイス威力','ダイス威力'],['使用時効果','使用時効果'],['特記','特記'],['発動時効果','発動時効果'],['チャットパレット','チャットパレット'],['特記処理','特記処理']];
  const choices = {分類:['物理','魔法','補助','防御','回避'],距離:['','近接','遠隔','広域-個別','広域-合算'],属性:['','打撃','斬撃','貫通']};
  const defaults = () => ({...Object.fromEntries(fields.slice(0,-1).map(([key])=>[key,''])),分類:'物理',特記処理:{}});
  function configure(value, refs) { schemas = value; references = refs; }
  function palette(payload, id) {
    const correction = {物理:'+1d{物理補正}',魔法:'+1d{魔法補正}'}[payload.分類] || '';
    return `${payload.基礎威力 || ''}${payload.ダイス威力 || ''}${correction} 【${id || ''} ${payload.デフォルト名称 || ''}】`;
  }
  function form(payload, errors = {}, options = {}) {
    const input = fields.slice(0,-1).map(([key, label]) => {
      const spec = {type: ['使用時効果','特記','発動時効果','チャットパレット'].includes(key) ? 'textarea' : 'string', options: choices[key], required:key === 'デフォルト名称'};
      const attrs = `id="cat-field-${key}" data-field="${key}" aria-describedby="cat-error-${key}"`;
      const control = spec.type === 'textarea' ? `<label class="cat-field cat-field-wide">${label}<textarea ${attrs} rows="3">${h(payload[key] ?? '')}</textarea></label>` : effects.control(label, payload[key], spec, attrs);
      return `<div class="${spec.type === 'textarea' ? 'cat-field-wide' : ''}">${control}<span class="cat-field-error" id="cat-error-${key}">${h(errors[`input:${key}`] || errors[key])}</span>${key === 'チャットパレット' ? '<button type="button" class="cat-button" data-skill-action="palette">項目から作る</button>' : ''}</div>`;
    }).join('');
    const rule = payload.特記処理;
    if (rule !== undefined && !effects.object(rule)) return input + '<p class="cat-callout cat-field-wide">特記処理はJSON で編集してください。</p>';
    const root = rule || {};
    const rootInputs = effects.control('power_bonus · 威力補正', root.power_bonus, {type:'json'}, 'data-rule-field="power_bonus" data-value-type="json"')
      + effects.control('tags · タグ', root.tags, {type:'json'}, 'data-rule-field="tags" data-value-type="json"')
      + effects.control('target_scope · 対象範囲', root.target_scope, {type:'string',options:['opposing_team','same_team','any','self'],labels:{opposing_team:'敵陣営',same_team:'同陣営',any:'全陣営',self:'自分'}}, 'data-rule-field="target_scope" data-value-type="string"');
    const cost = root.cost;
    const costForm = (cost === undefined || Array.isArray(cost) && cost.every(row=>effects.object(row) && Object.keys(row).every(key=>['type','value'].includes(key))))
      ? `<h4>コスト</h4>${(cost || []).map((row,index)=>`<div class="cat-cost-row">${effects.control('リソース',row.type,{options:['FP','MP','HP']},`data-cost-index="${index}" data-cost-field="type" data-value-type="string"`)}${effects.control('消費量',row.value,{type:'number'},`data-cost-index="${index}" data-cost-field="value" data-value-type="number"`)}<button type="button" class="cat-button" data-cost-remove="${index}">削除</button></div>`).join('')}<button type="button" class="cat-button" data-cost-add>コストを追加</button>`
      : effects.control('cost · コスト（JSON で編集）',cost,{type:'json'},'data-rule-field="cost" data-value-type="json"');
    const list = root.effects;
    return input + `<section class="cat-field-wide cat-rule-editor"><h3>特記処理</h3><div class="cat-field-grid">${rootInputs}</div>${costForm}<span class="cat-field-error" id="cat-error-特記処理">${h(errors['特記処理'])}</span>${Array.isArray(list) ? list.map((effect,index)=>effects.form(effect,index,schemas,references)).join('') : list === undefined ? '' : '<p class="cat-callout">効果の配列はJSON で編集してください。</p>'}<button type="button" class="cat-button" data-effect-action="add">効果を追加</button><span class="cat-field-error" data-skill-error></span></section>`;
  }
  function preview(payload, options = {}) {
    const id = options.entryId || '';
    const card = `<div class="skill-picker-card"><div class="skill-card-id">${h(id)}</div><div class="skill-card-name">${h(payload.デフォルト名称 || '名前未入力')}</div><div class="skill-card-badges">${['分類','距離','属性'].filter(key=>payload[key]).map(key=>`<span class="cat-badge">${h(payload[key])}</span>`).join('')}</div><div class="skill-card-cost">${h(payload.使用時効果 || '—')}</div></div>`;
    const detail = window.formatSkillDetailHTML ? window.formatSkillDetailHTML(Object.fromEntries(fields.slice(0,-1).map(([key])=>[key,String(payload[key] ?? '')]))) : `<p class="cat-description">${h(payload.発動時効果 || '')}</p>`;
    const list = payload.特記処理?.effects;
    return `<section class="bo-workspace__card"><h4>スキルのプレビュー</h4>${card}${detail}</section><section class="bo-workspace__card"><h4>効果の説明</h4>${Array.isArray(list) ? `<ol class="cat-effect-list">${list.map(row=>`<li>${h(effects.summary(row,schemas))}<small>${h(row?.timing)} · ${h(row?.type)}</small></li>`).join('')}</ol>` : '<p class="cat-caption">効果なし</p>'}</section>`;
  }
  function diff(before, after) { return [...new Set([...fields.map(([key])=>key),...Object.keys(before || {}),...Object.keys(after || {})])].map(key=>({key,label:fields.find(row=>row[0]===key)?.[1] || key,before:before?.[key],after:after?.[key],changed:JSON.stringify(before?.[key])!==JSON.stringify(after?.[key])})); }
  window.CatalogSkill = {...base, kind:'skill', label:'スキル', fields, groups, categories:[], defaults, form, preview, configure, palette, diff,
    displayName: payload=>payload.デフォルト名称,
    validatePayload: () => {}, parseField: (_,value)=>value,
    detail: (payload,options)=>preview(payload,options), externalLink:()=>'',
    recordMeta: payload=>[payload.分類,payload.距離,payload.属性].filter(Boolean).join(' · '),
    recordDescription: payload=>payload.発動時効果 || payload.使用時効果,
    jsonHint:'スキル全体を編集します。特記処理はオブジェクト、ID・tagsは含めません。',
    filter(rows, filters) {
      const needle=(filters.search || '').toLocaleLowerCase();
      return rows.filter(row=>(filters.status === 'all' || row.status === filters.status)
        && (!filters.category || (row.id_prefix || row.target_id.split('-')[0]) === filters.category)
        && [row.target_id,row.payload.デフォルト名称,row.payload.使用時効果,row.payload.発動時効果,row.payload.特記].join(' ').toLocaleLowerCase().includes(needle));
    },
  };
})();
