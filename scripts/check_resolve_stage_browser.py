"""PR57-1: 実DOMで描画・縮小・タブ・演出座標を検査する（Playwright + Chrome）。"""
import json
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_local/resolve_stage_check"

BUNDLE = r"""
import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
const source = `
import './static/js/fx/fx_core.js';
import './static/js/fx/fx_effects.js';
import {ResolveFlowPanel} from './static/js/battle/components/ResolveFlowPanel.js';
import {store} from './static/js/battle/core/BattleStore.js';
import {playResolveStageFx,resolveStageTiming} from './static/js/battle/components/resolve_flow_fx.js';
import {getLayout,participantSlots,stageFxPlacement} from './static/js/battle/components/resolve_stage_layout.js';
import {resolveStageStarts} from './static/js/battle/components/resolve_stage_timing.js';
import {stageMotionAt,renderStageMotion} from './static/js/battle/components/resolve_stage_motion.js';
const samples=__SAMPLES__,skills=__SKILLS__;
const flow=new ResolveFlowPanel();flow._skillById=id=>skills[id];
let events=[];
window.Fx.getLevel=()=> 'normal';
window.Fx.finishAll=host=>{for(const root of host?.querySelectorAll('.fx-root')||[])root.remove();};
window.Fx.play=(name,params,options)=>{
  const root=document.createElement('div');root.className='fx-root';
  Object.assign(root.style,{left:options.left+'px',top:options.top+'px'});options.host.append(root);
  const fx=Object.create(window.Fx.get(name));fx.mount(root,{...params,level:'normal'});fx.render(0.5);
  const item={name,params,options,root,fx};events.push(item);return item;
};
window.qa={samples,getLayout,participantSlots,stageFxPlacement,flow,seekMotion(time,level){
  const canvas=document.querySelector('.resolve-stage-canvas');
  renderStageMotion(canvas,stageMotionAt(flow._activeStep,time,level));
  return [...canvas.querySelectorAll('.portrait,.skill-plaque,.gem,.character-name,.clash-point')].map(el=>el.style.cssText);
},tail(){
  const attack=events.find(e=>e.name.startsWith('attack-'));
  flow._stepStartedAt=Date.now()-resolveStageStarts(flow._activeStep).outcome*1000;
  flow._renderStep(store._state);
  const retained=attack.root.isConnected;
  attack.fx.render(1.2);const visible=Number(attack.fx.el.style.opacity);
  attack.fx.render(1.4);return {retained,visible,finished:Number(attack.fx.el.style.opacity),duration:attack.fx.duration};
},render(id,phase='outcome'){
  flow._finishFx();flow._renderedStepKey=null;events=[];
  const sample=structuredClone(samples.find(s=>s.id===id));
  for(const side of ['attacker','defender']) if(sample.nameOverrides?.[side])sample.step[side+'SkillNameHint']=sample.nameOverrides[side];
  store._state=sample.state;flow._activeStep=sample.step;
  const starts=resolveStageStarts(sample.step);
  flow._stepStartedAt=Date.now()-(starts[phase]??starts.outcome)*1000-1;
  flow._renderStep(sample.state);
  playResolveStageFx(flow,{stage:phase,outcome:sample.step.outcome},sample.state);
  return {events:events.map(e=>({name:e.name,left:e.options.left,top:e.options.top,width:e.params.width,height:e.params.height,ceiling:e.params.ceiling,anchor:e.options.host.dataset.anchor,classes:e.root.className})),sample};
}};
`;
const samples=(await import('./scripts/resolve_preview/skills.mjs')).loadSamples;
const result=await build({stdin:{contents:source,resolveDir:process.cwd()},bundle:true,format:'iife',write:false,define:{__SAMPLES__:JSON.stringify(await samples()),__SKILLS__:await readFile('data/cache/skills_cache.json','utf8')}});
const css=await readFile('static/dist/app.bundle.css','utf8');
const motion=await readFile('static/css/modules/motion_fx.css','utf8');
const html='<meta charset="utf-8"><style>'+css+motion+'body{margin:0;background:#090d14}#map-viewport{position:fixed;inset:0;margin:0;border:0}</style><div id="map-viewport"></div><script>'+result.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')+'</script>';
await writeFile(process.argv[1],html,'utf8');
"""


def main():
    temporary = TemporaryDirectory(prefix="gem-resolve-stage-")
    fixture = Path(temporary.name) / "production_check.html"
    subprocess.run(["node", "--input-type=module", "-e", BUNDLE, str(fixture)], cwd=ROOT, check=True)
    OUT.mkdir(parents=True, exist_ok=True)
    checks = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://**", lambda route: route.abort())
        page.goto(fixture.as_uri(), wait_until="domcontentloaded")
        # 画像はローカルの実アセットを使う。ルート相対URLをファイルURLへ直す。
        page.evaluate("""root => {
          for(const sample of qa.samples)for(const c of sample.state.characters)if(c.image)c.image=root+c.image;
        }""", ROOT.as_uri())
        for width, height in [(1440, 1080), (1180, 768), (980, 900), (800, 768), (660, 600), (480, 400)]:
            page.set_viewport_size({"width": width, "height": height})
            for sample in page.evaluate("qa.samples.map(s=>s.id)"):
                for phase in ["names", "power", "attack", "outcome"]:
                    page.evaluate("([id,phase])=>qa.render(id,phase)", [sample, phase])
                    result = page.evaluate("""() => {
                      const panel=document.getElementById('resolve-flow-panel'),canvas=panel.querySelector('.resolve-stage-canvas');
                      const rect=canvas.getBoundingClientRect(),host=panel.querySelector('.resolve-stage-host').getBoundingClientRect();
                      const desc=panel.querySelector('.skill-descriptions');
                      const layout=qa.getLayout(innerWidth<=980?660:1180);
                      const expected=Math.max(0,Math.min(layout.copyHeight,innerHeight-108-layout.cardHeight-14));
                      const shown=expected>=40;
                      const visible=el=>getComputedStyle(el).visibility==='visible';
                      const step=qa.flow._activeStep;
                      const unarmed=step.kind!=='fizzle'&&qa.flow._isOneSidedPresentation(step);
                      return {width:rect.width,height:host.height,card:panel.querySelector('.theatre').getBoundingClientRect().height,
                        copy:parseFloat(desc.style.height),copyDisplay:getComputedStyle(desc).display,narrow:canvas.classList.contains('narrow'),
                        expected:shown?expected:0,phase:panel.className,plaque:[...panel.querySelectorAll('.skill-plaque')].every(visible),
                        summary:visible(panel.querySelector('.result-band')),nan:canvas.innerHTML.includes('NaN'),
                        unarmed,defenderPlaque:!!panel.querySelector('.combatant.defender .skill-plaque'),
                        defenderGem:!!panel.querySelector('.combatant.defender > .gem'),
                        defenderCopy:!!panel.querySelector('.description.defender'),
                        central:panel.querySelector('.clash-point').textContent,
                        expectedCentral:step.kind==='fizzle'?'不発':unarmed?qa.flow._kindLabel(step.kind):'VS',
                        gem:panel.querySelector('.gem')&&getComputedStyle(panel.querySelector('.gem')).getPropertyValue('--team').trim(),
                        rollMisaligned:[...panel.querySelectorAll('.event-power-roll')].some(root=>{
                          const number=root.parentElement.querySelector('.power-number').getBoundingClientRect(),r=root.getBoundingClientRect();
                          return Math.abs(r.x-number.x-number.width/2)>0.1||Math.abs(r.y-number.y-number.height/2)>0.1;
                        })};
                    }""")
                    assert result["width"] <= width + 1, (sample, result)
                    assert result["height"] <= height - 108 + 1, (sample, result)
                    assert result["copy"] == result["expected"], (sample, result)
                    assert result["narrow"] == (width <= 980)
                    assert result["plaque"] == (phase != "names"), (sample, phase, result)
                    assert result["summary"] == (phase == "outcome" or (sample == "fizzle" and phase == "attack"))
                    assert not result["nan"], (sample, result)
                    assert not result["rollMisaligned"], (sample, width, phase, result)
                    assert result["defenderPlaque"] == (not result["unarmed"]), (sample, result)
                    assert result["defenderGem"] == (not result["unarmed"]), (sample, result)
                    if result["unarmed"]:
                        assert not result["defenderCopy"], (sample, result)
                    assert result["central"] == result["expectedCentral"], (sample, result)
                    if sample == "fizzle":
                        assert result["gem"] == "#6d737c", result
                    checks += 1
            page.evaluate("qa.render('long-names','outcome')")
            if width <= 980 and height >= 768:
                page.locator('.description-tab.defender').click()
                assert page.locator('.skill-descriptions').get_attribute('data-active') == 'defender'
                assert page.locator('.description.defender').is_visible()
                assert not page.locator('.description.attacker').is_visible()
        page.set_viewport_size({"width": 1440, "height": 1080})
        page.evaluate("qa.render('ally-win','attack')")
        tail = page.evaluate("qa.tail()")
        assert tail["retained"] and tail["visible"] > 0 and tail["finished"] == 0 and tail["duration"] == 1.4, tail
        page.evaluate("qa.render('ally-win','outcome')")
        motion = page.evaluate("""() => {
          let count=0;const reference={};const times=[0,0.25,0.6,0.75,0.9,2,2.8,3.15,4];
          for(const level of ['light','normal','rich']){
            const frames=times.map(t=>JSON.stringify(qa.seekMotion(t,level)));
            reference[level]=frames;
            for(const i of [8,0,7,1,6,2,5,3,4]){
              if(JSON.stringify(qa.seekMotion(times[i],level))!==frames[i])throw Error('motion depends on previous frame');
              count++;
            }
          }return {count,reference,times};
        }""")
        page.evaluate("qa.render('ally-win','outcome')")
        page.screenshot(path=str(OUT / "production-last.png"))
        page.goto((ROOT / "_local/fx_gallery/fx_gallery.html").as_uri(), wait_until="domcontentloaded", timeout=60000)
        assert page.locator('.scene-card [data-gallery-resolve-panel] .arena').count() >= 7
        assert page.locator('.scene-card .stage-host > .stage').count() == 0
        for width in [1440, 800]:
            page.set_viewport_size({"width": width, "height": 1080})
            eight = page.locator('.scene-card[data-effect="eight-effects"]')
            assert eight.locator('.stage-host .event-effect-band').count() == 0
            assert eight.locator('.stage-host .event-ko-shatter').count() == 3
            assert eight.locator('.stage-host .event-resolve-damage').count() == 3
            assert float(eight.get_attribute('data-end')) > float(eight.get_attribute('data-window'))
        page.goto((ROOT / "_local/resolve_preview/resolve_preview.html").as_uri(), wait_until="domcontentloaded")
        preview_checks = 0
        for level, frames in motion["reference"].items():
            page.locator('.level-select').select_option(level)
            for i in [8, 0, 7, 1, 6, 2, 5, 3, 4]:
                actual = page.evaluate("""time => {
                  const seek=document.querySelector('.seek');seek.value=String(time);seek.dispatchEvent(new Event('input'));
                  return JSON.stringify([...document.querySelectorAll('.preview-canvas .portrait,.preview-canvas .skill-plaque,.preview-canvas .gem,.preview-canvas .character-name,.preview-canvas .clash-point')].map(el=>el.style.cssText));
                }""", motion["times"][i])
                assert actual == frames[i], (level, motion["times"][i], actual, frames[i])
                preview_checks += 1
        assert not errors, errors
        browser.close()
    temporary.cleanup()
    print(json.dumps({"browser_checks": checks, "motion_checks": motion["count"], "preview_motion_checks": preview_checks,
                      "attack_tail": tail, "page_errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
