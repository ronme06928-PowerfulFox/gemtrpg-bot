// 承認用の静止絵コンテだけを生成する。本編・音声・既存台本へ書き込まない。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { shots } from './s2-storyboard-data.mjs';
import { phase, boardBackground, actor, dice, effect, gm } from './scene-markup.mjs';
import { renderCredits } from '../common/credits.mjs';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const base = path.join(video, '01_1ラウンドの流れ');
const out = path.join(video, '_local/s2-storyboard');
fs.mkdirSync(out, { recursive: true });
for (const dir of ['themes', 'figs', 'images']) fs.cpSync(path.join(base, dir), path.join(out, dir), { recursive: true });
fs.cpSync(path.join(video, 'common/components'), path.join(out, 'components'), { recursive: true });
for (const file of ['motion.css', 'credits.css']) fs.copyFileSync(path.join(video, 'common', file), path.join(out, file));
fs.copyFileSync(path.join(base, 'app_mock.css'), path.join(out, 'app_mock.css'));
fs.copyFileSync(path.join(video, 'scripts/s2-storyboard.css'), path.join(out, 'storyboard.css'));
fs.copyFileSync(path.join(video, 'common/assets/ruins-battle.png'), path.join(out, 'images/ruins-battle.png'));
const json = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const credits = json(path.join(base, 'credits.json'));
credits.credits.push({ label: '背景', value: 'Codex画像生成（OpenAI）' });
const pair = (a = {}, b = {}) => actor(false, a) + actor(true, b);
function arrows(id) {
  return `<svg class="v2-arrows" viewBox="0 0 1184 130" aria-label="互いのスロットを指定するマッチの矢印"><defs><marker id="arrow-${id}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="#ffb020"/></marker></defs><path d="M330 35 Q610 0 890 35"/><path d="M890 80 Q610 120 330 80"/></svg>`.replaceAll('<path d="M330', `<path marker-end="url(#arrow-${id})" d="M330`).replaceAll('<path d="M890', `<path marker-end="url(#arrow-${id})" d="M890`);
}
function board(shot) {
  switch (shot.state) {
    case 'initial': return pair() + '<div class="v2-premise">基本の一太刀／スキル以外の追加効果なし</div>';
    case 'empty-slots': return pair({ slot: '' }, { slot: '' });
    case 'speed': return pair({}, { slot: 4 }) + dice() + '<div class="v2-speed-formula">出目4＋速度補正2＝6<br>出目3＋速度補正1＝4</div>';
    case 'selection': return pair({ slot: 6 }, { slot: 4 }) + arrows(shot.id) + '<div class="v2-skill ally">基本の一太刀</div><div class="v2-skill enemy">基本の一太刀</div>';
    case 'resolve': return pair({ slot: 6, active: true }, { slot: 4 }) + arrows(shot.id);
    case 'power-ally': return pair({ slot: 6 }, { slot: 4 }) + dice(true) + '<div class="v2-formula-label">味方／物理補正3（1d3）</div>';
    case 'power-enemy': return pair({ slot: 6 }, { slot: 4 }) + dice(true, true) + '<div class="v2-formula-label">敵／物理補正2（1d2）</div><div class="v2-compare">味方9 ＞ 敵6</div>';
    case 'damage': return pair({ slot: 6, fpValue: 1, spent: true }, { slot: 4, hpValue: 21, spent: true }) + '<span data-damage>−9</span><div class="v2-victory">勝利 +1</div>';
    case 'effect-timing': return pair({ slot: 6, fpValue: 1, spent: true }, { slot: 4, hpValue: 21, spent: true }) + effect.replace('<m-effect-frame>', '<m-effect-frame data-from="4" steps="1">');
    case 'effect-fp': return pair({ slot: 6, fpValue: 3, spent: true }, { slot: 4, hpValue: 21, fpValue: 2, spent: true }) + effect.replace('<m-effect-frame>', '<m-effect-frame data-from="3">');
    case 'next': return pair({ slot: '', fpValue: 3 }, { slot: '', hpValue: 21, fpValue: 2 });
    default: throw new Error(shot.state);
  }
}
const sections = shots.map((shot) => {
  if (shot.state === 'credits') {
    const ref = '<div class="book-reference"><span class="book-ruby" role="img" aria-label="ルビー">{{FIG:ruby-fill}}</span><span>基本ルールブック 第4章『戦闘の基本』</span></div>';
    return renderCredits(json(path.join(video, 'common/credits.json')), credits)
      .replace('credits-page"', 'credits-page v2-slide v2-credits"')
      .replace('id="s-credits"', 'id="s-story-credits"')
      .replace('<div class="body', '<h2>クレジットと本への参照</h2><div class="body')
      .replace('</dl>', '</dl>' + ref);
  }
  const indicator = phase.replace('<m-phase ', `<m-phase steps="${shot.phase}" `);
  const bubble = shot.gm ? gm.replace('ラウンド開始</div>', `${shot.gm}</div>`) : '';
  return `<section class="slide s1-slide v2-slide noconcl" id="s-story-${shot.id}" style="--battle-background-position:${shot.crop};--story-background-zoom:${shot.zoom}">
<h2>${shot.title}</h2>${boardBackground.replace('<m-background ', '<m-background class="v2-background" ')}
<div class="body s1-body plot">${indicator}<div class="s1-board">${board(shot)}${bubble}</div></div>
<div class="v2-caption">${shot.caption}</div></section>`;
});
fs.writeFileSync(path.join(out, 'deck.html'), `<!DOCTYPE html><html lang="ja" data-theme="gemuria"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>1ラウンドの流れ v2 承認済み絵コンテ</title><link rel="stylesheet" href="app_mock.css"><link rel="stylesheet" href="motion.css"><link rel="stylesheet" href="credits.css"><link rel="stylesheet" href="storyboard.css"></head><body><div id="stage">${sections.join('\n')}</div></body></html>\n`);
const timing = {};
for (const s of shots) for (let k = 0; k <= s.phase; k++) timing[`s-story-${s.id}:${k}`] = { dur: s.state === 'credits' ? 5 : 1, lead: 0, hold: 0, pad_after: 0 };
fs.writeFileSync(path.join(out, 'timeline.json'), JSON.stringify(timing, null, 2) + '\n');
// 品質チェック用の短い口述原稿。本編への採用・音声生成には使わない。
fs.writeFileSync(path.join(out, 'narration.md'), shots.map((s) => `## ${s.title} {#s-story-${s.id}}\n${Array.from({ length: s.phase + 1 }, (_, k) => `[${k}] ${s.state === 'credits' ? 'クレジットの配置見本です。' : '絵コンテの配置を確認します。'}`).join('\n')}`).join('\n\n') + '\n');
fs.writeFileSync(path.join(out, 'shots.json'), JSON.stringify(shots, null, 2) + '\n');
console.log(`Storyboard: ${shots.length} frames; estimated ${shots.reduce((n, s) => n + s.seconds, 0)} seconds (not measured audio)`);
