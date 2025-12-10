// --- 8. バトルフィールドタブ ---

let currentLogFilter = 'all';
let globalSkillMetadata = {};

// スキルメタデータを取得してキャッシュする
async function fetchSkillMetadata() {
    try {
        const response = await fetchWithSession('/api/get_skill_metadata');
        if (response.ok) {
            globalSkillMetadata = await response.json();
            console.log("Skill metadata loaded:", Object.keys(globalSkillMetadata).length);
        }
    } catch (e) {
        console.warn("Failed to load skill metadata:", e);
    }
}

function loadCharacterFromJSON(type, jsonString, resultElement) {
    // (この関数は変更なし)
    if (!jsonString) {
        resultElement.textContent = 'JSONを貼り付けてください。';
        resultElement.style.color = 'red';
        return false;
    }
    try {
        const charData = JSON.parse(jsonString);
        const name = charData.data.name;
        const hpStatus = charData.data.status.find(s => s.label === 'HP');
        const mpStatus = charData.data.status.find(s => s.label === 'MP');
        const initialStates = [
            { name: 'FP', value: 0 },
            { name: '出血', value: 0 },
            { name: '破裂', value: 0 },
            { name: '亀裂', value: 0 },
            { name: '戦慄', value: 0 },
            { name: '荊棘', value: 0 }
        ];
        const newCharacter = {
            name: name || '名前不明',
            hp: hpStatus ? hpStatus.value : 0,
            maxHp: hpStatus ? hpStatus.max : 0,
            mp: mpStatus ? mpStatus.value : 0,
            maxMp: mpStatus ? mpStatus.max : 0,
            params: charData.data.params,
            commands: charData.data.commands,
            states: initialStates,
            type: type,
            color: (type === 'ally') ? '#007bff' : '#dc3545',
            speedRoll: 0,
            hasActed: false,
            gmOnly: (currentUserAttribute === 'GM')
        };
        socket.emit('request_add_character', {
             room: currentRoomName,
             charData: newCharacter
        });
        resultElement.textContent = `読込成功: ${name} を ${type === 'ally' ? '味方' : '敵'}として追加リクエスト`;
        resultElement.style.color = 'green';
        return true;
    } catch (error) {
        resultElement.textContent = 'JSONの形式が正しくありません。エラー: ' + error.message;
        resultElement.style.color = 'red';
        return false;
    }
}

// static/js/tab_battlefield.js

function logToBattleLog(logData) {
    const logArea = document.getElementById('log-area');
    if (!logArea) return;
    const logLine = document.createElement('div');
    logLine.className = `log-line ${logData.type}`;

    // === ▼▼▼ 追加: チャットメッセージの装飾 (既存ロジック) ▼▼▼
    if (logData.type === 'chat') {
        logLine.innerHTML = `<span class="chat-user">${logData.user}:</span> <span class="chat-message">${logData.message}</span>`;
    } else {
        logLine.innerHTML = logData.message;
    }

    // === ▼▼▼ 追加: 現在のフィルタ適用 ▼▼▼
    // 'chat' フィルタ時: typeが 'chat' 以外なら隠す
    if (currentLogFilter === 'chat' && logData.type !== 'chat') {
        logLine.classList.add('hidden-log');
    }
    // 'system' フィルタ時: typeが 'chat' なら隠す
    else if (currentLogFilter === 'system' && logData.type === 'chat') {
        logLine.classList.add('hidden-log');
    }
    // === ▲▲▲ 追加ここまで ▲▲▲

    logArea.appendChild(logLine);

    // 非表示のログが追加された場合はスクロールしない
    if (!logLine.classList.contains('hidden-log')) {
        logArea.scrollTop = logArea.scrollHeight;
    }
}

// === ▼▼▼ 追加: ログ履歴を一括描画する関数 ▼▼▼ ===
function renderLogHistory(logs) {
    const logArea = document.getElementById('log-area');
    if (!logArea || !logs || !Array.isArray(logs)) return;

    // 既にログが表示されている（ヘッダー以外がある）場合は、再描画しない（スクロール飛び防止）
    // ただし、初期状態（"ログを読み込み中..."）の場合は描画する
    const currentLines = logArea.querySelectorAll('.log-line');
    // .info クラスを持つ要素が1つだけなら「初期状態」とみなす
    if (currentLines.length > 1) {
        return;
    }

    logArea.innerHTML = '<p class="log-line info">--- 過去ログ ---</p>';

    logs.forEach(logData => {
        logToBattleLog(logData);
    });
}
// === ▲▲▲ 追加ここまで ▲▲▲ ===


function safeMathEvaluate(expression) {
    // (この関数は変更なし)
    try {
        const sanitized = expression.replace(/[^-()\d/*+.]/g, '');
        return new Function('return ' + sanitized)();
    } catch (e) { console.error("Safe math eval error:", e); return 0; }
}

function rollDiceCommand(command) {
    // (この関数は変更なし)
    let calculation = command.replace(/【.*?】/g, '').trim();
    let details = calculation;
    const diceRegex = /(\d+)d(\d+)/g;
    let match;
    const allDiceDetails = [];
    while ((match = diceRegex.exec(calculation)) !== null) {
        const numDice = parseInt(match[1]);
        const numFaces = parseInt(match[2]);
        let sum = 0;
        const rolls = [];
        for (let i = 0; i < numDice; i++) {
            const roll = Math.floor(Math.random() * numFaces) + 1;
            rolls.push(roll);
            sum += roll;
        }
        allDiceDetails.push({ original: match[0], details: `(${rolls.join('+')})`, sum: sum });
    }
    for (let i = allDiceDetails.length - 1; i >= 0; i--) {
        const roll = allDiceDetails[i];
        details = details.replace(roll.original, roll.details);
        calculation = calculation.replace(roll.original, String(roll.sum));
    }
    const total = safeMathEvaluate(calculation);
    return { total: total, details: details };
}

// static/js/tab_battlefield.js

function renderTokenList() {
    const allyContainer = document.getElementById('ally-list-column');
    const enemyContainer = document.getElementById('enemy-list-column');
    if (!allyContainer || !enemyContainer) return;

    allyContainer.innerHTML = '';
    enemyContainer.innerHTML = '';

    if (battleState.characters.length === 0) {
        allyContainer.innerHTML = '<p class="char-token-placeholder">キャラクターが読み込まれていません。</p>';
        return;
    }

    // アイコンのマッピング定義
    const iconMap = {
        '出血': 'bleed.png',
        '破裂': 'rupture.png',
        '亀裂': 'fissure.png',
        '戦慄': 'fear.png',
        '荊棘': 'thorns.png'
    };

    battleState.characters.forEach(char => {
        const token = document.createElement('div');
        token.className = 'char-token';
        token.dataset.id = char.id;
        token.style.borderLeftColor = char.color;

        // --- 1. HP/MP バーの計算 ---
        const hpPercent = Math.max(0, Math.min(100, (char.hp / char.maxHp) * 100));
        const mpPercent = Math.max(0, Math.min(100, (char.mp / char.maxMp) * 100));

        // FPは最大値の概念が曖昧ですが、とりあえず100くらいを基準にゲージ化してみます（あるいはゲージなしでも可）
        const fpState = char.states.find(s => s.name === 'FP');
        const fpValue = fpState ? fpState.value : 0;
        // FPは上限がないためゲージは飾りですが、視覚的統一のために少し動かします(最大15想定)
        const fpPercent = Math.min(100, (fpValue / 15) * 100);

        // --- 2. 状態異常アイコンの生成 ---
        const activeStates = char.states.filter(s => {
            return !['HP', 'MP', 'FP'].includes(s.name) && s.value !== 0;
        });

        let debuffsHtml = '';
        if (activeStates.length > 0) {
            let itemsHtml = '';
            activeStates.forEach(s => {
                let iconHtml = '';

                // 特定のデバフ画像がある場合
                if (iconMap[s.name]) {
                    iconHtml = `<img src="images/${iconMap[s.name]}" class="status-icon-img" alt="${s.name}">`;
                }
                // その他の数値変動 (矢印対応)
                else {
                    if (s.value > 0) {
                        // 正の数 = 通常はバフや蓄積値 (上矢印)
                        iconHtml = `<span class="arrow-icon arrow-up">▲</span>`;
                    } else {
                        // 負の数 = デバフ (下矢印)
                        iconHtml = `<span class="arrow-icon arrow-down">▼</span>`;
                    }
                }

                itemsHtml += `
                    <div class="token-debuff-item">
                        ${iconHtml}
                        <span>${s.name}: ${s.value}</span>
                    </div>
                `;
            });
            debuffsHtml = `<div class="token-debuff-list">${itemsHtml}</div>`;
        }

        // --- 3. HTML構築 ---
        token.innerHTML = `
            <h4 class="token-name" style="margin-bottom: 5px;">${char.name}</h4>

            <div class="token-stats-grid" style="display: grid; grid-template-columns: 1fr 1fr 60px; gap: 10px; align-items: end;">
                <div class="stat-group">
                    <div style="font-size: 0.85em; display:flex; justify-content:space-between;">
                        <strong>HP</strong> <span>${char.hp}/${char.maxHp}</span>
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill hp-fill" style="width: ${hpPercent}%;"></div>
                    </div>
                </div>

                <div class="stat-group">
                    <div style="font-size: 0.85em; display:flex; justify-content:space-between;">
                        <strong>MP</strong> <span>${char.mp}/${char.maxMp}</span>
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill mp-fill" style="width: ${mpPercent}%;"></div>
                    </div>
                </div>

                <div class="stat-group">
                    <div style="font-size: 0.85em; text-align: center;">
                        <strong>FP</strong>: ${fpValue}
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill fp-fill" style="width: ${fpPercent}%;"></div>
                    </div>
                </div>
            </div>

            ${debuffsHtml}
        `;

        if (char.type === 'ally') {
            allyContainer.appendChild(token);
        } else {
            enemyContainer.appendChild(token);
        }
    });
}

// static/js/tab_battlefield.js
// static/js/tab_battlefield.js

function setupActionColumn(prefix) {
    const actorSelect = document.getElementById(`actor-${prefix}`);
    const targetSelect = document.getElementById(`target-${prefix}`);
    const skillSelect = document.getElementById(`skill-${prefix}`);
    const generateBtn = document.getElementById(`generate-btn-${prefix}`);
    const declareBtn = document.getElementById(`declare-btn-${prefix}`);
    const powerDisplay = document.getElementById(`power-display-${prefix}`);
    const commandDisplay = document.getElementById(`command-display-${prefix}`);
    const hiddenCommand = document.getElementById(`hidden-command-${prefix}`);
    const previewBox = document.getElementById(`skill-preview-${prefix}`);

    // 広域UIの要素取得
    const wideContainer = document.getElementById('wide-area-container');
    const wideList = document.getElementById('wide-defenders-list');
    const wideModeDisplay = document.getElementById('wide-area-mode-display');
    const executeWideBtn = document.getElementById('execute-wide-action-btn');

    if (!actorSelect) return;

    function populateSelectors() {
        const currentActor = actorSelect.value;
        const currentTarget = targetSelect.value;

        let actorOptions = '<option value="">-- 使用者 --</option>';
        let targetOptions = '<option value="">-- 対象 --</option>';

        battleState.characters.forEach(char => {
            const option = `<option value="${char.id}">${char.name}</option>`;

            // 攻撃側カラムの場合の特殊処理（再回避ロック中のキャラはTargetのみ）
            if (prefix === 'attacker') {
                const reEvasionBuff = char.special_buffs ? char.special_buffs.find(b => b.name === "再回避ロック") : null;
                if (reEvasionBuff) {
                    targetOptions += option;
                    return; // Actorには追加しない
                }
            }

            targetOptions += option;

            if (char.gmOnly && currentUserAttribute !== 'GM') {
                // GM専用キャラはActorリストには出さない（Targetには出る）
            } else {
                actorOptions += option;
            }
        });

        actorSelect.innerHTML = actorOptions;
        targetSelect.innerHTML = targetOptions;

        // 選択状態を復元（存在すれば）
        if (currentActor) actorSelect.value = currentActor;
        if (currentTarget) targetSelect.value = currentTarget;
    }

    function updateSkillDropdown(actorId) {
        skillSelect.innerHTML = '<option value="">-- スキル --</option>';
        if (!actorId) return;
        const actor = battleState.characters.find(c => c.id === actorId);
        if (!actor || !actor.commands) return;

        const reEvasionBuff = actor.special_buffs ? actor.special_buffs.find(b => b.name === "再回避ロック") : null;

        const commandsStr = actor.commands;
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;

        while ((match = regex.exec(commandsStr)) !== null) {
            const skillId = match[1];
            const customName = match[2];

            if (reEvasionBuff && skillId !== reEvasionBuff.skill_id) {
                continue;
            }

            // === ▼▼▼ 修正: 対応側(defender)の場合、広域スキルを選択肢から除外 ▼▼▼
            if (prefix === 'defender') {
                const meta = globalSkillMetadata[skillId];
                // メタデータがある場合のみ判定（ロード前は表示されるが、通常はロード済み）
                if (meta) {
                    const cat = meta.category || "";
                    const dist = meta.distance || "";
                    const tags = meta.tags || [];

                    // 広域タグ/分類/距離が含まれていればリストに追加しない
                    if (
                        cat.includes("広域") || dist.includes("広域") ||
                        tags.includes("広域-個別") || tags.includes("広域-合算")
                    ) {
                        continue;
                    }
                }
            }
            // === ▲▲▲ 修正ここまで ▲▲▲

            const option = document.createElement('option');
            option.value = skillId;
            option.textContent = `${skillId}: ${customName}`;
            option.dataset.customName = customName;
            skillSelect.appendChild(option);
        }

        if (reEvasionBuff) {
            skillSelect.value = reEvasionBuff.skill_id;
            skillSelect.disabled = true;
        } else {
            skillSelect.disabled = false;
        }
    }

    // --- 「威力計算」ボタン ---
    if (!generateBtn.dataset.listenerAttached) {
        generateBtn.dataset.listenerAttached = 'true';
        generateBtn.addEventListener('click', () => {
            const actorId = actorSelect.value;
            let targetId = targetSelect.value;
            const selectedSkill = skillSelect.options[skillSelect.selectedIndex];

            if (!selectedSkill || !actorId) {
                powerDisplay.value = 'エラー: 使用者とスキルを指定してください。';
                return;
            }

            const skillId = selectedSkill.value;
            const customSkillName = selectedSkill.dataset.customName;

            // 広域モードの場合、ターゲットIDは自分自身を入れておく
            if (!targetId) targetId = actorId;

            socket.emit('request_skill_declaration', {
                room: currentRoomName,
                prefix: prefix,
                actor_id: actorId,
                target_id: targetId,
                skill_id: skillId,
                custom_skill_name: customSkillName
            });
        });
    }

    // --- 「宣言」ボタン ---
    if (!declareBtn.dataset.listenerAttached) {
        declareBtn.dataset.listenerAttached = 'true';
        declareBtn.addEventListener('click', () => {
            actorSelect.disabled = true;
            targetSelect.disabled = true;
            skillSelect.disabled = true;
            generateBtn.disabled = true;
            declareBtn.disabled = true;
            powerDisplay.style.borderColor = "#4CAF50";
            powerDisplay.style.fontWeight = "bold";
            commandDisplay.style.borderColor = "#4CAF50";

            if (prefix === 'defender') {
                // 攻撃側のロックはそのまま、対応側の宣言完了
            }
        });
    }

    // --- UIリセット ---
    const resetUI = () => {
        generateBtn.disabled = false;
        skillSelect.disabled = false;

        if (prefix === 'attacker') {
            actorSelect.disabled = false;
            targetSelect.disabled = false;

            // 広域UIを閉じて通常UIを戻す
            if (wideContainer) {
                wideContainer.style.display = 'none';
                const defCol = document.getElementById('action-column-defender');
                if (defCol) defCol.style.display = 'flex';
            }
        } else {
            // 対応側は常にロック（攻撃側の操作に追従するため）
            actorSelect.disabled = true;
            targetSelect.disabled = true;
        }

        powerDisplay.value = "[威力計算待ち]";
        commandDisplay.value = "[コマンドプレビュー]";
        hiddenCommand.value = "";

        const senritsuField = document.getElementById(`hidden-senritsu-${prefix}`);
        if (senritsuField) senritsuField.value = "0";

        declareBtn.disabled = true;
        powerDisplay.style.borderColor = "";
        powerDisplay.style.fontWeight = "normal";
        commandDisplay.style.borderColor = "";

        if(previewBox) {
            previewBox.innerHTML = '';
            previewBox.style.display = 'none';
        }
    };

    // --- リスナー設定 ---
    if (!actorSelect.dataset.listenerAttached) {
        actorSelect.dataset.listenerAttached = 'true';
        actorSelect.addEventListener('change', (e) => {
            updateSkillDropdown(e.target.value);
            resetUI();

            // 攻撃側を変更したら、対応側の「対象」も連動させる
            if (prefix === 'attacker') {
                const defenderTargetSelect = document.getElementById('target-defender');
                if (defenderTargetSelect) {
                    defenderTargetSelect.value = e.target.value;
                    // 正しくイベントを発火させる
                    defenderTargetSelect.dispatchEvent(new Event('change'));
                }
            }
        });
    }

    if (!targetSelect.dataset.listenerAttached) {
        targetSelect.dataset.listenerAttached = 'true';
        targetSelect.addEventListener('change', (e) => {
            resetUI();

            // 攻撃側の「対象」を変更したら、対応側の「使用者」も連動させる
            if (prefix === 'attacker') {
                const targetId = e.target.value;
                const defenderActorSelect = document.getElementById('actor-defender');
                if (defenderActorSelect) {
                    defenderActorSelect.value = targetId;
                    // 対応側のスキル欄を更新するためにイベント発火は不要だが、内部ロジックを呼ぶ
                    if (window.defenderCol) {
                        window.defenderCol.updateSkillDropdown(targetId);
                    }
                }
            }
        });
    }

    if (!skillSelect.dataset.listenerAttached) {
        skillSelect.dataset.listenerAttached = 'true';
        skillSelect.addEventListener('change', (e) => {
            resetUI();

            // 広域スキルの判定処理
            if (prefix === 'attacker') {
                const selectedOption = skillSelect.options[skillSelect.selectedIndex];
                const skillId = selectedOption.value;
                if (!skillId) return;

                fetchWithSession(`/get_skill?id=${skillId}`)
                    .then(res => res.json())
                    .then(skillData => {
                        const cat = skillData['分類'] || '';
                        const dist = skillData['距離'] || '';
                        const tags = skillData['tags'] || [];
                        let wideMode = null;

                        if ((cat.includes('広域') && cat.includes('個別')) ||
                            (dist.includes('広域') && dist.includes('個別')) ||
                            tags.includes('広域-個別')) {
                            wideMode = 'individual';
                        }
                        else if ((cat.includes('広域') && cat.includes('合算')) ||
                                 (dist.includes('広域') && dist.includes('合算')) ||
                                 tags.includes('広域-合算')) {
                            wideMode = 'combined';
                        }

                        if (wideMode) {
                            document.getElementById('action-column-defender').style.display = 'none';
                            wideContainer.style.display = 'block';
                            wideModeDisplay.textContent = (wideMode === 'individual') ? '個別 (全員と1回ずつマッチ)' : '合算 (全員の防御値を合計)';
                            renderWideDefendersList(wideMode);
                        }
                    })
                    .catch(err => console.error("Skill fetch error:", err));
            }
        });
    }

// === ▼▼▼ 修正: 広域対象リスト描画関数 (広域スキル除外対応版) ▼▼▼
    function renderWideDefendersList(mode) {
        if (!wideList) return;
        wideList.innerHTML = '';
        const actorId = actorSelect.value;
        const actor = battleState.characters.find(c => c.id === actorId);
        if (!actor) return;

        const targetType = (actor.type === 'ally') ? 'enemy' : 'ally';
        const targets = battleState.characters.filter(c => c.type === targetType && c.hp > 0);

        if (targets.length === 0) {
            wideList.innerHTML = '<div style="padding:10px;">対象となるキャラクターがいません。</div>';
            executeWideBtn.disabled = true;
            return;
        }
        executeWideBtn.disabled = false;

        targets.forEach((tgt, index) => {
            const row = document.createElement('div');
            row.className = 'wide-defender-row';
            row.dataset.rowId = `wide-row-${tgt.id}`;

            let skillOptions = '<option value="">(スキルなし / 通常防御)</option>';
            if (tgt.commands) {
                const regex = /【(.*?)\s+(.*?)】/g;
                let match;
                while ((match = regex.exec(tgt.commands)) !== null) {
                    const sId = match[1];
                    const sName = match[2];

                    // ▼▼▼ 追加: 広域スキルの除外判定 ▼▼▼
                    let isWide = false;
                    const meta = globalSkillMetadata[sId];
                    if (meta) {
                        const cat = meta.category || "";
                        const dist = meta.distance || "";
                        const tags = meta.tags || [];
                        if (
                            cat.includes("広域") || dist.includes("広域") ||
                            tags.includes("広域-個別") || tags.includes("広域-合算")
                        ) {
                            isWide = true;
                        }
                    }
                    // 広域スキルならリストに追加しない
                    if (isWide) continue;
                    // ▲▲▲ 追加ここまで ▲▲▲

                    skillOptions += `<option value="${sId}">${sId}: ${sName}</option>`;
                }
            }

            // UI構築 (既存のまま)
            row.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <label style="font-weight:bold;">${tgt.name}</label>
                    <span class="wide-status-badge" style="font-size:0.8em; color:#666;">未宣言</span>
                </div>

                <div style="display:flex; gap:5px; margin-bottom:5px;">
                    <select class="wide-def-skill-select" data-id="${tgt.id}" style="flex-grow:1; padding:4px; border:1px solid #ccc; border-radius:3px;">
                        ${skillOptions}
                    </select>
                    <button class="wide-calc-btn action-btn" data-id="${tgt.id}" style="font-size:0.8em; padding:2px 8px;">計算</button>
                    <button class="wide-declare-btn action-btn declare-btn" data-id="${tgt.id}" disabled style="font-size:0.8em; padding:2px 8px;">宣言</button>
                </div>

                <div class="wide-result-area" style="font-size:0.85em; background:#f9f9f9; padding:4px; border-radius:3px; min-height:1.2em; color:#333;">
                    [計算待ち]
                </div>

                <input type="hidden" class="wide-final-command" value="">
            `;
            wideList.appendChild(row);

            // --- イベント設定 (既存のまま) ---
            const calcBtn = row.querySelector('.wide-calc-btn');
            const declBtn = row.querySelector('.wide-declare-btn');
            const skillSel = row.querySelector('.wide-def-skill-select');
            const resArea = row.querySelector('.wide-result-area');
            const finalCmdInput = row.querySelector('.wide-final-command');
            const statusBadge = row.querySelector('.wide-status-badge');

            calcBtn.onclick = () => {
                const sId = skillSel.value;
                resArea.textContent = "計算中...";
                resArea.style.color = "#333";
                socket.emit('request_skill_declaration', {
                    room: currentRoomName,
                    prefix: `wide-def-${tgt.id}`,
                    actor_id: tgt.id,
                    target_id: actorId,
                    skill_id: sId,
                    custom_skill_name: ""
                });
            };

            declBtn.onclick = () => {
                skillSel.disabled = true;
                calcBtn.disabled = true;
                declBtn.disabled = true;
                resArea.style.borderColor = "#4CAF50";
                resArea.style.fontWeight = "bold";
                resArea.style.color = "green";
                statusBadge.textContent = "宣言済";
                statusBadge.style.color = "green";
            };

            skillSel.onchange = () => {
                calcBtn.disabled = false;
                declBtn.disabled = true;
                resArea.textContent = "[計算待ち]";
                resArea.style.color = "#333";
                resArea.style.fontWeight = "normal";
                statusBadge.textContent = "未宣言";
                statusBadge.style.color = "#666";
                finalCmdInput.value = "";
            };
        });

        // 実行ボタン (既存のまま)
        executeWideBtn.onclick = () => {
            const actorCmd = document.getElementById('hidden-command-attacker').value;
            if (!actorCmd) {
                alert('先に攻撃側の「威力計算」を行い、コマンドを確定させてください。');
                return;
            }

            const defenders = [];
            const rows = wideList.querySelectorAll('.wide-defender-row');
            rows.forEach(r => {
                const charId = r.querySelector('.wide-def-skill-select').dataset.id;
                const skillId = r.querySelector('.wide-def-skill-select').value;
                const finalCmd = r.querySelector('.wide-final-command').value;
                defenders.push({
                    id: charId,
                    skillId: skillId,
                    command: finalCmd
                });
            });

            if (confirm(`${mode === 'individual' ? '個別' : '合算'}マッチを実行しますか？`)) {
                socket.emit('request_wide_match', {
                    room: currentRoomName,
                    actorId: actorId,
                    skillId: skillSelect.value,
                    mode: mode,
                    commandActor: actorCmd,
                    defenders: defenders
                });
                resetUI();
                actorSelect.value = "";
                actorSelect.dispatchEvent(new Event('change'));
            }
        };
    }

    populateSelectors();
    return { populateSelectors, updateSkillDropdown };
}


function renderTimeline() {
    // (この関数は変更なし)
    const roundCounterElem = document.getElementById('round-counter');
    const timelineListElem = document.getElementById('timeline-list');
    if (!timelineListElem || !roundCounterElem) return;
    timelineListElem.innerHTML = '';
    roundCounterElem.textContent = parseInt(battleState.round) || 0;
    battleState.timeline.forEach(charId => {
        const char = battleState.characters.find(c => c.id === charId);
        if (!char) return;
        const item = document.createElement('div');
        item.className = `timeline-item ${char.type}`;
        if (char.hasActed) {
            item.classList.add('acted');
        }
        item.innerHTML = `
            <span class="timeline-char-name">${char.name}</span>
            <span class="timeline-speed-roll">速度値: ${char.speedRoll}</span>
        `;
        timelineListElem.appendChild(item);
    });
}

function setupBattlefieldTab() {
    const openLoadModalBtn = document.getElementById('open-char-load-modal-btn');
    if (openLoadModalBtn) {
        openLoadModalBtn.addEventListener('click', openCharLoadModal);
    }

    // ログ履歴の描画
    if (battleState && battleState.logs) {
        renderLogHistory(battleState.logs);
    }

    // ソケットリスナー: ログ同期 (重複登録防止)
    if (window.battleLogStateListener) {
        socket.off('state_updated', window.battleLogStateListener);
    }
    window.battleLogStateListener = (state) => {
        if (document.getElementById('log-area')) {
            renderLogHistory(state.logs);
        }
    };
    socket.on('state_updated', window.battleLogStateListener);

    const leftColumn = document.getElementById('battlefield-left-column');
    if (!leftColumn) {
        console.error("Battlefield left column not found!");
        return;
    }
    if (!leftColumn.dataset.listenerAttached) {
        leftColumn.dataset.listenerAttached = 'true';
        leftColumn.addEventListener('click', (e) => {
            const token = e.target.closest('.char-token');
            if (token) {
                const charId = token.dataset.id;
                const char = battleState.characters.find(c => c.id === charId);
                if (char && char.gmOnly && currentUserAttribute !== 'GM') {
                    return;
                }
                openCharacterModal(charId);
            }
        });
    }


    // === ▼▼▼ 追加: ログフィルタボタンのイベント設定 ▼▼▼
    const filterButtons = document.querySelectorAll('.filter-btn');
    const logArea = document.getElementById('log-area');

    filterButtons.forEach(btn => {
        if (btn.dataset.listenerAttached) return;
        btn.dataset.listenerAttached = 'true';

        btn.addEventListener('click', () => {
            // 1. アクティブボタンの切り替え
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // 2. フィルタ状態の更新
            currentLogFilter = btn.dataset.filter; // 'all', 'chat', 'system'

            // 3. 既存ログの表示切り替え
            if (logArea) {
                const logs = logArea.querySelectorAll('.log-line');
                logs.forEach(line => {
                    // クラス名に 'chat' が含まれているかで判定
                    // (※logToBattleLogで生成時に logData.type がクラスとして付与されている前提)
                    const isChat = line.classList.contains('chat');

                    if (currentLogFilter === 'all') {
                        line.classList.remove('hidden-log');
                    } else if (currentLogFilter === 'chat') {
                        if (isChat) line.classList.remove('hidden-log');
                        else line.classList.add('hidden-log');
                    } else if (currentLogFilter === 'system') {
                        if (!isChat) line.classList.remove('hidden-log');
                        else line.classList.add('hidden-log');
                    }
                });
                logArea.scrollTop = logArea.scrollHeight;
            }
        });
    });
    // === ▲▲▲ 追加ここまで ▲▲▲

    window.attackerCol = setupActionColumn('attacker');
    window.defenderCol = setupActionColumn('defender');

    const actorAttacker = document.getElementById('actor-attacker');
    const targetAttacker = document.getElementById('target-attacker');
    const actorDefender = document.getElementById('actor-defender');
    const targetDefender = document.getElementById('target-defender');

    if (!targetAttacker.dataset.listenerAttached_auto) {
        targetAttacker.dataset.listenerAttached_auto = 'true';
        targetAttacker.addEventListener('change', (e) => {
            const targetId = e.target.value;
            if (targetId) {
                actorDefender.value = targetId;
                window.defenderCol.updateSkillDropdown(targetId);
            }
        });
    }

    if (!actorAttacker.dataset.listenerAttached_auto) {
        actorAttacker.dataset.listenerAttached_auto = 'true';
        actorAttacker.addEventListener('change', (e) => {
            const actorId = e.target.value;
            if (actorId) {
                targetDefender.value = actorId;
            }
        });
    }

    const matchStartBtn = document.getElementById('match-start-btn');
    const matchResultArea = document.getElementById('match-result-area');
    const hiddenCmdAttacker = document.getElementById('hidden-command-attacker');
    const hiddenCmdDefender = document.getElementById('hidden-command-defender');

    // UIリセット関数
// UIリセット関数
    const resetAllActionUI = () => {
        const prefixes = ['attacker', 'defender'];
        prefixes.forEach(prefix => {
            const actorEl = document.getElementById(`actor-${prefix}`);
            const targetEl = document.getElementById(`target-${prefix}`);

            if (prefix === 'attacker') {
                actorEl.disabled = false;
                targetEl.disabled = false;
            } else {
                actorEl.disabled = true;
                targetEl.disabled = true;
            }

            document.getElementById(`skill-${prefix}`).disabled = false;
            actorEl.value = "";
            targetEl.value = "";

            document.getElementById(`generate-btn-${prefix}`).disabled = false;
            document.getElementById(`declare-btn-${prefix}`).disabled = true;

            const powerDisplay = document.getElementById(`power-display-${prefix}`);
            powerDisplay.value = "[威力計算待ち]";
            powerDisplay.style.borderColor = "";
            powerDisplay.style.fontWeight = "normal";

            const commandDisplay = document.getElementById(`command-display-${prefix}`);
            commandDisplay.value = "[コマンドプレビュー]";
            commandDisplay.style.borderColor = "";

            document.getElementById(`hidden-command-${prefix}`).value = "";

            const senritsuField = document.getElementById(`hidden-senritsu-${prefix}`);
            if (senritsuField) senritsuField.value = "0";

            const previewBox = document.getElementById(`skill-preview-${prefix}`);
            if(previewBox) {
                previewBox.innerHTML = '';
                previewBox.style.display = 'none';
            }
        });

        if (window.attackerCol) window.attackerCol.updateSkillDropdown(null);
        if (window.defenderCol) window.defenderCol.updateSkillDropdown(null);
        if (window.attackerCol) window.attackerCol.populateSelectors();
        if (window.defenderCol) window.defenderCol.populateSelectors();
    };

    // 次のアクター選択
    const selectNextActor = () => {
        const nextActor = battleState.characters.find(c => !c.hasActed);
        if (nextActor) {
            const actorSelect = document.getElementById('actor-attacker');
            actorSelect.value = nextActor.id;
            actorSelect.dispatchEvent(new Event('change'));
        } else {
            alert("全てのキャラクターが行動済みです。「R終了処理」を行ってください。");
        }
    };

    if (!matchStartBtn.dataset.listenerAttached) {
        matchStartBtn.dataset.listenerAttached = 'true';
        matchStartBtn.addEventListener('click', () => {
            const actorIdA = actorAttacker.value;
            const actorIdD = actorDefender.value;

            const senritsuA = document.getElementById('hidden-senritsu-attacker').value || 0;
            const senritsuD = document.getElementById('hidden-senritsu-defender').value || 0;

            if (!hiddenCmdAttacker.value || !hiddenCmdDefender.value || !actorIdA || !actorIdD) {
                matchResultArea.innerHTML = 'エラー: 攻撃側と対応側の両方が正しく「宣言」されていません。';
                return;
            }

            socket.emit('request_match', {
                room: currentRoomName,
                actorIdA: actorIdA,
                actorIdD: actorIdD,
                commandA: hiddenCmdAttacker.value,
                commandD: hiddenCmdDefender.value,
                actorNameA: actorAttacker.options[actorAttacker.selectedIndex].text,
                actorNameD: actorDefender.options[actorDefender.selectedIndex].text,
                senritsuPenaltyA: senritsuA,
                senritsuPenaltyD: senritsuD
            });
            matchResultArea.innerHTML = '... マッチを実行中 ...';

            resetAllActionUI();
        });
    }

    // 宣言結果受信リスナー
    socket.off('skill_declaration_result');
    socket.on('skill_declaration_result', (data) => {
        const prefix = data.prefix;

        // === ▼▼▼ 追加: 広域防御用の処理分岐 ▼▼▼
        // prefix が "wide-def-" で始まる場合（広域防御の個別計算）
        if (prefix && prefix.startsWith('wide-def-')) {
            const charId = prefix.replace('wide-def-', '');
            // 該当する行を探す
            const row = document.querySelector(`.wide-defender-row[data-row-id="wide-row-${charId}"]`);
            if (row) {
                const resArea = row.querySelector('.wide-result-area');
                const declBtn = row.querySelector('.wide-declare-btn');
                const finalCmdInput = row.querySelector('.wide-final-command');

                if (data.error) {
                    resArea.textContent = data.final_command; // エラーメッセージ
                    resArea.style.color = "red";
                    declBtn.disabled = true;
                } else {
                    // 成功時: 結果を表示し、隠しフィールドにコマンドを保存
                    resArea.textContent = `威力: ${data.min_damage}～${data.max_damage} (${data.final_command})`;
                    resArea.style.color = "blue";
                    finalCmdInput.value = data.final_command;
                    declBtn.disabled = false; // 宣言ボタンを有効化
                }
            }
            return; // ここで処理終了（下の通常処理には行かせない）
        }
        // === ▲▲▲ 追加ここまで ▲▲▲

        // --- 以下、既存の通常処理 (攻撃側・対応側パネル用) ---
        const powerDisplay = document.getElementById(`power-display-${prefix}`);
        const commandDisplay = document.getElementById(`command-display-${prefix}`);
        const hiddenCommand = document.getElementById(`hidden-command-${prefix}`);
        const hiddenSenritsu = document.getElementById(`hidden-senritsu-${prefix}`);
        const declareBtn = document.getElementById(`declare-btn-${prefix}`);
        const generateBtn = document.getElementById(`generate-btn-${prefix}`);
        const previewBox = document.getElementById(`skill-preview-${prefix}`);

        if (!powerDisplay) return;

        generateBtn.disabled = false;

        if (data.error) {
            powerDisplay.value = data.final_command;
            commandDisplay.value = "--- エラー ---";
            powerDisplay.style.borderColor = "#dc3545";
            hiddenCommand.value = "";
            declareBtn.disabled = true;
            if(previewBox) previewBox.style.display = 'none';
            return;
        }

        powerDisplay.value = `威力: ${data.min_damage} ～ ${data.max_damage}`;
        commandDisplay.value = data.final_command;

        hiddenCommand.value = data.final_command;
        if (hiddenSenritsu) {
            hiddenSenritsu.value = data.senritsu_penalty || 0;
        }

        declareBtn.disabled = false;
        powerDisplay.style.borderColor = "";

        if (previewBox && data.skill_details) {
            const d = data.skill_details;
            const skillSelect = document.getElementById(`skill-${prefix}`);
            const skillName = skillSelect.options[skillSelect.selectedIndex].text || "スキル詳細";

            previewBox.innerHTML = `
                <div style="border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-bottom: 5px;">
                    <strong>${skillName}</strong><br>
                    <span style="font-size: 0.85em; color: #555;">
                        [${d['分類']}] / 距離:${d['距離']} / 属性:${d['属性']}
                    </span>
                </div>
                <div style="font-size: 0.9em; line-height: 1.4;">
                    ${d['使用時効果'] ? `<div><strong>[使用時]:</strong> ${d['使用時効果']}</div>` : ''}
                    ${d['発動時効果'] ? `<div><strong>[発動時]:</strong> ${d['発動時効果']}</div>` : ''}
                    ${d['特記'] ? `<div><strong>[特記]:</strong> ${d['特記']}</div>` : ''}
                </div>
            `;
            previewBox.style.display = 'block';
        }

        if (prefix === 'attacker' && data.is_one_sided_attack) {
            const defenderPower = document.getElementById('power-display-defender');
            const defenderCommand = document.getElementById('command-display-defender');
            const hiddenDefender = document.getElementById('hidden-command-defender');
            const declareBtnDefender = document.getElementById('declare-btn-defender');
            const defenderPreview = document.getElementById('skill-preview-defender');

            if (defenderPower) {
                const cmd = '【一方攻撃（行動済）】';
                defenderPower.value = "--- (一方攻撃) ---";
                defenderCommand.value = cmd;
                hiddenDefender.value = cmd;

                document.getElementById('actor-defender').disabled = true;
                document.getElementById('target-defender').disabled = true;
                document.getElementById('skill-defender').disabled = true;
                document.getElementById('generate-btn-defender').disabled = true;
                declareBtnDefender.disabled = true;
                defenderPower.style.borderColor = "#4CAF50";
                defenderPower.style.fontWeight = "bold";
                defenderCommand.style.borderColor = "#4CAF50";

                if(defenderPreview) defenderPreview.style.display = 'none';
            }
        }

        if (data.is_instant_action) {
            resetAllActionUI();
        }
    });

    // タイムライン・GMボタン
    const roundStartBtn = document.getElementById('round-start-btn');
    const roundEndBtn = document.getElementById('round-end-btn');
    const battleStartBtn = document.getElementById('battle-start-btn');
    const combatNextBtn = document.getElementById('combat-next-btn');
    const gmResetBtn = document.getElementById('gm-reset-action-btn');

    if (currentUserAttribute !== 'GM') {
        roundStartBtn.style.display = 'none';
        roundEndBtn.style.display = 'none';
        if(battleStartBtn) battleStartBtn.style.display = 'none';
        if(combatNextBtn) combatNextBtn.style.display = 'none';
        if(gmResetBtn) gmResetBtn.style.display = 'none';
    } else {
        if(battleStartBtn) battleStartBtn.style.display = 'inline-block';
        if(combatNextBtn) combatNextBtn.style.display = 'inline-block';
        if(gmResetBtn) gmResetBtn.style.display = 'inline-block';

        if (roundEndBtn && !roundEndBtn.dataset.listenerAttached) {
             roundEndBtn.dataset.listenerAttached = 'true';
             roundEndBtn.addEventListener('click', () => {
                const unacted = battleState.characters.filter(c => !c.hasActed);
                if (unacted.length > 0) {
                    const names = unacted.map(c => c.name).join(', ');
                    alert(`まだ行動していないキャラクターがいます: \n${names}\n\nラウンドを終了できません。`);
                    return;
                }
                if (confirm('「ラウンド終了時」の処理（出血ダメージなど）を実行しますか？')) {
                    socket.emit('request_end_round', { room: currentRoomName });
                }
            });
        }
        if (roundStartBtn && !roundStartBtn.dataset.listenerAttached) {
            roundStartBtn.dataset.listenerAttached = 'true';
            roundStartBtn.addEventListener('click', () => {
                if (confirm('「次ラウンド開始」の処理（速度ロールなど）を実行しますか？')) {
                    socket.emit('request_new_round', { room: currentRoomName });
                }
            });
        }
        if (battleStartBtn && !battleStartBtn.dataset.listenerAttached) {
            battleStartBtn.dataset.listenerAttached = 'true';
            battleStartBtn.addEventListener('click', () => {
                // ▼▼▼ 修正: モーダルを開くように変更 ▼▼▼
                openWideDeclarationModal();
                // ▲▲▲ 修正ここまで ▲▲▲
            });
        }
        if (combatNextBtn && !combatNextBtn.dataset.listenerAttached) {
            combatNextBtn.dataset.listenerAttached = 'true';
            combatNextBtn.addEventListener('click', () => {
                resetAllActionUI();
                selectNextActor();
            });
        }
        if (gmResetBtn && !gmResetBtn.dataset.listenerAttached) {
            gmResetBtn.dataset.listenerAttached = 'true';
            gmResetBtn.addEventListener('click', () => {
                if (confirm('GM専用: アクション欄のロックと宣言を強制的にリセットしますか？')) {
                    resetAllActionUI();
                }
            });
        }
    }

    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const diceCommandRegex = /^((\d+)?d\d+([\+\-]\d+)?(\s*[\+\-]\s*(\d+)?d\d+([\+\-]\d+)?)*)$/i;
    const sendChatMessage = () => {
        const message = chatInput.value.trim();
        if (!message) return;
        if (diceCommandRegex.test(message)) {
            const result = rollDiceCommand(message);
            const resultHtml = `${message} = ${result.details} = <span class="dice-result-total">${result.total}</span>`;
            socket.emit('request_log', {
                room: currentRoomName,
                message: `[${currentUsername}] ${resultHtml}`,
                type: 'dice'
            });
        } else {
            socket.emit('request_chat', {
                room: currentRoomName,
                user: currentUsername,
                message: message
            });
        }
        chatInput.value = '';
        chatInput.style.height = '60px';
    };

    if (!chatSendBtn.dataset.listenerAttached) {
        chatSendBtn.dataset.listenerAttached = 'true';
        chatSendBtn.addEventListener('click', sendChatMessage);
    }
    if (!chatInput.dataset.listenerAttached) {
        chatInput.dataset.listenerAttached = 'true';
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            chatInput.style.height = (chatInput.scrollHeight) + 'px';
        });
    }

    const saveBtn = document.getElementById('save-state-btn');
    const resetBtn = document.getElementById('reset-btn');
    const saveLoadMsg = document.getElementById('save-load-message');
    const leaveBtn = document.getElementById('leave-room-btn');

    // ▼▼▼ 追加: プリセット管理ボタンの要素取得 ▼▼▼
    const presetBtn = document.getElementById('preset-manager-btn');
    // ▲▲▲ 追加ここまで ▲▲▲

    if (saveBtn && saveLoadMsg && resetBtn && leaveBtn) {
        if (!saveBtn.dataset.listenerAttached) {
            saveBtn.dataset.listenerAttached = 'true';
            saveBtn.addEventListener('click', async () => {
                if (!currentRoomName) return;
                saveLoadMsg.textContent = 'セーブ中...';
                saveLoadMsg.style.color = '#333';
                try {
                    const response = await fetchWithSession('/save_room', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            room_name: currentRoomName,
                            state: battleState
                        })
                    });
                    const data = await response.json();
                    if (response.ok) {
                        saveLoadMsg.textContent = 'セーブ完了しました。';
                        saveLoadMsg.style.color = 'green';
                    } else {
                        saveLoadMsg.textContent = `セーブ失敗: ${data.error}`;
                        saveLoadMsg.style.color = 'red';
                    }
                } catch (error) {
                    saveLoadMsg.textContent = `サーバー接続エラー: ${error.message}`;
                    saveLoadMsg.style.color = 'red';
                }
            });
        }

        // ▼▼▼ 追加: プリセット管理ボタンのイベントリスナー ▼▼▼
        if (presetBtn && !presetBtn.dataset.listenerAttached) {
            presetBtn.dataset.listenerAttached = 'true';
            presetBtn.addEventListener('click', () => {
                if (typeof openPresetManagerModal === 'function') {
                    openPresetManagerModal();
                } else {
                    console.error("modals.js が読み込まれていないか、openPresetManagerModal が定義されていません。");
                }
            });
        }
        // ▲▲▲ 追加ここまで ▲▲▲

        if (!leaveBtn.dataset.listenerAttached) {
            leaveBtn.dataset.listenerAttached = 'true';
            leaveBtn.addEventListener('click', () => {
                if (confirm('ルーム一覧に戻りますか？\n（保存していない変更は失われます）')) {
                    if(socket) socket.emit('leave_room', {room: currentRoomName});
                    currentRoomName = null;
                    showRoomPortal();
                }
            });
        }

        if (!resetBtn.dataset.listenerAttached) {
            resetBtn.dataset.listenerAttached = 'true';
            resetBtn.addEventListener('click', () => {
                // modals.js で追加した openResetTypeModal を呼び出す
                if (typeof openResetTypeModal === 'function') {
                    openResetTypeModal((resetType) => {
                        socket.emit('request_reset_battle', {
                            room: currentRoomName,
                            mode: resetType // 'full' or 'status'
                        });

                        if (resetType === 'full') {
                            saveLoadMsg.textContent = '戦闘を完全リセットしました。';
                        } else {
                            saveLoadMsg.textContent = 'ステータスをリセットしました。';
                        }
                        saveLoadMsg.style.color = 'orange';
                    });
                } else {
                    // フォールバック
                    if (confirm('本当に現在のルームの戦闘をすべてリセットしますか？\n（セーブデータは消えません）')) {
                        socket.emit('request_reset_battle', {
                            room: currentRoomName,
                            mode: 'full'
                        });
                        saveLoadMsg.textContent = '戦闘をリセットしました。';
                        saveLoadMsg.style.color = 'orange';
                    }
                }
            });
        }
    }
}


// === ▼▼▼ 追加: 広域スキル宣言モーダル ▼▼▼
function openWideDeclarationModal() {
    const existing = document.getElementById('wide-decl-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'wide-decl-modal-backdrop';
    overlay.className = 'modal-backdrop';

    let allyHtml = '';
    let enemyHtml = '';

    battleState.characters.forEach(char => {
        if (char.hp <= 0) return;

        const html = `
            <label style="display: flex; align-items: center; padding: 8px; border-bottom: 1px solid #eee; cursor: pointer;">
                <input type="checkbox" class="wide-decl-checkbox" value="${char.id}" style="margin-right: 10px; transform: scale(1.2);">
                <span style="font-weight: bold; color: ${char.color}; margin-right: 10px;">${char.name}</span>
                <span style="margin-left: auto; font-size: 0.85em; color: #666;">速度: ${char.speedRoll}</span>
            </label>
        `;
        if (char.type === 'ally') allyHtml += html;
        else enemyHtml += html;
    });

    const content = `
        <div class="modal-content" style="width: 600px; padding: 25px; max-height: 80vh; display: flex; flex-direction: column;">
            <h3 style="margin-top: 0; border-bottom: 2px solid #007bff; padding-bottom: 10px; color: #0056b3;">
                ⚡ 広域スキル使用宣言
            </h3>
            <p style="font-size: 0.9em; color: #555; margin-bottom: 20px;">
                このラウンドで<strong>広域スキル</strong>を使用するキャラクターを選択してください。<br>
                選択されたキャラクターは、通常の速度順よりも優先して行動します。
            </p>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; overflow-y: auto; flex-grow: 1; margin-bottom: 20px;">
                <div>
                    <h4 style="margin: 5px 0; color: #007bff; border-bottom: 1px solid #eee;">味方</h4>
                    <div style="background: #fdfdfd; border: 1px solid #ddd; border-radius: 4px;">
                        ${allyHtml || '<div style="padding:10px; color:#999;">なし</div>'}
                    </div>
                </div>
                <div>
                    <h4 style="margin: 5px 0; color: #dc3545; border-bottom: 1px solid #eee;">敵</h4>
                    <div style="background: #fdfdfd; border: 1px solid #ddd; border-radius: 4px;">
                        ${enemyHtml || '<div style="padding:10px; color:#999;">なし</div>'}
                    </div>
                </div>
            </div>

            <div style="text-align: right; display: flex; justify-content: flex-end; gap: 10px;">
                <button id="cancel-decl-btn" style="padding: 10px 20px; border: 1px solid #ccc; background: #fff; border-radius: 4px; cursor: pointer;">キャンセル</button>
                <button id="confirm-decl-btn" style="padding: 10px 20px; border: none; background: #007bff; color: white; font-weight: bold; border-radius: 4px; cursor: pointer;">
                    決定して戦闘開始
                </button>
            </div>
        </div>
    `;

    overlay.innerHTML = content;
    document.body.appendChild(overlay);

    const closeFunc = () => overlay.remove();
    document.getElementById('cancel-decl-btn').onclick = closeFunc;

    document.getElementById('confirm-decl-btn').onclick = () => {
        const checkboxes = overlay.querySelectorAll('.wide-decl-checkbox');
        const selectedIds = [];
        checkboxes.forEach(cb => {
            if (cb.checked) selectedIds.push(cb.value);
        });

        socket.emit('request_declare_wide_skill_users', {
            room: currentRoomName,
            wideUserIds: selectedIds
        });

        // 少し待ってから次の行動者を自動選択
        setTimeout(() => {
            closeFunc();
            // ソート反映待ち
            setTimeout(() => {
                const actorSelect = document.getElementById('actor-attacker');
                const firstChar = battleState.characters[0];
                if (firstChar && !firstChar.hasActed) {
                    actorSelect.value = firstChar.id;
                    actorSelect.dispatchEvent(new Event('change'));
                }
            }, 500);
        }, 100);
    };
}

if (typeof fetchSkillMetadata === "function") {
    fetchSkillMetadata();
}