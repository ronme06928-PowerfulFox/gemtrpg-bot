// 承認済み12カットの原稿を組む。共通部品の写しは生成入力（Git管理外）。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { shots } from './s2-storyboard-data.mjs';
import { actor, phase, boardBackground, dice, effect, gm, json } from './scene-markup.mjs';
import { renderCredits } from '../common/credits.mjs';
import { prepareVoice } from './prepare-voice.mjs';
import { renderOpening, writeOpeningAudio } from '../common/opening.mjs';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ');
fs.mkdirSync(path.join(deck, 'sfx/imported'), { recursive: true });
fs.copyFileSync(path.join(video, '../../static/audio/dice-roll.mp3'), path.join(deck, 'sfx/imported/dice-roll.mp3'));
fs.copyFileSync(path.join(video, '../assets/gemuria_logo.png'), path.join(deck, 'images/gemuria_logo.png'));
for (const part of ['phase', 'dice', 'impact-hp', 'fp', 'effect-frame', 'background', 'gm-bubble']) {
  fs.cpSync(path.join(video, 'common/components', part), path.join(deck, 'components', part), { recursive: true });
}
for (const css of ['motion.css', 'credits.css', 'opening.css']) fs.copyFileSync(path.join(video, 'common', css), path.join(deck, css));
fs.copyFileSync(path.join(video, 'common/assets/ruins-battle.png'), path.join(deck, 'images/ruins-battle.png'));
const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const credits = read(path.join(deck, 'credits.json'));
credits.credits = credits.credits.filter((x) => x.label !== '背景');
credits.credits.push({ label: '背景', value: 'Codex画像生成（OpenAI）' });
const counts = [2, 2, 3, 2, 1, 2, 1, 3, 1, 2, 3];
const pair = (a = {}, b = {}) => actor(false, a) + actor(true, b);
function arrows(id) {
  return '<svg class="v2-arrows" viewBox="0 0 1184 130" aria-label="マッチ"><defs><marker id="match-head" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="#ffb020"/></marker></defs><path marker-end="url(#match-head)" d="M330 35 Q610 0 890 35"/><path marker-end="url(#match-head)" d="M890 80 Q610 120 330 80"/></svg>'.replaceAll('match-head', `match-head-${id}`);
}
const slots = (a = {}, b = {}) => pair({ slot: 6, ...a }, { slot: 4, ...b });
function content(id) {
  switch (id) {
    case 'intro': return pair() + '<div class="v2-premise">基本の一太刀／スキル以外の追加効果なし</div>';
    case 'slots': return pair({ slot: '' }, { slot: '' });
    case 'speed': {
      const ally = dice().replace('data-dice-target data-readable', 'data-dice-target id="speed-ally" data-mark="slot-ally" data-readable');
      const enemy = dice().replace('"face":4,"value":6,"from":[290,230],"stop":[500,230],"to":[290,50]', '"face":3,"value":4,"from":[930,230],"stop":[700,230],"to":[930,50]').replace('left:252px', 'left:892px').replace('data-dice-target data-readable', 'data-dice-target id="speed-enemy" data-readable');
      return pair({ slot: '' }, { slot: '' }) + ally + enemy + '<div class="v2-speed-formula"><div data-speed-row>出目<span data-speed-face>？</span>＋速度補正2＝<span data-speed-total>？</span></div><div data-speed-row>出目<span data-speed-face>？</span>＋速度補正1＝<span data-speed-total>？</span></div></div>';
    }
    case 'selection': return slots() + arrows(id).replace('class="v2-arrows"', 'class="v2-arrows" data-mark="match-arrow"') + '<div class="v2-skill ally">基本の一太刀</div><div class="v2-skill enemy">基本の一太刀</div>';
    case 'resolve': return slots() + arrows(id);
    case 'power-ally': case 'power-enemy': {
      const enemy = id === 'power-enemy';
      const power = dice(true, enemy).replace('"face":', `"firstFace":${enemy ? 1 : 2},"face":`)
        .replace(/<span class="formula-face">[\s\S]*?<\/span>/, `<span class="formula-face"><span data-first-die>${[1, 2, 3, 4, 5, 6].map((n) => `<span data-first-face="${n}">{{FIG:die-${n}}}</span>`).join('')}</span></span>`)
        .replace('data-dice-total>', `data-dice-total id="${enemy ? 'power-enemy' : 'power-ally'}">`);
      return slots() + power + `<div class="v2-formula-label">${enemy ? '敵／物理補正2（1d2）' : '味方／物理補正3（1d3）'}</div>` + (enemy ? '<div class="v2-compare">味方9 ＞ 敵6</div>' : '');
    }
    case 'damage': return `<m-impact-hp>${json({ hp: 30, max: 30, damage: 9 })}${slots({ animatedFp: true }, { hp: true }).replace('data-hp-value', 'data-hp-value data-mark="enemy-hp"').replace('data-fp-value', 'data-fp-value data-mark="ally-fp"')}<div data-hit></div><span data-damage></span></m-impact-hp>`;
    case 'effect-timing': return slots({ fpValue: 1, spent: true }, { hpValue: 21, spent: true }) + effect;
    case 'effect-fp': return slots({ animatedFp: true, spent: true }, { animatedFp: true, hpValue: 21, spent: true }).replaceAll('"initial":0,"gains":[{"amount":1,"reason":"勝利"},{"amount":2,"reason":"効果"}]', '"initial":1,"gains":[{"amount":2,"reason":"効果"}]').replace(/(<div class="app-piece enemy">[\s\S]*?"initial":)1/, '$10') + effect.replace('data-effect-text', 'data-effect-text data-mark="end-fp"');
    case 'next': return pair({ slot: '', fpValue: 3 }, { slot: '', hpValue: 21, fpValue: 2 });
    default: throw new Error(id);
  }
}
const sections = shots.map((shot, i) => {
  if (shot.id === 'credits') return renderCredits(read(path.join(video, 'common/credits.json')), credits)
    .replace('credits-page"', 'credits-page v2-slide v2-credits"').replace('<div class="body', '<h2>クレジットと本への参照</h2><div class="body')
    .replace('</dl>', '</dl><div class="book-reference"><span class="book-ruby" role="img" aria-label="ルビー">{{FIG:ruby-fill}}</span><span>基本ルールブック 第4章『戦闘の基本』</span></div>');
  const bubble = ['slots', 'resolve', 'next'].includes(shot.id) ? gm.replace('ラウンド開始</div>', `${shot.id === 'resolve' ? '解決開始' : 'ラウンド開始'}</div>`) : '';
  // 各子部品を段階0に固定し、末尾のdirectorが時刻から最終状態を決める。
  const markup = `${boardBackground.replace('<m-background ', '<m-background class="v2-background" ')}<div class="body s1-body plot">${phase}<div class="s1-board">${content(shot.id)}${bubble}</div></div>`
    .replace(/<(m-(?:background|phase|dice|impact-hp|fp|effect-frame|gm-bubble))\b([^>]*)>/g, (_, tag, attrs) => `<${tag}${attrs.replace(/\ssteps="\d+"/g, '')} steps="0">`);
  return `<section class="slide s1-slide v2-slide noconcl" id="s-${shot.id}" style="--battle-background-position:${shot.crop};--story-background-zoom:${shot.zoom}"><h2>${shot.title}</h2>${markup}${shot.id === 'intro' ? renderOpening('1ラウンドの流れ') : ''}<m-round-cut aria-label="カットの動きの進行" steps="${counts[i]}">${json({ id: shot.id, phase: shot.phase })}</m-round-cut></section>`;
});
fs.writeFileSync(path.join(deck, 'deck.html'), `<!DOCTYPE html><html lang="ja" data-theme="gemuria"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>1ラウンドの流れ v2</title><link rel="stylesheet" href="app_mock.css"><link rel="stylesheet" href="motion.css"><link rel="stylesheet" href="credits.css"><link rel="stylesheet" href="round-v2.css"><link rel="stylesheet" href="opening.css"></head><body><div id="stage">${sections.join('\n')}</div></body></html>\n`);
if (process.argv.includes('--voice')) {
  await prepareVoice(deck, process.argv[2], { boost: 6, credits: true });
  writeOpeningAudio(deck);
  const first = path.join(deck, 'out/s2-voice-first-generation.json');
  if (!fs.existsSync(first)) fs.copyFileSync(path.join(deck, 'out/audio-report-plus6.json'), first);
}
console.log('v2: 12 cuts');
