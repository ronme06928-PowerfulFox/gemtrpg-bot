# 12. Retaliation Plan（逆襲・残課題のみ）

**最終更新日**: 2026-07-07
**対象機能**: 逆襲（被ダメ起点の与ダメ増加）
**経緯**: 旧 `planned/03_New_Skill_Ideas_Feasibility_Plan.md` §4.3 の内容を本書へ統合し、03 は削除した（2026-07-07 棚卸し）。

---

## 1. 実装済みとして本書から除外した内容

- **加害者への追加ダメージ/状態異常/バフ付与**は、被弾反応パッシブ（`on_damage_reaction`）として実装済み。
  - 仕様書: `manuals/implemented/C02_Retaliation_Passive_Sheet_Examples.md`
  - 実装: `manager/utils.py::apply_passive_effect_buffs` / `manager/battle/runtime_actions.py::process_on_damage_buffs`
  - テスト: `tests/test_retaliation_passive.py`, `tests/test_retaliation_log_adapter.py`
- スキル使用可否のサーバー側一元判定層（`manager/battle/skill_access.py`）も実装済み（`B01_Skill_Logic_Core.md` §13）。

## 2. 残課題: 「そのターン被ダメした場合のみ与ダメ増加」

被弾反応は「殴られた瞬間に相手へ反応する」機構であり、「被ダメ済みターンに自分の攻撃が強くなる」条件参照は未実装。

### 2.1 未実装要素

- 「そのターン被ダメ済み」「誰から被ダメしたか」の戦闘メモリ
- 上記メモリを参照する条件（condition またはバフ）

### 2.2 推奨実装（旧03 §4.3 より）

各キャラに被ダメ記録を持たせる。

```json
{
  "damage_taken_this_round": 8,
  "damage_sources_this_round": { "char_A": 5, "char_B": 3 }
}
```

- 推奨配置: `char["flags"]` 配下、もしくは `char["combat_memory"]`
- HP を減らした**全経路**で `record_damage_taken(defender, attacker, amount)` を呼ぶ:
  - `manager/battle/core.py` / `duel_solver.py` / `wide_solver.py` / skill_effects の即時ダメージ / 追撃 / 反射 / 被弾反応自体
- リセット: `manager/battle/common_manager.py::process_full_round_end`
- 判定は2段階:
  - 被ダメしていれば全体与ダメボーナス
  - `current_target_id` が `damage_sources_this_round` に含まれていれば追加ボーナス

### 2.3 実装方式（どちらか）

- 方式A: `condition.source="battle_context"` に `param: "damage_taken_this_round"` / `"target_damaged_me_this_round"` を追加
- 方式B: 専用バフが `process_on_hit_buffs` で追加ダメージを返す

**初回実装は方式Bが事故が少ない**（旧03の結論を踏襲）。

## 3. 実装時チェックポイント（旧03 §6.4/§6.5 より）

- 被ダメ記録の更新漏れ: Select/Resolve・旧duel・wide・CUSTOM_EFFECT・追撃・反射のどの経路で記録され、どこが抜けるかを必ず洗う（逆襲系はここが最も壊れやすい）
- ラウンド境界: 被ダメ記録の「消し忘れ」と「早く消えすぎ」の両方を確認する

## 4. テスト観点

- 被ダメなしターンは逆襲補正が乗らない
- 被ダメありターンのみ乗る
- 追加ダメは「同ターンの加害者」にのみ発生
- 既存の被弾反応パッシブ（C02）と同時に持っても二重計上しない
