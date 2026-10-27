// このカット専用の時刻の配線。動きそのものは共通部品へ委ねる。
// DOM順で最後に置く。子部品はsteps=0で自律進行せず、全状態を毎フレーム再計算する。
DECK.define('m-round-cut', class extends DECK.MotionElement {
  static shape = { schema: { type: 'object', required: ['id', 'phase', 'wordLead'], properties: { id: { type: 'string' }, phase: { type: 'integer', minimum: 1, maximum: 4 }, wordLead: { type: 'number', minimum: 0 } } } };
  mount() {
    this.root = this.closest('section');
    if (this.root.id === 's-intro') document.addEventListener('deck:ready', () => DECK.captions(true), { once: true });
  }
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
    const word = (step, index) => DECK.AUDIO[`${root.id}:${step}`].cues[index] + this.data.wordLead;
    const light = (name, step, start, end) => all(`[data-spoken="${name}"]`).forEach((el) => el.classList.toggle('spoken', k === step && t >= start && t < end));
    all('[data-spoken]').forEach((el) => el.classList.remove('spoken'));
    if (id === 'intro') {
      light('full', 3, word(3, 0), word(3, 1));
      light('fp-zero', 3, word(3, 1), word(3, 1) + 1);
    }
    show(q('.video-opening'), id === 'intro' && k <= 1);
    const phases = q('m-phase');
    draw(phases, Infinity, id === 'resolve' && (k === 0 || (k === 1 && t < 1.2)) ? 2 : this.data.phase);
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
      el.classList.toggle('first-slot', id === 'resolve' && !!el.closest('.ally') && k === 1 && t >= .6 && t < 1.2);
    });
    if (id === 'speed') {
      const ds = all('m-dice');
      const times = [after(1, word(1, 0)), after(1, word(1, 0) + .4)];
      ds.forEach((d, i) => { show(d, times[i] >= 0); draw(d, times[i]); });
      slotEls.forEach((el, i) => { show(el, times[i] < 0); el.querySelector('span').textContent = ''; });
      show(q('.v2-speed-formula'), times[0] >= 1.1);
      all('[data-speed-row]').forEach((row, i) => {
        row.style.display = times[i] >= 1.1 ? '' : 'none';
        row.querySelector('[data-speed-face]').textContent = times[i] >= 1.1 ? String(i ? 3 : 4) : '？';
        row.querySelector('[data-speed-total]').textContent = times[i] >= 1.1 ? String(i ? 4 : 6) : '？';
      });
      light('speed-correction', 1, word(1, 1), word(1, 1) + 1.2);
    }
    if (id === 'selection') {
      const arrows = q('.v2-arrows');
      const start = cue('match-arrow') - .5;
      show(arrows, k >= 4 && t >= start);
      arrows.style.opacity = k >= 4 ? String(DECK.prog(t, start, .4)) : '0';
      all('.v2-skill').forEach((el) => show(el, k >= 2));
    }
    if (id.startsWith('power-')) {
      const ally = id === 'power-ally';
      const time = ally ? after(2, word(2, 3)) : after(1);
      draw(q('m-dice'), time);
      show(q('m-dice [data-die]'), time >= 0);
      show(q('m-dice [data-first-die]'), time >= 0);
      show(q('[data-first-label]'), time < 2.4);
      q('[data-equals]').style.display = time >= 2.4 ? '' : 'none';
      q('[data-dice-total]').style.display = time >= 2.4 ? '' : 'none';
      if (time < 2.4) { q('[data-dice-target]').textContent = ally ? '1d3' : '1d2'; q('[data-dice-target]').style.opacity = '1'; }
      if (ally) ['power-base', 'power-die', 'power-physical'].forEach((name, i) => light(name, 2, word(2, i), word(2, i + 1)));
      show(q('.v2-compare'), !ally && k === 2 && t >= cue(id));
    }
    if (id === 'damage') {
      const hpTime = after(2, cue('enemy-hp') - .8);
      draw(q('m-impact-hp'), hpTime);
      draw(q('m-fp'), after(3, cue('ally-fp')));
      slotEls.forEach((el) => {
        const spent = k >= 4;
        el.classList.toggle('is-spent', spent);
        let label = el.querySelector('.v2-spent');
        if (!label) { label = document.createElement('span'); label.className = 'v2-spent'; label.textContent = '行動済み'; el.append(label); }
        show(label, spent);
      });
    }
    if (id === 'effect-timing') draw(q('m-effect-frame'), k >= 2 ? t : -Infinity);
    if (id === 'effect-fp') {
      draw(q('m-effect-frame'), k === 1 ? t : Infinity, k ? 2 : 1);
      all('m-fp').forEach((el) => draw(el, after(1, cue('end-fp'))));
    }
  }
});
