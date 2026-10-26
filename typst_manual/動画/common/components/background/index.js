// 画像なしは格子、画像ありはcontain。現アプリと同じく格子を画像で置き換える。
DECK.define('m-background', class extends DECK.MotionElement {
  static steps = 1;
  mount() { this.image = this.querySelector('[data-background-image]'); }
  duration(k) { return k ? 0.8 : 0; }
  render(k, t) {
    // 途中の切替は動画の説明用。画像表示中は下の格子を見せない。
    const p = k ? DECK.prog(t, 0, 0.8) : 0;
    this.image.style.opacity = String(p);
    this.classList.toggle('has-background', k > 0 && p > 0);
  }
});
