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
const reader = window.CatalogSkillText.createReader(data.text_references);

// キーの並び、値が無いのと空の配列・空のオブジェクトの違いをそろえて比べる。
// target_scope は文章からではなく画面からの引き渡しで決まるので比べない。
const empty = value => value === undefined || (Array.isArray(value) && !value.length) || (value && typeof value === 'object' && !Array.isArray(value) && !Object.keys(value).length);
function normal(value) {
  if (Array.isArray(value)) return value.map(normal);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().filter(key => key !== 'target_scope' && !empty(value[key])).map(key => [key, normal(value[key])]));
  }
  return value;
}
const same = (a, b) => JSON.stringify(normal(a)) === JSON.stringify(normal(b));

// 書き方が違うだけで、戦闘での意味が同じものをそろえる（既定の値・重なった項目・説明だけの項目）。
// 文章の読み取りが空の文章から作る中身のない効果も、ここで落として別に数える。
function meaning(rule) {
  const copy = JSON.parse(JSON.stringify(rule || {}));
  const blank = effect => effect?.type === 'APPLY_STATE' && effect.state_name === undefined && effect.value === undefined;
  const blanks = (copy.effects || []).filter(blank).length;
  copy.effects = (copy.effects || []).filter(effect => !blank(effect)).map(effect => {
    const row = { ...effect };
    if (row.stat === row.state_name) delete row.stat;
    delete row.flavor;
    if (row.timing === 'IMMEDIATE') row.timing = 'PRE_MATCH';
    if (row.type === 'CUSTOM_EFFECT' && row.target === 'target') delete row.target;
    if (row.delay === 0) delete row.delay;
    if (row.lasting === -1) delete row.lasting;
    if (row.data && typeof row.data === 'object') {
      row.data = { ...row.data };
      if (row.data.count !== undefined && row.count === undefined) { row.count = row.data.count; delete row.data.count; }
      if (row.data.buff_id === row.buff_id) delete row.data.buff_id;
      delete row.data.display_name;
    }
    return row;
  });
  copy.power_bonus = (copy.power_bonus || []).map(bonus => {
    const row = { ...bonus };
    if (row.threshold === 1) delete row.threshold;
    if (row.apply_to === 'base') delete row.apply_to;
    return row;
  });
  return { rule: copy, blanks };
}

function differences(stored, made) {
  const out = [];
  for (const key of new Set([...Object.keys(stored || {}), ...Object.keys(made || {})])) {
    if (key === 'effects' || key === 'target_scope') continue;
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
let blankSkills = 0;
const kinds = new Map(), types = new Map(), timings = new Map(), conditions = { with: 0, without: 0 };
for (const row of rows) {
  const payload = row.payload, rule = payload.特記処理 || {};
  for (const effect of rule.effects || []) {
    types.set(effect.type === 'CUSTOM_EFFECT' ? `CUSTOM_EFFECT:${effect.value}` : effect.type, (types.get(effect.type === 'CUSTOM_EFFECT' ? `CUSTOM_EFFECT:${effect.value}` : effect.type) || 0) + 1);
    timings.set(effect.timing, (timings.get(effect.timing) || 0) + 1);
    conditions[effect.condition ? 'with' : 'without']++;
  }
  const parsed = reader.parse({ category: payload.分類, cost: payload.コスト, trigger: payload.発動時効果, note: payload.特記,
    tags: (rule.tags || []).join(','), id: rule.id, target_scope: rule.target_scope });
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
// --check：例外のスキル（今の言い回しで書けない文がある）を除き、意味が違う・読み取れないものがあれば失敗で終わる。
const EXCEPTIONS = new Set(['E-14', 'E-33', 'E-34', 'E-35', 'E-06']);
if (process.argv.includes('--check')) {
  const failed = [...result.differ, ...result.error].map(item => item.id).filter(id => !EXCEPTIONS.has(id));
  if (failed.length) {
    console.error(`\n往復の確かめに失敗：${failed.join(', ')}`);
    process.exit(1);
  }
  console.log(`\n往復の確かめ：例外（${[...EXCEPTIONS].join('・')}）を除き、すべて意味が同じ`);
}
