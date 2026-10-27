// このカット専用の時刻の配線。動きそのものは共通部品へ委ねる。
// DOM順で最後に置く。子部品はsteps=0で自律進行せず、全状態を毎フレーム再計算する。
DECK.define('m-round-cut', class extends DECK.MotionElement {
  static shape = { schema: { type: 'object', required: ['id', 'phase'], properties: { id: { type: 'string' }, phase: { type: 'integer', minimum: 1, maximum: 4 } } } };
  mount() { this.root = this.closest('section'); }
  duration(k) { return k ? DECK.TIMING[`${this.root.id}:${k}`]?.dur || 0 : 0; }
  render(k, t) {
    const root = this.root;
    const q = (s) => root.querySelector(s);
    const all = (s) => [...root.querySelectorAll(s)];
    const show = (el, yes) => { if (el) el.style.visibility = yes ? 'visible' : 'hidden'; };
    const key = `${root.id}:${k}`;
    const marks = DECK.MARKS[key] || [];
    const cues = DECK.AUDIO[key]?.cues || [];
    const cue = (id, fallback = 0) => {
      const phaseIndex = ['phase-start', 'phase-select', 'phase-resolve', 'phase-end'].indexOf(id);
      const index = phaseIndex >= 0 ? phaseIndex : marks.findIndex((x) => x.id === id);
      return index < 0 ? fallback : cues[index] ?? fallback;
    };
    const after = (step, at = 0) => k > step ? Infinity : k < step ? -Infinity : t - at;
    const draw = (el, time, step = 1) => { if (el) el.render(time < 0 ? 0 : step, Math.max(0, time)); };
    const id = this.data.id;
    show(q('.video-opening'), id === 'intro' && k === 0);
    const phases = q('m-phase');
    draw(phases, Infinity, id === 'resolve' && (k === 0 || t < 1.2) ? 2 : this.data.phase);
    all('[data-phase]').forEach((el) => { el.style.outline = 'none'; el.style.outlineOffset = '3px'; });
    if (id === 'slots' && k === 1) {
      ['phase-start', 'phase-select', 'phase-resolve', 'phase-end'].forEach((name, i) => {
        const start = cue(name);
        q(`[data-phase="${i}"]`).style.outline = t >= start && t < start + .65 ? '4px solid var(--emph)' : 'none';
      });
    }
    draw(q('m-background'), Infinity);
    const gm = q('m-gm-bubble');
    const slotStart = id === 'next' ? .5 : 0;
    if (gm) { show(gm, k > 0 && after(1, slotStart) >= 0); draw(gm, after(1, slotStart)); }
    const slotEls = all('.v2-slot');
    slotEls.forEach((el) => {
      show(el, !['slots', 'next'].includes(id) || (k > 0 && after(1, slotStart) >= 0));
      el.classList.toggle('first-slot', id === 'resolve' && !!el.closest('.ally') && k > 0 && t >= .6 && t < 1.2);
    });
    if (id === 'speed') {
      const ds = all('m-dice');
      const times = [after(2, cue('speed-ally') - 2.4), after(2, cue('speed-enemy') - 2.4)];
      ds.forEach((d, i) => { show(d, times[i] >= 0); draw(d, times[i]); });
      slotEls.forEach((el, i) => { show(el, times[i] < 0); el.querySelector('span').textContent = ''; });
      show(q('.v2-speed-formula'), k >= 2);
      all('[data-speed-row]').forEach((row, i) => {
        show(row, times[i] >= 0);
        row.querySelector('[data-speed-face]').textContent = times[i] >= 1.1 ? String(i ? 3 : 4) : '？';
        row.querySelector('[data-speed-total]').textContent = times[i] >= 2.4 ? String(i ? 4 : 6) : '？';
      });
    }
    if (id === 'selection') {
      const arrows = q('.v2-arrows');
      const start = cue('match-arrow') - .5;
      show(arrows, k >= 2 && t >= start);
      arrows.style.opacity = k >= 2 ? String(DECK.prog(t, start, .4)) : '0';
      all('.v2-skill').forEach((el) => show(el, k > 1 || (k === 1 && t >= 1)));
    }
    if (id.startsWith('power-')) {
      const step = id === 'power-ally' ? 2 : 1;
      const time = after(step, cue(id) - 2.4);
      draw(q('m-dice'), time);
      show(q('m-dice [data-die]'), time >= 0);
      show(q('m-dice [data-first-die]'), time >= 0);
      show(q('.v2-compare'), time >= 2.4);
    }
    if (id === 'damage') {
      const hpTime = after(1, cue('enemy-hp') - .8);
      draw(q('m-impact-hp'), hpTime);
      draw(q('m-fp'), after(2, cue('ally-fp')));
      slotEls.forEach((el) => {
        const spent = k >= 3;
        el.classList.toggle('is-spent', spent);
        let label = el.querySelector('.v2-spent');
        if (!label) { label = document.createElement('span'); label.className = 'v2-spent'; label.textContent = '行動済み'; el.append(label); }
        show(label, spent);
      });
    }
    if (id === 'effect-timing') draw(q('m-effect-frame'), k ? t : -Infinity);
    if (id === 'effect-fp') {
      draw(q('m-effect-frame'), k ? t : Infinity, k ? 2 : 1);
      all('m-fp').forEach((el) => draw(el, after(1, cue('end-fp'))));
    }
  }
});
