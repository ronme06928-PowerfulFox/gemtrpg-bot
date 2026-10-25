// 音声のmark時刻と(k,t)から描く。独自タイマー・乱数を使わない。
DECK.define('m-r1-scene', class extends DECK.MotionElement {
  static props = { scene: { type: 'string', default: 'selection' } };

  duration(k) {
    // 音付き字幕の切替も動画に含めるため、段階の全長を描く。
    return DECK.TIMING[`${this.closest('section').id}:${k}`]?.dur || 0;
  }

  render(k, t, ctx) {
    const key = `${this.closest('section').id}:${k}`;
    const time = t === Infinity || ctx.mode === 'lecture' ? this.duration(k) + 3 : t;
    const clamp = (x) => Math.max(0, Math.min(1, x));
    const progress = (at = 0, dur = 0.6) => 1 - (1 - clamp((time - at) / dur)) ** 3;
    const cue = (id, fallback = 0) => {
      const index = (DECK.MARKS[key] || []).findIndex((b) => b.id === id);
      return DECK.AUDIO[key]?.cues[index] ?? fallback;
    };
    const show = (el, alpha) => {
      if (!el) return;
      el.style.opacity = String(alpha);
      el.style.visibility = alpha > 0.001 ? 'visible' : 'hidden';
    };
    const pieces = [...this.querySelectorAll('.app-piece')];
    const slots = [...this.querySelectorAll('.app-slot')];
    const actor = (i, hp, fp) => {
      const p = pieces[i];
      p.querySelector('[data-stat="hp"] .app-stat-value').textContent = String(hp);
      p.querySelector('.app-bar-fill.hp').style.width = `${hp / (i ? 30 : 129) * 100}%`;
      p.querySelector('.app-fp').textContent = String(fp);
      p.querySelector('.app-fp').setAttribute('aria-label', `${i ? '敵' : '味方'} FP ${fp}`);
    };
    actor(0, 129, 0); actor(1, 30, 0);
    slots.forEach((s) => s.classList.remove('is-spent', 'is-committed'));
    this.querySelectorAll('[data-telop]').forEach((e) => show(e, 0));
    const telop = (id, p = progress()) => show(this.querySelector(`[data-telop="${id}"]`), p);
    if (this.props.scene === 'selection') {
      const matchedAt = k === 1 ? Math.max(1.5, cue('match-arrow', 4) - 0.5) : 0;
      const matched = k >= 2 || (k === 1 && time >= matchedAt);
      show(this.querySelector('.mock-declare'), k === 1 ? 1 - progress(Math.max(0.5, matchedAt - 2), 0.5) : 0);
      this.querySelectorAll('.declare-chip').forEach((e, i) => e.classList.toggle('done', k >= 2 || time >= 0.4 * i));
      slots.forEach((s) => s.classList.toggle('is-committed', matched));
      this.querySelectorAll('[data-arrow]').forEach((e, i) => {
        const p = k >= 2 ? 1 : k === 1 ? progress(Math.max(0, matchedAt - (i ? 1 : 2)), 0.9) : 0;
        const clip = this.querySelector(`[data-arrow-clip="${e.dataset.arrow}"]`);
        clip.setAttribute('x', String(i ? 950 - 640 * p : 310));
        clip.setAttribute('width', String(640 * p));
        show(e, p);
        e.style.stroke = matched ? '#ffb020' : '#8a93a3';
        e.style.strokeWidth = matched ? '6.8px' : '4.76px';
        e.style.strokeDasharray = matched ? 'none' : '11.9 8.5';
      });
      if (k === 1) telop('match', progress(matchedAt));
      if (k >= 2) telop('confirm');
    } else if (this.props.scene === 'power') {
      show(this.querySelector('.mock-resolve'), k > 0 ? progress() : 0);
      ['ally', 'enemy'].forEach((side) => {
        const p = k >= 2 ? progress(cue(`power-${side}`), 0.35) : 0;
        show(this.querySelector(`[data-power="${side}"]`), p);
        show(this.querySelector(`[data-roll="${side}"]`), p);
      });
      show(this.querySelector('.resolve-headline'), k >= 2 ? progress(cue('power-enemy') + 0.35, 0.5) : 0);
    } else if (this.props.scene === 'damage') {
      if (k === 1) {
        telop('damage', progress(cue('enemy-hp')));
        actor(1, 30 - Math.round(9 * progress(cue('enemy-hp'), 1.8)), 0);
      } else if (k >= 2) {
        actor(1, 21, 0);
        actor(0, 129, k === 2 ? Math.round(progress(cue('ally-fp'), 1.1)) : 1);
        telop(k === 2 ? 'victory-fp' : 'spent', progress(k === 2 ? cue('ally-fp') : 0));
      }
      slots.forEach((s) => s.classList.toggle('is-spent', k >= 3));
    }
  }
});
