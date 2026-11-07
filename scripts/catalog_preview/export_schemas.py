"""Export the real effect schemas and skill summaries for the static UI study."""
import contextlib
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

with contextlib.redirect_stdout(sys.stderr):
    from manager.battle.effect_handlers import EFFECT_SCHEMAS, render_effect_summary
    from manager.json_rule_v2 import extract_and_normalize_skill_rule_data
    from plugins import CUSTOM_EFFECT_SCHEMAS

    skills = json.loads((ROOT / "data/cache/skills_cache.json").read_text(encoding="utf-8"))
    exported = {}
    for skill_id, skill in skills.items():
        rule = extract_and_normalize_skill_rule_data(skill, strict=True)
        exported[skill_id] = {
            "rule": rule,
            "summaries": [render_effect_summary(effect) for effect in rule.get("effects", [])],
        }
    draft = copy.deepcopy(exported["Pb-13"]["rule"])
    draft["effects"][0]["value"] += 1
    draft_summaries = [render_effect_summary(effect) for effect in draft["effects"]]

json.dump({
    "effect_types": EFFECT_SCHEMAS,
    "custom_effects": CUSTOM_EFFECT_SCHEMAS,
    "skills": exported,
    "dash_draft": {"rule": draft, "summaries": draft_summaries},
}, sys.stdout, ensure_ascii=False)
sys.stdout.write("\n")
