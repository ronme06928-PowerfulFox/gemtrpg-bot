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

  // ダメージの数字と効果の不透明度：1秒は読ませ、残りで静かに薄れて終わりに0になる（計画52）。
  function lingerOpacity(t, duration, hold = 1) {
    const from = Math.max(0, Math.min(hold, duration - 0.3));
    const x = clamp01((t - from) / (duration - from));
    return prog(t, 0, 0.15) * (1 - x * x);
  }

  Fx.clamp01 = clamp01;
  Fx.ease = ease;
  Fx.prog = prog;
  Fx.lerp = lerp;
  Fx.stillOpacity = stillOpacity;
  Fx.lingerOpacity = lingerOpacity;
  Fx.EFFECT_BAND_ROW_HEIGHTS = Object.freeze({ title: 36, result: 28 });
  Fx.EFFECT_BAND_LAYOUT = Object.freeze({ speed: 200, deceleration: 0.4, visibleHeight: 180, slide: 0.12, gap: 8 });
  Fx.layoutEffectBand = function (groups) {
    const config = Fx.EFFECT_BAND_LAYOUT;
    let offset = 0;
    const placed = groups.map((group, i) => {
      const height = group.lines.reduce((sum, row) => sum + Fx.EFFECT_BAND_ROW_HEIGHTS[row.kind], 0);
      if (i) offset += height + config.gap;
      return { ...group, height, offset, at: offset / config.speed };
    });
    const cruiseUntil = (placed.at(-1)?.at || 0) + config.slide;
    return { groups: placed, cruiseUntil, stopAt: cruiseUntil + config.deceleration,
      stopDistance: config.speed * (cruiseUntil + config.deceleration / 2) };
  };
  Fx.bandDistance = function (t, layout) {
    const { speed, deceleration } = Fx.EFFECT_BAND_LAYOUT;
    if (t >= layout.stopAt) return layout.stopDistance;
    const cruise = Math.max(0, Math.min(t, layout.cruiseUntil));
    const slow = Math.max(0, Math.min(t - layout.cruiseUntil, deceleration));
    return speed * (cruise + slow - slow * slow / (2 * deceleration));
  };
  Fx.define = function (name, definition) {
    definitions[name] = definition;
  };
  Fx.get = function (name) {
    return definitions[name] || null;
  };
})(typeof window !== 'undefined' ? window : globalThis);
