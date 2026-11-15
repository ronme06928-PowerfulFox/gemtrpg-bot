// 本物のマスターデータの画面に「紙と金・控えめ」を当てて見比べる：node scripts/ui_layout_proto/build-real.mjs
// 先に node scripts/catalog_preview/pr19/build.mjs で作った current.html（本物の管理画面のコードを偽物のサーバーで動かす）に、
// 上書きの CSS と切り替えを足す。出力：/_local/ui_layout_proto/master_real.html
import { readFile, writeFile, mkdir } from 'node:fs/promises';

const root = new URL('../../', import.meta.url);
const read = path => readFile(new URL(path, root), 'utf8');
const [page, skin, template] = await Promise.all([
  read('_local/catalog_preview/pr19/current.html'),
  read('scripts/ui_layout_proto/real_skin.css'),
  read('manuals/projects/app_foundation/ui/ui_template.html'),
]);
// 紙の質感は、ひな形の値をそのまま使う。
const paper = template.slice(template.indexOf('[data-theme="paper"] {'), template.indexOf('[data-theme="night"] {'));
const textures = ['--ui-page-tex', '--ui-tex'].map(name => paper.match(new RegExp(`${name}: .+;`))[0]).join('\n  ');
const control = `<div id="skin-switch" role="group" aria-label="見た目">
<button type="button" data-skin="paper" aria-pressed="true">紙と金</button><button type="button" data-skin="" aria-pressed="false">今の見た目</button></div>
<script>document.documentElement.dataset.skin = 'paper';
document.getElementById('skin-switch').addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button) return;
  document.documentElement.dataset.skin = button.dataset.skin;
  for (const each of event.currentTarget.querySelectorAll('button')) each.setAttribute('aria-pressed', each === button);
});</script>`;
const html = page
  .replace('</head>', () => `<style>:root[data-skin="paper"] {\n  ${textures}\n}\n${skin}</style>\n</head>`)
  .replace('</body>', () => `${control}\n</body>`)
  .replace(/<title>[^<]*<\/title>/, '<title>マスターデータ（本物の画面）· 紙と金</title>');
await mkdir(new URL('_local/ui_layout_proto/', root), { recursive: true });
await writeFile(new URL('_local/ui_layout_proto/master_real.html', root), html, 'utf8');
console.log('Built _local/ui_layout_proto/master_real.html');
