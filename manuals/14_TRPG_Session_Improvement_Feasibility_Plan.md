# 14 TRPGセッション改善機能 調査・実現性メモ

**作成日**: 2026-03-05  
**対象**: 戦闘UI / Select-Resolve / GM運用補助 / 演出改善  
**目的**: 今後のセッション向け改善要望について、現状実装を確認し、実現性と実装時の論点を整理する

## 1. 結論サマリ

今回の要望は、全体として実現可能です。  
ただし、難易度と影響範囲には差があります。

| 要望 | 現状 | 実現性 | 所感 |
| :--- | :--- | :--- | :--- |
| GMによるバフ/デバフ・アイテム付与/没収 | 一部土台あり | 高 | バックエンドは流用できるが、専用UIと権限整理が必要 |
| 戦闘画面のスロット表示調整 | 既存UIあり | 高 | CSS中心で対応可能 |
| タイムラインUI非表示 | UIのみ対象 | 高 | 内部 `timeline` は維持し、画面表示だけ止める |
| 同速の行動順ロジック明文化・改善 | 仕様と実装は概ね存在 | 高 | 文言整理は容易、厳密改善は小〜中規模 |
| フローティングテキスト改善 | 仕組みありだが見えづらい | 高 | 主因は表示レイヤーとイベント粒度 |
| Resolve中の立ち絵表示 | 既存データあり | 高 | ResolveFlowPanelの拡張で対応可能 |

優先順位としては、まず `権限整理` と `表示レイヤー整理` を先に行うのが安全です。  
特に GM 操作系は、現状でも一部イベントがクライアント依存で制御されており、サーバー側の権限チェックを強めた方がよいです。

## 2. 現状調査

### 2.1 GMによる HP / MP / FP 編集の現状

- `static/js/action_dock.js` のクイック編集モーダルで HP / MP / FP の一括編集が可能です。
- 編集送信は `request_state_update` を使用しています。
- サーバー側では `events/socket_char.py` の `handle_state_update` が受け、`manager/room_manager.py` の `_update_char_stat()` で反映しています。
- HP / MP は専用分岐、FP は `states` 内の通常ステータスとして更新されます。

現状の制約:

- `special_buffs` を直接編集する専用APIはありません。
- `inventory` を直接編集する専用APIはありません。
- `_update_char_stat()` は数値ステータス向けで、`special_buffs` のような配列フィールドを安全に扱う設計ではありません。

注意点:

- `request_state_update` は `gmOnly` 以外の項目について、サーバー側で GM / 所有者チェックが入っていません。
- つまり、現状は UI 側の制御に依存しており、将来のGM機能追加前に権限整理を入れるべきです。

### 2.2 バフ / デバフ管理の現状

- バフ基盤自体はあります。
- `manager/utils.py` に `apply_buff()` / `remove_buff()` があり、`special_buffs` を更新できます。
- バフ定義は `manager/buff_catalog.py` と `manager/buffs/loader.py`、クライアント側補助は `static/js/buff_data.js` にあります。
- キャラクター詳細表示 (`static/js/modals.js`) では `special_buffs` を一覧表示できます。

不足している点:

- GMが任意のキャラへバフを付与 / 解除する専用 Socket イベントがありません。
- バフ一覧を選んで付与するGM用UIがありません。
- バフ付与時の lasting / delay / count を調整する運用UIも未整備です。

### 2.3 アイテム付与・没収の現状

- アイテム使用は `events/socket_items.py` の `request_use_item` で実装済みです。
- GM用に `request_gm_grant_item` は既にあります。
- `manager/items/usage_manager.py` には `grant_item()` があり、`inventory` へ加算できます。

不足している点:

- `request_gm_grant_item` を呼ぶフロントUIが見当たりません。
- `request_gm_remove_item` のような没収APIはありません。
- 個数調整（増減）UIがありません。

注意点:

- `request_use_item` は `user_id` をクライアント入力で受けていますが、サーバー側で所有権検証がありません。
- GM用機能を増やすなら、アイテム系も同時に権限チェックを見直した方が安全です。

### 2.4 戦闘画面のスロット表示の現状

- Select フェーズのスロットは、`static/js/visual/visual_map.js` の `renderSlotBadgesForAllTokens()` で描画されています。
- 見た目は `static/css/modules/visual_map.css` の `.slot-badge-container` / `.slot-badge` で制御されています。

現状の値:

- `.slot-badge-container` は `top: -52px`
- `.slot-badge` は `34px x 34px`
- 状態異常アイコン (`.mini-status-icon`) は `22px x 22px`

現状の問題:

- トークン上部にスロット表示を置いているため、状態異常アイコン数やトークンサイズ次第で視覚的に近くなりやすいです。
- 複数スロット持ちキャラでは横並び幅も増え、上部表示との干渉が起きやすいです。

### 2.5 タイムラインの現状

- UIとしてのタイムラインは `static/4_visual_battle.html` の `#visual-timeline-area` にあります。
- 描画は `static/js/battle/components/Timeline.js` が担当しています。
- CSS は `static/css/modules/visual_battle.css` にあります。

ただし、`timeline` は UI だけでなく内部データでも重要です。

- `manager/battle/common_manager.py` でラウンド開始時の行動順として生成されます。
- `manager/room_manager.py` で `battle_state.timeline` を補完・同期します。
- `manager/game_logic.py` では条件参照（速度値など）にも使います。
- Select/Resolve の解決順にも使われます。

今回の整理では、タイムラインは **画面上のUIを非表示にするだけ** を対象とします。  
内部の `timeline` データ構造は、行動順制御のためそのまま維持する前提です。

### 2.6 同速（同じ速度値）の現状

- 仕様書 `manuals/08_SelectResolve_Spec.md` には「同速グループだけ追加ロールで順序確定」と記載があります。
- 実装は `manager/battle/common_manager.py` の `process_select_resolve_round_start()` 側にあります。

現在の流れ:

1. 各スロットの `initiative` を計算
2. 同じ `initiative` のスロット群を抽出
3. 同速群だけ追加で 1d6 (`_tie_roll`) を振る
4. 並び順は `initiative desc -> tie_roll desc -> slot_id asc`
5. `battle_state.tiebreak` にグループ情報を保存

現状の論点:

- 追加ロールの結果がさらに同値だった場合、最終的に `slot_id` の文字列順で決まります。
- つまり「追加ロールだけで完全決着」ではなく、最後は内部ID依存の決着です。
- `tiebreak` は保存されていますが、現状のフロントでは表示・説明されていません。

### 2.7 フローティングテキストの現状

- フローティングテキスト自体は `static/js/visual/visual_map.js` の `showFloatingText()` で実装済みです。
- `char_stat_updated` イベント受信時に `updateCharacterTokenVisuals()` から即時表示されます。
- サーバー側でも Select/Resolve 中の差分更新は `manager/battle/core.py` の `_emit_char_stat_update()` / `_emit_stat_updates_from_applied()` で発火しています。

見えていない主因:

- `.floating-damage-text` の `z-index` は `100`
- Resolve演出パネル `#resolve-flow-panel` の `z-index` は `905`

そのため、Resolve中はフローティングテキストが **出ていても演出パネルの下に隠れやすい** です。  
「解決後にまとめて出ている」ように見える主因はここです。

追加の制約:

- `manager/battle/core.py` では `buff:*` 形式の状態変化は `char_stat_updated` に流していません。
- つまり、HP減少のような数値差分は飛びますが、「毒付与」「出血付与」のようなバフ付与そのものは、現状のフローティングテキスト対象外です。

### 2.8 Resolve中のマッチ表示の現状

- 現在の Resolve 演出は `static/js/battle/components/ResolveFlowPanel.js` が担当しています。
- 表示内容は「名前 / スキル名 / 威力 / 結果」が中心です。
- 現状のHTML生成には立ち絵表示ブロックがありません。

一方で、キャラの立ち絵データ自体は既にあります。

- 戦闘トークン描画 (`static/js/visual/visual_map.js`) で `char.image` を使っています。
- キャラ編集UIでも `image` / `imageOriginal` を保持しています。

広域-合算の現状:

- `_summationParticipants()` は `rolls.defender_powers` をもとに「参加スロット -> 名前 + 威力」を組み立てています。
- ここに actor_id / image を追加すれば、防御参加者の立ち絵並列表示へ発展できます。

## 3. 要望ごとの実現性評価

### 3.1 GMによるバフ・デバフ付与 / 解除、アイテム付与 / 没収

**実現性**: 高

理由:

- バフ基盤 (`apply_buff`, `remove_buff`) が既にある
- アイテム付与基盤 (`request_gm_grant_item`, `grant_item`) が既にある
- クイック編集UIという GM 向け導線も既にある

必要な実装:

1. GM専用 Socket イベントを追加
2. サーバー側で対象キャラを解決し、`special_buffs` / `inventory` を安全に更新
3. `broadcast_state_update()` と必要なら差分イベントを送る
4. クイック編集モーダル、または新規GM管理モーダルから操作できるようにする

推奨API:

- `request_gm_apply_buff`
- `request_gm_remove_buff`
- `request_gm_adjust_item`（増減を1本化）

注意点:

- 先に `request_state_update` / `request_use_item` の権限チェックを強化する
- バフの `lasting`, `delay`, `count` をどう指定するかをUIで固定化する
- 解除時に「名前指定」か「buff_id指定」かを統一する

推奨難易度:

- バックエンド: 小〜中
- UI: 中
- 権限整理込み: 中

### 3.2 戦闘画面UI改善（スロットを大きくして少し上へ）

**実現性**: 高

理由:

- 主に CSS 調整で完結します。
- スロット表示は独立した `.slot-badge-container` / `.slot-badge` にまとまっています。

想定対応:

- `.slot-badge-container` の `top` をより小さく（例: `-64px` 前後）する
- `.slot-badge` を 40〜44px 程度に拡大する
- 必要なら `gap` と `font-size` を再調整する
- モバイルや縮小トークン時の見え方も確認する

注意点:

- トークンサイズ変更機能 (`tokenScale`) があるため、固定値だけでなく極端な縮小時の見え方を確認する
- 立ち絵トークンと文字トークンの両方で確認する

推奨難易度:

- 小

### 3.3 タイムラインUIの非表示

**実現性**: 高

対応範囲:

- `static/4_visual_battle.html` の `#visual-timeline-area`
- `static/js/battle/index.js` の Timeline 初期化
- 必要なら CSS の整理

これは比較的軽い変更です。

実装方針:

- `#visual-timeline-area` を非表示にする
- `Timeline.js` の初期化は、残しても削ってもよいが、少なくとも画面には出さない
- `timeline` データは従来どおり生成・保持する

理由:

- `timeline` は Select/Resolve の処理順に使われている
- `manager/room_manager.py` や `manager/game_logic.py` でも参照されている
- したがって、今回は表示だけ止めるのが安全

### 3.4 同速ロジックの明文化と改善

**実現性**: 高

明文化だけならすぐできます。  
実装改善も小〜中規模で可能です。

現状で明文化すべき内容:

1. 同速判定は `initiative` 同値で行う
2. 同速グループだけ追加1d6を振る
3. 追加ロール高い順で並べる
4. 追加ロールも同値なら `slot_id` 昇順で決着

改善案:

- 案1: 現状のまま、仕様書とUIログに明示する
- 案2: 同値が残った組だけ再ロールを繰り返し、完全にランダム決着にする
- 案3: `slot_id` ではなく、`actor_id + index_in_actor + committed_at` 等の別ルールにする

推奨:

- まずは **現仕様の明文化 + tiebreak表示** を先に行う
- そのうえで、まだ不満があれば「再ロール方式」に拡張する

推奨難易度:

- 明文化のみ: 小
- 再ロール実装: 中

### 3.5 フローティングテキスト改善

**実現性**: 高

現状の主な阻害要因は、仕組み不足ではなく以下です。

1. Resolve演出パネルの下に隠れる
2. バフ付与イベントがフローティング対象に乗っていない

最小対応:

- `.floating-damage-text` の `z-index` を `#resolve-flow-panel` より上げる

これだけでも、Resolve中にマップ上へ見えるようになります。

より望ましい対応:

- `buff:*` の付与/解除も個別イベントにする
- または ResolveFlowPanel 側で `step.applied.damage` / `step.applied.statuses` / `step.damage_events` を読み、
  そのステップに紐づく受け手へ演出を出す

推奨実装方針:

- 第1段階: z-index 修正で「見えない」問題を解消
- 第2段階: バフ付与も可視化
- 第3段階: ResolveFlowPanel 内演出と統合する

推奨難易度:

- 第1段階: 小
- 第2段階: 中
- 第3段階: 中

### 3.6 Resolve中の立ち絵表示（片側/複数並び）

**実現性**: 高

理由:

- 既に `state.characters` に `image` を持っている
- ResolveFlowPanel はHTMLを1箇所で組み立てているため、拡張ポイントが明確
- 広域-合算も参加者一覧生成関数が既にある

実装方針:

1. `ResolveFlowPanel` に「サイドごとのポートレート描画」ヘルパーを追加
2. attacker / defender の actor_id から `state.characters` を引く
3. `mass_summation` は `_summationParticipants()` を拡張し、参加者の `actor_id` と `image` を拾う
4. 防御側に横並びサムネイルを表示する

注意点:

- 画像未設定時のフォールバック（名前イニシャルや無画像プレースホルダ）が必要
- 画像縦横比がバラバラでも崩れないよう `object-fit: cover` を前提にする
- 参加者数が多いときの折り返しや縮小ルールを決める

推奨難易度:

- 単体 1vs1 表示: 小〜中
- 広域-合算の複数人表示: 中

## 4. 実装時の主要リスク

### 4.1 権限・不正操作

最優先で見るべきリスクです。

- クライアント側の表示制御だけでは不十分
- GM用機能を増やすほど、サーバー側の認可不足が問題化しやすい

最低限やるべきこと:

- `request_state_update` に所有者 or GM チェックを入れる
- `request_use_item` に所有者チェックを入れる
- GM操作イベントはすべて `attribute == 'GM'` をサーバー側で強制する

### 4.2 旧UI / 新UIの二重系統

このリポジトリは、旧来の `battleState` ベース描画と、`BattleStore` ベースの Select/Resolve 新UIが混在しています。  
そのため、片側だけ直しても反映されない箇所が出やすいです。

特に注意:

- `static/js/visual/*.js`
- `static/js/battle/components/*.js`
- `battleState` と `window.BattleStore.state` の両方

### 4.3 演出の表示レイヤー

Resolve演出は overlay を持つため、マップ上演出の z-index がすぐ競合します。  
フローティングテキスト、矢印、スロット、モーダルの重なり順はまとめて確認した方が安全です。

### 4.4 広域系の表示密度

広域-合算で参加者立ち絵を並べる場合、人数が多いほど情報量が急増します。  
表示数上限、折り返し、縮小、スクロールのどれを採るかを先に決めるべきです。

## 5. 推奨実装順

以下の順で進めるのが安全です。

1. 権限チェック整理
2. GM用バフ / アイテム操作API追加
3. GM用管理UI追加（既存クイック編集拡張が有力）
4. スロット表示の見た目調整
5. タイムライン欄のUI非表示
6. 同速ロジックの明文化と表示
7. フローティングテキスト改善
8. ResolveFlowPanel の立ち絵対応

この順序にすると、先に運用事故を防ぎ、その後に視認性改善へ進めます。

## 6. 計画を見る時の観点（レビュー観点）

今後この改善計画を精査するときは、以下の観点で見ると抜け漏れを減らせます。

### 6.1 要件の切り分けが明確か

- 「UIを消す」のか「内部ロジックを消す」のか
- 「見えるようにする」のか「新しい演出を作る」のか
- 「GMだけできる」のか「PLも一部できる」のか

曖昧だと、影響範囲の見積もりがぶれます。

### 6.2 サーバー権限が先に定義されているか

- UI制御だけで終わっていないか
- Socketイベントごとに認可条件があるか
- クライアント送信値を信頼しすぎていないか

GM機能は、まず認可が仕様化されていることが前提です。

### 6.3 データモデルが既存構造に沿っているか

- `special_buffs` をどう持つか
- `inventory` をどう増減するか
- `battleState` と `BattleStore` のどちらを正にするか
- `timeline` を内部で維持したまま、UIだけ非表示にする方針になっているか

既存構造に逆らう変更は、実装コストが急増します。

### 6.4 差分イベントで済むか、全体再描画が必要か

- `char_stat_updated` のような差分イベントで足りるか
- `state_updated` を待つ必要があるか
- Resolve中に段階表示したいなら、どのタイミングのイベントを使うか

ここが曖昧だと、「処理はされているが見えない」問題が再発します。

### 6.5 見た目だけでなくレイヤー競合まで見ているか

- z-index
- overlay の有無
- モーダルとマップ演出の重なり
- モバイル時の崩れ

戦闘UIは、単体コンポーネント単位ではなく重なり順まで見ないと不具合が残ります。

### 6.6 旧UI / 新UIの両方に影響がないか

- `visual_*` 系だけ触ればよいのか
- `battle/components/*` 側も触る必要があるのか
- 旧マッチパネルと新ResolveFlowPanelが競合しないか

この確認を飛ばすと、「一部画面だけ反映されない」状態になります。

### 6.7 テスト観点が含まれているか

- 権限テスト
- 同速ロジックの順序テスト
- バフ / アイテム付与・解除テスト
- Resolve中の表示イベントテスト
- 画像未設定時のフォールバック確認

特に同速ロジックと権限は、テストを先に書ける領域です。

### 6.8 1回で全部やろうとしていないか

今回の要望は、運用機能・UI・演出が混ざっています。  
1本の巨大変更より、以下のように分割した方が安全です。

- GM管理機能
- UIレイアウト調整
- 行動順ロジック整理
- Resolve演出改善

## 7. 推奨スコープ分割

実装チケットに分けるなら、以下が扱いやすいです。

### チケットA: GM管理機能

- バフ付与/解除API
- アイテム増減API
- 権限チェック強化
- GM用モーダルUI

### チケットB: 戦闘UI整理

- スロット表示サイズ / 位置調整
- タイムライン欄のUI非表示

### チケットC: 行動順ルール整理

- 同速仕様の明文化
- 必要なら再ロール方式へ変更
- tiebreak表示追加

### チケットD: Resolve演出改善

- フローティングテキストのレイヤー修正
- バフ付与の演出対応
- ResolveFlowPanelの立ち絵表示
- 広域-合算の複数立ち絵表示

## 8. 最終判断

今回の要望は、**「無理な大改修」ではなく、既存の土台を伸ばして実装できる範囲** にあります。  
特に以下は、既存実装の再利用率が高く、費用対効果が良いです。

- GM用バフ/アイテム管理
- スロット表示の視認性改善
- フローティングテキストの視認性改善
- Resolve中の立ち絵表示

一方で、`timeline` は内部進行にも使っているため、今回は削除対象を UI に限定し、内部データは維持する方針です。  
また、GM運用機能に着手する前に、サーバー側の権限チェックを先に補強することを推奨します。
## 9. 2026-03-17 UI修正の実施結果

Manual14 の UI 系要望については、2026-03-17 時点で以下を実装済みとする。

### 9.1 実装済み項目

- スロット表示の拡大と上方配置
  - `static/css/modules/visual_map.css`
  - Select/Resolve 中のスロット番号を見やすくするため、バッジサイズを拡大し、トークン上部へ退避した。
- スロット番号と状態異常アイコンの干渉軽減
  - `static/css/modules/visual_map.css`
  - バッジの高さを再調整し、右上の状態異常アイコン帯と重なりにくい配置へ変更した。
- 矢印の始点・終点の視認性改善
  - `static/js/visual/visual_arrows.js`
  - 矢印のアンカーをスロット数字の中心から少し外した位置へ寄せ、数字を隠さず、かつ離れすぎない終点に調整した。
- タイムラインUIの非表示化
  - `static/css/modules/visual_battle.css`
  - 画面上の `#visual-timeline-area` は非表示にした。内部の `timeline` データや進行順ロジックは維持している。
- Resolve 画面の圧縮
  - `static/css/modules/visual_battle.css`
  - カード余白、フォント、立ち絵サイズ、下部サマリを再構成し、マッチ結果画面が縦に伸びすぎないよう圧縮した。
- Resolve 中の立ち絵表示
  - `static/js/battle/components/ResolveFlowPanel.js`
  - attacker / defender の立ち絵、および `mass_summation` 参加者の簡易表示を追加した。
- 同速情報の補助表示
  - `static/js/battle/components/ResolveFlowPanel.js`
  - `tiebreak` は現在表示中の Resolve 対象に限って補助表示するよう整理した。
- フローティングテキストの戦闘中抑制
  - `static/js/visual/visual_map.js`
  - `select / resolve_mass / resolve_single / round_end` 中はフローティングテキストを出さないよう変更した。戦闘開始時に一斉表示される問題の回避が目的である。

### 9.2 反映済みとみなす範囲

- Manual14 由来の UI 改善として、今回完了したのは以下の範囲である。
  - スロット表示調整
  - タイムラインUI整理
  - Resolve 表示改善
  - フローティングテキスト整理
- 一方で、GM 専用 API や権限チェック強化のようなサーバ側要望は本節の完了対象には含めない。

### 9.3 ドキュメント統合メモ

- UI特化の一時計画書 `manuals/18_Manual14_UI_Focused_Implementation_Plan.md` の内容は、本追補および恒常仕様書へ統合した。
- 恒常仕様として残す内容は `manuals/08_SelectResolve_Spec.md` と `manuals/06_Visual_Battle_Architecture.md` に反映する。
- したがって、今後 UI 修正の参照元は `14` の実施結果要約と `06/08` の恒常仕様を正本とする。

### 9.4 フローティングテキストの最終実装方針

- フローティングテキストは、最終的に「平時の数値変化補助」に用途を限定する。
- `select / resolve_mass / resolve_single / round_end` 中は表示しない方針を維持する。
- 戦闘中の主表示は `ResolveFlowPanel` とログを正本とする。
- バフ付与や状態異常付与を戦闘中のマップ上フローティングへ拡張しない。
- 将来、戦闘中の段階表示を増やす場合は、マップ上オーバーレイではなく `ResolveFlowPanel` 内演出として追加する。
