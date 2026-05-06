/* ========================================
   Image Picker Component
   画像選択モーダルコンポーネント
======================================== */

/**
 * 画像選択モーダルを開く
 * @param {Function} onSelect - 画像選択時のコールバック関数 (引数: { url, id, name })
 * @param {string} pickType - 選択タイプ ('character' | 'background') - デフォルト 'character'
 */
function openImagePicker(onSelect, pickType = 'character') {
    // 既存のモーダルを削除
    const existing = document.getElementById('image-picker-modal');
    if (existing) existing.remove();

    // モーダル作成
    const modal = document.createElement('div');
    modal.id = 'image-picker-modal';
    modal.className = 'modal-backdrop';
    modal.style.display = 'flex';
    modal.style.zIndex = '10000'; // ★ 設定パネルより上に表示

    const titlePrefix = pickType === 'background' ? '背景' : '画像';

    modal.innerHTML = `
        <div class="modal-content image-picker-content" style="max-width: 800px; width: 90%; height: 85vh; max-height: 800px; display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,0.3); border-radius: 12px; overflow: hidden;">
            <div class="modal-header" style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 20px 24px;
                margin: 0;
                border-bottom: none;
            ">
                <h3 style="margin: 0; font-size: 1.4em; font-weight: 600;">🖼️ ${titlePrefix}を選択</h3>
                <button class="modal-close-btn" style="background: rgba(255,255,255,0.2); border: none; font-size: 1.8em; cursor: pointer; color: white; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; transition: background 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.3)'" onmouseout="this.style.background='rgba(255,255,255,0.2)'">×</button>
            </div>

            <div style="padding: 20px; flex: 1; overflow-y: auto; display: flex; flex-direction: column;">
                <!-- タブナビゲーション -->
                <div class="image-picker-tabs" style="display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #e0e0e0; flex-shrink: 0;">
                    <button class="tab-btn active" data-tab="gallery">📚 ギャラリー</button>
                    <button class="tab-btn" data-tab="upload">⬆️ 新規アップロード</button>
                    <button class="tab-btn" data-tab="defaults">✨ デフォルト素材</button>
                </div>

                <!-- タブコンテンツ -->
                <div class="tab-content" style="flex: 1; overflow-y: auto;">
                    <!-- ギャラリータブ -->
                    <div class="tab-pane active" data-pane="gallery">
                        <div style="margin-bottom: 15px;">
                            <input type="text" id="image-search-input" placeholder="🔍 画像名で検索..." style="width: 100%; padding: 12px 16px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1em; transition: border-color 0.2s;" onfocus="this.style.borderColor='#667eea'" onblur="this.style.borderColor='#e0e0e0'">
                        </div>
                        <div id="gallery-images" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; padding: 4px;">
                            <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #999;">
                                <div style="font-size: 3em; margin-bottom: 10px;">🔄</div>
                                <div>読み込み中...</div>
                            </div>
                        </div>
                    </div>

                    <!-- アップロードタブ -->
                    <div class="tab-pane" data-pane="upload" style="display: none;">
                        <div style="border: 3px dashed #667eea; border-radius: 12px; padding: 40px; text-align: center; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); transition: all 0.3s;">
                            <input type="file" id="picker-file-input" accept="image/*" style="display: none;">
                            <div id="upload-dropzone">
                                <p style="font-size: 3em; margin: 0 0 15px 0;">📷</p>
                                <p style="font-size: 1.2em; margin-bottom: 15px; font-weight: 600; color: #333;">画像をドロップ または クリックして選択</p>
                                <button class="btn-primary" onclick="document.getElementById('picker-file-input').click()" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 32px; border: none; border-radius: 8px; font-size: 1em; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 12px rgba(102,126,234,0.4)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">ファイルを選択</button>
                            </div>
                            <div style="margin-top: 20px; text-align: left; max-width: 400px; margin-left: auto; margin-right: auto;">
                                <label style="display: block; margin-bottom: 8px; font-weight: bold; color: #333;">画像タイプ:</label>
                                <select id="picker-image-type" style="width: 100%; padding: 10px 14px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1em; margin-bottom: 15px;">
                                    <option value="character" ${pickType === 'character' ? 'selected' : ''}>キャラクター立ち絵</option>
                                    <option value="background" ${pickType === 'background' ? 'selected' : ''}>背景画像</option>
                                </select>

                                <label style="display: block; margin-bottom: 8px; font-weight: bold; color: #333;">画像名（省略可）:</label>
                                <input type="text" id="picker-image-name" placeholder="例: 戦士_男" style="width: 100%; padding: 10px 14px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1em; margin-bottom: 15px;">

                                <div id="gm-only-option" style="display: none; margin-bottom: 15px; background: #fff3cd; padding: 10px; border-radius: 8px; border: 1px solid #ffeeba;">
                                    <label style="display: flex; align-items: center; cursor: pointer;">
                                        <input type="checkbox" id="picker-gm-only" style="width: 18px; height: 18px; margin-right: 8px;">
                                        <span style="font-weight: bold; color: #856404;">🔒 GM限定画像として保存</span>
                                    </label>
                                    <div style="font-size: 0.85em; color: #856404; margin-top: 4px; margin-left: 26px;">GM権限を持つユーザーのみ閲覧・使用できます</div>
                                </div>
                            </div>
                            <div id="upload-preview" style="margin-top: 20px; display: none;">
                                <img id="upload-preview-img" style="max-width: 240px; max-height: 240px; border: 3px solid #667eea; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                                <p id="upload-status" style="margin-top: 15px; font-weight: bold; font-size: 1.1em;"></p>
                            </div>
                        </div>
                    </div>

                    <!-- デフォルト素材タブ -->
                    <div class="tab-pane" data-pane="defaults" style="display: none;">
                        <div id="default-images" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; max-height: 400px; overflow-y: auto; padding: 4px;">
                            <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #999;">
                                <div style="font-size: 3em; margin-bottom: 10px;">✨</div>
                                <div>デフォルト画像はまだありません</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // イベントハンドラ
    const closeBtn = modal.querySelector('.modal-close-btn');
    closeBtn.onclick = () => modal.remove();

    modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
    };

    // タブ切り替え
    const tabBtns = modal.querySelectorAll('.tab-btn');
    const tabPanes = modal.querySelectorAll('.tab-pane');

    tabBtns.forEach(btn => {
        btn.onclick = () => {
            // タブボタンのアクティブ切り替え
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // タブコンテンツの表示切り替え
            const targetTab = btn.dataset.tab;
            tabPanes.forEach(pane => {
                if (pane.dataset.pane === targetTab) {
                    pane.style.display = 'block';
                    pane.classList.add('active');
                } else {
                    pane.style.display = 'none';
                    pane.classList.remove('active');
                }
            });
        };
    });

    // ギャラリータブの初期化 (pickTypeを渡す)
    loadGalleryImages(modal, onSelect, '', pickType);

    // アップロードタブの初期化
    setupUploadTab(modal, onSelect, pickType);

    // デフォルト画像タブの初期化 (pickTypeに関わらず一旦全部出す、あるいはフィルタする？今回はそのまま)
    loadDefaultImages(modal, onSelect, pickType);

    // 検索機能
    const searchInput = modal.querySelector('#image-search-input');
    let searchTimeout = null;
    searchInput.oninput = () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            loadGalleryImages(modal, onSelect, searchInput.value, pickType);
        }, 300);
    };
}

async function maybeCropImageSelection(imageData, pickType) {
    if (pickType !== 'character') {
        return {
            ...imageData,
            originalUrl: imageData.url,
            croppedUrl: imageData.url
        };
    }
    return openImageCropperModal(imageData);
}

function openImageCropperModal(imageData) {
    return new Promise((resolve) => {
        const existing = document.getElementById('image-cropper-modal');
        if (existing) existing.remove();

        const viewportSize = 320;
        const modal = document.createElement('div');
        modal.id = 'image-cropper-modal';
        modal.className = 'modal-backdrop';
        modal.style.display = 'flex';
        modal.style.zIndex = '11000';
        modal.innerHTML = `
            <div class="modal-content" style="width: 92%; max-width: 560px; padding: 18px; border-radius: 12px;">
                <h3 style="margin: 0 0 12px 0;">画像の表示範囲を調整</h3>
                <p style="margin: 0 0 12px 0; color: #666; font-size: 0.9em;">ズームとドラッグで切り抜き範囲を決めます。</p>
                <div id="crop-viewport" style="
                    width: ${viewportSize}px;
                    height: ${viewportSize}px;
                    margin: 0 auto 12px auto;
                    border: 2px solid #667eea;
                    border-radius: 10px;
                    overflow: hidden;
                    position: relative;
                    background: #f2f4f8;
                    touch-action: none;
                    cursor: grab;
                ">
                    <img id="crop-image" alt="crop preview" style="position: absolute; user-select: none; -webkit-user-drag: none; max-width: none; max-height: none;">
                </div>
                <div style="margin-bottom: 12px;">
                    <label for="crop-zoom" style="display:block; font-size:0.9em; margin-bottom:6px;">ズーム</label>
                    <input id="crop-zoom" type="range" min="1" max="4" step="0.01" value="1" style="width:100%;">
                </div>
                <div style="display:flex; gap:8px; justify-content:flex-end; flex-wrap: wrap;">
                    <button id="crop-cancel-btn" class="btn-secondary" type="button">キャンセル</button>
                    <button id="crop-original-btn" class="btn-secondary" type="button">元画像のまま使う</button>
                    <button id="crop-apply-btn" class="btn-primary" type="button">切り抜いて決定</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        const viewport = modal.querySelector('#crop-viewport');
        const imgEl = modal.querySelector('#crop-image');
        const zoomInput = modal.querySelector('#crop-zoom');
        const cancelBtn = modal.querySelector('#crop-cancel-btn');
        const originalBtn = modal.querySelector('#crop-original-btn');
        const applyBtn = modal.querySelector('#crop-apply-btn');

        const sourceImg = new Image();
        let baseScale = 1;
        let zoom = 1;
        let offsetX = 0;
        let offsetY = 0;
        let dragStartX = 0;
        let dragStartY = 0;
        let dragOriginX = 0;
        let dragOriginY = 0;
        let dragging = false;

        let resolved = false;
        const onMouseMove = (e) => moveDrag(e.clientX, e.clientY);
        const onMouseUp = () => endDrag();
        const onTouchMove = (e) => {
            if (!e.touches || !e.touches[0]) return;
            moveDrag(e.touches[0].clientX, e.touches[0].clientY);
        };
        const onTouchEnd = () => endDrag();

        const closeWith = (value) => {
            if (resolved) return;
            resolved = true;
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
            window.removeEventListener('touchmove', onTouchMove);
            window.removeEventListener('touchend', onTouchEnd);
            modal.remove();
            resolve(value);
        };

        const clampOffsets = () => {
            const scale = baseScale * zoom;
            const w = sourceImg.naturalWidth * scale;
            const h = sourceImg.naturalHeight * scale;
            const maxX = Math.max(0, (w - viewportSize) / 2);
            const maxY = Math.max(0, (h - viewportSize) / 2);
            offsetX = Math.min(maxX, Math.max(-maxX, offsetX));
            offsetY = Math.min(maxY, Math.max(-maxY, offsetY));
        };

        const renderCropPreview = () => {
            const scale = baseScale * zoom;
            const w = sourceImg.naturalWidth * scale;
            const h = sourceImg.naturalHeight * scale;
            clampOffsets();
            const left = (viewportSize - w) / 2 + offsetX;
            const top = (viewportSize - h) / 2 + offsetY;
            imgEl.style.width = `${w}px`;
            imgEl.style.height = `${h}px`;
            imgEl.style.left = `${left}px`;
            imgEl.style.top = `${top}px`;
        };

        const startDrag = (clientX, clientY) => {
            dragging = true;
            dragStartX = clientX;
            dragStartY = clientY;
            dragOriginX = offsetX;
            dragOriginY = offsetY;
            viewport.style.cursor = 'grabbing';
        };

        const moveDrag = (clientX, clientY) => {
            if (!dragging) return;
            offsetX = dragOriginX + (clientX - dragStartX);
            offsetY = dragOriginY + (clientY - dragStartY);
            renderCropPreview();
        };

        const endDrag = () => {
            dragging = false;
            viewport.style.cursor = 'grab';
        };

        viewport.addEventListener('mousedown', (e) => {
            e.preventDefault();
            startDrag(e.clientX, e.clientY);
        });
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        viewport.addEventListener('touchstart', (e) => {
            if (!e.touches || !e.touches[0]) return;
            startDrag(e.touches[0].clientX, e.touches[0].clientY);
        }, { passive: true });
        window.addEventListener('touchmove', onTouchMove, { passive: true });
        window.addEventListener('touchend', onTouchEnd);

        zoomInput.addEventListener('input', () => {
            zoom = parseFloat(zoomInput.value) || 1;
            renderCropPreview();
        });

        cancelBtn.onclick = () => closeWith(null);
        originalBtn.onclick = () => closeWith({
            ...imageData,
            originalUrl: imageData.url,
            croppedUrl: imageData.url
        });

        applyBtn.onclick = () => {
            try {
                const scale = baseScale * zoom;
                const w = sourceImg.naturalWidth * scale;
                const h = sourceImg.naturalHeight * scale;
                const left = (viewportSize - w) / 2 + offsetX;
                const top = (viewportSize - h) / 2 + offsetY;
                const sxRaw = (0 - left) / scale;
                const syRaw = (0 - top) / scale;
                const swRaw = viewportSize / scale;
                const shRaw = viewportSize / scale;
                const sw = Math.min(sourceImg.naturalWidth, swRaw);
                const sh = Math.min(sourceImg.naturalHeight, shRaw);
                const sx = Math.max(0, Math.min(sourceImg.naturalWidth - sw, sxRaw));
                const sy = Math.max(0, Math.min(sourceImg.naturalHeight - sh, syRaw));

                const canvas = document.createElement('canvas');
                canvas.width = 512;
                canvas.height = 512;
                const ctx = canvas.getContext('2d');
                if (!ctx) {
                    closeWith({
                        ...imageData,
                        originalUrl: imageData.url,
                        croppedUrl: imageData.url
                    });
                    return;
                }
                ctx.drawImage(sourceImg, sx, sy, sw, sh, 0, 0, 512, 512);
                const croppedUrl = canvas.toDataURL('image/png');
                closeWith({
                    ...imageData,
                    originalUrl: imageData.url,
                    croppedUrl: croppedUrl,
                    url: croppedUrl,
                    name: `${imageData.name || 'image'} (cropped)`
                });
            } catch (err) {
                console.error('[ImagePicker] Crop error:', err);
                alert('画像の切り抜きに失敗しました。元画像を使用します。');
                closeWith({
                    ...imageData,
                    originalUrl: imageData.url,
                    croppedUrl: imageData.url
                });
            }
        };

        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeWith(null);
        });

        sourceImg.onload = () => {
            baseScale = Math.max(viewportSize / sourceImg.naturalWidth, viewportSize / sourceImg.naturalHeight);
            zoom = 1;
            zoomInput.value = '1';
            offsetX = 0;
            offsetY = 0;
            imgEl.src = imageData.url;
            renderCropPreview();
        };
        sourceImg.onerror = () => {
            alert('画像の読み込みに失敗しました。元画像を使用します。');
            closeWith({
                ...imageData,
                originalUrl: imageData.url,
                croppedUrl: imageData.url
            });
        };
        sourceImg.src = imageData.url;
    });
}

/**
 * ギャラリー画像を読み込んで表示
 */
async function loadGalleryImages(modal, onSelect, query = '', pickType = 'character') {
    const container = modal.querySelector('#gallery-images');
    container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 20px; color: #999;">読み込み中...</div>';

    try {
        const params = new URLSearchParams();
        if (query) params.append('q', query);

        // pickTypeからAPIのtypeパラメータへ変換
        const apiType = (pickType === 'background') ? 'background' : 'user';
        params.append('type', apiType);

        const response = await fetch(`/api/images?${params.toString()}`, {
            credentials: 'include'
        });

        const images = await response.json();

        if (images.length === 0) {
            container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 20px; color: #999;">画像がありません</div>';
            return;
        }

        container.innerHTML = '';
        images.forEach(img => {
            const card = createImageCard(img, async () => {
                const selected = await maybeCropImageSelection({ url: img.url, id: img.id, name: img.name }, pickType);
                if (!selected) return;
                onSelect(selected);
                modal.remove();
            }, true); // ★ 削除ボタン有効
            container.appendChild(card);
        });

    } catch (err) {
        console.error('[ImagePicker] Error loading gallery:', err);
        container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 20px; color: red;">読み込みエラー</div>';
    }
}

/**
 * デフォルト画像を読み込んで表示
 */
async function loadDefaultImages(modal, onSelect, pickType = 'character') {
    const container = modal.querySelector('#default-images');

    try {
        const response = await fetch(`/api/local_images?type=${pickType}`, {
            credentials: 'include'
        });

        const images = await response.json();

        if (images.length === 0) {
            container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 20px; color: #999;">デフォルト画像はまだありません</div>';
            return;
        }

        container.innerHTML = '';
        images.forEach(img => {
            const card = createImageCard(img, async () => {
                const selected = await maybeCropImageSelection({ url: img.url, id: img.id, name: img.name }, pickType);
                if (!selected) return;
                onSelect(selected);
                modal.remove();
            }, false); // ★ 削除不可
            container.appendChild(card);
        });

    } catch (err) {
        console.error('[ImagePicker] Error loading defaults:', err);
    }
}

/**
 * 画像カード要素を作成
 * @param {Object} imageData
 * @param {Function} onClickCallback
 * @param {boolean} allowDelete 削除ボタンを表示するかどうか
 */
function createImageCard(imageData, onClickCallback, allowDelete = false) {
    const card = document.createElement('div');
    card.className = 'image-card';
    card.style.cssText = 'position: relative; border: 2px solid #ddd; border-radius: 4px; overflow: hidden; cursor: pointer; transition: all 0.2s; background: #f9f9f9;';

    card.innerHTML = `
        <div style="aspect-ratio: 1; background-image: url('${imageData.url}'); background-size: cover; background-position: center;">
             ${imageData.visibility === 'gm' ? '<div style="position:absolute; top:5px; left:5px; background:rgba(0,0,0,0.6); color:#ffc107; padding:2px 6px; border-radius:4px; font-size:0.8em; font-weight:bold;">🔒 GM</div>' : ''}
        </div>
        <div style="padding: 5px; font-size: 0.8em; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${imageData.name || '無題'}</div>
    `;

    card.onclick = onClickCallback;

    card.onmouseenter = () => {
        card.style.borderColor = '#007bff';
        card.style.transform = 'scale(1.05)';
        const delBtn = card.querySelector('.delete-img-btn');
        if (delBtn) delBtn.style.display = 'flex';
    };

    card.onmouseleave = () => {
        card.style.borderColor = '#ddd';
        card.style.transform = 'scale(1)';
        const delBtn = card.querySelector('.delete-img-btn');
        if (delBtn) delBtn.style.display = 'none';
    };

    // ★ 削除ボタン
    if (allowDelete) {
        const delBtn = document.createElement('div');
        delBtn.className = 'delete-img-btn';
        delBtn.innerHTML = '🗑️'; // or ×
        delBtn.title = '削除';
        Object.assign(delBtn.style, {
            position: 'absolute',
            top: '5px',
            right: '5px',
            width: '24px',
            height: '24px',
            background: 'rgba(255, 68, 68, 0.9)',
            color: 'white',
            borderRadius: '4px',
            display: 'none', // Hoverで表示
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '14px',
            cursor: 'pointer',
            zIndex: '10'
        });

        delBtn.onclick = async (e) => {
            e.stopPropagation(); // 選択イベントを阻止
            if (await window.showAppConfirm(`画像「${imageData.name}」を完全に削除しますか？\n(クラウドからも削除されます)`, {
                title: '画像削除',
                confirmText: '削除',
            })) {
                try {
                    const res = await fetch(`/api/images/${imageData.id}`, { method: 'DELETE' });
                    if (res.ok) {
                        card.remove(); // 画面から削除
                    } else {
                        const dat = await res.json();
                        alert('削除に失敗しました: ' + (dat.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error(err);
                    alert('通信エラーが発生しました');
                }
            }
        };
        card.appendChild(delBtn);
    }

    return card;
}

/**
 * アップロードタブの設定
 */
function setupUploadTab(modal, onSelect, pickType = 'character') {
    const fileInput = modal.querySelector('#picker-file-input');
    const nameInput = modal.querySelector('#picker-image-name');
    const typeSelect = modal.querySelector('#picker-image-type');
    const preview = modal.querySelector('#upload-preview');
    const previewImg = modal.querySelector('#upload-preview-img');
    const statusText = modal.querySelector('#upload-status');
    const dropzone = modal.querySelector('#upload-dropzone');
    const gmOnlyCheck = modal.querySelector('#picker-gm-only');
    const gmOnlyArea = modal.querySelector('#gm-only-option');

    // Show GM option if user is GM
    if (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM') {
        gmOnlyArea.style.display = 'block';
    }

    // Create Upload Button dynamically
    const uploadBtn = document.createElement('button');
    uploadBtn.textContent = 'アップロード開始';
    uploadBtn.style.cssText = `
        display: none;
        margin-top: 15px;
        background: linear-gradient(135deg, #28a745 0%, #218838 100%);
        color: white;
        padding: 12px 32px;
        border: none;
        border-radius: 8px;
        font-size: 1.1em;
        font-weight: 600;
        cursor: pointer;
        width: 100%;
        max-width: 300px;
    `;
    preview.appendChild(uploadBtn);


    // ドラッグ＆ドロップ
    dropzone.ondragover = (e) => {
        e.preventDefault();
        dropzone.style.background = '#e3f2fd';
    };

    dropzone.ondragleave = () => {
        dropzone.style.background = '#f9f9f9';
    };

    dropzone.ondrop = (e) => {
        e.preventDefault();
        dropzone.style.background = '#f9f9f9';
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelect();
        }
    };

    fileInput.onchange = handleFileSelect;

    function handleFileSelect() {
        const file = fileInput.files[0];
        if (!file) return;

        // Reset status
        statusText.textContent = '';
        uploadBtn.style.display = 'block'; // Show upload button

        // プレビュー表示
        const reader = new FileReader();
        reader.onload = (e) => {
            previewImg.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(file);

        // 自動的にファイル名をセット（未入力の場合）
        if (!nameInput.value) {
            nameInput.value = file.name.replace(/\.[^/.]+$/, ''); // 拡張子を除去
        }
    }

    // Handle Upload Execution
    uploadBtn.onclick = async () => {
        const file = fileInput.files[0];
        if (!file) {
            alert("ファイルが選択されていません");
            return;
        }

        // Disable button to prevent double click
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'アップロード中...';
        uploadBtn.style.opacity = '0.7';
        uploadBtn.style.cursor = 'not-allowed';

        statusText.textContent = 'アップロード中...';
        statusText.style.color = '#666';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('name', nameInput.value || file.name);
        formData.append('name', nameInput.value || file.name);
        formData.append('type', typeSelect.value); // ★ タイプ送信
        if (gmOnlyCheck && gmOnlyCheck.checked) {
            formData.append('visibility', 'gm');
        }

        try {
            const response = await fetch('/api/upload_image', {
                method: 'POST',
                body: formData,
                credentials: 'include'
            });

            const data = await response.json();

            if (data.url) {
                statusText.textContent = '✓ アップロード完了！';
                statusText.style.color = '#28a745';
                uploadBtn.style.display = 'none'; // Hide button on success

                // 成功したら自動的に選択して閉じる
                setTimeout(async () => {
                    const selected = await maybeCropImageSelection({ url: data.url, id: data.id, name: data.name }, typeSelect.value || pickType);
                    if (!selected) return;
                    onSelect(selected);
                    modal.remove();
                }, 500);
            } else {
                statusText.textContent = '✗ アップロード失敗: ' + (data.error || '不明なエラー');
                statusText.style.color = '#dc3545';

                // Re-enable button
                uploadBtn.disabled = false;
                uploadBtn.textContent = 'アップロード開始';
                uploadBtn.style.opacity = '1';
                uploadBtn.style.cursor = 'pointer';
            }
        } catch (err) {
            console.error('[ImagePicker] Upload error:', err);
            statusText.textContent = '✗ 通信エラー';
            statusText.style.color = '#dc3545';

            // Re-enable button
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'アップロード開始';
            uploadBtn.style.opacity = '1';
            uploadBtn.style.cursor = 'pointer';
        }
    };
}
