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
  SoundFx: { canPlayEffect: () => enabled && !document.hidden, playNamed: name => played.push(name) },
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


def test_named_sound_uses_existing_settings_and_does_not_wait_for_media():
    _run_node(r"""
(async () => {
  const played = [], unlock = new Map();
  class Audio {
    constructor(src) { this.src = src; this.paused = true; }
    load() {}
    pause() { this.paused = true; }
    async play() { this.paused = false; played.push([this.src, this.volume]); }
  }
  const context = {Audio, console, document: makeDocument(), localStorage: {
    getItem: () => null, setItem() {},
  }};
  context.window = context;
  context.addEventListener = (name, fn) => unlock.set(name, fn);
  vm.runInNewContext(fs.readFileSync('static/js/sound_fx.js', 'utf8'), context);
  const sound = context.SoundFx;
  assert.equal(sound.getSettings().volume, 0.55);
  assert.equal(await sound.playNamed('gem-blessing'), false);
  unlock.get('pointerdown')();
  sound.setVolume(0.31);
  assert.equal(await sound.playNamed('gem-blessing'), true);
  assert.deepStrictEqual(played, [['/static/audio/gem-blessing.mp3', 0.31]]);
  sound.setEnabled(false);
  assert.equal(await sound.playNamed('gem-blessing'), false);
  sound.setEnabled(true);
  sound.setVolume(0);
  assert.equal(await sound.playNamed('gem-blessing'), true);
  assert.deepStrictEqual(played.at(-1), ['/static/audio/gem-blessing.mp3', 0]);
  context.document.hidden = true;
  assert.equal(await sound.playNamed('gem-blessing'), false);
  assert.equal(await sound.playNamed('toString'), false);
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
