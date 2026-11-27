(function () {
  const colors = {
    出血:'#e06a6a',破裂:'#ef9a4a',亀裂:'#8fd0ff',戦慄:'#b48cf0',荊棘:'#7fcf7f',蓄力:'#f0d27a',
    凝魔:'#6fb8e8',斬撃:'#e8e8e8',打撃:'#c9a27a',貫通:'#a0e0d0',汎用:'#9aa3b8',出身強化:'#f0a0c8',
  };
  const categories = Object.keys(colors).filter(name=>name !== '出身強化');
  const ranks = ['','Ⅰ','Ⅱ','Ⅲ','Ⅳ','Ⅴ'];
  const esc = value => window.CatalogWorkspaceParts.h(value ?? '');
  const color = name => Object.hasOwn(colors,name) ? colors[name] : '#9aa3b8';
  const plain = value => String(value || '').replace(/\[\[[^|\]\n]+\|([^\]\n]+)\]\]/g,'$1');
  const category = (name, attrs = '') => `<${attrs ? 'button type="button"' : 'span'} class="hollow-category hr-category"
    ${attrs}><i style="--dot:${color(name)}"></i>${esc(name)}</${attrs ? 'button' : 'span'}>`;
  const button = (label, action, attrs = '', primary = false) =>
    `<button type="button" class="hollow-route-btn${primary ? ' primary' : ''}" data-relic-action="${action}" ${attrs}>${label}</button>`;
  const gemPath = '<path d="M6 2h12l5 6-11 14L1 8zm2 2L5 7h4zm2 0 2 3 2-3zm6 0-1 3h4zM5 9l5 8-2-8zm5 0 2 9 2-9zm6 0-2 8 5-8z"/>';
  const gem = `<svg viewBox="0 0 24 24" aria-hidden="true">${gemPath}</svg>`;
  let room, phase, fusionCount, value, refresh, dialog, detail, dialogMarkup, chosen, slots, wish, wishOn, forecast, history, busy;
  let request = 0;

  function icon(item, size = '', action = '', attrs = '') {
    if (!item) return '';
    const type = action ? 'button' : 'span';
    const image = /^(https?:\/\/|\/(?!\/))/i.test(item.image || '') ? item.image : '';
    return `<${type} ${action ? `type="button" data-relic-action="${action}" aria-label="${esc(item.name)}" ${attrs}` : 'aria-hidden="true"'}
      class="hr-icon ${size}${image ? ' has-image' : ''}" style="--gem:${color(item.category)}" title="${esc(item.name)}">
      ${image ? `<img src="${esc(image)}" alt="" loading="lazy">` : ''}
      ${item.cost_text ? '<i class="hr-cost-mark"></i>' : ''}<b>${ranks[item.rank] || ''}</b></${type}>`;
  }

  function metadata(item) {
    return `<div class="hr-meta">${category(item.category)}<span>ランク ${ranks[item.rank]}</span></div>`;
  }

  function description(item, full) {
    return `${full ? `<p class="hr-sub">対象 ${esc(item.target_text)}</p>` : ''}
      <p class="hr-effect">${esc(plain(item.effect_text))}</p>
      ${item.cost_text ? `<p class="hr-cost">代償 ${esc(plain(item.cost_text))}</p>` : ''}
      ${full && item.flavor ? `<p class="hr-flavor">${esc(plain(item.flavor))}</p>` : ''}`;
  }

  function loadView(run, full) {
    const load = run.mana_load || 0;
    const {level = 0, stages = [], next_threshold:next} = run.load_stage || {};
    const at = stages.find(row=>row.threshold === next);
    const max = Math.max(1,load, (stages.at(-1)?.threshold || 0) + 4);
    return `<div class="hr-load ${full ? 'is-full' : ''}"><div class="hr-load-top">魔力負荷 <b>${load}</b>
      <span>段階 ${level}${at ? ` · 次は ${next}（あと ${next-load}）${full ? '' : ' ' + esc(at.name)}` : ''}</span></div>
      ${full ? `<div class="hr-load-bar" aria-hidden="true"><i style="width:${load/max*100}%"></i>
        ${stages.map(row=>`<s style="left:${row.threshold/max*100}%"></s>`).join('')}</div>
        <div class="hr-load-stages">${stages.map(row=>`<span class="${row.threshold <= load ? 'is-reached' : ''}">
          ${row.threshold} ${esc(row.name)}</span>`).join('')}</div>` : ''}</div>`;
  }

  function materials(run, edit) {
    const rows = Object.entries(run.materials || {}).map(([rank,count])=>{
      const left = count - (edit ? slots.filter(row=>row.rank === Number(rank)).length : 0);
      const label = `素材${ranks[rank]} ×${left}`;
      return edit ? button(label,'material',`data-key="${rank}" ${!left || slots.length === 4 ? 'disabled' : ''}`)
        : `<span class="hr-material">${label}</span>`;
    });
    return `<div class="hr-materials">${rows.join('') || '<span class="hr-sub">なし</span>'}</div>`;
  }

  function rewardCard(item, run, attrs = '') {
    const tag = attrs ? 'button' : 'article';
    return `<${tag} class="hr-reward-card" ${attrs}>
      ${icon(item,'is-big')}<h3>${esc(item.name)}</h3>${metadata(item)}${description(item,false)}
      ${run.relics.includes(item.id) ? `<span class="hr-owned">所持済み：素材${ranks[item.rank]}になる</span>` : ''}
      <strong class="hr-load-up">魔力負荷 ＋${item.rank}</strong></${tag}>`;
  }

  function rewardView(run, manage, type) {
    const cards = (run.reward.cards || []).map(item => rewardCard(item, run, manage
      ? `type="button" data-relic-action="select" data-key="${esc(item.id)}" aria-pressed="${chosen === item.id}" ${busy ? 'disabled' : ''}`
      : '')).join('');
    return `<section class="hr-screen"><header class="hr-head"><small>${run.floor}F ${esc(type)} · 制圧</small><h2>戦闘の報酬</h2>
      ${loadView(run,false)}</header><div class="hr-reward-cards">${cards}</div><div class="hr-actions">
      ${manage ? button('見送る','skip',busy ? 'disabled' : '') + button('受け取る','take',busy || !chosen ? 'disabled' : '',true)
        : '<p class="hr-sub">ホストが選んでいます</p>'}</div></section>`;
  }

  function forecastView() {
    if (slots.length < 2) return '<p class="hr-sub">材料を2〜4個選んでください</p>';
    if (!forecast) return '<p class="hr-sub">見込みを確認中…</p>';
    if (forecast.error) return `<p class="hr-cost">${esc(forecast.error)}</p>`;
    if (forecast.special) return '<p class="hr-omen">特別な遺物ができる気配がある</p>';
    const values = slots.map(row=>row.item?.rank || row.rank);
    const sum = values.reduce((a,b)=>a+b,0);
    const weights = wishOn && wish ? {[wish]:1} : forecast.weights || {};
    const total = Object.values(weights).reduce((a,b)=>a+b,0);
    return `<div class="hr-forecast">ランク <b>${ranks[Math.min(5,Math.ceil(sum/2))]}</b>
      <small>（${values.join('＋')}＝${sum} ÷2 切り上げ）</small>
      <div class="hr-odds">${Object.entries(weights).map(([name,n])=>`<span>${category(name)} ${Number((n/total*100).toFixed(1))}%</span>`).join('')
      || '<span class="hr-sub">この材料で作れるカテゴリはありません</span>'}</div></div>`;
  }

  function forge(run) {
    const used = new Set(slots.map(row=>row.relic_id));
    const selected = slots.length === 4;
    const pool = (run.relic_cards || []).map(item=>icon(item,'','add',`data-key="${esc(item.id)}" ${selected || used.has(item.id) ? 'disabled' : ''}`)).join('');
    const cells = Array.from({length:4},(_,index)=>{
      const row = slots[index];
      if (!row) return `<span class="hr-slot">${index < 2 ? '材料' : '空き'}</span>`;
      return row.item ? icon(row.item,'','remove',`data-key="${index}"`)
        : button('素材'+ranks[row.rank],'remove',`data-key="${index}"`);
    }).join('');
    const disabled = busy || slots.length < 2 || !forecast || forecast.error ||
      (!forecast.special && (wishOn ? !wish : !Object.keys(forecast.weights || {}).length));
    return `<div class="hr-forge"><section><h3>所持の淵遺物</h3><div class="hr-grid">${pool}</div>
      <h3>汎用素材</h3>${materials(run,true)}</section><fieldset class="hr-forge-controls" ${busy ? 'disabled' : ''}>
      <h3>材料</h3><div class="hr-slots">${cells}</div>${forecastView()}
      ${forecast?.special ? '' : `<div class="hr-wish"><label><input data-relic-wish type="checkbox" ${wishOn ? 'checked' : ''}
        ${run.fusion.wishes_left ? '' : 'disabled'}> 祈念 <small>残り ${run.fusion.wishes_left} 回</small></label>
        ${wishOn ? `<div class="hr-odds">${categories.map(name=>category(name,`data-relic-action="wish" data-key="${name}" aria-pressed="${wish === name}"`)).join('')}</div>` : ''}</div>`}
      <div class="hr-actions">${button('クリア','clear',slots.length ? '' : 'disabled')}${button('変転する','fuse',disabled ? 'disabled' : '',true)}</div>
      </fieldset></div>`;
  }

  function fusionView(run, manage) {
    const result = manage && slots.length ? null : run.fusion.result;
    return `<section class="hr-screen"><header class="hr-head"><small>${run.floor}F · ボスの前</small><h2>虚夢変転</h2>
      ${loadView(run,false)}</header>${manage ? forge(run) : `<p class="hr-host-wait hr-sub">ホストが選んでいます</p>
        <section class="hr-fusion-view"><h3>所持の淵遺物</h3><div class="hr-grid">${(run.relic_cards || []).map(item=>icon(item)).join('')}</div>
        <h3>汎用素材</h3>${materials(run,false)}</section>`}
      ${result ? `<section class="hr-result" aria-live="polite">${icon(result.card,'is-big')}<h3>${esc(result.card.name)}</h3>
        ${metadata(result.card)}${description(result.card,false)}
        ${result.material ? `<p class="hr-owned">所持済み：素材${ranks[result.rank]}になった</p>` : ''}
        ${result.special ? '<p class="hr-omen">特別な組み合わせを見つけた</p>' : ''}</section>` : ''}
      <aside class="hr-discoveries"><h3>見つけた組み合わせ</h3>
        ${history?.error ? '<p class="hr-sub">一覧を取得できません</p>' : history?.length ?
          `<ul>${history.map(row=>`<li>${row.material_names.map(esc).join(' ＋ ')} → ${esc(row.result_name)}</li>`).join('')}</ul>`
          : `<p class="hr-sub">${history ? 'まだ見つけていません' : '読み込み中…'}</p>`}</aside>
      ${manage ? `<div class="hr-actions">${button('変転を終えてボスへ','end',busy ? 'disabled' : '',true)}</div>` : ''}</section>`;
  }

  function renderDialog() {
    if (!dialog?.open || !value) return;
    const run = value.hollow.run;
    const cards = run.relic_cards || [];
    const selected = cards.find(item=>item.id === detail) || cards[0];
    detail = selected?.id;
    const body = `${loadView(run,true)}<div class="hr-inventory"><div class="hr-inventory-pool">
      <h3>所持の淵遺物 <small>${cards.length}個</small></h3><div class="hr-grid">
      ${cards.map(item=>icon(item,'','detail',`data-key="${esc(item.id)}" aria-pressed="${item.id === detail}"`)).join('')
      || '<p class="hr-sub">まだ淵遺物はありません</p>'}</div>
      <h3>汎用素材</h3>${materials(run,false)}<h3>一時バフ</h3>
      ${run.temp_buffs?.length ? `<ul>${run.temp_buffs.map(row=>`<li>${esc(row.name || row.buff_id)} · あと ${row.battles_left} 戦</li>`).join('')}</ul>`
      : '<p class="hr-sub">なし</p>'}</div><section class="hr-detail" aria-label="淵遺物の詳細">
      ${selected ? `${icon(selected,'is-big')}<h3>${esc(selected.name)}</h3>${metadata(selected)}${description(selected,true)}` : ''}</section></div>`;
    if (body === dialogMarkup) return;
    const scroll = dialog.querySelector('.hr-inventory-pool')?.scrollTop || 0;
    const focused = dialog.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    dialog.querySelector('.hr-dialog-body').innerHTML = body;
    dialog.querySelector('.hr-inventory-pool').scrollTop = scroll;
    if (focused) [...dialog.querySelectorAll('[data-key]')].find(el=>el.dataset.key===focused)?.focus({preventScroll:true});
    dialogMarkup = body;
  }

  function open() {
    if (!value) return;
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.className = 'hollow-window hr-dialog';
      dialog.dataset.theme = 'abyss';
      dialog.setAttribute('aria-labelledby','hr-dialog-title');
      dialog.innerHTML = '<header><h2 id="hr-dialog-title">淵遺物</h2><form method="dialog"><button class="hollow-route-btn">閉じる</button></form></header><div class="hr-dialog-body"></div>';
      dialog.onclick = event=>{
        const control = event.target.closest('[data-relic-action="detail"]');
        if (control) { detail = control.dataset.key; renderDialog(); }
      };
      document.body.append(dialog);
    }
    if (!dialog.open) dialog.showModal();
    renderDialog();
  }

  function mountDock(dock, state) {
    if (!dock) return;
    let item = dock.querySelector('#dock-hollow-relic');
    if (state?.play_mode !== 'hollow') { item?.remove(); return; }
    if (!item) {
      item = document.createElement('button');
      item.type = 'button';
      item.id = 'dock-hollow-relic';
      item.className = 'dock-icon hr-dock';
      item.setAttribute('aria-label','淵遺物');
      item.title = '淵遺物';
      item.innerHTML = gem + '<span class="hr-dock-count" aria-hidden="true"></span>';
      item.onclick = open;
      (dock.querySelector('#dock-hollow-party') || dock.firstElementChild)?.after(item);
      if (!item.isConnected) dock.append(item);
    }
    item.querySelector('.hr-dock-count').textContent = state.hollow.run.relics?.length || 0;
  }

  function loadHistory() {
    const key = phase;
    fetchWithSession('/api/hollow/recipes/discovered')
      .then(response=>{ if (!response.ok) throw new Error(); return response.json(); })
      .then(data=>{ if (phase === key) { history = data.recipes; refresh(); } })
      .catch(()=>{ if (phase === key) { history = {error:true}; refresh(); } });
  }

  function sync(state, name, paint) {
    value = state;
    refresh = paint;
    const run = state.hollow.run;
    const key = `${name}:${run.fusion ? 'fusion:'+run.fusion.floor : run.reward ? 'reward:'+run.reward.floor : ''}`;
    if (phase !== key) {
      phase = key;
      slots = [];
      chosen = wish = forecast = history = null;
      wishOn = busy = false;
      request++;
      if (run.fusion) loadHistory();
    } else if (run.fusion && fusionCount !== run.fusion.count) {
      slots = [];
      wishOn = false;
      forecast = wish = null;
      request++;
    }
    fusionCount = run.fusion?.count;
    room = name;
    renderDialog();
  }

  function close() {
    dialog?.remove();
    dialog = detail = room = phase = value = dialogMarkup = null;
    request++;
  }

  const payload = () => slots.map(row=>row.relic_id ? {relic_id:row.relic_id} : {rank:row.rank});
  function preview() {
    const token = ++request;
    forecast = null;
    refresh();
    if (slots.length < 2) return;
    window.socket.timeout(7000).emit('hollow_preview_fusion',{floor:value.hollow.run.floor,materials:payload()},(error,result)=>{
      if (request !== token) return;
      forecast = error || !result?.ok ? {error:result?.error || '見込みを取得できません'} : result;
      refresh();
    });
  }

  function send(event, args) {
    busy = true;
    const key = phase, sentRoom = room;
    refresh();
    window.socket.timeout(7000).emit(event,{floor:value.hollow.run.floor,...args},(error,result)=>{
      if (room !== sentRoom) return;
      if (error || !result?.ok) window.showAppNotice(result?.error || '通信に失敗しました',{kind:'error'});
      if (phase !== key) return;
      busy = false;
      if (!error && result?.ok && event === 'hollow_fuse_relics') {
        slots = [];
        wishOn = false;
        wish = forecast = null;
        loadHistory();
      }
      refresh();
    });
  }

  function click(control) {
    if (!value || busy || !window.HollowParty.canProgress(value)) return;
    const {relicAction:action,key} = control.dataset;
    const run = value.hollow.run;
    if (action === 'select') { chosen = key; refresh(); return; }
    if (action === 'take' || action === 'skip') return send('hollow_choose_reward',{relic_id:action === 'take' ? chosen : null});
    if (!run.fusion) return;
    if (action === 'wish') { wish = key; refresh(); return; }
    if (action === 'fuse') return send('hollow_fuse_relics',{materials:payload(),wish:wishOn && !forecast?.special ? wish : null});
    if (action === 'end') return send('hollow_end_fusion',{});
    if (action === 'clear') slots = [];
    if (action === 'remove') slots.splice(Number(key),1);
    if (slots.length < 4) {
      if (action === 'material') slots.push({rank:Number(key)});
      if (action === 'add') {
        const item = run.relic_cards.find(row=>row.id === key);
        if (item) slots.push({relic_id:key,item});
      }
    }
    preview();
  }

  function change(input) {
    if (!input.matches('[data-relic-wish]') || !window.HollowParty.canProgress(value)) return;
    wishOn = input.checked;
    wish = null;
    refresh();
  }

  window.HollowRelics = {color,rewardCard,rewardView,fusionView,sync,close,mountDock,click,change};
})();
