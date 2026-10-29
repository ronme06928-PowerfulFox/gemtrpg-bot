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

  // 攻撃の着弾と数字に同じ時刻・段階の揺れを使う。外側のカードには触らない。
  function impactShake(t, level, tier) {
    const strength = level === 'light' ? 0 : level === 'rich'
      ? ({ medium: 3, large: 6 }[tier] || 0) : tier === 'large' ? 2 : 0;
    const time = Math.max(0, Math.min(t, 0.3));
    return Math.sin(time * 75) * strength * (1 - Fx.prog(time, 0, 0.3));
  }

  function svgElement(root, tag, className, attrs = {}) {
    const el = root.ownerDocument.createElementNS('http://www.w3.org/2000/svg', tag);
    el.setAttribute('class', className);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    root.appendChild(el);
    return el;
  }

  function mountAttack(root, params, kind) {
    this.level = params.level;
    this.tier = params.tier || 'small';
    this.strength = { small: 1, medium: 1.6, large: 2.3 }[this.tier];
    this.el = element(root, 'div', `fx-attack ${kind} ${params.tone || 'enemy'} ${params.level} ${this.tier}`);
    const draw = params.mode === 'draw';
    this.el.style.width = `${draw ? 150 : Math.max(1, Number(params.width) || 320)}px`;
    this.el.style.height = `${draw ? 110 : Math.max(1, Number(params.height) || 240)}px`;
    const svg = svgElement(this.el, 'svg', 'fx-attack-svg', { viewBox: '0 0 320 240', preserveAspectRatio: 'none', 'aria-hidden': 'true' });
    svg.style.transform = `scaleX(${params.direction === -1 ? -1 : 1})`;
    this.moving = svgElement(svg, 'g', 'fx-attack-moving');
    this.impact = svgElement(svg, 'g', 'fx-attack-impact');
    this.fragments = [];
    if (kind === 'slash') {
      const attrs = { d: 'M 28 206 Q 86 32 292 48', 'stroke-width': 3 * this.strength, pathLength: 1 };
      this.trail = svgElement(this.moving, 'path', 'fx-attack-line', attrs);
      this.trail.style.strokeDasharray = '1';
      svgElement(this.impact, 'path', 'fx-attack-line fx-attack-white', attrs);
    } else if (kind === 'strike') {
      this.falling = svgElement(this.moving, 'g', 'fx-strike-falling');
      svgElement(this.falling, 'path', 'fx-strike-tail', { d: 'M 160 105 L 156 154 L 164 154 Z' });
      svgElement(this.falling, 'ellipse', 'fx-strike-core', { cx: 160, cy: 162, rx: 4 * this.strength, ry: 18 });
      this.flash = svgElement(this.impact, 'ellipse', 'fx-attack-white fx-strike-flash', { cx: 160, cy: 180, rx: 12 * this.strength, ry: 8 * this.strength });
      this.waves = Array.from({ length: this.tier === 'large' ? 2 : 1 }, () => {
        const wave = svgElement(this.impact, 'g', 'fx-strike-wave');
        // 先端へ向かって細くなる2本の筋。地面は viewBox の下から1/4。
        svgElement(wave, 'path', 'fx-strike-ray', { d: `M 160 ${180 - this.strength * 2} L 8 180 L 160 ${180 + this.strength * 2} L 312 180 Z` });
        svgElement(wave, 'ellipse', 'fx-attack-line fx-strike-ring', { cx: 160, cy: 180, rx: 150, ry: 13, 'stroke-width': this.strength });
        return wave;
      });
      this.fragments = Array.from({ length: { small: 0, medium: 4, large: 8 }[this.tier] }, (_, i) =>
        svgElement(this.impact, 'path', 'fx-strike-fragment', { d: `M -3 0 L 0 -${4 + i % 3} L 3 0 L 0 3 Z` }));
    } else {
      this.beam = svgElement(this.moving, 'path', 'fx-attack-line', { d: 'M 0 120 L 218 120', 'stroke-width': 2 * this.strength, pathLength: 1 });
      this.beam.style.strokeDasharray = '1';
      const radius = 16 * this.strength;
      svgElement(this.impact, 'path', 'fx-attack-line fx-attack-white', { d: `M ${218 - radius} 120 L ${218 + radius} 120 M 218 ${120 - radius} L 218 ${120 + radius}`, 'stroke-width': 2 * this.strength });
    }
  }

  function renderAttack(t, kind) {
    const light = this.level === 'light';
    const time = Math.max(0, Math.min(t, this.duration));
    const after = time - 0.8;
    this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
    this.el.style.transform = `translate(-50%, -50%) translateX(${light ? 0 : impactShake(after, this.level, this.tier)}px)`;
    this.moving.style.opacity = light || time >= 0.8 ? '0' : '1';
    this.impact.style.opacity = String(light ? Fx.stillOpacity(after, 0.6)
      : after < 0 ? 0 : 1 - Fx.prog(time, this.duration - 0.15, 0.15));
    const p = Fx.prog(time, 0, 0.8);
    if (kind === 'slash') {
      this.trail.style.strokeDashoffset = String(light ? 0 : 1 - p);
    } else if (kind === 'pierce') {
      this.beam.style.strokeDashoffset = String(light ? 0 : 1 - p);
    } else {
      const fall = light ? 1 : Math.min(time / 0.8, 1) ** 2;
      this.falling.setAttribute('transform', `translate(${-32 * (1 - fall)} ${-190 * (1 - fall)}) rotate(-10 160 180)`);
      this.flash.style.opacity = String(light ? 0 : 1 - Fx.prog(after, 0, 0.18));
      this.waves.forEach((wave, i) => {
        const age = after - i * 0.1;
        const extent = this.tier === 'small' ? 0.5 : 1;
        const spread = light ? extent : Fx.lerp(0.03, extent, Fx.prog(age, 0, 0.42));
        wave.setAttribute('transform', `translate(160 180) scale(${spread} ${light ? 1 : Fx.lerp(0.3, 1, Fx.prog(age, 0, 0.42))}) translate(-160 -180)`);
        wave.style.opacity = String(light ? (i === 0 ? 1 : 0) : Fx.stillOpacity(age, 0.5));
      });
      this.fragments.forEach((fragment, i) => {
        const age = light ? 0 : Fx.prog(after, 0, 0.6);
        const sign = i % 2 ? 1 : -1;
        const x = 160 + sign * (35 + i * 12) * age;
        const y = 180 - (130 + i % 3 * 28) * age + 205 * age * age;
        fragment.setAttribute('transform', `translate(${x} ${y}) rotate(${light ? 0 : sign * age * 160})`);
        fragment.style.opacity = String(light ? 0 : 1 - Fx.prog(after, 0.35, 0.25));
      });
    }
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
      this.shake = params.shake;
      this.delay = Math.max(0, Math.min(0.8, Number(params.delay) || 0));
      this.el = element(root, 'div', `fx-resolve-damage ${params.tone || 'enemy'} ${params.icon ? 'with-icon' : ''}`);
      if (params.icon) {
        const icon = element(this.el, 'img', 'fx-damage-icon');
        icon.setAttribute('src', params.icon);
        icon.setAttribute('alt', params.label || '');
      }
      element(this.el, 'span', 'fx-damage-minus');
      element(this.el, 'span', 'fx-damage-number', String(params.amount));
      // 列の最初の数字は10pxだけ浮き上がり、続く数字は前の数字の下から押し上げと同じ動きで入る。
      this.enter = Number(params.stackEnter) || 10;
      // 列の2つ目以降は、隣の数字にはみ出さないよう、出だしの拡大を控えめにする。
      this.pop = params.stackEnter ? 1.15 : (this.level === 'rich' ? 1.6 : 1.25);
      this.pushes = params.stackPushes || [];
    },
    render(t) {
      const time = t - this.delay;
      const length = this.duration - this.delay;
      const light = this.level === 'light';
      const move = (start) => (light ? (time >= start ? 1 : 0) : Fx.prog(time, start, 0.2));
      const lifted = this.pushes.reduce((sum, push) => sum + push.amount * move(push.at), 0);
      const y = (light ? 0 : this.enter * (1 - move(0))) - lifted;
      const third = this.pushes[2];
      const crowded = third ? 1 - Fx.prog(time, third.at, 0.15) : 1;
      this.el.style.opacity = String(Fx.stillOpacity(time, length) * crowded);
      this.el.style.transform = light ? `translate(-50%, -50%) translateY(${y}px)`
        : `translate(-50%, -50%) translateX(${impactShake(time, this.level, this.shake)}px) translateY(${y}px) scale(${Fx.lerp(this.pop, 1, Fx.prog(time, 0, 0.25))})`;
    },
  });

  Fx.EFFECT_BAND_ROW_HEIGHTS = Object.freeze({ title: 36, result: 28 });
  Fx.define('effect-band', {
    duration: 3.9,
    mount(root, params) {
      this.level = params.level;
      this.side = params.side || 'defender';
      this.duration = params.duration ?? this.duration;
      this.el = element(root, 'div', `fx-effect-band ${this.side}`);
      this.lines = (params.lines || []).map(line => {
        const row = element(this.el, 'div', `fx-effect-${line.kind} ${line.tone || 'enemy'}`);
        if (line.kind === 'title') row.textContent = line.text;
        else {
          element(row, 'span', 'fx-effect-label', String(line.text).replace(/^buff:/, ''));
          if (line.delta !== null && line.delta !== undefined) {
            if (line.delta < 0) element(row, 'span', 'fx-damage-minus');
            element(row, 'span', 'fx-effect-number', `${line.delta > 0 ? '+' : ''}${Math.abs(line.delta)}`);
          }
        }
        row.setAttribute('data-readable', '');
        return { ...line, el: row, height: Fx.EFFECT_BAND_ROW_HEIGHTS[line.kind] };
      });
    },
    render(t) {
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = this.side === 'attacker' ? 'translate(0, -50%)' : 'translate(-100%, -50%)';
      this.lines.forEach((line, i) => {
        const future = this.lines.slice(i + 1);
        const old = future.some(next => next.at <= t);
        const drop = future[2]?.at ?? Infinity;
        const fade = drop === Infinity ? 1 : 1 - Fx.prog(t, drop - 0.12, 0.12);
        line.el.style.opacity = String(Fx.prog(t, line.at, 0.08) * (old ? 0.6 : 1) * fade);
        // 新行と既存行を同じ距離で送る。移動中も矩形の境界を接したまま保つ。
        const y = this.level === 'light' ? -(2 - i % 3) * 36
          : (i ? line.height * (1 - Fx.prog(t, line.at, 0.22)) : 0)
            - future.reduce((sum, next) => sum + next.height * Fx.prog(t, next.at, 0.22), 0);
        const x = this.level === 'light' ? 0 : (this.side === 'attacker' ? -24 : 24) * (1 - Fx.prog(t, line.at, 0.18));
        line.el.style.transform = `translate(${x}px, ${y}px)`;
      });
    },
  });

  Fx.define('ko-shatter', {
    duration: 1.1,
    mount(root, params) {
      this.level = params.level;
      this.el = element(root, 'div', `fx-ko ${params.mode === 'chip' ? 'chip' : ''} ${params.level}`);
      this.el.style.width = `${params.width || 240}px`;
      this.el.style.height = `${params.height || 240}px`;
      this.shade = element(this.el, 'div', 'fx-ko-shade');
      const svg = svgElement(this.el, 'svg', 'fx-ko-svg', { viewBox: '0 0 100 100', 'aria-hidden': 'true' });
      this.face = svgElement(svg, 'path', 'fx-ko-face', { d: 'M 50 5 L 90 30 L 85 75 L 50 95 L 15 75 L 10 30 Z' });
      this.cracks = svgElement(svg, 'path', 'fx-ko-cracks', { d: 'M 50 5 L 48 40 L 25 52 L 15 75 M 48 40 L 62 60 L 85 75 M 62 60 L 50 95 M 48 40 L 90 30', pathLength: 1 });
      this.cracks.style.strokeDasharray = '1';
      this.fragments = Array.from({ length: params.level === 'rich' ? 10 : 6 }, (_, i) => {
        const a = i * Math.PI * 2 / (params.level === 'rich' ? 10 : 6);
        const b = a + 0.48;
        return { el: svgElement(svg, 'path', 'fx-ko-fragment', { d: `M 50 50 L ${50 + Math.cos(a) * 35} ${50 + Math.sin(a) * 35} L ${50 + Math.cos(b) * 36} ${50 + Math.sin(b) * 36} Z` }), angle: a };
      });
      this.label = element(this.el, 'div', 'fx-ko-label', params.mode === 'chip' ? '×' : '戦闘不能');
    },
    render(t) {
      const light = this.level === 'light';
      const p = Fx.prog(t, 0.32, 0.65);
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = 'translate(-50%, -50%)';
      this.face.style.opacity = String(light ? 0.45 : 1 - Fx.prog(t, 0.32, 0.2));
      this.cracks.style.strokeDashoffset = String(light ? 0 : 1 - Fx.prog(t, 0.12, 0.23));
      this.cracks.style.opacity = String(light ? 1 : 1 - Fx.prog(t, 0.5, 0.3));
      this.fragments.forEach((fragment, i) => {
        const x = light ? 0 : Math.cos(fragment.angle) * p * (this.level === 'rich' ? 30 : 20);
        const y = light ? 0 : Math.sin(fragment.angle) * p * 18 + p * p * 30;
        fragment.el.setAttribute('transform', `translate(${x} ${y}) rotate(${light ? 0 : (i % 2 ? 1 : -1) * p * 55} 50 50)`);
        fragment.el.style.opacity = String(light ? 0 : Fx.prog(t, 0.32, 0.08) * (1 - Fx.prog(t, 0.8, 0.3)));
      });
      this.shade.style.opacity = String(light ? 1 : Fx.prog(t, 0.6, 0.18));
      this.label.style.opacity = String(light ? 1 : Fx.prog(t, 0.65, 0.18));
    },
  });

  Fx.define('chat-dice', {
    duration: 1,
    mount(root, params) { mountRoll.call(this, root, params, 0.6, true); },
    render: renderRoll,
  });
})(typeof window !== 'undefined' ? window : globalThis);
