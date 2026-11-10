(function () {
  const effects = window.CatalogSkillEffects, h = window.CatalogGlossary.escape;
  const operations = {FIXED:'固定加算',FIXED_IF_EXISTS:'閾値以上で加算',PER_N_BONUS:'一定数ごとに加算',MULTIPLY:'参照値に比例'};
  function bonusAction(rule, action, index, operation = 'FIXED') {
    const result = effects.clone(rule);
    if (result.power_bonus !== undefined && !Array.isArray(result.power_bonus)) throw new Error('威力補正はJSONの節で修正してください。');
    result.power_bonus ??= [];
    if (action === 'add') {
      if (!operations[operation]) throw new Error('補正の方式を選んでください。');
      result.power_bonus.push({operation,...(operation === 'MULTIPLY' ? {value_per_param:1} : {value:1})});
    } else result.power_bonus.splice(index,1);
    return result;
  }
  function changeBonus(rule,index,path,raw,type) {
    const result = effects.clone(rule);
    result.power_bonus[index] = effects.setField(result.power_bonus[index],path,raw,type);
    return result;
  }
  const jsonLink = () => '<p class="cat-callout">この内容はJSONの節で編集できます。値は保持します。</p><button type="button" class="cat-button" data-section="json">JSONで編集</button>';
  function bonusForm(rule,schemas,references,tagInput = '',operation = 'FIXED',errors = {}) {
    const rows = rule.power_bonus;
    let html = '<h3>補正</h3>';
    if (rows !== undefined && (!Array.isArray(rows) || rows.some(row=>!effects.object(row)))) html += jsonLink();
    else html += (rows || []).map((row,index)=>{
      const op = row.operation || row.operator || 'FIXED';
      if (!operations[op] || !effects.conditionEditable(row.condition)) return `<section class="bo-workspace__card"><h4>補正 ${index+1}</h4>${jsonLink()}</section>`;
      const input = (key,label,spec) => `<div>${effects.control(label,key === 'operation' ? op : effects.get(row,key),spec,`data-bonus-index="${index}" data-bonus-field="${key}" data-value-type="${spec.type || 'string'}"`,references)}<span class="cat-field-error" data-bonus-error="${index}:${key}">${h(errors[`input:skill:bonus:${index}:${key}`])}</span></div>`;
      let body = input('operation','方式',{options:Object.keys(operations),labels:operations});
      body += input('apply_to','補正する威力',{options:['base','dice','final'],labels:{base:'基礎威力',dice:'ダイス威力',final:'最終威力'}});
      if (op !== 'FIXED') body += input('source','参照元',{options:['self','target'],labels:{self:'自分',target:'対象'}}) + input('param','参照する値',{type:'string'});
      body += op === 'MULTIPLY' ? input('value_per_param','参照値あたりの補正',{type:'number'}) : input('value','補正量',{type:'number'});
      if (op === 'FIXED_IF_EXISTS') body += input('threshold','閾値',{type:'int'});
      if (op === 'PER_N_BONUS') body += input('per_N','何個ごと',{type:'int'});
      for (const [key,label] of [['min_bonus','補正の下限'],['max_bonus','補正の上限']]) body += input(key,label,{type:'int'});
      body += `<label class="cat-field">条件<select data-bonus-condition="${index}"><option value="none" ${row.condition === undefined ? 'selected' : ''}>無し</option><option value="simple" ${row.condition !== undefined ? 'selected' : ''}>条件を指定</option></select></label>`;
      if (row.condition !== undefined) for (const key of ['source','param','operator','value']) body += input(`condition.${key}`,effects.conditionSpec(key,schemas).label,effects.conditionSpec(key,schemas));
      return `<section class="bo-workspace__card"><h4>補正 ${index+1}</h4><div class="cat-field-grid">${body}</div><button type="button" class="cat-button" data-bonus-remove="${index}">削除</button></section>`;
    }).join('') + `<div class="cat-actions"><label class="cat-field">追加する方式<select id="cat-bonus-operation">${Object.entries(operations).map(([key,label])=>`<option value="${key}" ${key === operation ? 'selected' : ''}>${label}</option>`).join('')}</select></label><button type="button" class="cat-button" data-bonus-add>補正を追加</button></div>`;
    return html;
  }
  function tagForm(rule,references,tagInput = '') {
    const tags = rule.tags;
    const html = '<h3>タグ</h3>';
    if (tags !== undefined && (!Array.isArray(tags) || tags.some(value=>typeof value !== 'string'))) return html + jsonLink();
    return html + `<div class="cat-chips">${(tags || []).map((value,index)=>`<span class="cat-chip">${h(value)}<button type="button" class="cat-chip-remove" data-skill-tag-remove="${index}" aria-label="${h(value)}を外す">×</button></span>`).join('')}</div><div class="cat-actions"><label class="cat-field">タグを入力<input id="cat-skill-tag-input" list="cat-skill-tag-options" value="${h(tagInput)}" placeholder="候補を選ぶか入力してEnter"><datalist id="cat-skill-tag-options">${(references.tags || []).map(row=>`<option value="${h(row.name)}"></option>`).join('')}</datalist></label><button type="button" class="cat-button" data-skill-tag-add>タグを追加</button></div>`;
  }
  window.CatalogSkillInputs = {bonusAction,changeBonus,bonusForm,tagForm,jsonLink};
})();
