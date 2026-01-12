// ============================================================
// Wide Match Synced - Phase 4-5: Skill Detail + Calculation
// ============================================================
(function () {
    'use strict';
    console.log("✅ wide_match_synced.js loaded (Phase 4-5)");

    // Local state for uncommitted values
    var wideMatchLocalState = {
        attackerSkillId: null,
        attackerCommand: null,
        defenders: {}
    };
    window.wideMatchLocalState = wideMatchLocalState;

    // ============================================
    // Open Wide Match Modal
    // ============================================
    window.openSyncedWideMatchModal = function (attackerId) {
        console.log("📡 openSyncedWideMatchModal called");

        var attacker = battleState.characters && battleState.characters.find(function (c) {
            return c.id === attackerId;
        });

        if (!attacker) return;

        var attackerType = attacker.type;
        var defenderIds = battleState.characters
            .filter(function (c) {
                return c.id !== attackerId && c.hp > 0 && c.type !== attackerType;
            })
            .map(function (c) { return c.id; });

        if (defenderIds.length === 0) {
            alert('防御対象のキャラクターがいません');
            return;
        }

        wideMatchLocalState = { attackerSkillId: null, attackerCommand: null, defenders: {} };
        window.wideMatchLocalState = wideMatchLocalState;

        socket.emit('open_wide_match_modal', {
            room: currentRoomName,
            attacker_id: attackerId,
            defender_ids: defenderIds,
            mode: 'individual'
        });
    };

    // ============================================
    // Populate Wide Match Panel
    // ============================================
    window.populateWideMatchPanel = function (matchData) {
        console.log("📋 populateWideMatchPanel called");

        var container = document.getElementById('wide-match-container');
        if (!container) return;

        // Load skill data if needed
        if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
            fetch('/api/get_skill_data')
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    window.allSkillData = data;
                    window.populateWideMatchPanel(matchData);
                });
            return;
        }

        var attacker = matchData.attacker_snapshot ||
            (battleState.characters && battleState.characters.find(function (c) {
                return c.id === matchData.attacker_id;
            }));

        if (!attacker) return;

        var defenders = matchData.defenders || [];

        // Update attacker section
        var attackerNameEl = document.getElementById('wide-attacker-name');
        if (attackerNameEl) attackerNameEl.textContent = attacker.name;

        // Populate attacker skill select
        populateAttackerSkillSelect(attacker, matchData);

        // Update defender count
        var defenderCountEl = document.getElementById('wide-defender-count');
        if (defenderCountEl) defenderCountEl.textContent = defenders.length;

        // Populate defender cards
        populateDefenderCards(defenders, matchData);

        // Setup event listeners (Phase 4-5)
        setupWideMatchEventListeners(matchData);

        // Show container
        container.style.display = '';
    };

    // ============================================
    // Populate Attacker Skill Select
    // ============================================
    function populateAttackerSkillSelect(attacker, matchData) {
        var selectEl = document.getElementById('wide-attacker-skill');
        if (!selectEl) return;

        selectEl.innerHTML = '<option value="">-- 広域スキル選択 --</option>';

        if (!attacker.commands) return;

        var regex = /【(.*?)\s+(.*?)】/g;
        var match;

        while ((match = regex.exec(attacker.commands)) !== null) {
            var skillId = match[1];
            var skillName = match[2];
            var skillData = window.allSkillData[skillId];

            if (skillData && window.isWideSkillData && window.isWideSkillData(skillData)) {
                var option = document.createElement('option');
                option.value = skillId;
                option.textContent = skillId + ': ' + skillName;
                selectEl.appendChild(option);
            }
        }

        if (matchData.attacker_data && matchData.attacker_data.skill_id) {
            selectEl.value = matchData.attacker_data.skill_id;
        } else {
            selectEl.value = "";
        }

        selectEl.disabled = matchData.attacker_declared || !canControlCharacter(matchData.attacker_id);
    }

    // ============================================
    // Populate Defender Cards
    // ============================================
    function populateDefenderCards(defenders, matchData) {
        var listEl = document.getElementById('wide-defenders-list');
        if (!listEl) return;

        listEl.innerHTML = '';

        defenders.forEach(function (def, index) {
            var defChar = (battleState.characters && battleState.characters.find(function (c) {
                return c.id === def.id;
            })) || def.snapshot;

            if (!defChar) return;

            var card = createDefenderCard(defChar, def, matchData, index);
            listEl.appendChild(card);
        });
    }

    // ============================================
    // Create Single Defender Card
    // ============================================
    function createDefenderCard(defChar, defData, matchData, index) {
        var canControl = canControlCharacter(defData.id);
        var isDeclared = defData.declared;

        var card = document.createElement('div');
        card.className = 'wide-defender-card' + (isDeclared ? ' declared' : '');
        card.dataset.defenderId = defData.id;
        card.dataset.index = index;

        // Header
        var header = document.createElement('div');
        header.className = 'wide-defender-header';

        var nameSpan = document.createElement('span');
        nameSpan.className = 'defender-name';
        nameSpan.textContent = defChar.name;
        header.appendChild(nameSpan);

        if (isDeclared) {
            var badge = document.createElement('span');
            badge.className = 'declared-badge';
            badge.textContent = '✓ 宣言済';
            header.appendChild(badge);
        }

        card.appendChild(header);

        // Body
        var body = document.createElement('div');
        body.className = 'wide-defender-body';

        var select = document.createElement('select');
        select.className = 'wide-defender-skill duel-select';
        select.dataset.defId = defData.id;
        select.disabled = isDeclared || !canControl;

        select.innerHTML = '<option value="">-- スキル選択 --</option>';
        if (defChar.commands) {
            var regex = /【(.*?)\s+(.*?)】/g;
            var match;
            while ((match = regex.exec(defChar.commands)) !== null) {
                var skillId = match[1];
                var skillData = window.allSkillData && window.allSkillData[skillId];

                // Skip immediate action and wide skills for defenders
                if (skillData) {
                    var tags = skillData.tags || [];
                    var isImmediate = tags.indexOf('即時発動') >= 0;
                    var isWide = window.isWideSkillData && window.isWideSkillData(skillData);
                    if (isImmediate || isWide) continue;
                }

                var option = document.createElement('option');
                option.value = skillId;
                option.textContent = skillId + ': ' + match[2];
                select.appendChild(option);
            }
        }

        if (defData.skill_id) {
            select.value = defData.skill_id;
        }

        body.appendChild(select);

        // Info button for skill details
        var infoBtn = document.createElement('button');
        infoBtn.className = 'duel-btn info wide-def-info-btn';
        infoBtn.dataset.defId = defData.id;
        infoBtn.textContent = 'ℹ';
        infoBtn.title = 'スキル詳細を表示';
        infoBtn.style.cssText = 'padding:5px 10px; font-size:14px; min-width:30px;';
        body.appendChild(infoBtn);

        if (canControl && !isDeclared) {
            var calcBtn = document.createElement('button');
            calcBtn.className = 'duel-btn secondary wide-def-calc-btn';
            calcBtn.dataset.defId = defData.id;
            calcBtn.textContent = '計算';
            body.appendChild(calcBtn);

            var declBtn = document.createElement('button');
            declBtn.className = 'duel-btn primary wide-def-declare-btn';
            declBtn.dataset.defId = defData.id;
            declBtn.textContent = '宣言';
            declBtn.disabled = true;
            body.appendChild(declBtn);
        }

        card.appendChild(body);

        // Result area
        var resultDiv = document.createElement('div');
        resultDiv.className = 'wide-defender-result';
        resultDiv.id = 'wide-def-result-' + defData.id;
        card.appendChild(resultDiv);

        // Restore calculation result - from server or local state
        // Priority: server declared data > local state
        if (defData.declared && defData.command) {
            // Declared via server (another user or self)
            if (defData.min !== undefined && defData.max !== undefined) {
                resultDiv.innerHTML = '<span style="color:#28a745;font-weight:bold;">宣言済 Range: ' + defData.min + '~' + defData.max + '</span> (' + defData.command + ')';
            } else {
                resultDiv.innerHTML = '<span style="color:#28a745;font-weight:bold;">宣言済</span> (' + defData.command + ')';
            }
        } else if (window.wideMatchLocalState &&
            window.wideMatchLocalState.defenders &&
            window.wideMatchLocalState.defenders[defData.id]) {

            var saved = window.wideMatchLocalState.defenders[defData.id];
            if (saved.command) {
                // If min/max saved use them, otherwise showing command only
                if (saved.min !== undefined && saved.max !== undefined) {
                    resultDiv.innerHTML = '<span style="color:#007bff;font-weight:bold;">Range: ' + saved.min + '~' + saved.max + '</span> (' + saved.command + ')';
                } else {
                    resultDiv.innerHTML = '<span style="color:#007bff;font-weight:bold;">Command: ' + saved.command + '</span>';
                }
            }
        }

        // Skill detail area (initially hidden)
        var skillDetailDiv = document.createElement('div');
        skillDetailDiv.className = 'wide-defender-skill-detail';
        skillDetailDiv.id = 'wide-def-skill-detail-' + defData.id;
        skillDetailDiv.style.cssText = 'display:none; padding:10px; background:#f8f9fa; border-radius:4px; margin-top:5px; font-size:0.9em;';
        card.appendChild(skillDetailDiv)

        return card;
    }

    // ============================================
    // Phase 4: Update Skill Detail Display
    // ============================================
    function updateWideSkillDetail(skillId) {
        var detailDiv = document.getElementById('wide-attacker-skill-detail');
        if (!detailDiv) {
            console.error("❌ detailDiv not found!");
            return;
        }

        if (!skillId || !window.allSkillData || !window.allSkillData[skillId]) {
            detailDiv.innerHTML = '<span class="placeholder">スキルを選択すると詳細が表示されます</span>';
            return;
        }

        var skill = window.allSkillData[skillId];

        // Debug: log skill data
        console.log("📋 Wide Match Skill data:", {
            skillId: skillId,
            '使用時効果': skill['使用時効果'],
            '発動時効果': skill['発動時効果'],
            '特記': skill['特記']
        });

        var generatedHTML = '';
        if (typeof window.formatSkillDetailHTML === 'function') {
            generatedHTML = window.formatSkillDetailHTML(skill);
            console.log("🔧 formatSkillDetailHTML available, generated HTML length:", generatedHTML.length);
            console.log("🔧 Generated HTML preview:", generatedHTML.substring(0, 200));
        } else {
            console.error("❌ formatSkillDetailHTML NOT AVAILABLE!");
            generatedHTML = '<div><strong>効果:</strong> ' + (skill['発動時効果'] || '---') + '</div>';
        }

        detailDiv.innerHTML = generatedHTML;
        console.log("✅ Skill detail updated for:", skillId, "HTML set to detailDiv");
    }

    // ============================================
    // Phase 4: Update Mode Badge
    // ============================================
    function updateWideModeBadge(skillId) {
        var modeLabel = document.getElementById('wide-mode-label');
        var modeInput = document.getElementById('wide-mode-select');
        if (!modeLabel || !modeInput) return;

        var mode = 'individual';
        var label = '個別';

        if (skillId && window.allSkillData && window.allSkillData[skillId]) {
            var skill = window.allSkillData[skillId];
            // Check 距離 field for mode, not tags
            var dist = skill['距離'] || '';
            if (dist.indexOf('広域-合算') >= 0) {
                mode = 'combined';
                label = '合算';
            } else if (dist.indexOf('広域-個別') >= 0) {
                mode = 'individual';
                label = '個別';
            }
        }

        modeLabel.textContent = label;
        modeInput.value = mode;
        console.log("✅ Mode updated:", label, "(from 距離 field)");
    }

    // ============================================
    // Phase 5: Calculate Skill Command
    // ============================================
    function calculateSkillCommand(char, skillData) {
        var cmd = skillData['チャットパレット'] || '';
        if (!cmd) return { command: '', min: 0, max: 0 };

        // Resolve placeholders
        if (char.params) {
            char.params.forEach(function (p) {
                var placeholder = '{' + p.label + '}';
                var regex = new RegExp(placeholder.replace(/[{}]/g, '\\$&'), 'g');
                cmd = cmd.replace(regex, p.value || '0');
            });
        }

        // Remove skill prefix
        cmd = cmd.replace(/【.*?】/g, '').trim();

        // Calculate min/max from dice
        var minResult = cmd;
        var maxResult = cmd;
        var diceMatches = cmd.match(/(\d+)d(\d+)/g) || [];

        diceMatches.forEach(function (diceExpr) {
            var parts = diceExpr.match(/(\d+)d(\d+)/);
            var numDice = parseInt(parts[1]);
            var numFaces = parseInt(parts[2]);
            minResult = minResult.replace(diceExpr, String(numDice));
            maxResult = maxResult.replace(diceExpr, String(numDice * numFaces));
        });

        var min = 0, max = 0;
        try {
            min = eval(minResult.replace(/[^-()\d/*+.]/g, '')) || 0;
            max = eval(maxResult.replace(/[^-()\d/*+.]/g, '')) || 0;
        } catch (e) { }

        return { command: cmd, min: min, max: max };
    }

    // ============================================
    // Phase 4-5: Setup Event Listeners
    // ============================================
    function setupWideMatchEventListeners(matchData) {
        // ★ 強制リセット: 全てのボタン状態を初期化（古い状態を引き継がないように）
        var attackerSkillSelect = document.getElementById('wide-attacker-skill');
        var attackerCalcBtn = document.getElementById('wide-attacker-calc-btn');
        var attackerDeclareBtn = document.getElementById('wide-attacker-declare-btn');
        var attackerResultDiv = document.getElementById('wide-attacker-result');

        // まず全てを有効化・リセット
        if (attackerSkillSelect) {
            attackerSkillSelect.disabled = false;
        }
        if (attackerCalcBtn) {
            attackerCalcBtn.disabled = false;
        }
        if (attackerDeclareBtn) {
            attackerDeclareBtn.disabled = true; // 計算前は無効
            attackerDeclareBtn.textContent = '宣言';
        }
        if (attackerResultDiv) {
            attackerResultDiv.innerHTML = '';
        }

        // Attacker skill select change
        if (attackerSkillSelect) {
            attackerSkillSelect.onchange = function () {
                wideMatchLocalState.attackerSkillId = this.value;
                updateWideModeBadge(this.value);
                updateWideSkillDetail(this.value);
            };

            // ★ 修正: スキルが選択されていない場合もリセット表示を行う
            updateWideModeBadge(attackerSkillSelect.value);
            updateWideSkillDetail(attackerSkillSelect.value);
        }

        // Initialize attacker button states based on server declared status
        // ★ デバッグログ追加
        console.log("🔍 setupWideMatchEventListeners matchData:", {
            attacker_declared: matchData.attacker_declared,
            attacker_data: matchData.attacker_data
        });

        // ★ 修正: attacker_declared が明示的に true の場合のみ無効化
        // また、attacker_data にスキル情報がない場合は新規マッチとみなしてスキップ
        if (matchData.attacker_declared === true && matchData.attacker_data && matchData.attacker_data.skill_id) {
            // Attacker already declared - disable all controls
            if (attackerCalcBtn) {
                attackerCalcBtn.disabled = true;
            }
            if (attackerDeclareBtn) {
                attackerDeclareBtn.disabled = true;
                attackerDeclareBtn.textContent = '宣言済';
            }
            // Restore attacker result from server data with range if available
            if (attackerResultDiv && matchData.attacker_data.command) {
                var displayText = '宣言済';
                if (matchData.attacker_data.min !== undefined && matchData.attacker_data.max !== undefined) {
                    displayText += ' Range: ' + matchData.attacker_data.min + '~' + matchData.attacker_data.max;
                }
                attackerResultDiv.innerHTML = '<span style="color:#dc3545;font-weight:bold;">' + displayText + '</span> (' + matchData.attacker_data.command + ')';
            }
        }

        // Attacker calc button
        var attackerCalcBtn = document.getElementById('wide-attacker-calc-btn');
        if (attackerCalcBtn) {
            attackerCalcBtn.onclick = function () {
                var skillId = attackerSkillSelect ? attackerSkillSelect.value : '';
                if (!skillId) {
                    alert('スキルを選択してください');
                    return;
                }

                var attacker = matchData.attacker_snapshot ||
                    (battleState.characters && battleState.characters.find(function (c) {
                        return c.id === matchData.attacker_id;
                    }));
                var skillData = window.allSkillData[skillId];
                if (!skillData || !attacker) return;

                var result = calculateSkillCommand(attacker, skillData);
                wideMatchLocalState.attackerCommand = result.command;

                var resultDiv = document.getElementById('wide-attacker-result');
                if (resultDiv) {
                    resultDiv.innerHTML = '<span style="color:#dc3545;font-weight:bold;">Range: ' + result.min + '~' + result.max + '</span> (' + result.command + ')';
                    resultDiv.dataset.command = result.command;
                    resultDiv.dataset.minDamage = result.min;
                    resultDiv.dataset.maxDamage = result.max;
                }

                var declareBtn = document.getElementById('wide-attacker-declare-btn');
                if (declareBtn) declareBtn.disabled = false;

                console.log("✅ Attacker calc result:", result);
            };
        }

        // Defender skill dropdown change - close info panel when skill changes
        document.querySelectorAll('.wide-defender-skill').forEach(function (select) {
            select.onchange = function () {
                var defId = this.dataset.defId;
                var detailDiv = document.getElementById('wide-def-skill-detail-' + defId);
                if (detailDiv) {
                    detailDiv.style.display = 'none';
                }
            };
        });

        // Defender calc buttons (event delegation)
        document.querySelectorAll('.wide-def-calc-btn').forEach(function (btn) {
            btn.onclick = function () {
                var defId = this.dataset.defId;
                var select = document.querySelector('.wide-defender-skill[data-def-id="' + defId + '"]');
                var skillId = select ? select.value : '';

                if (!skillId) {
                    alert('スキルを選択してください');
                    return;
                }

                var defChar = battleState.characters && battleState.characters.find(function (c) {
                    return c.id === defId;
                });
                var skillData = window.allSkillData[skillId];
                if (!skillData || !defChar) return;

                var result = calculateSkillCommand(defChar, skillData);

                if (!wideMatchLocalState.defenders[defId]) {
                    wideMatchLocalState.defenders[defId] = {};
                }
                wideMatchLocalState.defenders[defId].skillId = skillId;
                wideMatchLocalState.defenders[defId].command = result.command;
                wideMatchLocalState.defenders[defId].min = result.min;
                wideMatchLocalState.defenders[defId].max = result.max;

                var resultDiv = document.getElementById('wide-def-result-' + defId);
                if (resultDiv) {
                    resultDiv.innerHTML = '<span style="color:#007bff;font-weight:bold;">Range: ' + result.min + '~' + result.max + '</span> (' + result.command + ')';
                    resultDiv.dataset.command = result.command;
                }

                var declareBtn = document.querySelector('.wide-def-declare-btn[data-def-id="' + defId + '"]');
                if (declareBtn) declareBtn.disabled = false;

                console.log("✅ Defender calc result:", defId, result);
            };
        });

        // Defender info buttons
        document.querySelectorAll('.wide-def-info-btn').forEach(function (btn) {
            btn.onclick = function () {
                var defId = this.dataset.defId;
                var select = document.querySelector('.wide-defender-skill[data-def-id="' + defId + '"]');
                var skillId = select ? select.value : '';
                var detailDiv = document.getElementById('wide-def-skill-detail-' + defId);

                if (!detailDiv) return;

                // Toggle visibility
                if (detailDiv.style.display === 'none' || !detailDiv.style.display) {
                    if (skillId && window.allSkillData && window.allSkillData[skillId]) {
                        var skillData = window.allSkillData[skillId];
                        if (typeof window.formatSkillDetailHTML === 'function') {
                            detailDiv.innerHTML = window.formatSkillDetailHTML(skillData);
                        } else {
                            detailDiv.innerHTML = '<div>スキル情報を読み込めません</div>';
                        }
                        detailDiv.style.display = 'block';
                    } else {
                        detailDiv.innerHTML = '<div style="color:#888;">スキルを選択してください</div>';
                        detailDiv.style.display = 'block';
                    }
                } else {
                    detailDiv.style.display = 'none';
                }
            };
        });

        // ============================================
        // Phase 6: Attacker Declare Button
        // ============================================
        var attackerDeclareBtn = document.getElementById('wide-attacker-declare-btn');
        if (attackerDeclareBtn) {
            attackerDeclareBtn.onclick = function () {
                var skillId = attackerSkillSelect ? attackerSkillSelect.value : '';
                var command = wideMatchLocalState.attackerCommand;

                if (!skillId || !command) {
                    alert('先に計算を実行してください');
                    return;
                }

                // ★ FP/MPコストチェック（特記処理.cost配列を使用）
                var skillData = window.allSkillData[skillId];
                var attacker = matchData.attacker_snapshot || (battleState.characters && battleState.characters.find(function (c) { return c.id === matchData.attacker_id; }));
                if (skillData && attacker) {
                    try {
                        var ruleJson = skillData['特記処理'] || '{}';
                        var ruleData = JSON.parse(ruleJson);
                        var costs = ruleData.cost || [];
                        for (var i = 0; i < costs.length; i++) {
                            var cost = costs[i];
                            var costType = cost.type;
                            var costValue = parseInt(cost.value || 0, 10);
                            if (costValue > 0 && costType) {
                                var currentVal = 0;
                                if (costType === 'FP') currentVal = attacker.fp || 0;
                                else if (costType === 'MP') currentVal = attacker.mp || 0;
                                if (currentVal < costValue) {
                                    alert(costType + 'が不足しています。必要: ' + costValue + ', 現在: ' + currentVal);
                                    return;
                                }
                            }
                        }
                    } catch (e) {
                        console.log('Cost check parse error:', e);
                    }
                }

                // ★ レンジ情報を取得
                var resultDiv = document.getElementById('wide-attacker-result');
                var minDmg = resultDiv && resultDiv.dataset.minDamage ? resultDiv.dataset.minDamage : '';
                var maxDmg = resultDiv && resultDiv.dataset.maxDamage ? resultDiv.dataset.maxDamage : '';

                socket.emit('wide_attacker_declare', {
                    room: currentRoomName,
                    skill_id: skillId,
                    command: command,
                    min: minDmg,
                    max: maxDmg
                });

                // Disable button and update display with range preserved
                this.disabled = true;
                this.textContent = '宣言済';

                if (resultDiv && minDmg && maxDmg) {
                    resultDiv.innerHTML = '<span style="color:#dc3545;font-weight:bold;">宣言済 Range: ' + minDmg + '~' + maxDmg + '</span> (' + command + ')';
                }

                console.log("✅ Attacker declared:", skillId, command);
            };
        }

        // ============================================
        // Phase 6: Defender Declare Buttons
        // ============================================
        document.querySelectorAll('.wide-def-declare-btn').forEach(function (btn) {
            btn.onclick = function () {
                var defId = this.dataset.defId;
                var localData = wideMatchLocalState.defenders[defId];

                if (!localData || !localData.skillId || !localData.command) {
                    alert('先に計算を実行してください');
                    return;
                }

                socket.emit('wide_declare_skill', {
                    room: currentRoomName,
                    defender_id: defId,
                    skill_id: localData.skillId,
                    command: localData.command,
                    min: localData.min,
                    max: localData.max
                });

                this.disabled = true;
                this.textContent = '宣言済';
                console.log("✅ Defender declared:", defId, localData.skillId);
            };
        });

        // ============================================
        // Phase 8: Execute Button
        // ============================================
        var executeBtn = document.getElementById('wide-execute-btn');
        if (executeBtn) {
            // Only GM or attacker owner can execute
            var canExecute = canControlCharacter(matchData.attacker_id);

            if (!canExecute) {
                executeBtn.disabled = true;
                executeBtn.title = 'GMまたは攻撃者の所有者のみ実行可能';
            }

            executeBtn.onclick = function () {
                // Double-check permission
                if (!canControlCharacter(matchData.attacker_id)) {
                    alert('GMまたは攻撃者の所有者のみがマッチを実行できます。');
                    return;
                }

                socket.emit('execute_synced_wide_match', {
                    room: currentRoomName
                });

                this.disabled = true;
                this.textContent = '実行中...';
                console.log("✅ Wide match execution requested");
            };
        }

        // ============================================
        // Update Execute Button State
        // ============================================
        updateExecuteButtonState(matchData);
    }

    // ============================================
    // Check if all declared and enable execute button
    // ============================================
    function updateExecuteButtonState(matchData) {
        var executeBtn = document.getElementById('wide-execute-btn');
        if (!executeBtn) return;

        var attackerDeclared = matchData.attacker_declared;
        var allDefendersDeclared = matchData.defenders && matchData.defenders.length > 0 &&
            matchData.defenders.every(function (d) {
                return d.declared;
            });

        executeBtn.disabled = !(attackerDeclared && allDefendersDeclared);

        // Update status text
        var statusDiv = document.getElementById('wide-status');
        if (statusDiv) {
            if (attackerDeclared && allDefendersDeclared) {
                statusDiv.innerHTML = '<span style="color:#28a745;">全員宣言完了！実行可能</span>';
            } else {
                var pending = [];
                if (!attackerDeclared) pending.push('攻撃者');
                if (matchData.defenders) {
                    var undeclared = matchData.defenders.filter(function (d) { return !d.declared; });
                    if (undeclared.length > 0) pending.push('防御者' + undeclared.length + '人');
                }
                statusDiv.innerHTML = '<span class="waiting">宣言待ち: ' + pending.join(', ') + '</span>';
            }
        }
    }

    // Export for external use
    window.updateWideExecuteButtonState = updateExecuteButtonState;

})();
