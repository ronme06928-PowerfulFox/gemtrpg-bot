// 勝利FPと終了時効果のFPを別の段階で示す。
DECK.define('m-fp', class extends DECK.MotionElement {
  static steps = 2;
  static shape = {
    schema: { type: 'object', required: ['initial', 'gains'], properties: {
      initial: { type: 'integer', minimum: 0 },
      gains: { type: 'array', minItems: 1, maxItems: 2, items: { type: 'object', required: ['amount', 'reason'], properties: {
        amount: { type: 'integer', minimum: 1 }, reason: { type: 'string' }
      } } }
    } }, example: { initial: 0, gains: [{ amount: 1, reason: '勝利' }, { amount: 2, reason: '効果' }] }
  };
  mount() { this.value = this.querySelector('[data-fp-value]'); this.reason = this.querySelector('[data-fp-reason]'); }
  duration(k) { return k ? 1.4 : 0; }
  render(k, t) {
    const index = Math.max(0, Math.min(k, this.data.gains.length) - 1);
    const p = k ? DECK.prog(t, 0, 1.1) : 0;
    const before = this.data.initial + this.data.gains.slice(0, index).reduce((n, e) => n + e.amount, 0);
    this.value.textContent = String(before + Math.round(this.data.gains[index].amount * p));
    const glow = p >= 1 ? 0 : Math.sin(p * Math.PI);
    this.value.style.boxShadow = `0 0 ${32 * glow}px var(--accent2)`;
    this.value.style.outline = `${8 * glow}px solid var(--accent2)`;
    this.reason.textContent = `${this.data.gains[index].reason} +${this.data.gains[index].amount}`;
    this.reason.style.opacity = k ? String(DECK.prog(t, 0, 0.3)) : '0';
  }
});
