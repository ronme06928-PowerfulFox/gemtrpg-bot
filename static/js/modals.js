// --- モーダル関連の関数 ---

/**
 * ユーザー設定モーダルを開く
 */
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
            <input type="text" value="${oldAttr}" readonly disabled
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

/**
 * 参加者一覧モーダル
 */
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

            // オーナー判定ロジック
            let ownerBadge = '';
            if (battleState.owner_id && user.user_id && user.user_id === battleState.owner_id) {
                ownerBadge = ' <span style="color:#e67e22; font-weight:bold; font-size:0.9em;">(オーナー)</span>';
            }

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

/**
 * キャラクター詳細モーダルを閉じる
 */
function closeCharacterModal() {
    const modal = document.getElementById('char-modal-backdrop');
    if (modal) {
        modal.remove();
        renderTokenList();
    }
}

/**
 * キャラクター詳細カードHTML生成 (統合版)
 *
 * 【復旧仕様】
 * 1. 歯車設定UI: 以前のリスト形式（垂直配置）＋スライダーUIを復元
 * 2. バフ表示: スキル定義等から継承された flavor/description を優先表示
 *    (Gouged Wound等が動的定義のデフォルトテキストに上書きされないようにする)
 */
function renderCharacterCard(char) {
    const ownerName = char.owner || '不明';
    const fpState = char.states.find(s => s.name === 'FP');
    const fpVal = fpState ? fpState.value : 0;

    // --- Params ---
    const coreStats = ['筋力', '生命力', '体格', '精神力', '速度', '直感', '経験', '物理補正', '魔法補正'];
    const explorationStats = ['五感', '採取', '本能', '鑑定', '対話', '尋問', '諜報', '窃取', '隠密', '運動', '制作', '回避'];

    // Normalize params to array of objects
    let charParams = [];
    if (Array.isArray(char.params)) {
        charParams = char.params;
    } else if (char.params && typeof char.params === 'object') {
        charParams = Object.entries(char.params).map(([k, v]) => ({ label: k, value: v }));
    }

    // Helper to generate grid HTML
    const renderParamsGrid = (labels) => {
        const items = labels.map(stat => {
            const p = charParams.find(cp => cp.label === stat);
            const val = p ? p.value : 0;
            return `
                <div class="char-param-item">
                    <span class="param-label">${stat}</span>
                    <span class="param-value">${val}</span>
                </div>
            `;
        });
        return `<div class="char-params-grid">${items.join('')}</div>`;
    };

    // Determine default view mode based on global BattleState
    const isExploration = (typeof battleState !== 'undefined' && battleState.mode === 'exploration');
    const displayBattle = isExploration ? 'none' : 'block';
    const displayExploration = isExploration ? 'block' : 'none';
    const btnText = isExploration ? '戦闘ステータスへ' : '探索技能へ';
    const currentMode = isExploration ? 'exploration' : 'battle';

    const paramsHtml = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
             <h4 style="margin:0; color:#333; font-size:1em;">Parameters</h4>
             <button class="params-toggle-btn action-btn secondary"
                style="font-size:0.8em; padding:2px 8px; cursor:pointer;"
                data-mode="${currentMode}">
                ${btnText}
             </button>
        </div>
        <div class="params-container params-battle" style="display:${displayBattle};">
            ${renderParamsGrid(coreStats)}
        </div>
        <div class="params-container params-exploration" style="display:${displayExploration};">
            ${renderParamsGrid(explorationStats)}
        </div>
    `;

    // ... (rest of renderCharacterCard) ...

    /* Note: Ideally we shouldn't have to duplicate the logic, but since we are modifying lines far apart,
       we will handle the event listener replacement in a separate chunk within this same tool call or if needed separately.
       Wait, I can't modify multiple non-contiguous blocks in one 'replace_file_content'.
       Ill use this block for the HTML generation part first.
    */

    // --- States (Stack) ---
    let statesHtml = '';
    char.states.forEach(s => {
        if (['HP', 'MP', 'FP'].includes(s.name)) return;
        if (s.value === 0) return;
        const config = (typeof STATUS_CONFIG !== 'undefined') ? STATUS_CONFIG[s.name] : null;
        const colorStyle = config ? `color: ${config.color}; font-weight:bold;` : '';
        statesHtml += `<div class="detail-buff-item" style="${colorStyle}">${s.name}: ${s.value}</div>`;
    });
    if (!statesHtml) statesHtml = '<span style="color:#999; font-size:0.9em;">なし</span>';

    // --- Buffs (Flavor Text Handling Fix) ---
    let specialBuffsHtml = '';
    if (char.special_buffs && char.special_buffs.length > 0) {
        char.special_buffs.forEach((b) => {
            let descriptionText = b.description;
            let flavorText = b.flavor;

            // If description/flavor not present in instance, look up in BUFF_DATA
            if (!descriptionText || !flavorText) {
                let lookupName = b.name;
                if (lookupName.includes('_')) lookupName = lookupName.split('_')[0];

                if (typeof BUFF_DATA !== 'undefined' && typeof BUFF_DATA.get === 'function') {
                    const found = BUFF_DATA.get(b.name);
                    if (found) {
                        if (!descriptionText) descriptionText = found.description;
                        if (!flavorText) flavorText = found.flavor;
                    } else {
                        const foundBase = BUFF_DATA.get(lookupName);
                        if (foundBase) {
                            if (!descriptionText) descriptionText = foundBase.description;
                            if (!flavorText) flavorText = foundBase.flavor;
                        }
                    }
                }
            }

            if (!descriptionText) descriptionText = "説明なし";
            if (!flavorText) flavorText = "";

            let nameDisplay = b.name;
            if (nameDisplay && nameDisplay.includes('_')) {
                nameDisplay = nameDisplay.split('_')[0];
            }

            let durationVal = b.lasting;
            if (durationVal === undefined) durationVal = b.round;
            if (durationVal === undefined) durationVal = b.duration;

            let durationHtml = "";

            // 1. 持続ラウンド表示 (無限(-1)の場合は非表示)
            if (durationVal !== null && durationVal !== undefined && !isNaN(durationVal)) {
                if (durationVal > 0 && durationVal < 99) {
                    durationHtml += `<span class="buff-duration-badge" style="background:#666; color:#fff; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:8px; white-space: nowrap;">残り${durationVal}R</span>`;
                }
                // -1 (無限) の場合は何も追加しない
            }

            // 2. 残り回数表示 (count > 0 なら表示)
            const countVal = b.count;
            if (countVal !== undefined && countVal !== null && countVal > 0) {
                durationHtml += `<span class="buff-count-badge" style="background:#0dcaf0; color:#000; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:4px; white-space: nowrap; font-weight:bold;">残${countVal}回</span>`;
            }

            const delayVal = parseInt(b.delay, 10) || 0;
            if (delayVal > 0) {
                durationHtml += `<span class="buff-delay-badge" style="background:#d63384; color:#fff; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:4px; white-space: nowrap;">発動まで${delayVal}R</span>`;
            }

            specialBuffsHtml += `
                <details class="detail-buff-item" style="border: 1px solid #dee2e6; border-radius: 4px; margin-bottom: 5px; overflow: hidden; background: #fff;">
                    <summary style="background: #e9ecef; padding: 8px 10px; cursor: pointer; font-weight: bold; font-size: 0.95em; display: flex; align-items: center; justify-content: space-between; outline: none;">
                        <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 5px;">
                            <span>${nameDisplay}</span>
                            ${durationHtml}
                        </div>
                        <span style="font-size: 0.8em; color: #666;">▼</span>
                    </summary>
                    <div style="padding: 10px; background: #fff; border-top: 1px solid #dee2e6;">
                        <div class="buff-desc-row" style="font-weight: bold; color: #212529; font-size: 0.9em; margin-bottom: 5px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word;">${descriptionText}</div>
                        ${flavorText ? `<div class="buff-flavor-row" style="color: #6c757d; font-size: 0.85em; font-style: italic; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word; border-top: 1px dashed #eee; margin-top: 5px; padding-top: 5px;">${flavorText}</div>` : ''}
                    </div>
                </details>
            `;
        });
    }
    if (!specialBuffsHtml) specialBuffsHtml = '<span style="color:#999; font-size:0.9em;">なし</span>';

    // --- Skills ---
    let skillsHtml = '';
    const hiddenSkills = char.hidden_skills || [];
    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

    if (char.commands) {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        let skillItems = [];

        while ((match = regex.exec(char.commands)) !== null) {
            const skillId = match[1];
            const skillName = match[2];
            const isHidden = hiddenSkills.includes(skillId);

            if (!isGM && isHidden) continue;

            let toggleHtml = '';
            if (isGM) {
                const checked = !isHidden ? 'checked' : '';
                toggleHtml = `
                    <label class="skill-visibility-checkbox" onclick="event.stopPropagation();" style="font-size:0.8em; display:flex; align-items:center; cursor:pointer; margin-left:auto;">
                        <input type="checkbox" class="skill-public-toggle" data-skill-id="${skillId}" ${checked}>
                        <span style="margin-left:2px; font-weight:normal; color:#555;">公開</span>
                    </label>
                `;
            }

            let itemClass = 'char-skill-item skill-item';
            if (isGM && isHidden) itemClass += ' hidden';

            skillItems.push(`
                <div class="${itemClass}" data-skill-id="${skillId}" data-skill-name="${skillName}">
                    <div style="display:flex; flex-direction:column; overflow:hidden;">
                        <span style="font-size:0.75em; color:#888;">${skillId}</span>
                        <span style="font-weight:bold; font-size:0.9em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${skillName}</span>
                    </div>
                    ${toggleHtml}
                </div>
            `);
        }
        if (skillItems.length > 0) {
            skillsHtml = `<div class="char-skills-grid">${skillItems.join('')}</div>`;
        } else {
            skillsHtml = `<div style="color:#999; font-size:0.9em;">なし</div>`;
        }
    }

    // --- Inline CSS ---
    const inlineStyle = `
        <style>
            .char-detail-modal-content {
                width: 650px;
                max-width: 90vw;
                box-sizing: border-box;
                /* Prevent horizontal scroll/expansion */
                overflow-x: hidden;
            }
            .char-skills-grid {
                display: grid !important;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
            }
            .char-skill-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                border: 1px solid #eee;
                padding: 6px 10px;
                border-radius: 4px;
                background: #fff;
                cursor: pointer;
                transition: background 0.2s;
            }
            .char-skill-item:hover {
                background: #f0f8ff;
                border-color: #baddff;
            }
            .char-skill-item.hidden {
                background: #f9f9f9;
                opacity: 0.7;
                border: 1px dashed #ccc;
            }
            /* Parameter Grid Styles */
            .char-params-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 8px;
                width: 100%;
            }
            .char-param-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                border: 1px solid #ddd;
                padding: 6px 10px;
                border-radius: 4px;
                background: #f9f9f9;
                font-size: 0.9em;
            }
            .param-label {
                color: #555;
                font-weight: bold;
            }
            .param-value {
                font-weight: bold;
                font-size: 1.1em;
                color: #222;
            }

            /* Buff Item Styles */
            .detail-buff-item {
                border-bottom: 1px solid #f0f0f0;
                padding: 8px 5px;
            }
            .detail-buff-item:last-child {
                border-bottom: none;
            }
            /* Reset Details marker for custom arrow if needed, but default is fine for now */
            details > summary {
                list-style: none;
            }
            details > summary::-webkit-details-marker {
                display: none;
            }
            .detail-stat-box {
                flex: 1;
                text-align: center;
                padding: 10px;
                background: #fff;
                border: 1px solid #eee;
                border-radius: 4px;
                box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            }
            .detail-stat-label {
                display: block;
                font-size: 0.8em;
                color: #666;
                font-weight: bold;
                text-transform: uppercase;
                margin-bottom: 4px;
            }
            .detail-stat-val {
                font-size: 1.3em;
                font-weight: bold;
            }
        </style>
    `;

    return `
        ${inlineStyle}
        <div class="char-detail-modal-content" style="padding:10px; width:650px; max-width:90vw;">
            <div class="detail-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <h2 style="margin:0; font-size:1.5em; border-left:5px solid ${char.color}; padding-left:10px;">${char.name}</h2>
                <div style="display:flex; gap:15px; align-items:center;">
                    <button class="modal-settings-btn" id="modal-settings-trigger" style="background:none; border:none; font-size:1.5em; cursor:pointer; color:#555;" title="設定">⚙</button>
                    <button class="modal-close-btn" style="background:none; border:none; font-size:2em; cursor:pointer; color:#888; line-height:1;">&times;</button>
                </div>
            </div>

            <div id="char-image-preview" style="text-align:center; ${char.image ? '' : 'display: none;'} margin-bottom:15px;">
                <img id="char-preview-img" src="${char.image || ''}" style="max-height: 120px; border: 1px solid #ccc; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            </div>

            <div class="detail-stat-grid" style="display:flex; gap:10px; margin-bottom:20px;">
                <div class="detail-stat-box">
                    <span class="detail-stat-label">HP</span>
                    <span class="detail-stat-val" style="color:#28a745;">${char.hp} <span style="font-size:0.7em; color:#999;">/ ${char.maxHp}</span></span>
                </div>
                <div class="detail-stat-box">
                    <span class="detail-stat-label">MP</span>
                    <span class="detail-stat-val" style="color:#007bff;">${char.mp} <span style="font-size:0.7em; color:#999;">/ ${char.maxMp}</span></span>
                </div>
                <div class="detail-stat-box">
                    <span class="detail-stat-label">FP</span>
                    <span class="detail-stat-val" style="color:#ffc107;">${fpVal}</span>
                </div>
            </div>

            <div class="detail-section" style="margin-bottom:20px;">
                ${paramsHtml}
            </div>

            <div class="detail-section" style="margin-bottom:20px;">
                <h4 style="margin:0 0 8px 0; color:#333; font-size:1em; border-bottom:2px solid #eee; padding-bottom:4px;">状態異常</h4>
                <div class="detail-buff-list">${statesHtml}</div>
            </div>

            <div class="detail-section">
                <h4 style="margin:0 0 8px 0; color:#333; font-size:1em; border-bottom:2px solid #eee; padding-bottom:4px;">特殊効果 / バフ</h4>
                <div class="detail-buff-list" style="background:#fff;">${specialBuffsHtml}</div>
            </div>

            <div class="detail-section" style="margin-bottom:20px;">
                <details open style="border: 1px solid #eee; border-radius: 4px;">
                    <summary style="background: #f8f9fa; padding: 10px; cursor: pointer; font-weight: bold; font-size: 1.1em; outline: none; display: flex; justify-content: space-between; align-items: center; user-select: none;">
                        <span>Skills</span>
                        <span style="font-size: 0.8em; color: #666;">▼</span>
                    </summary>
                    <div style="padding: 10px; background: #fff;">
                        ${skillsHtml}
                    </div>
                </details>
            </div>
        </div>
    `;
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
    // Prevent horizontal scroll on body
    modalContent.style.overflowX = 'hidden';

    // Call the single unified renderer
    modalContent.innerHTML = renderCharacterCard(char);

    modalBackdrop.appendChild(modalContent);
    document.body.appendChild(modalBackdrop);
    modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) closeCharacterModal();
    });
    modalContent.querySelector('.modal-close-btn').addEventListener('click', closeCharacterModal);

    // --- Context Menu for Settings ---
    const settingsBtn = modalContent.querySelector('#modal-settings-trigger');
    settingsBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // Stop propagation
        createSettingsContextMenu(e.target, char);
    });

    // Input Debouncing for States
    let debounceTimer = null;
    let pendingChanges = {};
    modalContent.addEventListener('input', (e) => {
        const target = e.target;
        // Skip inputs managed by other handlers
        if (target.type === 'file' || target.classList.contains('settings-input')) return;

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

    // Skill Interactions
    const skillItems = modalContent.querySelectorAll('.skill-item');
    skillItems.forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.closest('.skill-visibility-checkbox') || e.target.classList.contains('skill-public-toggle')) return;
            const skillId = item.dataset.skillId;
            openSkillDetailModal(skillId, item.dataset.skillName);
        });
    });

    const skillToggles = modalContent.querySelectorAll('.skill-public-toggle');
    skillToggles.forEach(chk => {
        chk.addEventListener('change', (e) => {
            const skillId = chk.dataset.skillId;
            const isPublic = chk.checked;

            let currentHidden = char.hidden_skills || [];
            if (isPublic) {
                currentHidden = currentHidden.filter(id => id !== skillId);
            } else {
                if (!currentHidden.includes(skillId)) {
                    currentHidden.push(skillId);
                }
            }
            socket.emit('request_state_update', {
                room: currentRoomName,
                charId: char.id,
                changes: { hidden_skills: currentHidden }
            });
        });
    });

    // --- Parameter Toggle Listener ---
    const paramToggleBtn = modalContent.querySelector('.params-toggle-btn');
    if (paramToggleBtn) {
        paramToggleBtn.addEventListener('click', () => {
            const currentMode = paramToggleBtn.dataset.mode;
            const battleContainer = modalContent.querySelector('.params-battle');
            const explorationContainer = modalContent.querySelector('.params-exploration');

            if (currentMode === 'exploration') {
                // Switch TO Battle
                if (battleContainer) battleContainer.style.display = 'block';
                if (explorationContainer) explorationContainer.style.display = 'none';
                paramToggleBtn.textContent = '探索技能へ';
                paramToggleBtn.dataset.mode = 'battle';
            } else {
                // Switch TO Exploration
                if (battleContainer) battleContainer.style.display = 'none';
                if (explorationContainer) explorationContainer.style.display = 'block';
                paramToggleBtn.textContent = '戦闘ステータスへ';
                paramToggleBtn.dataset.mode = 'exploration';
            }
        });
    }
}

/**
 * 設定コンテキストメニューを作成・表示
 */
function createSettingsContextMenu(triggerEl, char) {
    // 既存のメニューがあれば削除
    const existing = document.getElementById('char-settings-context-menu');
    if (existing) existing.remove();

    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
    const ownerName = char.owner || '不明';

    // 譲渡先リスト
    let ownerOptions = '';
    if (typeof currentRoomUserList !== 'undefined') {
        currentRoomUserList.forEach(u => {
            ownerOptions += `<option value="${u.user_id}">${u.username}</option>`;
        });
    }

    const menuHtml = `
        <div id="char-settings-context-menu" style="position:absolute; z-index:10000; background:#fff; border:1px solid #ced4da; box-shadow:0 4px 15px rgba(0,0,0,0.15); border-radius:6px; padding:15px; width:280px; font-size:0.95em; color: #333;">
            <div style="font-weight:bold; border-bottom:2px solid #f8f9fa; padding-bottom:8px; margin-bottom:12px; color: #495057; font-size: 1.1em;">${char.name} 設定</div>

            <div style="margin-bottom:15px;">
                <label style="display:block; color:#6c757d; margin-bottom:4px; font-size: 0.85em; font-weight: bold;">所有権の譲渡</label>
                <div style="display:flex; gap:5px;">
                     <select id="ctx-transfer-select" class="settings-input" style="flex:1; padding:4px; border: 1px solid #ced4da; border-radius: 4px;">
                         <option value="">(選択)</option>
                         ${ownerOptions}
                     </select>
                     <button id="ctx-transfer-btn" style="padding:4px 10px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">実行</button>
                </div>
                <div style="font-size:0.8em; color:#adb5bd; margin-top:2px;">現在の所有者: ${ownerName}</div>
            </div>

            <div style="margin-bottom:15px;">
                <label style="display:block; color:#6c757d; margin-bottom:4px; font-size: 0.85em; font-weight: bold;">駒サイズ: <span id="ctx-scale-val">${char.tokenScale || 1.0}</span>倍</label>
                <input type="range" id="ctx-scale-slider" class="settings-input" min="0.5" max="2.0" step="0.1" value="${char.tokenScale || 1.0}" style="width:100%;">
            </div>

            <div style="margin-bottom:15px;">
                 <label style="display:block; color:#6c757d; margin-bottom:4px; font-size: 0.85em; font-weight: bold;">立ち絵</label>
                 <button id="ctx-image-btn" style="width:100%; padding: 8px; background: #0d6efd; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; transition: background 0.2s;">画像を変更</button>
            </div>

            <div style="margin-bottom:15px;">
                 <button id="ctx-return-btn" style="width:100%; background:#f8f9fa; color: #495057; border: 1px solid #ced4da; padding: 8px; border-radius: 4px; cursor: pointer; font-weight: bold;">未配置に戻す</button>
            </div>

            ${isGM ? `
            <div style="margin-bottom:15px; padding: 5px; background: #f8f9fa; border-radius: 4px;">
                <label style="display:flex; align-items:center; cursor: pointer;">
                    <input type="checkbox" id="ctx-gm-only" class="settings-input" ${char.gmOnly ? 'checked' : ''} style="margin-right: 8px;"> <span style="font-size: 0.9em; color: #495057;">GMのみ操作可能</span>
                </label>
            </div>
            ` : ''}

            <hr style="border:0; border-top:1px solid #e9ecef; margin:10px 0 15px 0;">
            <button id="ctx-delete-btn" style="width:100%; background:#dc3545; color:white; border:none; padding:10px; border-radius:4px; font-weight:bold; cursor: pointer; transition: background 0.2s;">削除</button>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', menuHtml);
    const menu = document.getElementById('char-settings-context-menu');

    // Positioning (Near the trigger button)
    const rect = triggerEl.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    menu.style.top = `${rect.bottom + scrollTop + 5}px`;
    menu.style.left = `${rect.left - 200}px`; // Shift left to keep in viewport usually

    // Event Listeners

    // Close on clicking outside
    const closeMenu = () => menu.remove();
    setTimeout(() => document.addEventListener('click', closeMenu, { once: true }), 0);
    menu.addEventListener('click', (e) => e.stopPropagation()); // Prevent closing when clicking inside

    // Transfer
    const transferBtn = menu.querySelector('#ctx-transfer-btn');
    transferBtn.addEventListener('click', () => {
        const select = menu.querySelector('#ctx-transfer-select');
        const newOwnerId = select.value;
        const newOwnerName = select.options[select.selectedIndex].text;
        if (!newOwnerId) return;
        if (confirm(`所有権を「${newOwnerName}」に譲渡しますか？`)) {
            socket.emit('request_transfer_character_ownership', {
                room: currentRoomName, character_id: char.id, new_owner_id: newOwnerId, new_owner_name: newOwnerName
            });
            closeMenu();
        }
    });

    // Scale
    const scaleSlider = menu.querySelector('#ctx-scale-slider');
    const scaleValDisplay = menu.querySelector('#ctx-scale-val');
    scaleSlider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        scaleValDisplay.textContent = val.toFixed(1);
        socket.emit('request_update_token_scale', {
            room: currentRoomName, charId: char.id, scale: val
        });
    });

    // Image
    const imgBtn = menu.querySelector('#ctx-image-btn');
    imgBtn.addEventListener('click', () => {
        openImagePicker((selectedImage) => {
            socket.emit('request_state_update', {
                room: currentRoomName, charId: char.id, statName: 'image', newValue: selectedImage.url
            });
            // Update modal preview immediately if possible
            const previewImg = document.getElementById('char-preview-img');
            const previewArea = document.getElementById('char-image-preview');
            if (previewImg) {
                previewImg.src = selectedImage.url;
                previewArea.style.display = 'block';
            }
            closeMenu();
        });
    });

    // Return
    const returnBtn = menu.querySelector('#ctx-return-btn');
    returnBtn.addEventListener('click', () => {
        if (confirm('未配置に戻しますか？')) {
            socket.emit('request_move_character', { room: currentRoomName, character_id: char.id, x: -1, y: -1 });
            closeGameModal('char-modal-backdrop'); // Helper or manually remove
            const modal = document.getElementById('char-modal-backdrop');
            if (modal) modal.remove();
            closeMenu();
        }
    });

    // Delete
    const delBtn = menu.querySelector('#ctx-delete-btn');
    delBtn.addEventListener('click', () => {
        if (confirm('完全に削除しますか？')) {
            socket.emit('request_delete_character', { room: currentRoomName, charId: char.id });
            const modal = document.getElementById('char-modal-backdrop');
            if (modal) modal.remove();
            closeMenu();
        }
    });

    // GM Only
    const gmToggle = menu.querySelector('#ctx-gm-only');
    if (gmToggle) {
        gmToggle.addEventListener('change', (e) => {
            socket.emit('request_state_update', {
                room: currentRoomName, charId: char.id, statName: 'gmOnly', newValue: e.target.checked
            });
        });
    }
}

// Helper to close modal by ID (if not exists in global scope, defined here just in case)
function closeGameModal(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}


function openSkillDetailModal(skillId, skillName) {
    // スキルデータを取得
    const skillData = (window.allSkillData && window.allSkillData[skillId]) ? window.allSkillData[skillId] : null;

    // 既存のスキル詳細モーダルがあれば削除
    const existing = document.getElementById('skill-detail-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'skill-detail-modal-backdrop';
    overlay.className = 'modal-backdrop';

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.style.maxWidth = '500px';
    content.style.padding = '20px';

    let bodyHtml = '';
    if (skillData) {
        bodyHtml = `
            <div style="margin-bottom: 10px;">
                <span style="font-size: 0.85em; color: #666; font-weight: bold;">[${skillId}]</span>
                <span class="skill-detail-category" style="float:right; font-size:0.8em; background:#eee; padding:2px 6px; border-radius:4px;">${skillData['分類'] || '---'}</span>
            </div>
            <div class="skill-detail-body">
                ${formatSkillDetailHTML(skillData)}
            </div>
        `;
    } else {
        bodyHtml = `<p>スキルデータが見つかりません: ${skillId}</p>`;
    }

    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #ddd; padding-bottom:10px; margin-bottom:15px;">
            <h3 style="margin:0;">${skillName || skillId}</h3>
            <button class="modal-close-btn" style="border:none; background:none; font-size:1.5em; cursor:pointer;">×</button>
        </div>
        ${bodyHtml}
    `;

    overlay.appendChild(content);
    document.body.appendChild(overlay);

    const closeFunc = () => overlay.remove();
    content.querySelector('.modal-close-btn').addEventListener('click', closeFunc);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeFunc();
    });
}

// 互換性のためのエイリアス
// 過去のコードが renderBeautifulCharacterCard を呼んでいても、統合版が動くようにする
function renderBeautifulCharacterCard(char) {
    return renderCharacterCard(char);
}
// V2も同様
function renderBeautifulCharacterCardV2(char) {
    return renderCharacterCard(char);
}

function openCharLoadModal() {
    closeCharacterModal();

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
}

function openPresetManagerModal() {
    const existing = document.getElementById('preset-manager-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'preset-manager-backdrop';
    overlay.className = 'modal-backdrop';

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.style.maxWidth = '500px';
    content.style.textAlign = 'left';
    content.style.padding = '25px';

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
            li.style.padding = '8px 12px';
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

// Global Alias for Character Detail Modal (Used by Battle/Exploration views)
window.showCharacterDetail = openCharacterModal;