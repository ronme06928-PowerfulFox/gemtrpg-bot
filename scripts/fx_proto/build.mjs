// 演出の試作（計画52 PR4.5e の攻撃、PR5 の宝石の加護と戦闘の終わり）をそれぞれ1枚のHTMLにまとめる。本番のバンドルには入らない。
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = path => readFile(join(root, path), 'utf8');
const embed = async path => `data:image/png;base64,${(await readFile(join(root, path))).toString('base64')}`;
const scriptsOf = async paths => (await Promise.all(paths.map(read))).join('\n');
const outDir = join(root, '_local', 'fx_proto');
await mkdir(outDir, { recursive: true });

// 置き換えは関数で渡し、中身の「$」を置換の記号として読ませない。
const css = await read('static/css/modules/motion_fx.css');
const attackJs = await scriptsOf(['static/js/fx/fx_core.js', 'static/js/fx/fx_effects.js', 'scripts/fx_proto/proto.js']);
const attack = (await read('scripts/fx_proto/page.html'))
  .replace('__MOTION_FX_CSS__', () => css).replace('__FX_SCRIPTS__', () => attackJs);
const assets = { ally: await embed('static/images/characters/女冒険者.png'), enemy: await embed('static/images/characters/人狼型シュラーカー.png') };
const pr5Js = await scriptsOf(['static/js/fx/fx_core.js', 'static/js/fx/fx_effects.js', 'scripts/fx_proto/pr5.js']);
const pr5 = (await read('scripts/fx_proto/pr5.html'))
  .replace('__MOTION_FX_CSS__', () => css).replace('__FX_SCRIPTS__', () => pr5Js).replace('__ASSETS__', () => JSON.stringify(assets));
for (const [name, html] of [['slash_proto.html', attack], ['pr5_proto.html', pr5]]) {
  const out = join(outDir, name);
  await writeFile(out, html, 'utf8');
  console.log(out);
}
