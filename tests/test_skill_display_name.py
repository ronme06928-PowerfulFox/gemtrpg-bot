import json
import subprocess
from pathlib import Path

from manager.battle import duel_log_utils


MASTER = {"E-23": {"デフォルト名称": "根で圧し潰す"}}


def test_log_name_prefers_actor_command_name(monkeypatch):
    monkeypatch.setattr(duel_log_utils, "all_skill_data", MASTER)
    actor = {"commands": "2+1d10+1d{物理補正} 【E-23 何がなんでも】"}
    assert duel_log_utils._resolve_skill_name("E-23", None, actor) == "何がなんでも (E-23)"


def test_log_name_falls_back_to_master_name(monkeypatch):
    monkeypatch.setattr(duel_log_utils, "all_skill_data", MASTER)
    assert duel_log_utils._resolve_skill_name("E-23", None, {"commands": "1d6 【Ps-00 基本の一太刀】"}) == "根で圧し潰す (E-23)"
    assert duel_log_utils._resolve_skill_name("E-23", None, None) == "根で圧し潰す (E-23)"


def _declare_panel_names(actor, skill_id):
    source = Path("static/js/battle/components/DeclarePanel.js").read_text(encoding="utf-8")
    start = source.index("    _resolveSkillDisplayName(")
    end = source.index("    _toggleSideMinimized(")
    methods = source[start:end]
    script = f"""
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
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_declare_panel_label_and_tooltip_use_actor_command_name():
    actor = {"commands": "2+1d10+1d{物理補正} 【E-23 何がなんでも】"}
    assert _declare_panel_names(actor, "E-23") == ["E-23 何がなんでも", "何がなんでも"]


def test_declare_panel_falls_back_to_master_name():
    assert _declare_panel_names({"commands": ""}, "E-23") == ["E-23 根で圧し潰す", "根で圧し潰す"]
