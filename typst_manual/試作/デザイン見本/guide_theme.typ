// 計画46・デザイン見本（操作ガイド）。基本ルールブックと同じ骨組みに、線画の宝石・等幅の英字ラベル・
// 角括弧の図枠・格子模様を加えて、少しだけデジタルな雰囲気にする。
#import "book_theme.typ": gem-shape, ink, muted

#let mono = ("DejaVu Sans Mono",)
#let night = rgb("13213a")

// 編ごとの色と宝石。
#let parts = (
  "intro": (shape: "amber", code: "INTRO", label: "巻頭", main: rgb("c2700f"), light: rgb("fbf0e2")),
  "common": (shape: "aquamarine", code: "COMMON", label: "共通", main: rgb("1f86a0"), light: rgb("e4f4f8")),
  "pl": (shape: "iolite", code: "PL", label: "PL編", main: rgb("4b4fb0"), light: rgb("ecedf9")),
  "gm": (shape: "opal", code: "GM", label: "GM編", main: rgb("a8457f"), light: rgb("f8ecf3")),
  "index": (shape: "tourmaline", code: "INDEX", label: "索引", main: rgb("9a8a00"), light: rgb("f8f5d8")),
)
#let tab-order = ("intro", "common", "pl", "gm", "index")

#let current-mark() = {
  let marks = query(<guide-mark>).filter(m => m.location().page() <= here().page())
  if marks.len() > 0 { marks.last().value } else { none }
}
#let part-of(mark) = parts.at(if mark == none { "intro" } else { mark.part })

#let fig-counter = counter("guide-figure")

// 細い格子の模様。章扉の帯に敷く。
#let grid-pattern(color) = tiling(size: (4mm, 4mm), {
  place(line(start: (0pt, 0pt), end: (4mm, 0pt), stroke: 0.3pt + color))
  place(line(start: (0pt, 0pt), end: (0pt, 4mm), stroke: 0.3pt + color))
})

// 角だけを描く枠。
#let corner-frame(color, body, inset: 4mm) = block(width: 100%, inset: inset, {
  let c = 4mm
  let st = 1pt + color
  place(top + left, dx: -inset, dy: -inset, { place(line(end: (c, 0pt), stroke: st)); place(line(end: (0pt, c), stroke: st)) })
  place(top + right, dx: inset, dy: -inset, { place(right, line(start: (-c, 0pt), end: (0pt, 0pt), stroke: st)); place(right, line(end: (0pt, c), stroke: st)) })
  place(bottom + left, dx: -inset, dy: inset, { place(bottom, line(end: (c, 0pt), stroke: st)); place(bottom, line(start: (0pt, -c), end: (0pt, 0pt), stroke: st)) })
  place(bottom + right, dx: inset, dy: inset, { place(bottom + right, line(start: (-c, 0pt), end: (0pt, 0pt), stroke: st)); place(bottom + right, line(start: (0pt, -c), end: (0pt, 0pt), stroke: st)) })
  body
})

// 章扉。紺の帯に格子を敷き、編のコードと章名を置く。
#let chapter(part, code, title, lead) = {
  pagebreak(weak: true)
  fig-counter.update(0)
  let g = parts.at(part)
  [#metadata((part: part, code: code, title: title)) <guide-mark>]
  block(width: 100%, fill: night, radius: 2mm, clip: true, below: 5mm, {
    place(top + left, rect(width: 100%, height: 100%, fill: grid-pattern(g.main.transparentize(70%))))
    place(top + left, rect(width: 100%, height: 1.2mm, fill: g.main))
    place(right + horizon, dx: -8mm, gem-shape(g.shape, 26mm, g.main.lighten(30%), wire: true))
    block(inset: (x: 8mm, top: 7mm, bottom: 6mm), {
      block(below: 3mm, text(font: mono, size: 8.5pt, fill: g.main.lighten(45%), tracking: 0.08em)[\/\/ #g.code #code])
      heading(level: 1, text(fill: white, title))
    })
  })
  block(width: 100%, below: 6mm, text(size: 11.5pt, lead))
}

#let fig(caption, body) = context {
  fig-counter.step()
  let mark = current-mark()
  let g = part-of(mark)
  block(breakable: false, above: 4mm, below: 4mm, width: 100%, {
    corner-frame(g.main, block(width: 100%, fill: g.light.transparentize(40%), inset: (y: 2mm), body))
    v(2mm)
    text(size: 9pt, fill: muted)[#text(font: mono, weight: "bold", fill: g.main)[FIG #mark.code\-#context fig-counter.display()]　#caption]
  })
}

#let callout(kind, body) = context {
  let g = part-of(current-mark())
  let label = (tip: "TIP", check: "CHECK", gm: "GM").at(kind)
  let ja = (tip: "ポイント", check: "確かめること", gm: "GMの操作").at(kind)
  block(width: 100%, fill: g.light, inset: (left: 5mm, right: 5mm, y: 3.5mm),
    stroke: (left: 1.3mm + g.main), above: 3mm, below: 4mm, breakable: false, {
      text(font: mono, size: 8.5pt, weight: "bold", fill: g.main)[\[#label\]]
      h(1.5mm)
      text(size: 9pt, weight: "bold", fill: g.main, ja)
      v(1mm)
      text(size: 10.5pt, body)
    })
}

#let guide-table(columns, header, ..rows) = context {
  let g = part-of(current-mark())
  table(columns: columns, inset: (x: 6pt, y: 6pt), stroke: (x, y) => (bottom: 0.5pt + rgb("dce3e8")),
    fill: (x, y) => if y == 0 { night } else if calc.even(y) { rgb("f8f9fb") },
    table.header(..header.map(h => text(fill: g.main.lighten(55%), weight: "bold", h))),
    ..rows)
}

#let guide-conf(doc) = {
  set page(paper: "a4", binding: left,
    margin: (inside: 24mm, outside: 20mm, top: 23mm, bottom: 23mm),
    header: context {
      let mark = current-mark()
      if mark != none {
        let g = part-of(mark)
        set text(size: 8pt)
        grid(columns: (1fr, auto), align: bottom,
          text(font: mono, fill: muted, tracking: 0.05em)[SESSION OPERATION GUIDE],
          text(fill: g.main, weight: "bold")[#text(font: mono)[#mark.code]　#mark.title])
        v(-1.5mm)
        line(length: 100%, stroke: (paint: g.main.lighten(30%), thickness: 0.5pt, dash: "dashed"))
      }
    },
    footer: context {
      let g = part-of(current-mark())
      let n = counter(page).display("001")
      set text(font: mono, size: 8.5pt, fill: g.main, weight: "bold")
      if calc.odd(here().page()) { align(right)[\[ #n \]] } else { align(left)[\[ #n \]] }
    },
    background: context {
      let mark = current-mark()
      if mark != none {
        let idx = tab-order.position(k => k == mark.part)
        let g = parts.at(mark.part)
        let odd = calc.odd(here().page())
        place(if odd { top + right } else { top + left }, dy: 30mm + idx * 30mm,
          rect(width: 9mm, height: 26mm, fill: night,
            stroke: if odd { (left: 1.2mm + g.main) } else { (right: 1.2mm + g.main) },
            align(center + horizon, rotate(-90deg, reflow: true, text(font: mono, size: 9pt, weight: "bold", fill: g.main.lighten(40%), g.code)))))
      }
    })
  set text(font: "Noto Sans JP", size: 11pt, lang: "ja", fill: ink)
  set par(leading: 0.65em, spacing: 1.4em)
  set heading(numbering: none, outlined: true)
  show heading.where(level: 1): set text(size: 23pt)
  show heading.where(level: 1): set block(above: 0pt, below: 0pt)
  show heading.where(level: 2): it => context {
    let g = part-of(current-mark())
    block(sticky: true, above: 5mm, below: 2mm, {
      grid(columns: (5mm, 1fr), column-gutter: 2.2mm, align: horizon,
        align(center, gem-shape(g.shape, 5mm, g.main, wire: true)),
        text(size: 14pt, fill: g.main, weight: "bold", it.body))
      v(-1mm)
      line(length: 100%, stroke: (paint: g.main.lighten(50%), thickness: 0.5pt, dash: "dashed"))
    })
  }
  doc
}
