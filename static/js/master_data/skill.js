(function () {
  const base = window.CatalogGlossary, effects = window.CatalogSkillEffects, h = base.escape;
  let schemas = {}, references = {};
  const groups = [['物理', [['Ps','斬撃'],['Pb','打撃'],['Pp','貫通']]], ['魔法', [['Ms','斬撃'],['Mb','打撃'],['Mp','貫通']]],
    ['防御・補助', [['D','防御・回避'],['B','宝石の加護'],['C','共通']]], ['敵', [['E','敵スキル']]]];
  const fields = [['デフォルト名称','名前'],['分類','分類'],['距離','距離'],['属性','属性'],['取得コスト','取得コスト'],
    ['基礎威力','基礎威力'],['ダイス威力','ダイス威力'],['コスト','コスト'],['特記','特記'],['発動時効果','発動時効果'],['チャットパレット','チャットパレット'],['特記処理','特記処理']];
  const choices = {分類:['物理','魔法','補助','防御','回避'],距離:['','近接','遠隔','広域-個別','広域-合算'],属性:['','打撃','斬撃','貫通']};
  const defaults = () => ({...Object.fromEntries(fields.slice(0,-1).map(([key])=>[key,''])),分類:'物理',ダイス威力:'+0',特記処理:{}});
  function configure(value, refs) { schemas = value; references = refs; }
  function palette(payload, id) {
    const correction = window.CatalogSkillNotes.omitsCorrection(payload.分類, payload.特記) ? '' : {物理:'+1d{物理補正}',魔法:'+1d{魔法補正}'}[payload.分類] || '';
    return `${payload.基礎威力 || ''}${payload.ダイス威力 || ''}${correction} 【${id || ''} ${payload.デフォルト名称 || ''}】`;
  }
  function diceControl(value,error = '') {
    const raw = String(value ?? ''), match = raw.match(/^([+-])(\d+)d(\d+)$/), none = raw === '+0';
    if (!none && !match) return `${effects.control('ダイス威力',value,{type:'string'},'id="cat-field-ダイス威力" data-field="ダイス威力"')}<span class="cat-field-error" id="cat-error-ダイス威力">${h(error)}</span>`;
    const [sign,count,faces] = match ? match.slice(1) : ['+','1','4'];
    return `<div class="cat-dice cat-field-wide" data-dice><span class="cat-field-label">ダイス威力</span><div class="cat-dice-row"><label class="cat-check"><input type="checkbox" data-dice-part="none" ${none ? 'checked' : ''}>振らない</label><select data-dice-part="sign" aria-label="足すか引くか" ${none ? 'disabled' : ''}><option value="+" ${sign === '+' ? 'selected' : ''}>＋ 足す</option><option value="-" ${sign === '-' ? 'selected' : ''}>− 引く</option></select><input type="number" min="1" step="1" data-dice-part="count" aria-label="ダイスの数" value="${h(count)}" ${none ? 'disabled' : ''}><span class="cat-dice-d">d</span><input type="number" min="1" step="1" data-dice-part="faces" aria-label="ダイスの面の数" value="${h(faces)}" ${none ? 'disabled' : ''}><output class="cat-dice-value">${h(raw)}</output></div><span class="cat-field-error" id="cat-error-ダイス威力">${h(error)}</span></div>`;
  }
  function diceValue({none,sign,count,faces}) {
    if (none) return '+0';
    if (![count,faces].every(value=>/^\d+$/.test(String(value)) && Number.isSafeInteger(Number(value)) && Number(value)>0)) throw new Error('ダイスの数と面は1以上の整数で入力してください。');
    return `${sign === '-' ? '-' : '+'}${Number(count)}d${Number(faces)}`;
  }
  function form(payload, errors = {}, options = {}) {
    const input = fields.slice(0,-1).filter(([key])=>!options.section || window.CatalogEditor.keys('skill',options.section).includes(key)).map(([key, label]) => {
      if (key === 'ダイス威力') return diceControl(payload[key],errors['input:'+key] || errors[key]);
      const spec = {type: ['コスト','特記','発動時効果','チャットパレット'].includes(key) ? 'textarea' : 'string', options: choices[key], required:key === 'デフォルト名称'};
      const attrs = `id="cat-field-${key}" data-field="${key}" aria-describedby="cat-error-${key}"`;
      const control = spec.type === 'textarea' ? `<label class="cat-field cat-field-wide">${label}<textarea ${key === 'チャットパレット' ? '' : 'data-catalog-text '}${attrs} rows="3">${h(payload[key] ?? '')}</textarea></label>` : effects.control(label, payload[key], spec, attrs);
      return `<div class="${spec.type === 'textarea' ? 'cat-field-wide' : ''}">${control}<span class="cat-field-error" id="cat-error-${key}">${h(errors[`input:${key}`] || errors[key])}</span>${key === 'チャットパレット' ? '<button type="button" class="cat-button" data-skill-action="palette">項目から作る</button>' : ''}</div>`;
    }).join('');
    if (options.section === 'description') return `<div class="cat-field-wide"><div class="cat-writer-top"><h3 class="cat-heading-info">文章${window.CatalogInfo.render('効果から文章を作る','「効果」の節の設定から、ゲームの書き方の文章を作ります。今の文章と欄ごとに見比べて、置き換えるかを選べます。保存はしません。')}</h3><button type="button" class="cat-button" data-action="writer-open">効果から文章を作る</button></div><div id="cat-writing-result"></div></div>${input}`;
    const tags = () => `<section class="cat-field-wide">${payload.特記処理 === undefined || effects.object(payload.特記処理) ? window.CatalogSkillInputs.tagForm(payload.特記処理 || {},references,options.skillTagInput) : window.CatalogSkillInputs.jsonLink()}</section>`;
    if (options.section === 'body') return input + tags();
    const section = options.section;
    const rule = payload.特記処理;
    const fallback = window.CatalogSkillInputs.jsonLink;
    if (rule !== undefined && !effects.object(rule)) return input + fallback();
    const root = rule || {};
    const cost = root.cost;
    const costForm = (cost === undefined || Array.isArray(cost) && cost.every(row=>effects.object(row) && Object.keys(row).every(key=>['type','value'].includes(key))))
      ? `<h3>コスト</h3>${(cost || []).map((row,index)=>`<div class="cat-cost-row">${effects.control('リソース',row.type,{options:['FP','MP','HP']},`data-cost-index="${index}" data-cost-field="type" data-value-type="string"`)}${effects.control('消費量',row.value,{type:'number'},`data-cost-index="${index}" data-cost-field="value" data-value-type="number"`)}<button type="button" class="cat-button" data-cost-remove="${index}">削除</button></div>`).join('')}<button type="button" class="cat-button" data-cost-add>コストを追加</button>` : fallback();
    if (section === 'cost') return `<section class="cat-field-wide">${costForm}</section>`;
    const bonus = () => window.CatalogSkillInputs.bonusForm(root,schemas,references,options.skillTagInput,options.bonusOperation,errors);
    if (section === 'bonus') return `<section class="cat-field-wide">${bonus()}</section>`;
    const rootInput = effects.control('対象範囲',root.target_scope,{options:['opposing_team','same_team','any','self'],labels:{opposing_team:'敵陣営',same_team:'同陣営',any:'全陣営',self:'自分'}},'data-rule-field="target_scope" data-value-type="string"');
    const list = root.effects;
    const extra = Object.keys(root).some(key=>!['schema','id','target_scope','cost','power_bonus','tags','effects'].includes(key)) ? fallback() : '';
    const effectForm = `<h3>効果</h3>${effects.keyToggle()}${rootInput}${extra}${Array.isArray(list) ? list.map((effect,index)=>effects.form(effect,index,schemas,references)).join('') : list === undefined ? '' : fallback()}<button type="button" class="cat-button" data-effect-action="add">効果を追加</button>`;
    return input + `<section class="cat-field-wide cat-rule-editor">${!section ? '<h3>特記処理</h3>'+tags()+costForm+bonus() : ''}${effectForm}<span class="cat-field-error" id="cat-error-特記処理">${h(errors['特記処理'])}</span><span class="cat-field-error" data-skill-error></span></section>`;
  }
  function preview(payload, options = {}) {
    const detail = window.formatSkillDetailHTML ? window.formatSkillDetailHTML(Object.fromEntries(fields.slice(0,-1).map(([key])=>[key,String(payload[key] ?? '')]))) : `<p class="cat-description">${h(payload.発動時効果 || '')}</p>`;
    const list = payload.特記処理?.effects;
    const writer = window.CatalogSkillText?.createWriter(options.textReferences);
    const lines = Array.isArray(list) && writer ? writer.describe(list) : (Array.isArray(list) ? list.map(row=>({row,text:null})) : []);
    const descriptions = lines.map(({row,text})=>`<li>${h(text === null ? effects.summary(row,schemas) : writer.plain(text))}<small>${h(effects.timingLabels[row?.timing] || 'タイミング未指定')}${text === null && row?.condition ? ' · '+h(effects.conditionText(row.condition)) : ''}</small></li>`).join('');
    return `<section class="bo-workspace__card cat-skill-preview"><h4>ゲームでの見え方</h4>${detail}</section>${options.power || ''}<section class="bo-workspace__card"><h4 class="cat-heading-info">効果の説明${window.CatalogInfo.render('効果の説明','「効果」の節の設定を文にしたもの。上の文章と食い違いがないかを見比べます。')}</h4>${lines.length ? `<ol class="cat-effect-list">${descriptions}</ol>` : '<p class="cat-caption">効果なし</p>'}</section>`;
  }
  window.CatalogSkill = {...base, kind:'skill', label:'スキル', fields, groups, categories:[], defaults, form, preview, configure, palette, diceControl, diceValue,
    displayName: payload=>payload.デフォルト名称,
    validatePayload: () => {}, parseField: (_,value)=>value,
    detail: (payload,options)=>preview(payload,options), externalLink:()=>'',
    recordMeta: payload=>[payload.分類,payload.距離,payload.属性].filter(Boolean).join(' · '),
    recordDescription: payload=>window.CatalogEditor.plainText(payload.発動時効果 || payload.コスト),
    jsonHint:'スキル全体を編集します。特記処理はオブジェクト、ID・tagsは含めません。',
    filter(rows, filters) {
      const needle=(filters.search || '').toLocaleLowerCase();
      return rows.filter(row=>(filters.status === 'all' || row.status === filters.status)
        && (!filters.category || (row.id_prefix || row.target_id.split('-')[0]) === filters.category)
        && [row.target_id,row.payload.デフォルト名称,row.payload.コスト,row.payload.発動時効果,row.payload.特記].join(' ').toLocaleLowerCase().includes(needle));
    },
  };
})();
