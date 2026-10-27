import test from 'node:test';
import assert from 'node:assert/strict';
import { effectTime } from './prepare-voice.mjs';
test('SEをcue 0や名前付きmarkから同じ時刻へ置ける', () => {
  assert.ok(Math.abs(effectTime({ cue: 0, offset: 1.32 }, [{ type: 'cue' }], [2]) - 3.32) < 1e-9);
  assert.equal(effectTime({ mark: 'done', offset: -.5 }, [{ id: 'done' }], [3]), 2.5);
  assert.equal(effectTime({ at: 1 }, [], []), 1);
});
test('存在しない同期点や二重指定を黙って先頭へ置かない', () => {
  assert.throws(() => effectTime({ cue: 1 }, [], []));
  assert.throws(() => effectTime({ mark: 'missing' }, [], []));
  assert.throws(() => effectTime({ mark: 'x', cue: 0 }, [{ id: 'x' }], [1]));
});
