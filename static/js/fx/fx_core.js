// 演出の定義と時刻の計算。アプリに依存しないので、説明動画の部品と共有できる（計画52 §4.2・§4.4）。
// prog / ease / lerp は Egatari（kit/deck.js）の DECK.prog などと同じ式にする。
(function (global) {
  const Fx = global.Fx || (global.Fx = {});
  const definitions = {};

  function clamp01(x) {
    return Math.max(0, Math.min(1, x));
  }

  function ease(x) {
    x = clamp01(x);
    return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
  }

  // 開始 start 秒から dur 秒かけて 0→1 へ進む値。t = Infinity は 1。
  function prog(t, start, dur) {
    if (t === Infinity) return 1;
    if (dur <= 0) return t >= start ? 1 : 0;
    return ease((t - start) / dur);
  }

  function lerp(a, b, e) {
    return a + (b - a) * e;
  }

  // 「軽め」の不透明度：出すときと消すときだけ短くフェードする。
  function stillOpacity(t, duration) {
    return prog(t, 0, 0.15) * (1 - prog(t, duration - 0.15, 0.15));
  }

  // ダメージの数字と効果の浮かび方（計画52）。数字が昇る速さの上限px/秒・減速の時定数秒・
  // 漂う速さpx/秒・濃いまま残す秒・縮み切る倍率（数字・まとまり）・出だしの倍率。
  Fx.FLOAT = Object.freeze({ numberSpeed: 60, glide: 0.5, drift: 12, hold: 0.8, shrink: 0.82, groupShrink: 0.9, enterFrom: 0.6 });

  // 昇った距離。until 秒までは一定の速さ、その後はなめらかに漂う速さへ近づく（速さが段にならない）。
  function floatDistance(t, until, speed = Fx.FLOAT.numberSpeed) {
    const { glide, drift } = Fx.FLOAT;
    const run = Math.max(0, Math.min(t, until)), rest = Math.max(0, t - Math.max(0, until));
    return speed * run + drift * rest + (speed - drift) * glide * (1 - Math.exp(-rest / glide));
  }

  // 読ませた後、表示の終わりまでの薄れの進み（0→1）。短い表示は終わりの0.3秒で進める。
  function lingerProgress(t, duration) {
    const from = Math.max(0, Math.min(Fx.FLOAT.hold, duration - 0.3));
    return clamp01((t - from) / (duration - from));
  }

  // 尾を引いて薄れる：始めに目に見えて薄くなり、終わりは長くかすかに残る。
  function lingerOpacity(t, duration) {
    return prog(t, 0, 0.15) * Math.pow(1 - lingerProgress(t, duration), 2);
  }

  Fx.clamp01 = clamp01;
  Fx.ease = ease;
  Fx.prog = prog;
  Fx.lerp = lerp;
  Fx.stillOpacity = stillOpacity;
  Fx.floatDistance = floatDistance;
  Fx.lingerProgress = lingerProgress;
  Fx.lingerOpacity = lingerOpacity;
  Fx.EFFECT_BAND_ROW_HEIGHTS = Object.freeze({ title: 40, result: 32 });
  // 効果は1行ずつばらして出す：後の行は、前の行がその行の高さ＋ゆとりだけ昇ってから帯の下の端に出る（計画52）。
  Fx.EFFECT_BAND_LAYOUT = Object.freeze({ visibleHeight: 180, slide: 0.3, speed: 80, margin: 8, fadeZone: 36 });
  Fx.layoutEffectBand = function (groups) {
    const config = Fx.EFFECT_BAND_LAYOUT;
    let at = null;
    const placed = groups.map(group => {
      const lines = group.lines.map(line => {
        const height = Fx.EFFECT_BAND_ROW_HEIGHTS[line.kind];
        at = at === null ? 0 : at + (height + config.margin) / config.speed;
        return { ...line, height, at };
      });
      return { ...group, lines, height: lines.reduce((sum, line) => sum + line.height, 0),
        at: lines[0]?.at ?? 0, lastAt: lines.at(-1)?.at ?? 0 };
    });
    // 行が出続ける間は一緒に昇り、最後の行が出た時刻からそろって減速する。
    const lastAt = at ?? 0;
    for (const group of placed) for (const line of group.lines) line.until = lastAt - line.at;
    return { groups: placed, lastAt, stopAt: lastAt + config.slide };
  };
  Fx.define = function (name, definition) {
    definitions[name] = definition;
  };
  Fx.get = function (name) {
    return definitions[name] || null;
  };
})(typeof window !== 'undefined' ? window : globalThis);
