import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = process.argv[2]
  ? pathToFileURL(resolve(process.argv[2]) + '/')
  : new URL('../../_local/ui_room_night_proto/', import.meta.url);
const widths = [1280, 1024];
const levels = [['none', 'なし'], ['light', '弱'], ['medium', '中']];
const scenes = [
  {
    id: 'a', title: 'A　探索中',
    note: '夜色の枠が立ち絵と探索背景を囲い、長文と判定は紙のチャットで追える。弱のかすれは金線の近くに収まり、中では線の途切れと角の曇りが分かりやすい。',
    shots: [['a', 'PC4人・会話・探索ドック']],
  },
  {
    id: 'b', title: 'B　戦闘中のラウンド',
    note: '宣言パネルとチャットは紙の面として見分けられる。明るい陣営色は盤面で輪郭を拾いやすく、濃い青・赤は色の差が大きい。HP・MPは数字、FPは丸い札でも読める。',
    shots: [['b-board', '盤面と陣営色', true], ['b-declare', '宣言とチャット'], ['b-resolve', '解決とチャット']],
  },
  {
    id: 'c', title: 'C　窓',
    note: '紙の窓は暗い枠から浮き、行とボタンを拾いやすい。崩しは紙の縁に収まり、中は角の欠けと焼けが読める。宝石の印は絵文字のない見出しとタブに絞ると重複しない。',
    shots: [['c-character', 'キャラ設定・スキル・バフ'], ['c-items', 'アイテム'], ['c-room', 'ルーム設定'], ['c-skill', 'スキル詳細']],
  },
  {
    id: 'd', title: 'D　知らせ',
    note: '紙の窓は判断する箇所が分かり、誤りと成功は見出しと縁で区別できる。右下の知らせは盤面を覆わず、1024pxではチャットの末尾に重なる。',
    shots: [['d-confirm', '保存の確認'], ['d-error', '誤りの窓'], ['d-notices', '成功と誤りの知らせ']],
  },
];

const files = new Map();

function picture(id, variant, width, title, detail = false) {
  const src = `shots/${id}-${variant}-${width}${detail ? '-detail' : ''}.png`;
  const dimensions = detail ? (id === 'a-wear' ? [343, 281] : [315, 170]) : [width, 800];
  files.set(src, dimensions);
  return `<a href="${src}" target="_blank" rel="noopener">
    <img src="${src}" width="${dimensions[0]}" height="${dimensions[1]}" alt="${title}" loading="lazy"></a>`;
}

function figure(id, variant, width, title) {
  return `<figure><figcaption>${title}</figcaption>${picture(id, variant, width, title)}</figure>`;
}

function compare([id, title, palette], width) {
  if (!palette) return `<h3>${title}</h3><div class="comparison">
    ${figure(id, 'current', width, '今の画面')}
    ${figure(id, 'night', width, '夜色の枠と紙の窓')}
  </div>`;
  return `<h3>${title}</h3><div class="comparison">
    ${figure(id, 'night', width, '今の陣営・HP・MP・FP色')}
    ${figure(id, 'tokens', width, '夜色のトークンによる陣営・HP・MP・FP色')}
  </div>`;
}

function wearComparison(id, width) {
  return `<h3>飾りの崩し</h3><p>宝石の印を付けた同じ画面で比較します。下段は同じ範囲の拡大です。</p>
    <div class="triptych">${levels.map(([variant, label]) =>
      figure(`${id}-wear`, variant, width, label)).join('')}</div>
    <div class="triptych details">${levels.map(([variant, label]) =>
      picture(`${id}-wear`, variant, width, `${label}の拡大`, true)).join('')}</div>`;
}

function sceneHtml({id, title, note, shots}, width) {
  const gems = id === 'c' ? `<h3>宝石の印 · 絵文字のない見出しとタブ</h3>
    <div class="comparison">${figure('c-title', 'night', width, '印なし')}${figure('c-title', 'gems', width, '印あり')}</div>` : '';
  const wear = id === 'a' || id === 'c' ? wearComparison(id, width) : '';
  return `<section id="${id}-${width}"><h2>${title}</h2><p>${note}</p>
    ${shots.map(shot => compare(shot, width)).join('')}${wear}${gems}</section>`;
}

const main = widths.map((width, i) => `<div data-width="${width}" ${i ? 'hidden' : ''}>
  ${scenes.map(scene => sceneHtml(scene, width)).join('')}</div>`).join('');

await Promise.all([...files].map(async ([filename, [width, height]]) => {
  const png = await readFile(new URL(filename, out));
  if (png.readUInt32BE(16) !== width || png.readUInt32BE(20) !== height) throw Error(`画像の寸法が不正です: ${filename}`);
}));

const common = await readFile(new URL('../../static/css/modules/common_ui.css', import.meta.url), 'utf8');
const night = common.match(/\[data-theme="night"\]\s*\{[^}]+\}/)[0];

await writeFile(new URL('index.html', out), `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>夜色の枠と紙の窓 · 第2回</title>
<style>
  ${night}
  * { box-sizing: border-box; }
  body { color-scheme: dark; color: var(--ui-text); background: var(--ui-page); font: 16px/1.65 system-ui, sans-serif;
    max-width: 2600px; padding: 1.2rem clamp(.8rem, 2vw, 2rem) 3rem; margin: auto; }
  h1, h2 { font-family: var(--ui-head-font); margin: 0; }
  h1, a { color: var(--ui-focus); }
  h3 { margin: 1.1rem 0 .4rem; font-size: 1rem; }
  p { margin: .35rem 0 .8rem; max-width: 75ch; color: var(--ui-sub); }
  fieldset { margin: 0; padding: .2rem .7rem .45rem; border: 1px solid var(--ui-control); border-radius: .4rem; }
  legend { padding-inline: .3rem; }
  label { margin-inline-end: .7rem; white-space: nowrap; }
  input { accent-color: var(--ui-primary); }
  :focus-visible { outline: 2px solid var(--ui-focus); outline-offset: 2px; }
  nav { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
  section { margin-top: 1.6rem; border-top: 1px solid var(--ui-gold); padding-top: 1rem; }
  .comparison, .triptych { display: grid; gap: .8rem; }
  .comparison { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .triptych { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .details { margin-top: .8rem; }
  figure { margin: 0; }
  figcaption { margin-bottom: .25rem; font-weight: 700; }
  img { display: block; width: 100%; height: auto; border: 1px solid var(--ui-gold); border-radius: .4rem; }
</style>
</head>
<body data-theme="night">
<h1>夜色の枠と紙の窓 · 第2回</h1>
<p>同じルームを1280pxと1024pxで撮影しました。画像を押すと原寸で開きます。</p>
<nav aria-label="表示切替">
  <fieldset><legend>撮影時の幅</legend>
    ${widths.map((width, i) => `<label><input type="radio" name="width" value="${width}" ${i ? '' : 'checked'}> ${width}px</label>`).join('')}
  </fieldset>
  ${scenes.map(({id, title}) => `<a data-scene="${id}" href="#${id}-1280">${title}</a>`).join('')}
</nav>
<main>${main}</main>
<script>
  document.addEventListener('change', ({target}) => {
    if (target.name !== 'width') return;
    for (const panel of document.querySelectorAll('[data-width]')) panel.hidden = panel.dataset.width !== target.value;
    for (const link of document.querySelectorAll('[data-scene]')) link.href = '#' + link.dataset.scene + '-' + target.value;
  });
</script>
</body>
</html>
`, 'utf8');
console.log(`比較ページを生成しました（画像 ${files.size} 枚）`);
