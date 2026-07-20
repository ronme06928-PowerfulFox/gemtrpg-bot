from .base import BaseEffect


DEAL_TARGET_MAX_HP_DAMAGE = "DEAL_TARGET_MAX_HP_DAMAGE"


class TargetMaxHpDamageEffect(BaseEffect):
    """Emit unmodified damage equal to the target's maximum HP."""

    def apply(self, actor, target, params, context):
        if not isinstance(target, dict):
            return [], []
        try:
            max_hp = int(target.get("maxHp", 0) or 0)
        except (TypeError, ValueError):
            max_hp = 0
        if max_hp <= 0:
            return [], []

        target_name = str(target.get("name") or target.get("id") or "対象")
        return (
            [(target, "CUSTOM_DAMAGE", DEAL_TARGET_MAX_HP_DAMAGE, max_hp)],
            [f"《{DEAL_TARGET_MAX_HP_DAMAGE}》{target_name}に{max_hp}ダメージ"],
        )
