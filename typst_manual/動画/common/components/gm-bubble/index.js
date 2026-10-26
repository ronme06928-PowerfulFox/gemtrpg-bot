// 字幕より上に置くオパール色のGMの札と案内。
DECK.define('m-gm-bubble', class extends DECK.MotionElement {
  static steps = 1;
  mount() { this.panel = this.querySelector('[data-gm-panel]'); }
  duration(k) { return k ? 0.6 : 0; }
  render(k, t) {
    const p = k ? DECK.prog(t, 0, 0.6) : 0;
    this.panel.style.opacity = String(p);
    this.panel.style.transform = `translateY(${18 * (1 - p)}px)`;
  }
});
