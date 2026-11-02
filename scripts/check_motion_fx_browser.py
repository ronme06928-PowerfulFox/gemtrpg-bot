"""PR4.5b: real browser checks for reversible reactions in generated previews."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_local/pr45b_check"


def seek(page, value, scope=""):
    return page.locator(f"{scope} .seek".strip()).evaluate(
        "(el,t)=>{el.value=String(t);el.dispatchEvent(new Event('input'));}", value)


def choose(locator, value):
    locator.evaluate("(el,v)=>{el.value=v;el.dispatchEvent(new Event('change'));}", value)


def main():
    checks = 0
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", timeout=15000)
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://**", lambda route: route.abort())
        page.goto((ROOT / "_local/fx_gallery/fx_gallery.html").as_uri(), wait_until="domcontentloaded")
        assert page.locator(".gallery-card").count() == 25
        for effect in ["attack-slash", "attack-strike", "attack-pierce", "hit-react", "hit-shake"]:
            card = f'.effect-card[data-effect="{effect}"]'
            options = page.locator(card + " .sample option").evaluate_all("els=>els.map(el=>el.value)")
            # 全パラメータの組はNodeテストで覆い、実DOMでは両端の代表を検査する。
            options = [options[0], options[-1]]
            for option in options:
                choose(page.locator(card + " .sample"), option)
                for strength in ["light", "normal", "rich"]:
                    choose(page.locator(card + " .level"), strength)
                    for t in ([0.04, 0.15, 0.3] if effect.startswith("hit-") else [0.69, 0.7, 0.75, 0.78, 1.08]):
                        seek(page, t, card)
                        shot = page.locator(card + " .stage-host").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))")
                        seek(page, 0, card)
                        seek(page, t, card)
                        assert page.locator(card + " .stage-host").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))") == shot, (effect, option, strength, t)
                        checks += 1
                    seek(page, 0.04, card)
                    changed = page.locator(card + " .stage-host [data-anchor]").evaluate_all(
                        "els=>els.filter(el=>el.style.translate && el.style.translate!=='none').length")
                    if effect.startswith("hit-"):
                        assert bool(changed) == (strength != "light" and not (effect == "hit-shake" and "small" in option)), (effect, option, strength, changed)
                    seek(page, 1.4, card)
                    assert not page.locator(card + " .stage-host [data-anchor]").evaluate_all("els=>els.some(el=>el.style.translate)")
            print(effect, checks, flush=True)
        print("gallery checks", checks, flush=True)
        page.goto((ROOT / "_local/resolve_preview/resolve_preview.html").as_uri(), wait_until="domcontentloaded")
        for width in ["1180", "660"]:
            choose(page.locator(".width-select"), width)
            for sample in ["ally-win", "enemy-ko", "one-sided", "summation", "fizzle", "hard-attack", "mass-individual"]:
                choose(page.locator(".sample-select"), sample)
                for level in ["light", "normal", "rich"]:
                    choose(page.locator(".level-select"), level)
                    for t in [2.4, 2.44, 2.52, 2.6, 2.8, 0]:
                        seek(page, t)
                        shot = page.locator(".preview-canvas").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))")
                        seek(page, 4.5)
                        seek(page, t)
                        assert page.locator(".preview-canvas").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))") == shot, (sample, level, t)
                        checks += 1
                    if sample == "summation" and level != "light":
                        seek(page, 2.44)
                        assert page.locator(".participants .portrait").evaluate_all("els=>els.every(el=>!!el.style.translate)")
                        seek(page, 2.52)
                        data = page.evaluate("""() => {
                          const lane=document.querySelector('[data-anchor="damage:participants"]');
                          const group=document.querySelector('.participants');
                          const attack=document.querySelector('.event-attack-slash,.event-attack-strike,.event-attack-pierce,.event-attack-flash');
                          const numbers=[...lane.querySelectorAll('.fx-root')];
                          return {lane:lane.style.translate,group:group.style.translate,attack:attack.style.translate,
                            inBounds:numbers.every(el=>parseFloat(el.style.left)>0&&parseFloat(el.style.left)<parseFloat(lane.style.width))};
                        }""")
                        assert data["lane"] and data["lane"] == data["group"] == data["attack"], data
                        assert data["inBounds"], data
        choose(page.locator(".sample-select"), "summation")
        choose(page.locator(".width-select"), "1180")
        choose(page.locator(".level-select"), "rich")
        seek(page, 2.52)
        OUT.mkdir(parents=True, exist_ok=True)
        page.locator(".preview-view").screenshot(path=str(OUT / "latest.png"))
        assert not errors, errors
        browser.close()
    print(json.dumps({"browser_checks": checks, "page_errors": errors}))


# 実際のResolveFlowPanelを描く既存の検査用バンドルへ、画素検査と計測の入口だけ足す。
CANVAS_QA = r"""
window.qa.paint = params => {
  window.qa.paintRoot?.remove();
  const root=document.createElement('div');document.body.append(root);window.qa.paintRoot=root;
  const fx=Object.create(Fx.get('attack-'+params.kind));fx.mount(root,params);window.qa.paintFx=fx;
  if(root.querySelectorAll('canvas').length!==1||root.querySelector('svg'))throw Error('attack must own one canvas');
  return {counts:fx.counts,dpr:fx.dpr};
};
window.qa.pixels = t => {
  const fx=window.qa.paintFx;fx.render(t===null?Infinity:t);
  if(!fx.canvas.width)return {hash:0,painted:0,width:0,height:0};
  const bytes=fx.ctx.getImageData(0,0,fx.canvas.width,fx.canvas.height).data;
  let hash=2166136261,painted=0;
  for(let i=0;i<bytes.length;i+=4){hash=Math.imul(hash^bytes[i],16777619);hash=Math.imul(hash^bytes[i+1],16777619);hash=Math.imul(hash^bytes[i+2],16777619);hash=Math.imul(hash^bytes[i+3],16777619);if(bytes[i+3])painted++;}
  return {hash:hash>>>0,painted,width:fx.canvas.width,height:fx.canvas.height};
};
window.qa.prepareOverlap = (attribute,level,scenario) => {
  window.qa.paintRoot?.remove();flow._finishFx();events=[];flow._renderedStepKey=null;
  const sample=structuredClone(samples.find(s=>s.id===scenario));
  for(const c of sample.state.characters)if(c.image)c.image=window.qa.assetRoot+c.image;
  flow._skillById=id=>({...skills[id],'属性':attribute});
  store._state=sample.state;flow._activeStep=sample.step;
  window.qaLevel=level;window.Fx.getLevel=()=>level;
  const starts=resolveStageStarts(sample.step),frozen=Date.now();
  flow._stepStartedAt=frozen-starts.attack*1000;flow._renderStep(sample.state);
  events=[];
  playResolveStageFx(flow,{stage:'attack',outcome:sample.step.outcome},sample.state);
  flow._stepStartedAt=frozen-starts.outcome*1000;flow._renderStep(sample.state);
  playResolveStageFx(flow,{stage:'outcome',outcome:sample.step.outcome},sample.state);
  const canvas=document.querySelector('.resolve-stage-canvas');
  const attack=events.find(e=>e.name.startsWith('attack-'));
  window.qa.overlapFrame=age=>{
    renderStageMotion(canvas,stageMotionAt(sample.step,starts.outcome+age,level));
    for(const event of events){
      const time=event.name.startsWith('attack-')?0.7+age:age-(event.options.delaySeconds||0);
      event.root.hidden=time<0||time>=event.fx.duration;
      event.fx.render(time<0?0:time>=event.fx.duration?Infinity:time);
    }
    canvas.getBoundingClientRect();
  };
  window.qa.overlapFrame(0.22);
  return {layout:parseFloat(canvas.style.width),viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,
    canvas:[attack.fx.pixelWidth,attack.fx.pixelHeight],ratio:attack.fx.dpr,counts:attack.fx.counts,
    effects:events.map(e=>e.name),imagesReady:[...canvas.querySelectorAll('img')].every(e=>e.complete)};
};
window.qa.measureOverlap = async () => {
  const intervals=[],renders=[];let last=null;
  for(let i=0;i<90;i++){
    const now=await new Promise(resolve=>requestAnimationFrame(resolve));
    if(i>=20)intervals.push(now-last);
    const start=performance.now();window.qa.overlapFrame(0.18+(i%60)*0.006);
    const elapsed=performance.now()-start;if(i>=20)renders.push(elapsed);last=now;
  }
  const summary=values=>{values.sort((a,b)=>a-b);return {median:values[Math.floor(values.length/2)],p95:values[Math.floor(values.length*.95)],max:values.at(-1)};};
  return {frames:intervals.length,frameMs:summary(intervals),renderMs:summary(renders)};
};
"""


def canvas_main(pixel_scale=1, software_canvas=False):
    import subprocess
    from check_resolve_stage_browser import BUNDLE

    output = ROOT / "_local/pr45e_check"
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / "canvas_check.html"
    bundle = BUNDLE.replace("}};\n`;", "}};\n" + CANVAS_QA + "\n`;")
    assert bundle != BUNDLE
    bundle = bundle.replace("root.className='fx-root';", "root.className='fx-root event-'+name;")
    bundle = bundle.replace("level:'normal'", "level:window.qaLevel||'normal'")
    if pixel_scale != 1:
        assert "fx.render(0.5);" in bundle
        bundle = bundle.replace("fx.render(0.5);", f"if(fx.canvas){{fx.dpr*={pixel_scale};fx.pixelWidth=Math.floor(fx.pixelWidth*{pixel_scale});fx.pixelHeight=Math.floor(fx.pixelHeight*{pixel_scale});}}fx.render(0.5);")
    # 元のバンドルではFxはwindow.Fx。描画定義の追加入口も同じ実体を使う。
    bundle = bundle.replace("const source = `", "const source = `const Fx=window.Fx;\n")
    subprocess.run(["node", "--input-type=module", "-e", bundle, str(fixture)], cwd=ROOT, check=True, timeout=120)
    errors, measurements = [], []
    checks = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", timeout=15000)
            page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=2)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("https://**", lambda route: route.abort())
            page.goto(fixture.as_uri(), wait_until="domcontentloaded")
            # 連続readbackでGPU/CPUのラスタライズ先が途中で切り替わらないよう、画素検査だけCPU読取り用にする。
            page.evaluate("""() => {
              const original=HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext=function(kind,options){return original.call(this,kind,kind==='2d'?{...options,willReadFrequently:true}:options);};
            }""")
            for kind in ["slash", "strike", "pierce"]:
                for level in ["light", "normal", "rich"]:
                    for mode in ["hit", "wide", "draw"]:
                        params = dict(kind=kind, level=level, tier="large", tone="ally", direction=-1, mode=mode, width=320, height=240)
                        page.evaluate("params=>qa.paint(params)", params)
                        times = [0, 0.69, 0.7, 0.75, 0.78, 0.9, 1.1, None]
                        shots = [page.evaluate("t=>qa.pixels(t)", t) for t in times]
                        for i in [7, 0, 5, 3, 6, 1, 4, 2]:
                            actual = page.evaluate("t=>qa.pixels(t)", times[i])
                            assert actual == shots[i], (kind, level, mode, times[i], actual, shots[i])
                            checks += 1
                        assert shots[0]["painted"] == shots[-1]["painted"] == 0
                        assert shots[5]["painted"] > 0
                        if level == "light":
                            assert shots[1]["painted"] == 0
                            assert shots[5] == shots[6]
            print("canvas pixel checks", checks, flush=True)
            # readbackによるCanvasの実装切替を計測に混ぜないよう、文書を開き直す。
            page.goto(fixture.as_uri(), wait_until="domcontentloaded")
            if software_canvas:
                page.evaluate("""() => {
                  const original=HTMLCanvasElement.prototype.getContext;
                  HTMLCanvasElement.prototype.getContext=function(kind,options){return original.call(this,kind,kind==='2d'?{...options,willReadFrequently:true}:options);};
                }""")
            page.evaluate("root=>{qa.assetRoot=root;}", ROOT.as_uri())
            for width, height in [(1440, 1080), (800, 768)]:
                page.set_viewport_size({"width": width, "height": height})
                for attribute in ["斬撃", "打撃", "貫通"]:
                    for level in ["normal", "rich"]:
                        condition = page.evaluate("([a,l])=>qa.prepareOverlap(a,l,'ally-win')", [attribute, level])
                        assert "effect-band" in condition["effects"] and "resolve-damage" in condition["effects"]
                        page.wait_for_function("[...document.querySelectorAll('.arena img')].every(e=>e.complete)")
                        condition["imagesReady"] = page.evaluate("[...document.querySelectorAll('.arena img')].every(e=>e.complete&&e.naturalWidth>0)")
                        assert condition["imagesReady"]
                        # 本番では名前・威力の段階で立ち絵が既に見えているため、画像デコードを計測へ混ぜない。
                        page.evaluate("Promise.all([...document.querySelectorAll('.arena img')].map(e=>e.decode()))")
                        assert "reveal-outcome" in page.locator('#resolve-flow-panel').get_attribute('class')
                        result = page.evaluate("()=>qa.measureOverlap()")
                        measurements.append(dict(attribute=attribute, level=level, **condition, **result))
                        print(json.dumps(measurements[-1], ensure_ascii=False), flush=True)
            # 最新1点の見本。実際の舞台で攻撃・数字・効果の帯が重なるところ。
            page.set_viewport_size({"width": 1440, "height": 1080})
            page.evaluate("()=>qa.prepareOverlap('斬撃','rich','ally-win')")
            page.evaluate("()=>qa.overlapFrame(.22)")
            page.locator('.resolve-stage-canvas').screenshot(path=str(output / "latest.png"))
            page.goto((ROOT / "_local/fx_proto/slash_proto.html").as_uri(), wait_until="domcontentloaded")
            for kind in ["slash", "strike", "pierce"]:
                choose(page.locator('.attribute'), kind)
                assert page.locator('.row:not([hidden])').count() == (3 if kind == 'slash' else 2)
                assert page.locator('.row').first.locator('canvas').count() == 1
                seek(page, .9)
            assert not errors, errors
            browser.close()
        report = dict(pixel_checks=checks, page_errors=errors, browser="Chrome/headless " + browser.version, device_scale_factor=2,
                      frames="20 warmup + 70 samples per case; outcome age 0.18..0.534s", pixel_scale=pixel_scale, software_canvas=software_canvas, measurements=measurements)
        (output / "measurements.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(dict(pixel_checks=checks, page_errors=errors), ensure_ascii=False))
    finally:
        fixture.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--canvas", action="store_true", help="PR4.5e pixel checks and production-stage frame measurement")
    parser.add_argument("--pixel-scale", type=float, default=1, help="Measurement only: multiply the production pixel ratio (0 < scale <= 1)")
    parser.add_argument("--software-canvas", action="store_true", help="Measurement only: compare CPU Canvas 2D")
    args = parser.parse_args()
    if not 0 < args.pixel_scale <= 1:
        parser.error("--pixel-scale must be greater than 0 and at most 1")
    canvas_main(args.pixel_scale, args.software_canvas) if args.canvas else main()
