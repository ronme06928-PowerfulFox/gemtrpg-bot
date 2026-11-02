// 斬撃の試作（案A：SVGを作り込む／案B：Canvasの粒子）。本番の Fx と同じく render(t) の時刻だけで描く。
(function (global) {
  const Fx = global.Fx;
  const NS = 'http://www.w3.org/2000/svg';
  const HIT = 0.7, STOP = 0.78, SWING = 0.5;
  const TONES = { enemy: ['#ffd56b', '#ff9d2e'], ally: ['#ff7373', '#ff2f55'], neutral: ['#e9e7df', '#a9b4c8'] };
  const TIER = { small: 0.7, medium: 1, large: 1.4 };
  const fract = x => x - Math.floor(x);
  const rand = (i, k) => fract(Math.sin(i * 12.9898 + k * 78.233) * 43758.5453);
  const clamp01 = x => Math.max(0, Math.min(1, x));
  const lerp = (a, b, e) => a + (b - a) * e;

  // 刃の通り道：受けた側の箱（W×H）の中で、左下から右上へ振り上げる大きな弧。
  function geometry(W, H) {
    const C = { x: W * 0.62, y: H * 1.25 }, R = H * 0.81;
    const a0 = -2.75, a1 = -0.85, aHit = -1.77;
    const at = (a, r = R) => ({ x: C.x + Math.cos(a) * r, y: C.y + Math.sin(a) * r });
    return { C, R, a0, a1, aHit, at, hit: at(aHit), tangent: aHit + Math.PI / 2 };
  }
  // 刃の頭と尾の角度。ツメで一気に振り抜き、止めの後は尾が頭へ追いついて消える。
  function blade(g, time) {
    const p = clamp01((Math.min(time, HIT) - SWING) / (HIT - SWING));
    const s = p ** 1.6;
    const head = lerp(g.a0, g.a1, s);
    const tailAtHit = g.a1 - 1.45;
    if (time <= STOP) return { head, tail: Math.max(g.a0 - 0.2, head - 1.45 * clamp01(s * 1.4)), visible: time >= SWING };
    const close = Fx.prog(time, STOP, 0.42);
    return { head: g.a1 + 0.06 * close, tail: lerp(tailAtHit, g.a1 + 0.06, close), visible: close < 1 };
  }
  // 三日月：尾（u=0）から頭（u=1）へ。頭は鋭く、頭の手前が一番太い。
  function crescent(g, b, thick, inner = 0.32) {
    const outer = [], inside = [];
    for (let i = 0; i <= 48; i++) {
      const u = i / 48, a = lerp(b.tail, b.head, u);
      const h = thick * Math.pow(u, 1.3) * Math.pow(1 - u, 0.22) * 1.6;
      outer.push(g.at(a, g.R + h));
      inside.push(g.at(a, g.R - h * inner));
    }
    return [...outer, ...inside.reverse()];
  }
  // 切り口：刃と同じ弧に沿って、命中点を中心に両端へ細くなる。
  function cutArc(g, len, w, spread = 1) {
    const span = len / g.R, outer = [], inside = [];
    for (let i = 0; i <= 32; i++) {
      const u = i / 32, a = g.aHit + (u - 0.5) * 2 * span, h = w * Math.sin(Math.PI * u) ** 0.8 * spread;
      outer.push(g.at(a, g.R + h)); inside.push(g.at(a, g.R - h));
    }
    return [...outer, ...inside.reverse()];
  }
  const pathOf = pts => 'M ' + pts.map(p => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' L ') + ' Z';
  function spark(i, g, tau, scale) {
    const spread = (rand(i, 1) - 0.5) * 1.5, back = rand(i, 5) < 0.25 ? Math.PI : 0;
    const angle = g.tangent + spread + back, speed = (260 + rand(i, 2) * 560) * scale;
    const life = 0.28 + rand(i, 3) * 0.4;
    const pos = d => ({ x: g.hit.x + Math.cos(angle) * speed * d, y: g.hit.y + Math.sin(angle) * speed * d + 520 * d * d });
    return { life, a: pos(Math.max(0, tau - 0.03)), b: pos(tau), alpha: clamp01(1 - tau / life), width: 1 + rand(i, 4) * 2.2 * scale };
  }

  function box(root, params, className) {
    const W = Math.max(1, Number(params.width) || 590), H = Math.max(1, Number(params.height) || 420);
    const el = root.ownerDocument.createElement('div');
    el.className = className;
    Object.assign(el.style, { position: 'absolute', left: '0', top: '0', width: `${W}px`, height: `${H}px`,
      transform: `translate(-50%, -50%) scaleX(${params.direction === -1 ? -1 : 1})`, pointerEvents: 'none' });
    root.appendChild(el);
    return { el, W, H };
  }
  let uid = 0;
  const svg = (parent, tag, attrs = {}) => {
    const node = parent.ownerDocument.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    parent.appendChild(node);
    return node;
  };

  // 案A：SVGのまま、芯は白く外ほど色の濃いグラデーション・ぼかしの発光・加算合成・質感・火花を重ねる。
  Fx.define('proto-slash-a', {
    duration: 1.4,
    mount(root, params) {
      const { el, W, H } = box(root, params, 'proto-a');
      this.W = W; this.H = H; this.g = geometry(W, H);
      this.k = TIER[params.tier] || 1; this.tone = TONES[params.tone] || TONES.enemy;
      const id = `pa${++uid}`;
      const s = svg(el, 'svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, style: 'overflow:visible;display:block' });
      const defs = svg(s, 'defs');
      this.grad = svg(defs, 'linearGradient', { id: `${id}g`, gradientUnits: 'userSpaceOnUse' });
      [[0, this.tone[1], 0], [0.45, this.tone[1], 0.75], [0.78, this.tone[0], 1], [0.93, '#fff7df', 1], [1, '#ffffff', 1]]
        .forEach(([o, c, a]) => svg(this.grad, 'stop', { offset: o, 'stop-color': c, 'stop-opacity': a }));
      const glow = svg(defs, 'filter', { id: `${id}f`, x: '-50%', y: '-50%', width: '200%', height: '200%' });
      svg(glow, 'feTurbulence', { type: 'fractalNoise', baseFrequency: '0.035', numOctaves: 2, seed: 7, result: 'n' });
      svg(glow, 'feDisplacementMap', { in: 'SourceGraphic', in2: 'n', scale: 22 * this.k, result: 'd' });
      svg(glow, 'feGaussianBlur', { in: 'd', stdDeviation: 7 * this.k });
      const soft = svg(defs, 'filter', { id: `${id}s`, x: '-50%', y: '-50%', width: '200%', height: '200%' });
      svg(soft, 'feGaussianBlur', { stdDeviation: 3 });
      const flashGrad = svg(defs, 'radialGradient', { id: `${id}r`, gradientUnits: 'userSpaceOnUse', cx: this.g.hit.x, cy: this.g.hit.y, r: W * 0.75 });
      [[0, '#ffffff', 1], [0.25, this.tone[0], 0.55], [1, this.tone[1], 0]].forEach(([o, c, a]) => svg(flashGrad, 'stop', { offset: o, 'stop-color': c, 'stop-opacity': a }));
      this.dim = svg(s, 'rect', { x: -W, y: -H, width: W * 3, height: H * 3, fill: '#05060c' });
      const add = svg(s, 'g', { style: 'mix-blend-mode:screen' });
      this.glint = svg(add, 'path', { fill: '#fff' });
      this.glintHalo = svg(add, 'circle', { r: 1, fill: this.tone[0], filter: `url(#${id}s)` });
      this.glow = svg(add, 'path', { fill: this.tone[0], filter: `url(#${id}f)` });
      this.body = svg(add, 'path', { fill: `url(#${id}g)` });
      this.core = svg(add, 'path', { fill: '#fff' });
      this.cutGlow = svg(add, 'path', { fill: this.tone[0], filter: `url(#${id}s)` });
      this.cut = svg(add, 'path', { fill: '#fff' });
      this.flash = svg(add, 'rect', { x: -W, y: -H, width: W * 3, height: H * 3, fill: `url(#${id}r)` });
      this.ring = svg(add, 'ellipse', { fill: 'none', stroke: '#fff' });
      this.sparks = Array.from({ length: Math.round(26 * this.k) }, (_, i) => svg(add, 'line', { stroke: i % 3 ? this.tone[0] : '#fff', 'stroke-linecap': 'round' }));
    },
    render(t) {
      const time = Math.max(0, Math.min(t, this.duration)), g = this.g, k = this.k;
      const b = blade(g, time);
      // タメ：振り始めの位置に刃の光が細く宿り、受けた側の周りが少し暗くなる。
      const charge = Fx.prog(time, 0.05, SWING - 0.05);
      const start = g.at(g.a0 + 0.12);
      const r = (3 + 11 * charge) * k * (time < SWING + 0.05 ? 1 : 0);
      const spin = time * 2.4;
      const star = [0, 1, 2, 3, 4, 5, 6, 7].map(i => {
        const a = spin + i * Math.PI / 4, len = i % 2 ? r * 0.22 : r * (i % 4 ? 0.7 : 1.4);
        return { x: start.x + Math.cos(a) * len, y: start.y + Math.sin(a) * len };
      });
      this.glint.setAttribute('d', r > 0.5 ? pathOf(star) : '');
      this.glintHalo.setAttribute('cx', start.x); this.glintHalo.setAttribute('cy', start.y);
      this.glintHalo.setAttribute('r', r * 1.6); this.glintHalo.style.opacity = String(r > 0.5 ? 0.8 : 0);
      this.dim.style.opacity = String(0.28 * charge * (1 - Fx.prog(time, HIT, 0.25)));
      // ツメと止め：三日月が走り抜け、命中の2コマは真っ白、止めの間は姿勢を保つ。
      const white = time >= HIT && time < HIT + 0.045;
      const thick = 13 * k * (white ? 1.25 : 1);
      if (b.visible && b.head - b.tail > 0.01) {
        const shape = pathOf(crescent(g, b, thick));
        this.body.setAttribute('d', shape); this.glow.setAttribute('d', pathOf(crescent(g, b, thick * 1.6, 0.6)));
        this.core.setAttribute('d', pathOf(crescent(g, b, thick * (white ? 1 : 0.38), white ? 0.32 : 0.1)));
        const tail = g.at(b.tail), head = g.at(b.head);
        for (const [n, v] of Object.entries({ x1: tail.x, y1: tail.y, x2: head.x, y2: head.y })) this.grad.setAttribute(n, v);
        const fade = time > STOP ? 1 - Fx.prog(time, STOP + 0.1, 0.32) : 1;
        this.body.style.opacity = String(fade); this.core.style.opacity = String(fade);
        this.glow.style.opacity = String(0.9 * fade);
      } else for (const n of [this.body, this.glow, this.core]) n.setAttribute('d', '');
      // 切り口：命中点を通る細い光の線が残り、細くなって消える。
      const cutAge = time - HIT;
      const w = cutAge < 0 ? 0 : 5 * k * Fx.prog(cutAge, 0, 0.04) * (1 - Fx.prog(cutAge, 0.08, 0.5));
      const len = this.W * (0.42 + 0.08 * Fx.prog(cutAge, 0, 0.4));
      this.cut.setAttribute('d', w > 0.05 ? pathOf(cutArc(g, len, w)) : '');
      this.cutGlow.setAttribute('d', w > 0.05 ? pathOf(cutArc(g, len, w, 3)) : '');
      // 命中の閃光と、命中点から広がる輪。
      this.flash.style.opacity = String(cutAge < 0 ? 0 : 1 - Fx.prog(cutAge, 0, 0.09));
      const ringAge = clamp01((time - HIT) / 0.35);
      this.ring.setAttribute('cx', g.hit.x); this.ring.setAttribute('cy', g.hit.y);
      this.ring.setAttribute('rx', 10 + 90 * k * ringAge); this.ring.setAttribute('ry', 4 + 30 * k * ringAge);
      this.ring.setAttribute('transform', `rotate(${g.tangent * 180 / Math.PI} ${g.hit.x} ${g.hit.y})`);
      this.ring.setAttribute('stroke-width', 3 * (1 - ringAge));
      this.ring.style.opacity = String(time < HIT ? 0 : 1 - ringAge);
      // 火花：斬った向きへ飛び、落ちながら消える。
      const tau = time - HIT - 0.02;
      this.sparks.forEach((line, i) => {
        const sp = spark(i, g, tau, k);
        const show = tau > 0 && tau < sp.life;
        line.setAttribute('x1', sp.a.x); line.setAttribute('y1', sp.a.y); line.setAttribute('x2', sp.b.x); line.setAttribute('y2', sp.b.y);
        line.setAttribute('stroke-width', sp.width); line.style.opacity = String(show ? sp.alpha : 0);
      });
    },
  });

  // 案B：Canvasに加算合成で描く。速さの線・発光・放射の光・数百の火花・残り火・煙。
  Fx.define('proto-slash-b', {
    duration: 1.4,
    mount(root, params) {
      const { el, W, H } = box(root, params, 'proto-b');
      this.W = W; this.H = H; this.g = geometry(W, H);
      this.k = TIER[params.tier] || 1; this.tone = TONES[params.tone] || TONES.enemy;
      const pad = 0.5, dpr = Math.min(2, global.devicePixelRatio || 1);
      this.pad = pad;
      this.canvas = root.ownerDocument.createElement('canvas');
      this.canvas.width = Math.round(W * (1 + pad * 2) * dpr); this.canvas.height = Math.round(H * (1 + pad * 2) * dpr);
      Object.assign(this.canvas.style, { position: 'absolute', left: `${-W * pad}px`, top: `${-H * pad}px`,
        width: `${W * (1 + pad * 2)}px`, height: `${H * (1 + pad * 2)}px` });
      el.appendChild(this.canvas);
      this.ctx = this.canvas.getContext('2d');
      this.dpr = dpr;
    },
    render(t) {
      const time = Math.max(0, Math.min(t, this.duration)), g = this.g, k = this.k, ctx = this.ctx;
      const [c0, c1] = this.tone;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      ctx.setTransform(this.dpr, 0, 0, this.dpr, this.W * this.pad * this.dpr, this.H * this.pad * this.dpr);
      const poly = pts => { ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.closePath(); };
      // タメ：暗がりと、刃の光の集まり。
      const charge = Fx.prog(time, 0.05, SWING - 0.05);
      ctx.globalCompositeOperation = 'source-over';
      ctx.fillStyle = `rgba(4,5,12,${0.3 * charge * (1 - Fx.prog(time, HIT, 0.25))})`;
      ctx.fillRect(-this.W, -this.H, this.W * 3, this.H * 3);
      ctx.globalCompositeOperation = 'lighter';
      if (time < SWING + 0.04) {
        const start = g.at(g.a0 + 0.12);
        for (let i = 0; i < 18; i++) {
          const a = rand(i, 9) * Math.PI * 2, dist = (1 - charge) * (40 + rand(i, 8) * 60) * k;
          ctx.fillStyle = `rgba(255,240,200,${0.7 * charge})`;
          ctx.beginPath(); ctx.arc(start.x + Math.cos(a) * dist, start.y + Math.sin(a) * dist, 1.2 + rand(i, 7) * 1.5, 0, Math.PI * 2); ctx.fill();
        }
        const glow = ctx.createRadialGradient(start.x, start.y, 0, start.x, start.y, 34 * k * charge + 1);
        glow.addColorStop(0, 'rgba(255,255,255,0.9)'); glow.addColorStop(0.4, c0 + 'aa'); glow.addColorStop(1, c1 + '00');
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(start.x, start.y, 34 * k * charge + 1, 0, Math.PI * 2); ctx.fill();
      }
      // ツメ：過去の頭の位置を何本も細く重ねた速さの線と、発光する三日月。
      const b = blade(g, time);
      const white = time >= HIT && time < HIT + 0.045;
      if (b.visible && b.head - b.tail > 0.01) {
        const fade = time > STOP ? 1 - Fx.prog(time, STOP + 0.1, 0.32) : 1;
        for (let j = 0; j < 14; j++) {
          const r = g.R + (rand(j, 11) - 0.3) * 26 * k, from = lerp(b.tail, b.head, 0.15 + rand(j, 12) * 0.3);
          ctx.strokeStyle = `rgba(255,${200 + j * 3},${140 + j * 6},${0.18 * fade})`;
          ctx.lineWidth = 0.8 + rand(j, 13) * 1.6;
          ctx.beginPath(); ctx.arc(g.C.x, g.C.y, r, from, b.head - 0.02); ctx.stroke();
        }
        const thick = 13 * k * (white ? 1.25 : 1);
        ctx.save(); ctx.filter = `blur(${9 * k}px)`; ctx.globalAlpha = 0.85 * fade;
        ctx.fillStyle = c0; poly(crescent(g, b, thick * 1.7, 0.7)); ctx.fill(); ctx.restore();
        const tail = g.at(b.tail), head = g.at(b.head);
        const grad = ctx.createLinearGradient(tail.x, tail.y, head.x, head.y);
        grad.addColorStop(0, c1 + '00'); grad.addColorStop(0.45, c1 + 'bb'); grad.addColorStop(0.8, c0); grad.addColorStop(0.94, '#fff7df'); grad.addColorStop(1, '#ffffff');
        ctx.globalAlpha = fade; ctx.fillStyle = grad; poly(crescent(g, b, thick)); ctx.fill();
        ctx.fillStyle = '#ffffff'; poly(crescent(g, b, thick * (white ? 1 : 0.36), white ? 0.32 : 0.1)); ctx.fill();
        ctx.globalAlpha = 1;
      }
      const age = time - HIT;
      if (age >= 0) {
        const hx = g.hit.x, hy = g.hit.y;
        // 命中：大きな閃光と、放射の光の筋。
        const flash = 1 - Fx.prog(age, 0, 0.1);
        if (flash > 0) {
          const rad = ctx.createRadialGradient(hx, hy, 0, hx, hy, this.W * 0.8);
          rad.addColorStop(0, `rgba(255,255,255,${flash})`); rad.addColorStop(0.2, c0 + Math.round(150 * flash).toString(16).padStart(2, '0')); rad.addColorStop(1, c1 + '00');
          ctx.fillStyle = rad; ctx.fillRect(-this.W, -this.H, this.W * 3, this.H * 3);
        }
        const burst = clamp01(age / 0.16);
        if (burst < 1) for (let i = 0; i < 11; i++) {
          const a = rand(i, 21) * Math.PI * 2, len = (60 + rand(i, 22) * 150) * k * (0.4 + burst), w = (3 + rand(i, 23) * 4) * (1 - burst);
          ctx.fillStyle = `rgba(255,250,230,${0.9 * (1 - burst)})`;
          ctx.beginPath(); ctx.moveTo(hx + Math.cos(a + 1.57) * w, hy + Math.sin(a + 1.57) * w);
          ctx.lineTo(hx + Math.cos(a) * len, hy + Math.sin(a) * len); ctx.lineTo(hx - Math.cos(a + 1.57) * w, hy - Math.sin(a + 1.57) * w); ctx.fill();
        }
        // 切り口。
        const w = 5 * k * Fx.prog(age, 0, 0.04) * (1 - Fx.prog(age, 0.08, 0.5));
        if (w > 0.05) {
          const len = this.W * (0.42 + 0.08 * Fx.prog(age, 0, 0.4));
          ctx.save(); ctx.shadowColor = c0; ctx.shadowBlur = 18 * k; ctx.fillStyle = '#fff';
          poly(cutArc(g, len, w));
          ctx.fill(); ctx.restore();
        }
        // 火花（数を多く、筋を長く）と、ゆっくり漂う残り火。
        const tau = age - 0.02;
        ctx.lineCap = 'round';
        for (let i = 0; i < Math.round(55 * k); i++) {
          const sp = spark(i, g, tau, k);
          if (tau <= 0 || tau >= sp.life) continue;
          const heat = sp.alpha;
          ctx.strokeStyle = heat > 0.6 ? `rgba(255,255,240,${heat})` : i % 2 ? c0 : c1;
          ctx.globalAlpha = Math.min(1, heat * 1.3);
          ctx.lineWidth = sp.width * (0.5 + heat);
          ctx.beginPath(); ctx.moveTo(sp.a.x, sp.a.y); ctx.lineTo(sp.b.x, sp.b.y); ctx.stroke();
        }
        for (let i = 0; i < Math.round(16 * k); i++) {
          const life = 0.45 + rand(i, 31) * 0.2, e = tau / life;
          if (tau <= 0 || e >= 1) continue;
          const a = g.tangent + (rand(i, 32) - 0.5) * 2.4, v = (40 + rand(i, 33) * 120) * k;
          const x = hx + Math.cos(a) * v * tau + Math.sin(tau * 9 + i) * 6, y = hy + Math.sin(a) * v * tau - 40 * tau;
          ctx.globalAlpha = (1 - e) * (0.6 + 0.4 * Math.sin(tau * 40 + i * 3));
          ctx.fillStyle = i % 2 ? c0 : '#fff2c8';
          ctx.beginPath(); ctx.arc(x, y, 1.4 + rand(i, 34) * 1.6, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = 1;
        // 煙：加算をやめて暗い靄をうっすら残す。
        ctx.globalCompositeOperation = 'source-over';
        for (let i = 0; i < 8; i++) {
          const e = clamp01((age - 0.06) / 0.62);
          if (e <= 0 || e >= 1) continue;
          const a = g.tangent + (rand(i, 41) - 0.5) * 2, d = (20 + rand(i, 42) * 70) * k * e;
          const x = hx + Math.cos(a) * d, y = hy + Math.sin(a) * d - 25 * e, rr = (18 + rand(i, 43) * 26) * k * (0.6 + e);
          const fog = ctx.createRadialGradient(x, y, 0, x, y, rr);
          fog.addColorStop(0, `rgba(40,36,48,${0.32 * (1 - e)})`); fog.addColorStop(1, 'rgba(40,36,48,0)');
          ctx.fillStyle = fog; ctx.beginPath(); ctx.arc(x, y, rr, 0, Math.PI * 2); ctx.fill();
        }
      }
      ctx.globalCompositeOperation = 'source-over';
    },
  });
// 打撃・貫通は本番と同じ道具・配分の見本。別実装を増やさず、並べたときの一致も確認する。
  for (const kind of ['strike', 'pierce']) {
    Fx.define(`proto-${kind}-b`, {
      duration: 1.4,
      mount(root, params) { Fx.get(`attack-${kind}`).mount.call(this, root, params); },
      render(t) { Fx.get(`attack-${kind}`).render.call(this, t); },
    });
  }
})(window);
