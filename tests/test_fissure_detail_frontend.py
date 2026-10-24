import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", [
    "grouped", "permanent", "empty", "mismatch", "delay", "invalid", "render",
])
def test_fissure_detail(scenario):
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const context = vm.createContext({window: {}, console});
vm.runInContext(fs.readFileSync('static/js/modals.js', 'utf8'), context);
const bucket = (lasting, count, delay = 0) => ({
  name: `亀裂_R${lasting}`, buff_id: 'Bu-Fissure', lasting, count, delay,
});
const char = (total, buffs = []) => ({
  name: '表示テスト', states: [{name: '亀裂', value: total}], special_buffs: buffs,
  params: [], hp: 30, maxHp: 30, mp: 20, maxMp: 20,
});
const summarize = (c) => JSON.parse(JSON.stringify(context.buildFissureDetailView(c)));
const scenario = process.argv[1];
if (scenario === 'grouped') {
  const c = char(6, [bucket(2, 2), bucket(1, 1), bucket(1, 3)]);
  const before = JSON.stringify(c);
  assert.deepEqual(summarize(c), {total: 6, visible: true, inconsistent: false,
    rows: [{label: '1ラウンド', count: 4}, {label: '2ラウンド', count: 2}]});
  assert.equal(JSON.stringify(c), before);
} else if (scenario === 'permanent') {
  assert.deepEqual(summarize(char(6, [bucket(1, 4)])).rows,
    [{label: '1ラウンド', count: 4}, {label: '期限なし', count: 2}]);
  assert.deepEqual(summarize(char(6)).rows, [{label: '期限なし', count: 6}]);
  assert.equal(summarize(char(6)).visible, true);
} else if (scenario === 'empty') {
  assert.equal(summarize(char(0)).visible, false);
  assert.equal(summarize({}).visible, false);
} else if (scenario === 'mismatch') {
  for (const total of [0, 2]) {
    const view = summarize(char(total, [bucket(1, 4)]));
    assert.equal(view.total, total);
    assert.equal(view.visible, true);
    assert.equal(view.inconsistent, true);
    assert.deepEqual(view.rows, []);
  }
} else if (scenario === 'delay') {
  assert.deepEqual(summarize(char(10, [bucket(2, 1, 2), bucket(2, 2, 1),
    bucket(2, 3), bucket(2, 4, 1)])).rows,
    [{label: '2ラウンド', count: 3},
     {label: '発動まで1ラウンド / 持続2ラウンド', count: 6},
     {label: '発動まで2ラウンド / 持続2ラウンド', count: 1}]);
  assert.equal(summarize(char('3', [bucket('2', '3', '0')])).inconsistent, false);
} else if (scenario === 'invalid') {
  for (const b of [bucket(0, 1), bucket(2, -1), bucket(2, 1, -1), bucket('bad', 1)]) {
    assert.equal(summarize(char(6, [b])).inconsistent, true);
  }
} else if (scenario === 'render') {
  context.markupToHtml = text => text;
  const c = char(6, [bucket(1, 4), bucket(2, 2),
    {name: '別のバフ', lasting: 3, count: 2, description: '別の効果'}]);
  const html = context.renderCharacterCard(c);
  assert.equal((html.match(/data-fissure-detail/g) || []).length, 1);
  assert.ok(html.includes('6重'));
  assert.ok(html.includes('4重'));
  assert.ok(html.includes('2重'));
  assert.ok(html.includes('亀裂: 6'));
  assert.ok(!html.includes('亀裂_R'));
  assert.ok(html.includes('別のバフ'));
  assert.ok(html.includes('残り3R'));
  assert.ok(html.includes('残2回'));
  const fissureHtml = context.renderFissureDetail(context.buildFissureDetailView(c));
  assert.ok(!fissureHtml.includes('buff-duration-badge'));
  assert.ok(!fissureHtml.includes('残6回'));
  assert.ok(!fissureHtml.includes('src:'));
  assert.ok(!fissureHtml.includes('<details class="buff-accordion" data-fissure-detail open'));
  const invalidHtml = context.renderFissureDetail(context.buildFissureDetailView(char(2, [bucket(1, 4)])));
  assert.ok(invalidHtml.includes('残りラウンドの内訳を確認できません'));
  assert.ok(!invalidHtml.includes('<table'));
}
"""
    result = subprocess.run(
        ["node", "-e", script, scenario], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
