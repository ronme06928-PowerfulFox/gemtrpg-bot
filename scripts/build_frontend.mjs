/**
 * フロントエンドのバンドルビルド (esbuild)
 *
 * 出力:
 *   static/dist/app.bundle.js      … クラシック(グローバル共有)スクリプト35本を
 *                                     index.html の読み込み順に連結 + minify
 *   static/dist/battle.bundle.js   … ESモジュール battle/index.js の import ツリーを
 *                                     bundle + minify
 *
 * 連結バンドルはグローバルスコープ共有方式のため、識別子の mangling は無効化し
 * (トップレベル名を壊さない)、空白・構文圧縮のみを行う。
 * battle 側は正規の ES モジュールなので完全圧縮で問題ない。
 *
 * ビルド後、static/index.html の `?v=` を成果物のコンテンツハッシュで書き換える
 * (キャッシュバスティング)。Render は Python 環境で Node を持たないため、
 * 成果物 (static/dist/*) はリポジトリにコミットして運用する。
 */
import { build, transform } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const STATIC = path.join(ROOT, 'static');
const JS = path.join(STATIC, 'js');
const DIST = path.join(STATIC, 'dist');
const INDEX_HTML = path.join(STATIC, 'index.html');

// === クラシックスクリプトの読み込み順（index.html と一致させること） ===
// これがバンドル順序の単一の正。index.html を編集したらここも更新する。
const CLASSIC_SCRIPTS = [
  'js/buff_data.js',
  'js/common/glossary_ui.js',
  'js/sound_fx.js',
  'js/legacy_globals.js',
  'js/action_dock.js',
  'js/exploration/exploration_view.js',
  'js/exploration/exploration_dock.js',
  'js/visual/visual_globals.js',
  'js/visual/visual_arrows.js',
  'js/visual/visual_map.js',
  'js/visual/visual_controls.js',
  'js/visual/visual_ui.js',
  'js/visual/visual_panel.js',
  'js/visual/visual_wide.js',
  'js/visual/visual_socket.js',
  'js/visual/visual_main.js',
  'js/tab_visual_battle.js',
  'js/wide_match_synced.js',
  'js/tab_battlefield.js',
  'js/tab_skill_search.js',
  'js/modals.js',
  'js/modals/behavior_flow_editor_modal.js',
  'js/modals/battle_only_catalog_modal.js',
  'js/modals/battle_only_formation_hub_modal.js',
  'js/modals/battle_only_enemy_formation_modal.js',
  'js/modals/battle_only_ally_formation_modal.js',
  'js/modals/battle_only_stage_preset_modal.js',
  'js/modals/battle_only_draft_modal.js',
  'js/modals/battle_only_quick_start_modal.js',
  'js/modals/battle_only_participant_modal.js',
  'js/modals/room_preset_apply_modal.js',
  'js/image_picker.js',
  'js/item_modal.js',
  'js/user_management.js',
  'js/main.js',
];

const BATTLE_ENTRY = path.join(JS, 'battle', 'index.js');

// import パスに付く `?v=...` クエリを除去して解決する esbuild プラグイン。
// 例: import { timeline } from './components/Timeline.js?v=20260204_2'
const stripQueryPlugin = {
  name: 'strip-import-query',
  setup(b) {
    b.onResolve({ filter: /\?/ }, (args) => {
      const clean = args.path.replace(/\?.*$/, '');
      if (clean.startsWith('.') || clean.startsWith('/')) {
        const resolved = path.resolve(path.dirname(args.importer), clean);
        return { path: resolved };
      }
      return undefined;
    });
  },
};

function shortHash(content) {
  return createHash('sha256').update(content).digest('hex').slice(0, 12);
}

async function buildClassicBundle() {
  const parts = [];
  for (const rel of CLASSIC_SCRIPTS) {
    const abs = path.join(STATIC, rel);
    const src = await readFile(abs, 'utf8');
    // ファイル境界に `;` と改行を挟んで ASI/行コメントの事故を防ぐ
    parts.push(`/* === ${rel} === */\n${src}\n;\n`);
  }
  const concatenated = parts.join('\n');

  const result = await transform(concatenated, {
    loader: 'js',
    minify: true,
    minifyIdentifiers: false, // グローバル名(トップレベル)を壊さないため無効
    minifyWhitespace: true,
    minifySyntax: true,
    legalComments: 'none',
    sourcemap: 'external',
    sourcefile: 'app.bundle.src.js',
  });

  const hash = shortHash(result.code);
  const outJs = path.join(DIST, 'app.bundle.js');
  const codeWithMapRef = `${result.code}\n//# sourceMappingURL=app.bundle.js.map\n`;
  await writeFile(outJs, codeWithMapRef, 'utf8');
  await writeFile(path.join(DIST, 'app.bundle.js.map'), result.map, 'utf8');
  console.log(`[build] app.bundle.js  (${CLASSIC_SCRIPTS.length} files, ${(codeWithMapRef.length / 1024).toFixed(1)} KB, v=${hash})`);
  return hash;
}

async function buildBattleBundle() {
  const outJs = path.join(DIST, 'battle.bundle.js');
  await build({
    entryPoints: [BATTLE_ENTRY],
    bundle: true,
    minify: true,
    format: 'esm',
    target: 'es2019',
    legalComments: 'none',
    sourcemap: true,
    plugins: [stripQueryPlugin],
    outfile: outJs,
  });
  const code = await readFile(outJs, 'utf8');
  const hash = shortHash(code);
  console.log(`[build] battle.bundle.js  (${(code.length / 1024).toFixed(1)} KB, v=${hash})`);
  return hash;
}

async function updateIndexHtmlVersions(appHash, battleHash) {
  let html = await readFile(INDEX_HTML, 'utf8');
  html = html.replace(/dist\/app\.bundle\.js\?v=[^"']*/g, `dist/app.bundle.js?v=${appHash}`);
  html = html.replace(/dist\/battle\.bundle\.js\?v=[^"']*/g, `dist/battle.bundle.js?v=${battleHash}`);
  await writeFile(INDEX_HTML, html, 'utf8');
  console.log(`[build] index.html updated (app v=${appHash}, battle v=${battleHash})`);
}

async function main() {
  await mkdir(DIST, { recursive: true });
  const appHash = await buildClassicBundle();
  const battleHash = await buildBattleBundle();
  await updateIndexHtmlVersions(appHash, battleHash);
  console.log('[build] done.');
}

main().catch((err) => {
  console.error('[build] FAILED:', err);
  process.exit(1);
});
