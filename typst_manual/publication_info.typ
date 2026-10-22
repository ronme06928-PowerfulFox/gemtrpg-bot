// 刊行情報の単一の管理元。公開時に release-date を日付へ変更する。
// 例: #let release-date = datetime(year: 2026, month: 10, day: 22)
#let release-date = datetime(year: 2026, month: 10, day: 22)
#let publisher = "創作ゆる大地"
#let publications = (
  book: (
    title: "基本ルールブック",
    edition: "第1版",
    app-checked: none,
    history: ((edition: "第1版", summary: "最初の版"),),
  ),
  guide: (
    title: "セッション操作ガイド",
    edition: "第1版",
    app-checked: "2026年10月22日",
    history: ((edition: "第1版", summary: "最初の版"),),
  ),
)
#let publication-status(key) = {
  let info = publications.at(key)
  if release-date == none { [#info.edition　刊行前の確認版] } else { [#info.edition] }
}
#let publication-date = if release-date == none { none } else { release-date.display("[year]年[month]月[day]日") }
