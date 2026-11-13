// PR60-24 の試作：効果から作った文章を読み取りに通し、元の効果に戻るかを数える（本番には入らない）。
// 使い方：node scripts/catalog_preview/pr24/measure.mjs [--list]
import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const root = fileURLToPath(new URL('../../../', import.meta.url));
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
for (const file of ['static/js/master_data/json.js', 'static/js/master_data/glossary.js', 'static/js/master_data/skill_text_help.js',
  'static/js/master_data/skill_notes.js', 'static/js/master_data/skill_text.js', 'scripts/catalog_preview/pr24/writer.js']) {
  vm.runInContext(readFileSync(path.join(root, file), 'utf8'), context);
}
// 画面（workspace.js の prepareSkill）と同じ参照データを渡す。
const list = kind => data.lists[kind].entries;
const references = {
  buff_refs: list('buff').map(row => ({ id: row.entry_id, name: row.payload.name })),
  glossary_refs: list('glossary').map(row => ({ id: row.entry_id, ...row.payload })),
  skill_refs: list('skill').map(row => ({ id: row.entry_id, name: row.payload.デフォルト名称 })),
  summon_refs: list('summon').filter(row => !row.deprecated).map(row => ({ id: row.entry_id, ...row.payload })),
  ...data.text_references,
};
const reader = window.CatalogSkillText.createReader(references);
const writer = window.CatalogSkillWriter.create(references);

// 比べ方は scripts/catalog_text_roundtrip.mjs と同じ。
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
    if (row.target === 'target') delete row.target;
    if (row.type === 'USE_SKILL_AGAIN' && row.max_reuses === 1) delete row.max_reuses;
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
  // 戦闘はタイミングごとに効果を処理する。同じタイミングの順序は保つ。
  copy.effects.sort((a, b) => String(a.timing).localeCompare(String(b.timing)));
  copy.power_bonus = (copy.power_bonus || []).map(bonus => {
    const row = { ...bonus };
    row.operation = row.operation ?? row.operator ?? 'FIXED';
    delete row.operator;
    const condition = row.condition;
    if (row.operation === 'FIXED_IF_EXISTS' && !condition && row.source && row.param) {
      row.condition = {source: row.source, param: row.param, operator: 'GTE', value: row.threshold ?? 1};
      row.operation = 'FIXED';
      delete row.source;
      delete row.param;
      delete row.threshold;
    }
    if (row.threshold === 1) delete row.threshold;
    if (row.apply_to === 'base') delete row.apply_to;
    return row;
  });
  if (copy.tags) copy.tags.sort();
  return { rule: copy, blanks };
}

const rows = data.lists.skill.entries.filter(row => !row.deprecated);
const out = { roundtrip: [], unknown: [], differ: [], error: [] };
const unknownTypes = new Map();
for (const row of rows) {
  const payload = row.payload, rule = payload.特記処理 || {};
  const made = writer.write(payload);
  if (made.unknown.length) {
    out.unknown.push(row.entry_id);
    for (const item of made.unknown) { const key = item.type ? (item.type === 'CUSTOM_EFFECT' ? `CUSTOM_EFFECT:${item.value}` : item.type) : `power_bonus:${item.operation || item.operator}`; unknownTypes.set(key, (unknownTypes.get(key) || 0) + 1); }
    continue;
  }
  const parsed = reader.parse({ category: payload.分類, cost: made.コスト, trigger: made.発動時効果, note: made.特記,
    tags: (rule.tags || []).join(','), id: rule.id, target_scope: rule.target_scope });
  if (parsed.errors?.length) out.error.push({ id: row.entry_id, made, reasons: parsed.errors.map(e => `${e.column}「${e.line}」${e.reason}`) });
  else if (same(meaning(rule).rule, meaning(parsed.rule).rule)) out.roundtrip.push(row.entry_id);
  else out.differ.push({ id: row.entry_id, made, stored: meaning(rule).rule, read: meaning(parsed.rule).rule });
}
console.log(`公開中のスキル ${rows.length}件`);
console.log(`- 作った文章を読み取ると元の効果に戻る：${out.roundtrip.length}件`);
console.log(`- 文にできない効果がある：${out.unknown.length}件`);
console.log(`- 作った文章を読み取ると違う効果になる：${out.differ.length}件`);
console.log(`- 作った文章を読み取れない：${out.error.length}件`);
console.log('\n文にできない効果（数）');
for (const [key, n] of [...unknownTypes].sort((a, b) => b[1] - a[1])) console.log(`  ${key}: ${n}`);
if (process.argv.includes('--list')) {
  for (const item of out.error) console.log(`\n[読めない] ${item.id}\n  ${JSON.stringify({コスト: item.made.コスト, 発動: item.made.発動時効果, 特記: item.made.特記})}\n  ${item.reasons.join(' / ')}`);
  for (const item of out.differ) console.log(`\n[違う] ${item.id}\n  ${JSON.stringify({コスト: item.made.コスト, 発動: item.made.発動時効果, 特記: item.made.特記})}\n  保存 ${JSON.stringify(item.stored.effects)} ${JSON.stringify(item.stored.power_bonus)}\n  読取 ${JSON.stringify(item.read.effects)} ${JSON.stringify(item.read.power_bonus)}`);
}
