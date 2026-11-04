import { createNativePanel } from './r1-resolve-native.mjs';
import { sceneAt } from './r25-dialogue-data.mjs';
DECK.define('m-r25-panel',class extends DECK.MotionElement {
  static steps=14;
  mount(){
    this.world=this.querySelector('.r1-world');this.native=createNativePanel(this.world);
    this.formula=this.querySelector('.r25-formula');this.world.querySelectorAll('[data-board="after"]').forEach(e=>e.remove());
    window.R25=this;
    const mode=new URLSearchParams(location.search).get('subtitle')==='b'?'b':'a';
    document.documentElement.dataset.subtitle=mode;
    document.addEventListener('deck:ready',()=>DECK.captions(true),{once:true});
    document.addEventListener('deck:captions',()=>this.updateSpeaker());
    this.observe=new MutationObserver(()=>this.updateSpeaker());this.observe.observe(document.body,{subtree:true,childList:true});
  }
  updateSpeaker(){
    const cap=document.querySelector('#deck-cap');if(!cap)return;
    const novice=!!cap.querySelector('.novice');cap.dataset.speaker=novice?'novice':'expert';
    const badge=cap.querySelector('.r25-speaker');const name=novice?'聞き手 つむぎ':'説明役 ひまり';
    if(badge?.textContent===name)return;
    cap.querySelector('.r25-speaker')?.remove();
    if(cap.querySelector('.cap-line')){const e=document.createElement('span');e.className='r25-speaker';e.textContent=name;cap.prepend(e);}
  }
  duration(k){return k===1?1.2:k===11?.7:k===12?2.2:0;}
  render(k,t){
    if(!this.native)return;
    const s=sceneAt(k,t);this.world.style.transform='';this.native.render(s.time);
    const zoomed=!!s.zoom;this.native.panel.classList.toggle('r25-zoom',zoomed);
    if(zoomed){
      const side=s.zoom==='ally'?'attacker':'defender',box=this.native.panel.querySelector(`.combatant.${side} > .gem`).getBoundingClientRect();
      const base=this.getBoundingClientRect();const screenScale=base.width/1280;
      const x=(box.x-base.x+box.width/2)/screenScale,y=(box.y-base.y+box.height/2)/screenScale;
      this.world.style.transform=`translate(${640-2.3*x}px,${245-2.3*y}px) scale(2.3)`;
    }
    this.formula.hidden=!s.formula;
    this.formula.innerHTML=s.formula==='enemy'?'4 ＋ 1d2 ＋ 1d2<br>4 ＋ 1 ＋ 1 ＝ <b>6</b>':'4 ＋ 1d2 ＋ 1d3<br>4 ＋ 2 ＋ 3 ＝ <b>9</b>';
    this.dataset.nativeTime=s.time;this.dataset.r25Step=k;
    this.updateSpeaker();
  }
});
