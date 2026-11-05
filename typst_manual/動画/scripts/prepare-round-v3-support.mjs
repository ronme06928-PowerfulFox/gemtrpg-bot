// R2.5の取り出し・VOICEVOXキャッシュ処理を本編用に移したもの。
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { voices } from './round-v3-data.mjs';
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
  const timing={},manifest={segments:{}},measures=[];
  for(const shot of shots)for(let k=0;k<=(shot.id==='credits'?1:shot.count);k++){
    const dur=shot.id==='credits'?(k===0?0:5.8):shot.id==='intro'?(k===0?2.6:k===2?.8:0):k===1?({names:.5,'power-roll':1.2+config.pauses.cut,attack:.7+config.pauses.cut,outcome:2.2}[shot.id]||0):0;
    timing[`s-${shot.id}:${k}`]={dur,hold:dur,lead:0,pad_after:0};
  }
  const se=pcm(run(['-i','static/audio/dice-roll.mp3','-f','s16le','-ar','24000','-ac','1','pipe:1']));const gain=10**(-16/20)/peak(se);const dice=se.map(x=>x*gain);
  const sounds={dice};
  for(const [name,s] of Object.entries(JSON.parse(fs.readFileSync(path.join(deck,'sfx/cues.json'),'utf8')).sources)){
    if(name==='dice')continue;
    const a=pcm(run(['-i',path.join(deck,'sfx',s.file),'-f','s16le','-ar','24000','-ac','1','pipe:1']));
    const gain=10**((s.peakDb+6)/20)/peak(a);sounds[name]=a.map((x,i)=>x*gain*Math.min(1,(a.length-1-i)/(24000*.008)));
  }
  const segments=parseNarration(fs.readFileSync(path.join(deck,'narration.md'),'utf8'));
  for(const [index,s] of segments.entries()){
    const key=`${s.slideKey}:${s.stepKey}`;
    assert.equal(s.turns.length,1);const turn=s.turns[0],arrays=[],hashes=[],readings=[];
    for(const part of turn.ttsParts){if(!part.trim()){arrays.push(null);continue;}const raw=await synth(part,turn.role,key);arrays.push(raw.samples);hashes.push(raw.hash);readings.push(raw.reading);}
    const joined=joinParts(arrays,24000,config.partGap);assert.equal(joined.cues.length,s.bounds.length);
    const b=encodeWav(joined.samples,24000);
    const normalized=run(['-i','pipe:0','-af','loudnorm=I=-20:TP=-3:LRA=7','-ar','24000','-ac','1','-f','s16le','pipe:1'],b);
    const samples=pcm(normalized),lead=s.slideKey==='s-names'?.5:key==='s-speed:1'?3.4:0;
    const next=segments[index+1];
    const cut=!next||s.slideKey!==next.slideKey;
    const gap=cut?config.pauses.cut:turn.role!==next.turns[0].role?config.pauses.speakerChange:config.pauses.sameSpeaker;
    // 原音にある文末0.10秒と次の文頭0.08秒も「間」に数える。
    // 題の後には既存の盤面0.7秒があるので、同じ無音を二重に足さない。
    const tail=Math.max(.3,gap-config.postPhonemeLength-config.prePhonemeLength-(s.slideKey==='s-intro'?.7:0));
    const dur=Math.ceil((samples.length/24000+tail+lead)*100)/100;
    const mix=new Float32Array(Math.round(dur*24000));mix.set(samples,Math.round(lead*24000));
    const cues=joined.cues.map(x=>+(x+lead).toFixed(4));
    const file=`steps/${s.slideKey}-${s.stepKey}.wav`;
    if(key==='s-speed:1')for(const at of [1.4,1.8])mixEffect(mix,dice,Math.round(at*24000));
    for(const effect of events[key]?.effects||[])mixEffect(mix,sounds[effect.sound],Math.round(effectTime(effect,s.bounds,cues)*24000));
    fs.writeFileSync(path.join(deck,'audio',file),encodeWav(mix,24000));
    manifest.segments[key]={file,dur,cues,sync:'manual',kind:'imported',inputHash:await inputHash(s)};
    const fadeLead=key==='s-selection:2'?2:key==='s-effect-fp:1'?1.4:['s-names:1','s-speed:1'].includes(key)?0:key==='s-return:1'?.5:.3;
    timing[key]={dur:+(dur+fadeLead).toFixed(2),hold:dur,lead:fadeLead,pad_after:0};
    measures.push({key,role:turn.role,text:turn.display,dur,gap,tail,readings,hashes});console.log(`${key} ${dur}s`);
  }
  fs.writeFileSync(path.join(deck,'audio/steps/s-intro-0.wav'),openingSound());
  manifest.segments['s-intro:0']={file:'steps/s-intro-0.wav',dur:2.6,cues:[],sync:'manual',kind:'imported'};
  const power=new Float32Array(28800);power.set(dice);fs.writeFileSync(path.join(deck,'audio/steps/power-se.wav'),encodeWav(power,24000));
  manifest.segments['s-power-roll:1']={file:'steps/power-se.wav',dur:1.2,cues:[],sync:'manual',kind:'imported',inputHash:await inputHash({turns:[]})};
  json(path.join(deck,'audio/manifest.json'),manifest);json(path.join(deck,'timeline.json'),timing);
  const duration=Object.values(timing).reduce((n,v)=>n+v.dur,0);
  json(path.join(local,'voice-report.json'),{version:'0.26.0',voices,made,cached,duration,measures});console.log(JSON.stringify({made,cached,duration}));
}
