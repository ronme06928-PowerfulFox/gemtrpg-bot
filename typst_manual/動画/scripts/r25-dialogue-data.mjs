export const voices = {
  expert: { name:'冥鳴ひまり', id:14, style:'ノーマル', speedScale:1.1, pitchScale:0, intonationScale:1.03 },
  novice: { name:'春日部つむぎ', id:8, style:'ノーマル', speedScale:1.08, pitchScale:0, intonationScale:1 }
};
const endPower = 1.7 - .000001, endOutcome = 4.6 - .000001;
function mappedScene(k,t) {
  if(k===0)return {time:.5+Math.min(Math.max(0,t),1.2-.000001)};
  if(k===7)return {time:1.7+Math.min(Math.max(0,t),.7-.000001)};
  if(k===8)return {time:2.4+Math.min(Math.max(0,t),2.2-.000001)};
  return {time:k>=9?endOutcome:endPower,zoom:[1,2,3].includes(k)?'ally':k===4?'enemy':null,
    formula:[2,3].includes(k)?'ally':k===4?'enemy':null};
}
export function sceneAt(k,t){return k===0?{time:.5}:mappedScene(k-1,t);}
