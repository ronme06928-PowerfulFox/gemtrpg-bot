// 本編に書き込まず、Git管理外に8場面の確認デッキを組む。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const base = path.join(video, '01_1ラウンドの流れ');
const common = path.join(video, 'common');
const out = path.join(video, '_local/s1-components');
fs.mkdirSync(path.join(out, 'images'), { recursive: true });
for (const dir of ['themes', 'figs']) fs.cpSync(path.join(base, dir), path.join(out, dir), { recursive: true });
fs.cpSync(path.join(common, 'components'), path.join(out, 'components'), { recursive: true });
fs.copyFileSync(path.join(base, 'app_mock.css'), path.join(out, 'app_mock.css'));
fs.copyFileSync(path.join(common, 'motion.css'), path.join(out, 'motion.css'));
for (const file of ['ally-adventurer.png', 'wolf-shularker.png']) fs.copyFileSync(path.join(base, 'images', file), path.join(out, 'images', file));
fs.copyFileSync(path.join(common, 'assets/ruins-battle.png'), path.join(out, 'images/ruins-battle.png'));

const json = (data) => `<script type="application/json">${JSON.stringify(data)}</script>`;
const boardBackground = `<m-background data-from="1" steps="1" aria-label="遺跡の背景"><div data-background-image><img src="images/ruins-battle.png" alt="石柱と開けた石床の遺跡"></div></m-background>`;
const phase = `<m-phase aria-label="ラウンドの現在の段階">${['開始', '選択', '解決', '終了'].map((s, i) => `${i ? '<span>→</span>' : ''}<span data-phase="${i}" data-readable>${s}</span>`).join('')}</m-phase>`;
const fp = `<m-fp>${json({ initial: 0, gains: [{ amount: 1, reason: '勝利' }, { amount: 2, reason: '効果' }] })}<div class="app-fp" data-fp-value data-readable>0</div><span data-fp-reason data-readable></span></m-fp>`;
function actor(enemy = false, { hp = false, animatedFp = false } = {}) {
  const max = enemy ? 30 : 100;
  return `<div class="app-piece ${enemy ? 'enemy' : 'ally'}"><div class="app-token-body"><img class="app-portrait" src="images/${enemy ? 'wolf-shularker' : 'ally-adventurer'}.png" alt="${enemy ? '人狼型シュラーカー' : '男冒険者'}"><div class="app-status">
    <div class="app-stat-row"><span class="app-stat-label" data-readable>HP</span><div class="app-bar"><div class="app-bar-fill hp" ${hp ? 'data-hp-fill' : ''} style="width:100%"></div></div><span class="app-stat-value" ${hp ? 'data-hp-value' : ''} data-readable>${max}</span></div>
    <div class="app-stat-row"><span class="app-stat-label" data-readable>MP</span><div class="app-bar"><div class="app-bar-fill mp" style="width:100%"></div></div><span class="app-stat-value" data-readable>${enemy ? 6 : 10}</span></div>
    </div></div>${animatedFp ? fp : '<div class="app-fp" data-readable>0</div>'}<div class="app-name" data-readable>${enemy ? '敵' : '味方'}</div></div>`;
}
const dice = (power = false) => {
  // 計画53の作例。速度: 5+1=6。威力: 4+2+3=9。
  const data = power
    ? { face: 3, value: 4 + 2 + 3, from: [290, 230], stop: [500, 230], to: [600, 210] }
    : { face: 5, value: 5 + 1, from: [290, 230], stop: [500, 230], to: [290, 50] };
  assert.equal(data.value, power ? 9 : 6);
  return `<m-dice aria-label="ダイスから${power ? '威力' : '速度値'}へ">${json(data)}<div data-die>${[1, 2, 3, 4, 5, 6].map((i) => `<span data-face="${i}">{{FIG:die-${i}}}</span>`).join('')}</div><span data-dice-number data-readable></span>${power ? '<div class="s1-formula" data-readable>4 + 2 + 3 =</div><span class="s1-power" data-dice-target data-readable>？</span>' : '<span class="s1-slot" style="left:252px;top:12px" data-dice-target data-readable>？</span>'}</m-dice>`;
};
const effect = `<m-effect-frame><div class="s1-effect-name" data-readable>基本の一太刀</div><div data-effect-text data-readable><span data-effect-timing>（ラウンド終了時）</span><span>：FPを2得る。</span><span data-effect-frame></span></div></m-effect-frame>`;
const gm = `<m-gm-bubble aria-label="GMの案内"><div data-gm-panel><div class="s1-gm-icon" role="img" aria-label="GMの仮アイコン：円形の顔"><svg viewBox="0 0 80 80"><circle cx="40" cy="40" r="36" style="fill:var(--series-3);stroke:var(--emph);stroke-width:4"/><circle cx="28" cy="33" r="4" style="fill:var(--fg)"/><circle cx="52" cy="33" r="4" style="fill:var(--fg)"/><path d="M26 49 Q40 62 54 49" style="fill:none;stroke:var(--fg);stroke-width:4;stroke-linecap:round"/></svg></div><div class="s1-gm-text" data-readable>GM：ラウンド開始</div></div></m-gm-bubble>`;
const cases = [
  { id: 'phase', title: '段階表示', steps: 4, content: `${phase}<div class="s1-board app-board">${actor()}${actor(true)}</div>` },
  { id: 'dice-slot', title: 'ダイス → 速度値のスロット', steps: 1, content: `<div class="s1-board app-board">${actor()}${actor(true)}${dice()}</div>` },
  { id: 'dice-power', title: 'ダイス → 最終威力', steps: 1, content: `<div class="s1-board app-board">${actor()}${actor(true)}${dice(true)}</div>` },
  { id: 'impact', title: '一撃 → HP（動画の説明用）', steps: 1, content: `<div class="s1-board app-board"><m-impact-hp>${json({ hp: 30, max: 30, damage: 9 })}${actor()}${actor(true, { hp: true })}<span data-hit></span><span data-damage data-readable></span></m-impact-hp></div>` },
  { id: 'fp', title: 'FPの丸：勝利と効果', steps: 2, content: `<div class="s1-board app-board">${actor(false, { animatedFp: true })}${actor(true)}</div>` },
  { id: 'effect', title: '効果文の枠：タイミング → 全体', steps: 2, content: `<div class="s1-board app-board">${actor()}${actor(true)}${effect}</div>` },
  { id: 'background', title: '背景：青空の遺跡', steps: 1, content: `<div class="s1-board app-board">${boardBackground}${actor()}${actor(true)}</div>` },
  { id: 'gm', title: 'GMの吹き出し（仮アイコン）', steps: 1, content: `<div class="s1-board app-board">${actor()}${actor(true)}${gm}</div>`, caption: '字幕の帯：下部を案内と分けて使います。' }
];
const timeline = {};
for (const c of cases) {
  timeline[`s-${c.id}:0`] = { dur: 0.1, lead: 0, hold: 0, pad_after: 0 };
  for (let k = 1; k <= c.steps; k++) timeline[`s-${c.id}:${k}`] = { dur: c.id === 'effect' && k === 1 ? 4.5 : c.id === 'phase' ? 1.3 : 2.8, lead: 0, hold: 0, pad_after: 0 };
}
fs.writeFileSync(path.join(out, 'deck.html'), `<!DOCTYPE html>
<html lang="ja" data-theme="gemuria"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>S1 共通の動きの部品</title><link rel="stylesheet" href="app_mock.css"><link rel="stylesheet" href="motion.css"></head>
<body><div id="stage">${cases.map((c) => `<section class="slide s1-slide noconcl" id="s-${c.id}"><h2>${c.title}</h2><div class="body s1-body plot">${c.content}</div>${c.caption ? `<div class="caption-reserve">${c.caption}</div>` : ''}</section>`).join('\n')}</div></body></html>\n`);
fs.writeFileSync(path.join(out, 'timeline.json'), JSON.stringify(timeline, null, 2) + '\n');
fs.writeFileSync(path.join(out, 'narration.md'), cases.map((c) => `## ${c.title} {#s-${c.id}}\n\n${Array.from({ length: c.steps + 1 }, (_, k) => `[${k}] ${c.title}の部品を確認します。`).join('\n')}`).join('\n\n') + '\n');
console.log(`S1 preview: ${out}`);
