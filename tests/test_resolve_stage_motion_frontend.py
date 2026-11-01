"""PR57-2: 共有時計、時刻だけから描く舞台、進行の境界。"""
from tests.test_motion_fx_frontend import _run_node


def test_timing_and_waits_cover_normal_knockout_and_fizzle():
    _run_node(r"""
(async()=>{
 const timing=await import('./static/js/battle/components/resolve_stage_timing.js');
 const fx=await import('./static/js/battle/components/resolve_flow_fx.js');
 assert.strictEqual(timing.resolveStageTiming,fx.resolveStageTiming);
 const ko={kind:'clash',selfDestructed:['d','e']};
 // 計画58の段階表。不発は攻撃を飛ばし、KOは決着だけを延ばす。
 for(const [step,stages,wait,total,window,outcome] of [
  [{kind:'clash'},[500,1200,700,2200],600,5200,2.8,2.4],
  [ko,[500,1200,700,3700],600,6700,4.3,2.4],
  [{kind:'fizzle',selfDestructed:['a']},[500,1200,900],500,3100,1.4,1.7],
 ]) {
  assert.deepStrictEqual(timing.resolveStageTiming(step).map(r=>r.ms),stages);
  assert.strictEqual(timing.resolveWaitMs(step),wait);
  assert.strictEqual(stages.reduce((s,n)=>s+n,wait),total);
  assert.strictEqual(timing.resolveOutcomeWindow(step),window);
  assert.ok(Math.abs(timing.resolveStageStarts(step).outcome-outcome)<1e-9);
 }
 const Fx=loadShared({});
 assert.strictEqual(Fx.get('attack-slash').duration,1.4);
 // 攻撃は段階に合わせて速めて再生し、定義の0.8秒の命中が決着の開始に当たる。
 const starts=timing.resolveStageStarts({}),rate=timing.fxPlaybackRate('attack');
 assert.ok(Math.abs(starts.attack+0.8/rate-starts.outcome)<1e-9);
 assert.ok(starts.attack+Fx.get('attack-slash').duration/rate>starts.outcome);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_motion_positions_opacity_scale_and_brightness_are_seekable_for_all_levels():
    _run_node(r"""
(async()=>{
 const {stageMotionAt}=await import('./static/js/battle/components/resolve_stage_motion.js');
 const {resolveStageStarts}=await import('./static/js/battle/components/resolve_stage_timing.js');
 const step={kind:'clash',outcome:'attacker_win'};
 // 動きの時刻は段階の開始からの相対で書く（段階の長さは本番の段階表から求める）。
 const s=resolveStageStarts(step),f=resolveStageStarts({kind:'fizzle'});
 const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);
 for(const level of ['normal','rich','light']) {
  const light=level==='light';
  const half=stageMotionAt(step,0.25,level);
  near(half.sides.attacker.portraitX,light?0:-15);
  near(half.sides.defender.portraitX,light?0:15);
  near(half.sides.attacker.portraitOpacity,0.5);near(half.sides.attacker.nameOpacity,0.5);
  const slide=stageMotionAt(step,s.power+0.15,level);
  near(slide.sides.attacker.plaqueX,light?0:-18);
  near(slide.sides.defender.plaqueX,light?0:18);
  near(slide.sides.attacker.plaqueOpacity,light?0.5:1);
  near(slide.sides.attacker.smallGemX,0);
  const peak=stageMotionAt(step,s.outcome+0.35,level);
  near(peak.sides.attacker.gemScale,light?1:1.1);
  near(peak.sides.attacker.gemBrightness,light?1:2.2);
  near(peak.sides.defender.gemScale,1);near(peak.sides.defender.gemBrightness,0.42);
  near(stageMotionAt(step,s.outcome-0.1,level).centralOpacity,0.3);
  near(stageMotionAt(step,s.outcome,level).centralOpacity,0);
  for(const kind of ['one_sided','hard_attack','mass_individual']) {
   const one={kind,resolutionKind:'one_sided'},o=resolveStageStarts(one);
   near(stageMotionAt(one,o.outcome-0.1,level).centralOpacity,0.8);
   near(stageMotionAt(one,o.outcome+0.15,level).centralOpacity,0.4);
   near(stageMotionAt(one,o.outcome+0.3,level).centralOpacity,0);
  }
  near(stageMotionAt({kind:'fizzle'},f.outcome-0.1,level).centralOpacity,0);
  near(stageMotionAt({kind:'fizzle'},f.outcome+0.2,level).centralOpacity,1);
  for(const outcome of ['draw','no_effect'])near(stageMotionAt({...step,outcome},s.outcome+0.35,level).sides.attacker.gemScale,1);
  near(stageMotionAt({...step,outcome:'defender_win'},s.outcome+0.35,level).sides.defender.gemScale,light?1:1.1);
  const times=[0,0.25,s.power-0.01,s.power,s.power+0.15,s.power+0.3,s.attack,s.outcome,s.outcome+0.35,s.wait,20];
  const frames=times.map(t=>JSON.stringify(stageMotionAt(step,t,level)));
  for(const i of [10,1,6,0,8,3,9,2,7,5,4])assert.strictEqual(JSON.stringify(stageMotionAt(step,times[i],level)),frames[i]);
 }
 const page=fs.readFileSync('scripts/resolve_preview/page.js','utf8');
 assert.ok(page.includes('stageMotionAt')&&page.includes('renderStageMotion'));
 assert.ok(!page.includes('Math.sin')&&!page.includes('portrait.style.transform'));
 const css=fs.readFileSync('static/css/modules/visual_battle.css','utf8');
 assert.ok(css.includes('.reveal-names .power-number { visibility: hidden; }'));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_auto_advance_uses_kind_wait_and_keeps_overflow_deadline_and_controller_guard():
    _run_node(r"""
(async()=>{
 const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
 const {RESOLVE_WAIT_MS,FIZZLE_WAIT_MS}=await import('./static/js/battle/components/resolve_stage_timing.js');
 const flow=new ResolveFlowPanel(),oldTimeout=global.setTimeout,oldNow=Date.now;
 let delay,requests=0;
 flow._waitingForAdvance=true;flow._autoAdvanceEnabled=true;flow._canDriveResolveFlow=()=>true;
 flow._onAdvanceRequested=()=>requests++;
 Date.now=()=>10000;global.setTimeout=(fn,ms)=>{delay=ms;fn();return 1;};
 try {
  for(const [step,wait] of [[{kind:'clash'},RESOLVE_WAIT_MS],[{kind:'fizzle'},FIZZLE_WAIT_MS]]) {
   flow._activeStep=step;flow._pendingAdvanceTimer=null;
   flow._scheduleAutoAdvanceIfNeeded({});assert.strictEqual(delay,wait);
   flow._pendingAdvanceTimer=null;flow._outcomeFxDeadline={step,atMs:13000};
   flow._scheduleAutoAdvanceIfNeeded({});assert.strictEqual(delay,3000);
  }
  assert.strictEqual(requests,4);
  flow._pendingAdvanceTimer=null;flow._canDriveResolveFlow=()=>false;
  flow._scheduleAutoAdvanceIfNeeded({});assert.strictEqual(requests,4);
 } finally {global.setTimeout=oldTimeout;Date.now=oldNow;}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_real_playback_clock_manual_auto_claim_sync_and_deferred_log_boundary():
    _run_node(r"""
(async()=>{
 const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
 const {store}=await import('./static/js/battle/core/BattleStore.js');
 const {socketClient}=await import('./static/js/battle/core/SocketClient.js');
 const {eventBus}=await import('./static/js/battle/core/EventBus.js');
 const {RESOLVE_TEMPO:T,RESOLVE_WAIT_MS,FIZZLE_WAIT_MS}=await import('./static/js/battle/components/resolve_stage_timing.js');
 const flow=new ResolveFlowPanel(),timers=new Map(),intervals=new Map(),sent=[],logs=[],finished=[],sounds=[];
 let now=100000,seq=0;
 const saved={now:Date.now,timeout:global.setTimeout,clear:global.clearTimeout,interval:global.setInterval,clearInterval:global.clearInterval};
 global.setTimeout=(fn,ms)=>{const id=++seq;timers.set(id,{fn,at:now+ms});return id;};
 global.clearTimeout=id=>timers.delete(id);
 global.setInterval=fn=>{const id=++seq;intervals.set(id,fn);return id;};
 global.clearInterval=id=>intervals.delete(id);Date.now=()=>now;
 global.window={currentUserId:'gm',SoundFx:{playDiceRoll:()=>sounds.push(now)},flushDeferredResolveByStepKey:p=>logs.push([now,p.key])};
 store._state={room_id:'R',battle_id:'B',round:1,phase:'resolve_single',resolvePresentation:{controller_user_id:'gm',revision:3}};
 socketClient.sendResolveFlowAdvance=p=>{sent.push([now,p]);return true;};
 socketClient.sendResolveFlowClaim=p=>{sent.push([now,p]);return true;};
 eventBus.on('battle:resolve:flow:step-finished',p=>finished.push([now,p.key]));
 flow._renderStep=()=>{
  if(!flow._activeStep)return;
  const step=flow._activeStep,stage=flow._revealStageByElapsed(now-flow._stepStartedAt,step);
  flow._tryPlayPowerRevealSe(flow._traceKey(step),stage);
  flow._notifyStage(flow._traceKey(step),stage,step);
 };
 const advance=ms=>{
  const end=now+ms;
  while(true){const due=[...timers.entries()].filter(([,v])=>v.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].fn();}
  now=end;for(const fn of [...intervals.values()])fn();
 };
 try {
  flow._autoAdvanceEnabled=true;
  flow._playQueue=[{kind:'clash',rawStepIndex:0,stepIndex:0},{kind:'fizzle',rawStepIndex:1,stepIndex:1},{kind:'clash',rawStepIndex:2,stepIndex:2}];
  // 段階の長さと待ちは本番の段階表から求める。
  const step0=100000+T.names+T.power+T.attack+T.outcome,sent0=step0+RESOLVE_WAIT_MS;
  const sent1=sent0+T.names+T.power+T.fizzleOutcome+FIZZLE_WAIT_MS,power2=sent1+T.names;
  flow._playNextStep();advance(T.names);assert.strictEqual(sounds.length,1);
  advance(T.power);advance(T.attack);assert.strictEqual(flow._revealStageByElapsed(now-flow._stepStartedAt,flow._activeStep),'outcome');
  advance(T.outcome);assert.strictEqual(now,step0);assert.ok(flow._waitingForAdvance);
  assert.deepStrictEqual(finished,[[step0,'raw:0']]);assert.deepStrictEqual(logs,[]);
  advance(RESOLVE_WAIT_MS-1);assert.strictEqual(sent.length,0);advance(1);assert.strictEqual(sent[0][0],sent0);
  assert.strictEqual(sent[0][1].expected_step_index,0);assert.deepStrictEqual(logs,[]);
  flow._onSyncedAdvanceSignal({room_id:'R',battle_id:'B',round:1,expected_step_index:0});
  assert.deepStrictEqual(logs,[[sent0,'raw:0']]);assert.strictEqual(flow._activeStep.kind,'fizzle');
  advance(T.names);assert.strictEqual(sounds.at(-1),sent0+T.names);
  advance(T.power+T.fizzleOutcome);assert.ok(flow._waitingForAdvance);advance(FIZZLE_WAIT_MS-1);assert.strictEqual(sent.length,1);
  advance(1);assert.strictEqual(sent[1][0],sent1);
  flow._onSyncedAdvanceSignal({room_id:'R',battle_id:'B',round:1,expected_step_index:1});
  assert.deepStrictEqual(logs.at(-1),[sent1,'raw:1']);
  flow._onAutoAdvanceToggle({target:{checked:false}});advance(T.names);assert.strictEqual(sounds.at(-1),power2);advance(T.power+T.attack+T.outcome);
  flow._onAdvanceRequested();assert.strictEqual(sent[2][0],power2+T.power+T.attack+T.outcome);
  flow._onAdvanceRequested();assert.strictEqual(sent.length,3);
  flow._canClaimResolveFlow=()=>true;flow._onClaimRequested();
  assert.deepStrictEqual(sent[3][1],{room_id:'R',battle_id:'B',round:1});
  assert.strictEqual(logs.length,2);assert.strictEqual(sounds.length,3);
 } finally {
  Date.now=saved.now;global.setTimeout=saved.timeout;global.clearTimeout=saved.clear;
  global.setInterval=saved.interval;global.clearInterval=saved.clearInterval;
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_dom_motion_renderer_restores_every_style_without_measuring():
    _run_node(r"""
(async()=>{
 const {stageMotionAt,renderStageMotion}=await import('./static/js/battle/components/resolve_stage_motion.js');
 const doc=makeDocument(),canvas=doc.createElement('div'),nodes={};
 for(const side of ['attacker','defender']) {
  const node=doc.createElement('div'),portrait=doc.createElement('div'),name=doc.createElement('div');
  const plaque=doc.createElement('div'),gem=doc.createElement('div'),small=doc.createElement('div');
  gem.className='gem';small.className='gem small-gem';plaque.className='skill-plaque';
  [portrait,name,plaque,gem,small].forEach(el=>node.appendChild(el));canvas.appendChild(node);
  node.querySelector=()=>name;node.querySelectorAll=s=>s==='.portrait'?[portrait]:[plaque,gem,small];
  nodes[side]={node,portrait,name,plaque,gem,small};
 }
 const central=doc.createElement('div');canvas.appendChild(central);
 canvas.querySelector=s=>s==='.clash-point'?central:nodes[s.split('.')[2]]?.node;
 canvas.getBoundingClientRect=()=>{throw Error('render must not measure');};
 const times=[0,0.25,0.6,0.75,0.9,2.8,3.15,4];
 for(const level of ['normal','rich','light']) {
  const draw=t=>{renderStageMotion(canvas,stageMotionAt({kind:'clash',outcome:'attacker_win'},t,level));return snapshot(canvas);};
  const frames=times.map(draw);
  for(const i of [7,0,6,1,5,3,2,4])assert.strictEqual(draw(times[i]),frames[i]);
  draw(0.75);assert.ok(nodes.defender.small.style.transform.startsWith('translateX(0px)'));
  if(level==='light')assert.strictEqual(nodes.attacker.gem.style.transform,'translateX(0px) scale(1)');
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_animation_frames_only_draw_and_are_cancelled_with_playback_timers():
    _run_node(r"""
(async()=>{
 const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
 const flow=new ResolveFlowPanel(),frames=new Map();let id=0,draws=0;
 global.window={requestAnimationFrame:fn=>{frames.set(++id,fn);return id;},cancelAnimationFrame:n=>frames.delete(n)};
 flow._activeStep={kind:'clash'};flow._drawMotion=()=>draws++;
 flow._startMotionPlayback();
 for(let i=0;i<3;i++){const [n,fn]=frames.entries().next().value;frames.delete(n);fn();}
 assert.strictEqual(draws,3);assert.strictEqual(flow._waitingForAdvance,false);
 assert.strictEqual(frames.size,1);flow._clearTimers();assert.strictEqual(frames.size,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_next_match_clock_does_not_subtract_the_server_clock_from_the_device_clock():
    # 計画58：サーバーの step_started_at と端末の Date.now() を直接引き算すると、
    # 端末の時計が遅れている分だけマッチの頭が止まり、進んでいる分だけ頭が飛ぶ。
    _run_node(r"""
(async()=>{
 const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
 const {store}=await import('./static/js/battle/core/BattleStore.js');
 let now=500000;const saved={now:Date.now,timeout:global.setTimeout,clear:global.clearTimeout,interval:global.setInterval,clearInterval:global.clearInterval};
 global.setTimeout=()=>0;global.clearTimeout=()=>{};global.setInterval=()=>0;global.clearInterval=()=>{};Date.now=()=>now;
 global.window={currentUserId:'gm'};
 const flow=new ResolveFlowPanel();flow._renderStep=()=>{};flow._startMotionPlayback=()=>{};
 const presentation=(index,startedAt)=>{store._state={room_id:'R',battle_id:'B',round:1,phase:'resolve_single',
   resolvePresentation:{controller_user_id:'gm',revision:3,current_step_index:index,step_started_at:startedAt}};};
 try {
  // 次へ進む合図：サーバーの時計が端末より2秒進んでいても、合図を受け取った瞬間から始める。
  presentation(0,now);flow._playQueue=[{kind:'clash',rawStepIndex:0,stepIndex:0},{kind:'clash',rawStepIndex:1,stepIndex:1}];
  flow._playNextStep();flow._waitingForAdvance=true;
  now+=7000;presentation(1,now+2000);
  flow._onSyncedAdvanceSignal({room_id:'R',battle_id:'B',round:1,expected_step_index:0});
  assert.strictEqual(flow._activeStep.rawStepIndex,1);assert.strictEqual(flow._stepStartedAt,now);
  // サーバーの時計が遅れていても、マッチの頭を飛ばさない。
  flow._playQueue=[{kind:'clash',rawStepIndex:2,stepIndex:2}];flow._waitingForAdvance=true;
  now+=7000;presentation(2,now-1500);
  flow._onSyncedAdvanceSignal({room_id:'R',battle_id:'B',round:1,expected_step_index:1});
  assert.strictEqual(flow._stepStartedAt,now);
  // 途中参加の合流：過去の開始時刻は使い、未来の開始時刻は端末の今に丸める。
  flow._playQueue=[{kind:'clash',rawStepIndex:3,stepIndex:3}];presentation(3,now-1500);flow._playNextStep();
  assert.strictEqual(flow._stepStartedAt,now-1500);
  flow._playQueue=[{kind:'clash',rawStepIndex:4,stepIndex:4}];presentation(4,now+2000);flow._playNextStep();
  assert.strictEqual(flow._stepStartedAt,now);
 } finally {Date.now=saved.now;global.setTimeout=saved.timeout;global.clearTimeout=saved.clear;global.setInterval=saved.interval;global.clearInterval=saved.clearInterval;}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
