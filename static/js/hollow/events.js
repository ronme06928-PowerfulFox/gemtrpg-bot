(function () {
  const {h} = window.CatalogWorkspaceParts;
  const {rewardCard} = window.HollowRelics;
  const types = {miasma:'魔素だまり', chest:'宝箱', town:'町', camp:'先人のキャンプ'};
  const button = (label, action, {primary = false, disabled = false} = {}) =>
    `<button type="button" class="hollow-route-btn${primary ? ' primary' : ''}"
      data-event-action="${action}" ${disabled ? 'disabled' : ''}>${label}</button>`;
  const skillLevel = (char, skill) => {
    const params = char.params;
    const value = Array.isArray(params) ? params.find(row => row.label === skill)?.value : params?.[skill];
    if (typeof value === 'number') return Number.isFinite(value) ? Math.trunc(value) : 0;
    return typeof value === 'string' && /^[+-]?\d+$/.test(value.trim()) ? Number(value) : 0;
  };

  function chance(level, difficulty) {
    let wins = 0;
    for (let first = 1; first <= 6; first++) {
      for (let second = 1; second <= 6; second++) {
        if (first + second + level >= difficulty) wins++;
      }
    }
    return Math.round(wins * 100 / 36);
  }

  const memberName = (party, id) => party.find(char => char.id === id)?.name || '—';
  const image = char => /^(https?:\/\/|\/(?!\/))/i.test(char.image || '')
    ? `<img src="${h(char.image)}" alt="">` : '<span class="he-face" aria-hidden="true">◇</span>';

  function members(run, party, member, choice, chest) {
    const check = choice && Object.hasOwn(choice, 'difficulty');
    return `<section class="he-pick"><h3>${chest ? '受け取る人' : check ? '判定に挑む人' : '対象の人'}</h3>
      <div class="he-members">${party.map(char => {
        const level = check ? skillLevel(char, choice.skill) : 0;
        return `<button type="button" class="he-member" data-event-member="${h(char.id)}"
          aria-pressed="${member === char.id}" ${!chest && char.hp <= 0 ? 'disabled' : ''}>
          ${image(char)}<b>${h(char.name)} ${!run.active.includes(char.id) ? '<small>控え</small>' : ''}</b>
          <small>${char.hp <= 0 ? '戦闘不能' : `HP ${char.hp}/${char.maxHp}`}</small>
          ${check && char.hp > 0 ? `<strong>Lv${level} · ${chance(level, choice.difficulty)}%</strong>` : ''}</button>`;
      }).join('')}</div></section>`;
  }

  function gainView(gain, party, run) {
    if (!gain) return '';
    if (gain.kind === 'relic') {
      const remaining = {relics: gain.material ? run.relics : []};
      return rewardCard(gain.card, remaining);
    }
    const item = gain.kind === 'item';
    const targets = item ? (gain.char_id ? memberName(party, gain.char_id) : '')
      : `${(gain.char_ids || []).map(id => memberName(party, id)).join('・')} · あと ${gain.battles_left} 戦`;
    return `<article class="he-gain"><span aria-hidden="true">${item ? '🧪' : '✦'}</span><div>
      <strong>${h(gain.name)}</strong><small>${item ? 'アイテム' : '一時バフ'} ${h(targets)}</small>
      <p>${h(gain.description || '')}</p></div></article>`;
  }

  function miasma(run, event, party, manage, selected, member) {
    const current = event.choices[selected];
    const choices = event.choices.map((choice, index) => {
      const tag = manage ? 'button' : 'div';
      const attrs = manage ? `type="button" data-event-choice="${index}" aria-pressed="${selected === index}"` : '';
      return `<${tag} class="he-choice" ${attrs}><span>${index + 1}</span><b>${h(choice.label)}</b>
        <small>${Object.hasOwn(choice,'difficulty') ? `${h(choice.skill)} · 難易度 ${choice.difficulty}` : '判定なし'}</small></${tag}>`;
    }).join('');
    const ready = current && (!current.needs_member || party.some(char => char.id === member && char.hp > 0));
    return `<div class="he-choices">${choices}</div>
      ${manage && current?.needs_member ? members(run, party, member, current, false) : ''}
      ${actions(manage, button('決める','decide',{primary:true, disabled:!ready}))}`;
  }

  function actions(manage, controls) {
    return `<footer class="hr-actions">${manage ? controls + button('撤退','retreat') : '<p class="hr-sub">ホストが選んでいます</p>'}</footer>`;
  }

  function resultView(run, event, party) {
    const result = event.result;
    const dice = result.dice ? `<div class="he-dice" role="status">
      ${result.dice.map(value => `<b class="he-die">${value}</b>`).join('')}
      <span>＋ ${h(result.skill)} Lv${result.skill_level} ＝ <b>${result.total}</b></span><span>難易度 ${result.difficulty}</span>
      <strong class="${result.success ? 'he-ok' : 'he-fail'}">${result.success ? '成功' : '失敗'}</strong></div>` : '';
    const actor = result.char_id ? `<p class="he-actor">${h(memberName(party, result.char_id))}${dice ? ' が挑んだ' : ''}</p>` : '';
    const gain = gainView(result.gain, party, run);
    return dice + actor + `<div class="he-loot">${gain || '<p class="hr-sub">何も起こらなかった</p>'}</div>`;
  }

  function recovery(event, party) {
    return `<ul class="he-rest">${event.recovery.map(row => {
      const char = party.find(member => member.id === row.char_id);
      return `<li>${char ? image(char) : ''}<b>${h(memberName(party, row.char_id))}</b>
        <span>HP ${row.hp_before} → <b>${row.hp_after}</b></span><span>MP ${row.mp_before} → <b>${row.mp_after}</b></span>
        ${row.revived ? '<strong class="he-ok">復帰</strong>' : ''}</li>`;
    }).join('')}</ul>`;
  }

  function render(run, party, manage, selected, member) {
    const event = run.current_event;
    const {type, resolved} = event;
    const rest = type === 'town' || type === 'camp';
    const title = resolved && type === 'miasma' ? event.choices[event.result.choice_index].label : event.name;
    const next = run.fusion ? '虚夢変転へ' : run.map_candidates ? 'マップを選ぶ画面へ' : '地図へ戻る';
    let content;
    if (rest) content = recovery(event, party);
    else if (resolved) content = resultView(run, event, party);
    else if (type === 'miasma') content = miasma(run, event, party, manage, selected, member);
    else {
      const item = event.loot.kind === 'item';
      const loot = item ? gainView(event.loot, party, run) : rewardCard(event.loot, run);
      content = `<div class="he-loot">${loot}</div>` + (manage && item ? members(run, party, member, null, true) : '') +
        actions(manage, button('見送る','skip') + button('受け取る','take',{primary:true,disabled:item && !member}));
    }
    const text = rest || !resolved ? `<p class="he-text">${h(event.text)}</p>` : '';
    const note = rest ? `<p>${type === 'town' ? '全回復（戦闘不能も起き上がる）'
      : '最大 HP・MP の50%を回復（戦闘不能は50%で起き上がる）'}</p>` : '';
    return `<section class="hr-screen he-screen"><div class="he-panel">
      <header class="hr-head"><small>${run.floor}F ${types[type]}</small><h2>${h(title)}</h2>${note}</header>
      ${text}${content}${resolved ? `<footer class="hr-actions">${button(next,'close',{primary:true})}</footer>` : ''}
      </div></section>`;
  }

  window.HollowEvents = {types, render};
})();
