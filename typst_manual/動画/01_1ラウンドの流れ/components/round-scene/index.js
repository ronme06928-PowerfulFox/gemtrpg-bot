// egatariの(k,t)だけで描く。時計・CSSアニメーション・前回の描画状態を使わない。
DECK.define('m-round-scene', class extends DECK.MotionElement {
  static props = { scene: { type: 'string', default: 'resources' } };

  // 題はスライド入場（段階0）から動かす。fromとstepsでスライドの段階へ対応させる。
  get from() { return this.props.scene === 'title' ? 0 : super.from; }

  mount() {
    this.pieces = [...this.querySelectorAll('.app-piece')];
    this.rows = [...this.querySelectorAll('.app-stat-row')];
    this.badges = [...this.querySelectorAll('.app-fp')];
    this.telops = [...this.querySelectorAll('[data-telop]')];
    this.cards = [...this.querySelectorAll('.book-card')];
  }

  duration(k) {
    if (this.props.scene === 'title') return k === 1 ? 1.2 : 12.5;
    return [0, 8.4, 2.4, 1.4][k] || 0;
  }

  render(k, t, ctx) {
    const clamp = (v) => Math.max(0, Math.min(1, v));
    const ease = (v) => 1 - (1 - clamp(v)) ** 3;
    const time = t === Infinity || ctx.mode === 'lecture' ? this.duration(k) + 1 : t;
    const show = (el, alpha, y = 0, scale = 1) => {
      el.style.opacity = alpha.toFixed(4);
      el.style.visibility = alpha > 0.001 ? 'visible' : 'hidden';
      el.style.transform = `translateY(${y.toFixed(3)}px) scale(${scale.toFixed(4)})`;
    };
    const telop = (name, alpha) => {
      const el = this.telops.find((e) => e.dataset.telop === name);
      if (el) show(el, alpha, 16 * (1 - alpha));
    };
    const envelope = (start, end) => {
      if (time < start) return 0;
      return ease((time - start) / 0.5) * (end === Infinity ? 1 : 1 - ease((time - end + 0.5) / 0.5));
    };
    this.telops.forEach((el) => show(el, 0));
    this.cards.forEach((el) => show(el, 0));
    this.pieces.forEach((el) => { el.style.transform = 'translateX(0px)'; });
    [...this.rows, ...this.badges].forEach((el) => {
      el.style.transform = 'scale(1)';
      el.style.boxShadow = 'none';
    });

    if (this.props.scene === 'title') {
      const approach = k <= 1 ? ease(time / 1.1) : 1;
      this.pieces.forEach((el, i) => {
        el.style.transform = `translateX(${(i ? 1 : -1) * 60 * (1 - approach)}px)`;
      });
      if (k <= 1) telop('intro', 1);
      else {
        telop('slots', envelope(0, 3));
        telop('skill', envelope(3, 8));
        telop('conditions', envelope(8, Infinity));
      }
      return;
    }

    if (k === 1) {
      const index = time < 2.7 ? 0 : time < 5.4 ? 1 : 2;
      const name = ['hp', 'mp', 'fp'][index];
      const start = [0, 2.7, 5.4][index];
      const end = [2.7, 5.4, Infinity][index];
      const amount = envelope(start, end);
      telop(name, amount);
      const targets = name === 'fp' ? this.badges : this.rows.filter((el) => el.dataset.stat === name);
      targets.forEach((el) => {
        // バーの文字はtoken-bodyの余白に収め、FPの丸だけ大きく持ち上げる。
        el.style.transform = `scale(${1 + (name === 'fp' ? 0.12 : 0.04) * amount})`;
        el.style.boxShadow = `0 0 0 ${4 * amount}px white, 0 0 ${24 * amount}px var(--focus-${name})`;
      });
    } else if (k === 2) {
      this.cards.forEach((el, i) => {
        const p = ease((time - i * 0.65) / 0.9);
        show(el, p, 34 * (1 - p));
      });
    } else if (k === 3) {
      const p = ease(time / 1.1);
      this.cards.forEach((el) => show(el, 1 - p, 60 * p));
      telop('carry', ease((time - 0.45) / 0.7));
    }
  }
});
