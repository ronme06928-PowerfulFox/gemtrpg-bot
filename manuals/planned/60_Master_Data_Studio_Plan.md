# 計画60：マスターデータ管理画面（スキル・バフ・用語図鑑の編集をアプリで行う）

作成日: 2026-11-04
状態: Phase 1（PR60-1・PR60-2）完了（2026-11-06）。管理画面の UI は試作で確定（2026-11-07）。Phase 2（PR60-3〜PR60-5）完了（2026-11-08、§5.4・§5.5）。Phase 2 の追補（PR60-6：関連用語と別名を選んで入れる、§5.6）も完了（2026-11-08）。Phase 3 はバフ（3a）とスキル（3b）の2段に分け、論点を決めた（2026-11-08、§8 Phase 3 論点1〜7）。3a（PR60-7・PR60-8）は完了（2026-11-08、§5.7・§5.8）。3a は完了（2026-11-08）。3b の PR分割と実装詳細は §5.9・§5.10（PR60-9〜PR60-12）。Phase 6 は完了（2026-11-10、§5.12・§5.13）。UI 改修と本番で使ってみての直し（PR60-16〜19）は完了（2026-11-11、§5.14・§5.15）。コストの呼び名と補正を付けない印（PR60-20、§5.17）も完了（2026-11-11）。威力の見込み（PR60-21、§5.18）も完了（2026-11-13）。効果のリクエスト（PR60-22、§5.19）も完了（2026-11-14）。文章の読み取りの直し（PR60-23、§5.16）は完了。次は効果から文章を作る（PR60-24）。残りは §6 の検討事項（1回ぶつける・勝率は計画63へ移した）。一括編集の手段は必要になったら決める。[マスターデータベース・プロジェクト](../projects/master_database/README.md)の段階1。

## 1. 目的

今 Google Sheets で行っているスキル・バフ・用語図鑑などの管理を、アプリの中の専用画面で行えるようにする。新しいスキルを作る・直す・確かめるまでの手間を下げ、サーバーのメンバーも権限の範囲で作成に加われるようにする。

あわせて、新しい効果タイプを足すときに、実行・入力画面・検査・説明文がばらばらに直す必要のある今の作りを、1か所の定義から揃う形に変える。

## 2. 今の作り（2026-11-04 調査）

- **取り込み**：スキルは `manager/data_manager.py` が gspread（サービスアカウント）で Sheets を読む。バフ・用語図鑑・アイテム・特殊パッシブ・輝化スキル・召喚テンプレートは、各 `manager/*/loader.py` が Sheets の公開CSVを読む。どれも JSON キャッシュ（`data/cache/`）に書き、実行時はキャッシュを読む。反映には `python app.py --update` と push が要る。
- **効果タイプ**：実行側は `manager/battle/effect_handlers/` の各モジュールの `HANDLERS` を `EFFECT_HANDLERS` にまとめる（計画29）。`CUSTOM_EFFECT` だけは `plugins.EFFECT_REGISTRY` を使う。
- **JSONビルダー**：`CharaCreator/json_definition_builder.html`（約2700行）。効果タイプの一覧 `TYPES` を手で書いている（336行目）。バフなどの参照データ `CharaCreator/json_builder_reference_data.js` は 2026-04-05 に作った写しのままで、今のデータとずれうる。文章から JSON を作る機能と、その監査API `/api/json_nl_builder_audit` がある。
- **検査**：`manager/json_rule_v2.py`（strict）と `manager/skill_catalog_validation.py`（lint、計画31）。
- **試し撃ちに使える部品**：戦闘シミュレータ `manager/sim/`（計画30、F03）。
- **権限**：アカウント（計画26・36）と、アプリ管理者権限 `is_app_admin`（F01 Part 1-B）がある。マスターデータの編集に関する権限はまだ無い。
- **全体から参照される辞書**：`all_skill_data` は多くの本番モジュールから直接参照されている（計画45 §12-5）。ルームごとに別のデータを持たせるには、引き方を関数へまとめる改修が要る。

## 3. 構想（4つの柱）

### 3.1 効果タイプのスキーマ（土台）

各ハンドラの横に、その効果タイプの説明を値で持たせる。中身は、項目名・型・必須かどうか・説明・例・説明文の型。

```python
SCHEMAS = {
    "APPLY_STATE": {
        "label": "状態を付与",
        "fields": {
            "state": {"type": "state_ref", "required": True},
            "value": {"type": "int", "required": True},
        },
        "summary": "{target}に{state}を{value}付与",
    },
}
```

`EFFECT_HANDLERS` と同じように `EFFECT_SCHEMAS` へまとめ、`/api/effect_schemas` で配信する。これを次の所が使う。

- JSONビルダー：手書きの `TYPES` をやめ、入力欄をスキーマから作る。
- 検査：必須項目の抜け、存在しない状態・バフIDの参照を見つける。
- 説明文：「対象に出血を3付与」のような文を作り、管理画面・ツールチップ・用語図鑑で使う。
- テスト：`EFFECT_HANDLERS` と `EFFECT_SCHEMAS` のキーが一致することを確かめる（片方だけ足すと落ちる）。
- 区分：各効果タイプに「メンバーが使ってよいか」などの区分を持たせ、計画41 Phase 1 の記法の区分表の正本にする（§8 論点9）。

新しい効果タイプを足す手順は「ハンドラ＋スキーマ＋テスト」になり、入力画面は直さずに追従する。この柱は管理画面を作らなくても、今のビルダーと検査に効く。

### 3.2 管理画面と DB 化

アプリの中に管理画面を作り、マスターデータの正本を Sheets から DB へ移す。

- **画面**：今のアプリ（`index.html`）の中の大型ワークスペース。プリセット管理ワークスペース（E02 Part 10・11）と同じ作りで、入口はロビーの「マスターデータ」ボタン（全員に表示）（§8 UI論点1）。
  - 閲覧は3ペイン（左：種類と絞り込み、中央：一覧、右：詳細）。編集のときだけ一覧と詳細をたたみ、左に入力・右に文章・JSON・プレビュー・1回ぶつけてみるの2列にする。承認は「承認待ち」の絞り込み（アプリ管理者だけ）から、公開中の版と下書きの差分を同じ2列で見せる（§8 UI論点2）。
  - スキルは専用の画面で扱う。見た目と操作は同じ3ペインで、左の列を Sheets と同じカテゴリ（ID の頭：Ps・Pb・Pp・Ms・Mb・Mp・D・B・C・E）と状態の絞り込みにする。マスターデータ画面の「スキル」から入り、「← マスターデータ」で戻る。編集・承認の並びはほかの種類と共通で、承認待ちの絞り込みはそれぞれの画面の分だけを出す（§8 プレビュー確認1）。
  - 入力は「フォーム」「JSON」「文章から作る」のタブ。フォームが主で、JSON は直接書き換えられる（§8 UI論点3）。
  - 今の JSON ビルダーは、Phase 3 でスキルを管理画面で編集できるようになった時点で消す（§8 UI論点4）。
  - 見た目は試作（`npm run catalog-preview`、§5.3）で確定した（2026-11-07、§8 UIの進め方）。

- **保存の形**：`preset_resources` とは別に、同じ形（種類＋安定した ID＋中身の JSON＋版）のテーブルを3つ作る（§8 論点10）。
  - `catalog_entries`：公開中の版。種類・ID・中身・`revision`・廃止の印・更新者。
  - `catalog_drafts`：下書き。種類・対象の ID（新規は `X-`）・中身・作成者・状態（下書き／承認待ち／却下）・元にした `revision`。
  - `catalog_history`：公開のたびに版の写しを残す。前の版に戻すときは、その写しを公開し直す。
  - 参照のつながりは表に保存せず、必要なときに中身の JSON から計算する。参照の検査と「どこで使われているか」は、プリセットとも共通の関数にする。

- **権限**：閲覧は全員、提案はアプリ管理者が指名した「制作者」、承認はアプリ管理者（`is_app_admin`）。ユーザーに制作者の印を1つ足し、ユーザー管理画面で付け外しする（§8 論点2）。下書きは制作者とアプリ管理者だけが見られ、公開したデータは今と同じく全員が見られる（§8 論点3）。
- **下書きと公開**：メンバーは下書きを作る。承認者が差分を見て公開する。公開でメモリ上の辞書とキャッシュを入れ替え、再起動や push なしで反映する。つながっている画面には読み直しを知らせ、戦闘中のルームでは次に使った時点から新しい定義になる。ルームのログや画面の表示は出さない（§8 論点7、Phase 3 論点3）。
- **ID**：新しいデータの下書きは仮の ID（`X-` で始まる）で作る。承認のときに承認者が正式な ID を付け、その仮の ID を参照しているほかの下書きも書き換える。公開したデータに `X-` の ID が混ざっていたら、検査でエラーにする（§8 論点4、計画45 §12-1）。スキルの下書きは作るときにカテゴリを選び、承認で付ける正式な ID はそのカテゴリの頭（`Ps-` など）の次の番号にする（§8 プレビュー確認1）。公開した後は ID を変えられない。消す代わりに「廃止」の印を付け、新しく選ぶ一覧からは外し、すでに使っているキャラやプリセットではそのまま動かす（§8 論点4-補）。
- **履歴**：行ごとに版を残し、誰がいつ何を変えたかを見られ、前の版に戻せるようにする。
- **書き出し**：公開時に JSON を書き出し、バックアップとリポジトリへの取り込みに使う。
- **相互参照**：あるバフや用語を使っているスキルの一覧、廃止したときの影響を見られるようにする。
- **文章と JSON**：今のビルダーの決まった言い回しを読み取る機能を移し、逆向きにスキーマの説明文で JSON から文章を作って、両方を並べて見せる。食い違えばすぐ気づけるようにする。LLM はアプリに入れず、自由な文章からの作成は外の AI エージェントが API で下書きを作る形にする（§8 論点8）。

Git でメンバーに編集してもらう案は、ハードルを下げる目的に合わないため主な経路にしない（§6-1）。

### 3.3 試し撃ち

下書きのスキルを、出す前に確かめられるようにする（§8 論点5）。

- **計算だけのプレビュー**：戦闘の処理は動かさず、ダイスの式から威力の最小・平均・最大を、スキーマの説明文で付く状態やコストを出す。入力しながら常に見せる。
- **1回ぶつけてみる**：→ **計画60から外し、[計画63 戦闘マスター](63_Battle_Master_Plan.md)へ移した（2026-11-12）。** 以下は移す前の記録。下書き1つと相手のキャラ・スキルを選び、本物の処理で1回の対決を解決した結果（ダイス・威力・勝敗・付いた状態・ログ）を見せる。`manager/sim/` は動かす間アプリ全体の部品を差し替えるため、本番のプロセスの中では動かさない。**別のプロセス**で動かし、そのプロセスの辞書にだけ下書きを重ねる。本番のメモリが足りるかは、実装の前に測る。
- 短い戦闘を何回か回す集計は作らない。今の CLI（F03）をローカルで使う。

### 3.4 未対応の効果のリクエスト

今の効果タイプで表現できない効果が出たとき、管理画面から文章と例を添えて「リクエスト」を出せるようにする。管理者はそれをもとにハンドラとスキーマを足す。スキーマが配信されると、管理画面に新しい効果タイプが出る。

リクエストは管理画面の中の一覧に置く（§8 論点6）。状態は「受付・対応中・実装済み・見送り」で、元になった下書きにひもづける。中身を計画書や Issue のたたき台としてコピーできるボタンを付け、開発のときはそれを AI エージェントに渡して作業に入れるようにする。

## 4. 対象範囲

対象とするもの：

- 効果タイプのスキーマと配信API、それを使う JSON ビルダーと検査
- 管理画面（一覧・編集・下書き・承認・公開・履歴）
- マスターデータの DB 化と、Sheets からの初回取り込み
- 試し撃ち
- 未対応の効果のリクエスト

対象としないもの：

- 新しい効果タイプそのものの追加（個別に行う）
- キャラクター作成ツール（CharaCreator）の作り直し
- モバイル版

## 5. 実装段階

| 段階 | 状態 | 内容 | 単独で役に立つか |
|---|---|---|---|
| Phase 1 | 完了 | 効果タイプのスキーマ・`/api/effect_schemas`・キー一致のテスト | 立つ。ビルダーのずれをなくした（旧ビルダーは3bで廃止） |
| Phase 2 | 完了 | 用語図鑑をDBへ移し、下書き・承認・公開・履歴を作る | 立つ |
| Phase 3a | 完了 | バフの移行、参照と検査、枠内への描画 | 立つ |
| Phase 3b | 完了 | スキルの移行、専用画面・効果フォーム・文章から作る、旧ビルダーの廃止 | 立つ |
| Phase 4 | 威力の見込み（PR60-21、§5.18）は完了（2026-11-13）。1回ぶつける・勝率は計画63へ移した | 編集と閲覧に最小・平均・最大、条件で変わる威力を表示 | 立つ |
| Phase 5 | 効果のリクエスト（PR60-22、§5.19）は完了（2026-11-14） | 依頼の提出・取り下げ、管理者の回答、依頼文のコピー | 立つ |
| Phase 6 | 完了 | アイテム・特殊パッシブ・輝化スキル・召喚テンプレートの移行と管理画面、Sheets取得の廃止 | データ移行の完了 |
| UI 改修 | PR60-16〜19 完了（2026-11-11、§5.14・§5.15） | 管理画面の区切り・色・状態と操作の見やすさ。試作で比べて形を決めた（§6-3） | 立つ |
| コストの呼び名・補正を付けない印 | 完了（PR60-20、2026-11-11、§5.17） | 項目名 `使用時効果` を `コスト` に変え、特記の決まった文で補正を付けないスキルを示す | 立つ |
| 効果から文章を作る | PR60-23（読み取りの直し）完了。PR60-24 は試作の後に詳細（§5.16） | 効果の設定からゲームの書き方の文章を作る。食い違いの注意にも使う | 立つ |

番号順ではなくPhase 6を先行して完了した。データ移行はPhase 1〜3b・6で完了した。移行後のUI改修とPhase 4・5も完了した。残る検討事項は§6に分けて記す。

始める時期：Phase 1 はいつでも始めてよい。Phase 2 以降は計画46の主な作業が落ち着いてから、としていたが、ユーザーの判断で Phase 2 から先に進めている（§8 論点9）。

推奨PR分割と実装詳細は、各 Phase の着手の前に書く。Phase 1 の分は §5.1・§5.2、Phase 2 の分は §5.4・§5.5、Phase 3a の分は §5.7・§5.8、Phase 3b の分は §5.9・§5.10、Phase 3 の追補2は §5.11、Phase 6 の分は §5.12・§5.13、UI 改修の分は §5.14・§5.15、効果から文章を作るは §5.16。

### 5.1 Phase 1 の推奨PR分割

Phase 1 完了（2026-11-06）。PR60-1：22効果タイプ・9カスタム効果のスキーマ、説明文生成、認証なしの配信APIとテストを追加。PR60-2：`/json_builder` と参照APIを追加し、効果・参照一覧をAPI読み込みへ切り替えた。旧参照JSを削除した。

| PR | 内容 | 画面の変化 |
|---|---|---|
| PR60-1 | 効果タイプのスキーマ（`EFFECT_SCHEMAS`）と `CUSTOM_EFFECT` の名前ごとのスキーマ（`CUSTOM_EFFECT_SCHEMAS`）、説明文を作る関数、`/api/effect_schemas`、テスト | なし |
| PR60-2 | ビルダーをアプリから配信し（`/json_builder`）、効果タイプの一覧・`CUSTOM_EFFECT` の一覧・参照データを API から読む。参照データの写し `json_builder_reference_data.js` を消す | ビルダーの効果タイプと参照データが、今のデータと一致する |

スキーマを使った保存前の検査（必須項目の抜け・存在しない ID）は Phase 1 に含めない。管理画面で検査の結果を見せる Phase 3 で作る。

### 5.2 Phase 1 の実装詳細

#### PR60-1：スキーマと配信 API

完了（2026-11-06）。以下の契約を実装。`internal` は当初の割り当てを維持し、戦闘処理・ビルダーは変更していない。実装済み仕様は B01 の追加手順と C01 §17 を参照。

1. **スキーマの置き場**：各ハンドラモジュール（`manager/battle/effect_handlers/` の `action_effects.py`・`buff_effects.py`・`power_effects.py`・`stack_resources.py`・`state_effects.py`）の `HANDLERS` の横に `SCHEMAS` を置く。`__init__.py` で `EFFECT_HANDLERS` と同じように `EFFECT_SCHEMAS` へまとめる。`CUSTOM_EFFECT` はハンドラが `game_logic` 側にあるため、`EFFECT_SCHEMAS["CUSTOM_EFFECT"]` は `__init__.py` に直接書く。
2. **スキーマの形**（1つの効果タイプにつき1つ）：

    ```python
    SCHEMAS = {
        "APPLY_STATE": {
            "label": "状態を付与",              # 日本語の短い名前
            "description": "対象に状態異常を付与する。",
            "internal": False,                 # True は内部専用（ビルダーの一覧に出さない）
            "fields": {
                "state_name": {"type": "state_ref", "required": True, "label": "状態"},
                "value": {"type": "int", "required": True, "label": "量"},
            },
            "summary": "{target}に{state_name}を{value}付与",
            "example": {"timing": "HIT", "type": "APPLY_STATE", "target": "target", "state_name": "出血", "value": 3},
        },
    }
    ```

    - `fields` のキーは effect のキー名そのもの。`data` の中は `"data.count"` のようにドットでつなぐ。`timing`・`type`・`target`・`condition` などの全タイプ共通のキーは書かない。
    - `type` は `int`・`number`・`string`・`bool`・`json` と、参照の型 `state_ref`・`buff_ref`・`skill_ref`・`summon_ref`・`glossary_ref` のいずれか。
    - 各キーの名前・必須かどうか・意味は、ハンドラのコードと C01 を読んで書く。例の `state_name` は形を示すための仮のもの。実際のキー名はコードに合わせる。
    - `internal`：今のビルダーの `TYPES`（`json_definition_builder.html` 336行目）に無い `FORCE_UNOPPOSED`・`APPLY_FISSURE_BUFFED` は `True`、ほかは `False` で始める。コードを読んで実は作成者が使うべきだと判断したものは、変えずに報告する。
    - `summary` の `{…}` には `fields` のキーと `target` だけを使う。
    - `example` は、そのまま effect として動く1件にする。
3. **`CUSTOM_EFFECT_SCHEMAS`**：`plugins/__init__.py` の `EFFECT_REGISTRY` の横に、名前ごとに `label`・`description`（今のビルダーの `CUSTOM_EFFECT_REFS` の `summary` を移す）・`fields`（同じく `keys` を上の形に直す）を置く。
4. **説明文を作る関数**：`manager/battle/effect_handlers/` に `render_effect_summary(effect: dict) -> str` を置く。`summary` の `{…}` を effect の値で埋める。`{target}` は `self`→「自分」、`target`→「対象」のような日本語にする（対応表は関数の横に置く）。値が無い所は `?` にする。使うのは Phase 3 以降だが、テストで全スキーマの `example` を通すためにここで作る。
5. **API**：`app.py` の `/api/get_*` と同じ並びに `GET /api/effect_schemas` を足す。返す形は `{"effect_types": EFFECT_SCHEMAS, "custom_effects": CUSTOM_EFFECT_SCHEMAS}`。認証は付けない（論点3：公開したデータは全員が見られる）。
6. **テスト**（`tests/test_effect_schemas.py`）：
    - `EFFECT_SCHEMAS` のキーが、`EFFECT_HANDLERS` のキーに `CUSTOM_EFFECT` を足したものと一致する（ハンドラだけ、スキーマだけを足すと落ちる）。
    - `CUSTOM_EFFECT_SCHEMAS` のキーが、`EFFECT_REGISTRY` のキーと一致する。
    - 各スキーマに `label`・`description`・`internal`・`fields`・`summary`・`example` がある。`fields` の各 `type` が決まった値のどれか。`summary` の `{…}` が `fields` か `target` にある。`example["type"]` が自分のキーと同じ。
    - 各 `example` が `manager/json_rule_v2.py` の strict の正規化を通る（スキルの `rule_data` の形に包んで通す）。
    - 各 `example` を `render_effect_summary` に通すと `?` を含まない。
    - `/api/effect_schemas` が 200 で、上の2つの辞書を返す。

#### PR60-2：ビルダーを API から読む形にする

完了（2026-11-06）。`/json_builder` で効果タイプ20種・カスタム効果9種・バフ候補53件を確認した。撮影は2枚のみ、画像ファイルは保存していない。APIの公開配信・現行データの反映・両APIの読み込み待ち・失敗時の初期化停止をテストした。他の手書き一覧と文章読み取り処理は変更していない。実装済み仕様は C01 §5、開き方は A02 §4.5 を参照。

1. **配信**：`app.py` に `/json_builder` を足し、`CharaCreator/json_definition_builder.html` を返す（`/chara_creator` と同じ書き方）。ビルダーは今、どこからも配信されておらず、ファイルを直接開くと同じオリジンの API（`/api/get_glossary_data`・`/api/json_nl_builder_audit`）が届かない。配信すればこれも届くようになる。
2. **参照データの API**：`GET /api/json_builder_reference` を足す。返す形は、今の `window.JSON_BUILDER_REFERENCE` と同じ `buff_refs`・`skill_refs`・`summon_refs`・`state_refs`（`generated_at` は不要）。`extensions.py` の `all_buff_data`・`all_skill_data` と、`manager/summons/loader.py` の `load_summon_templates()` から、その場で作る。`state_refs` は今の写しの9つをサーバー側の定数にする。
3. **ビルダーの読み込み**：
    - `<script src="./json_builder_reference_data.js">` を消し、`CharaCreator/json_builder_reference_data.js` を削除する。
    - 起動時に `/api/effect_schemas` と `/api/json_builder_reference` を読み終えてから、今の初期化を走らせる。
    - `TYPES` は `effect_types` のうち `internal` が `false` のキーから作る。並び順は今の `TYPES` の順を保てるなら保つ。
    - `CUSTOM_EFFECT_REFS` は `custom_effects` から作る（表示に使う `value`・`summary`・`keys` の形に直す）。
    - 読み込みに失敗したら、画面の上にエラーを出して止める。古い写しへの切り戻しは作らない（後方互換を持たない方針）。
4. **テストの直し**：`tests/test_origin_boon_name.py` は、消える `json_builder_reference_data.js` を読んでいる。`/api/json_builder_reference` の `buff_refs` を確かめる形に直す。`tests/test_json_builder_encoding_guard.py` は、残す文字列の確認がそのまま通ることを確かめる。新しく、`/json_builder` が 200 を返すことと、`/api/json_builder_reference` が今のバフ図鑑と同じ ID を返すことのテストを足す。
5. **確認**：アプリを起動して `/json_builder` を開き、効果タイプの一覧（今の20個と同じ）、`CUSTOM_EFFECT` の一覧、バフの候補が出ることを確かめる。ビルダーは `static/` のバンドルの外なので、`npm run build` は要らない。

#### 触らないもの

- 戦闘の処理（ハンドラの中身、`game_logic`）の動き。ハンドラのモジュールには `SCHEMAS` を足すだけ。
- ビルダーのほかの手書きの一覧（`TIMINGS`・`TARGETS`・`POWER_OPS`・`COND_*`）と、文章から JSON を作る読み取りの処理。
- `CharaCreator/GEMDICEBOT_CharaCreator.html`、`static/` のフロントエンド。

#### 資料の更新

- PR60-1：B01（effect の処理）に「新しい効果タイプは、ハンドラ・`SCHEMAS`・テストを足す」手順を書く。C01 に `/api/effect_schemas` を書く。
- PR60-2：C01 §5 と A02 のビルダーの開き方を `/json_builder` に直す。`manuals/projects/app_foundation/repository_inventory.md` のビルダーの行（配信されていないという記述）を直す。
- Phase 1 を終えても計画60は残す。この §5.1・§5.2 に「完了」と結果の要約を書く。

### 5.3 管理画面のプレビュー（Phase 2 の前）

状態：**完了・UI 確定（2026-11-07）**。1回目の試作をユーザーが確かめ、スキルをカテゴリごとに分けた専用の画面にする直し（§8 プレビュー確認1）を入れて作り直し、確定した。680px のスキル編集が縦に長い点は、PC Web 版が中心のためこのままとする。Phase 2 以降の画面は、この試作の見た目に揃える。

UI の決定（§8 UI論点1〜4）を見た目で確かめるための試作。本番のバンドルには入れず、ユーザーが確かめてから Phase 2 の実装に入る（§8 UIの進め方）。中身は §8 のプレビュー論点1〜3で決めた。

#### 作り方

- `npm run catalog-preview` で、`/_local/catalog_preview/catalog_preview.html` を1枚作る。作りは `npm run resolve-preview`（`scripts/resolve_preview/`）に倣う。
- 置き場：`scripts/catalog_preview/`（`build.mjs`・`page.js`・`page.css` と、必要ならデータの読み込みを分けたファイル）。`package.json` の `scripts` に `catalog-preview` を足す。
- 見た目：本番の CSS（`static/dist/app.bundle.css`）を埋め込み、プリセット管理ワークスペースのクラス（`bo-workspace` など、E02 Part 10・11）を使える所は使う。足りない分だけ `page.css` に `cat-` で始まるクラスで書く。フォントは `static/index.html` と同じ読み込みにする。
- データ：ビルドのときに `data/cache/` のキャッシュ（スキル・バフ・特殊パッシブ・用語・アイテム・輝化スキル・召喚テンプレート）を読み、HTML に埋め込む。効果タイプのスキーマ（`EFFECT_SCHEMAS`・`CUSTOM_EFFECT_SCHEMAS`）と、全スキルの効果の説明文（`render_effect_summary`）は、Python の小さな書き出しスクリプト（`scripts/catalog_preview/export_schemas.py`）で JSON にして渡す（`resolve_preview` の `embed_icons.py` と同じ呼び方）。
- 編集の見本は、スキル `Pb-13 ダッシュ`（効果4つ・コストあり）と用語 `W-08 荊棘`（リンク7つ）。
- 下書き・承認待ち・却下・廃止の状態は、見本として決めた数件に付ける。例：`Pb-13` を承認待ち（基礎威力と効果の値を1か所ずつ変えた下書き）、`W-08` を下書き、ほかに廃止を1件。ほかは公開中。

#### 画面の上の操作（プレビューだけの帯）

- 場面：「閲覧」「スキル」「編集」「承認」（「スキル」はプレビュー確認1で追加）
- 幅：「広い（1280px）」「980px」「680px」。選んだ幅の枠の中にワークスペースを描く。

#### 場面

1. **閲覧**（3ペイン）
    - 枠の左上に、ロビーの「マスターデータ」ボタンを小さく見せる。
    - 左：種類（スキル・バフ・パッシブ・用語・アイテム・輝化スキル・召喚と、それぞれの件数）、絞り込み（状態、タグ）、検索。「スキル」を押すと、下のスキル専用の画面に移る。
    - 中央：一覧のカード（ID・名前・分類・状態の印・説明の1行）。
    - 右：選んだデータの詳細。スキルは効果の説明文の並び、項目、JSON（たためる）、使われている所、履歴（見本2行）。「編集」「廃止」のボタン（押しても何も起きない）。使われている所は、バフなら参照しているスキル、用語ならリンクしている用語のように、キャッシュから計算して出す。
2. **編集**（2列）
    - 一覧と詳細をたたみ、左に入力、右に文章・JSON・プレビュー・1回ぶつけてみる。上に「戻る」。
    - 左の入力は「フォーム」「JSON」「文章から作る」のタブ。
      - フォーム：スキル本体の項目（ID・デフォルト名称・分類・距離・属性・取得コスト・基礎威力・ダイス威力・チャットパレット・タグ・使用時効果・発動時効果）と、コスト、効果のカード。効果のカードは `timing`・効果タイプ・`target` の選択と、選んだ効果タイプのスキーマの `fields` から作った欄。効果タイプを選び直すと欄が入れ替わる。効果タイプの選択肢は `internal` が `false` のものを `label` 付きで並べる。`condition` は JSON の欄。用語のときは用語の項目（表示名・分類・短い説明・長い説明・フレーバー・リンク・別名）。
      - JSON：今のデータを整形して見せる（フォームとの行き来は作らない）。
      - 文章から作る：今のビルダーと同じ3つの欄とボタン（押しても何も起きない）。
    - 右：効果の説明文、JSON（読むだけ）、計算だけのプレビュー（ダイスの式から威力の最小・平均・最大を出す）、1回ぶつけてみる（相手を選ぶ欄とボタン。押すと、決めておいた見本の結果を出す）。
    - 下：「下書きを保存」「承認を申請」（押しても何も起きない）。
3. **承認**
    - 左の絞り込みの「承認待ち」（アプリ管理者だけに見える前提）を選んだ状態。
    - 編集と同じ広い2列で、左に公開中の版、右に下書きを並べ、変わった項目に印を付ける。
    - 下に、却下の理由の欄と「承認」「却下」のボタン（押しても何も起きない）。

#### スキル専用の画面（プレビュー確認1で追加）

- マスターデータ画面と同じ3ペインの見た目で、見出しを「スキル」にし、左上に「← マスターデータ」を置く。
- 左の列：カテゴリを4つの群に分けて並べ、それぞれの件数を出す。その下に状態の絞り込みと検索。
    - 物理：Ps 斬撃・Pb 打撃・Pp 貫通
    - 魔法：Ms 斬撃・Mb 打撃・Mp 貫通
    - 防御・補助：D 防御・回避・B 宝石の加護・C 共通
    - 敵：E
- カテゴリは ID の頭の文字で決める。初めは「すべて」ではなく、先頭のカテゴリ（Ps）を選んだ状態で開く。
- スキルの編集（`Pb-13`）と承認は、この画面の中で開く。「戻る」はこの画面の一覧に戻る。編集の見本の切り替え（スキルと用語）はやめ、用語の編集はマスターデータ画面の用語から開く。
- 場面の切り替えの帯に「スキル」を足す（閲覧・スキル・編集・承認）。編集と承認はスキル専用の画面の中の場面として見せ、用語の下書き（`W-08`）はマスターデータ画面の閲覧から見られれば足りる。

#### 狭い幅

- 980px：閲覧の詳細を一覧の下に回す。
- 680px：閲覧を縦に積み、編集と承認の2列も縦に積む。横スクロールを出さない。

#### 確認と片付け

- 確認は軽くてよい。3つの場面を「広い」と「680px」で撮影し、合わせて数枚で足りる。撮影は確認後に消し、`catalog_preview.html` だけを残す。
- テストは書かない（本番に入らない試作のため）。`npm run build` は要らない（本番の JS・CSS を変えない）。
- AGENTS.md には、`npm run catalog-preview` と置き場 `/_local/catalog_preview/` を書き足してある（2026-11-07）。

#### 触らないもの

- 本番のコード（`static/`・`app.py`・`manager/` など）と、ビルドの成果物（`static/dist/`）。

### 5.4 Phase 2 の推奨PR分割（完了）

用語図鑑（83件、すべて `W-`）だけを DB へ移し、管理画面で下書き・承認・公開・履歴・廃止を回す。権限と公開の型をここで固め、Phase 3 でバフ・スキルを同じ型に載せる。

| PR | 内容 | 画面の変化 |
|---|---|---|
| PR60-3 | DB の3つの表、用語の保存と読み込み（起動時に DB から辞書へ、DB が空なら今のキャッシュから初回取り込み）、Sheets からの用語の取り込みを外す、制作者の印（列・ユーザー管理のボタン・ログイン時の返り値） | ユーザー管理に「制作者」の付け外しが出る。用語の中身は変わらない |
| PR60-4 | 管理用の HTTP API（一覧・履歴・下書き・申請・承認・却下・廃止・版を戻す）、公開時の知らせ（ソケット）、用語図鑑の画面の読み直し | なし（API だけ） |
| PR60-5 | 管理画面（ロビーの「マスターデータ」ボタン、閲覧・編集・承認）、資料の仕上げ | 管理画面で用語を作れる |

PR60-3完了（2026-11-07）：用語の正本をDBへ移し、保存・下書き・履歴の土台と制作者の指名を追加した。PR60-4完了（2026-11-08）により、制作者・アプリ管理者はHTTP APIで下書き・申請・承認を操作できる。PR60-5完了（2026-11-08）により、ロビーの「マスターデータ」で用語の閲覧・下書き・承認・履歴・復元・廃止を操作できる。

### 5.5 Phase 2 の実装詳細（完了）

#### Phase 2 で決めたこと

§8 の決定を用語に当てはめるときに、次のように決めた。

- **API は HTTP**：管理の操作は `routes/` の Blueprint にし、`session_required` で守る。外の AI エージェントが API で下書きを作る形（§8 論点8）にそのまま使える。プリセット管理のようなソケットにはしない。
- **下書きは1件の公開データにつき1つ**：同じ用語に2つ目の下書きは作れない（今ある下書きを開く）。誰が直しているかが分かり、承認での食い違いが起きない。新規の下書き（`X-`）は数の制限を設けない。
- **下書きは制作者とアプリ管理者の全員が見られる**。書き換え・申請・取り下げは作った人とアプリ管理者だけ。
- **用語の公開ではルームのログを出さない**：用語は戦闘の処理に使わないため。ソケットの知らせは出す（バフ・スキルでもログは出さないことにした。§8 Phase 3 論点3）。
- **用語の項目を絞る**：今のキャッシュで1件も使っていない `icon`・`extra_json` と、廃止の印で置き換わる `is_enabled` は持たない。
- **廃止と版を戻すのは、アプリ管理者がその場で行う**（下書きと承認を通さない）。どちらも版を1つ進め、履歴に残す。
- **「文章から作る」のタブは Phase 3 で足す**：今のビルダーの読み取りはスキルの効果のためのもので、用語には使わない。Phase 2 の入力は「フォーム」と「JSON」。

#### PR60-3：保存の土台と制作者の印

完了（2026-11-07）。初回83件と履歴83件の取り込み、DBからの配信、制作者の指名・解除を実装。新規公開ではlinksと文章中の仮IDをほかの下書きで置き換え、未解決の仮IDが残る公開は拒否する。下書きの保存は不完全なフォームを許容し、申請・承認で項目と参照を検査する。承認待ちの下書きは書き換えず、却下後の書き換えでdraftへ戻す。管理API・公開通知・管理画面は後続PR。全件テストは1708件成功・45件スキップ（上限1200秒、364秒）。ローカルの公開APIで83件、ユーザー管理で指名・解除を確認し、撮影2枚は確認後に破棄した。

1. **表**（`models.py`）。形は §3.2 のとおり。
    - `catalog_entries`：`id`・`kind`（`'glossary'` など）・`entry_id`（`W-08` など）・`payload`（JSON）・`revision`（1から）・`deprecated`（真偽）・`updated_by`（`users.id`、消えたら NULL）・`updated_at`。`(kind, entry_id)` は一意。
    - `catalog_drafts`：`id`・`kind`・`target_id`（公開データの ID、新規は `X-` と16進8桁）・`payload`・`status`（`draft`・`pending`・`rejected`）・`base_revision`（新規は NULL）・`created_by`（`users.id`、消えたら NULL）・`reject_reason`・`created_at`・`updated_at`・`submitted_at`。`(kind, target_id)` は一意（1件につき下書き1つ）。
    - `catalog_history`：`id`・`kind`・`entry_id`・`revision`・`payload`・`deprecated`・`action`（`import`・`publish`・`deprecate`・`undeprecate`・`restore`）・`actor_user_id`・`draft_id`（公開のもとになった下書き、無ければ NULL）・`created_at`。`(kind, entry_id, revision)` は一意。
    - 表は `db.create_all()` で作る。列の追加の仕組み（`manager/db_migration.py`）は使わない（新しい表のため）。
2. **種類の定義**（`manager/catalog/kinds.py`）：種類ごとに、ID の形（用語は `^W-\d{2,}$`）・項目の定義・中身の検査・辞書の形への変換を1か所に置く。Phase 3 で種類を足すときは、ここに足す。
    - 用語の項目：`display_name`（必須）・`category`（必須。今の7つ：ルール・タイミング・効果・バフ・状態異常・スキルタグ・デバフ）・`short`・`long`・`flavor`・`links`（用語 ID の並び）・`synonyms`（文字の並び）・`sort_order`（整数か NULL）。
    - 検査：必須の抜け、型の違い、`links` の行き先が公開中の用語か `X-` の下書きにない、`links` に自分自身。決まった項目以外のキーはエラー。
    - 辞書の形：今の `all_glossary_data` と同じ `{"W-08": {"term_id": "W-08", "display_name": …, "links": […], …}}`。廃止したものも辞書に残し、`"deprecated": true` を付ける（すでに書かれたリンクを壊さない。§8 論点4-補）。
3. **保存と読み込み**（`manager/catalog/repository.py`）：
    - `load_kind_into_memory(kind)`：`catalog_entries` から辞書を作り、`extensions` の辞書を `clear()`＋`update()` で入れ替える。
    - `seed_kind_if_empty(kind)`：その種類の行が1つも無いとき、`data/cache/glossary_catalog_cache.json` から取り込む。各行を `revision=1` で入れ、履歴に `action='import'` を残す。
    - 下書きの作成・書き換え・申請・取り下げ・承認・却下、廃止、版を戻すの関数。権限の判断は呼ぶ側（PR60-4 の API）で行い、ここでは中身と版だけを扱う。
    - **承認**：下書きの `base_revision` が公開中の `revision` と違えば、食い違いのエラーにする（そのあいだに別の公開があった）。新規は承認者が正式な ID を渡す。ID の形・重複を確かめ、ほかの下書きの中身にある同じ `X-` の ID を正式な ID に書き換える。公開したら `revision` を1つ進め、履歴を残し、下書きを消し、`load_kind_into_memory` を呼ぶ。公開する中身に `X-` の ID が残っていたらエラー。
    - **版を戻す**：指定した版の履歴の中身で公開し直す（版は戻さず、1つ進める）。
4. **起動時の読み込み**：`manager/data_manager.py` の `init_app_data` の「用語辞書データの読み込み」を、`seed_kind_if_empty('glossary')` と `load_kind_into_memory('glossary')` に置き換える。`app.py` の `get_glossary_data` の「辞書が空なら読み込む」も同じ関数にする。
5. **Sheets の取り込みを外す**：`python app.py --update` の手順から用語を外し、7段階を6段階にする。`manager/glossary/loader.py` の CSV の取得とキャッシュの書き込みを消す（`manager/glossary/` は空になるなら消す）。`data/cache/glossary_catalog_cache.json` は初回取り込みの元として残す。
6. **制作者の印**：
    - `users` に `is_catalog_author`（真偽、既定は偽）を足す。今ある表への列の追加なので、`manager/db_migration.py` の `user_column_specs` に足す。
    - `manager/user_manager.py`：`is_catalog_author(user_id)`（アプリ管理者も真にする）と `set_catalog_author(user_id, enabled)`。`get_all_users()` の返り値に `is_catalog_author` を足す。
    - `routes/admin.py`：`POST /api/admin/set_catalog_author`（アプリ管理者だけ）。
    - `static/js/user_management.js`：各ユーザーの行に「制作者に指名」「制作者を外す」のボタンと「制作者」の印。
    - `routes/account.py`：`is_app_admin` を返している所に `is_catalog_author` も足し、`static/js/main.js` で `window.currentUserIsCatalogAuthor` に入れる。
7. **テスト**：
    - 種類の定義：用語の検査（必須の抜け・知らない項目・存在しないリンク・自分へのリンク・`X-` のリンク）。
    - 保存：初回取り込みで83件・履歴83件。2回目の起動では取り込まない。下書きを承認すると版が進み、辞書が入れ替わる。`base_revision` の食い違いでエラー。新規の承認で正式な ID になり、ほかの下書きの `X-` が書き換わる。廃止しても辞書に残り `deprecated` が付く。版を戻すと中身が戻り、版は進む。
    - 制作者：アプリ管理者は制作者として扱う。`/api/admin/set_catalog_author` はアプリ管理者以外は 403。
    - `--update` の手順に用語が無い。

#### PR60-4：管理用の API と公開の知らせ

完了（2026-11-08）。管理HTTP API12本を追加し、保存・承認は既存repositoryへ委譲。公開用語・スキル・バフの参照箇所の検索、正式ID候補、成功後の全接続へのcatalog_updatedと用語の読み直し（読み終わるまで古い中身を表示）を実装した。キャッシュ読み込み中の古い応答は、失効後の内容を上書きしない。制作者の指名解除後は、その人の下書き操作も拒否する。対象テスト75件と全件テスト1763件成功・45件スキップ（上限1200秒、423秒）。複数のSocket接続への通知、公開APIへの反映、キャッシュの古い応答の排除もテストで確認した。管理画面は未着手。

1. **Blueprint**：`routes/catalog.py` に置き、`app.py` の Blueprint の登録に足す。すべて `session_required`。`<kind>` は `kinds.py` にある種類だけを受け付ける（Phase 2 は `glossary`）。
2. **エンドポイント**：

    | メソッドとパス | 誰が | 中身 |
    |---|---|---|
    | `GET /api/catalog/<kind>` | ログインした全員 | 公開中の一覧（ID・中身・版・廃止の印・更新者の名前・更新日時）。制作者とアプリ管理者には下書きの一覧（状態・作った人・元の版・却下の理由）も付ける |
    | `GET /api/catalog/<kind>/<entry_id>/history` | 全員 | 履歴の一覧（版・操作・誰が・いつ・中身） |
    | `GET /api/catalog/<kind>/<entry_id>/references` | 全員 | 使われている所。用語は、ほかの用語の `links` と、スキル・バフの文章の中の `[[W-08|…]]` の書き方 |
    | `POST /api/catalog/<kind>/drafts` | 制作者 | 下書きを作る。`{target_id}` で公開データの写しから、`{}` なら新規（`X-`） |
    | `PUT /api/catalog/drafts/<id>` | 作った人・アプリ管理者 | 中身を書き換える。却下された下書きは書き換えると `draft` に戻る |
    | `POST /api/catalog/drafts/<id>/submit` | 作った人・アプリ管理者 | 検査を通れば `pending` にする。通らなければ検査の結果を返す |
    | `DELETE /api/catalog/drafts/<id>` | 作った人・アプリ管理者 | 取り下げる（下書きを消す） |
    | `POST /api/catalog/drafts/<id>/approve` | アプリ管理者 | 公開する。新規は `{entry_id}` で正式な ID を渡す |
    | `POST /api/catalog/drafts/<id>/reject` | アプリ管理者 | `{reason}` を付けて `rejected` にする |
    | `POST /api/catalog/<kind>/<entry_id>/deprecate` | アプリ管理者 | `{deprecated: true/false}` で廃止の印を付け外しする |
    | `POST /api/catalog/<kind>/<entry_id>/restore` | アプリ管理者 | `{revision}` の版の中身で公開し直す |
    | `GET /api/catalog/<kind>/next_id` | アプリ管理者 | 新規の承認の欄に入れる、次の正式な ID の候補（用語は `W-` の最大の番号＋1） |

    - 書き込みの返り値は、変わった後の公開データか下書き。食い違い・検査のエラーは 409・422 と、どの項目がなぜかを返す。
3. **使われている所**：`manager/catalog/references.py` に、中身の JSON から参照を探す関数を置く（§3.2：表に保存せず計算する）。Phase 3 でバフ・スキルの参照を足す。
4. **公開の知らせ**：公開・廃止・版を戻すのたびに、全員へ `catalog_updated`（`{kind, entry_id, revision}`）を送る。`static/js/common/glossary_ui.js` は `kind` が `glossary` ならすぐに `/api/get_glossary_data` を読み直す。読み終わるまでは古い中身を出し続ける（用語名や説明が消えないように）。
5. **テスト**：各エンドポイントの権限（ログインなし・一般・制作者・アプリ管理者）、下書きの流れ（作る→書き換え→申請→却下→書き換え→申請→承認）、1件に2つ目の下書きを作れない、検査の失敗で申請できない、公開で `catalog_updated` を送る、`/api/get_glossary_data` が公開後の中身を返す。

#### PR60-5：管理画面

完了（2026-11-08）。試作に揃えた用語専用の3ペイン・フォーム/JSON編集・承認差分を実装。アプリ管理者・制作者・一般の3人で既存用語の編集→申請→承認、却下→再編集→再申請、新規の仮ID→正式ID W-83 の公開と別の利用者の用語説明への即時反映を確認した。広い幅と680pxで確認し、左右の差分の行高も一致した。5分のHTTPキャッシュで古い説明が残る問題は、用語読み込みのcache: no-cacheによる再検証で解消。API・サーバーの変更なし。スキル・計算・試し撃ち・文章から作るは未実装のまま。撮影と確認用DB・サーバー補助は確認後に削除済み。対象の入力・API・キャッシュ検査8件成功、全件テスト1770件成功・45件スキップ（上限1200秒、364秒）。

1. **置き場**：`static/js/master_data/` にクラシックスクリプト（API の呼び出し・画面・用語のフォームなどに分ける）、`static/css/modules/master_data.css`。`scripts/build_frontend.mjs` の `CLASSIC_SCRIPTS` に足し、`styles.css` に `@import` を足し、`npm run build`。
2. **入口**：`static/js/main.js` の `renderRoomPortal` に「マスターデータ」ボタンを全員に出す（「マイキャラクター」と同じ並び）。押すと `openMasterDataWorkspace()`。
3. **見た目**：試作（`npm run catalog-preview`）に揃える。プリセット管理ワークスペースのクラス（`bo-workspace` など）を使い、足りない分は `cat-` で始まるクラスにする（試作の `page.css` から要る分を移す）。
4. **場面**：
    - 閲覧：3ペイン。左の種類は、DB にある種類だけを出す（Phase 2 は「用語」だけ）。絞り込みは分類・状態・検索。制作者とアプリ管理者には「下書き」「承認待ち」「却下」の状態も出る。右の詳細に、項目・リンク・使われている所・履歴。制作者には「編集」「新しく作る」、アプリ管理者には「廃止」「この版に戻す」のボタン。
    - 編集：2列。左に「フォーム」「JSON」のタブ。JSON は直接書き換えられ、正しく読めればフォームへ反映し、読めなければエラーを出してフォームには戻さない（§8 UI論点3）。右に、用語図鑑のツールチップと同じ見た目のプレビュー・リンク先の名前・JSON。下に「下書きを保存」「承認を申請」「取り下げ」。検査のエラーは項目の横に出す。
    - 承認：アプリ管理者の「承認待ち」から開く。左に公開中の版、右に下書き、変わった項目に印。新規なら正式な ID の欄（`next_id` を入れておく）。却下の理由の欄と「承認」「却下」。
    - `catalog_updated` を受けたら、開いている一覧を読み直す。
5. **狭い幅**：980px 以下で詳細を下に、680px 以下で縦に積む（§8 UI論点2）。
6. **確認**：ローカルで、アプリ管理者・制作者・一般の3人で、用語を1件直して申請→承認し、別の画面の用語図鑑のツールチップが新しい中身になることを確かめる。新規の用語も1件、`X-` から正式な ID で公開する。撮影は数枚で、確認後に消す。

#### 触らないもの

- バフ・スキルなど用語以外の取り込み（Phase 3 以降）。
- 今の JSON ビルダー（Phase 3 で消す）。
- 用語図鑑の表示（`glossary_ui.js` の見た目・`action_dock.js` の一覧）。読み直しの1か所だけを直す。

#### 資料の更新

- PR60-3：F01（アカウントの権限）に制作者の印、A02 に制作者の指名の仕方。A04 の用語の管理の説明を「Sheets で直して `--update`」から「アプリの管理画面」へ（画面ができるまでは API のこと）。`manuals/projects/app_foundation/repository_inventory.md` の `manager/glossary/` の行。
- PR60-4：F01 に管理用 API と権限の表。
- PR60-5：E02 に管理画面の Part を足す。A02・A04 に画面での作り方。
- Phase 2 を終えても計画60は残す。この §5.4・§5.5 に「完了」と結果の要約を書く。

### 5.6 Phase 2 の追補：関連用語と別名を選んで入れる（Phase 3 の前）

本番で管理画面を使ってみて、関連用語と別名を JSON の配列で手書きする入力が使いにくいと分かった（§8 追補1）。画面だけを直し、API・サーバー側・保存の形は変えない。

#### PR60-6：関連用語と別名の入力

完了（2026-11-08）。関連用語をID・名前・別名で検索して札に追加し、上下矢印・Enterでも選べるようにした。自分自身・追加済み・廃止を候補から除き、既存の廃止・未登録IDは印付きで残す。別名はEnter/追加と×で操作し、空欄・重複を増やさない。ローカルの制作者で2件追加→1件削除、別名追加・保存、開き直し後の札・JSON・プレビューの一致を確認。対象11件成功、全件テスト1773件成功・45件スキップ（上限1200秒、423秒）。撮影2枚・確認用DB・サーバー補助は削除済み。API・サーバー側・保存形式は未変更。

1. **関連用語**（`links`）：
    - 今のリンクを、ID と名前の札（例：「W-01 出血氾濫 ×」）で並べる。× で外す。並びは足した順。
    - 札の下に検索の欄を置く。ID・名前・別名で絞った候補を出し、押すと足す（キーボードでも選べる）。
    - 候補は、公開中で廃止していない用語だけ。自分自身と、すでに足した用語は出さない。
    - すでに足してある ID が廃止・未登録のときも札は出し、印を付ける（外すかどうかは書く人が決める）。
2. **別名**（`synonyms`）：札で並べる。文字を打って Enter（または「追加」）で足し、× で外す。空の文字と重複は足さない。
3. **JSON のタブ**：今のまま。フォームと JSON の行き来も今と同じ。
4. **入れないもの**：相手の用語にも同時にリンクを付ける機能（相手の下書きも作ることになり重い）、札の並べ替え。
5. **置き場**：`static/js/master_data/glossary.js` の `form`・`parseField` と、`workspace.js` の入力のつなぎ。札と候補の見た目は `master_data.css` に `cat-` で始まるクラスで足す。`npm run build`。
6. **テスト**：`tests/test_master_data_frontend.py` に、候補の絞り込み（廃止・自分・足し済みを除く、ID・名前・別名で当たる）、足す・外す、別名の空と重複を足さない、を足す。
7. **確認**：ローカルで制作者として用語を1件開き、関連用語を検索で2つ足して1つ外し、別名を足して保存し、JSON のタブとプレビューに反映されることを確かめる。撮影は数枚で、確認後に消す。
8. **資料**：E02 の管理画面の Part と A04 の作り方を直す。終わったらこの節に「完了」と結果の要約を書く。

### 5.7 Phase 3a の推奨PR分割（バフ）

バフ（53件、すべて `Bu-`）を DB へ移し、用語と同じ画面で下書き・承認・公開・履歴・廃止を回す。検査の問題の一覧と、バフが使われている所の表示をここで作り、3b のスキルでそのまま使う（§8 Phase 3 論点1）。

| PR | 内容 | 本番での見え方 |
|---|---|---|
| PR60-7（完了） | バフの種類の定義、DB からの読み込み（DB が空ならキャッシュから初回取り込み）、Sheets からのバフの取り込みを外す、戦闘・アイテムの読み先を辞書にそろえる、検査の問題の一覧（API）、バフが使われている所 | バフの中身は変わらない。管理 API で `buff` を扱えるようになる |
| PR60-8（完了） | 管理画面に「バフ」を足す。画面を「渡された枠の中に描く」作りに分ける。問題の一覧と使われている所を画面に出す | マスターデータの左の列に「バフ」が出る |

### 5.8 Phase 3a の実装詳細

#### Phase 3a で決めたこと

§8 の決定をバフに当てはめるときに、次のように決めた。

- **内部名（`name`）は公開した後に変えられない**：戦闘はバフを内部名で数え、キャラが持っているバフやスキルの `buff_name` も内部名で書かれているため（ID と同じ扱い。§8 論点4-補）。画面に出す名前は `display_name` で変えられる。内部名はバフの中で重ならないようにする。
- **検査の流れは Phase 2 の作りに合わせる**：下書きの保存は止めず（書きかけのフォームも保存できる）、問題は一覧で見せる。申請で形と参照先がないことを止め、承認で仮の ID も止める。参照先が廃止は注意だけ（§8 Phase 3 論点4）。
- **効果（`effect`）は JSON の欄で書く**：今の53件のうち効果を持つのは12件で、形もプラグインの名前・`stat_mod`・`power_bonus` の並び・`state_receive_bonus` の並びとまちまち。フォームの中に JSON の小さな欄を置き、`effect.type` が `plugin` のバフだけ、その ID のプラグインがコードにあるかを確かめる（戦闘はプラグインをバフの ID で呼び、`effect.name` は使っていない）。効果のフォーム化は 3b のスキルの効果と合わせて考える。
- **使われている所はメモリ上のデータとキャッシュから探す**：スキル・アイテム・特殊パッシブ・輝化スキルの中の `buff_id`（と `buff_name`）。プリセット（`preset_resources`）の中は 3a では探さない（計画61 と共通の参照の検査で扱う）。

#### PR60-7：バフの保存と検査

完了（2026-11-08）。バフ53件と初回履歴53件のDB取り込み、段階別の問題一覧、管理APIのbuff対応、承認・廃止・復元後の共有辞書への反映、参照箇所の検索、公開通知での読み直しを実装。Sheets更新は5段階にし、旧バフローダーを削除した。全件テストは1796 passed・45 skipped（442.67秒、タイムアウト1200秒）。ローカルの隔離DBとHTTPサーバーで、起動時の53件取り込み、公開APIと従来キャッシュの完全一致、制作者の下書き保存・申請→管理者の承認（版2）→`get_buff_by_id`と公開APIへの反映を確認した。確認用DBは削除済み。

補足：プラグインの検査は、確認のあとでバフの ID で引く形へ直した（`plugins/buffs/` の `BUFF_IDS` に ID が無ければ、承認で止める。新規の `X-` の下書きは注意だけ）。戦闘プラグインは変更していない。単独のスキルlintも暗黙のファイル読み込みに依存していたため、DBからバフ辞書を準備する入口を追加し、隔離DBで138スキル・エラー0件とJSON出力を確認した。管理画面とその分割はPR60-7の対象外とし、PR60-8で対応した。

変更ファイル（このPRの作業分）：
- 保存・起動・配信・CLI：`app.py`、`manager/buff_catalog.py`、`manager/buffs/__init__.py`、`manager/buffs/loader.py`、`manager/catalog/kinds.py`、`manager/catalog/references.py`、`manager/catalog/repository.py`、`manager/data_manager.py`、`plugins/items/buff.py`、`routes/catalog.py`、`scripts/skill_catalog_tool.py`。
- 通知・ビルド：`static/dist/app.bundle.js`、`static/dist/app.bundle.js.map`、`static/index.html`、`static/js/main.js`。
- 資料：`manuals/implemented/C01_JSON_Definition_Master.md`、`manuals/implemented/F01_Operations_Manual.md`、`manuals/planned/60_Master_Data_Studio_Plan.md`。
- テスト：`tests/conftest.py`、`tests/legacy/test_buff_plugin.py`、`tests/test_apply_buff_per_n.py`、`tests/test_data_manager_lint_hook.py`、`tests/test_effect_schemas.py`、`tests/test_gyoma_chikuryoku_skill_behaviors.py`、`tests/test_lost_hp_apply_buff_per_n.py`、`tests/test_motion_fx_pr7_server.py`、`tests/test_ms13_consume_gain_apply_buff.py`、`tests/test_non_action_battle_objects.py`、`tests/test_phase3_strict_rehearsal.py`、`tests/test_shindou_state_receive_bonus.py`、`tests/test_skill_catalog_smoke.py`、`tests/test_skill_catalog_tool_cli.py`、`tests/test_skill_catalog_tool_lint.py`、`tests/test_catalog_buff.py`、`tests/test_catalog_buff_frontend.py`。

1. **種類の定義**（`manager/catalog/kinds.py`）に `buff` を足す。
    - ID の形 `^Bu-\d{2,}$`、頭 `Bu-`。辞書の名前 `all_buff_data`、辞書の ID の項目 `id`（今の `{"Bu-00": {"id": "Bu-00", "name": …}}` の形のまま）。
    - 項目：`name`（必須）・`display_name`・`description`・`flavor`・`effect`（オブジェクト、既定は `{}`）・`default_duration`（整数。`-1` は解除されるまで、`1` 以上はラウンド数。既定は `1`）。分類は持たない。
    - 初回取り込みの元のキャッシュを種類ごとに持たせる（用語は `glossary_catalog_cache.json`、バフは `buff_catalog_cache.json`）。`seed_kind_if_empty` の `GLOSSARY_CACHE_FILE` の決め打ちをやめ、種類の定義から引く。
2. **検査を「問題の一覧」を返す形にする**（`manager/catalog/kinds.py` か新しい `manager/catalog/inspection.py`）。
    - `inspect_payload(kind, payload, *, entry_id, stage)` が `[{"level": "error"|"warning", "field": …, "message": …}]` を返す。`stage` は `draft`（保存）・`submit`（申請）・`approve`（承認）。
    - 形：必須の抜け・知らない項目・型の違い・用語の分類・バフの `default_duration` が `-1` か1以上でない・バフの `effect.type` が `plugin` なのに、その ID が `plugins/buffs/` の `BUFF_IDS` に無い（新規の `X-` の下書きは申請まで注意、承認で止める）・内部名がほかのバフと重なる・公開済みのバフの内部名を変えた。
    - 参照先がない：用語の `links`（今の検査）と、すべての種類の文字の項目の `[[W-xx|…]]` が公開中の用語にも `X-` の下書きにもない。
    - 参照先が廃止：`links` と `[[W-xx|…]]` の行き先が廃止の用語（注意）。
    - 仮の ID：今の `validate_public_payload` と同じ（承認のときだけ止める）。
    - 申請は「形」「参照先がない」の error で止め、承認はそれに「仮の ID」を足して止める。保存は止めない。今の `validate_payload` と `validate_public_payload` はこの関数の上に作り直し、二重の検査を残さない。
3. **API**（`routes/catalog.py`）：`kind` に `buff` を受ける。下書きの JSON に `problems`（`inspect_payload` の `stage="submit"` の結果）を付ける。検査で止めたときの 422 の `errors` は今と同じ形にする。
4. **起動時と配信**：
    - `manager/data_manager.py` の `init_app_data` のバフの読み込みを、`seed_kind_if_empty('buff')` と `load_kind_into_memory('buff')` に置き換える。
    - `app.py` の `get_buff_data` は `all_buff_data` を返す（空なら上の2つを呼ぶ。用語と同じ）。
5. **読み先を辞書にそろえる**：公開で辞書が入れ替わっても戦闘が古い中身を読まないようにする。
    - `manager/buff_catalog.py` の `get_buff_by_id` はキャッシュのファイルを読んでいる。`all_buff_data` を引く形にし、ファイルの更新時刻を見るキャッシュの仕組みは消す。
    - `plugins/items/buff.py` の `buff_catalog_loader.get_buff` も `all_buff_data` を引く。
    - 廃止したバフも辞書に残し、`"deprecated": true` を付ける。戦闘はこれまでどおり使える（§8 論点4-補）。
6. **Sheets の取り込みを外す**：`python app.py --update` の手順からバフを外し、6段階を5段階にする。`manager/buffs/loader.py` の CSV の取得・キャッシュの書き込み・ローダーのクラスを消す（`manager/buffs/` は空になるなら消す）。`data/cache/buff_catalog_cache.json` は初回取り込みの元として残す。
7. **使われている所**（`manager/catalog/references.py`）：`find_references('buff', 'Bu-05')` が、スキル（`all_skill_data`、`特記処理` の JSON の中も）・アイテム・特殊パッシブ・輝化スキルの中で `buff_id` がその ID のもの、`buff_name` がその内部名のものを返す。用語の参照（`links` と `[[W-xx]]`）の探し方は今のまま。
8. **画面側の読み直し**：`static/js/main.js` の `catalog_updated` で `kind === 'buff'` のとき `/api/get_buff_data` を読み直して `window.buffCatalogData` を入れ替える（読み終わるまで古い中身を使う。用語と同じ）。
9. **テスト**：
    - 種類の定義：バフの検査（必須・型・`default_duration`・知らないプラグイン・内部名の重なり・公開後の内部名の変更）、`[[W-xx]]` の参照先がない（error）と廃止（warning）、保存は止めず申請と承認で止まる。
    - 保存：初回取り込みで53件・履歴53件。2回目の起動では取り込まない。承認で `all_buff_data` が入れ替わり、`get_buff_by_id` が新しい中身を返す。
    - 使われている所：スキルの `buff_id` と `buff_name` が見つかる。
    - `--update` の手順にバフが無い。
    - 今の用語のテストがそのまま通る。

#### PR60-8：管理画面にバフを足す

完了（2026-11-08）。`mountCatalogWorkspace(container, options)`へ枠内の描画・操作を分け、窓側は生成・終了・フォーカス制御を担当する。種類別定義にバフを追加し、種類を受け取るAPIクライアント、フォーム・JSON・プレビュー、編集と承認の問題一覧、参照元の種類・ID・名前を実装した。API・サーバー側は変更していない。全件テストは1801 passed・45 skipped（414.16秒、タイムアウト1200秒）。ビルド・文字コード・文字化け・差分検査も成功。

隔離DBのローカルアプリで制作者としてBu-00の表示名・説明・持続を改訂して申請し、新規バフも作成・申請。管理者として廃止用語W-08の参照の注意を確認したうえでBu-00を承認（版2）、新規をBu-53で公開（版1）した。53件の一覧、内部名の読み取り専用、効果JSONのエラー表示・入力保持、解除までと3ラウンドの持続、参照元の表示を確認した。広い幅と680pxで編集・承認を撮影して確認し、広い承認では左右全項目の上端・高さの一致も確認。確認用DB・4枚の画像・サーバーと検証ログは確認後に削除した。UIの決定を変える必要はなかった。

変更ファイル（PR60-8）：

- 画面とビルド元：`scripts/build_frontend.mjs`、`static/css/modules/master_data.css`、`static/js/master_data/catalog_api.js`、`static/js/master_data/glossary.js`、`static/js/master_data/workspace.js`、`static/js/master_data/buff.js`。
- 生成物：`static/dist/app.bundle.css`、`static/dist/app.bundle.css.map`、`static/dist/app.bundle.js`、`static/dist/app.bundle.js.map`、`static/index.html`。
- テスト：`tests/test_master_data_frontend.py`。
- 資料：`manuals/implemented/A04_Glossary_Tutorial.md`、`manuals/implemented/C01_JSON_Definition_Master.md`、`manuals/implemented/E02_UI_Component_Specs.md`、`manuals/implemented/F01_Operations_Manual.md`、`manuals/planned/60_Master_Data_Studio_Plan.md`。


1. **画面の作りを分ける**（`static/js/master_data/workspace.js`）：
    - `mountCatalogWorkspace(container, options)` が、渡された枠の中に閲覧・編集・承認の場面を描き、`{ refresh, destroy }` を返す。
    - `openMasterDataWorkspace()` は重ねて開く窓を作り、その中の枠を `mountCatalogWorkspace` に渡すだけにする（閉じるときに `destroy`）。
    - 中で `document` 全体から要素を探している所は、渡された枠の中から探す形に直す。
2. **種類の切り替え**：左の列の「種類」に「用語」「バフ」を並べ、押すと一覧・絞り込み・フォーム・プレビューが入れ替わる。種類ごとの違い（項目・絞り込み・プレビュー・一覧の列）は `glossary.js` と同じ形の `buff.js`（`window.CatalogBuff`）に置き、`workspace.js` は種類の定義を受け取って描くだけにする。`catalog_api.js` は種類を引数にとる。
3. **バフのフォーム**：内部名・表示名・説明・フレーバー・持続（「解除まで」か数を選ぶ）・効果（JSON の小さな欄。読めないときはその欄の下にエラー）。公開済みのバフを直すときは、内部名の欄を読むだけにする。JSON のタブは今と同じ。
4. **バフのプレビュー**：表示名・持続・説明・フレーバーを、戦闘の画面のバフの説明と同じ見た目で出し、その下に効果の JSON を出す。
5. **問題の一覧**：編集の右の列と承認の差分の上に、`problems` を「エラー」「注意」に分けて出す。0件なら「問題はありません」。
6. **使われている所**：詳細の「参照箇所」に、バフのときはスキル・アイテムなどの名前と ID を並べる。
7. **見た目**：今の `cat-` の部品を使い、足りない所だけ `master_data.css` に足す。`npm run build`。
8. **テスト**：`tests/test_master_data_frontend.py` に、種類の切り替え、バフのフォームの読み書き（持続の「解除まで」と数、効果の JSON の読めないとき）、公開済みの内部名を変えられない、問題の一覧の出し分け、`mountCatalogWorkspace` を渡した枠の中だけに描くこと、を足す。
9. **確認**：ローカルで制作者として、バフを1件直して申請し、アプリ管理者として承認する。新しいバフを1件作り、正式な ID（`Bu-53`）で公開する。廃止の用語を説明の `[[W-xx]]` に書いたときに注意が出ることを確かめる。撮影は数枚で、確認後に消す。

#### 触らないもの

- スキル・アイテムなどほかの種類の取り込み（3b・Phase 6）。
- 今の JSON ビルダー（3b の最後で消す）。ビルダーのバフの参照（`/api/json_builder_reference`）は `all_buff_data` を読んでいるので、そのまま新しい中身になる。
- 戦闘の中のバフの処理（`plugins/buffs/`・`STATIC_BUFFS`・名前の型で作るバフ）。

#### 資料の更新

- C01：バフの定義の正本が DB になり、管理画面で直すこと。項目と `default_duration` の意味。
- E02：管理画面の Part に、種類の切り替え・バフのフォーム・問題の一覧・使われている所。
- F01：起動時の読み込みと `--update` の5段階、バフの Sheets を読まなくなったこと。
- A04：管理画面の作り（`mountCatalogWorkspace`、種類ごとのファイル）。
- 終わったら、この節の各 PR に「完了」と結果の要約を書く。

### 5.9 Phase 3b の推奨PR分割（スキル）

スキル（138件）を DB へ移し、スキル専用の画面で下書き・承認・公開を回す。手元のファイルと道具は、本番から取ってくるコマンドで本番に合わせる（§8 Phase 3b 論点1）。最後に今の JSON ビルダーを管理画面へ吸収して消す（§8 Phase 3 論点6）。

| PR | 内容 | 本番での見え方 |
|---|---|---|
| PR60-9（完了） | 本番から取ってくるコマンド（`python app.py --pull`）。用語・バフ・スキルの公開 API から `data/cache/` を書き換え、手元では DB も入れ替える | 本番は変わらない |
| PR60-10 | スキルの種類の定義・DB からの読み込み・検査・使われている所。効果の共通の項目をスキーマに足す。Sheets からのスキルの取り込みを外す | スキルの中身は変わらない。管理 API で `skill` を扱えるようになる |
| PR60-11 | スキル専用の画面（カテゴリの列・効果のフォーム・チャットパレットの「項目から作る」・JSON から文章のプレビュー） | マスターデータに「スキル」が出る |
| PR60-12 | 「文章から作る」のタブ。今の JSON ビルダー（`/json_builder`）を消す | ビルダーのページがなくなり、管理画面のタブになる |

PR60-9 はほかと関係なく先に出せる。PR60-10 を本番に出す前に、最後に一度 `--update` で Sheets から取り込んでコミットしておく（本番の最初の取り込みは、リポジトリのキャッシュから行うため）。→ 済み（2026-11-08、PR60-10 の前のコミットで `--update` を実行。スキル138件・アイテム・輝化スキル・特殊パッシブ・召喚テンプレートとも、リポジトリのキャッシュと中身は同じだった）。

### 5.10 Phase 3b の実装詳細

#### Phase 3b で決めたこと

- **手元は本番から取ってくる**：`--pull` で本番の公開 API から `data/cache/` を書き換える。道具（シミュレーター・lint・確認用スクリプト）は今までどおりファイルを読む（§8 Phase 3b 論点1）。
- **チャットパレットは手で書く欄のまま、「項目から作る」と注意を足す**（§8 Phase 3b 論点2）。
- **辞書の形は今のまま**：戦闘・画面が読む `all_skill_data` は、今の `{"Ps-00": {"スキルID": "Ps-00", "チャットパレット": …, "特記処理": "<JSONの文字列>", "tags": […]}}` の形を保つ。DB の中身では `特記処理` をオブジェクトで持ち（検査とフォームで扱いやすい）、辞書へ入れるときに文字列にする。`tags` は保存せず、辞書へ入れるときに今の取り込みと同じ規則（分類・`特記処理.tags`・発動時効果の `[即時発動]`）で作る。
- **カテゴリは下書きに持たせる**：ID の頭（Ps・Pb・Pp・Ms・Mb・Mp・D・B・C・E）は分類・属性から決まりきらない（B・C・E があるため）。新しいスキルの下書きは作るときにカテゴリを選び、`catalog_drafts.id_prefix` に入れる。公開したスキルのカテゴリは ID の頭で分かる。
- **検査は今の厳しい読み取りを正本にする**：`特記処理` の形は、今 lint が使っている `extract_and_normalize_skill_rule_data(strict=True)` で確かめる。lint の相場の注意（`warn_catalog`）は、問題の一覧の「注意」に出す。

#### PR60-9：本番から取ってくるコマンド

完了（2026-11-08）。`python app.py --pull` を実装。`CATALOG_PULL_BASE_URL`（既定は本番）から3種類を取得・形の検査後、ファイルと用語・バフの公開DBへ一括反映する。下書き・既存履歴は保持し、中身か廃止の印が変わった行だけローカルの版を進めて取り込み（`import`）の履歴を残す。Renderでは拒否し、通常の起動・Sheets取得・HTTPサーバーの起動は行わない。取得・検査・反映の失敗時は既存データを保つ。復元も妨げられた場合は元の退避ファイルを残す。システムスキル（`SYS-`）はコードが正本で起動時に辞書へ足されるため、写さない。

全件テストは1827 passed・45 skipped（483.63秒、タイムアウト1200秒）。追加した26テストではHTTP・JSON・形の不正・ファイル反映・DB保存の失敗、復元時の退避保持、下書き・履歴保持、Render拒否、起動を省くこと、システムスキルを確認。ビルド・文字コード・文字化け・差分検査も成功。

本番への確認：初回は公開APIの`SYS-STRUGGLE`で検査が停止し、キャッシュ3ファイル・DB履歴が未変更であることを確認。システムスキルを扱うようにして再実行し、同期に成功した。用語83件・バフ53件・スキル139件を別途本番APIとJSONとして照合し、3ファイルと既存ローカルDBの用語・バフが一致した。下書きは実行前と同一。既存ローカルDBと同期済みファイルは残し、比較用の写し・テストの一時出力は確認後に削除した。

キャッシュの差分：`glossary_catalog_cache.json`は83件すべてから旧`icon`・`is_enabled`を外して`deprecated`を追加（ほかの値は同じ）。`buff_catalog_cache.json`は53件の値は同じでキー順・最終改行の整形だけ。`skills_cache.json`は138件の値は同じで、キー順が公開APIの返却順に揃った。

実装で分かった点：公開APIは通常のスキル138件だけでなく、コードで定義したシステムスキル（`SYS-STRUGGLE`）も返す。

確認のあとの直し（Claude）：①`--pull` はシステムスキルを除いて写す（`--update` と同じ138件になり、PR60-10 の取り込みで区別が要らない）。②履歴は新しい種類 `pull` を作らず、今ある `import`（画面は「取り込み」）を使う。履歴の表の制約の変更と SQLite の表の作り直しは消した（手元の DB の `pull` 136件は `import` に直した）。③中身と廃止の印が同じ行は飛ばし、版も履歴も増やさない。④DB が空のときの最初の取り込みで、キャッシュの廃止の印を読む（`--pull` のファイルには廃止の印が入りうるため）。

変更ファイル（PR60-9）：

- コマンド・保存・テスト：`app.py`、`manager/catalog/repository.py`、`models.py`、`manager/catalog/pull.py`、`tests/test_catalog_pull.py`。
- 生成物：`static/dist/app.bundle.js`、`static/dist/app.bundle.js.map`、`static/index.html`、`static/js/master_data/workspace.js`。
- 同期したキャッシュ：`data/cache/buff_catalog_cache.json`、`data/cache/glossary_catalog_cache.json`、`data/cache/skills_cache.json`。
- 資料：`manuals/implemented/F01_Operations_Manual.md`、`manuals/planned/60_Master_Data_Studio_Plan.md`。


1. `python app.py --pull`：本番の公開 API（`/api/get_glossary_data`・`/api/get_buff_data`・`/api/get_skill_data`）を読み、`data/cache/` の3つのファイルを書き換える。取ってくる先の URL は環境変数（無ければ本番の URL）。どれか1つでも読めないか形がおかしければ、何も書き換えずに失敗で終える。
2. 手元の DB の入れ替え：書き換えたあと、手元の DB のその種類の公開データを、ファイルの中身で入れ替える（中身が変わった行だけ版を進め、履歴は `action='import'` で残す。下書きは消さない）。Render の上（`IS_RENDER`）では、このコマンドを実行できないようにする。
3. スキルはまだ DB に無いので、PR60-9 の時点ではファイルの書き換えだけ（DB の入れ替えは用語とバフ）。PR60-10 でスキルも入れ替えの対象にする。
4. テスト：取ってきた中身でファイルが書き換わる、1つ失敗したら何も書き換えない、手元の DB が入れ替わり下書きは残る、Render の上では止まる（通信はモック）。
5. 資料：F01 に `--pull` の使い方（スキル・バフ・用語を直したあと、手元の道具を使う前やコミットの前に実行する）。

#### PR60-10：スキルの保存と検査（完了）

1. **種類の定義**に `skill` を足す。
    - ID の形 `^(Ps|Pb|Pp|Ms|Mb|Mp|D|B|C|E)-\d{2,}$`。辞書の名前 `all_skill_data`、辞書の ID の項目 `スキルID`。
    - 項目（キーは今のまま）：`デフォルト名称`（必須）・`チャットパレット`・`分類`（物理・魔法・補助・防御・回避）・`距離`（近接・遠隔・広域-個別・広域-合算・空）・`属性`（打撃・斬撃・貫通・空）・`取得コスト`・`基礎威力`・`ダイス威力`・`使用時効果`・`特記`・`発動時効果`（どれも文字）・`特記処理`（オブジェクト）。
    - 辞書へ入れるときの変換（`特記処理` を文字列に、`tags` を作る）を種類の定義に持たせ、`to_memory_entry` から呼ぶ。
    - 初回取り込みの元は `skills_cache.json`。取り込みでは `特記処理` の文字列をオブジェクトにし、`スキルID` と `tags` は捨てる。
2. **カテゴリと採番**：`catalog_drafts` に `id_prefix`（文字、空を許す）を足す（今ある表への列の追加なので `manager/db_migration.py`）。スキルの新規の下書きは `id_prefix` が必須。`GET /api/catalog/skill/next_id?prefix=Ps` はその頭の次の番号を返す。承認の正式な ID は、その頭で始まらなければ止める。
3. **効果の共通の項目**（§8 Phase 3 論点5）：`manager/battle/effect_handlers/` に `timing`・`target`・`condition` の定義を足し、`/api/effect_schemas` で配る。`timing` と `target` の選択肢は `manager/json_rule_v2.py` が許す値を正本にし、二重に書かない。`condition` は `source`・`param`・`operator`・`value`。
4. **検査**（`inspect_payload` に足す）：
    - 形：項目・型・選択肢。`特記処理` の厳しい読み取りの失敗（エラーの場所を `field` に入れる）。
    - 参照先がない：効果の `buff_id` が公開中のバフにも `X-` のバフの下書きにもない。`[[W-xx]]` は今のまま。
    - 参照先が廃止：`buff_id` の行き先が廃止のバフ（注意）。
    - 注意：チャットパレットが決まった形（`{基礎威力}{ダイス威力}+1d{物理補正|魔法補正} 【{ID} {デフォルト名称}】`、物理・魔法以外は補正の項なし）と違う。`buff_name` がバフにも決まったバフ（`STATIC_BUFFS`・名前の型）にもない。`warn_catalog` の相場の注意。
5. **使われている所**：スキルの ID を、ほかのスキル・アイテム・特殊パッシブ・輝化スキル・召喚テンプレートの中の値から探す（バフの探し方と同じ作り）。
6. **起動時と配信**：`init_app_data` のスキルの読み込みを `seed_kind_if_empty('skill')`＋`load_kind_into_memory('skill')` に。`get_skill_data` も同じ（空なら読み込む）。`--pull` でスキルも DB を入れ替える。システムスキル（`SYS-`、`manager/battle/system_skills.py`）は DB に入れない。`load_kind_into_memory('skill')` は辞書を入れ替えるので、入れ替えたあとに `ensure_system_skills_registered()` を呼び、公開のたびにシステムスキルが消えないようにする。
7. **Sheets の取り込みを外す**：`--update` からスキルと、スキルの lint のフック（検査は申請・承認でかかるようになる）を外し、4段階（アイテム・輝化スキル・特殊パッシブ・召喚テンプレート）にする。`fetch_and_save_sheets_data` と `load_skills_from_cache` の Sheets の部分を消す。シミュレーターなど手元の道具は、今までどおり `skills_cache.json` を読む。
8. **画面側の読み直し**：`catalog_updated` で `kind === 'skill'` のとき `/api/get_skill_data` を読み直して `window.allSkillData` を入れ替える（読み終わるまで古い中身。バフと同じ）。
9. **テスト**：初回取り込みで138件、辞書の形が今の `skills_cache.json` と一致する（`特記処理` の文字列は同じ中身の JSON、`tags` は同じ）。カテゴリと採番、検査の各項目、`buff_id` の `X-` が承認で正式な ID に置き換わる、`--update` が4段階、全件テストがそのまま通る。

実装結果（2026-11-08）：通常スキル138件をDBから配信する形にし、種類別の変換・検査・カテゴリ採番・参照箇所・共通効果項目を追加。管理APIの下書きに `id_prefix` と `problems` を返す。`--pull` もスキルDBを入れ替え、`--update` は4種類のみ。SYS-はDBへ保存せず、辞書の更新後に再登録する。ローカルHTTPで138件＋SYS-1件の配信、既存Ps-00の申請・承認、新規Ps-15の公開、SYS-保持を確認した。Sheetsの最終取り込みはこの作業では実行していない。`npm run build`・文字コード/文字化け/差分検査が成功。全件テスト（タイムアウト1200秒）は **1848 passed・45 skipped**（450.29秒）。参照値の項目名による除外を外した最終修正も対象テストで成功。

変更ファイル：`app.py`、`models.py`、`routes/catalog.py`、`manager/db_migration.py`、`manager/data_manager.py`、`manager/catalog/{kinds,skills,repository,references,pull}.py`、`manager/json_rule_v2.py`、`manager/battle/effect_handlers/__init__.py`、`manager/skill_catalog_warnings.py`、`scripts/skill_catalog_tool.py`、`static/js/main.js`、`static/index.html`、`static/dist/app.bundle.js` とそのmap、`tests/test_catalog_{skill,skill_frontend,pull}.py`、`tests/test_data_manager_lint_hook.py`、`tests/test_effect_schemas.py`、`tests/test_json_rule_v2_phase1.py`、C01・F01・本計画書。

#### PR60-11：スキル専用の画面（完了）

1. **入口**：マスターデータの種類の「スキル」から入り、「← マスターデータ」で戻る（§3.2）。`mountCatalogWorkspace` と同じく渡された枠の中に描く（`mountSkillWorkspace(container, options)`）。見た目と編集・承認の並びは用語・バフと共通にし、共通の部分は `workspace.js` から使い回す。
2. **左の列**：試作（§5.3 スキル専用の画面）のとおり、物理（Ps・Pb・Pp）・魔法（Ms・Mb・Mp）・防御・補助（D・B 宝石の加護・C 共通）・敵（E）の4つのまとまりと、状態の絞り込み。承認待ちはスキルの分だけ。
3. **フォーム**：
    - 本体の項目：名前・分類・距離・属性・取得コスト・基礎威力・ダイス威力・使用時効果・特記・発動時効果・チャットパレット（「項目から作る」ボタン）。新規の下書きはカテゴリを選ぶ。
    - `特記処理`：`power_bonus`・`cost`・`tags`・`target_scope` と効果の並び。効果は1つずつの札にし、効果タイプを選ぶとスキーマの項目の欄が出る。共通の `timing`・`target` は選択肢、`condition` は4つの欄（無しも選べる）。札の追加・削除・上下の入れ替え。フォームで表せない中身（4つの欄に収まらない条件など）は、その札に「JSON で編集」の印を出し、JSON のタブで書く。
    - JSON のタブは今と同じ（`特記処理` を含む中身全体）。
4. **プレビュー**：戦闘の宣言の画面と同じ見た目のスキルの札と、効果ごとに `render_effect_summary` の文（JSON から文章）を並べる。説明文を作る関数は `/api/effect_schemas` の `summary` から JS でも同じ規則で作る（`{target}` の言い換え表も配る）。
5. **問題の一覧と使われている所**：用語・バフと同じ。
6. **テスト**：カテゴリの切り替え、効果の札の追加・削除・入れ替え、効果タイプで欄が入れ替わる、`condition` の4つの欄、チャットパレットの「項目から作る」、フォームと JSON の行き来で中身が変わらない（今の138件で往復しても同じ）。
7. **確認**：ローカルで制作者として、既存のスキルの効果を1つ直して申請、アプリ管理者で承認。新しいスキルを Ps で作り、正式な ID（Ps の次の番号）で公開。撮影は数枚で、確認後に消す。

実装結果（2026-11-09）：共通workspaceへスキルの定義を追加し、`mountSkillWorkspace(container, options)` を用意した。4群10カテゴリ、新規のカテゴリ選択、効果の札と共通条件・配信スキーマのフォーム、コスト・対象範囲・タグ・威力補正、チャットパレット生成、スキルと効果説明のプレビューを追加。138件のフォーム/JSON往復、追加・削除・並べ替え・条件・カテゴリ・枠内の保存のテストを追加した。ローカルの制作者がPs-00の効果値を2→3にして申請し、アプリ管理者が差分で承認。新規もPsカテゴリで作成・申請し、次番号Ps-15で公開、コマンドの正式ID化とSYS保持を確認した。広い幅（1440px）・680pxの閲覧・編集・承認で横のはみ出しはなく、広い承認の全行の高さが一致した。全件テスト（タイムアウト1200秒）は **1855 passed・45 skipped**（500.24秒）。`npm run build` と文字コード・文字化け・差分検査も成功。説明の入れ子の値の表現もPythonと照合した。一時DB・撮影の使い捨て出力は残さず、試作HTMLだけを確認の目印として残す。

画面のためのサーバー変更：効果スキーマへ既存の `TARGET_LABELS` を `target_labels` として追加。新規スキル自身の仮IDを承認前に正式IDへ置換し、生成したチャットパレットを公開できるようにした。他の未公開IDは従来どおり止める。試作の生成スクリプトはバフ参照をキャッシュから解決するよう補修した。文章から作る・計算・試し撃ち・ビルダー削除は未実装のまま。

変更ファイル：`static/js/master_data/{skill,skill_effects,workspace,catalog_api}.js`、`static/css/modules/master_data.css`、`scripts/build_frontend.mjs`、`scripts/catalog_preview/export_schemas.py`、`static/index.html`、`static/dist/app.bundle.{js,css}`と各map、`app.py`、`manager/catalog/repository.py`、`tests/test_catalog_skill_editor.py`、`tests/test_catalog_skill.py`、`tests/test_effect_schemas.py`、A02・A04・C01・E02・F01・本計画書。

#### PR60-12：「文章から作る」とビルダーの削除（完了）

1. `CharaCreator/json_definition_builder.html` の決まった言い回しの読み取り（`_nl` で始まる関数群）を `static/js/master_data/skill_text.js` へ移す。バフ・召喚テンプレートの名前の引き当ては、管理画面が持っている公開データから行う。
2. スキルの編集に「文章から作る」のタブを足す。発動時効果などの文章を読み取り、結果をフォームと JSON に入れる。読み取れなかった行はタブの中にエラーで出す。
3. 消すもの：`CharaCreator/json_definition_builder.html`・`/json_builder`・`/api/json_builder_reference`・`/api/json_nl_builder_audit`（ビルダーだけが使っている）と、そのテスト。
4. テスト：今のビルダーのテストのうち読み取りのものを、新しい場所に移して通す。削除前の読み取り結果を固定して比較し、言い回しの追加・読み取りの改良はしない。
5. 資料：A02・C01 のビルダーの節を、管理画面の「文章から作る」に書き換える。
6. 補助機能の取捨選択（2026-11-09 ユーザー決定）：参照表・チートシートを「文章から作る」の折りたたみの早見表として移し、行ごとのガイドは読み取れなかった行のエラーに含める。JSONタブへコピーを足す。クイックテンプレート・レシピ・震盪雛形、初心者/上級者モード、動的バフ名の一致チェックは移さず、既存フォーム・JSON・検査に任せる。そのうえでビルダーのページと3つの専用経路を消す。

実装結果（2026-11-09）：読み取り本体987行を変更せず移し、旧UIの既定値・省略規則も維持。スキル編集に文章タブ、行エラー、折りたたみの早見表、JSONコピーを追加。バフ・用語・スキルは管理画面の公開版、召喚名・持続・タグは認証付きの `GET /api/catalog/skill/text_references` から読む。旧HTMLと3つの専用経路、旧ページ/APIのテストを削除。読み取り結果の144ケースと元規則のハッシュ、タブ間の反映・失敗時保持・コピー・枠破棄のテストを追加した。ユーザー決定どおり、クイックテンプレート・レシピ・震盪雛形、モード切り替え、動的バフ名チェックは移していない。

検証結果：全件テスト1857 passed・45 skipped（478.71秒、タイムアウト1200秒）。`npm run build`、文字コード・文字化け・差分検査も成功。確認用サーバーを停止し、確認用DB・撮影などの一時出力は削除した。

変更ファイル：`static/js/master_data/{skill_text,skill_text_help,workspace,catalog_api}.js`、`static/css/modules/master_data.css`、`scripts/build_frontend.mjs`、`static/index.html`、`static/dist/app.bundle.{js,css}`と各map、`app.py`、`routes/catalog.py`、`tests/test_catalog_skill_text.py`、`tests/fixtures/skill_text_legacy.json`、`tests/test_catalog_api.py`、`tests/test_app_factory.py`、`tests/test_origin_boon_name.py`、A02・C01・E02・F01・本計画書・計画00/41/46・基盤プロジェクトの配置台帳2件。削除：`CharaCreator/json_definition_builder.html`、`tests/test_json_builder_api.py`、`tests/test_json_builder_encoding_guard.py`。


##### PR60-12 確認時の既存データとの差（2026-11-09）

移植前の出力を固定した144ケースは移植後もすべて一致。現在のキャッシュ138件の `effects` を生成結果と機械比較すると、JSON一致69件、差分65件、読み取り失敗4件。同義キー・数値型・既定値・空配列の差も数えた結果であり、65件すべてが戦闘の動作差という意味ではない。今回、読み取り規則とマスターは修正していない。

ローカル画面ではPs-00・Ps-01・Ps-02・Ps-05・Pb-13・E-19の6件を実際に読み取った。Ps-01は同義のstatの省略、Ps-05はCUSTOM_EFFECTの対象が現在targetに対しself。他の4件のeffectsは一致。未知の行・禁止語のエラーと特記処理の保持、早見表の開閉、コピー成功も確認した。

| ID | 現在のeffects→旧ビルダーと移植後の生成結果 |
|---|---|
| B-01・B-02 | effects[0].data.display_name 省略 / effects[0].timing "PRE_MATCH"→"IMMEDIATE" |
| B-03・B-04 | effects[0].timing "PRE_MATCH"→"IMMEDIATE" |
| D-00・D-01・D-05・D-06・E-00・E-01・E-02・E-15・E-22・E-24・E-30・Mb-03・Pp-01・Pp-10 | effects 件数 0→1 |
| E-06 | effects 件数 1→2 / effects[0].buff_id 省略 / effects[0].consume_cost 追加 / effects[0].delay 省略 / effects[0].lasting 省略 / effects[0].max_reuses 追加 / effects[0].timing "END_MATCH"→"HIT" / effects[0].type "APPLY_BUFF"→"USE_SKILL_AGAIN" |
| E-09 | effects 件数 4→3 / effects[2].data.display_name 省略 / effects[2].target "self"→"target" |
| E-12 | effects 件数 1→2 |
| E-16 | effects[0].data.display_name 省略 / effects[0].delay 1→2 / effects[1].data.display_name 省略 / effects[1].delay 2→1 / effects[1].timing "PRE_MATCH"→"HIT" |
| E-20 | effects[0].data.display_name 省略 / effects[0].delay 0→1 / effects[0].lasting 3→1 / effects[0].timing "PRE_MATCH"→"HIT" |
| E-25 | effects[0].data.display_name 省略 / effects[0].target "target"→"self" / effects[0].timing "RESOLVE_START"→"END_ROUND" |
| E-29 | effects 件数 2→3 / effects[1].condition 省略 |
| Mb-00・Mp-00・Ms-00 | effects[1].timing "END_ROUND"→"HIT" |
| Mb-04・Pb-04 | effects[0].target 追加 |
| Mb-06・Pp-12 | effects[1].data.display_name 省略 |
| Mb-07 | effects[0].buff_id 省略 / effects[0].delay 省略 / effects[0].lasting 省略 / effects[0].timing "HIT"→"END_ROUND" / effects[0].type "APPLY_BUFF"→"CUSTOM_EFFECT" / effects[0].value 追加 |
| Mb-08 | effects[0].condition 省略 / effects[0].value 2.0→2 |
| Mb-10・Pb-02 | effects[1].condition 省略 |
| Mb-11・Ps-11・Ps-14 | effects[0].count 省略 / effects[0].data.buff_id 省略 / effects[0].data.count 追加 / effects[0].delay 省略 / effects[0].lasting 省略 |
| Mb-12 | effects[0].buff_name 省略 / effects[0].consume_required 省略 / effects[0].gains 省略 / effects[0].state_name 追加 / effects[0].type "CONSUME_BUFF_COUNT_FOR_GAIN"→"APPLY_STATE" / effects[0].value 追加 |
| Mb-13 | effects[1].value 4→6 |
| Mp-03 | effects[0].condition 省略 / effects[0].target "target"→"self" |
| Mp-04 | effects 件数 1→2 / effects[0].damage_per_fissure 4→3 / effects[0].target 追加 |
| Mp-05 | effects[0].buff_id "Bu-40"→"Bu-41" / effects[0].count 追加 / effects[0].data.display_name "そこが弱いの？"→"突き崩す（亀裂付与量アップ単発）" / effects[0].delay 省略 / effects[0].lasting 1→999 |
| Mp-06 | effects[0].max_value 省略 |
| Mp-09 | effects 件数 1→2 / effects[0].max_reuses 省略 / effects[0].target 追加 |
| Ms-02 | effects[0].condition 省略 |
| Ms-04 | effects[1].condition 省略 / effects[1].target "target"→"self" |
| Ms-07 | effects[1].data 省略 |
| Ms-08・Ps-05 | effects[0].target "target"→"self" |
| Pb-05 | effects[0].target 追加 / effects[1].target 追加 |
| Pb-06 | effects[0].flavor 省略 |
| Pb-07 | effects 件数 2→3 / effects[0].target 追加 / effects[1].target 追加 |
| Pb-11 | effects[0].data 省略 / effects[0].target "target"→"self" |
| Pp-05 | effects 件数 1→2 / effects[0].target 追加 |
| Pp-06 | effects[0].buff_id 省略 / effects[0].damage_per_fissure 追加 / effects[0].delay 省略 / effects[0].lasting 省略 / effects[0].timing "PRE_MATCH"→"HIT" / effects[0].type "APPLY_BUFF"→"CUSTOM_EFFECT" / effects[0].value 追加 / effects[1].data 省略 / effects[1].target 追加 / effects[1].value "FISSURE_COLLAPSE"→"破裂爆発" |
| Pp-07 | effects 件数 1→2 / effects[0].max_value 省略 |
| Ps-01・Ps-03 | effects[0].stat 省略 |
| Ps-04 | effects 件数 2→3 / effects[1].condition 省略 / effects[1].max_reuses 省略 / effects[1].target 追加 |
| Ps-06 | effects[1].timing "WIN"→"HIT" |
| Ps-07 | effects[0].delay 追加 / effects[0].flavor 省略 |
| Ps-12 | effects[0].count 省略 / effects[0].data.buff_id 省略 / effects[0].data.count 追加 / effects[0].delay 省略 / effects[0].lasting 省略 / effects[1].condition 省略 / effects[1].count 省略 / effects[1].data.buff_id 省略 / effects[1].data.count 追加 / effects[1].delay 省略 / effects[1].lasting 省略 |
| Ps-13 | effects[1].buff_name 省略 / effects[1].consume_required 省略 / effects[1].gains 省略 / effects[1].state_name 追加 / effects[1].type "CONSUME_BUFF_COUNT_FOR_GAIN"→"APPLY_STATE" / effects[1].value 追加 |

| 読み取り失敗のID | 理由 |
|---|---|
| E-14 | コストを解釈できません。例: FPを2消費 |
| E-33 | 特記を解釈できません。対応文型（条件付き固定加算 / Nごと加算 / timing付き効果）で記述してください。 |
| E-34 | 特記を解釈できません。対応文型（条件付き固定加算 / Nごと加算 / timing付き効果）で記述してください。 |
| E-35 | 特記を解釈できません。対応文型（条件付き固定加算 / Nごと加算 / timing付き効果）で記述してください。 |

#### 触らないもの

- 輝化スキル・アイテム・特殊パッシブ・召喚テンプレートの取り込み（Phase 6）。
- 戦闘の中のスキルの処理と `特記処理` の読み方。
- キャラクター作成ツール（CharaCreator 本体）。

#### 資料の更新

- C01：スキルの定義の正本が DB になったこと、項目、カテゴリと採番、検査。ビルダーの節（PR60-12）。
- E02：スキル専用の画面。
- F01：`--pull`、`--update` の4段階、起動時の読み込み。
- A02・A04：スキルの作り方を管理画面へ。
- 終わったら、この節の各 PR に「完了」と結果の要約を書く。

### 5.11 Phase 3 の追補：用語リンクとタイミングを選んで入れる（Phase 6 の前）

本番でスキルを書いてみて、`[[W-26|ラウンド終了時]]` を手で打つのは手間がかかり間違えやすいと分かった（§8 追補2）。画面だけを直し、API・サーバー側・保存の形は変えない。

#### PR60-13：文章の欄の入力の補助（完了）

1. **置き場**：管理画面の文章の欄（`textarea`）すべての上に、小さな道具の帯を置く（用語の短い説明・長い説明・フレーバー、バフの説明・フレーバー、スキルの使用時効果・発動時効果・特記など。Phase 6 で足す種類の説明の欄も同じ部品を使う）。部品は `static/js/master_data/text_tools.js`（`window.CatalogTextTools`）にまとめ、各種類のフォームは欄に印を付けるだけにする。
2. **用語を挿入**：
    - 帯の「用語を挿入」で検索の欄を出す。候補の絞り込みは PR60-6 の `linkCandidates`（ID・名前・別名、廃止は出さない）を使う。編集中の用語自身も候補から外す。
    - 選ぶと、カーソルの位置に `[[W-xx|表示名]]` を入れる。表示名は用語の `display_name`。文字を選んだ状態なら、その文字を表示名にしてリンクで包む。
    - 欄の中で `[[` と打ったときも同じ候補を出す（上下の矢印・Enter で選び、Esc で閉じる）。選ぶと打った `[[` を置き換える。
    - 入れたあとはカーソルをリンクの直後に置き、入力の変更として扱う（保存前の「入力を変更しました」に乗る）。
3. **タイミング**：
    - 帯に「タイミング」の選択を置く。選択肢は、公開中で廃止していない用語のうち分類が「タイミング」のもの（今は W-19 使用時〜W-28 戦闘終了時・W-34 即時発動・W-62・W-63 の13件）を `sort_order`・ID の順に並べる。一覧はコードに書かない。
    - 選ぶと、カーソルのある行の頭に `([[W-xx|表示名]]):` を入れる。その行の頭がすでに `([[W-..|..]]):` か `(…):` の形なら、入れ替える。
4. **入れないもの**：リンクの表示名を用語の名前と別にする入力欄、文章中の既存リンクの一覧・一括置換。
5. **テスト**：カーソルの位置への挿入、選んだ文字を包む、`[[` の置き換え、タイミングの行の頭への挿入と入れ替え、候補から廃止と自分を除く、選択肢が用語の分類から作られる。
6. **確認**：ローカルで制作者として、スキルの発動時効果に「タイミング」と「用語を挿入」で1行書き、プレビューのリンクが開くことを確かめる。撮影は数枚で、確認後に消す。
7. **資料**：E02 の管理画面の Part と A04 の作り方を直す。終わったらこの節に「完了」と結果の要約を書く。

実装結果（2026-11-09）：`CatalogTextTools` を追加し、用語の3欄・バフの2欄・スキルの4欄・「文章から作る」の3欄に共通の入力補助を付けた。JSON欄は対象外。用語候補は既存の `linkCandidates`、タイミングは公開用語の分類から生成する。選択文字・カーソル・`[[` の置換、行頭のタイミング置換、キーボード・IME・部品破棄を検査。API・サーバー・保存形式・読み取り規則は変更していない。

検証結果：全件テスト1862 passed・45 skipped（493.73秒、タイムアウト1200秒）。画面確認時のラベル修正後の関連16件、`npm run build`、構文・文字コード・文字化け・差分検査も成功。

変更ファイル：`static/js/master_data/{text_tools,glossary,buff,skill,skill_text,workspace}.js`、`static/css/modules/master_data.css`、`scripts/build_frontend.mjs`、`static/index.html`、`static/dist/app.bundle.{js,css}`と各map、`tests/test_catalog_text_tools.py`、`tests/test_catalog_skill_{text,editor}.py`、A04・E02・本計画書。既存の計画書へのユーザー追記は保持した。

ローカル確認：隔離DBの制作者でフォーム・「文章から作る」の発動時効果に `([[W-20|的中時]]):[[W-00|出血]]5を付与。` を作成し、プレビューから出血の説明を開いた。タイミング13件、選択文字のリンク化、`[[W-02`からの補完、矢印・Enter・Esc、2行目だけのタイミング挿入と入れ替え、変更表示・特記処理の保持を確認。画像は画面確認にのみ使い、ファイルとして残さない。確認用サーバーは停止、確認用DBは削除済み。

### 5.12 Phase 6 の推奨PR分割（残りの種類）

アイテム（3件、`I-`）・特殊パッシブ（8件、`Pa-`）・輝化スキル（9件、`S-`）・召喚テンプレート（3件、`U-`）を DB へ移し、Sheets からの取り込みをすべてなくす。召喚テンプレートは JSON のタブで直す形だけにする（§8 Phase 6 論点1）。

| PR | 内容 | 本番での見え方 |
|---|---|---|
| PR60-14（完了） | 4種類の種類の定義・DB からの読み込み・検査・使われている所。読み手を辞書にそろえる。`--update` と Sheets を読む処理をすべて消す。`--pull` を7種類にする | 中身は変わらない。管理 API で4種類を扱えるようになる |
| PR60-15（完了） | 管理画面に4種類を足す（アイテム・特殊パッシブ・輝化スキルはフォーム、召喚テンプレートは JSON のタブとプレビュー） | マスターデータの左の列に4つ出る |

最後の `--update` とSheets・キャッシュの一致確認はユーザーが実施済み（2026-11-10、PR60-14着手前）。このPRでは `--update` を実行せず、取得コードを削除する。

### 5.13 Phase 6 の実装詳細

#### Phase 6 で決めたこと

- **3つはバフと同じ型**：アイテム・特殊パッシブ・輝化スキルは、項目と効果の JSON の欄で持つ（§5.8 のバフと同じ）。
- **召喚テンプレートは JSON で直す**：敵キャラに近い形で、項目ごとのフォームは計画61の敵キャラのフォームと合わせて考える（§8 Phase 6 論点1）。
- **辞書の形は今のまま**：各ローダーが返していた今のキャッシュの形（`{"I-00": {"id": "I-00", …}}`、召喚テンプレートは `{"U-00": {"baseName": "U-00", …}}`）を保つ。

#### PR60-14：残りの種類の保存と、Sheets の取り込みの廃止（完了）

1. **種類の定義**に4つを足す。辞書は `extensions` に `all_item_data`・`all_passive_data`・`all_radiance_data`・`all_summon_template_data` を足す。
    - `item`：ID `^I-\d{2,}$`、辞書の ID の項目 `id`。項目 `name`（必須）・`description`・`flavor`・`consumable`（真偽）・`usable`（真偽）・`round_limit`（整数。`-1` は制限なし）・`effect`（オブジェクト）。
    - `passive`：ID `^Pa-\d{2,}$`、`id`。項目 `name`（必須）・`cost`（整数）・`description`・`flavor`・`effect`（オブジェクト）。
    - `radiance`：ID `^S-\d{2,}$`、`id`。項目 `name`（必須）・`cost`（整数）・`description`・`flavor`・`effect`（オブジェクト）・`duration`（整数。`-1` は解除まで）・`granted_tag_ids`（文字の並び）。
    - `summon`：ID `^U-\d{2,}$`、辞書の ID の項目 `baseName`。項目は今のキャッシュの19項目（`name` が必須。型は今のキャッシュのとおり）。
    - 初回取り込みの元は各キャッシュ。
2. **検査**：形（項目・型・必須）に加えて、召喚テンプレートの参照を見る。`initial_skill_ids`・`hidden_skills` がスキル、`SPassive` が特殊パッシブ、`radiance_skills` が輝化スキルの公開中の ID か `X-` の下書きにない（エラー）、廃止（注意）。`[[W-xx]]` は今のまま。
3. **読み手を辞書にそろえる**：`manager/items/loader.py`・`manager/passives/loader.py`・`manager/radiance/loader.py`・`manager/summons/loader.py` の CSV の取得とキャッシュの書き込みを消す。読む関数（`item_loader.load_items()`・`get_item()` など、`load_summon_templates()`・`get_summon_template()`）は辞書を返す形にして残すか、呼び手（`events/socket_items.py`・`manager/items/usage_manager.py`・`manager/utils.py`・`manager/radiance/applier.py`・`events/battle_only/catalog_state.py`・`events/socket_char.py`・`routes/owned_characters.py`・`app.py` など）を辞書の直読みに直す。どちらにするかは、呼び手の数と読みやすさで決めてよい。公開で辞書が入れ替わったら、次に読んだときから新しい中身になること。
4. **起動時と配信**：`init_app_data` で4種類を `seed_kind_if_empty`＋`load_kind_into_memory`。`/api/get_item_data`・`/api/get_passive_data`・`/api/get_radiance_data` は辞書を返す。召喚テンプレートの公開 API `/api/get_summon_data` を足す（ほかと同じく認証なし、`--pull` が読む）。PR60-12 の `/api/catalog/skill/text_references` は辞書を読む。
5. **`--update` をなくす**：`python app.py --update`、`update_all_data`、`manager/data_manager.py` の Sheets 関係、`requirements.txt` の `gspread`（PR60-10 以降どこからも使っていない）を消す。Google のサービスアカウントの鍵（`GOOGLE_CREDENTIALS_JSON`）は不要になるので、F01 の手順と Render の環境変数の説明から外す（Render の環境変数そのものはユーザーが消す）。
6. **`--pull` を7種類に**：取ってくる先に4つの公開 API を足し、手元の DB も7種類を入れ替える。
7. **使われている所**：アイテム・特殊パッシブ・輝化スキルの ID を、召喚テンプレートとほかのデータの中の値から探す。召喚テンプレートの ID を、スキルの効果の中の値から探す。
8. **画面側の読み直し**：`catalog_updated` で4種類のとき、それぞれの公開 API を読み直して `window` の辞書（`allItemData` など今の名前）を入れ替える。
9. **テスト**：初回取り込みの件数（3・8・9・3）、辞書の形が今のキャッシュと一致、召喚テンプレートの参照の検査、承認で辞書が入れ替わり読み手が新しい中身を返す、`--update` が無い、`--pull` が7種類、全件テストがそのまま通る。

完了（2026-11-10）：4種類の定義を`manager/catalog/resources.py`へまとめ、`kinds.py`の種類の定義に登録。起動時の初回取り込み・共有辞書、共通の保存・承認・問題一覧、召喚の参照検査、7種類の使われている所、召喚の公開APIと7種類の`--pull`を実装した。読む関数は呼び手が多いため薄い辞書参照として残し、ローダーの独自キャッシュはなくした。召喚を1件読む関数は、戦闘中の変更が正本へ漏れないよう従来どおり深いコピーを返す。正式IDの編集下書きだけが残っていても、公開版のない参照先は許可しない。管理画面・戦闘の効果処理・CharaCreatorは変更していない。

検証結果：全件テスト1868 passed・45 skipped（531.63秒、タイムアウト1200秒）。正式IDの編集下書きだけが残る参照の境界も個別に確認した。`npm run build`、JS構文・文字コード・文字化け・差分検査も成功。

変更ファイル：`AGENTS.md`・`README.md`、`app.py`・`extensions.py`、`manager/catalog/{resources,kinds,pull,references}.py`、`manager/data_manager.py`、`manager/{items,passives,radiance}/loader.py`、`manager/summons/{loader,__init__}.py`、`requirements.txt`、`static/js/{main,item_modal}.js`、`static/index.html`・`static/dist/app.bundle.js`とmap、`tests/test_catalog_{resources,resource_frontend,pull,buff,skill}.py`、`tests/test_{cache_paths,app_factory,character_tags}.py`、A04・C01・E02・F01・本計画書・計画00/61・配置台帳・アカウント運用/復旧/バックアップ手順。削除：`tests/test_summon_loader.py`・`tests/test_data_manager_lint_hook.py`・`tests/legacy/test_loaders.py`（Sheets取得専用の検査）。旧タグ列の区切り文字の検査も削除し、DBの文字列配列の検査へ移した。

ローカル確認：通常の起動処理で隔離DBへ3・8・9・3件を取り込み、4種類の公開APIと元キャッシュの完全一致を確認。制作者の管理APIでI-00・Pa-00・S-00・U-00を1件ずつ保存・申請し、アプリ管理者の承認後に共有辞書と各公開APIが新しい名前を返すことを確認した。サーバーは停止、確認用DBは削除済み。キャッシュ本体の変更はない。

#### PR60-15：管理画面に残りの種類を足す（完了）

1. 左の列の「種類」に、アイテム・特殊パッシブ・輝化スキル・召喚テンプレートを足す（用語・バフ・スキルの下）。
2. アイテム・特殊パッシブ・輝化スキルのフォームは、バフの `buff.js` と同じ作り（`item.js` などにまとめるか、共通の定義から作るかは任せる）。真偽は選択、`round_limit`・`duration` は「制限なし／解除まで」か数、`granted_tag_ids` は札で入れる。効果は JSON の小さな欄。
3. 召喚テンプレートは、フォームのタブを出さず JSON のタブだけにする。プレビューは名前・HP・MP・召喚の持続・最初から持つスキル（ID と名前）・能力値を並べる。
4. 問題の一覧・使われている所・文章の欄の補助（PR60-13）は、ほかの種類と同じ。
5. テスト：種類の切り替え、3つのフォームの読み書き、召喚テンプレートが JSON のタブだけになる。
6. 確認：ローカルで制作者として、各種類を1件ずつ直して申請し、アプリ管理者で承認する。撮影は数枚で、確認後に消す。

完了（2026-11-10）：`resources.js`に3種類の共通フォームと召喚のJSON専用定義を追加し、既存workspaceへ登録。真偽値・ラウンド制限/持続・効果JSON・付与タグの札、用語挿入の共通部品、問題一覧・参照・履歴・差分承認を使い回した。召喚にはHP/MP・持続・スキルIDと公開名・能力値のプレビューを付けた。スキル公開名の更新時は編集中のJSONを保持してプレビューを更新する。API・サーバー・保存形式・CSS・戦闘処理は変更していない。

検証結果：全件テスト1871 passed・45 skipped（515.12秒、タイムアウト1200秒）。スキル公開名更新の回帰を含む関連19件、`npm run build`、JS構文・文字コード・文字化け・差分検査も成功。

変更ファイル：`static/js/master_data/resources.js`（追加）・`workspace.js`、`scripts/build_frontend.mjs`、`static/index.html`・`static/dist/app.bundle.js`とmap、`tests/test_catalog_resource_editor.py`（追加）、A02・E02・F01・本計画書・計画00。

ローカル確認：隔離DBで制作者がI-00・Pa-00・S-00・U-00を各1件編集・申請し、アプリ管理者が画面の差分から4件とも承認。すべて公開版2と新しい名前になった。アイテムは消耗なし・2ラウンド、パッシブは取得コスト1、輝化はタグの重複防止・持続3ラウンドとJSONへの反映、召喚はJSONタブだけ・構文エラー表示・HP28/30・スキル名・能力値・E-19からの参照・公開履歴を確認。撮影3枚は画面確認だけに使い、ファイルに残していない。確認用サーバーは停止、確認用DBは削除済み。

#### 触らないもの

- 戦闘の中のアイテム・パッシブ・輝化スキル・召喚の処理。
- 敵キャラのフォームと行動パターン（計画61）。
- キャラクター作成ツール（CharaCreator 本体）。読んでいる API の形は変えない。

#### 資料の更新

- C01：4種類の定義の正本が DB になったこと、項目、検査。
- E02：管理画面の種類の追加。
- F01：`--update` の廃止、`--pull` の7種類、Google の鍵が不要になったこと、起動時の読み込み。
- 計画61：召喚テンプレートの項目ごとのフォームを敵キャラのフォームと合わせて考える、と一行足す。
- 終わったら、この節の各 PR に「完了」と結果の要約を書く。

### 5.14 UI 改修の推奨PR分割

§6-3 の洗い出し・決まりごと・試作で決めた形を、今の管理画面に入れる。閲覧と編集は試作の案B（上のタブと節の目次）、承認は案A（変わった項目だけを左右に並べる）にする。見本は `npm run catalog-preview` の `/_local/catalog_preview/ui_revision.html`（`scripts/catalog_preview/revision.js`・`revision.css`）。

| PR | 内容 | 本番での見え方 |
|---|---|---|
| PR60-16 | 共通の土台：下書きは保存したときに作る、未保存の確かめ、浮かぶ枠の閉じ方と「挿入」の1つの枠、操作の重みと置き場、札、色、知らせ、下の帯 | 並べ方は今のまま。押した手応え・色・札・危ない操作の場所が変わる |
| PR60-17 | 閲覧と編集を案Bに：種類を上のタブ、絞り込みを一覧の上の1行、編集を節の目次。種類をまたぐ承認待ち。効果の札を文で見せ、欄の名前を日本語だけにし、候補から選ぶ | 閲覧と編集の並べ方が変わる |
| PR60-18 | 承認を案Aに：変わった項目だけを左右に並べ、文字の単位で差分を出す。正式ID・却下の理由・持続の見せ方 | 承認の画面が変わる |
| PR60-19 | 本番で使ってみての直し（2026-11-11 追加、試作で形を決めた）：スキルを前の専用画面に戻す、飾りの線を薄く、上の部分・詳細・プレビューを詰める、一度読んだものは読み直さない、挿入をいつも見せる、文章から効果を作るの名前と ⓘ、ダイス威力を選んで入れる、効果タイプを系統ごとに並べる | スキルが別の画面に戻り、画面が柔らかく詰まって見え、タブの行き来で待たない。スキルの編集が選んで入れる形になる |

PR60-16 → 17 → 18 → 19 の順に進める。どれも `workspace.js` と `master_data.css` を触るので、同時には進めない。

### 5.15 UI 改修の実装詳細

#### UI 改修で決めたこと

- **形**：閲覧と編集は案B、承認は案A（2026-11-10 ユーザー、§6-3）。試作の両案に共通で入れたものはすべて入れる。
- **下書きを作る時**：「編集」「新しく作る」では下書きを作らない。最初に「下書きを保存」か「承認を申請」を押したときに作る。保存していない変更があるまま離れようとしたら確かめる（2026-11-10 ユーザー）。
- **注意書きを増やさない**：意味は画面の作り（候補・要らない欄を隠す・区切り・効果の文の見出し）で伝える。詳しい説明は、管理画面専用の操作マニュアルで別に補う（§6-3）。
- **見本との差**：見本は見た目と手応えの確認用で、データの形・保存・検査は今の実装のまま。見本と今の実装で動きが食い違うときは、今の実装の保存・検査の動きを優先し、見た目を見本に寄せる。

#### PR60-16：共通の土台

**完了（2026-11-10）**。7種類共通で、保存時の下書き作成、未保存の3択確認とページ離脱の確認、1つの挿入枠、操作の置き場、札・色・浮かぶ知らせ、680pxでも残る編集・承認の帯を実装した。既存の下書きの権限を保ち、初回保存時の他人の下書き・承認待ち・公開版の更新は上書きせず止める。左の列・3列・入力タブ、API・保存形式・文章の読み取り規則は変更していない。

検証：`npm run build`、画面関連37件、全件 `pytest -q`（タイムアウト1200秒、1875 passed / 45 skipped）、文字コード・文字化け検査を通過。制作者・管理者で、編集して戻るだけでは下書きが残らないこと、3択、挿入枠の外への1回の操作、タイミング挿入、スキルからの戻り、承認・公開、通知の手動閉じ、680pxの編集・承認の帯を確認した。確認用DB・起動用ファイル・テストの一時出力は削除し、撮影ファイルは保存していない。

すべての種類（用語・バフ・スキル・アイテム・特殊パッシブ・輝化スキル・召喚テンプレート）に効く。並べ方（左の列・3列・入力のタブ）は変えない。

1. **下書きは保存したときに作る**（決まり8）：
    - `startEdit` で `request('create')` を呼ばない。既存の項目は公開中の版の中身と版番号を、新規は既定の中身を、手元の編集の状態（下書き ID なし）として持つ。
    - 最初の「下書きを保存」か「承認を申請」で `create` してから `save` する。それまでは一覧に下書きを足さず、絞り込みも「下書き」に切り替えない。
    - その項目に下書きがもうあるときは、今と同じくその下書きを開く（作成者・管理者以外と承認待ちの扱いも今のまま）。
    - サーバーの API は変えない。`create` が既存の下書きを返す（別の画面で先に作られていた）ときに他人の下書きなら、上書きせずに知らせて止める。
2. **未保存の確かめ**（決まり8）：保存していない変更があるまま、「← 戻る」・閉じる（ボタン・Esc・背景）・スキルの画面との行き来で離れようとしたら、確かめを出す。
    - 選べるのは「編集に戻る」「変更を捨てる」「下書きを保存して移る」の3つ。主な操作は「下書きを保存して移る」。
    - 今の `showAppConfirm` は2択なので、管理画面の中に3択の確かめを作る。
    - ページを閉じる・再読み込みするときは `beforeunload` で止める。
    - 編集の上の帯には、変更があるときだけ「編集中・未保存」の札を出す。下の帯にも「● 保存していない変更があります」を出す。
3. **浮かぶ枠の閉じ方**（決まり9）：`text_tools.js` の候補の枠は、管理画面の外も含め、枠とその開くボタン以外のどこを押しても閉じる。
    - 閉じるときは枠だけを消し、画面を描き直さない。押した先のボタンや欄に、そのクリックがそのまま届くこと。
    - Esc でも閉じる。
4. **「挿入」の1つの枠**（決まり7・9）：
    - 「用語を挿入」のボタンと「タイミング」の標準の選択欄を、「挿入 ▾」のボタン1つにまとめる。開く枠の中で、タイミングと用語を探して選ぶ（試作の形）。
    - 挿入の位置と、選んだ文字を囲む動き、`[[` での候補は今のまま。
    - 道具の帯は、触っている文章の欄にだけ見せる。ほかの欄では場所は取ったまま隠し、欄がずれないようにする。
5. **操作の重みと置き場**（決まり4・5）：
    - 1つの場面で、色を塗った主な操作は1つにする。
    - 閲覧の詳細の「廃止」（と「廃止を取り消す」）は、詳細の一番下の「その他の操作」に移す。
    - 編集の下の帯の「取り下げ」は、帯の左の「その他 ▾」の中に移す。
    - 押すと確かめを出す（今の確かめを使ってよい）。
    - 戻るは左上、保存と申請は右下にそろえる。
6. **札**（決まり2）：
    - 「公開中」の札は出さない。下書き・承認待ち・却下・廃止・編集中だけを、文字と枠で出す。
    - 札の文字は12pxにする。廃止と編集中は破線の枠にして、色だけに頼らない。
7. **色**（決まり3）：文字は背景に対して4.5:1以上、入力欄・ボタン・カードの枠は3:1以上にする。
    - 足りない今の値：小さい文字 `#7b8798`（3.65:1）、廃止の札（4.28:1）、入力欄とボタンの枠（1.7〜1.8:1）、差分の背景（1.09:1）。
    - `master_data.css` の頭に色の変数をまとめ、各所はそれを使う。値は試作の `revision.css` の `:root` を目安にする。
    - キーボードで動かしたときの枠（フォーカス）を、はっきり見せる。
8. **知らせ**（決まり9）：「下書きを保存しました」などの知らせは、管理画面の右下に浮かべ、数秒で消す。画面はずらさない。
    - 誤りの知らせは消えず、閉じるボタンを付ける。
    - 欄ごとの誤りと問題の一覧は、今の場所のまま。
9. **下の帯**（決まり5）：編集と承認の下の帯は、狭い幅（680px）でも画面の下に留め、入力の側だけをスクロールさせる。
10. **テスト**：既存の画面のテスト（`tests/test_catalog_*_frontend.py`・`*_editor.py` の node で動かす形）にならって足す。
    - 「編集」で `create` を呼ばないこと。最初の保存で `create`→`save` になること。
    - 変更があるときに戻ると確かめが出ること。3つの選択それぞれの結果。
    - 挿入の枠が外を押すと閉じること。
    - 「公開中」の札が出ないこと。
11. **確認**：ローカルで、制作者とアプリ管理者の2人で行う。
    - 既存の項目で「編集」を押して戻ったとき、下書きが残らないこと。
    - 直して戻ると確かめが出て、3つの選択がそれぞれ働くこと。
    - 挿入の枠を開いたまま別のボタンを押すと、1回で枠が閉じて押した先も働くこと。
    - 680px でも下の帯が見えること。
    - 撮影は数枚で、確認後に消す。

#### PR60-17：閲覧と編集を案Bに

**完了（2026-11-10）**。7種類の上部タブ・件数と絞り込み・2列の閲覧・種類横断の承認待ち一覧、種類ごとの節の目次と680pxのプレビュー切り替えを実装。入力中の文字と誤りを節の移動でも保持する。JSONを集約し、召喚の並び順、公開効果の例、持続の横並び、スキルの日本語の札と条件の文、参照候補、威力補正の4方式、タグの札を追加した。スキーマの `visible_when` は亀裂の欄だけの表示に使い、隠した値は保持する。

サーバーの変更は `GET /api/catalog/overview` とスキーマの表示条件だけ。保存形式・既存API・文章の読み取り規則・承認画面の構造は維持した。数値2.0の表記を画面側で引き継ぎ、全138件の効果の文がPythonと一致するテストを通した。

検証：ビルド、全件テスト1886 passed / 45 skipped（実行制限1200秒）、文字コード・文字化け検査。別の確認用DBで制作者・管理者それぞれが7種類を編集・申請し、横断一覧から計14件を承認した。1280px・680px、節の移動と誤り、参照候補・亀裂の欄・補正・タグ・効果の例・JSON集約を確認した。確認用DB・起動用ファイル・テスト出力を削除。撮影ファイルは保存していない。手元の `instance/gemtrpg.db` は同一内容であることをハッシュで確認した。

1. **閲覧の並べ方**：
    - 種類を、上のタブ（件数つき）にする。スキルもタブの1つにし、別の画面への行き来（「← マスターデータ」）はなくす。
    - その下の1行に、探す・状態（件数つきのボタンの並び）・分類（ある種類だけ）・「＋新しく作る」（右端）を置く。スキルの分類は、今の4群10カテゴリを選択欄のまとまり（`optgroup`）で出す。
    - 一覧と詳細の2列にする。狭い幅では、一覧の下に詳細を置く。
2. **件数と承認待ちの一覧**：
    - 種類ごとの件数（公開中・下書き・承認待ち）を一度に返す API を足し、まだ開いていない種類の件数も出す。「—」は出さない。
    - アプリ管理者には見出しの右に「承認待ち n件」を出す。押すと、種類をまたいだ承認待ちの一覧を開き、そこから承認の画面へ進む。
    - API は、今の管理 API と同じ認証にする。
3. **一覧のカード**：
    - スキルの説明は、記法を外した読める文で出す（プレビューと同じ）。
    - 召喚テンプレートのカードは「説明未入力」を出さず、HP・MP など召喚の要点を出す。
4. **編集の並べ方**：
    - 左に節の目次を置き、選んだ節だけを出す。右はプレビュー。狭い幅では、目次は上の横の帯にし、プレビューは目次の「プレビュー」から開く。
    - 今の入力のタブ（フォーム・JSON・文章から作る）は、目次の項目にまとめる。目次の下側に、区切りの線を挟んで「JSON」「文章から作る」（スキルだけ）を置く。
    - 節は種類ごとに決める。
        - 用語：本体（名前・分類・別名）・説明・関連用語
        - バフ・アイテム・特殊パッシブ・輝化スキル：本体（名前と、持続などの値）・説明・効果
        - スキル：本体（チャットパレットを含む）・文章・コスト・補正・効果
        - 召喚テンプレート：JSON だけ
    - 節を移っても、入力はそのまま残す。誤りのある欄があるときは、その節の目次に印を付ける。
5. **JSON を1か所に**（決まり6）：
    - 効果の JSON は、目次の「JSON」の節だけに出す。プレビューの「効果のJSON」と、下の「JSON」の折りたたみはなくす。
    - 召喚テンプレートの JSON は、名前・HP・MP など読みたい順に並べて見せる。保存する中身の順は問わない。
6. **スキルの効果の札**（決まり6・7）：
    - 札の見出しは「タイミング｜効果の文」にし、条件があれば文で添える。例：「使用時｜このスキルの基礎威力を+3」「自分の蓄力が2以上のとき」。
    - 効果の文はスキーマの `summary` から作る。Python の `render_effect_summary` と同じ結果になること。
    - 欄の名前は日本語だけにする。タイミングと効果タイプの選択肢も日本語の名前だけにし、`APPLY_STATE`・`END_ROUND` などは JSON の節にだけ出す。
7. **候補から選ぶ**（決まり7）：
    - 状態（`state_ref`）は、用語の状態異常とFP・MP・HPを候補にする。バフ・スキル・召喚の参照は、それぞれの公開中の ID と名前を候補にする。
    - 威力補正は、今の4つの形（FIXED・FIXED_IF_EXISTS・PER_N_BONUS・MULTIPLY）を選んで行を足す形にする。中身は今の JSON の形のまま。
    - タグは札で入れ、用語のスキルタグを候補にする。
8. **その値のときだけ使う欄**（決まり7）：
    - 効果のスキーマの欄に「この値のときだけ出す」の印を足し、印のある欄はその値のときだけ出す。例：`APPLY_STATE` の `rounds`・`source` は状態が亀裂のときだけ。
    - 印は `EFFECT_SCHEMAS` に持たせ、`/api/effect_schemas` で配る。キー一致のテスト（Phase 1）を通すこと。
9. **バフなどの効果の欄**：効果の JSON の欄の下に、公開中のデータで使われている効果の `type` と1件の例を出し、選ぶと例を欄に入れられるようにする。
10. **持続**：持続などの「単位の選択」と「数の欄」を1行に並べる。
11. **テスト**：
    - 7種類の節の目次と、節を移っても入力が残ること。
    - 効果の文が `render_effect_summary` と一致すること（138件のスキル）。
    - 内部名がフォームの節に出ないこと。
    - 亀裂のときだけ欄が出ること。
    - 威力補正とタグの読み書き。
    - 件数の API。
    - 承認待ちの一覧。
12. **確認**：ローカルで、制作者とアプリ管理者が7種類を1件ずつ直して申請し、種類をまたいだ承認待ちの一覧から承認する。1280px と 680px。撮影は数枚で、確認後に消す。

#### PR60-18：承認を案Aに

**完了（2026-11-11）。** 7種類共通で変更項目だけを左右に並べ、日本語・追加・削除の文字差分、未変更項目の開閉、持続の読みやすい表示、既存IDの文字表示、却下理由の開閉を実装した。スキルの効果は1件ずつ文で比べ、効果の例はID・名前・説明で選ぶ。保存値だけが違って同じ文になる場合も、折りたたみで元の値を確認できる。旧来の種類ごとの比較処理と縦積み用CSSを削除した。API・保存形式・検査・承認の流れは変更していない。

検査：全件pytestは1890件成功・45件スキップ（641.86秒、タイムアウト1200秒）。最終修正後の関連画面テスト36件、npm run build、文字コード・文字化け・構文・差分の検査も成功した。

別DBで制作者がBu-00とPs-00を編集・申請し、管理者がバフを承認、スキルを理由つきで却下した。1280px・680pxで左右の整列、差分・未変更の開閉、ID、却下理由と操作の収まりを確認した。確認用DB・起動用スクリプトを削除し、手元のinstance/gemtrpg.dbが未変更であることを確認した。

1. **変わった項目だけ**：
    - 左に公開中の版、右に下書きを並べ、変わった項目だけを出す。
    - 「変わっていない項目も見る（n）」で残りを開く。
    - 新規の項目は左を「新規」とし、右に全項目を出す。
2. **文字の単位の差分**（決まり2）：
    - 変わった項目に「変更」の札を付ける。左は消した文字に取り消し線と背景、右は足した文字に下線と背景を付ける。
    - 文章の差分は、記法を外した読める文で比べる。
    - スキルの効果は、PR60-17 の効果の文で1行ずつ比べる。
    - 長い文は、変わった所の前後だけを出してもよい。
3. **値の見せ方**：持続などは「1ラウンド」「解除まで」のように、一覧やプレビューと同じ見せ方にする。
4. **下の帯**：
    - 既存の項目の正式IDは、入力欄にせず文字で見せる（新規は今のまま次の ID を入れた欄）。
    - 却下の理由の欄は「却下…」を押してから出し、「却下する」と「取りやめる」を並べる。
    - 主な操作は「承認して公開」。
5. **効果の例のボタン（PR60-17 の残り、2026-11-10 追加）**：
    - バフなどの効果の欄の下の「公開中の効果の例」のボタンに、`stat_mod` のような効果の `type` 名をそのまま出さない（決まり6）。
    - ボタンは例にした項目の ID と名前（例「Bu-00 鋭敏と同じ形」）にし、その項目の説明を小さく添える。
    - 効果の `type` 名は、入れた後の JSON で見える。
6. **テスト**：
    - 文字の差分（足す・消す・入れ替え・日本語）。
    - 変わっていない項目が隠れること。
    - 既存の項目で正式IDが入力欄にならないこと。
    - 却下の理由の欄が最初は出ないこと。
    - 効果の例のボタンに `type` 名が出ないこと。
7. **確認**：ローカルで、制作者がバフとスキルを1件ずつ直して申請し、アプリ管理者が差分を見て片方を承認、片方を却下する。1280px と 680px。撮影は数枚で、確認後に消す。

#### PR60-19：本番で使ってみての直し

**完了（2026-11-11）。** スキル専用画面・線の使い分け・上部と詳細の圧縮・常設の挿入・文章生成の配置とⓘ・ダイス入力・効果タイプの系統と英字キー・画面内での取得結果の保持を、元の部品に実装した。サーバーは22効果タイプのgroup追加のみ。API・保存形式・読み取り規則・承認の流れは変更していない。試作のソースは変更していない。

検査：全件pytestは1894件成功・45件スキップ（763.20秒、タイムアウト1200秒）。最終修正後の関連テスト30件、npm run build、文字コード・文字化け・構文・差分の検査も成功した。確認用DB・通信ログ・起動用スクリプトは削除した。撮影はファイルに残さず、手元のinstance/gemtrpg.dbはハッシュが一致した。

別DBで制作者がPs-00のダイス威力を選び、効果タイプと文章生成を使って申請し、管理者が承認待ちの一覧から承認して同一覧へ戻ることを確認した。680pxのカテゴリ帯・検索のフォーカス・未保存の確認も確認した。通信記録では、7種類の2周目に管理APIへの問い合わせが0件だった。

1280×720で今回生成した見本と実画面を同じ条件で測ると、一覧の先頭は用語239.85px／239.85px、スキル196px／196px、全部見えるカードは用語6件／6件・スキル7件／7件。Ps-04の管理者の詳細は846px／846pxで一致した（前に記録した205px・161px・849pxとは異なるため、今回再生成した見本との実測として記録した）。

検証で、ⓘの説明（body直下に出す）の重なり順が1300で、ロビーの管理画面の窓（1500）の後ろに隠れていたため、1600に直した（確認の窓12000より下）。テストに重なり順の範囲の検査を足した。

PR60-18 の本番反映の後、ユーザーが使ってみて不満が出た（2026-11-11）。改修前（コミット `6c4526bb`）と今を 1280×720 で並べて原因を確かめ、本物の管理画面のコードを偽物のサーバーで動かす試作で形を決めた。

- スキルの専用画面がなくなった：PR60-17 でスキルを種類タブの1つにし、分類を右上の選択欄に入れた。
- カクカクして見える：PR60-16 で、決まり3の「操作の枠は3:1以上」を、カード・区切り・JSON の枠・プレビューなど飾りの線にまで当て、すべて濃い `#7b8798` にした。W3C の解説（非テキストのコントラスト）でも、3:1 が要るのは押す・入れる部品の見分けに要る枠で、文字で読み取れるカードや区切りの線は対象外とされる。
- スクロールが多い：見出し・2段の種類タブ（「下書き0・承認待ち0」の段）・絞り込みの行で、720px の高さの約4割を使う。一覧が窓の上端から 291px で始まり、全部見えるカードは2件。スキルの詳細も1件で約1260px あり、同じ札と名前が2回出ていた。
- タブを替えるたびに読み込みが入る：種類を替えるたびに、一覧・用語・件数をサーバーから取り直す（毎回3〜5回）。スキルではさらにスキーマ・バフ・用語・召喚を取り直す。
- スキルの編集：ダイス威力を `+1d4` のように全部手で打つ。「文章から作る」の使い方が分からない。用語・タイミングの挿入が、欄を触るまで見えず、消えたように見える。効果タイプの選択肢が22件並ぶだけで探しにくい。

**見本（正本）**：`node scripts/catalog_preview/pr19/build.mjs` で作る `/_local/catalog_preview/pr19/compare.html` の「案」。
- 案の中身は3つのファイルにある。`scripts/catalog_preview/pr19/workspace.js`（`static/js/master_data/workspace.js` の写しに直しを入れたもの。各直しに番号の注釈がある）、`overrides.js`（スキルの部品に重ねる直し）、`proposal.css`（本番の CSS に重ねる直し）。
- 見本は、本番のコードに直しを重ねただけで、作り方は真似なくてよい。実装は元のファイル（`workspace.js`・`skill.js`・`skill_text.js`・`skill_effects.js`・`master_data.css` など）を直して、重ねる仕組みを使わない。
- 見本の測った値（1280×720）：一覧の始まりは用語 205px・スキル 161px、全部見えるカードは用語6件・スキル7件。2回目に開く種類は約25ms で問い合わせなし（0.4秒の待ちを入れて測った）。Ps-04 の詳細は 1258px→849px、編集のプレビューは 792px→581px（1024×768）。

PR60-16〜18 の残りの決めごと（下書きは保存したときに作る、未保存の確かめ、挿入の枠、札、知らせ、下の帯、節の目次、効果の札、候補、承認の差分）は変えない。

1. **スキルを前の専用画面に戻す**（ユーザー決定）：
    - 種類タブの「スキル」を押すと、スキル専用の画面に移る。見出しは「スキル」、右上に「← マスターデータ」を置き、押すと直前の種類タブに戻る。スキル専用の画面では種類タブを出さない。
    - 左の列に4群10カテゴリ（物理：Ps・Pb・Pp／魔法：Ms・Mb・Mp／防御・補助：D・B・C／敵：E）を件数つきで並べる。件数は今の状態・検索の絞り込みに合うものを数える。右上の分類の選択欄はなくす。
    - 左の列はカテゴリだけにする（改修前は検索と状態も左にあり、列が縦にスクロールした）。探す・状態・「＋新しく作る」は一覧の上の1行に置き、その下に一覧と詳細を並べる。
    - 680px では、カテゴリを上の横の帯に並べる。
    - 編集と承認は、スキル専用の画面の中で開く。編集の「← 戻る」はスキルの一覧に戻る。編集中に「← マスターデータ」を押したときも、未保存の確かめを出す。
    - 種類をまたいだ承認待ちの一覧からスキルを開いたときは、承認の後や「← 戻る」で、今と同じく承認待ちの一覧に戻る。
2. **線**（決まり3の当てる範囲の直し）：
    - 色の変数を2つに分ける。飾りの線（`--cat-edge`）は薄い色（見本は `#d6dee8`）、操作の枠（`--cat-control`）は今の濃い色 `#7b8798` のまま3:1以上を保つ。
    - 操作の枠を使うのは、入力欄・選択欄・文章の欄・ボタン・状態の絞り込みのボタン・「その他 ▾」。それ以外の線（窓の外枠、カード、一覧の行、区切り、JSON・プレビュー・承認の比べる枠、帯の境目、履歴）は飾りの線。
    - 札の枠は文字と同じ色、フォーカスの枠は今のまま。見本の「背景で区切る」は採らない。
3. **上の部分を詰める**：
    - 見出しの下の説明文（「マスターデータの閲覧・下書き・承認」）は出さない。見出しの文字を少し小さくし、見出しと右上のボタンを1行に収める。
    - 種類タブを1段にする。名前と公開中の件数を並べ、下書き・承認待ちは1件以上あるときだけ「承認待ち1」のような小さな札で添える。
    - 探す・分類の欄の名前は、見えない名前（読み上げには残す）にし、入れる例を欄の中に出す。
    - 一覧のカードを2行にする。1行目に ID・名前・札、2行目に要点と説明を1行で切って出す。
4. **詳細とプレビューを短くする**：
    - 詳細の名前と「編集」のボタンを1行に並べる。
    - 「使われている所（n件）」「履歴（n版）」は件数つきで畳む。
    - スキルのプレビューは「ゲームでの見え方」のカード1枚にし、名前・札・コストを出していた小さなカードをなくす（その中で `[[W-19|使用時]]` の記法がそのまま出ていた）。カードの文字の大きさと余白を管理画面に合わせる。
    - 「効果の説明」の一覧の行を詰める。
5. **文章の欄の「挿入 ▾」をいつも見せる**：
    - 「挿入 ▾」は、欄の名前と同じ行の右に置き、いつも見せる。欄の上に場所を取らないので、出しても欄はずれない。これで PR60-16 の「触っている欄にだけ見せ、ほかは場所を取って隠す」をやめる。
    - 押したときに開く枠と、挿入の動きは今のまま。
6. **「文章から作る」を「文章から効果を作る」にする**：
    - 目次と見出しの名前を「文章から効果を作る」にする。見出しの横に 7 の ⓘ を置き、「下の3つの欄を読み取り、コスト・補正・効果を作り直します。今の設定は置き換わり、保存はしません。」を出す。画面の説明文の段落はなくす。
    - 「文章を読み取って効果を作る」のボタンと結果を、節のいちばん上（見出しのすぐ下）に置く。その下に3つの文章の欄・タグの欄・早見表。
    - 読み取れたときは「効果を作りました。確かめる節：」と「コスト」「補正」「効果」の節へ移るボタンを出す。読み取れない行があるときは、今と同じく行と理由を出し、効果は変えない。
    - 「効果の説明」の見出しにも ⓘ を置き、「『効果』の節の設定を文にしたもの。上の文章と食い違いがないかを見比べます。」を出す。
7. **ⓘ の説明**：
    - 丸に i の小さなボタン。カーソルを合わせるか、キーボードで選ぶと説明が出る。説明は1〜2文にする。
    - 説明は画面に固定した位置に出し、スクロールする枠に切られないようにする。読み上げでは、ボタンに説明が結び付くようにする。
    - ほかの所へ ⓘ を増やすのは、必要になったときに1つずつ決める。
8. **ダイス威力を選んで入れる**（ユーザーの希望）：
    - 「振らない」のチェック、「＋ 足す／− 引く」の選択、ダイスの数、「d」、面の数を1行に並べ、右に保存される値（`+1d6` など）を小さく出す。
    - 「振らない」は `+0`。チェックの間は、ほかの欄を押せなくする。
    - 保存の形は今のまま（文字の `+1d4` など）。チャットパレットの「項目から作る」も今のまま値をつなぐ。
    - この形（`+0` と、`+` か `-` に続く「数 d 面」）に合わない値（今は `+5` と `+1d4+1d{物理補正}` の形の3件）は、今の文字の欄のまま出す。
9. **効果タイプを系統ごとに並べる**（ユーザーの希望）：
    - 効果のスキーマ（`EFFECT_SCHEMAS`）の各タイプに系統（`group`）を持たせ、`/api/effect_schemas` で配る。キー一致のテスト（Phase 1）に、全タイプが決まった系統のどれかを持つ検査を足す。
    - 系統と順（見本の分け方）：状態異常（状態を付与・参照値ごとに状態を付与・期限付き亀裂を付与・状態を乗算）／バフ（バフを付与・参照値ごとにバフを付与・人数から威力バフを付与・バフを解除）／スタック（スタックを消費して効果を得る・スタックを威力へ変換・スタック資源を変換）／威力・ロール（基礎威力補正・最終威力補正・ロール補正）／ダメージ・回復（追加ダメージ・HP吸収）／行動・進行（スキルを再使用・一方攻撃を強制・効果を予約・スキルを付与・キャラクターを召喚）／特殊（カスタム効果）。
    - 効果タイプの選択欄は、系統ごとのまとまり（`optgroup`）で出す。
    - 「効果」の節の頭に「効果タイプの英字のキーも出す」のチェックを置く。入れると選択肢が「状態を付与（APPLY_STATE）」になる。最初は外す。選んだ状態はその人のブラウザーに覚えさせ（読めないときは外したまま）、ほかの効果の札や次に開いたときも同じにする。これは決まり6（内部名は JSON に任せる）の、ユーザーが選んだときだけの例外。
10. **一度読んだものは読み直さない**：
    - 種類ごとの一覧、件数（`/api/catalog/overview`）、効果のスキーマ、スキルの画面が使う参照（バフ・用語・召喚）、詳細の履歴と参照箇所は、一度読んだら画面の中に持つ。種類を替えるときや「← 戻る」では、持っているものですぐ描き、サーバーに取りに行かない。
    - 読み直すのは、①公開の知らせ（`catalog_updated`）が来たとき（すべて捨てて取り直す）、②自分が保存・申請・取り下げ・承認・却下・廃止・復元をしたとき（その種類と件数）、③「更新」を押したとき（すべて捨てて取り直す）、④画面を閉じて開き直したとき。
    - 同じものを同時に2回取りに行かない。取りに行って失敗したものは持たない。
    - 入力中のフォームを通知で上書きしない、古い応答を画面に戻さない、の今の決めごとは保つ。
11. **テスト**：既存の node で動かす画面のテストにならって足す。
    - 「スキル」でスキル専用の画面に移り、10カテゴリと件数が出て、カテゴリで一覧が絞られ、「← マスターデータ」で直前の種類に戻ること。編集中は未保存の確かめが出ること。
    - 一度開いた種類に戻るとき、`CatalogApi` の一覧・件数・スキーマを呼ばないこと。知らせ・自分の操作・「更新」では読み直すこと。
    - 飾りの線の要素が `--cat-edge` を、入力欄とボタンが `--cat-control` を使うこと。
    - 種類タブに「下書き0・承認待ち0」の段が出ないこと。
    - ダイス威力：今の値（`+1d4`・`-1d6`・`+0`）を読んで欄に出すこと、欄を変えると値が変わり未保存になること、「振らない」で `+0`、形に合わない値は文字の欄になること。
    - 効果タイプの系統のまとまりと、英字のキーの切り替え。スキーマの全タイプに系統があること（Python）。
    - 「文章から効果を作る」の名前・ボタンの位置・読み取れたときの節へのボタン。
    - スキルのプレビューに小さなカードが出ず、記法がそのまま出ないこと。
12. **確認**：
    - ローカルで、1280×720 の撮影を見本の「案」と並べ、線・上の部分の高さ・一覧の件数・詳細の長さが同じくらいになること。680px でも崩れないこと。
    - 種類を2周して、2周目に通信が出ないこと（ネットワークの記録で見る）。
    - 制作者とアプリ管理者で、スキル専用の画面からスキルを直して（ダイス威力・効果タイプ・文章から効果を作るを使う）申請し、承認待ちの一覧から承認する。
    - 撮影は数枚で、確認後に消す。

#### 触らないもの

- 保存の形・検査・承認の流れと API（PR60-17 の件数の API、スキーマの印、PR60-19 のスキーマの系統を除く）。
- 「文章から作る」の読み取り規則（`skill_text.js` の読み取りの部分。PR60-19 で画面の部分だけ変える）。
- 戦闘の画面と処理、キャラクター作成ツール。
- 試し撃ち（Phase 4）と効果のリクエスト（Phase 5）。

#### 資料の更新

- E02：管理画面の並べ方・札・色・確かめ・知らせ・挿入の枠・承認の差分。
- A02：制作者が下書きを作る時（保存したとき）と、承認待ちの一覧。
- C01：効果のスキーマの「この値のときだけ出す」の印（PR60-17）と系統（PR60-19）。
- §6-3 は短くまとめ済み（PR60-16）。PR60-18 の後に、終わったことを一行足す。
- 終わったら、この節の各 PR に「完了」と結果の要約を書く。

### 5.16 効果から文章を作る（PR60-23 完了・PR60-24 着手前）

状態：**数えた（2026-11-14）。言い回しの決まりは読み取りと同じものを正本にする。読み取りの直し（PR60-23）は完了。次は効果から文章を作る（PR60-24、画面は試作で決めてから詳細を書く）。**

#### 目的

スキルの効果をフォーム（プルダウンなど）で組んだあと、その設定からゲームの書き方の文章（コスト・発動時効果・特記）を作れるようにする。「文章から効果を作る」（PR60-11）の逆向き。手で書く文章と効果の設定の食い違いを減らし、新しいスキルを作る手間を下げる。

#### 今あるものと足りないもの

今は効果タイプごとのスキーマの `summary` から、効果の札の見出しと「効果の説明」の文を作っている（Python の `render_effect_summary` と画面で同じ文になる）。この仕組みを広げて使う。

2026-11-11 に8件のスキルで、今作れる文と書かれている文章を比べた。

| スキル | 書かれている文章 | 今作れる文 |
|---|---|---|
| E-04 | 出血3を付与 | 対象に出血を3付与 |
| B-04 | MPを10回復する | 自分にMPを10付与 |
| Pp-12 | 蓄力4を得る | 自分にバフBu-30を付与 |
| Pb-02 | 対象の破裂が8以上なら、破裂5を付与 | 対象に破裂を5付与（条件が抜ける） |
| Mp-04 | 亀裂崩壊。消費した亀裂1につき4ダメージ | ?に亀裂崩壊_DAMAGEを実行 |

足りないものは次の5つ。

1. **言い回しの決まり**：「〇〇Nを付与」「MPを回復する」のようなゲームの書き方の型。効果タイプごと・カスタム効果ごとに要る。値や対象で言い回しが変わるもの（MP・HP・FP を付与するときは「回復する」「得る」）も決める。
2. **名前と用語のリンク**：バフ・スキル・状態は ID でなく名前で書き、`[[W-00|出血]]` のように用語図鑑につなぐ。
3. **タイミングと条件**：行の頭に `([[W-20|的中時]]):` を付け、「〜なら、」の条件を文に入れる。同じタイミングの効果は1文にまとめる。コストはコストの欄に `([[W-19|使用時]]):FPを3消費` の形で書く。
4. **設定にない補足**：E-21 の「この効果で付与されたスキルは2回まで使用可能」のように、文章にしかない説明がある。全部は自動にできないので、作った文を人が直す前提にする。
5. **往復の確かめ**：作った文章を「文章から効果を作る」で読み直すと、同じ効果に戻ること。
6. **組になった効果を1つの文にする**（2026-11-11 ユーザーの覚書）：設定では2件に分かれていても、遊ぶ人には1つの効果に見えるものがある。例：特記「([[W-19|使用時]]):[[W-74|蓄力]]2を消費し、このスキルの基礎威力+3。」は、設定では「蓄力のスタック数が2以上のとき、基礎威力補正3」と「蓄力を2消費して効果を得る」の2件で、「効果の説明」にも2行で出る。こうした組を見分けて1つの文にまとめる（「効果の説明」も1行にする）。組の見分け方（同じタイミング・同じ資源の条件と消費、など）は、数える段階で例を集めて決める。

#### 画面の形（案）

- 専用の画面は作らない。スキルの編集の「文章」の節に「効果から文章を作る」のボタンを置く。
- 押すと、今の文章と作った文章を欄ごとに左右に並べる（承認の差分と同じ見せ方）。欄ごとに置き換えるかを選ぶ。置き換えても保存はしない。
- 言い回しの決まりができたら、「効果の説明」の文も同じ決まりで作る（「?へスキルを最大1回再使用」のような「?」もここで直す）。
- 書かれた文章と効果の設定から作った文章が食い違うスキルを、検査の注意として知らせる（今は「効果の説明」の ⓘ で見比べを頼んでいるだけ）。

#### 数えた結果（2026-11-14）

道具：`node scripts/catalog_text_roundtrip.mjs [--list]`。公開中の138件の文章（コスト・発動時効果・特記・タグ）を「文章から効果を作る」の読み取りにかけ、保存中の特記処理と比べる。`target_scope` は文章からではなく画面の引き渡しで決まるので比べない。既定の値・重なった項目・説明だけの項目（`stat`、`flavor`、`data.display_name`、`delay: 0`、`lasting: -1`、`threshold: 1`、`apply_to: base`、カスタム効果の対象 `target`、`data.count` と `count`、`IMMEDIATE` と `PRE_MATCH`）はそろえて「意味が同じ」として数える。

| 結果 | 件数 |
|---|---|
| 読み取ると保存中の効果とそっくり同じ | 61 |
| 書き方が違うだけで意味は同じ | 32（うち、空の文章から中身のない効果を作るもの14） |
| 意味が違う | 41 |
| 読み取れない行がある | 4（E-14 のコスト「出血を5得る」、E-33〜35 の特別な説明） |

- 意味まで一致するのは93件（67%）。文章は、ほぼ読み取りの言い回しで書かれている。
- 意味が違う41件を1件ずつ見ると、ほとんどは読み取りの不具合だった（下の PR60-23 の一覧）。
- 文章とデータが本当に食い違うのは5件だった（下の「データの直し」）。
- 効果の数は180（条件つき23）。タイプは APPLY_STATE 84・APPLY_BUFF 42 が多く、ほかは21種類（カスタム効果7種類を含む）。タイミングは的中時106・使用時33・マッチ勝利時19・ラウンド終了時12など。

#### 決めたこと（2026-11-14 ユーザー決定）

- **言い回しの決まりは、読み取り（`static/js/master_data/skill_text.js`）と同じものを正本にする。** 効果から文章を作るのは、読み取りの決まりの裏返し。作った文章を読み取ると、同じ意味の効果に戻ることをテストで確かめる。`summary`（効果の札の見出し）とは別の決まりになる。
- **文章とデータの食い違いは、一覧にして先に直す。どちらに合わせるかは、5件とも文章に合わせる。**

#### データの直し（PR60-23 の前に、管理画面から）

| スキル | 文章 | 直す前のデータ | 直し方 |
|---|---|---|---|
| Ms-06 | MPを3消費 | コスト MP 2 | コストの MP を3に |
| Mb-13 | 破裂6を付与 | 2件目の効果 破裂 4 | 値を6に |
| Pb-10 | FPを4消費 | コスト FP 2 | コストの FP を4に |
| E-20 | (的中時):２ラウンド後まで、自身の物理補正+1 | 使用時（PRE_MATCH）、3ラウンド | タイミングを的中時（HIT）に。続く長さ（3、このラウンドと2ラウンド後まで）はそのまま |
| E-06 | このスキルは使用したターンの間は消滅せず、再利用する | 該当する効果なし | 今の効果タイプでは書けない（攻撃の再使用 `USE_SKILL_AGAIN` とは別の、防御がそのラウンドのあいだ残る動き）。今は害がないので**直さずに置く**（2026-11-14 ユーザー決定）。往復の確かめの例外にする |

Ms-06・Mb-13・Pb-10・E-20 の4件は本番で直し、手元へ取り直した（2026-11-14）。直した後の数は、そっくり同じ62・意味は同じ33・意味が違う39・読み取れない4。E-20 と Pb-10 に残る違いは読み取りの側の不具合（下の10と13）。

#### PR の分け方

1. **PR60-23 読み取りの直し**：138件の文章を読み取ると、保存中の効果と同じ意味になるようにする。例外は読み取れない4件と E-06 の1文だけ。往復の確かめの土台。
2. **PR60-24 効果から文章を作る**：読み取りの決まりを裏返して文章を作り、「文章」の節で今の文章と左右に並べて欄ごとに置き換える。「効果の説明」も同じ決まりの文にする。食い違いの注意を出す。画面は試作で決めてから、この節に詳細を書く。

#### PR60-23：読み取りの直し

**PR60-23 完了。** `--list` はそっくり同じ93件、意味は同じ40件、意味が違う0件、読み取れない5件。読み取れないのは E-06・E-14・E-33・E-34・E-35。E-06 は攻撃の再使用に変換せず、読み取りエラーを出す。`--check` は例外を除く133件で成功した。確認用DBの管理画面で Mb-00・Ps-04・Mb-12 を読み直し、保存済みの効果と同じ意味になることを確認した。

目標：`node scripts/catalog_text_roundtrip.mjs --check` が、例外（E-14・E-33・E-34・E-35・E-06）を除く133件すべてで「同じ」か「意味は同じ」になり、それ以外があれば失敗で終わる。pytest からこれを呼ぶテストを足す（`--check` は道具に足す）。

直す読み取りの不具合（41件を見て分けたもの。例のスキルで確かめる）：

1. 空の欄から効果を作らない（D-00・E-00 ほか、空の文章から中身のない APPLY_STATE を作っている14件）。
2. 同じタイミングの2文目以降もそのタイミングにする（Mb-00・Mp-00・Ms-00・Ps-06：ラウンド終了時・マッチ勝利時の2文目が的中時になる）。
3. 「〜なら、」の条件を落とさない（Mb-08・Mb-10・Ms-02・Pb-02・Mp-03・Ms-04・Ps-12）。
4. 同じ効果を2回作らない（Ps-04・Mp-09・Pp-05・Pb-07・Mp-04・Pp-07・E-29）。Mp-04 の「1につき4ダメージ」が既定の3に置き換わるのも直す。
5. 「（最大でN）」を落とさない（Mp-06・Pp-07）。
6. 「〇〇をN消費し、△△を得る／回復する」を消費して得る効果（`CONSUME_BUFF_COUNT_FOR_GAIN`）として読む（Mb-12・Ps-13）。
7. 「より高い」「より大きい」を GT にする（D-06）。
8. カスタム効果（出血氾濫など）の対象の既定を、保存中のデータと同じ「対象」にする（Ps-05・Ms-04・Ms-08）。自分にかけるときだけ「自分に」と書く（Ms-09）。
9. バフの名前の取り違えと、対象の取り違えを直す（Mp-05 は Bu-40、Pb-11 の震盪は Bu-29 を対象に、E-09 は自身の+1 と対象の-1 の2つ、E-16 の遅れの順）。
10. 時間の言い方を読み分ける：E-20「２ラウンド後まで」、E-25「(戦闘開始時):…ラウンド終了時まで」、Ms-07「2ラウンドの出血遷延」（出血遷延は残り回数 `count` で数える）。
11. 特別な言い回し：Mb-07「付与から数えて3回目のラウンド終了時に自身に破裂爆発を起こす」状態（Bu-07）、Pp-06「亀裂崩壊。消費した亀裂4につき1回、破裂爆発」と特記「このスキルを使用している間、相手の破裂威力は減少しない」（Bu-06）、E-12「その後、ラウンド終了」（タグ「ラウンド終了」で表す）。
12. タグに英字の別名を重ねない（C-00・E-25 の `non_damage`・`self_target`）。
13. 「対象の破裂威力の値だけ基礎威力を加算（最大で30）」の「最大で30」を落とさない（Pb-10）。Pb-10 の保存中のデータは項目名が `operation` でなく `operator` だが、戦闘も見込みもどちらも読むので、比べ方で同じと見なす（データは直さない）。

- 同じ意味の書き方が2つあるもの（`FIXED_IF_EXISTS` と `threshold`、`FIXED` と `condition` など）は、読み取りが作る形を1つに決め、比べ方（道具の `meaning`）で同じと見なす形を資料に書く。保存中のデータは書き換えない。
- 旧ビルダーと同じ結果であることを固定していたテスト（`tests/fixtures/skill_text_legacy.json` の144件）は、直した結果に期待値を改める（後方互換は持たない）。
- 変えないもの：保存形式、戦闘の処理、ほかの画面。

確認：道具の `--list` で例外以外が0件になること。管理画面で、直したスキルのいくつか（Mb-00・Ps-04・Mb-12）を「文章から効果を作る」で読み直し、効果が変わらないこと。

資料：C01（文章の読み取りの決まりの追補：直した言い回しと、同じ意味の形）、E02 は変更なし。終わったら、この節に「PR60-23 完了」と結果の数を書く。

#### PR60-24：効果から文章を作る（PR60-23 の後に詳細を書く）

- 読み取りの決まりの裏返しで、コスト・発動時効果・特記の文章を作る。用語は `[[W-xx|名前]]` でつなぐ。同じタイミングの効果は1文にまとめ、組になった効果（上の6）は1つの文にする。
- 「文章」の節に「効果から文章を作る」を置き、今の文章と作った文章を欄ごとに左右に並べ、欄ごとに置き換える（保存はしない）。
- 「効果の説明」も同じ決まりの文にする（「?へスキルを最大1回再使用」の「?」もなくなる）。
- 食い違いの注意：文章を読み取った効果と保存中の効果の意味が違うとき、申請を止めない注意として画面に出す。補足だけの文（上の4）を数えない方法も決める。
- 既存の138件の文章は書き直さない。

### 5.17 コストの呼び名と、補正を付けない印（PR60-20）

**完了（2026-11-11）。** 旧キーの起動時移行と、キャッシュ・管理画面・戦闘の表示・見本のキー改称を実装した。読み替えは設けず、戦闘の支払いと `特記処理.cost` は変更していない。補正なしの文は共有JSONに置き、検査・パレット生成・文章の読み取りで同じ判定になることを確かめた。

別SQLite DBで公開138件・下書き1件・履歴138件を移行し、旧キー277件→0件、新キー0件→277件。行数・値・キーの位置を保持し、2回目の更新なしと共存時の起動中止・ロールバックをテストした。公開APIとPs-01のコスト欄・【コスト】・文章生成を確認。E-26はリンク付きの印でパレットの注意が消え、補正なしのパレット生成と文章生成が通った。E-26などへの本番の追記は従来どおりpush後の作業。

検査：全件pytestは1898件成功・45件スキップ（481.65秒、タイムアウト1200秒）。npm run build、管理画面・解決画面の見本の再生成、文字コード・文字化け・構文の検査も成功。確認用DBと一時ログを削除し、手元のDBはハッシュの一致を確認した。


§6 の (4)（「使用時効果」と「コスト」）と (2)（補正を付けないスキルの印）を、1つの PR で片付ける。どちらもスキルの文章の欄・チャットパレットの検査・文章の読み取りに触る。§5.16 より先に行う（2026-11-11 ユーザー決定）。

#### 調べたこと（2026-11-11、`data/cache/skills_cache.json` の138件）

- `使用時効果` の欄は、空が48件、コストだけが89件（1種類63件、MP と FP など複数26件）。コスト以外は E-14 の「出血を5得る」1件だけ。
- 使用時に起きる効果は、`発動時効果` の欄に `(使用時)` を付けて書いてある（22件。C-00 の MP 回復、E-19 の召喚など）。つまり `使用時効果` の欄は、中身はコストの欄になっている。
- 本（`typst_manual/`）の「使用時効果」は「使用時に起きる効果」というルールの言葉で、この欄の名前とは別の意味。本は変えない。
- `取得コスト`（経験値で払う取得の値）は別の項目で、そのまま残す。

#### 決めたこと

- **(4) 項目名ごと「コスト」に変える。** データの項目名 `使用時効果` を `コスト` にし、画面の名前も「コスト」にそろえる。読み替え（古い名前も読む）は置かない。E-14 の「出血を5得る」は、使う代わりに負うものなので `コスト` に残す。
- **(2) 特記に決まった文を書く。** 補正を付けないスキルは、`特記` に「このスキルには物理補正を適用しない。」（魔法のスキルは「魔法補正」）と書く。データの印（新しい項目）は作らない。文はゲームのカードにもそのまま出るので、遊ぶ人にも分かる。

#### PR60-20 で変えること

1. **本番のデータを移す。** `manager/db_migration.py` の `run_auto_migration` に、`catalog_entries`・`catalog_drafts`・`catalog_history` の `kind='skill'` の payload で、`使用時効果` を `コスト` に移す処理を足す。キーの並びの位置は保つ。何度動かしても同じ結果になる（`使用時効果` が無ければ何もしない）。`コスト` と `使用時効果` の両方を持つ行があれば、起動を止める（ほかの列の追加と同じく fail-fast）。JSON の列は、新しい dict を入れ直して変更を確実に書く。手元の DB も同じ処理で移る。
2. **キャッシュと見本のデータ。** `data/cache/skills_cache.json` と `tests/fixtures/skill_text_legacy.json` のキーを `コスト` にする（位置は保つ）。
3. **サーバー。** `manager/catalog/skills.py` の `TEXT_FIELDS`、`manager/battle/power_preview.py` の `cost_text`（`コスト` だけを読む）、`scripts/verify_skill_constraints.py`。
4. **画面。** 管理画面（`skill.js` の項目と名前、`editor.js` の「文章」の節、`workspace.js` の読み取りへの受け渡し、`skill_text.js` の欄の名前と誤りの欄名、`skill_text_help.js` の例）。戦闘の画面（`DomUtils.js`・`legacy_globals.js` は `コスト` だけを読む、`resolve_stage.js`、`DeclarePanel.js`）。`owned_characters_modal.js` は「コスト」を表示し、取得の値の表示を「取得コスト（経験値）」に直して、2つのコストを取り違えないようにする。`wide_match_synced.js` の確認用の出力も `コスト` にする。
5. **補正を付けない印。** 文は「このスキルには物理補正を適用しない。」「このスキルには魔法補正を適用しない。」の2つ。スキルの `分類` と同じ補正の文だけを数える（物理のスキルに「魔法補正を適用しない」は印にならない）。用語のリンク（`[[W-53|物理補正]]` など）を付けて書いてもよく、比べるときはリンクを外した文字で比べる。文末の「。」は無くてもよい。
    - チャットパレットの検査（§5.10 PR60-10 の4）は、印があれば補正の項を付けない形を定型とする。
    - 管理画面の「項目から作る」も、印があれば補正の項を付けない。
    - 「文章から効果を作る」は、特記のこの文を読み飛ばす（効果を作らず、誤りにもしない）。
    - 判定はサーバーと画面で同じ文を使う。文はどちらか1か所に書き、もう片方はテストで一致を確かめる。
6. **見本の作り直しの道具。** `scripts/catalog_preview/`（`page.js`・`revision.js`・`export_api.py`・`pr19/`）と `scripts/resolve_preview/skills.mjs` の `使用時効果` も `コスト` にし、作り直せる状態を保つ。
7. **テスト。** 移す処理（古い payload を入れた SQLite で、3つの表が移ること・2回目は何もしないこと・両方を持つ行で止まること）、キャッシュと見本に `使用時効果` が残っていないこと、印の判定（物理・魔法・リンク付き・分類違い・文末の「。」なし）、検査・「項目から作る」・文章の読み取りが印に従うこと。既存のテストの `使用時効果` は `コスト` にする。
8. **確認。** 別の DB で、古い名前のデータから起動して移ることを見る。管理画面の「文章」の節が「コスト」になること、文章から効果を作るが通ること、ゲームのカードの【コスト】が出ること、E-26 の特記に印を書くとチャットパレットの注意が消えることを見る。

#### 触らないもの

- 本（`typst_manual/`）と `CharaCreator/`（Sheets を読む古い道具）。`logs/` と、計画書の過去の記録。
- 特記処理（`特記処理.cost`）の形と、戦闘でコストを払う処理。payload の項目名だけを変える。

#### push の後にすること

- 本番の公開 API のスキルに `コスト` があり、`使用時効果` が無いことを見る。push の前に `python app.py --pull` をしない（古い名前で取ってくるため）。
- E-26・E-27・Pb-10 の特記に印の文を、管理画面から下書き→承認で書き足す（ユーザー）。その後、手元は `--pull` で取り直す。

#### 資料の更新

C01（スキルの項目名とコストの欄、補正を付けない印の文）、E02（管理画面の「文章」の節）、A02（制作者向けの書き方に、印の文）、A04（項目名の一覧の `使用時効果` / `コスト` を `コスト` に）。終わったら §6 の (2)(4) を完了にする。

### 5.18 試し撃ち：威力の見込み（Phase 4、PR60-21、完了）

Phase 4（§3.3）は、この節の「スキルの素の性能の表示」だけにする。本物の処理で1回ぶつける機能・スキル同士の勝率・ルームでの有利不利の表示は、戦闘に関わる機能をまとめる別の画面として [計画63 戦闘マスター](63_Battle_Master_Plan.md) へ移した（2026-11-12 ユーザー決定。マスターデータの画面を膨らませないため）。付く状態とコストは、今の「効果の説明」と「ゲームでの見え方」が既に出しているので、4a は威力に絞る。

形は試作で確かめた（2026-11-12）。見本は `node scripts/catalog_preview/pr21/build.mjs` で作り、`python scripts/catalog_preview/pr21/serve.py` を動かして `http://127.0.0.1:8766/` で見る。本物の管理画面のコードに、本物の計算（`calculate_skill_preview`）をつないだもの。見本の作り（`scripts/catalog_preview/pr21/` の `power.py`・`overrides.js`・`card.css`）は正本ではなく、計算の前提・文の言い回し・カードの並びの見本として使う。

**完了（2026-11-13）。** スキルの閲覧・編集に「威力の見込み」を追加し、戦闘と同じ計算関数を呼ぶ読み取り専用 API を実装した。138件すべてで計算でき、36件の上乗せ41行を文章化できた。確認用DBの制作者で1280×720と680pxの編集・閲覧を確認し、Ps-04・Mb-13・Ms-09・E-30 の見込みと上乗せが試作と一致した。Ps-04 で補正5・3とパレットの再生成を確認した。全件テストは1903件成功、45件スキップ。

#### 決めたこと（2026-11-12 ユーザー決定）

- **普段は補正なしの値を出し、「補正を適用」を入れたときだけ補正の欄を出す。** 欄はチャットパレットが使う補正（物理補正・魔法補正）のものだけ。適用するときの初めの値は5（キャラ作成の既定値、`events/socket_char.py`）。入れたかどうかと欄の値はブラウザーに覚えさせ、全スキルで共通にする（`localStorage`、効果タイプの英字キーと同じ扱い）。（同日、はじめは「欄をいつも出し初めは0」と決めたが、こちらに改めた。）
- **条件で増える威力は「基準の見込み＋上乗せの一覧」で見せる。** 条件の値を入れる欄は作らない。
- **出す場所は編集と閲覧の両方。** 編集中は右のプレビューに入力しながら出し、閲覧の詳細にも同じカードを置く。既存のスキル同士を見比べられる。
- **見込みはチャットパレットで計算し、項目と違えば1行で知らせる。** ゲームで振るのはチャットパレットなので、それに合わせる。編集中にダイス威力などを変えても、「項目から作る」でパレットを作り直すまで数は変わらない。そのため、パレットの式（`【】` より前）が項目から作る式と違うときは、カードに「チャットパレットが項目と違います（項目からは `7+2d6+1d{物理補正}`）。見込みはチャットパレットで計算しています。「項目から作る」でそろえると見込みも変わります。」と出す。
    - （検証で直した、2026-11-13）戦闘は基礎威力を「基礎威力」の項目から、ダイスをパレットの先頭の数字より後ろから読む（パレットにダイスが無ければ「ダイス威力」の項目）。見込みも本物のスキルをそのまま渡して戦闘と同じ値にし、食い違いの1行は「見込みはゲームと同じく、基礎威力を項目から、ダイスをチャットパレットから読んでいます。「項目から作る」でそろえてください。」とする。

#### 基準の見込み

- 使う人は、物理補正・魔法補正が0（「補正を適用」のときは欄の値）で、ほかの値・状態・バフはすべて0。**相手は置かない**（相手の値を見る条件は数えない）。この前提で、戦闘と同じ `calculate_skill_preview`（`manager/game_logic.py`）を動かし、最小・平均・最大を出す。計算を画面側に写さない（戦闘とのずれを作らない）。
- 平均は、出てきたダイスの式から求める（`NdM` は N×(M+1)/2）。
- 補正が0のとき、チャットパレットの `1d{物理補正}` は今の置き換えでは `1d0` になり、戦闘の幅の計算はこれを「最小1・最大0」と数えている。見込みでは面が0以下のダイスを0として数え、表示する式からも外す（Ps-04 は `7+1d6`・最小8）。戦闘の処理は変えない。
- `特記処理.power_bonus` の決まりのうち、この前提で成り立つもの（例：Ms-09「自分の出血が2未満なら基礎威力-7」）は、基準の見込みに入る。相手の値を見る決まり（例：E-30「相手の速度値が3以下なら基礎威力+4」）は入らない。入ったかどうかは、その決まりを除いて計算し直した結果と比べて決め、上乗せの一覧に示す。

#### 上乗せの一覧

- `power_bonus` の決まりを1行ずつ文にして並べる（例：Mb-13「相手の破裂4につき基礎威力+1（+3まで）」、Pb-14「自分の蓄力3につき最終威力+1（+7まで）」、Pp-10「相手の亀裂2につきダイスの面-1（-4まで）」、Pb-08「相手の破裂が0なら基礎威力+2」）。各行に、どこに足すか（基礎威力・ダイスの面・最終威力）と、基準の見込みに入っているかを付ける。今の138件のうち36件が持つ形（`FIXED`・`FIXED_IF_EXISTS`・`PER_N_BONUS`・操作なしの `condition` だけ、条件の比べ方 `GT`・`GTE`・`LT`・`LTE`・`EQUALS`、`threshold`・`max_bonus`・`min_bonus`・`apply_to`、`蓄力_count` の `_count`）をすべて文にする。試作では全件が文になった。文にできない形は「JSON を見る」と出し、黙って落とさない。
- 威力を変える効果（系統「威力・ロール」の効果と、スタックを消費して威力を変える `CONSUME_BUFF_COUNT_FOR_POWER`。例：Pb-10 の基礎威力の加算、Mb-13 の凝魔の消費）は、「効果の説明」と同じ文で一覧の下に並べ、「効果 · タイミング」を添える。

#### 画面

- カード「威力の見込み」（見出しに ⓘ「補正なしで、自分のほかの値はすべて0、相手はいないとして計算します。「補正を適用」で補正の値を入れられます。」）。上に「補正を適用」のチェックボックス。入れると、その下にチャットパレットが使う補正の欄だけを横並びで出す（`{物理補正}` を含めば物理補正、`{魔法補正}` なら魔法補正）。どちらも使わないスキル（E-26 など）はチェックボックスも出さない。その下に食い違いの1行（あれば）、「最小・平均・最大」の3つの枠、補正を入れたあとの式、見出し「条件で変わる威力」と一覧（無ければ「条件で変わる威力はありません。」）。
- 「ゲームでの見え方」と「効果の説明」の間。編集中も閲覧の詳細も同じ位置。編集中の再計算は入力が止まってから（約300ms）。チャットパレットが空・読めないときは、計算せずに理由を1行出す。
- 閲覧で一度出した結果は、PR60-19 の決まりどおりワークスペースの寿命だけ持つ（キーは種類・ID・版・補正の値）。

#### サーバー

- `POST /api/catalog/skill/power_preview`：本文は `{payload, params:{物理補正, 魔法補正}}`、返事は `{min, avg, max, dice, rules:[{text, apply_to, in_baseline}]}`（威力を変える効果は、画面が持つスキーマと `summary` で並べる）。保存も検査もしない。管理画面を開ける人（ログインした人）なら使える。payload が読めないときは 400 と理由。
- 本番のメモリ・戦闘の状態に触れない（ルームの状態を読まない・書かない）。

#### テスト

- Ps-04：補正0で最小8・平均10.5・最大13、物理補正3で `7+1d6+1d3`・最小9・平均12.5・最大16。
- E-26（補正を付けない印）は補正の欄を出さない。Ms-09 は `22-1d6-7`・最小9・平均11.5・最大14で、「出血が2未満なら-7」が基準に入り、E-30 の相手の条件は入らない。Mb-13・Pb-14・Pp-10・Pb-08 の文。文にできない形は「JSON を見る」になる。
- 食い違いの1行：Ps-04 でダイス威力を `+2d6` にすると出て、「項目から作る」で消え、見込みが `7+2d6` で計算し直される。
- 138件すべてで、エラーにならずに返事が返る。
- 画面：「補正を適用」を入れないと欄が隠れ、Ps-04 は最小8・平均10.5・最大13。入れると欄（初め5）が出て `7+1d6+1d5`・最小9・平均13.5・最大18。入れたかどうかと欄の値が覚えられ、別のスキルでも同じになる。閲覧の2回目は問い合わせが出ない。

#### 確認

ローカルの別 DB で、制作者として Ps-04・Mb-13・E-30 を編集と閲覧で見る。「補正を適用」の出し入れと欄の値で数が変わること、1280×720 と 680px で崩れないことを見る。

#### 資料の更新

E02（管理画面のプレビューのカード）、A02（制作者向けに、見込みの読み方と基準の前提）、F01 か C01 のどちらか近い方に API。終わったら §5 の表の Phase 4 を完了にする。

### 5.19 未対応の効果のリクエスト（Phase 5、PR60-22、完了）

§3.4 の「リクエスト」を作る。今の効果タイプで作れない効果を、制作者が管理画面から管理者に頼み、管理者が状態とメモで答える。

形は試作で確かめた（2026-11-13）。見本は `node scripts/catalog_preview/pr22/build.mjs` で作り、`_local` を配って `http://127.0.0.1:8765/catalog_preview/pr22/index.html`（管理者の見え方）と `?as=author`（制作者の見え方）で見る。本物の管理画面のコードに、リクエストの場面を重ねたもの。データは画面の中だけに持つ。見本の作り（`scripts/catalog_preview/pr22/` の `overrides.js`・`request.css`）は正本ではなく、並び・言い回し・流れの見本として使う。

**完了（2026-11-14）。** 5種類の効果の節と一覧からの提出、本人の修正・取り下げ、管理者の回答を実装した。確認用DBの制作者・管理者で Ps-04 の保存前の知らせ、提出後の編集への復帰、下書きとリクエストの行き来、回答の表示を確認した。1280×720と680pxで表示し、コピーした Markdown は試作と同じ順に実際の下書きの文章・効果 JSON と回答を含む。

#### 決めたこと（2026-11-13 ユーザー決定）

- **出せる人**：制作者と管理者。一般の人には見出しのボタンも API も出さない。
- **対象**：効果を持つ種類すべて（スキル・バフ・アイテム・特殊パッシブ・輝化スキル）。用語と召喚テンプレートは対象外。
- **入口は2つ**：
    - 編集の「効果」の節のいちばん上に「作りたい効果がタイプに無いときは **リクエストを出す**」の1行。押すと、編集中の下書きがひもづいたフォームを開く。
    - 見出しの「リクエスト」の場面の「＋新しく出す」。下書きはひもづかない。
- **一覧の置き場**：見出しの「承認待ち」の左に「リクエスト n件」のボタン（n は受付と対応中の件数）。押すとリクエストの場面になり、「← 戻る」で元の場面へ戻る。種類タブは増やさない。
- **見える範囲**：制作者・管理者の全員が全件を見られる（同じ効果を二重に頼まないため）。直す・取り下げるは、出した本人だけが、状態が「受付」のあいだだけできる。
- **やりとり**：管理者のメモ1つ。状態とメモは管理者だけが変える。「実装済み」にするときは、使う効果タイプをメモに書く（専用の欄は作らない）。知らせ（通知）は作らず、見出しの件数と一覧で分かるようにする。
- **依頼文としてコピー**：AI エージェントに渡すたたき台の Markdown を、クリップボードに写す（下の「依頼文」）。
- **出した後**：効果の節から出したら、編集の画面に戻り「リクエストを出しました。上の「リクエスト」から見られます。」と知らせる。一覧から出したら一覧に残り、出したものを選んだ状態にする。
- **保存前**：ひもづけられるのは保存済みの下書きだけ。効果の節から出そうとしたとき、まだ下書きを保存していなければ「先に下書きを保存してください。」と知らせてフォームを開かない（下書きなしで出したいときは一覧から出す）。
- **下書きの側からの見え方**：ひもづくリクエストがある下書きは、閲覧の詳細と編集の上の帯に「効果のリクエスト：題（状態）」を1行出す。押すとそのリクエストを選んだ一覧へ移る。

#### データ

新しい表 `catalog_effect_requests`（起動時の `db.create_all` で作る）。

| 列 | 中身 |
|---|---|
| `id` | 番号 |
| `title` | 題（必須、80字まで） |
| `want` | 欲しい効果（必須） |
| `example` | 文の例（任意） |
| `near_type` | 近い効果タイプ（任意、`EFFECT_SCHEMAS` のキー） |
| `draft_id` | ひもづく下書き（`catalog_drafts`、消えたら NULL） |
| `draft_kind`・`draft_target_id`・`draft_name` | 出したときの下書きの写し。下書きは承認・取り下げで消え、新規の X-ID は承認で正式IDに変わるため |
| `status` | `open`（受付）・`in_progress`（対応中）・`done`（実装済み）・`declined`（見送り） |
| `memo` | 管理者のメモ |
| `created_by` | 出した人（`users`、消えたら NULL） |
| `created_at`・`updated_at` | 日時 |

- 下書きが承認で正式IDになったときは、ひもづくリクエストの `draft_target_id` を正式IDに直す。
- 下書きが消えた後は「下書きは公開・取り下げで無くなりました（スキル Ps-04）」と出し、コピーの依頼文には公開中の版を入れる（無ければ写しの ID と名前だけ）。

#### API

すべてログインと制作者または管理者の印が要る（`_endpoint("author")`）。

- `GET /api/catalog/effect_requests`：全件を新しい順に。出した人の名前を付ける。
- `POST /api/catalog/effect_requests`：`{title, want, example, near_type, draft_id?}`。`draft_id` は効果を持つ種類の下書きだけ。写しの列を埋める。
- `PATCH /api/catalog/effect_requests/<id>`：本人・受付のときだけ。題・欲しい効果・文の例・近い効果タイプ・ひもづけを外す。
- `DELETE /api/catalog/effect_requests/<id>`：本人・受付のときだけ（取り下げ）。
- `POST /api/catalog/effect_requests/<id>/review`：管理者だけ。`{status, memo}`。
- `GET /api/catalog/overview` の返事に、制作者・管理者のとき `open_requests`（受付と対応中の件数）を足す。
- 他の人へのソケットの知らせは出さない。画面は PR60-19 の決まりで、一覧をワークスペースの寿命だけ持ち、自分の操作と「更新」で読み直す。

#### 画面

- 場面：上の帯（「← 戻る」と「効果のリクエスト」）、状態の絞り込み（受付・対応中／実装済み／見送り／すべて、件数つき）と「＋新しく出す」、左にカード（題・状態の札・出した人・日付・下書きのID）、右に詳細かフォーム。680px では縦に積む。
- 状態の札：受付は青、対応中は黄、実装済みと見送りは灰（色だけに頼らず文字で書く）。
- 詳細：題・状態・出した人・日付、欲しい効果、文の例、近い効果タイプ（名前と英字キー）、元の下書き（押すとその下書きを開く）、管理者のメモ（あれば）。操作は「依頼文としてコピー」（誰でも）、「直す」「取り下げる」（本人・受付）、管理者の「状態」「管理者のメモ」「状態とメモを保存」。
- フォーム：題（一言で）・欲しい効果・文の例（ゲームの書き方で）・近い効果タイプ（任意、系統ごとのまとまり）・元の下書き（「外す」）。上に「今の効果タイプでは作れない効果を、管理者に頼みます。出したリクエストは制作者の全員が見られます。」。題と欲しい効果が空なら「題と欲しい効果は必ず書いてください。」。

#### 依頼文

見本の `copyText` の並び：見出し「効果のリクエスト：題」、状態・出した人と日付、「欲しい効果」「文の例」「近い効果タイプ」（キーと名前）、「元の下書き」（種類・ID・名前、スキルならコスト・発動時効果・特記の文章、効果の JSON）、「管理者のメモ」、「作り方」（新しい効果タイプは `manager/battle/effect_handlers/` にハンドラを足し、`HANDLERS` と `SCHEMAS`（group・label・description・項目）に登録する。`tests/test_effect_schemas.py` のキー一致のテストを通す。開発ルールは `AGENTS.md` に従う）。

#### テスト

- 印：一般の人は全 API が 403、制作者は出す・自分の分を直す・取り下げる、他人の分と受付以外は直せない、状態とメモは管理者だけ。
- 下書き：効果を持たない種類（用語・召喚）の下書きはひもづけられない。承認で正式IDに直る。下書きが消えると `draft_id` が NULL になり写しは残る。
- `overview` の `open_requests` の件数。
- 画面：効果の節の入口（5種類）、保存前の知らせ、出した後に編集へ戻ること、下書きの側の1行、コピーの Markdown の並び、PR60-19 の読み直しの決まり。

#### 確認

ローカルの別 DB で、制作者として Ps-04 の効果の節から出す（保存前の知らせ→保存→出す→編集へ戻る）、一覧から下書きなしで出す、直す・取り下げる。管理者として状態とメモを変え、制作者の側で見えることを見る。1280×720 と 680px。

#### 資料の更新

E02（リクエストの場面）、A02（制作者向けに、出し方と状態の意味、管理者向けに答え方）、F01（API）、C01 に新しい効果タイプを足すときの入口としてリクエストの依頼文の使い方。終わったら §5 の表の Phase 5 を完了にする。

## 6. 未決定事項

§5 の各 Phase は完了した。以下は移行後に検討する事項。「効果から文章を作る」は §5.16 に記録している。(3)のUI改修は完了（§5.14・§5.15）。管理画面専用の操作マニュアルは別途検討する。

- (1) **一括編集の手段**：正本は DB に決めた（§8）。表計算でしていた一括の書き換え・見比べを何で補うか。CSV の書き出し・読み込み、管理画面に軽い表計算の機能を持たせる、AI エージェントが API 経由で下書きをまとめて作る、などの候補がある。今はあまり使っていないため、必要になった段階で決める。
- (2) **補正を付けないスキルの印**（2026-11-08 ユーザーの覚書）：チャットパレットに物理補正・魔法補正の項が無いスキル（今は E-26・E-27・Pb-10）が、意図した例外か書き忘れかを、データの上で分かるようにしたい。データの印ではなく、スキルの説明（`特記` など）に「このスキルに物理補正は適用されない」のように書いておく形を考えている。書くかどうか、書く言い回しを決めて検査がそれを読み、チャットパレットの注意（§5.10 PR60-10 の4）を出さないようにするかは、必要になったら決める。3b では入れない。→ **決定（2026-11-11）**：特記に「このスキルには物理補正（魔法補正）を適用しない。」と書く。PR60-20（§5.17）で検査・「項目から作る」・文章の読み取りが読む。**実装完了（2026-11-11）。**
- (4) **「使用時効果」と「コスト」の呼び方**（2026-11-11 ユーザーの覚書）：スキルのコストの文章は、データの項目名が `使用時効果`（Sheets の列の名残）で、管理画面の「文章」の節にもその名で出る。一方で、設定の節は「コスト」、ゲームのカードは「【コスト】」と呼ぶ。同じものに2つの名前があって紛らわしいので、「コスト」にそろえたい。画面の表示名だけを変えるか、データの項目名（`使用時効果`、C01・戦闘の処理・文章の読み取り・キャッシュ）まで変えるかを決める。この PJ は後方互換を持たない方針なので、変えるなら項目名ごと変えるのが筋。PR60-19 には入れない。→ **決定（2026-11-11）**：項目名ごと `コスト` に変える。本番のデータは起動時に移す。PR60-20（§5.17）。**実装完了（2026-11-11）。**
- (3) **管理画面の見やすさの改修**：7種類の閲覧・編集・承認・スキル専用・狭い幅を洗い出し、試作で形を決めた（2026-11-10）。
    - 決まり：①項目を意味のまとまりで区切る、②色だけに頼らず札と文字で状態を示す、③文字4.5:1・操作枠3:1以上、④主操作は場面ごとに1つ、⑤戻る・保存・危ない操作の場所を揃える、⑥内部名はJSONに任せる、⑦候補と条件に合う欄で入力を助ける、⑧保存前の変更を失わせない、⑨浮かぶ枠は外の1回の操作で閉じ、知らせで画面をずらさない。
    - 見本：`npm run catalog-preview` の `/_local/catalog_preview/ui_revision.html`（`scripts/catalog_preview/revision.js`・`revision.css`）。案Aは今の3列と縦の編集、案Bは上の種類タブと編集の節の目次。1280px・680pxで操作と収まりを比べた。
    - 決定：閲覧・編集は案B、承認は案A（変わった項目を左右に並べる）。両案に共通の札・色・保存時の下書き作成・未保存の確かめ・挿入の枠・操作の置き場・知らせ・下の帯はすべて採用。実装は §5.14・§5.15 の PR60-16→17→18。
    - UI改修はPR60-16（共通の土台）・17（並べ方・候補・効果フォーム）・18（承認の差分）をすべて完了した（2026-11-11）。本番で使ってみての直し（専用画面・線・高さ・取得・入力の補助）もPR60-19で完了した（同日）。決まり3の3:1は操作の枠だけに当て、飾りの線には当てない。
    - 詳しい説明は画面内へ増やさず、管理画面専用の操作マニュアルで補う。アプリのマニュアル体系の設計と協力して置き場・形を決める（PR60-16〜18 には含めず、改修の後に別で進める）。洗い出しと決まりごとの全文はコミット 6c4526bb の §6-3 にある。

## 7. 関係

- マスターデータベース・プロジェクト：この計画はその段階1。段階2の[計画61](61_Enemy_Behavior_Pattern_Plan.md)（敵キャラと行動パターン）と、データの形（種類＋ID＋中身＋版）・参照の検査・廃止の扱いを共通にする（§8 論点10）。
- 計画45：§2-1 の「マスターデータの正本は Sheets のまま」は、この計画の論点1で、移った種類について置き換えた。Tier B（マスターデータの寄稿）の将来拡張 §12 は、この計画の範囲と重なる。この計画が進めば、Tier B の受付はこの管理画面で行う形になる。§12 の `X-` 接頭辞・検証・サンドボックスの検討をここで引き継ぐ。
- 計画41：Phase 1 の「記法の4区分表」のうち効果タイプの区分は、この計画のスキーマを正本にし、計画41はそこから作るか参照する（§8 論点9）。
- 仕様：JSON 定義は C01、効果の処理は B01・B02、権限は F01 Part 1-B・Part 6、シミュレータは F03。

## 8. 決定事項ログ

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 2026-11-04 | 計画の立て方 | **マスターデータ管理画面の構想を計画60のたたき台にする** | ユーザーの希望。スキーマ・管理画面・試し撃ち・リクエストの4つの柱で、議論前の材料をまとめる |
| 2026-11-04 | 論点1 正本の置き場 | **DB へ一本化する。種類ごとに移し、移っていない種類は当面 Sheets から取り込む。計画45 §2-1（正本は Sheets）は、移った種類について置き換える** | 検査と承認を必ず通る入口を1つにできる。Sheets の直接編集という抜け道が残らず、push なしで反映できる。表計算の一括編集は今あまり使っておらず、別の手段で補える |
| 2026-11-04 | 論点2 権限 | **閲覧は全員、提案はアプリ管理者が指名した制作者、承認はアプリ管理者（`is_app_admin`）。新しく作るのはユーザーの制作者の印だけ。AI エージェントに下書きを作らせるときは、ユーザーの権限で提案者として動かす** | 数人の協力者という規模（計画45）に合い、権限の追加が最小で済む。承認を任せたい人が出たら、専用の役割へ広げる |
| 2026-11-04 | 論点3 ネタバレ | **下書きは制作者とアプリ管理者だけが見られる。公開したデータは今と同じく全員が見られる（マスターデータAPIは認証なしの全公開のまま）。敵専用のデータを隠す対策は、この計画では扱わない** | 戦闘の画面は全データを読む前提で、隠すには敵のスキルの送り方の改修が要る。作成の手間を下げる目的とは別の問題で、計画45も全公開を前提にしている。必要になったら別の計画にする |
| 2026-11-04 | 論点7 公開の反映 | **公開したらすぐ全体に反映する。共有の辞書をその場で入れ替え（今の `clear()`＋`update()` と同じ）、つながっている画面へソケットで知らせて読み直させ、戦闘中のルームのログに一行出す。戦闘中のルームも、次にそのスキルを使った時点から新しい定義になる** | 戦闘の処理は使うたびにIDで辞書を引くため、改修が小さい。仲間内の規模で、公開のタイミングは承認者が握れる。ルームごとに古い定義を残すには辞書の引き方の大きな改修が要る |
| 2026-11-04 | 論点5 試し撃ちの範囲 | **計算だけのプレビューと、別のプロセスで本物の処理を1回ぶつけてみる機能を作る。短い戦闘の集計は作らず、今の CLI（F03）に任せる** | シミュレータは動かす間アプリ全体の部品を差し替えるため、本番のプロセスでは動かせない。別のプロセスなら辞書の引き方の改修も要らない。集計はバランス調整の道具で、承認者がローカルで回せば足りる |
| 2026-11-04 | 論点4 ID の採番 | **下書きは仮の ID（`X-` で始まる）で作り、承認のときに承認者が正式な ID を付ける。仮の ID を参照しているほかの下書きも、そのとき書き換える。公開したデータに `X-` の ID が混ざっていたら検査でエラーにする（計画45 §12-1 の案を採る）** | ユーザーの判断。使われなかった番号が残らず、正式な ID の付け方を承認者が握れる |
| 2026-11-04 | 論点4-補 公開後の ID と消し方 | **公開した後は ID を変えられない。消す代わりに「廃止」の印を付け、新しく選ぶ一覧からは外し、すでに使っているキャラやプリセットではそのまま動かす** | ID はチャットパレット・プリセット・ほかのスキルの JSON から参照され、持ちキャラのチャットパレットのようにアプリが把握しきれない所にも書かれる |
| 2026-11-04 | 論点6 リクエストの置き場 | **管理画面の中の一覧に置く。状態は受付・対応中・実装済み・見送りで、元の下書きにひもづける。計画書・Issue のたたき台としてコピーできるボタンを付ける** | メンバーがアプリの中だけで済み、どの下書きがどの効果を待っているかが分かる。GitHub のトークンをサーバーに置かずに済む |
| 2026-11-04 | 論点8 文章から JSON を作る機能 | **今の決まった言い回しを読み取る機能を管理画面へ移し、逆向きの「JSON から文章」をスキーマの説明文で作って並べて見せる。LLM はアプリに入れず、自由な文章からの作成は外の AI エージェントが API で下書きを作る** | 費用と API キーをアプリに持ち込まずに済む。文章と JSON の食い違いにすぐ気づける。外の AI エージェントの動かし方は論点2で決めてある |
| 2026-11-04 | 論点9 始める時期と計画41との分担 | **Phase 1（スキーマ）はいつでも始めてよい。Phase 2 以降は計画46の主な作業が落ち着いてから。効果タイプの区分は、この計画のスキーマを計画41 Phase 1 の区分表の正本にする** | Phase 1 は小さく、それだけでビルダーのずれがなくなる。計画41の区分表の土台にもなり、二度手間が減る |
| 2026-11-04 | 論点10 保存の形 | **`preset_resources` とは別に、同じ形（種類＋安定した ID＋中身の JSON＋版）の `catalog_entries`（公開中）・`catalog_drafts`（下書き）・`catalog_history`（公開の履歴）を作る。参照のつながりは表に保存せず、必要なときに中身の JSON から計算する** | プリセットは持ち主が直接保存し、ルールの部品は承認して公開するため、流れの違うものを同じ表に入れない。形を揃えて参照の検査を共通にできる。件数が小さく全走査で足り、参照の表の更新し忘れを避けられる |
| 2026-11-06 | UI論点1 画面の形と入口 | **今のアプリ（`index.html`）の中の大型ワークスペースにする。プリセット管理ワークスペース（E02 Part 10・11）と同じ作りで、入口はロビーの「マスターデータ」ボタン（閲覧は全員なので全員に見せる）。データごとの URL は最初は作らず、必要になったら「アプリを開いたらそのデータの詳細を開く」URL を足す** | ログイン・公開時のソケットの知らせ・画面の部品と CSS をそのまま使え、プリセット管理と見た目や操作が揃う。権限の作りが違うプリセット管理のタブにはしない |
| 2026-11-06 | UI論点2 並べ方 | **閲覧はプリセット管理と同じ3ペイン（左：種類と絞り込み、中央：一覧、右：詳細）。編集のときだけ同じワークスペースの中で一覧と詳細をたたみ、左に入力・右に文章・JSON・プレビュー・1回ぶつけてみるの2列にする。「戻る」で選んでいたデータのまま一覧に戻る。承認は左の絞り込みの「承認待ち」（アプリ管理者だけ）から、公開中の版と下書きを左右に並べた差分を同じ広い並びで見せ、承認・却下のボタンを置く。狭い幅はプリセット管理と同じく980px以下で詳細を下に、680px以下で縦に積み、編集の2列も縦に積む** | 編集は入力しながらプレビューを見るのが中心で、横に広く使える。ワークスペースを出ないので戻り先を見失わない。新しく作る編集画面を別のモーダルに分ける理由は薄い |
| 2026-11-06 | UIの進め方 | **UI の論点がすべて決まったら、実装の前に見た目の試作（プレビュー）を作り、ユーザーが確かめてから Phase 2 の実装に入る。試作は本番のバンドルに入れず、Git 管理外の置き場（解決パネルの見本と同じく `/_local/` の下）に出す** | ユーザーの希望。実際の画面を見て直してから作るほうが、作り直しが少ない |
| 2026-11-06 | UI論点3 編集の入力の形 | **編集の並びの左列に「フォーム」「JSON」「文章から作る」のタブを置く。フォームはスキーマから作り、効果タイプを選ぶとその項目の欄が出る（普段はここで作る）。JSON は直接書き換えられ、正しく読めればフォームへ反映し、読めなければエラーを出してフォームには戻さない。文章から作るは今のビルダーの決まった言い回しの読み取りで、結果をフォームと JSON に入れる。スキル本体の項目（基礎威力・分類・距離・チャットパレットなど）は種類ごとに決まった項目の定義を用意し、効果の共通キー（`timing`・`target`・`condition`）の定義は Phase 3 でスキーマに足す** | メンバーはフォーム、ユーザーや AI エージェントは JSON と使い分けられ、今のビルダーの入力の仕方も引き継げる |
| 2026-11-06 | UI論点4 今の JSON ビルダーの扱い | **管理画面に吸収する。Phase 2（用語図鑑だけ）の間は今のビルダーをそのまま使い、スキルを管理画面で編集できるようになった時点（Phase 3）で、ビルダーの HTML・`/json_builder`・`/api/json_builder_reference` を消す** | 入力の作りを1か所にでき、Phase 2 の間もスキルを作る手段が途切れない。スキルの正本が DB に移ると、ビルダーの貼り付け先の Sheets がなくなる |
| 2026-11-07 | プレビュー論点1 入れる場面 | **閲覧（3ペイン）・編集（2列）・承認（差分）の3場面と、幅の切り替え（広い・980px・680px）。ロビーの入口ボタンは場面の頭に小さく見せる。リクエストの一覧は入れない** | 承認の差分は幅の使い方がいちばん難しく、先に見ておく価値がある。リクエストは Phase 5 で先 |
| 2026-11-07 | プレビュー論点2 見本のデータ | **一覧は今のキャッシュの実際のデータを並べ、編集の見本は用語1件とスキル1件（効果を持つもの）。説明文は PR60-1 の本物の関数で作る** | 本物の件数や文章の長さで見ないと、一覧の詰まり具合や欄の幅を判断しにくい。スキルのフォームが無理なく収まるかを今のうちに確かめられる |
| 2026-11-07 | プレビュー論点3 どこまで動かすか | **見て回れる程度に動かす（場面と幅の切り替え、一覧の選択、絞り込み、入力のタブ、効果タイプで欄が入れ替わる）。保存・承認・検査・1回ぶつけてみるは見た目だけ（結果は固定の見本）。フォームと JSON の行き来は作らない** | 触らないと分からない所だけを見られるようにし、試作を実装と同じ重さにしない |
| 2026-11-07 | プレビュー確認1 スキルの並べ方 | **スキルは Sheets と同じカテゴリ（ID の頭：Ps・Pb・Pp・Ms・Mb・Mp・D・B・C・E）ごとに分けて見せ、マスターデータ画面とは別のスキル専用の画面で扱う。見た目と編集・承認の並びは共通。スキルの下書きは作るときにカテゴリを選び、正式な ID はそのカテゴリの頭で番号を取る** | ユーザーの判断。10のカテゴリを種類の一覧と同じ列に入れると、ほかの種類を探しにくい。スキルは件数がいちばん多く、今後も増える |
| 2026-11-08 | 追補1 関連用語と別名の入力 | **関連用語は札と検索の候補から選んで足し、別名は打って Enter で足す形にする（§5.6、PR60-6）。Phase 3 の前に行う。相手側へのリンクの同時追加と並べ替えは入れない** | ユーザーの希望。本番で使ってみて、JSON の配列を手で書く入力は手間がかかり間違えやすいと分かった |
| 2026-11-08 | Phase 3 論点1 段の分け方 | **2段に分ける。3a でバフ（53件・7項目）を移し、参照の検査をここで作る。3b でスキル（138件）を移し、スキル専用の画面・効果のフォーム・「文章から作る」のタブ・JSON ビルダーの削除を入れる** | スキルはバフを参照するので、先にバフの参照の検査を作ればスキルでそのまま使える。小さいバフで、戦闘に効くデータでも型が回るかを確かめられる。本番に出す1回の変更が小さい |
| 2026-11-08 | Phase 3 論点2 Sheets からの取り込み | **用語と同じにする。種類を DB に移した時点で `--update` からその種類の取り込みを外し、DB が空のときだけキャッシュから最初の中身を入れる。Sheets の表はアプリから読まなくなり、残すか消すかはユーザーが手で決める。3a と 3b の間は、バフはアプリ、スキルは Sheets で直す** | 正本が2つある期間を作らない（論点1）。用語で試して問題がなかった。今はメンバーがデータを直していないので、間を短くすれば影響はない |
| 2026-11-08 | Phase 3 論点3 公開の知らせ方 | **ルームのログには出さず、画面の表示も出さない。今の `catalog_updated` で裏で読み直すだけにする（論点7の「戦闘中のルームのログに一行出す」を取り消す）** | ユーザーの判断。効果の変更は頻繁ではない |
| 2026-11-08 | Phase 3 論点4 保存前の検査 | **段階で分ける。下書きの保存では参照の問題（参照先がない・参照先が廃止・仮の ID）で止めず、画面に問題の一覧を出す。承認・公開では、形・参照先がない・仮の ID で止め、参照先が廃止は注意だけ出して承認者が判断する。形の検査は、Phase 2 の作り（書きかけのフォームも保存でき、申請で止める）に合わせて申請の時点で止める（§5.8）** | まだ承認されていない新しいバフ（`X-`）を使うスキルの下書きを並行して作れる。書きかけの途中保存が参照の問題で止まらない。存在しない参照は公開されない |
| 2026-11-08 | Phase 3 論点5 効果の共通の項目 | **`timing`・`target`・`condition` をスキーマに足す。`timing` と `target` は選択肢から選ぶ。`condition` は `source`・`param`・`operator`・`value` の4つの欄で作り、これに収まらない条件は JSON のタブで書く。スキル全体の項目（`cost`・`power_bonus`・`target_scope`・`tags` など）は種類の定義（`kinds.py`）に持たせる** | 今のスキル138件の条件23件はすべて4つの欄の形に収まる。フォームだけでスキルを作りきれ、知らないタイミングや条件の書き間違いも検査で見つけられる |
| 2026-11-08 | Phase 3 論点6 「文章から作る」とビルダーの削除 | **3b の最後の PR で、ビルダーの決まった言い回しの読み取りを管理画面の「文章から作る」タブへ移し、同時に別ページのビルダー（`/json_builder`）を消す（UI論点3・4 と論点8 のとおり）** | ビルダーの機能は残したい（ユーザー）。スキルを画面で作れるまではビルダーが残るので作る手段が途切れず、同じ機能が2か所にある期間も短い |
| 2026-11-08 | Phase 3 論点7 画面の作り | **3a で、`workspace.js` の窓を作る部分と中身を描く部分を分け、中身は渡された枠の中に描く作りにする。3b のスキル専用画面も同じ作りにする** | のちにメインメニュー（ロビーの前の画面、マスターデータ完了後に検討）を作るとき、窓の代わりにページの枠を渡すだけで1画面にできる。3a でどうせ触るので手間が少ない |
| 2026-11-08 | Phase 3b 論点1 手元のファイルと道具 | **本番から取ってくるコマンド（`python app.py --pull`）を作る。本番の公開 API から用語・バフ・スキルを読んで `data/cache/` を書き換え、手元では DB の公開データも入れ替える。Render の上では実行できない** | 本番のサーバーのファイルはデプロイで消えるので、公開時の書き出しではリポジトリに残らない。シミュレーター・lint・確認用スクリプトはファイルを読んだまま書き直さずに済み、コミットで本番の写しも残る。今の `--update` の取ってくる先が本番に変わる形 |
| 2026-11-08 | Phase 3b 論点2 チャットパレット | **手で書く欄のまま残し、「項目から作る」ボタンと、決まった形と違うときの注意を足す** | 138件中135件が決まった形で、残る3件（E-26・E-27・Pb-10）は補正の項がない例外。例外を残せて、名前や威力を変えたときの直し忘れにも気づける |
| 2026-11-09 | Phase 3b PR60-12 補助機能 | **早見表・行エラー・JSONコピーだけを移す。テンプレート/レシピ/震盪雛形・モード切り替え・動的バフ名チェックは移さず、ビルダーと専用経路を削除する** | ユーザー決定。前者には代わりがなく、後者は既存のフォーム/JSON/検査で代えられる |
| 2026-11-09 | 追補2 用語リンクとタイミングの入力 | **文章の欄の上に道具の帯を置き、「用語を挿入」（検索して選ぶとカーソルの位置に `[[W-xx|表示名]]`、選んだ文字は包む、`[[` と打っても候補を出す）と「タイミング」（行の頭に `([[W-xx|表示名]]):` を入れる。選択肢は用語の分類「タイミング」から作る）を足す（§5.11、PR60-13）。Phase 6 の前に行う** | ユーザーの希望。本番でスキルを書いてみて、リンクを手で打つのは手間がかかり間違えやすいと分かった。タイミングの一覧を用語から作れば、コードに二重に書かずに済む |
| 2026-11-11 | UI 改修 PR60-19 スキルの画面 | **スキルは種類タブの1つにせず、改修前の専用画面（左に10カテゴリ、「← マスターデータ」で戻る）に戻す。編集の中身は PR60-17 のまま** | ユーザー決定。本番で使ってみて、分類が選択欄に隠れて探しにくかった。案「スキルのタブの中に分類の列を出す」より前の形を選んだ |
| 2026-11-11 | コストの呼び名・補正を付けない印 | **項目名 `使用時効果` を `コスト` に変え、読み替えは置かない（欄の中身はコストだけで、使用時の効果は `発動時効果` に書かれているため）。本番のデータは起動時の移行で移す。補正を付けないスキルは特記に「このスキルには物理補正（魔法補正）を適用しない。」と書き、データの印は作らない。PR60-20 として §5.16 より先に行う。** | ユーザー決定。§5.17 |
| 2026-11-14 | 効果から文章を作る | **138件を数えた（意味まで一致93件）。言い回しの決まりは読み取りと同じものを正本にし、作った文章を読み取ると同じ意味に戻ることを確かめる。文章とデータの食い違い5件は文章に合わせて先に直す（E-06 は今の効果タイプで書けず、害がないので直さずに置き、往復の確かめの例外にする）。読み取りの直し（PR60-23）を先に行う。** | ユーザー決定。§5.16 |
| 2026-11-13 | Phase 5 効果のリクエスト | **出せるのは制作者と管理者、対象は効果を持つ全種類。入口は効果の節の1行（下書きをひもづける）と一覧の「＋新しく出す」。一覧は見出しのボタン。全員が全件を見られ、直せるのは本人・受付のあいだ。やりとりは管理者のメモ1つ。コピーは下書きの中身まで入れた Markdown。出したら編集へ戻る、保存前は先に保存を求める、下書きの側にリクエストを1行出す。** | ユーザー決定。試作で形を確かめた。§5.19 |
| 2026-11-12 | Phase 4 試し撃ちの計算 | **Phase 4 は「スキルの素の性能の表示」だけにし、1回ぶつける・勝率・ルームでの有利不利は計画63 戦闘マスターへ移す。普段は補正なしの値、「補正を適用」を入れたときだけ補正の欄（初め5）を出し、ブラウザーに覚えて全スキル共通。見込みはチャットパレットで計算し、項目と違えば1行で知らせる。条件で増える威力は、すべて0の前提の見込みと上乗せの一覧で見せる。編集と閲覧の両方に出す。計算は戦闘と同じ関数をサーバーで動かす。** | ユーザー決定（計算の置き場は Claude）。§5.18 |
| 2026-11-11 | 効果から文章を作る | **PR60-19 とは別の項目（§5.16）にし、PR60-19 の後に着手する。専用の画面は作らず、スキルの「文章」の節に置く。最初に138件で作り直せる件数を数えてから、言い回しの決まりの量と置き場を決める** | ユーザー決定。今の効果の文は機械的な言い回しで、ゲームの書き方の型・名前と用語のリンク・条件・補足が足りない（§5.16 の比べた表）。UI の直しとは規模も確かめ方も違う |
| 2026-11-09 | Phase 6 論点1 召喚テンプレート | **Phase 6 では JSON のタブで直せるようにするだけにし、項目ごとのフォームは作らない。敵キャラ向けのフォームは計画61で作り、そのときに召喚テンプレートにも使えるかを考える** | 3件と少なく直す機会も少ない。これで Phase 6 のうちに Sheets からの取り込みをすべてなくせる。項目ごとのフォームを今作ると、計画61の敵キャラのフォームと作りがかぶる |

## 9. 受け入れ条件（暫定）

- [ ] 新しい効果タイプを足すとき、ハンドラ・スキーマ・テストの3つを足せば、ビルダーと検査が追従する。
- [ ] メンバーが Sheets・リポジトリに触らずに、スキル・バフ・用語の下書きを作れる。
- [ ] 承認者が差分を見て公開でき、再起動や push なしで反映される。
- [ ] 変更の履歴を見られ、前の版に戻せる。
- [ ] 下書きのスキルを本番に出す前に、威力の見込み（最小・平均・最大と条件で変わる威力）を見られる。本物の処理でぶつける試し撃ちは計画63。
- [x] 表現できない効果を、管理画面からリクエストとして出せる（PR60-22、§5.19）。
