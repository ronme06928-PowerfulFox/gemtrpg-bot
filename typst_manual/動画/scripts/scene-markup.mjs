import assert from 'node:assert/strict';

export const json = (data) => `<script type="application/json">${JSON.stringify(data)}</script>`;
export const boardBackground = `<m-background data-from="1" steps="1" aria-label="遺跡の背景"><div data-background-image><img src="images/ruins-battle.png" alt="石柱と開けた石床の遺跡"></div></m-background>`;
export const phase = `<m-phase aria-label="ラウンドの現在の段階">${['ラウンド開始', '選択フェーズ', '解決フェーズ', 'ラウンド終了'].map((s, i) => `${i ? '<span>→</span>' : ''}<span data-phase="${i}" data-readable>${s}</span>`).join('')}</m-phase>`;
export const fp = `<m-fp>${json({ initial: 0, gains: [{ amount: 1, reason: '勝利' }, { amount: 2, reason: '効果' }] })}<div class="app-fp" data-fp-value data-readable>0</div><span data-fp-reason data-readable></span></m-fp>`;
export function actor(enemy = false, { hp = false, animatedFp = false, hpValue, fpValue = 0, slot, spent = false, active = false } = {}) {
  const max = enemy ? 30 : 100;
  const current = hpValue ?? max;
  const slotHtml = slot === undefined ? '' : `<div class="s1-slot v2-slot${spent ? ' is-spent' : ''}${active ? ' first-slot' : ''}"><span>${slot}</span>${spent ? '<span class="v2-spent">行動済み</span>' : ''}</div>`;
  return `<div class="app-piece ${enemy ? 'enemy' : 'ally'}">${slotHtml}<div class="app-token-body"><img class="app-portrait" src="images/${enemy ? 'wolf-shularker' : 'ally-adventurer'}.png" alt="${enemy ? '人狼型シュラーカー' : '男冒険者'}"><div class="app-status">
    <div class="app-stat-row"><span class="app-stat-label" data-readable>HP</span><div class="app-bar"><div class="app-bar-fill hp" ${hp ? 'data-hp-fill' : ''} style="width:${current / max * 100}%"></div></div><span class="app-stat-value" ${hp ? 'data-hp-value' : ''} data-readable>${current}</span></div>
    <div class="app-stat-row"><span class="app-stat-label" data-readable>MP</span><div class="app-bar"><div class="app-bar-fill mp" style="width:100%"></div></div><span class="app-stat-value" data-readable>${enemy ? 6 : 10}</span></div>
    </div></div>${animatedFp ? fp : `<div class="app-fp" data-readable>${fpValue}</div>`}<div class="app-name" data-readable>${enemy ? '敵' : '味方'}</div></div>`;
}
export const dice = (power = false, enemy = false) => {
  // 計画53の作例。速度: 4+2=6。威力: 4+2+3=9。
  const data = power
    ? { face: enemy ? 1 : 3, value: enemy ? 4 + 1 + 1 : 4 + 2 + 3, from: [enemy ? 930 : 290, 230], stop: [500, 230], to: [600, 210] }
    : { face: 4, value: 4 + 2, from: [290, 230], stop: [500, 230], to: [290, 50] };
  assert.equal(data.value, power ? enemy ? 6 : 9 : 6);
  return `<m-dice aria-label="ダイスから${power ? '威力' : '速度値'}へ">${json(data)}<div data-die>${[1, 2, 3, 4, 5, 6].map((i) => `<span data-face="${i}">{{FIG:die-${i}}}</span>`).join('')}</div><span data-dice-number data-readable></span>${power ? `<div class="s1-formula" data-readable><span>4</span><span>+</span><span class="formula-face">{{FIG:die-${enemy ? 1 : 2}}}</span><span>+</span><span data-dice-target>？</span><span data-equals>=</span><span data-dice-total>？</span></div>` : '<span class="s1-slot" style="left:252px;top:12px" data-dice-target data-readable>？</span>'}</m-dice>`;
};
export const effect = `<m-effect-frame><div class="s1-effect-name" data-readable>基本の一太刀</div><div data-effect-text data-readable><span data-effect-timing>（ラウンド終了時）</span><span>：FPを2得る。</span><span data-effect-frame></span></div></m-effect-frame>`;
export const gm = `<m-gm-bubble aria-label="GMの案内"><div data-gm-panel><div class="s1-gm-icon" aria-label="GMの札">GM</div><div class="s1-gm-text" data-readable>ラウンド開始</div></div></m-gm-bubble>`;
