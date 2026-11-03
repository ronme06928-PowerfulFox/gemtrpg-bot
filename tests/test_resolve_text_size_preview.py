"""計画58 §5.3：解決パネルの文字の大きさは役割ごとのトークンで1か所から決め、プレビューは画面ごとの実寸を本番と同じ決め方で描く。"""
import re

from tests.test_motion_fx_frontend import ROOT, _run_node

ROLE_SIZES = {
    'label': 13, 'progress': 13, 'copy': 14, 'result': 17, 'result-narrow': 15,
    'participant': 13, 'participant-narrow': 11,
    'stack': 14, 'stack-narrow': 13,
}


def _tokens(path):
    text = (ROOT / path).read_text(encoding='utf-8')
    return {k: int(v) for k, v in re.findall(r'--resolve-text-([a-z-]+): (\d+)px', text)}


def test_production_text_sizes_are_role_tokens():
    css = (ROOT / 'static/css/modules/visual_battle.css').read_text(encoding='utf-8')
    assert '--resolve-font-' not in css
    tokens = _tokens('static/css/modules/visual_battle.css')
    assert {k: tokens[k] for k in ROLE_SIZES} == ROLE_SIZES
    for rule, token in [('.top-band', 'label'), ('.power-range', 'label'), ('.description h3', 'label'),
                        ('.description-tab', 'label'), ('.progress-band', 'progress'), ('.skill-copy', 'copy'),
                        ('.result-band', 'result'), ('.narrow .result-band', 'result-narrow'),
                        ('.participant-name', 'participant'), ('.narrow .participant-name', 'participant-narrow'),
                        ('.stack-chip b', 'stack'), ('.narrow .stack-chip b', 'stack-narrow')]:
        body = re.search(r'(?m)^#resolve-flow-panel ' + re.escape(rule) + r' \{([^}]*)\}', css)
        assert body and f'var(--resolve-text-{token})' in body.group(1), rule


def test_preview_draws_the_production_sizes_and_fit():
    production, preview = _tokens('static/css/modules/visual_battle.css'), _tokens('scripts/resolve_preview/page.css')
    assert set(ROLE_SIZES) <= set(preview)
    assert preview == {k: production[k] for k in preview}
    _run_node(r"""
(async()=>{
 const {SCREENS,fitScreen}=await import('./scripts/resolve_preview/screen.mjs');
 const {pickStageLayout,fitStage}=await import('./static/js/battle/components/resolve_stage_layout.js');
 assert.deepStrictEqual(SCREENS.map(s=>s.id),['1920x945','1536x730','1440x780','1366x650','1280x600','1100x650','980x650']);
 for (const s of SCREENS) {
  const r=fitScreen(s), layout=pickStageLayout(s.map*0.92,s.height);
  assert.strictEqual(r.layout,layout);
  assert.deepStrictEqual(r.fit,fitStage(layout,s.map*0.92,s.height));
  assert.ok(r.fit.copyHeight>=layout.minCopyHeight,s.id);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
    script = (ROOT / 'scripts/resolve_preview/page.js').read_text(encoding='utf-8')
    assert "selectControl('画面'" in script
    assert "selectControl('文字'" not in script and 'TEXT_VARIANTS' not in script
