import { createNativePanel } from './r1-resolve-native.mjs';
import { sceneAt } from './round-v3-data.mjs';
DECK.define('m-resolve-panel',class extends DECK.MotionElement {
  static steps=1;
  mount(){
    this.world=this.querySelector('.r1-world');this.native=createNativePanel(this.world);
    this.formula=this.querySelector('.r25-formula');this.world.querySelectorAll('[data-board="after"]').forEach(e=>e.remove());
    this.cutId=this.closest('section').id.slice(2);
  }
  duration(k){return DECK.TIMING[`${this.closest('section').id}:${k}`]?.dur||0;}
  render(k,t){
    if(!this.native)return;
    const s=sceneAt(this.cutId,k,t);this.world.style.transform='';this.native.render(s.time);
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

  }
});
