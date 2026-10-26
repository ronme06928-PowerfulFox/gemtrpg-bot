# S1の背景素材

## 採用画像（2026-10-27）

`ruins-battle.png`：正面向き・青空・奥の階段・左右の柱とアーチのある遺跡。1672×941px、不透明。ユーザーが最新案を採用したため、同名素材を生成結果のまま差し替えた。

- 道具：Codex内蔵 `image_gen.imagegen`。新規生成。参照画像の添付なし、`transparent_background:false`。モデル識別子は返されていない。
- 生成・採用日：2026-10-27（JST）。
- 保存元：Codexの `generated_images/01a178ce-242b-7121-ba3e-b7132e8a5e06/exec-d449212f-0e27-4e39-898b-e0c6f787219f.png`。
- 実際に送った全文：[ruins-battle-prompt.txt](ruins-battle-prompt.txt)。
- 動画はcover表示で領域全体を満たし、カットごとに切り取り位置を調整する。デフォルト格子を見せる導入は使わない。既定は中央・縦65%。
- 以下の規約確認結果は同じ道具・同日の生成にも適用する。初期案や途中の水彩案・斜め構図案は採用していない。

## 初期案の制作履歴（採用前）

以下は最初の画像の記録。現在のPNGの指示文・保存元は上の採用画像の節を参照。

- 生成日・規約確認日：2026-10-27（JST）。S1部品の承認日は2026-10-26。
- 道具：Codex内蔵 `image_gen.imagegen`。API/CLIは使っていない。モデル識別子は道具から返されないため記載しない。
- 絵柄の参照：既存本編の `images/ally-adventurer.png` と `images/wolf-shularker.png`。太い輪郭・デフォルメ・セル調の陰影を参照し、人物は背景へ描かない。
- 保存元：Codexの `generated_images/01a178ce-242b-7121-ba3e-b7132e8a5e06/exec-90d97339-053a-444c-9064-d6d322740e24.png`。

## 実際に送った指示文

```text
Use case: illustration-story. Asset type: background image for a Japanese fantasy TRPG tutorial battle board. Create one landscape 16:9 image of an ancient stone ruin courtyard, empty and suitable for placing two character tokens. Style references: the two attached images are ONLY visual style references, not subjects to include: chunky chibi fantasy adventurer sticker and armored mechanical wolf sticker, bold dark ink outlines, cel shaded painted illustration, warm ochre leather and cool gray metal, subtle purple shadow accents. Match their approachable illustrated fantasy feel. Environment: worn stone slabs across a broad open central floor, broken pillars and low ruined walls around the perimeter, sparse moss, soft warm daylight. Composition: slightly elevated game board view, open uncluttered center, peripheral architecture adds depth without obscuring tokens; landscape 16:9, medium restrained contrast behind foreground UI. No people, no creatures, no characters, no text, no logo, no watermark, no drawn square grid, no UI. Opaque background.
```

`referenced_image_paths` に上記の2枚を渡し、`transparent_background: false` を指定した。

## 利用条件を確認した結果

OpenAI公式の現行[利用規約](https://openai.com/policies/terms-of-use/)（2026-01-01施行）の「Content」と「Using our Services」を実際に開いて確認した。OpenAIとの関係では、適用法の認める範囲で出力は利用者に帰属する。出力の独自性は保証されず、第三者の権利を侵害せずに利用する責任は利用者にある。生成物を人間が作成したものと偽ってはならない。

あわせて、事業者向けの[Services Agreement §4](https://openai.com/policies/services-agreement/)（2026-01-01施行）も確認した。こちらもOpenAIとの関係で出力は顧客に帰属し、入力の権利と出力の利用の確認は顧客が担う。契約上の帰属の記載は、法的な著作権の成立や独占性の保証ではない。

この条件を前提として、本プロジェクトの動画・HTMLへ背景として組み込む。素材記録と公開時の素材一覧には「背景：Codex画像生成（OpenAI、2026-10-27）」と記載する。これは制作履歴の表記であり、規約が指定する必須クレジットだとは扱わない。

## 盤面での比較

`../README.md` のS1検証手順を参照。画像そのものに格子は描いていない。石床の目地は距離やマス目を表す格子ではない。
