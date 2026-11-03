// 計画52 PR5の試作：宝石の加護（案B 砕ける宝石）と戦闘の終わりの控えめな飾り。本番のバンドルには入らない。
// 本番の演出と同じく、render(t) の時刻と引数だけで描く（乱れは番号から決める）。
(function () {
  const Fx = window.Fx;
  const lin = (t, s, d) => Fx.clamp01((t - s) / d);
  const rnd = (i, k) => { const x = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453; return x - Math.floor(x); };
  const GEMS = ['#ffe08a', '#bfe8ff', '#ff9cc4', '#c4b0ff', '#9ff3d0'];
  const GOLD = '#ffd56a';
  const MIN_FIT = 0.55;

  function el(parent, tag, cls, text) {
    const node = parent.ownerDocument.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node);
    return node;
  }
  function canvasOn(root, w, h, x = 0, y = 0) {
    const c = el(root, 'canvas', 'p5-canvas');
    const dpr = Math.min(2, root.ownerDocument.defaultView.devicePixelRatio || 1);
    c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    Object.assign(c.style, { position: 'absolute', left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px`, pointerEvents: 'none' });
    return { c, ctx: c.getContext('2d'), dpr, w, h };
  }
  function begin(cv) {
    const ctx = cv.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.c.width, cv.c.height);
    ctx.setTransform(cv.dpr, 0, 0, cv.dpr, 0, 0);
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.lineWidth = 1; ctx.lineCap = 'round';
    return ctx;
  }
  function poly(ctx, points) {
    ctx.beginPath();
    points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
  }
  function glow(ctx, x, y, r, color, alpha) {
    if (!(r > 0 && alpha > 0)) return;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `color-mix(in srgb, #ffffff ${alpha * 100}%, transparent)`);
    g.addColorStop(0.25, `color-mix(in srgb, ${color} ${alpha * 70}%, transparent)`);
    g.addColorStop(1, 'transparent');
    ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  // 4つの光の先を持つきらめき。
  function sparkle(ctx, x, y, r, color, alpha) {
    if (!(alpha > 0.01)) return;
    glow(ctx, x, y, r * 2.4, color, alpha * 0.5);
    ctx.globalAlpha = alpha; ctx.fillStyle = '#ffffff';
    poly(ctx, [[x, y - r * 1.6], [x + r * 0.22, y - r * 0.22], [x + r * 1.6, y], [x + r * 0.22, y + r * 0.22],
      [x, y + r * 1.6], [x - r * 0.22, y + r * 0.22], [x - r * 1.6, y], [x - r * 0.22, y - r * 0.22]]);
    ctx.fill(); ctx.globalAlpha = 1;
  }

  // 字の形だけを光らせる帯。下書きのCanvasに字を書き、そこへ斜めの光を重ねてから写す。p は左から右への進み（0〜1）。
  function textShine(ctx, mask, dpr, box, label, p, width, alpha, tint = '255,250,225') {
    // 配置が決まる前に測ると幅0の下書きになり、写すと例外で再生が止まる。その時は描かない。
    if (!mask.width || !mask.height) return 0;
    const m = mask.getContext('2d');
    m.setTransform(1, 0, 0, 1, 0, 0); m.clearRect(0, 0, mask.width, mask.height);
    m.setTransform(dpr, 0, 0, dpr, 0, 0); m.globalCompositeOperation = 'source-over';
    m.font = label.font; m.letterSpacing = label.spacing; m.textAlign = 'center'; m.textBaseline = 'middle'; m.fillStyle = '#fff';
    m.fillText(label.text, box.w / 2 + parseFloat(label.spacing) / 2, box.h / 2);
    const x = Fx.lerp(-width * 2, box.w + width * 2, p);
    const g = m.createLinearGradient(x - width, box.h, x + width * 0.6, 0);
    g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(0.5, `rgba(${tint},${alpha})`); g.addColorStop(1, 'rgba(255,255,255,0)');
    m.globalCompositeOperation = 'source-in'; m.fillStyle = g; m.fillRect(0, 0, box.w, box.h);
    ctx.drawImage(mask, box.x, box.y, box.w, box.h);
    glow(ctx, box.x + x, box.y + box.h / 2, box.h * 0.9, GOLD, 0.3 * alpha * Math.sin(Math.PI * p));
    return x;
  }
  function textMask(root, box, dpr) {
    const mask = root.ownerDocument.createElement('canvas');
    mask.width = Math.ceil(box.w * dpr); mask.height = Math.ceil(box.h * dpr);
    return mask;
  }

  // ---- 宝石の加護（案B）：宝石が砕けて加護が降りる ----
  // mode 'full'：宣言の間、戦闘画面の全体（1.6秒）。小さく「宝石の加護」＋大きくスキル名（表記1、決定）。
  // mode 'band'：解決の中、使った側の半分（1.2秒）。直後にスキル名の札が出るので「宝石の加護」だけを出す。
  function gemFacets(cx, cy, R, turn) {
    const outer = Array.from({ length: 6 }, (_, i) => [cx + Math.cos(turn + i * Math.PI / 3) * R, cy + Math.sin(turn + i * Math.PI / 3) * R * 0.92]);
    const inner = Array.from({ length: 6 }, (_, i) => [cx + Math.cos(turn + i * Math.PI / 3) * R * 0.5, cy + Math.sin(turn + i * Math.PI / 3) * R * 0.46]);
    const facets = [];
    for (let i = 0; i < 6; i++) {
      const j = (i + 1) % 6;
      facets.push([outer[i], outer[j], inner[j]], [outer[i], inner[j], inner[i]], [[cx, cy], inner[i], inner[j]]);
    }
    return facets;
  }
  Fx.define('proto-gem-b', {
    duration: 1.6,
    mount(root, params) {
      this.mode = params.mode || 'full';
      const full = this.mode === 'full';
      this.duration = full ? 1.6 : 1.2;
      this.w = params.width; this.h = params.height; this.level = params.level || 'normal';
      this.target = params.target || { x: this.w / 2, y: this.h * 0.55 };
      Object.assign(root.style, { position: 'absolute', left: '0', top: '0', width: `${this.w}px`, height: `${this.h}px`, overflow: 'hidden', pointerEvents: 'none' });
      if (full) {
        this.dim = el(root, 'div', 'p5-dim');
        // 使った人の名前は立ち絵の有無にかかわらず陣営の色の光で大きく出す。
        // 立ち絵ありは立ち絵の下寄り、立ち絵なしは人の姿の代わりに胸の高さへ、より大きく出す。
        if (params.image) { this.figure = el(root, 'img', 'p5-b-figure'); this.figure.src = params.image; this.figure.alt = ''; }
        this.name = el(root, 'div', `p5-namecard ${params.team || 'ally'}`, params.actorName || '');
        this.name.style.fontSize = `${this.h * (params.image ? 0.09 : 0.13)}px`;
        this.nameFit = Math.max(MIN_FIT, Math.min(1, this.w * 0.7 / Math.max(1, this.name.scrollWidth)));
      }
      this.cv = canvasOn(root, this.w, this.h);
      this.text = el(root, 'div', 'p5-b-text');
      if (full) el(this.text, 'div', 'p5-label', '宝石の加護');
      this.title = el(this.text, 'div', 'p5-title', full ? params.skillName : '宝石の加護');
      // 置き場所の幅に収まるまで字を小さくする（下限55%）。mountで一度だけ測る。
      this.fontSize = full ? this.h * 0.1 : this.h * 0.085;
      this.text.style.fontSize = `${this.fontSize}px`;
      const maxWidth = full ? this.w * 0.78 : this.w * 0.86;
      this.fit = Math.max(MIN_FIT, Math.min(1, maxWidth / Math.max(1, this.title.scrollWidth)));
      // 縮めるのはスキル名だけ。上の「宝石の加護」の字の大きさは保つ。
      this.title.style.fontSize = `${this.fit}em`;
      this.root = root;
    },
    render(t) {
      const done = t >= this.duration;
      const T = done ? 1.6 : Math.max(0, t) * 1.6 / this.duration;
      const w = this.w, h = this.h, full = this.mode === 'full', rich = this.level === 'rich';
      const out = 1 - Fx.prog(T, 1.32, 0.26);
      this.root.style.visibility = done || t <= 0 ? 'hidden' : '';
      if (this.dim) this.dim.style.opacity = String(0.66 * Fx.prog(T, 0, 0.14) * out);
      const cx = full ? w / 2 : this.target.x, cy = full ? h * 0.44 : this.target.y - h * 0.18;
      const R = (full ? h * 0.14 : h * 0.085) * (Fx.prog(T, 0.06, 0.3) * (1 + 0.12 * Math.sin(Math.PI * lin(T, 0.06, 0.3))));
      const turn = -Math.PI / 2 + 0.25 * lin(T, 0, 0.6);
      const ctx = begin(this.cv);
      if (T < 0.6 && R > 0.5) {
        glow(ctx, cx, cy, R * (2 + 2.5 * lin(T, 0.2, 0.38)), GEMS[1], 0.25 + 0.5 * lin(T, 0.2, 0.38));
        gemFacets(cx, cy, R, turn).forEach((tri, i) => {
          const shade = [0.95, 0.7, 0.85][i % 3] - (Math.floor(i / 3) % 2) * 0.12 + 0.15 * Math.sin(T * 9 + i);
          ctx.fillStyle = `color-mix(in srgb, #7fd8ff ${Math.round(shade * 100)}%, #3a2a8a)`;
          poly(ctx, tri); ctx.fill();
          ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 1; ctx.stroke();
        });
        // 表面を流れる光。
        ctx.globalCompositeOperation = 'lighter';
        glow(ctx, cx + Fx.lerp(-R, R, lin(T, 0.25, 0.25)), cy - R * 0.3, R * 0.6, '#ffffff', 0.8 * Math.sin(Math.PI * lin(T, 0.25, 0.25)));
        // ひび：中心から頂点へ走る。
        const crack = lin(T, 0.46, 0.13);
        if (crack > 0) {
          ctx.strokeStyle = '#ffffff'; ctx.lineWidth = full ? 2.2 : 1.4;
          for (let i = 0; i < 7; i++) {
            const a = turn + rnd(i, 61) * Math.PI * 2, len = R * (0.6 + rnd(i, 62) * 0.5) * crack;
            ctx.beginPath(); ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.cos(a + 0.2) * len * 0.5, cy + Math.sin(a + 0.2) * len * 0.5);
            ctx.lineTo(cx + Math.cos(a) * len, cy + Math.sin(a) * len); ctx.stroke();
          }
          glow(ctx, cx, cy, R * 1.6, '#ffffff', 0.6 * crack);
        }
      }
      ctx.globalCompositeOperation = 'lighter';
      if (T >= 0.6) {
        const age = T - 0.6, R0 = full ? h * 0.14 : h * 0.085;
        // 白い閃光と放射の光。
        glow(ctx, cx, cy, (full ? w * 0.4 : h * 0.7), GEMS[1], 1 - lin(age, 0, 0.18));
        for (let i = 0; i < (full ? 14 : 8); i++) {
          const a = rnd(i, 71) * Math.PI * 2, p = lin(age, 0, 0.22), len = (full ? h * 0.7 : h * 0.45) * (0.4 + p) * (0.6 + rnd(i, 72) * 0.6);
          ctx.globalAlpha = 0.8 * (1 - p); ctx.fillStyle = '#ffffff';
          poly(ctx, [[cx + Math.cos(a + 1.57) * 3, cy + Math.sin(a + 1.57) * 3], [cx + Math.cos(a) * len, cy + Math.sin(a) * len], [cx - Math.cos(a + 1.57) * 3, cy - Math.sin(a + 1.57) * 3]]);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
        // 破片：面がそのまま外へ飛び、回りながら薄れる。
        gemFacets(cx, cy, R0, turn).forEach((tri, i) => {
          const mx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3, my = (tri[0][1] + tri[1][1] + tri[2][1]) / 3;
          const a = Math.atan2(my - cy, mx - cx) + (rnd(i, 81) - 0.5) * 0.6, v = (full ? 520 : 260) * (0.5 + rnd(i, 82));
          const d = v * (age - age * age * 0.9), alpha = 1 - lin(age, 0.1, 0.38);
          if (alpha <= 0) return;
          ctx.save(); ctx.translate(mx + Math.cos(a) * d, my + Math.sin(a) * d + 120 * age * age); ctx.rotate((rnd(i, 83) - 0.5) * 9 * age);
          ctx.globalAlpha = alpha; ctx.fillStyle = GEMS[(i % 4) + 1];
          poly(ctx, tri.map(([x, y]) => [x - mx, y - my])); ctx.fill(); ctx.restore();
        });
        ctx.globalAlpha = 1;
        // 光の粒が使った人の胸へ吸い込まれる。
        const tx = this.target.x, ty = this.target.y, n = Math.round((full ? 56 : 24) * (rich ? 1.3 : 1));
        for (let i = 0; i < n; i++) {
          const p = lin(age, 0.12 + rnd(i, 91) * 0.25, 0.32 + rnd(i, 92) * 0.12);
          if (p <= 0 || p >= 1) continue;
          const a = rnd(i, 93) * Math.PI * 2, r0 = R0 * (1.6 + rnd(i, 94) * 2.2), e = p * p;
          const bend = Math.sin(Math.PI * p) * (rnd(i, 95) - 0.5) * R0 * 2;
          sparkle(ctx, Fx.lerp(cx + Math.cos(a) * r0, tx, e) + bend, Fx.lerp(cy + Math.sin(a) * r0, ty, e), (full ? 4 : 2.6) * (1 - p * 0.4), GEMS[i % 5], Math.min(1, (1 - p) * 3));
        }
        glow(ctx, tx, ty, (full ? h * 0.3 : h * 0.22), GEMS[0], 0.55 * Math.sin(Math.PI * lin(age, 0.35, 0.5)) * out);
      }
      if (this.name) {
        const arrive = lin(T, 0.6, 0.6), appear = Fx.prog(T, 0.55, 0.25) * out;
        const filter = `brightness(${1 + 1.4 * Math.sin(Math.PI * Fx.clamp01(arrive * 1.2))}) drop-shadow(0 0 24px rgba(191,232,255,${0.6 * arrive}))`;
        if (this.figure) Object.assign(this.figure.style, { opacity: String(appear), filter, height: `${h * 0.74}px`, left: `${this.target.x}px`, bottom: '0' });
        Object.assign(this.name.style, { opacity: String(appear), filter: this.figure ? '' : filter, left: `${this.target.x}px`,
          top: `${this.figure ? h * 0.86 : this.target.y}px`, transform: `translate(-50%, -50%) scale(${this.nameFit * Fx.lerp(1.15, 1, Fx.prog(T, 0.55, 0.3))})` });
      }
      // 文字：宝石が砕けた後に、暗い帯の上へ出る。
      const show = Fx.prog(T, 0.72, 0.18);
      Object.assign(this.text.style, { left: `${full ? w / 2 : this.target.x}px`, top: `${full ? h * 0.12 : this.target.y + h * 0.34}px`,
        opacity: String(show * out), transform: `translate(-50%, -50%) scale(${Fx.lerp(1.2, 1, show)})` });
    },
  });

  // ---- 戦闘の終わり：今のカードの上に重ねる控えめな飾り ----
  // 勝利：見出しの字の上だけを光の帯が1本走り、縁が一度光り、金のきらめきが少し立ちのぼる（1.8秒）。
  // 敗北：見出しが少し沈んで暗くなり、上から浅い暗さが降りる。沈んだ姿はカードが閉じるまで（4.2秒）保つ。
  Fx.define('proto-conclusion', {
    duration: 1.8,
    mount(root, params) {
      this.outcome = params.outcome;
      this.duration = this.outcome === 'defeat' ? 4.2 : 1.8;
      this.card = params.card; this.title = params.titleBox; this.pad = 140;
      this.titleEl = params.titleEl;
      this.original = this.titleEl ? { translate: this.titleEl.style.translate, filter: this.titleEl.style.filter } : null;
      const { x, y, w, h } = this.card;
      this.cv = canvasOn(root, w + this.pad * 2, h + this.pad * 2, x - this.pad, y - this.pad);
      this.label = { text: params.text, font: params.font, spacing: params.letterSpacing || '0px' };
      this.mask = textMask(root, this.title, this.cv.dpr);
    },
    render(t) {
      const ctx = begin(this.cv);
      if (this.titleEl) Object.assign(this.titleEl.style, this.original);
      if (t <= 0 || t >= this.duration || !['victory', 'defeat'].includes(this.outcome)) return;
      ctx.translate(this.pad - this.card.x, this.pad - this.card.y);
      const c = this.card, tb = this.title;
      if (this.outcome === 'victory') {
        ctx.globalCompositeOperation = 'lighter';
        // 縁の光：カードが出た瞬間に一度光る。
        ctx.strokeStyle = GOLD; ctx.lineWidth = 2; ctx.globalAlpha = 0.5 * (1 - lin(t, 0.1, 0.9));
        ctx.beginPath(); ctx.roundRect(c.x - 2, c.y - 2, c.w + 4, c.h + 4, 15); ctx.stroke();
        ctx.globalAlpha = 1;
        // 見出しの字の上を光の帯が左から右へ走る。字の形で切り抜く。
        const p = lin(t, 0.15, 0.55);
        if (p > 0 && p < 1) textShine(ctx, this.mask, this.cv.dpr, tb, this.label, p, 50, 0.9);
        // カードの周りから金のきらめきが少し立ちのぼる。
        const out = 1 - Fx.prog(t, 1.5, 0.3);
        for (let i = 0; i < 26; i++) {
          const born = 0.1 + rnd(i, 21) * 1.15, life = 0.6 + rnd(i, 22) * 0.4, age = t - born;
          if (age < 0 || age > life) continue;
          const edge = rnd(i, 23), along = rnd(i, 24);
          const [x0, y0] = edge < 0.5 ? [c.x + along * c.w, c.y + c.h] : edge < 0.75 ? [c.x - 10, c.y + along * c.h] : [c.x + c.w + 10, c.y + along * c.h];
          const e = age / life;
          sparkle(ctx, x0 + (rnd(i, 25) - 0.5) * 30 * age + Math.sin(age * 5 + i) * 8, y0 - (50 + rnd(i, 26) * 110) * age,
            (1.8 + rnd(i, 27) * 1.8) * (1 - e * 0.5), GOLD, Math.min(1, (1 - e) * 1.6) * (0.65 + 0.35 * Math.sin(age * 22 + i)) * out);
        }
      } else {
        // 敗北：見出しが少し沈んで暗くなる。0.15秒から0.85秒かけて沈み、その姿を保つ。
        const sink = Fx.prog(t, 0.15, 0.85);
        if (this.titleEl) Object.assign(this.titleEl.style, { translate: `0 ${8 * sink}px`, filter: `brightness(${1 - 0.32 * sink}) saturate(${1 - 0.25 * sink})` });
        // 上から浅い暗さが降りる。
        const g = ctx.createLinearGradient(0, c.y, 0, c.y + c.h);
        g.addColorStop(0, `rgba(4,6,14,${0.3 * sink})`); g.addColorStop(Math.max(0.01, sink * 0.8), `rgba(4,6,14,${0.14 * sink})`); g.addColorStop(1, 'rgba(4,6,14,0)');
        ctx.fillStyle = g; ctx.beginPath(); ctx.roundRect(c.x, c.y, c.w, c.h, 14); ctx.fill();
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    },
  });

  // ---- ラウンド開始のバナー（今のround-bannerに重ねる飾り、1.8秒）----
  // mode 'sweep'＝字の上を光の帯が走る。'sparkle'＝枠の縁から宝石の色の粒がはじけて漂う。
  Fx.define('proto-banner-shine', {
    duration: 1.8,
    mount(root, params) {
      this.mode = params.mode; this.box = params.box; this.pad = 160;
      const { x, y, w, h } = this.box;
      this.cv = canvasOn(root, w + this.pad * 2, h + this.pad * 2, x - this.pad, y - this.pad);
      this.label = { text: params.text, font: params.font, spacing: params.letterSpacing || '0px' };
      this.textBox = params.textBox;
      this.mask = textMask(root, this.textBox, this.cv.dpr);
    },
    render(t) {
      const ctx = begin(this.cv);
      if (t <= 0 || t >= this.duration) return;
      ctx.translate(this.pad - this.box.x, this.pad - this.box.y);
      ctx.globalCompositeOperation = 'lighter';
      const b = this.box, out = 1 - Fx.prog(t, 1.404, 0.396);
      if (this.mode === 'sweep') {
        // バナーが落ち着いた0.36秒から、字の上を金の光が1本走る（白い字なので金で染め、外にも光をにじませる）。
        const p = lin(t, 0.36, 0.6);
        if (p > 0 && p < 1) {
          const x = textShine(ctx, this.mask, this.cv.dpr, this.textBox, this.label, p, 46, 1, '255,196,70');
          glow(ctx, this.textBox.x + x, this.textBox.y + this.textBox.h / 2, this.textBox.h * 1.6, GOLD, 0.45 * Math.sin(Math.PI * p));
        }
      } else {
        // 出た瞬間に枠の縁から宝石の色の粒がはじけ、ゆっくり漂って消える。四隅に光の点。
        for (let i = 0; i < 40; i++) {
          const born = 0.12 + rnd(i, 51) * 0.18, life = 0.7 + rnd(i, 52) * 0.6, age = t - born;
          if (age < 0 || age > life) continue;
          const along = rnd(i, 53), top = i % 2;
          const x0 = b.x + along * b.w, y0 = top ? b.y : b.y + b.h;
          const vx = (along - 0.5) * 120, vy = (top ? -1 : 1) * (40 + rnd(i, 54) * 70);
          const drag = 1 - Math.min(1, age * 0.9), e = age / life;
          sparkle(ctx, x0 + vx * age * drag, y0 + vy * age * drag - 14 * age, (2.8 + rnd(i, 55) * 3.4) * (1 - e * 0.5), GEMS[i % 5],
            Math.min(1, (1 - e) * 1.6) * (0.65 + 0.35 * Math.sin(age * 20 + i)) * out);
        }
        const corner = Math.sin(Math.PI * lin(t, 0.2, 0.7));
        for (const [cx, cy] of [[b.x, b.y], [b.x + b.w, b.y], [b.x, b.y + b.h], [b.x + b.w, b.y + b.h]]) sparkle(ctx, cx, cy, 6, GEMS[1], corner * out);
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    },
  });
}());
