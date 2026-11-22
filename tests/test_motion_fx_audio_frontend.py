from tests.test_motion_fx_frontend import ROOT, _run_node


def test_gem_cue_matches_s3_and_has_a_local_mp3_mapping():
    _run_node(r"""
const context = { Audio: class { load() {} }, console };
context.window = context;
context.addEventListener = () => {};
context.document = makeDocument();
const Fx = loadShared(context);
vm.runInContext(fs.readFileSync('static/js/sound_fx.js', 'utf8'), context);
const { cue } = JSON.parse(fs.readFileSync('scripts/sound_lab/presets.json', 'utf8'));
const effect = Fx.get('gem-blessing');
const sounds = JSON.parse(JSON.stringify(effect.sounds));
assert.deepStrictEqual(sounds, [{ t: cue, name: 'gem-blessing', mode: 'full' }]);
for (const row of effect.sounds) {
  assert(Object.values(row).every(v => ['number', 'string'].includes(typeof v)));
  assert(Number.isFinite(row.t) && row.t >= 0 && row.t <= effect.duration);
  assert(Object.hasOwn(context.SoundFx.effectSources, row.name));
}
assert.equal(context.SoundFx.effectSources['gem-blessing'], '/static/audio/gem-blessing.mp3');
""")
    size = (ROOT / "static/audio/gem-blessing.mp3").stat().st_size
    assert 30_000 <= size <= 60_000


def test_fx_reserves_only_future_enabled_cues_and_cancels_on_finish_or_hide():
    _run_node(r"""
const document = makeDocument(), listeners = new Map(), timers = new Map(), played = [];
let enabled = true, id = 0;
document.addEventListener = (name, fn) => listeners.set(name, fn);
const context = {
  document, performance: { now: () => 0 },
  setTimeout: (fn, ms) => { timers.set(++id, {fn, ms}); return id; },
  clearTimeout: id => timers.delete(id), requestAnimationFrame: () => {},
  localStorage: { getItem: () => 'light' },
  SoundFx: {
    canPlayEffect: () => enabled && !document.hidden,
    playNamed(name, at) {
      const id = context.setTimeout(() => { if (this.canPlayEffect()) played.push(name); }, at);
      return () => context.clearTimeout(id);
    },
  },
};
context.window = context;
const Fx = loadShared(context);
vm.runInContext(fs.readFileSync('static/js/fx/fx_player.js', 'utf8'), context);
const host = document.createElement('div');
function play(options = {}, mode = 'full') {
  return Fx.play('gem-blessing', { mode, width: 600, height: 400 }, {host, ...options});
}
function delays() {return [...timers.values()].map(row => Math.round(row.ms)).sort((a,b) => a-b);}
assert.equal(play({ delaySeconds: 0.4, elapsedSeconds: 0.13 }).level, 'light');
play({ delaySeconds: 2.0, elapsedSeconds: 0.13 });
assert.deepStrictEqual(delays(), [330, 1870, 1930, 3470]);
timers.get([...timers.keys()].find(id => Math.round(timers.get(id).ms) === 330)).fn();
assert.deepStrictEqual(played, ['gem-blessing']);
Fx.finishAll(host);
assert.deepStrictEqual(delays(), []);
for (const [options, mode, expected] of [
  [{elapsedSeconds: 0.07}, 'full', [1530]],
  [{elapsedSeconds: 0.03, rate: 2}, 'full', [0, 770]],
  [{}, 'band', [1200]],
  [{silent: true}, 'full', [1600]],
]) {
  play(options, mode);
  assert.deepStrictEqual(delays(), expected);
  Fx.finishAll(host);
}
enabled = false;
play();
assert.deepStrictEqual(delays(), [1600]);
Fx.finishAll(host);
enabled = true;
play({ delaySeconds: 0.4 });
document.hidden = true;
listeners.get('visibilitychange')();
assert.deepStrictEqual(delays(), [2000]);
play();
assert.deepStrictEqual(delays(), [1600, 2000]);
document.hidden = false;
play();
enabled = false;
timers.get([...timers.keys()].find(id => Math.round(timers.get(id).ms) === 60)).fn();
assert.deepStrictEqual(played, ['gem-blessing']);
Fx.finishAll(host);
""")


def test_named_sound_uses_the_audio_clock_and_falls_back_while_decoding():
    _run_node(r"""
(async () => {
  const played = [], queued = new Map(), unlock = new Map(), visibility = new Map();
  const sources = [], gains = [];
  let decoded, loads = 0, nextTimer = 0;
  class AudioContext {
    state = 'running';
    currentTime = 4.2;
    destination = {};
    getOutputTimestamp() { return { contextTime: 4.19, performanceTime: 1000 }; }
    decodeAudioData() { return new Promise(resolve => { decoded = resolve; }); }
    createGain() {
      const node = { gain: { value: null }, connect() {}, disconnect() {} };
      gains.push(node);
      return node;
    }
    createBufferSource() {
      const node = { connect() {}, disconnect() {}, start(when) { this.when = when; },
        stop() { this.stopped = true; } };
      sources.push(node);
      return node;
    }
  }
  class Audio {
    constructor(src) { this.src = src; this.paused = true; }
    load() {}
    pause() { this.paused = true; }
    addEventListener() {}
    removeEventListener() {}
    async play() { this.paused = false; played.push([this.src, this.volume]); }
  }
  const context = {
    Audio, AudioContext, console, document: makeDocument(),
    performance: {now: () => 1000},
    fetch: async () => { loads++; return {ok: true, arrayBuffer: async () => new ArrayBuffer(1)}; },
    setTimeout: (callback, ms) => { queued.set(++nextTimer, {callback, ms}); return nextTimer; },
    clearTimeout: id => queued.delete(id),
    localStorage: {getItem: () => null, setItem() {}},
  };
  context.window = context;
  context.addEventListener = (name, fn) => unlock.set(name, fn);
  context.document.addEventListener = (name, fn) => visibility.set(name, fn);
  vm.runInNewContext(fs.readFileSync('static/js/sound_fx.js', 'utf8'), context);
  const sound = context.SoundFx;
  assert.equal(sound.getSettings().volume, 0.55);
  assert.equal(sound.playNamed('gem-blessing'), null);
  unlock.get('pointerdown')();
  unlock.get('keydown')();
  await new Promise(setImmediate);
  assert.equal(loads, 1);
  sound.setVolume(0.31);
  const cancelFallback = sound.playNamed('gem-blessing', 1450);
  assert.equal(queued.get(1).ms, 450);
  assert.equal(sources.length, 0);
  queued.get(1).callback();
  assert.deepStrictEqual(played, [['/static/audio/gem-blessing.mp3', 0.31]]);
  cancelFallback();
  assert.equal(queued.size, 0);
  decoded({duration: 1.54});
  await new Promise(setImmediate);
  const stop = sound.playNamed('gem-blessing', 1450);
  assert(Math.abs(sources[0].when - 4.64) < 1e-9);
  assert.equal(sources[0].stopped, undefined);
  assert.equal(gains[0].gain.value, 0.31);
  stop();
  stop();
  assert.equal(sources[0].stopped, true);
  sound.playNamed('gem-blessing', 1450);
  sound.playNamed('gem-blessing', 3050);
  sound.playNamed('gem-blessing', 4650);
  assert.equal(sources.length, 4);
  sound.setVolume(0);
  assert.equal(gains[1].gain.value, 0);
  sound.setEnabled(false);
  assert(sources.slice(1).every(source => source.stopped));
  assert.equal(sound.playNamed('gem-blessing'), null);
  sound.setEnabled(true);
  sound.playNamed('gem-blessing', 1450);
  context.document.hidden = true;
  visibility.get('visibilitychange')();
  assert.equal(sources.at(-1).stopped, true);
  assert.equal(sound.playNamed('gem-blessing'), null);
  assert.equal(sound.playNamed('toString'), null);
})().catch(e => {console.error(e);process.exit(1)});
""")


def test_gem_uses_a_decoded_portrait_or_keeps_the_missing_layout():
    _run_node(r"""
(async () => {
  const doc = makeDocument(), context = {};
  const Fx = loadShared(context);
  const host = doc.createElement('div'), resolveDecode = new Map();
  global.Image = function () {
    const image = doc.createElement('img');
    image.decode = () => new Promise((resolve, reject) => resolveDecode.set(image.src, {resolve, reject}));
    return image;
  };
  global.window = {Fx: {play(name, params) {
    const root = doc.createElement('div'), effect = Object.create(Fx.get(name));
    effect.mount(root, {...params, level: 'light'});
    effect.render(.64);
    mounted.push({root, effect});
  }}};
  global.document = {getElementById: () => host};
  const {ResolveFlowPanel} = await import('./static/js/battle/components/ResolveFlowPanel.js');
  const {playResolveStageFx} = await import('./static/js/battle/components/resolve_flow_fx.js');
  const flow = new ResolveFlowPanel(), mounted = [];
  const state = {characters: [{id:'a', image:'late.jpg'}, {id:'b', image:'ready.jpg'}],
    battle_state: {pending_gem_blessings: [{actor_id: 'a'}, {actor_id: 'b'}]}};
  flow._preparePendingGemPortraits(state);
  assert.equal(resolveDecode.size, 2);
  resolveDecode.get('ready.jpg').resolve();
  await Promise.resolve();
  flow._activeStep = {kind: 'gem_blessing_prelude', gemBlessings: state.battle_state.pending_gem_blessings};
  flow._stepStartedAt = Date.now();
  playResolveStageFx(flow, {liveGemPrelude: true}, state);
  const [missing, ready] = mounted;
  assert(!missing.effect.figure);
  assert.equal(ready.effect.figure.src, 'ready.jpg');
  assert.equal(ready.effect.figure.className, 'fx-gem-b-figure');
  resolveDecode.get('late.jpg').resolve();
  await Promise.resolve();
  missing.effect.render(1);
  assert(!missing.effect.figure);
  assert(!missing.root.children.some(child => child.tagName === 'img'));
})().catch(e => {console.error(e);process.exit(1)});
""")


def test_gem_prelude_only_sounds_after_the_matching_live_phase_signal():
    _run_node(r"""
(async () => {
  const handlers = new Map(), reserved = [];
  global.document = {getElementById: id => id === 'map-viewport' ? {clientWidth: 800, clientHeight: 600} : null};
  global.window = {addEventListener() {}, Fx: {
    play: (name, params, opts) => reserved.push(opts.silent),
    cancelSounds: () => reserved.push('canceled'),
  }, socket: {on: (name, fn) => handlers.set(name, fn)}};
  const {socketClient} = await import('./static/js/battle/core/SocketClient.js');
  const {ResolveFlowPanel} = await import('./static/js/battle/components/ResolveFlowPanel.js');
  const flow = new ResolveFlowPanel();
  flow._onStateUpdated = () => {};
  flow._characterById = () => ({});
  flow._actorVisualMeta = () => ({});
  socketClient.initialize();
  flow.initialize();
  function prelude(timestamp) {
    flow._activeStep = {kind: 'gem_blessing_prelude', timestamp,
      gemBlessings: [{actor_id: 'a'}, {actor_id: 'b'}]};
    flow._stepStartedAt = Date.now();
    flow._notifyStage(flow._traceKey(flow._activeStep), 'prelude', flow._activeStep);
  }
  function live(timestamp) {
    handlers.get('battle_phase_changed')({from: 'select', to: 'resolve_mass', gem_prelude_timestamp: timestamp});
  }
  prelude(100);
  live(300);
  handlers.get('battle_phase_changed')({from: 'resolve_mass', to: 'resolve_single'});
  prelude(200);
  prelude(300);
  prelude(300);
  live(400);
  handlers.get('disconnect')();
  prelude(400);
  assert.deepStrictEqual(reserved, [true,true,true,true,false,false,'canceled',true,true]);
})().catch(e => {console.error(e);process.exit(1)});
""")
