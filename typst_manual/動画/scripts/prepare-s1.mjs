// 本編に書き込まず、Git管理外に8場面の確認デッキを組む。
import fs from 'node:fs';
import path from 'node:path';
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

import { json, boardBackground, phase, actor, dice, effect, gm } from './scene-markup.mjs';

const cases = [
  { id: 'phase', title: '段階表示', steps: 4, content: `${phase}<div class="s1-board app-board">${actor()}${actor(true)}</div>` },
  { id: 'dice-slot', title: 'ダイス → 速度値のスロット', steps: 1, content: `<div class="s1-board app-board">${actor()}${actor(true)}${dice()}</div>` },
  { id: 'dice-power', title: 'ダイス → 最終威力', steps: 1, content: `<div class="s1-board app-board">${actor()}${actor(true)}${dice(true)}</div>` },
  { id: 'impact', title: '一撃 → HP（動画の説明用）', steps: 1, content: `<div class="s1-board app-board"><m-impact-hp>${json({ hp: 30, max: 30, damage: 9 })}${actor()}${actor(true, { hp: true })}<span data-hit></span><span data-damage data-readable></span></m-impact-hp></div>` },
  { id: 'fp', title: 'FPの丸：勝利と効果', steps: 2, content: `<div class="s1-board app-board">${actor(false, { animatedFp: true })}${actor(true)}</div>` },
  { id: 'effect', title: '効果文の枠：タイミング → 全体', steps: 2, content: `<div class="s1-board app-board">${actor()}${actor(true)}${effect}</div>` },
  { id: 'background', title: '背景：青空の遺跡', steps: 1, content: `<div class="s1-board app-board">${boardBackground}${actor()}${actor(true)}</div>` },
  { id: 'gm', title: 'GMの札と吹き出し', steps: 1, content: `<div class="s1-board app-board">${actor()}${actor(true)}${gm}</div>`, caption: '字幕の帯：下部を案内と分けて使います。' }
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
