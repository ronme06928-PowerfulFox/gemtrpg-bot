# Battle Balance Designer Skill 運用マニュアル

最終更新: 2026-05-31

## 目的

`battle-balance-designer` は、TRPG/ダイス戦闘のバランスと面白さを相談するための Codex Skill である。

単に「強い/弱い」を判定するのではなく、次の観点を一緒に見る。

- プレイヤーの選択に意味があるか
- 勝敗やダメージ結果に納得感があるか
- 戦闘テンポが重すぎないか
- 防御、支援、召喚、妨害、火力の役割が成立しているか
- GMやプレイヤーの処理負荷が卓で扱える範囲か
- Gem_DiceBotTool の Select/Resolve、clash、one-sided、召喚、FP、バフスタック、PvE自動意図と矛盾しないか

## Skill の保存場所

現在の Skill は次に配置している。

```text
C:\Users\yharu\.codex\skills\battle-balance-designer
```

主なファイルは以下。

```text
SKILL.md
references/usage-guide-ja.md
references/evaluation-framework.md
references/gem-dicebottool.md
references/response-patterns.md
agents/openai.yaml
```

## 使い方

明示的に使いたい場合は、依頼文に `$battle-balance-designer` を含める。

例:

```text
$battle-balance-designer を使って、この新スキルが強すぎないか見てください。
狙いは「支援役が一瞬だけ火力役を輝かせる」です。
効果: 味方1人の次の攻撃ダメージ+8、命中時FP+1。消費MP3。
```

```text
$battle-balance-designer で、PvEボスの第2形態を相談したいです。
プレイヤー4人、想定戦闘は5ラウンド程度。
今の問題は、3ラウンド目以降に単調になることです。
```

```text
$battle-balance-designer を使って、召喚スキルの制限を考えたいです。
召喚体は次ラウンドから行動可能で、3R継続です。
行動経済が壊れないようにしたいです。
```

## 暗黙的な読み込みについて

Codex の Skill は、常に全文が読み込まれているわけではない。

通常は、各 Skill の `name` と `description` がトリガー判定に使われる。依頼内容が description に合うと判断された場合、Codex がその Skill の `SKILL.md` を読み込んで使う。

この Skill は description に次のようなトリガー語を入れている。

- TRPG
- ダイス戦闘
- PvE遭遇
- スキルカタログ
- バフ/デバフ
- 召喚
- 行動経済
- clash/duel
- Gem_DiceBotTool
- 戦闘バランス
- ゲームの面白さ
- 戦闘テンポ

そのため、「このスキル強すぎる？」「PvE敵の行動を調整したい」「召喚が壊れないようにしたい」のような相談では、明示しなくても呼ばれる可能性が高い。

ただし、確実に使わせたい場合は `$battle-balance-designer` と書くのが安全である。

## 相談時にあるとよい情報

相談時は、全部を揃える必要はないが、次があるとレビュー精度が上がる。

- 作りたい面白さ
- 想定プレイヤー人数
- 想定ラウンド数
- 既存スキルとの比較対象
- コスト、対象、タイミング、継続時間、使用制限
- 失敗してほしくない体験
- その案を使う役割: 火力、防御、支援、妨害、召喚、PvE敵など

## 返答の基本形

大きめのレビューでは、Skill は次の形で返すようにしている。

```text
狙い:
この案が作りたい体験。

強い点:
面白さや役割として成立している部分。

リスク:
支配的行動、雪だるま化、処理負荷、リソース黒字、行動経済破壊など。

調整案:
小さく試せる変更案。各案のトレードオフも書く。

検証:
プレイテストや簡易計算で見るべきこと。
```

短い相談では、見出しを省略して会話形式で答える。

## Gem_DiceBotTool で特に見る観点

Gem_DiceBotTool の戦闘では、次を重く見る。

- `clash` はダメージだけでなくFP獲得や防御/回避の価値に関わる。
- `one_sided` は対抗不能時の圧力を作るため、対象選択とテンポに影響する。
- 召喚は追加ユニットだけでなく、将来の行動スロットと対象数を増やす。
- `USE_SKILL_AGAIN` は追加行動に近く、行動価値を大きく増幅する。
- バフ/スタック資源は、上限、持続、掃除、表示を同時に設計する必要がある。
- PvE自動意図と敵AIは、プレイヤースキルを変えなくても遭遇難度を大きく変える。
- resolve log で説明できない効果は、プレイヤーの納得感を落としやすい。

## 実装相談で参照するファイル

実装や具体的なスキルJSONに踏み込む場合は、Skill は次のファイルを確認する想定である。

```text
manuals/implemented/B01_Skill_Logic_Core.md
manuals/implemented/B02_Skill_Logic_Extensions.md
manuals/implemented/B03_SelectResolve_Spec.md
manuals/implemented/C01_JSON_Definition_Master.md
manager/game_logic.py
manager/battle/core.py
manager/battle/resolve_auto_single_phase.py
manager/battle/pve_intent_planner.py
manager/battle/enemy_behavior.py
manager/battle/skill_access.py
manager/summons/service.py
manager/utils.py
```

関連テストは、対象メカニクスに応じて `tests/` から探す。

## 運用上の注意

この Skill は、最終的な正解を固定するためのものではなく、設計判断の質を上げるための文脈である。

数値だけで結論を出さず、次のように扱う。

- まず「何を面白くしたいか」を確認する。
- 次に「どの条件で壊れるか」を見る。
- 最後に「小さく試せる調整案」を出す。

特に、追加行動、召喚、無料リアクション、無制限スタック、リソース黒字ループは、初期案では控えめに設計する。

## 更新方針

Skill の内容を更新したら、このマニュアルも必要に応じて更新する。

更新対象になりやすいもの:

- Skill の保存場所
- 相談例
- Gem_DiceBotTool 固有の重点観点
- 新しく増えた戦闘メカニクス
- 参照すべきファイルやテスト
