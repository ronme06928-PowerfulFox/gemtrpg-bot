// ホロウの部屋の操作盤（PR35-6）の試作を /_local/hollow_party_proto/ に作る。本番のバンドルには入らない。
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../../', import.meta.url);
const read = (path, encoding = 'utf8') => readFile(new URL(path, root), encoding);
const [source, script, common, page, cave, male, female] = await Promise.all([
  read('scripts/hollow_party_proto/page.html'),
  read('scripts/hollow_party_proto/page.js'),
  read('static/css/modules/common_ui.css'),
  read('scripts/hollow_party_proto/page.css'),
  read('static/images/backgrounds/暗い遺跡洞窟.webp', 'base64'),
  read('static/images/characters/男冒険者.png', 'base64'),
  read('static/images/characters/女冒険者.png', 'base64'),
]);
const images = `[data-theme="abyss"] { --cave: url(data:image/webp;base64,${cave}); }
:root { --face-male: url(data:image/png;base64,${male}); --face-female: url(data:image/png;base64,${female}); }`;
const html = source
  .replace('<!--STYLE-->', () => `<style>${common}\n${page}\n${images}</style>`)
  .replace('<!--SCRIPT-->', () => `<script>\n${script}</script>`);
const output = new URL('_local/hollow_party_proto/', root);
await mkdir(output, { recursive: true });
await writeFile(new URL('index.html', output), html, 'utf8');
console.log('Built _local/hollow_party_proto/index.html');
