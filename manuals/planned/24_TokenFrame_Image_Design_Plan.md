# 24. キャラ駒 枠画像 設計計画

**作成日**: 2026-05-16  
**対象機能**: バトルマップ上のキャラクター駒（`.map-token`）の枠デザイン  
**ステータス**: 設計確定

---

## 1. 現状の実装

### 駒の構造（抜粋）

```
div.map-token.PC / .Enemy / .NPC
  style:
    width: 132px, height: 132px
    border: 4px solid #007bff (味方) / #dc3545 (敵)
    borderRadius: "18px 18px 0 0"
    boxShadow: "0 4px 8px rgba(0,0,0,0.4)"
```

### 現状の枠の実装方法

`visual_map.js` の `createMapToken()` 内でインラインスタイルとして設定：

```javascript
token.style.border = `4px solid ${tokenStyle.borderColor}`;
// #007bff（味方）/ #dc3545（敵）/ #999（NPC）
```

CSS（`visual_map.css`）でも `.map-token.PC / .Enemy / .NPC` に `border-color` を定義しているが、
JS側のインラインスタイルが優先されている。

---

## 2. 設計方針

### 方針: 枠を画像オーバーレイ div に置き換える

CSSの `border` を廃止し、駒の内部に **`div.token-frame`** を追加する。  
このdivが絶対位置で駒全体を覆い、枠デザイン画像（PNG）を表示する。

```
div.map-token（132×132px）
  ├── [既存] token-body（アバター画像・HP/MPバー）
  ├── [既存] token-name-label
  ├── [既存] token-badges
  └── [追加] div.token-frame（絶対位置・最前面）
               └── <img src="frames/ally_frame.png">
```

---

## 3. 枠画像の仕様

### ファイル配置

```
static/
  images/
    frames/
      ally_frame.png    ← 味方用（青系）
      enemy_frame.png   ← 敵用（赤系）
      npc_frame.png     ← NPC用（グレー系）・省略可
```

### 画像サイズ・形式

| 項目 | 値 |
|---|---|
| 形式 | PNG（アルファチャンネル必須） |
| 推奨サイズ | **160 × 160 px** |
| 内側透過領域 | 中央 **116 × 116 px** を透明にする |
| 枠幅 | 外周 **22 px** 程度 |
| DPI | 72〜96 dpi（Web表示用） |

### 座標系イメージ

```
160px
┌──────────────────────────────┐
│ ←── 22px ──┐             │
│            ┌────────────┐   │
│            │            │   │  ↑ 22px
│            │  透明領域  │   │
│            │  (116×116) │   │
│            │            │   │
│            └────────────┘   │
│                             │  ↓ 22px
└──────────────────────────────┘
```

> **理由**: 駒本体は 132px。オーバーレイを `inset: -14px` に配置することで  
> 外周に枠が 14px はみ出し、内側の透明部分で駒コンテンツが見える。

### デザイン上の注意

- 4辺の枠デザインは異なってよい（上部を豪華にするなど）
- 底辺は `borderRadius: 0` のため、角丸なし
- 上辺左右は `borderRadius: 18px` のため、上隅は丸みに合わせてデザインする
- 枠の外側に光沢・影エフェクトを入れて立体感を出せる
- 生成AI（Midjourney / DALL-E / Stable Diffusion）で生成する場合、  
  **背景透過PNGとして書き出す** こと（WebP も可だが PNG 推奨）

---

## 4. JS実装方針

### 4.1 変更対象

`static/js/visual/visual_map.js` の `createMapToken()` 関数（L.1377〜）

### 4.2 変更内容

#### (a) インライン border を削除

```javascript
// 変更前
token.style.border = `4px solid ${tokenStyle.borderColor}`;

// 変更後
token.style.border = 'none';   // 画像枠に置き換えるため
```

#### (b) token-frame div を追加

```javascript
// createMapToken() の末尾付近、token への appendChild 前に追加
const frameImg = resolveTokenFrameSrc(tokenStyle.className);
if (frameImg) {
    const frameEl = document.createElement('div');
    frameEl.className = 'token-frame';
    const img = document.createElement('img');
    img.src = frameImg;
    img.className = 'token-frame-img';
    img.draggable = false;
    frameEl.appendChild(img);
    token.appendChild(frameEl);
}
```

#### (c) フレーム画像パスの解決関数を追加

```javascript
function resolveTokenFrameSrc(className) {
    const base = '/static/images/frames/';
    if (className === 'PC')    return `${base}ally_frame.png`;
    if (className === 'Enemy') return `${base}enemy_frame.png`;
    if (className === 'NPC')   return `${base}npc_frame.png`;
    return null;
}
```

#### (d) active-turn 時の枠切り替え（任意）

ターンがアクティブな駒には専用の枠画像（光る版）を使う場合：

```javascript
// active-turn クラス付与時に token-frame-img の src を差し替える
function updateTokenFrameForTurn(token, isActive) {
    const img = token.querySelector('.token-frame-img');
    if (!img) return;
    const base = '/static/images/frames/';
    const side = token.classList.contains('PC') ? 'ally'
               : token.classList.contains('Enemy') ? 'enemy'
               : 'npc';
    img.src = isActive
        ? `${base}${side}_frame_active.png`   // 光る版
        : `${base}${side}_frame.png`;          // 通常版
}
```

> active版画像を用意しない場合はCSSのアニメーションで代替可（後述）

---

## 5. CSS実装方針

### 5.1 変更対象

`static/css/modules/visual_map.css`

### 5.2 変更内容

#### (a) `.map-token.PC / .Enemy / .NPC` の border を無効化

```css
/* 変更前 */
.map-token.PC    { border-color: #3498db; ... }
.map-token.Enemy { border-color: #e74c3c; ... }

/* 変更後 */
.map-token.PC,
.map-token.Enemy,
.map-token.NPC {
    border: none;
    background-color: transparent;  /* 必要に応じて */
}
```

#### (b) token-frame の配置

```css
.token-frame {
    position: absolute;
    inset: -14px;          /* 駒より外側に 14px はみ出す */
    z-index: 50;           /* バッジ類より前面 */
    pointer-events: none;  /* クリック・ドラッグを駒本体に透過 */
}

.token-frame-img {
    width: 100%;
    height: 100%;
    object-fit: fill;
    display: block;
    pointer-events: none;
}
```

#### (c) active-turn の光エフェクト（画像を使わない場合の代替）

```css
/* 画像枠に対して filter で光らせる */
.map-token.PC.active-turn .token-frame-img {
    filter: drop-shadow(0 0 10px #007bff) drop-shadow(0 0 20px #007bff);
    animation: pulse-frame-ally 1.5s infinite alternate;
}
.map-token.Enemy.active-turn .token-frame-img {
    filter: drop-shadow(0 0 10px #dc3545) drop-shadow(0 0 20px #dc3545);
    animation: pulse-frame-enemy 1.5s infinite alternate;
}

@keyframes pulse-frame-ally {
    from { filter: drop-shadow(0 0 6px #007bff); }
    to   { filter: drop-shadow(0 0 18px #007bff) drop-shadow(0 0 30px #4fc3f7); }
}
@keyframes pulse-frame-enemy {
    from { filter: drop-shadow(0 0 6px #dc3545); }
    to   { filter: drop-shadow(0 0 18px #dc3545) drop-shadow(0 0 30px #ff8a80); }
}
```

---

## 6. 実装フェーズ

| Phase | 内容 | 前提条件 |
|---|---|---|
| **Phase 1** | CSS border を無効化 + `token-frame` div を追加（画像なしでも動作確認） | なし |
| **Phase 2** | 枠画像（`ally_frame.png` / `enemy_frame.png`）を配置 | 画像の用意 |
| **Phase 3** | active-turn 時の `filter` アニメーション適用 | Phase 2 完了後 |
| **Phase 4** | active-turn 専用画像（光る版）に差し替え（任意） | 追加画像の用意 |

---

## 7. 完了条件チェックリスト

- [ ] `static/images/frames/` ディレクトリが存在する
- [ ] `ally_frame.png` / `enemy_frame.png` が配置されている
- [ ] `.token-frame` div が各駒に追加されている
- [ ] `border: none` で CSS/JS の旧ボーダーが消えている
- [ ] 駒上のクリック・ドラッグが `token-frame` に邪魔されない（`pointer-events: none`）
- [ ] active-turn 時に枠が光る（filter または active画像）
- [ ] 駒のリサイズ（`tokenScale`）に枠が追従する

---

## 8. 生成AI画像のプロンプト例（参考）

### 味方枠（青系・Fantasy RPG）
```
A decorative rectangular picture frame for a fantasy TRPG game token.
Blue and gold color scheme. Ornate border with gem details.
Transparent center (alpha channel). PNG format, 160x160px.
Top corners rounded (18px radius), bottom corners sharp.
Dark navy and sapphire blue tones, metallic gold accents.
No text. Clean edges for digital overlay use.
```

### 敵枠（赤系・Fantasy RPG）
```
A decorative rectangular picture frame for a fantasy TRPG enemy token.
Red and dark iron color scheme. Menacing border with spike details.
Transparent center (alpha channel). PNG format, 160x160px.
Top corners rounded (18px radius), bottom corners sharp.
Crimson red and dark steel tones, bone-white accents.
No text. Clean edges for digital overlay use.
```
