import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { voices } from './r25-dialogue-data.mjs';
import { decodeWav, encodeWav, peak } from './r1-audio.mjs';
import { sharedImageCss } from '../common/shared-images.mjs';
import { extractResolvePanelCss, GALLERY_PANEL_SELECTOR } from '../../../scripts/fx_gallery/panel_css.mjs';

const video='typst_manual/動画',src=path.join(video,'r25-dialogue'),dest=path.resolve(video,'_local/r25-dialogue');
const engine='C:/Users/yharu/tools/egatari-studio-0.6.3';
const {parseNarration}=await import(pathToFileURL(path.join(engine,'kit/core/narration-core.mjs')));
const {inputHash}=await import(pathToFileURL(path.join(engine,'kit/core/portable.mjs')));
const req=createRequire(path.join(engine,'package.json'));
const {parse,serialize}=await import(pathToFileURL(req.resolve('parse5')));
for(const name of ['out','logs','voice/cache','audio/steps','components/r25-panel','images','vendor/repo'])fs.mkdirSync(path.join(dest,name),{recursive:true});
const json=(file,obj)=>fs.writeFileSync(path.join(dest,file),JSON.stringify(obj,null,2)+'\n');
const run=(args,input)=>{
  const p=spawnSync('ffmpeg',['-v','error',...args],{input,maxBuffer:32*1024*1024});assert.equal(p.status,0,p.stderr?.toString());return p.stdout;
};
const endpoint='http://127.0.0.1:50021';
const request=async(url,init)=>{const r=await fetch(endpoint+url,{...init,signal:AbortSignal.timeout(180000)});assert.ok(r.ok,`${url}: ${r.status}`);return r;};
assert.equal(await (await request('/version')).json(),'0.26.0');
const speakers=await (await request('/speakers')).json();
for(const v of Object.values(voices)){
  const s=speakers.find(s=>s.name===v.name);assert.ok(s?.styles.some(s=>s.id===v.id&&s.name===v.style));
  const info=await (await request(`/speaker_info?speaker_uuid=${s.speaker_uuid}`)).json();
  fs.writeFileSync(path.join(dest,'logs',`policy-${v.id}.md`),info.policy,'utf8');
}
let made=0,cached=0;
const synth=async(text,role,setting={})=>{
  const voice={...voices[role],...setting};
  const settings={speedScale:voice.speedScale,pitchScale:voice.pitchScale,intonationScale:voice.intonationScale,prePhonemeLength:.08,postPhonemeLength:.1,outputSamplingRate:24000,outputStereo:false};
  const reading=text.replaceAll('1d3','いちディーさん');
  const hash=createHash('sha256').update(JSON.stringify({version:'0.26.0',voice:voice.id,reading,settings})).digest('hex');
  const file=path.join(dest,'voice/cache',hash+'.wav');
  if(fs.existsSync(file))cached++;else{
    const q=await (await request(`/audio_query?speaker=${voice.id}&text=${encodeURIComponent(reading)}`,{method:'POST'})).json();Object.assign(q,settings);
    const wav=Buffer.from(await (await request(`/synthesis?speaker=${voice.id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)})).arrayBuffer());
    decodeWav(wav);fs.writeFileSync(file,wav);json(`voice/cache/${hash}.json`,{role,text,voice,query:q});made++;
  }
  return {file,hash,...decodeWav(fs.readFileSync(file))};
};
const narration=fs.readFileSync(path.join(src,'narration.md'),'utf8');
const segments=parseNarration(narration),manifest={segments:{}},timing={},measures=[];
for(let k=0;k<=11;k++){const dur=k===1?1.2:k===8?.7:k===9?2.2:0;timing[`s-dialogue:${k}`]={dur,hold:dur,lead:0,pad_after:0};}
timing['s-credits:0']={dur:5,hold:5,lead:0,pad_after:0};
for(const s of segments){
  assert.equal(s.turns.length,1);const turn=s.turns[0],raw=await synth(turn.tts,turn.role);
  const normalized=run(['-i',raw.file,'-af','loudnorm=I=-20:TP=-3:LRA=7','-ar','24000','-ac','1','-f','wav','pipe:1']);
  // ffmpegのストリームWAVはサイズ未確定なのでPCMを取り出して正規ヘッダーへ戻す。
  const pcm=run(['-i','pipe:0','-f','s16le','-ar','24000','-ac','1','pipe:1'],normalized);
  const samples=Float32Array.from({length:pcm.length/2},(_,i)=>pcm.readInt16LE(i*2)/32768);
  assert.ok(peak(samples)<.9);
  const key=`${s.slideKey}:${s.stepKey}`,file=`steps/${s.slideKey}-${s.stepKey}.wav`;
  fs.writeFileSync(path.join(dest,'audio',file),encodeWav(samples,24000));
  const audioSeconds=samples.length/24000,dur=Math.ceil((audioSeconds+.1)*100)/100;
  manifest.segments[key]={file,dur:audioSeconds,cues:[],sync:'manual',kind:'imported',inputHash:await inputHash(s)};
  timing[key]={dur,hold:dur,lead:0,pad_after:0};
  measures.push({key,role:turn.role,text:turn.display,audioSeconds,dur,hash:raw.hash,peakDb:20*Math.log10(peak(samples))});
  console.log(`${key} ${turn.role}: ${dur}s`);
}
// 初期設定と速さ/抑揚だけを変えた短い比較素材を作る。原音キャッシュは再使用できる。
const candidates=[];
for(const role of ['expert','novice']){
  const text=segments.find(s=>s.turns[0].role===role).turns[0].tts;
  for(const setting of [{speedScale:1,intonationScale:1},{}]){
    const sound=await synth(text,role,setting);candidates.push({role,settings:{...voices[role],...setting},hash:sound.hash,seconds:sound.samples.length/sound.rate});
  }
}
const duration=Object.values(timing).reduce((n,v)=>n+v.dur,0),noviceSeconds=measures.filter(m=>m.role==='novice').reduce((n,m)=>n+m.dur,0);
// 本番のpower開始と同じ1回。既存素材の基準-22dBへ+6dBを適用する。
const sePcm=run(['-i','static/audio/dice-roll.mp3','-f','s16le','-ar','24000','-ac','1','pipe:1']);
const se=Float32Array.from({length:sePcm.length/2},(_,i)=>sePcm.readInt16LE(i*2)/32768);
assert.ok(se.length/24000<=1.2,'本番の威力段階内にSEが収まる');
const seGain=10**(-16/20)/peak(se);const seMix=new Float32Array(28800);seMix.set(se.map(x=>x*seGain));
fs.writeFileSync(path.join(dest,'audio/steps/power-se.wav'),encodeWav(seMix,24000));
manifest.segments['s-dialogue:1']={file:'steps/power-se.wav',dur:1.2,cues:[],sync:'manual',kind:'imported',inputHash:await inputHash({turns:[]})};
json('logs/voice-report.json',{version:'0.26.0',voices,measures,candidates,made,cached,dialogueSeconds:duration,soloSeconds:duration-noviceSeconds,sceneSeconds:duration-5,soloSceneSeconds:duration-noviceSeconds-5});
if(!fs.existsSync(path.join(dest,'logs/voice-first-generation.json')))fs.copyFileSync(path.join(dest,'logs/voice-report.json'),path.join(dest,'logs/voice-first-generation.json'));
json('audio/manifest.json',manifest);json('timeline.json',timing);fs.writeFileSync(path.join(dest,'narration.md'),narration);

// 本番依存はR1と同じ取り出し方で写し、その写しをbundleする。
const skill=JSON.parse(fs.readFileSync('data/cache/skills_cache.json','utf8'))['Ps-00'];
const entry=path.join(video,'scripts/r25-dialogue-runtime.mjs');
const opts={bundle:true,write:false,format:'iife',target:'es2020',charset:'utf8',minifyWhitespace:true,minifySyntax:true,metafile:true,define:{__R1_SKILL__:JSON.stringify(skill)}};
const scanned=await build({...opts,entryPoints:[entry]});const copyRoot=path.join(dest,'vendor/repo');const copies=[];
for(const file of Object.keys(scanned.metafile.inputs).filter(f=>!f.startsWith('<'))){
  const target=path.join(copyRoot,file);fs.mkdirSync(path.dirname(target),{recursive:true});const bytes=fs.readFileSync(file);fs.writeFileSync(target,bytes);
  copies.push({file,sha256:createHash('sha256').update(bytes).digest('hex')});
}
const bundled=await build({...opts,absWorkingDir:copyRoot,entryPoints:[entry]});fs.writeFileSync(path.join(dest,'components/r25-panel/index.js'),bundled.outputFiles[0].text);json('logs/copies.json',copies);
for(const n of ['app_mock.css','motion.css','round-v2.css'])fs.copyFileSync(path.join(video,'01_1ラウンドの流れ',n),path.join(dest,n));
for(const n of ['ruins','ally','enemy'])fs.copyFileSync(path.join(video,'common/assets/video',n+'.webp'),path.join(dest,'images',n+'.webp'));
fs.writeFileSync(path.join(dest,'shared-images.css'),sharedImageCss({ruins:'images/ruins.webp',ally:'images/ally.webp',enemy:'images/enemy.webp'}));
fs.writeFileSync(path.join(dest,'panel.css'),extractResolvePanelCss(fs.readFileSync('static/css/modules/visual_battle.css','utf8'))+'\n'+fs.readFileSync('static/css/modules/motion_fx.css','utf8').replaceAll('#resolve-flow-panel',GALLERY_PANEL_SELECTOR));
fs.copyFileSync(path.join(src,'deck.css'),path.join(dest,'deck.css'));
const tree=parse(fs.readFileSync(path.join(video,'_local/r1-resolve/out/r1-resolve-latest.html'),'utf8'));
const find=node=>node.attrs?.some(a=>a.name==='class'&&a.value.split(' ').includes('r1-world'))?node:(node.childNodes||[]).map(find).find(Boolean);
const world=serialize(find(tree));
const html=`<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>掛け合いの試作</title>${['app_mock.css','motion.css','round-v2.css','shared-images.css','panel.css','deck.css'].map(n=>`<link rel="stylesheet" href="${n}">`).join('')}</head><body><div id="stage"><section class="slide r25-slide noconcl" id="s-dialogue"><h2>威力からダメージ</h2><m-r25-panel steps="11" aria-label="本番の解決パネル"><div class="r1-world">${world}</div><div class="r25-phase"><span>ラウンド開始</span><span>選択フェーズ</span><span class="current">解決フェーズ</span><span>ラウンド終了</span></div><div class="r25-formula" hidden></div></m-r25-panel></section><section class="slide r25-credit noconcl" id="s-credits"><h2>試作のクレジット</h2><div><div class="credit-title">1ラウンドの流れ　掛け合いの試作</div>ジェムリアTRPG／創作ゆる大地<br>説明役　VOICEVOX:冥鳴ひまり<br>聞き手　VOICEVOX:春日部つむぎ<br>ダイス音　Springin’ Sound Stock<br>背景　Codex画像生成（OpenAI）<br>基本ルールブック 第4章「戦闘の基本」</div></section></div></body></html>`;
const captionDefault='<script>(()=>{const u=new URL(location.href);if(!u.searchParams.has("captions"))u.searchParams.set("captions","1");if(!u.searchParams.has("mode"))u.searchParams.set("mode","video");history.replaceState(null,"",u.href)})();</script>';
fs.writeFileSync(path.join(dest,'deck.html'),html.replace('<head>','<head>'+captionDefault));json('credits.json',{title:'1ラウンドの流れ 掛け合いの試作',credits:[{label:'説明役',value:'VOICEVOX:冥鳴ひまり'},{label:'聞き手',value:'VOICEVOX:春日部つむぎ'}]});
const buildDeck=()=>{const p=spawnSync(process.execPath,[path.join(engine,'kit/build.mjs'),path.join(dest,'deck.html'),'--embed-audio'],{encoding:'utf8',maxBuffer:8*1024*1024});assert.equal(p.status,0,p.stderr);console.log(p.stdout.trim());};
// 実際の一人語り版も同じ入力から組み、尺を検査できるようにする。
const soloTiming=structuredClone(timing),soloManifest=structuredClone(manifest);
for(const m of measures.filter(m=>m.role==='novice')){soloTiming[m.key]={dur:0,hold:0,lead:0,pad_after:0};delete soloManifest.segments[m.key];}
const soloNarration='## 威力からダメージ {#s-dialogue}\n'+segments.filter(s=>s.turns[0].role==='expert').map(s=>`[${s.stepKey}]\nExpert: ${s.turns[0].raw}\n`).join('');
json('timeline.json',soloTiming);json('audio/manifest.json',soloManifest);fs.writeFileSync(path.join(dest,'narration.md'),soloNarration);buildDeck();
fs.copyFileSync(path.join(dest,'out/deck.html'),path.join(dest,'out/solo-reference.html'));
json('timeline.json',timing);json('audio/manifest.json',manifest);fs.writeFileSync(path.join(dest,'narration.md'),narration);buildDeck();
fs.copyFileSync(path.join(dest,'out/deck.html'),path.join(dest,'out/r25-dialogue-latest.html'));
console.log(JSON.stringify({made,cached,duration,solo:duration-noviceSeconds}));
