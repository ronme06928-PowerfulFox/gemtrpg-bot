import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../../', import.meta.url);
const read = (path, encoding = 'utf8') => readFile(new URL(path, root), encoding);
const modules = ['common_ui', 'modals', 'master_data', 'unit_management', 'main_menu'];
const [source, script, cave, ...styles] = await Promise.all([
  read('scripts/hollow_data_proto/page.html'),
  read('scripts/hollow_data_proto/page.js'),
  read('static/images/backgrounds/暗い遺跡洞窟.webp', 'base64'),
  ...modules.map(name => read(`static/css/modules/${name}.css`)),
  read('scripts/hollow_data_proto/themes.css'),
  read('scripts/hollow_data_proto/page.css'),
]);
const html = source
  .replace('<!--STYLE-->', () => `<style>${styles.join('\n')}\n[data-theme="abyss"] { --cave: url(data:image/webp;base64,${cave}); }</style>`)
  .replace('<!--SCRIPT-->', () => `<script>\n${script}</script>`);
const output = new URL('_local/hollow_data_proto/', root);
await mkdir(output, { recursive: true });
await writeFile(new URL('index.html', output), html, 'utf8');
console.log('Built _local/hollow_data_proto/index.html');
