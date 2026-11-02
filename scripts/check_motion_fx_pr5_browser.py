"""PR5: generated pages plus production flow, real layout, Fx player and conclusion card."""
import json
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
from check_resolve_stage_browser import BUNDLE, ROOT
from check_motion_fx_browser import choose, seek


def main():
    output = ROOT / '_local/pr5_check'
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / 'production.html'
    bundle = BUNDLE.replace('<div id="map-viewport"></div>', '<div id="visual-battle-container" style="position:fixed;inset:0"><div id="map-viewport"></div></div>')
    subprocess.run(['node', '--input-type=module', '-e', bundle, str(fixture)], cwd=ROOT, check=True)
    errors, checks = [], 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='chrome', timeout=20000)
            page = browser.new_page(viewport={'width': 1440, 'height': 1080})
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('https://**', lambda route: route.abort())
            page.goto((ROOT / '_local/fx_gallery/fx_gallery.html').as_uri())
            for effect in ['gem-blessing', 'combat-conclusion']:
                scope = f'.effect-card[data-effect="{effect}"]'
                options = page.locator(scope + ' .sample option').evaluate_all('els=>els.map(e=>e.value)')
                for option in options:
                    choose(page.locator(scope + ' .sample'), option)
                    for level in ['light', 'normal', 'rich']:
                        choose(page.locator(scope + ' .level'), level)
                        for t in [.3, .6, .95]:
                            seek(page, t, scope)
                            assert page.locator(scope + ' .stage-host').evaluate("el=>![...el.querySelectorAll('*')].some(e=>e.style.cssText.includes('NaN'))")
                            if level == 'light':
                                assert page.locator(scope + ' canvas').count() == 0
                            checks += 1
                seek(page, .95, scope)
            page.goto((ROOT / '_local/resolve_preview/resolve_preview.html').as_uri())
            choose(page.locator('.sample-select'), 'gem-blessing')
            seek(page, 1)
            assert page.locator('.theatre').evaluate("el=>getComputedStyle(el).visibility") == 'hidden'
            seek(page, 3.85)
            assert page.locator('.theatre').evaluate("el=>getComputedStyle(el).visibility") == 'visible'
            assert '5.0s' in page.locator('.marker-buttons').inner_text()
            checks += 2
            page.goto(fixture.as_uri())
            page.add_script_tag(path=str(ROOT / 'static/js/fx/fx_player.js'))
            page.add_script_tag(path=str(ROOT / 'static/js/visual/visual_combat_session.js'))
            result = page.evaluate("""() => {
              const assert=(v,m)=>{if(!v)throw Error(m)};
              Fx.setLevel('normal');
              const host=document.getElementById('visual-battle-container');
              const sample=qa.samples.find(s=>s.id==='gem-blessing');
              qa.render('gem-blessing','names');
              assert(document.querySelector('.resolve-stage-canvas'),'real stage');
              assert(document.querySelectorAll('.fx-gem-title').length>0,'inline gem mounted');
              qa.flow._finishFx();
              qa.flow._activeStep={kind:'battle_start'};qa.flow._playQueue=[{kind:'battle_start'}];
              qa.flow._ingestTrace({...sample.state,resolvePresentation:{status:'playing',current_step_index:0},
                resolveTrace:[{kind:'gem_blessing_prelude',step_index:0,gem_blessings:[{actor_id:'a'}]}]});
              assert(qa.flow._activeStep===null&&!qa.flow._playQueue.some(s=>s.kind==='battle_start'),'intro yields to shared prelude');
              qa.flow._activeStep=sample.preludeStep; qa.flow._renderedStepKey=null;
              qa.flow._stepStartedAt=Date.now()-900;
              qa.flow._renderStep(sample.state);
              assert(!document.querySelector('.resolve-stage-canvas'),'no first match in prelude');
              // Zero-size title mask must skip safely, including seek after Infinity.
              const root=document.createElement('div');host.append(root);
              const fx=Object.create(Fx.get('combat-conclusion'));
              fx.mount(root,{outcome:'victory',level:'normal',card:{x:0,y:0,w:600,h:220},titleBox:{x:0,y:0,w:0,h:0}});
              fx.render(.4);fx.render(Infinity);fx.render(.4);
              let tracked; const play=Fx.play;
              Fx.play=(...args)=>{tracked=play(...args);return tracked};
              showCombatConclusionResult({id:'pr5-defeat',outcome:'DEFEAT'});
              const title=document.querySelector('.combat-conclusion-result__title');
              tracked.fx.render(3.9);assert(title.style.translate==='0px 8px','defeat holds until close');
              document.querySelector('.combat-conclusion-result__close').click();
              assert(title.style.translate===''&&title.style.filter==='','close restores');
              showCombatConclusionResult({id:'pr5-victory',outcome:'VICTORY'});
              tracked.fx.render(.4);Fx.finishAll(document.getElementById('combat-conclusion-result-overlay'));
              assert(!document.querySelector('#combat-conclusion-result-overlay canvas'),'finishAll removes');
              document.querySelector('.combat-conclusion-result__close').click();
              return 9;
            }""")
            checks += result
            # One latest visual for review; no intermediate screen captures retained.
            page.goto((ROOT / '_local/fx_gallery/fx_gallery.html').as_uri())
            choose(page.locator('.effect-card[data-effect="gem-blessing"] .sample'), 'gem-long')
            seek(page, .98, '.effect-card[data-effect="gem-blessing"]')
            page.locator('.effect-card[data-effect="gem-blessing"]').screenshot(path=str(output / 'latest.png'))
            page.goto((ROOT / '_local/fx_proto/pr5_proto.html').as_uri())
            assert page.locator('canvas').count() > 0
            assert not errors, errors
            browser.close()
        report = {'checks': checks, 'page_errors': errors, 'browser': 'Chrome/headless', 'viewport': '1440x1080'}
        (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        fixture.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
