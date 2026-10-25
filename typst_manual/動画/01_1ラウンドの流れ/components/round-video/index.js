// 音声cueと(k,t)から毎回復元する。巻き戻し・書き出しも同じ状態になる。
DECK.define('m-round-video', class extends DECK.MotionElement {
  static props = { scene: { type: 'string', default: 'title' } };

  duration(k) { return DECK.TIMING[`${this.closest('section').id}:${k}`]?.dur || 0; }

  render(k, t, ctx) {
    const key = `${this.closest('section').id}:${k}`;
    const time = t === Infinity || ctx.mode === 'lecture' ? this.duration(k) + 5 : t;
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
      if (!p) return;
      p.querySelector('[data-stat="hp"] .app-stat-value').textContent = String(hp);
      p.querySelector('.app-bar-fill.hp').style.width = `${hp / (i ? 30 : 100) * 100}%`;
      p.querySelector('.app-fp').textContent = String(fp);
      p.querySelector('.app-fp').setAttribute('aria-label', `${i ? '敵' : '味方'} FP ${fp}`);
    };
    actor(0, 100, 0); actor(1, 30, 0);
    slots.forEach((s) => { s.classList.remove('is-spent', 'is-committed'); show(s, 1); });
    this.querySelectorAll('[data-telop], .calc-card, .speed-fly').forEach((e) => show(e, 0));
    const telop = (id, p = progress()) => show(this.querySelector(`[data-telop="${id}"]`), p);
    switch (this.props.scene) {
      case 'title': {
        slots.forEach((s) => show(s, 0));
        pieces.forEach((p, i) => {
          const enter = progress(i * 0.15, 0.8);
          p.style.opacity = String(enter);
          p.style.transform = `translateX(${(i ? 1 : -1) * 70 * (1 - enter)}px)`;
        });
        telop(k <= 1 ? 'intro' : 'conditions');
        show(this.querySelector('.conditions-note'), k >= 2 ? progress(1) : 0);
        break;
      }
      case 'flow': {
        this.querySelectorAll('.flow-card').forEach((e, i) => show(e, k >= 2 ? 1 : k === 1 ? progress(0.5 + i * 1.25) : 0));
        this.querySelectorAll('.flow-link').forEach((e, i) => show(e, k >= 2 ? 1 : k === 1 ? progress(1.75 + i * 1.25) : 0));
        show(this.querySelector('.slot-guide'), k >= 2 ? progress() : 0);
        break;
      }
      case 'speed': {
        slots.forEach((s) => show(s, k >= 3 ? progress(0.65, 0.55) : 0));
        if (k === 1) telop('speed-rule');
        if (k === 2 || k === 3) {
          const move = k === 3 ? progress(0, 1.1) : 0;
          this.querySelectorAll('.calc-card').forEach((e, i) => show(e, k === 2 ? progress(i * 0.25) : 1 - move));
          this.querySelectorAll('.speed-fly').forEach((e, i) => {
            show(e, k === 2 ? progress(cue(i ? 'speed-enemy' : 'speed-ally', i * 2), 0.3) : 1 - progress(0.75, 0.35));
            e.style.transform = `translate(${(i ? -149 : -157) * move}px, ${-36 * move}px)`;
          });
        }
        if (k >= 3) telop('speed-slot', progress(1.1));
        break;
      }
      case 'selection': {
        const matchedAt = k === 2 ? Math.max(0.8, cue('match-arrow', 3) - 0.5) : 0;
        const matched = k >= 3 || (k === 2 && time >= matchedAt);
        show(this.querySelector('.mock-declare'), k === 1 ? progress() : 0);
        this.querySelectorAll('.declare-chip').forEach((e, i) => e.classList.toggle('done', k >= 2 || time >= 0.7 * i));
        slots.forEach((s) => s.classList.toggle('is-committed', matched));
        this.querySelectorAll('[data-arrow]').forEach((e, i) => {
          const p = k >= 3 ? 1 : k === 2 ? progress(Math.max(0, matchedAt - (i ? 0.7 : 1.4)), 0.7) : 0;
          const clip = this.querySelector(`[data-arrow-clip="${e.dataset.arrow}"]`);
          clip.setAttribute('x', String(i ? 950 - 640 * p : 310));
          clip.setAttribute('width', String(640 * p));
          show(e, p);
          e.style.stroke = matched ? '#ffb020' : '#8a93a3';
          e.style.strokeWidth = matched ? '6.8px' : '4.76px';
          e.style.strokeDasharray = matched ? 'none' : '11.9 8.5';
        });
        if (k === 2) telop('match', progress(matchedAt));
        if (k >= 3) telop('confirm');
        break;
      }
      case 'power': {
        show(this.querySelector('.mock-resolve'), k > 0 ? progress() : 0);
        ['ally', 'enemy'].forEach((side) => {
          const p = k >= 2 ? progress(cue(`power-${side}`), 0.35) : 0;
          show(this.querySelector(`[data-power="${side}"]`), p);
          show(this.querySelector(`[data-roll="${side}"]`), p);
        });
        show(this.querySelector('.resolve-headline'), k >= 2 ? progress(cue('power-enemy') + 0.35) : 0);
        break;
      }
      case 'damage': {
        if (k === 1) {
          telop('damage', progress(cue('enemy-hp')));
          actor(1, 30 - Math.round(9 * progress(cue('enemy-hp'), 1.8)), 0);
        } else if (k >= 2) {
          actor(1, 21, 0);
          actor(0, 100, k === 2 ? Math.round(progress(cue('ally-fp'), 1.1)) : 1);
          telop(k === 2 ? 'victory-fp' : 'spent', progress(k === 2 ? cue('ally-fp') : 0));
        }
        slots.forEach((s) => s.classList.toggle('is-spent', k >= 3));
        break;
      }
      case 'end': {
        const p = k === 2 ? progress(cue('end-fp'), 1.3) : k > 2 ? 1 : 0;
        actor(0, 100, 1 + Math.round(2 * p)); actor(1, 21, Math.round(2 * p));
        slots.forEach((s) => { s.classList.toggle('is-spent', k < 4); show(s, k < 4 ? 1 : 0); });
        show(this.querySelector('.effect-card'), k >= 1 && k < 4 ? progress() : 0);
        const frame = this.querySelector('.effect-highlight');
        const timing = this.querySelector('.effect-timing');
        const full = this.querySelector('.effect-text');
        const expand = k >= 2 ? (k === 2 ? progress(0, 0.7) : 1) : 0;
        frame.style.width = `${timing.offsetWidth + (full.offsetWidth - timing.offsetWidth) * expand + 16}px`;
        frame.dataset.extent = expand >= 0.999 ? 'full' : 'timing';
        show(frame, k >= 2 ? 1 : k === 1 ? progress(3.5) : 0);
        if (k === 2) telop('end-fp', progress(cue('end-fp')));
        if (k >= 4) telop('next');
        break;
      }
    }
  }
});
