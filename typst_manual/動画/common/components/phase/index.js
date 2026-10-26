// 盤面の上で4段階の現在地を示す。
DECK.define('m-phase', class extends DECK.MotionElement {
  static steps = 4;
  mount() {
    this.items = [...this.querySelectorAll('[data-phase]')];
    const labels = ['ラウンド開始', '選択フェーズ', '解決フェーズ', 'ラウンド終了'];
    this.items.forEach((e, i) => { e.textContent = labels[i]; });
  }
  duration(k) { return k > 0 ? 0.8 : 0; }
  render(k, t) {
    const p = k ? DECK.prog(t, 0, 0.8) : 0;
    this.items.forEach((e, i) => {
      e.classList.toggle('current', i === Math.max(0, k - 1));
      const glow = p >= 1 ? 0 : Math.sin(p * Math.PI);
      e.style.background = i === k - 1 ? `color-mix(in srgb, var(--emph) ${8 + 20 * glow}%, var(--series-3))` : 'var(--series-3)';
      e.setAttribute('aria-current', i === Math.max(0, k - 1) ? 'step' : 'false');
    });
  }
});
