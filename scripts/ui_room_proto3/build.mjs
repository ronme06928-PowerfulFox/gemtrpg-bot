// ルームの試作 第3回（UI計画 §7.4 論点7・8・9）を /_local/ui_room_proto3/ に作る。本番のバンドルには入らない。
import { copyFileSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const here = join(root, 'scripts', 'ui_room_proto3');
const out = join(root, '_local', 'ui_room_proto3');
rmSync(out, { recursive: true, force: true });
mkdirSync(join(out, 'images'), { recursive: true });
copyFileSync(join(here, 'page.html'), join(out, 'index.html'));
for (const name of ['marble.css', 'setting.css']) copyFileSync(join(here, name), join(out, name));
copyFileSync(join(root, 'static', 'css', 'modules', 'common_ui.css'), join(out, 'common_ui.css'));
const images = {
  'bg.png': 'backgrounds/暗い遺跡洞窟.png',
  'ally1.png': 'characters/男冒険者.png',
  'ally2.png': 'characters/女冒険者.png',
  'enemy1.png': 'characters/人狼型シュラーカー.png',
  'enemy2.png': 'characters/小人型シュラーカー.png',
};
for (const [to, from] of Object.entries(images)) copyFileSync(join(root, 'static', 'images', from), join(out, 'images', to));
console.log('wrote', join(out, 'index.html'));
