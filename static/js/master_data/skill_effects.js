(function () {
  const h = window.CatalogGlossary.escape;
  const clone = value => window.CatalogJson.clone(value);
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const timingLabels = {PRE_MATCH:'使用時',BEFORE_POWER_ROLL:'威力ロール前',WIN:'マッチ勝利時',LOSE:'マッチ敗北時',HIT:'的中時',UNOPPOSED:'一方攻撃時',AFTER_DAMAGE_APPLY:'ダメージ適用後',RESOLVE_START:'解決開始時',RESOLVE_STEP_END:'解決手順終了時',RESOLVE_END:'解決終了時',END_MATCH:'マッチ終了時',END_ROUND:'ラウンド終了時',IMMEDIATE:'即時発動',BATTLE_START:'戦闘開始時'};
  const sources = {self:'自分',target:'対象',actor_skill:'自分のスキル',target_skill:'対象のスキル',context:'状況',relation:'陣営の関係'};
  const operators = {GTE:'以上',LTE:'以下',GT:'より大きい',LT:'未満',EQ:'と等しい',EQUALS:'と等しい',NE:'と異なる',NOT_EQUALS:'と異なる',IN:'に含まれる',NOT_IN:'に含まれない'};
  const get = (value, path) => path.split('.').reduce((row, key) => row?.[key], value);
  function setField(effect, path, raw, type) {
    const result = clone(effect), keys = path.split('.');
    let value = raw;
    if (raw !== '') {
      if (type === 'json' || type === 'json_scalar') { try { value = window.CatalogJson.parse(raw); } catch (_) { throw new Error('JSONの書き方を確認してください。'); } }
      if (type === 'bool') value = raw === 'true';
      if (type === 'int' || type === 'number') {
        value = Number(raw);
        if (!Number.isFinite(value) || (type === 'int' && !Number.isSafeInteger(value))) throw new Error('数値の形を確認してください。');
      }
    }
    let row = result;
    for (const key of keys.slice(0, -1)) { if (!object(row[key])) row[key] = {}; row = row[key]; }
    window.CatalogJson.forget(row,keys.at(-1));
    if (raw === '') delete row[keys.at(-1)]; else row[keys.at(-1)] = value;
    if (path.startsWith('condition.') && !Object.keys(result.condition).length) delete result.condition;
    return result;
  }
  function changeType(effect, type, schemas) {
    const result = clone(effect);
    if (effect.type === type) return result;
    const oldFields = {...schemas.effect_types[effect.type]?.fields,
      ...(effect.type === 'CUSTOM_EFFECT' ? schemas.custom_effects[effect.value]?.fields : {})};
    for (const path of Object.keys(oldFields)) {
      const keys = path.split('.');
      const remove = (row, depth) => {
        if (!object(row)) return;
        const key = keys[depth];
        if (depth === keys.length - 1) delete row[key];
        else { remove(row[key], depth + 1); if (object(row[key]) && !Object.keys(row[key]).length) delete row[key]; }
      };
      remove(result, 0);
    }
    result.type = type;
    return result;
  }
  function mutate(rule, action, index = 0) {
    const result = clone(rule || {});
    if (result.effects !== undefined && !Array.isArray(result.effects)) throw new Error('効果の配列をJSONの節で修正してください。');
    result.effects ??= [];
    const rows = result.effects;
    if (action === 'add') { result.schema ??= 'skill_json_rule_v2'; rows.push({ type: 'APPLY_STATE', timing: 'HIT', target: 'target' }); }
    if (action === 'remove') rows.splice(index, 1);
    const other = action === 'up' ? index - 1 : action === 'down' ? index + 1 : -1;
    if (other >= 0 && other < rows.length) [rows[index], rows[other]] = [rows[other], rows[index]];
    return result;
  }
  function summary(effect, schemas) {
    const schema = schemas.effect_types?.[effect?.type];
    if (!schema) return '?';
    const repr = (value,holder,key) => {
      if (value === null) return 'None';
      if (value === true || value === false) return value ? 'True' : 'False';
      if (Array.isArray(value)) return `[${value.map((child,index)=>repr(child,value,String(index))).join(', ')}]`;
      if (object(value)) return `{${Object.entries(value).map(([key, child])=>`${repr(key)}: ${repr(child,value,key)}`).join(', ')}}`;
      if (typeof value !== 'string') return typeof value === 'number' ? window.CatalogJson.numberText(holder,key) ?? String(value) : String(value);
      const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
      return quote + value.replace(/\\/g, '\\\\').replace(new RegExp(quote, 'g'), `\\${quote}`).replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t') + quote;
    };
    const python = value => typeof value === 'string' ? value : repr(value);
    return schema.summary.replace(/\{([^{}]+)\}/g, (_, key) => {
      const value = get(effect, key);
      const parts = key.split('.'), holder = parts.length === 1 ? effect : get(effect,parts.slice(0,-1).join('.'));
      const numeric = typeof value === 'number' ? window.CatalogJson.numberText(holder,parts.at(-1)) : null;
      return value == null ? '?' : key === 'target' ? schemas.target_labels?.[String(value)] ?? String(value) : numeric ?? python(value);
    });
  }
  function control(label, value, spec, attrs, references = {}) {
    const type = spec.type || 'string';
    let options = spec.options?.map(value => [String(value), spec.labels?.[value] || String(value)]);
    if (type === 'bool') options = [['true', 'はい'], ['false', 'いいえ']];
    const refKind = { state_ref: 'state', buff_ref: 'buff', skill_ref: 'skill', glossary_ref: 'glossary', summon_ref: 'summon' }[type];
    if (refKind && references[refKind]) options = references[refKind].map(row => [row.id, type === 'state_ref' ? row.name : `${row.id} ${row.name}`]);
    let input;
    if (options) {
      if (value != null && !options.some(([key]) => key === String(value))) options.push([String(value), `${value}（現在の値）`]);
      input = `<select ${attrs}><option value="">未指定</option>${options.map(([key, name]) => `<option value="${h(key)}" ${String(value) === key ? 'selected' : ''}>${h(name)}</option>`).join('')}</select>`;
    } else if (type === 'json') input = '<button type="button" class="cat-button" data-section="json">JSONで編集</button>';
    else if (type === 'json_scalar') input = `<input ${attrs} type="text" value="${h(value === undefined ? '' : JSON.stringify(value))}">`;
    else input = `<input ${attrs} type="${['int', 'number'].includes(type) ? 'number' : 'text'}" ${type === 'int' ? 'step="1"' : type === 'number' ? 'step="any"' : ''} value="${h(value ?? '')}">`;
    return `<label class="cat-field ${type === 'json' ? 'cat-field-wide' : ''}">${h(label)}${spec.required ? ' *' : ''}${input}</label>`;
  }
  function conditionEditable(value) {
    return value === undefined || (object(value) && (value.value == null || typeof value.value !== 'object') && Object.keys(value).every(key => ['source', 'param', 'operator', 'value'].includes(key))
      && ['source', 'param', 'operator'].every(key => value[key] === undefined || typeof value[key] === 'string'));
  }
  const groups = ['状態異常','バフ','スタック','威力・ロール','ダメージ・回復','行動・進行','特殊'];
  const typeOrder = ['APPLY_STATE','APPLY_STATE_PER_N','APPLY_FISSURE_BUFFED','MULTIPLY_STATE','APPLY_BUFF','APPLY_BUFF_PER_N','APPLY_BUFF_FROM_CHARACTER_COUNT','REMOVE_BUFF','CONSUME_BUFF_COUNT_FOR_GAIN','CONSUME_BUFF_COUNT_FOR_POWER','CONVERT_STACK_RESOURCE_VARIANT','MODIFY_BASE_POWER','MODIFY_FINAL_POWER','MODIFY_ROLL','DAMAGE_BONUS','DRAIN_HP','USE_SKILL_AGAIN','FORCE_UNOPPOSED','SCHEDULE_EFFECT','GRANT_SKILL','SUMMON_CHARACTER','CUSTOM_EFFECT'];
  let showKeys = false;
  try { showKeys = window.localStorage?.getItem('catalog-effect-keys') === '1'; } catch (_) {}
  function setShowKeys(value) {
    showKeys = !!value;
    try { window.localStorage?.setItem('catalog-effect-keys',showKeys ? '1' : '0'); } catch (_) {}
  }
  function typeControl(value,schemas,attrs = 'data-effect-path="type"') {
    const rank = key => typeOrder.includes(key) ? typeOrder.indexOf(key) : typeOrder.length;
    const types = Object.entries(schemas.effect_types || {}).sort(([a],[b])=>rank(a)-rank(b));
    const names = [...groups,...new Set(types.map(([,spec])=>spec.group || 'その他').filter(group=>!groups.includes(group)))];
    return `<label class="cat-field">効果タイプ<select ${attrs}><option value="">未指定</option>${names.map(group=>{
      const rows = types.filter(([,spec])=>(spec.group || 'その他') === group);
      return rows.length ? `<optgroup label="${h(group)}">${rows.map(([key,spec])=>`<option value="${h(key)}" ${value === key ? 'selected' : ''}>${h(spec.label)}${showKeys ? `（${h(key)}）` : ''}</option>`).join('')}</optgroup>` : '';
    }).join('')}</select></label>`;
  }
  const keyToggle = () => `<label class="cat-key-toggle"><input type="checkbox" id="cat-effect-keys" ${showKeys ? 'checked' : ''}>効果タイプの英字のキーも出す</label>`;
  function form(effect, index, schemas, references) {
    const schema = schemas.effect_types?.[effect?.type];
    const custom = effect?.type === 'CUSTOM_EFFECT' ? schemas.custom_effects?.[effect.value] : null;
    const specs = { ...schema?.fields, ...custom?.fields };
    const keys = new Set(['type', 'timing', 'target', 'condition', ...Object.keys(specs).map(key => key.split('.')[0])]);
    const fallback = !object(effect) || !schema || !conditionEditable(effect.condition);
    const action = (label, action, disabled = false) => `<button type="button" class="cat-button" data-effect-action="${action}" data-index="${index}" ${disabled ? 'disabled' : ''}>${label}</button>`;
    const heading = `<div class="cat-effect-heading"><strong><span class="cat-effect-when">${h(timingLabels[effect?.timing] || 'タイミング未指定')}</span>｜${h(summary(effect,schemas))}${effect?.condition ? `<small>${h(conditionText(effect.condition))}</small>` : ''}</strong><div>${action('↑', 'up', index === 0)}${action('↓', 'down')}${action('削除', 'remove')}</div></div>`;
    if (fallback) return `<section class="bo-workspace__card cat-effect-card" data-effect-index="${index}">${heading}<p class="cat-callout">JSON で編集 · この札にはフォームで扱えない項目があります。</p>${action('JSON で編集', 'json')}</section>`;
    const extra = Object.keys(effect).some(key => !keys.has(key)) ? '<p class="cat-callout">追加の項目は JSON で編集できます。値は保持されます。</p>' : '';
    const attrs = (path, type = 'string') => `data-effect-index="${index}" data-effect-path="${h(path)}" data-value-type="${type}"`;
    let inputs = typeControl(effect.type,schemas,attrs('type'));
    for (const key of ['timing', 'target']) inputs += control(schemas.common_fields[key].label, effect[key], {...schemas.common_fields[key],labels:key === 'target' ? schemas.target_labels : timingLabels}, attrs(key));
    for (const [path, spec] of Object.entries(specs)) {
      if (spec.visible_when && !Object.entries(spec.visible_when).every(([key,value]) => get(effect,key) === value)) continue;
      const definition = path === 'value' && effect.type === 'CUSTOM_EFFECT' ? { ...spec, options: Object.keys(schemas.custom_effects), labels:Object.fromEntries(Object.entries(schemas.custom_effects).map(([key,value])=>[key,value.label])) } : spec;
      const value = get(effect,path);
      const nameRefs = ['buff_name','resource_name'].includes(path) ? {...references,state:[...(references.buff || []).map(row=>({id:row.name,name:row.name})),...(references.state || [])]} : references;
      inputs += control(spec.label, value, ['buff_name','resource_name'].includes(path) ? {...definition,type:'state_ref'} : definition, attrs(path, spec.type), nameRefs);
    }
    inputs += `<label class="cat-field cat-field-wide">条件<select data-condition-mode="${index}"><option value="none" ${effect.condition === undefined ? 'selected' : ''}>無し</option><option value="simple" ${effect.condition !== undefined ? 'selected' : ''}>4つの欄で指定</option></select></label>`;
    if (effect.condition !== undefined) for (const key of ['source','param','operator','value']) { const spec = conditionSpec(key,schemas); inputs += control(spec.label, effect.condition[key], spec, attrs(`condition.${key}`, spec.type),references); }
    return `<section class="bo-workspace__card cat-effect-card" data-effect-index="${index}">${heading}${extra}<div class="cat-field-grid">${inputs}</div><span class="cat-field-error" data-effect-error="${index}"></span></section>`;
  }
  function conditionSpec(key,schemas) {
    const spec = schemas.common_fields.condition.fields[key];
    if (key === 'source') return {...spec,options:Object.keys(sources),labels:sources};
    if (key === 'operator') return {...spec,options:Object.keys(operators),labels:Object.fromEntries(Object.entries(operators).map(([key,label])=>[key,label]))};
    return key === 'value' ? {...spec,type:'json_scalar'} : spec;
  }
  function conditionText(condition) {
    if (!condition) return '';
    if (!conditionEditable(condition)) return '複合条件あり（JSONで確認）';
    const param = String(condition.param || '').replace(/_count$/, 'のスタック数').replace(/^buff_count:/,'バフのスタック数：');
    return `${sources[condition.source] || '参照元'}の${param}が${typeof condition.value === 'object' ? JSON.stringify(condition.value) : condition.value ?? '?'}${operators[condition.operator] || 'と比較'}のとき`;
  }
  window.CatalogSkillEffects = { typeControl, keyToggle, setShowKeys, timingLabels, conditionText, conditionSpec, clone, object, get, setField, changeType, mutate, summary, control, conditionEditable, form };
})();
