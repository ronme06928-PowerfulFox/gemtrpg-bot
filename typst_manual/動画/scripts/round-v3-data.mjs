export const voices = {
  expert: { name:'冥鳴ひまり', id:14, style:'ノーマル', speedScale:1.1, pitchScale:0, intonationScale:1.03 },
  novice: { name:'春日部つむぎ', id:8, style:'ノーマル', speedScale:1.08, pitchScale:0, intonationScale:1 }
};
export function sceneAt(id,k,t) {
  const clamp=(x,d)=>Math.min(Math.max(0,x),d-.000001);
  if(id==='names')return {time:k?clamp(t,.5):0};
  if(id==='power-roll')return {time:.5+(k?clamp(t,1.2):0)};
  if(id==='attack')return {time:1.7+(k?clamp(t,.7):0)};
  if(id==='outcome')return {time:k>=2?4.6-.000001:2.4+(k?clamp(t,2.2):0)};
  return {time:1.7-.000001,zoom:id==='power-ally'?'ally':k===1?'enemy':null,
    formula:id==='power-ally'?(k>=2?'ally':null):k===1?'enemy':null};
}
