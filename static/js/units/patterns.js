(function () {
  const h = window.CatalogGlossary.escape;
  const {clone} = window.CatalogJson;
  const special = {'__NO_ACTION__':'行動しない','__RANDOM_USABLE__':'使用可能スキルからランダム'};
  const randomAliases = ['__random_usable__','random_usable','__random_skill__','random_skill','__random__','random'];
  const specialName = id => (Object.hasOwn(special,id) ? special[id] : '') || (randomAliases.includes(String(id).toLowerCase()) ? special.__RANDOM_USABLE__ : '');
  const isMissing = (id, unit) => id && !specialName(id) && !(unit.skills || []).some(skill => skill.id === id);
  const canCreate = unit => unit.allow_enemy !== false;

  function create(unit, source) {
    const ids = new Set((unit.patterns || []).map(pattern => pattern.id));
    let number = 1;
    while (ids.has('BP-' + number)) number++;
    return {id:'BP-' + number, name:source ? source.name + '（複製）' : 'パターン ' + number,
      note:source?.note || '', profile:clone(source?.profile || {enabled:true,slot_generation_mode:'step_actions'})};
  }

  function missingActions(profile, unit) {
    return Object.entries(profile.loops || {}).flatMap(([loop, value]) => (value.steps || []).flatMap((step, round) =>
      (step.actions || []).flatMap((id, action) => isMissing(id,unit) ? [{loop,round,action,id}] : [])));
  }

  function remap(profile, missing, choices) {
    const copy = clone(profile);
    const removed = new Map();
    missing.forEach(({loop,round,action},index) => {
      if (choices[index]) copy.loops[loop].steps[round].actions[action] = choices[index];
      else {
        if (!removed.has(loop)) removed.set(loop,new Set());
        removed.get(loop).add(round);
      }
    });
    for (const [loop, rounds] of removed) {
      copy.loops[loop].steps = copy.loops[loop].steps.filter((_,i) => !rounds.has(i));
    }
    return copy;
  }

  function skillName(id, unit, skills) {
    const master = skills.find(row => row.entry_id === id);
    return specialName(id) || unit.skills?.find(skill => skill.id === id)?.name ||
      window.UnitForms.nameOf(master?.payload) || id || '自動選択';
  }

  function targetName(target) {
    const selections = {random:'ランダム',nearest:'最寄り',farthest:'最遠',fastest:'最速',slowest:'最遅'};
    if (typeof target === 'string') {
      if (target === 'target_self') return '自分';
      const match = target.match(/^target_(enemy|ally)_(.+)$/);
      if (match) return (match[1] === 'ally' ? '味方' : '敵') + '・' + (selections[match[2]] || match[2]);
      return target;
    }
    const teams = {opposing_team:'敵',same_team:'味方',any:'全員',self:'自分'};
    return (target?.candidates || (Array.isArray(target) ? target : [target])).filter(Boolean).map(candidate => {
      if (candidate.team === 'self') return '自分';
      return [teams[candidate.team] || candidate.team, selections[candidate.selection] || candidate.selection,
        ...(candidate.required_tag_ids || [])].filter(Boolean).join('・');
    }).join(' → ') || '敵・ランダム';
  }

  function users(records, unitId, id, defaultId) {
    return records.filter(row => row.kind === 'formation' && row.payload.type === 'enemy' &&
      row.payload.members?.some(member => member.unit_id === unitId && (member.pattern_id || defaultId) === id));
  }

  function render(row, records, skills, edit) {
    const unit = row.payload;
    if (!canCreate(unit)) return '<p class="cat-caption">キャラ区分で敵キャラクターを選ぶと作成できます。</p>';
    const {button,field} = window.UnitForms;
    return (unit.patterns || []).map((pattern,index) => {
      const isDefault = unit.default_pattern_id === pattern.id;
      const formations = row.entry_id ? users(records,row.entry_id,pattern.id,unit.default_pattern_id) : [];
      const reason = isDefault ? '別のパターンを既定に設定してください。' : formations.length ? '編成で使用中です。' : '';
      const attrs = `data-id="${h(pattern.id)}"`;
      const steps = Object.entries(pattern.profile.loops || {}).flatMap(([loop,value]) =>
        (value.steps || []).map((step,round) => {
          const actions = (step.actions || []).map((id,i) => {
            const name = h(skillName(id,unit,skills));
            const label = isMissing(id,unit) ? `<strong class="unit-pattern-missing">未所持 ${h(id)}</strong>` : name;
            return `${label}${id === '__NO_ACTION__' ? '' : ' → ' + h(targetName(step.targets?.[i]))}`;
          });
          return `<li><code>${h(loop)}</code> ${round + 1}手目 · ${actions.join(' / ') || '自動選択'}</li>`;
        }));
      return `<article class="unit-pattern-row">
        <div class="unit-pattern-heading"><strong>${h(pattern.name || '名称未入力')}</strong>${isDefault ? '<span class="cat-badge">既定</span>' : ''}
          ${pattern.profile.enabled ? '' : '<span class="cat-badge">無効</span>'}</div>
        ${edit ? field('名称',`patterns.${index}.name`,pattern.name) + field('説明',`patterns.${index}.note`,pattern.note || '') :
          `<p>${h(pattern.note || '')}</p>`}
        ${steps.length ? `<ul class="unit-pattern-steps">${steps.join('')}</ul>` : '<p class="cat-caption">ステップなし</p>'}
        <p class="cat-caption">使用編成 ${formations.map(item => h(item.entry_id + ' ' + item.payload.name)).join('、') || 'なし'}</p>
        ${edit ? `<div class="unit-row-actions">
          ${button('チャート編集','pattern-edit',attrs)} ${button('複製','pattern-copy',attrs)}
          ${button('既定に設定','pattern-default',attrs + (isDefault ? ' disabled' : ''))}
          ${button('他ユニットへ複製','pattern-copy-to',attrs + ' data-source="pattern-target"')}
          ${button('削除','pattern-delete',attrs + (reason ? ` disabled aria-describedby="unit-pattern-delete-${index}"` : ''),'cat-danger unit-remove')}
        </div>${reason ? `<p class="cat-caption unit-pattern-reason" id="unit-pattern-delete-${index}">${reason}</p>` : ''}` : ''}</article>`;
    }).join('') || '<p class="cat-caption">パターンなし</p>';
  }

  window.UnitPatterns = {canCreate,create,missingActions,remap,render,skillName,users};
})();
