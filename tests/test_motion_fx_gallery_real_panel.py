"""計画56: 場面カードを本物の解決パネル（本番の描画と本番のCSS）で描く。"""
import subprocess
from pathlib import Path

from tests.test_motion_fx_frontend import _run_node

ROOT = Path(__file__).resolve().parents[1]


def test_panel_css_keeps_only_resolve_panel_rules_and_rescopes_the_id():
    _run_node(r"""
(async()=>{
const {extractResolvePanelCss,GALLERY_PANEL_SELECTOR}=await import('./scripts/fx_gallery/panel_css.mjs');
const css=`/* 説明 */
body { margin: 0; }
#visual-timeline-list { flex: 1; }
#resolve-flow-panel.resolve-flow-panel { position: absolute; }
#resolve-flow-panel .resolve-flow-card, #resolve-flow-panel .side { color: red; }
@media (max-width: 980px) {
  #resolve-flow-panel .resolve-flow-card { width: 10px; }
  .other { color: blue; }
}
@media print { .other { color: blue; } }`;
const out=extractResolvePanelCss(css);
assert.strictEqual(GALLERY_PANEL_SELECTOR,'[data-gallery-resolve-panel]');
assert.ok(!out.includes('#resolve-flow-panel'));
assert.ok(!out.includes('body')&&!out.includes('visual-timeline')&&!out.includes('.other')&&!out.includes('print'));
assert.ok(out.includes('[data-gallery-resolve-panel].resolve-flow-panel { position: absolute; }'));
assert.ok(out.includes('[data-gallery-resolve-panel] .resolve-flow-card, [data-gallery-resolve-panel] .side { color: red; }'));
assert.ok(/@media \(max-width: 980px\) \{\n\[data-gallery-resolve-panel\] \.resolve-flow-card \{ width: 10px; \}\n\}/.test(out));
const real=extractResolvePanelCss(fs.readFileSync('static/css/modules/visual_battle.css','utf8'));
assert.ok(!real.includes('#resolve-flow-panel'));
for(const selector of ['.resolve-flow-card','.resolve-flow-background','.resolve-flow-versus .side','.resolve-flow-summation-inline .summation-chips','.resolve-flow-summation-inline .charge-chip'])
  assert.ok(real.includes('[data-gallery-resolve-panel] '+selector),selector);
})().catch(e=>{console.error(e);process.exit(1);});
""")


def test_built_gallery_embeds_the_real_panel_css_and_draws_scenes_with_the_real_panel():
    result = subprocess.run(["node", "scripts/fx_gallery/build.mjs"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stderr
    html = (ROOT / "_local/fx_gallery/fx_gallery.html").read_text(encoding="utf-8")
    assert "[data-gallery-resolve-panel] .resolve-flow-card" in html
    assert "#resolve-flow-panel" not in html
    gallery = (ROOT / "scripts/fx_gallery/gallery.js").read_text(encoding="utf-8")
    assert "createRealStage" in gallery
    real = (ROOT / "scripts/fx_gallery/real_panel.mjs").read_text(encoding="utf-8")
    assert "_renderStep" in real and "Date.now" in real
    assert "initialize(" not in real


def test_numbers_on_summation_chips_are_small_enough_for_the_real_chip_spacing():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const fx=Object.create(Fx.get('resolve-damage'));fx.mount(doc.createElement('div'),{level:'normal',amount:8,mode:'chip'});
assert.ok(fx.el.className.split(' ').includes('chip'));
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
assert.ok(/\.fx-resolve-damage\.chip \{ font-size: calc\(30px \* var\(--fx-scale\)\); \}/.test(css));
""")


def test_mock_stage_rules_do_not_leak_into_the_real_panel():
    # 仮の台の位置決め（.side の absolute など）が本物のパネルに効くと、名前・威力の段の高さが0になって重なる。
    import re
    css = (ROOT / "scripts/fx_gallery/gallery.css").read_text(encoding="utf-8")
    for name in ["side", "name", "actual", "vs", "summation-chips", "summation-total", "participant-chip",
                 "resolve-flow-background", "resolve-flow-portrait-inline", "chat-total", "stage-caption"]:
        for match in re.finditer(r"(^|\})\s*([^{}]*\." + re.escape(name) + r"\b[^{}]*)\{", css, re.M):
            for selector in match.group(2).split(","):
                if re.search(r"\." + re.escape(name) + r"\b", selector):
                    assert re.search(r"(^|\s)\.(stage|real-stage)(\s|>)", selector.strip()), selector.strip()
