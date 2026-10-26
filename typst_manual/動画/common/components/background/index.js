// 動画用。初期表示から採用画像を敷き、切替や巻き戻しでも格子を露出しない。
DECK.define('m-background', class extends DECK.MotionElement {
  static steps = 1;
  mount() { this.image = this.querySelector('[data-background-image]'); }
  duration(k) { return k ? 0.8 : 0; }
  render(k, t) {
    const p = k ? DECK.prog(t, 0, 0.8) : 0;
    this.image.style.opacity = String(0.85 + 0.15 * p);
  }
});
