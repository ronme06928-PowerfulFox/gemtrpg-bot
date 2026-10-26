// 動画の説明用。一撃の到着を起点にHPを減らす（アプリの演出の再現ではない）。
DECK.define('m-impact-hp', class extends DECK.MotionElement {
  static steps = 1;
  static shape = {
    schema: { type: 'object', required: ['hp', 'max', 'damage'], properties: {
      hp: { type: 'integer', minimum: 0 }, max: { type: 'integer', minimum: 1 }, damage: { type: 'integer', minimum: 0 }
    } }, example: { hp: 30, max: 30, damage: 9 }
  };
  mount() {
    this.hit = this.querySelector('[data-hit]');
    this.value = this.querySelector('[data-hp-value]');
    this.fill = this.querySelector('[data-hp-fill]');
    this.damage = this.querySelector('[data-damage]');
  }
  duration(k) { return k ? 2.4 : 0; }
  render(k, t) {
    const time = k ? t : 0;
    const travel = DECK.prog(time, 0, 0.8);
    const drain = DECK.prog(time, 0.8, 1.1);
    const float = DECK.prog(time, 0.8, 1.6);
    const hp = Math.max(0, this.data.hp - Math.round(this.data.damage * drain));
    this.hit.style.transform = `translate(${640 * travel}px, 0)`;
    this.hit.style.opacity = k && travel < 1 ? '1' : '0';
    this.value.textContent = String(hp);
    this.fill.style.width = `${hp / this.data.max * 100}%`;
    this.damage.textContent = `−${this.data.damage}`;
    this.damage.style.transform = `translateY(${-65 * float}px)`;
    this.damage.style.opacity = k && time >= 0.8 ? String(1 - DECK.prog(time, 1.8, 0.6)) : '0';
  }
});
