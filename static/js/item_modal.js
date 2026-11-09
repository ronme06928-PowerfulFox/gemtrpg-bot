// static/js/item_modal.js
/**
 * アイテム使用UIモジュール
 */

// グローバルアイテムデータキャッシュ
let allItemData = {};
window.allItemData = allItemData;
let itemCatalogRequestVersion = 0;

// アイテムデータを読み込み
async function loadItemData() {
    const version = ++itemCatalogRequestVersion;
    try {
        const response = await fetch('/api/get_item_data', {cache: 'no-cache'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (version === itemCatalogRequestVersion) {
            allItemData = data;
            window.allItemData = data;
            console.log(`[OK] アイテムデータを読み込みました (${Object.keys(allItemData).length}件)`);
        }
    } catch (error) {
        console.error('[ERROR] アイテムデータの読み込みに失敗:', error);
    }
}

// アイテムモーダルを開く
function openItemModal() {
    // 既存のモーダルがあれば表示を切り替え
    let backdrop = document.getElementById('item-modal-backdrop');
    if (backdrop) {
        if (backdrop.style.display === 'none') {
            backdrop.style.display = 'flex';
            showCharacterList();
            return;
        } else {
            backdrop.style.display = 'none';
            return;
        }
    }

    // モーダルを新規作成
    backdrop = document.createElement('div');
    backdrop.id = 'item-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content item-modal';
    modalContent.style.width = '550px';
    modalContent.style.maxHeight = '650px';

    // ヘッダー
    const header = document.createElement('div');
    header.className = 'modal-header';
    header.id = 'item-modal-header';
    header.style.cssText = `
        background: linear-gradient(135deg, #4A90E2 0%, #357ABD 100%);
        color: white;
        padding: 15px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-radius: 8px 8px 0 0;
    `;
    header.innerHTML = `
        <h3 style="margin: 0; font-size: 1.2em;">🎒 アイテム使用</h3>
        <div class="modal-controls" style="display: flex; gap: 12px;">
            <button class="window-control-btn minimize-btn" style="
                background: rgba(255,255,255,0.2);
                border: none;
                color: white;
                width: 36px;
                height: 36px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 1.2em;
                font-weight: bold;
                transition: background 0.2s;
            " title="最小化">−</button>
            <button class="window-control-btn close-btn" style="
                background: rgba(255,255,255,0.2);
                border: none;
                color: white;
                width: 36px;
                height: 36px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 1.3em;
                font-weight: bold;
                transition: background 0.2s;
            " title="閉じる">×</button>
        </div>
    `;

    // ボディ
    const body = document.createElement('div');
    body.className = 'modal-body';
    body.id = 'item-modal-body';
    body.style.overflowY = 'auto';
    body.style.maxHeight = '550px';

    modalContent.appendChild(header);
    modalContent.appendChild(body);
    backdrop.appendChild(modalContent);
    document.body.appendChild(backdrop);

    // イベントリスナー
    header.querySelector('.minimize-btn').onclick = () => {
        backdrop.style.display = 'none';
    };

    header.querySelector('.close-btn').onclick = () => {
        backdrop.remove();
    };

    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
            backdrop.remove();
        }
    });

    // キャラクター一覧を表示
    showCharacterList();
}

// キャラクター一覧を表示
function showCharacterList() {
    const header = document.getElementById('item-modal-header');
    const body = document.getElementById('item-modal-body');

    if (!header || !body) return;

    // ヘッダー更新
    header.querySelector('h3').textContent = '🎒 アイテム使用';
    header.querySelector('h3').style.cssText = 'margin: 0; font-size: 1.2em;';

    // ボタンのホバー効果を追加
    const minimizeBtn = header.querySelector('.minimize-btn');
    const closeBtn = header.querySelector('.close-btn');

    if (minimizeBtn) {
        minimizeBtn.onmouseenter = () => { minimizeBtn.style.background = 'rgba(255,255,255,0.3)'; };
        minimizeBtn.onmouseleave = () => { minimizeBtn.style.background = 'rgba(255,255,255,0.2)'; };
    }

    if (closeBtn) {
        closeBtn.onmouseenter = () => { closeBtn.style.background = 'rgba(255,255,255,0.3)'; };
        closeBtn.onmouseleave = () => { closeBtn.style.background = 'rgba(255,255,255,0.2)'; };
    }

    // ボディをクリア
    body.innerHTML = '';

    if (!battleState || !battleState.characters) {
        body.innerHTML = '<div style="padding:20px; text-align:center; color:#999;">キャラクターがいません</div>';
        return;
    }

    // 自分のキャラクターを取得（配置済みのみ）
    const myChars = battleState.characters.filter(c => {
        const isOwner = c.owner === currentUsername || (currentUserId && c.owner_id === currentUserId);
        const isPlaced = c.x >= 0 && c.y >= 0;
        return isOwner && isPlaced;
    });

    if (myChars.length === 0) {
        body.innerHTML = '<div style="padding:20px; text-align:center; color:#999;">あなたのキャラクターがいません</div>';
        return;
    }

    const title = document.createElement('div');
    title.style.cssText = 'padding: 10px 15px; background: #f0f8ff; border-bottom: 2px solid #3498db; margin-bottom: 10px;';
    title.innerHTML = '<strong>キャラクターを選択してください</strong>';
    body.appendChild(title);

    myChars.forEach(char => {
        const row = document.createElement('div');
        row.className = 'char-item-row';
        row.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
            transition: background 0.2s;
        `;

        const inventory = char.inventory || {};
        const itemCount = Object.keys(inventory).length;
        const totalItems = Object.values(inventory).reduce((sum, count) => sum + count, 0);

        const isDead = char.hp <= 0;

        if (isDead) {
            row.style.background = '#f8f8f8';
            row.style.cursor = 'not-allowed';
            row.style.opacity = '0.6';
        }

        row.innerHTML = `
            <div>
                <div style="font-weight: bold; margin-bottom: 3px;">${char.name}</div>
                <div style="font-size: 0.85em; color: #666;">
                    HP: ${char.hp}/${char.maxHp} | アイテム: ${totalItems}個 (${itemCount}種類)
                </div>
            </div>
            <div style="color: ${isDead ? '#999' : '#3498db'}; font-size: 1.2em;">
                ${isDead ? '✖' : '▶'}
            </div>
        `;

        if (!isDead) {
            row.onmouseenter = () => { row.style.background = '#f0f8ff'; };
            row.onmouseleave = () => { row.style.background = 'white'; };
            row.onclick = () => showItemList(char.id);
        }

        body.appendChild(row);
    });
}

// アイテム一覧を表示
function showItemList(charId) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    const header = document.getElementById('item-modal-header');
    const body = document.getElementById('item-modal-body');

    if (!header || !body) return;

    // ヘッダー更新（戻るボタン追加）
    header.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px;">
            <button class="back-btn" style="
                background: rgba(255,255,255,0.2);
                border: none;
                color: white;
                width: 40px;
                height: 40px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 1.4em;
                transition: background 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
            " title="戻る">←</button>
            <h3 style="margin: 0; font-size: 1.2em;">🎒 ${char.name} のアイテム</h3>
        </div>
        <div class="modal-controls" style="display: flex; gap: 12px;">
            <button class="window-control-btn minimize-btn" style="
                background: rgba(255,255,255,0.2);
                border: none;
                color: white;
                width: 36px;
                height: 36px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 1.2em;
                font-weight: bold;
                transition: background 0.2s;
            " title="最小化">−</button>
            <button class="window-control-btn close-btn" style="
                background: rgba(255,255,255,0.2);
                border: none;
                color: white;
                width: 36px;
                height: 36px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 1.3em;
                font-weight: bold;
                transition: background 0.2s;
            " title="閉じる">×</button>
        </div>
    `;

    // ホバー効果を追加
    const backBtn = header.querySelector('.back-btn');
    const minimizeBtn = header.querySelector('.minimize-btn');
    const closeBtn = header.querySelector('.close-btn');

    if (backBtn) {
        backBtn.onmouseenter = () => { backBtn.style.background = 'rgba(255,255,255,0.3)'; };
        backBtn.onmouseleave = () => { backBtn.style.background = 'rgba(255,255,255,0.2)'; };
        backBtn.onclick = showCharacterList;
    }

    if (minimizeBtn) {
        minimizeBtn.onmouseenter = () => { minimizeBtn.style.background = 'rgba(255,255,255,0.3)'; };
        minimizeBtn.onmouseleave = () => { minimizeBtn.style.background = 'rgba(255,255,255,0.2)'; };
        minimizeBtn.onclick = () => {
            document.getElementById('item-modal-backdrop').style.display = 'none';
        };
    }

    if (closeBtn) {
        closeBtn.onmouseenter = () => { closeBtn.style.background = 'rgba(255,255,255,0.3)'; };
        closeBtn.onmouseleave = () => { closeBtn.style.background = 'rgba(255,255,255,0.2)'; };
        closeBtn.onclick = () => {
            document.getElementById('item-modal-backdrop').remove();
        };
    }

    // ボディをクリア
    body.innerHTML = '';

    const inventory = char.inventory || {};
    const itemIds = Object.keys(inventory);

    if (itemIds.length === 0) {
        body.innerHTML = '<div style="padding:20px; text-align:center; color:#999;">アイテムを所持していません</div>';
        return;
    }

    itemIds.forEach(itemId => {
        const quantity = inventory[itemId];
        const itemData = allItemData[itemId];

        if (!itemData) {
            console.warn(`[WARN] アイテムデータが見つかりません: ${itemId}`);
            return;
        }

        const card = document.createElement('div');
        card.className = 'item-card';
        card.style.cssText = `
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 12px;
            transition: box-shadow 0.2s;
        `;

        card.onmouseenter = () => { card.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'; };
        card.onmouseleave = () => { card.style.boxShadow = 'none'; };

        const headerRow = document.createElement('div');
        headerRow.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;';

        const titleDiv = document.createElement('div');
        titleDiv.innerHTML = `
            <div style="font-weight: bold; font-size: 1.1em; margin-bottom: 3px;">${itemData.name}</div>
            <div style="font-size: 0.85em; color: #666;">所持数: ${quantity}個</div>
        `;

        const useBtn = document.createElement('button');
        useBtn.textContent = '使用';
        useBtn.className = 'item-use-btn';
        useBtn.style.cssText = `
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 20px;
            cursor: pointer;
            font-weight: bold;
            transition: background 0.2s;
        `;
        useBtn.onmouseenter = () => { useBtn.style.background = '#229954'; };
        useBtn.onmouseleave = () => { useBtn.style.background = '#27ae60'; };
        useBtn.onclick = () => openUseItemConfirm(char.id, itemId);

        headerRow.appendChild(titleDiv);
        headerRow.appendChild(useBtn);

        const descDiv = document.createElement('div');
        descDiv.className = 'item-description';
        descDiv.style.cssText = 'font-size: 0.9em; color: #555; margin-top: 8px; line-height: 1.4;';
        descDiv.textContent = itemData.description || '(説明なし)';

        const flavorDiv = document.createElement('div');
        flavorDiv.className = 'item-flavor';
        flavorDiv.style.cssText = 'font-size: 0.85em; color: #888; font-style: italic; margin-top: 5px;';
        flavorDiv.textContent = itemData.flavor || '';

        card.appendChild(headerRow);
        card.appendChild(descDiv);
        if (itemData.flavor) {
            card.appendChild(flavorDiv);
        }

        body.appendChild(card);
    });
}

// アイテム使用確認モーダルを開く
function openUseItemConfirm(charId, itemId) {
    const char = battleState.characters.find(c => c.id === charId);
    const itemData = allItemData[itemId];

    if (!char || !itemData) return;

    const effect = itemData.effect || {};
    const targetType = effect.target || 'single';

    // 確認モーダルを作成
    const confirmBackdrop = document.createElement('div');
    confirmBackdrop.className = 'modal-backdrop';
    confirmBackdrop.style.display = 'flex';
    confirmBackdrop.style.zIndex = '10001'; // アイテムモーダルより前面

    const confirmContent = document.createElement('div');
    confirmContent.className = 'modal-content';
    confirmContent.style.width = '450px';

    const confirmHeader = document.createElement('div');
    confirmHeader.className = 'modal-header';
    confirmHeader.innerHTML = `<h3>${itemData.name} を使用</h3>`;

    const confirmBody = document.createElement('div');
    confirmBody.className = 'modal-body';
    confirmBody.style.padding = '20px';

    if (targetType === 'single') {
        // 単体対象：味方一覧から選択
        confirmBody.innerHTML = '<div style="margin-bottom: 10px; font-weight: bold;">対象を選択してください:</div>';

        const charType = char.type || 'ally';
        const allies = battleState.characters.filter(c => c.type === charType && c.hp > 0 && c.x >= 0 && c.y >= 0);

        allies.forEach(target => {
            const radio = document.createElement('div');
            radio.style.cssText = 'padding: 10px; cursor: pointer; border-bottom: 1px solid #eee;';
            radio.innerHTML = `
                <label style="cursor: pointer; display: flex; align-items: center; gap: 10px;">
                    <input type="radio" name="item-target" value="${target.id}" style="cursor: pointer;">
                    <span>${target.name} (HP: ${target.hp}/${target.maxHp})</span>
                </label>
            `;
            radio.onmouseenter = () => { radio.style.background = '#f0f8ff'; };
            radio.onmouseleave = () => { radio.style.background = 'white'; };
            radio.onclick = (e) => {
                if (e.target.tagName !== 'INPUT') {
                    radio.querySelector('input').checked = true;
                }
            };
            confirmBody.appendChild(radio);
        });
    } else {
        // 全体対象：確認のみ
        const charType = char.type || 'ally';
        const targets = battleState.characters.filter(c => {
            if (targetType === 'all_allies') {
                return c.type === charType && c.hp > 0 && c.x >= 0 && c.y >= 0;
            } else if (targetType === 'all_enemies') {
                const enemyType = charType === 'ally' ? 'enemy' : 'ally';
                return c.type === enemyType && c.hp > 0 && c.x >= 0 && c.y >= 0;
            }
            return false;
        });

        confirmBody.innerHTML = `
            <div style="margin-bottom: 10px;">${itemData.description}</div>
            <div style="margin-bottom: 10px; font-weight: bold;">対象:</div>
            <div style="padding: 10px; background: #f9f9f9; border-radius: 5px;">
                ${targets.map(t => t.name).join(', ')}
            </div>
        `;
    }

    const confirmFooter = document.createElement('div');
    confirmFooter.style.cssText = 'display: flex; justify-content: flex-end; gap: 10px; padding: 15px; border-top: 1px solid #eee;';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'キャンセル';
    cancelBtn.style.cssText = 'padding: 8px 20px; background: #95a5a6; color: white; border: none; border-radius: 5px; cursor: pointer;';
    cancelBtn.onclick = () => confirmBackdrop.remove();

    const executeBtn = document.createElement('button');
    executeBtn.textContent = '使用';
    executeBtn.style.cssText = 'padding: 8px 20px; background: #27ae60; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;';
    executeBtn.onclick = () => {
        let targetId = null;
        if (targetType === 'single') {
            const selected = confirmBody.querySelector('input[name="item-target"]:checked');
            if (!selected) {
                alert('対象を選択してください');
                return;
            }
            targetId = selected.value;
        }

        executeItemUse(charId, targetId, itemId);
        confirmBackdrop.remove();

        // アイテムモーダルを閉じる
        const itemBackdrop = document.getElementById('item-modal-backdrop');
        if (itemBackdrop) {
            itemBackdrop.remove();
        }
    };

    confirmFooter.appendChild(cancelBtn);
    confirmFooter.appendChild(executeBtn);

    confirmContent.appendChild(confirmHeader);
    confirmContent.appendChild(confirmBody);
    confirmContent.appendChild(confirmFooter);
    confirmBackdrop.appendChild(confirmContent);
    document.body.appendChild(confirmBackdrop);

    confirmBackdrop.addEventListener('click', (e) => {
        if (e.target === confirmBackdrop) {
            confirmBackdrop.remove();
        }
    });
}

// アイテムを使用
function executeItemUse(userId, targetId, itemId) {
    socket.emit('request_use_item', {
        room: currentRoomName,
        user_id: userId,
        target_id: targetId,
        item_id: itemId
    });
}
