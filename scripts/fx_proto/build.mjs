// 攻撃の試作（計画52 PR4.5e の見本）を1枚のHTMLにまとめる。本番のバンドルには入らない。
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = path => readFile(join(root, path), 'utf8');
const scripts = ['static/js/fx/fx_core.js', 'static/js/fx/fx_effects.js', 'scripts/fx_proto/proto.js'];
const js = (await Promise.all(scripts.map(read))).join('\n');
const css = await read('static/css/modules/motion_fx.css');
const page = (await read('scripts/fx_proto/page.html'))
  .replace('__MOTION_FX_CSS__', () => css).replace('__FX_SCRIPTS__', () => js);
const out = join(root, '_local', 'fx_proto', 'slash_proto.html');
await mkdir(dirname(out), { recursive: true });
await writeFile(out, page, 'utf8');
console.log(out);
