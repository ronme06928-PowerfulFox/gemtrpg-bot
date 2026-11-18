window.createEncyclopediaView = function (panel, DATA) {
  const {jewels, jewelDefinitions, jewelArt, PROP_KEYS, propArt} = window.EncyclopediaArt;
  const $ = selector => panel.querySelector(selector);
  const dialog = $('#book-window');
  dialog.addEventListener('cancel', event => event.stopPropagation());
  if (panel.closest('.encyclopedia-room')) {
    const closeRoom = document.createElement('button');
    closeRoom.type = 'button';
    closeRoom.textContent = 'ルームへ戻る';
    closeRoom.addEventListener('click', () => window.closeRoomEncyclopedia());
    $('.book-bar').append(closeRoom);
  }
  const spread = $('#spread');
  const leaf = $('.turn-leaf');
  const front = $('.turn-front');
  const back = $('.turn-back');
  const pageTemplate = document.createElement('template');
  const query = $('#query');
  const results = $('#search-results');
  const pageJump = $('#page-jump');
  const pageJumpButton = $('#page-jump summary');
  const pageTarget = $('#page-target');
  const pageError = $('.page-jump-error');
  const doors = $('#doors');
  const shelves = $('#shelves');
  const chapterTabs = $('#chapter-tabs');
  const types = new Map(DATA.types.map(([kind, label]) => [kind, label]));
  const termPattern = /\[\[(W-\d{2,})(?:\|([^\]]*))?\]\]/g;
  const skillColors = {
    Ps:'ruby', Pb:'topaz', Pp:'citrine', Ms:'sapphire', Mb:'amethyst', Mp:'aquamarine',
    D:'pearl', B:'prism', C:'lapis', E:'garnet',
  };
  const kindColors = {glossary:'moonstone',buff:'emerald',item:'peridot',enemy:'onyx',radiance:'tourmaline',passive:'spinel'};
  const titleOverrides = { D:'守備' };
  const skills = DATA.groups.map(([prefix, groupTitle, category], index) => {
    const title = titleOverrides[prefix] || groupTitle;
    return {
    key:prefix, title:index < 6 ? `${category}・${title}` : title, spineTitle:title,
    spineCategory:index < 6 ? category : '', color:skillColors[prefix], kind:'skill',
    rows:DATA.rowsByKind.skill.filter(row => row.id.split('-')[0] === prefix),
    };
  });
  const others = [...types].filter(([key]) => key !== 'skill').flatMap(([key, title]) => key === 'buff'
    ? window.EncyclopediaData.buffVolumes(DATA.rowsByKind.buff) : [{
    key, title, color:kindColors[key], kind:key, rows:DATA.rowsByKind[key],
  }]);
  const books = [...skills, ...others];
  const booksByKey = new Map(books.map(book => [book.key, book]));
  const buffKeys = others.filter(book => book.kind === 'buff').map(book => book.key);
  // バフの本は1つの区画に並べ、先頭に「ここからバフ」を示す空の函を立てる。
  const worldCells = [['quill', 'glossary'], ['case:バフ', ...buffKeys, 'hourglass']];
  const rooms = new Map([
    // 棚の区画を左上から順に。区画の中は本と小物（PROP_KEYS）を並べた順に置く。
    ['adventurers', ['冒険者', 4, [['Ps', 'Pb', 'Pp'], ['Ms', 'Mb', 'Mp'], ['B', 'C', 'D'], ['radiance', 'item']], ['Ps', 'Ms', 'radiance']]],
    ['monsters', ['魔物', 1, [['candle', 'E', 'enemy', 'passive', 'dice']], ['E', 'enemy', 'passive']]],
    ['world', ['世界の理', worldCells.length, worldCells, ['glossary', ...buffKeys.slice(0, 1)]]],
  ].map(([key, [title, columns, cells, ornaments]]) => {
    const shelfRows = cells.map(items => items.map(id => PROP_KEYS.has(id) || id.startsWith('case:') ? id : booksByKey.get(id)));
    return [key, { title, columns, shelfRows, books:shelfRows.flat().filter(item => typeof item !== 'string'), ornaments }];
  }));
  const chapterOrder = ['ルール', 'タイミング', '効果', 'バフ', 'デバフ', '状態異常', 'スキルタグ'];
  const cardsPerPage = 12;
  const cardsPerSpread = cardsPerPage * 2;
  const all = books.flatMap(book => book.rows);
  const byId = new Map(all.map(row => [row.id, row]));
  const locationById = new Map();
  for (const book of books) {
    const category = row => row.data.category || '分類なし';
    const labels = [...new Set([...chapterOrder, ...book.rows.map(category)])];
    const sections = book.kind === 'glossary'
      ? labels.map(label => ({ label, rows:book.rows.filter(row => category(row) === label) })).filter(section => section.rows.length)
      : [{ label:'', rows:book.rows }];
    book.chapters = [];
    book.pages = [];
    for (const { label, rows } of sections) {
      const start = book.pages.length;
      const count = Math.max(1, Math.ceil(rows.length / cardsPerSpread));
      if (label) book.chapters.push({ label, start });
      for (let number = 0; number < count; number++) {
        const offset = number * cardsPerSpread;
        book.pages.push({ cards:rows.slice(offset, offset + cardsPerSpread), label, start, number, count });
      }
      for (const [index, row] of rows.entries()) {
        locationById.set(row.id, { book, page:book.pages.length });
        book.pages.push({ row, start, contentsPage:start + Math.floor(index / cardsPerSpread) });
      }
    }
  }
  let activeRoom = null;
  let activeBook;
  let page = 0;
  let highlightedEntry;
  let openFrom = null;
  let turningTo;
  panel.insertAdjacentHTML('afterbegin', jewelDefinitions());

  const h = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
  })[ch]);
  const readable = row => row && row.met;
  // バフの文章の {{value}} などはゲーム内で数値に置き換わる。図鑑では「X」と書く。
  const variablePattern = /{{\s*(?:value|count|duration)\s*}}/gi;
  const hasVariable = value => /{{\s*(?:value|count|duration)\s*}}/i.test(String(value ?? ''));
  const variables = html => html.replace(variablePattern, '<var class="encyclopedia-variable">X</var>');
  const plain = value => String(value ?? '').replace(termPattern, (_, id, label) => label || byId.get(id)?.name || id)
    .replace(variablePattern, 'X');
  const description = row => row.data.long || row.data.short || row.data.description || row.data.発動時効果 || '';
  const link = (id, label) => readable(byId.get(id)) ? `<a href="#${h(id)}" data-entry="${h(id)}">${h(label)}</a>` : h(label);
  function markup(value) {
    const text = String(value ?? '');
    let start = 0;
    let output = '';
    for (const [match, id, label] of text.matchAll(termPattern)) {
      const index = text.indexOf(match, start);
      output += variables(h(text.slice(start, index))) + link(id, label || byId.get(id)?.name || id);
      start = index + match.length;
    }
    return output + variables(h(text.slice(start)));
  }

  const searchable = new Map(all.map(row => [row.id, [row.id, row.name, description(row), row.data.short, row.data.flavor,
    ...(row.data.synonyms || []), row.data.コスト, row.data.特記].map(plain).join(' ').normalize('NFKC').toLowerCase()]));

  const titled = book => book.kind === 'skill' ? `${book.key} ${book.title}` : book.title;
  const jewelStyle = color => {
    const gem = jewels[color];
    return `--jewel:${gem.hue};--jewel-mid:${gem.mid};--jewel-deep:${gem.dark}`;
  };

  const unlockCount = rows => rows.filter(readable).length;

  function renderDoors() {
    $('#total-count').textContent = `${books.length}冊 · 全体の解禁 ${all.filter(readable).length}/${all.length}`;
    for (const button of doors.querySelectorAll('[data-door]')) button.remove();
    doors.insertAdjacentHTML('afterbegin', [...rooms].map(([key, { title, books, ornaments }]) => {
      const rows = books.flatMap(book => book.rows);
      return `<button type="button" class="door" data-door="${key}" aria-controls="shelves">
        <span class="door-emblem">${ornaments.map(id => jewelArt(booksByKey.get(id).color)).join('')}</span>
        <strong class="door-title">${h(title)}</strong><small class="door-count">解禁 ${unlockCount(rows)}/${rows.length}</small>
      </button>`;
    }).join(''));
  }

  function renderShelf() {
    if (!activeRoom) return;
    const room = rooms.get(activeRoom);
    $('#shelf-title').textContent = room.title;
    $('#shelf-books').style.setProperty('--shelf-columns', room.columns);
    $('#shelf-books').innerHTML = room.shelfRows.map(row => `<div class="shelf-row">${row.map(book => {
      if (typeof book === 'string' && book.startsWith('case:')) {
        return `<span class="shelf-case" role="note" aria-label="ここから${h(book.slice(5))}の本"><strong>${h(book.slice(5))}</strong></span>`;
      }
      if (typeof book === 'string') return propArt(book);
      const unlocked = unlockCount(book.rows);
      const complete = unlocked === book.rows.length;
      return `<button type="button" class="shelf-book${book.color === 'prism' ? ' prism' : ''}" data-book="${book.key}" aria-haspopup="dialog" style="${jewelStyle(book.color)}">
        <span class="spine-mark">${jewelArt(book.color)}${book.kind === 'skill' ? `<code>${h(book.key)}</code>` : ''}</span>
        <span class="spine-heading">${book.spineCategory ? `<small class="spine-category">${h(book.spineCategory)}</small>` : ''}
          <strong class="spine-title">${h(book.spineTitle || book.title)}</strong></span>
        <small class="spine-count">解禁 ${unlocked}/${book.rows.length}</small>
        <span class="clasp${complete ? ' complete' : ''}">${complete ? `${jewelArt(book.color,true)}<span>全解禁</span>` : '<span aria-hidden="true" class="clasp-hole"></span>'}</span>
      </button>`;
    }).join('')}</div>`).join('');
  }

  function renderSearch() {
    const needle = query.value.normalize('NFKC').trim().toLowerCase();
    results.hidden = !needle;
    doors.hidden = !!needle || !!activeRoom;
    shelves.hidden = !!needle || !activeRoom;
    if (!needle) return;
    const matches = all.filter(row => (readable(row) ? searchable.get(row.id) : row.id.toLowerCase()).includes(needle));
    results.innerHTML = `<h2>検索結果 <small>${matches.length}件</small></h2><div class="search-grid">${matches.map(row => {
      const visible = readable(row);
      return `<button type="button" class="search-hit${visible ? '' : ' locked'}" data-entry="${h(row.id)}" data-kind="${row.kind}" ${visible ? 'aria-haspopup="dialog"' : 'disabled'}>
        <code>${h(row.id)}</code><strong>${visible ? h(row.name) : '？？？'}</strong>
        ${visible ? `<small>${h(titled(locationById.get(row.id).book))}</small>` : ''}</button>`;
    }).join('')}</div>`;
  }

  const duration = value => value == null ? null : value === -1 ? '解除まで' : `${value}ラウンド`;
  function summary(row) {
    const data = row.data;
    const facts = {
      glossary: [['分類', data.category]], buff: [['持続', duration(data.default_duration)]],
      item: [['消耗', data.consumable ? 'あり' : 'なし'], ['使用', data.usable ? '可' : '不可'],
        ['ラウンド制限', data.round_limit === -1 ? '制限なし' : data.round_limit]],
      enemy: [['HP', data.hp], ['MP', data.mp]],
      radiance: [['取得コスト', data.cost], ['持続', duration(data.duration)]],
      passive: [['取得コスト', data.cost]],
    }[row.kind];
    const values = facts.filter(([, value]) => value != null && value !== '');
    const related = row.kind === 'glossary' ? data.links || [] : row.kind === 'enemy' ? (data.skills || []).map(skill => skill.id) : [];
    const links = related.filter(id => readable(byId.get(id))).map(id => `<li>${link(id, `${id} ${byId.get(id).name}`)}</li>`).join('');
    return `${values.length ? `<dl class="facts">${values.map(([label,value]) => `<div><dt>${label}</dt><dd>${h(value)}</dd></div>`).join('')}</dl>` : ''}
      ${data.short && data.long && data.short !== data.long ? `<p>${markup(data.short)}</p>` : ''}
      <p>${markup(description(row) || '説明未登録')}</p>
      ${hasVariable(description(row)) ? '<p class="variable-note"><var class="encyclopedia-variable">X</var> は、このバフを付ける効果で決まる値。</p>' : ''}
      ${links ? `<section class="detail-links"><h3>${row.kind === 'enemy' ? '所持スキル' : '関連用語'}</h3><ul>${links}</ul></section>` : ''}`;
  }

  function contents({ cards, label, number, count }) {
    const entries = cards.map(row => {
      const visible = readable(row);
      const state = visible ? (row.id === highlightedEntry ? ' highlighted' : '') : ' locked';
      return `<button type="button" class="contents-entry${state}" data-entry="${h(row.id)}" ${visible ? '' : 'disabled'}>
        ${visible ? jewelArt(activeBook.color) : ''}<code>${h(row.id)}</code><strong>${visible ? h(row.name) : '？？？'}</strong>${visible ? `<small>${locationById.get(row.id).page + 1}ページ</small>` : ''}</button>`;
    });
    const grid = cards => `<div class="contents-grid">${cards.join('')}</div>`;
    return `<div class="contents contents-left"><header><h3>${label ? `<small>目次</small> ${h(label)}` : '目次'}${count > 1 ? ` <small>${number + 1}/${count}</small>` : ''}</h3>${activeBook.rows.some(row => !readable(row)) ? '<p>戦闘で出会うと解禁</p>' : ''}</header>
      ${grid(entries.slice(0, cardsPerPage))}</div>
      <div class="contents contents-right">${grid(entries.slice(cardsPerPage))}</div>`;
  }

  function specimenNotes(row) {
    const data = row.data;
    const range = data.射程 || data.距離;
    const marks = (data.marks || []).filter(mark => mark !== 'known').map(mark => DATA.markLabels[mark]).filter(Boolean);
    const tags = (row.kind === 'skill'
      ? [data.タイミング || data.分類, data.属性, range ? `射程 ${range}` : '', ...(data.tags || [])]
      : [data.category, ...(data.tags || []), ...(data.granted_tag_ids || [])])
      .filter(tag => tag && tag !== '---').concat(marks);
    const date = row.firstSeenAt ? new Date(row.firstSeenAt).toLocaleDateString('ja-JP') : '未記録';
    return `${tags.length ? `<ul class="specimen-tags">${[...new Set(tags)].map(tag => `<li>${h(tag)}</li>`).join('')}</ul>` : ''}
      ${data.flavor ? `<p class="flavor">${markup(data.flavor)}</p>` : ''}
      ${row.gated ? `<dl class="encounter-date"><dt>初めて出会った日</dt><dd>${date}</dd></dl>` : ''}`;
  }

  function itemSpread(row) {
    const classification = row.kind === 'skill' ? `スキル · ${titled(activeBook)}` : types.get(row.kind);
    return `<div class="specimen-page">
      <div class="specimen-mount">${jewelArt(activeBook.color,true)}</div>
      <div class="specimen-label"><code class="specimen-id">${h(row.id)}</code><h3>${h(row.name)}</h3><p>${h(classification)}</p></div>
      ${specimenNotes(row)}
    </div>
    <div class="text-page">
      <div class="book-reading-body">${row.kind === 'skill' ? window.formatSkillDetailHTML(row.data, {markupToHtml: markup}) : summary(row)}</div>
    </div>`;
  }

  const totalPages = () => activeBook.pages.length;
  const pageIsRead = position => {
    const spread = activeBook.pages[position];
    return spread && (!spread.row || readable(spread.row));
  };

  function neighbor(direction) {
    for (let next = page + direction; next >= 0 && next < totalPages(); next += direction) {
      if (pageIsRead(next)) return next;
    }
  }

  function renderBook() {
    $('#book-title').textContent = titled(activeBook);
    dialog.style.cssText = jewelStyle(activeBook.color);
    dialog.classList.toggle('prism', activeBook.color === 'prism');
    spread.innerHTML = spreadHTML(page);
    renderPageControls();
  }

  function renderPageControls() {
    $('#page-number').textContent = `${page + 1}/${totalPages()}`;
    const current = activeBook.pages[page];
    $('#show-contents').disabled = !current.row;
    pageTarget.max = totalPages();
    $('#page-range').textContent = `1〜${totalPages()}ページ`;
    $('#previous').disabled = neighbor(-1) === undefined;
    $('#next').disabled = neighbor(1) === undefined;
    for (const tab of chapterTabs.querySelectorAll('button')) {
      if (Number(tab.dataset.chapter) === current.start) tab.setAttribute('aria-current', 'true');
      else tab.removeAttribute('aria-current');
    }
  }

  function spreadHTML(position) {
    const entry = activeBook.pages[position];
    return entry.row ? itemSpread(entry.row) : contents(entry);
  }

  function clearTurn() {
    turningTo = undefined;
    delete leaf.dataset.direction;
    front.replaceChildren();
    back.replaceChildren();
    spread.inert = false;
  }

  function openBook(book, position, from) {
    clearTurn();
    activeBook = book;
    chapterTabs.innerHTML = book.chapters.map(({ label, start }) =>
      `<button type="button" data-chapter="${start}">${h(label)}</button>`).join('');
    chapterTabs.hidden = !book.chapters.length;
    dialog.classList.toggle('chaptered', !chapterTabs.hidden);
    page = position;
    highlightedEntry = undefined;
    pageJump.open = false;
    renderBook();
    if (!dialog.open) {
      openFrom = from;
      dialog.showModal();
    } else {
      $('#close-book').focus();
    }
  }

  function turn(direction) {
    const next = neighbor(direction);
    if (next === undefined || turningTo !== undefined) return;
    pageJump.open = false;
    highlightedEntry = undefined;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      page = next;
      renderBook();
      return;
    }
    const side = direction > 0 ? 1 : 0;
    const outgoing = spread.children[side];
    const scroll = outgoing.scrollTop;
    pageTemplate.innerHTML = spreadHTML(next);
    const [nextLeft, nextRight] = pageTemplate.content.children;
    const nextPages = [nextLeft, nextRight];
    // Under the turning sheet, the far half already belongs to the destination spread.
    outgoing.replaceWith(nextPages[side]);
    front.replaceChildren(outgoing);
    back.replaceChildren(nextPages[1 - side]);
    spread.inert = true;
    turningTo = next;
    leaf.dataset.direction = direction > 0 ? 'forward' : 'back';
    outgoing.scrollTop = scroll;
  }

  panel.addEventListener('click', event => {
    const control = event.target.closest('[data-book], [data-entry]');
    if (!control || control.disabled) return;
    event.preventDefault();
    if (control.dataset.book) {
      openBook(booksByKey.get(control.dataset.book), 0, control);
    } else if (readable(byId.get(control.dataset.entry))) {
      const target = locationById.get(control.dataset.entry);
      openBook(target.book, target.page, control);
    }
  });
  doors.addEventListener('click', event => {
    const door = event.target.closest('button[data-door]');
    if (!door) return;
    activeRoom = door.dataset.door;
    renderShelf();
    renderSearch();
    $('#shelf-title').focus();
  });
  $('#close-shelf').addEventListener('click', () => {
    const door = doors.querySelector(`[data-door="${activeRoom}"]`);
    activeRoom = null;
    renderSearch();
    door.focus();
  });
  query.addEventListener('input', renderSearch);
  $('#close-book').addEventListener('click', () => dialog.close());
  $('#show-contents').addEventListener('click', () => {
    clearTurn();
    const current = activeBook.pages[page];
    highlightedEntry = current.row.id;
    page = current.contentsPage;
    pageJump.open = false;
    renderBook();
    $('.contents-entry.highlighted').focus();
  });
  chapterTabs.addEventListener('click', event => {
    const tab = event.target.closest('button[data-chapter]');
    if (!tab) return;
    clearTurn();
    page = Number(tab.dataset.chapter);
    highlightedEntry = undefined;
    pageJump.open = false;
    renderBook();
  });
  pageJumpButton.addEventListener('click', () => {
    if (pageJump.open) return;
    pageTarget.value = page + 1;
    pageError.hidden = true;
  });
  pageJump.addEventListener('toggle', () => {
    if (!pageJump.open || document.activeElement !== pageJumpButton) return;
    pageTarget.focus();
    pageTarget.select();
  });
  $('#page-jump-form').addEventListener('submit', event => {
    event.preventDefault();
    const destination = pageTarget.valueAsNumber - 1;
    if (!pageIsRead(destination)) {
      pageError.textContent = 'このページは戦闘で出会うと解禁されます。';
      pageError.hidden = false;
      return;
    }
    clearTurn();
    page = destination;
    highlightedEntry = undefined;
    pageJump.open = false;
    renderBook();
    pageJumpButton.focus();
  });
  $('#previous').addEventListener('click', () => turn(-1));
  $('#next').addEventListener('click', () => turn(1));
  dialog.addEventListener('keydown', event => {
    if (pageJump.open && event.key === 'Escape') {
      event.preventDefault();
      pageJump.open = false;
      pageJumpButton.focus();
      return;
    }
    if (event.target.closest('#page-jump form')) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      turn(event.key === 'ArrowLeft' ? -1 : 1);
    }
  });
  dialog.addEventListener('close', () => {
    clearTurn();
    pageJump.open = false;
    if (openFrom?.isConnected) openFrom.focus();
  });
  function finishTurn(event) {
    if (event.target !== leaf || turningTo === undefined) return;
    const destinationSide = leaf.dataset.direction === 'forward' ? 0 : 1;
    spread.children[destinationSide].replaceWith(back.firstElementChild);
    page = turningTo;
    clearTurn();
    renderPageControls();
  }
  leaf.addEventListener('animationend', finishTurn);
  leaf.addEventListener('animationcancel', finishTurn);

  renderDoors();
  return {
    openEntry(id) {
      const destination = locationById.get(id);
      if (!destination || !readable(byId.get(id))) return false;
      activeRoom = [...rooms].find(([, room]) => room.books.includes(destination.book))?.[0] || null;
      renderShelf(); renderSearch();
      openBook(destination.book, destination.page, null);
      return true;
    },
    getState() {
      return { room:activeRoom, book:dialog.open ? activeBook.key : null, page,
        entryId:dialog.open ? activeBook.pages[page].row?.id : null, query:query.value };
    },
    restore(position) {
      if (!position) return;
      activeRoom = rooms.has(position.room) ? position.room : null;
      renderShelf();
      query.value = position.query || '';
      renderSearch();
      const book = booksByKey.get(position.book);
      if (position.entryId && this.openEntry(position.entryId)) return;
      if (book) {
        const target = Math.min(Math.max(position.page || 0, 0), book.pages.length - 1);
        openBook(book, !book.pages[target].row || readable(book.pages[target].row) ? target : 0, null);
      }
    },
    destroy() { clearTurn(); if (dialog.open) dialog.close(); panel.replaceChildren(); },
  };
};
