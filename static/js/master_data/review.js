(function () {
  const h = window.CatalogGlossary.escape, plain = window.CatalogEditor.plainText;
  const json = value => window.CatalogJson.stringify(value);
  function charDiff(before,after) {
    const a = [...before], b = [...after], parts = [];
    const push = (type,text) => {
      if (!text) return;
      const last = parts.at(-1);
      if (last?.type === type) last.text += text; else parts.push({type,text});
    };
    let start = 0, tail = 0;
    while (start < a.length && start < b.length && a[start] === b[start]) start++;
    while (tail < a.length-start && tail < b.length-start && a[a.length-1-tail] === b[b.length-1-tail]) tail++;
    push('same',a.slice(0,start).join(''));
    const x = a.slice(start,a.length-tail), y = b.slice(start,b.length-tail);
    // 長いJSONや文章でも承認画面の描画でイベントループを占有しない。
    if (!x.length || !y.length || x.length*y.length > 250000) { push('del',x.join(''));push('ins',y.join('')); }
    else {
      const dp = Array.from({length:x.length+1},()=>new Uint16Array(y.length+1));
      for (let i=x.length-1;i>=0;i--) for (let j=y.length-1;j>=0;j--) dp[i][j] = x[i] === y[j] ? dp[i+1][j+1]+1 : Math.max(dp[i+1][j],dp[i][j+1]);
      let i=0,j=0;
      while (i<x.length && j<y.length) {
        if (x[i] === y[j]) { push('same',x[i++]);j++; }
        else if (dp[i+1][j] >= dp[i][j+1]) push('del',x[i++]); else push('ins',y[j++]);
      }
      push('del',x.slice(i).join(''));push('ins',y.slice(j).join(''));
    }
    push('same',a.slice(a.length-tail).join(''));
    return parts;
  }
  const side = (parts,keep) => parts.filter(part=>part.type === 'same' || part.type === keep).map(part=>part.type === 'same' ? h(part.text) : `<${keep}>${h(part.text)}</${keep}>`).join('');
  function format(value,key,kind,payload,options) {
    if (value == null || value === '') return '—';
    if (['default_duration','duration','round_limit','summon_duration'].includes(key)) {
      if (value === -1 || key === 'summon_duration' && payload?.summon_duration_mode === 'permanent') return key === 'round_limit' ? '制限なし' : '解除まで';
      return `${value}ラウンド`;
    }
    if (key === 'summon_duration_mode') return value === 'permanent' ? '解除まで' : value === 'duration_rounds' ? 'ラウンド数' : plain(value);
    if (key === 'target_scope') return {opposing_team:'敵陣営',same_team:'同陣営',any:'全陣営',self:'自分'}[value] || plain(value);
    if (typeof value === 'boolean') return value ? 'はい' : 'いいえ';
    if (Array.isArray(value)) {
      if (key === 'cost' && value.every(row=>row && typeof row === 'object')) return value.map(row=>`${row.type ?? '?'}を${row.value ?? '?'}消費`).join('、') || 'なし';
      const refKind = key === 'links' ? 'glossary' : key === 'initial_skill_ids' ? 'skill' : null;
      if (value.every(item=>typeof item !== 'object')) return value.map(item=>{
        const ref = refKind && options.catalogs?.[refKind]?.entries.find(row=>row.entry_id === item);
        return ref ? `${item} ${ref.payload.display_name || ref.payload.デフォルト名称 || ''}` : plain(String(item));
      }).join('、') || 'なし';
    }
    return typeof value === 'object' ? json(value) : plain(String(value));
  }
  function effectText(effect,schemas) {
    if (effect === undefined) return '—';
    const schema = schemas?.effect_types?.[effect?.type];
    if (!schema) return json(effect);
    const helpers = window.CatalogSkillEffects;
    const represented = new Set([...schema.summary.matchAll(/\{([^{}]+)\}/g)].map(match=>match[1].split('.')[0]));
    const fields = {...schema.fields,...(effect.type === 'CUSTOM_EFFECT' ? schemas.custom_effects?.[effect.value]?.fields : {})};
    const rest = Object.entries(effect).filter(([key])=>!['type','timing','target','condition'].includes(key) && !represented.has(key));
    const extra = rest.map(([key,value])=>`${fields[key]?.label || key}：${typeof value === 'object' ? json(value) : value}`).join('、');
    return `${helpers.timingLabels[effect.timing] || 'タイミング未指定'}｜${helpers.summary(effect,schemas)}${extra ? `（${extra}）` : ''}${effect.condition ? ` / ${helpers.conditionEditable(effect.condition) ? helpers.conditionText(effect.condition) : '条件：'+json(effect.condition)}` : ''}`;
  }
  function rows(model,before,after,options = {}) {
    const same = (a,b) => json(a) === json(b);
    const result = [];
    const add = (key,label,a,b,display) => result.push({key,label,rawBefore:a,rawAfter:b,changed:before === undefined || !same(a,b),before:display ? display(a) : format(a,key,model.kind,before,options),after:display ? display(b) : format(b,key,model.kind,after,options)});
    const keys = [...new Set([...model.fields.map(([key])=>key),...Object.keys(before || {}),...Object.keys(after || {})])];
    for (const key of keys) {
      const a = before?.[key], b = after?.[key];
      if (model.kind === 'skill' && key === '特記処理' && [a,b].every(value=>value === undefined || window.CatalogSkillEffects.object(value))) {
        const rootKeys = [...new Set([...Object.keys(a || {}),...Object.keys(b || {})])];
        if (!rootKeys.length) add(key,'特記処理',a,b);
        for (const rootKey of rootKeys) {
          if (rootKey === 'effects' && [a?.effects,b?.effects].every(value=>value === undefined || Array.isArray(value))) {
            const count = Math.max(a?.effects?.length || 0,b?.effects?.length || 0);
            if (!count) add('effects','効果',a?.effects,b?.effects);
            for (let index=0;index<count;index++) add(`effect:${index}`,`効果${index+1}`,a?.effects?.[index],b?.effects?.[index],value=>effectText(value,options.schemas));
          } else {
            const label = {cost:'コスト',power_bonus:'威力補正',tags:'タグ',effects:'効果',target_scope:'対象範囲',schema:'定義形式',id:'処理の識別子'}[rootKey] || rootKey;
            add(rootKey,label,a?.[rootKey],b?.[rootKey]);
          }
        }
      } else add(key,model.fields.find(row=>row[0] === key)?.[1] || key,a,b);
    }
    return result;
  }
  function render(model,base,draft,options = {}) {
    const changes = rows(model,base?.payload,draft.payload,options);
    const unchanged = changes.filter(row=>!row.changed).length;
    const shown = options.showSame ? changes : changes.filter(row=>row.changed);
    const cells = shown.map(row=>{
      const parts = charDiff(row.before,row.after);
      const rawOnly = row.changed && row.before === row.after;
      return ['before','after'].map(which=>`<section class="cat-review-cell ${row.changed ? 'is-changed' : ''}" data-review-field="${h(row.key)}"><h4>${h(row.label)} ${row.changed ? '<span class="cat-badge">変更</span>' : ''}</h4><p class="cat-description">${base ? side(parts,which === 'before' ? 'del' : 'ins') : which === 'before' ? '—' : `<ins>${h(row.after)}</ins>`}</p>${rawOnly ? `<details><summary>保存される値</summary><pre class="cat-description">${h(json(row[which === 'before' ? 'rawBefore' : 'rawAfter']) ?? '未指定')}</pre></details>` : ''}</section>`).join('');
    }).join('');
    return `<div class="cat-review-grid"><div class="cat-review-heading"><h3>${base ? '公開中の版' : '新規'}</h3>${base ? `<small>版 ${base.revision}</small>` : ''}</div><div class="cat-review-heading"><h3>下書き</h3><small>${h(draft.created_by_name || '削除済みユーザー')}</small></div>${cells}</div>${shown.length ? '' : '<p class="cat-empty">変更された項目はありません。</p>'}${unchanged ? `<button type="button" class="cat-button cat-review-same" data-action="review-same">${options.showSame ? '変わっていない項目を隠す' : `変わっていない項目も見る（${unchanged}）`}</button>` : ''}`;
  }
  window.CatalogReview = {charDiff,side,rows,render};
})();
