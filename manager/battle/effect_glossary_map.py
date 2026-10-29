"""効果の識別子だけを管理する。表示名の正本は用語図鑑。"""
import extensions


CUSTOM_EFFECT_TERMS = {
    "出血氾濫": "W-01", "破裂爆発": "W-03",
    "亀裂崩壊_DAMAGE": "W-05", "FISSURE_COLLAPSE": "W-05",
    "戦慄殺到": "W-07", "荊棘飛散": "W-09",
}


def effect_term(effect, converted_resource=None):
    kind = effect.get("type", "CUSTOM_EFFECT")
    term_id = CUSTOM_EFFECT_TERMS.get(effect.get("value")) if kind == "CUSTOM_EFFECT" else None
    if kind == "USE_SKILL_AGAIN":
        term_id = "W-58"
    elif kind == "CONVERT_STACK_RESOURCE_VARIANT" and isinstance(converted_resource, dict):
        resource_id = converted_resource.get("buff_id") or (converted_resource.get("data") or {}).get("buff_id")
        resource_name = str(converted_resource.get("name") or "")
        if resource_id == "Bu-31" or "gyoma" in resource_name.lower() or "凝魔" in resource_name:
            term_id = "W-79"
        elif resource_id == "Bu-30" or "chikuryoku" in resource_name.lower() or "蓄力" in resource_name:
            term_id = "W-81"
    term = extensions.all_glossary_data.get(term_id, {})
    name = str(term.get("display_name") or "").strip()
    return (term_id, name) if term_id and name else None
