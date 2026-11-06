// 新規SEは外部素材を使わずPCM合成。固定乱数で同じWAVを再生成する。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodeWav, peak } from './r1-audio.mjs';
const target=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../01_1ラウンドの流れ/sfx');
const rate=24000;
let seed=5406;
const noise=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/2147483648-1;};
for(const [name,duration] of [['soft-pop',.14],['soft-swish',.26],['paper-turn',.32]]){
  const samples=new Float32Array(Math.round(duration*rate));let phase=0,low=0,band=0;
  for(let i=0;i<samples.length;i++){
    const t=i/rate,x=t/duration;
    if(name==='soft-pop'){
      phase+=2*Math.PI*(145+430*Math.exp(-t*28))/rate;
      samples[i]=(Math.sin(phase)+.16*Math.sin(2*phase))*Math.min(1,t/.004)*Math.exp(-t/ .035)*(1-x);
    }else{
      const raw=noise();low+=.12*(raw-low);band+=.3*((raw-low)-band);
      const flutter=name==='paper-turn'?.6+.4*Math.sin(2*Math.PI*24*t)**2:1;
      samples[i]=band*Math.sin(Math.PI*x)**1.8*flutter;
    }
  }
  const gain=.8/peak(samples);
  fs.writeFileSync(path.join(target,`${name}.wav`),encodeWav(samples.map(x=>x*gain),rate));
}
console.log('自作SE: soft-pop / soft-swish / paper-turn');
