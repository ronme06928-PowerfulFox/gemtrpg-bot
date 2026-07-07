# manager/battle/effect_handlers/session.py
import copy


class EffectSession:
    """process_skill_effects 1回分の共有状態。

    game_logic.process_skill_effects のクロージャ変数・ヘルパクロージャを移設したもの。
    フィールド名・更新順序は移設前のローカル変数と1対1で対応させている
    （manuals/planned/29_Game_Logic_Refactoring_Plan.md Phase 1）。

    循環import回避のため、game_logic 側の状態取得/設定関数
    （_stable_get_status_value / _stable_set_status_value）はコンストラクタで注入する。
    """

    def __init__(self, actor, target, timing, context, base_damage,
                 get_status_value_fn, set_status_value_fn):
        self.actor = actor
        self.target = target
        self.timing = timing
        self.context = context
        self.base_damage = base_damage
        self.total_bonus_damage = 0
        self.log_snippets = []
        self.changes_to_apply = []
        self.simulated_chars = {}
        # Original hit target (before per-effect target remapping like target=self).
        self.original_sim_target = None
        self.get_status_value = get_status_value_fn
        self.set_status_value = set_status_value_fn

    def get_simulated_char(self, real_char):
        if not real_char: return None
        cid = real_char.get('id')
        if cid not in self.simulated_chars:
            self.simulated_chars[cid] = copy.deepcopy(real_char)
        return self.simulated_chars[cid]

    def queue_fissure_round_buff(self, target_obj, sim_target, amount, rounds, source='skill'):
        amount = int(amount or 0)
        rounds = int(rounds or 0)
        if amount <= 0 or rounds <= 0:
            return

        current_val = self.get_status_value(sim_target, "亀裂")
        self.set_status_value(sim_target, "亀裂", current_val + amount)

        self.changes_to_apply.append((
            target_obj,
            "APPLY_BUFF",
            f"亀裂_R{rounds}",
            {
                "lasting": rounds,
                "delay": 0,
                "data": {
                    "buff_id": "Bu-Fissure",
                    "source": source,
                    "count": amount,
                    "fissure_count": amount,
                    "original_rounds": rounds
                }
            }
        ))

    def queue_remaining_buff(self, target_obj, sim_bucket, buff_name, remaining):
        self.changes_to_apply.append((target_obj, "REMOVE_BUFF", buff_name, 0))
        if remaining <= 0:
            return

        preserved_data = {}
        preserved_lasting = -1
        preserved_delay = 0
        explicit_lasting = False
        if isinstance(sim_bucket, dict):
            preserved_data = dict(sim_bucket.get("data") or {})
            try:
                preserved_lasting = int(sim_bucket.get("lasting", -1))
            except (TypeError, ValueError):
                preserved_lasting = -1
            try:
                preserved_delay = int(sim_bucket.get("delay", 0))
            except (TypeError, ValueError):
                preserved_delay = 0
            explicit_lasting = ("lasting" in sim_bucket)
            if sim_bucket.get("buff_id") and "buff_id" not in preserved_data:
                preserved_data["buff_id"] = sim_bucket.get("buff_id")
            if sim_bucket.get("description") and "description" not in preserved_data:
                preserved_data["description"] = sim_bucket.get("description")
            if sim_bucket.get("flavor") and "flavor" not in preserved_data:
                preserved_data["flavor"] = sim_bucket.get("flavor")

        preserved_data["count"] = remaining
        self.changes_to_apply.append((
            target_obj,
            "APPLY_BUFF",
            buff_name,
            {
                "lasting": preserved_lasting,
                "delay": preserved_delay,
                "count": remaining,
                "data": preserved_data,
                "explicit_lasting": explicit_lasting,
            }
        ))
