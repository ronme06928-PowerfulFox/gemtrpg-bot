# Cloudinary 画像統合ガイド

## 目次

1. [はじめに](#はじめに)
2. [Cloudinaryとは](#cloudinaryとは)
3. [Cloudinaryアカウント登録手順](#cloudinaryアカウント登録手順)
4. [実装アーキテクチャ](#実装アーキテクチャ)
5. [バックエンド実装](#バックエンド実装)
6. [フロントエンド実装](#フロントエンド実装)
7. [デプロイメント設定](#デプロイメント設定)
8. [トラブルシューティング](#トラブルシューティング)

---

## はじめに

このマニュアルでは、ジェムリアTRPGダイスボットアプリケーションに **Cloudinary** を使用した画像アップロード・表示機能を実装する方法を解説します。

### 現状の課題

現在、Render（Free/Starterプラン）でホスティングしているアプリケーションには以下の問題があります：

1. **ファイル消失**: Renderのファイルシステムは一時的（Ephemeral）であり、再起動やデプロイ時にサーバー内の画像がすべて削除される
2. **DB容量圧迫**: データベース（Neon/PostgreSQL）に直接バイナリデータを保存すると、容量制限（500MB）をすぐに圧迫し、パフォーマンスが低下する

### ソリューション

Cloudinaryを外部ストレージとして使用することで、以下が実現できます：

- ✅ 画像の永続化（再起動しても消えない）
- ✅ データベースの負荷軽減（URLのみを保存）
- ✅ 無料枠での十分な運用（月間25クレジット = 約25GB）
- ✅ 自動画質最適化（WebP変換など）

---

## Cloudinaryとは

**Cloudinary** は、開発者向けに特化した画像・動画管理のクラウドサービスです。

### 主な機能

- 🖼️ **画像アップロード・保存**: クラウド上に永続的に保存
- 🔄 **自動最適化**: 画質を保ったまま容量削減（WebP、AVIF変換）
- 📏 **リサイズ・変換**: URLパラメータで動的に画像を加工
- 🚀 **CDN配信**: 高速な画像配信

### 無料プラン（Freeプラン）

| 項目 | 無料枠 |
| ------ | -------- |
| 月間クレジット | 25クレジット |
| ストレージ | 約25GB相当 |
| 帯域幅 | 約25GB相当 |
| クレジットカード | **不要** |

> **💡 TRPG用途であれば十分**: ブラウザキャッシュが効くため、同じ画像を何度表示しても通信量は発生しません。

---

## Cloudinaryアカウント登録手順

### ステップ1: アカウント作成

1. **公式サイトにアクセス**
   - URL: [https://cloudinary.com/](https://cloudinary.com/)

2. **「Sign Up for Free」をクリック**
   - 画面右上のボタンから登録ページへ

3. **登録情報を入力**

   ```
   Email: （あなたのメールアドレス）
   Password: （8文字以上の安全なパスワード）
   ```

   - または、Google/GitHub アカウントで簡単登録も可能

4. **利用目的を選択**（任意）
   - 「Personal」または「Developer」を選択

5. **メール認証**
   - 登録したメールアドレスに確認メールが届くので、リンクをクリック

### ステップ2: APIキー取得

登録完了後、ダッシュボードで以下の情報が表示されます：

```text
Cloud Name: （例: dxxxxxxxxx）
API Key:    （例: 123456789012345）
API Secret: （例: xxxxxxxxxxxxxxxxxxxxxxxxxxx）
```

> ⚠️ **重要**: `API Secret` は **絶対に外部に公開しない** でください。
> GitHubなどにコミットする際は、`.env` ファイルに記載し、`.gitignore` に登録すること。

### ステップ3: ダッシュボード確認

- **Media Library**: アップロードされた画像一覧
- **Settings**: セキュリティ設定、フォルダ管理など
- **Usage**: 現在の使用量（クレジット残量）

---

## 実装アーキテクチャ

### データフロー

```
[ユーザー]
   ↓ 1. 画像選択
[Webアプリ (Flask)]
   ↓ 2. 一時的に受け取り
   ↓ 3. Cloudinaryへ転送
[Cloudinary]
   ↓ 4. 保存完了、URL発行
[Webアプリ (Flask)]
   ↓ 5. URLをDBに保存
[データベース (PostgreSQL)]
```

### 技術スタック

| レイヤー | 技術 |
| ---------- | ------ |
| フロントエンド | JavaScript (Vanilla) |
| バックエンド | Flask (Python) |
| 画像ストレージ | Cloudinary |
| データベース | PostgreSQL (Neon) |

### セキュリティ

- ユーザーは **直接Cloudinaryにアクセスしない**
- サーバーがプロキシとして動作し、APIキーを保護
- アップロードはサーバー経由のみ

---

## バックエンド実装

### 1. 依存関係のインストール

**`requirements.txt` に追加:**

```txt
cloudinary
```

インストールコマンド（ローカル環境）:

```bash
pip install cloudinary
```

### 2. 環境変数の設定

**`.env` ファイルに追加:**

```bash
# Cloudinary設定
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

> ⚠️ **`.env` ファイルを `.gitignore` に追加** して、Gitにコミットされないようにしてください。

**`.gitignore` に追加（未設定の場合）:**

```
.env
```

### 3. `app.py` への追加実装

#### 3-1. Cloudinaryライブラリのインポート

```python
import cloudinary
import cloudinary.uploader
```

#### 3-2. Cloudinary設定の初期化

`app.py` の冒頭（`CORS`, `socketio` 初期化の前後）に追加:

```python
# Cloudinary設定 (環境変数から読み込み)
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)
```

#### 3-3. 画像アップロードAPIの作成

```python
@app.route('/api/upload_image', methods=['POST'])
@session_required  # セッション必須（不正アップロード防止）
def upload_image():
    """
    Cloudinaryへ画像をアップロードするエンドポイント
    """
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    try:
        # Cloudinaryへアップロード
        # folder: 保存先フォルダ名（整理用）
        # transformation: 自動軽量化・リサイズ設定
        result = cloudinary.uploader.upload(
            file,
            folder="gemtrpg/characters",  # フォルダ分け（任意）
            transformation=[
                {'width': 300, 'crop': "limit"},  # 幅300pxに制限
                {'quality': "auto", 'fetch_format': "auto"}  # 自動最適化
            ]
        )

        # アップロード成功: セキュアURL（https）を返す
        return jsonify({'url': result['secure_url']})

    except Exception as e:
        # エラーログ出力
        print(f"[Cloudinary] Upload Error: {e}")
        return jsonify({'error': 'アップロードに失敗しました'}), 500
```

### 4. データベーススキーマへの追加

既存のキャラクターデータに `image_url` フィールドを追加する必要があります。

**現在のデータ構造（例）:**

```json
{
  "id": "char_001",
  "name": "テストキャラ",
  "hp": 50,
  "maxHp": 50,
  "image_url": null  // ← 追加するフィールド
}
```

> **注**: 現在のシステムはJSON形式でキャラクターデータを保持しているため、スキーマ変更は不要です。単に新しいキー `image_url` を追加するだけで動作します。

---

## フロントエンド実装

### 1. キャラクターモーダルへのアップロード機能追加

#### 場所: `static/js/modals.js`

`renderCharacterCard` 関数に画像アップロード用のHTMLを追加します。

#### 追加コード（設定パネル内）

```javascript
// 既存の gmSettingsHtml の後ろに追加
const imageUploadHtml = `
    <div style="margin-left: 15px; border-left: 2px solid #eee; padding-left: 10px; margin-top: 10px;">
        <label for="char-image-input" style="display: block; margin-bottom: 5px; font-weight: bold;">
            立ち絵画像
        </label>
        <input type="file" id="char-image-input" accept="image/*" style="margin-bottom: 5px;">
        <input type="hidden" id="char-image-url" value="${char.image || ''}">

        <div id="char-image-preview" style="margin-top: 10px; ${char.image ? '' : 'display: none;'}">
            <p style="font-size: 0.85em; color: #555;">プレビュー:</p>
            <img id="char-preview-img" src="${char.image || ''}"
                 style="max-height: 100px; border: 1px solid #ccc; border-radius: 4px;">
        </div>
    </div>
`;
```

#### インテグレーション位置

`renderCharacterCard` 関数内の `headerHtml` セクション内、`.char-modal-settings` の中に挿入:

```javascript
const headerHtml = `
    <h3>
        <span class="modal-char-name">${char.name}</span>
        <span class="modal-header-buttons">
            <button class="modal-settings-btn">⚙️</button>
            <button class="modal-close-btn">×</button>
        </span>
    </h3>
    <div class="char-modal-settings" style="display: none; flex-wrap: wrap;">
        <div style="width: 100%; font-size: 0.85em; color: #555; margin-bottom: 8px; border-bottom: 1px solid #ddd; padding-bottom: 4px;">
            所有者: <strong>${ownerName}</strong>
        </div>

        <label for="char-color-picker">トークン色:</label>
        <input type="color" id="char-color-picker" value="${char.color}">
        <button class="color-reset-btn">リセット</button>

        ${gmSettingsHtml}

        ${imageUploadHtml}  <!-- ★ここに追加 -->

        <button class="delete-char-btn" style="margin-left: auto;">このキャラを削除</button>
    </div>
`;
```

### 2. アップロード処理の実装

#### `openCharacterModal` 関数に追加

モーダルが開かれた後、ファイル選択イベントリスナーを設定:

```javascript
function openCharacterModal(charId) {
    // ... 既存のコード ...

    // ★ 画像アップロード処理
    const fileInput = modalContent.querySelector('#char-image-input');
    const urlInput = modalContent.querySelector('#char-image-url');
    const previewArea = modalContent.querySelector('#char-image-preview');
    const previewImg = modalContent.querySelector('#char-preview-img');

    if (fileInput) {
        fileInput.addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;

            // FormDataを作成
            const formData = new FormData();
            formData.append('file', file);

            // アップロード中の表示
            fileInput.disabled = true;
            previewArea.style.display = 'block';
            previewImg.style.opacity = 0.5;
            previewImg.src = ''; // 一時的にクリア

            try {
                // サーバーのAPIへ送信
                const response = await fetch('/api/upload_image', {
                    method: 'POST',
                    body: formData,
                    credentials: 'include'  // セッションクッキーを含める
                });

                const data = await response.json();

                if (data.url) {
                    // URL取得成功: サーバーへ保存
                    urlInput.value = data.url;
                    previewImg.src = data.url;
                    previewImg.style.opacity = 1.0;

                    // キャラクターデータを更新（サーバーへ送信）
                    socket.emit('request_state_update', {
                        room: currentRoomName,
                        charId: char.id,
                        statName: 'image',
                        newValue: data.url
                    });

                    alert('画像をアップロードしました！');
                } else {
                    alert('アップロード失敗: ' + (data.error || '不明なエラー'));
                }
            } catch (err) {
                console.error(err);
                alert('通信エラーが発生しました');
            } finally {
                fileInput.disabled = false;
            }
        });
    }
}
```

### 3. マップ表示への統合

#### 場所: `static/js/tab_visual_battle.js`

`createMapToken` 関数を修正し、画像が設定されている場合はそれを表示します。

#### 修正箇所

`.token-body` 要素に背景画像を設定:

```javascript
function createMapToken(char) {
    // ... 既存のコード ...

    // ★ 画像URLがある場合は背景として設定
    let tokenBodyStyle = '';
    if (char.image) {
        tokenBodyStyle = `
            background-image: url('${char.image}');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        `;
    }

    token.innerHTML = `
        ${wideBtnHtml}
        <div class="token-bars">
            <div class="token-bar" title="HP: ${hp}/${maxHp}">
                <div class="token-bar-fill hp" style="width: ${hpPer}%"></div>
            </div>
            <div class="token-bar" title="MP: ${mp}/${maxMp}">
                <div class="token-bar-fill mp" style="width: ${mpPer}%"></div>
            </div>
            <div class="token-bar" title="FP: ${fp}">
                <div class="token-bar-fill fp" style="width: ${fpPer}%"></div>
            </div>
        </div>
        <div class="token-body" style="${tokenBodyStyle}">
            ${char.image ? '' : '<span>' + char.name.charAt(0) + '</span>'}
        </div>
        <div class="token-info-container">
            <div class="token-label">${char.name}</div>
            <div class="token-status-overlay">${iconsHtml}</div>
        </div>
    `;

    // ... 残りのコード ...
}
```

#### CSS調整（任意）

画像が円形に収まるようにスタイルを調整する場合:

**`static/css/visual_battle.css` に追加:**

```css
.token-body {
    overflow: hidden;
    border-radius: 50%; /* 円形にクリップ */
}
```

---

## デプロイメント設定

### Renderへのデプロイ

#### 1. 環境変数の設定

Renderダッシュボードで以下を追加:

```bash
CLOUDINARY_CLOUD_NAME = your_cloud_name
CLOUDINARY_API_KEY    = your_api_key
CLOUDINARY_API_SECRET = your_api_secret
```

#### 2. `requirements.txt` の反映

```bash
git add requirements.txt
git commit -m "Add cloudinary dependency"
git push
```

Renderが自動的に依存関係をインストールします。

### 動作確認

1. アプリを起動
2. キャラクター詳細モーダルを開く
3. 設定アイコン（⚙️）をクリック
4. 「立ち絵画像」から画像をアップロード
5. マップ上のトークンに画像が表示されることを確認

---

## トラブルシューティング

### エラー: `Module not found: cloudinary`

**原因:** `cloudinary` がインストールされていない

**解決策:**

```bash
pip install cloudinary
```

### エラー: `API Secret is not set`

**原因:** 環境変数が読み込まれていない

**解決策:**

1. `.env` ファイルが正しく配置されているか確認
2. `python-dotenv` がインストールされているか確認
3. `load_dotenv()` が呼ばれているか確認

### 画像がアップロードできない

**原因1:** ファイルサイズが大きすぎる

- Cloudinaryの無料プランは **最大10MB/ファイル**
- 必要に応じてクライアント側で圧縮

**原因2:** Content-Type が正しくない

- `multipart/form-data` が正しく設定されているか確認

### アップロード後、画像が表示されない

**原因:** URLが正しくキャラクターデータに保存されていない

**デバッグ方法:**

1. ブラウザの開発者ツールを開く
2. Network タブでレスポンスを確認
3. `battleState.characters` をコンソールで確認し、`image` プロパティが存在するか確認

---

## まとめ

以上の手順で、Cloudinaryを使用した画像アップロード・表示機能が実装できます。

### 実装チェックリスト

- [ ] Cloudinaryアカウント登録
- [ ] APIキー取得
- [ ] `.env` に環境変数設定
- [ ] `requirements.txt` に `cloudinary` 追加
- [ ] `app.py` にアップロードAPI追加
- [ ] `modals.js` にアップロードUI追加
- [ ] `tab_visual_battle.js` に表示処理追加
- [ ] Renderに環境変数を設定
- [ ] デプロイ・動作確認

何か問題が発生した場合は、このマニュアルのトラブルシューティングセクションを参照してください。
