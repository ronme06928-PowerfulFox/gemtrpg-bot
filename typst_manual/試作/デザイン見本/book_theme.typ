// 計画46・デザイン見本（2026-10-21）。章ごとに宝石の色を割り当てる案。
// 本文サイズ・余白・段落間隔は4CのC案を維持し、色・見出し・図の部品だけを変える。

#let ink = rgb("253345")
#let muted = rgb("647080")

// 章の色。名前は章扉に表示する。
#let gems = (
  "0": (shape: "quartz", name: "水晶", main: rgb("4f6d84"), light: rgb("edf2f6")),
  "1": (shape: "diamond", name: "ダイヤモンド", main: rgb("6c8aa3"), light: rgb("eef3f7")),
  "2": (shape: "topaz", name: "トパーズ", main: rgb("b06a17"), light: rgb("fbf1e4")),
  "3": (shape: "emerald", name: "エメラルド", main: rgb("1b7a54"), light: rgb("e6f3ed")),
  "4": (shape: "ruby", name: "ルビー", main: rgb("ad2840"), light: rgb("fbeaed")),
  "5": (shape: "sapphire", name: "サファイア", main: rgb("1f4fa3"), light: rgb("e8eef9")),
  "6": (shape: "amethyst", name: "アメジスト", main: rgb("71479e"), light: rgb("f1ebf8")),
  "7": (shape: "citrine", name: "シトリン", main: rgb("97760a"), light: rgb("faf4dd")),
  "A": (shape: "onyx", name: "オニキス", main: rgb("2c2f36"), light: rgb("eceef1")),
)
// 選べる宝石の一覧。章や編への割り当ては、この中から選ぶ。
#let stones = (
  quartz: (name: "水晶", main: rgb("4f6d84")),
  diamond: (name: "ダイヤモンド", main: rgb("6c8aa3")),
  topaz: (name: "トパーズ", main: rgb("b06a17")),
  amber: (name: "琥珀", main: rgb("c2700f")),
  citrine: (name: "シトリン", main: rgb("97760a")),
  emerald: (name: "エメラルド", main: rgb("1b7a54")),
  tourmaline: (name: "トルマリン", main: rgb("9a8a00")),
  ruby: (name: "ルビー", main: rgb("ad2840")),
  morganite: (name: "モルガナイト", main: rgb("c06a72")),
  amethyst: (name: "アメジスト", main: rgb("71479e")),
  sapphire: (name: "サファイア", main: rgb("1f4fa3")),
  aquamarine: (name: "アクアマリン", main: rgb("1f86a0")),
  onyx: (name: "オニキス", main: rgb("2c2f36")),
  opal: (name: "オパール", main: rgb("a8457f")),
  iolite: (name: "アイオライト", main: rgb("4b4fb0")),
  redberyl: (name: "レッドベリル", main: rgb("b3245a")),
  rough: (name: "原石", main: rgb("5b6876")),
)
#let tab-order = ("0", "1", "2", "3", "4", "5", "6", "7", "A")

// そのページで有効な章（章扉の目印から求める）。
#let current-key() = {
  let marks = query(<chapter-mark>).filter(m => m.location().page() <= here().page())
  if marks.len() > 0 { marks.last().value.key } else { none }
}
#let current-mark() = {
  let marks = query(<chapter-mark>).filter(m => m.location().page() <= here().page())
  if marks.len() > 0 { marks.last().value } else { none }
}
#let gem-of(key) = gems.at(if key == none { "0" } else { key })

// ロゴの宝石に合わせた菱形。縦横の線を入れ、上を明るくする。
// size は高さ。幅は高さの半分。
#let gem(size, color, outline: auto) = box(width: size * 0.5, height: size, baseline: 18%, {
  let w = size * 0.5
  let edge = if outline == auto { color.darken(40%) } else { outline }
  place(polygon(fill: gradient.linear(color.lighten(45%), color, angle: 90deg),
    stroke: (paint: edge, thickness: size * 0.06, join: "miter"),
    (w / 2, 0pt), (w, size / 2), (w / 2, size), (0pt, size / 2)))
  place(line(start: (w / 2, 0pt), end: (w / 2, size), stroke: size * 0.025 + edge))
  place(line(start: (0pt, size / 2), end: (w, size / 2), stroke: size * 0.025 + edge))
})

// 章の宝石を、その石らしいカットや結晶の形で描く。size は高さ。
//   水晶：先のとがった六角柱　トパーズ：ペアシェイプ　エメラルド：エメラルドカット
//   ルビー：オーバル　アメジスト：結晶の群れ　シトリン：ラウンドブリリアント　原石：不定形
// wire: true で線画（操作ガイド用）にする。
#let gem-shape(shape, size, color, outline: auto, wire: false) = {
  let u = size
  let edge = if wire { color } else if outline == auto { color.darken(40%) } else { outline }
  // 石ごとの塗り。水晶・ダイヤモンドは白に近い透明感、淡い石は明るめ、琥珀は内側が光る、
  // オニキスは黒、トルマリンは黄から黄緑にする。
  let clear = shape in ("quartz", "diamond")
  let body-fill = if wire { color.transparentize(88%) }
    else if clear { gradient.linear(white, color.lighten(78%), color.lighten(45%), angle: 70deg) }
    else if shape in ("aquamarine", "morganite") { gradient.linear(white, color.lighten(55%), color.lighten(5%), angle: 70deg) }
    else if shape == "amber" { gradient.radial(rgb("ffe08a"), color.lighten(10%), color.darken(35%), center: (38%, 32%)) }
    else if shape == "onyx" { gradient.linear(rgb("6a6e78"), rgb("1c1d22"), rgb("0c0c0f"), angle: 70deg) }
    else if shape == "opal" { gradient.linear(rgb("f4f8ff"), rgb("d3e4f6"), rgb("ddd3f1"), angle: 60deg) }
    else if shape == "iolite" { gradient.linear(color.lighten(45%), color, rgb("5d7fa8"), angle: 120deg) }
    else if shape == "tourmaline" { gradient.linear(rgb("fffbc2"), rgb("f4e04a"), rgb("d8bf16"), rgb("a8a21a"), angle: 90deg) }
    else { gradient.linear(color.lighten(50%), color, color.darken(15%), angle: 90deg) }
  if clear and not wire and outline == auto { edge = color.lighten(15%) }
  if shape == "onyx" and not wire and outline == auto { edge = rgb("08080a") }
  let rim = (paint: edge, thickness: u * (if clear { 0.04 } else { 0.055 }), join: "round")
  let facet = u * (if clear { 0.018 } else { 0.025 }) + edge.transparentize(if clear { 30% } else { 0% })
  let pt(x, y) = (x * u, y * u)
  // 左上から差す光沢を、同じ形に重ねる。
  let gloss = gradient.linear((white.transparentize(30%), 0%), (white.transparentize(75%), 30%), (white.transparentize(100%), 55%), (white.transparentize(100%), 100%), angle: 40deg)
  let poly(..pts) = {
    let p = pts.pos().map(((x, y)) => pt(x, y))
    place(polygon(fill: body-fill, stroke: rim, ..p))
    if not wire { place(polygon(fill: gloss, stroke: none, ..p)) }
  }
  let seg(a, b) = place(line(start: pt(..a), end: pt(..b), stroke: facet))
  let ring(cx, cy, rx, ry, n, rot: 0deg) = range(n).map(i => {
    let t = rot + 360deg * i / n
    (cx + rx * calc.sin(t), cy - ry * calc.cos(t))
  })
  let (w, draw) = if shape == "quartz" {
    (0.56, {
      poly((0.04, 0.4), (0.28, 0.02), (0.52, 0.4), (0.52, 0.98), (0.04, 0.98))
      seg((0.28, 0.02), (0.18, 0.44)); seg((0.28, 0.02), (0.38, 0.44))
      seg((0.04, 0.4), (0.18, 0.44)); seg((0.18, 0.44), (0.38, 0.44)); seg((0.38, 0.44), (0.52, 0.4))
      seg((0.18, 0.44), (0.18, 0.98)); seg((0.38, 0.44), (0.38, 0.98))
    })
  } else if shape == "topaz" {
    // ペアシェイプ：上がとがり、下が丸い
    let outer = range(24).map(i => {
      let t = 360deg * i / 24
      (0.4 + 0.36 * calc.sin(t) * calc.pow(calc.abs(calc.sin(t / 2)), 0.9), 0.52 - 0.47 * calc.cos(t))
    })
    let inner = outer.map(((x, y)) => (0.4 + (x - 0.4) * 0.48, 0.6 + (y - 0.52) * 0.48))
    (0.8, {
      poly(..outer)
      place(polygon(fill: none, stroke: facet, ..inner.map(((x, y)) => pt(x, y))))
      for i in range(0, 24, step: 4) { seg(outer.at(i), inner.at(i)) }
    })
  } else if shape == "emerald" {
    let oct(x0, y0, x1, y1, c) = ((x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c))
    let o = oct(0.03, 0.03, 0.73, 0.97, 0.16)
    let m = oct(0.13, 0.13, 0.63, 0.87, 0.11)
    let t = oct(0.23, 0.23, 0.53, 0.77, 0.06)
    (0.76, {
      poly(..o)
      place(polygon(fill: none, stroke: facet, ..m.map(((x, y)) => pt(x, y))))
      place(polygon(fill: none, stroke: facet, ..t.map(((x, y)) => pt(x, y))))
      for i in range(8) { seg(o.at(i), t.at(i)) }
    })
  } else if shape == "ruby" {
    let outer = ring(0.38, 0.5, 0.35, 0.47, 16)
    let table = ring(0.38, 0.5, 0.17, 0.23, 8)
    (0.76, {
      poly(..outer)
      place(polygon(fill: none, stroke: facet, ..table.map(((x, y)) => pt(x, y))))
      for i in range(8) { seg(table.at(i), outer.at(2 * i)) }
    })
  } else if shape == "amethyst" {
    (0.86, {
      poly((0.02, 0.98), (0.02, 0.52), (0.14, 0.34), (0.26, 0.52), (0.26, 0.98))
      poly((0.58, 0.98), (0.58, 0.46), (0.71, 0.27), (0.84, 0.46), (0.84, 0.98))
      poly((0.22, 0.98), (0.22, 0.3), (0.42, 0.02), (0.62, 0.3), (0.62, 0.98))
      seg((0.42, 0.02), (0.42, 0.98)); seg((0.22, 0.3), (0.62, 0.3))
    })
  } else if shape == "citrine" {
    let outer = ring(0.49, 0.5, 0.47, 0.47, 16)
    let table = ring(0.49, 0.5, 0.22, 0.22, 8, rot: 22.5deg)
    (0.98, {
      poly(..outer)
      place(polygon(fill: none, stroke: facet, ..table.map(((x, y)) => pt(x, y))))
      for i in range(8) {
        seg(table.at(i), outer.at(calc.rem(2 * i + 1, 16)))
        seg(table.at(i), outer.at(calc.rem(2 * i + 2, 16)))
      }
    })
  } else if shape == "tourmaline" {
    // 長い柱状の結晶。縦の筋が入る
    (0.52, {
      poly((0.06, 0.1), (0.17, 0.02), (0.35, 0.02), (0.46, 0.1), (0.46, 0.98), (0.06, 0.98))
      seg((0.06, 0.1), (0.46, 0.1))
      seg((0.17, 0.02), (0.17, 0.1)); seg((0.35, 0.02), (0.35, 0.1))
      seg((0.19, 0.1), (0.19, 0.98)); seg((0.33, 0.1), (0.33, 0.98))
    })
  } else if shape == "diamond" {
    // ブリリアントカットを横から見た形
    (1.0, {
      poly((0.2, 0.12), (0.8, 0.12), (0.98, 0.36), (0.5, 0.98), (0.02, 0.36))
      seg((0.02, 0.36), (0.98, 0.36))
      seg((0.2, 0.12), (0.26, 0.36)); seg((0.26, 0.36), (0.5, 0.12)); seg((0.5, 0.12), (0.74, 0.36)); seg((0.74, 0.36), (0.8, 0.12))
      seg((0.26, 0.36), (0.5, 0.98)); seg((0.5, 0.36), (0.5, 0.98)); seg((0.74, 0.36), (0.5, 0.98))
    })
  } else if shape == "amber" {
    // 琥珀：カットのない丸みのある塊。中に小さな粒
    let outer = range(30).map(i => {
      let t = 360deg * i / 30
      let r = 1 + 0.07 * calc.sin(3 * t) + 0.04 * calc.cos(5 * t)
      (0.46 + 0.42 * r * calc.sin(t), 0.52 - 0.44 * r * calc.cos(t))
    })
    (0.94, {
      poly(..outer)
      place(circle(radius: u * 0.035, fill: color.darken(45%).transparentize(30%), stroke: none), dx: u * 0.56, dy: u * 0.58)
      place(circle(radius: u * 0.022, fill: color.darken(45%).transparentize(40%), stroke: none), dx: u * 0.4, dy: u * 0.7)
    })
  } else if shape == "morganite" {
    // ハートシェイプ
    let heart = range(32).map(i => {
      let t = 360deg * i / 32
      let x = 16 * calc.pow(calc.sin(t), 3)
      let y = 13 * calc.cos(t) - 5 * calc.cos(2 * t) - 2 * calc.cos(3 * t) - calc.cos(4 * t)
      (0.48 + x * 0.028, 0.44 - y * 0.028)
    })
    let inner = heart.map(((x, y)) => (0.48 + (x - 0.48) * 0.45, 0.5 + (y - 0.44) * 0.45))
    (0.96, {
      poly(..heart)
      place(polygon(fill: none, stroke: facet, ..inner.map(((x, y)) => pt(x, y))))
      for i in range(0, 32, step: 4) { seg(heart.at(i), inner.at(i)) }
    })
  } else if shape == "sapphire" {
    // クッションカット：角の丸い四角
    let outer = range(28).map(i => {
      let t = 360deg * i / 28
      let sx = calc.sin(t); let cy = calc.cos(t)
      let k(v) = if v >= 0 { calc.pow(v, 0.55) } else { -calc.pow(-v, 0.55) }
      (0.43 + 0.4 * k(sx), 0.5 - 0.46 * k(cy))
    })
    let table = ring(0.43, 0.5, 0.18, 0.21, 8, rot: 22.5deg)
    (0.86, {
      poly(..outer)
      place(polygon(fill: none, stroke: facet, ..table.map(((x, y)) => pt(x, y))))
      for i in range(8) { seg(table.at(i), outer.at(calc.rem(int(calc.round(i * 3.5 + 2)), 28))) }
    })
  } else if shape == "aquamarine" {
    // マーキースカット：上下がとがった舟形
    let outer = range(28).map(i => {
      let t = 360deg * i / 28
      let sx = calc.sin(t)
      let k = if sx >= 0 { calc.pow(sx, 1.4) } else { -calc.pow(-sx, 1.4) }
      (0.32 + 0.3 * k, 0.5 - 0.48 * calc.cos(t))
    })
    let inner = outer.map(((x, y)) => (0.32 + (x - 0.32) * 0.45, 0.5 + (y - 0.5) * 0.55))
    (0.64, {
      poly(..outer)
      place(polygon(fill: none, stroke: facet, ..inner.map(((x, y)) => pt(x, y))))
      seg(outer.at(0), inner.at(0)); seg(outer.at(14), inner.at(14))
      for i in (4, 10, 18, 24) { seg(outer.at(i), inner.at(i)) }
    })
  } else if shape == "opal" {
    // オパール：丸いカボション。中に虹色の斑が浮かぶ
    let outer = ring(0.42, 0.5, 0.4, 0.47, 28)
    let patch(c, ..pts) = place(polygon(fill: c.transparentize(if wire { 70% } else { 40% }), stroke: none, ..pts.pos().map(((x, y)) => pt(x, y))))
    (0.84, {
      poly(..outer)
      patch(rgb("ff6fa8"), (0.2, 0.36), (0.34, 0.27), (0.4, 0.4), (0.27, 0.48))
      patch(rgb("3fd08a"), (0.46, 0.54), (0.62, 0.46), (0.68, 0.64), (0.52, 0.7))
      patch(rgb("3d8cff"), (0.26, 0.6), (0.4, 0.58), (0.4, 0.78), (0.28, 0.75))
      patch(rgb("ffd23f"), (0.48, 0.22), (0.62, 0.27), (0.58, 0.4), (0.47, 0.35))
      patch(rgb("a86bff"), (0.6, 0.72), (0.7, 0.7), (0.66, 0.84), (0.56, 0.82))
    })
  } else if shape == "iolite" {
    // アイオライト：辺がふくらんだ三角形（トリリアントカット）。見る向きで紫と青が変わる
    let corners = ((0.5, 0.05), (0.96, 0.88), (0.04, 0.88))
    let (gx, gy) = (0.5, 0.6)
    let outer = ()
    for i in range(3) {
      let (ax, ay) = corners.at(i)
      let (bx, by) = corners.at(calc.rem(i + 1, 3))
      for j in range(6) {
        let t = j / 6
        let (mx, my) = (ax + (bx - ax) * t, ay + (by - ay) * t)
        let (nx, ny) = (mx - gx, my - gy)
        let len = calc.sqrt(nx * nx + ny * ny)
        let bulge = 0.05 * calc.sin(180deg * t)
        outer.push((mx + nx / len * bulge, my + ny / len * bulge))
      }
    }
    let table = corners.map(((x, y)) => (gx + (x - gx) * 0.38, gy + (y - gy) * 0.38))
    (1.0, {
      poly(..outer)
      place(polygon(fill: none, stroke: facet, ..table.map(((x, y)) => pt(x, y))))
      for i in range(3) { seg(table.at(i), outer.at(i * 6)); seg(table.at(i), outer.at(i * 6 + 3)); seg(table.at(i), outer.at(calc.rem(i * 6 + 15, 18))) }
    })
  } else if shape == "redberyl" {
    // レッドベリル：平たい六角柱の結晶を斜め上から見た形
    let top = ring(0.5, 0.36, 0.44, 0.3, 6, rot: 30deg)
    (1.0, {
      poly(top.at(1), top.at(2), (top.at(2).at(0), top.at(2).at(1) + 0.32), (top.at(3).at(0), top.at(3).at(1) + 0.32), (top.at(4).at(0), top.at(4).at(1) + 0.32), top.at(4), top.at(3))
      poly(..top)
      seg(top.at(3), (top.at(3).at(0), top.at(3).at(1) + 0.32))
      let inner = ring(0.5, 0.36, 0.22, 0.15, 6, rot: 30deg)
      place(polygon(fill: none, stroke: facet, ..inner.map(((x, y)) => pt(x, y))))
    })
  } else if shape == "onyx" {
    // 磨いた楕円の石。白い縞が1本入る
    let outer = ring(0.4, 0.5, 0.37, 0.47, 28)
    let band = range(9).map(i => {
      let x = 0.07 + 0.66 * i / 8
      (x, 0.62 - 0.1 * calc.sin(180deg * i / 8))
    })
    (0.8, {
      poly(..outer)
      for i in range(8) { place(line(start: pt(..band.at(i)), end: pt(..band.at(i + 1)), stroke: u * 0.03 + white.transparentize(45%))) }
    })
  } else {
    // 原石：角の不ぞろいな塊
    (0.9, {
      poly((0.06, 0.55), (0.2, 0.18), (0.55, 0.04), (0.84, 0.24), (0.88, 0.66), (0.6, 0.96), (0.22, 0.9))
      seg((0.2, 0.18), (0.45, 0.5)); seg((0.45, 0.5), (0.84, 0.24)); seg((0.45, 0.5), (0.6, 0.96))
    })
  }
  // 小さな四つ星のきらめき。大きく描くときだけ置く。
  let sparkle(cx, cy, r) = place(polygon(fill: white, stroke: none,
    ..range(8).map(i => {
      let t = 45deg * i
      let rr = if calc.even(i) { r } else { r * 0.22 }
      (cx + rr * calc.sin(t), cy - rr * calc.cos(t))
    })))
  box(width: w * u, height: u, baseline: 18%, {
    draw
    if not wire and size >= 8mm {
      sparkle(w * u * 0.3, u * 0.2, u * 0.12)
      sparkle(w * u * 0.72, u * 0.62, u * 0.06)
    }
  })
}

#let fig-counter = counter("book-figure")

// 章扉。章の色の帯・章番号・リード文・この章の節を置く。
#let chapter(key, num, title, lead) = {
  pagebreak(weak: true)
  fig-counter.update(0)
  let g = gems.at(key)
  [#metadata((key: key, num: num, title: title)) <chapter-mark>]
  block(width: 100%, fill: g.main, radius: 3mm, inset: (x: 8mm, y: 6mm), below: 5mm, clip: true, {
    place(right + horizon, dx: -4mm, gem-shape(g.shape, 30mm, white.transparentize(78%), outline: white.transparentize(50%)))
    let appendix = key == "A"
    grid(columns: (auto, 1fr), column-gutter: if appendix { 0mm } else { 7mm }, align: horizon,
      if appendix { [] } else { text(size: 46pt, weight: "bold", fill: white, num) },
      {
        text(size: 8.5pt, fill: white.transparentize(15%), tracking: 0.12em)[#if appendix [APPENDIX] else [CHAPTER #num　#g.name]]
        v(1.5mm)
        heading(level: 1, text(fill: white, title))
      },
    )
  })
  block(width: 100%, below: 4mm, text(size: 11.5pt, lead))
  context {
    let next = query(selector(<chapter-mark>).after(here(), inclusive: false))
    let sel = selector(heading.where(level: 2)).after(here())
    if next.len() > 0 { sel = sel.before(next.first().location()) }
    let items = query(sel)
    if items.len() > 0 {
      let half = calc.ceil(items.len() / 2)
      let entry(hd) = link(hd.location(), box(width: 100%, inset: (y: 0.8mm),
        [#gem-shape(g.shape, 3.4mm, g.main)#h(1.6mm)#text(size: 9.5pt, fill: ink, hd.body)#box(width: 1fr)#text(size: 8.5pt, fill: muted, str(hd.location().page()))]))
      block(width: 100%, fill: g.light, radius: 2mm, inset: (x: 5mm, y: 4mm), below: 7mm, {
        text(size: 8.5pt, weight: "bold", fill: g.main, tracking: 0.08em)[この章で扱うこと]
        v(1.5mm)
        grid(columns: (1fr, 1fr), column-gutter: 8mm,
          stack(..items.slice(0, half).map(entry)),
          stack(..items.slice(half).map(entry)))
      })
    }
  }
}

// 図。章ごとに「図4-2」のように番号を振り、枠の上辺に章の色を付ける。
#let fig(caption, body) = context {
  fig-counter.step()
  let mark = current-mark()
  let g = gem-of(if mark == none { none } else { mark.key })
  let num = if mark == none { "" } else { mark.num + "-" }
  block(breakable: false, above: 3mm, below: 4mm, width: 100%, {
    block(width: 100%, fill: rgb("f8f9fb"), stroke: (top: 1.2mm + g.main, rest: 0.5pt + rgb("dce3e8")),
      radius: (bottom: 2mm), inset: (x: 4mm, y: 4mm), body)
    v(1.2mm)
    text(size: 9pt, fill: muted)[#text(weight: "bold", fill: g.main)[図#num#context fig-counter.display()]　#caption]
  })
}

// 囲み。ポイント・例・GMへの3種類。
#let callout(kind, body) = context {
  let g = gem-of(current-key())
  let label = (point: "ポイント", example: "例", gm: "GMへ").at(kind)
  block(width: 100%, fill: g.light, radius: (right: 2mm), inset: (left: 5mm, right: 5mm, y: 3.5mm),
    stroke: (left: 1.3mm + g.main), above: 3mm, below: 4mm, breakable: false, {
      text(size: 9pt, weight: "bold", fill: g.main)[#gem-shape(g.shape, 3.6mm, g.main)#h(1.5mm)#label]
      v(1mm)
      text(size: 10.5pt, body)
    })
}

// 図の部品：資源の札とダイス。
#let res(label, color, value) = box(fill: color.lighten(88%), stroke: 0.6pt + color, radius: 1.5mm,
  inset: (x: 1.6mm, y: 0.9mm), baseline: 22%,
  [#text(size: 7.5pt, weight: "bold", fill: color, label)#h(1mm)#text(size: 9.5pt, weight: "bold", value)])
#let hp(v) = res("HP", rgb("c0392b"), v)
#let mp(v) = res("MP", rgb("2a6fb0"), v)
#let fp(v) = res("FP", rgb("b7791f"), v)

#let die(n, color: ink) = box(width: 6mm, height: 6mm, baseline: 25%, {
  place(top + left, rect(width: 6mm, height: 6mm, radius: 1.2mm, fill: white, stroke: 0.7pt + color))
  let p = (
    "1": ((1, 1),), "2": ((0, 0), (2, 2)), "3": ((0, 0), (1, 1), (2, 2)),
    "4": ((0, 0), (2, 0), (0, 2), (2, 2)), "5": ((0, 0), (2, 0), (1, 1), (0, 2), (2, 2)),
    "6": ((0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)),
  ).at(str(n))
  for (x, y) in p { place(top + left, dx: 1.35mm + x * 1.1mm, dy: 1.35mm + y * 1.1mm, circle(radius: 0.55mm, fill: color)) }
})

// 人物の札。陣営は名前と線の色の両方で示す。
#let ally = rgb("246589")
#let enemy = rgb("a9493e")
#let card(title, color, body) = rect(width: 100%, inset: 3.5mm, radius: 2mm, fill: white, stroke: 0.8pt + color)[
  #text(size: 11pt, weight: "bold", fill: color, title) \ #v(0.5mm) #text(size: 10pt, body)
]
#let pair(left, right) = grid(columns: (1fr, 1fr), gutter: 6mm, left, right)

// 表の見出し行に章の色を付ける。
#let book-table(columns, header, ..rows) = context {
  let g = gem-of(current-key())
  table(columns: columns, inset: (x: 6pt, y: 6pt), stroke: (x, y) => (bottom: 0.5pt + rgb("dce3e8")),
    fill: (x, y) => if y == 0 { g.main } else if calc.even(y) { rgb("f8f9fb") },
    table.header(..header.map(h => text(fill: white, weight: "bold", h))),
    ..rows)
}

#let book-conf(doc) = {
  set page(paper: "a4", binding: left,
    margin: (inside: 24mm, outside: 20mm, top: 23mm, bottom: 23mm),
    header: context {
      let mark = current-mark()
      if mark != none {
        let g = gems.at(mark.key)
        set text(size: 8pt)
        grid(columns: (1fr, auto), align: bottom,
          text(fill: muted)[ジェムリアTRPG 基本ルールブック],
          text(fill: g.main, weight: "bold")[#if mark.key != "A" [#mark.num　]#mark.title])
        v(-1.5mm)
        line(length: 100%, stroke: 0.5pt + g.main.lighten(40%))
      }
    },
    footer: context {
      let mark = current-mark()
      let g = gem-of(if mark == none { none } else { mark.key })
      let n = counter(page).display()
      let odd = calc.odd(here().page())
      set text(size: 8.5pt, fill: g.main, weight: "bold")
      if odd { align(right)[#n#h(2mm)#gem-shape(g.shape, 3.6mm, g.main)] } else { align(left)[#gem-shape(g.shape, 3.6mm, g.main)#h(2mm)#n] }
    },
    // 外側の余白に章のつまみを置く。
    background: context {
      let mark = current-mark()
      if mark != none {
        let idx = tab-order.position(k => k == mark.key)
        let g = gems.at(mark.key)
        let odd = calc.odd(here().page())
        let label = if mark.key == "A" { "巻末" } else { mark.num }
        place(if odd { top + right } else { top + left }, dy: 28mm + idx * 25mm,
          rect(width: 9mm, height: 21mm, fill: g.main,
            radius: if odd { (left: 2mm) } else { (right: 2mm) },
            align(center + horizon, text(size: if mark.key == "A" { 7pt } else { 11pt }, weight: "bold", fill: white, label))))
      }
    })
  set text(font: "Noto Sans JP", size: 11pt, lang: "ja", fill: ink)
  set par(leading: 0.65em, spacing: 1.4em)
  set heading(numbering: none, outlined: true)
  show heading.where(level: 1): set text(size: 23pt)
  show heading.where(level: 1): set block(above: 0pt, below: 0pt)
  show heading.where(level: 2): it => context {
    let g = gem-of(current-key())
    block(sticky: true, above: 5mm, below: 2mm, {
      grid(columns: (5mm, 1fr), column-gutter: 2.2mm, align: horizon,
        align(center, gem-shape(g.shape, 5mm, g.main)), text(size: 14pt, fill: g.main, weight: "bold", it.body))
      v(-1mm)
      line(length: 100%, stroke: 0.5pt + g.main.lighten(60%))
    })
  }
  show link: it => text(fill: rgb("246589"), it)
  doc
}
