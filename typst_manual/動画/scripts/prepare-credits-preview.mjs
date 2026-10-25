// リポジトリのルートから: node typst_manual/動画/scripts/prepare-credits-preview.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderCredits } from '../common/credits.mjs';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const common = path.join(video, 'common');
const base = path.join(video, '01_1ラウンドの流れ');
const preview = path.join(video, '_local/credits-preview');
const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
const branding = readJson(path.join(common, 'credits.json'));
const settings = readJson(path.join(base, 'credits.json'));
const section = renderCredits(branding, settings);
fs.mkdirSync(path.join(preview, 'images'), { recursive: true });
fs.cpSync(path.join(base, 'themes'), path.join(preview, 'themes'), { recursive: true });
fs.copyFileSync(path.join(video, '../assets/gemuria_logo.png'), path.join(preview, 'images/gemuria_logo.png'));
fs.copyFileSync(path.join(common, 'credits.css'), path.join(preview, 'credits.css'));
fs.writeFileSync(path.join(preview, 'deck.html'), `<!DOCTYPE html>
<html lang="ja" data-theme="gemuria">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>共通クレジット見本</title>
  <link rel="stylesheet" href="credits.css">
</head>
<body><div id="stage">
${section}
</div></body>
</html>
`);
fs.writeFileSync(path.join(preview, 'timeline.json'), JSON.stringify({ 's-credits:0': { dur: 5, hold: 5, lead: 0, pad_after: 0 } }, null, 2) + '\n');
console.log(`Credits preview: ${preview}`);
