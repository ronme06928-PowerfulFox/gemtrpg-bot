# 23. スキルピッカーUI 改修計画

**作成日**: 2026-05-15  
**更新日**: 2026-05-15（案B実装計画 確定版）  
**対象バージョン**: Current  
**対象機能**: 宣言パネル（DeclarePanel）のスキル選択UI  
**ステータス**: 実装計画確定

---

## 1. 概要・目的

### 1.1 現状の課題

| 問題 | 詳細 |
|---|---|
| 情報量の不足 | スキル名とコスト（FP/MP）しか表示されない |
| 一覧性の低さ | 縦一列プルダウンでスキル比較が難しい |
| 属性情報の非表示 | 属性・分類・距離が見えない |
| 操作感の乏しさ | HTMLフォームそのままで没入感がない |

### 1.2 採用方針：**案B（縦・インライン切替）**

宣言パネル下半分（`.declare-panel-scroll` 領域）を、状態に応じて
**スキルピッカーグリッド ↔ スキル詳細** に切り替える方式。

- 画面幅を追加消費しない（横方向へのはみ出しゼロ）
- 方向制御が不要でシンプル
- モバイル対応への延長も容易

---

## 2. UIの状態遷移

```
パネル起動（スキル未選択）
    ↓
[下半分 = スキルピッカーグリッド]
    - 2カラムのスキルカード一覧
    - スクロール可能
    ↓ カードをクリック
[スキル選択 → 下半分 = スキル詳細]
    - 威力レンジ・コマンド・発動時効果 etc.
    - スキル行に「↩ 再選択」ボタン表示
    ↓ ↩ ボタンをクリック
[下半分 = スキルピッカーグリッドに戻る]
```

### パネル下半分の表示ルール

| 条件 | 下半分の表示 |
|---|---|
| `skillId` が空 かつ `!isUiReadOnly` | **スキルピッカーグリッド** |
| `skillId` あり かつ `_skillPickerOpen === false` | **スキル詳細**（既存 `.declare-skill-meta`） |
| `isUiReadOnly === true` | スキル詳細（固定） |

`_skillPickerOpen` は `DeclarePanel` インスタンスの内部フラグ。

---

## 3. スキルカード仕様

### 3.1 カードのレイアウト

```
┌──────────────────────────┐
│ Pb-01                    │  ← スキルID（小・薄色）
│ 叩き打ち                 │  ← スキル名（太字）
│ [打撃] [物理] [近接]     │  ← 属性バッジ
│                   FP:1   │  ← コスト（右寄せ）
└──────────────────────────┘
```

### 3.2 属性バッジ カラー定義

| バッジ | 背景 | 文字 |
|---|---|---|
| 斬撃 | `#daeaf8` | `#1a5276` |
| 打撃 | `#fde8cc` | `#a04000` |
| 貫通 | `#fadbd8` | `#922b21` |
| 物理 | `#e8daef` | `#6c3483` |
| 魔法 | `#d6eaf8` | `#1a4d7a` |
| 補助 | `#d5f5e3` | `#1d6a3a` |
| 近接 | `#ebe6e0` | `#5d4037` |
| 遠隔 | `#d0f0f5` | `#00695c` |
| 広域-個別 | `#efefef` | `#555` |
| 広域-合算 | `#e8e8e8` | `#333` |

※ パネル背景がパーチメント系（ベージュ/タン）のため、バッジも彩度を落とした和色系で統一する。

### 3.3 カード状態

| 状態 | クラス | 見た目 |
|---|---|---|
| 通常 | — | ベージュ系背景 |
| ホバー | `:hover` | 少し明るく |
| 選択中 | `.is-selected` | 濃紺ハイライト・白文字 |
| コスト不足 | `.is-disabled` | 半透明（opacity:0.45） |
| クリック瞬間 | `:active` | scale(0.97) |

---

## 4. 実装計画

### ステップ概要

| # | 作業 | 変更ファイル |
|---|---|---|
| S1 | `_skillPickerOpen` フラグ追加 | `DeclarePanel.js` |
| S2 | `_buildSkillPickerHtml()` 追加 | `DeclarePanel.js` |
| S3 | `_buildSkillBadgesHtml()` 追加 | `DeclarePanel.js` |
| S4 | `_onSkillCardClick()` 追加（選択ロジック移植） | `DeclarePanel.js` |
| S5 | `interactiveHtml` テンプレート修正 | `DeclarePanel.js` |
| S6 | `_render()` のイベントバインド修正 | `DeclarePanel.js` |
| S7 | CSS追加 | `visual_battle.css` |

---

### S1: `_skillPickerOpen` フラグの追加

**場所**: `constructor()` 内

```javascript
// 変更前
this._sideUi = {
    ally: { minimized: false },
    enemy: { minimized: false }
};

// 変更後
this._sideUi = {
    ally: { minimized: false },
    enemy: { minimized: false }
};
this._skillPickerOpen = false;   // ← 追加
```

**リセットタイミング**（`_render()` 内の既存の非表示処理に追記）:

```javascript
// L.146 付近 — パネルを閉じるときに追記
if (phase !== 'select' || !shouldShowPanel) {
    root.style.display = 'none';
    leftPanel.style.display = 'none';
    rightPanel.style.display = 'none';
    this._lastCalcKey = null;
    this._lastCompareCalcKeyBySlot = {};
    leftPanel.classList.remove('is-target-picking');
    rightPanel.classList.remove('is-target-picking');
    this._skillPickerOpen = false;   // ← 追加
    return;
}
```

**自動オープン**: `_render()` 内でスキルが未選択のとき、ピッカーを自動展開する。

```javascript
// L.198 付近、skillOptions の構築直後あたりに追加
// skillId が空になったタイミングでピッカーを自動展開
if (!skillId && !isUiReadOnly) {
    this._skillPickerOpen = true;
}
```

---

### S2: `_buildSkillPickerHtml()` の追加

**場所**: `_buildSkillOptions()` の直後（L.910 付近）に追加。

```javascript
/**
 * スキルピッカーグリッドのHTML文字列を生成する。
 * _buildSkillOptions() の代替として使用する。
 */
_buildSkillPickerHtml(actor, state, sourceSlotId, selectedTargetSlotId, selectedSkillId, isReadOnly) {
    const all = window.allSkillData || {};
    const candidates = this._extractActorSkillCandidates(actor, all);

    if (candidates.length === 0) {
        return `<div class="skill-picker-empty">習得スキルがありません</div>`;
    }

    const cards = candidates.slice(0, 400).map((item) => {
        const id = item.id;

        // 対象互換チェック（既存ロジック流用）
        if (
            selectedTargetSlotId &&
            !this._isSkillCompatibleWithTarget(state, sourceSlotId, selectedTargetSlotId, id)
        ) {
            return '';
        }

        const skillData = all[id] || {};
        const displayName = item.name || this._readSkillMeta(id).name || id;
        const costs = this._extractCosts(id, null);
        const costLabel = this._formatSkillCostLabel(costs);
        const isSelected = (id === selectedSkillId);

        // コスト不足チェック（既存ロジック流用）
        const sourceActorId = state?.slots?.[sourceSlotId]?.actor_id || null;
        const costCheck = this._evaluateCost(state, sourceActorId, id, null);
        const isDisabled = costCheck.insufficient;

        const badgesHtml = this._buildSkillBadgesHtml(skillData);

        const selectedClass = isSelected ? ' is-selected' : '';
        const disabledClass = isDisabled ? ' is-disabled' : '';

        return `
            <div class="skill-picker-card${selectedClass}${disabledClass}"
                 data-skill-id="${this._escapeHtml(id)}"
                 title="${isDisabled ? this._escapeHtml(costCheck.message) : ''}">
                <div class="skill-card-id">${this._escapeHtml(id)}</div>
                <div class="skill-card-name">${this._escapeHtml(displayName)}</div>
                <div class="skill-card-badges">${badgesHtml}</div>
                <div class="skill-card-cost">${this._escapeHtml(costLabel || '—')}</div>
            </div>
        `;
    }).filter(Boolean);

    return `<div class="skill-picker-grid">${cards.join('')}</div>`;
}
```

---

### S3: `_buildSkillBadgesHtml()` の追加

**場所**: `_buildSkillPickerHtml()` の直後に追加。

```javascript
/**
 * スキルデータから属性・分類・距離のバッジHTML文字列を生成する。
 */
_buildSkillBadgesHtml(skillData) {
    const BADGE_COLORS = {
        // 属性
        '斬撃':     { bg: '#daeaf8', color: '#1a5276' },
        '打撃':     { bg: '#fde8cc', color: '#a04000' },
        '貫通':     { bg: '#fadbd8', color: '#922b21' },
        // 分類
        '物理':     { bg: '#e8daef', color: '#6c3483' },
        '魔法':     { bg: '#d6eaf8', color: '#1a4d7a' },
        '補助':     { bg: '#d5f5e3', color: '#1d6a3a' },
        // 距離
        '近接':     { bg: '#ebe6e0', color: '#5d4037' },
        '遠隔':     { bg: '#d0f0f5', color: '#00695c' },
        '広域-個別':{ bg: '#efefef', color: '#555' },
        '広域-合算':{ bg: '#e8e8e8', color: '#333' },
    };

    const labels = [
        String(skillData['属性'] || '').trim(),
        String(skillData['分類'] || '').trim(),
        String(skillData['距離'] || '').trim(),
    ].filter(Boolean);

    return labels.map((label) => {
        const c = BADGE_COLORS[label] || { bg: '#e0e0e0', color: '#444' };
        return `<span class="skill-badge" style="background:${c.bg};color:${c.color}">${this._escapeHtml(label)}</span>`;
    }).join('');
}
```

---

### S4: `_onSkillCardClick()` の追加

**場所**: `_buildSkillBadgesHtml()` の直後に追加。

既存の `skillSelect.onchange` ハンドラ（L.369〜L.417）のロジックをそのまま移植し、
`e.target.value` の代わりに引数 `nextSkillId` を受け取る形にする。

```javascript
/**
 * スキルカードクリック時の処理。
 * 旧: skillSelect.onchange (DeclarePanel.js L.369-417) をそのまま移植。
 */
_onSkillCardClick(nextSkillId, declaredTargetType, sourceSlotId) {
    const current = store.get('declare') || {};
    const prevTargetType = this._normalizeTargetType(current.targetType || declaredTargetType);
    const nextTargetType = this._resolveEffectiveTargetType(nextSkillId, prevTargetType);
    const prevTargetScope = this._inferTargetScopeFromSkill(current.skillId || '');
    const nextTargetScope = this._inferTargetScopeFromSkill(nextSkillId);
    let nextTargetSlotId = current.targetSlotId || null;
    let nextLastSingleTargetSlotId = current.lastSingleTargetSlotId || null;

    if (this._isMassTargetType(nextTargetType)) {
        if (!this._isMassTargetType(prevTargetType) && nextTargetSlotId) {
            nextLastSingleTargetSlotId = nextTargetSlotId;
        }
        nextTargetSlotId = null;
    } else {
        if (this._isMassTargetType(prevTargetType)) {
            nextTargetSlotId = current.lastSingleTargetSlotId || null;
        }
        if (nextTargetSlotId) {
            nextLastSingleTargetSlotId = nextTargetSlotId;
        }
    }
    if (prevTargetScope === 'self' && nextTargetSlotId === sourceSlotId) {
        nextTargetSlotId = nextLastSingleTargetSlotId || null;
    }
    if (nextTargetScope === 'self') {
        nextTargetSlotId = sourceSlotId;
    }

    const nextDeclare = {
        ...current,
        skillId: nextSkillId || null,
        targetType: nextTargetType,
        targetSlotId: nextTargetSlotId,
        lastSingleTargetSlotId: nextLastSingleTargetSlotId,
        mode: (
            !this._isMassTargetType(nextTargetType)
            && !nextTargetSlotId
            && String(current.mode || '') === 'ready'
        )
            ? 'ready'
            : this._resolveDeclareMode(nextTargetType, nextTargetSlotId)
    };

    // ピッカーを閉じてスキル詳細に切り替え
    this._skillPickerOpen = false;

    store.setDeclare(nextDeclare);
    this._emitPreviewFromDeclare(store.state, nextDeclare);
    this._requestCalc(store.state, nextDeclare, true);
}
```

---

### S5: `interactiveHtml` テンプレートの修正

**場所**: `_render()` 内 L.198 付近（`skillOptions` の計算行）と L.245〜L.301（テンプレート文字列）。

#### S5-a: `skillOptions` 変数の削除

```javascript
// 削除する行 (L.198):
const skillOptions = this._buildSkillOptions(sourceChar, state, sourceSlotId, effectiveTargetSlotId);
```

#### S5-b: `_skillPickerOpen` の状態を確定

```javascript
// skillOptions の削除行の代わりに追加:
const showSkillPicker = this._skillPickerOpen && !isUiReadOnly;
const skillPickerHtml = showSkillPicker
    ? this._buildSkillPickerHtml(sourceChar, state, sourceSlotId, effectiveTargetSlotId, skillId, isUiReadOnly)
    : '';
const currentSkillLabel = skillId
    ? `[${skillId}] ${this._escapeHtml(interactiveSkillDisplay)}`
    : '-- スキルを選択 --';
```

#### S5-c: テンプレート内の変更箇所

**変更箇所①: スキル行 (L.277〜282)**

```javascript
// 変更前
<div class="declare-panel-row">
    <span>スキル</span>
    <select id="declare-skill-select" class="declare-skill-select" ${isUiReadOnly ? 'disabled' : ''}>
        ${skillOptions}
    </select>
</div>

// 変更後
<div class="declare-panel-row declare-skill-row">
    <span>スキル</span>
    <span class="declare-skill-display" id="declare-skill-display">
        ${currentSkillLabel}
    </span>
    ${(skillId && !isUiReadOnly) ? `
        <button id="declare-skill-reopen-btn"
                class="declare-skill-reopen-btn"
                title="スキルを選び直す">↩</button>
    ` : ''}
</div>
```

**変更箇所②: `.declare-panel-scroll` (L.284〜300)**

```javascript
// 変更前
<div class="declare-panel-scroll">
    <div class="declare-skill-meta">
        ...（既存の詳細HTML）...
    </div>
    ${costCheck.insufficient ? `<div class="declare-cost-warning">...</div>` : ''}
    ${calcErrorText ? `<div class="declare-cost-warning">...</div>` : ''}
</div>

// 変更後
${showSkillPicker ? `
    <div class="declare-panel-scroll declare-panel-scroll--picker">
        ${skillPickerHtml}
    </div>
` : `
    <div class="declare-panel-scroll">
        <div class="declare-skill-meta">
            <div><strong>${this._escapeHtml(interactiveSkillDisplay)}</strong></div>
            <div>${meta.description || '-'}</div>
            <div>威力レンジ: ${this._escapeHtml(interactiveRangeText)}</div>
            <div>コマンド: <code class="declare-command">${this._escapeHtml(commandText || '-')}</code></div>
            <div>威力: ${this._escapeHtml(powerSummary)}</div>
            ${powerAdjustRows.length > 0 ? `
            <div class="declare-power-adjust">
                <div class="declare-power-adjust-title">威力変化の内訳</div>
                ${powerAdjustRows.map((row) => `<div class="declare-power-adjust-row">${this._escapeHtml(row)}</div>`).join('')}
            </div>` : ''}
            ${meta.detailHtml ? `<div class="declare-skill-detail">${meta.detailHtml}</div>` : ''}
        </div>
        ${costCheck.insufficient ? `<div class="declare-cost-warning">${costCheck.message}</div>` : ''}
        ${calcErrorText ? `<div class="declare-cost-warning">${calcErrorText}</div>` : ''}
    </div>
`}
```

---

### S6: `_render()` のイベントバインド修正

**場所**: L.365〜L.418（`skillSelect` の参照・バインド処理）

#### S6-a: 旧 `skillSelect` ブロックの削除

以下のブロック（L.365〜L.418）を**削除**する。

```javascript
// 削除対象 (L.365-418):
const skillSelect = interactivePanel.querySelector('#declare-skill-select');
if (skillSelect) {
    skillSelect.value = skillId || '';
    skillSelect.disabled = isUiReadOnly;
    skillSelect.onchange = (e) => {
        // ... 48行のロジック ...
    };
}
```

#### S6-b: 新しいバインド処理に置き換え

削除した箇所に、以下を追加する。

```javascript
// スキルカードへのクリックバインド
const pickerGrid = interactivePanel.querySelector('.skill-picker-grid');
if (pickerGrid) {
    pickerGrid.onclick = (e) => {
        if (isUiReadOnly) return;
        const card = e.target.closest('.skill-picker-card');
        if (!card || card.classList.contains('is-disabled')) return;
        const nextSkillId = card.dataset.skillId || '';
        if (!nextSkillId) return;
        this._onSkillCardClick(nextSkillId, declaredTargetType, sourceSlotId);
    };
}

// 「↩ 再選択」ボタン
const reopenBtn = interactivePanel.querySelector('#declare-skill-reopen-btn');
if (reopenBtn) {
    reopenBtn.onclick = () => {
        if (isUiReadOnly) return;
        this._skillPickerOpen = true;
        this._render(store.state);
    };
}
```

---

### S7: CSS追加（`visual_battle.css`）

既存の `.declare-panel-scroll` ブロック（L.904）の後に追加する。

```css
/* ===== スキルピッカー（案B: インライン切替） ===== */

/* ピッカー表示時のスクロール領域 */
.declare-panel-scroll--picker {
    overflow-y: auto;
    padding: 6px 2px 8px 2px;
    /* パネルの残り高さを使い切る */
    flex: 1 1 auto;
    min-height: 120px;
}

/* 2カラムグリッド */
.skill-picker-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
}

/* スキルカード */
.skill-picker-card {
    background: rgba(255, 248, 228, 0.7);
    border: 1px solid rgba(138, 106, 63, 0.4);
    border-radius: 6px;
    padding: 6px 8px;
    cursor: pointer;
    transition: background 0.12s, transform 0.08s, box-shadow 0.12s;
    color: #2f2315;
    user-select: none;
}
.skill-picker-card:hover {
    background: rgba(255, 240, 200, 0.9);
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
}
.skill-picker-card.is-selected {
    background: #1a5276;
    border-color: #5dade2;
    color: #fff;
    box-shadow: 0 0 0 2px #5dade2;
}
.skill-picker-card.is-selected .skill-card-id,
.skill-picker-card.is-selected .skill-card-cost {
    color: #aed6f1;
}
.skill-picker-card:active {
    transform: scale(0.97);
}
.skill-picker-card.is-disabled {
    opacity: 0.45;
    pointer-events: none;
}

/* カード内: スキルID */
.skill-card-id {
    font-size: 10px;
    color: #7a5c35;
    margin-bottom: 2px;
    font-family: monospace;
}

/* カード内: スキル名 */
.skill-card-name {
    font-size: 12px;
    font-weight: bold;
    line-height: 1.3;
    margin-bottom: 5px;
    overflow-wrap: break-word;
}

/* カード内: バッジ列 */
.skill-card-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    margin-bottom: 5px;
    min-height: 16px;
}

/* バッジ共通 */
.skill-badge {
    font-size: 9px;
    padding: 1px 4px;
    border-radius: 3px;
    white-space: nowrap;
    font-weight: 600;
    line-height: 1.4;
}

/* カード内: コスト */
.skill-card-cost {
    font-size: 10px;
    color: #7a5c35;
    text-align: right;
}

/* ピッカーが空のとき */
.skill-picker-empty {
    text-align: center;
    color: #8a6a3f;
    font-size: 13px;
    padding: 20px 8px;
}

/* スキル行: 選択済み表示 */
.declare-skill-row {
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
}
.declare-skill-display {
    flex: 1;
    font-size: 13px;
    color: #2f2315;
    overflow-wrap: break-word;
}

/* 再選択ボタン */
.declare-skill-reopen-btn {
    background: transparent;
    border: 1px solid rgba(138, 106, 63, 0.5);
    border-radius: 4px;
    color: #5d4220;
    font-size: 12px;
    padding: 2px 6px;
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.1s;
}
.declare-skill-reopen-btn:hover {
    background: rgba(138, 106, 63, 0.15);
}
```

---

## 5. フェーズ分割

| Phase | 内容 | 実装ステップ |
|---|---|---|
| **Phase 1** ★★★ | カードグリッド基本実装（クリック選択・バッジ表示） | S1〜S7 全て |
| **Phase 2** ★★☆ | ホバーツールチップ（威力レンジ・コマンド・発動時効果） | `_bindTooltipEvents()` 追加 |
| **Phase 3** ★★☆ | コスト不足カード: ツールチップで理由表示（現状は `title` 属性のみ） | S2内の拡張 |
| **Phase 4** ★☆☆ | 案A（横スライド）オプション化 | 別途設計 |
| **Phase 5** ★☆☆ | テキスト検索フィルター | ピッカー上部に `<input>` 追加 |

---

## 6. 影響範囲・注意事項

### 6.1 削除・変更するコード一覧

| 場所 | 行 | 内容 |
|---|---|---|
| `DeclarePanel.js` | L.198 | `const skillOptions = this._buildSkillOptions(...)` → 削除 |
| `DeclarePanel.js` | L.277〜282 | `<select id="declare-skill-select">` → スキル表示行に置換 |
| `DeclarePanel.js` | L.284〜300 | `.declare-panel-scroll` 内容 → 条件分岐に置換 |
| `DeclarePanel.js` | L.365〜418 | `skillSelect` 参照・onchange → 削除して S6-b に置換 |
| `DeclarePanel.js` | `_buildSkillOptions()` (L.890〜910) | 廃止（削除してもよい／コメントアウトでも可） |

### 6.2 `declare-skill-select` への外部参照

`Grep` 確認済み: `static/js/**` 内での参照は `DeclarePanel.js` の2箇所のみ。  
外部からの依存はなし。

### 6.3 `is-minimized` との整合

`.declare-panel.is-minimized .declare-panel-scroll` は既存CSSで非表示になる（L.1134）。  
`.declare-panel-scroll--picker` も同じく非表示になるよう、CSSセレクタを追加する。

```css
/* visual_battle.css 既存の is-minimized ブロック（L.1132〜）に追記 */
.declare-panel.is-minimized .declare-panel-scroll--picker {
    display: none;
}
```

### 6.4 モバイル対応

`static/mobile/` 以下の宣言UIは本改修の対象外。別途検討。

---

## 7. 完了条件チェックリスト

- [ ] `<select id="declare-skill-select">` が削除されている
- [ ] スキルカードグリッドが宣言パネル下部に2カラムで表示される
- [ ] スキルID・スキル名・属性バッジ（属性/分類/距離）・コストが各カードに表示される
- [ ] カードクリックでスキルが選択され、下半分がスキル詳細に切り替わる
- [ ] 選択中カードに `is-selected` が付き濃紺ハイライトされる
- [ ] 「↩」ボタンクリックでピッカーグリッドに戻れる
- [ ] スキル未選択状態では自動的にピッカーグリッドが開く
- [ ] パネルが閉じると `_skillPickerOpen` がリセットされる
- [ ] コスト不足スキルが半透明で表示され、クリック不可になる
- [ ] グリッドが縦スクロール可能
- [ ] `is-minimized` 時にピッカーも非表示になる
- [ ] ホバーツールチップが表示される（Phase 2）
