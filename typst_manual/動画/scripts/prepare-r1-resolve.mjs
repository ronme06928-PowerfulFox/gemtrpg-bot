// 本編を変更せず、本番ソースの依存グラフを写してから音声なし試作を組む。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { extractResolvePanelCss, GALLERY_PANEL_SELECTOR } from '../../../scripts/fx_gallery/panel_css.mjs';
import { sharedImageCss, shareSceneImages } from '../common/shared-images.mjs';
import { holds } from './r1-resolve-time.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const video = path.join(root, 'typst_manual/動画');
const output = path.join(video, '_local/r1-resolve');
const snapshot = path.join(output, 'vendor/repo');
const engine = process.argv[2] || 'C:/Users/yharu/tools/egatari-studio-0.6.3';
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const skill = JSON.parse(read('data/cache/skills_cache.json'))['Ps-00'];
assert.equal(skill['デフォルト名称'], '基本の一太刀');
const entry = 'typst_manual/動画/scripts/r1-resolve-runtime.mjs';
const options = { bundle: true, write: false, format: 'iife', target: 'es2020', charset: 'utf8', metafile: true,
  minifyWhitespace: true, minifySyntax: true, minifyIdentifiers: false, define: { __R1_SKILL__: JSON.stringify(skill) } };
const scan = await build({ ...options, absWorkingDir: root, entryPoints: [entry] });
const sources = [...new Set([...Object.keys(scan.metafile.inputs).filter(name => !name.startsWith('<')),
  'static/css/modules/visual_battle.css', 'static/css/modules/motion_fx.css', 'scripts/fx_gallery/panel_css.mjs'])].sort();
assert.ok(!sources.some(name => name.endsWith('/fx_player.js')), 'アプリの時計は写さない');
const copies = [];
for (const relative of sources) {
  assert.ok(!relative.startsWith('..') && !path.isAbsolute(relative));
  const bytes = fs.readFileSync(path.join(root, relative));
  const target = path.join(snapshot, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, bytes);
  copies.push({ path: relative, sha256: hash(bytes), bytes: bytes.length });
}
const bundled = await build({ ...options, absWorkingDir: snapshot, entryPoints: [entry] });
const reference = await build({ ...options, absWorkingDir: root, entryPoints: ['typst_manual/動画/scripts/r1-resolve-reference.mjs'] });
const gallery = await build({ ...options, absWorkingDir: root, entryPoints: ['typst_manual/動画/scripts/r1-resolve-gallery.mjs'],
  define: { ...options.define, __GALLERY_SKILLS__: JSON.stringify({ 'Ps-00': skill }) } });
const panelCss = extractResolvePanelCss(fs.readFileSync(path.join(snapshot, 'static/css/modules/visual_battle.css'), 'utf8'));
assert.ok(panelCss.includes('.resolve-stage-canvas') && panelCss.includes('.resolve-flow-overlay'));
fs.mkdirSync(path.join(output, 'components/resolve-prototype'), { recursive: true });
fs.writeFileSync(path.join(output, 'components/resolve-prototype/index.js'), bundled.outputFiles[0].text);
fs.writeFileSync(path.join(output, 'reference-component.js'), reference.outputFiles[0].text);
for (const name of ['app_mock.css', 'motion.css', 'round-v2.css']) fs.copyFileSync(path.join(video, '01_1ラウンドの流れ', name), path.join(output, name));
fs.mkdirSync(path.join(output, 'images'), { recursive: true });
for (const name of ['ruins', 'ally', 'enemy']) fs.copyFileSync(path.join(video, 'common/assets/video', `${name}.webp`), path.join(output, 'images', `${name}.webp`));
fs.writeFileSync(path.join(output, 'shared-images.css'), sharedImageCss({ ruins: 'images/ruins.webp', ally: 'images/ally.webp', enemy: 'images/enemy.webp' }));
fs.writeFileSync(path.join(output, 'panel.css'), panelCss + '\n' + fs.readFileSync(path.join(snapshot, 'static/css/modules/motion_fx.css'), 'utf8').replaceAll('#resolve-flow-panel', GALLERY_PANEL_SELECTOR));
fs.copyFileSync(path.join(video, 'scripts/r1-resolve.css'), path.join(output, 'prototype.css'));
const { parse, parseFragment, serialize } = await import(pathToFileURL(createRequire(path.join(engine, 'package.json')).resolve('parse5')));
const find = (node, match) => match(node) ? node : (node.childNodes || []).map(child => find(child, match)).find(Boolean);
const attr = (node, name) => node.attrs?.find(item => item.name === name);
const hasClass = (node, name) => attr(node, 'class')?.value.split(/\s+/).includes(name);
const section = find(parse(read('typst_manual/動画/01_1ラウンドの流れ/deck.html')), node => attr(node, 'id')?.value === 's-selection');
const boardSource = serialize(find(section, node => hasClass(node, 's1-board')));
const board = (after = false) => {
  const tree = parseFragment(boardSource);
  if (after) {
    const ally = find(tree, node => hasClass(node, 'app-piece') && hasClass(node, 'ally'));
    const enemy = find(tree, node => hasClass(node, 'app-piece') && hasClass(node, 'enemy'));
    const setText = (node, value) => { node.childNodes = [{ nodeName: '#text', value: String(value), parentNode: node }]; };
    setText(find(ally, node => hasClass(node, 'app-fp')), 1);
    setText(find(enemy, node => hasClass(node, 'app-stat-value')), 21);
    attr(find(enemy, node => hasClass(node, 'hp')), 'style').value = 'width:70%';
    for (const actor of [ally, enemy]) {
      const slot = find(actor, node => hasClass(node, 'v2-slot'));
      attr(slot, 'class').value += ' is-spent';
      slot.childNodes.push(...parseFragment('<span class="v2-spent">行動済み</span>').childNodes);
    }
    tree.childNodes = tree.childNodes.filter(node => !hasClass(node, 'v2-arrows') && !hasClass(node, 'v2-skill'));
  }
  return `<div class="r1-board s1-slide v2-slide" data-board="${after ? 'after' : 'before'}"><div class="r1-board-bg video-shared-image" data-video-image="ruins" role="img" aria-label="遺跡"></div><div class="s1-board">${shareSceneImages(serialize(tree))}</div></div>`;
};
const html = `<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>R1 解決パネル試作</title>${['app_mock.css', 'motion.css', 'round-v2.css', 'shared-images.css', 'panel.css', 'prototype.css'].map(file => `<link rel="stylesheet" href="${file}">`).join('')}</head><body><div id="stage"><section class="slide r1-slide noconcl" id="s-prototype"><h2>解決パネルの試作</h2><m-resolve-prototype steps="5"><div class="r1-world">${board()}${board(true)}</div></m-resolve-prototype></section></div></body></html>\n`;
fs.writeFileSync(path.join(output, 'deck.html'), html);
fs.writeFileSync(path.join(output, 'timeline.json'), JSON.stringify(Object.fromEntries(holds.map((dur, k) => [`s-prototype:${k}`, { dur, hold: dur }])), null, 2) + '\n');
const nativeInputs = Object.keys(bundled.metafile.inputs).filter(name => name.startsWith('static/'));
for (const name of ['ResolveFlowPanel.js', 'resolve_stage.js', 'resolve_stage_motion.js', 'resolve_stage_layout.js', 'fx_core.js', 'fx_effects.js']) assert.ok(nativeInputs.some(file => file.endsWith('/' + name)), `必須ソースがbundleにない: ${name}`);
fs.writeFileSync(path.join(output, 'copy-manifest.json'), JSON.stringify({ copies, nativeInputs, skill }, null, 2) + '\n');
const runBuild = () => {
  const result = spawnSync(process.execPath, [path.join(engine, 'kit/build.mjs'), path.join(output, 'deck.html')], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  assert.equal(result.status, 0, result.stderr); console.log(result.stdout.trim());
};
runBuild();
fs.copyFileSync(path.join(output, 'out/deck.html'), path.join(output, 'out/r1-resolve-latest.html'));
fs.writeFileSync(path.join(output, 'components/resolve-prototype/index.js'), reference.outputFiles[0].text);
runBuild();
fs.copyFileSync(path.join(output, 'out/deck.html'), path.join(output, 'out/r1-native-reference.html'));
fs.writeFileSync(path.join(output, 'components/resolve-prototype/index.js'), gallery.outputFiles[0].text);
runBuild();
fs.copyFileSync(path.join(output, 'out/deck.html'), path.join(output, 'out/r1-gallery-reference.html'));
fs.writeFileSync(path.join(output, 'components/resolve-prototype/index.js'), bundled.outputFiles[0].text);
console.log(`R1: ${copies.length} source files copied, ${nativeInputs.length} native modules, ${output}`);
