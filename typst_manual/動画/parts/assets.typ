// リポジトリのルートから --root . --format svg --input asset=名前 で書き出す。
#import "../../manual_theme.typ": gem-shape, gems, die

#set page(width: auto, height: auto, margin: 1mm, fill: none)

#let asset = sys.inputs.at("asset")
#let ruby-gem = gems.at("4")
#if asset == "ruby-fill" {
  gem-shape(ruby-gem.shape, 24mm, ruby-gem.main)
} else if asset == "ruby-wire" {
  gem-shape(ruby-gem.shape, 24mm, ruby-gem.main, wire: true)
} else if asset in ("die-1", "die-2", "die-3", "die-4", "die-5", "die-6") {
  die(int(asset.split("-").last()))
} else {
  panic("Unknown video asset: " + asset)
}
