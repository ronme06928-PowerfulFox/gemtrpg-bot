import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { sample } from './r1-resolve-sample.mjs';
import { prototypeTime, stages } from './r1-resolve-time.mjs';

test('計画53の9対6・9ダメージ・勝利FP1だけを使う', () => {
  assert.equal(sample.step.attackerSkillId, 'Ps-00');
  assert.equal(sample.step.defenderSkillId, 'Ps-00');
  assert.deepEqual([sample.step.rolls.power_a, sample.step.rolls.power_b], [9, 6]);
  assert.deepEqual(sample.step.applied.damage, [{ target_id: 'd', hp: 9, hp_after: 21, source: 'dice' }]);
  assert.equal(sample.after.allyFp, 1);
  assert.equal(sample.after.enemyHp, 21);
});

test('本番の段階の速さを保ち、余白時間とInfinityは段階末尾で止まる', () => {
  assert.deepEqual(stages.map((s) => s.seconds), [.5, 1.2, .7, 2.2]);
  for (let k = 1; k <= 4; k++) {
    const row = stages[k - 1];
    assert.equal(prototypeTime(k, .1).time, row.start + .1);
    assert.deepEqual(prototypeTime(k, 100), prototypeTime(k, Infinity));
    assert.ok(prototypeTime(k, Infinity).time < row.start + row.seconds);
  }
  assert.equal(prototypeTime(0, 0).board, 'before');
  assert.equal(prototypeTime(5, 0).board, 'after');
});

test('本番の描画・Fx・舞台の依存を組めて、アプリ専用の時計を含めない', async () => {
  const skill = JSON.parse(fs.readFileSync('data/cache/skills_cache.json', 'utf8'))['Ps-00'];
  assert.equal(skill['属性'], '斬撃');
  const bundled = await build({ entryPoints: [fileURLToPath(new URL('./r1-resolve-runtime.mjs', import.meta.url))],
    bundle: true, write: false, format: 'iife', metafile: true, define: { __R1_SKILL__: JSON.stringify(skill) } });
  const inputs = Object.keys(bundled.metafile.inputs).map(name => name.replaceAll('\\', '/'));
  for (const name of ['ResolveFlowPanel.js', 'resolve_stage.js', 'resolve_stage_layout.js', 'resolve_stage_motion.js', 'fx_core.js', 'fx_effects.js']) {
    assert.ok(inputs.some(file => file.endsWith('/' + name)), name);
  }
  assert.ok(!inputs.some(file => file.endsWith('/fx_player.js')));
});
