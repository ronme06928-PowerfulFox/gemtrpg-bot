(function () {
  const played = new Set();
  const observers = new WeakMap();
  const visibilityThreshold = .75;

  function cover(breaking = false, key = '') {
    if (!breaking) return '<div class="hidden-passive-cover" aria-label="伏せたパッシブ">？？？</div>';
    const revealKey = encodeURIComponent(key);
    if (played.has(revealKey) || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return '';
    return `<span class="hidden-passive-cover is-armed" data-reveal-key="${revealKey}" aria-hidden="true">
      <span class="hidden-passive-face">？？？</span>
    </span>`;
  }

  function stopObserving(root) {
    observers.get(root)?.();
  }

  function observe(root, level) {
    stopObserving(root);
    const pending = new Set(root?.querySelectorAll?.('.hidden-passive-cover.is-armed'));
    if (!pending.size) return;
    const visible = new Set();

    function startVisible() {
      if (document.visibilityState === 'hidden') return;
      for (const card of visible) {
        const { revealKey } = card.dataset;
        if (revealKey) played.add(revealKey);
        card.dataset.level = level || window.Fx?.getLevel?.() || 'normal';
        card.addEventListener('animationend', event => {
          if (event.animationName === 'hidden-passive-sweep') card.remove();
        });
        card.classList.remove('is-armed');
        card.classList.add('is-sweeping');
        observer?.unobserve(card);
        pending.delete(card);
      }
      visible.clear();
      if (!pending.size) stopObserving(root);
    }

    const observer = window.IntersectionObserver ? new window.IntersectionObserver(entries => {
      for (const { target, intersectionRatio } of entries) {
        if (intersectionRatio >= visibilityThreshold) visible.add(target);
        else visible.delete(target);
      }
      startVisible();
    }, { threshold: visibilityThreshold }) : null;
    observers.set(root, () => {
      observer?.disconnect();
      document.removeEventListener('visibilitychange', startVisible);
      observers.delete(root);
    });
    document.addEventListener('visibilitychange', startVisible);
    for (const card of pending) {
      if (observer) observer.observe(card);
      else visible.add(card);
    }
    if (!observer) startVisible();
  }

  function newThisRound(character, state) {
    return Number(state?.round) > 0 && !state.is_round_ended
      && Number(character?.passive_revealed_round) === Number(state.round);
  }

  window.HiddenPassiveFx = { cover, newThisRound, observe, stopObserving };
})();
