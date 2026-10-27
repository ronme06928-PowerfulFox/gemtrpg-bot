// 本のSVGが転がり、確定値がスロットまたは威力の位置へ移る。
DECK.define('m-dice', class extends DECK.MotionElement {
  static steps = 1;
  static shape = {
    schema: { type: 'object', required: ['face', 'value', 'from', 'stop', 'to'], properties: {
      face: { type: 'integer', minimum: 1, maximum: 6 },
      firstFace: { type: 'integer', minimum: 1, maximum: 6 },
      value: { type: 'integer', minimum: 1 },
      from: { type: 'array', items: { type: 'number' }, minItems: 2, maxItems: 2 },
      stop: { type: 'array', items: { type: 'number' }, minItems: 2, maxItems: 2 },
      to: { type: 'array', items: { type: 'number' }, minItems: 2, maxItems: 2 }
    } },
    example: { face: 5, value: 6, from: [290, 230], stop: [500, 230], to: [290, 50] }
  };
  mount() {
    this.die = this.querySelector('[data-die]');
    this.faces = [...this.querySelectorAll('[data-face]')];
    this.number = this.querySelector('[data-dice-number]');
    this.target = this.querySelector('[data-dice-target]');
    this.total = this.querySelector('[data-dice-total]');
    this.first = this.querySelector('[data-first-die]');
  }
  duration(k) { return k ? 2.4 : 0; }
  render(k, t) {
    const time = k ? t : 0;
    const roll = DECK.prog(time, 0, 1.1);
    const fly = DECK.prog(time, 1.5, 0.9);
    const settled = k > 0 && time >= 1.1;
    const face = settled ? this.data.face : (Math.floor(roll * 13) % 6) + 1;
    this.faces.forEach((e) => { e.style.display = Number(e.dataset.face) === face ? 'block' : 'none'; });
    const [x, y] = this.data.stop;
    const host = this.getBoundingClientRect();
    const target = this.target.getBoundingClientRect();
    const scale = host.width / this.offsetWidth || 1;
    const to = this.total ? [(target.x + target.width / 2 - host.x) / scale, (target.y + target.height / 2 - host.y) / scale] : this.data.to;
    const dx = this.total ? DECK.lerp(x, to[0], fly) : x;
    const dy = this.total ? DECK.lerp(y, to[1], fly) : y;
    this.die.style.transform = `translate(${DECK.lerp(this.data.from[0], dx, roll)}px, ${DECK.lerp(this.data.from[1], dy, roll) - Math.abs(Math.sin(roll * Math.PI * 3)) * 45}px) rotate(${720 * roll}deg)`;
    this.die.style.opacity = this.total ? '1' : String(1 - fly);
    this.number.textContent = String(this.data.value);
    this.number.style.opacity = !this.total && settled && time >= 1.5 && fly < 1 ? '1' : '0';
    this.number.style.transform = `translate(${DECK.lerp(x, this.data.to[0], fly)}px, ${DECK.lerp(y, this.data.to[1], fly)}px)`;
    this.target.textContent = fly >= 1 ? String(this.total ? this.data.face : this.data.value) : '？';
    this.target.style.opacity = this.total && fly >= 1 ? '0' : '1';
    if (this.total) this.total.textContent = fly >= 1 ? String(this.data.value) : '？';
    // 本編の2個の威力ダイス。式の箱は固定し、その中のSVGを動かす。
    if (this.first) {
      const box = this.first.parentElement.getBoundingClientRect();
      const end = [(box.x + box.width / 2 - host.x) / scale, (box.y + box.height / 2 - host.y) / scale];
      const px = DECK.lerp(this.data.from[0] - 70, DECK.lerp(x - 70, end[0], fly), roll) - end[0];
      const py = DECK.lerp(this.data.from[1], DECK.lerp(y, end[1], fly), roll) - end[1] - Math.abs(Math.sin(roll * Math.PI * 3)) * 45;
      this.first.style.transform = `translate(${px}px, ${py}px) rotate(${720 * roll}deg)`;
      const firstFace = settled ? this.data.firstFace : (Math.floor(roll * 13 + 2) % 6) + 1;
      this.first.querySelectorAll('[data-first-face]').forEach((el) => { el.style.display = +el.dataset.firstFace === firstFace ? 'block' : 'none'; });
    }
  }
});
