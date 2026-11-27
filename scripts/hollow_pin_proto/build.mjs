// 推薦ピン（PR35-18）の試作を /_local/hollow_pin_proto/ に作る。本番のバンドルには入らない。
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../../', import.meta.url);
const read = (path, encoding = 'utf8') => readFile(new URL(path, root), encoding);
const [source, script, common, base, select, relic, events, page, cave] = await Promise.all([
  read('scripts/hollow_pin_proto/page.html'),
  read('scripts/hollow_pin_proto/page.js'),
  read('static/css/modules/common_ui.css'),
  read('scripts/hollow_map_proto/page.css'),
  read('scripts/hollow_map_select_proto/page.css'),
  read('scripts/hollow_relic_proto/page.css'),
  read('scripts/hollow_event_proto/page.css'),
  read('scripts/hollow_pin_proto/page.css'),
  read('static/images/backgrounds/暗い遺跡洞窟.webp', 'base64'),
]);
const images = `:root, [data-theme="abyss"] { --cave: url(data:image/webp;base64,${cave}); }`;
const html = source
  .replace('<!--STYLE-->', () => `<style>${common}\n${base}\n${select}\n${relic}\n${events}\n${page}\n${images}</style>`)
  .replace('<!--SCRIPT-->', () => `<script>\n${script}</script>`);
const output = new URL('_local/hollow_pin_proto/', root);
await mkdir(output, { recursive: true });
await writeFile(new URL('index.html', output), html, 'utf8');
console.log('Built _local/hollow_pin_proto/index.html');
