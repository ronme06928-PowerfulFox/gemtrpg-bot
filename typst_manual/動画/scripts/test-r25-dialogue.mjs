import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { parseNarration } from 'file:///C:/Users/yharu/tools/egatari-studio-0.6.3/kit/core/narration-core.mjs';
import { sceneAt, voices } from './r25-dialogue-data.mjs';

test('2人を別の声へ割り当て、質問2つ以外のルール説明はExpertへ置く', () => {
  const rows = parseNarration(fs.readFileSync('typst_manual/動画/r25-dialogue/narration.md','utf8'));
  assert.equal(rows.length,8);
  assert.ok(rows.every(r=>r.turns.length===1));
  assert.deepEqual(rows.filter(r=>r.turns[0].role==='novice').map(r=>+r.stepKey),[2,6]);
  assert.notEqual(voices.expert.id, voices.novice.id);
  assert.ok(!rows.some(r=>/出目.*[23]と[13]/.test(r.turns[0].tts)));
});
test('説明中は本番末尾を保持し、演出だけ等倍で進める', () => {
  assert.equal(sceneAt(1,.3).time,.8);
  assert.equal(sceneAt(3,0).time,sceneAt(3,50).time);
  assert.equal(sceneAt(8,.3).time,2);
  assert.equal(sceneAt(9,.4).time,2.8);
  assert.ok(sceneAt(11,50).time<4.6);
  assert.equal(sceneAt(3,2).zoom,'ally');
  assert.equal(sceneAt(5,2).zoom,'enemy');
});
