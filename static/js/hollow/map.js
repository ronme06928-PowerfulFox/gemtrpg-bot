(function () {
  const events = window.HollowEvents;
  const TYPES = {battle: '通常戦闘', elite: '精鋭戦闘', boss: 'ボス', ...events.types};
  // A later tier starts on the boss node just defeated, so it keeps that boss's look.
  const look = node => node.type === 'start' && node.floor ? 'boss' : node.type;
  const typeName = node => look(node) === 'start' ? '地上' : TYPES[look(node)];
  const TIERS = ['入穴', '浅層上部', '浅層中部', '浅層下部', '深層境界'];
  const ICONS = {
    battle: 'M20 3h-5l-9 9-2-2-1.5 1.5 3 3L3 17l1.5 1.5L7 16l3 3 1.5-1.5-2-2 9-9z',
    elite: 'M21 3h-4.5l-6 6 4.5 4.5 6-6zM3 3h4.5l11 11 2-2 1.5 1.5-3 3 2.5 2.5-1.5 1.5-2.5-2.5-3 3-1.5-1.5 2-2zM5.5 16.5l3-3 2 2-3 3 1 1L7 21l-4-4 1.5-1.5z',
    boss: 'M2 6l5 4 5-7 5 7 5-4-2 13H4zm10 6.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM4.5 20.5h15V22h-15z',
    chest: 'M4 4h16a1 1 0 0 1 1 1v4H3V5a1 1 0 0 1 1-1zM3 10h18v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zm7.5 1v4h3v-4z',
    miasma: 'M12 3a9 9 0 1 0 9 9h-2.2A6.8 6.8 0 1 1 12 5.2a4.6 4.6 0 1 1-4.6 4.6h2.2a2.4 2.4 0 1 0 2.4-2.4z',
    camp: 'M12 3 2 20h7.5L12 14.5 14.5 20H22zM11 1h2v3h-2z',
  };
  const OUTCOMES = {CLEAR: 'クリア', RETREAT: '撤退', DEFEAT: '全滅'};
  const relics = window.HollowRelics;
  const pins = window.HollowPins;
  const esc = value => window.CatalogWorkspaceParts.h(value ?? '');
  const chooseLabel = (node, next, run, manage) => node.id === run.map.current
    ? '今いるマス' : run.map.visited.includes(node.id) ? '通過'
    : next.has(node.id) ? (manage ? '押して入場' : pins.canPin(state) ? '押してピンを立てる' : '選べるマス')
    : node.floor <= run.floor ? '選ばなかったマス' : '先のマス';
  let mount, view, curtain, dialog, resize, state, room, snapshot, markup;
  let enterNode, picked, busy, timer, leavingTimer, pendingRound;
  let frame = 0, scrollKey;
  let eventKey, shownEvent, selectedChoice, selectedMember;
  const keyFor = run => Object.hasOwn(events.types, run.current_event?.type)
    ? `${run.floor}:${run.current_event.type}` : null;

  function tierName(map) { return map.name || TIERS[map.tier - 1] || ''; }

  function tierRange(tier) { return `T${tier} · ${tier * 10 - 9}〜${tier * 10}F`; }

  function panelFor(value) {
    const run = value.hollow.run;
    if (run.status === 'finished') return 'finished';
    if (value.combat_phase === 'active') return 'battle';
    if (run.reward) return 'reward';
    if (keyFor(run) && keyFor(run) === shownEvent) return 'event';
    if (run.fusion) return 'fusion';
    if (run.map_candidates) return 'map-pending';
    return run.status === 'in_progress' ? 'map' : 'forming';
  }

  function parties(run, state) {
    const byId = new Map((state.characters || []).map(char => [char.id, char]));
    const order = run.party_order || state.party?.order || [];
    const active = run.active || order.slice(0, 4);
    return {
      active: active.map(id => byId.get(id)).filter(Boolean),
      reserve: order.filter(id => !active.includes(id)).map(id => byId.get(id)).filter(Boolean),
      order: order.map(id => byId.get(id)).filter(Boolean),
    };
  }

  function pinHint(manage) {
    const text = pins.hint(state, manage);
    return text ? `<p class="hollow-pin-hint">${esc(text)}</p>` : '';
  }

  function card(title, content) {
    return `<div class="hollow-route-card"><small>ホロウダンジョン</small><h2>${title}</h2>${content}</div>`;
  }

  function renderCard(run, screen, manage) {
    const roster = parties(run, state);
    if (screen === 'finished') {
      const result = run.result || {floor: run.floor || 0};
      const growth = (result.growth || []).map(row => `<li>${esc(row.name)} 経験＋${esc(row.exp_gain)}・通過点＋${esc(row.radiance_gain)}
        （${row.tiers.map(tier => `T${esc(tier)}`).join('・')} 初踏破）</li>`).join('');
      return card(OUTCOMES[result.outcome] || '遠征終了', `
        <dl><dt>到達階</dt><dd>${esc(result.floor)}F</dd>
        ${growth ? `<dt>初踏破の成果</dt><dd><ul class="hollow-growth-results">${growth}</ul></dd>` : ''}
        <dt>パーティ</dt><dd>${esc(roster.order.map(char => char.name).join('・') || '—')}</dd></dl>
        <button class="hollow-route-btn primary" data-route-action="return">ダンジョンへ戻る</button>`);
    }
    return card('出発前', `<p>出撃 ${esc(roster.active.map(char => char.name).join('・') || '—')}<br>
      控え ${esc(roster.reserve.map(char => char.name).join('・') || '—')}</p>
      ${manage ? `<button class="hollow-route-btn primary" data-route-action="start"${roster.active.length ? '' : ' disabled'}>ランを始める</button>
        ${roster.active.length ? '' : '<p>パーティに味方を加えてください</p>'}`
        : '<p>ホストの出発を待っています</p>'}`);
  }

  function mapChoice(run, manage) {
    const {tier, maps} = run.map_candidates;
    const lead = tier === 1 ? '最初に降りるマップを選んでください'
      : `${run.floor}F ${run.current_event?.boss_name || '区切りの主'}を退けた。下へ続く道を選んでください`;
    const cards = maps.map(area => {
      const image = window.UnitForms.image(area.image);
      const categories = (area.categories || []).map(category =>
        `<span class="hollow-category"><i style="--dot:${relics.color(category)}"></i>${esc(category)}</span>`).join('');
      const pinnable = !manage && pins.canPin(state);
      return `<button type="button" class="hollow-choice-card" data-map-id="${esc(area.map_id)}"
        ${manage ? '' : pinnable ? pins.attrs(state, area.map_id) : ' disabled'}>${pins.marks(state, area.map_id)}
        <span class="hollow-choice-art">${image}</span>
        <span class="hollow-choice-copy"><strong>${esc(area.name)}</strong>
        <span class="hollow-choice-description">${esc(area.description)}</span>
        ${categories ? `<span class="hollow-choice-label">出やすい淵遺物</span><span class="hollow-choice-categories">${categories}</span>` : ''}</span>
        </button>`;
    }).join('');
    return `<section class="hollow-choice"><div class="hollow-choice-head"><small>${tierRange(tier)}</small>
      <h2>${tier === 1 ? '虚夢の辺縁へ降りる' : '次のマップを選ぶ'}</h2>
      <p>${esc(lead)}</p>
      ${manage ? '<button class="hollow-route-btn danger" data-route-action="retreat">撤退</button>'
        : pinHint(manage) ? '' : '<p>ホストがマップを選んでいます</p>'}${pinHint(manage)}</div>
      <div class="hollow-choice-cards">${cards}</div></section>`;
  }

  function nextIds(run) {
    const {map} = run;
    return new Set(map.rows.flat().find(item => item.id === map.current)?.next || []);
  }

  function nodeButton(node, run, next, manage) {
    const now = node.id === run.map.current;
    const done = !now && run.map.visited.includes(node.id);
    const offered = next.has(node.id);
    const cls = ['hollow-node', `type-${look(node)}`, now && 'is-now', done && 'is-done',
      offered && 'is-next', !now && !done && node.floor <= run.floor && 'is-skipped'].filter(Boolean).join(' ');
    const label = `${node.floor}F ${typeName(node)}、${chooseLabel(node, next, run, manage)}`;
    const shift = Math.max(-20, Math.min(20, Number(node.shift) || 0));
    const pinnable = offered && !manage && pins.canPin(state);
    return `<button type="button" class="${cls}" data-node="${esc(node.id)}" aria-label="${label}"
      ${offered && (manage || pinnable) ? '' : 'aria-disabled="true" tabindex="-1"'} ${pinnable ? pins.attrs(state, node.id) : ''}
      ${now ? 'aria-current="location"' : ''} style="--shift:${shift}px">
      ${ICONS[look(node)] ? `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[look(node)]}"/></svg>` : ''}
      <span>${typeName(node)}</span>${offered ? pins.marks(state, node.id) : ''}</button>`;
  }

  function chip(char, enabled) {
    const down = !(char.hp > 0);
    const img = char.image
      ? `<img src="${esc(char.image)}" alt="">` : `<span class="hollow-map-face">${esc(Array.from(char.name || '？')[0])}</span>`;
    const text = `${img}<b>${esc(char.name)}</b><small>${down ? '戦闘不能' : `HP ${esc(char.hp)}/${esc(char.maxHp)}`}</small>`;
    const cls = `hollow-map-chip${down ? ' is-down' : ''}`;
    return enabled ? `<button type="button" class="${cls}" data-chip="${esc(char.id)}"
      aria-pressed="${picked === char.id}">${text}</button>` : `<span class="${cls}">${text}</span>`;
  }

  function renderMap(run, manage) {
    const {map} = run;
    const last = map.last_floor;
    const first = last - 9;
    const floor = `${run.floor}F`;
    const next = nextIds(run);
    const player = parties(run, state);
    const canSwap = manage && player.active.length && player.reserve.some(char => char.hp > 0);
    const chosen = player.order.find(char => char.id === picked);
    const rows = Array.from({length: last - first + 2}, (_, index) => {
      const row = map.rows[index];
      return `<div class="hollow-map-row${row ? '' : ' is-fog'}"><span class="hollow-map-floor">${first - 1 + index}F</span>
        ${row ? row.map(node => nodeButton(node, run, next, manage)).join('') : '<span class="hollow-map-fog">未踏</span>'}</div>`;
    }).join('');
    return `<header class="hollow-map-head"><div><small>T${map.tier} · ${first}〜${last}F</small><h2>${esc(tierName(map))}</h2></div>
      <div class="hollow-map-guide"><strong>${floor}</strong><span>${manage ? '次のマスを選ぶ' : 'ホストが次のマスを選ぶ'}</span>
        ${pinHint(manage)}</div>
      ${manage ? `<button class="hollow-route-btn danger" data-route-action="retreat">撤退${pins.marks(state, 'retreat')}</button>`
        : pins.canPin(state) ? `<button class="hollow-route-btn danger" ${pins.attrs(state, 'retreat')}>撤退${pins.marks(state, 'retreat')}</button>` : ''}</header>
      ${run.next_tier_error ? `<div class="hollow-map-retry"><span>${esc(run.next_tier_error)}</span>
        ${manage ? '<button class="hollow-route-btn" data-route-action="retry">次の区切りを開く</button>' : ''}</div>` : ''}
      <div class="hollow-map-scroll" tabindex="0" aria-label="階の地図"><div class="hollow-map-canvas">
        <svg class="hollow-map-paths" aria-hidden="true"></svg><div class="hollow-map-rows">${rows}</div>
      </div></div><div class="hollow-map-tip" aria-hidden="true" hidden></div>
      <footer class="hollow-map-tray">
        <div class="hollow-map-group"><b>出撃</b>${player.active.map(char => chip(char, canSwap)).join('') || '—'}</div>
        <div class="hollow-map-group"><b>控え</b>${player.reserve.map(char => chip(char, canSwap && char.hp > 0)).join('') || '—'}</div>
        ${canSwap ? `<span class="hollow-map-note">${chosen ? `${esc(chosen.name)}と入れ替える相手を選ぶ` : '1人ずつ押して入れ替え'}</span>` : ''}
      </footer>`;
  }

  function draw() {
    frame = 0;
    if (mount) mount.style.setProperty('--hollow-room-top', `${Math.max(0, mount.getBoundingClientRect().top)}px`);
    const canvas = view?.querySelector('.hollow-map-canvas');
    if (!canvas?.getClientRects().length || !state?.hollow?.run?.map) return;
    const run = state.hollow.run;
    const origin = canvas.getBoundingClientRect();
    const boxes = new Map([...canvas.querySelectorAll('[data-node]')].map(el => [el.dataset.node, el.getBoundingClientRect()]));
    const paths = [];
    for (const node of run.map.rows.flat()) {
      const from = boxes.get(node.id);
      for (const target of node.next) {
        const to = boxes.get(target);
        if (!from || !to) continue;
        const used = run.map.visited.includes(node.id) && run.map.visited.includes(target);
        const kind = used ? 'done' : node.id === run.map.current ? 'next' : node.floor <= run.floor ? 'past' : '';
        paths.push(`<line class="${kind}" x1="${from.left + from.width / 2 - origin.left}" y1="${from.bottom - origin.top}"
          x2="${to.left + to.width / 2 - origin.left}" y2="${to.top - origin.top}"/>`);
      }
    }
    canvas.querySelector('svg').innerHTML = paths.join('');
    const key = `${run.map.tier}/${run.map.current}`;
    if (scrollKey === key) return;
    scrollKey = key;
    const current = canvas.querySelector('.is-now, .is-next');
    const scroller = canvas.parentElement;
    if (current) scroller.scrollTop = current.getBoundingClientRect().top - origin.top - scroller.clientHeight / 2 + current.offsetHeight / 2;
  }

  function requestDraw() { if (!frame) frame = requestAnimationFrame(draw); }

  function paint() {
    const screen = panelFor(state);
    const changed = mount.dataset.hollowScreen !== screen;
    mount.dataset.hollowScreen = screen;
    view.hidden = screen === 'battle';
    if (view.hidden) {
      if (changed) requestAnimationFrame(() => window.renderVisualMap?.());
      return;
    }
    const run = state.hollow.run;
    const manage = window.HollowParty.canProgress(state);
    const html = screen === 'map' ? renderMap(run, manage)
      : screen === 'map-pending' ? mapChoice(run, manage)
      : screen === 'event' ? events.render(state, parties(run, state).order, manage, selectedChoice, selectedMember)
      : screen === 'reward' ? relics.rewardView(run, manage, TYPES[run.current_event?.type])
      : screen === 'fusion' ? relics.fusionView(run, manage) : renderCard(run, screen, manage);
    if (markup === html) return;
    const scroll = view.querySelector('.hollow-map-scroll')?.scrollTop || 0;
    const panelScroll = changed ? 0 : view.querySelector('.hr-screen')?.scrollTop || 0;
    const focused = view.contains(document.activeElement) ? document.activeElement.dataset : null;
    view.innerHTML = html;
    markup = html;
    const panel = view.querySelector('.hr-screen');
    if (panel) panel.scrollTop = panelScroll;
    if (screen === 'map') {
      view.querySelector('.hollow-map-scroll').scrollTop = scroll;
      requestDraw();
    }
    if (focused) [...view.querySelectorAll('button,input')].find(el =>
      (focused.relicAction && el.dataset.relicAction === focused.relicAction && el.dataset.key === focused.key)
      || (focused.relicWish !== undefined && el.hasAttribute('data-relic-wish'))
      || ['pin', 'node', 'chip', 'routeAction', 'mapId', 'eventAction', 'eventChoice', 'eventMember'].some(key => focused[key] && focused[key] === el.dataset[key]))?.focus({preventScroll: true});
  }

  function announce(title, subtitle, sinking) {
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches || window.Fx?.getLevel?.() === 'light';
    view.classList.toggle('is-sinking', sinking && !reduced);
    curtain.querySelector('strong').textContent = title;
    curtain.querySelector('span').textContent = subtitle;
    curtain.hidden = false;
    curtain.className = 'hollow-map-curtain is-in';
    curtain.classList.toggle('is-reduced', reduced);
    clearTimeout(timer);
    clearTimeout(leavingTimer);
    timer = setTimeout(() => {
      timer = null;
      paint();
      view.classList.remove('is-sinking');
      curtain.classList.replace('is-in', 'is-out');
      leavingTimer = setTimeout(() => {
        curtain.hidden = true;
        const round = pendingRound;
        pendingRound = null;
        if (round && panelFor(state) === 'battle') window.showRoundStartBanner?.(round);
        else if (round) window.EventBus?.emit('battle:round:banner:finished', {round});
      }, reduced ? 65 : 380);
    }, reduced ? 230 : 1150);
  }

  function tip(event) {
    const float = event.currentTarget.querySelector('.hollow-map-tip');
    if (!float || !state) return;
    const key = event.target.closest('[data-node]')?.dataset.node;
    const run = state.hollow.run;
    const node = run.map?.rows.flat().find(el => el.id === key);
    float.hidden = !node;
    if (!node) return;
    float.innerHTML = `<b>${node.floor}F ${typeName(node)}</b><span>${chooseLabel(node, nextIds(run), run, window.HollowParty.canProgress(state))}</span>`;
    float.style.left = `${Math.max(4, Math.min(event.clientX + 16, innerWidth - float.offsetWidth - 6))}px`;
    float.style.top = `${Math.max(4, Math.min(event.clientY + 16, innerHeight - float.offsetHeight - 6))}px`;
  }

  function send(event, payload = {}) {
    if (busy) return;
    busy = true;
    const sentRoom = room;
    window.socket.timeout(7000).emit(event, payload, (error, result) => {
      if (room !== sentRoom) return;
      busy = false;
      if (error || !result?.ok) window.showAppNotice(result?.error || '通信に失敗しました', {kind: 'error'});
    });
  }

  function openEntry(node, tier) {
    enterNode = {node_id: node.id, tier};
    dialog.querySelector('h2').textContent = `${node.floor}F ${TYPES[node.type]}`;
    dialog.returnValue = '';
    dialog.showModal();
  }

  function pick(id, run) {
    const prior = picked;
    picked = id === picked ? null : id;
    if (prior && picked && run.active.includes(prior) !== run.active.includes(id)) {
      const first = run.active.includes(prior);
      picked = null;
      send('hollow_swap_party', {active_id: first ? prior : id, reserve_id: first ? id : prior});
    }
    paint();
  }

  async function click(event) {
    const button = event.target.closest('button');
    if (!button || !state || busy || timer) return;
    if (button.dataset.pin !== undefined && !window.HollowParty.canProgress(state)) {
      const scene = state.hollow.run.pins?.scene;
      return scene && send('hollow_pin', {scene, option: button.dataset.pin});
    }
    if (button.dataset.relicAction) return relics.click(button);
    const action = button.dataset.routeAction;
    if (action === 'return') return leaveRoomTo('dungeon');
    const run = state.hollow.run;
    if (button.dataset.eventAction === 'close') {
      shownEvent = null;
      return paint();
    }
    if (!window.HollowParty.canProgress(state)) return;
    if (panelFor(state) === 'event' && button.dataset.eventAction !== 'retreat') {
      const current = run.current_event;
      if (current.resolved) return;
      if (button.dataset.eventChoice !== undefined) {
        selectedChoice = Number(button.dataset.eventChoice);
        selectedMember = null;
        return paint();
      }
      if (button.dataset.eventMember) {
        selectedMember = button.dataset.eventMember;
        return paint();
      }
      if (button.dataset.eventAction === 'decide') {
        const choice = current.choices[selectedChoice];
        return send('hollow_resolve_miasma', {floor:run.floor, choice_index:selectedChoice,
          char_id:choice.needs_member ? selectedMember : null});
      }
      if (['take','skip'].includes(button.dataset.eventAction)) {
        return send('hollow_resolve_chest', {floor:run.floor, take:button.dataset.eventAction === 'take',
          char_id:selectedMember});
      }
      return;
    }
    if (action === 'start') return send('hollow_run_start');
    if (button.dataset.mapId && run.map_candidates) {
      const current = room;
      const candidates = run.map_candidates;
      const area = candidates.maps.find(row => row.map_id === button.dataset.mapId);
      if (!area) return;
      const confirmed = await window.showAppConfirm(`${tierRange(candidates.tier)}\n${area.name}`, {
        title: 'このマップへ進む', confirmText: '進む', defaultFocus: 'cancel', danger: false, theme: 'abyss',
      });
      if (confirmed && room === current && state?.hollow.run.map_candidates?.tier === candidates.tier
          && window.HollowParty.canProgress(state)) {
        send('hollow_choose_map', {map_id: area.map_id, tier: candidates.tier});
      }
      return;
    }
    if (action === 'retreat' || button.dataset.eventAction === 'retreat') {
      const current = room;
      const confirmed = await window.showAppConfirm('遠征を終えて撤退しますか？',
        {title: '撤退', confirmText: '撤退', defaultFocus: 'cancel', danger: true});
      if (confirmed && room === current && state && ['map', 'map-pending', 'event'].includes(panelFor(state))
          && window.HollowParty.canProgress(state)) {
        send('hollow_retreat');
      }
      return;
    }
    if (action === 'retry') return send('hollow_select_node', {node_id: run.map.current, tier: run.map.tier});
    if (button.dataset.chip) return pick(button.dataset.chip, run);
    if (nextIds(run).has(button.dataset.node)) {
      openEntry(run.map.rows.flat().find(node => node.id === button.dataset.node), run.map.tier);
    }
  }

  function close() {
    relics.close();
    eventKey = shownEvent = selectedChoice = selectedMember = null;
    clearTimeout(timer);
    clearTimeout(leavingTimer);
    if (pendingRound) window.EventBus?.emit('battle:round:banner:finished', {round: pendingRound});
    cancelAnimationFrame(frame);
    if (mount) {
      delete mount.dataset.hollowScreen;
      mount.style.removeProperty('--hollow-room-top');
    }
    if (view) { view.hidden = true; view.classList.remove('is-sinking'); }
    if (curtain) curtain.hidden = true;
    dialog?.remove();
    resize?.disconnect();
    mount = view = curtain = dialog = resize = state = room = snapshot = markup = enterNode = picked = timer = scrollKey = null;
    pendingRound = null;
    busy = false;
    frame = 0;
  }

  function sync(value) {
    const root = document.getElementById('visual-battle-container');
    if (value?.play_mode !== 'hollow' || !value.hollow?.run || !root) return;
    if (mount !== root || room !== currentRoomName) {
      close();
      mount = root;
      room = currentRoomName;
      view = root.querySelector('#hollow-map-view');
      curtain = root.querySelector('#hollow-map-curtain');
      if (!view || !curtain) return;
      view.onclick = click;
      view.onchange = event => relics.change(event.target);
      view.onpointermove = tip;
      view.onpointerleave = event => {
        const el = event.currentTarget.querySelector('.hollow-map-tip');
        if (el) el.hidden = true;
      };
      resize = new ResizeObserver(requestDraw);
      resize.observe(view);
      const header = document.querySelector('#main-app-container > header');
      if (header) resize.observe(header);
      dialog = document.createElement('dialog');
      dialog.className = 'hollow-window hollow-map-entry';
      dialog.dataset.theme = 'abyss';
      dialog.setAttribute('aria-labelledby', 'hollow-entry-title');
      dialog.innerHTML = `<header><h2 id="hollow-entry-title"></h2></header><form method="dialog">
        <button value="cancel" class="hollow-route-btn" autofocus>キャンセル</button>
        <button value="enter" class="hollow-route-btn primary">入場</button></form>`;
      dialog.onclose = event => {
        const node = enterNode;
        enterNode = null;
        if (node && event.currentTarget.returnValue === 'enter' && state && panelFor(state) === 'map'
            && window.HollowParty.canProgress(state)) send('hollow_select_node', node);
      };
      document.body.append(dialog);
    }
    const previous = snapshot;
    state = value;
    relics.sync(state, room, () => { if (!timer) paint(); });
    const run = state.hollow.run;
    const key = keyFor(run);
    if (key !== eventKey) {
      eventKey = key;
      shownEvent = key && (previous || !run.current_event.resolved) ? key : null;
      selectedChoice = selectedMember = null;
    }
    const screen = panelFor(state);
    snapshot = {screen, floor:run.floor, tier: run.map?.tier, candidates: run.map_candidates?.maps};
    if (!window.HollowParty.canProgress(state)) {
      picked = null;
      if (dialog.open) dialog.close('cancel');
    }
    if (previous && run.floor > previous.floor && ['battle','event'].includes(screen)) {
      if (dialog.open) dialog.close('cancel');
      picked = null;
      announce(`${run.floor}F`, TYPES[run.current_event?.type], true);
    } else if (previous?.screen === 'battle' && screen !== 'battle') {
      const result = run.log?.findLast(row => row.floor === run.floor && row.outcome)?.outcome;
      if (snapshot.tier && snapshot.tier !== previous.tier) announce(`T${snapshot.tier}`, tierName(run.map), false);
      else if (result === 'VICTORY') announce(`${run.floor}F`, '制圧', false);
      else if (screen === 'finished') announce(`${run.floor}F`, OUTCOMES[run.result?.outcome], false);
      else paint();
    } else if (previous?.screen === 'map-pending' && screen === 'map') {
      const chosen = previous.candidates.find(row => row.map_id === run.map.map_id);
      if (chosen) announce(chosen.name, tierRange(run.map.tier), true);
      else if (!timer) paint();
    } else if (!timer) paint();
  }

  function deferRoundBanner(round) {
    if (!mount || round !== 1 || (mount.dataset.hollowScreen !== 'map' && curtain.hidden)) return false;
    pendingRound = round;
    return true;
  }

  window.HollowMap = {sync, close, deferRoundBanner};
})();
