// 比較側は元の本番ソースを直接bundleし、egatariの段階変換を通さず本番の秒数を渡す。
import { createNativePanel } from './r1-resolve-native.mjs';
DECK.define('m-resolve-prototype', class extends DECK.MotionElement {
  static steps = 5;
  mount() {
    this.native = createNativePanel(this.querySelector('.r1-world'));
    this.querySelector('[data-board="after"]').style.visibility = 'hidden';
    window.R1_REFERENCE = this.native;
  }
  duration() { return 1; }
  render() {}
});
