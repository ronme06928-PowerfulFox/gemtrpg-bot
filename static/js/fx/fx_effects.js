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
      // 結果の段階では、出た後も枠の終わり（戦闘不能の対象は割れる時刻）まで残す長さを受け取る。
      this.duration = params.duration ?? this.duration;
      this.leaveAt = params.leaveAt;
      this.delay = Math.max(0, Math.min(0.8, Number(params.delay) || 0));
      this.el = element(root, 'div', `fx-resolve-damage ${params.tone || 'enemy'} ${params.icon ? 'with-icon' : ''} ${params.mode === 'chip' ? 'chip' : ''}`);
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
        : `translate(-50%, -50%) translateX(${impactShake(time, this.level, this.shake)}px) translateY(${y}px) scale(${swell * Fx.lerp(1, Fx.FLOAT.shrink, fading)})`;
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
