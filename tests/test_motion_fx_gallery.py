"""計画56: 本番の定義・結果計画をそのまま使う単体HTML。"""
import re
import subprocess
from html.parser import HTMLParser

import pytest

from tests.test_motion_fx_frontend import ROOT, _run_node


def test_gallery_samples_cover_exactly_the_registered_effects_and_variants():
    _run_node(r"""
(async () => {
  const { effectSamples, sceneSamples } = await import('./scripts/fx_gallery/samples.mjs');
  const context = {};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/js/fx/fx_core.js', 'utf8'), context);
  const defined = [], define = context.Fx.define;
  context.Fx.define = (name, def) => { defined.push(name); define(name, def); };
  vm.runInContext(fs.readFileSync('static/js/fx/fx_effects.js', 'utf8'), context);
  assert.deepStrictEqual([...new Set(effectSamples.map(s => s.effect))].sort(), defined.sort());
  const all = [...effectSamples, ...sceneSamples];
  assert.strictEqual(new Set(all.map(s => s.id)).size, all.length);
  for (const sample of all) {
    assert.ok(sample.label && ['light','normal','rich'].includes(sample.level));
  }
  for (const effect of ['attack-slash','attack-strike','attack-pierce']) {
    const rows = effectSamples.filter(s => s.effect === effect);
    for (const tier of ['small','medium','large']) for (const direction of [1,-1]) {
      for (const mode of ['hit','wide','draw']) {
        assert.ok(rows.some(s => s.params.tier === tier && s.params.direction === direction && s.params.mode === mode));
      }
    }
  }
  const damage = effectSamples.filter(s => s.effect === 'resolve-damage');
  for (const tone of ['ally','enemy','extra']) assert.ok(damage.some(s => s.params.tone === tone));
  for (const shake of ['small','medium','large']) assert.ok(damage.some(s => s.params.shake === shake));
  for (const status of ['出血','破裂','亀裂','荊棘','戦慄','蓄力','凝魔']) assert.ok(damage.some(s => s.params.label === status));
  const effects = effectSamples.filter(s => s.effect === 'effect-band');
  for (const name of ['power-roll','chat-dice']) {
    assert.ok(effectSamples.some(s => s.effect === name && s.params.range));
    assert.ok(effectSamples.some(s => s.effect === name && !s.params.range));
  }
  assert.ok(sceneSamples.some(s => s.step.applied.fired_effects.length > 3));
  for (const tone of ['ally','enemy','self']) assert.ok(effects.some(s => s.params.lines.some(line=>line.tone === tone)));
  assert.ok(effects.some(s => s.params.lines.filter(line=>line.kind==='result').length > 1));
  assert.ok(effects.some(s => s.params.lines.length===1 && s.params.lines[0].text==='混乱'));
  for (const mode of ['hit','chip']) assert.ok(effectSamples.some(s => s.effect === 'ko-shatter' && s.params.mode === mode));
})().catch(e => { console.error(e); process.exitCode = 1; });
""")


def test_scene_events_use_the_production_plan_positions_tones_and_fit_the_derived_outcome_window():
    _run_node(r"""
(async () => {
  global.window = { Fx: loadShared({}) };
  const { sceneSamples } = await import('./scripts/fx_gallery/samples.mjs');
  const { collectSceneEvents } = await import('./scripts/fx_gallery/scene.mjs');
  const { ResolveFlowPanel } = await import('./static/js/battle/components/ResolveFlowPanel.js');
  const { collectDamagePopups, attackTier } = await import('./static/js/battle/components/resolve_flow_fx.js');
  const { planResolveOutcome, collectKnockouts, collectDamageKnockouts } = await import('./static/js/battle/components/resolve_flow_result_fx.js');
  assert.strictEqual(sceneSamples.length, 5);
  const panels = new Map();
  global.document = { getElementById: id => panels.get(id) };
  for (const scene of sceneSamples) {
    const {step, state} = scene;
    assert.ok(step.kind && step.outcome && step.attackerActorId && step.defenderActorId);
    assert.ok(step.rolls && Array.isArray(step.applied.damage) && Array.isArray(step.applied.fired_effects));
    assert.ok(Array.isArray(step.applied.statuses) && Array.isArray(step.damageEvents) && Array.isArray(step.selfDestructed));
    const measured = [];
    const panel = {id: scene.id, getBoundingClientRect: () => ({left:0,top:0}),
      querySelector(selector) {
        measured.push(selector);
        const chip = selector.includes('participant-chip');
        return {getBoundingClientRect: () => ({left:chip?200:100,top:50,width:chip?32:160,height:chip?32:240})};
      }};
    panels.set(panel.id, panel);
    const flow = new ResolveFlowPanel();
    const entries = flow._collectDamageSummary(step, state).entries;
    const popups = collectDamagePopups(entries, [...step.applied.damage, ...step.damageEvents]);
    const plan = planResolveOutcome(step, popups, 4.6, name=>window.Fx.get(name).duration, id=>id==='a'?'attacker':'defender').events;
    for (const level of ['light','normal','rich']) {
      const {events,beatSeconds} = collectSceneEvents(scene, panel, level);
      assert.ok(beatSeconds>=0.25&&beatSeconds<=0.5);
      const actual = events.filter(e => ['resolve-damage','effect-band','ko-shatter'].includes(e.name));
      assert.deepStrictEqual(actual.map(e => [e.name,e.at]), plan.map(e => [e.name,e.at]));
      for (const event of events) {
        assert.ok(event.at >= 0 && event.at + (event.params.duration??window.Fx.get(event.name).duration) <= 4.600001, scene.id);
        assert.ok(event.params.width > 0 && event.params.height > 0);
      }
      for (const event of actual) {
        const planned = plan.find(e => e.name === event.name && e.at === event.at && e.params.text === event.params.text);
        assert.ok(planned);
        if (event.params.self) assert.strictEqual(event.params.tone,'self');
        if (event.params.kind === 'effect') assert.strictEqual(event.params.tone,'extra');
      }
      if (step.kind === 'mass_summation') {
        assert.strictEqual(actual.filter(e => e.name === 'resolve-damage').length, 3);
        const ko = actual.find(e => e.name === 'ko-shatter');
        assert.strictEqual(ko.params.mode, 'chip');
        assert.strictEqual(ko.params.width, 32);
        assert.ok(measured.some(s => s.includes('data-actor-id="e"')));
      }
    }
    if (scene.id === 'fear-ko') {
      assert.ok(collectDamageKnockouts(step).has('d'));
      assert.strictEqual(plan.find(e => e.name === 'effect-band').params.lines.at(-1).text,'混乱');
    }
    if (scene.id === 'self-destruct') {
      assert.ok(collectKnockouts(step).has('a'));
      assert.ok(!collectDamageKnockouts(step).has('a'));
      assert.strictEqual(attackTier(2),'small');
    }
  }
  assert.strictEqual(window.Fx.play, undefined);
})().catch(e => { console.error(e); process.exitCode = 1; });
""")


class ResourceParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"src", "href"} and value:
                assert value.startswith(("data:", "#", "https://fonts.googleapis.com", "https://fonts.gstatic.com")), value


@pytest.fixture(scope="module")
def gallery_page():
    result = subprocess.run(
        ["node", "scripts/fx_gallery/build.mjs"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return ROOT / "_local/fx_gallery/fx_gallery.html"


def test_gallery_build_is_one_self_contained_html_under_2mb(gallery_page):
    output = ROOT / "_local/fx_gallery"
    assert sorted(p.name for p in output.iterdir()) == ["fx_gallery.html"]
    page = gallery_page
    assert page.stat().st_size <= 2 * 1024 * 1024
    html = page.read_text(encoding="utf-8")
    ResourceParser().feed(html)
    for url in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", html):
        assert not url.startswith(("http:", "https:", "/", "./", "../")), url
    assert '<script type="module"' not in html
    assert "fx_player.js" not in html
    assert "localStorage" not in html
    assert html.count('<script>') == 3


def test_built_page_mounts_all_cards_seeks_remounts_and_plays_without_file_reads(gallery_page):
    # ブラウザがfile://を拒否する環境でも、完成したHTMLの3つのscriptをそのまま実行する。
    # レイアウト・フォントの視覚確認の代わりにはしない。
    _run_node(r"""
const page = fs.readFileSync('_local/fx_gallery/fx_gallery.html','utf8');
const scripts = [...page.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const doc = makeDocument();
const all = [];
const originalCreate = doc.createElement;
function matches(node, selector) {
  const attr = selector.match(/\[data-actor-id="([^"]+)"\]/);
  if (attr && node.dataset.actorId !== attr[1]) return false;
  const simple = selector.replace(/\[[^\]]+\]/g,'');
  const classes = [...simple.matchAll(/\.([\w-]+)/g)].map(m => m[1]);
  if (!classes.every(c => node.className.split(' ').includes(c))) return false;
  const tag = simple.match(/^\w+/)?.[0];
  if (tag && node.tagName !== tag) return false;
  if (simple.startsWith('#') && node.id !== simple.slice(1)) return false;
  return true;
}
function descendants(node) { return node.children.flatMap(child => [child,...descendants(child)]); }
function query(node, selector) {
  const parts = selector.split(' ');
  return descendants(node).find(candidate => {
    if (!matches(candidate,parts.at(-1))) return false;
    let ancestor = candidate.parentNode;
    for (let i=parts.length-2; i>=0; i--) {
      while (ancestor && !matches(ancestor,parts[i])) ancestor=ancestor.parentNode;
      if (!ancestor) return false;
      ancestor=ancestor.parentNode;
    }
    return true;
  });
}
doc.createElement = tag => {
  const node = originalCreate(tag);
  all.push(node);
  node.dataset = {};
  node.events = {};
  node.addEventListener = (name,handler) => { node.events[name]=handler; };
  node.append = (...children) => children.forEach(child => node.appendChild(child));
  node.replaceChildren = (...children) => {node.children=[];node.append(...children);};
  node.classList.toggle = (name,on) => {
    if(on) node.classList.add(name);
    else node.className=node.className.split(' ').filter(c=>c!==name).join(' ');
  };
  node.querySelector = selector => query(node,selector);
  Object.defineProperty(node,'offsetWidth',{get:()=>parseFloat(node.style.width)||320});
  node.getBoundingClientRect = () => ({left:0,top:0,width:node.offsetWidth,height:280});
  return node;
};
doc.createTextNode = text => { const n=doc.createElement('text');n.textContent=text;return n; };
doc.createElementNS = (_,tag) => doc.createElement(tag);
doc.body = doc.createElement('body');
doc.documentElement = {clientWidth:375};
for (const id of ['scenes','effects']) {
  const section=doc.createElement('section');section.id=id;
  const cards=doc.createElement('div');cards.className='cards';section.append(cards);doc.body.append(section);
}
doc.querySelector = selector => query(doc.body,selector);
doc.getElementById = id => all.find(node => node.id === id);
let now=0,raf;
const context={document:doc,console,performance:{now:()=>now},requestAnimationFrame:callback=>{raf=callback;},addEventListener:()=>{}};
context.window=context;
vm.createContext(context);
for (const script of scripts) vm.runInContext(script,context);
const cards=all.filter(node=>node.className.split(' ').includes('gallery-card'));
assert.strictEqual(cards.length,19);
assert.strictEqual(cards.filter(c=>c.className.includes('scene-card')).length,5);
for (const card of cards) {
  const stage=card.querySelector('.stage-host').children[0];
  assert.ok(descendants(stage).some(node=>node.className==='fx-root'));
  assert.ok(card.querySelector('.filmstrip').children.length>=4);
  const seek=card.querySelector('.seek'), clock=card.querySelector('.clock');
  seek.value='0.2';seek.events.input();
  assert.ok(clock.value.startsWith('0.20'));
  if(card.dataset.effect==='power-roll') assert.strictEqual(stage.querySelector('.actual.attacker').style.visibility,'hidden');
  if(card.dataset.effect==='chat-dice') assert.strictEqual(stage.querySelector('.chat-total').style.visibility,'hidden');
  const shot=snapshot(stage);
  seek.value='0.5';seek.events.input();seek.value='0.2';seek.events.input();
  assert.strictEqual(snapshot(stage),shot);
  const level=card.querySelector('.level');level.value='rich';level.events.change();
  assert.strictEqual(card.dataset.level,'rich');
  assert.notStrictEqual(card.querySelector('.stage-host').children[0],stage);
  card.querySelector('.filmstrip').children[0].events.click();
  assert.ok(clock.value.startsWith('0.00'));
  card.querySelector('.play').events.click();now+=100;raf(now);
  assert.ok(clock.value.startsWith('0.10'));
  card.querySelector('.pause').events.click();now+=100;raf(now);
  assert.ok(clock.value.startsWith('0.10'));
  const end=Number(seek.max);
  if(card.className.includes('scene-card')) {assert.ok(Number(card.dataset.beat)>=0.25);assert.ok(card.querySelector('.timing-note').textContent.includes('拍'));}
  if(card.dataset.effect==='effect-band') assert.strictEqual(end,3.9);
  seek.value=String(end);seek.events.input();
  card.querySelector('.loop').checked=true;
  card.querySelector('.play').events.click();now+=end*1000+200;raf(now);
  assert.ok(clock.value.startsWith('0.20'));
  card.querySelector('.pause').events.click();
  const select=card.querySelector('.sample');
  if(select) {
    select.value=select.children.at(-1).value;select.events.change();
    assert.strictEqual(card.dataset.sample,select.value);
    if(card.dataset.effect==='effect-band') {
      select.value='band-heights';select.events.change();assert.strictEqual(Number(seek.max),4.6);
      const items=card.querySelector('.event-details').children[1].children;
      assert.ok(items.some(item=>item.textContent.includes('4.60')));
    }
  }
}
for(const image of descendants(doc.body).filter(node=>node.tagName==='img')) {
  assert.ok(String(image.src || image.attributes.src).startsWith('data:'),'image must be embedded');
}
assert.ok(!snapshot(doc.body).includes('NaN'));
""")
