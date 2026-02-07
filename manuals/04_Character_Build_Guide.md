# キャラクタービルドガイド

このガイドでは、推奨されるキャラクタービルドの例を紹介します。
キャラクター作成時の「経験（5～10）」をコスト上限として、効率的なスキルの組み合わせを提案します。

## ビルドの基本

* **コスト管理**:
  * キャラクター作成時（初期ビルド）に取得できる通常の戦闘スキルのコスト合計は、「経験」ステータス（5～10）以下である必要があります。
  * **輝化スキル (S-xx)** は初期作成時には取得できません。シナリオクリア後に得られる「通過点」を使用して成長として取得します。
* **物理 vs 魔法**:
  * **<span style="color:#e74c3c; font-weight:bold;">物理 (Physical)</span>**: `筋力` `体格` `速度` を重視。
  * **<span style="color:#3498db; font-weight:bold;">魔法 (Magic)</span>**: `精神力` `直感` を重視。
* **リソース管理 (重要)**:
  * 強力なスキルはFPやMPを消費し続けるため、**コスト0の基本スキル（-00系）**を合間に挟んでリソースを回復する立ち回りが必須です。
  * **<span style="color:#e74c3c; font-weight:bold;">物理基本</span>**: ラウンド終了時に **<span style="color:#f1c40f; font-weight:bold;">FP+2</span>**。
  * **<span style="color:#3498db; font-weight:bold;">魔法基本</span>**: ラウンド終了時に **<span style="color:#f1c40f; font-weight:bold;">FP+1, MP+1</span>**。

<div style="page-break-after: always;"></div>

## 1. 【物理/斬撃】深手追撃型フェンサー (Bleed Chaser)

出血（スリップダメージ）を与えつつ、傷口を深くするデバフを重ねて大ダメージを狙うテクニカルなアタッカーです。

* **コンセプト**: `Ps-07` で「攻撃を受けるたびに出血する状態」にし、手数の多い攻撃で出血を加速させる。
* **推奨ステータス**: **速度**（手数を増やす）、**筋力**（基礎火力）

### 初期スキル構成 (合計コスト: 5)

バランス重視の構成です。経験点が潤沢(10)なら追加で攻撃スキルを取れます。

<table width="100%">
<thead>
<tr>
<th>スキルID</th>
<th>名称</th>
<th>コスト</th>
<th>用途</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Ps-00</strong></td>
<td>基本の一太刀</td>
<td>0</td>
<td>FP回復用。ここからコンボを始動。</td>
</tr>
<tr>
<td><strong>Ps-01</strong></td>
<td>横振り</td>
<td>1</td>
<td>低燃費で出血5を付与。主力。</td>
</tr>
<tr>
<td><strong>Ps-07</strong></td>
<td><strong>深く抉る</strong></td>
<td>2</td>
<td><strong>【キーカード】</strong> 被弾時に出血3を与えるデバフ「抉られた傷」を付与。</td>
</tr>
<tr>
<td><strong>D-01</strong></td>
<td>基本の回避</td>
<td>0</td>
<td>コストを抑えるための基本防御手段。</td>
</tr>
<tr>
<td><strong>D-02</strong></td>
<td>鉄壁の防御</td>
<td>1</td>
<td>いざという時の保険。敗北時FP回復も優秀。</td>
</tr>
<tr>
<td><strong>Pb-01</strong></td>
<td>叩き打ち</td>
<td>1</td>
<td>(任意) サブウェポン。破裂も少し使える。</td>
</tr>
</tbody>
</table>

> **初期運用のコツ**:
> 戦闘開始時は `Ps-00` でFPを溜め、FP2になったら `Ps-07`。その後は `Ps-01` や味方の攻撃で追撃して、出血を一気に稼ぎます。

### 成長プラン (通過点・シナリオ経験の使い道)

シナリオをクリアして得た「通過点」や「経験」で以下を取得します。

1. **輝化スキル: `S-02 戦闘準備` (Cost 3)**
    * 開幕FP+1。初手から `Ps-01` 等を動きやすくします。
2. **輝化スキル: `S-05 準備万端` (Cost 7)**
    * 開幕FP+2。これにより、1ターン目から `Ps-07` (Cost:FP2) を使用可能になり、即座にデバフを展開できます。
3. **戦闘スキル追加: `Ps-04 乱斬` (Cost 2)**
    * 2回攻撃（速度8以上時）。「抉られた傷」との相性が抜群です。

---

## 2. 【魔法/打撃】破裂蓄積バースト型 (Rupture Blaster)

「破裂」をひたすら溜めて、一撃で爆発させるロマン砲。FP/MP管理が重要です。

* **コンセプト**: `Mb-04` の「破裂爆発」を最大火力で叩き込む。
* **推奨ステータス**: **精神力**（MP確保）、**直感**（魔法命中）

### 初期スキル構成 (合計コスト: 5)

<table width="100%">
<thead>
<tr>
<th>スキルID</th>
<th>名称</th>
<th>コスト</th>
<th>用途</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Mb-00</strong></td>
<td>魔力の槌</td>
<td>0</td>
<td>MP/FP両方を回復する重要スキル。</td>
</tr>
<tr>
<td><strong>Mb-01</strong></td>
<td>叩き伏せる</td>
<td>1</td>
<td>低コストで破裂5を付与。</td>
</tr>
<tr>
<td><strong>Mb-02</strong></td>
<td>お前がぶつかるんだ！</td>
<td>1</td>
<td>マッチ勝利時に破裂を付与。自衛しながら火力を溜める。</td>
</tr>
<tr>
<td><strong>Mb-04</strong></td>
<td><strong>派手に爆ぜな</strong></td>
<td>2</td>
<td><strong>【キーカード】</strong> 破裂爆発を起こす起爆スキル。</td>
</tr>
<tr>
<td><strong>D-04</strong></td>
<td>見切ったよ！</td>
<td>1</td>
<td>回避成功時にMP回復。魔法型のリソース源。</td>
</tr>
</tbody>
</table>

### 成長プラン

1. **輝化スキル: `S-00 魔力の解放` (Cost 1)**
    * 魔法型はMPが命です。まずは安価なコストでMP最大値を底上げし、ガス欠を防ぎます。
2. **輝化スキル: `S-03 魔術の鍛錬` (Cost 3)**
    * さらにMPを強化します。（※同名スキルは取れないためS-00の次はこれになります）
3. **戦闘スキル追加: `Mb-05 頑なな気流` (Cost 2)**
    * 破裂のスタック数に応じて基礎威力が上がるため、中盤の火力底上げになります。
4. **戦闘スキル追加: `Mb-10 大地裂` (Cost 1)**
    * 減速を付与し、さらに条件付きで大量の破裂(8)を与えます。

<div style="page-break-after: always;"></div>

## 3. 【物理/貫通】亀裂崩壊ランサー (Fissure Lancer)

防御の上からダメージを通す「亀裂」を操る、対ボス・高防御エネミー特化型。

* **コンセプト**: 「亀裂」を付与し、`Pp-05` で崩壊させて固定ダメージを与える。
* **推奨ステータス**: **筋力**、**技術**（確実に当てるため）

### 初期スキル構成 (合計コスト: 5)

<table width="100%">
<thead>
<tr>
<th>スキルID</th>
<th>名称</th>
<th>コスト</th>
<th>用途</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Pp-00</strong></td>
<td>基本の刺突</td>
<td>0</td>
<td>FP回復用。</td>
</tr>
<tr>
<td><strong>Pp-02</strong></td>
<td>狙い突く</td>
<td>1</td>
<td>亀裂1を付与。消費FP2と少し重い。</td>
</tr>
<tr>
<td><strong>Pp-03</strong></td>
<td>突き崩す</td>
<td>1</td>
<td>次の亀裂付与数を+1するバフ。コンボパーツ。</td>
</tr>
<tr>
<td><strong>Pp-05</strong></td>
<td><strong>一点突貫</strong></td>
<td>2</td>
<td><strong>【キーカード】</strong> 亀裂崩壊。FP4消費の大技。</td>
</tr>
<tr>
<td><strong>D-02</strong></td>
<td>鉄壁の防御</td>
<td>1</td>
<td>物理型の安定防御。</td>
</tr>
</tbody>
</table>

### 成長プラン

1. **輝化スキル: `S-02 戦闘準備` (Cost 3)**
    * このビルドはFP消費が非常に激しい（`Pp-05`だけでFP4消費）ため、初期FPの確保が急務です。
2. **輝化スキル: `S-05 準備万端` (Cost 7)**
    * さらに初期FPを強化します。
3. **戦闘スキル追加: `Pp-04 隙だらけだな！` (Cost 1)**
    * 亀裂の数に応じて威力が上がるため、崩壊させる前の削り技として優秀です。

---

## 4. 【タンク/支援】ヘイト管理ガーディアン (Guardian)

味方を守り、敵の攻撃を引き受ける守護神。初期コストに余裕があるため、幅広い対応が可能です。

* **コンセプト**: `Pb-06` でヘイトを稼ぎ、生存能力を高めて耐え抜く。
* **推奨ステータス**: **生命力**、**体格**

### 初期スキル構成 (合計コスト: 4)

コストが余りやすいため、初期作成時の経験点を「5」に抑えて、その分を「体格」や「生命力」のパラメータ上昇に割り振るのがおすすめです。

<table width="100%">
<thead>
<tr>
<th>スキルID</th>
<th>名称</th>
<th>コスト</th>
<th>用途</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Pb-00</strong></td>
<td>基本の殴打</td>
<td>0</td>
<td>FP回復用。</td>
</tr>
<tr>
<td><strong>Pb-06</strong></td>
<td><strong>俺を見ろ！</strong></td>
<td>1</td>
<td><strong>【キーカード】</strong> 全敵の攻撃対象を自分に固定。</td>
</tr>
<tr>
<td><strong>D-02</strong></td>
<td><strong>鉄壁の防御</strong></td>
<td>1</td>
<td>メイン防御手段。</td>
</tr>
<tr>
<td><strong>Pb-01</strong></td>
<td>叩き打ち</td>
<td>1</td>
<td>余裕がある時の攻撃・デバフ用。</td>
</tr>
<tr>
<td><strong>D-00</strong></td>
<td>基本の防御</td>
<td>0</td>
<td>FP温存用。</td>
</tr>
</tbody>
</table>

### 成長プラン

1. **輝化スキル: `S-01 体力の研鑽` (Cost 1)**
    * HP+5。まずは安価に耐久力を上げます。
2. **輝化スキル: `S-04 身体の錬成` (Cost 3)**
    * HP+10。さらに耐久力を盤石にします。
3. **戦闘スキル追加: `Ms-10 一心不乱` (Cost 2)**
    * HPを消費して攻撃し、与ダメージの半分を回復するドレインスキル。「肉を切らせて骨を断つ」戦法が可能になります。

<div style="page-break-after: always;"></div>

## 5. 【魔法/斬撃】鮮血の魔術師 (Blood Hexer)

自らの血を代償に強力な魔法を行使し、出血を強いるハイリスク・ハイリターンな魔術師。

* **コンセプト**: HP消費スキルも辞さず、`Ms-07` や `Ms-09` で大量の出血を与え続ける。
* **推奨ステータス**: **精神力**（威力・MP）、**生命力**（コスト用HP）

### 初期スキル構成 (合計コスト: 6)

HP消費スキルを多用するため、初期HPが低いと危険です。コスト上限が許すなら輝化スキルでHPを上げたいところですが、初期作成では無理なので、ステータス割り振りで「生命力」を意識しましょう。

<table width="100%">
<thead>
<tr>
<th>スキルID</th>
<th>名称</th>
<th>コスト</th>
<th>用途</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Ms-00</strong></td>
<td>魔力の刃</td>
<td>0</td>
<td>MP/FP回復用。</td>
</tr>
<tr>
<td><strong>Ms-01</strong></td>
<td>飛刃</td>
<td>1</td>
<td>低コスト出血付与。</td>
</tr>
<tr>
<td><strong>Ms-07</strong></td>
<td><strong>放出の呪い</strong></td>
<td>3</td>
<td><strong>【キーカード】</strong> 出血5と「出血遷延」を付与。出血が自然治癒しなくなる強力なデバフ。</td>
</tr>
<tr>
<td><strong>Ms-09</strong></td>
<td><strong>瀉血</strong></td>
<td>1</td>
<td>HP10消費の超大技。基礎威力22。出血を与えつつ自分も出血し、リスクを負う。</td>
</tr>
<tr>
<td><strong>D-04</strong></td>
<td>見切ったよ！</td>
<td>1</td>
<td>回避でMP回復。HPが減りやすいので被弾は避けたい。</td>
</tr>
</tbody>
</table>

> **運用**:
> `Ms-09` は強力ですがHP10を消費します。ここぞという時の切り札として温存し、基本は `Ms-00` と `Ms-01`、そして `Ms-07` で相手をじわじわ追い詰めます。

### 成長プラン

1. **輝化スキル: `S-01 体力の研鑽` (Cost 1)**
    * HP消費スキルを多用するため、まずはHP最大値を確保します。
2. **戦闘スキル追加: `Ms-04 手足とお別れ` (Cost 2)**
    * 出血が溜まった後半戦で「出血氾濫」を狙います。
3. **戦闘スキル追加: `Ms-10 一心不乱` (Cost 2)**
    * 減ったHPをドレインで回復する手段として有効です。

---

## 6. 【物理/打撃】剛腕の破壊者 (Impact Crusher)

小細工なしの圧倒的な物理攻撃力で敵を粉砕します。

* **コンセプト**: 高い基礎威力のスキルで、相性や防御の上から強引にダメージを通す。
* **推奨ステータス**: **筋力**（物理火力）、**体格**（FP確保）

### 初期スキル構成 (合計コスト: 5)

<table width="100%">
<thead>
<tr>
<th>スキルID</th>
<th>名称</th>
<th>コスト</th>
<th>用途</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Pb-00</strong></td>
<td>基本の殴打</td>
<td>0</td>
<td>FP回復用。</td>
</tr>
<tr>
<td><strong>Pb-05</strong></td>
<td><strong>圧殺</strong></td>
<td>2</td>
<td><strong>【キーカード】</strong> 基礎威力11。純粋な高火力。FP4消費。</td>
</tr>
<tr>
<td><strong>Pb-02</strong></td>
<td>鳩尾殴り</td>
<td>1</td>
<td>破裂を付与しつつダメージ。</td>
</tr>
<tr>
<td><strong>Pb-07</strong></td>
<td><strong>破砕</strong></td>
<td>2</td>
<td>破裂・亀裂特効。状態異常の相手に強い。</td>
</tr>
<tr>
<td><strong>D-02</strong></td>
<td>鉄壁の防御</td>
<td>0</td>
<td>耐久用。</td>
</tr>
<tr>
<td><strong>D-00</strong></td>
<td>基本の防御</td>
<td>0</td>
<td>コスト調整用。</td>
</tr>
</tbody>
</table>

### 成長プラン

1. **輝化スキル: `S-02 戦闘準備` (Cost 3)**
    * `Pb-05` (消費FP4) を撃つためのFPタンクを作ります。
2. **戦闘スキル追加: `Pb-10 右肩上がり` (Cost 1)**
    * 相手の破裂値に応じて基礎威力が最大+30されるロマン砲。

<div style="page-break-after: always;"></div>

## 7. 【魔法/貫通】精神穿孔スナイパー (Mind Piercer)

魔法の矢で敵の精神的弱点（亀裂）を正確に射抜く、魔法版ランサー。

* **コンセプト**: `Mp-04` で亀裂をこじ開け、固定ダメージを通す。MP管理が重要。
* **推奨ステータス**: **精神力**、**直感**

### 初期スキル構成 (合計コスト: 5)

<table width="100%">
<thead>
<tr>
<th>スキルID</th>
<th>名称</th>
<th>コスト</th>
<th>用途</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Mp-00</strong></td>
<td>魔力の針</td>
<td>0</td>
<td>MP/FP回復。</td>
</tr>
<tr>
<td><strong>Mp-01</strong></td>
<td>飛ばし貫く</td>
<td>1</td>
<td>亀裂付与。</td>
</tr>
<tr>
<td><strong>Mp-05</strong></td>
<td><strong>そこが弱いの？</strong></td>
<td>1</td>
<td>マッチ勝利で亀裂2を付与＋ラウンド中の亀裂付与数+1。</td>
</tr>
<tr>
<td><strong>Mp-04</strong></td>
<td><strong>こじ開ける</strong></td>
<td>2</td>
<td><strong>【キーカード】</strong> 亀裂崩壊。魔法型のフィニッシャー。FP3消費。</td>
</tr>
<tr>
<td><strong>D-04</strong></td>
<td>見切ったよ！</td>
<td>1</td>
<td>マッチ勝利でMP回復＋亀裂付与（Mp-05効果中）を狙えます。</td>
</tr>
</tbody>
</table>

### 成長プラン

1. **輝化スキル: `S-02 戦闘準備` (Cost 3)**
    * `Mp-05` (FP2) → `Mp-04` (FP3) と繋げるためにFPが必須です。
2. **戦闘スキル追加: `Mp-03 綻びを狙って` (Cost 1)**
    * 条件付きですが一度に亀裂2を付与できるため、崩壊へのカウントダウンを早められます。
3. **戦闘スキル追加: `Mp-08 圧し通す` (Cost 3)**
    * 基礎威力13の貫通魔法。コストは非常に重い(MP6/FP4)ですが、絶大な威力を誇ります。
