import assert from 'node:assert/strict';

const escape = (value) => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const text = (value, key) => {
  assert.ok(typeof value === 'string' && value.trim(), `クレジットの${key}が空です`);
  return escape(value);
};

// ロゴは各デッキ内のimages/gemuria_logo.pngへ、元PNGをそのまま配置する。
export function renderCredits(branding, video) {
  const title = text(video.title, 'title');
  assert.ok(Array.isArray(video.credits), 'creditsは配列で指定してください');
  const voice = video.credits.filter(r=>['音声','声'].includes(r.label)).map(r=>r.value);
  const effects = video.credits.filter(r=>['効果音','ダイス音'].includes(r.label)).map(r=>r.value);
  const rows = [
    ...(voice.length?[{label:'声',value:voice.join('／')}]:[]),
    ...(effects.length?[{label:'効果音',value:effects.join('・')}]:[]),
    ...video.credits.filter(r=>!['音声','声','効果音','ダイス音','発行元'].includes(r.label))
  ];
  return `<section class="slide noconcl credits-page" id="s-credits">
  <div class="body credits-content">
    <img class="credits-logo" src="images/gemuria_logo.png" alt="ジェムリアのロゴ">
    <p class="credits-project">${text(branding.project, 'project')}</p>
    <h1 class="credits-title">${title}</h1>
    <div class="credits-rule"></div>
    <dl class="credits-list">
${rows.map((r) => `      <div><dt>${text(r.label, 'label')}</dt><dd>${text(r.value, 'value')}</dd></div>`).join('\n')}
    </dl>
    ${branding.reference?`<div class="credits-book"><span class="credits-book-ruby" role="img" aria-label="ルビー">{{FIG:ruby-fill}}</span><span>${text(branding.reference,'reference')}</span></div>`:''}
    <p class="credits-publisher">${text(branding.publisher,'publisher')}</p>
  </div>
</section>`;
}
