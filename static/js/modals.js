// --- モーダル関連の関数 ---

function openUserSettingsModal(allowAttributeChange = false) {
    const oldName = currentUsername;
    const oldAttr = currentUserAttribute;
    let attributeHtml = '';
    if (allowAttributeChange) {
        attributeHtml = `
            <label for="modal-attribute">あなたの属性:</label>
            <select id="modal-attribute">
                <option value="Player" ${oldAttr === 'Player' ? 'selected' : ''}>プレイヤー (Player)</option>
                <option value="GM" ${oldAttr === 'GM' ? 'selected' : ''}>ゲームマスター (GM)</option>
            </select>
        `;
    } else {
        attributeHtml = `
            <label>あなたの属性:</label>
            <input type-="text" value="${oldAttr}" readonly disabled
                   style="background: #eee; color: #777; cursor: not-allowed;"
                   title="属性の変更はルームポータルに戻って行ってください">
        `;
    }
    const modalHtml = `
        <div class="modal-backdrop" id="user-settings-modal-backdrop">
            <div class="modal-content" style="width: 400px; padding: 25px;">
                <button class="modal-close-btn" style="float: right;">×</button>
                <h2>ユーザー情報変更</h2>
                <div class="auth-form">
                    <label for="modal-username">あなたの名前:</label>
                    <input type="text" id="modal-username" value="${oldName}">
                    ${attributeHtml}
                    <button id="modal-user-update-btn">更新</button>
                    <div id="modal-user-message" class="auth-message"></div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const backdrop = document.getElementById('user-settings-modal-backdrop');
    const updateBtn = document.getElementById('modal-user-update-btn');
    const msgEl = document.getElementById('modal-user-message');

    const closeModal = () => {
        backdrop.remove();
    };
    backdrop.querySelector('.modal-close-btn').addEventListener('click', closeModal);
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeModal();
    });

    updateBtn.addEventListener('click', async () => {
        const newName = document.getElementById('modal-username').value.trim();
        let newAttr;
        if (allowAttributeChange) {
            newAttr = document.getElementById('modal-attribute').value;
        } else {
            newAttr = currentUserAttribute;
        }
        if (!newName) {
            msgEl.textContent = '名前は必須です。';
            msgEl.className = 'auth-message error';
            return;
        }
        try {
            const response = await fetchWithSession('/api/entry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: newName, attribute: newAttr })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error);
            socket.emit('request_update_user_info', {
                username: newName,
                attribute: newAttr
            });
            msgEl.textContent = '更新しました。';
            msgEl.className = 'auth-message success';
            setTimeout(closeModal, 1000);
        } catch (error) {
            msgEl.textContent = `更新失敗: ${error.message}`;
            msgEl.className = 'auth-message error';
        }
    });
}

function openUserListModal() {
    const existingBackdrop = document.getElementById('user-list-modal-backdrop');
    if (existingBackdrop) {
        existingBackdrop.remove();
    }
    let listHtml = '';
    if (currentRoomUserList.length === 0) {
        listHtml = '<p>現在、他の参加者はいません。</p>';
    } else {
        currentRoomUserList.forEach(user => {
            const attrClass = user.attribute === 'GM' ? 'gm' : 'player';

            // ▼▼▼ 追加: オーナー判定ロジック ▼▼▼
            let ownerBadge = '';
            // battleState.owner_id (部屋主) と user.user_id (参加者) が一致したら表示
            if (battleState.owner_id && user.user_id && user.user_id === battleState.owner_id) {
                ownerBadge = ' <span style="color:#e67e22; font-weight:bold; font-size:0.9em;">(オーナー)</span>';
            }
            // ▲▲▲ 追加ここまで ▲▲▲

            listHtml += `
                <li class="user-list-item">
                    <span class="user-list-name">${user.username}</span>
                    <span class="user-list-attribute ${attrClass}">${user.attribute}</span>
                    ${ownerBadge} </li>
            `;
        });
    }
    const modalHtml = `
        <div class="modal-backdrop" id="user-list-modal-backdrop">
            <div class="modal-content user-list-modal-content">
                <button class="modal-close-btn" style="float: right;">×</button>
                <h2>参加者一覧 (${currentRoomUserList.length}名)</h2>
                <ul class="user-list-container">
                    ${listHtml}
                </ul>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const backdrop = document.getElementById('user-list-modal-backdrop');
    backdrop.querySelector('.modal-close-btn').addEventListener('click', () => backdrop.remove());
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) backdrop.remove();
    });
}

function closeCharacterModal() {
    const modal = document.getElementById('char-modal-backdrop');
    if (modal) {
        modal.remove();
        renderTokenList();
    }
}

function renderCharacterCard(char) {
    // ▼▼▼ 追加: 所有者情報の取得 (データがない場合は '不明') ▼▼▼
    const ownerName = char.owner || '不明';

    const fpState = char.states.find(s => s.name === 'FP');
    const statsHtml = `
        <div class="char-stats">
            <div class="char-stat-hp">
                HP: <input type="number" class="hp-input" value="${char.hp}"> <span>/ ${char.maxHp}</span>
            </div>
            <div class="char-stat-mp">
                MP: <input type="number" class="mp-input" value="${char.mp}"> <span>/ ${char.maxMp}</span>
            </div>
            <div class="char-stat-fp">
                FP: <input type="number" class="state-value-input" data-state-name="FP" value="${fpState ? fpState.value : 0}">
            </div>
        </div>
    `;
    const coreStats = ['筋力', '生命力', '体格', '精神力', '速度', '直感', '経験'];
    let coreStatsHtml = '';
    char.params.forEach(p => {
        if (coreStats.includes(p.label)) {
            coreStatsHtml += `<div class="char-param"><span class="char-param-label">${p.label}</span><span class="char-param-value">${p.value}</span></div>`;
        }
    });
    const statsDetailHtml = `<details class="char-details" open><summary>ステータス</summary><div class="char-params-grid">${coreStatsHtml}</div></details>`;

    // (数値状態: 出血、破裂など)
    let statesHtml = '';
    char.states.forEach(s => {
        if (s.name !== 'HP' && s.name !== 'MP' && s.name !== 'FP') {
            statesHtml += `<div class="state-item"><label>${s.name}:</label><input type="number" class="state-value-input" data-state-name="${s.name}" value="${s.value}"></div>`;
        }
    });
    const statesManageHtml = `<div class="char-states"><strong>状態・デバフ</strong><div class="state-list">${statesHtml}</div><div class="state-controls"><input type="text" class="new-state-input" placeholder="デバフ名 (例: 呪い)"><button class="add-state-btn">状態追加</button><button class="delete-state-btn">状態削除</button></div></div>`;

    // === バフ表示処理 ===
    let buffsHtml = '';
    const specialBuffs = char.special_buffs || [];
    if (specialBuffs.length > 0) {
        specialBuffs.forEach(buff => {
            let def = { name: buff.name, description: "説明なし", type: "buff" };
            if (typeof BUFF_DATA !== 'undefined' && typeof BUFF_DATA.get === 'function') {
                const found = BUFF_DATA.get(buff.name);
                if (found) def = found;
            }

            // 残り時間の表示
            let timer = '';
            if (buff.delay > 0) {
                timer = `(発動まで ${buff.delay}R)`;
            } else if (buff.lasting > 900) {
                timer = ''; // 永続なら時間は表示しない
            } else if (buff.lasting > 0) {
                timer = `(残り ${buff.lasting}R)`;
            }

            // 表示用HTMLの生成
            // def.name を使うことで _Atk5 などが消えた名前が表示されます
            buffsHtml += `
                <li class="buff-item ${def.type || ''}">
                    <strong class="buff-name">${def.name}</strong>
                    <span class="buff-timer">${timer}</span>
                    <p class="buff-description">${def.description}</p>
                </li>
            `;
        });
    } else {
        buffsHtml = '<li class="buff-none">(なし)</li>';
    }
    const buffsManageHtml = `<div class="char-buffs"><strong>特殊効果 (バフ)</strong><ul class="buff-list">${buffsHtml}</ul></div>`;

    // === GM用設定 ===
    let gmSettingsHtml = '';
    if (currentUserAttribute === 'GM') {
        gmSettingsHtml = `
            <div style="margin-left: 15px; border-left: 2px solid #eee; padding-left: 10px;">
                <label for="char-gm-only-toggle" title="ONの場合、プレイヤーは詳細閲覧や操作ができなくなります">
                    <input type="checkbox" id="char-gm-only-toggle" ${char.gmOnly ? 'checked' : ''}>
                    GMのみ操作可能
                </label>
            </div>
        `;
    }

    // ▼▼▼ 修正: char-modal-settings 内に所有者表示を追加 ▼▼▼
    // flex-wrap: wrap を追加して、所有者表示行が全幅を取れるように調整
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

            <button class="delete-char-btn" style="margin-left: auto;">このキャラを削除</button>
        </div>
    `;

    return `<div class="char-card" style="border-left-color: ${char.color};">${headerHtml}<div class="card-content">${statsHtml}${statsDetailHtml}${statesManageHtml}${buffsManageHtml}</div></div>`;
}

function openCharacterModal(charId) {
    closeCharacterModal();
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;
    const modalBackdrop = document.createElement('div');
    modalBackdrop.id = 'char-modal-backdrop';
    modalBackdrop.className = 'modal-backdrop';
    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';
    modalContent.innerHTML = renderCharacterCard(char);
    modalBackdrop.appendChild(modalContent);
    document.body.appendChild(modalBackdrop);
    modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) closeCharacterModal();
    });
    modalContent.querySelector('.modal-close-btn').addEventListener('click', closeCharacterModal);
    const settingsPanel = modalContent.querySelector('.char-modal-settings');
    modalContent.querySelector('.modal-settings-btn').addEventListener('click', () => {
        settingsPanel.style.display = (settingsPanel.style.display === 'none') ? 'flex' : 'none';
    });
    const gmOnlyToggle = modalContent.querySelector('#char-gm-only-toggle');
    if (gmOnlyToggle) {
        gmOnlyToggle.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            socket.emit('request_state_update', {
                room: currentRoomName,
                charId: char.id,
                statName: 'gmOnly',
                newValue: isChecked
            });
            char.gmOnly = isChecked;
        });
    }
    modalContent.querySelector('#char-color-picker').addEventListener('input', (e) => {
        socket.emit('request_state_update', {
            room: currentRoomName,
            charId: char.id,
            statName: 'color',
            newValue: e.target.value
        });
    });
    modalContent.querySelector('.color-reset-btn').addEventListener('click', () => {
        const defaultColor = (char.type === 'ally') ? '#007bff' : '#dc3545';
        socket.emit('request_state_update', {
            room: currentRoomName,
            charId: char.id,
            statName: 'color',
            newValue: defaultColor
        });
    });
    let debounceTimer = null;
    let pendingChanges = {};
    modalContent.addEventListener('input', (e) => {
        const target = e.target;
        if (target.id === 'char-color-picker') return;
        const newValue = parseInt(target.value, 10) || 0;
        let statName = null;
        if (target.classList.contains('hp-input')) statName = 'HP';
        else if (target.classList.contains('mp-input')) statName = 'MP';
        else if (target.classList.contains('state-value-input')) statName = target.dataset.stateName;
        if (statName) {
            pendingChanges[statName] = newValue;
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                socket.emit('request_state_update', {
                    room: currentRoomName,
                    charId: char.id,
                    changes: pendingChanges
                });
                pendingChanges = {};
            }, 2000);
        }
    });
    modalContent.addEventListener('click', (e) => {
        const target = e.target;
        if (target.classList.contains('delete-char-btn')) {
            if (confirm(`本当に「${char.name}」を戦闘から削除しますか？`)) {
                socket.emit('request_delete_character', {
                    room: currentRoomName,
                    charId: char.id
                });
                closeCharacterModal();
            }
            return;
        }
        if (target.classList.contains('add-state-btn')) {
            const input = modalContent.querySelector('.new-state-input');
            const stateName = input.value.trim();
            if (stateName && !char.states.find(s => s.name === stateName)) {
                socket.emit('request_state_update', {
                    room: currentRoomName,
                    charId: char.id,
                    statName: stateName,
                    newValue: 1,
                    isNew: true
                });
            }
            input.value = '';
        }
        if (target.classList.contains('delete-state-btn')) {
            const stateName = prompt(`削除したい状態名を入力してください (例: 呪い)\n現在の状態: ${char.states.map(s => s.name).join(', ')}`);
            if (stateName) {
                const protectedStates = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘'];
                if (protectedStates.includes(stateName)) {
                    alert('基本ステータスは削除できません。');
                    return;
                }
                socket.emit('request_state_update', {
                    room: currentRoomName,
                    charId: char.id,
                    statName: stateName,
                    isDelete: true
                });
            }
        }
    });
}

// modals.js (301行目)
function openCharLoadModal() {
    closeCharacterModal();


    // === ▼▼▼ 修正点（GM限定ボタンの追加・分割） ▼▼▼ ===
    let gmButtonHtml = '';
    if (currentUserAttribute === 'GM') {
        gmButtonHtml = `
            <div style="margin-top: 15px; border-top: 1px solid #ddd; padding-top: 10px;">
                <p style="font-weight:bold; margin-bottom:5px; font-size: 0.9em; color:#555;">★ GM専用: デバッグキャラ生成 (全スキル, MP/FP 1000)</p>
                <div style="display: flex; gap: 10px;">
                    <button id="modal-debug-ally-btn" class="room-action-btn" style="flex: 1; background-color: #007bff; font-size: 0.9em; padding: 6px;">
                        味方として生成
                    </button>
                    <button id="modal-debug-enemy-btn" class="room-action-btn danger" style="flex: 1; font-size: 0.9em; padding: 6px;">
                        敵として生成
                    </button>
                </div>
            </div>
        `;
    }
    // === ▲▲▲ 修正ここまで ▲▲▲ ===

    const modalHtml = `
        <div class="modal-backdrop" id="char-load-modal-backdrop">
            <div class="modal-content">
                <div class="char-load-modal">
                    <button class="modal-close-btn" style="float: right;">×</button>
                    <h2>キャラクターJSONの読み込み</h2>
                    <p>スプレッドシートで生成したJSONを貼り付けてください。</p>
                    <textarea id="modal-char-json-input" placeholder='{"kind":"character","data":{...}}'></textarea>
                    <div class="char-load-buttons">
                        <button id="modal-load-ally-btn">味方として追加</button>
                        <button id="modal-load-enemy-btn">敵として追加</button>
                    </div>
                    <p id="modal-load-result-msg" style="font-weight: bold;"></p>

                    ${gmButtonHtml} </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const backdrop = document.getElementById('char-load-modal-backdrop');
    const allyBtn = document.getElementById('modal-load-ally-btn');
    const enemyBtn = document.getElementById('modal-load-enemy-btn');
    const jsonInput = document.getElementById('modal-char-json-input');
    const resultMsg = document.getElementById('modal-load-result-msg');

    backdrop.querySelector('.modal-close-btn').addEventListener('click', () => backdrop.remove());
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
            backdrop.remove();
        }
    });
    allyBtn.addEventListener('click', () => {
        if (loadCharacterFromJSON('ally', jsonInput.value, resultMsg)) {
            jsonInput.value = '';
            setTimeout(() => backdrop.remove(), 1000);
        }
    });
    enemyBtn.addEventListener('click', () => {
        if (loadCharacterFromJSON('enemy', jsonInput.value, resultMsg)) {
            jsonInput.value = '';
            setTimeout(() => backdrop.remove(), 1000);
        }
    });

    // === ▼▼▼ 修正点（GMボタンのリスナー追加・分割） ▼▼▼ ===
    const debugAllyBtn = document.getElementById('modal-debug-ally-btn');
    const debugEnemyBtn = document.getElementById('modal-debug-enemy-btn');

    if (debugAllyBtn) {
        debugAllyBtn.addEventListener('click', () => {
            socket.emit('request_add_debug_character', {
                room: currentRoomName,
                type: 'ally'
            });
            resultMsg.textContent = 'デバッグキャラ(味方)の生成をリクエストしました...';
            resultMsg.style.color = 'blue';
            setTimeout(() => backdrop.remove(), 1000);
        });
    }

    if (debugEnemyBtn) {
        debugEnemyBtn.addEventListener('click', () => {
            socket.emit('request_add_debug_character', {
                room: currentRoomName,
                type: 'enemy'
            });
            resultMsg.textContent = 'デバッグキャラ(敵)の生成をリクエストしました...';
            resultMsg.style.color = 'red';
            setTimeout(() => backdrop.remove(), 1000);
        });
    }
    // === ▲▲▲ 修正ここまで ▲▲▲ ===
}

function openPresetManagerModal() {
    // 既存のモーダルがあれば閉じる (IDを修正)
    const existing = document.getElementById('preset-manager-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'preset-manager-backdrop';
    overlay.className = 'modal-backdrop';

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.style.maxWidth = '500px';
    // テキスト選択などがしやすいよう、念のためcursorスタイルも調整
    content.style.textAlign = 'left';

    // ▼▼▼ 追加: モーダル内部に余白を持たせる ▼▼▼
    content.style.padding = '25px';
    // ▲▲▲ 追加ここまで ▲▲▲

    // ヘッダー
    content.innerHTML = `
        <h3 style="margin-top: 0;">敵プリセット管理</h3>
        <p style="font-size:0.9em; color:#666;">現在の「敵」一覧を保存したり、保存したセットを呼び出します。<br>
        ※読込を行うと、現在の敵キャラクターは全て削除され入れ替わります。</p>

        <div style="border-bottom:1px solid #ddd; margin-bottom:20px; padding-bottom:20px;">
            <label><strong>現在の敵を保存:</strong></label>
            <div style="display:flex; gap:10px; margin-top:5px;">
                <input type="text" id="preset-save-name" placeholder="プリセット名 (例: ゴブリン3体)" style="flex:8; padding:8px;">
                <button id="preset-save-btn" class="room-action-btn" style="flex:2; padding:8px; background-color:#28a745; text-align:center;">保存</button>
            </div>
            <div id="preset-msg-area" style="font-size:0.85em; margin-top:5px; height:1.2em;"></div>
        </div>

        <div>
            <label><strong>保存済みプリセット:</strong></label>
            <ul id="preset-list" style="list-style:none; padding:0; margin-top:5px; max-height:200px; overflow-y:auto; border:1px solid #eee;">
                <li style="padding:10px; text-align:center; color:#999;">読み込み中...</li>
            </ul>
        </div>

        <div style="text-align: right; margin-top: 20px;">
            <button id="modal-close-btn" style="padding: 8px 16px;">閉じる</button>
        </div>
    `;

    overlay.appendChild(content);
    document.body.appendChild(overlay);

    // (以下、イベントリスナー等のロジックは変更なし)
    const saveNameInput = document.getElementById('preset-save-name');
    const saveBtn = document.getElementById('preset-save-btn');
    const msgArea = document.getElementById('preset-msg-area');
    const listArea = document.getElementById('preset-list');
    const closeBtn = document.getElementById('modal-close-btn');

    const closeFunc = () => {
        overlay.remove();
    };
    closeBtn.addEventListener('click', closeFunc);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeFunc();
    });

    socket.emit('request_get_presets', { room: currentRoomName });

    const renderList = (presets) => {
        listArea.innerHTML = '';
        if (!presets || presets.length === 0) {
            listArea.innerHTML = '<li style="padding:10px; text-align:center; color:#999;">プリセットがありません</li>';
            return;
        }

        presets.forEach(name => {
            const li = document.createElement('li');
            li.style.borderBottom = '1px solid #eee';
            li.style.padding = '8px 12px'; // リストアイテムも少し余白調整
            li.style.display = 'flex';
            li.style.justifyContent = 'space-between';
            li.style.alignItems = 'center';

            const nameSpan = document.createElement('span');
            nameSpan.textContent = name;
            nameSpan.style.fontWeight = 'bold';

            const btnGroup = document.createElement('div');

            const loadBtn = document.createElement('button');
            loadBtn.textContent = '読込';
            loadBtn.style.marginRight = '5px';
            loadBtn.style.fontSize = '0.85em';
            loadBtn.style.padding = '4px 10px';
            loadBtn.onclick = () => {
                if (confirm(`現在の敵を消去し、プリセット「${name}」を展開しますか？`)) {
                    socket.emit('request_load_preset', { room: currentRoomName, name: name });
                    closeFunc();
                }
            };

            const delBtn = document.createElement('button');
            delBtn.textContent = '削除';
            delBtn.style.fontSize = '0.85em';
            delBtn.style.padding = '4px 10px';
            delBtn.style.backgroundColor = '#dc3545';
            delBtn.style.color = 'white';
            delBtn.style.border = 'none';
            delBtn.onclick = () => {
                if (confirm(`プリセット「${name}」を削除しますか？`)) {
                    socket.emit('request_delete_preset', { room: currentRoomName, name: name });
                    li.remove();
                }
            };

            btnGroup.appendChild(loadBtn);
            btnGroup.appendChild(delBtn);
            li.appendChild(nameSpan);
            li.appendChild(btnGroup);
            listArea.appendChild(li);
        });
    };

    socket.off('receive_preset_list');
    socket.on('receive_preset_list', (data) => {
        renderList(data.presets);
    });

    socket.off('preset_saved');
    socket.on('preset_saved', (data) => {
        msgArea.textContent = `「${data.name}」を保存しました`;
        msgArea.style.color = 'green';
        saveNameInput.value = '';
        socket.emit('request_get_presets', { room: currentRoomName });
    });

    socket.off('preset_save_error');
    socket.on('preset_save_error', (data) => {
        if (data.error === 'duplicate') {
            if (confirm(data.message)) {
                socket.emit('request_save_preset', {
                    room: currentRoomName,
                    name: saveNameInput.value,
                    overwrite: true
                });
            }
        } else {
            msgArea.textContent = data.message;
            msgArea.style.color = 'red';
        }
    });

    saveBtn.addEventListener('click', () => {
        const name = saveNameInput.value.trim();
        if (!name) {
            msgArea.textContent = '名前を入力してください';
            msgArea.style.color = 'red';
            return;
        }
        socket.emit('request_save_preset', { room: currentRoomName, name: name });
        msgArea.textContent = '保存中...';
        msgArea.style.color = '#333';
    });
}


function openResetTypeModal(callback) {
    // 既存のモーダル削除
    const existing = document.getElementById('reset-type-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'reset-type-modal-backdrop';
    overlay.className = 'modal-backdrop';

    overlay.innerHTML = `
        <div class="modal-content" style="width: 400px; padding: 25px; text-align: center;">
            <h3 style="margin-top: 0; color: #dc3545;">リセットの種類の選択</h3>
            <p style="color: #555; margin-bottom: 20px;">
                実行したいリセット処理を選択してください。
            </p>

            <div style="display: flex; flex-direction: column; gap: 10px;">
                <button id="reset-status-btn" class="room-action-btn" style="padding: 12px; background-color: #ffc107; color: #333; font-weight: bold;">
                    ステータスのみリセット<br>
                    <span style="font-size: 0.8em; font-weight: normal;">(HP/MP/FP全快、状態異常・バフ解除)</span>
                </button>

                <button id="reset-full-btn" class="room-action-btn danger" style="padding: 12px; font-weight: bold;">
                    完全リセット<br>
                    <span style="font-size: 0.8em; font-weight: normal;">(キャラクターを全員削除し、初期状態へ)</span>
                </button>
            </div>

            <div style="margin-top: 20px;">
                <button id="reset-cancel-btn" style="padding: 8px 16px; border: none; background: #ccc; border-radius: 4px; cursor: pointer;">キャンセル</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const closeFunc = () => overlay.remove();

    document.getElementById('reset-cancel-btn').onclick = closeFunc;

    document.getElementById('reset-status-btn').onclick = () => {
        if (confirm('全キャラクターのHP・MP等を回復し、状態異常を解除しますか？\n(キャラ自体は削除されません)')) {
            callback('status');
            closeFunc();
        }
    };

    document.getElementById('reset-full-btn').onclick = () => {
        if (confirm('本当にキャラクターを全員削除し、戦闘を初期化しますか？\nこの操作は取り消せません。')) {
            callback('full');
            closeFunc();
        }
    };
}