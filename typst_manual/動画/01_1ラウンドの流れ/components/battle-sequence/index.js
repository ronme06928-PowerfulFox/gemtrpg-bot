// 第4章の作例。k,tから毎回状態を復元し、前の再生や乱数に依存させない。
DECK.define('m-battle-sequence', class extends DECK.MotionElement {
  static props = { scene: { type: 'string', default: 'flow' } };

  mount() {
    this.pieces = [...this.querySelectorAll('.app-piece')];
    this.slots = [...this.querySelectorAll('.app-slot')];
    this.telops = [...this.querySelectorAll('[data-telop]')];
    this.cards = [...this.querySelectorAll('.calc-card')];
    this.numbers = [...this.querySelectorAll('.speed-fly')];
  }

  duration(k) {
    const durations = {
      flow: [0, 0.8, 1, 1, 1],
      speed: [0, 0.8, 1.8, 1.5, 2.8],
      selection: [0, 6.5, 2.5, 0.8, 1],
      power: [0, 0.8, 1.5, 1.5, 1],
      damage: [0, 2.8, 2.2, 1],
      end: [0, 3, 1, 0.8, 1],
    };
    return durations[this.props.scene]?.[k] || 0;
  }

  render(k, t, ctx) {
    const clamp = (v) => Math.max(0, Math.min(1, v));
    const ease = (v) => 1 - (1 - clamp(v)) ** 3;
    const time = t === Infinity || ctx.mode === 'lecture' ? this.duration(k) + 1 : t;
    const progress = (delay = 0, duration = 0.7) => ease((time - delay) / duration);
    const show = (el, alpha, y = 0) => {
      if (!el) return;
      el.style.opacity = alpha.toFixed(4);
      el.style.visibility = alpha > 0.001 ? 'visible' : 'hidden';
      el.style.transform = `translateY(${y.toFixed(3)}px)`;
    };
    const telop = (name, p = progress()) => {
      show(this.telops.find((el) => el.dataset.telop === name), p, 14 * (1 - p));
    };
    const actor = (i, hp, fp) => {
      const piece = this.pieces[i];
      if (!piece) return;
      piece.querySelector('[data-stat="hp"] .app-stat-value').textContent = String(hp);
      const maxHp = i === 0 ? 129 : 30;
      piece.querySelector('.app-bar-fill.hp').style.width = `${hp / maxHp * 100}%`;
      const badge = piece.querySelector('.app-fp');
      badge.textContent = String(fp);
      badge.setAttribute('aria-label', `${piece.querySelector('.app-name').textContent} FP ${fp}`);
    };
    this.telops.forEach((el) => show(el, 0));
    this.cards.forEach((el) => show(el, 0));
    this.numbers.forEach((el) => show(el, 0));
    this.slots.forEach((el) => {
      el.style.visibility = 'visible';
      el.style.opacity = '1';
      el.style.transform = 'translateX(-50%)';
      el.classList.remove('is-committed', 'is-spent');
    });
    this.pieces.forEach((el, i) => actor(i, +el.dataset.hp, +el.dataset.fp));

    switch (this.props.scene) {
      case 'flow': {
        this.querySelectorAll('.flow-card').forEach((el, i) => {
          const p = k > i + 1 ? 1 : k === i + 1 ? progress(0, 0.8) : 0;
          show(el, p, 20 * (1 - p));
        });
        this.querySelectorAll('.flow-link').forEach((el, i) => show(el, k > i + 2 ? 1 : k === i + 2 ? progress(0, 0.8) : 0));
        break;
      }
      case 'speed': {
        this.slots.forEach((el) => {
          const p = k > 3 ? 1 : k === 3 ? progress(0.5, 0.6) : 0;
          el.style.visibility = p > 0 ? 'visible' : 'hidden';
          el.style.opacity = String(p);
        });
        if (k === 1) telop('speed-rule');
        if (k === 2 || k === 3) {
          const move = k === 3 ? progress(0, 1.1) : 0;
          this.cards.forEach((el, i) => show(el, k === 2 ? progress(i * 0.3) : 1 - move));
          this.numbers.forEach((el, i) => {
            const p = k === 2 ? progress(0.7 + i * 0.3) : 1 - progress(0.7, 0.4);
            show(el, p);
            el.style.transform = `translate(${(i ? -149 : -157) * move}px, ${-36 * move}px)`;
          });
          if (k === 3) telop('speed-slot', progress(0.8));
        }
        if (k >= 4) {
          telop('origin-fp');
          actor(0, 110, 1 + Math.round(progress(0.8, 1.4)));
        }
        break;
      }
      case 'selection': {
        const panel = this.querySelector('.mock-declare');
        show(panel, k === 1 ? progress(0, 0.5) : k === 2 ? 1 - progress(0, 0.5) : 0);
        this.querySelectorAll('.declare-chip').forEach((el, i) => {
          el.classList.toggle('done', k > 1 || time > 1 + i * 0.8);
          el.classList.toggle('active', k === 1 && time >= i * 0.8 && time < 1 + i * 0.8);
        });
        const matched = k > 2 || (k === 2 && time >= 1.8);
        this.slots.forEach((el) => el.classList.toggle('is-committed', matched));
        this.querySelectorAll('[data-arrow]').forEach((el, i) => {
          const p = i === 0 ? (k > 1 ? 1 : k === 1 ? progress(4.5, 1.4) : 0)
            : k > 2 ? 1 : k === 2 ? progress(0.2, 1.1) : 0;
          const clip = this.querySelector(`[data-arrow-clip="${el.dataset.arrow}"]`);
          clip.setAttribute('x', String(i === 0 ? 310 : 950 - 640 * p));
          clip.setAttribute('width', String(640 * p));
          el.style.visibility = p > 0 ? 'visible' : 'hidden';
          el.style.stroke = matched ? 'var(--arrow-match)' : 'var(--arrow-pending)';
          el.style.strokeWidth = matched ? '6.8px' : '4.76px';
          el.style.strokeDasharray = matched ? 'none' : '11.9 8.5';
        });
        if (k === 2) telop('match', progress(1.8, 0.5));
        if (k === 3) telop('confirm');
        if (k >= 4) {
          telop('order');
          this.slots[0].style.transform = `translateX(-50%) scale(${1 + 0.1 * progress()})`;
        }
        break;
      }
      case 'power': {
        show(this.querySelector('.mock-resolve'), k > 0 ? (k === 1 ? progress() : 1) : 0);
        ['ally', 'enemy'].forEach((side, i) => {
          const start = i + 2;
          const p = k > start ? 1 : k === start ? progress(0.4, 0.8) : 0;
          show(this.querySelector(`[data-power="${side}"]`), p, 12 * (1 - p));
          show(this.querySelector(`[data-roll="${side}"]`), p, 12 * (1 - p));
        });
        show(this.querySelector('.resolve-headline'), k >= 4 ? progress() : 0, k >= 4 ? 12 * (1 - progress()) : 0);
        break;
      }
      case 'damage': {
        if (k === 1) {
          telop('damage');
          actor(1, 30 - Math.round(9 * progress(0.6, 1.8)), 0);
        } else if (k >= 2) {
          actor(1, 21, 0);
          actor(0, 110, k === 2 ? 2 + Math.round(progress(0.7, 1.1)) : 3);
          telop(k === 2 ? 'victory-fp' : 'spent');
        }
        this.slots.forEach((el) => el.classList.toggle('is-spent', k >= 3));
        break;
      }
      case 'end': {
        const p = k === 1 ? progress(0.8, 1.8) : k > 1 ? 1 : 0;
        actor(0, 110, 3 + Math.round(2 * p));
        actor(1, 21, Math.round(2 * p));
        show(this.querySelector('.fp-breakdown'), k === 2 ? progress() : 0);
        if (k === 1) telop('end-fp');
        if (k === 3) telop('unchanged');
        if (k >= 4) telop('next');
        break;
      }
    }
  }
});
