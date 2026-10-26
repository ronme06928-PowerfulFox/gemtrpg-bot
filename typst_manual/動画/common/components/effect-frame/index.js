// r3-v2の赤枠を、タイミング→効果全体の2段階にする。
DECK.define('m-effect-frame', class extends DECK.MotionElement {
  static steps = 2;
  mount() {
    this.frame = this.querySelector('[data-effect-frame]');
    this.timing = this.querySelector('[data-effect-timing]');
    this.full = this.querySelector('[data-effect-text]');
  }
  duration(k) { return k === 1 ? 4.1 : k === 2 ? 0.7 : 0; }
  render(k, t) {
    const expand = k >= 2 ? DECK.prog(t, 0, 0.7) : 0;
    this.frame.style.width = `${DECK.lerp(this.timing.offsetWidth, this.full.offsetWidth, expand) + 16}px`;
    this.frame.style.opacity = k >= 2 ? '1' : k === 1 ? String(DECK.prog(t, 3.5, 0.6)) : '0';
    this.frame.dataset.extent = expand >= 1 ? 'full' : 'timing';
  }
});
