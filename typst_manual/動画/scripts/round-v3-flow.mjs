// 秒数の例外でleadを埋めず、実際に見せる動きから一拍を組む。
export const motion = { fade:.3, scene:.5, title:.8, settle:.4, sceneRest:1,
  conversation:.6, topic:1.2, markDraw:.5, markHold:1,
  notice:1.5, arrowDraw:.5, arrowGap:1,
  die:2.4, dieRoll:1.1, dieStagger:.4, names:.5, power:1.2, attack:.7,
  outcome:2.2, speedHighlight:.6, effectFrame:.6, effectExpand:.7, fp:1.4, opening:2.6, credits:5 };
const boardTopics=[['slots','speed','selection','resolve'],['return','effect-timing','effect-fp','next']];
export function repose(id,next){
  if((id==='intro'&&next==='slots')||(id==='resolve'&&next==='names')||
    (id==='outcome'&&next==='return')||(id==='next'&&next==='credits'))return motion.sceneRest;
  return boardTopics.some(row=>row.indexOf(id)>=0&&row.indexOf(next)===row.indexOf(id)+1)?motion.topic:motion.conversation;
}
export function planBeat({id,k,last,next,previous,voiceSeconds=0,cues=[],bounds=[]}){
  const events={};let entranceEnd=0;
  const before=(name,duration)=>{events[name]={start:entranceEnd,duration};entranceEnd+=duration;};
  const together=(name,duration)=>{events[name]={start:0,duration};entranceEnd=Math.max(entranceEnd,duration);};
  const first=k===1;
  const scene=(id==='intro'&&k===2)||(['names','return','credits'].includes(id)&&first);
  if(id==='intro'&&k===0)before('opening',motion.opening);
  if(id==='intro'&&k===2)before('sceneFade',motion.title);
  if(first&&id!=='intro'){
    before('sceneFade',id==='credits'?motion.title:['names','return'].includes(id)?motion.scene:motion.fade);
    if(!['names','power-roll','power-ally','power-enemy','attack','outcome','credits'].includes(id)){
      together('slots',motion.fade);
      if(['resolve','next'].includes(id))together('gm',motion.fade);
      if(id==='return')together('win',motion.fade);
      if(['effect-timing','effect-fp'].includes(id))together('effect',motion.fade);
    }
  }
  if(id==='slots'&&k===2){together('slots',motion.fade);together('gm',motion.fade);}
  if(id==='selection'&&k===2)before('skills',motion.fade);
  if(id==='selection'&&k===5)before('match',motion.fade);
  if(id==='resolve'&&first)before('speedHighlight',motion.speedHighlight);
  if(id==='effect-timing'&&k===2)before('timingFrame',motion.effectFrame);
  if(id==='effect-fp'&&first)before('effectExpand',motion.effectExpand);
  if((id==='power-ally'&&k===2)||(id==='power-enemy'&&first))before('formula',motion.fade);
  const nativeDuration={names:motion.names,'power-roll':motion.power,attack:motion.attack,outcome:motion.outcome}[id];
  if(first&&nativeDuration)before('native',nativeDuration);
  const settle=scene?motion.sceneRest:motion.settle;
  let voiceStart=entranceEnd+(voiceSeconds?settle:0);
  if(id==='slots'&&k===2)voiceStart=Math.max(voiceStart,events.slots.start+events.slots.duration+motion.notice);
  if(id==='selection'&&k===3){
    const arrow=previous.events.arrowEnemy;
    const elapsed=previous.duration-(arrow.start+arrow.duration);
    voiceStart=Math.max(voiceStart,motion.notice-elapsed);
  }
  const voiceEnd=voiceStart+voiceSeconds;
  let motionEnd=entranceEnd;
  const synced=(name,start,duration)=>{events[name]={start,duration};motionEnd=Math.max(motionEnd,start+duration);};
  if(id==='selection'&&k===2){
    synced('arrowAlly',voiceEnd,motion.arrowDraw);
    synced('arrowEnemy',voiceEnd+motion.arrowDraw+motion.arrowGap,motion.arrowDraw);
  }
  if(first&&['selection','effect-timing','next'].includes(id))synced('phaseChange',0,0);
  if(id==='resolve'&&first)synced('phaseChange',events.speedHighlight.start+events.speedHighlight.duration,0);
  if(id==='speed'&&first){
    const at=voiceStart+cues[0]+.2;
    synced('diceAlly',at,motion.die+motion.fade);
    synced('diceEnemy',at+motion.dieStagger,motion.die+motion.fade);
    synced('speedFormula',at+motion.dieRoll,motion.fade);
  }
  if(id==='slots'&&first)cues.forEach((at,i)=>synced(`phase-${i}`,voiceStart+at,motion.markHold));
  if(id==='effect-fp'&&first){
    const index=bounds.findIndex(b=>b.type==='mark'&&b.id==='end-fp');
    synced('fp',voiceStart+cues[index],motion.fp);
  }
  const marks=bounds.flatMap((b,i)=>b.type==='mark'?[{id:b.id,start:voiceStart+cues[i],
    drawn:voiceStart+cues[i]+motion.markDraw,held:voiceStart+cues[i]+motion.markDraw+motion.markHold}]:[]);
  motionEnd=Math.max(motionEnd,...marks.map(m=>m.held));
  const contentEnd=Math.max(voiceEnd,motionEnd);
  const exits=(last&&!['intro','names','power-roll','power-ally','power-enemy','attack','outcome','credits','resolve'].includes(id))||
    (id==='power-ally'&&last)||(id==='power-enemy'&&first);
  if(exits){events.exit={start:contentEnd,duration:motion.fade};motionEnd=contentEnd+motion.fade;}
  const after=id==='credits'?motion.sceneRest+motion.credits:
    id==='intro'&&k===2?motion.sceneRest:last?repose(id,next):motion.conversation;
  const duration=Math.ceil((Math.max(voiceEnd,motionEnd)+after)*100)/100;
  return {events,voiceStart,voiceEnd,motionEnd,contentEnd,marks,repose:after,duration};
}
