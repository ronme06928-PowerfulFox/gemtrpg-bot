// R2.5の取り出し・VOICEVOXキャッシュ処理を本編用に移したもの。
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { voices } from './round-v3-data.mjs';
import { planBeat, motion } from './round-v3-flow.mjs';
import { decodeWav, encodeWav, joinParts, mixEffect, peak } from './r1-audio.mjs';
import { openingSound } from '../common/opening.mjs';
import { effectTime } from './prepare-voice.mjs';
import { extractResolvePanelCss, GALLERY_PANEL_SELECTOR } from '../../../scripts/fx_gallery/panel_css.mjs';
const engine='C:/Users/yharu/tools/egatari-studio-0.6.3';
const video=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const local=path.join(video,'_local/round-v3');
const {parseNarration}=await import(pathToFileURL(path.join(engine,'kit/core/narration-core.mjs')));
const {inputHash}=await import(pathToFileURL(path.join(engine,'kit/core/portable.mjs')));
const run=(args,input)=>{
  const p=spawnSync('ffmpeg',['-v','error',...args],{input,maxBuffer:32*1024*1024});assert.equal(p.status,0,p.stderr?.toString());return p.stdout;
};
const pcm=b=>Float32Array.from({length:b.length/2},(_,i)=>b.readInt16LE(i*2)/32768);
const json=(file,obj)=>fs.writeFileSync(file,JSON.stringify(obj,null,2)+'\n');

export async function buildResolvePanel(deck){
  const entry=path.join(video,'scripts/resolve-panel-runtime.mjs');
  const skill=JSON.parse(fs.readFileSync('data/cache/skills_cache.json','utf8'))['Ps-00'];
  const opts={bundle:true,write:false,format:'iife',target:'es2020',charset:'utf8',minifyWhitespace:true,minifySyntax:true,metafile:true,define:{__R1_SKILL__:JSON.stringify(skill)}};
  const scanned=await build({...opts,entryPoints:[entry]});const copyRoot=path.join(local,'vendor/repo');const copies=[];
  for(const file of Object.keys(scanned.metafile.inputs).filter(f=>!f.startsWith('<'))){
    const target=path.join(copyRoot,path.relative(process.cwd(),file));fs.mkdirSync(path.dirname(target),{recursive:true});const bytes=fs.readFileSync(file);fs.writeFileSync(target,bytes);
    copies.push({file,sha256:createHash('sha256').update(bytes).digest('hex')});
  }
  const bundled=await build({...opts,absWorkingDir:copyRoot,entryPoints:[path.relative(process.cwd(),entry)]});
  fs.mkdirSync(path.join(deck,'components/resolve-panel'),{recursive:true});
  fs.writeFileSync(path.join(deck,'components/resolve-panel/index.js'),bundled.outputFiles[0].text);json(path.join(local,'copies.json'),copies);
  const panelCss=extractResolvePanelCss(fs.readFileSync('static/css/modules/visual_battle.css','utf8'))+'\n'+fs.readFileSync('static/css/modules/motion_fx.css','utf8').replaceAll('#resolve-flow-panel',GALLERY_PANEL_SELECTOR);
  fs.writeFileSync(path.join(deck,'panel.css'),panelCss.replaceAll('Yu Gothic UI','BIZ UDPGothic'));
}

export async function prepareDialogueVoice(deck,shots){
  for(const n of ['voice/cache','audio/steps','out'])fs.mkdirSync(path.join(deck,n),{recursive:true});
  const config=JSON.parse(fs.readFileSync(path.join(deck,'voice/config.json'),'utf8'));
  const events=JSON.parse(fs.readFileSync(path.join(deck,'voice/events.json'),'utf8'));
  const request=async(url,init)=>{const r=await fetch('http://127.0.0.1:50021'+url,{...init,signal:AbortSignal.timeout(180000)});assert.ok(r.ok,`${url}: ${r.status}`);return r;};
  const cacheOnly=process.argv.includes('--cache-only');
  if(!cacheOnly)assert.equal(await(await request('/version')).json(),'0.26.0');
  let made=0,cached=0;
  const synth=async(text,role,key)=>{
    const voice=voices[role];const settings={speedScale:voice.speedScale,pitchScale:voice.pitchScale,intonationScale:voice.intonationScale,prePhonemeLength:.08,postPhonemeLength:.1,outputSamplingRate:24000,outputStereo:false};
    let reading=text;
    for(const [display,spoken] of Object.entries(config.segmentReadings?.[key]||{}))reading=reading.replaceAll(display,spoken);
    for(const [display,spoken] of Object.entries(config.readings))reading=reading.replaceAll(display,spoken);
    const hash=createHash('sha256').update(JSON.stringify({version:'0.26.0',voice:voice.id,reading,settings})).digest('hex');
    const file=path.join(deck,'voice/cache',hash+'.wav');
    if(fs.existsSync(file))cached++;else{
      assert.ok(!cacheOnly,`声キャッシュがないため生成せず停止: ${key}`);
      const q=await(await request(`/audio_query?speaker=${voice.id}&text=${encodeURIComponent(reading)}`,{method:'POST'})).json();Object.assign(q,settings);
      const wav=Buffer.from(await(await request(`/synthesis?speaker=${voice.id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)})).arrayBuffer());
      decodeWav(wav);fs.writeFileSync(file,wav);json(file.replace('.wav','.json'),{role,text,voice,query:q});made++;
    }
    return {...decodeWav(fs.readFileSync(file)),hash,reading};
  };
  const timing={},manifest={segments:{}},measures=[],flow={};
  const sounds={};
  for(const [name,s] of Object.entries(JSON.parse(fs.readFileSync(path.join(deck,'sfx/cues.json'),'utf8')).sources)){
    const a=pcm(run(['-i',path.join(deck,'sfx',s.file),'-f','s16le','-ar','24000','-ac','1','pipe:1']));
    const gain=10**((s.peakDb+6)/20)/peak(a);sounds[name]=a.map((x,i)=>x*gain*Math.min(1,(a.length-1-i)/(24000*.008)));
  }
  const segments=parseNarration(fs.readFileSync(path.join(deck,'narration.md'),'utf8'));
  const byKey=new Map(segments.map(s=>[`${s.slideKey}:${s.stepKey}`,s]));
  for(const [index,shot] of shots.entries())for(let k=0;k<=(shot.id==='credits'?1:shot.count);k++){
    const key=`s-${shot.id}:${k}`,s=byKey.get(key),hashes=[],readings=[],arrays=[];
    if(s){
      assert.equal(s.turns.length,1);
      for(const part of s.turns[0].ttsParts){
        if(!part.trim()){arrays.push(null);continue;}
        const raw=await synth(part,s.turns[0].role,key);arrays.push(raw.samples);hashes.push(raw.hash);readings.push(raw.reading);
      }
    }
    const joined=joinParts(arrays,24000,config.partGap);
    if(s)assert.equal(joined.cues.length,s.bounds.length);
    const samples=s?pcm(run(['-i','pipe:0','-af','loudnorm=I=-20:TP=-3:LRA=7','-ar','24000','-ac','1','-f','s16le','pipe:1'],encodeWav(joined.samples,24000))):new Float32Array();
    const beat=k===0&&shot.id!=='intro'?{events:{},duration:0,voiceStart:0,voiceEnd:0,marks:[]}:planBeat({
      id:shot.id,k,last:k===shot.count||(shot.id==='intro'&&k===1),next:shots[index+1]?.id,
      voiceSeconds:samples.length/24000,cues:joined.cues,bounds:s?.bounds||[]});
    flow[key]=beat;timing[key]={dur:beat.duration,hold:beat.duration,lead:0,pad_after:0};
    const seEvents=[];
    for(const effect of events[key]?.effects||[]){
      const name=effect.sound==='slot'?(beat.events.skills?'skills':'slots'):effect.sound==='match'?'match':effect.sound;
      const event=beat.events[name];
      seEvents.push({sound:effect.sound,at:event?event.start:beat.voiceStart+effectTime(effect,s?.bounds||[],joined.cues)});
    }
    for(const name of ['diceAlly','diceEnemy'])if(beat.events[name])seEvents.push({sound:'dice',at:beat.events[name].start+motion.dieRoll});
    if(shot.id==='power-roll'&&beat.events.native)seEvents.push({sound:'dice',at:beat.events.native.start});
    const hasOpening=!!beat.events.opening;
    if(s||seEvents.length||hasOpening){
      const mix=new Float32Array(Math.round(beat.duration*24000));
      if(samples.length)mix.set(samples,Math.round(beat.voiceStart*24000));
      for(const event of seEvents)mixEffect(mix,sounds[event.sound],Math.round(event.at*24000));
      if(hasOpening)mixEffect(mix,decodeWav(openingSound()).samples,0);
      const file=`steps/${shot.id}-${k}.wav`;
      fs.writeFileSync(path.join(deck,'audio',file),encodeWav(mix,24000));
      manifest.segments[key]={file,dur:beat.duration,cues:joined.cues.map(x=>+(x+beat.voiceStart).toFixed(4)),sync:'manual',kind:'imported',inputHash:await inputHash(s||{turns:[]})};
    }
    if(s)measures.push({key,role:s.turns[0].role,text:s.turns[0].display,readings,hashes,...beat});
    console.log(`${key} ${beat.duration}s`);
  }
  json(path.join(deck,'audio/manifest.json'),manifest);json(path.join(deck,'timeline.json'),timing);json(path.join(deck,'flow.json'),flow);
  const duration=Object.values(timing).reduce((n,v)=>n+v.dur,0);
  json(path.join(local,'voice-report.json'),{version:'0.26.0',voices,made,cached,duration,measures});console.log(JSON.stringify({made,cached,duration}));
  return flow;
}
