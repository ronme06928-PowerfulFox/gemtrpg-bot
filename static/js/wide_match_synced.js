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
        // Attacker skill select change
        var attackerSkillSelect = document.getElementById('wide-attacker-skill');
        if (attackerSkillSelect) {
            attackerSkillSelect.onchange = function () {
                wideMatchLocalState.attackerSkillId = this.value;
                updateWideModeBadge(this.value);
                updateWideSkillDetail(this.value);
            };

            // Trigger for initial selection
            if (attackerSkillSelect.value) {
                updateWideModeBadge(attackerSkillSelect.value);
                updateWideSkillDetail(attackerSkillSelect.value);
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

                var resultDiv = document.getElementById('wide-def-result-' + defId);
                if (resultDiv) {
                    resultDiv.innerHTML = '<span style="color:#007bff;font-weight:bold;">Range: ' + result.min + '~' + result.max + '</span> (' + result.command + ')';
                    resultDiv.dataset.command = result.command;
                }

                var declareBtn = document.querySelector('.wide-def-declare-btn[data-def-id="' + defId + '"]');
                if (declareBtn) declareBtn.disabled = false;

                // Auto-close info panel after calculation
                var detailDiv = document.getElementById('wide-def-skill-detail-' + defId);
                if (detailDiv) {
                    detailDiv.style.display = 'none';
                }

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
    }

})();
