// --- 8. バトルフィールドタブ ---

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

function logToBattleLog(logData) {
    const logArea = document.getElementById('log-area');
    if (!logArea) return;
    const logLine = document.createElement('div');
    logLine.className = `log-line ${logData.type}`;
    if (logData.type === 'chat') {
        logLine.innerHTML = `<span class="chat-user">${logData.user}:</span> <span class="chat-message">${logData.message}</span>`;
    } else {
        logLine.innerHTML = logData.message;
    }
    logArea.appendChild(logLine);
    logArea.scrollTop = logArea.scrollHeight;
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

function renderTokenList() {
    // (この関数は変更なし)
    const allyContainer = document.getElementById('ally-list-column');
    const enemyContainer = document.getElementById('enemy-list-column');
    if (!allyContainer || !enemyContainer) return;
    allyContainer.innerHTML = '';
    enemyContainer.innerHTML = '';
    if (battleState.characters.length === 0) {
        allyContainer.innerHTML = '<p class="char-token-placeholder">キャラクターが読み込まれていません。</p>';
        return;
    }
    battleState.characters.forEach(char => {
        const token = document.createElement('div');
        token.className = 'char-token';
        token.dataset.id = char.id;
        token.style.borderLeftColor = char.color;
        const fpState = char.states.find(s => s.name === 'FP');
        const fpValue = fpState ? fpState.value : 0;
        const activeDebuffs = char.states.filter(s => {
            return !['HP', 'MP', 'FP'].includes(s.name) && s.value >= 1;
        });
        let debuffsHtml = '';
        if (activeDebuffs.length > 0) {
            let debuffItemsHtml = '';
            activeDebuffs.forEach(s => {
                let colorClass = '';
                switch (s.name) {
                    case '出血': colorClass = 'shukketsu'; break;
                    case '破裂': colorClass = 'haretsu'; break;
                    case '亀裂': colorClass = 'kiretsu'; break;
                    case '戦慄': colorClass = 'senritsu'; break;
                    case '荊棘': colorClass = 'keikyoku'; break;
                    default: colorClass = '';
                }
                debuffItemsHtml += `<span class="token-debuff ${colorClass}">${s.name}: ${s.value}</span>`;
            });
            debuffsHtml = `<div class="token-debuff-list">${debuffItemsHtml}</div>`;
        }
        token.innerHTML = `
            <h4 class="token-name">${char.name}</h4>
            <div class="token-stats-grid">
                <span class="token-stat">HP: ${char.hp}/${char.maxHp}</span>
                <span class="token-stat">MP: ${char.mp}/${char.maxMp}</span>
                <span class="token-stat">FP: ${fpValue}</span>
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

    if (!actorSelect) return;

    function populateSelectors() {
        const currentActor = actorSelect.value;
        const currentTarget = targetSelect.value;
        actorSelect.innerHTML = '<option value="">-- 使用者 --</option>';
        targetSelect.innerHTML = '<option value="">-- 対象 --</option>';

        battleState.characters.forEach(char => {
            const option = `<option value="${char.id}">${char.name}</option>`;

            if (prefix === 'attacker') {
                const reEvasionBuff = char.special_buffs ? char.special_buffs.find(b => b.name === "再回避ロック") : null;
                if (reEvasionBuff) {
                    targetSelect.innerHTML += option;
                    return;
                }
            }

            targetSelect.innerHTML += option;

            if (char.gmOnly && currentUserAttribute !== 'GM') {
            } else {
                actorSelect.innerHTML += option;
            }
        });
        actorSelect.value = currentActor;
        targetSelect.value = currentTarget;
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

    // --- 「威力計算」ボタンのロジック ---
    if (!generateBtn.dataset.listenerAttached) {
        generateBtn.dataset.listenerAttached = 'true';
        generateBtn.addEventListener('click', () => {
            const actorId = actorSelect.value;
            let targetId = targetSelect.value;
            const selectedSkill = skillSelect.options[skillSelect.selectedIndex];

            if (!selectedSkill || !actorId) {
                powerDisplay.value = 'エラー: 使用者とスキルを指定してください。';
                commandDisplay.value = "";
                hiddenCommand.value = "";
                declareBtn.disabled = true;
                if(previewBox) previewBox.style.display = 'none';
                return;
            }

            const skillId = selectedSkill.value;
            const customSkillName = selectedSkill.dataset.customName;
            const actorState = battleState.characters.find(c => c.id === actorId);

            if (!targetId) {
                targetId = actorId;
            }

            const targetState = battleState.characters.find(c => c.id === targetId);

            powerDisplay.value = '計算中...';
            commandDisplay.value = "";
            hiddenCommand.value = "";
            declareBtn.disabled = true;
            generateBtn.disabled = true;

            if(previewBox) previewBox.style.display = 'none';

            socket.emit('request_skill_declaration', {
                room: currentRoomName,
                prefix: prefix,
                actor_id: actorId,
                target_id: targetId,
                skill_id: skillId,
                custom_skill_name: customSkillName,
                actor_state: actorState,
                target_state: targetState
            });
        });
    }

    // --- 「宣言」ボタンのロジック ---
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
                const actorAttacker = document.getElementById('actor-attacker');
                const targetAttacker = document.getElementById('target-attacker');
                actorAttacker.disabled = true;
                targetAttacker.disabled = true;
                document.getElementById('skill-attacker').disabled = false;
                document.getElementById('generate-btn-attacker').disabled = false;
                document.getElementById('declare-btn-attacker').disabled = true;
            }
        });
    }

    // --- ドロップダウン変更時のリセットロジック ---
    const resetUI = () => {
        generateBtn.disabled = false;
        skillSelect.disabled = false;

        if (prefix === 'attacker') {
            actorSelect.disabled = false;
            targetSelect.disabled = false;
        } else {
            actorSelect.disabled = true;
            targetSelect.disabled = true;
        }

        powerDisplay.value = "[威力計算待ち]";
        commandDisplay.value = "[コマンドプレビュー]";
        hiddenCommand.value = "";

        // (戦慄ペナルティのリセット)
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

    if (!actorSelect.dataset.listenerAttached) {
        actorSelect.dataset.listenerAttached = 'true';
        actorSelect.addEventListener('change', (e) => {
            updateSkillDropdown(e.target.value);
            resetUI();

            if (prefix === 'attacker') {
                const defenderTargetSelect = document.getElementById('target-defender');
                defenderTargetSelect.value = e.target.value;
                defenderTargetSelect.dispatchEvent(new Event('change'));
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
                defenderActorSelect.value = targetId;
                defenderActorSelect.dispatchEvent(new Event('change'));
            }
        });
    }

    if (!skillSelect.dataset.listenerAttached) {
        skillSelect.dataset.listenerAttached = 'true';
        skillSelect.addEventListener('change', (e) => {
            resetUI();
        });
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
    const resetAllActionUI = () => {
        const prefixes = ['attacker', 'defender'];
        prefixes.forEach(prefix => {
            document.getElementById(`actor-${prefix}`).disabled = false;
            document.getElementById(`target-${prefix}`).disabled = false;
            document.getElementById(`skill-${prefix}`).disabled = false;
            document.getElementById(`actor-${prefix}`).value = "";
            document.getElementById(`target-${prefix}`).value = "";

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
                resetAllActionUI();
                selectNextActor();
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