(function () {
  const glossary = window.CatalogGlossary;
  let nextId = 0;
  const candidates = (entries, currentId, query = '') => glossary.linkCandidates(entries, currentId, [], query);
  function timings(entries) {
    return entries.filter(row => !row.deprecated && row.payload.category === 'タイミング')
      .sort((a, b) => (a.payload.sort_order ?? Infinity) - (b.payload.sort_order ?? Infinity) || a.entry_id.localeCompare(b.entry_id));
  }
  function replace(value, start, end, inserted) {
    return { value: value.slice(0, start) + inserted + value.slice(end), caret: start + inserted.length };
  }
  function insertLink(value, start, end, term, inlineStart = null) {
    const label = inlineStart == null && end > start ? value.slice(start, end) : term.payload.display_name;
    return replace(value, inlineStart ?? start, end, `[[${term.entry_id}|${label}]]`);
  }
  function inlineQuery(value, start, end) {
    if (start !== end) return null;
    const before = value.slice(0, start);
    const match = before.match(/\[\[([^\[\]\n|]*)$/);
    return match ? { start: start - match[0].length, query: match[1] } : null;
  }
  function insertTiming(value, caret, term) {
    const start = caret > 0 ? value.lastIndexOf('\n', caret - 1) + 1 : 0;
    const prefix = value.slice(start).match(/^[ \t]*\([^\n)]*\)[ \t]*[:：][ \t]*/);
    return replace(value, start, start + (prefix?.[0].length || 0), `([[${term.entry_id}|${term.payload.display_name}]]):`);
  }
  function mount(root, { entries, currentId = '' }) {
    const cleanups = [];
    for (const field of root.querySelectorAll('textarea[data-catalog-text]')) {
      const document = field.ownerDocument;
      const id = `cat-text-tools-${++nextId}`;
      const label = field.closest('label');
      const oldFor = label?.getAttribute('for');
      const oldId = field.getAttribute('id');
      const oldAriaLabel = field.getAttribute('aria-label');
      const title = label ? [...label.childNodes].filter(node => node.nodeType === 3).map(node => node.textContent.trim()).join(' ').trim() : '';
      if (oldAriaLabel == null && title) field.setAttribute('aria-label', title);
      if (!field.id) field.id = `${id}-field`;
      // 暗黙のlabelは最初のbuttonを指すため、文章欄を明示して関連を維持する。
      if (label) label.setAttribute('for', field.id);
      const toolbar = document.createElement('div');
      toolbar.className = 'cat-text-tools';
      toolbar.innerHTML = `<div class="cat-text-tools-bar"><button type="button" class="cat-button" data-text-insert aria-expanded="false" aria-controls="${id}-picker">用語を挿入</button><select aria-label="タイミング" data-text-timing><option value="">タイミング</option>${timings(entries).map(row => `<option value="${glossary.escape(row.entry_id)}">${glossary.escape(row.payload.display_name)}</option>`).join('')}</select></div><div class="cat-text-picker" id="${id}-picker" hidden><input type="search" aria-label="挿入する用語を検索" placeholder="ID・名前・別名で検索" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${id}-options"><div class="cat-link-candidates" id="${id}-options" role="listbox" aria-label="挿入する用語の候補"></div></div>`;
      field.before(toolbar);
      const button = toolbar.querySelector('[data-text-insert]');
      const timing = toolbar.querySelector('[data-text-timing]');
      const picker = toolbar.querySelector('.cat-text-picker');
      const search = toolbar.querySelector('input');
      const list = toolbar.querySelector('[role="listbox"]');
      let start = 0, end = 0, inlineStart = null, query = '', index = 0, options = [];
      const listeners = [];
      function listen(target, type, handler) { target.addEventListener(type, handler); listeners.push([target, type, handler]); }
      function remember() { start = field.selectionStart; end = field.selectionEnd; }
      function close() {
        picker.hidden = true; inlineStart = null;
        for (const control of [button, search, field]) { control.setAttribute('aria-expanded', 'false'); control.removeAttribute('aria-activedescendant'); }
      }
      function render() {
        options = candidates(entries, currentId, query);
        index = Math.max(0, Math.min(index, options.length - 1));
        list.innerHTML = options.length ? options.map((row, i) => `<button type="button" role="option" tabindex="-1" id="${id}-${i}" data-text-option="${i}" aria-selected="${index === i}"><code>${glossary.escape(row.entry_id)}</code><span>${glossary.escape(row.payload.display_name)}</span></button>`).join('') : '<p class="cat-caption" role="status">候補がありません。</p>';
        for (const control of [search, field]) {
          control.setAttribute('aria-expanded', 'true');
          if (options.length) control.setAttribute('aria-activedescendant', `${id}-${index}`);
          else control.removeAttribute('aria-activedescendant');
        }
      }
      function open(inline = null) {
        remember(); inlineStart = inline?.start ?? null; query = inline?.query || ''; index = 0;
        picker.hidden = false; button.setAttribute('aria-expanded', 'true'); search.value = query; render();
        if (!inline) search.focus();
      }
      function apply(result) {
        close(); field.value = result.value; field.focus(); field.setSelectionRange(result.caret, result.caret);
        field.dispatchEvent(new field.ownerDocument.defaultView.Event('input', { bubbles: true }));
      }
      function choose(position) {
        const term = options[position];
        if (term) apply(insertLink(field.value, start, end, term, inlineStart));
      }
      listen(button, 'click', event => { event.preventDefault(); if (picker.hidden) open(); else { close(); field.focus(); } });
      // 選択欄へフォーカスが移る前の文章位置を保持する（キーボード操作はblurでも保持）。
      listen(field, 'blur', remember);
      listen(timing, 'pointerdown', remember);
      listen(timing, 'change', () => {
        const term = timings(entries).find(row => row.entry_id === timing.value);
        timing.value = ''; if (term) apply(insertTiming(field.value, start, term));
      });
      listen(search, 'input', () => { query = search.value; index = 0; render(); });
      listen(list, 'pointerdown', event => event.preventDefault());
      listen(list, 'click', event => {
        const option = event.target.closest('[data-text-option]');
        if (option) { event.preventDefault(); choose(Number(option.dataset.textOption)); }
      });
      listen(field, 'input', event => {
        if (event.isComposing) return;
        const inline = inlineQuery(field.value, field.selectionStart, field.selectionEnd);
        if (inline) open(inline); else close();
      });
      listen(field, 'compositionend', () => {
        const inline = inlineQuery(field.value, field.selectionStart, field.selectionEnd);
        if (inline) open(inline);
      });
      function keydown(event) {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Tab'].includes(event.key)) { close(); return; }
        if (picker.hidden || event.isComposing || event.keyCode === 229 || !['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) return;
        event.preventDefault(); event.stopPropagation();
        if (event.key === 'Escape') { close(); field.focus(); return; }
        if (event.key === 'Enter') { choose(index); return; }
        if (options.length) index = (index + (event.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length;
        render(); list.querySelector(`[aria-selected="true"]`)?.scrollIntoView({ block: 'nearest' });
      }
      listen(search, 'keydown', keydown); listen(field, 'keydown', keydown);
      listen(root, 'pointerdown', event => { if (event.target !== field && !toolbar.contains(event.target)) close(); });
      listen(field, 'click', () => close());
      cleanups.push(() => {
        close(); listeners.forEach(([target, type, handler]) => target.removeEventListener(type, handler)); toolbar.remove();
        if (label) { if (oldFor == null) label.removeAttribute('for'); else label.setAttribute('for', oldFor); }
        if (oldId == null) field.removeAttribute('id');
        if (oldAriaLabel == null) field.removeAttribute('aria-label');
      });
    }
    return { destroy() { cleanups.splice(0).forEach(cleanup => cleanup()); } };
  }
  window.CatalogTextTools = { candidates, timings, insertLink, inlineQuery, insertTiming, mount };
})();
