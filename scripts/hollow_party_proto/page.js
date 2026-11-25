(() => {
  const people = [
    { id: 'rio', name: 'リオ', owner: true },
    { id: 'nagi', name: 'ナギ' },
    { id: 'touka', name: 'トウカ' },
  ];
  const chars = [
    { id: 'alto', name: 'アルト', owner: 'rio', img: 'male', hp: [42, 42], mp: [18, 18], fp: [3, 5] },
    { id: 'bell', name: 'ベル', owner: 'nagi', img: 'female', hp: [17, 36], mp: [9, 24], fp: [5, 5] },
    { id: 'kai', name: 'カイ', owner: 'touka', img: 'male', hp: [51, 51], mp: [12, 12], fp: [2, 5] },
    { id: 'dia', name: 'ディア', owner: 'nagi', img: 'female', hp: [30, 30], mp: [30, 30], fp: [4, 5] },
    { id: 'ema', name: 'エマ', owner: 'rio', img: 'female', hp: [33, 33], mp: [21, 21], fp: [5, 5] },
  ];
  const MAX = 6;
  const state = { party: ['alto', 'bell', 'kai', 'dia'], host: 'rio', viewer: 'rio', run: 'forming', place: 'a', sort: 'a' };
  const room = document.querySelector('.room');
  const $ = selector => document.querySelector(selector);
  const person = id => people.find(p => p.id === id);
  const char = id => chars.find(c => c.id === id);
  const esc = text => String(text).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

  const isLead = () => state.viewer === state.host || person(state.viewer).owner;
  const canEdit = () => isLead() && state.run !== 'running';
  const canUse = c => isLead() || c.owner === state.viewer;

  let toastTimer;
  function toast(text) {
    const node = $('[data-toast]');
    node.textContent = text;
    node.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.hidden = true; }, 2200);
  }

  function bar(label, [now, max], kind) {
    const pct = Math.round((now / max) * 100);
    return `<span class="stat stat-${kind}" title="${label} ${now}/${max}"><span class="stat-label">${label}</span>`
      + `<span class="stat-bar"><span style="width:${pct}%"></span></span><span class="stat-num">${now}/${max}</span></span>`;
  }

  function partyRow(id, index) {
    const c = char(id);
    const edit = canEdit();
    const last = state.party.length - 1;
    const handle = state.sort === 'b'
      ? `<button type="button" class="row-handle" data-handle="${id}" aria-label="${esc(c.name)}を動かす（上下の矢印キー）" ${edit ? '' : 'disabled'}>⠿</button>`
      : '';
    const arrows = state.sort === 'a'
      ? `<span class="row-move"><button type="button" class="ui-btn ghost icon" data-up="${id}" aria-label="${esc(c.name)}を上へ" ${edit && index > 0 ? '' : 'disabled'}>↑</button>`
        + `<button type="button" class="ui-btn ghost icon" data-down="${id}" aria-label="${esc(c.name)}を下へ" ${edit && index < last ? '' : 'disabled'}>↓</button></span>`
      : '';
    return `<li class="party-row${c.hp[0] < c.hp[1] / 2 ? ' is-hurt' : ''}" data-id="${id}" ${state.sort === 'b' && edit ? 'draggable="true"' : ''}>`
      + handle
      + `<span class="slot" aria-label="${index + 1}番目">${index + 1}</span>`
      + `<span class="face face-${c.img}" aria-hidden="true"></span>`
      + `<span class="who"><b>${esc(c.name)}</b><small>${esc(person(c.owner).name)}</small></span>`
      + `<span class="stats">${bar('HP', c.hp, 'hp')}${bar('MP', c.mp, 'mp')}${bar('FP', c.fp, 'fp')}</span>`
      + `<span class="row-actions">${arrows}`
      + `<button type="button" class="ui-btn ghost small" data-item="${id}" ${canUse(c) ? '' : 'disabled'}>アイテム</button>`
      + `<button type="button" class="ui-btn ghost small" data-detail="${id}">詳細</button>`
      + `<button type="button" class="ui-btn ghost small danger" data-remove="${id}" ${edit ? '' : 'disabled'}>外す</button>`
      + `</span></li>`;
  }

  function panel() {
    const rest = chars.filter(c => !state.party.includes(c.id));
    const locked = state.run === 'running';
    const addable = canEdit() && rest.length && state.party.length < MAX;
    const add = locked ? '' : `<div class="party-add">`
      + `<label><span>控え</span><select data-add-select ${addable ? '' : 'disabled'}>`
      + (rest.length ? rest.map(c => `<option value="${c.id}">${esc(c.name)}（${esc(person(c.owner).name)}）</option>`).join('') : '<option>なし</option>')
      + `</select></label><button type="button" class="ui-btn primary small" data-add ${addable ? '' : 'disabled'}>加える</button></div>`;
    const lead = isLead();
    const members = people.map((p, i) => {
      const badges = (p.id === state.host ? '<span class="badge host">ホスト</span>' : '')
        + (p.owner ? '<span class="badge owner">オーナー</span>' : '')
        + (p.id === state.viewer ? '<span class="badge self">自分</span>' : '');
      const give = lead && p.id !== state.host
        ? `<button type="button" class="ui-btn ghost small" data-give="${p.id}">ホストを譲る</button>` : '';
      return `<li class="member-row"><span class="join-order" aria-label="参加${i + 1}番目">${i + 1}</span>`
        + `<b>${esc(p.name)}</b>${badges}<span class="member-give">${give}</span></li>`;
    }).join('');
    return `<section class="panel-block">`
      + `<h3>パーティ <small>${state.party.length}/${MAX}</small>${locked ? '<span class="lock">🔒 並び固定</span>' : ''}</h3>`
      + `<p class="panel-caption">番号＝淵遺物の「N番目」</p>`
      + `<ol class="party-list">${state.party.map(partyRow).join('')}</ol>${add}</section>`
      + `<section class="panel-block"><h3>参加者 <small>${people.length}人</small></h3><ol class="member-list">${members}</ol>`
      + `<button type="button" class="ui-btn ghost small code-open" data-open-code>参加コード</button></section>`;
  }

  function render() {
    room.dataset.place = state.place;
    document.body.dataset.sort = state.sort;
    document.querySelectorAll('[data-panel]').forEach(node => { node.innerHTML = panel(); });
    $('[data-host-name]').textContent = person(state.host).name;
    $('[data-party-count]').textContent = `${state.party.length}/${MAX}`;
    $('[data-run-label]').textContent = state.run === 'running' ? 'ラン中・12F・T2' : 'パーティを組んでいる';
    const me = person(state.viewer);
    const role = state.viewer === state.host ? 'ホスト' : me.owner ? 'オーナー' : 'プレイヤー';
    $('[data-viewer-label]').textContent = `${me.name}（${role}）`;
    document.querySelectorAll('[data-compare]').forEach(b => b.setAttribute('aria-pressed', String(state[b.dataset.compare] === b.dataset.value)));
    document.querySelectorAll('[data-viewer]').forEach(b => b.setAttribute('aria-pressed', String(state.viewer === b.dataset.viewer)));
    document.querySelectorAll('[data-run]').forEach(b => b.setAttribute('aria-pressed', String(state.run === b.dataset.run)));
  }

  function move(id, delta, focus) {
    const from = state.party.indexOf(id);
    const to = from + delta;
    if (!canEdit() || from < 0 || to < 0 || to >= state.party.length) return;
    state.party.splice(to, 0, state.party.splice(from, 1)[0]);
    render();
    if (focus) document.querySelector(`.party-dialog[open] [data-handle="${id}"], [data-place="a"] .inline-panel [data-handle="${id}"]`)?.focus();
    toast(`${char(id).name}を${to + 1}番目にしました`);
  }

  let confirmTarget = null;
  document.addEventListener('click', event => {
    const t = event.target.closest('button');
    if (!t) return;
    const d = t.dataset;
    if (d.compare) { state[d.compare] = d.value; render(); }
    else if (d.viewer) { state.viewer = d.viewer; render(); }
    else if (d.run) { state.run = d.run; render(); }
    else if (d.codeMode) openCode('created');
    else if ('openParty' in d) $('[data-party-dialog]').showModal();
    else if ('openCode' in d) openCode('review');
    else if (d.up) move(d.up, -1);
    else if (d.down) move(d.down, 1);
    else if (d.remove) { state.party = state.party.filter(id => id !== d.remove); render(); toast(`${char(d.remove).name}を外しました`); }
    else if ('add' in d) {
      const id = t.closest('.party-add').querySelector('select').value;
      if (char(id) && state.party.length < MAX) { state.party.push(id); render(); toast(`${char(id).name}を加えました`); }
    }
    else if (d.item) toast(`${char(d.item).name}のアイテムの窓を開く（試作）`);
    else if (d.detail) toast(`${char(d.detail).name}の詳細を開く（試作）`);
    else if (d.give) {
      confirmTarget = d.give;
      $('[data-confirm-text]').textContent = `ホストを${person(d.give).name}に譲ります。マスの選択と戦闘の進行は${person(d.give).name}が行います。`;
      $('[data-confirm-dialog]').showModal();
    }
    else if ('confirmOk' in d) {
      state.host = confirmTarget;
      $('[data-confirm-dialog]').close();
      render();
      toast(`ホストが${person(confirmTarget).name}になりました`);
    }
    else if ('copy' in d) {
      const text = '部屋：青晶坑の先遣隊　参加コード：8YJGBP';
      navigator.clipboard?.writeText(text).catch(() => {});
      $('[data-copied]').textContent = `写しました：${text}`;
    }
    else if ('close' in d) t.closest('dialog').close();
  });

  function openCode(mode) {
    $('[data-code-title]').textContent = mode === 'created' ? '部屋を作りました' : '参加コード';
    $('[data-code-lead]').textContent = mode === 'created' ? '部屋の名前とコードを参加者に伝えます。' : '';
    $('[data-copied]').textContent = '';
    $('[data-code-dialog]').showModal();
  }

  document.addEventListener('keydown', event => {
    const handle = event.target.closest?.('[data-handle]');
    if (!handle || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    move(handle.dataset.handle, event.key === 'ArrowUp' ? -1 : 1, true);
  });

  let dragging = null;
  document.addEventListener('dragstart', event => {
    const row = event.target.closest?.('.party-row');
    if (!row) return;
    dragging = row.dataset.id;
    row.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', dragging);
  });
  document.addEventListener('dragover', event => {
    if (dragging && event.target.closest?.('.party-row')) event.preventDefault();
  });
  document.addEventListener('drop', event => {
    const row = event.target.closest?.('.party-row');
    if (!dragging || !row) return;
    event.preventDefault();
    move(dragging, state.party.indexOf(row.dataset.id) - state.party.indexOf(dragging));
  });
  document.addEventListener('dragend', () => { dragging = null; document.querySelectorAll('.is-dragging').forEach(n => n.classList.remove('is-dragging')); });

  function contrast() {
    const probe = document.createElement('span');
    const host = $('.hollow-strip');
    host.append(probe);
    const rgb = value => {
      probe.style.color = value;
      return getComputedStyle(probe).color.match(/[\d.]+/g).slice(0, 3).map(Number);
    };
    const lum = ([r, g, b]) => [r, g, b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
      .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    const pairs = [
      ['本文', '--ui-text', '--ui-bg', 4.5], ['補足', '--ui-sub', '--ui-bg', 4.5], ['補足・行', '--ui-sub', '--ui-soft', 4.5],
      ['主色', '--ui-primary', '--ui-bg', 4.5], ['主ボタン', '--ui-on-primary', '--ui-primary', 4.5],
      ['ホスト札', '--ui-warn', '--ui-warn-soft', 4.5], ['オーナー札', '--ui-ally', '--ui-ally-soft', 4.5],
      ['外す', '--ui-danger', '--ui-soft', 4.5], ['枠', '--ui-control', '--ui-bg', 3], ['枠・行', '--ui-control', '--ui-soft', 3],
    ];
    const rows = pairs.map(([label, fg, bg, need]) => {
      const value = ratio(`var(${fg})`, `var(${bg})`);
      return { label, value, ok: value >= need, need };
    });
    probe.remove();
    $('[data-contrast]').innerHTML = rows.map(r => `<tr class="${r.ok ? '' : 'ng'}"><th>${r.label}</th><td>${r.value.toFixed(2)}</td><td>${r.need}</td></tr>`).join('');
    const text = rows.filter(r => r.need === 4.5);
    const line = rows.filter(r => r.need === 3);
    const ng = rows.filter(r => !r.ok).length;
    $('[data-contrast-summary]').textContent = `文字 ${Math.min(...text.map(r => r.value)).toFixed(2)}・枠 ${Math.min(...line.map(r => r.value)).toFixed(2)}${ng ? `・未達${ng}` : ''}`;
    $('[data-contrast-summary]').classList.toggle('ng', ng > 0);
  }

  render();
  contrast();
})();
