"""Transient metadata carried from damage application to on-death effects."""


def build_damage_context(actor=None, skill_data=None, damage_type=None, skill_id=None):
    context = {}
    if isinstance(actor, dict):
        context["actor"] = actor
    if isinstance(skill_data, dict):
        context["skill_data"] = skill_data
        if not skill_id:
            for key in ("id", "skill_id", "スキルID", "ID"):
                if skill_data.get(key):
                    skill_id = skill_data.get(key)
                    break
    if skill_id is not None and str(skill_id).strip():
        context["skill_id"] = str(skill_id).strip()
    if damage_type is not None and str(damage_type).strip():
        context["damage_type"] = str(damage_type).strip()
    return context


def with_damage_type(damage_context, damage_type):
    context = dict(damage_context) if isinstance(damage_context, dict) else {}
    if damage_type is not None and str(damage_type).strip():
        context.setdefault("damage_type", str(damage_type).strip())
    return context
