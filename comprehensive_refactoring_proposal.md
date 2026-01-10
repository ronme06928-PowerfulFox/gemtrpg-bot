# Visual Battle System: 抜本的リファクタリング企画書

## 1. 目的と背景 (Context & Objectives)

### 現状の課題
現在の `tab_visual_battle.js` は3000行を超える巨大なマモノリス（Monolith）となっており、以下の問題が発生しています。

- **責務の混在**: マップ描画、通信処理、状態管理、UI操作、イベントハンドラが単一ファイルに混在しており、どこか修正すると予期せぬ場所でバグが起きる（広域マッチの実装で顕著化）。
- **不透明な状態管理**: `battleState`、`visualScale`、`duelState`、`visualWideState` などがグローバル変数として散在し、誰がいつ書き換えたか追跡不能。同期ズレの主原因。
- **レガシーコードの蓄積**: 試行錯誤の過程で残った未使用関数（`_Disabled`など）や、古いコメントアウトが可読性を低下させている。
- **拡張性の限界**: 新機能（広域マッチ、特殊効果など）を追加するたびにコードが指数関数的に複雑化する。

### リファクタリングのゴール
**「拡張に強く、バグ修正が容易な、モジュール化されたシステム」** への移行。

- **保守性**: 機能ごとにファイルが分かれ、影響範囲が明確になる。
- **安定性**: 状態管理を一元化し、データの整合性を保証する。
- **拡張性**: 新しいUIや機能を「プラグイン」のように追加できる設計にする。

## 2. 提案アーキテクチャ (Proposed Architecture)
フロントエンドフレームワーク（React/Vue）の導入は学習・環境構築コストが高いため、「Modern Vanilla JS + ES Modules」 によるクラスベース設計を提案します。

### ディレクトリ構造案
`static/js/battle/` ディレクトリを新設し、機能を分割します。

```
static/js/battle/
├── core/
│   ├── BattleStore.js       # 【核】状態管理（State Management）を一元化。Reduxライクな更新通知。
│   ├── SocketClient.js      # Socket.io通信のラッパー。送受信を型定義のように管理。
│   └── EventBus.js          # コンポーネント間の疎結合な通信用。
├── components/
│   ├── VisualMap.js         # マップ描画（Canvas/DOM操作）専任。
│   ├── ActionDock.js        # アクションドックUI管理。
│   ├── Timeline.js          # タイムライン表示管理。
│   ├── panels/
│   │   ├── DuelPanel.js     # 対決マッチパネル。
│   │   └── WidePanel.js     # 広域マッチパネル。
│   └── modals/
│       └── CharacterModal.js # キャラクター詳細設定モーダル。
├── utils/
│   ├── AssetLoader.js       # 画像読み込み管理。
│   └── DomUtils.js          # 便利なDOM操作ヘルパー。
└── main.js                  # エントリーポイント。各コンポーネントを初期化しStoreと接続。
```

### コアコンセプト: Store パターン
すべての状態（キャラクター、盤面、マッチ状況）は `BattleStore` だけで管理し、各コンポーネントは Store を購読（Subscribe）して画面を更新します。

```javascript
// イメージ
class BattleStore {
    constructor() {
        this.state = { characters: [], activeMatch: null, ... };
        this.listeners = [];
    }

    // 状態更新は必ずこのメソッドを通す
    update(newState) {
        this.state = { ...this.state, ...newState };
        this.notify();
    }

    subscribe(callback) {
        this.listeners.push(callback);
    }
}
```

## 3. 移行計画 (Migration Phases)
一度にすべて書き換えると崩壊するため、4つのフェーズに分けて段階的に移行します。

### Phase 1: モジュール基盤の構築とユーティリティの切り出し (1-2日)
- `static/js/battle/` フォルダ作成。
- `tab_visual_battle.js` から依存性の少ない関数（計算ロジック、DOMヘルパー、定数）を `utils/` に切り出す。
- HTML側で `type="module"` として読み込める環境を整える。

### Phase 2: コア（Store & Socket）の実装 (2-3日)
- `BattleStore.js` を作成し、現在 `window.battleState` で行っている管理を移行。
- `SocketClient.js` を作成し、通信ロジックを分離。
- この段階ではまだUI描画は古い `tab_visual_battle.js` のままだが、データ参照先を Store に切り替える。

### Phase 3: UIコンポーネントの分割 (3-5日)
- 最も独立性が高い「アクションドック」や「タイムライン」からクラス化して別ファイルへ。
- 次に巨大な「マップ描画処理（`renderVisualMap`）」を `VisualMap.js` へ移動。
- 最後に「マッチパネル」関連を `panels/` へ移動。

### Phase 4: 完全移行とクリーンアップ (1-2日)
- `tab_visual_battle.js` に残った接着剤コードを `battle/main.js` に整理。
- 古いファイルの削除。
- ドキュメント整備。

## 4. 次のアクション
この企画書に基づき、まずは **Phase 1（ディレクトリ作成とユーティリティの切り出し）** から着手することを提案します。
