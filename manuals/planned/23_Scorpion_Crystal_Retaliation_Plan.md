# 23. Scorpion Crystal Retaliation Plan

**作成日**: 2026-05-11  
**ステータス**: Current  
**対象**: 被弾反応パッシブ  
**主題**: 自分がダメージを受けた時に、攻撃者へダメージ、状態異常、バフを返す仕組みの整理

---

## 1. 目的

サソリ系の敵キャラクター向けに、「被弾時に砕けた毒晶が飛び散り、攻撃者へ反撃効果を与える」パッシブを実装する。

この仕組みは特定の敵専用ではなく、今後の敵や装備、特殊パッシブでも再利用できる共通機能として扱う。

目標は次の 3 系統を同じ枠組みで扱えるようにすること。

- 被弾時に攻撃者へ固定ダメージを与える
- 被弾時に攻撃者へ状態異常を付与する
- 被弾時に攻撃者へ `Bu-XX` バフを付与する

---

## 2. 現状整理

### 2.1 実装済みの中心

- `manager/utils.py::apply_passive_effect_buffs`
  - 特殊パッシブの `effect` を `special_buffs` へ展開する入口
- `manager/battle/runtime_actions.py::process_on_damage_buffs`
  - 被弾反応の主処理

### 2.2 現在サポートしている `on_damage_reaction`

現行実装では、`on_damage_reaction` で以下を扱える。

- `target`
- `damage`
- `apply_state`
- `apply_buff`
- `condition.damage_gte`

呼び出し側では、被弾者が誰に攻撃されたかを渡すために次の系統が `attacker_char` を引き回している。

- `manager/battle/duel_solver.py`
- `manager/battle/wide_solver.py`
- `manager/battle/resolve_match_runtime.py`
- `manager/battle/resolve_effect_runtime.py`
- `manager/skill_effects.py`

テストは `tests/test_retaliation_passive.py` で確認している。

### 2.3 まだ整理不足の点

- 反応ダメージの再帰発火ルールが明文化不足
- 「スキルで受けたダメージのみ」などの条件追加が未対応
- ログ表示の粒度が未整理
- `apply_buff` で `buff_id` をどこまで必須扱いにするかの運用方針が未明確

---

## 3. 現在のデータ仕様

### 3.1 最小構成

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 3
  }
}
```

意味:

- このパッシブ所持者がダメージを受けた時
- 攻撃者に 3 ダメージを与える

### 3.2 状態異常付与

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "出血", "value": 2 }
    ]
  }
}
```

`apply_state` のロールモデルは `出血` と `亀裂` を前提にする。

- `出血` は `name` と `value` で付与する
- `亀裂` は `name` と `value` に加えて `rounds` を指定する
- `亀裂` の `rounds` は必須扱いとする

亀裂の例:

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "亀裂", "value": 1, "rounds": 2 }
    ]
  }
}
```

### 3.3 バフ付与

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_buff": [
      {
        "buff_id": "Bu-47",
        "buff_name": "被弾時出血",
        "lasting": 2,
        "delay": 0,
        "data": { "value": 3 }
      }
    ]
  }
}
```

### 3.4 複合反応

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 2,
    "apply_state": [
      { "name": "出血", "value": 2 },
      { "name": "亀裂", "value": 1, "rounds": 2 }
    ],
    "apply_buff": [
      {
        "buff_id": "Bu-32",
        "lasting": 1,
        "delay": 0,
        "data": { "value": 3 }
      }
    ]
  }
}
```

### 3.5 条件付き

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 3,
    "condition": {
      "damage_gte": 1
    }
  }
}
```

意味:

- 実際に 1 以上のダメージを受けた時だけ反応する

---

## 4. 実装方針

### 4.1 主入口を一本化する

被弾反応の判定と適用は `process_on_damage_buffs` に集約する。

理由:

- duel / wide / Select-Resolve の経路差分を減らせる
- 将来条件を追加しても一か所で管理できる
- 反応ダメージの再帰防止を集中管理できる

### 4.2 既存の `on_damage_state` は急いで消さない

旧仕様が残っている可能性があるため、当面は互換維持を優先する。

整理方針:

- 新規定義は `on_damage_reaction` を推奨
- 旧形式は読み取りのみ維持
- 将来まとめて移行する

### 4.3 `apply_buff` は `buff_id` 優先

推奨運用:

- `buff_id` を実体参照の主キーとする
- `buff_name` は表示補助として扱う
- `lasting` と `delay` は明示指定を推奨
- `data.value` は value-driven buff 用の拡張入力として通す

---

## 5. 今後の拡張フェーズ

### Phase A. 仕様の固定

やること:

- `damage`
- `apply_state`
- `apply_buff`
- `condition.damage_gte`

この 4 つを正式仕様としてマニュアル化し、シート運用例も統一する。

状態異常付与は、少なくとも次の 2 系統を固定対象とする。

- `出血`: `value` 指定
- `亀裂`: `value` と `rounds` 指定

### Phase B. 再帰防止の明文化と強化

やること:

- 反応ダメージでさらに `on_damage_reaction` が連鎖しないようにする
- どの経路でも同じガードが効くようにする

優先度:

- 高

理由:

- 反撃同士の無限連鎖が最も危険な不具合になりやすい

### Phase C. 条件拡張

候補:

- `skill_only: true`
- `once_per_hit: true`
- `once_per_turn: true`
- `source_tags`
- `melee_only`

優先度:

- 中

理由:

- 設計幅は広がるが、まずは基礎反応の安定が先
- 当面の正式対応は `condition.damage_gte` のみとし、追加条件は保留にする

### Phase D. ログ改善

やること:

- 誰のどの被弾反応が発動したかを戦闘ログに出す
- ダメージ、状態異常、バフ付与を見分けやすくする

優先度:

- 中

---

## 6. 推奨 JSON パターン

### 6.1 毒晶反射

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 3
  }
}
```

### 6.2 出血と亀裂を返す

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "出血", "value": 2 },
      { "name": "亀裂", "value": 1, "rounds": 2 }
    ]
  }
}
```

### 6.3 専用デバフを返す

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_buff": [
      {
        "buff_id": "Bu-58",
        "buff_name": "毒晶侵食",
        "lasting": 2,
        "delay": 0,
        "data": { "value": 2 }
      }
    ]
  }
}
```

### 6.4 ダメージと亀裂を同時に返す

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 2,
    "apply_state": [
      { "name": "亀裂", "value": 1, "rounds": 2 }
    ]
  }
}
```

---

## 7. テスト計画

最低限必要な確認項目は次のとおり。

- 被弾時に攻撃者へ固定ダメージが入る
- 被弾時に攻撃者へ `出血` が入る
- 被弾時に攻撃者へ `亀裂` が `rounds` 付きで入る
- 被弾時に攻撃者へ `Bu-XX` が入る
- `condition.damage_gte` が正しく効く
- `亀裂` の `rounds` 未指定時の挙動が固定されている
- 反応ダメージで再帰発火しない

確認先:

- `tests/test_retaliation_passive.py`

必要なら将来的に以下も追加する。

- duel 系
- wide 系
- Select-Resolve 系
- ログ文言の確認

---

## 8. 実装タスク整理

1. `on_damage_reaction` の現行仕様をこのマニュアル内容に合わせて維持する
2. 再帰防止の仕様をコードと文書の両方で明文化する
3. `skill_only` などの追加条件が必要になった時点で JSON 仕様を拡張する
4. シート記入例を特殊パッシブ向けに別マニュアルか一覧へ整理する
5. ログ表示を改善してデバッグしやすくする

---

## 9. 決定事項ログ

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 2026-05-11 | 被弾反応の亀裂制限 | **被弾反応の亀裂は通常の1ラウンド1回制限と共有しない** | 被弾反応専用の別枠挙動として運用したい |
| 2026-05-11 | ログ表示方針 | **チャットログはプレイヤー向けの自然文にする** | 実戦ログで読みやすさを優先する |
| 2026-05-11 | 条件拡張の扱い | **現時点では `damage_gte` のみ正式対応、他条件は保留** | 追加条件より基礎挙動の安定を優先する |
| 2026-05-11 | 確認範囲 | **実装確認は自動テストまででよい** | 今回はコード回帰と仕様整合の確認を優先する |

---

## 10. 結論

被弾反応パッシブは、すでに `on_damage_reaction` を軸にした基礎実装へ乗っている。

今後はこのキーを正式仕様として整理し、

- ダメージ
- 状態異常
- バフ付与

を同じ枠組みで扱う方針で進める。

サソリの毒晶外殻のような敵は、この仕様上で自然に表現できる。
