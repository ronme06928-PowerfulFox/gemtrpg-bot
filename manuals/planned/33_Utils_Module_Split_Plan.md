# 33 manager/utils.py 分割計画

**作成日**: 2026-07-08
**位置づけ**: `manager/utils.py`（1510行、`LEGACY_FILE_CEILINGS` にピン留め）を1500行制限内へ分割し、例外リストから外す計画。計画書29（game_logic分割・実装完了）と同じ「ファサード再export方式」を踏襲するが、utils特有の注意点（§4.3）がある。議論前のたたき台。

---

## 1. 目的

- `manager/utils.py` を 1500 行制限内に戻し、`tests/test_python_module_size_guard.py` の例外を1件減らす（残りは common_routes.py → 計画書34）。
- 約370行の巨大関数 `apply_buff`（buff_id別の特殊分岐の集合体）を独立モジュール化し、バフ付与ロジックの見通しを改善する。
- **挙動変更は一切行わない**。既存テストは無修正で全通過が条件。

## 2. 現状分析（2026-07-08 調査）

### 2.1 超過はわずか11行、構成はテーマ別に整理可能

| グループ | 行スパン | 概算行数 | 内容 |
|---|---|---:|---|
| 定数群 | 1-73 | 73 | ORIGIN_BONUS_BUFFS / STACK_RESOURCE_* / GYOMA・CHIKURYOKU定数 / エイリアス辞書（空） |
| A スタック資源 | 76-192 | 117 | resolve_stack_resource_name / get_stack_resource_count 等10関数 |
| B 正規化 | 195-258 | 64 | normalize_status_name / normalize_buff_name / normalize_character_labels |
| C ステータスget/set | 260-353 | 94 | get_status_value(61行) / set_status_value(31行) |
| D 数値ヘルパ | 356-402 | 47 | _safe_int / _resolve_fissure_* / _resolve_stack_count |
| **E バフ・ライフサイクル** | 405-839 | **435** | **`apply_buff`(405-774, 約370行・唯一の100行超)** / remove_buff / clear_*_flags |
| F バフ/パッシブ補正 | 842-1083 | 242 | get_buff_stat_mod / apply_passive_effect_buffs / get_buff_stat_mod_details |
| G Flask・雑 | 1085-1133 | 49 | session_required / resolve_placeholders |
| H+I 出身系・戦闘コンテキスト | 1136-1505 | 370 | 出身ボーナス / compute_origin_skill_modifiers / build_origin_hit_changes ほか |

### 2.2 呼び出され方は3系統（すべて `manager.utils` 名前空間経由）

1. `from manager.utils import X`（events/routes/plugins/room_manager/effect_handlers 等、多数）
2. `import manager.utils as _utils_mod` → 属性アクセス（battle層6モジュール）
3. `sys.modules.get('manager.utils')` + `getattr`（game_logic の `_utils_module()` ほか7箇所の遅延delegate）

→ **移設した全シンボルを `manager.utils` 名前空間へ再exportすれば、3系統とも無改変で動く。**

### 2.3 循環importの構図

- utils のトップレベル import は葉的（copy/re/functools/flask/logs のみ）で安全。
- buff_catalog / passives / models / extensions へは**関数内の遅延importのみ**で触れる（意図的な循環回避。この位置関係を崩さない）。
- battle層 → utils は遅延またはモジュール参照経由。

### 2.4 分割時の固有リスク（29と違う点）

1. **出身系（H+I）は monkeypatch 対象**: `tests/test_origin_bonuses.py:42-43` が `monkeypatch.setattr(utils, "get_effective_origin_id", ...)` 等でパッチし、同一モジュール内グローバル参照によってそれが波及することに依存している。別モジュールへ移すと再exportエイリアスの差し替えが波及せず**テストが壊れる**。解消には29同様の関数注入が必要 → **初手では触らない**。
2. **`apply_buff` 移設時の相互import**: apply_buff は B/D の低レベルヘルパに依存し、utils側の `apply_origin_bonus_buffs`(1206) は apply_buff を呼ぶ。素直に相互importするとロード時循環。回避は (a) 共有純関数を先に `utils_base` へ分離、(b) 新モジュール側から utils を遅延import、のどちらか（§7）。
3. 安全な点: `apply_buff` 自体はテストで `setattr` 差し替えされていない（丸ごと ModuleType 置換のみ）→ ファサード再exportだけで全呼び出しが無改変で通る。スタック資源グループ（A）も monkeypatch 非対象で安全。

## 3. 対象範囲

### 触るもの
- `manager/utils.py`（分割元・ファサード化）
- 新規: `manager/buff_apply.py`（E群の apply_buff 本体＋付随ヘルパ）
- （採用時）新規: `manager/utils_base.py`（B/D の共有純関数）
- 完了時: `tests/test_python_module_size_guard.py`（utils.py の ceiling 削除）

### 触らないもの（禁止事項）
- 公開シンボル名と `manager.utils` 名前空間（全 import 文・遅延getattr・monkeypatch が無改変で通ること）
- 出身系グループ（H+I）の移設（**本計画のスコープ外**。触るなら関数注入設計を伴う別フェーズ）
- バフ付与の挙動・ログ・buff_id別分岐の内容
- 関数内遅延importの位置関係（buff_catalog / passives / models）

## 4. 設計方針

- **最小手**: 超過11行に対し、E群 `apply_buff`（＋D群の fissure/stack ヘルパ約45行）を `manager/buff_apply.py` へ移すだけで確実に1500行を下回る（ファサードの再export行を足しても十分なマージン）。
- utils.py 側は `from manager.buff_apply import apply_buff`（再export）を置き、既存の3系統アクセスを全て維持する。
- 循環回避は §7 で決定（推奨: 新モジュール側の遅延import。既存の utils の流儀と一致し、ファイル数も増えない）。
- 余力があれば第2手として A群（スタック資源、117行）を `manager/stack_resources_util.py` へ移設（定数 `GYOMA_*`/`STACK_RESOURCE_*` は `effect_handlers/stack_resources.py` が直接 import しているため再export必須）。

## 5. 実装段階

| Phase | 内容 | 完了条件 |
|---|---|---|
| 0 | ベースライン確認: `pytest -q` 全通過を記録 | — |
| 1 | `manager/buff_apply.py` 新設、E群移設＋utils側再export。循環回避方式の適用 | テスト無修正で全通過、utils.py が1500行未満 |
| 2（任意） | A群（スタック資源）を移設＋定数の再export | 同上 |
| 3 | `LEGACY_FILE_CEILINGS` から `manager/utils.py` を削除、B01 or F01 へ構成追補、本計画書を削除 | サイズガード・全テスト・エンコーディングチェック通過 |

## 6. 推奨PR分割

1. Phase 1（apply_buff 移設。diff は大きいが機械的移動＋再export）
2. Phase 2（任意・スタック資源移設）
3. Phase 3（サイズガード更新・ドキュメント）

## 7. 未決定事項

| 論点 | 選択肢 | 備考 |
|---|---|---|
| 循環回避方式 | (1) buff_apply 側から utils を遅延import（推奨） / (2) `utils_base.py` を新設し双方が参照 | (1)は既存流儀と一致・ファイル増なし。(2)は依存が明示的だがファイルが増える |
| Phase 2 の実施 | apply_buff のみで止める / スタック資源も移す | 行数目標達成だけなら Phase 1 で足りる |
| 出身系の将来扱い | 本計画では触らない（確認） / 関数注入設計で別計画化 | test_origin_bonuses の monkeypatch 依存が解消条件 |
| 分割形態 | 単一モジュール追加（推奨） / `manager/utils/` パッケージ化 | パッケージ化は `sys.modules.get('manager.utils')` 参照があるため `__init__.py` facade で互換維持は可能だが、変更面積が大きい |

## 8. 決定事項ログ

（一問一答の議論後に追記する）

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| | | | |

## 9. 受け入れ条件

- `manager/utils.py` が1500行未満になり、`LEGACY_FILE_CEILINGS` から削除されている。
- 全既存テストが**無修正**で通過（特に `test_origin_bonuses.py` の monkeypatch 経路と、sys.modules 差し替え系テスト）。
- `from manager.utils import apply_buff` 等、既存 import 文が一切変わっていない。
- 新設モジュールが1500行制限内。
- エンコーディング/文字化けチェック通過。バフ付与の挙動・ログに変化がない。
