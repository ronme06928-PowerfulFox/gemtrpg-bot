/* static/js/tab_battlefield.js */

// --- 8. バトルフィールドタブ ---

let currentLogFilter = 'all';
let globalSkillMetadata = {};

// スキルメタデータを取得してキャッシュする
async function fetchSkillMetadata() {
    // ★ 修正: fetchWithSession が定義されていない場合はスキップ
    if (typeof fetchWithSession !== 'function') {
        console.warn("fetchWithSession is not defined yet, skipping fetchSkillMetadata");
        return;
    }
    try {
        const response = await fetchWithSession('/api/get_skill_metadata');
        if (response.ok) {
            globalSkillMetadata = await response.json();
        }
    } catch (e) {
        console.warn("Failed to load skill metadata:", e);
    }
}

function loadCharacterFromJSON(type, jsonString, resultElement) {
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

function logToBattleLog(logData) {
    // 1. データへの保存
    if (battleState && battleState.logs) {
        battleState.logs.push(logData);
    }

    // 2. テキストバトルフィールドへの描画
    const textLogArea = document.getElementById('log-area');
    if (textLogArea) {
        appendLogLineToElement(textLogArea, logData, currentLogFilter);
    }

    // 3. ビジュアルバトルフィールドへの描画
    const visualLogArea = document.getElementById('visual-log-area');
    // window.currentVisualLogFilter が未定義の場合は 'all' とする
    const visualFilter = (typeof window.currentVisualLogFilter !== 'undefined') ? window.currentVisualLogFilter : 'all';

    if (visualLogArea) {
        appendLogLineToElement(visualLogArea, logData, visualFilter);
    }
}

// ログ1行を生成して要素に追加するヘルパー関数
function appendLogLineToElement(container, logData, filterType) {
    const isChat = logData.type === 'chat';

    // フィルタリング
    if (filterType === 'chat' && !isChat) return;
    if (filterType === 'system' && isChat) return;

    const logLine = document.createElement('div');
    let className = `log-line ${logData.type}`;

    // シークレットダイスの処理
    let displayMessage = logData.message;
    if (logData.secret) {
        className += ' secret-log';
        const isSender = (logData.user === currentUsername);
        const isGM = (currentUserAttribute === 'GM');

        if (isGM || isSender) {
            displayMessage = `<span class="secret-mark">[SECRET]</span> ${logData.message}`;
        } else {
            displayMessage = `<span class="secret-masked">（シークレットダイスが振られました）</span>`;
        }
    }

    logLine.className = className;

    // チャットの場合の装飾
    if (logData.type === 'chat' && !logData.secret) {
        logLine.innerHTML = `<span class="chat-user">${logData.user}:</span> <span class="chat-message">${logData.message}</span>`;
    } else {
        logLine.innerHTML = displayMessage;
    }

    logLine.style.borderBottom = "1px dotted #eee";
    logLine.style.padding = "2px 5px";
    logLine.style.fontSize = "0.9em";

    container.appendChild(logLine);
    container.scrollTop = container.scrollHeight;
}

// ログ履歴を一括描画する関数
function renderLogHistory(logs) {
    const logArea = document.getElementById('log-area');
    if (!logArea || !logs || !Array.isArray(logs)) return;

    // 既にログが表示されている場合は再描画しない（スクロール飛び防止）
    // ただし、中身が空なら描画する
    if (logArea.children.length > 1) {
        // 必要に応じて更新ロジックを入れるが、基本は追記型なので放置でも良い
        // 今回は念のため再描画せずリターン（パフォーマンス優先）
        // return;
        // ↑ もしフィルタ切り替え時などに再描画が必要なら、innerHTML = '' してから描画する
        logArea.innerHTML = '<p class="log-line info">--- 過去ログ ---</p>';
    } else {
        logArea.innerHTML = '<p class="log-line info">--- 過去ログ ---</p>';
    }

    logs.forEach(logData => {
        appendLogLineToElement(logArea, logData, currentLogFilter);
    });
    logArea.scrollTop = logArea.scrollHeight;
}

function safeMathEvaluate(expression) {
    try {
        const sanitized = expression.replace(/[^-()\d/*+.]/g, '');
        return new Function('return ' + sanitized)();
    } catch (e) { console.error("Safe math eval error:", e); return 0; }
}

function rollDiceCommand(command) {
    let calculation = command.replace(/【.*?】/g, '').trim();
    calculation = calculation.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');

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

function renderTokenList() {
    const allyContainer = document.getElementById('ally-list-column');
    const enemyContainer = document.getElementById('enemy-list-column');
    if (!allyContainer || !enemyContainer) return;

    allyContainer.innerHTML = '';
    enemyContainer.innerHTML = '';

    if (!battleState || !battleState.characters || battleState.characters.length === 0) {
        allyContainer.innerHTML = '<p class="char-token-placeholder">キャラクターが読み込まれていません。</p>';
        return;
    }

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

        const hpPercent = Math.max(0, Math.min(100, (char.hp / char.maxHp) * 100));
        const mpPercent = Math.max(0, Math.min(100, (char.mp / char.maxMp) * 100));

        const fpState = char.states.find(s => s.name === 'FP');
        const fpValue = fpState ? fpState.value : 0;
        const fpPercent = Math.min(100, (fpValue / 15) * 100);

        const activeStates = char.states.filter(s => {
            return !['HP', 'MP', 'FP'].includes(s.name) && s.value !== 0;
        });

        let debuffsHtml = '';
        if (activeStates.length > 0) {
            let itemsHtml = '';
            activeStates.forEach(s => {
                let iconHtml = '';
                if (iconMap[s.name]) {
                    iconHtml = `<img src="images/${iconMap[s.name]}" class="status-icon-img" alt="${s.name}">`;
                } else {
                    if (s.value > 0) {
                        iconHtml = `<span class="arrow-icon arrow-up">▲</span>`;
                    } else {
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

            if (prefix === 'attacker') {
                const reEvasionBuff = char.special_buffs ? char.special_buffs.find(b => b.name === "再回避ロック") : null;
                if (reEvasionBuff) {
                    targetOptions += option;
                    return;
                }
            }

            targetOptions += option;

            if (char.gmOnly && currentUserAttribute !== 'GM') {
            } else {
                actorOptions += option;
            }
        });

        actorSelect.innerHTML = actorOptions;
        targetSelect.innerHTML = targetOptions;

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

            if (prefix === 'defender') {
                const meta = globalSkillMetadata[skillId];
                if (meta) {
                    const cat = meta.category || "";
                    const dist = meta.distance || "";
                    const tags = meta.tags || [];

                    if (
                        cat.includes("広域") || dist.includes("広域") ||
                        tags.includes("広域-個別") || tags.includes("広域-合算")
                    ) {
                        continue;
                    }
                }
            }

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

            if (!targetId) targetId = actorId;

            socket.emit('request_skill_declaration', {
                room: currentRoomName,
                prefix: prefix,
                actor_id: actorId,
                target_id: targetId,
                skill_id: skillId,
                custom_skill_name: customSkillName,
                commit: false
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

            if (declareBtn.dataset.isImmediate === 'true') {
                const actorId = actorSelect.value;
                const targetId = targetSelect.value || actorId;
                const selectedSkill = skillSelect.options[skillSelect.selectedIndex];
                const skillId = selectedSkill.value;
                const customSkillName = selectedSkill.dataset.customName;

                socket.emit('request_skill_declaration', {
                    room: currentRoomName,
                    prefix: prefix,
                    actor_id: actorId,
                    target_id: targetId,
                    skill_id: skillId,
                    custom_skill_name: customSkillName,
                    commit: true
                });
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

            if (wideContainer) {
                wideContainer.style.display = 'none';
                const defCol = document.getElementById('action-column-defender');
                if (defCol) defCol.style.display = 'flex';
            }
        } else {
            actorSelect.disabled = true;
            targetSelect.disabled = true;
        }

        powerDisplay.value = "[威力計算待ち]";
        commandDisplay.value = "[コマンドプレビュー]";
        hiddenCommand.value = "";

        const senritsuField = document.getElementById(`hidden-senritsu-${prefix}`);
        if (senritsuField) senritsuField.value = "0";

        declareBtn.disabled = true;
        declareBtn.dataset.isImmediate = 'false';
        powerDisplay.style.borderColor = "";
        powerDisplay.style.fontWeight = "normal";
        commandDisplay.style.borderColor = "";

        if (previewBox) {
            previewBox.innerHTML = '';
            previewBox.style.display = 'none';
        }
    };

    if (!actorSelect.dataset.listenerAttached) {
        actorSelect.dataset.listenerAttached = 'true';
        actorSelect.addEventListener('change', (e) => {
            updateSkillDropdown(e.target.value);
            resetUI();

            if (prefix === 'attacker') {
                const defenderTargetSelect = document.getElementById('target-defender');
                if (defenderTargetSelect) {
                    defenderTargetSelect.value = e.target.value;
                    defenderTargetSelect.dispatchEvent(new Event('change'));
                }
            }
        });
    }

    if (!targetSelect.dataset.listenerAttached) {
        targetSelect.dataset.listenerAttached = 'true';
        targetSelect.addEventListener('change', (e) => {
            resetUI();

            if (prefix === 'attacker') {
                const targetId = e.target.value;
                const defenderActorSelect = document.getElementById('actor-defender');
                if (defenderActorSelect) {
                    defenderActorSelect.value = targetId;
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
                    if (isWide) continue;

                    skillOptions += `<option value="${sId}">${sId}: ${sName}</option>`;
                }
            }

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
                    custom_skill_name: "",
                    commit: false
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
    const roundCounterElem = document.getElementById('round-counter');
    const timelineListElem = document.getElementById('timeline-list');

    if (!timelineListElem || !roundCounterElem) return;

    timelineListElem.innerHTML = '';

    if (battleState && battleState.round) {
        roundCounterElem.textContent = battleState.round;
    }

    if (battleState && battleState.timeline) {
        battleState.timeline.forEach(charId => {
            const char = battleState.characters.find(c => c.id === charId);
            if (!char) return;

            const item = document.createElement('div');
            item.className = `timeline-item ${char.type || 'NPC'}`;
            if (char.hasActed) item.classList.add('acted');

            const typeColor = (char.type === 'ally') ? '#007bff' : '#dc3545';

            if (char.id === battleState.turn_char_id) {
                item.classList.add('active-turn');
                item.style.borderTop = "2px solid #ff9800";
                item.style.borderBottom = "2px solid #ff9800";
                item.style.borderRight = "2px solid #ff9800";
                item.style.borderLeft = `6px solid ${typeColor}`;
                item.style.fontWeight = "bold";
                item.style.background = "#fff8e1";
            } else {
                item.style.borderLeft = `4px solid ${typeColor}`;
            }

            item.innerHTML = `
                <span class="timeline-char-name">${char.name}</span>
                <span class="timeline-speed-roll">SPD:${char.speedRoll}</span>
            `;
            timelineListElem.appendChild(item);
        });
    }
}

function openCharSettingsModal(charId) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    const existing = document.getElementById('char-settings-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'char-settings-modal-backdrop';
    overlay.className = 'modal-backdrop';

    const ownerName = char.owner || "不明";

    overlay.innerHTML = `
        <div class="modal-content" style="width: 400px; padding: 20px;">
            <h3 style="margin-top: 0; border-bottom: 1px solid #eee; padding-bottom: 10px;">
                ${char.name} の設定
            </h3>
            <div style="margin-bottom: 15px; padding: 10px; background: #eef5ff; border: 1px solid #cce5ff; border-radius: 4px; color: #004085;">
                <span style="font-weight:bold;">所有者:</span> ${ownerName}
            </div>
            <label style="display:block; margin-bottom:10px; font-weight:bold;">
                キャラクター名:
                <input type="text" id="edit-char-name" value="${char.baseName}" style="width:100%; padding: 5px; margin-top: 5px;">
            </label>
            <label style="display:flex; align-items:center; margin-bottom:20px; cursor:pointer;">
                <input type="checkbox" id="edit-char-gm-only" ${char.gmOnly ? 'checked' : ''} style="transform: scale(1.2); margin-right: 8px;">
                GMのみ操作可能にする
            </label>
            <div style="text-align: right; display: flex; justify-content: flex-end; gap: 10px;">
                <button id="cancel-settings-btn" style="padding: 8px 16px; cursor: pointer;">キャンセル</button>
                <button id="save-settings-btn" class="primary-btn" style="padding: 8px 16px; cursor: pointer;">保存</button>
            </div>
            <hr style="margin: 20px 0;">
            <button id="delete-char-btn" style="background:#dc3545; color:white; border:none; padding:10px; border-radius:4px; width:100%; cursor: pointer; font-weight:bold;">
                🗑️ キャラクターを削除する
            </button>
        </div>
    `;

    document.body.appendChild(overlay);

    document.getElementById('cancel-settings-btn').onclick = () => overlay.remove();

    document.getElementById('save-settings-btn').onclick = () => {
        const newName = document.getElementById('edit-char-name').value;
        const newGmOnly = document.getElementById('edit-char-gm-only').checked;

        if (newName && newName !== char.baseName) {
            socket.emit('request_state_update', {
                room: currentRoomName,
                charId: char.id,
                changes: { baseName: newName }
            });
        }

        if (newGmOnly !== char.gmOnly) {
            socket.emit('request_state_update', {
                room: currentRoomName,
                charId: char.id,
                statName: 'gmOnly',
                newValue: newGmOnly
            });
        }
        overlay.remove();
    };

    document.getElementById('delete-char-btn').onclick = () => {
        if (confirm(`本当に ${char.name} を削除しますか？`)) {
            socket.emit('request_delete_character', {
                room: currentRoomName,
                charId: char.id
            });
            overlay.remove();
        }
    };
}

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

        setTimeout(() => {
            closeFunc();
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

// --- ★初期化関数 (すべてのリスナー登録をここに集約) ---
function setupBattlefieldTab() {
    // 1. DOM要素のセットアップ (毎回必要)
    const openLoadModalBtn = document.getElementById('open-char-load-modal-btn');
    if (openLoadModalBtn) {
        openLoadModalBtn.addEventListener('click', openCharLoadModal);
    }

    if (battleState && battleState.logs) {
        renderLogHistory(battleState.logs);
    }
    renderTimeline();
    renderTokenList();

    // 2. イベントリスナーの設定 (ボタン等)
    const leftColumn = document.getElementById('battlefield-left-column');
    if (leftColumn && !leftColumn.dataset.listenerAttached) {
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

    const filterButtons = document.querySelectorAll('.filter-btn');
    const logArea = document.getElementById('log-area');
    filterButtons.forEach(btn => {
        if (btn.dataset.listenerAttached) return;
        btn.dataset.listenerAttached = 'true';
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentLogFilter = btn.dataset.filter;
            if (logArea) {
                const logs = logArea.querySelectorAll('.log-line');
                logs.forEach(line => {
                    const isChat = line.classList.contains('chat');
                    if (currentLogFilter === 'all') line.classList.remove('hidden-log');
                    else if (currentLogFilter === 'chat') {
                        if (isChat) line.classList.remove('hidden-log'); else line.classList.add('hidden-log');
                    } else if (currentLogFilter === 'system') {
                        if (!isChat) line.classList.remove('hidden-log'); else line.classList.add('hidden-log');
                    }
                });
                logArea.scrollTop = logArea.scrollHeight;
            }
        });
    });

    window.attackerCol = setupActionColumn('attacker');
    window.defenderCol = setupActionColumn('defender');

    const actorAttacker = document.getElementById('actor-attacker');
    const targetAttacker = document.getElementById('target-attacker');
    const actorDefender = document.getElementById('actor-defender');
    const targetDefender = document.getElementById('target-defender');

    if (targetAttacker && !targetAttacker.dataset.listenerAttached_auto) {
        targetAttacker.dataset.listenerAttached_auto = 'true';
        targetAttacker.addEventListener('change', (e) => {
            const targetId = e.target.value;
            if (targetId && actorDefender && window.defenderCol) {
                actorDefender.value = targetId;
                window.defenderCol.updateSkillDropdown(targetId);
            }
        });
    }

    if (actorAttacker && !actorAttacker.dataset.listenerAttached_auto) {
        actorAttacker.dataset.listenerAttached_auto = 'true';
        actorAttacker.addEventListener('change', (e) => {
            const actorId = e.target.value;
            if (actorId && targetDefender) {
                targetDefender.value = actorId;
            }
        });
    }

    const matchStartBtn = document.getElementById('match-start-btn');
    if (matchStartBtn && !matchStartBtn.dataset.listenerAttached) {
        matchStartBtn.dataset.listenerAttached = 'true';
        matchStartBtn.addEventListener('click', () => {
            const hiddenCmdAttacker = document.getElementById('hidden-command-attacker');
            const hiddenCmdDefender = document.getElementById('hidden-command-defender');

            if (!hiddenCmdAttacker.value || !hiddenCmdDefender.value || !actorAttacker.value || !actorDefender.value) {
                document.getElementById('match-result-area').innerHTML = 'エラー: 双方の宣言が必要です。';
                return;
            }
            socket.emit('request_match', {
                room: currentRoomName,
                actorIdA: actorAttacker.value, actorIdD: actorDefender.value,
                commandA: hiddenCmdAttacker.value, commandD: hiddenCmdDefender.value,
                actorNameA: actorAttacker.options[actorAttacker.selectedIndex].text,
                actorNameD: actorDefender.options[actorDefender.selectedIndex].text,
                senritsuPenaltyA: document.getElementById('hidden-senritsu-attacker').value || 0,
                senritsuPenaltyD: document.getElementById('hidden-senritsu-defender').value || 0
            });
            document.getElementById('match-result-area').innerHTML = '... マッチを実行中 ...';

            // 入力リセットとロック解除 (修正適用済み)
            const prefixes = ['attacker', 'defender'];
            prefixes.forEach(prefix => {
                const actorEl = document.getElementById(`actor-${prefix}`);
                const targetEl = document.getElementById(`target-${prefix}`);
                const skillEl = document.getElementById(`skill-${prefix}`);

                // 1. 値のクリア
                if (actorEl) actorEl.value = "";
                if (targetEl) targetEl.value = "";
                if (skillEl) skillEl.value = "";

                // 2. disabled状態の解除
                if (skillEl) skillEl.disabled = false; // スキルは両者とも選択可能に戻す

                if (prefix === 'attacker') {
                    // 攻撃側は使用者・対象・スキルすべて選択可能に戻す
                    if (actorEl) actorEl.disabled = false;
                    if (targetEl) targetEl.disabled = false;
                } else {
                    // 防御側の使用者・対象は攻撃側の選択に連動するため、disabledのままにする
                    if (actorEl) actorEl.disabled = true;
                    if (targetEl) targetEl.disabled = true;
                }

                // その他のUI要素のリセット
                document.getElementById(`generate-btn-${prefix}`).disabled = false;
                document.getElementById(`declare-btn-${prefix}`).disabled = true;
                document.getElementById(`power-display-${prefix}`).value = "[威力計算待ち]";
                document.getElementById(`command-display-${prefix}`).value = "[コマンドプレビュー]";
                document.getElementById(`hidden-command-${prefix}`).value = "";
                const pb = document.getElementById(`skill-preview-${prefix}`);
                if (pb) pb.style.display = 'none';
            });
        });
    }

    // チャット、保存、GMボタン
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const sendChatMessage = () => {
        let rawMessage = chatInput.value.trim();
        if (!rawMessage) return;
        let message = rawMessage;
        let isSecret = false;
        if (/^(\/sroll|\/sr)(\s+|$)/i.test(message)) isSecret = true;

        const diceCommandRegex = /^((\d+)?d\d+([\+\-]\d+)?(\s*[\+\-]\s*(\d+)?d\d+([\+\-]\d+)?)*)$/i;

        // ダイス判定強化: メッセージ全体がダイス式か、またはコマンドを含むか
        let isDice = diceCommandRegex.test(message) || /^(\/roll|\/r|\/sroll|\/sr)/i.test(message);

        if (isDice) {
            const result = rollDiceCommand(message);
            // コマンド部分をきれいにする
            let cleanCmd = message.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');
            const resultHtml = `${cleanCmd} = ${result.details} = <span class="dice-result-total">${result.total}</span>`;
            socket.emit('request_log', {
                room: currentRoomName,
                message: `[${currentUsername}] ${resultHtml}`,
                type: 'dice',
                secret: isSecret,
                user: currentUsername
            });
        } else {
            if (isSecret) message = message.replace(/^(\/sroll|\/sr)\s*/i, '');
            socket.emit('request_chat', { room: currentRoomName, user: currentUsername, message: message, secret: isSecret });
        }
        chatInput.value = '';
    };

    if (chatSendBtn && !chatSendBtn.dataset.listenerAttached) {
        chatSendBtn.dataset.listenerAttached = 'true';
        chatSendBtn.addEventListener('click', sendChatMessage);
    }
    if (chatInput && !chatInput.dataset.listenerAttached) {
        chatInput.dataset.listenerAttached = 'true';
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
        });
    }

    const roundStartBtn = document.getElementById('round-start-btn');
    const roundEndBtn = document.getElementById('round-end-btn');
    const battleStartBtn = document.getElementById('battle-start-btn');
    const combatNextBtn = document.getElementById('combat-next-btn');
    const gmResetBtn = document.getElementById('gm-reset-action-btn');

    if (currentUserAttribute === 'GM') {
        if (battleStartBtn) battleStartBtn.style.display = 'inline-block';
        if (combatNextBtn) combatNextBtn.style.display = 'inline-block';
        if (gmResetBtn) gmResetBtn.style.display = 'inline-block';

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
                openWideDeclarationModal();
            });
        }
        if (combatNextBtn && !combatNextBtn.dataset.listenerAttached) {
            combatNextBtn.dataset.listenerAttached = 'true';
            combatNextBtn.addEventListener('click', () => {
                // 次のアクター選択
                const nextActor = battleState.characters.find(c => !c.hasActed);
                if (nextActor) {
                    const actorSelect = document.getElementById('actor-attacker');
                    actorSelect.value = nextActor.id;
                    actorSelect.dispatchEvent(new Event('change'));
                } else {
                    alert("全てのキャラクターが行動済みです。「R終了処理」を行ってください。");
                }
            });
        }
        if (gmResetBtn && !gmResetBtn.dataset.listenerAttached) {
            gmResetBtn.dataset.listenerAttached = 'true';
            gmResetBtn.addEventListener('click', () => {
                if (confirm('GM専用: 強制リセットしますか？')) {
                    const prefixes = ['attacker', 'defender'];
                    prefixes.forEach(prefix => {
                        const actorEl = document.getElementById(`actor-${prefix}`);
                        if (actorEl) {
                            actorEl.value = "";
                            actorEl.disabled = (prefix === 'defender'); // defenderは元々disabled
                        }
                        // 他のリセット処理
                        document.getElementById(`skill-${prefix}`).disabled = false;
                        document.getElementById(`generate-btn-${prefix}`).disabled = false;
                        document.getElementById(`declare-btn-${prefix}`).disabled = true;
                    });
                }
            });
        }
    } else {
        if (roundStartBtn) roundStartBtn.style.display = 'none';
        if (roundEndBtn) roundEndBtn.style.display = 'none';
        if (battleStartBtn) battleStartBtn.style.display = 'none';
        if (combatNextBtn) combatNextBtn.style.display = 'none';
        if (gmResetBtn) gmResetBtn.style.display = 'none';
    }

    const saveBtn = document.getElementById('save-state-btn');
    const resetBtn = document.getElementById('reset-btn');
    const saveLoadMsg = document.getElementById('save-load-message');
    const leaveBtn = document.getElementById('leave-room-btn');
    const presetBtn = document.getElementById('preset-manager-btn');

    if (saveBtn && !saveBtn.dataset.listenerAttached) {
        saveBtn.dataset.listenerAttached = 'true';
        saveBtn.addEventListener('click', async () => {
            if (!currentRoomName) return;
            saveLoadMsg.textContent = 'セーブ中...';
            try {
                await fetchWithSession('/save_room', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ room_name: currentRoomName, state: battleState })
                });
                saveLoadMsg.textContent = 'セーブ完了しました。';
                saveLoadMsg.style.color = 'green';
            } catch (error) {
                saveLoadMsg.textContent = `セーブ失敗: ${error.message}`;
                saveLoadMsg.style.color = 'red';
            }
        });
    }
    if (presetBtn && !presetBtn.dataset.listenerAttached) {
        presetBtn.dataset.listenerAttached = 'true';
        presetBtn.addEventListener('click', () => {
            if (typeof openPresetManagerModal === 'function') openPresetManagerModal();
        });
    }
    if (leaveBtn && !leaveBtn.dataset.listenerAttached) {
        leaveBtn.dataset.listenerAttached = 'true';
        leaveBtn.addEventListener('click', () => {
            if (confirm('ルーム一覧に戻りますか？')) {
                if (socket) socket.emit('leave_room', { room: currentRoomName });
                currentRoomName = null;
                showRoomPortal();
            }
        });
    }
    if (resetBtn && !resetBtn.dataset.listenerAttached) {
        resetBtn.dataset.listenerAttached = 'true';
        resetBtn.addEventListener('click', () => {
            if (typeof openResetTypeModal === 'function') {
                openResetTypeModal((resetType) => {
                    socket.emit('request_reset_battle', { room: currentRoomName, mode: resetType });
                });
            } else if (confirm('本当にリセットしますか？')) {
                socket.emit('request_reset_battle', { room: currentRoomName, mode: 'full' });
            }
        });
    }

    // 3. Socketリスナー登録
    if (typeof socket !== 'undefined') {
        // A. 【状態更新リスナー】(初回のみ登録)
        if (!window.battleSocketHandlersRegistered) {

            window.battleSocketHandlersRegistered = true;

            socket.on('state_updated', (state) => {
                // A. テキストバトルフィールドが表示中なら更新
                if (document.getElementById('battlefield-grid')) {
                    if (typeof renderTimeline === 'function') renderTimeline();
                    if (typeof renderTokenList === 'function') renderTokenList();
                }
                if (document.getElementById('log-area')) {
                    if (typeof renderLogHistory === 'function') renderLogHistory(state.logs);
                }

                // B. ビジュアルバトルフィールドが表示中なら更新
                if (document.getElementById('visual-battle-container')) {
                    if (typeof renderVisualMap === 'function') renderVisualMap();
                    if (typeof renderStagingArea === 'function') renderStagingArea();
                    if (typeof renderVisualTimeline === 'function') renderVisualTimeline();
                    if (typeof renderVisualLogHistory === 'function') renderVisualLogHistory(state.logs);
                    if (typeof updateVisualRoundDisplay === 'function') updateVisualRoundDisplay(state.round);
                }
            });
        }

        // B. 【スキル結果リスナー】 (★修正: タブ切り替えで消されるため、毎回強制的に再登録する)
        // まず既存のリスナー（ビジュアルタブ用など）を削除して重複・競合を防止
        socket.off('skill_declaration_result');


        socket.on('skill_declaration_result', (data) => {
            // 1. ビジュアル側の処理 (prefixが visual_*)
            // テキストタブにいてもビジュアル用データが飛んでくる可能性に備えて残すが、
            // 基本的にはテキストタブ用の処理をここで行う

            if (data.prefix && data.prefix.startsWith('visual_')) {
                // ビジュアルタブ用のデータはここでは無視するか、必要なら処理する
                return;
            }

            // 2. テキスト側の処理
            // (DOM要素が存在するか確認してから操作する)

            // 広域防御の処理
            if (data.prefix && data.prefix.startsWith('wide-def-')) {
                const charId = data.prefix.replace('wide-def-', '');
                const row = document.querySelector(`.wide-defender-row[data-row-id="wide-row-${charId}"]`);
                if (row) {
                    const resArea = row.querySelector('.wide-result-area');
                    const declBtn = row.querySelector('.wide-declare-btn');
                    const finalCmdInput = row.querySelector('.wide-final-command');

                    if (data.error) {
                        resArea.textContent = data.final_command;
                        resArea.style.color = "red";
                        declBtn.disabled = true;
                    } else {
                        resArea.textContent = `威力: ${data.min_damage}～${data.max_damage} (${data.final_command})`;
                        resArea.style.color = "blue";
                        finalCmdInput.value = data.final_command;
                        declBtn.disabled = false;
                    }
                }
                return;
            }

            // 1vs1アクション (attacker / defender)
            const prefix = data.prefix;
            const powerDisplay = document.getElementById(`power-display-${prefix}`);

            // 要素がなければ何もしない (ビジュアルタブ閲覧中など)
            if (!powerDisplay) return;

            const commandDisplay = document.getElementById(`command-display-${prefix}`);
            const hiddenCommand = document.getElementById(`hidden-command-${prefix}`);
            const hiddenSenritsu = document.getElementById(`hidden-senritsu-${prefix}`);
            const declareBtn = document.getElementById(`declare-btn-${prefix}`);
            const generateBtn = document.getElementById(`generate-btn-${prefix}`);
            const previewBox = document.getElementById(`skill-preview-${prefix}`);

            generateBtn.disabled = false;

            if (data.error) {
                powerDisplay.value = data.final_command;
                commandDisplay.value = "--- エラー ---";
                powerDisplay.style.borderColor = "#dc3545";
                hiddenCommand.value = "";
                declareBtn.disabled = true;
                if (previewBox) previewBox.style.display = 'none';
                return;
            }

            powerDisplay.value = `威力: ${data.min_damage} ～ ${data.max_damage}`;
            commandDisplay.value = data.final_command;
            hiddenCommand.value = data.final_command;
            if (hiddenSenritsu) hiddenSenritsu.value = data.senritsu_penalty || 0;

            declareBtn.disabled = false;
            declareBtn.dataset.isImmediate = data.is_immediate_skill ? 'true' : 'false';
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
                if (defenderPower) {
                    defenderPower.value = "--- (一方攻撃) ---";
                    document.getElementById('command-display-defender').value = '【一方攻撃（行動済）】';
                    document.getElementById('hidden-command-defender').value = '【一方攻撃（行動済）】';
                    document.getElementById('actor-defender').disabled = true;
                    document.getElementById('target-defender').disabled = true;
                    document.getElementById('skill-defender').disabled = true;
                    document.getElementById('generate-btn-defender').disabled = true;
                    document.getElementById('declare-btn-defender').disabled = true;
                    defenderPower.style.borderColor = "#4CAF50";
                    defenderPower.style.fontWeight = "bold";
                    if (document.getElementById('skill-preview-defender')) document.getElementById('skill-preview-defender').style.display = 'none';
                }
            }

            if (data.is_instant_action) {
                const actorEl = document.getElementById('actor-attacker');
                if (actorEl) {
                    actorEl.value = "";
                    actorEl.dispatchEvent(new Event('change'));
                }
            }
        });
    }
}

if (typeof fetchSkillMetadata === "function") {
    fetchSkillMetadata();
}