import json
import os
from pathlib import Path
import subprocess

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from flask import Flask

import app as app_module
from manager.summons import loader as summon_loader


@pytest.fixture
def client():
    app = Flask(__name__)
    app_module.register_http_routes(app)
    return app.test_client()


def test_json_builder_is_served_without_login(client):
    response = client.get("/json_builder")
    assert response.status_code == 200
    assert "JSON定義ビルダー（rule_data / v2 strict）" in response.get_data(as_text=True)
    assert "json_builder_reference_data.js" not in response.get_data(as_text=True)
    assert not Path("CharaCreator/json_builder_reference_data.js").exists()


def test_reference_uses_current_masters_and_summon_templates(client, monkeypatch):
    buffs = json.loads(Path("data/cache/buff_catalog_cache.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(app_module, "all_buff_data", buffs, raising=False)
    monkeypatch.setattr(app_module, "all_skill_data", {
        "TEST-SKILL": {"デフォルト名称": "現在のスキル", "tags": ["攻撃"]},
    })
    monkeypatch.setattr(summon_loader, "load_summon_templates", lambda: {
        "TEST-SUMMON": {"name": "現在の召喚", "summon_duration_mode": "permanent", "summon_duration": 0},
    })
    response = client.get("/api/json_builder_reference")
    assert response.status_code == 200
    data = response.get_json()
    assert set(data) == {"buff_refs", "skill_refs", "summon_refs", "state_refs"}
    assert {row["id"] for row in data["buff_refs"]} == set(buffs)
    assert next(row for row in data["buff_refs"] if row["id"] == "Bu-30")["effect"] == buffs["Bu-30"]["effect"]
    assert data["skill_refs"] == [{"id": "TEST-SKILL", "name": "現在のスキル", "tags": ["攻撃"]}]
    assert data["summon_refs"] == [{"id": "TEST-SUMMON", "name": "現在の召喚", "summon_duration_mode": "permanent", "summon_duration": 0}]
    assert data["state_refs"] == ["FP", "HP", "MP", "亀裂", "荊棘", "出血", "戦慄", "速度値", "破裂"]
    buffs["NEW-BUFF"] = {"name": "追加したバフ", "description": "新しい説明", "effect": {}, "default_duration": 2}
    assert next(row for row in client.get("/api/json_builder_reference").get_json()["buff_refs"] if row["id"] == "NEW-BUFF")["name"] == "追加したバフ"


def test_empty_masters_return_empty_reference_lists(client, monkeypatch):
    monkeypatch.setattr(app_module, "all_buff_data", {}, raising=False)
    monkeypatch.setattr(app_module, "all_skill_data", {})
    monkeypatch.setattr(summon_loader, "load_summon_templates", lambda: {})
    data = client.get("/api/json_builder_reference").get_json()
    assert data["buff_refs"] == data["skill_refs"] == data["summon_refs"] == []


def test_builder_waits_for_both_apis_and_stops_on_load_failure():
    script = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const html = fs.readFileSync('CharaCreator/json_definition_builder.html', 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const schemas = {effect_types: {PUBLIC: {internal: false}, PRIVATE: {internal: true}}, custom_effects: {CUSTOM: {description: '説明', fields: {'data.count': {type: 'int'}}}}};
const reference = {buff_refs: [{id: 'CURRENT'}], skill_refs: [], summon_refs: [], state_refs: []};
async function run(failure) {
  const error = {hidden: true, textContent: ''};
  const calls = [];
  const pending = {};
  const context = vm.createContext({document: {getElementById: () => error}, fetch: (url) => new Promise((resolve, reject) => {pending[url] = {resolve, reject};}), console});
  vm.runInContext(script, context);
  for (const name of ['bind','renderHelp','renderPbDocs','renderEffectDocs','initQuickTemplates','initRef','_ensureLinkRefCacheLoaded','addEffectRow','checkDynamicBuffName','setBuilderTab','toggleRefPanel','generate']) {
    context[name] = () => calls.push(name);
  }
  assert.deepEqual(Object.keys(pending).sort(), ['/api/effect_schemas', '/api/json_builder_reference']);
  pending['/api/effect_schemas'].resolve({ok: true, json: async () => schemas});
  await new Promise(setImmediate);
  assert.equal(calls.length, 0);
  if (failure === 'network') pending['/api/json_builder_reference'].reject(new Error('network'));
  else pending['/api/json_builder_reference'].resolve({ok: failure !== 'http', status: 503, json: async () => {
    if (failure === 'json') throw new Error('invalid json');
    return reference;
  }});
  await new Promise(setImmediate);
  if (failure) {
    assert.equal(calls.length, 0);
    assert.equal(error.hidden, false);
    assert.ok(error.textContent.includes('読み込み'));
  } else {
    assert.ok(calls.includes('bind') && calls.includes('generate'));
    assert.equal(vm.runInContext('JSON.stringify(TYPES)', context), '["PUBLIC"]');
    assert.equal(vm.runInContext('REF.buff_refs[0].id', context), 'CURRENT');
    assert.equal(vm.runInContext('CUSTOM_EFFECT_REFS[0].value', context), 'CUSTOM');
    assert.equal(vm.runInContext('CUSTOM_EFFECT_REFS[0].summary', context), '説明');
    assert.equal(vm.runInContext('CUSTOM_EFFECT_REFS[0].keys', context), 'data.count');
  }
}
for (const failure of [null, 'network', 'http', 'json']) await run(failure);
'''
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
