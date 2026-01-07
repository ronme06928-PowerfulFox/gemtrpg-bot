// === ▼▼▼ Action Dock & Immediate Skills Functions ▼▼▼ ===

// 即時発動スキル判定関数
// 即時発動スキル判定関数
function hasImmediateSkill(char) {
    if (!window.allSkillData || !char.commands) return false;
    const regex = /【(.*?)\s+(.*?)】/g;
    let match;
    while ((match = regex.exec(char.commands)) !== null) {
        const skillId = match[1];
        const skillData = window.allSkillData[skillId];
        if (skillData && skillData.tags && skillData.tags.includes('即時発動')) {
            return true;
        }
    }
    return false;
}

// アクションドックの更新関数
function updateActionDock() {
    const immediateIcon = document.getElementById('dock-immediate-icon');
    const wideIcon = document.getElementById('dock-wide-icon');
    const stagingIcon = document.getElementById('dock-staging-icon');

    if (!immediateIcon) return;

    if (!battleState || !battleState.characters) {
        immediateIcon.classList.remove('active');
        immediateIcon.classList.add('disabled');
        return;
    }

    // ログインユーザーのキャラクターを特定
    const myChars = battleState.characters.filter(c => {
        return c.owner === currentUsername || (currentUserId && c.owner_id === currentUserId);
    });

    // 即時発動スキル所持 & 未使用のキャラクターがいるか判定
    const canUseImmediate = myChars.some(char => {
        const hasSkill = hasImmediateSkill(char);
        const notUsed = !(char.flags && char.flags.immediate_action_used);
        const alive = char.hp > 0;
        return hasSkill && notUsed && alive;
    });

    // アイコンの活性/非活性を切り替え
    if (canUseImmediate) {
        immediateIcon.classList.add('active');
        immediateIcon.classList.remove('disabled');
    } else {
        immediateIcon.classList.remove('active');
        immediateIcon.classList.add('disabled');
    }

    // 広域アイコンの表示/非表示
    if (wideIcon) {
        // 広域マッチが進行中かどうかを判定
        if (typeof visualWideState !== 'undefined' && visualWideState.isDeclared) {
            wideIcon.style.display = 'flex';
        } else {
            wideIcon.style.display = 'none';
        }
    }

    // 未配置エリア（モーダル）のリストがあれば無条件に更新（非表示でも最新化しておく）
    const stagingList = document.getElementById('staging-overlay-list');
    if (stagingList) {
        // console.log('📦 Updating staging overlay list...'); // 頻出しすぎる場合はコメントアウト
        renderStagingOverlayList(stagingList);
    }
}

// 即時発動モーダルを開く
function openImmediateSkillModal() {
    const immediateIcon = document.getElementById('dock-immediate-icon');

    // 非活性状態ならクリック無効
    if (immediateIcon && immediateIcon.classList.contains('disabled')) {
        return;
    }

    // 既存のモーダルがあれば表示を切り替え
    let backdrop = document.getElementById('immediate-modal-backdrop');
    if (backdrop) {
        if (backdrop.style.display === 'none') {
            backdrop.style.display = 'flex';
            immediateIcon.classList.remove('minimized');
            return;
        } else {
            backdrop.style.display = 'none';
            return;
        }
    }

    // モーダルを新規作成
    backdrop = document.createElement('div');
    backdrop.id = 'immediate-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content immediate-modal';

    // ヘッダー
    const header = document.createElement('div');
    header.className = 'modal-header';
    header.innerHTML = `
        <h3>⚡ 即時発動スキル</h3>
        <div class="modal-controls">
            <button class="window-control-btn minimize-btn" title="最小化">_</button>
            <button class="window-control-btn close-btn" title="閉じる">×</button>
        </div>
    `;

    // ボディ
    const body = document.createElement('div');
    body.className = 'modal-body';
    body.id = 'immediate-skill-list';

    // キャラクターリストを生成
    if (battleState && battleState.characters) {
        const myChars = battleState.characters.filter(c => {
            return c.owner === currentUsername || (currentUserId && c.owner_id === currentUserId);
        });

        if (myChars.length === 0) {
            body.innerHTML = '<div style="padding:20px; text-align:center; color:#999;">あなたのキャラクターがいません</div>';
        } else {
            myChars.forEach(char => {
                const row = createImmediateCharRow(char);
                body.appendChild(row);
            });
        }
    }

    modalContent.appendChild(header);
    modalContent.appendChild(body);
    backdrop.appendChild(modalContent);
    document.body.appendChild(backdrop);

    // イベントリスナー
    header.querySelector('.minimize-btn').onclick = () => {
        backdrop.style.display = 'none';
        immediateIcon.classList.add('minimized');
    };

    header.querySelector('.close-btn').onclick = () => {
        backdrop.remove();
        immediateIcon.classList.remove('minimized');
    };

    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
            backdrop.remove();
            immediateIcon.classList.remove('minimized');
        }
    });
}

// キャラクターの行を作成
function createImmediateCharRow(char) {
    const row = document.createElement('div');
    row.className = 'immediate-char-row';

    const isUsed = char.flags && char.flags.immediate_action_used;
    const isDead = char.hp <= 0;

    if (isUsed || isDead) {
        row.classList.add('used');
    }

    // キャラクター名
    const nameDiv = document.createElement('div');
    nameDiv.className = 'immediate-char-name';
    nameDiv.textContent = char.name;

    if (isUsed) {
        const status = document.createElement('div');
        status.className = 'immediate-char-status used';
        status.textContent = '✔ 使用済み';
        nameDiv.appendChild(status);
    } else if (isDead) {
        const status = document.createElement('div');
        status.className = 'immediate-char-status used';
        status.textContent = '✖ 戦闘不能';
        nameDiv.appendChild(status);
    }

    // スキル選択プルダウン
    const select = document.createElement('select');
    select.className = 'immediate-skill-select';
    select.disabled = isUsed || isDead;

    // 即時発動スキルを抽出
    const immediateSkills = [];
    if (char.commands && window.allSkillData) {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        while ((match = regex.exec(char.commands)) !== null) {
            const skillId = match[1];
            const skillName = match[2];
            const skillData = window.allSkillData[skillId];
            if (skillData && skillData.tags && skillData.tags.includes('即時発動')) {
                immediateSkills.push({ id: skillId, name: skillName, data: skillData });
            }
        }
    }

    if (immediateSkills.length === 0) {
        const option = document.createElement('option');
        option.textContent = '(即時発動スキルなし)';
        select.appendChild(option);
        select.disabled = true;
    } else {
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'スキルを選択...';
        select.appendChild(defaultOption);

        immediateSkills.forEach(skill => {
            const option = document.createElement('option');
            option.value = skill.id;
            option.textContent = `${skill.id} ${skill.name}`;
            select.appendChild(option);
        });
    }

    // 実行ボタン
    const executeBtn = document.createElement('button');
    executeBtn.className = 'immediate-execute-btn';
    executeBtn.textContent = '実行';
    executeBtn.disabled = isUsed || isDead || immediateSkills.length === 0;

    executeBtn.onclick = () => {
        const selectedSkillId = select.value;
        if (!selectedSkillId) {
            alert('スキルを選択してください');
            return;
        }

        // スキル実行リクエストを送信
        executeBtn.disabled = true;
        executeBtn.textContent = '処理中...';

        socket.emit('request_skill_declaration', {
            room: currentRoomName,
            actor_id: char.id,
            target_id: char.id, // 即時発動スキルは自身がターゲット
            skill_id: selectedSkillId,
            commit: true,
            prefix: `immediate_${char.id}`
        });

        // 少し待ってからモーダルを閉じる
        setTimeout(() => {
            const backdrop = document.getElementById('immediate-modal-backdrop');
            if (backdrop) {
                backdrop.remove();
            }
            const immediateIcon = document.getElementById('dock-immediate-icon');
            if (immediateIcon) {
                immediateIcon.classList.remove('minimized');
            }
        }, 500);
    };

    row.appendChild(nameDiv);
    row.appendChild(select);
    row.appendChild(executeBtn);

    return row;
}

// アクションドックの初期化（イベントリスナー設定のみ）
function initializeActionDock() {
    console.log('Initializing Action Dock...');

    const immediateIcon = document.getElementById('dock-immediate-icon');
    const addCharIcon = document.getElementById('dock-add-char-icon'); // 追加
    const stagingIcon = document.getElementById('dock-staging-icon');
    const wideIcon = document.getElementById('dock-wide-icon');

    if (!immediateIcon) {
        console.error('dock-immediate-icon not found in DOM');
        return;
    }

    // 即時発動アイコンのクリックイベント
    immediateIcon.onclick = function (e) {
        console.log('🎯 ICON CLICKED!', e);
        openImmediateSkillModal();
    };

    console.log('✅ Click event registered!');

    console.log('✅ Click event registered!');

    // キャラ追加アイコンのクリックイベント
    if (addCharIcon) {
        // テキストバトルフィールドと同じJSON読込/デバッグ生成モーダルを使用
        if (typeof openCharLoadModal === 'function') {
            addCharIcon.onclick = openCharLoadModal;
        } else {
            console.warn("openCharLoadModal is not defined.");
        }
        console.log('✅ Add Char icon click event registered');
    }

    // 未配置エリアアイコンのクリックイベント
    if (stagingIcon) {
        stagingIcon.onclick = toggleStagingAreaOverlay;
        console.log('✅ Staging icon click event registered');
    }

    // 広域戦闘アイコンのクリックイベント
    if (wideIcon) {
        wideIcon.onclick = () => {
            const wideModal = document.getElementById('visual-wide-match-modal');
            if (wideModal) {
                if (wideModal.style.display === 'none') {
                    wideModal.style.display = 'block';
                    wideIcon.classList.remove('minimized');
                } else {
                    wideModal.style.display = 'none';
                    wideIcon.classList.add('minimized');
                }
            }
        };
    }

    console.log('Action Dock initialized successfully');

    // 初回更新
    updateActionDock();
}

// === ▲▲▲ Action Dock & Immediate Skills Functions ▲▲▲ ===

// === ▼▼▼ Staging Area Overlay ▼▼▼ ===

// 未配置エリアオーバーレイの表示/非表示
function toggleStagingAreaOverlay() {
    console.log('📦 Toggling staging area overlay...');

    let overlay = document.getElementById('staging-overlay');

    if (overlay) {
        // 既に存在する場合は表示/非表示を切り替え
        if (overlay.style.display === 'none') {
            overlay.style.display = 'flex';
        } else {
            overlay.style.display = 'none';
        }
        return;
    }

    // オーバーレイを新規作成
    overlay = document.createElement('div');
    overlay.id = 'staging-overlay';
    overlay.className = 'modal-backdrop';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'flex-start';
    overlay.style.paddingTop = '60px';

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.style.width = '600px';
    content.style.maxHeight = '70vh';
    content.style.display = 'flex';
    content.style.flexDirection = 'column';

    // ヘッダー
    const header = document.createElement('div');
    header.className = 'modal-header';
    header.style.background = 'linear-gradient(135deg, #e67e22 0%, #d35400 100%)';
    header.style.color = 'white';
    header.style.padding = '15px 20px';
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    header.innerHTML = `
        <h3 style="margin:0;">📦 未配置キャラクター</h3>
        <button class="window-control-btn close-btn" style="background:none; border:none; color:white; font-size:1.5em; cursor:pointer;">×</button>
    `;

    // ボディ
    const body = document.createElement('div');
    body.className = 'modal-body';
    body.style.padding = '20px';
    body.style.overflowY = 'auto';
    body.id = 'staging-overlay-list';

    // 未配置キャラクターのリストを表示
    renderStagingOverlayList(body);

    content.appendChild(header);
    content.appendChild(body);
    overlay.appendChild(content);
    document.body.appendChild(overlay);

    // 閉じるボタンのイベント
    header.querySelector('.close-btn').onclick = () => {
        overlay.style.display = 'none';
    };

    // 背景クリックで閉じる
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.style.display = 'none';
        }
    });
}

// 未配置キャラクターのリストを描画
function renderStagingOverlayList(container) {
    if (!battleState || !battleState.characters) {
        container.innerHTML = '<p style="text-align:center; color:#999;">キャラクターがいません</p>';
        return;
    }

    const unplacedChars = battleState.characters.filter(c => c.x < 0 || c.y < 0);

    if (unplacedChars.length === 0) {
        container.innerHTML = '<p style="text-align:center; color:#999;">未配置のキャラクターはいません</p>';
        return;
    }

    container.innerHTML = '';

    unplacedChars.forEach(char => {
        const row = document.createElement('div');
        row.style.padding = '10px';
        row.style.borderBottom = '1px solid #eee';
        row.style.display = 'flex';
        row.style.justifyContent = 'space-between';
        row.style.alignItems = 'center';

        const nameSpan = document.createElement('span');
        nameSpan.textContent = char.name;
        nameSpan.style.fontWeight = 'bold';
        nameSpan.style.display = 'block';

        const statsSpan = document.createElement('span');
        statsSpan.textContent = `HP: ${char.hp} / SPD: ${char.SPD}`;
        statsSpan.style.fontSize = '0.9em';
        statsSpan.style.color = '#666';
        statsSpan.style.display = 'block';
        statsSpan.style.marginTop = '3px';

        const infoDiv = document.createElement('div');
        infoDiv.appendChild(nameSpan);
        infoDiv.appendChild(statsSpan);

        // ボタンを並べるコンテナ
        const buttonContainer = document.createElement('div');
        buttonContainer.style.display = 'flex';
        buttonContainer.style.gap = '8px';

        // 削除ボタン
        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = '削除';
        deleteBtn.style.padding = '8px 16px';
        deleteBtn.style.background = '#e74c3c';
        deleteBtn.style.color = 'white';
        deleteBtn.style.border = 'none';
        deleteBtn.style.borderRadius = '4px';
        deleteBtn.style.cursor = 'pointer';
        deleteBtn.style.fontWeight = 'bold';
        deleteBtn.onclick = () => {
            if (confirm(`「${char.name}」を削除しますか？`)) {
                socket.emit('request_delete_character', {
                    room: currentRoomName,
                    charId: char.id
                });
            }
        };

        // 配置ボタン
        const placeBtn = document.createElement('button');
        placeBtn.textContent = '配置';
        placeBtn.style.padding = '8px 16px';
        placeBtn.style.background = '#3498db';
        placeBtn.style.color = 'white';
        placeBtn.style.border = 'none';
        placeBtn.style.borderRadius = '4px';
        placeBtn.style.cursor = 'pointer';
        placeBtn.style.fontWeight = 'bold';
        placeBtn.onclick = () => placeCharacterToDefaultPosition(char);

        buttonContainer.appendChild(deleteBtn);
        buttonContainer.appendChild(placeBtn);

        row.appendChild(infoDiv);
        row.appendChild(buttonContainer);
        container.appendChild(row);
    });
}

// キャラクターをデフォルト位置に配置
// キャラクターをデフォルト位置に配置
function placeCharacterToDefaultPosition(char) {
    console.log(`[DEBUG] placeCharacterToDefaultPosition called for ${char.name}`);

    // フィールドの中央をグリッド座標で指定（25x25の中央 = 12, 12）
    const defaultX = 12;
    const defaultY = 12;

    // 空き位置を探す（グリッド座標）
    const position = findEmptyPosition(defaultX, defaultY);
    console.log(`[DEBUG] Found empty position: (${position.x}, ${position.y})`);

    // socketオブジェクトの確認
    const socketToUse = window.socket || socket;
    if (!socketToUse) {
        console.error('[ERROR] socket is not initialized!');
        alert('サーバーとの接続エラーです。ページをリロードしてください。');
        return;
    }

    // サーバーに移動を通知（グリッド座標）
    console.log('[DEBUG] Emitting request_move_character event...');
    socketToUse.emit('request_move_character', {
        room: currentRoomName,
        character_id: char.id,
        x: position.x,
        y: position.y
    });

    console.log(`Placing ${char.name} at (${position.x}, ${position.y})`);
}

// 空き位置を探す（螺旋状に探索）
function findEmptyPosition(startX, startY) {
    if (!battleState || !battleState.characters) {
        return { x: startX, y: startY };
    }

    // 指定位置が空いているか確認
    const isOccupied = (x, y) => {
        return battleState.characters.some(c => c.x === x && c.y === y);
    };

    // まず指定位置をチェック
    if (!isOccupied(startX, startY)) {
        return { x: startX, y: startY };
    }

    // 周囲を螺旋状に探索
    const directions = [
        [1, 0], [0, 1], [-1, 0], [0, -1],  // 右、下、左、上
        [1, 1], [1, -1], [-1, 1], [-1, -1] // 斜め
    ];

    for (let radius = 1; radius <= 5; radius++) {
        for (const [dx, dy] of directions) {
            const x = startX + dx * radius;
            const y = startY + dy * radius;

            // マップの範囲内かチェック（25x25グリッド）
            if (x >= 0 && x < 25 && y >= 0 && y < 25 && !isOccupied(x, y)) {
                return { x, y };
            }
        }
    }

    // 見つからなければデフォルト位置を返す
    return { x: startX, y: startY };
}

// ピクセル座標用の空き位置を探す（螺旋状に探索）
function findEmptyPositionPixel(startX, startY) {
    if (!battleState || !battleState.characters) {
        return { x: startX, y: startY };
    }

    const tokenSize = 90; // 駒のサイズ（余裕を持たせる）

    // 指定位置が空いているか確認（ピクセル座標で判定）
    const isOccupied = (x, y) => {
        return battleState.characters.some(c => {
            // 駒が配置済み（x, y >= 0）かつ重なっているか判定
            if (c.x < 0 || c.y < 0) return false;
            const dx = Math.abs(c.x - x);
            const dy = Math.abs(c.y - y);
            return dx < tokenSize && dy < tokenSize;
        });
    };

    // まず指定位置をチェック
    if (!isOccupied(startX, startY)) {
        return { x: startX, y: startY };
    }

    // 周囲を螺旋状に探索（ピクセル単位）
    const directions = [
        [1, 0], [0, 1], [-1, 0], [0, -1],  // 右、下、左、上
        [1, 1], [1, -1], [-1, 1], [-1, -1] // 斜め
    ];

    for (let radius = 1; radius <= 10; radius++) {
        for (const [dx, dy] of directions) {
            const x = startX + dx * tokenSize;
            const y = startY + dy * tokenSize;

            // マップの範囲内かチェック（2250px以内）
            if (x >= 0 && x < 2250 && y >= 0 && y < 2250 && !isOccupied(x, y)) {
                return { x, y };
            }
        }
    }

    // 見つからなければデフォルト位置を返す
    return { x: startX, y: startY };
}

// === ▲▲▲ Staging Area Overlay ▲▲▲ ===
