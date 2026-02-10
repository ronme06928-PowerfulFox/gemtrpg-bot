// === ▼▼▼ Action Dock & Immediate Skills Functions ▼▼▼ ===

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
// アクションドックの更新関数
function updateActionDock() {
    // ★ Exploration Mode Check
    const mode = battleState ? (battleState.mode || 'battle') : 'unknown';
    console.log(`[ActionDock] Update called. Mode: ${mode}`);

    // ★ Unplaced Area (Shared Modal) Update
    // Always update this if it exists, regardless of mode
    const stagingList = document.getElementById('staging-overlay-list');
    if (stagingList) {
        renderStagingOverlayList(stagingList);
    }

    // Force Exploration Dock if mode is exploration
    if (mode === 'exploration') {
        const dock = document.getElementById('action-dock');

        // Ensure we don't have battle icons
        if (dock && !dock.classList.contains('exploration-mode')) {
            console.log('[ActionDock] Switching to Exploration Dock (Clearing content)');
            dock.innerHTML = '';
            dock.className = 'action-dock exploration-mode';
        }

        if (window.ExplorationDock && typeof window.ExplorationDock.render === 'function') {
            console.log('[ActionDock] Rendering ExplorationDock content');
            window.ExplorationDock.render();
        } else {
            // Script might not be loaded yet
            console.warn('[ActionDock] ExplorationDock not ready, retrying...');
            setTimeout(updateActionDock, 200);
        }
        return; // Always return to prevent Battle Dock rendering
    }

    // Battle Mode Logic
    // Reset to Battle Dock (if switching back)
    const dock = document.getElementById('action-dock');
    if (dock && dock.classList.contains('exploration-mode')) {
        console.log('[ActionDock] Switching back to Battle Dock');
        dock.className = 'action-dock';
        dock.innerHTML = `
            <div id="dock-match-icon" class="dock-icon" style="display: none;" title="マッチ実行">⚔️</div>
            <div id="dock-immediate-icon" class="dock-icon disabled" title="即時発動スキル">⚡</div>
            <div id="dock-item-icon" class="dock-icon" title="アイテム使用">🎒</div>
            <div id="dock-quick-edit-icon" class="dock-icon" title="簡易ステータス編集">📝</div>
            <div id="dock-add-char-icon" class="dock-icon" title="キャラクター追加">➕</div>
            <div id="dock-staging-icon" class="dock-icon" title="未配置キャラクター">📦</div>
            <div id="dock-arrow-toggle-icon" class="dock-icon" title="矢印表示切替">🏹</div>
        `;
        // Re-initialize listeners
        initializeActionDock();

        // ★ Explorationから戻った場合にラウンドボタン表示を復帰させる
        // GMの場合のみ表示する (setupVisualSidebarControlsのロジックと同様)
        if (currentUserAttribute === 'GM') {
            const rStartBtn = document.getElementById('visual-round-start-btn');
            const rEndBtn = document.getElementById('visual-round-end-btn');
            if (rStartBtn) rStartBtn.style.display = 'inline-block';
            if (rEndBtn) rEndBtn.style.display = 'inline-block';
        }
    }

    // ★ Add Switch to Exploration Button for GM (if not exists)
    if (currentUserAttribute === 'GM' && dock) {
        let expBtn = document.getElementById('dock-to-exploration-btn');
        if (!expBtn) {
            expBtn = document.createElement('div');
            expBtn.id = 'dock-to-exploration-btn';
            expBtn.className = 'dock-icon';
            expBtn.textContent = '🗺️';
            expBtn.title = '探索パートへ切替';
            expBtn.style.background = '#27ae60'; // Green
            expBtn.onclick = () => {
                if (confirm('探索パートへ切り替えますか？')) {
                    socket.emit('request_change_mode', { room: currentRoomName, mode: 'exploration' });
                }
            };
            // Insert at bottom
            dock.appendChild(expBtn);
        }
    }


    const immediateIcon = document.getElementById('dock-immediate-icon');
    const matchIcon = document.getElementById('dock-match-icon');
    const stagingIcon = document.getElementById('dock-staging-icon');
    const quickEditIcon = document.getElementById('dock-quick-edit-icon');

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

    // マッチアイコンの状態表示
    if (matchIcon) {
        // マッチが開催中の時のみアイコンを表示
        if (battleState.active_match && battleState.active_match.is_active) {
            matchIcon.style.display = 'flex';
            matchIcon.classList.add('active');
        } else {
            matchIcon.style.display = 'none';
            matchIcon.classList.remove('active');
        }
    }

    // 未配置エリア（モーダル）のリストがあれば無条件に更新（非表示でも最新化しておく）
    // const stagingList = document.getElementById('staging-overlay-list'); // Moved to top
    if (stagingList) {
        // console.log('📦 Updating staging overlay list...'); // 頻出しすぎる場合はコメントアウト
        renderStagingOverlayList(stagingList);
    }

    // Quick Edit Icon is always available but only works if characters exist
    if (quickEditIcon) {
        if (battleState.characters.length > 0) {
            quickEditIcon.classList.remove('disabled');
        } else {
            quickEditIcon.classList.add('disabled');
        }
    }

    // ★ 一方攻撃時のUI更新
    updateDefenderUIForOneSidedAttack();
}

// ★ 一方攻撃時の防御者UI更新（Phase 11バグ修正）
function updateDefenderUIForOneSidedAttack() {
    if (!battleState || !battleState.active_match) return;

    const matchData = battleState.active_match;
    const isOneSided = matchData.is_one_sided_attack || false;

    if (!isOneSided) return; // 通常マッチなら何もしない

    const defenderControls = document.getElementById('duel-defender-controls');
    const defenderLockMsg = document.getElementById('duel-defender-lock-msg');

    if (defenderControls) {
        defenderControls.style.display = 'none';
    }

    if (defenderLockMsg) {
        defenderLockMsg.style.display = 'block';
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
            // ★配置済みかつ自分のキャラ
            return (c.x >= 0 && c.y >= 0) && (c.owner === currentUsername || (currentUserId && c.owner_id === currentUserId));
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
            option.textContent = `${skill.id} ${skill.name} `;
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
            prefix: `immediate_${char.id} `
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

// 簡易ステータス編集モーダルを開く
function openQuickEditModal() {
    const icon = document.getElementById('dock-quick-edit-icon');
    if (icon && icon.classList.contains('disabled')) return;

    let backdrop = document.getElementById('quick-edit-modal-backdrop');
    if (backdrop) {
        if (backdrop.style.display === 'none') {
            backdrop.style.display = 'flex';
        } else {
            backdrop.style.display = 'none';
        }
        return;
    }

    backdrop = document.createElement('div');
    backdrop.id = 'quick-edit-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';
    backdrop.style.alignItems = 'flex-start'; // 上寄せにする
    backdrop.style.paddingTop = '50px';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';
    modalContent.style.width = '700px';
    modalContent.style.maxHeight = '85vh';
    modalContent.style.display = 'flex';
    modalContent.style.flexDirection = 'column';
    modalContent.style.borderRadius = '12px';
    modalContent.style.border = 'none';
    modalContent.style.boxShadow = '0 10px 25px rgba(0,0,0,0.5)';
    modalContent.style.background = '#f4f6f9'; // 少しグレーがかった背景

    // カスタムスタイル定義
    const style = document.createElement('style');
    style.textContent = `
        .qe-card {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 12px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            display: grid;
            grid-template-columns: 60px 1fr 280px 80px; /* Icon, Name, Stats, Button */
            align-items: center;
            gap: 15px;
            border-left: 5px solid #ccc;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .qe-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        .qe-card.ally { border-left-color: #3498db; }
        .qe-card.enemy { border-left-color: #e74c3c; }

        .qe-icon {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            object-fit: cover;
            border: 2px solid #eee;
            background: #ddd;
        }
        .qe-name-area {
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .qe-name {
            font-weight: bold;
            font-size: 1.1em;
            color: #333;
            margin-bottom: 4px;
        }
        .qe-sub {
            font-size: 0.85em;
            color: #777;
        }

        .qe-stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 10px;
        }
        .qe-stat-box {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .qe-label {
            font-size: 0.75em;
            font-weight: bold;
            margin-bottom: 2px;
            text-transform: uppercase;
        }
        .qe-input {
            width: 100%;
            padding: 6px;
            border: 1px solid #ddd;
            border-radius: 6px;
            text-align: center;
            font-weight: bold;
            font-size: 1.1em;
            transition: border-color 0.2s;
        }
        .qe-input:focus {
            border-color: #3498db;
            outline: none;
            background: #f0f8ff;
        }

        /* Stat Specific Colors */
        .stat-hp .qe-label { color: #27ae60; }
        .stat-hp .qe-input { color: #27ae60; }

        .stat-mp .qe-label { color: #2980b9; }
        .stat-mp .qe-input { color: #2980b9; }

        .stat-fp .qe-label { color: #d35400; }
        .stat-fp .qe-input { color: #d35400; }

        .qe-update-btn {
            background: linear-gradient(to bottom, #f8f9fa, #e9ecef);
            border: 1px solid #ced4da;
            border-radius: 6px;
            padding: 8px 0;
            cursor: pointer;
            font-weight: bold;
            color: #555;
            transition: all 0.2s;
        }
        .qe-update-btn:hover {
            background: #e2e6ea;
            border-color: #adb5bd;
            color: #333;
        }
        .qe-update-btn:active {
            transform: scale(0.98);
        }
        .qe-update-btn.success {
            background: #d4edda;
            border-color: #c3e6cb;
            color: #155724;
        }

        /* Scrollbar styling */
        .modal-body::-webkit-scrollbar { width: 8px; }
        .modal-body::-webkit-scrollbar-track { background: transparent; }
        .modal-body::-webkit-scrollbar-thumb { background: #cbd5e0; border-radius: 4px; }
        .modal-body::-webkit-scrollbar-thumb:hover { background: #a0aec0; }
    `;
    modalContent.appendChild(style);

    modalContent.innerHTML += `
        <div class="modal-header" style="background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); color: white; padding: 15px 20px; display:flex; justify-content:space-between; align-items:center; border-radius: 12px 12px 0 0;">
            <div style="display:flex; align-items:center;">
                <span style="font-size: 1.5em; margin-right: 10px;">📝</span>
                <div>
                    <h3 style="margin:0; font-size: 1.25em;">簡易ステータス編集</h3>
                    <div style="font-size: 0.8em; opacity: 0.9; font-weight: normal;">Combat Status Quick Editor</div>
                </div>
            </div>
            <button class="window-control-btn close-btn" style="border:none; background:rgba(255,255,255,0.2); color:white; width: 32px; height: 32px; border-radius: 50%; font-size:1.2em; cursor:pointer; display:flex; align-items:center; justify-content:center; transition: background 0.2s;">×</button>
        </div>
        <div class="modal-body" style="overflow-y:auto; flex:1; padding: 20px; background: #f4f6f9;">
            <div id="quick-edit-list"></div>
        </div>
    `;

    backdrop.appendChild(modalContent);
    document.body.appendChild(backdrop);

    const closeFunc = () => backdrop.remove();
    modalContent.querySelector('.close-btn').addEventListener('click', closeFunc);
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeFunc();
    });

    // Close button hover effect
    const closeBtn = modalContent.querySelector('.close-btn');
    closeBtn.onmouseenter = () => closeBtn.style.background = 'rgba(255,255,255,0.4)';
    closeBtn.onmouseleave = () => closeBtn.style.background = 'rgba(255,255,255,0.2)';

    const listContainer = document.getElementById('quick-edit-list');
    renderQuickEditList(listContainer);
}

function renderQuickEditList(container) {
    if (!battleState || !battleState.characters) return;

    // GMは全キャラ、PLは自分の持ちキャラのみ
    const targetChars = battleState.characters.filter(c => {
        if (currentUserAttribute === 'GM') return true;
        return c.owner === currentUsername || (currentUserId && c.owner_id === currentUserId);
    });

    if (targetChars.length === 0) {
        container.innerHTML = `
            <div style="text-align:center; padding: 40px; color:#999;">
                <div style="font-size: 3em; margin-bottom: 10px;">👻</div>
                <p>編集可能なキャラクターがいません</p>
            </div>`;
        return;
    }

    // ソート: 味方 -> 敵, 名前順
    targetChars.sort((a, b) => {
        if (a.type !== b.type) return a.type === 'ally' ? -1 : 1;
        return a.name.localeCompare(b.name);
    });

    targetChars.forEach(char => {
        const row = document.createElement('div');
        const isAlly = char.type === 'ally';
        row.className = `qe-card ${isAlly ? 'ally' : 'enemy'}`;

        // 1. Icon Section
        const iconDiv = document.createElement('div');
        iconDiv.style.textAlign = 'center';

        if (char.image) {
            const img = document.createElement('img');
            img.src = char.image;
            img.className = 'qe-icon';
            img.onerror = () => { img.src = ''; img.style.display = 'none'; iconDiv.textContent = '👤'; iconDiv.style.fontSize = '2em'; };
            iconDiv.appendChild(img);
        } else {
            const initial = document.createElement('div');
            initial.className = 'qe-icon';
            initial.style.display = 'flex';
            initial.style.alignItems = 'center';
            initial.style.justifyContent = 'center';
            initial.style.background = char.color || '#ccc';
            initial.style.color = 'white';
            initial.style.fontWeight = 'bold';
            initial.textContent = char.name.charAt(0);
            iconDiv.appendChild(initial);
        }

        // 2. Name Section
        const nameDiv = document.createElement('div');
        nameDiv.className = 'qe-name-area';
        nameDiv.innerHTML = `
            <div class="qe-name" style="color: ${char.color || '#333'}">${char.name}</div>
            <div class="qe-sub">${isAlly ? '味方' : '敵'} / Init: ${char.speedRoll || '-'}</div>
        `;

        // 3. Stats Section
        const statsDiv = document.createElement('div');
        statsDiv.className = 'qe-stats-grid';

        const createStatBox = (label, value, cls) => {
            const box = document.createElement('div');
            box.className = `qe-stat-box ${cls}`;
            box.innerHTML = `<div class="qe-label">${label}</div>`;

            const input = document.createElement('input');
            input.type = 'number';
            input.value = value;
            input.className = 'qe-input';

            box.appendChild(input);
            return { box, input };
        };

        const hpGrp = createStatBox('HP', char.hp, 'stat-hp');
        const mpGrp = createStatBox('MP', char.mp, 'stat-mp');

        // FP Logic
        const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
        const fpVal = fpState ? fpState.value : 0;
        const fpGrp = createStatBox('FP', fpVal, 'stat-fp');

        statsDiv.appendChild(hpGrp.box);
        statsDiv.appendChild(mpGrp.box);
        statsDiv.appendChild(fpGrp.box);

        // 4. Button Section
        const btnDiv = document.createElement('div');
        const btn = document.createElement('button');
        btn.innerHTML = '更新';
        btn.className = 'qe-update-btn';
        btn.style.width = '100%';

        btn.onclick = () => {
            const newHp = parseInt(hpGrp.input.value, 10);
            const newMp = parseInt(mpGrp.input.value, 10);
            const newFp = parseInt(fpGrp.input.value, 10);

            if (isNaN(newHp) || isNaN(newMp) || isNaN(newFp)) {
                alert('数値を入力してください');
                return;
            }

            const changes = {};
            // 差分チェック
            if (newHp !== char.hp) changes.HP = newHp;
            if (newMp !== char.mp) changes.MP = newMp;
            if (newFp !== fpVal) changes.FP = newFp;

            if (Object.keys(changes).length > 0) {
                const socketToUse = window.socket || (typeof socket !== 'undefined' ? socket : null);
                if (socketToUse) {
                    socketToUse.emit('request_state_update', {
                        room: currentRoomName,
                        charId: char.id,
                        changes: changes
                    });
                } else {
                    console.error("Socket not found");
                    alert("通信エラーが発生しました。");
                    return;
                }

                // Visual feedback
                btn.innerHTML = '✔';
                btn.classList.add('success');
                setTimeout(() => {
                    btn.innerHTML = '更新';
                    btn.classList.remove('success');
                }, 1000);
            } else {
                // No changes
                btn.style.transform = 'translateX(2px)';
                setTimeout(() => btn.style.transform = 'translateX(-2px)', 50);
                setTimeout(() => btn.style.transform = 'translateX(0)', 100);
            }
        };
        btnDiv.appendChild(btn);

        // Append All
        row.appendChild(iconDiv);
        row.appendChild(nameDiv);
        row.appendChild(statsDiv);
        row.appendChild(btnDiv);

        container.appendChild(row);
    });
}

// アクションドックの初期化（イベントリスナー設定のみ）
function initializeActionDock() {
    // If in Exploration Mode, do NOT initialize battle dock listeners.
    if (battleState && battleState.mode === 'exploration') {
        console.log('[InitializeActionDock] Skipping Battle Dock init due to Exploration Mode.');
        // Ensure dock is cleared or delegates to updateActionDock
        if (typeof updateActionDock === 'function') updateActionDock();
        return;
    }


    const immediateIcon = document.getElementById('dock-immediate-icon');
    const addCharIcon = document.getElementById('dock-add-char-icon');
    const stagingIcon = document.getElementById('dock-staging-icon');
    const matchIcon = document.getElementById('dock-match-icon');
    const itemIcon = document.getElementById('dock-item-icon');
    const quickEditIcon = document.getElementById('dock-quick-edit-icon');
    const arrowIcon = document.getElementById('dock-arrow-toggle-icon');


    // ★ 修正: 個別にチェックして設定（1つがなくても他は設定する）
    if (arrowIcon) {
        // 初期状態の反映
        if (typeof window.VISUAL_SHOW_ARROWS !== 'undefined' && !window.VISUAL_SHOW_ARROWS) {
            arrowIcon.classList.add('disabled'); // 便宜上 disabled クラスで薄くする
            arrowIcon.style.opacity = '0.3';
        }

        arrowIcon.onclick = () => {
            if (typeof window.VISUAL_SHOW_ARROWS === 'undefined') window.VISUAL_SHOW_ARROWS = true;
            window.VISUAL_SHOW_ARROWS = !window.VISUAL_SHOW_ARROWS;

            // Visual Feedback
            if (window.VISUAL_SHOW_ARROWS) {
                arrowIcon.style.opacity = '1.0';
                arrowIcon.classList.remove('disabled');
            } else {
                arrowIcon.style.opacity = '0.3';
                arrowIcon.classList.add('disabled');
            }

            // Redraw
            if (typeof window.renderArrows === 'function') {
                window.renderArrows();
            } else {
                // If renderArrows not globally available yet, force map update
                if (typeof window.renderVisualMap === 'function') window.renderVisualMap();
            }
        };
    }

    if (immediateIcon) {
        immediateIcon.onclick = function (e) {

            openImmediateSkillModal();
        };

    } else {
        console.warn('dock-immediate-icon not found in DOM');
    }

    if (quickEditIcon) {
        quickEditIcon.onclick = () => {
            openQuickEditModal();
        };
    } else {
        // console.warn('dock-quick-edit-icon not found in DOM'); // Suppress if not needed
    }

    if (addCharIcon) {
        if (typeof openCharLoadModal === 'function') {
            addCharIcon.onclick = function (e) {

                openCharLoadModal();
            };

        } else {
            console.warn("openCharLoadModal is not defined.");
        }
    } else {
        console.warn('dock-add-char-icon not found in DOM');
    }

    if (stagingIcon) {
        stagingIcon.onclick = function (e) {

            toggleStagingAreaOverlay();
        };

    } else {
        console.warn('dock-staging-icon not found in DOM');
    }

    if (matchIcon) {
        matchIcon.onclick = () => {

            // ★ 追加: activeでない場合は無視（誤操作防止）
            if (!matchIcon.classList.contains('active')) {

                return;
            }

            // ★ 変更: パネルを展開し、最新状態で再描画
            if (typeof expandMatchPanel === 'function') {
                expandMatchPanel();
            }
            if (typeof reloadMatchPanel === 'function') {
                reloadMatchPanel();

            } else if (typeof toggleMatchPanel === 'function') {
                // Fallback: toggleMatchPanel if reloadMatchPanel not available
                console.warn('reloadMatchPanel not found, using toggle');
            }
        };

    } else {
        console.warn('dock-match-icon not found in DOM');
    }

    // ★ Phase 5: アイテムアイコン
    if (itemIcon) {
        itemIcon.onclick = () => {
            if (typeof openItemModal === 'function') {
                openItemModal();
            } else {
                console.warn('openItemModal is not defined');
            }
        };
    } else {
        console.warn('dock-item-icon not found in DOM');
    }

    // 初回更新
    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }


}

// === ▲▲▲ Action Dock & Immediate Skills Functions ▲▲▲ ===

// === ▼▼▼ Staging Area Overlay ▼▼▼ ===

// 未配置エリアオーバーレイの表示/非表示
function toggleStagingAreaOverlay() {


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

    const activeChars = unplacedChars.filter(c => c.hp > 0);
    const deadChars = unplacedChars.filter(c => c.hp <= 0);

    const createCharRow = (char, isDead) => {
        const row = document.createElement('div');
        row.style.padding = '10px';
        row.style.borderBottom = '1px solid #eee';
        row.style.display = 'flex';
        row.style.justifyContent = 'space-between';
        row.style.alignItems = 'center';
        if (isDead) {
            row.style.backgroundColor = '#fff0f0'; // 薄い赤背景
        }

        const nameSpan = document.createElement('span');
        nameSpan.textContent = char.name;
        nameSpan.style.fontWeight = 'bold';
        nameSpan.style.display = 'block';
        if (isDead) nameSpan.style.color = '#c0392b';

        const statsSpan = document.createElement('span');
        statsSpan.textContent = `HP: ${char.hp} / SPD: ${char.speedRoll || '-'}`;
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
        placeBtn.style.background = isDead ? '#95a5a6' : '#3498db';
        placeBtn.style.color = 'white';
        placeBtn.style.border = 'none';
        placeBtn.style.borderRadius = '4px';
        placeBtn.style.cursor = isDead ? 'not-allowed' : 'pointer';
        placeBtn.style.fontWeight = 'bold';

        if (isDead) {
            placeBtn.disabled = true;
            placeBtn.title = "HPが0のため配置できません";
        } else {
            placeBtn.onclick = () => placeCharacterToDefaultPosition(char);
        }

        buttonContainer.appendChild(deleteBtn);
        buttonContainer.appendChild(placeBtn);

        row.appendChild(infoDiv);
        row.appendChild(buttonContainer);
        return row;
    };

    // --- Active Section ---
    if (activeChars.length > 0) {
        const header = document.createElement('h4');
        header.textContent = "未配置 (Active)";
        header.style.margin = "10px 0 5px 0";
        header.style.paddingBottom = "5px";
        header.style.borderBottom = "2px solid #3498db";
        header.style.color = "#2c3e50";
        container.appendChild(header);
        activeChars.forEach(c => container.appendChild(createCharRow(c, false)));
    }

    // --- Incapacitated Section ---
    if (deadChars.length > 0) {
        const header = document.createElement('h4');
        header.textContent = "戦闘不能 (Incapacitated)";
        header.style.margin = "20px 0 5px 0";
        header.style.paddingBottom = "5px";
        header.style.borderBottom = "2px solid #c0392b";
        header.style.color = "#c0392b";
        container.appendChild(header);
        deadChars.forEach(c => container.appendChild(createCharRow(c, true)));
    }
}

// キャラクターをデフォルト位置に配置
// キャラクターをデフォルト位置に配置
function placeCharacterToDefaultPosition(char) {


    // フィールドの中央をグリッド座標で指定（25x25の中央 = 12, 12）
    const defaultX = 12;
    const defaultY = 12;

    // 空き位置を探す（グリッド座標）
    const position = findEmptyPosition(defaultX, defaultY);


    // socketオブジェクトの確認
    const socketToUse = window.socket || socket;
    if (!socketToUse) {
        console.error('[ERROR] socket is not initialized!');
        alert('サーバーとの接続エラーです。ページをリロードしてください。');
        return;
    }

    // サーバーに移動を通知（グリッド座標）

    socketToUse.emit('request_move_character', {
        room: currentRoomName,
        character_id: char.id,
        x: position.x,
        y: position.y
    });


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
