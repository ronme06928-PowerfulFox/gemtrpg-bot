(function () {
  const h = window.CatalogGlossary.escape;
  const clone = value => JSON.parse(JSON.stringify(value));
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const get = (value, path) => path.split('.').reduce((row, key) => row?.[key], value);
  function setField(effect, path, raw, type) {
    const result = clone(effect), keys = path.split('.');
    let value = raw;
    if (raw !== '') {
      if (type === 'json') { try { value = JSON.parse(raw); } catch (_) { throw new Error('JSONの書き方を確認してください。'); } }
      if (type === 'bool') value = raw === 'true';
      if (type === 'int' || type === 'number') {
        value = Number(raw);
        if (!Number.isFinite(value) || (type === 'int' && !Number.isSafeInteger(value))) throw new Error('数値の形を確認してください。');
      }
    }
    let row = result;
    for (const key of keys.slice(0, -1)) { if (!object(row[key])) row[key] = {}; row = row[key]; }
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
    if (result.effects !== undefined && !Array.isArray(result.effects)) throw new Error('効果の配列をJSONタブで修正してください。');
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
    const repr = value => {
      if (value === null) return 'None';
      if (value === true || value === false) return value ? 'True' : 'False';
      if (Array.isArray(value)) return `[${value.map(repr).join(', ')}]`;
      if (object(value)) return `{${Object.entries(value).map(([key, child])=>`${repr(key)}: ${repr(child)}`).join(', ')}}`;
      if (typeof value !== 'string') return String(value);
      const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
      return quote + value.replace(/\\/g, '\\\\').replace(new RegExp(quote, 'g'), `\\${quote}`).replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t') + quote;
    };
    const python = value => typeof value === 'string' ? value : repr(value);
    return schema.summary.replace(/\{([^{}]+)\}/g, (_, key) => {
      const value = get(effect, key);
      return value == null ? '?' : key === 'target' ? schemas.target_labels?.[String(value)] ?? String(value) : python(value);
    });
  }
  function control(label, value, spec, attrs, references = {}) {
    const type = spec.type || 'string';
    let options = spec.options?.map(value => [String(value), spec.labels?.[value] || String(value)]);
    if (type === 'bool') options = [['true', 'はい'], ['false', 'いいえ']];
    const refKind = { buff_ref: 'buff', skill_ref: 'skill', glossary_ref: 'glossary', summon_ref: 'summon' }[type];
    if (refKind && references[refKind]) options = references[refKind].map(row => [row.id, `${row.id} ${row.name}`]);
    let input;
    if (options) {
      if (value != null && !options.some(([key]) => key === String(value))) options.push([String(value), `${value}（現在の値）`]);
      input = `<select ${attrs}><option value="">未指定</option>${options.map(([key, name]) => `<option value="${h(key)}" ${String(value) === key ? 'selected' : ''}>${h(name)}</option>`).join('')}</select>`;
    } else if (type === 'json') input = `<textarea ${attrs} rows="3" spellcheck="false">${h(value === undefined ? '' : JSON.stringify(value, null, 2))}</textarea>`;
    else input = `<input ${attrs} type="${['int', 'number'].includes(type) ? 'number' : 'text'}" ${type === 'int' ? 'step="1"' : type === 'number' ? 'step="any"' : ''} value="${h(value ?? '')}">`;
    return `<label class="cat-field ${type === 'json' ? 'cat-field-wide' : ''}">${h(label)}${spec.required ? ' *' : ''}${input}${spec.description ? `<small>${h(spec.description)}</small>` : ''}</label>`;
  }
  function conditionEditable(value) {
    return value === undefined || (object(value) && Object.keys(value).every(key => ['source', 'param', 'operator', 'value'].includes(key))
      && ['source', 'param', 'operator'].every(key => value[key] === undefined || typeof value[key] === 'string'));
  }
  function form(effect, index, schemas, references) {
    const schema = schemas.effect_types?.[effect?.type];
    const custom = effect?.type === 'CUSTOM_EFFECT' ? schemas.custom_effects?.[effect.value] : null;
    const specs = { ...schema?.fields, ...custom?.fields };
    const keys = new Set(['type', 'timing', 'target', 'condition', ...Object.keys(specs).map(key => key.split('.')[0])]);
    const fallback = !object(effect) || !schema || !conditionEditable(effect.condition);
    const action = (label, action, disabled = false) => `<button type="button" class="cat-button" data-effect-action="${action}" data-index="${index}" ${disabled ? 'disabled' : ''}>${label}</button>`;
    const heading = `<div class="cat-effect-heading"><strong>効果 ${index + 1} · ${h(schema?.label || effect?.type || '未定義')}</strong><div>${action('↑', 'up', index === 0)}${action('↓', 'down')}${action('削除', 'remove')}</div></div>`;
    if (fallback) return `<section class="bo-workspace__card cat-effect-card" data-effect-index="${index}">${heading}<p class="cat-callout">JSON で編集 · この札にはフォームで扱えない項目があります。</p>${action('JSON で編集', 'json')}<pre class="cat-effect-json">${h(JSON.stringify(effect, null, 2))}</pre></section>`;
    const extra = Object.keys(effect).some(key => !keys.has(key)) ? '<p class="cat-callout">追加の項目は JSON で編集できます。値は保持されます。</p>' : '';
    const attrs = (path, type = 'string') => `data-effect-index="${index}" data-effect-path="${h(path)}" data-value-type="${type}"`;
    let inputs = control('効果タイプ', effect.type, {options:Object.keys(schemas.effect_types), labels:Object.fromEntries(Object.entries(schemas.effect_types).map(([key,spec])=>[key,`${spec.label} / ${key}`]))}, attrs('type'));
    for (const key of ['timing', 'target']) inputs += control(schemas.common_fields[key].label, effect[key], {...schemas.common_fields[key],labels:key === 'target' ? schemas.target_labels : undefined}, attrs(key));
    for (const [path, spec] of Object.entries(specs)) {
      const definition = path === 'value' && effect.type === 'CUSTOM_EFFECT' ? { ...spec, options: Object.keys(schemas.custom_effects) } : spec;
      inputs += control(`${spec.label} · ${path}`, get(effect, path), definition, attrs(path, spec.type), references);
    }
    inputs += `<label class="cat-field cat-field-wide">条件<select data-condition-mode="${index}"><option value="none" ${effect.condition === undefined ? 'selected' : ''}>無し</option><option value="simple" ${effect.condition !== undefined ? 'selected' : ''}>4つの欄で指定</option></select></label>`;
    if (effect.condition !== undefined) for (const key of ['source','param','operator','value']) { const spec = schemas.common_fields.condition.fields[key]; inputs += control(spec.label, effect.condition[key], spec, attrs(`condition.${key}`, spec.type)); }
    return `<section class="bo-workspace__card cat-effect-card" data-effect-index="${index}">${heading}${extra}<div class="cat-field-grid">${inputs}</div><span class="cat-field-error" data-effect-error="${index}"></span></section>`;
  }
  window.CatalogSkillEffects = { clone, object, get, setField, changeType, mutate, summary, control, conditionEditable, form };
})();
