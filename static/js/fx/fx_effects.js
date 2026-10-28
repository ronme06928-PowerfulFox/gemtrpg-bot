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

  Fx.define('power-roll', {
    duration: 1,
    mount(root, params) {
      this.level = params.level;
      this.text = String(params.text);
      this.el = element(root, 'div', 'fx-power-roll', this.text);
      this.el.style.width = `${params.width}px`;
      this.el.style.height = `${params.height}px`;
    },
    render(t) {
      const time = Math.max(0, Math.min(t, this.duration));
      const roll = this.level !== 'light' && time < 0.7;
      this.el.textContent = roll ? String((Math.floor(time * 47) * 7 + 3) % 20 + 1) : this.text;
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = this.level === 'light' ? 'translate(-50%, -50%)'
        : `translate(-50%, -50%) rotateX(${roll ? time * (this.level === 'rich' ? 2200 : 1400) : 0}deg)`;
    },
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
      this.el = element(root, 'div', `fx-attack-flash ${params.level}`);
    },
    render(t) {
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = this.level === 'light' ? 'translate(-50%, -50%)'
        : `translate(-50%, -50%) rotate(-28deg) scaleX(${Fx.lerp(this.level === 'rich' ? 0.1 : 0.3, 1.6, Fx.prog(t, 0, this.duration))})`;
    },
  });

  Fx.define('resolve-damage', {
    duration: 1.6,
    mount(root, params) {
      this.level = params.level;
      this.delay = Math.max(0, Math.min(0.8, Number(params.delay) || 0));
      this.el = element(root, 'div', `fx-resolve-damage ${params.tone || 'enemy'} ${params.icon ? 'with-icon' : ''}`);
      this.el.style.marginTop = `${24 + (Number(params.row) || 0) * 34}px`;
      if (params.icon) {
        const icon = element(this.el, 'img', 'fx-damage-icon');
        icon.setAttribute('src', params.icon);
        icon.setAttribute('alt', params.label || '');
      }
      element(this.el, 'span', 'fx-damage-minus');
      element(this.el, 'span', 'fx-damage-number', String(params.amount));
    },
    render(t) {
      const time = t - this.delay;
      const length = this.duration - this.delay;
      const p = Fx.prog(time, 0, length);
      this.el.style.opacity = String(Fx.stillOpacity(time, length));
      this.el.style.transform = this.level === 'light' ? 'translate(-50%, -50%)'
        : `translate(-50%, -50%) translateY(${Fx.lerp(12, -34, p)}px) scale(${Fx.lerp(this.level === 'rich' ? 1.6 : 1.25, 1, Fx.prog(time, 0, 0.25))})`;
    },
  });

  Fx.define('chat-dice', {
    duration: 0.8,
    mount(root, params) {
      this.level = params.level;
      this.images = params.images;
      this.el = element(root, 'span', 'fx-chat-dice');
      this.die = element(this.el, 'img', 'fx-chat-die');
      this.die.setAttribute('alt', '');
      this.total = element(this.el, 'span', 'fx-chat-total', params.text);
    },
    render(t) {
      const time = Math.max(0, Math.min(t, this.duration));
      const light = this.level === 'light';
      const showTotal = light || time >= 0.45;
      this.el.style.opacity = String(Fx.stillOpacity(t, this.duration));
      this.el.style.transform = light ? 'translate(0, 0)'
        : `translateY(${showTotal ? 0 : -Math.abs(Math.sin(time * 24)) * (this.level === 'rich' ? 7 : 3)}px)`;
      this.die.setAttribute('src', this.images[Math.floor(time * 22) % this.images.length]);
      this.die.style.opacity = showTotal ? '0' : '1';
      this.die.style.transform = light || showTotal ? 'rotate(0deg)' : `rotate(${time * (this.level === 'rich' ? 1200 : 720)}deg)`;
      this.total.style.opacity = showTotal ? '1' : '0';
    },
  });
})(typeof window !== 'undefined' ? window : globalThis);
