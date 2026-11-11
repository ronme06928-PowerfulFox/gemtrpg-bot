(function () {
  const h = window.CatalogGlossary.escape;
  let nextId = 0;
  function render(label, text) {
    const id = `cat-info-${++nextId}`;
    return `<span class="cat-info"><button type="button" class="cat-info-button" aria-label="${h(label.endsWith('説明') ? label : label+'の説明')}" aria-describedby="${id}">i</button><span class="cat-info-tip cat-workspace" role="tooltip" id="${id}" hidden>${h(text)}</span></span>`;
  }
  function mount(root) {
    const doc = root.ownerDocument;
    if (!doc) return {close() {},destroy() {}};
    let active;
    function close() {
      if (!active) return;
      active.tip.hidden = true;active.parent.appendChild(active.tip);active = null;
    }
    function show(event) {
      const button = event.target.closest?.('.cat-info-button');
      if (!button || button === active?.button) return;
      close();
      const parent = button.parentElement, tip = parent.querySelector('[role="tooltip"]');
      if (!tip) return;
      active = {button,parent,tip};doc.body.appendChild(tip);tip.hidden = false;
      const rect = button.getBoundingClientRect(), view = doc.defaultView;
      const width = Math.min(300,view.innerWidth-24);
      tip.style.width = `${width}px`;
      tip.style.left = `${Math.max(12,Math.min(rect.left-10,view.innerWidth-width-12))}px`;
      tip.style.top = `${Math.max(12,Math.min(rect.bottom+6,view.innerHeight-tip.offsetHeight-12))}px`;
    }
    function leave(event) { if (event.target === active?.button && !(event.type === 'pointerout' && doc.activeElement === active.button)) close(); }
    function escape(event) { if (event.key === 'Escape' && active) {event.preventDefault();event.stopPropagation();close();} }
    root.addEventListener('pointerover',show);root.addEventListener('focusin',show);
    root.addEventListener('pointerout',leave);root.addEventListener('focusout',leave);
    root.addEventListener('keydown',escape);doc.addEventListener('scroll',close,true);
    doc.defaultView.addEventListener('resize',close);
    return {close,destroy() {close();root.removeEventListener('pointerover',show);root.removeEventListener('focusin',show);root.removeEventListener('pointerout',leave);root.removeEventListener('focusout',leave);root.removeEventListener('keydown',escape);doc.removeEventListener('scroll',close,true);doc.defaultView.removeEventListener('resize',close);}};
  }
  window.CatalogInfo = {render,mount};
})();
