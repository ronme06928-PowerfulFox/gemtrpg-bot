import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { launch,fileUrl } from 'file:///C:/Users/yharu/tools/egatari-studio-0.6.3/kit/browser.mjs';
import { pixelStats,LEGACY_TOL } from 'file:///C:/Users/yharu/tools/egatari-studio-0.6.3/kit/render-compare.mjs';
import { waitForVideoImages } from './video-image-browser.mjs';
import { sceneAt } from './r25-dialogue-data.mjs';
const root=path.resolve('typst_manual/動画/_local/r25-dialogue'),out=path.join(root,'out');
const frames=path.join(root,'frames');fs.mkdirSync(frames,{recursive:true});
const voice=JSON.parse(fs.readFileSync(path.join(root,'logs/voice-report.json'),'utf8'));
const errors=[],shots=[],checks=[];const browser=await launch();
try{
  const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
  await page.addInitScript(()=>{const NativeAudio=window.Audio;window.__r25Players=[];window.Audio=function(...args){const a=new NativeAudio(...args);window.__r25Players.push(a);return a;};window.Audio.prototype=NativeAudio.prototype;});
  page.on('pageerror',e=>errors.push(e.message));await page.route(/^https?:/,r=>r.abort());
  await page.goto(fileUrl(path.join(out,'r25-dialogue-latest.html')));await page.waitForFunction(()=>DECK.ready);await waitForVideoImages(page);
  assert.equal(await page.evaluate(()=>DECK.captions()),true,'URL指定なしで字幕ON');
  const seek=async(k,t)=>{await page.evaluate(({k,t})=>DECK.seek(0,k,t),{k,t});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));};
  const timeline=await page.evaluate(()=>DECK.timeline().map(s=>({i:s.i,k:s.k,dur:s.dur,audio:!!s.audio})));
  const total=timeline.reduce((n,s)=>n+s.dur,0);assert.ok(Math.abs(total-voice.dialogueSeconds)<.001);assert.ok(total>=30&&total<=45);
  assert.equal(timeline.filter(s=>s.audio).length,9);
  // 音声はデータURIのまま読み、オフラインで全てデコードする。
  const decoded=await page.evaluate(async()=>{
    const text=[...document.scripts].map(e=>e.textContent).join('\n');
    const urls=[...new Set(text.match(/data:audio\/[\w.+-]+;base64,[A-Za-z0-9+/=]+/g)||[])];
    const context=new AudioContext(),results=[];
    for(const url of urls){const bytes=Uint8Array.from(atob(url.split(',')[1]),c=>c.charCodeAt(0));const b=await context.decodeAudioData(bytes.buffer);results.push(b.duration);}
    await context.close();return results;
  });assert.equal(decoded.length,9);
  for(const row of timeline.filter(s=>s.i===0)){
    const times=new Set(row.dur?[0,row.dur/2,row.dur-.001]:[0]);for(let t=0;t<row.dur;t+=.25)times.add(+t.toFixed(3));
    for(const t of times){
      await seek(row.k,t);
      const state=await page.evaluate(()=>({opacity:getComputedStyle(R25).opacity,time:+R25.dataset.nativeTime,
        caption:[...document.querySelectorAll('#deck-cap .cap-line')].map(e=>({text:e.textContent,novice:e.classList.contains('novice'),size:parseFloat(getComputedStyle(e).fontSize),box:e.getBoundingClientRect().toJSON(),clipped:e.scrollHeight>e.clientHeight+1})),
        name:document.querySelector('.r25-speaker')?.textContent,
        hiddenLabels:[...R25.native.panel.querySelectorAll('.top-band,.progress-band,.skill-id,.description h3')].every(e=>getComputedStyle(e).visibility==='hidden'),
        cutPlaques:[...R25.native.panel.querySelectorAll('.skill-plaque')].map(e=>getComputedStyle(e).visibility),
        formula:R25.formula.hidden?'':R25.formula.textContent,
        clocks:R25.native.clocks,errors:DECK.componentErrors}));
      assert.equal(state.opacity,'1','部品を透明にする予約属性を使わない');assert.deepEqual(state.errors,[]);assert.ok(state.hiddenLabels);
      assert.ok(Object.values(state.clocks).every(v=>v===null));assert.ok(Math.abs(state.time-sceneAt(row.k,t).time)<.00001,JSON.stringify({k:row.k,t,state:state.time,expected:sceneAt(row.k,t)}));
      const spoken=voice.measures.find(m=>m.key===`s-dialogue:${row.k}`);
      if(spoken){
        assert.equal(state.caption.length,1);assert.equal(state.caption[0].text,spoken.text);
        assert.equal(state.caption[0].novice,spoken.role==='novice');assert.ok(state.name.includes(spoken.role==='novice'?'つむぎ':'ひまり'));
        const c=state.caption[0];assert.ok(c.size>=27&&!c.clipped&&c.box.top>=0&&c.box.bottom<=720);
      }else assert.equal(state.caption.length,0,'無言の演出に前の台詞を持ち越さない');
      if(sceneAt(row.k,t).zoom)assert.ok(state.cutPlaques.every(v=>v==='hidden'),'寄りで切れた札を出さない');
      assert.ok(!state.formula.includes('動画の説明式'));
      checks.push({k:row.k,t,time:state.time});
    }
    await seek(row.k,row.dur/2);const before=await page.screenshot();await seek(11,2);await seek(0,0);await seek(row.k,row.dur/2);const after=await page.screenshot();
    const diff=await pixelStats(page,before,after);assert.ok(diff.n<=LEGACY_TOL,JSON.stringify({k:row.k,diff}));
    if([2,3,5,7,8,10,11].includes(row.k)){const name=`a-${row.k}`;fs.writeFileSync(path.join(frames,name+'.png'),before);shots.push({name,k:row.k,diff});}
  }
  // Bの左右配置。声・本文・時刻はAと同じ。
  await page.goto(fileUrl(path.join(out,'r25-dialogue-latest.html'))+'?subtitle=b&mode=video');await page.waitForFunction(()=>DECK.ready);await waitForVideoImages(page);
  assert.equal(await page.evaluate(()=>DECK.captions()),true,'動画モードも初期字幕ON');
  for(const k of [2,3]){await seek(k,1);await page.screenshot({path:path.join(frames,`b-${k}.png`)});}
  await page.evaluate(()=>DECK.seek(1,0,3));
  assert.ok((await page.locator('#s-credits').innerText()).includes('VOICEVOX:春日部つむぎ'));
  assert.ok((await page.locator('#s-credits').innerText()).includes('VOICEVOX:冥鳴ひまり'));
  await page.screenshot({path:path.join(frames,'credits.png')});
  // 比較版の実タイムラインも測定する。
  await page.goto(fileUrl(path.join(out,'solo-reference.html'))+'?mode=video');await page.waitForFunction(()=>DECK.ready);
  const solo=await page.evaluate(()=>DECK.timeline().reduce((n,s)=>n+s.dur,0));assert.ok(Math.abs(solo-voice.soloSeconds)<.001);
  // 読み上げの開始、停止、切替が実際に動くことを通信遮断で確認する。
  await page.goto(fileUrl(path.join(out,'r25-dialogue-latest.html'))+'?mode=video');await page.waitForFunction(()=>DECK.ready);
  await page.evaluate(()=>DECK.seek(0,2,0));await page.keyboard.press('a');await page.waitForTimeout(1300);
  const playing=await page.evaluate(()=>window.__r25Players.map(e=>({time:e.currentTime,paused:e.paused,src:e.src.slice(0,20)})));
  await page.keyboard.press('a');
  assert.ok(playing.some(e=>!e.paused&&e.time>0),'埋め込み音声が再生される');
  await page.evaluate(()=>DECK.seek(0,0,0));await page.keyboard.press('a');
  const seen=new Set(),autoplay=[];let creditAt=null;const began=Date.now();
  while(Date.now()-began<(total+4)*1000){
    await page.waitForTimeout(300);
    const snapshot=await page.evaluate(()=>({k:+R25.dataset.r25Step,credit:document.querySelector('#s-credits').classList.contains('active'),
      caption:document.querySelector('#deck-cap .cap-line')?.textContent,
      audio:window.__r25Players.some(e=>!e.paused&&e.currentTime>.05)}));
    const elapsed=(Date.now()-began)/1000;
    if(snapshot.credit){creditAt??=elapsed;if(elapsed-creditAt>=5)break;continue;}
    const spoken=voice.measures.find(m=>m.key===`s-dialogue:${snapshot.k}`);
    if(spoken&&snapshot.audio){assert.equal(snapshot.caption,spoken.text);seen.add(snapshot.k);}
    if(!autoplay.some(row=>row.k===snapshot.k))autoplay.push({elapsed,...snapshot});
  }
  await page.evaluate(()=>DECK.autoplay(false));
  assert.equal(seen.size,8,'通し再生で8発言全てを確認');assert.ok(creditAt!==null,'最後の5秒へ到達');
  const old=JSON.parse(fs.readFileSync('typst_manual/動画/_local/r2-storyboard/capture-report.json','utf8'));
  for(const [file,hash]of Object.entries(old.protectedFiles))assert.equal(createHash('sha256').update(fs.readFileSync(file)).digest('hex'),hash,file);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(root,'logs/browser-report.json'),JSON.stringify({total,solo,delta:total-solo,decoded,checks,shots,playing,autoplay,creditAt,errors},null,2)+'\n');
  console.log(`PASS: ${checks.length} times, 12 rewind states, 8 voices + 1 SE; dialogue ${total}s / solo ${solo}s`);
}finally{await browser.close();}
