import { createNativePanel } from './r1-resolve-native.mjs';
import { prototypeTime, holds } from './r1-resolve-time.mjs';

DECK.define('m-resolve-prototype', class extends DECK.MotionElement {
  static steps = 5;
  mount() {
    this.world = this.querySelector('.r1-world');
    this.native = createNativePanel(this.world);
    window.R1_PROTOTYPE = { native: this.native, render: (k, t) => this.render(k, t) };
  }
  duration(k) { return holds[k]; }
  render(k, t) {
    if (!this.native) return;
    const frame = prototypeTime(k, t);
    this.native.panel.style.display = frame.board ? 'none' : '';
    this.world.querySelector('[data-board="before"]').style.opacity = frame.board === 'after' ? '0' : '1';
    this.world.querySelector('[data-board="after"]').style.opacity = frame.board === 'after' ? '1' : '0';
    if (!frame.board) this.native.render(frame.time);
    this.dataset.stage = frame.stage || frame.board;
    this.dataset.nativeTime = String(frame.time);
  }
});
