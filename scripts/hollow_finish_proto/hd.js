// 高解像度版（C）：ノイズの霧を3層で流すキャンバスと、縦穴・光・魔素の粒・紋章の封鎖の幕。
(() => {
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 乱数の種から決まる、横につながるノイズ（値ノイズの fBm）を色つきの画像にする。
  function noiseLayer(seed, width, height, {cell, octaves, color, gain, bias}) {
    let s = seed >>> 0;
    const rand = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
    const grids = [];
    for (let o = 0; o < octaves; o++) {
      const cx = Math.max(2, Math.round(width / (cell / 2 ** o)));
      const cy = Math.max(2, Math.round(height / (cell / 2 ** o)));
      grids.push({cx, cy, values: Float32Array.from({length: cx * cy}, rand)});
    }
    const smooth = t => t * t * (3 - 2 * t);
    const sample = ({cx, cy, values}, x, y) => {
      const gx = x / width * cx, gy = y / height * cy;
      const x0 = Math.floor(gx), y0 = Math.floor(gy), tx = smooth(gx - x0), ty = smooth(gy - y0);
      const at = (i, j) => values[((j % cy) + cy) % cy * cx + ((i % cx) + cx) % cx];
      const top = at(x0, y0) + (at(x0 + 1, y0) - at(x0, y0)) * tx;
      const bottom = at(x0, y0 + 1) + (at(x0 + 1, y0 + 1) - at(x0, y0 + 1)) * tx;
      return top + (bottom - top) * ty;
    };
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    const image = ctx.createImageData(width, height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let value = 0, amp = 1, total = 0;
        grids.forEach(grid => { value += sample(grid, x, y) * amp; total += amp; amp *= .5; });
        const alpha = Math.max(0, Math.min(1, (value / total - bias) * gain));
        const i = (y * width + x) * 4;
        image.data[i] = color[0];
        image.data[i + 1] = color[1];
        image.data[i + 2] = color[2];
        image.data[i + 3] = alpha * 255;
      }
    }
    ctx.putImageData(image, 0, 0);
    return canvas;
  }

  // ---- 霧 ----
  let layers, fogCanvas, fogFrame, fogStart = performance.now(), parting = null, glints = [];
  function makeLayers() {
    layers = [
      {img: noiseLayer(11, 512, 128, {cell: 128, octaves: 5, color: [120, 160, 178], gain: 1.5, bias: .38}), speed: 6, alpha: .42, scale: 2},
      {img: noiseLayer(29, 512, 128, {cell: 96, octaves: 5, color: [170, 208, 220], gain: 1.6, bias: .45}), speed: 13, alpha: .32, scale: 1.5},
      {img: noiseLayer(47, 512, 128, {cell: 64, octaves: 4, color: [214, 236, 242], gain: 1.8, bias: .52}), speed: 24, alpha: .22, scale: 1.15},
    ];
  }

  function fogRegion(canvasHost) {
    const rows = [...canvasHost.querySelectorAll('.map-row.is-fog, .map-row.is-revealing')];
    if (!rows.length) return null;
    const host = canvasHost.getBoundingClientRect();
    const first = rows[0].getBoundingClientRect(), last = rows.at(-1).getBoundingClientRect();
    const reveal = canvasHost.querySelector('.map-row.is-revealing')?.getBoundingClientRect();
    return {left: first.left - host.left, top: first.top - host.top, width: first.width,
      height: last.bottom - first.top, reveal: reveal && {top: reveal.top - first.top, height: reveal.height}};
  }

  function drawFog(now) {
    fogFrame = 0;
    if (!fogCanvas?.isConnected || document.body.dataset.fog !== 'hd') return;
    const region = fogRegion(fogCanvas.parentElement);
    if (!region) { fogCanvas.hidden = true; return; }
    fogCanvas.hidden = false;
    const ratio = Math.min(2, devicePixelRatio || 1);
    Object.assign(fogCanvas.style, {left: `${region.left}px`, top: `${region.top}px`, width: `${region.width}px`, height: `${region.height}px`});
    const w = Math.round(region.width * ratio), h = Math.round(region.height * ratio);
    if (fogCanvas.width !== w || fogCanvas.height !== h) { fogCanvas.width = w; fogCanvas.height = h; }
    const ctx = fogCanvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, region.width, region.height);
    const t = reduced() ? 0 : (now - fogStart) / 1000;
    // 地の濃さ：下ほど濃い
    const base = ctx.createLinearGradient(0, 0, 0, region.height);
    base.addColorStop(0, '#1b263600');
    base.addColorStop(.12, '#1b2636cc');
    base.addColorStop(1, '#141c28f2');
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, region.width, region.height);
    // 3つの層を違う速さで流す（遠い層ほど大きく遅い）
    ctx.imageSmoothingQuality = 'high';
    for (const layer of layers) {
      const tileW = layer.img.width * layer.scale, tileH = region.height;
      const offset = (t * layer.speed) % tileW;
      ctx.globalAlpha = layer.alpha;
      for (let x = -offset; x < region.width; x += tileW) ctx.drawImage(layer.img, x, 0, tileW, tileH);
    }
    ctx.globalAlpha = 1;
    // 霧の奥で、ときどき鉱石の光が透ける
    if (!reduced()) {
      if (glints.length < 5 && Math.random() < .02) {
        glints.push({x: Math.random() * region.width, y: region.height * (.25 + Math.random() * .7), born: now, life: 2600 + Math.random() * 1800, r: 10 + Math.random() * 16});
      }
      glints = glints.filter(g => now - g.born < g.life);
      ctx.globalCompositeOperation = 'lighter';
      for (const g of glints) {
        const p = (now - g.born) / g.life, a = Math.sin(p * Math.PI) * .35;
        const glow = ctx.createRadialGradient(g.x, g.y, 0, g.x, g.y, g.r);
        glow.addColorStop(0, `rgba(133,221,221,${a})`);
        glow.addColorStop(1, 'rgba(133,221,221,0)');
        ctx.fillStyle = glow;
        ctx.fillRect(g.x - g.r, g.y - g.r, g.r * 2, g.r * 2);
      }
      ctx.globalCompositeOperation = 'source-over';
    }
    // 晴れる段：中央から左右へ割れて巻き取られる
    if (region.reveal) {
      parting ??= now;
      const p = reduced() ? 1 : Math.min(1, (now - parting) / 1500);
      const ease = 1 - (1 - p) ** 3;
      const {top, height} = region.reveal;
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      const half = region.width / 2 * ease * 1.15;
      const cut = ctx.createLinearGradient(region.width / 2 - half - 40, 0, region.width / 2 + half + 40, 0);
      cut.addColorStop(0, 'rgba(0,0,0,0)');
      cut.addColorStop(.12, 'rgba(0,0,0,1)');
      cut.addColorStop(.88, 'rgba(0,0,0,1)');
      cut.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = cut;
      ctx.fillRect(0, top - 6, region.width, height + 12);
      // 下の段との境目を柔らかく
      const edge = ctx.createLinearGradient(0, top + height - 2, 0, top + height + 26);
      edge.addColorStop(0, `rgba(0,0,0,${ease * .8})`);
      edge.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = edge;
      ctx.fillRect(0, top + height - 2, region.width, 28);
      ctx.restore();
    } else {
      parting = null;
    }
    // 見えている段との境目に、霧の上の縁の淡い光
    const rim = ctx.createLinearGradient(0, (region.reveal ? region.reveal.top + region.reveal.height : 0), 0, (region.reveal ? region.reveal.top + region.reveal.height : 0) + 22);
    rim.addColorStop(0, 'rgba(133,221,221,.22)');
    rim.addColorStop(1, 'rgba(133,221,221,0)');
    ctx.fillStyle = rim;
    ctx.fillRect(0, region.reveal ? region.reveal.top + region.reveal.height : 0, region.width, 22);
    if (!reduced()) fogFrame = requestAnimationFrame(drawFog);
  }

  function syncFog(host, revealing) {
    if (document.body.dataset.fog !== 'hd') {
      fogCanvas?.remove();
      fogCanvas = null;
      cancelAnimationFrame(fogFrame);
      fogFrame = 0;
      return;
    }
    layers ??= (makeLayers(), layers);
    if (!fogCanvas || fogCanvas.parentElement !== host) {
      fogCanvas?.remove();
      fogCanvas = document.createElement('canvas');
      fogCanvas.className = 'fog-canvas';
      fogCanvas.setAttribute('aria-hidden', 'true');
      host.append(fogCanvas);
    }
    if (revealing) parting = null;
    cancelAnimationFrame(fogFrame);
    fogFrame = requestAnimationFrame(drawFog);
  }

  // ---- 封鎖の幕 ----
  // 奥に昏い光の道。その手前へ、宝石の混じった暗い岩が端や奥から突き出して道を塞ぐ。
  const GEMS = ['#5fd0d0', '#9a6ad8', '#c84a5a', '#d9b25a'];
  const VANISH_Y = .44;

  function rockShape(rand, len, width) {
    // 軸は x、根元が 0（画面の外や壁の奥）、先が len。尾根の線と左右の縁で面に分ける。
    const steps = 7;
    const ridge = [], upper = [], lower = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const x = (t * (.94 + rand() * .08)) * len - (i === 0 ? 90 : 0);
      const half = width / 2 * (1 - t * .86) * (.7 + rand() * .5);
      ridge.push([x + (rand() - .5) * len * .03, (rand() - .5) * half * .5]);
      upper.push([x + (rand() - .5) * len * .05, -half]);
      lower.push([x + (rand() - .5) * len * .05, half]);
    }
    const tip = [len * (1.02 + rand() * .05), (rand() - .5) * width * .08];
    const facets = [];
    for (let i = 0; i < steps; i++) {
      for (const [edge, side] of [[upper, -1], [lower, 1]]) {
        const tone = (rand() - .5) * .35;
        facets.push({side, t: i / steps, tone, points: [ridge[i], edge[i], edge[i + 1]]});
        facets.push({side, t: i / steps, tone: tone + (rand() - .5) * .2, points: [ridge[i], edge[i + 1], ridge[i + 1]]});
      }
    }
    facets.push({side: -1, t: 1, tone: .1, points: [ridge[steps], upper[steps], tip]});
    facets.push({side: 1, t: 1, tone: -.1, points: [ridge[steps], lower[steps], tip]});
    const outline = [...upper, tip, ...lower.slice().reverse()];
    const gems = Array.from({length: Math.floor(rand() * 2.4)}, () => {
      const t = .3 + rand() * .45, s = Math.max(5, width * (.03 + rand() * .035));
      return {x: t * len, y: (rand() - .5) * width * .4 * (1 - t), s, color: GEMS[Math.floor(rand() * GEMS.length)], spin: rand() * 3};
    });
    const grain = Array.from({length: 40}, () => {
      const t = rand() * .95;
      return {x: t * len, y: (rand() - .5) * width * (1 - t * .85), r: .6 + rand() * 1.8, light: rand() < .35};
    });
    return {facets, outline, ridge, upper, tip, gems, grain};
  }

  function makeRocks(W, H, seed) {
    let s = seed >>> 0;
    const rand = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
    const cx = W / 2, cy = H * VANISH_Y;
    const rocks = [];
    // 奥の岩：通路の壁・床・天井から生えて、光の口の手前を狭める。根元は壁の闇に溶かす。
    const walls = [[-.2, -.06], [-.17, .1], [.18, -.08], [.2, .08], [-.05, .2], [.07, -.2], [.12, .19], [-.11, -.18]];
    walls.forEach(([dx, dy], i) => {
      const x = cx + dx * W, y = cy + dy * H;
      const tx = cx + (rand() - .5) * W * .05, ty = cy + (rand() - .5) * H * .06;
      const dist = Math.hypot(tx - x, ty - y);
      rocks.push({x, y, angle: Math.atan2(ty - y, tx - x), len: dist * (.7 + rand() * .25), width: 90 + rand() * 70,
        delay: 1500 + i * 110 + rand() * 100, dur: 480, depth: .5, seed: rand()});
    });
    // 手前の岩：画面の端・角・下から勢いよく突き出す
    const anchors = [
      [-.05, .15], [-.05, .5], [-.05, .85], [1.05, .2], [1.05, .55], [1.05, .9], [.15, -.05], [.5, -.06], [.85, -.05],
      [.1, 1.05], [.38, 1.06], [.62, 1.06], [.9, 1.05], [-.04, -.04], [1.04, -.04], [-.04, 1.04], [1.04, 1.04],
    ];
    anchors.forEach(([ax, ay], i) => {
      const x = ax * W + (rand() - .5) * 40, y = ay * H + (rand() - .5) * 40;
      const target = {x: cx + (rand() - .5) * W * .35, y: cy + (rand() - .5) * H * .3};
      const dist = Math.hypot(target.x - x, target.y - y);
      rocks.push({x, y, angle: Math.atan2(target.y - y, target.x - x) + (rand() - .5) * .25,
        len: dist * (.8 + rand() * .32), width: 160 + rand() * 150,
        delay: 2300 + i * 105 + rand() * 160, dur: 380 + rand() * 120, depth: 1, seed: rand()});
    });
    rocks.sort((a, b) => a.depth - b.depth || a.delay - b.delay);
    for (const rock of rocks) {
      let t = Math.floor(rock.seed * 4294967296);
      const r = () => ((t = (t * 1664525 + 1013904223) >>> 0) / 4294967296);
      rock.shape = rockShape(r, rock.len, rock.width);
      // 奥の光の向き（岩の根元から光の口へ）
      const lx = cx - rock.x, ly = cy - rock.y, ll = Math.hypot(lx, ly) || 1;
      rock.light = [lx / ll, ly / ll];
    }
    return rocks;
  }

  const easeOutBack = p => 1 + 2.4 * (p - 1) ** 3 + 1.4 * (p - 1) ** 2;
  const poly = (ctx, points) => {
    ctx.beginPath();
    points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
  };

  function drawRock(ctx, rock, p, now) {
    const {facets, outline, ridge, upper, tip, gems, grain} = rock.shape;
    const slide = (1 - easeOutBack(Math.min(1, p))) * rock.len;
    const far = rock.depth < 1;
    ctx.save();
    ctx.translate(rock.x, rock.y);
    ctx.rotate(rock.angle);
    ctx.translate(-slide, 0);
    const sin = Math.sin(rock.angle), cos = Math.cos(rock.angle);
    // 面ごとの明暗：面の向き（尾根の上側か下側か）と奥の光の向き、先ほど光に近い
    for (const facet of facets) {
      const nx = -facet.side * sin, ny = facet.side * cos;
      const facing = Math.max(0, nx * rock.light[0] + ny * rock.light[1]);
      const lit = Math.max(0, Math.min(1, .04 + facing * .75 + facet.t * .3 + facet.tone)) * (far ? .7 : 1);
      const r = 10 + lit * 120, g = 9 + lit * 92, b = 15 + lit * 140;
      poly(ctx, facet.points);
      ctx.fillStyle = `rgb(${r | 0},${g | 0},${b | 0})`;
      ctx.fill();
      ctx.strokeStyle = `rgba(${r | 0},${g | 0},${b | 0},.9)`;
      ctx.lineWidth = .8;
      ctx.stroke();
    }
    poly(ctx, outline);
    ctx.save();
    ctx.clip();
    for (const g of grain) {
      ctx.fillStyle = g.light ? 'rgba(150,130,180,.12)' : 'rgba(0,0,0,.3)';
      ctx.beginPath();
      ctx.arc(g.x, g.y, g.r, 0, Math.PI * 2);
      ctx.fill();
    }
    // 尾根のかすかな光と、面の境の影
    ctx.beginPath();
    ridge.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.lineTo(...tip);
    ctx.strokeStyle = `rgba(190,165,230,${far ? .1 : .22})`;
    ctx.lineWidth = 1.2;
    ctx.stroke();
    ctx.restore();
    // 光を受けた側の縁
    const upperFacing = Math.max(0, -sin * -1 * rock.light[0] + -1 * cos * rock.light[1]);
    ctx.beginPath();
    [...upper.slice(2), tip].forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.strokeStyle = `rgba(200,170,240,${(far ? .12 : .35) * (.3 + upperFacing)})`;
    ctx.lineWidth = 1.4;
    ctx.stroke();
    for (const gem of gems) {
      const glow = .55 + .25 * Math.sin(now / 700 + gem.spin * 4);
      const shade = far ? .55 : 1;
      ctx.save();
      ctx.translate(gem.x, gem.y);
      ctx.rotate(gem.spin);
      const halo = ctx.createRadialGradient(0, 0, 0, 0, 0, gem.s * 3);
      halo.addColorStop(0, gem.color + Math.round(60 * glow * shade).toString(16).padStart(2, '0'));
      halo.addColorStop(1, gem.color + '00');
      ctx.fillStyle = halo;
      ctx.fillRect(-gem.s * 3, -gem.s * 3, gem.s * 6, gem.s * 6);
      poly(ctx, [[0, -gem.s], [gem.s * .8, 0], [0, gem.s], [-gem.s * .8, 0]]);
      ctx.fillStyle = gem.color;
      ctx.globalAlpha = (.5 + .3 * glow) * shade;
      ctx.fill();
      poly(ctx, [[0, -gem.s], [gem.s * .8, 0], [0, 0]]);
      ctx.fillStyle = '#ffffff';
      ctx.globalAlpha = .2 * glow * shade;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.restore();
    }
    if (far) {
      // 奥の岩は自分だけの層に描かれている。根元を透明へ溶かし、壁から生えて見せる
      ctx.globalCompositeOperation = 'destination-out';
      const fade = ctx.createLinearGradient(-90, 0, rock.len * .5, 0);
      fade.addColorStop(0, 'rgba(0,0,0,1)');
      fade.addColorStop(.6, 'rgba(0,0,0,.6)');
      fade.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = fade;
      ctx.fillRect(-100, -rock.width, rock.len * .5 + 100, rock.width * 2);
      ctx.globalCompositeOperation = 'source-over';
    }
    ctx.restore();
  }

  // 奥へ続く通路と、その先の昏い光の口
  function drawPassage(ctx, W, H, t, fade) {
    const cx = W / 2, cy = H * VANISH_Y;
    const pulse = .85 + .15 * Math.sin(t / 1300);
    const mouthW = W * .045, mouthH = H * .14;
    ctx.save();
    ctx.globalAlpha = fade;
    // 通路の4面：光の口の近くほど明るい
    const faces = [
      [[-W * .1, H], [W * 1.1, H], [cx + mouthW, cy + mouthH / 2], [cx - mouthW, cy + mouthH / 2]],
      [[-W * .1, 0], [W * 1.1, 0], [cx + mouthW, cy - mouthH / 2], [cx - mouthW, cy - mouthH / 2]],
      [[0, -H * .1], [0, H * 1.1], [cx - mouthW, cy + mouthH / 2], [cx - mouthW, cy - mouthH / 2]],
      [[W, -H * .1], [W, H * 1.1], [cx + mouthW, cy + mouthH / 2], [cx + mouthW, cy - mouthH / 2]],
    ];
    faces.forEach((face, i) => {
      const [ax, ay] = [(face[0][0] + face[1][0]) / 2, (face[0][1] + face[1][1]) / 2];
      const g = ctx.createLinearGradient(ax, ay, cx, cy);
      const floor = i === 0;
      g.addColorStop(0, 'rgba(6,6,12,1)');
      g.addColorStop(.7, floor ? `rgba(30,21,48,${pulse})` : `rgba(20,15,32,${pulse})`);
      g.addColorStop(1, floor ? `rgba(80,58,112,${pulse})` : `rgba(52,38,76,${pulse})`);
      poly(ctx, face);
      ctx.fillStyle = g;
      ctx.fill();
    });
    // 床と壁の継ぎ目、奥へ流れる横の目地
    ctx.strokeStyle = 'rgba(140,110,180,.12)';
    ctx.lineWidth = 1;
    for (const [x, y] of [[-W * .1, H], [W * 1.1, H], [-W * .1, 0], [W * 1.1, 0], [W * .3, H], [W * .7, H]]) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(cx + Math.sign(x - cx) * mouthW, cy + Math.sign(y - cy) * mouthH / 2);
      ctx.stroke();
    }
    for (let i = 0; i < 9; i++) {
      const d = ((i + (t / 3500) % 1) / 9) ** 2.2;
      const y = cy + mouthH / 2 + (H - cy - mouthH / 2) * d;
      const half = mouthW + (W * .6 - mouthW) * d;
      ctx.strokeStyle = `rgba(150,120,190,${.05 + d * .08})`;
      ctx.beginPath();
      ctx.moveTo(cx - half, y);
      ctx.lineTo(cx + half, y);
      ctx.stroke();
    }
    // 光の口と、床へこぼれる光
    const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(W, H) * .45);
    halo.addColorStop(0, `rgba(170,130,215,${.34 * pulse})`);
    halo.addColorStop(.1, `rgba(100,66,150,${.2 * pulse})`);
    halo.addColorStop(.4, 'rgba(34,20,56,.1)');
    halo.addColorStop(1, 'rgba(3,4,8,0)');
    ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, W, H);
    const spill = ctx.createLinearGradient(cx, cy, cx, H);
    spill.addColorStop(0, `rgba(160,120,210,${.15 * pulse})`);
    spill.addColorStop(1, 'rgba(170,130,220,0)');
    ctx.fillStyle = spill;
    poly(ctx, [[cx - mouthW, cy + mouthH / 2], [cx + mouthW, cy + mouthH / 2], [cx + W * .22, H], [cx - W * .22, H]]);
    ctx.fill();
    ctx.globalCompositeOperation = 'source-over';
    const mouth = ctx.createLinearGradient(cx, cy - mouthH / 2, cx, cy + mouthH / 2);
    mouth.addColorStop(0, `rgba(120,95,170,${.55 * pulse})`);
    mouth.addColorStop(.5, `rgba(210,190,240,${.72 * pulse})`);
    mouth.addColorStop(1, `rgba(120,95,170,${.55 * pulse})`);
    ctx.fillStyle = mouth;
    ctx.fillRect(cx - mouthW, cy - mouthH / 2, mouthW * 2, mouthH);
    ctx.restore();
  }

  // 奥へ歩いていく視点。奥の岩が出ると歩みが鈍り、手前の岩が突き出すと立ち止まって半歩押し戻される。
  const WALK_END = 1500, STOP_END = 2300, RECOIL_AT = 2600;
  function camera(t) {
    const v = .3 / (WALK_END + (STOP_END - WALK_END) / 2);
    const u = Math.max(0, Math.min(1, (t - WALK_END) / (STOP_END - WALK_END)));
    const z = Math.min(t, WALK_END) * v + v * (STOP_END - WALK_END) * (u - u * u / 2);
    const recoil = t > RECOIL_AT ? .06 * (1 - Math.exp(-(t - RECOIL_AT) / 140)) : 0;
    const stride = 1 - u;
    const step = t / 1000 * Math.PI * 1.8;
    return {scale: 1 + z * 1.25 - recoil, x: Math.sin(step / 2) * 3 * stride, y: (Math.abs(Math.sin(step)) * -6 + 3) * stride};
  }

  function playSeal(screen, done) {
    screen.innerHTML = `<canvas class="hd-shaft" aria-hidden="true"></canvas>
      <div class="hd-title" aria-hidden="true">浅層踏破</div>
      <div class="hd-verdict" role="status"><span>虚夢の深淵、</span><span>未だ立ち入る資格なし</span></div>`;
    screen.classList.add('is-hd');
    const canvas = screen.querySelector('canvas');
    const ctx = canvas.getContext('2d');
    const layer = document.createElement('canvas');
    const layerCtx = layer.getContext('2d');
    const start = performance.now();
    let rocks, size = '', frame, shake = 0, finished = false;
    const dust = [];
    const arrived = new Set();
    const stages = [];
    const later = (ms, fn) => stages.push(setTimeout(fn, ms));
    function finish() {
      if (finished) return;
      finished = true;
      stages.forEach(clearTimeout);
      cancelAnimationFrame(frame);
      screen.onclick = null;
      screen.classList.remove('is-hd', 'is-title', 'is-verdict', 'is-still');
      done();
    }
    function draw(now) {
      const t = now - start;
      const ratio = Math.min(2, devicePixelRatio || 1);
      const W = screen.clientWidth, H = screen.clientHeight;
      if (size !== `${W}x${H}`) {
        size = `${W}x${H}`;
        canvas.width = layer.width = Math.round(W * ratio);
        canvas.height = layer.height = Math.round(H * ratio);
        rocks = makeRocks(W, H, 7);
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      shake *= .9;
      const sx = (Math.random() - .5) * shake, sy = (Math.random() - .5) * shake;
      ctx.translate(sx, sy);
      const fade = Math.min(1, t / 1000);
      ctx.fillStyle = '#030408';
      ctx.fillRect(-20, -20, W + 40, H + 40);
      // 奥の通路と奥の岩は、歩く視点（拡大と揺れ）の中に描く。手前の岩は画面に固定
      const cam = reduced() ? {scale: 1.3, x: 0, y: 0} : camera(t);
      const vx = W / 2, vy = H * VANISH_Y;
      ctx.save();
      ctx.translate(vx + cam.x, vy + cam.y);
      ctx.scale(cam.scale, cam.scale);
      ctx.translate(-vx, -vy);
      drawPassage(ctx, W, H, t, fade);
      const drawFar = rock => {
        layerCtx.setTransform(1, 0, 0, 1, 0, 0);
        layerCtx.clearRect(0, 0, layer.width, layer.height);
        layerCtx.setTransform(ctx.getTransform());
        drawRock(layerCtx, rock, (t - rock.delay) / rock.dur, now);
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(layer, 0, 0);
        ctx.restore();
      };
      for (const rock of rocks) {
        if (rock.depth < 1 && t > rock.delay) drawFar(rock);
      }
      ctx.restore();
      // 岩が突き出した瞬間の揺れと欠片。手前の岩を描く
      for (const [index, rock] of rocks.entries()) {
        const p = (t - rock.delay) / rock.dur;
        if (p <= 0) continue;
        if (p >= .82 && !arrived.has(index)) {
          arrived.add(index);
          shake = Math.min(26, shake + (rock.depth < 1 ? 4 : 11));
          const tipX = rock.x + Math.cos(rock.angle) * rock.len * .7, tipY = rock.y + Math.sin(rock.angle) * rock.len * .7;
          for (let k = 0; k < (rock.depth < 1 ? 0 : 16); k++) {
            const a = Math.random() * Math.PI * 2, v = 40 + Math.random() * 160;
            dust.push({x: tipX, y: tipY, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 30, born: now, r: 1 + Math.random() * 2.5});
          }
        }
        if (rock.depth === 1) drawRock(ctx, rock, p, now);
      }
      // 砕けた欠片と砂埃
      for (const d of dust) {
        const s = (now - d.born) / 1000;
        if (s > 1.4) continue;
        ctx.fillStyle = `rgba(120,110,130,${(1 - s / 1.4) * .8})`;
        ctx.beginPath();
        ctx.arc(d.x + d.vx * s, d.y + d.vy * s + 120 * s * s, d.r, 0, Math.PI * 2);
        ctx.fill();
      }
      // 文字の間は全体を少し沈める
      if (screen.classList.contains('is-title') || screen.classList.contains('is-verdict')) {
        ctx.fillStyle = 'rgba(3,4,8,.45)';
        ctx.fillRect(-20, -20, W + 40, H + 40);
      }
      frame = requestAnimationFrame(draw);
    }
    if (reduced()) {
      // 最後の形（岩で塞がれた道）を止めて見せ、文字を順に出す
      screen.classList.add('is-still');
      frame = requestAnimationFrame(now => { draw(now + 6000); cancelAnimationFrame(frame); });
      later(300, () => screen.classList.add('is-title'));
      later(2600, () => { screen.classList.remove('is-title'); screen.classList.add('is-verdict'); });
      later(6000, finish);
    } else {
      frame = requestAnimationFrame(draw);
      later(4900, () => screen.classList.add('is-title'));
      later(8800, () => { screen.classList.remove('is-title'); screen.classList.add('is-verdict'); });
      later(13800, finish);
    }
    screen.onclick = finish;
  }

  window.HollowHD = {syncFog, playSeal};
})();
