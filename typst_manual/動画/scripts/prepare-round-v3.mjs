// 承認済み12カットの原稿を組む。共通部品の写しは生成入力（Git管理外）。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import { buildResolvePanel, prepareDialogueVoice } from './prepare-round-v3-support.mjs';
import { actor, phase, boardBackground, dice, effect, gm, json } from './scene-markup.mjs';
import { renderCredits } from '../common/credits.mjs';
import { renderOpening } from '../common/opening.mjs';
import { shareSceneImages, sharedImageCss, videoImages } from '../common/shared-images.mjs';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ');
fs.mkdirSync(path.join(deck, 'sfx/imported'), { recursive: true });
fs.copyFileSync(path.join(video, '../../static/audio/dice-roll.mp3'), path.join(deck, 'sfx/imported/dice-roll.mp3'));
fs.copyFileSync(path.join(video, '../assets/gemuria_logo.png'), path.join(deck, 'images/gemuria_logo.png'));
for (const part of ['phase', 'dice', 'impact-hp', 'fp', 'effect-frame', 'background', 'gm-bubble']) {
  fs.cpSync(path.join(video, 'common/components', part), path.join(deck, 'components', part), { recursive: true });
}
for (const css of ['motion.css', 'credits.css', 'opening.css']) fs.copyFileSync(path.join(video, 'common', css), path.join(deck, css));
const imageManifest = JSON.parse(fs.readFileSync(path.join(video, 'common/assets/video/manifest.json'), 'utf8'));
const imageHash = (file) => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
for (const [key, image] of Object.entries(videoImages)) {
  if (key === 'logo') continue; // 元PNGは上で未加工のままコピー済み。
  const source = key === 'ruins' ? path.join(video, 'common/assets', image.source) : path.join(deck, 'images', image.source);
  const compressed = path.join(video, 'common/assets/video', image.file);
  assert.equal(imageHash(source), imageManifest.sources[key], '元画像を更新したらprepare-video-images.pyで再変換する');
  assert.equal(imageHash(compressed), imageManifest.outputs[key], 'WebPと変換記録を一致させる');
  fs.copyFileSync(compressed, path.join(deck, 'images', image.file));
}
fs.writeFileSync(path.join(deck, 'shared-images.css'), sharedImageCss(Object.fromEntries(Object.entries(videoImages).map(([key, image]) => [key, `images/${image.file}`]))));
const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const credits = read(path.join(deck, 'credits.json'));
credits.credits = credits.credits.filter((x) => x.label !== '背景');
credits.credits.push({ label: '背景', value: 'Codex画像生成（OpenAI）' });
const shots=[
['intro','題と開始状態',1,2],['slots','スロット',1,6],['speed','速度値を決める',1,5],['selection','宣言',2,5],['resolve','解決へ',3,1],
['names','名前',3,1],['power-roll','威力のロール',3,1],['power-ally','味方の威力の説明',3,5],['power-enemy','敵と比較',3,4],['attack','攻撃',3,1],['outcome','勝敗とダメージ',3,3],
['return','盤面への帰還',3,3],['effect-timing','効果のタイミング',4,3],['effect-fp','終了時FP',4,3],['next','次ラウンド',1,4],['credits','最後の5秒',1,0]
].map(([id,title,phase,count])=>({id,title,phase,count,crop:'center 65%',zoom:1.08}));
const voiceConfig = read(path.join(deck, 'voice/config.json'));
const wordLead = voiceConfig.partGap + voiceConfig.prePhonemeLength;
const pair = (a = {}, b = {}) => actor(false, a) + actor(true, b);
function arrows(id) {
  return '<svg class="v2-arrows" viewBox="0 0 1184 130" aria-label="マッチ"><defs><marker id="match-head" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="#ffb020"/></marker></defs><path marker-end="url(#match-head)" d="M330 35 Q610 0 890 35"/><path marker-end="url(#match-head)" d="M890 80 Q610 120 330 80"/></svg>'.replaceAll('match-head', `match-head-${id}`);
}
const slots = (a = {}, b = {}) => pair({ slot: 6, ...a }, { slot: 4, ...b });
function content(id) {
  switch (id) {
    case 'intro': return pair().replaceAll('class="app-bar"', 'class="app-bar" data-spoken="full"').replaceAll('class="app-fp"', 'class="app-fp" data-spoken="fp-zero"') + '<div class="v2-premise">基本スキル／スキル以外の追加効果なし</div>';
    case 'slots': return pair({ slot: '' }, { slot: '' }).replace('class="s1-slot v2-slot"', 'class="s1-slot v2-slot" data-mark="slot-ally"');
    case 'speed': {
      const ally = dice().replace('data-dice-target data-readable', 'data-dice-target id="speed-ally" data-mark="slot-ally" data-readable');
      const enemy = dice().replace('"face":4,"value":6,"from":[290,230],"stop":[500,230],"to":[290,50]', '"face":3,"value":4,"from":[930,230],"stop":[700,230],"to":[930,50]').replace('left:252px', 'left:892px').replace('data-dice-target data-readable', 'data-dice-target id="speed-enemy" data-readable');
      return pair({ slot: '' }, { slot: '' }) + ally + enemy + '<div class="v2-speed-formula"><div data-speed-row>出目<span data-speed-face>？</span>＋<span data-spoken="speed-correction">速度補正2</span>＝<span data-speed-total>？</span></div><div data-speed-row>出目<span data-speed-face>？</span>＋<span data-spoken="speed-correction">速度補正1</span>＝<span data-speed-total>？</span></div></div>';
    }
    case 'selection': return slots() + arrows(id).replace('class="v2-arrows"', 'class="v2-arrows" data-mark="match-arrow"') + '<div class="v2-skill ally">基本の一太刀</div><div class="v2-skill enemy">基本の一太刀</div>';
    case 'resolve': return slots() + arrows(id);
    case 'power-ally': case 'power-enemy': {
      const enemy = id === 'power-enemy';
      const power = dice(true, enemy).replace('"face":', `"firstFace":${enemy ? 1 : 2},"face":`)
        .replace(/<span class="formula-face">[\s\S]*?<\/span>/, `<span class="formula-face" data-spoken="power-die"><span data-first-label>1d2</span><span data-first-die>${[1, 2, 3, 4, 5, 6].map((n) => `<span data-first-face="${n}">{{FIG:die-${n}}}</span>`).join('')}</span></span>`)
        .replace('<span>4</span>', '<span data-spoken="power-base">4</span>')
        .replace('data-dice-target>', 'data-dice-target data-spoken="power-physical">')
        .replace('data-dice-total>', `data-dice-total id="${enemy ? 'power-enemy' : 'power-ally'}">`);
      return slots() + power + `<div class="v2-formula-label">${enemy ? '敵／物理補正2（1d2）' : '味方／物理補正3（1d3）'}</div>` + (enemy ? '<div class="v2-compare">味方9 ＞ 敵6</div>' : '');
    }
    case 'return': return slots({fpValue:1,spent:true},{hpValue:21,spent:true})+'<div class="v3-win-fp">勝利＋1 ／ FP 0 → 1</div>';
    case 'damage': return `<m-impact-hp>${json({ hp: 30, max: 30, damage: 9 })}${slots({ animatedFp: true }, { hp: true }).replace('data-hp-value', 'data-hp-value data-mark="enemy-hp"').replace('data-fp-value', 'data-fp-value data-mark="ally-fp"')}<div data-hit></div><span data-damage></span></m-impact-hp>`;
    case 'effect-timing': return slots({ fpValue: 1, spent: true }, { hpValue: 21, spent: true }) + effect;
    case 'effect-fp': return slots({ animatedFp: true, spent: true }, { animatedFp: true, hpValue: 21, spent: true }).replaceAll('"initial":0,"gains":[{"amount":1,"reason":"勝利"},{"amount":2,"reason":"効果"}]', '"initial":1,"gains":[{"amount":2,"reason":"効果"}]').replace(/(<div class="app-piece enemy">[\s\S]*?"initial":)1/, '$10') + effect.replace('data-effect-text', 'data-effect-text data-mark="end-fp"');
    case 'next': return pair({ slot: '', fpValue: 3 }, { slot: '', hpValue: 21, fpValue: 2 });
    default: throw new Error(id);
  }
}

await buildResolvePanel(deck);
const native = `<div class="r1-board s1-slide v2-slide" data-board="before"><div class="r1-board-bg video-shared-image" data-video-image="ruins" role="img" aria-label="遺跡"></div><div class="s1-board">${shareSceneImages(content('selection'))}</div></div>`;
const sections=shots.map(shot=>{
  if(shot.id==='credits')return renderCredits(read(path.join(video,'common/credits.json')),credits)
    .replace('credits-page"','credits-page v2-slide v2-credits"').replace('<div class="body','<h2>クレジットと本への参照</h2><div class="body')
    .replace('</dl>','</dl><div class="book-reference"><span class="book-ruby">{{FIG:ruby-fill}}</span><span>基本ルールブック 第4章『戦闘の基本』</span></div>');
  if(['names','power-roll','power-ally','power-enemy','attack','outcome'].includes(shot.id))return `<section class="slide r25-slide noconcl" id="s-${shot.id}"><h2>${shot.title}</h2><m-resolve-panel steps="${shot.count}" aria-label="本番の解決パネル"><div class="r1-world" data-clip>${native}</div><div class="r25-phase"><span>ラウンド開始</span><span>選択フェーズ</span><span class="current">解決フェーズ</span><span>ラウンド終了</span></div><div class="r25-formula" hidden></div></m-resolve-panel></section>`;
  const bubble=['slots','resolve','next'].includes(shot.id)?gm.replace('ラウンド開始</div>',`${shot.id==='resolve'?'解決開始':'ラウンド開始'}</div>`):'';
  const markup=`${boardBackground.replace('<m-background ','<m-background class="v2-background" ')}<div class="body s1-body plot">${phase}<div class="s1-board">${content(shot.id)}${bubble}</div></div>`
    .replace(/<(m-(?:background|phase|dice|impact-hp|fp|effect-frame|gm-bubble))\b([^>]*)>/g,(_,tag,attrs)=>`<${tag}${attrs.replace(/\ssteps="\d+"/g,'')} steps="0">`);
  return `<section class="slide s1-slide v2-slide noconcl" id="s-${shot.id}" style="--battle-background-position:${shot.crop};--story-background-zoom:${shot.zoom}"><h2>${shot.title}</h2>${markup}${shot.id==='intro'?renderOpening('1ラウンドの流れ'):''}<m-round-cut steps="${shot.count}">${json({id:shot.id,phase:shot.phase,wordLead})}</m-round-cut></section>`;
});
const css=['app_mock.css','motion.css','credits.css','round-v2.css','opening.css','shared-images.css','panel.css','dialogue.css','fonts.css'];
const licenses=['Cinzel','ZenAntique'].map(n=>fs.readFileSync(path.join(video,'common/fonts',`OFL-${n}.txt`),'utf8').split(/\r?\n/).map(line=>line.trimEnd()).join('\n')).join('\n');
const creditDirector=`<m-round-cut steps="1">${json({id:'credits',phase:1,wordLead})}</m-round-cut>`;
const scenes=sections.join('\n').replace(/(<section[^>]*id="s-credits"[\s\S]*?)(<\/section>)/,`$1${creditDirector}$2`);
const defaultCaptions='<script>(()=>{const u=new URL(location.href);if(!u.searchParams.has("captions"))u.searchParams.set("captions","1");history.replaceState(null,"",u.href)})();</script>';
const flow=await prepareDialogueVoice(deck,shots);
fs.writeFileSync(path.join(deck,'deck.html'),`<!doctype html><html lang="ja" data-theme="gemuria"><head><meta charset="utf-8"><title>1ラウンドの流れ v3</title>${defaultCaptions}${css.map(n=>`<link rel="stylesheet" href="${n}">`).join('')}<script type="application/json" id="video-flow">${JSON.stringify(flow)}</script><script type="text/plain" id="font-licenses">${licenses}</script></head><body><div id="stage">${shareSceneImages(scenes)}</div></body></html>\n`);
console.log('v3: 16 cuts');
