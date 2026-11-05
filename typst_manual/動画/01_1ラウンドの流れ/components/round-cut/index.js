// 既存の2場面を重ねる。別タイマーや画像の写しは使わず、段階の時刻で描く。
DECK.videoFade = (root,k,t) => {
  if(!root.classList.contains('active'))return;
  const duration=root.id==='s-credits'?.8:['s-names','s-return'].includes(root.id)?.5:.3;
  const previous=root.previousElementSibling;
  if(k>1||!previous||(k===1&&t>=duration))return;
  const director=previous.querySelector('m-round-cut,m-resolve-panel');
  if(director)director.render(director.steps,Infinity);
  previous.style.visibility='visible';previous.style.opacity='1';previous.style.zIndex='1';
  root.style.opacity=String(k===0?0:DECK.prog(t,0,duration));root.style.zIndex='2';
};
DECK.videoObjectFade=(root,k,t,selector,start=0,at=0,end=true)=>{
  start=Math.max(1,start);
  const enter=k>start?1:k<start?0:DECK.prog(t,at,.3);
  const last=root.querySelector('m-round-cut,m-resolve-panel').steps;
  const dur=DECK.TIMING[`${root.id}:${k}`]?.dur||0;
  const exit=end&&k===last?1-DECK.prog(t,dur-.3,.3):1;
  root.querySelectorAll(selector).forEach(el=>el.style.opacity=String(enter*exit));
};
function updateSpeaker(){
    const cap=document.querySelector('#deck-cap');if(!cap)return;
    const novice=!!cap.querySelector('.novice');cap.dataset.speaker=novice?'novice':'expert';
    const badge=cap.querySelector('.r25-speaker');const name=novice?'聞き手 つむぎ':'説明役 ひまり';
    if(badge?.textContent===name)return;
    cap.querySelector('.r25-speaker')?.remove();
    if(cap.querySelector('.cap-line')){const e=document.createElement('span');e.className='r25-speaker';e.textContent=name;cap.prepend(e);}
  }
// このカット専用の時刻の配線。動きそのものは共通部品へ委ねる。
// DOM順で最後に置く。子部品はsteps=0で自律進行せず、全状態を毎フレーム再計算する。
DECK.define('m-round-cut', class extends DECK.MotionElement {
  static shape = { schema: { type: 'object', required: ['id', 'phase', 'wordLead'], properties: { id: { type: 'string' }, phase: { type: 'integer', minimum: 1, maximum: 4 }, wordLead: { type: 'number', minimum: 0 } } } };
  mount() {
    this.root = this.closest('section');
    if (this.root.id === 's-intro') {
      DECK.T.slide=0;
      document.addEventListener('deck:ready', () => DECK.captions(true), { once: true });
      document.addEventListener('deck:captions', updateSpeaker);
      new MutationObserver(updateSpeaker).observe(document.body,{subtree:true,childList:true});
    }
  }
  duration(k) { return DECK.TIMING[`${this.root.id}:${k}`]?.dur || 0; }
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
      return (index < 0 ? fallback : cues[index] ?? fallback)+(DECK.TIMING[key]?.lead||0);
    };
    const after = (step, at = 0) => k > step ? Infinity : k < step ? -Infinity : t - at;
    const draw = (el, time, step = 1) => { if (el) el.render(time < 0 ? 0 : step, Math.max(0, time)); };
    const id = this.data.id;
    const word = (step, index) => DECK.AUDIO[`${root.id}:${step}`].cues[index] + this.data.wordLead+(DECK.TIMING[`${root.id}:${step}`]?.lead||0);
    const light = (name, step, start, end) => all(`[data-spoken="${name}"]`).forEach((el) => el.classList.toggle('spoken', k === step && t >= start && t < end));
    all('[data-spoken]').forEach((el) => el.classList.remove('spoken'));
    show(q('.video-opening'), id === 'intro' && (k <= 1 || (k===2&&t<.8)));
    if(q('.video-opening'))q('.video-opening').style.opacity=k===2?String(1-DECK.prog(t,0,.8)):'1';
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
    const slotStart = 0;
    const slotStep=id==='slots'?2:0;
    if (gm) { show(gm, after(slotStep, slotStart) >= 0); draw(gm, Infinity); }
    const slotEls = all('.v2-slot');
    slotEls.forEach((el) => {
      show(el, !['slots', 'next'].includes(id) || after(slotStep, slotStart) >= 0);
      el.classList.toggle('first-slot', id === 'resolve' && !!el.closest('.ally') && k === 1 && t >= .6 && t < 1.2);
    });
    if (id === 'speed') {
      const ds = all('m-dice');
      const times = k===1?[t-.3,t-.7]:k===0?[-Infinity,-Infinity]:[Infinity,Infinity];
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
      const matched = k >= 5;
      const color = matched ? '#ffb020' : '#8a93a3';
      const count = k > 2 ? 2 : k === 2 ? (t >= 1.6 ? 2 : t >= .4 ? 1 : 0) : 0;
      show(arrows, count > 0);
      arrows.style.opacity = matched ? '.98' : '.9';
      arrows.style.stroke = color;
      arrows.style.strokeWidth = matched ? '6.8' : '4.76';
      arrows.style.strokeDasharray = matched ? 'none' : '11.9 8.5';
      arrows.querySelector('marker path').setAttribute('fill', color);
      [...arrows.querySelectorAll(':scope > path')].forEach((el, i) => {show(el,i<count);el.style.opacity=k===2?String(DECK.prog(t,i?1.6:.4,.3)):'1';});
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
    if (id === 'effect-timing') draw(q('m-effect-frame'), k>2?Infinity:k===2?3.5+Math.min(t,.3)*2:-Infinity);
    if (id === 'effect-fp') {
      draw(q('m-effect-frame'), k === 1 ? t : Infinity, k ? 2 : 1);
      all('m-fp').forEach((el) => draw(el, after(1)));
    }
    DECK.videoObjectFade(root,k,t,'.v2-slot',slotStep,0,!['resolve'].includes(id));
    DECK.videoObjectFade(root,k,t,'m-gm-bubble',slotStep);
    DECK.videoObjectFade(root,k,t,'.v2-skill',2);
    DECK.videoObjectFade(root,k,t,'.v3-win-fp,m-effect-frame',0);
    if(id==='speed'){
      DECK.videoObjectFade(root,k,t,'.v2-speed-formula',0,1.4);
      all('m-dice').forEach((el,i)=>{
        const time=k===1?t-.3-i*.4:k===0?-Infinity:Infinity;
        el.querySelector('[data-dice-target]').style.opacity=String(time>=2.4?DECK.prog(time,2.4,.3):1);
      });
    }
    DECK.videoFade(root,k,t);
  }
});
