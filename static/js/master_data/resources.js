(function () {
  const base = window.CatalogBuff;
  const h = window.CatalogGlossary.escape;
  const common = [['name', '名前', 'text'], ['description', '説明', 'textarea'], ['flavor', 'フレーバー', 'textarea'], ['effect', '効果', 'json']];
  const definitions = {
    item: {label:'アイテム', fields:[common[0], ['consumable','消耗','boolean'], ['usable','使用可能','boolean'], ['round_limit','ラウンド制限','duration'], ...common.slice(1)],
      defaults:{name:'',description:'',flavor:'',consumable:false,usable:false,round_limit:-1,effect:{}}},
    passive: {label:'特殊パッシブ', fields:[common[0], ['cost','取得コスト','number'], ...common.slice(1)],
      defaults:{name:'',cost:0,description:'',flavor:'',effect:{}}},
    radiance: {label:'輝化スキル', fields:[common[0], ['cost','取得コスト','number'], ['duration','持続','duration'], ['granted_tag_ids','付与タグ','tags'], ...common.slice(1)],
      defaults:{name:'',cost:0,description:'',flavor:'',effect:{},duration:-1,granted_tag_ids:[]}},
  };
  function integer(value) {
    if (!/^-?\d+$/.test(value) || !Number.isSafeInteger(Number(value))) throw new Error('整数で入力してください。');
    return Number(value);
  }
  const duration = (key, value) => value === -1 ? key === 'round_limit' ? '制限なし' : '解除まで' : `${value}ラウンド`;
  const facts = rows => `<dl class="cat-facts">${rows.map(([label,value])=>`<div><dt>${h(label)}</dt><dd>${h(value)}</dd></div>`).join('')}</dl>`;
  function tagsField(value, errors, input) {
    const valid = Array.isArray(value) && value.every(tag=>typeof tag === 'string');
    return `<fieldset class="cat-array-field cat-field-wide"><legend>付与タグ</legend><div id="cat-granted_tag_ids-chips" class="cat-chips">${valid ? base.chips('granted_tag_ids',value) : '<p class="cat-field-error">文字列の配列にしてください。JSONの節で修正できます。</p>'}</div><div class="cat-alias-entry"><label class="cat-array-label">タグを入力<input id="cat-granted-tag-input" value="${h(input)}" placeholder="Enterで追加" ${valid ? '' : 'disabled'}></label><button type="button" class="cat-button" data-tag-add="true" ${valid ? '' : 'disabled'}>追加</button></div><span class="cat-field-error" id="cat-error-granted_tag_ids">${h(errors['input:granted_tag_ids'] || errors.granted_tag_ids)}</span></fieldset>`;
  }
  function make(kind, definition) {
    const {label,fields} = definition;
    const defaults = () => JSON.parse(JSON.stringify(definition.defaults));
    function parseField(key, value) {
      if (key === 'effect') return base.parseJSON(value);
      const type = fields.find(field=>field[0]===key)?.[2];
      if (type === 'boolean') {
        if (!['true','false'].includes(value)) throw new Error('はい・いいえから選んでください。');
        return value === 'true';
      }
      if (type === 'number' || type === 'duration') return integer(value);
      if (type === 'tags') return window.CatalogGlossary.parseField('synonyms',value);
      return value;
    }
    function form(payload, errors = {}, options = {}) {
      return fields.filter(([key])=>!options.section || window.CatalogEditor.keys(kind,options.section).includes(key)).map(([key,title,type])=>{
        const value = payload[key] ?? defaults()[key];
        if (type === 'tags') return tagsField(value,errors,options.tagInput || '');
        const attrs = `id="cat-field-${key}" data-field="${key}" aria-describedby="cat-error-${key}"`;
        let control;
        if (type === 'boolean') control = `<select ${attrs}><option value="true" ${value === true ? 'selected' : ''}>はい</option><option value="false" ${value === false ? 'selected' : ''}>いいえ</option></select>`;
        else if (type === 'duration') control = `<span class="cat-duration-row"><select data-duration-mode data-duration-field="${key}" aria-label="${title}の単位"><option value="rounds" ${value !== -1 ? 'selected' : ''}>ラウンド数</option><option value="permanent" ${value === -1 ? 'selected' : ''}>${key === 'round_limit' ? '制限なし' : '解除まで'}</option></select><input ${attrs} aria-label="${title}のラウンド数" type="number" step="1" value="${h(value === -1 ? '' : value)}" ${value === -1 ? 'disabled' : ''}></span>`;
        else if (type === 'textarea') control = `<textarea data-catalog-text ${attrs} rows="3">${h(value)}</textarea>`;
        else if (type === 'json') control = `<textarea ${attrs} class="cat-effect-source" spellcheck="false" rows="6">${h(options.effectText ?? JSON.stringify(value,null,2))}</textarea>`;
        else control = `<input ${attrs} type="${type === 'number' ? 'number' : 'text'}" ${type === 'number' ? 'step="1"' : ''} value="${h(value)}">`;
        return `<label class="cat-field ${['textarea','json'].includes(type) ? 'cat-field-wide' : ''}">${h(title)}${key === 'name' ? ' *' : ''}${control}<span class="cat-field-error" id="cat-error-${key}">${h(errors['input:'+key] || errors[key])}</span></label>`;
      }).join('');
    }
    function metadata(payload) {
      if (kind === 'item') return `${payload.usable ? '使用可能' : '使用不可'} · ${payload.consumable ? '消耗' : '消耗なし'} · ${duration('round_limit',payload.round_limit ?? -1)}`;
      return `取得コスト ${payload.cost ?? 0}${kind === 'radiance' ? ' · '+duration('duration',payload.duration ?? -1) : ''}`;
    }
    function preview(payload) {
      const details = fields.filter(([_key,_title,type])=>['boolean','number','duration'].includes(type)).map(([key,title,type])=>[title,type === 'boolean' ? payload[key] ? 'はい' : 'いいえ' : type === 'duration' ? duration(key,payload[key] ?? -1) : payload[key] ?? 0]);
      const markup = value => window.Glossary?.parseMarkupToHTML(String(value || '')) ?? h(value);
      return `<section class="bo-workspace__card"><h4>${label}のプレビュー</h4><details class="buff-accordion" open><summary class="buff-summary"><div class="buff-summary-body"><span class="buff-name">${h(payload.name || '名前未入力')}</span><div class="buff-meta">${h(metadata(payload))}</div></div><span class="buff-arrow">▼</span></summary><div class="buff-body"><div class="buff-desc-row">${markup(payload.description)}</div>${payload.flavor ? `<div class="buff-flavor-row">${markup(payload.flavor)}</div>` : ''}</div></details>${facts(details)}${kind === 'radiance' ? `<div class="cat-chips">${Array.isArray(payload.granted_tag_ids) ? payload.granted_tag_ids.map(tag=>`<span class="cat-chip">${h(tag)}</span>`).join('') : '<span class="cat-field-error">付与タグは文字列の配列で入力してください。</span>'}</div>` : ''}</section>`;
    }
    return {...base,kind,label,fields,defaults,parseField,form,preview,detail:preview,recordMeta:metadata,validatePayload() {},
      jsonHint:'名前・説明・効果などを編集します。IDは含めません。',
    };
  }
  const models = Object.fromEntries(Object.entries(definitions).map(([kind,definition])=>[kind,make(kind,definition)]));
  const summonFields = [['name','名前'],['hp','HP'],['maxHp','最大HP'],['mp','MP'],['maxMp','最大MP'],['initial_skill_ids','最初から持つスキル'],['hidden_skills','秘匿スキル'],['SPassive','特殊パッシブ'],['radiance_skills','輝化スキル'],['inventory','所持アイテム'],['summon_duration_mode','持続の種類'],['summon_duration','持続ラウンド'],['allow_duplicate_same_team','同陣営の重複'],['params','能力値'],['tag_ids','タグ'],['disabled_tag_ids','無効なタグ'],['special_buffs','バフ'],['flags','設定']];
  function summonPreview(payload, options = {}) {
    const skills = Array.isArray(payload.initial_skill_ids) ? payload.initial_skill_ids : [];
    const params = Array.isArray(payload.params) ? payload.params.filter(row=>row && typeof row === 'object') : [];
    const lasting = payload.summon_duration_mode === 'permanent' ? '解除まで' : `${payload.summon_duration ?? 0}ラウンド`;
    return `<section class="bo-workspace__card"><h4>召喚テンプレートのプレビュー</h4><h3>${h(payload.name || '名前未入力')}</h3>${facts([['HP',`${payload.hp ?? 0} / ${payload.maxHp ?? 0}`],['MP',`${payload.mp ?? 0} / ${payload.maxMp ?? 0}`],['召喚の持続',lasting]])}</section><section class="bo-workspace__card"><h4>最初から持つスキル</h4>${skills.length ? `<ul class="cat-effect-list">${skills.map(id=>{const row=options.skillEntries?.find(row=>row.entry_id===id);return `<li><code>${h(id)}</code> ${h(row?.payload.デフォルト名称 || '公開名なし')}</li>`;}).join('')}</ul>` : '<p class="cat-caption">なし</p>'}</section><section class="bo-workspace__card"><h4>能力値</h4>${facts(params.map(row=>[row.label,row.value]))}</section>`;
  }
  models.summon = {...base,kind:'summon',label:'召喚テンプレート',form:null,fields:summonFields,
    defaults:()=>({name:'',hp:0,maxHp:0,mp:0,maxMp:0,initial_skill_ids:[],hidden_skills:[],SPassive:[],radiance_skills:[],inventory:{},summon_duration_mode:'permanent',summon_duration:0,allow_duplicate_same_team:true,params:[],tag_ids:[],disabled_tag_ids:[],special_buffs:[],flags:{}}),
    validatePayload() {},preview:summonPreview,detail:summonPreview,recordMeta:payload=>`HP ${payload.hp ?? 0} / MP ${payload.mp ?? 0}`,
    recordDescription:payload=>`${payload.summon_duration_mode === 'permanent' ? '解除まで' : `${payload.summon_duration ?? 0}ラウンド`} · スキル ${Array.isArray(payload.initial_skill_ids) ? payload.initial_skill_ids.length : 0}件`,jsonHint:'召喚テンプレートのJSONを編集します。baseName（ID）は含めません。',
  };
  window.CatalogResources = models;
})();
