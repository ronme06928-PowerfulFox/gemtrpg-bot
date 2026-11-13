// スキルの文章と効果の設定が、どれだけ「決まった言い回し」で対応しているかを数える（計画60 §5.16 の1）。
// 使い方：node scripts/catalog_text_roundtrip.mjs [--list] [--check]
// 公開中の138件の文章（コスト・発動時効果・特記・タグ）を「文章から効果を作る」の読み取りにかけ、
// 保存されている特記処理と同じになるかを比べる。同じなら、その文章は読み取りの言い回しどおりに書かれている。
import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const root = fileURLToPath(new URL('../', import.meta.url));
const localPython = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const python = process.env.PYTHON || (existsSync(localPython) ? localPython : 'python');
const exported = spawnSync(python, [path.join(root, 'scripts/catalog_preview/export_api.py')], {
  cwd: root, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
});
if (exported.status !== 0) throw new Error(`API の書き出しに失敗: ${exported.stderr || exported.error}`);
const data = JSON.parse(exported.stdout);

const window = {};
const context = vm.createContext({ window, console });
context.catalogNoCorrectionNotes = JSON.parse(readFileSync(path.join(root, 'data/skill_no_correction_notes.json'), 'utf8'));
for (const name of ['json', 'glossary', 'skill_text_help', 'skill_notes', 'skill_text']) {
  vm.runInContext(readFileSync(path.join(root, `static/js/master_data/${name}.js`), 'utf8'), context);
}
// 画面（static/js/master_data/workspace.js の prepareSkill）と同じ参照データを渡す。
const list = kind => data.lists[kind].entries;
const references = {
  buff_refs: list('buff').map(row => ({ id: row.entry_id, name: row.payload.name })),
  glossary_refs: list('glossary').map(row => ({ id: row.entry_id, ...row.payload })),
  skill_refs: list('skill').map(row => ({ id: row.entry_id, name: row.payload.デフォルト名称 })),
  summon_refs: list('summon').filter(row => !row.deprecated).map(row => ({ id: row.entry_id, ...row.payload })),
  ...data.text_references,
};
const reader = window.CatalogSkillText.createReader(references);

const { empty, same, meaning, sameMeaning, readPayload } = window.CatalogSkillText;
const writer = window.CatalogSkillText.createWriter(references);

function differences(stored, made) {
  const out = [];
  for (const key of new Set([...Object.keys(stored || {}), ...Object.keys(made || {})])) {
    if (key === 'effects' || key === 'target_scope' || (empty(stored?.[key]) && empty(made?.[key]))) continue;
    if (!same(stored?.[key], made?.[key])) out.push(key);
  }
  const a = stored?.effects || [], b = made?.effects || [];
  if (a.length !== b.length) out.push(`effects件数 ${a.length}→${b.length}`);
  else a.forEach((row, index) => {
    const keys = [...new Set([...Object.keys(row || {}), ...Object.keys(b[index] || {})])].filter(key => !same(row?.[key], b[index]?.[key]));
    if (keys.length) out.push(`effects[${index}].${keys.join('/')}`);
  });
  return out;
}

const rows = data.lists.skill.entries.filter(row => !row.deprecated).sort((a, b) => a.entry_id.localeCompare(b.entry_id, 'en', { numeric: true }));
const result = { same: [], alike: [], differ: [], error: [] };
const written = { roundtrip: [], unknown: [], differ: [], error: [] };
let blankSkills = 0;
const kinds = new Map(), types = new Map(), timings = new Map(), conditions = { with: 0, without: 0 };
for (const row of rows) {
  const payload = row.payload, rule = payload.特記処理 || {};
  for (const effect of rule.effects || []) {
    types.set(effect.type === 'CUSTOM_EFFECT' ? `CUSTOM_EFFECT:${effect.value}` : effect.type, (types.get(effect.type === 'CUSTOM_EFFECT' ? `CUSTOM_EFFECT:${effect.value}` : effect.type) || 0) + 1);
    timings.set(effect.timing, (timings.get(effect.timing) || 0) + 1);
    conditions[effect.condition ? 'with' : 'without']++;
  }
  const parsed = readPayload(reader, payload);
  const madeText = writer.write(payload);
  const reread = readPayload(reader, payload, madeText);
  if (madeText.unknown.length) written.unknown.push({id:row.entry_id, details:madeText.unknown});
  else if (reread.errors.length) written.error.push({id:row.entry_id, details:reread.errors});
  else if (sameMeaning(rule, reread.rule)) written.roundtrip.push(row.entry_id);
  else written.differ.push({id:row.entry_id, details:{stored:meaning(rule).rule, read:meaning(reread.rule).rule, text:madeText}});
  if (parsed.errors?.length) {
    result.error.push({ id: row.entry_id, reasons: parsed.errors.map(error => `${error.column}「${error.line}」${error.reason}`) });
    for (const error of parsed.errors) kinds.set(error.reason, (kinds.get(error.reason) || 0) + 1);
  } else if (same(rule, parsed.rule)) result.same.push(row.entry_id);
  else {
    const stored = meaning(rule), made = meaning(parsed.rule);
    if (made.blanks) blankSkills++;
    if (same(stored.rule, made.rule)) result.alike.push(row.entry_id);
    else result.differ.push({ id: row.entry_id, keys: differences(stored.rule, made.rule) });
  }
}

const top = map => [...map].sort((a, b) => b[1] - a[1]);
console.log(`公開中のスキル ${rows.length}件`);
console.log(`- 文章を読み取ると保存中の効果と同じ：${result.same.length}件`);
console.log(`- 書き方が違うだけで意味は同じ：${result.alike.length}件（空の文章から中身のない効果を作るもの ${blankSkills}件を含む）`);
console.log(`- 意味が違う：${result.differ.length}件`);
console.log(`- 読み取れない行がある：${result.error.length}件`);
const diffKeys = new Map();
for (const item of result.differ) for (const key of item.keys) { const k = key.replace(/\[\d+\]/, '[n]'); diffKeys.set(k, (diffKeys.get(k) || 0) + 1); }
console.log('\n意味が違う所（件数）');
for (const [key, count] of top(diffKeys)) console.log(`  ${key}: ${count}`);
console.log('\n読み取れない理由（行数）');
for (const [key, count] of top(kinds)) console.log(`  ${key}: ${count}`);
console.log('\n効果タイプ（効果の数）');
for (const [key, count] of top(types)) console.log(`  ${key}: ${count}`);
console.log('\nタイミング（効果の数）');
for (const [key, count] of top(timings)) console.log(`  ${key}: ${count}`);
console.log(`\n条件つきの効果：${conditions.with} ／ 条件なし：${conditions.without}`);
if (process.argv.includes('--list')) {
  console.log('\n--- 効果が違うスキル ---');
  for (const item of result.differ) console.log(`${item.id}: ${item.keys.join(', ')}`);
  console.log('\n--- 読み取れないスキル ---');
  for (const item of result.error) console.log(`${item.id}: ${item.reasons.join(' / ')}`);
}
console.log('\n文章を作る側の往復');
console.log('- 作った文章を読み取ると元の効果に戻る：' + written.roundtrip.length + '件');
console.log('- 文にできない効果がある：' + written.unknown.length + '件');
console.log('- 作った文章を読み取ると違う効果になる：' + written.differ.length + '件');
console.log('- 作った文章を読み取れない：' + written.error.length + '件');
if (process.argv.includes('--list')) {
  for (const [label,items] of [['文にできない',written.unknown],['違う',written.differ],['読めない',written.error]]) {
    for (const item of items) console.log('[' + label + '] ' + item.id + ': ' + JSON.stringify(item.details));
  }
}
// --check：例外のスキル（今の言い回しで書けない文がある）を除き、意味が違う・読み取れないものがあれば失敗で終わる。
const EXCEPTIONS = new Set(['E-14', 'E-33', 'E-34', 'E-35', 'E-06']);
if (process.argv.includes('--check')) {
  const failed = [...result.differ, ...result.error, ...written.unknown, ...written.differ, ...written.error].map(item => item.id).filter(id => !EXCEPTIONS.has(id));
  if (failed.length) {
    console.error(`\n往復の確かめに失敗：${failed.join(', ')}`);
    process.exit(1);
  }
  console.log(`\n往復の確かめ：例外（${[...EXCEPTIONS].join('・')}）を除き、すべて意味が同じ`);
}
