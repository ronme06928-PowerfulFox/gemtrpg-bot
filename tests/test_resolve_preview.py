"""計画57: 本番を変更しない、時刻から描く比較用HTMLの契約。"""
import re
import hashlib
import subprocess
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest

from tests.test_motion_fx_frontend import ROOT, _run_node


def test_preview_samples_and_timeline_keep_the_production_outcome_plan():
    _run_node(r"""
(async () => {
  const fx = loadShared({});
  const { loadSamples } = await import('./scripts/resolve_preview/skills.mjs');
  const samples = await loadSamples();
  const { createTimeline, phaseAt } = await import('./scripts/resolve_preview/timeline.mjs');
  const { planResolveOutcome, collectKnockouts } = await import('./static/js/battle/components/resolve_flow_result_fx.js');
  const { resolveStageTiming, resolveOutcomeWindow } = await import('./static/js/battle/components/resolve_flow_fx.js');
  assert.strictEqual(new Set(samples.map(s => s.id)).size, samples.length);
  for (const id of ['ally-win','enemy-ko','long-names','one-sided','summation','fizzle','silhouette']) {
    assert.ok(samples.some(s => s.id === id), id);
  }
  assert.ok(samples.find(s=>s.id==='long-names').skills.attacker.fields.reduce((sum,f)=>sum+f.text.length,0) > 200);
  assert.ok(samples.find(s=>s.id==='long-names').skills.attacker.name.length >= 20);
  assert.ok(samples.find(s=>s.id==='silhouette').state.characters.some(c=>!c.image));
  assert.strictEqual(collectKnockouts(samples.find(s=>s.id==='enemy-ko').step).size,1);
  assert.strictEqual(samples.find(s=>s.id==='summation').step.damageEvents.length,3);
  assert.ok(new Set(samples.map(s=>s.state.characters.find(c=>c.id==='a').image)).size>=3);
  for (const sample of samples) for (const level of ['light','normal','rich']) for (const waitSeconds of [0.5,1,2]) {
    const timeline = createTimeline(sample, fx, level, waitSeconds);
    const timing = resolveStageTiming(sample.step);
    const fizzle = sample.step.kind === 'fizzle';
    assert.strictEqual(timeline.outcomeStart,fizzle?2:2.8);
    assert.ok(Math.abs(timeline.waitStart-(fizzle?3:2.8+timing.at(-1).ms/1000))<1e-9);
    assert.strictEqual(timeline.duration,timeline.waitStart+(fizzle?0.5:waitSeconds));
    assert.strictEqual(timeline.outcomeWindow,timeline.duration-timeline.outcomeStart);
    assert.strictEqual(phaseAt(timeline,0),'names');
    assert.strictEqual(phaseAt(timeline,0.6),'power');
    assert.strictEqual(phaseAt(timeline,2),fizzle?'outcome':'attack');
    assert.strictEqual(phaseAt(timeline,timeline.outcomeStart),'outcome');
    assert.strictEqual(phaseAt(timeline,timeline.waitStart),'wait');
    const plan=planResolveOutcome(sample.step,timeline.popups,timeline.outcomeWindow,fx,
      id=>id===sample.step.attackerActorId?'attacker':'defender');
    const actual=timeline.events.filter(e=>['resolve-damage','effect-band','ko-shatter'].includes(e.name));
    assert.deepStrictEqual(actual.map(e=>[e.name,e.at,e.targetId,e.params.stackPushes]),
      plan.events.map(e=>[e.name,e.at+timeline.outcomeStart,e.targetId,e.params.stackPushes]));
    for (const event of timeline.events) {
      assert.ok(event.at>=0);
      assert.ok(event.at+(event.params.duration??fx.get(event.name).duration)<=timeline.duration+1e-6, sample.id);
      assert.ok(event.anchor);
    }
    if (fizzle) { assert.strictEqual(timeline.events.length,0);assert.strictEqual(timeline.duration,3.5); }
    else {
      const attack=timeline.events.find(e=>e.name.startsWith('attack-'));
      assert.strictEqual(attack.at+0.8,timeline.outcomeStart);
      assert.ok(attack.at+fx.get(attack.name).duration>timeline.outcomeStart);
    }
    if (sample.step.kind==='one_sided') {
      assert.strictEqual(timeline.events.filter(e=>e.name==='power-roll').length,1);
    }
    if (sample.step.kind==='mass_summation') {
      assert.strictEqual(timeline.events.filter(e=>e.name==='power-roll').length,5);
      assert.ok(actual.filter(e=>e.name==='resolve-damage').every(e=>e.anchor==='portrait:'+e.targetId));
    }
  }
})().catch(e=>{ console.error(e);process.exitCode=1; });
""")


def test_v2_skills_are_cache_values_and_missing_data_stops_build():
    _run_node(r"""
(async()=>{
  const { loadSamples, hydrateSamples, plainSkillText }=await import('./scripts/resolve_preview/skills.mjs');
  const { samples:specs }=await import('./scripts/resolve_preview/samples.mjs');
  const cache=JSON.parse(fs.readFileSync('data/cache/skills_cache.json','utf8'));
  const samples=await loadSamples();
  await assert.rejects(loadSamples('missing-preview-skills-cache.json'),/スキルキャッシュ.*見つかりません/);
  assert.throws(()=>hydrateSamples(specs,{}),/スキルID/);
  for(const sample of samples) for(const side of ['attacker','defender']) {
    const id=sample.skillIds[side], skill=sample.skills[side];
    if(!id){assert.strictEqual(skill,null);continue;}
    assert.strictEqual(skill.id,cache[id]['スキルID']);
    assert.strictEqual(skill.attribute,cache[id]['属性']);
    if(sample.id!=='long-names') assert.strictEqual(skill.name,cache[id]['デフォルト名称']);
    assert.deepStrictEqual(skill.fields,['使用時効果','発動時効果','特記'].filter(label=>cache[id][label]?.trim())
      .map(label=>({label,text:cache[id][label]})));
  }
  assert.strictEqual(plainSkillText('([[W-20|的中時]]):[[W-02|破裂]]3を付与。'),'（的中時）:破裂3を付与。'.replace('（','(').replace('）',')'));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_v2_fixed_boxes_and_shared_damage_bases_do_not_intersect():
    _run_node(r"""
(async()=>{
  const { getLayout, damageBases, damageEnterOffsets, sideBox }=await import('./scripts/resolve_preview/layout.mjs');
  const { loadSamples }=await import('./scripts/resolve_preview/skills.mjs');
  const { createTimeline }=await import('./scripts/resolve_preview/timeline.mjs');
  const fx=loadShared({});
  for(const width of [1180,660]) {
    const layout=getLayout(width), {damage,band}=layout;
    assert.ok(band.x+band.width<damage.x);
    assert.ok(damage.x+damage.width<=width/2);
    assert.strictEqual(band.height,180);
    assert.ok(band.y>layout.plaqueTop+layout.plaqueHeight);
    assert.ok(damage.y+damage.height<=layout.arenaHeight);
    const rightBand=sideBox(layout,band,'defender'),rightDamage=sideBox(layout,damage,'defender');
    assert.ok(rightDamage.x+rightDamage.width<rightBand.x);
    for(const sample of await loadSamples()) for(const wait of [0.5,1,2]) {
      const timeline=createTimeline(sample,fx,'rich',wait);
      const bases=damageBases(sample,timeline,layout);
      const damageEvents=timeline.events.filter(e=>e.name==='resolve-damage');
      assert.strictEqual(bases.size,new Set(damageEvents.map(e=>e.targetId)).size);
      for(const event of damageEvents) {
        const base=bases.get(event.targetId);
        assert.ok(base.x>=0&&base.y>=damage.y&&base.y<=damage.y+damage.height);
        const totalPush=(event.params.stackPushes||[]).reduce((n,p)=>n+p.amount,0);
        assert.ok(base.y-totalPush-26>=damage.y,sample.id);
      }
      // 実際の定義を描き、同時に入る追加数字も0.1秒ごとに交差しないことを確認する。
      for(const level of ['light','normal','rich']) {
        const offsets=damageEnterOffsets(timeline),doc=makeDocument();
        const rendered=damageEvents.map(event=>{
          const effect=Object.create(fx.get(event.name)),root=doc.createElement('div');
          effect.mount(root,{...event.params,level,stackEnter:offsets.get(event)});
          return {event,effect};
        });
        for(let time=0;time<timeline.duration;time+=0.1) {
          const visible=[];
          for(const row of rendered) {
            const age=time-row.event.at;
            if(age<0||age>=row.effect.duration)continue;
            row.effect.render(age);
            if(Number(row.effect.el.style.opacity)<0.15)continue;
            const transform=row.effect.el.style.transform;
            const y=bases.get(row.event.targetId).y+Number(transform.match(/translateY\(([^p]+)px\)/)[1]);
            const scale=Number(transform.match(/scale\(([^)]+)\)/)?.[1]||1);
            visible.push({id:row.event.targetId,y,height:(row.event.params.kind==='dice'?46:30)*scale});
          }
          for(let i=0;i<visible.length;i++)for(let j=i+1;j<visible.length;j++) {
            const a=visible[i],b=visible[j];
            if(a.id===b.id)assert.ok(Math.abs(a.y-b.y)>=(a.height+b.height)/2,sample.id+' '+time);
          }
        }
      }
    }
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


class PreviewResources(HTMLParser):
    def handle_starttag(self, tag, attrs):
        assert tag not in {"html", "head", "body"}
        for key, value in attrs:
            if key in {"src", "href"} and value:
                assert value.startswith(("data:", "#")) or (
                    urlsplit(value).scheme == "https"
                    and urlsplit(value).netloc in {"fonts.googleapis.com", "fonts.gstatic.com"}
                ), value


@pytest.fixture(scope="module")
def preview_page():
    protected = [path for base in [ROOT / "static", ROOT / "events", ROOT / "manager"]
                 for path in base.rglob("*") if path.is_file()]
    protected += [ROOT / "app.py", ROOT / "models.py"]
    before = {path: hashlib.sha256(path.read_bytes()).digest() for path in protected}
    result = subprocess.run(
        ["node", "scripts/resolve_preview/build.mjs"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert all(hashlib.sha256(path.read_bytes()).digest() == digest for path, digest in before.items())
    return ROOT / "_local/resolve_preview/resolve_preview.html"


def test_preview_build_is_artifact_ready_and_self_contained(preview_page):
    assert sorted(p.name for p in preview_page.parent.iterdir()) == ["resolve_preview.html"]
    assert preview_page.stat().st_size <= 3 * 1024 * 1024
    html = preview_page.read_text(encoding="utf-8")
    assert "<title>舞台型の解決パネル</title>" in html[:8192]
    assert 'name="claude:viewport-fit-sides" content="cover"' in html[:8192]
    assert not re.search(r"<!doctype|</?(?:html|head|body)(?:\s|>)", html, re.I)
    PreviewResources().feed(html)
    for url in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", html):
        assert url.startswith(("data:", "#")), url
    assert not re.search(r"\b(?:fetch|alert)\(|localStorage", html)
    assert '<script type="module"' not in html
    # esbuildの入力へ本番ソースが実際に含まれることを別の契約テストでも検証する。
    assert 'data-build-inputs="' in html
    for name in ["fx_core.js", "fx_effects.js", "resolve_flow_result_fx.js", "resolve_flow_fx.js"]:
        assert name in html
    assert "prefers-reduced-motion" in html
    assert "variant-select" not in html
    assert "variant-b" not in html
    assert "無防備" not in html
    assert "mask-composite: intersect" in html


def test_built_preview_controls_and_seek_are_deterministic_without_network(preview_page):
    # 完成品のscriptを実行する。レイアウトの視覚検査とは区別する。
    _run_node(r"""
const page=fs.readFileSync('_local/resolve_preview/resolve_preview.html','utf8');
const script=page.match(/<script>([\s\S]*?)<\/script>/)[1];
function run(reduced) {
  const doc=makeDocument(), all=[];
  const original=doc.createElement;
  const descendants=node=>node.children.flatMap(child=>[child,...descendants(child)]);
  function matches(node,selector) {
    const anchor=selector.match(/\[data-anchor="([^"]+)"\]/);
    if(anchor) return node.dataset.anchor===anchor[1];
    if(selector.startsWith('.')) return node.className.split(' ').includes(selector.slice(1));
    return node.tagName===selector;
  }
  doc.createElement=tag=>{
    const node=original(tag); all.push(node); node.dataset={}; node.events={};
    node.append=(...children)=>children.forEach(child=>node.appendChild(child));
    node.replaceChildren=(...children)=>{node.children=[];node.append(...children);};
    node.addEventListener=(name,handler)=>{node.events[name]=handler;};
    node.style.setProperty=(name,value)=>{node.style[name]=value;};
    node.classList.toggle=(name,on)=>{
      if(on) node.classList.add(name);
      else node.className=node.className.split(' ').filter(c=>c!==name).join(' ');
    };
    node.querySelectorAll=selector=>descendants(node).filter(n=>selector.split(', ').some(s=>matches(n,s)));
    node.querySelector=selector=>node.querySelectorAll(selector)[0]||null;
    Object.defineProperty(node,'parentElement',{get:()=>node.parentNode});
    function stageCanvas(){let n=node;while(n&&!n.classList.contains('preview-canvas'))n=n.parentNode;return n;}
    Object.defineProperty(node,'offsetWidth',{get:()=>node.classList.contains('combatant')?parseFloat(stageCanvas().style.width)/2:parseFloat(node.style.width)||100});
    Object.defineProperty(node,'offsetHeight',{get:()=>node.classList.contains('combatant')?parseFloat(stageCanvas().style['--arena-height']):node.className.includes('preview-canvas')?(node.className.includes('narrow')?816:716):70});
    Object.defineProperty(node,'offsetTop',{get:()=>11});
    Object.defineProperty(node,'clientWidth',{get:()=>node.className==='preview-view'?368:100});
    Object.defineProperty(node,'scrollWidth',{get:()=>node.className==='skill-name'?500:100});
    node.getBoundingClientRect=()=>({left:0,top:0,right:node.offsetWidth,bottom:node.offsetHeight,width:node.offsetWidth,height:node.offsetHeight});
    return node;
  };
  doc.createElementNS=(ns,tag)=>{const n=doc.createElement(tag);n.namespaceURI=ns;return n;};
  doc.createTextNode=text=>{const n=doc.createElement('text');n.textContent=text;return n;};
  const main=doc.createElement('main');main.id='resolve-preview';doc.body.appendChild(main);
  doc.getElementById=id=>all.find(n=>n.id===id);
  let raf,now=0,resize;
  const context={document:doc,console,performance:{now:()=>now},
    getComputedStyle:()=>({fontSize:'27px'}), matchMedia:()=>({matches:reduced}),
    ResizeObserver:class { constructor(callback){resize=callback;} observe(){} },
    requestAnimationFrame:callback=>{raf=callback;},
  };
  context.window=context;vm.createContext(context);
  try { vm.runInContext(script,context); } catch(error) { assert.fail(error.message); }
  const find=cls=>main.querySelector('.'+cls);
  const sample=find('sample-select'),width=find('width-select'),level=find('level-select'),wait=find('wait-slider');
  assert.strictEqual(find('variant-select'),null);
  assert.strictEqual(wait.value,'1');
  assert.strictEqual(level.value,reduced?'light':'normal');
  const seek=find('seek'),clock=find('clock'),host=find('stage-host');
  const canvas=()=>host.children[0];
  const input=value=>{seek.value=String(value);seek.events.input();};
  assert.ok(clock.value.startsWith('4.60'));
  assert.strictEqual(sample.children.length,9);
  for(const option of sample.children) {
    sample.value=option.value;sample.events.change();
    assert.ok(clock.value.startsWith('0.00'));
    for(const size of ['1180','660']) {
      width.value=size;width.events.change();
      assert.strictEqual(canvas().style.width,size+'px');
      assert.ok(parseFloat(host.style.width)<=368);
      assert.ok(parseFloat(host.style.height)>0);
      for(const strength of ['light','normal','rich']) {
        level.value=strength;level.events.change();
        for(const t of [0,0.6,1,2,2.8,3,Number(seek.max)-0.1]) {
          input(t);const shot=snapshot(canvas());
          input(Number(seek.max));input(t);
          assert.strictEqual(snapshot(canvas()),shot,option.value+' seek '+t);
          assert.ok(!shot.includes('NaN')&&!shot.includes('undefinedpx'));
        }
        input(1);
        assert.strictEqual(canvas().querySelector('.skill-descriptions').style.visibility,'visible');
        if(option.value!=='fizzle') assert.ok(canvas().querySelectorAll('.fx-root').some(n=>!n.hidden));
        input(0);
        assert.strictEqual(canvas().querySelector('.skill-descriptions').style.visibility,'hidden');
        assert.ok(canvas().querySelectorAll('.fx-root').every(n=>n.hidden));
      }
      input(1);width.events.change();assert.ok(clock.value.startsWith('1.00'));
      for(const value of ['0.5','1','2']) {
        wait.value=value;wait.events.input();
        if(option.value==='fizzle') {assert.ok(wait.disabled);assert.strictEqual(Number(seek.max),3.5);}
        else {assert.ok(!wait.disabled);assert.ok(Math.abs(Number(seek.max)-(option.value==='enemy-ko'||option.value==='summation'?6.9:5.4)-Number(value))<1e-6);}
      }
      if(option.value==='one-sided') {
        const defender=canvas().querySelectorAll('.combatant').find(n=>n.className.includes('defender'));
        assert.strictEqual(defender.querySelector('.gem'),null);
        assert.strictEqual(defender.querySelector('.skill-plaque'),null);
        assert.strictEqual(defender.querySelector('.unarmed'),null);
        assert.strictEqual(canvas().querySelector('.clash-point').textContent,'一方攻撃');
      }
      if(option.value==='summation') {
        assert.strictEqual(canvas().querySelectorAll('.participant').length,3);
        assert.strictEqual(canvas().querySelectorAll('.small-gem').length,3);
      }
      if(option.value==='fizzle') assert.strictEqual(canvas().querySelectorAll('.fx-root').length,0);
      const ko=canvas().querySelector('.half-ko');
      if(option.value==='enemy-ko') {
        assert.ok(ko);
        assert.strictEqual(ko.children[0].style.width,size==='1180'?'590px':'330px');
        assert.strictEqual(ko.children[0].style.height,size==='1180'?'420px':'374px');
      }
      const targets=new Map();
      for(const root of canvas().querySelectorAll('.event-resolve-damage')) {
        assert.ok(root.parentNode.className.includes('damage-lane'));
        const id=root.dataset.targetId;
        if(targets.has(id))assert.strictEqual(root.style.top,targets.get(id));
        else targets.set(id,root.style.top);
      }
    }
  }
  input(0);find('play-button').events.click();now+=250;raf(now);
  assert.ok(clock.value.startsWith('0.25'));
  find('pause-button').events.click();now+=250;raf(now);assert.ok(clock.value.startsWith('0.25'));
  find('restart-button').events.click();assert.ok(clock.value.startsWith('0.00'));
  input(Number(seek.max));find('loop').checked=true;find('play-button').events.click();
  now+=Number(seek.max)*1000+200;raf(now);assert.ok(clock.value.startsWith('0.20'));
  resize();assert.ok(parseFloat(host.style.height)>0);
  find('marker-buttons').children[2].events.click();assert.ok(clock.value.startsWith('2.00'));
  for(const image of descendants(main).filter(n=>n.tagName==='img')) {
    assert.ok(String(image.src||image.attributes.src).startsWith('data:'));
  }
}
run(false);run(true);
""")
