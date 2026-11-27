// 淵遺物の窓・報酬・虚夢変転（PR35-14）の試作を /_local/hollow_relic_proto/ に作る。本番のバンドルには入らない。
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../../', import.meta.url);
const read = (path, encoding = 'utf8') => readFile(new URL(path, root), encoding);
const [source, script, common, base, page, cave, male, female, wolf, dwarf] = await Promise.all([
  read('scripts/hollow_relic_proto/page.html'),
  read('scripts/hollow_relic_proto/page.js'),
  read('static/css/modules/common_ui.css'),
  read('scripts/hollow_map_proto/page.css'),
  read('scripts/hollow_relic_proto/page.css'),
  read('static/images/backgrounds/暗い遺跡洞窟.webp', 'base64'),
  read('static/images/characters/男冒険者.png', 'base64'),
  read('static/images/characters/女冒険者.png', 'base64'),
  read('static/images/characters/人狼型シュラーカー.png', 'base64'),
  read('static/images/characters/小人型シュラーカー.png', 'base64'),
]);
const images = `:root, [data-theme="abyss"] { --cave: url(data:image/webp;base64,${cave}); }
:root { --face-male: url(data:image/png;base64,${male}); --face-female: url(data:image/png;base64,${female});
  --enemy-wolf: url(data:image/png;base64,${wolf}); --enemy-dwarf: url(data:image/png;base64,${dwarf}); }`;
const html = source
  .replace('<!--STYLE-->', () => `<style>${common}\n${base}\n${page}\n${images}</style>`)
  .replace('<!--SCRIPT-->', () => `<script>\n${script}</script>`);
const output = new URL('_local/hollow_relic_proto/', root);
await mkdir(output, { recursive: true });
await writeFile(new URL('index.html', output), html, 'utf8');
console.log('Built _local/hollow_relic_proto/index.html');
