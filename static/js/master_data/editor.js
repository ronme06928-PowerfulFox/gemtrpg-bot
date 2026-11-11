(function () {
  const h = window.CatalogGlossary.escape;
  const fields = {
    glossary:{body:['display_name','category','synonyms','sort_order'],description:['short','long','flavor'],links:['links']},
    skill:{body:['デフォルト名称','分類','距離','属性','取得コスト','基礎威力','ダイス威力','チャットパレット'],description:['使用時効果','発動時効果','特記'],cost:['特記処理'],bonus:['特記処理'],effects:['特記処理']},
  };
  const generic = {body:['name','display_name','default_duration','cost','duration','round_limit','usable','consumable','granted_tag_ids'],description:['description','flavor'],effects:['effect']};
  function sections(model) {
    const labels = {body:'本体',description:model.kind === 'skill' ? '文章' : '説明',links:'関連用語',cost:'コスト',bonus:'補正',effects:'効果'};
    return [...Object.keys(model.kind === 'summon' ? {} : fields[model.kind] || generic).map(key=>[key,labels[key]]),['json','JSON'],...(model.kind === 'skill' ? [['text','文章から効果を作る']] : []),['preview','プレビュー']];
  }
  function sectionFor(kind,key) {
    key = key.replace(/^input:/,'');
    if (kind === 'skill' && key.startsWith('skill:')) return key.startsWith('skill:cost:') ? 'cost' : key.startsWith('skill:tags') ? 'body' : key.startsWith('skill:bonus:') ? 'bonus' : 'effects';
    if (kind === 'skill' && key.startsWith('特記処理')) return key.includes('tags') ? 'body' : key.includes('power_bonus') ? 'bonus' : key.includes('cost') ? 'cost' : 'effects';
    return Object.entries(fields[kind] || generic).find(([,names])=>names.some(name=>key === name || key.startsWith(name+'.') || key.startsWith(name+'[')))?.[0] || 'json';
  }
  function keys(kind,section) { return (fields[kind] || generic)[section] || []; }
  function navigation(model,section,errors) {
    const marked = new Set(Object.keys(errors).map(key=>sectionFor(model.kind,key)));
    return `<nav class="cat-toc" aria-label="編集の節">${sections(model).map(([key,label])=>`<button type="button" data-section="${key}" class="${['json','text','preview'].includes(key) ? 'cat-toc-tool' : ''}" aria-current="${section === key}">${h(label)}${marked.has(key) ? '<span class="cat-field-error">● 誤りあり</span>' : ''}</button>`).join('')}</nav>`;
  }
  function jsonText(kind,payload) {
    if (kind !== 'summon') return window.CatalogJson.stringify(payload);
    const order = ['name','hp','maxHp','mp','maxMp','summon_duration_mode','summon_duration','initial_skill_ids','hidden_skills','params'];
    return window.CatalogJson.stringify(window.CatalogJson.ordered(payload,[...new Set([...order,...Object.keys(payload)])].filter(key=>key in payload)));
  }
  function examples(entries) {
    const seen = new Set();
    return entries.filter(row=>!row.deprecated).flatMap(row=>{
      const effect = row.payload.effect;
      if (!effect || typeof effect !== 'object' || Array.isArray(effect)) return [];
      const key = effect.type || Object.keys(effect).join('・') || '空の効果';
      if (seen.has(key)) return [];
      seen.add(key);return [{payload:effect,id:row.entry_id,name:row.payload.display_name || row.payload.name,description:plainText(row.payload.description || '')}];
    });
  }
  function exampleButtons(entries) {
    return `<section class="cat-effect-examples"><h4>公開中の効果の例</h4>${examples(entries).map((row,index)=>`<button type="button" class="cat-button" data-effect-example="${index}"><strong>${h(row.id)} ${h(row.name)}と同じ形</strong>${row.description ? `<small>${h(row.description)}</small>` : ''}</button>`).join('') || '<p class="cat-caption">例はありません。</p>'}</section>`;
  }
  const plainText = value => String(value || '').replace(/\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g,(_match,id,name)=>name || id);
  window.CatalogEditor = {sections,sectionFor,keys,navigation,jsonText,examples,exampleButtons,plainText};
})();
