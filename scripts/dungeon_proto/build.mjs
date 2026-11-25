import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../../', import.meta.url);
const read = (path, encoding = 'utf8') => readFile(new URL(path, root), encoding);
const modules = ['common_ui', 'main_menu', 'paper_screens'];
const [source, script, cave, ...styles] = await Promise.all([
  read('scripts/dungeon_proto/page.html'),
  read('scripts/dungeon_proto/page.js'),
  read('static/images/backgrounds/暗い遺跡洞窟.webp', 'base64'),
  ...modules.map(name => read(`static/css/modules/${name}.css`)),
  read('scripts/dungeon_proto/page.css'),
]);
const html = source
  .replace('<!--STYLE-->', () => `<style>${styles.join('\n')}\n.dungeon-hero { --dungeon-cave: url(data:image/webp;base64,${cave}); }</style>`)
  .replace('<!--SCRIPT-->', () => `<script>\n${script}</script>`);
const output = new URL('_local/dungeon_proto/', root);
await mkdir(output, { recursive: true });
await writeFile(new URL('index.html', output), html, 'utf8');
console.log('Built _local/dungeon_proto/index.html');
