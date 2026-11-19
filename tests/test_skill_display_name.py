import json
import subprocess
from pathlib import Path

from manager.battle import duel_log_utils, resolve_trace_runtime, runtime_actions


MASTER = {"E-23": {"デフォルト名称": "根で圧し潰す"}}


def test_log_name_prefers_actor_command_name(monkeypatch):
    monkeypatch.setattr(duel_log_utils, "all_skill_data", MASTER)
    actor = {"commands": "2+1d10+1d{物理補正} 【E-23 何がなんでも】"}
    assert duel_log_utils._resolve_skill_name("E-23", None, actor) == "何がなんでも (E-23)"


def test_log_name_falls_back_to_master_name(monkeypatch):
    monkeypatch.setattr(duel_log_utils, "all_skill_data", MASTER)
    assert duel_log_utils._resolve_skill_name("E-23", None, {"commands": "1d6 【Ps-00 基本の一太刀】"}) == "根で圧し潰す (E-23)"
    assert duel_log_utils._resolve_skill_name("E-23", None, None) == "根で圧し潰す (E-23)"


def test_custom_name_accepts_space_and_colon_separators():
    commands = "1d6 【Ps-00 基本の一太刀】\n2+1d8 【E-23：何がなんでも】 【E-24: 薙ぎ払い】"
    assert duel_log_utils.skill_name_from_commands({"commands": commands}, "E-23") == "何がなんでも"
    assert duel_log_utils.skill_name_from_commands({"commands": commands}, "E-24") == "薙ぎ払い"
    assert duel_log_utils.skill_name_from_commands({"commands": commands}, "E-2") == ""
    assert runtime_actions.format_skill_name_for_log("E-23", MASTER["E-23"], {"commands": commands}) == "E-23: 何がなんでも"


def test_resolve_popup_uses_actor_command_name(monkeypatch):
    monkeypatch.setattr(resolve_trace_runtime, "all_skill_data", MASTER)
    state = {
        "characters": [
            {"id": "foe", "name": "マンティス", "commands": "2+1d8+1d3 【E-23 何がなんでも】"},
            {"id": "hero", "name": "ツイン", "commands": "1d6 【E-23 別の名前】"},
        ],
        "battle_state": {"slots": {"s1": {"actor_id": "foe"}, "s2": {"actor_id": "hero"}},
                         "intents": {"s1": {"skill_id": "E-23"}, "s2": {"skill_id": "E-23"}}},
    }
    entry = {"kind": "clash", "attacker_actor_id": "foe", "defender_actor_id": "hero",
             "attacker_slot_id": "s1", "defender_slot_id": "s2", "rolls": {"command": "2+1d8+1d3"}}
    popup = resolve_trace_runtime._build_trace_popup_payload(entry, state)
    assert popup["attacker"]["skill_name"] == "何がなんでも"
    assert popup["defender"]["skill_name"] == "別の名前"
    state["characters"][0]["commands"] = ""
    assert resolve_trace_runtime._build_trace_popup_payload(entry, state)["attacker"]["skill_name"] == "根で圧し潰す"


def test_client_custom_name_helper():
    script = r"""
import { skillNameFromCommands } from './static/js/battle/utils/SkillUtils.js';
const commands = '1d6 【Ps-00 基本の一太刀】\n2+1d8 【E-23：何がなんでも】 [E-24 薙ぎ払い]';
process.stdout.write(JSON.stringify(['Ps-00', 'E-23', 'E-24', 'E-2'].map(id => skillNameFromCommands({ commands }, id))));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["基本の一太刀", "何がなんでも", "薙ぎ払い", ""]


def _declare_panel_names(actor, skill_id):
    source = Path("static/js/battle/components/DeclarePanel.js").read_text(encoding="utf-8")
    start = source.index("    _resolveSkillDisplayName(")
    end = source.index("    _toggleSideMinimized(")
    methods = source[start:end]
    script = f"""
import {{ skillNameFromCommands }} from './static/js/battle/utils/SkillUtils.js';
class P {{
{methods}
  _readSkillMeta(id) {{ return {{ name: ({json.dumps(MASTER, ensure_ascii=False)}[id] || {{}})['デフォルト名称'] || id }}; }}
}}
const p = new P();
const actor = {json.dumps(actor, ensure_ascii=False)};
process.stdout.write(JSON.stringify([
  p._resolveSkillDisplayName({json.dumps(skill_id)}, p._readSkillMeta({json.dumps(skill_id)}).name, actor),
  p._skillNameForActor(actor, {json.dumps(skill_id)}),
]));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_declare_panel_label_and_tooltip_use_actor_command_name():
    actor = {"commands": "2+1d10+1d{物理補正} 【E-23 何がなんでも】"}
    assert _declare_panel_names(actor, "E-23") == ["E-23 何がなんでも", "何がなんでも"]


def test_declare_panel_falls_back_to_master_name():
    assert _declare_panel_names({"commands": ""}, "E-23") == ["E-23 根で圧し潰す", "根で圧し潰す"]


def test_declare_detail_command_uses_actor_command_name():
    source = Path("static/js/battle/components/DeclarePanel.js").read_text(encoding="utf-8")
    start = source.index("    _resolveDisplayMeta(")
    end = source.index("    _evaluateCost(")
    script = f"""
import {{ skillNameFromCommands }} from './static/js/battle/utils/SkillUtils.js';
globalThis.window = {{ allSkillData: {{ 'E-00': {{ 'デフォルト名称': '殴る', 'チャットパレット': '2+1d2 【E-00 殴る】' }} }},
  formatSkillDetailHTML: data => data['チャットパレット'] }};
class P {{
{source[start:end]}
  _readSkillMeta(id) {{ return {{ name: '殴る' }}; }}
  _resolveCommandText() {{ return ''; }}
}}
const p = new P();
const foe = {{ commands: '2+1d2 【E-00 番兵の一撃】' }};
process.stdout.write(JSON.stringify([
  p._resolveDisplayMeta('E-00', null, foe).detailHtml,
  p._resolveDisplayMeta('E-00', {{}}, foe).detailHtml,
  p._resolveDisplayMeta('E-00', null, {{ commands: '' }}).detailHtml,
]));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == ["2+1d2 【E-00 番兵の一撃】", "2+1d2 【E-00 番兵の一撃】", "2+1d2 【E-00 殴る】"]
