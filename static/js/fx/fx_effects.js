// 各演出の定義。mount で root の中に自分の要素を作り、render(t) は t だけから見た目を決める。
// アプリの状態・タイマー・乱数・CSSアニメーションは使わない（計画52 §4.2・§4.4）。
(function (global) {
  const Fx = global.Fx;

  // ダメージ・回復などの数値が浮かんで消える。params: text, tone（色のクラス）, level
  Fx.define('float-text', {
    duration: 3,
    mount(root, params) {
      this.level = params.level;
      this.el = root.ownerDocument.createElement('div');
      this.el.className = `fx-float-text ${params.tone || ''}`.trim();
      this.el.textContent = params.text;
      this.el.setAttribute('data-readable', '');
      root.appendChild(this.el);
    },
    render(t) {
      const style = this.el.style;
      if (this.level === 'light') {
        style.opacity = String(Fx.stillOpacity(t, this.duration));
        style.transform = 'translate(-50%, -50%)';
        return;
      }
      const rich = this.level === 'rich';
      const p = Fx.prog(t, 0, this.duration);
      const time = Math.min(t, this.duration);
      // 派手は出だしの0.3秒だけ左右に揺れる。
      const shake = rich ? Math.sin(time * 60) * 6 * (1 - Fx.prog(time, 0, 0.3)) : 0;
      const scale = rich ? Fx.lerp(1.5, 0.7, p) : Fx.lerp(1.2, 0.6, p);
      style.opacity = String(1 - p);
      style.transform = `translate(-50%, ${Fx.lerp(-50, -150, p)}%) translateX(${shake}px) scale(${scale})`;
    },
  });

  // ラウンド開始のバナー。params: text, level
  Fx.define('round-banner', {
    duration: 1.8,
    mount(root, params) {
      const doc = root.ownerDocument;
      this.level = params.level;
      this.el = doc.createElement('div');
      this.el.className = 'fx-round-banner';
      const text = doc.createElement('div');
      text.className = 'round-banner-text';
      text.textContent = params.text;
      text.setAttribute('data-readable', '');
      this.el.appendChild(text);
      root.appendChild(this.el);
    },
    render(t) {
      const style = this.el.style;
      if (this.level === 'light') {
        style.opacity = String(Fx.stillOpacity(t, this.duration));
        style.transform = 'scale(1)';
        return;
      }
      // 0.216秒で大きく出て、0.36秒で落ち着き、1.404秒から消える。
      const overshoot = this.level === 'rich' ? 1.15 : 1.08;
      const appear = Fx.prog(t, 0, 0.216);
      const settle = Fx.prog(t, 0.216, 0.144);
      const leave = Fx.prog(t, 1.404, 0.396);
      let scale;
      if (t < 0.216) scale = Fx.lerp(0.7, overshoot, appear);
      else if (t < 1.404) scale = Fx.lerp(overshoot, 1, settle);
      else scale = Fx.lerp(1, 1.05, leave);
      style.opacity = String(appear * (1 - leave));
      style.transform = `scale(${scale})`;
    },
  });
  function element(root, tag, className, text) {
    const el = root.ownerDocument.createElement(tag);
    el.className = className;
    if (text !== undefined) {
      el.textContent = text;
      el.setAttribute('data-readable', '');
    }
    root.appendChild(el);
    return el;
  }

  // 候補と切替時刻を先に決める。描画の呼出し順は列に影響しない。
  function mountRoll(root, params, stop, chat) {
    this.level = params.level;
    this.text = String(params.text);
    this.stop = stop;
    this.el = element(root, chat ? 'span' : 'div', chat ? 'fx-chat-dice' : 'fx-power-roll');
    this.number = element(this.el, 'span', chat ? 'fx-chat-total' : 'fx-power-number', this.text);
    if (!chat) {
      this.el.style.width = `${params.width || 80}px`;
      this.el.style.height = `${params.height || 50}px`;
    }
    const final = Number(params.text), radius = Math.max(1, Math.ceil(Math.abs(final) * 0.4));
    const fallbackMin = Math.max(0, Math.floor(final - radius));
    const range = params.range || { min: fallbackMin, max: Math.max(fallbackMin + 1, Math.ceil(final + radius)) };
    const min = Math.ceil(range.min), max = Math.floor(range.max);
    const excludes = Number.isInteger(final) && final >= min && final <= max;
    const count = Number.isFinite(final) ? Math.max(0, max - min + 1 - (excludes ? 1 : 0)) : 0;
    this.rolls = [];
    let at = 0, previous = -1;
    for (let i = 0; at < stop; i++) {
      let index = count ? (Math.abs(Math.trunc(final)) * 7 + i * 11) % count : -1;
      if (count > 1 && index === previous) index = (index + 1) % count;
      let value = min + index;
      if (excludes && value >= final) value++;
      this.rolls.push({ at, text: count ? String(value) : '…' });
      previous = index;
      at += 0.03 + 0.07 * at / stop;
    }
    this.center = chat ? 'translate(0, 0)' : 'translate(-50%, -50%)';
  }
  function renderRoll(t) {
    const time = Math.max(0, Math.min(t, this.duration));
    const rolling = this.level !== 'light' && time < this.stop;
    const current = this.rolls.filter(row => row.at <= time).at(-1);
    this.number.textContent = rolling ? current.text : this.text;
    this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
    const settle = this.level === 'light' || rolling ? 1 : Fx.lerp(1.15, 1, Fx.prog(time, this.stop, 0.18));
    this.el.style.transform = `${this.center} scale(${settle})`;
    this.number.style.filter = this.level === 'light' || rolling ? 'brightness(1)'
      : `brightness(${Fx.lerp(this.level === 'rich' ? 2.2 : 1.8, 1, Fx.prog(time, this.stop, 0.18))})`;
  }
  Fx.define('power-roll', {
    duration: 1.4,
    mount(root, params) { mountRoll.call(this, root, params, 1, false); },
    render: renderRoll,
  });

  Fx.define('clash-flash', {
    duration: 0.6,
    mount(root, params) {
      this.level = params.level;
      this.el = element(root, 'div', `fx-clash-flash ${params.level}`);
    },
    render(t) {
      const p = Fx.prog(t, 0, this.duration);
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = this.level === 'light' ? 'translate(-50%, -50%)'
        : `translate(-50%, -50%) scale(${Fx.lerp(this.level === 'rich' ? 0.3 : 0.6, 1.8, p)}) rotate(${Fx.lerp(this.level === 'rich' ? -18 : -6, 0, p)}deg)`;
    },
  });

  Fx.define('clash-shade', {
    duration: 0.8,
    mount(root, params) {
      this.level = params.level;
      this.el = element(root, 'div', `fx-clash-shade ${params.winner ? 'winner' : 'loser'} ${params.level}`);
      this.el.style.width = `${params.width}px`;
      this.el.style.height = `${params.height}px`;
    },
    render(t) {
      const p = Fx.prog(t, 0, this.duration);
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = this.level === 'light' ? 'translate(-50%, -50%)'
        : `translate(-50%, -50%) translateX(${Math.sin(Math.min(t, this.duration) * 35) * (1 - p) * (this.level === 'rich' ? 3 : 1)}px)`;
    },
  });

  Fx.define('attack-flash', {
    duration: 0.8,
    mount(root, params) {
      this.level = params.level;
      this.direction = params.direction === -1 ? -1 : 1;
      this.el = element(root, 'div', `fx-attack-flash ${params.level} ${params.tone || 'enemy'}`);
      if (params.mode === 'draw') this.el.style.width = '80px';
    },
    render(t) {
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = this.level === 'light' ? 'translate(-50%, -50%)'
        : `translate(-50%, -50%) rotate(${-28 * this.direction}deg) scaleX(${Fx.lerp(this.level === 'rich' ? 0.1 : 0.3, 1.6, Fx.prog(t, 0, this.duration))})`;
    },
  });

  // 対象DOMを持つ演出だけの復元情報。入場のtransformと紋章には触れない。
  function rememberTargets(targets, properties) {
    return [...new Set((targets || []).filter(Boolean))].map(el => ({ el,
      original: Object.fromEntries(properties.map(key => [key, el.style[key] || ''])) }));
  }
  function restoreTargets(records) {
    for (const { el, original } of records) Object.assign(el.style, original);
  }
  function translated(original, x, y) {
    if (!original || original === 'none') return `${x}px ${y}px`;
    const [bx, by = '0px', bz] = original.split(/\s+/);
    return `calc(${bx} + ${x}px) calc(${by} + ${y}px)${bz ? ` ${bz}` : ''}`;
  }
  Fx.define('hit-react', {
    duration: 0.3,
    mount(root, params) {
      this.level = params.level;
      this.direction = params.direction === -1 ? -1 : 1;
      this.targets = rememberTargets(params.targets, ['translate', 'filter']);
    },
    render(t) {
      if (this.level === 'light' || t <= 0 || t >= this.duration) { restoreTargets(this.targets); return; }
      const strength = Fx.prog(t, 0, 0.025) * (1 - Fx.prog(t, 0.025, 0.275));
      for (const { el, original } of this.targets) {
        el.style.translate = translated(original.translate, this.direction * 6 * strength, 0);
        el.style.filter = `${original.filter && original.filter !== 'none' ? original.filter + ' ' : ''}brightness(${1 + 1.8 * strength})`;
      }
    },
  });
  Fx.define('hit-shake', {
    duration: 0.3,
    mount(root, params) {
      this.amplitude = params.level === 'light' ? 0
        : ({ normal: { medium: 3, large: 4 }, rich: { medium: 4, large: 6 } }[params.level]?.[params.tier] || 0);
      this.targets = rememberTargets(params.targets, ['translate']);
      this.card = rememberTargets(params.level === 'rich' && params.tier === 'large' ? [params.cardTarget] : [], ['translate']);
      this.offset = [0, 0];
    },
    render(t) {
      const time = Math.max(0, Math.min(t, this.duration));
      const phase = time * 28, index = Math.floor(phase), blend = phase - index;
      const point = n => {
        const bits = Math.imul(n + 17, 1597334677) ^ Math.imul(n + 37, 3812015801);
        const angle = (bits >>> 0) / 4294967296 * Math.PI * 2;
        return [Math.cos(angle), Math.sin(angle)];
      };
      const a = point(index), b = point(index + 1);
      const envelope = Math.min(time / 0.018, 1) * (1 - time / this.duration) ** 2;
      const unit = a.map((value, i) => Fx.lerp(value, b[i], blend) * envelope);
      this.offset = unit.map(value => value * this.amplitude);
      if (!this.amplitude || t <= 0 || t >= this.duration) {
        restoreTargets(this.targets); restoreTargets(this.card); return;
      }
      for (const { el, original } of this.targets) el.style.translate = translated(original.translate, ...this.offset);
      for (const { el, original } of this.card) el.style.translate = translated(original.translate, unit[0] * 4, unit[1] * 4);
    },
  });

  function svgElement(root, tag, className, attrs = {}) {
    const el = root.ownerDocument.createElementNS('http://www.w3.org/2000/svg', tag);
    el.setAttribute('class', className);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    root.appendChild(el);
    return el;
  }

  // PR4.5e。斬撃の幾何は試作proto-slash-bと同じ弧を使う。
  const ATTACK_HIT = 0.7, ATTACK_STOP = 0.78;
  const ATTACK_PARTICLES = {
    slash: { sparks: 75, debris: 0, embers: 22, rays: 11, smoke: 8 },
    strike: { sparks: 40, debris: 24, embers: 18, rays: 10, smoke: 14 },
    pierce: { sparks: 64, debris: 12, embers: 20, rays: 11, smoke: 6 },
  };
  function attackRandom(i, seed) {
    const x = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453;
    return x - Math.floor(x);
  }
  function attackGeometry(W, H, kind) {
    const C = { x: W * 0.62, y: H * 1.25 }, R = H * 0.81;
    const at = (a, r = R) => ({ x: C.x + Math.cos(a) * r, y: C.y + Math.sin(a) * r });
    const a0 = -2.75, a1 = -0.85, aHit = -1.77;
    return { C, R, a0, a1, aHit, at,
      hit: kind === 'slash' ? at(aHit) : { x: W * (kind === 'strike' ? 0.52 : 0.68), y: H * (kind === 'strike' ? 0.76 : 0.5) },
      tangent: kind === 'slash' ? aHit + Math.PI / 2 : 0 };
  }
  function attackBlade(g, time) {
    const p = Fx.clamp01((Math.min(time, ATTACK_HIT) - 0.5) / 0.2), s = p ** 1.6;
    const head = Fx.lerp(g.a0, g.a1, s);
    if (time <= ATTACK_STOP) return { head, tail: Math.max(g.a0 - 0.2, head - 1.45 * Fx.clamp01(s * 1.4)), visible: time >= 0.5 };
    const close = Fx.prog(time, ATTACK_STOP, 0.42);
    return { head: g.a1 + 0.06 * close, tail: Fx.lerp(g.a1 - 1.45, g.a1 + 0.06, close), visible: close < 1 };
  }
  function attackCrescent(g, b, thick, inner = 0.32) {
    const outer = [], inside = [];
    for (let i = 0; i <= 48; i++) {
      const u = i / 48, a = Fx.lerp(b.tail, b.head, u);
      const h = thick * u ** 1.3 * (1 - u) ** 0.22 * 1.6;
      outer.push(g.at(a, g.R + h)); inside.push(g.at(a, g.R - h * inner));
    }
    return [...outer, ...inside.reverse()];
  }
  function attackCut(g, len, width) {
    const outer = [], inside = [], span = len / g.R;
    for (let i = 0; i <= 32; i++) {
      const u = i / 32, a = g.aHit + (u - 0.5) * 2 * span, h = width * Math.sin(Math.PI * u) ** 0.8;
      outer.push(g.at(a, g.R + h)); inside.push(g.at(a, g.R - h));
    }
    return [...outer, ...inside.reverse()];
  }
  const attackAlpha = (color, alpha) => `color-mix(in srgb, ${color} ${Fx.clamp01(alpha) * 100}%, transparent)`;
  function attackPoly(ctx, points) {
    ctx.beginPath();
    points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
    ctx.closePath();
  }
  function attackGlow(ctx, x, y, radius, colors, alpha = 1) {
    if (!(radius > 0 && alpha > 0)) return;
    const glow = ctx.createRadialGradient(x, y, 0, x, y, radius);
    glow.addColorStop(0, attackAlpha(colors.white, alpha));
    glow.addColorStop(0.22, attackAlpha(colors.main, alpha * 0.7));
    glow.addColorStop(1, attackAlpha(colors.edge, 0));
    ctx.fillStyle = glow;
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }
  function attackStar(ctx, x, y, radius, color, angle = 0) {
    ctx.fillStyle = color;
    attackPoly(ctx, Array.from({ length: 8 }, (_, i) => {
      const a = angle + i * Math.PI / 4, r = radius * (i % 2 ? 0.16 : i % 4 ? 0.7 : 1);
      return { x: x + Math.cos(a) * r, y: y + Math.sin(a) * r };
    }));
    ctx.fill();
  }
  function mountAttack(root, params, kind) {
    this.level = params.level;
    this.tier = params.tier || 'small';
    // 試作と同じ設計の箱で描き、渡された箱に収まる倍率で全体（太さ・速さ・光）を伸び縮みさせる。
    const draw = params.mode === 'draw';
    this.W = draw ? 150 : 320 * (params.mode === 'wide' ? 1.35 : 1);
    this.H = draw ? 110 : 240;
    this.scale = draw ? 1 : Math.min(Math.max(1, Number(params.width) || this.W) / this.W, Math.max(1, Number(params.height) || this.H) / this.H);
    this.k = { small: 0.7, medium: 1, large: 1.4 }[this.tier];
    this.start = { slash: 0.5, strike: 0.55, pierce: 0.58 }[kind];
    this.g = attackGeometry(this.W, this.H, kind);
    const factor = (this.level === 'light' ? 0 : { small: 0.5, medium: 0.7, large: 1 }[this.tier]) * (this.level === 'rich' ? 1.3 : 1);
    this.counts = Object.fromEntries(Object.entries({ ...ATTACK_PARTICLES[kind], charge: 18, speed: 14 }).map(([key, n]) => [key, Math.round(n * factor)]));
    this.el = element(root, 'div', `fx-attack ${kind} ${params.tone || 'enemy'} ${params.level} ${this.tier}`);
    // 置き場所の点は、引き分けは箱の中心、それ以外は命中の点（向きの反転後）。
    const direction = params.direction === -1 ? -1 : 1, s = this.scale;
    const hitX = (direction === -1 ? this.W - this.g.hit.x : this.g.hit.x) * s;
    Object.assign(this.el.style, { width: `${this.W * s}px`, height: `${this.H * s}px`,
      transform: `${draw ? 'translate(-50%, -50%)' : `translate(${-hitX}px, ${-this.g.hit.y * s}px)`} scaleX(${direction})` });
    this.canvas = element(this.el, 'canvas', 'fx-attack-canvas');
    this.canvas.setAttribute('aria-hidden', 'true');
    this.ctx = this.canvas.getContext('2d');
    const view = root.ownerDocument.defaultView;
    const style = view.getComputedStyle(this.el);
    const tone = ['ally', 'neutral'].includes(params.tone) ? params.tone : 'enemy';
    this.colors = { main: style.getPropertyValue({ enemy: '--fx-win', ally: '--fx-ally', neutral: '--fx-neutral' }[tone]).trim(),
      edge: style.getPropertyValue(`--fx-attack-${tone}-edge`).trim(), white: style.getPropertyValue('--fx-white').trim(),
      smoke: style.getPropertyValue('--fx-attack-smoke').trim() };
    // 余白は四方に箱の半分。拡大率に加えて画素数も制限し、一覧の多数の見本でもメモリを絞る。
    this.pad = 0.5;
    const w = this.W * s, h = this.H * s;
    this.dpr = Math.min(2, view.devicePixelRatio || 1, Math.sqrt(1000000 / (w * h * 4)));
    this.pixelWidth = Math.floor(w * 2 * this.dpr);
    this.pixelHeight = Math.floor(h * 2 * this.dpr);
    Object.assign(this.canvas.style, { left: `${-w * this.pad}px`, top: `${-h * this.pad}px`, width: `${w * 2}px`, height: `${h * 2}px` });
    this.canvas.width = 0; this.canvas.height = 0;
  }
  function attackShape(fx, time, kind) {
    if (kind === 'slash') return attackBlade(fx.g, time);
    const p = Fx.clamp01((Math.min(time, ATTACK_HIT) - fx.start) / (ATTACK_HIT - fx.start));
    return { rush: p ** 2, squash: kind === 'strike' && time >= ATTACK_HIT,
      retreat: Fx.prog(time, ATTACK_STOP, 0.5) };
  }
  function drawAttackShape(fx, time, kind) {
    const ctx = fx.ctx, g = fx.g, k = fx.k, c = fx.colors, shape = fx.shape;
    const { x: hx, y: hy } = g.hit;
    const tail = Math.max(0, time - ATTACK_STOP);
    const fade = 1 - Fx.prog(tail, 0.1, 0.42);
    const white = time >= ATTACK_HIT && time < ATTACK_HIT + 0.033;
    if (time < fx.start) return;
    if (kind === 'slash') {
      if (!shape.visible || shape.head - shape.tail < 0.01) return;
      const thick = 13 * k;
      for (let j = 0; j < fx.counts.speed; j++) {
        const r = g.R + (attackRandom(j, 11) - 0.3) * 26 * k, from = Fx.lerp(shape.tail, shape.head, 0.15 + attackRandom(j, 12) * 0.3);
        ctx.strokeStyle = c.main; ctx.globalAlpha = 0.18 * fade; ctx.lineWidth = 0.8 + attackRandom(j, 13) * 1.6;
        ctx.beginPath(); ctx.arc(g.C.x, g.C.y, r, from, Math.max(from, shape.head - 0.02)); ctx.stroke();
      }
      // 幅を変えた3層の発光。全面のblurを避け、試作の白芯と色の階調を保つ。
      for (const [width, alpha] of [[2.4, 0.1], [1.7, 0.24]]) {
        ctx.globalAlpha = fade * alpha; ctx.fillStyle = c.main;
        attackPoly(ctx, attackCrescent(g, shape, thick * width, 0.7)); ctx.fill();
      }
      const a = g.at(shape.tail), b = g.at(shape.head), gradient = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
      gradient.addColorStop(0, attackAlpha(c.edge, 0)); gradient.addColorStop(0.45, attackAlpha(c.edge, 0.73));
      gradient.addColorStop(0.8, c.main); gradient.addColorStop(0.94, c.white); gradient.addColorStop(1, c.white);
      ctx.globalAlpha = fade; ctx.fillStyle = gradient; attackPoly(ctx, attackCrescent(g, shape, thick)); ctx.fill();
      ctx.fillStyle = c.white; attackPoly(ctx, attackCrescent(g, shape, thick * (white ? 1 : 0.36), white ? 0.32 : 0.1)); ctx.fill();
    } else {
      const rush = shape.rush, x = kind === 'strike' ? hx - 28 * (1 - rush) : hx;
      const y = kind === 'strike' ? hy - fx.H * 0.85 * (1 - rush) : hy;
      const length = kind === 'strike' ? fx.H * (shape.squash ? 0.055 : 0.52) : fx.W * 0.66 * rush;
      const radius = (kind === 'strike' ? shape.squash ? 48 : 11 : 10) * k;
      const base = kind === 'strike' ? { x: x - radius * 0.45, y: y - length } : { x: hx - length + length * shape.retreat, y };
      const points = kind === 'strike' ? [{ x: x - radius, y }, { x: x - radius * 0.45, y: y - length }, { x, y: y - length * 1.2 }, { x: x + radius * 0.55, y: y - length }, { x: x + radius, y }, { x, y: y + radius * 0.4 }]
        : [{ x: base.x, y: y - radius * (1 - shape.retreat) }, { x: hx + shape.retreat * fx.W * 0.2, y }, { x: base.x, y: y + radius * (1 - shape.retreat) }];
      ctx.globalAlpha = fade;
      attackGlow(ctx, x, y, radius * 4, c, 0.45 * fade);
      const gradient = ctx.createLinearGradient(base.x, base.y, x, y);
      gradient.addColorStop(0, attackAlpha(c.edge, 0)); gradient.addColorStop(0.45, c.edge); gradient.addColorStop(0.8, c.main); gradient.addColorStop(1, c.white);
      ctx.fillStyle = gradient; attackPoly(ctx, points); ctx.fill();
      ctx.strokeStyle = c.white; ctx.lineWidth = (white ? 4 : 1.5) * k;
      ctx.beginPath(); ctx.moveTo(base.x, base.y); ctx.lineTo(x, y); ctx.stroke();
      for (let i = 0; i < fx.counts.speed; i++) {
        const offset = (attackRandom(i, 17) - 0.5) * radius * 6, length = (15 + attackRandom(i, 18) * 70) * k;
        const drift = attackRandom(i, 19) * 0.8;
        ctx.strokeStyle = i % 3 ? c.main : c.white; ctx.globalAlpha = 0.25 * fade; ctx.lineWidth = 0.5 + attackRandom(i, 20);
        ctx.beginPath();
        if (kind === 'strike') { ctx.moveTo(x + offset, y - length - drift * fx.H); ctx.lineTo(x + offset, y - drift * fx.H); }
        else { ctx.moveTo(base.x + length * drift, y + offset); ctx.lineTo(Math.min(hx, base.x + length * (1 + drift)), y + offset); }
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }
  function drawAttackImpact(fx, time, kind) {
    const age = time - ATTACK_HIT;
    if (age < 0) return;
    const ctx = fx.ctx, g = fx.g, k = fx.k, c = fx.colors, { x: hx, y: hy } = g.hit;
    const burst = Fx.clamp01(age / 0.16), flash = 1 - Fx.prog(age, 0, 0.1);
    attackGlow(ctx, hx, hy, fx.W * (fx.level === 'rich' ? 0.9 : 0.8), c, flash);
    if (kind === 'pierce') attackStar(ctx, hx, hy, 45 * k, attackAlpha(c.white, 1 - Fx.prog(age, 0, 0.22)));
    if (burst < 1) for (let i = 0; i < fx.counts.rays; i++) {
      const a = attackRandom(i, 21) * Math.PI * 2, len = (60 + attackRandom(i, 22) * 150) * k * (0.4 + burst), w = (3 + attackRandom(i, 23) * 4) * (1 - burst);
      ctx.globalAlpha = 0.9 * (1 - burst); ctx.fillStyle = c.white;
      attackPoly(ctx, [{ x: hx + Math.cos(a + 1.57) * w, y: hy + Math.sin(a + 1.57) * w }, { x: hx + Math.cos(a) * len, y: hy + Math.sin(a) * len }, { x: hx - Math.cos(a + 1.57) * w, y: hy - Math.sin(a + 1.57) * w }]); ctx.fill();
    }
    ctx.globalAlpha = 1;
    if (kind === 'slash') {
      const w = 5 * k * Fx.prog(age, 0, 0.04) * (1 - Fx.prog(age, 0.08, 0.5));
      const len = fx.W * (0.42 + 0.08 * Fx.prog(age, 0, 0.4));
      if (w > 0.05) {
        for (const [scale, alpha] of [[3, 0.16], [1.7, 0.35], [1, 1]]) {
          ctx.fillStyle = scale === 1 ? c.white : c.main; ctx.globalAlpha = alpha;
          attackPoly(ctx, attackCut(g, len, w * scale)); ctx.fill();
        }
      }
    } else if (kind === 'strike') {
      for (let i = 0; i < 2; i++) {
        const a = time - ATTACK_STOP - i * 0.1;
        if (a <= 0) continue;
        const p = Fx.prog(a, 0, 0.48), extent = fx.tier === 'small' ? 0.5 : 1;
        ctx.globalAlpha = (1 - p) * (i ? 0.55 : 0.85); ctx.strokeStyle = i ? c.main : c.white; ctx.lineWidth = (1 - p) * 4 * k;
        ctx.beginPath(); ctx.ellipse(hx, hy, (4 + fx.W * 0.48 * p) * extent, 2 + 22 * k * p, 0, 0, Math.PI * 2); ctx.stroke();
      }
    } else {
      const p = Fx.prog(time, ATTACK_STOP, 0.5);
      ctx.globalAlpha = 1 - p; ctx.strokeStyle = c.main; ctx.lineWidth = 2 * k * (1 - p);
      ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(hx + fx.W * 0.32 * p, hy); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  function drawAttackParticles(fx, time, kind) {
    const tau = time - ATTACK_STOP;
    if (tau <= 0) return;
    const ctx = fx.ctx, g = fx.g, c = fx.colors, k = fx.k, { x: hx, y: hy } = g.hit;
    ctx.lineCap = 'round';
    for (let i = 0; i < fx.counts.sparks; i++) {
      const spread = kind === 'pierce' ? 0.45 : 1.5;
      const a = kind === 'strike' ? -Math.PI * attackRandom(i, 1) : g.tangent + (attackRandom(i, 1) - 0.5) * spread + (kind === 'slash' && attackRandom(i, 5) < 0.25 ? Math.PI : 0);
      const speed = (260 + attackRandom(i, 2) * (kind === 'pierce' ? 650 : 560)) * k;
      const life = 0.28 + attackRandom(i, 3) * 0.4;
      if (tau >= life) continue;
      const position = t => ({ x: hx + Math.cos(a) * speed * t, y: hy + Math.sin(a) * speed * t + (kind === 'pierce' ? 50 : 520) * t * t });
      const a0 = position(Math.max(0, tau - 0.03)), b = position(tau), heat = 1 - tau / life;
      ctx.strokeStyle = heat > 0.6 ? c.white : i % 2 ? c.main : c.edge;
      ctx.globalAlpha = Math.min(1, heat * 1.3); ctx.lineWidth = (1 + attackRandom(i, 4) * 2.2 * k) * (0.5 + heat);
      ctx.beginPath(); ctx.moveTo(a0.x, a0.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    for (let i = 0; i < fx.counts.debris; i++) {
      const p = Fx.clamp01(tau / (0.38 + attackRandom(i, 51) * 0.24));
      const a = kind === 'strike' ? -Math.PI * (0.08 + attackRandom(i, 52) * 0.84) : (attackRandom(i, 52) - 0.5) * 0.45;
      const v = (80 + attackRandom(i, 53) * 150) * k;
      const x = hx + Math.cos(a) * v * tau, y = hy + Math.sin(a) * v * tau + (kind === 'strike' ? 620 : 40) * tau * tau;
      const r = (kind === 'strike' ? 2.5 + attackRandom(i, 54) * 4 : 1 + attackRandom(i, 54) * 2) * k;
      ctx.globalAlpha = 1 - p; ctx.fillStyle = i % 3 ? c.edge : c.main;
      ctx.save(); ctx.translate(x, y); ctx.rotate(tau * (i % 2 ? 4 : -4));
      attackPoly(ctx, kind === 'strike' ? [{ x: -r, y: 0 }, { x: 0, y: -r }, { x: r, y: r * 0.3 }, { x: 0, y: r }] : [{ x: -r * 5, y: 0 }, { x: r * 3, y: -r }, { x: r * 4, y: 0 }, { x: r * 3, y: r }]); ctx.fill(); ctx.restore();
    }
    for (let i = 0; i < fx.counts.embers; i++) {
      const life = 0.45 + attackRandom(i, 31) * 0.2, e = tau / life;
      if (e >= 1) continue;
      const a = g.tangent + (attackRandom(i, 32) - 0.5) * (kind === 'pierce' ? 0.5 : 2.4), v = (40 + attackRandom(i, 33) * 120) * k;
      const x = hx + Math.cos(a) * v * tau + Math.sin(tau * 9 + i) * 6, y = hy + Math.sin(a) * v * tau - 40 * tau;
      ctx.globalAlpha = (1 - e) * (0.6 + 0.4 * Math.sin(tau * 40 + i * 3)); ctx.fillStyle = i % 2 ? c.main : c.white;
      ctx.beginPath(); ctx.arc(x, y, 1.4 + attackRandom(i, 34) * 1.6, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    const e = Fx.clamp01((tau - 0.06) / 0.56);
    if (e > 0 && e < 1) for (let i = 0; i < fx.counts.smoke; i++) {
      const a = kind === 'strike' ? Math.PI * attackRandom(i, 41) : g.tangent + (attackRandom(i, 41) - 0.5) * 2;
      const d = (20 + attackRandom(i, 42) * 70) * k * e, x = hx + Math.cos(a) * d, y = hy + Math.sin(a) * d - 25 * e;
      const r = (18 + attackRandom(i, 43) * 26) * k * (0.6 + e), fog = ctx.createRadialGradient(x, y, 0, x, y, r);
      fog.addColorStop(0, attackAlpha(c.smoke, 0.32 * (1 - e))); fog.addColorStop(1, attackAlpha(c.smoke, 0));
      ctx.fillStyle = fog; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    }
  }
  function renderAttack(t, kind) {
    const time = Math.max(0, Math.min(t, this.duration)), ctx = this.ctx;
    this.el.style.opacity = String(this.level === 'light' ? Fx.stillOpacity(time - ATTACK_HIT, 0.7) : Fx.stillOpacity(t, this.duration));
    this.shape = attackShape(this, time, kind);
    if (t <= 0 || t >= this.duration || this.level === 'light' && time <= ATTACK_HIT) {
      this.canvas.width = 0; this.canvas.height = 0;
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, this.pixelWidth, this.pixelHeight); return;
    }
    if (!this.canvas.width) { this.canvas.width = this.pixelWidth; this.canvas.height = this.pixelHeight; }
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, this.pixelWidth, this.pixelHeight);
    // Canvasの全状態も毎コマ戻す。呼出し順・直前の煙・サイズ変更に依存させない。
    const unit = this.dpr * this.scale;
    ctx.setTransform(unit, 0, 0, unit, this.W * this.pad * unit, this.H * this.pad * unit);
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.lineWidth = 1; ctx.lineCap = 'butt';
    ctx.fillStyle = this.colors.main; ctx.strokeStyle = this.colors.main;
    const g = this.g, { x: hx, y: hy } = g.hit, k = this.k;
    if (this.level === 'light') {
      if (kind === 'slash') { attackPoly(ctx, attackCut(g, this.W * 0.42, 3 * k)); ctx.fill(); }
      else if (kind === 'strike') { ctx.beginPath(); ctx.ellipse(hx, hy, this.W * 0.4, 3 * k, 0, 0, Math.PI * 2); ctx.fill(); }
      else attackStar(ctx, hx, hy, 24 * k, this.colors.main);
      return;
    }
    ctx.globalCompositeOperation = 'lighter';
    if (time < this.start + 0.04) {
      const charge = Fx.prog(time, 0.05, this.start - 0.05);
      const start = kind === 'slash' ? g.at(g.a0 + 0.12) : { x: kind === 'strike' ? hx - 28 : this.W * 0.05 - 12 * charge, y: kind === 'strike' ? this.H * 0.07 : hy };
      for (let i = 0; i < this.counts.charge; i++) {
        const a = attackRandom(i, 9) * Math.PI * 2, d = (1 - charge) * (40 + attackRandom(i, 8) * 60) * k;
        ctx.globalAlpha = 0.7 * charge; ctx.fillStyle = this.colors.white;
        ctx.beginPath(); ctx.arc(start.x + Math.cos(a) * d, start.y + Math.sin(a) * d, 1.2 + attackRandom(i, 7) * 1.5, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      attackGlow(ctx, start.x, start.y, kind === 'strike' ? (30 - 20 * charge) * k : (8 + 26 * charge) * k, this.colors, charge);
    }
    drawAttackShape(this, time, kind); drawAttackImpact(this, time, kind); drawAttackParticles(this, time, kind);
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  }
  for (const kind of ['slash', 'strike', 'pierce']) {
    Fx.define(`attack-${kind}`, {
      duration: 1.4,
      mount(root, params) { mountAttack.call(this, root, params, kind); },
      render(t) { renderAttack.call(this, t, kind); },
    });
  }

  Fx.define('impact-flash', {
    duration: 0.3,
    mount(root, params) {
      this.level = params.level;
      this.el = element(root, 'div', 'fx-impact-flash');
      this.el.style.width = `${params.width}px`;
      this.el.style.height = `${params.height}px`;
    },
    render(t) {
      this.el.style.transform = 'translate(-50%, -50%)';
      this.el.style.opacity = String(this.level === 'rich' ? Fx.stillOpacity(t, this.duration) : 0);
    },
  });

  Fx.define('resolve-damage', {
    duration: 1.6,
    mount(root, params) {
      this.level = params.level;
      // 結果の段階では、出た後も枠の終わり（戦闘不能の対象は割れる時刻）まで残す長さを受け取る。
      this.duration = params.duration ?? this.duration;
      this.leaveAt = params.leaveAt;
      this.delay = Math.max(0, Math.min(0.8, Number(params.delay) || 0));
      this.el = element(root, 'div', `fx-resolve-damage ${params.tone || 'enemy'} ${params.kind === 'effect' ? 'extra' : ''} ${params.icon ? 'with-icon' : ''} ${params.mode === 'chip' ? 'chip' : ''}`);
      if (params.icon) {
        const icon = element(this.el, 'img', 'fx-damage-icon');
        icon.setAttribute('src', params.icon);
        icon.setAttribute('alt', params.label || '');
      }
      // ダメージは常に減る向きなので符号を付けない（効果の帯の増減は符号を残す）。
      element(this.el, 'span', 'fx-damage-number', String(params.amount));
      // 押し上げはしない。until 秒まで一定の速さで昇り、その後なめらかに減速する（同じ対象の数字は同時に減速する）。
      this.until = Math.max(0, Number(params.until) || 0);
      this.speed = Number(params.speed) || Fx.FLOAT.numberSpeed;
      // 昇ってよい高さ（px）。帯の上端と同じく、その36px手前から薄れて消える。
      this.ceiling = params.ceiling;
      this.crowdAt = params.crowdAt;
      // 列の2つ目以降は、上の数字にはみ出さないよう、出だしの膨らみを控えめにする。
      this.pop = params.stacked ? 1.12 : (this.level === 'rich' ? 1.6 : 1.3);
    },
    render(t) {
      const time = t - this.delay;
      const length = this.duration - this.delay;
      const light = this.level === 'light';
      // 軽めは動かさず、最初から最後の並びの位置に置く。
      const y = -(light ? this.speed * this.until : Fx.floatDistance(Math.min(time, length), this.until, this.speed));
      const crowded = (this.crowdAt === undefined ? 1 : 1 - Fx.prog(time, this.crowdAt, 0.15))
        * (this.ceiling === undefined ? 1 : Fx.clamp01((this.ceiling + y) / 36));
      const fading = this.leaveAt === undefined ? Fx.lingerProgress(time, length) : Fx.prog(time, this.leaveAt, 0.3);
      this.el.style.opacity = String((this.leaveAt === undefined ? Fx.lingerOpacity(time, length)
        : Fx.prog(time, 0, 0.15) * (1 - fading)) * crowded);
      // 0.3秒かけて手前へ膨らみ、0.5秒かけて落ち着き、薄れと同じ進みで縮む。
      const swell = time < 0.3 ? Fx.lerp(Fx.FLOAT.enterFrom, this.pop, Fx.prog(time, 0, 0.3))
        : Fx.lerp(this.pop, 1, Fx.prog(time, 0.3, 0.5));
      this.el.style.transform = light ? `translate(-50%, -50%) translateY(${y}px)`
        : `translate(-50%, -50%) translateY(${y}px) scale(${swell * Fx.lerp(1, Fx.FLOAT.shrink, fading)})`;
    },
  });

  function bandRow(root, entry) {
    const el = element(root, 'div', `fx-effect-${entry.kind} ${entry.tone || 'enemy'}`);
    el.setAttribute('data-readable', '');
    const icon = entry.icon ? element(el, 'img', 'fx-effect-icon') : null;
    if (icon) { icon.setAttribute('src', entry.icon); icon.setAttribute('alt', ''); }
    const label = element(el, 'span', 'fx-effect-label', String(entry.text || '').replace(/^buff:/, ''));
    const minus = element(el, 'span', 'fx-damage-minus'), number = element(el, 'span', 'fx-effect-number');
    const numeric = entry.kind === 'result' && entry.delta !== null && entry.delta !== undefined;
    minus.style.display = numeric && entry.delta < 0 ? '' : 'none';
    number.style.display = numeric ? '' : 'none';
    number.textContent = numeric ? `${entry.delta > 0 ? '+' : ''}${Math.abs(entry.delta)}` : '';
    return { el, icon, label, minus, number, entry };
  }
  Fx.define('effect-band', {
    duration: 3.9,
    mount(root, params) {
      this.level = params.level;
      this.side = params.side || 'defender';
      this.duration = params.duration ?? this.duration;
      this.layout = Fx.layoutEffectBand(params.groups || []);
      this.el = element(root, 'div', `fx-effect-band ${this.side}`);
      this.el.style.width = `${(params.width || 240) * 0.5}px`;
      this.el.style.maxWidth = this.el.style.width;
      const viewport = element(this.el, 'div', 'fx-effect-viewport');
      viewport.style.height = `${Fx.EFFECT_BAND_LAYOUT.visibleHeight}px`;
      this.groups = this.layout.groups.map(group => {
        const el = element(viewport, 'div', 'fx-effect-group');
        // 行はばらして動かすので、どの行も帯の下の端を土台にする。
        const lines = group.lines.map(line => {
          const row = { ...bandRow(el, line), height: line.height, at: line.at, until: line.until };
          row.el.style.transformOrigin = this.side === 'attacker' ? 'left bottom' : 'right bottom';
          return row;
        });
        return { ...group, el, lines };
      });
      this.rowTimes = this.groups.flatMap(group => group.lines.map(row => row.at));
    },
    render(t) {
      const light = this.level === 'light', config = Fx.EFFECT_BAND_LAYOUT;
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = this.side === 'attacker' ? 'translate(0, -50%)' : 'translate(-100%, -50%)';
      // 軽めは滑らかに動かさず、新しい行が出た瞬間にだけ1行分上へ置き直す。
      const latest = Math.max(0, ...this.rowTimes.filter(at => at <= t));
      for (const group of this.groups) {
        const leave = group.leaveAt === undefined ? 0 : Fx.prog(t, group.leaveAt, 0.3);
        for (const row of group.lines) {
          const age = t - row.at, length = this.duration - row.at;
          const rise = light ? config.speed * Math.max(0, latest - row.at)
            : Fx.floatDistance(Math.min(age, length), row.until, config.speed);
          const ceiling = Fx.clamp01((config.visibleHeight - row.height - rise) / config.fadeZone);
          row.el.style.opacity = String(age < 0 ? 0 : Fx.lingerOpacity(age, length) * ceiling * (1 - leave));
          const x = light ? 0 : (this.side === 'attacker' ? -24 : 24) * (1 - Fx.prog(age, 0, config.slide));
          const shrink = Fx.lerp(1, Fx.FLOAT.groupShrink, Math.max(Fx.lingerProgress(age, length), leave));
          row.el.style.transform = `translate(${x}px, ${-rise}px)${light ? '' : ` scale(${shrink})`}`;
        }
      }
    },
  });

  // 番号から決まる疑似乱数（mulberry32）。種は戦闘不能になったキャラのIDから作り、同じ場面なら毎回同じ割れ方にする。
  function glassRandom(seedText) {
    let seed = 2166136261;
    for (const ch of String(seedText ?? 'ko')) seed = Math.imul(seed ^ ch.charCodeAt(0), 16777619);
    return () => {
      seed = (seed + 0x6D2B79F5) | 0;
      let x = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  }

  // 放射と輪の折れ線を面同士で共有し、その面をそのまま破片へ使う。
  // 本物のガラスに寄せて、放射の角度と本数をばらつかせ、輪はひびごとに半径を揺らし、間ごとに途切れさせる（計画52 §6.6-8）。
  function glassPane(width, height, origin, options, random) {
    const { count, fractions, gapChance } = options;
    const [cx, cy] = origin, turn = Math.PI * 2;
    const angle = p => (Math.atan2(p[1] - cy, p[0] - cx) + turn) % turn;
    const ringRadius = Math.min(cx, width - cx, cy, height - cy);
    const corners = [[width, height], [0, height], [0, 0], [width, 0]].map(point => ({ point, angle: angle(point) }));
    const gaps = Array.from({ length: count }, () => 0.5 + random() * 1.1);
    const gapTotal = gaps.reduce((sum, gap) => sum + gap, 0);
    let next = random() * turn / count;
    const rays = gaps.map(gap => {
      const own = next % turn, step = gap / gapTotal * turn;
      next += step;
      const dx = Math.cos(own), dy = Math.sin(own);
      const length = Math.min(dx > 0 ? (width - cx) / dx : dx < 0 ? -cx / dx : Infinity,
        dy > 0 ? (height - cy) / dy : dy < 0 ? -cy / dy : Infinity);
      const outer = [Math.max(0, Math.min(width, cx + dx * length)), Math.max(0, Math.min(height, cy + dy * length))];
      const radii = fractions.map(fraction => fraction * ringRadius * (0.82 + random() * 0.36));
      const points = [origin, ...radii.map(radius => {
        const bend = own + (random() - 0.5) * Math.min(step, 0.5) * 0.18;
        return [cx + Math.cos(bend) * radius, cy + Math.sin(bend) * radius];
      }), outer];
      const duration = 0.28 * (0.78 + random() * 0.22);
      return { angle: own, points, radii, arrivals: [0, ...radii.map(radius => radius / length * duration), duration] };
    }).sort((x, y) => x.angle - y.angle);
    const cells = [], edges = [];
    for (let i = 0; i < count; i++) {
      const ray = rays[i], after = rays[(i + 1) % count];
      // その間に残す輪。内側の輪は必ず残し、外側の輪はところどころ途切れさせる。
      const present = fractions.map((_, j) => j === 0 || random() >= gapChance);
      const ringPoint = fractions.map((_, j) => {
        const first = angle(ray.points[j + 1]), last = angle(after.points[j + 1]);
        const middle = (first + (last <= first ? last + turn : last)) / 2;
        const radius = (ray.radii[j] + after.radii[j]) / 2 * (0.96 + random() * 0.08);
        return [cx + Math.cos(middle) * radius, cy + Math.sin(middle) * radius];
      });
      const bounds = [-1, ...fractions.map((_, j) => j).filter(j => present[j]), fractions.length];
      const endAngle = i + 1 < count ? after.angle : turn + rays[0].angle;
      const boundary = corners.map(c => ({ ...c, angle: c.angle < ray.angle ? c.angle + turn : c.angle }))
        .filter(c => c.angle > ray.angle && c.angle < endAngle).sort((x, y) => x.angle - y.angle).map(c => c.point);
      for (let k = 0; k + 1 < bounds.length; k++) {
        const inner = bounds[k], outerRing = bounds[k + 1];
        const from = inner + 1, to = outerRing + 1;
        const cell = ray.points.slice(from, to + 1);
        if (outerRing === fractions.length) cell.push(...boundary);
        else cell.push(ringPoint[outerRing]);
        cell.push(...after.points.slice(Math.max(1, from), to + 1).reverse());
        if (inner >= 0) cell.push(ringPoint[inner]);
        cells.push(cell);
      }
      for (let j = 0; j + 1 < ray.points.length; j++) edges.push({ kind: 'radial', rayIndex: i,
        points: [ray.points[j], ray.points[j + 1]], start: ray.arrivals[j], span: ray.arrivals[j + 1] - ray.arrivals[j] });
      fractions.forEach((fraction, j) => {
        if (!present[j]) return;
        const start = Math.max(ray.arrivals[j + 1], after.arrivals[j + 1]);
        edges.push({ kind: 'ring', rayIndex: i, ringIndex: j,
          points: [ray.points[j + 1], ringPoint[j], after.points[j + 1]], start, span: Math.max(0.02, 0.28 - start) });
      });
    }
    return { cells, rays, edges };
  }
  function insideGlass(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const a = polygon[i], b = polygon[j];
      if ((a[1] > point[1]) !== (b[1] > point[1])
        && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  }
  // strokeの伸び方と同じeaseを逆算して、枝の位置を親が通る時刻を求める。
  function glassArrival(fraction) {
    return fraction < 0.5 ? Math.sqrt(fraction / 2) : 1 - Math.sqrt((1 - fraction) / 2);
  }
  function glassBranches(pane, level, chip, random) {
    const branches = [], owners = new Map();
    const edgeKey = (a, b) => [a.join(','), b.join(',')].sort().join('|');
    pane.cells.forEach((cell, index) => cell.forEach((a, i) => {
      const key = edgeKey(a, cell[(i + 1) % cell.length]);
      if (!owners.has(key)) owners.set(key, []);
      owners.get(key).push(index);
    }));
    const add = (from, direction, wanted, cells, timing, meta) => {
      if (timing.start + timing.span > 0.4) return null;
      for (const owner of cells) for (const length of [wanted, Math.max(3, wanted * 0.65), 3]) {
        for (const bend of [0, 0.35, -0.35, 0.7, -0.7, 1.1, -1.1, Math.PI]) {
          const end = [from[0] + Math.cos(direction + bend) * length, from[1] + Math.sin(direction + bend) * length];
          if (!insideGlass(end, pane.cells[owner]) || !insideGlass(from.map((v, axis) => (v + end[axis]) / 2), pane.cells[owner])) continue;
          const branch = { ...meta, ...timing, points: [from, end], length, owner };
          branches.push(branch);
          return branches.length - 1;
        }
      }
      return null;
    };
    pane.edges.forEach((edge, parentEdge) => {
      const lengths = edge.points.slice(1).map((b, i) => Math.hypot(b[0] - edge.points[i][0], b[1] - edge.points[i][1]));
      const total = lengths.reduce((sum, length) => sum + length, 0);
      let travelled = 0;
      lengths.forEach((length, segmentIndex) => {
        const a = edge.points[segmentIndex], b = edge.points[segmentIndex + 1], direction = Math.atan2(b[1] - a[1], b[0] - a[0]);
        // 起点に近い区間ほど枝を多く。位置・角度・長さは疑似乱数でばらつかせる。
        const near = edge.kind === 'radial' && segmentIndex === 0 ? 1 : 0;
        const count = chip ? (length >= 8 && random() < 0.6 ? 1 : 0)
          : Math.floor(random() * (level === 'rich' ? 4 : 3)) + near;
        for (let k = 0; k < count; k++) {
          const phase = Math.floor(random() * 4);
          const fraction = 0.12 + random() * 0.76, from = a.map((v, axis) => Fx.lerp(v, b[axis], fraction));
          const arrival = edge.start + edge.span * glassArrival((travelled + length * fraction) / total);
          const turnAway = (random() < 0.5 ? -1 : 1) * (Math.PI / 9 + random() * Math.PI / 4.5);
          const root = add(from, direction + turnAway, 3 + Math.pow(random(), 1.6) * 11,
            owners.get(edgeKey(a, b)) || [], { arrival, start: arrival + 0.02 + random() * 0.03, span: 0.04 + random() * 0.03 },
            { parentEdge, segmentIndex, parentBranch: null, depth: 1, width: random() < 0.5 ? 0.5 : 0.7, phase });
          if (root === null || random() < 0.6) continue;
          let parent = root;
          const deepest = random() < 0.3 ? 3 : 2;
          for (let depth = 2; depth <= deepest; depth++) {
            const branch = branches[parent], [p, q] = branch.points;
            const at = branch.start + branch.span * glassArrival(0.5);
            const child = add(p.map((v, axis) => Fx.lerp(v, q[axis], 0.5)),
              Math.atan2(q[1] - p[1], q[0] - p[0]) + (random() < 0.5 ? -1 : 1) * (0.4 + random() * 0.6),
              Math.max(3, branch.length * (0.45 + random() * 0.3)), [branch.owner],
              { arrival: at, start: at + 0.02, span: 0.04 },
              { parentEdge, segmentIndex, parentBranch: parent, depth, width: depth === 2 ? 0.35 : 0.3, phase });
            if (child === null) break;
            parent = child;
          }
        }
        travelled += length;
      });
    });
    return branches;
  }
  function polygonArea(points) {
    return Math.abs(points.reduce((sum, a, i) => { const b = points[(i + 1) % points.length]; return sum + a[0] * b[1] - a[1] * b[0]; }, 0)) / 2;
  }
  Fx.define('ko-shatter', {
    duration: 3.1,
    mount(root, params) {
      this.level = params.level;
      this.duration = params.duration ?? this.duration;
      const width = this.width = params.width || 240, height = this.height = params.height || 240;
      this.origin = [width * 0.5, height * 0.38];
      const [cx, cy] = this.origin;
      const chip = params.mode === 'chip', rich = params.level === 'rich';
      this.el = element(root, 'div', `fx-ko ${chip ? 'chip' : ''} ${params.level}`);
      this.el.style.width = `${width}px`;
      this.el.style.height = `${height}px`;
      this.shade = element(this.el, 'div', 'fx-ko-shade');
      const svg = this.svg = svgElement(this.el, 'svg', 'fx-ko-svg', { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: 'xMidYMid meet', 'aria-hidden': 'true' });
      this.face = svgElement(svg, 'rect', 'fx-ko-face', { x: 0, y: 0, width, height });
      const random = glassRandom(params.targetId);
      const fractions = chip ? [0.45] : [0.2, 0.45, 0.78];
      const count = chip ? 4 + Math.floor(random() * 3) : rich ? 9 + Math.floor(random() * 3) : 8 + Math.floor(random() * 3);
      const pane = glassPane(width, height, this.origin, { count, fractions, gapChance: chip ? 0 : rich ? 0.35 : 0.45 }, random);
      this.radials = pane.rays;
      this.rings = fractions;
      const distance = p => Math.hypot(p[0] - cx, p[1] - cy) / Math.hypot(width / 2, height * 0.62);
      this.cracks = pane.edges.map(edge => {
        const base = (chip ? 1.2 : rich ? 2.3 : 2.0) - edge.points.reduce((sum, p) => sum + distance(p), 0) / edge.points.length * 0.9;
        const width = Math.min(chip ? 1.2 : 2.4, Math.max(chip ? 0.7 : 1.2, base * (0.85 + random() * 0.3)));
        const el = svgElement(svg, 'path', 'fx-ko-crack', { d: `M ${edge.points.map(p => p.join(' ')).join(' L ')}`, pathLength: 1, 'stroke-width': width });
        el.style.strokeDasharray = '1';
        return { ...edge, width, el };
      });
      this.branches = glassBranches(pane, this.level, chip, random);
      const batches = new Map();
      for (const branch of this.branches) {
        const key = `${branch.width}:${branch.phase}`;
        if (!batches.has(key)) batches.set(key, { width: branch.width, phase: branch.phase, items: [] });
        batches.get(key).items.push(branch);
      }
      const pathFor = points => `M ${points[0].join(' ')} L ${points[1].join(' ')}`;
      this.branchPaths = [...batches.values()].map(batch => ({ ...batch,
        fullPath: batch.items.map(branch => pathFor(branch.points)).join(' '),
        el: svgElement(svg, 'path', 'fx-ko-crack', { 'stroke-width': batch.width }),
      }));
      const star = Array.from({ length: 20 }, (_, i) => {
        const a = i * Math.PI / 10, radius = (chip ? 0.3 : 1) * (i % 2 ? 2.5 : 8 + i % 3);
        return [cx + Math.cos(a) * radius, cy + Math.sin(a) * radius];
      });
      this.star = svgElement(svg, 'polygon', 'fx-ko-star', { points: star.map(p => p.join(',')).join(' ') });
      const maxArea = Math.max(...pane.cells.map(polygonArea));
      this.fragments = params.level === 'light' ? [] : pane.cells.map((points, i) => {
        const center = points.reduce((sum, p) => [sum[0] + p[0] / points.length, sum[1] + p[1] / points.length], [0, 0]);
        const area = polygonArea(points), border = points.some(p => p[0] === 0 || p[0] === width || p[1] === 0 || p[1] === height);
        const el = svgElement(svg, 'g', 'fx-ko-fragment');
        const facet = svgElement(el, 'polygon', 'fx-ko-facet', { points: points.map(p => p.join(',')).join(' '), 'fill-opacity': 0.12 + (i * 7 % 6) * 0.035 });
        const glint = svgElement(el, 'polyline', 'fx-ko-glint', { points: points.slice(0, 3).map(p => p.join(',')).join(' ') });
        return { points, center, area, el, facet, glint, fallStart: 0.9 + (border && Math.floor(i / (fractions.length + 1)) % 3 === 0 ? 0.1 : 0), fallDuration: 0.5 + area / maxArea * 0.1 };
      });
      this.particles = Array.from({ length: params.level === 'light' ? 0 : chip ? rich ? 8 : 4 : rich ? 20 : 12 }, (_, i) =>
        ({ el: svgElement(svg, 'circle', 'fx-ko-particle', { r: chip ? 0.3 : 0.6 + i % 3 * 0.3 }), angle: i * 2.399 }));
      this.sweep = svgElement(svg, 'path', 'fx-ko-sweep', { d: `M ${-width * 0.15} ${-height * 0.1} L ${width * 0.15} ${height * 1.1}` });
      this.flash = element(this.el, 'div', 'fx-ko-flash');
      this.label = element(this.el, 'div', 'fx-ko-label', chip ? '×' : '戦闘不能');
      this.label.style.fontSize = `${chip ? 28 : Math.min(48, Math.max(24, (params.width || 240) / 4.6))}px`;
    },
    render(t) {
      const light = this.level === 'light', fade = Fx.stillOpacity(t, this.duration);
      this.el.style.opacity = '1';
      this.el.style.transform = 'translate(-50%, -50%)';
      this.face.style.opacity = String(fade * (light ? 0.18 : 1 - Fx.prog(t, 0.9, 0.04)));
      this.cracks.forEach((crack, i) => {
        crack.el.style.strokeDashoffset = String(light ? 0 : 1 - Fx.prog(t, crack.start, crack.span));
        crack.el.style.opacity = String(fade * (light ? 1 : (1 - Fx.prog(t, 0.9, 0.06)) * (0.92 + 0.08 * Math.pow(Math.sin(Math.max(0, Math.min(0.9, t)) * 8 - i * 0.37), 2))));
      });
      this.branchPaths.forEach(batch => {
        const d = light || t >= 0.4 ? batch.fullPath : batch.items.map(branch => {
          const progress = Fx.prog(t, branch.start, branch.span);
          if (!progress) return '';
          const [a, b] = branch.points, end = a.map((v, axis) => Fx.lerp(v, b[axis], progress));
          return `M ${a.join(' ')} L ${end.join(' ')}`;
        }).join(' ');
        batch.el.setAttribute('d', d);
        batch.el.style.opacity = String(fade * (light ? 1 : t >= 0.9 ? 0
          : 0.92 + 0.08 * Math.pow(Math.sin(Math.max(0, Math.min(0.9, t)) * 8 - batch.phase), 2)));
      });
      this.star.style.opacity = String(fade * (light ? 0.45 : Fx.prog(t, 0, 0.04) * (1 - Fx.prog(t, 0.9, 0.06))));
      this.fragments.forEach((fragment, i) => {
        const fall = Fx.clamp01((t - fragment.fallStart) / fragment.fallDuration);
        const x = (fragment.center[0] - this.origin[0]) * 0.2 * fall + (i % 3 - 1) * 5 * fall;
        const y = 8 * fall + this.height * 0.95 * fall * fall;
        const spin = (i % 2 ? -1 : 1) * (20 + i * 13 % 80) * fall;
        fragment.el.setAttribute('transform', `translate(${x} ${y}) rotate(${spin} ${fragment.center.join(' ')})`);
        fragment.el.style.opacity = String(fade * Fx.prog(t, 0.9, 0.025) * (1 - Fx.prog(t, fragment.fallStart + fragment.fallDuration - 0.08, 0.08)));
        fragment.glint.style.opacity = String(Math.pow(Math.abs(Math.sin(i * 0.77 + fall * Math.PI * 3)), 6));
      });
      const scatter = Fx.clamp01((t - 0.9) / 0.65);
      this.particles.forEach((particle, i) => {
        particle.el.setAttribute('cx', this.origin[0] + Math.cos(particle.angle) * scatter * (18 + i % 5 * 5));
        particle.el.setAttribute('cy', this.origin[1] + Math.sin(particle.angle) * scatter * 22 + scatter * scatter * 40);
        particle.el.style.opacity = String(fade * Fx.prog(t, 0.9, 0.04) * (1 - Fx.prog(t, 1.4, 0.15)) * Math.pow(Math.abs(Math.sin(i + scatter * 12)), 4));
      });
      this.sweep.setAttribute('transform', `translate(${light ? 0 : Fx.lerp(-this.width * 0.3, this.width * 1.3, Fx.prog(t, 0.6, 0.2))} 0)`);
      this.sweep.style.opacity = String(light ? 0 : fade * Fx.prog(t, 0.6, 0.03) * (1 - Fx.prog(t, 0.77, 0.03)));
      this.flash.style.opacity = String(light || t < 0.9 || t >= 0.94 ? 0 : fade * (1 - Fx.prog(t, 0.9, 0.04)));
      this.shade.style.opacity = String(fade * (light ? 1 : Fx.prog(t, 1.0, 0.4)));
      this.label.style.opacity = String(fade * Fx.prog(t, 1.3, 0.08));
    },
  });

  Fx.define('chat-dice', {
    duration: 1,
    mount(root, params) { mountRoll.call(this, root, params, 0.6, true); },
    render: renderRoll,
  });
})(typeof window !== 'undefined' ? window : globalThis);
