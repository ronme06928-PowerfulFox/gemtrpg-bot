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

    const ORIGIN_NAMES = {
        1: "ヨキューク・ツォー",
        2: "アーク・ジェムリア",
        3: "ラティウム",
        4: "アヌッサ・ホロウ",
        5: "マホロバ",
        6: "ラグラゼシス(都市部)",
        7: "ラグラゼシス(非都市部)",
        8: "ギァン・バルフ",
        9: "綿津見",
        10: "シンシア",
        11: "リテラール",
        12: "オーセクト",
        13: "ヴァルヴァイレ"
    };

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
        ${(() => {
            const originParam = charParams.find(p => p.label === '出身');
            const bonusParam = charParams.find(p => p.label === 'ボーナス');
            let originText = "不明";
            let bonusText = "";

            if (originParam) {
                const originId = parseInt(originParam.value, 10);
                if (originId === 0) return ''; // 出身なしの場合は表示しない、または「出身なし」と表示するか？ここでは表示しないか、シンプルにする
                originText = ORIGIN_NAMES[originId] || "その他/不明";

                if ([1, 2, 12].includes(originId) && bonusParam) {
                    const bonusId = parseInt(bonusParam.value, 10);
                    if (bonusId > 0 && ORIGIN_NAMES[bonusId]) {
                        // ヨキューク、アーク・ジェムリア、オーセクトの場合はボーナス国を表示
                        bonusText = ` <span style="color:#666; font-weight:normal;">(ボーナス: ${ORIGIN_NAMES[bonusId]})</span>`;
                    }
                }
                return `
                <div style="margin-top: 8px; font-size: 0.9em; color: #555; background: #f9f9f9; padding: 4px 8px; border-radius: 4px; border: 1px solid #ddd; display: flex; align-items: center;">
                    <span style="font-weight: bold; margin-right: 6px; color: #333;">出身:</span>
                    <span style="font-weight: bold; color: #222;">${originText}</span>
                    ${bonusText}
                </div>`;
            }
            return '';
        })()}
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
    const summonDurationMode = String(char.summon_duration_mode || '').toLowerCase();
    const summonRemainingRounds = parseInt(char.remaining_summon_rounds, 10);
    if (
        char.is_summoned
        && summonDurationMode === 'duration_rounds'
        && Number.isFinite(summonRemainingRounds)
        && summonRemainingRounds > 0
    ) {
        specialBuffsHtml += `
            <details class="detail-buff-item" style="border: 1px solid #ffc078; border-radius: 4px; margin-bottom: 5px; overflow: hidden; background: #fff;">
                <summary style="background: #fff3bf; padding: 8px 10px; cursor: pointer; font-weight: bold; font-size: 0.95em; display: flex; align-items: center; justify-content: space-between; outline: none;">
                    <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 5px;">
                        <span>召喚継続</span>
                        <span class="buff-duration-badge" style="background:#666; color:#fff; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:8px; white-space: nowrap;">残り${summonRemainingRounds}R</span>
                    </div>
                    <span style="font-size: 0.8em; color: #666;">▼</span>
                </summary>
                <div style="padding: 10px; background: #fff; border-top: 1px solid #ffe8a1;">
                    <div class="buff-desc-row" style="font-weight: bold; color: #212529; font-size: 0.9em; margin-bottom: 5px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word;">この召喚体はラウンド終了時に残り継続ラウンドが減少し、0で消滅します。</div>
                </div>
            </details>
        `;
    }
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

    // --- Passives (SPassive) ---
    if (char.SPassive && Array.isArray(char.SPassive) && char.SPassive.length > 0) {
        char.SPassive.forEach(pid => {
            const pData = (window.allPassiveData && window.allPassiveData[pid]) ? window.allPassiveData[pid] : null;
            // データがなくてもIDだけは表示する
            const name = pData ? pData.name : pid;
            const desc = pData ? pData.description : "詳細情報なし";
            const flavor = pData ? pData.flavor : "";

            specialBuffsHtml += `
                <details class="detail-buff-item" style="border: 1px solid #e0cffc; border-radius: 4px; margin-bottom: 5px; overflow: hidden; background: #fff;">
                    <summary style="background: #f3e5f5; padding: 8px 10px; cursor: pointer; font-weight: bold; font-size: 0.95em; display: flex; align-items: center; justify-content: space-between; outline: none;">
                        <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 5px;">
                            <span style="color: #6a1b9a;">★ ${name}</span>
                            <span style="background:#6a1b9a; color:#fff; padding:1px 6px; border-radius:10px; font-size:0.7em; margin-left:8px;">パッシブ</span>
                        </div>
                        <span style="font-size: 0.8em; color: #666;">▼</span>
                    </summary>
                    <div style="padding: 10px; background: #fff; border-top: 1px solid #e0cffc;">
                        <div class="buff-desc-row" style="font-weight: bold; color: #212529; font-size: 0.9em; margin-bottom: 5px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word;">${desc}</div>
                        ${flavor ? `<div class="buff-flavor-row" style="color: #6c757d; font-size: 0.85em; font-style: italic; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word; border-top: 1px dashed #eee; margin-top: 5px; padding-top: 5px;">${flavor}</div>` : ''}
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

    const grantedSkillRows = Array.isArray(char.granted_skills) ? char.granted_skills : [];
    const grantedBySkillId = {};
    grantedSkillRows.forEach((row) => {
        if (!row || typeof row !== 'object') return;
        const sid = String(row.skill_id || '').trim();
        if (!sid) return;
        grantedBySkillId[sid] = row;
    });

    if (char.commands) {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        let skillItems = [];
        const escAttr = (value) => String(value ?? '').replace(/"/g, '&quot;');

        while ((match = regex.exec(char.commands)) !== null) {
            const skillId = match[1];
            const skillName = match[2];
            const isHidden = hiddenSkills.includes(skillId);
            const granted = grantedBySkillId[skillId] || null;
            const isGranted = !!granted;
            const grantMode = isGranted ? String(granted.mode || '').trim() : '';
            const remainingRounds = isGranted && granted.remaining_rounds != null ? parseInt(granted.remaining_rounds, 10) : NaN;
            const remainingUses = isGranted && granted.remaining_uses != null ? parseInt(granted.remaining_uses, 10) : NaN;

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
            if (isGranted) itemClass += ' granted';

            skillItems.push(`
                <div class="${itemClass}" data-skill-id="${escAttr(skillId)}" data-skill-name="${escAttr(skillName)}" data-is-granted="${isGranted ? '1' : '0'}" data-grant-mode="${escAttr(grantMode)}" data-grant-rounds="${Number.isFinite(remainingRounds) ? remainingRounds : ''}" data-grant-uses="${Number.isFinite(remainingUses) ? remainingUses : ''}">
                    <div style="display:flex; flex-direction:column; overflow:hidden;">
                        <span style="font-size:0.75em; color:#888;">${skillId}</span>
                        <span style="font-weight:bold; font-size:0.9em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${skillName}</span>
                    </div>
                    ${isGranted ? '<span style="background:#ffe08a; color:#5a4300; border:1px solid #f3c34a; border-radius:10px; font-size:0.72em; padding:1px 6px; margin-right:6px; white-space:nowrap;">付与</span>' : ''}
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
            .char-skill-item.granted {
                background: #fff8dc;
                border-color: #f1cf67;
            }
            .char-skill-item.granted:hover,
            .char-skill-item.granted.selected {
                background: #ffefb0;
                border-color: #dfb33f;
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
            skillItems.forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            const skillId = item.dataset.skillId;
            const isGranted = item.dataset.isGranted === '1';
            const grantRoundsRaw = parseInt(item.dataset.grantRounds, 10);
            const grantUsesRaw = parseInt(item.dataset.grantUses, 10);
            const granted = isGranted ? {
                mode: item.dataset.grantMode || '',
                remaining_rounds: Number.isFinite(grantRoundsRaw) ? grantRoundsRaw : null,
                remaining_uses: Number.isFinite(grantUsesRaw) ? grantUsesRaw : null,
            } : null;
            openSkillDetailModal(skillId, item.dataset.skillName, { granted });
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

function coerceBehaviorConditionValue(rawValue) {
    const text = String(rawValue ?? '').trim();
    if (!text) return '';
    if (/^-?\d+$/.test(text)) return parseInt(text, 10);
    if (/^-?\d+\.\d+$/.test(text)) return parseFloat(text);
    if (text.toLowerCase() === 'true') return true;
    if (text.toLowerCase() === 'false') return false;
    return text;
}

function normalizeBehaviorProfileForEditor(rawProfile) {
    const profile = (rawProfile && typeof rawProfile === 'object') ? rawProfile : {};
    const loopsRaw = (profile.loops && typeof profile.loops === 'object') ? profile.loops : {};
    const loops = {};

    Object.keys(loopsRaw).forEach((rawLoopId) => {
        const loopId = String(rawLoopId || '').trim();
        if (!loopId) return;
        const loopData = (loopsRaw[rawLoopId] && typeof loopsRaw[rawLoopId] === 'object') ? loopsRaw[rawLoopId] : {};

        const steps = Array.isArray(loopData.steps)
            ? loopData.steps.map((step) => {
                const stepObj = (step && typeof step === 'object') ? step : {};
                const actionsRaw = Array.isArray(stepObj.actions) ? stepObj.actions : [];
                const actions = actionsRaw.map((action) => {
                    const txt = String(action ?? '').trim();
                    return txt || null;
                });
                return { actions };
            })
            : [];

        const transitions = Array.isArray(loopData.transitions)
            ? loopData.transitions
                .map((tr) => {
                    const trObj = (tr && typeof tr === 'object') ? tr : {};
                    const toLoopId = String(trObj.to_loop_id || '').trim();
                    if (!toLoopId) return null;
                    const whenAll = Array.isArray(trObj.when_all)
                        ? trObj.when_all
                            .filter((cond) => cond && typeof cond === 'object')
                            .map((cond) => ({
                                source: String(cond.source || 'self').trim() || 'self',
                                param: String(cond.param || '').trim(),
                                operator: String(cond.operator || 'EQUALS').trim().toUpperCase() || 'EQUALS',
                                value: (cond.value === undefined) ? '' : cond.value
                            }))
                        : [];
                    return {
                        priority: Number.isFinite(Number(trObj.priority)) ? parseInt(trObj.priority, 10) : 0,
                        to_loop_id: toLoopId,
                        reset_step_index: trObj.reset_step_index !== false,
                        when_all: whenAll
                    };
                })
                .filter(Boolean)
                .sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0))
            : [];

        loops[loopId] = {
            repeat: loopData.repeat !== false,
            steps,
            transitions
        };
    });

    if (Object.keys(loops).length === 0) {
        loops.loop_1 = {
            repeat: true,
            steps: [{ actions: [null] }],
            transitions: []
        };
    }

    const loopIds = Object.keys(loops);
    let initialLoopId = String(profile.initial_loop_id || '').trim();
    if (!initialLoopId || !loops[initialLoopId]) initialLoopId = loopIds[0];

    return {
        enabled: !!profile.enabled,
        version: 1,
        initial_loop_id: initialLoopId,
        loops
    };
}

function getCharacterOwnedSkillsForBehaviorEditor(char) {
    const out = [];
    const seen = new Set();
    const add = (skillId, skillName, source) => {
        const id = String(skillId || '').trim();
        if (!id || seen.has(id)) return;
        const all = window.allSkillData || {};
        const dataName = all[id] && all[id].name ? String(all[id].name) : '';
        const name = String(skillName || dataName || id).trim();
        out.push({ id, name, source: source || 'unknown' });
        seen.add(id);
    };

    if (char && typeof char.commands === 'string') {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        while ((match = regex.exec(char.commands)) !== null) {
            add(match[1], match[2], 'commands');
        }
    }

    const granted = Array.isArray(char?.granted_skills) ? char.granted_skills : [];
    granted.forEach((row) => {
        if (!row || typeof row !== 'object') return;
        add(row.skill_id, '', 'granted');
    });

    return out;
}

function formatBehaviorConditionSpec(whenAll) {
    if (!Array.isArray(whenAll) || whenAll.length === 0) return '';
    return whenAll.map((cond) => {
        const src = String(cond?.source || 'self').trim();
        const param = String(cond?.param || '').trim();
        const op = String(cond?.operator || 'EQUALS').trim().toUpperCase();
        const value = String(cond?.value ?? '').trim();
        return `${src}:${param}:${op}:${value}`;
    }).join(' && ');
}

function parseBehaviorConditionSpec(specText) {
    const raw = String(specText || '').trim();
    if (!raw) return [];
    return raw
        .split('&&')
        .map((chunk) => String(chunk || '').trim())
        .filter(Boolean)
        .map((chunk) => {
            const parts = chunk.split(':').map((v) => String(v || '').trim());
            const source = parts[0] || 'self';
            const param = parts[1] || '';
            const operator = (parts[2] || 'EQUALS').toUpperCase();
            const value = coerceBehaviorConditionValue(parts.slice(3).join(':'));
            return { source, param, operator, value };
        });
}

const BEHAVIOR_CONDITION_SOURCES = [
    { value: 'self', label: '自身' },
    { value: 'battle', label: '戦闘全体' }
];

const BEHAVIOR_CONDITION_OPERATORS = [
    { value: 'EQUALS', label: '一致 (=)' },
    { value: 'GTE', label: '以上 (>=)' },
    { value: 'LTE', label: '以下 (<=)' },
    { value: 'GT', label: 'より大きい (>)' },
    { value: 'LT', label: 'より小さい (<)' },
    { value: 'CONTAINS', label: '含む' }
];

const BEHAVIOR_CONDITION_PARAM_PRESETS = {
    self: [
        { value: 'HP', label: 'HP' },
        { value: 'MP', label: 'MP' },
        { value: 'FP', label: 'FP' },
        { value: '出血', label: '出血' },
        { value: '破裂', label: '破裂' },
        { value: '亀裂', label: '亀裂' },
        { value: '戦慄', label: '戦慄' },
        { value: '荊棘', label: '荊棘' }
    ],
    battle: [
        { value: 'round', label: 'ラウンド' },
        { value: 'phase', label: 'フェーズ' }
    ]
};

function normalizeBehaviorConditionRow(raw) {
    const cond = (raw && typeof raw === 'object') ? raw : {};
    const source = String(cond.source || 'self').trim().toLowerCase();
    const safeSource = (source === 'battle') ? 'battle' : 'self';
    const operatorRaw = String(cond.operator || 'EQUALS').trim().toUpperCase();
    const safeOperator = BEHAVIOR_CONDITION_OPERATORS.some((op) => op.value === operatorRaw) ? operatorRaw : 'EQUALS';
    return {
        source: safeSource,
        param: String(cond.param || '').trim(),
        operator: safeOperator,
        value: (cond.value === undefined) ? '' : cond.value
    };
}

function getBehaviorConditionParamPresets(source) {
    const key = String(source || 'self').trim().toLowerCase();
    return Array.isArray(BEHAVIOR_CONDITION_PARAM_PRESETS[key])
        ? BEHAVIOR_CONDITION_PARAM_PRESETS[key]
        : BEHAVIOR_CONDITION_PARAM_PRESETS.self;
}

function openBehaviorFlowEditorModal(char) {
    if (!char || !char.id) return;
    const existing = document.getElementById('behavior-flow-editor-backdrop');
    if (existing) existing.remove();

    const currentFlags = (char.flags && typeof char.flags === 'object') ? char.flags : {};
    const draft = normalizeBehaviorProfileForEditor(currentFlags.behavior_profile);
    const ownedSkills = getCharacterOwnedSkillsForBehaviorEditor(char);
    let selectedLoopId = String(draft.initial_loop_id || Object.keys(draft.loops)[0] || '');
    const nodeLayout = {};
    let connectFromLoopId = null;
    let isDirty = false;

    function loopIds() {
        return Object.keys(draft.loops || {});
    }

    function buildOwnedSkillOptions(selectedSkillId) {
        const options = [{ id: '', name: '(未指定)' }, ...ownedSkills];
        const selected = String(selectedSkillId || '').trim();
        if (selected && !options.some((row) => row.id === selected)) {
            options.push({ id: selected, name: `${selected} (所持外)` });
        }
        return options;
    }
    function ensureSelection() {
        const ids = loopIds();
        if (!ids.length) {
            draft.loops.loop_1 = { repeat: true, steps: [{ actions: [null] }], transitions: [] };
            selectedLoopId = 'loop_1';
            draft.initial_loop_id = 'loop_1';
            return;
        }
        if (!draft.loops[selectedLoopId]) selectedLoopId = ids[0];
        if (!draft.loops[draft.initial_loop_id]) draft.initial_loop_id = ids[0];
    }
    function uniqueLoopId(base) {
        const seed = String(base || 'loop').trim() || 'loop';
        const ids = new Set(loopIds());
        if (!ids.has(seed)) return seed;
        let i = 1;
        while (ids.has(`${seed}_${i}`)) i += 1;
        return `${seed}_${i}`;
    }

    function markDirty() {
        isDirty = true;
        const indicator = content.querySelector('#behavior-dirty-indicator');
        if (indicator) indicator.textContent = '保存状態: 未保存の変更あり';
    }

    function clearDirty() {
        isDirty = false;
        const indicator = content.querySelector('#behavior-dirty-indicator');
        if (indicator) indicator.textContent = '保存状態: 保存済み';
    }

    const overlay = document.createElement('div');
    overlay.id = 'behavior-flow-editor-backdrop';
    overlay.className = 'modal-backdrop';

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.style.maxWidth = '1280px';
    content.style.width = '98vw';
    content.style.maxHeight = '94vh';
    content.style.height = '94vh';
    content.style.overflow = 'auto';
    content.style.padding = '16px';
    content.style.border = '1px solid #cfe1f1';
    content.style.background = '#f7fbff';
    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <h3 style="margin:0; color:#1e4766;">行動チャート編集（フローチャート）</h3>
            <div style="display:flex; align-items:center; gap:8px;">
                <span id="behavior-dirty-indicator" style="font-size:0.8em; color:#5a758b;">保存状態: 保存済み</span>
                <button id="behavior-flow-close-x" style="border:none; background:#dbe9f5; color:#1e4766; padding:6px 10px; border-radius:6px; cursor:pointer;">閉じる</button>
            </div>
        </div>
        <div style="font-size:0.9em; color:#35556d; margin-bottom:10px;">${char.name} の行動チャートを視覚的に編集します（内部保存はJSON）。</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:10px;">
            <label style="display:flex; align-items:center; gap:6px; background:#fff; border:1px solid #cfe1f1; padding:6px 10px; border-radius:6px;">
                <input type="checkbox" id="behavior-enabled">
                <span>有効化</span>
            </label>
            <label style="display:flex; align-items:center; gap:6px; background:#fff; border:1px solid #cfe1f1; padding:6px 10px; border-radius:6px;">
                <span>初期ループ</span>
                <select id="behavior-initial-loop" style="padding:4px;"></select>
            </label>
            <div style="margin-left:auto; display:flex; gap:6px;">
                <input id="behavior-new-loop-id" placeholder="新規ループ名" style="padding:6px; min-width:180px;">
                <button id="behavior-add-loop-btn" style="padding:6px 10px; border:none; background:#2f7fbf; color:#fff; border-radius:6px; cursor:pointer;">追加</button>
                <button id="behavior-reset-profile-btn" style="padding:6px 10px; border:none; background:#c23b3b; color:#fff; border-radius:6px; cursor:pointer;">チャート初期化</button>
            </div>
        </div>
        <details style="margin-bottom:10px; background:#fff; border:1px solid #cfe1f1; border-radius:8px; padding:8px;" open>
            <summary style="cursor:pointer; font-weight:bold; color:#2a516c;">仕様ガイド（条件分岐・スキル使用）</summary>
            <div style="font-size:0.83em; color:#37596f; margin-top:6px; line-height:1.55;">
                <div>・<strong>手順</strong>: 1ラウンドごとに現在の手順を参照して行動します（ラウンド終了時に次の手順へ進行）。</div>
                <div>・<strong>手順内スキル</strong>: スロット数より多い場合はランダム抽選、少ない場合は最後のスキルを繰り返します。</div>
                <div>・<strong>条件遷移</strong>: 優先度が高い順に判定し、最初に成立した遷移だけ適用します。</div>
                <div>・<strong>判定元</strong>: 自身（HP/MP/状態値）または戦闘全体（ラウンド/フェーズなど）。</div>
                <div>・<strong>未保存確認</strong>: 変更後に閉じると確認ダイアログが表示されます。</div>
            </div>
        </details>
        <div style="display:grid; grid-template-columns: 1.15fr 1fr; gap:10px;">
            <div style="background:#fff; border:1px solid #cfe1f1; border-radius:8px; padding:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <div style="font-weight:bold; color:#1e4766;">フローチャート表示</div>
                    <div style="display:flex; gap:6px;">
                        <button id="behavior-connect-start-btn" style="padding:4px 8px; border:none; background:#2f7fbf; color:#fff; border-radius:5px; cursor:pointer; font-size:0.82em;">接続開始</button>
                        <button id="behavior-connect-cancel-btn" style="padding:4px 8px; border:1px solid #b9cddd; background:#fff; color:#2f4858; border-radius:5px; cursor:pointer; font-size:0.82em;">接続解除</button>
                    </div>
                </div>
                <div id="behavior-flow-connect-hint" style="font-size:0.8em; color:#5f7a8f; margin-bottom:5px;">ノードをドラッグで移動。接続開始後に接続先ノードをクリック。</div>
                <div id="behavior-flow-preview"></div>
            </div>
            <div style="background:#fff; border:1px solid #cfe1f1; border-radius:8px; padding:8px;">
                <div style="font-weight:bold; color:#1e4766; margin-bottom:6px;">編集</div>
                <div id="behavior-loop-tabs" style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px;"></div>
                <div id="behavior-loop-editor"></div>
            </div>
        </div>
        <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:12px;">
            <button id="behavior-cancel-btn" style="padding:8px 12px; background:#fff; border:1px solid #b9cddd; border-radius:6px; cursor:pointer;">キャンセル</button>
            <button id="behavior-save-btn" style="padding:8px 12px; background:#2f7fbf; border:none; color:#fff; border-radius:6px; cursor:pointer;">保存</button>
        </div>
    `;
    overlay.appendChild(content);
    document.body.appendChild(overlay);

    const enabledEl = content.querySelector('#behavior-enabled');
    const initialEl = content.querySelector('#behavior-initial-loop');
    const addLoopBtn = content.querySelector('#behavior-add-loop-btn');
    const resetProfileBtn = content.querySelector('#behavior-reset-profile-btn');
    const newLoopInput = content.querySelector('#behavior-new-loop-id');
    const tabsEl = content.querySelector('#behavior-loop-tabs');
    const previewEl = content.querySelector('#behavior-flow-preview');
    const connectStartBtn = content.querySelector('#behavior-connect-start-btn');
    const connectCancelBtn = content.querySelector('#behavior-connect-cancel-btn');
    const connectHintEl = content.querySelector('#behavior-flow-connect-hint');
    const editorEl = content.querySelector('#behavior-loop-editor');

    clearDirty();
    const closeModal = (force = false) => {
        if (!force && isDirty) {
            const ok = confirm('未保存の変更があります。保存せずに閉じますか？');
            if (!ok) return;
        }
        overlay.remove();
    };
    content.querySelector('#behavior-flow-close-x')?.addEventListener('click', () => closeModal());
    content.querySelector('#behavior-cancel-btn')?.addEventListener('click', () => closeModal());
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });

    function renderInitialLoopOptions() {
        initialEl.innerHTML = '';
        loopIds().forEach((id) => {
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = id;
            if (id === draft.initial_loop_id) opt.selected = true;
            initialEl.appendChild(opt);
        });
    }

    function renderLoopTabs() {
        tabsEl.innerHTML = '';
        loopIds().forEach((id) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = id;
            btn.style.padding = '5px 8px';
            btn.style.border = '1px solid #8fb5d2';
            btn.style.borderRadius = '999px';
            btn.style.cursor = 'pointer';
            btn.style.background = (id === selectedLoopId) ? '#2f7fbf' : '#eef6ff';
            btn.style.color = (id === selectedLoopId) ? '#fff' : '#234c67';
            btn.addEventListener('click', () => {
                selectedLoopId = id;
                renderAll();
            });
            tabsEl.appendChild(btn);
        });
    }

    function ensureNodeLayout() {
        const ids = loopIds();
        const valid = new Set(ids);
        Object.keys(nodeLayout).forEach((id) => {
            if (!valid.has(id)) delete nodeLayout[id];
        });
        ids.forEach((id, idx) => {
            if (!nodeLayout[id]) {
                const col = idx % 2;
                const row = Math.floor(idx / 2);
                nodeLayout[id] = { x: 30 + (col * 210), y: 30 + (row * 130) };
            }
        });
    }

    function renderPreview() {
        previewEl.innerHTML = '';
        const ids = loopIds();
        if (!ids.length) {
            previewEl.innerHTML = '<div style="color:#789; font-size:0.9em;">ループがありません。</div>';
            return;
        }
        ensureNodeLayout();
        const boardW = Math.max(520, Math.min(860, (previewEl?.clientWidth || 640) - 12));
        const boardH = Math.max(300, (Math.ceil(ids.length / 2) * 130) + 90);

        const board = document.createElement('div');
        board.style.position = 'relative';
        board.style.width = `${boardW}px`;
        board.style.height = `${boardH}px`;
        board.style.border = '1px solid #d7e8f6';
        board.style.borderRadius = '8px';
        board.style.background = 'linear-gradient(180deg, #fbfdff 0%, #f3f8fd 100%)';
        board.style.overflow = 'hidden';

        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', String(boardW));
        svg.setAttribute('height', String(boardH));
        svg.style.position = 'absolute';
        svg.style.left = '0';
        svg.style.top = '0';
        svg.style.pointerEvents = 'none';

        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        marker.setAttribute('id', 'behavior-flow-arrow');
        marker.setAttribute('markerWidth', '8');
        marker.setAttribute('markerHeight', '8');
        marker.setAttribute('refX', '7');
        marker.setAttribute('refY', '4');
        marker.setAttribute('orient', 'auto');
        const arrowPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arrowPath.setAttribute('d', 'M0,0 L8,4 L0,8 z');
        arrowPath.setAttribute('fill', '#5e88a6');
        marker.appendChild(arrowPath);
        defs.appendChild(marker);
        svg.appendChild(defs);

        const nodeW = 170;
        const nodeH = 78;
        ids.forEach((fromId) => {
            const from = nodeLayout[fromId];
            const fromLoop = draft.loops[fromId] || {};
            const transitions = Array.isArray(fromLoop.transitions) ? fromLoop.transitions : [];
            transitions.forEach((tr) => {
                const toId = String(tr.to_loop_id || '').trim();
                if (!toId || !nodeLayout[toId]) return;
                const to = nodeLayout[toId];
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', String(from.x + nodeW));
                line.setAttribute('y1', String(from.y + (nodeH / 2)));
                line.setAttribute('x2', String(to.x));
                line.setAttribute('y2', String(to.y + (nodeH / 2)));
                line.setAttribute('stroke', '#5e88a6');
                line.setAttribute('stroke-width', '1.8');
                line.setAttribute('marker-end', 'url(#behavior-flow-arrow)');
                svg.appendChild(line);
            });
        });
        board.appendChild(svg);

        ids.forEach((id) => {
            const loop = draft.loops[id] || { repeat: true, steps: [], transitions: [] };
            const pos = nodeLayout[id];
            const node = document.createElement('div');
            node.style.position = 'absolute';
            node.style.left = `${pos.x}px`;
            node.style.top = `${pos.y}px`;
            node.style.width = `${nodeW}px`;
            node.style.minHeight = `${nodeH}px`;
            node.style.borderRadius = '8px';
            node.style.border = (id === selectedLoopId) ? '2px solid #2f7fbf' : '1px solid #c6dbeb';
            node.style.background = (id === selectedLoopId) ? '#f1f8ff' : '#ffffff';
            node.style.padding = '6px';
            node.style.cursor = 'move';
            node.style.boxShadow = '0 2px 6px rgba(0,0,0,0.08)';
            node.dataset.loopId = id;

            const actionsCount = (Array.isArray(loop.steps) ? loop.steps.length : 0);
            const trCount = (Array.isArray(loop.transitions) ? loop.transitions.length : 0);
            const initialTag = (id === draft.initial_loop_id) ? '初期' : '';
            const connectTag = (connectFromLoopId === id) ? '接続元' : '';
            node.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <strong style="font-size:0.84em; color:#214a67;">${id}</strong>
                    <button data-connect-from="${id}" style="padding:1px 5px; border:none; background:#2f7fbf; color:#fff; border-radius:4px; cursor:pointer; font-size:0.75em;">→</button>
                </div>
                <div style="font-size:0.75em; color:#55748c; margin-bottom:3px;">手順:${actionsCount} / 遷移:${trCount}</div>
                <div style="font-size:0.73em; color:#6b879b;">${loop.repeat ? 'ループ' : '停止'} ${initialTag ? `/ ${initialTag}` : ''} ${connectTag ? `/ ${connectTag}` : ''}</div>
            `;

            let dragStartX = 0;
            let dragStartY = 0;
            let startNodeX = 0;
            let startNodeY = 0;
            const onMouseMove = (ev) => {
                const dx = ev.clientX - dragStartX;
                const dy = ev.clientY - dragStartY;
                const nx = Math.max(5, Math.min(boardW - nodeW - 5, startNodeX + dx));
                const ny = Math.max(5, Math.min(boardH - nodeH - 5, startNodeY + dy));
                nodeLayout[id].x = nx;
                nodeLayout[id].y = ny;
                renderPreview();
            };
            const onMouseUp = () => {
                window.removeEventListener('mousemove', onMouseMove);
                window.removeEventListener('mouseup', onMouseUp);
            };
            node.addEventListener('mousedown', (ev) => {
                if (ev.target && ev.target.closest('[data-connect-from]')) return;
                dragStartX = ev.clientX;
                dragStartY = ev.clientY;
                startNodeX = nodeLayout[id].x;
                startNodeY = nodeLayout[id].y;
                window.addEventListener('mousemove', onMouseMove);
                window.addEventListener('mouseup', onMouseUp);
            });

            node.addEventListener('click', (ev) => {
                if (ev.target && ev.target.closest('[data-connect-from]')) return;
                if (connectFromLoopId && connectFromLoopId !== id) {
                    const srcLoop = draft.loops[connectFromLoopId];
                    if (srcLoop && Array.isArray(srcLoop.transitions)) {
                        srcLoop.transitions.push({
                            priority: 10,
                            to_loop_id: id,
                            reset_step_index: true,
                            when_all: []
                        });
                        markDirty();
                    }
                    connectFromLoopId = null;
                    selectedLoopId = id;
                    renderAll();
                    return;
                }
                if (connectFromLoopId === id) {
                    connectFromLoopId = null;
                    renderPreview();
                    if (connectHintEl) connectHintEl.textContent = 'ノードをドラッグで移動。接続開始後に接続先ノードをクリック。';
                    return;
                }
                selectedLoopId = id;
                renderAll();
            });

            node.querySelector('[data-connect-from]')?.addEventListener('click', (ev) => {
                ev.stopPropagation();
                connectFromLoopId = id;
                if (connectHintEl) connectHintEl.textContent = `接続元: ${id}。接続先ノードをクリックしてください。`;
                renderPreview();
            });

            board.appendChild(node);
        });

        previewEl.appendChild(board);
    }

    function renderLoopEditor() {
        const loop = draft.loops[selectedLoopId];
        if (!loop) {
            editorEl.innerHTML = '<div style="color:#789;">編集対象ループがありません。</div>';
            return;
        }
        const steps = Array.isArray(loop.steps) ? loop.steps : [];
        const transitions = Array.isArray(loop.transitions) ? loop.transitions : [];
        const toLoopOptions = loopIds().map((id) => `<option value="${id}">${id}</option>`).join('');

        editorEl.innerHTML = `
            <div style="display:grid; grid-template-columns: 1fr auto auto; gap:6px; align-items:end; margin-bottom:8px;">
                <label style="font-size:0.85em; color:#2f566f;">ループID
                    <input id="behavior-loop-id" value="${selectedLoopId}" style="width:100%; padding:5px; margin-top:2px;">
                </label>
                <label style="display:flex; align-items:center; gap:5px; font-size:0.84em; border:1px solid #d5e6f4; border-radius:6px; padding:6px 8px;">
                    <input type="checkbox" id="behavior-loop-repeat" ${loop.repeat ? 'checked' : ''}> ループする
                </label>
                <button id="behavior-loop-delete-btn" style="padding:6px 8px; border:none; background:#c23b3b; color:#fff; border-radius:6px; cursor:pointer;">削除</button>
            </div>
            <div style="border:1px solid #dbeaf6; border-radius:7px; padding:8px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                    <div style="font-weight:bold; color:#2f566f; font-size:0.88em;">手順</div>
                    <button id="behavior-step-add-btn" style="padding:4px 8px; border:none; background:#2f7fbf; color:#fff; border-radius:5px; cursor:pointer;">追加</button>
                </div>
                <div style="font-size:0.77em; color:#5b7890; margin-bottom:5px;">※所持スキル一覧から選択します（未指定も可）</div>
                <div id="behavior-step-list"></div>
            </div>
            <div style="border:1px solid #dbeaf6; border-radius:7px; padding:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                    <div style="font-weight:bold; color:#2f566f; font-size:0.88em;">条件遷移</div>
                    <button id="behavior-tr-add-btn" style="padding:4px 8px; border:none; background:#2f7fbf; color:#fff; border-radius:5px; cursor:pointer;">追加</button>
                </div>
                <div style="font-size:0.77em; color:#5b7890; margin-bottom:5px;">各条件は「判定元・項目・比較・値」を行単位で追加します。</div>
                <div id="behavior-tr-list"></div>
            </div>
        `;

        const stepListEl = editorEl.querySelector('#behavior-step-list');
        if (!steps.length) {
            stepListEl.innerHTML = '<div style="font-size:0.84em; color:#7b94a6;">stepなし</div>';
        } else {
            steps.forEach((step, idx) => {
                const row = document.createElement('div');
                row.style.display = 'grid';
                row.style.gridTemplateColumns = '42px 1fr auto';
                row.style.gap = '6px';
                row.style.marginBottom = '6px';
                row.innerHTML = `<div style="font-size:0.82em; color:#3f637b; align-self:start; padding-top:4px;">S${idx + 1}</div>`;

                const actionsWrap = document.createElement('div');
                actionsWrap.style.display = 'grid';
                actionsWrap.style.gap = '4px';
                const actionItems = (Array.isArray(step.actions) && step.actions.length) ? step.actions : [null];
                actionItems.forEach((actionSkillId, actionIdx) => {
                    const actionRow = document.createElement('div');
                    actionRow.style.display = 'grid';
                    actionRow.style.gridTemplateColumns = '1fr auto';
                    actionRow.style.gap = '4px';

                    const select = document.createElement('select');
                    select.dataset.stepAction = `${idx}:${actionIdx}`;
                    select.style.width = '100%';
                    select.style.padding = '4px';
                    const options = buildOwnedSkillOptions(actionSkillId);
                    options.forEach((optData) => {
                        const opt = document.createElement('option');
                        opt.value = optData.id;
                        opt.textContent = optData.id ? `${optData.id} / ${optData.name}` : optData.name;
                        if (String(actionSkillId || '') === optData.id) opt.selected = true;
                        select.appendChild(opt);
                    });

                    const delActionBtn = document.createElement('button');
                    delActionBtn.type = 'button';
                    delActionBtn.dataset.stepActionDel = `${idx}:${actionIdx}`;
                    delActionBtn.textContent = 'x';
                    delActionBtn.style.padding = '3px 6px';
                    delActionBtn.style.border = 'none';
                    delActionBtn.style.background = '#c23b3b';
                    delActionBtn.style.color = '#fff';
                    delActionBtn.style.borderRadius = '4px';
                    delActionBtn.style.cursor = 'pointer';
                    delActionBtn.title = 'このスキル指定を削除';

                    actionRow.appendChild(select);
                    actionRow.appendChild(delActionBtn);
                    actionsWrap.appendChild(actionRow);
                });
                if (!ownedSkills.length) {
                    const msg = document.createElement('div');
                    msg.style.fontSize = '0.76em';
                    msg.style.color = '#a35c33';
                    msg.textContent = '所持スキルを取得できません。char.commands を確認してください。';
                    actionsWrap.appendChild(msg);
                }

                const actionAddBtn = document.createElement('button');
                actionAddBtn.type = 'button';
                actionAddBtn.dataset.stepActionAdd = `${idx}`;
                actionAddBtn.textContent = 'スキル指定追加';
                actionAddBtn.style.padding = '3px 8px';
                actionAddBtn.style.border = 'none';
                actionAddBtn.style.background = '#5f9ec9';
                actionAddBtn.style.color = '#fff';
                actionAddBtn.style.borderRadius = '4px';
                actionAddBtn.style.cursor = 'pointer';
                actionAddBtn.style.width = 'fit-content';
                actionsWrap.appendChild(actionAddBtn);

                row.appendChild(actionsWrap);

                const delStepBtn = document.createElement('button');
                delStepBtn.type = 'button';
                delStepBtn.dataset.stepDel = String(idx);
                delStepBtn.textContent = '削除';
                delStepBtn.style.padding = '4px 8px';
                delStepBtn.style.border = 'none';
                delStepBtn.style.background = '#c23b3b';
                delStepBtn.style.color = '#fff';
                delStepBtn.style.borderRadius = '5px';
                delStepBtn.style.cursor = 'pointer';
                row.appendChild(delStepBtn);
                stepListEl.appendChild(row);
            });
        }

        const trListEl = editorEl.querySelector('#behavior-tr-list');
        if (!transitions.length) {
            trListEl.innerHTML = '<div style="font-size:0.84em; color:#7b94a6;">遷移なし</div>';
        } else {
            const buildSourceOptions = (selectedValue) => BEHAVIOR_CONDITION_SOURCES.map((row) => {
                const selected = (row.value === selectedValue) ? 'selected' : '';
                return `<option value="${row.value}" ${selected}>${row.label}</option>`;
            }).join('');
            const buildOperatorOptions = (selectedValue) => BEHAVIOR_CONDITION_OPERATORS.map((row) => {
                const selected = (row.value === selectedValue) ? 'selected' : '';
                return `<option value="${row.value}" ${selected}>${row.label}</option>`;
            }).join('');
            const buildParamOptions = (source, selectedParam) => {
                const presets = getBehaviorConditionParamPresets(source);
                const selected = String(selectedParam || '').trim();
                const hasSelectedInPreset = presets.some((row) => row.value === selected);
                let html = presets.map((row) => {
                    const selectedTag = (row.value === selected) ? 'selected' : '';
                    return `<option value="${row.value}" ${selectedTag}>${row.label}</option>`;
                }).join('');
                html += `<option value="__custom__" ${hasSelectedInPreset ? '' : 'selected'}>自由入力</option>`;
                return html;
            };
            transitions.forEach((tr, tIdx) => {
                const whenAll = Array.isArray(tr.when_all) ? tr.when_all.map(normalizeBehaviorConditionRow) : [];
                const condRows = whenAll.length
                    ? whenAll.map((cond, cIdx) => {
                        const param = String(cond.param || '').trim();
                        const presets = getBehaviorConditionParamPresets(cond.source);
                        const hasPreset = presets.some((row) => row.value === param);
                        return `
                            <div style="display:grid; grid-template-columns: 120px 150px 170px 140px 1fr auto; gap:6px; align-items:end; margin-bottom:6px; padding:6px; border:1px solid #e2edf7; border-radius:6px; background:#fafdff;">
                                <label style="font-size:0.8em;">判定元
                                    <select data-tr-cond-source="${tIdx}:${cIdx}" style="width:100%;">
                                        ${buildSourceOptions(cond.source)}
                                    </select>
                                </label>
                                <label style="font-size:0.8em;">項目
                                    <select data-tr-cond-param-select="${tIdx}:${cIdx}" style="width:100%;">
                                        ${buildParamOptions(cond.source, cond.param)}
                                    </select>
                                </label>
                                <label style="font-size:0.8em; ${hasPreset ? 'display:none;' : ''}">項目名
                                    <input data-tr-cond-param-custom="${tIdx}:${cIdx}" value="${hasPreset ? '' : param}" placeholder="例: 破裂" style="width:100%;">
                                </label>
                                <label style="font-size:0.8em;">比較
                                    <select data-tr-cond-op="${tIdx}:${cIdx}" style="width:100%;">
                                        ${buildOperatorOptions(cond.operator)}
                                    </select>
                                </label>
                                <label style="font-size:0.8em;">値
                                    <input data-tr-cond-value="${tIdx}:${cIdx}" value="${String(cond.value ?? '')}" placeholder="例: 50" style="width:100%;">
                                </label>
                                <button data-tr-cond-del="${tIdx}:${cIdx}" style="padding:4px 7px; border:none; background:#c23b3b; color:#fff; border-radius:5px; cursor:pointer;">削除</button>
                            </div>
                        `;
                    }).join('')
                    : '<div style="font-size:0.8em; color:#7b94a6; margin-bottom:6px;">条件がありません（常に遷移）。</div>';
                const box = document.createElement('div');
                box.style.border = '1px solid #d5e6f4';
                box.style.borderRadius = '6px';
                box.style.padding = '6px';
                box.style.marginBottom = '6px';
                box.innerHTML = `
                    <div style="display:grid; grid-template-columns: 78px 1fr auto auto; gap:6px; align-items:end; margin-bottom:5px;">
                        <label style="font-size:0.8em;">優先度<input data-tr-priority="${tIdx}" type="number" value="${Number(tr.priority || 0)}" style="width:100%;"></label>
                        <label style="font-size:0.8em;">遷移先ループ<select data-tr-to="${tIdx}" style="width:100%;">${toLoopOptions}</select></label>
                        <label style="display:flex; align-items:center; gap:4px; font-size:0.8em;"><input data-tr-reset="${tIdx}" type="checkbox" ${tr.reset_step_index !== false ? 'checked' : ''}>先頭手順へ戻す</label>
                        <button data-tr-del="${tIdx}" style="padding:4px 7px; border:none; background:#c23b3b; color:#fff; border-radius:5px; cursor:pointer;">削除</button>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                        <div style="font-size:0.8em; color:#385c73; font-weight:bold;">判定条件（すべて成立で遷移）</div>
                        <button data-tr-cond-add="${tIdx}" style="padding:3px 8px; border:none; background:#5f9ec9; color:#fff; border-radius:4px; cursor:pointer;">条件追加</button>
                    </div>
                    <div>${condRows}</div>
                `;
                const select = box.querySelector(`[data-tr-to="${tIdx}"]`);
                if (select) select.value = String(tr.to_loop_id || '');
                trListEl.appendChild(box);
            });
        }

        editorEl.querySelector('#behavior-loop-id')?.addEventListener('change', (e) => {
            const newId = String(e.target.value || '').trim();
            if (!newId || newId === selectedLoopId) {
                e.target.value = selectedLoopId;
                return;
            }
            if (draft.loops[newId]) {
                alert('同名のループIDが既に存在します。');
                e.target.value = selectedLoopId;
                return;
            }
            const oldId = selectedLoopId;
            draft.loops[newId] = draft.loops[oldId];
            delete draft.loops[oldId];
            if (nodeLayout[oldId]) {
                nodeLayout[newId] = nodeLayout[oldId];
                delete nodeLayout[oldId];
            }
            Object.values(draft.loops).forEach((lp) => {
                if (!lp || !Array.isArray(lp.transitions)) return;
                lp.transitions.forEach((tr) => {
                    if (tr.to_loop_id === oldId) tr.to_loop_id = newId;
                });
            });
            if (draft.initial_loop_id === oldId) draft.initial_loop_id = newId;
            if (connectFromLoopId === oldId) connectFromLoopId = newId;
            selectedLoopId = newId;
            markDirty();
            renderAll();
        });
        editorEl.querySelector('#behavior-loop-repeat')?.addEventListener('change', (e) => {
            loop.repeat = !!e.target.checked;
            markDirty();
            renderPreview();
        });
        editorEl.querySelector('#behavior-loop-delete-btn')?.addEventListener('click', () => {
            if (loopIds().length <= 1) {
                alert('最低1つのループは必要です。');
                return;
            }
            if (!confirm(`ループ「${selectedLoopId}」を削除しますか？`)) return;
            const removed = selectedLoopId;
            delete draft.loops[removed];
            delete nodeLayout[removed];
            if (connectFromLoopId === removed) connectFromLoopId = null;
            Object.values(draft.loops).forEach((lp) => {
                if (!lp || !Array.isArray(lp.transitions)) return;
                lp.transitions = lp.transitions.filter((tr) => tr.to_loop_id !== removed);
            });
            ensureSelection();
            markDirty();
            renderAll();
        });

        editorEl.querySelector('#behavior-step-add-btn')?.addEventListener('click', () => {
            loop.steps.push({ actions: [null] });
            markDirty();
            renderAll();
        });
        editorEl.querySelectorAll('[data-step-action]').forEach((select) => {
            select.addEventListener('change', (e) => {
                const [stepIdxRaw, actionIdxRaw] = String(e.target.dataset.stepAction || '').split(':');
                const stepIdx = parseInt(stepIdxRaw, 10);
                const actionIdx = parseInt(actionIdxRaw, 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep) return;
                const actions = Array.isArray(targetStep.actions) ? targetStep.actions : [null];
                actions[actionIdx] = String(e.target.value || '').trim() || null;
                targetStep.actions = actions;
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-step-action-add]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const stepIdx = parseInt(e.currentTarget.dataset.stepActionAdd, 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep) return;
                const actions = Array.isArray(targetStep.actions) ? targetStep.actions : [null];
                actions.push(null);
                targetStep.actions = actions;
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-step-action-del]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const [stepIdxRaw, actionIdxRaw] = String(e.currentTarget.dataset.stepActionDel || '').split(':');
                const stepIdx = parseInt(stepIdxRaw, 10);
                const actionIdx = parseInt(actionIdxRaw, 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep) return;
                const actions = Array.isArray(targetStep.actions) ? targetStep.actions : [null];
                actions.splice(actionIdx, 1);
                targetStep.actions = actions.length ? actions : [null];
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-step-del]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.dataset.stepDel, 10);
                loop.steps.splice(idx, 1);
                markDirty();
                renderAll();
            });
        });

        editorEl.querySelector('#behavior-tr-add-btn')?.addEventListener('click', () => {
            const toLoop = loopIds().find((id) => id !== selectedLoopId) || selectedLoopId;
            loop.transitions.push({
                priority: 10,
                to_loop_id: toLoop,
                reset_step_index: true,
                when_all: []
            });
            markDirty();
            renderAll();
        });
        editorEl.querySelectorAll('[data-tr-priority]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.trPriority, 10);
                loop.transitions[idx].priority = Number.isFinite(Number(e.target.value)) ? parseInt(e.target.value, 10) : 0;
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-to]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.trTo, 10);
                loop.transitions[idx].to_loop_id = String(e.target.value || '').trim();
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-reset]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.trReset, 10);
                loop.transitions[idx].reset_step_index = !!e.target.checked;
                markDirty();
                renderPreview();
            });
        });
        const readConditionRef = (token) => {
            const [trIdxRaw, condIdxRaw] = String(token || '').split(':');
            const trIdx = parseInt(trIdxRaw, 10);
            const condIdx = parseInt(condIdxRaw, 10);
            if (!Number.isFinite(trIdx) || !Number.isFinite(condIdx)) return null;
            const trObj = loop.transitions[trIdx];
            if (!trObj || typeof trObj !== 'object') return null;
            if (!Array.isArray(trObj.when_all)) trObj.when_all = [];
            const rawCond = trObj.when_all[condIdx];
            const cond = normalizeBehaviorConditionRow(rawCond);
            trObj.when_all[condIdx] = cond;
            return { trObj, cond, trIdx, condIdx };
        };
        editorEl.querySelectorAll('[data-tr-cond-add]').forEach((el) => {
            el.addEventListener('click', (e) => {
                const trIdx = parseInt(e.currentTarget.dataset.trCondAdd, 10);
                const trObj = loop.transitions[trIdx];
                if (!trObj || typeof trObj !== 'object') return;
                if (!Array.isArray(trObj.when_all)) trObj.when_all = [];
                const presets = getBehaviorConditionParamPresets('self');
                trObj.when_all.push({
                    source: 'self',
                    param: presets[0] ? presets[0].value : 'HP',
                    operator: 'LTE',
                    value: 50
                });
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-source]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondSource);
                if (!ref) return;
                ref.cond.source = (String(e.target.value || '').trim() === 'battle') ? 'battle' : 'self';
                const presets = getBehaviorConditionParamPresets(ref.cond.source);
                const hasCurrent = presets.some((row) => row.value === ref.cond.param);
                if (!hasCurrent && presets[0]) ref.cond.param = presets[0].value;
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-param-select]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondParamSelect);
                if (!ref) return;
                const selected = String(e.target.value || '').trim();
                if (selected !== '__custom__') {
                    ref.cond.param = selected;
                } else if (!String(ref.cond.param || '').trim()) {
                    ref.cond.param = '';
                }
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-param-custom]').forEach((el) => {
            el.addEventListener('input', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondParamCustom);
                if (!ref) return;
                ref.cond.param = String(e.target.value || '').trim();
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-op]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondOp);
                if (!ref) return;
                ref.cond.operator = String(e.target.value || '').trim().toUpperCase() || 'EQUALS';
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-value]').forEach((el) => {
            el.addEventListener('input', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondValue);
                if (!ref) return;
                ref.cond.value = coerceBehaviorConditionValue(e.target.value);
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-del]').forEach((el) => {
            el.addEventListener('click', (e) => {
                const ref = readConditionRef(e.currentTarget.dataset.trCondDel);
                if (!ref) return;
                ref.trObj.when_all.splice(ref.condIdx, 1);
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-del]').forEach((el) => {
            el.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.dataset.trDel, 10);
                loop.transitions.splice(idx, 1);
                markDirty();
                renderAll();
            });
        });
    }

    function renderAll() {
        ensureSelection();
        ensureNodeLayout();
        enabledEl.checked = !!draft.enabled;
        renderInitialLoopOptions();
        renderLoopTabs();
        renderPreview();
        renderLoopEditor();
        if (connectHintEl) {
            connectHintEl.textContent = connectFromLoopId
                ? `接続元: ${connectFromLoopId}。接続先ノードをクリックしてください。`
                : 'ノードをドラッグで移動。接続開始後に接続先ノードをクリック。';
        }
    }

    enabledEl.addEventListener('change', (e) => {
        draft.enabled = !!e.target.checked;
        markDirty();
        renderPreview();
    });
    initialEl.addEventListener('change', (e) => {
        draft.initial_loop_id = String(e.target.value || '').trim() || draft.initial_loop_id;
        markDirty();
        renderPreview();
    });
    addLoopBtn.addEventListener('click', () => {
        const loopId = uniqueLoopId(newLoopInput.value || 'loop');
        draft.loops[loopId] = { repeat: true, steps: [{ actions: [null] }], transitions: [] };
        if (!nodeLayout[loopId]) nodeLayout[loopId] = { x: 30, y: 30 };
        selectedLoopId = loopId;
        if (!draft.initial_loop_id) draft.initial_loop_id = loopId;
        newLoopInput.value = '';
        markDirty();
        renderAll();
    });
    resetProfileBtn?.addEventListener('click', () => {
        const ok = confirm('このキャラの行動チャートを初期化します。よろしいですか？');
        if (!ok) return;
        draft.enabled = false;
        draft.initial_loop_id = 'loop_1';
        draft.loops = {
            loop_1: {
                repeat: true,
                steps: [{ actions: [null] }],
                transitions: []
            }
        };
        selectedLoopId = 'loop_1';
        connectFromLoopId = null;
        Object.keys(nodeLayout).forEach((id) => { delete nodeLayout[id]; });
        nodeLayout.loop_1 = { x: 30, y: 30 };
        markDirty();
        renderAll();
    });
    newLoopInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addLoopBtn.click();
        }
    });

    connectStartBtn?.addEventListener('click', () => {
        ensureSelection();
        connectFromLoopId = selectedLoopId || loopIds()[0] || null;
        renderAll();
    });
    connectCancelBtn?.addEventListener('click', () => {
        connectFromLoopId = null;
        renderAll();
    });

    content.querySelector('#behavior-save-btn')?.addEventListener('click', () => {
        const normalized = normalizeBehaviorProfileForEditor(draft);
        const nextFlags = Object.assign({}, currentFlags, { behavior_profile: normalized });
        socket.emit('request_state_update', {
            room: currentRoomName,
            charId: char.id,
            statName: 'flags',
            newValue: nextFlags
        });
        clearDirty();
        closeModal(true);
    });

    renderAll();
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
    const baseBehaviorProfile = (
        char.flags
        && typeof char.flags === 'object'
        && char.flags.behavior_profile
        && typeof char.flags.behavior_profile === 'object'
    )
        ? char.flags.behavior_profile
        : { enabled: false, version: 1, initial_loop_id: null, loops: {} };

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

            <div style="margin-bottom:15px; padding: 5px; background: #fff8e1; border-radius: 4px;">
                <label style="display:flex; align-items:center; cursor: pointer;">
                    <input type="checkbox" id="ctx-show-planned" class="settings-input" ${(char.flags && char.flags.show_planned_skill) ? 'checked' : ''} style="margin-right: 8px;">
                    <span style="font-size: 0.9em; color: #495057;">予約スキルを公開 (AI用)</span>
                </label>
            </div>

            ${isGM ? `
            <div style="margin-bottom:15px; padding: 8px; background: #eef6ff; border-radius: 4px; border:1px solid #d0e2ff;">
                <label style="display:flex; align-items:center; cursor: pointer; margin-bottom:8px;">
                    <input type="checkbox" id="ctx-behavior-enabled" class="settings-input" ${baseBehaviorProfile.enabled ? 'checked' : ''} style="margin-right: 8px;">
                    <span style="font-size: 0.9em; color: #2f4858;">行動チャート有効</span>
                </label>
                <button id="ctx-behavior-edit-btn" style="width:100%; padding: 6px 8px; background:#2f7fbf; color:#fff; border:none; border-radius:4px; cursor:pointer;">行動チャート編集（フロー）</button>
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
            const battleImage = selectedImage.croppedUrl || selectedImage.url;
            const explorationImage = selectedImage.originalUrl || selectedImage.url;
            socket.emit('request_state_update', {
                room: currentRoomName,
                charId: char.id,
                changes: {
                    image: battleImage,
                    imageOriginal: explorationImage
                }
            });
            // Update modal preview immediately if possible
            const previewImg = document.getElementById('char-preview-img');
            const previewArea = document.getElementById('char-image-preview');
            if (previewImg) {
                previewImg.src = battleImage;
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

    // Show Planned Skill Toggle (For AI)
    const planToggle = menu.querySelector('#ctx-show-planned');
    if (planToggle) {
        planToggle.addEventListener('change', (e) => {
            // Clone existing flags to avoid mutating local state prematurely (though render updates it anyway)
            const currentFlags = char.flags || {};
            const newFlags = Object.assign({}, currentFlags, { show_planned_skill: e.target.checked });
            socket.emit('request_state_update', {
                room: currentRoomName, charId: char.id, statName: 'flags', newValue: newFlags
            });
        });
    }

    const behaviorToggle = menu.querySelector('#ctx-behavior-enabled');
    if (behaviorToggle) {
        behaviorToggle.addEventListener('change', (e) => {
            const currentFlags = char.flags || {};
            const currentProfile = (currentFlags.behavior_profile && typeof currentFlags.behavior_profile === 'object')
                ? currentFlags.behavior_profile
                : { version: 1, initial_loop_id: null, loops: {} };
            const nextProfile = Object.assign({}, currentProfile, { enabled: !!e.target.checked });
            const newFlags = Object.assign({}, currentFlags, { behavior_profile: nextProfile });
            socket.emit('request_state_update', {
                room: currentRoomName, charId: char.id, statName: 'flags', newValue: newFlags
            });
        });
    }

    const behaviorEditBtn = menu.querySelector('#ctx-behavior-edit-btn');
    if (behaviorEditBtn) {
        behaviorEditBtn.addEventListener('click', () => {
            openBehaviorFlowEditorModal(char);
            closeMenu();
        });
    }
}

// Helper to close modal by ID (if not exists in global scope, defined here just in case)
function closeGameModal(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}


function openSkillDetailModal(skillId, skillName, options = {}) {
    // スキルデータを取得
    const skillData = (window.allSkillData && window.allSkillData[skillId]) ? window.allSkillData[skillId] : null;
    const granted = (options && typeof options === 'object' && options.granted && typeof options.granted === 'object')
        ? options.granted
        : null;
    const isGranted = !!granted;

    // 既存のスキル詳細モーダルがあれば削除
    const existing = document.getElementById('skill-detail-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'skill-detail-modal-backdrop';
    overlay.className = 'modal-backdrop book-modal-backdrop';

    const content = document.createElement('div');
    content.className = 'modal-content book-skill-detail-modal';
    content.style.maxWidth = '680px';
    content.style.padding = '20px';
    if (isGranted) {
        content.style.borderColor = '#dfb33f';
        content.style.boxShadow = '0 18px 45px rgba(120, 88, 22, 0.40)';
    }

    let grantInfoHtml = '';
    if (isGranted) {
        const mode = String(granted.mode || '').toLowerCase();
        const rounds = parseInt(granted.remaining_rounds, 10);
        const uses = parseInt(granted.remaining_uses, 10);
        let statusHtml = '<span style="background:#ffe08a; color:#5a4300; border:1px solid #f3c34a; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em;">付与スキル</span>';
        if (mode === 'permanent') {
            statusHtml += '<span style="background:#f6f6f6; color:#555; border:1px solid #ddd; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em; margin-left:6px;">永続</span>';
        }
        if (Number.isFinite(rounds) && rounds > 0) {
            statusHtml += `<span style="background:#fff3bf; color:#5a4300; border:1px solid #f3c34a; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em; margin-left:6px;">残り${rounds}R</span>`;
        }
        if (Number.isFinite(uses) && uses >= 0) {
            statusHtml += `<span style="background:#fff3bf; color:#5a4300; border:1px solid #f3c34a; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em; margin-left:6px;">残り${uses}回</span>`;
        }
        grantInfoHtml = `
            <div style="margin: 0 0 10px 0; padding: 8px 10px; border: 1px solid #f3c34a; border-radius: 8px; background: #fff8dc;">
                ${statusHtml}
            </div>
        `;
    }

    let bodyHtml = '';
    if (skillData) {
        bodyHtml = `
            <div class="book-skill-meta">
                <span class="book-skill-id">[${skillId}]</span>
                <span class="book-skill-category">${skillData['分類'] || '---'}</span>
            </div>
            ${grantInfoHtml}
            <div class="skill-detail-body book-reading-body">
                ${formatSkillDetailHTML(skillData)}
            </div>
        `;
    } else {
        bodyHtml = `<p class="book-reading-body">スキルデータが見つかりません: ${skillId}</p>`;
    }

    content.innerHTML = `
        <div class="book-modal-header">
            <h3 class="book-modal-title" style="${isGranted ? 'color:#7a5a16;' : ''}">${skillName || skillId}</h3>
            <button class="modal-close-btn book-modal-close" aria-label="閉じる">×</button>
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

        <div style="margin-top:16px; border-top:1px solid #ddd; padding-top:12px;">
            <label><strong>プリセットJSON搬出入:</strong></label>
            <textarea id="preset-json-transfer" placeholder='{"schema":"gem_dicebot_enemy_preset.v1", ...}' style="width:100%; min-height:100px; margin-top:6px; padding:8px; font-family:monospace;"></textarea>
            <div style="display:flex; justify-content:flex-end; margin-top:6px;">
                <button id="preset-import-btn" class="room-action-btn" style="padding:6px 12px;">JSON取込</button>
            </div>
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
    const transferArea = document.getElementById('preset-json-transfer');
    const importBtn = document.getElementById('preset-import-btn');
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

            const exportBtn = document.createElement('button');
            exportBtn.textContent = 'JSON出力';
            exportBtn.style.fontSize = '0.85em';
            exportBtn.style.padding = '4px 10px';
            exportBtn.style.marginRight = '5px';
            exportBtn.onclick = () => {
                socket.emit('request_export_preset_json', { room: currentRoomName, name: name });
            };

            btnGroup.appendChild(exportBtn);
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

    socket.off('preset_error');
    socket.on('preset_error', (data) => {
        msgArea.textContent = data?.message || 'プリセット操作でエラーが発生しました';
        msgArea.style.color = 'red';
    });

    socket.off('preset_json_exported');
    socket.on('preset_json_exported', (data) => {
        const raw = data?.json || JSON.stringify(data?.payload || {}, null, 2);
        if (transferArea) transferArea.value = raw;
        msgArea.textContent = `「${data?.name || 'preset'}」をJSON出力しました`;
        msgArea.style.color = 'green';
    });

    socket.off('preset_export_error');
    socket.on('preset_export_error', (data) => {
        msgArea.textContent = data?.message || 'JSON出力に失敗しました';
        msgArea.style.color = 'red';
    });

    socket.off('preset_imported');
    socket.on('preset_imported', (data) => {
        msgArea.textContent = `JSONを「${data?.name || ''}」として取り込みました`;
        msgArea.style.color = 'green';
        socket.emit('request_get_presets', { room: currentRoomName });
    });

    socket.off('preset_import_error');
    socket.on('preset_import_error', (data) => {
        if (data?.error === 'duplicate') {
            if (confirm(data.message || '同名プリセットがあります。上書きしますか？')) {
                socket.emit('request_import_preset_json', {
                    room: currentRoomName,
                    json: transferArea?.value || '',
                    overwrite: true
                });
            }
            return;
        }
        msgArea.textContent = data?.message || 'JSON取込に失敗しました';
        msgArea.style.color = 'red';
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

    if (importBtn) {
        importBtn.addEventListener('click', () => {
            const raw = (transferArea?.value || '').trim();
            if (!raw) {
                msgArea.textContent = '取込JSONを入力してください';
                msgArea.style.color = 'red';
                return;
            }
            socket.emit('request_import_preset_json', { room: currentRoomName, json: raw });
            msgArea.textContent = 'JSON取込中...';
            msgArea.style.color = '#333';
        });
    }
}



function openResetTypeModal(callback) {
    const existing = document.getElementById('reset-type-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'reset-type-modal-backdrop';
    overlay.className = 'modal-backdrop';

    overlay.innerHTML = `
        <div class="modal-content" style="width: 450px; padding: 25px;">
            <h3 style="margin-top: 0; color: #dc3545; border-bottom: 2px solid #eee; padding-bottom: 10px;">
                戦闘リセット設定
            </h3>

            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 10px 0; color: #555;">ステータスリセットの対象</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; background: #f8f9fa; padding: 15px; border-radius: 4px; border: 1px solid #dee2e6;">
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-hp" checked> <span style="margin-left: 5px;">HP全快</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-mp" checked> <span style="margin-left: 5px;">MP全快</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-fp" checked> <span style="margin-left: 5px;">FP/蓄積値リセット</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-bad" checked> <span style="margin-left: 5px;">状態異常解除</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center; grid-column: span 2;">
                        <input type="checkbox" id="reset-opt-buffs" checked> <span style="margin-left: 5px;">バフ・特殊状態リセット</span>
                    </label>
                </div>
                <div style="font-size: 0.85em; color: #666; margin-top: 5px;">
                    ※「バフリセット」は初期所持バフ（パッシブ由来など）を除き削除します。
                </div>
            </div>

            <div style="display: flex; flex-direction: column; gap: 10px;">
                <button id="reset-status-exec-btn" class="room-action-btn" style="padding: 12px; background-color: #ffc107; color: #333; font-weight: bold; border: 1px solid #e0a800;">
                    上記の内容でステータスのみリセット
                </button>

                <button id="reset-logs-exec-btn" class="room-action-btn" style="padding: 10px; background-color: #17a2b8; color: white; font-weight: bold;">
                    ログのみリセット
                </button>

                <hr style="width: 100%; border: 0; border-top: 1px solid #ddd; margin: 15px 0;">

                <button id="reset-full-exec-btn" class="room-action-btn danger" style="padding: 10px; background-color: #dc3545; color: white; font-weight: bold;">
                    ⚠️ 完全リセット (全キャラ削除・初期化)
                </button>
            </div>

            <div style="margin-top: 20px; text-align: right;">
                <button id="reset-cancel-btn" style="padding: 8px 16px; border: 1px solid #ccc; background: #fff; border-radius: 4px; cursor: pointer;">キャンセル</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const closeFunc = () => overlay.remove();
    document.getElementById('reset-cancel-btn').onclick = closeFunc;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeFunc();
    });

    // ステータスリセット実行
    document.getElementById('reset-status-exec-btn').onclick = () => {
        const options = {
            hp: document.getElementById('reset-opt-hp').checked,
            mp: document.getElementById('reset-opt-mp').checked,
            fp: document.getElementById('reset-opt-fp').checked,
            states: document.getElementById('reset-opt-fp').checked, // 蓄積値はFPと一緒に扱う簡易実装
            bad_states: document.getElementById('reset-opt-bad').checked,
            buffs: document.getElementById('reset-opt-buffs').checked,
            timeline: true // ステータスリセット時にタイムラインもクリア
        };

        if (confirm('選択した内容でステータスをリセットしますか？')) {
            callback('status', options);
            closeFunc();
        }
    };

    // ログのみリセット実行
    document.getElementById('reset-logs-exec-btn').onclick = () => {
        if (confirm('ログだけを削除しますか？')) {
            callback('logs', null);
            closeFunc();
        }
    };

    // 完全リセット実行
    document.getElementById('reset-full-exec-btn').onclick = () => {
        if (confirm('本当にキャラクターを全員削除し、戦闘を初期化しますか？\nこの操作は取り消せません。')) {
            callback('full', null); // オプションなし=デフォルト
            closeFunc();
        }
    };
}

// Global Alias for Character Detail Modal (Used by Battle/Exploration views)
window.showCharacterDetail = openCharacterModal;
