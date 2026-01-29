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

        // ★ 権限チェック: 攻撃者の所有者またはGMのみが実行可能
        var isOwner = attacker.owner === currentUsername;
        var isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

        // ★ 重要: openSyncedWideMatchModal は "開始" のための関数。
        // リロード時の "再表示" は populateWideMatchPanel 等で行われるため、
        // ここで弾いても同期表示や再表示には影響しない。
        if (!isOwner && !isGM) {
            alert("キャラクターの所有者またはGMのみがマッチを開始できます。");
            return;
        }

        var attackerType = attacker.type;
        var defenderIds = battleState.characters
            .filter(function (c) {
                // フィールドに配置されている（x, y座標が0以上）キャラのみを対象
                // 未配置キャラは x=-1 となっている場合があるため、値のチェックも行う
                var isPlaced = (c.x !== undefined && c.x !== null && c.x >= 0 && c.y !== undefined && c.y !== null && c.y >= 0);
                return c.id !== attackerId && c.hp > 0 && c.type !== attackerType && isPlaced;
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
    // Phase 9: Differential Updates (Latency Optimization)
    // ============================================
    // Socket初期化後に呼び出すための関数
    window.initWideMatchSocketListeners = function () {
        if (typeof socket === 'undefined') {
            console.warn("⚠️ socket is undefined in initWideMatchSocketListeners");
            return;
        }
        console.log("📡 Initializing Wide Match Differential Listeners");

        // これらのリスナーは初期化時に一度だけ登録されるべきですが、
        // wide_match_synced.js は通常読み込みっぱなしなのでここで登録します。
        // 二重登録防止のため、フラグチェックをするか、既に登録済みならoffしてからonします。

        socket.off('wide_defender_updated');
        socket.on('wide_defender_updated', function (data) {
            // console.log("⚡ wide_defender_updated received:", data);
            var defId = data.defender_id;

            // 1. Update button state in UI
            var btn = document.querySelector('.wide-def-declare-btn[data-def-id="' + defId + '"]');
            var statusSpan = document.getElementById('wide-def-status-' + defId);

            if (btn) {
                btn.disabled = true;
                btn.textContent = '宣言済';
                btn.classList.add('locked');
            }
            if (statusSpan) {
                statusSpan.textContent = '宣言完了';
                statusSpan.style.color = 'green';
                statusSpan.style.fontWeight = 'bold';
            }

            // 2. Update local battleState (Optimistic / Consistency)
            // これをしておかないと、別の要因で populateWideMatchPanel が呼ばれた時に
            // ボタンが「未宣言」に戻ってしまう（Full Stateが来るまでは）。
            if (window.battleState && window.battleState.active_match) {
                if (window.battleState.active_match.defenders) {
                    // 型変換して比較 (defIdは文字列で来る可能性が高いが、state内は数値の可能性も)
                    var def = window.battleState.active_match.defenders.find(function (d) { return String(d.id) === String(defId); });
                    if (def) {
                        def.declared = true;
                        // ★ data (command詳細) もマージ
                        if (data.data) {
                            def.data = data.data;
                        }

                        // ★ 完全な再描画を行う (緑色のスタイルなどを適用するため)
                        if (typeof window.populateWideMatchPanel === 'function') {
                            window.populateWideMatchPanel(window.battleState.active_match);
                        }
                    } else {
                        console.warn("⚠️ defender not found in local state:", defId);
                    }
                } else {
                    console.warn("⚠️ battleState.active_match.defenders is missing");
                }
            } else {
                console.warn("⚠️ battleState or active_match is missing");
            }

            // 3. Check execution state
            // battleState.active_match を更新したので、それを渡してチェック
            if (window.battleState && window.battleState.active_match) {
                if (window.updateWideExecuteButtonState) {
                    window.updateWideExecuteButtonState(window.battleState.active_match);
                }
            }
        });

        socket.off('wide_attacker_updated');
        socket.on('wide_attacker_updated', function (data) {
            // console.log("⚡ wide_attacker_updated received:", data);

            // 1. Update UI
            var declareBtn = document.getElementById('wide-attacker-declare-btn');
            var calcBtn = document.getElementById('wide-attacker-calc-btn');

            if (declareBtn) {
                declareBtn.disabled = true;
                declareBtn.textContent = '宣言済';
            }
            if (calcBtn) {
                calcBtn.disabled = true;
            }

            // 2. Update local state
            if (window.battleState && window.battleState.active_match) {
                window.battleState.active_match.attacker_declared = true;

                // ★ data (command詳細) もマージ
                if (data.data) {
                    window.battleState.active_match.attacker_data = data.data;
                }

                // data.attacker_id がある場合、念のためチェック
                if (data.attacker_id && String(window.battleState.active_match.attacker_id) !== String(data.attacker_id)) {
                    console.warn("⚠️ Attacker ID mismatch in event vs local state");
                }

                // ★ 完全な再描画を行う
                if (typeof window.populateWideMatchPanel === 'function') {
                    window.populateWideMatchPanel(window.battleState.active_match);
                }

            } else {
                console.warn("⚠️ battleState or active_match is missing (Attacker)");
            }

            // 3. Execution Check
            if (window.battleState && window.battleState.active_match) {
                if (window.updateWideExecuteButtonState) {
                    window.updateWideExecuteButtonState(window.battleState.active_match);
                }
            }
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

        // ★ 新規マッチ時（または攻撃者が変わった時）はローカルキャッシュをリセット
        if (!window._prevWideMatchAttackerId || window._prevWideMatchAttackerId !== matchData.attacker_id) {
            window._wideLocalCalcCache = { attacker: null, defenders: {} };
            window._prevWideMatchAttackerId = matchData.attacker_id;
        }

        var defenders = matchData.defenders || [];

        // Update attacker section
        var attackerNameEl = document.getElementById('wide-attacker-name');
        if (attackerNameEl) {
            attackerNameEl.textContent = attacker.name;
            // ★ 詳細リンク
            attackerNameEl.style.cursor = "pointer";
            attackerNameEl.title = "クリックで詳細を表示";
            attackerNameEl.onclick = function (e) {
                e.stopPropagation();
                if (window.showCharacterDetail) window.showCharacterDetail(attacker.id);
            };
        }

        // ★ 攻撃者ステータス表示
        // renderCharacterStatsBar は tab_visual_battle.js にあるが、グローバルスコープで利用可能か確認が必要
        // tab_visual_battle.js は <script> で読み込まれており、strict mode IIFE でない限りグローバル関数になるはず。
        // 確認上 tab_visual_battle.js の関数定義は `function renderCharacterStatsBar...` なのでグローバル。
        // ★ 攻撃者ステータス表示 (Compact Mode)
        if (window.renderCharacterStatsBar) {
            window.renderCharacterStatsBar(attacker, 'wide-attacker-stats', { compact: true, theme: 'dark' });
        }

        // Populate attacker skill select
        populateAttackerSkillSelect(attacker, matchData);

        // Update defender count
        var defenderCountEl = document.getElementById('wide-defender-count');
        if (defenderCountEl) defenderCountEl.textContent = defenders.length;

        // Populate defender cards
        populateDefenderCards(defenders, matchData);

        // Setup event listeners (Phase 4-5)
        setupWideMatchEventListeners(matchData);

        // ★追加: GM用 強制終了ボタンの注入（パネルヘッダーボタン群に配置）
        // 重複防止のため、両方のIDを削除
        var existingForceEndBtn = document.getElementById('wide-force-end-match-btn');
        if (existingForceEndBtn) existingForceEndBtn.remove();
        var existingDuelBtn = document.getElementById('force-end-match-btn');
        if (existingDuelBtn) existingDuelBtn.remove();

        var isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
        if (isGM) {
            var headerButtons = document.querySelector('.panel-header-buttons');
            var reloadBtn = document.getElementById('panel-reload-btn');

            // 既にどちらかのボタンが存在しない場合のみ追加
            if (headerButtons && reloadBtn && !document.getElementById('wide-force-end-match-btn') && !document.getElementById('force-end-match-btn')) {
                var forceEndBtn = document.createElement('button');
                forceEndBtn.id = 'wide-force-end-match-btn';
                forceEndBtn.className = 'panel-reload-btn'; // 更新ボタンと同じクラス
                forceEndBtn.innerHTML = '⚠️';
                forceEndBtn.title = 'GM権限でマッチを強制終了します';
                forceEndBtn.style.cssText = 'background-color:#dc3545; color:white; border:1px solid #bd2130;';

                forceEndBtn.onclick = function (e) {
                    e.stopPropagation();
                    if (confirm('【GM権限】マッチを強制終了しますか？\n現在行われているマッチ、または意図せず開いているマッチ画面を閉じます。\nこの操作は元に戻せません。')) {
                        if (socket) socket.emit('request_force_end_match', { room: currentRoomName });
                    }
                };

                // 更新ボタンの前に挿入
                headerButtons.insertBefore(forceEndBtn, reloadBtn);
            }
        }

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
    // Populate Defender Cards (差分更新方式)
    // ============================================
    // ★ 前回のマッチIDを記憶して、新しいマッチかどうかを判定
    var _lastWideMatchAttackerId = null;

    function populateDefenderCards(defenders, matchData) {
        var listEl = document.getElementById('wide-defenders-list');
        if (!listEl) return;

        var currentAttackerId = matchData.attacker_id;

        // ★ 新しいマッチ（攻撃者が変わった）場合はフルリセット
        if (_lastWideMatchAttackerId !== currentAttackerId) {
            console.log("📋 New wide match detected, full reset");
            listEl.innerHTML = '';
            _lastWideMatchAttackerId = currentAttackerId;

            // 新規マッチなので全カードを新規作成
            defenders.forEach(function (def, index) {
                var defChar = (battleState.characters && battleState.characters.find(function (c) {
                    return c.id === def.id;
                })) || def.snapshot;

                if (!defChar) return;

                var card = createDefenderCard(defChar, def, matchData, index);
                listEl.appendChild(card);
            });
            return;
        }

        // ★ 同じマッチ内での更新 → 差分更新
        console.log("📋 Same match, incremental update");

        // 既存のカードを取得して選択状態を保持
        var existingCards = {};
        var existingSelections = {};
        listEl.querySelectorAll('.wide-defender-card').forEach(function (card) {
            var defId = card.dataset.defenderId;
            if (defId) {
                existingCards[defId] = card;
                // 未宣言のスキル選択値を保存
                var select = card.querySelector('.wide-defender-skill');
                if (select && select.value) {
                    existingSelections[defId] = select.value;
                }
            }
        });

        defenders.forEach(function (def, index) {
            var defChar = (battleState.characters && battleState.characters.find(function (c) {
                return c.id === def.id;
            })) || def.snapshot;

            if (!defChar) return;

            var existingCard = existingCards[def.id];

            // ★ 既存のカードがあり、宣言状態が変わっていなければ更新のみ
            if (existingCard) {
                var wasDecl = existingCard.classList.contains('declared');
                var nowDecl = def.declared;

                if (wasDecl === nowDecl) {
                    // Update Aux Info (Modifiers) even if input is preserved
                    updateDefenderAuxInfo(existingCard, def);

                    // If declared, ensure Range/Command display is updated (for dynamic mods)
                    if (nowDecl) {
                        var resultDiv = existingCard.querySelector('.wide-defender-result');
                        var cmd = def.final_command || def.command;
                        if (resultDiv && cmd) {
                            var rangeText = '';
                            if (def.damage_range_text) {
                                rangeText = 'Range: ' + def.damage_range_text;
                            } else if (def.min !== undefined && def.max !== undefined) {
                                rangeText = 'Range: ' + def.min + '~' + def.max;
                            } else {
                                rangeText = 'Command: ' + cmd;
                            }

                            var detailText = '';
                            // correction_details
                            var corrections = def.correction_details || (def.data && def.data.correction_details);
                            var bd = def.power_breakdown || (def.data && def.data.power_breakdown);
                            var hasCorrections = corrections && corrections.length > 0;

                            if (!hasCorrections && bd) {
                                var mod = bd.base_power_mod;
                                if (mod && mod !== 0) {
                                    detailText += '\n[基礎威力 ' + (mod > 0 ? '+' : '') + mod + ']';
                                }
                            }

                            if (def.senritsu_dice_reduction && def.senritsu_dice_reduction > 0) {
                                detailText += '\n(戦慄: ダイス-' + def.senritsu_dice_reduction + ')';
                            }

                            if (hasCorrections) {
                                corrections.forEach(function (d) {
                                    var sign = d.value > 0 ? '+' : '';
                                    detailText += '\n[' + d.source + ' ' + sign + d.value + ']';
                                });
                            }

                            resultDiv.innerHTML = '<span style="color:#28a745;font-weight:bold;white-space:pre-line;">宣言済 ' + rangeText + ' (' + cmd + ')' + detailText + '</span>';
                        }
                    }

                    // 宣言状態が同じなら何もしない（選択値を維持）
                    delete existingCards[def.id]; // 処理済みマーク
                    return;
                }

                // 宣言状態が変わった場合は、既存カードを更新
                if (nowDecl && !wasDecl) {
                    // 未宣言→宣言済みに変わった
                    existingCard.classList.add('declared');

                    // ヘッダーに宣言済みバッジを追加
                    var header = existingCard.querySelector('.wide-defender-header');
                    if (header && !header.querySelector('.declared-badge')) {
                        var badge = document.createElement('span');
                        badge.className = 'declared-badge';
                        badge.textContent = '✓ 宣言済';
                        header.appendChild(badge);
                    }

                    // スキル選択を無効化
                    var select = existingCard.querySelector('.wide-defender-skill');
                    if (select) {
                        select.disabled = true;
                        if (def.skill_id) select.value = def.skill_id;
                    }

                    // 計算・宣言ボタンを削除
                    var calcBtn = existingCard.querySelector('.wide-def-calc-btn');
                    var declBtn = existingCard.querySelector('.wide-def-declare-btn');
                    if (calcBtn) calcBtn.remove();
                    if (declBtn) declBtn.remove();

                    // 結果エリアを更新
                    var resultDiv = existingCard.querySelector('.wide-defender-result');
                    var cmd = def.final_command || def.command;
                    if (resultDiv && cmd) {
                        var rangeText = '';
                        if (def.damage_range_text) {
                            rangeText = 'Range: ' + def.damage_range_text;
                        } else if (def.min !== undefined && def.max !== undefined) {
                            rangeText = 'Range: ' + def.min + '~' + def.max;
                        } else {
                            rangeText = 'Command: ' + cmd;
                        }

                        var detailText = '';
                        // correction_details
                        var corrections = def.correction_details || (def.data && def.data.correction_details);
                        var bd = def.power_breakdown || (def.data && def.data.power_breakdown);
                        var hasCorrections = corrections && corrections.length > 0;

                        if (!hasCorrections && bd) {
                            var mod = bd.base_power_mod;
                            if (mod && mod !== 0) {
                                detailText += '\n[基礎威力 ' + (mod > 0 ? '+' : '') + mod + ']';
                            }
                        }

                        if (def.senritsu_dice_reduction && def.senritsu_dice_reduction > 0) {
                            detailText += '\n(戦慄: ダイス-' + def.senritsu_dice_reduction + ')';
                        }

                        if (hasCorrections) {
                            corrections.forEach(function (d) {
                                var sign = d.value > 0 ? '+' : '';
                                detailText += '\n[' + d.source + ' ' + sign + d.value + ']';
                            });
                        }

                        resultDiv.innerHTML = '<span style="color:#28a745;font-weight:bold;white-space:pre-line;">宣言済 ' + rangeText + ' (' + cmd + ')' + detailText + '</span>';
                    }
                }

                delete existingCards[def.id]; // 処理済みマーク
                return;
            }

            // ★ 既存カードがない場合は新規作成
            var card = createDefenderCard(defChar, def, matchData, index);

            // 保存していた選択値を復元（未宣言の場合のみ）
            if (!def.declared && existingSelections[def.id]) {
                var select = card.querySelector('.wide-defender-skill');
                if (select) {
                    select.value = existingSelections[def.id];
                }
            }

            listEl.appendChild(card);
        });
    }

    // ★ マッチ終了時にリセットするための関数を公開
    window.resetWideMatchState = function () {
        _lastWideMatchAttackerId = null;
        wideMatchLocalState = { attackerSkillId: null, attackerCommand: null, defenders: {} };
        window.wideMatchLocalState = wideMatchLocalState;
    };

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
        // Flexbox for column layout
        header.style.display = 'flex';
        header.style.flexDirection = 'column';
        header.style.alignItems = 'flex-start';

        // Name and Badge Row
        var nameRow = document.createElement('div');
        nameRow.style.display = 'flex';
        nameRow.style.alignItems = 'center';
        nameRow.style.width = '100%';

        var nameSpan = document.createElement('span');
        nameSpan.className = 'defender-name';
        nameSpan.textContent = defChar.name;
        nameSpan.textContent = defChar.name;
        nameRow.appendChild(nameSpan);

        if (isDeclared) {
            var badge = document.createElement('span');
            badge.className = 'declared-badge';
            badge.textContent = '✓ 宣言済';
            badge.textContent = '✓ 宣言済';
            nameRow.appendChild(badge);
        }

        header.appendChild(nameRow);

        card.appendChild(header);

        // Body
        // ★ 防御者ステータス表示用コンテナ追加
        var statsDiv = document.createElement('div');
        statsDiv.id = 'wide-def-stats-' + defData.id;
        statsDiv.style.marginTop = '4px';  // Space between name and stats
        statsDiv.style.marginLeft = '0';   // Align left
        statsDiv.style.display = 'inline-block';
        header.appendChild(statsDiv);

        if (window.renderCharacterStatsBar) {
            // Pass element directly as it is not in DOM yet
            window.renderCharacterStatsBar(defChar, statsDiv, { compact: true, theme: 'light' });
        }

        // ★ 名前クリックで詳細
        nameSpan.style.cursor = "pointer";
        nameSpan.title = "詳細を表示";
        nameSpan.onclick = function (e) {
            e.stopPropagation();
            if (window.showCharacterDetail) window.showCharacterDetail(defData.id);
        };

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
            calcBtn.onclick = function () {
                var defId = defData.id;
                var select = document.querySelector('.wide-defender-skill[data-def-id="' + defId + '"]');
                var skillId = select ? select.value : '';

                if (!skillId) {
                    alert('スキルを選択してください');
                    return;
                }

                var skillData = window.allSkillData[skillId];
                if (!skillData || !defChar) return;

                // ★ コストチェック
                if (skillData['特記処理']) {
                    try {
                        var rule = JSON.parse(skillData['特記処理']);
                        var tags = skillData.tags || [];
                        if (rule.cost && tags.indexOf("即時発動") === -1) {
                            for (var i = 0; i < rule.cost.length; i++) {
                                var c = rule.cost[i];
                                var type = c.type;
                                var val = parseInt(c.value || 0);
                                if (val > 0 && type) {
                                    var current = 0;
                                    var key = (type === 'SAN') ? 'sanity' : (type === 'FP' || type === 'MP' || type === 'HP') ? type.toLowerCase() : null;
                                    if (key && defChar[key] !== undefined) {
                                        current = parseInt(defChar[key] || 0);
                                    } else {
                                        var found = (defChar.states || []).find(s => s.name === type);
                                        current = found ? parseInt(found.value || 0) : 0;
                                    }

                                    if (current < val) {
                                        var resDiv = document.getElementById('wide-def-result-' + defId);
                                        if (resDiv) {
                                            resDiv.innerHTML = '<span style="color:#dc3545;font-weight:bold;">⚠️ ' + type + '不足 (必要:' + val + ')</span>';
                                        }
                                        var dBtn = card.querySelector('.wide-def-declare-btn');
                                        if (dBtn) dBtn.disabled = true;
                                        return;
                                    }
                                }
                            }
                        }
                    } catch (e) { console.error(e); }
                }

                // ★ 修正: サーバー側で計算（バフ補正込み）
                socket.emit('calculate_wide_skill', {
                    room: currentRoomName,
                    char_id: defId,
                    skill_id: skillId
                });

                // 結果待ちの表示
                var resultDiv = document.getElementById('wide-def-result-' + defId);
                if (resultDiv) {
                    resultDiv.innerHTML = '<span style="color:#666;">計算中...</span>';
                }

                // ★ 計算結果を受け取るリスナーを一時的に設定
                socket.once('wide_skill_calculated', function (result) {
                    if (result.error) {
                        if (resultDiv) {
                            resultDiv.innerHTML = '<span style="color:#dc3545;">エラー: ' + result.error + '</span>';
                        }
                        return;
                    }

                    if (result.char_id === defId) {
                        // ローカルステートに保存
                        if (!wideMatchLocalState.defenders[defId]) {
                            wideMatchLocalState.defenders[defId] = {};
                        }
                        wideMatchLocalState.defenders[defId].skillId = result.skill_id;
                        wideMatchLocalState.defenders[defId].command = result.command;
                        wideMatchLocalState.defenders[defId].min = result.min;
                        wideMatchLocalState.defenders[defId].max = result.max;

                        // ★ local cache への保存 (自分が計算した場合)
                        if (!window._wideLocalCalcCache) window._wideLocalCalcCache = { attacker: null, defenders: {} };
                        window._wideLocalCalcCache.defenders[defId] = {
                            result: result,
                            skillId: select.value
                        };

                        // 表示を更新
                        if (resultDiv) {
                            var rangeText = '';
                            if (result.damage_range_text) {
                                rangeText = 'Range: ' + result.damage_range_text;
                            } else {
                                rangeText = 'Range: ' + result.min + '~' + result.max;
                            }

                            var displayText = '<span style="color:#007bff;font-weight:bold;">' + rangeText + ' (' + result.command + ')</span>';

                            // ★ 詳細な補正内訳を表示 (Declarer display logicと統一)

                            // 1. 基礎威力補正
                            // correction_detailsがあればそちらを使用
                            if (!result.correction_details || result.correction_details.length === 0) {
                                var pb = result.power_breakdown;
                                var baseMod = pb ? pb.base_power_mod : (result.base_power_mod || 0);
                                if (baseMod && baseMod !== 0) {
                                    displayText += '<br><span style="color:#666;font-size:0.9em;">[基礎威力 ' + (baseMod > 0 ? '+' : '') + baseMod + ']</span>';
                                }
                            }

                            // 2. 戦慄
                            if (result.senritsu_dice_reduction && result.senritsu_dice_reduction > 0) {
                                displayText += '<br><span style="color:#666;font-size:0.9em;">(戦慄: ダイス-' + result.senritsu_dice_reduction + ')</span>';
                            }

                            // 3. その他補正 (物理/魔法/威力/追加威力)
                            if (result.correction_details && result.correction_details.length > 0) {
                                result.correction_details.forEach(function (d) {
                                    var sign = d.value > 0 ? '+' : '';
                                    displayText += '<br><span style="color:#666;font-size:0.9em;">[' + d.source + ' ' + sign + d.value + ']</span>';
                                });
                            }

                            resultDiv.innerHTML = displayText;
                        }

                        // 宣言ボタンを有効化
                        var dBtn = card.querySelector('.wide-def-declare-btn');
                        if (dBtn) dBtn.disabled = false;

                        console.log("✅ Defender calc result (server):", result);
                    }
                });
            };
            body.appendChild(calcBtn);

            var declBtn = document.createElement('button');
            declBtn.className = 'duel-btn primary wide-def-declare-btn';
            declBtn.dataset.defId = defData.id;
            declBtn.textContent = '宣言';
            declBtn.disabled = true;

            declBtn.onclick = function () {
                var defId = defData.id; // Access from closure
                var localData = wideMatchLocalState.defenders[defId];

                if (!localData || !localData.skillId || !localData.command) {
                    alert('先に計算を実行してください');
                    return;
                }

                // ★ インラインコストチェック
                var skillData = window.allSkillData && window.allSkillData[localData.skillId];
                if (skillData && skillData['特記処理']) {
                    try {
                        var rule = JSON.parse(skillData['特記処理']);
                        // コストがある場合のみチェック（即時発動はJS側では判定難しいのでタグチェックも入れたいがあれば）
                        var tags = skillData.tags || [];
                        // 即時発動タグがあれば消費しないのでチェックしない？（サーバー側ロジックに合わせる）

                        if (rule.cost && tags.indexOf("即時発動") === -1) {
                            for (var i = 0; i < rule.cost.length; i++) {
                                var c = rule.cost[i];
                                var type = c.type;
                                var val = parseInt(c.value || 0);
                                if (val > 0 && type) {
                                    var current = 0;
                                    if (type === 'MP') current = parseInt(defChar.mp || 0); // defChar from closure
                                    else if (type === 'HP') current = parseInt(defChar.hp || 0);
                                    else {
                                        var found = (defChar.states || []).find(s => s.name === type);
                                        current = found ? parseInt(found.value || 0) : 0;
                                    }

                                    if (current < val) {
                                        // エラー表示
                                        var resDiv = document.getElementById('wide-def-result-' + defId);
                                        if (resDiv) {
                                            resDiv.innerHTML = '<span style="color:#dc3545;font-weight:bold;">⚠️ ' + type + '不足 (必要:' + val + ')</span>';
                                        } else {
                                            alert(type + "が不足しています (必要:" + val + ", 現在:" + current + ")");
                                        }
                                        return; // 中断
                                    }
                                }
                            }
                        }
                    } catch (e) { console.error(e); }
                }

                // 成功時
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
            };

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
            var cmd = defData.final_command || defData.command;

            var rangeText = '';
            if (defData.damage_range_text) {
                rangeText = 'Range: ' + defData.damage_range_text;
            } else if (defData.min !== undefined && defData.max !== undefined) {
                rangeText = 'Range: ' + defData.min + '~' + defData.max;
            } else {
                rangeText = 'Command: ' + cmd;
            }

            var detailText = '';

            // ★ 補正内訳を表示 (power_breakdown)
            // correction_detailsがある場合はそちらに基礎威力も含まれるため、重複しないように調整
            // 基本的に correction_details を優先する

            var bd = defData.power_breakdown || (defData.data && defData.data.power_breakdown);
            // correction_details がない、もしくは空の場合のみレガシー表示
            var corrections = defData.correction_details || (defData.data && defData.data.correction_details);
            var hasCorrections = corrections && corrections.length > 0;

            if (!hasCorrections && bd) {
                var mod = bd.base_power_mod;
                if (mod && mod !== 0) {
                    detailText += '\n[基礎威力 ' + (mod > 0 ? '+' : '') + mod + ']';
                }
            }

            // ★ 戦慄によるダイス減少を表示
            if (defData.senritsu_dice_reduction && defData.senritsu_dice_reduction > 0) {
                detailText += '\n(戦慄: ダイス-' + defData.senritsu_dice_reduction + ')';
            }

            // ★ 物理/魔法/威力補正の内訳を表示
            var corrections = defData.correction_details || (defData.data && defData.data.correction_details);
            if (corrections && corrections.length > 0) {
                corrections.forEach(function (d) {
                    var sign = d.value > 0 ? '+' : '';
                    detailText += '\n[' + d.source + ' ' + sign + d.value + ']';
                });
            }

            resultDiv.innerHTML = '<span style="color:#28a745;font-weight:bold;white-space:pre-line;">宣言済 ' + rangeText + detailText + '</span> (' + cmd + ')';
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

                // ★ 宣言ボタンを有効化 (Sync時に計算済みなら押せるように)
                var dBtn = card.querySelector('.wide-def-declare-btn');
                if (dBtn) dBtn.disabled = false;
            }
        } else if (window._wideLocalCalcCache && window._wideLocalCalcCache.defenders && window._wideLocalCalcCache.defenders[defData.id]) {
            // ★ local cache からの復元チェック
            var cached = window._wideLocalCalcCache.defenders[defData.id];
            var select = card.querySelector('.v-wide-def-skill-select');
            var currentSkillId = select ? select.value : '';
            if (cached.skillId === currentSkillId && currentSkillId) {
                console.log("[Sync] Restoring local wide defender calc result for", defData.id);
                var res = cached.result;
                wideMatchLocalState.defenders[defData.id] = {
                    skillId: res.skill_id,
                    command: res.command,
                    min: res.min,
                    max: res.max
                };
                var rangeText = res.damage_range_text ? 'Range: ' + res.damage_range_text : 'Range: ' + res.min + '~' + res.max;
                resultDiv.innerHTML = '<span style="color:#007bff;font-weight:bold;">' + rangeText + ' (' + res.command + ')</span>';

                var dBtn = card.querySelector('.wide-def-declare-btn');
                if (dBtn) dBtn.disabled = false;
            }
        }

        // Skill detail area (initially hidden)
        var skillDetailDiv = document.createElement('div');
        skillDetailDiv.className = 'wide-defender-skill-detail';
        skillDetailDiv.id = 'wide-def-skill-detail-' + defData.id;
        skillDetailDiv.style.cssText = 'display:none; padding:10px; background:#f8f9fa; border-radius:4px; margin-top:5px; font-size:0.9em;';
        card.appendChild(skillDetailDiv)

        updateDefenderAuxInfo(card, defData);
        return card;
    }

    // ============================================
    // Helper: Update Auxiliary Info (Modifiers)
    // ============================================
    function updateDefenderAuxInfo(card, defData) {
        if (!card || !defData) return;

        // Support both structures (data.power_breakdown or root power_breakdown)
        var bd = defData.power_breakdown || (defData.data && defData.data.power_breakdown);
        if (!bd) return;

        var mod = bd.base_power_mod || 0;

        // Remove existing badge if any
        var existingBadge = card.querySelector('.wide-def-mod-badge');
        if (existingBadge) existingBadge.remove();

        if (mod !== 0) {
            var badge = document.createElement('div');
            badge.className = 'wide-def-mod-badge';
            var sign = mod > 0 ? '+' : '';
            badge.textContent = '補正: 基礎威力 ' + sign + mod;
            badge.style.cssText = 'background:#ffc107; color:#000; padding:2px 6px; border-radius:4px; font-size:0.8em; margin-left:8px; font-weight:bold; display:inline-block;';

            // Insert in Header
            var header = card.querySelector('.wide-defender-header');
            if (header) {
                header.appendChild(badge);
            }
        }
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
                if (matchData.attacker_data.damage_range_text) {
                    displayText += ' Range: ' + matchData.attacker_data.damage_range_text;
                } else if (matchData.attacker_data.min !== undefined && matchData.attacker_data.max !== undefined) {
                    displayText += ' Range: ' + matchData.attacker_data.min + '~' + matchData.attacker_data.max;
                }

                var detailText = '';

                // ★ 補正内訳を表示 (power_breakdown)
                var pb = matchData.attacker_data.power_breakdown;
                if (pb) {
                    if (pb.base_power_mod && pb.base_power_mod !== 0) {
                        detailText += '\n[基礎威力 ' + (pb.base_power_mod > 0 ? '+' : '') + pb.base_power_mod + ']';
                    }
                }

                // ★ 戦慄によるダイス減少を表示
                if (matchData.attacker_data.senritsu_dice_reduction && matchData.attacker_data.senritsu_dice_reduction > 0) {
                    detailText += '\n(戦慄: ダイス-' + matchData.attacker_data.senritsu_dice_reduction + ')';
                }

                // ★ 物理/魔法/威力補正の内訳を表示
                if (matchData.attacker_data.correction_details && matchData.attacker_data.correction_details.length > 0) {
                    matchData.attacker_data.correction_details.forEach(function (d) {
                        var sign = d.value > 0 ? '+' : '';
                        detailText += '\n[' + d.source + ' ' + sign + d.value + ']';
                    });
                }

                // ★ Commandを1行目の末尾に移動
                attackerResultDiv.innerHTML = '<span style="color:#dc3545;font-weight:bold;white-space:pre-line;">' + displayText + ' (' + matchData.attacker_data.command + ')' + detailText + '</span>';
            } else if (attackerResultDiv && attackerDeclareBtn && window._wideLocalCalcCache && window._wideLocalCalcCache.attacker) {
                // ★ local cache からの復元チェック
                var cached = window._wideLocalCalcCache.attacker;
                var currentSkillId = attackerSkillSelect ? attackerSkillSelect.value : '';
                if (cached.attackerId === matchData.attacker_id && cached.skillId === currentSkillId && currentSkillId) {
                    console.log("[Sync] Restoring local wide attacker calc result");
                    var res = cached.result;
                    wideMatchLocalState.attackerCommand = res.command;

                    var rangeText = res.damage_range_text ? 'Range: ' + res.damage_range_text : 'Range: ' + res.min + '~' + res.max;
                    attackerResultDiv.innerHTML = '<span style="color:#dc3545;font-weight:bold;">' + rangeText + ' (' + res.command + ')</span>';

                    attackerDeclareBtn.disabled = false;
                    attackerDeclareBtn.textContent = '宣言';
                    attackerDeclareBtn.classList.remove('locked');
                }
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

                if (!attacker) return;

                // ★ コストチェック
                if (window.allSkillData[skillId] && window.allSkillData[skillId]['特記処理']) {
                    try {
                        var rule = JSON.parse(window.allSkillData[skillId]['特記処理']);
                        var tags = window.allSkillData[skillId].tags || [];
                        if (rule.cost && tags.indexOf("即時発動") === -1) {
                            for (var i = 0; i < rule.cost.length; i++) {
                                var c = rule.cost[i];
                                var type = c.type;
                                var val = parseInt(c.value || 0);
                                if (val > 0 && type) {
                                    var key = (type === 'SAN') ? 'sanity' : (type === 'FP' || type === 'MP' || type === 'HP') ? type.toLowerCase() : null;
                                    var current = 0;
                                    if (key && attacker[key] !== undefined) {
                                        current = parseInt(attacker[key] || 0);
                                    } else {
                                        var found = (attacker.states || []).find(s => s.name === type);
                                        current = found ? parseInt(found.value || 0) : 0;
                                    }
                                    if (current < val) {
                                        alert(type + 'が不足しています (必要:' + val + ', 現在:' + current + ')');
                                        return;
                                    }
                                }
                            }
                        }
                    } catch (e) { console.error("Cost check error:", e); }
                }

                // ★ サーバー側で計算
                socket.emit('calculate_wide_skill', {
                    room: currentRoomName,
                    char_id: attacker.id,
                    skill_id: skillId
                });

                var resultDiv = document.getElementById('wide-attacker-result');
                if (resultDiv) {
                    resultDiv.innerHTML = '<span style="color:#666;">計算中...</span>';
                }

                // ★ 結果を受け取る
                socket.once('wide_skill_calculated', function (result) {
                    if (result.error) {
                        if (resultDiv) {
                            resultDiv.innerHTML = '<span style="color:#dc3545;">エラー: ' + result.error + '</span>';
                        }
                        return;
                    }

                    if (result.char_id === attacker.id) {
                        wideMatchLocalState.attackerCommand = result.command;

                        // ★ local cache への保存 (自分が計算した場合)
                        if (!window._wideLocalCalcCache) window._wideLocalCalcCache = { attacker: null, defenders: {} };
                        window._wideLocalCalcCache.attacker = {
                            result: result,
                            skillId: skillId,
                            attackerId: attacker.id
                        };

                        if (resultDiv) {
                            var rangeText = '';
                            if (result.damage_range_text) {
                                rangeText = 'Range: ' + result.damage_range_text;
                            } else {
                                rangeText = 'Range: ' + result.min + '~' + result.max;
                            }

                            var displayText = '<span style="color:#dc3545;font-weight:bold;">' + rangeText + ' (' + result.command + ')</span>';

                            // ★ 詳細な補正内訳を表示 (Declarer display logicと統一)

                            // 1. 基礎威力補正
                            // correction_detailsがあればそちらを使用
                            if (!result.correction_details || result.correction_details.length === 0) {
                                var pb = result.power_breakdown;
                                var baseMod = pb ? pb.base_power_mod : (result.base_power_mod || 0);
                                if (baseMod && baseMod !== 0) {
                                    displayText += '<br><span style="color:#666;font-size:0.9em;">[基礎威力 ' + (baseMod > 0 ? '+' : '') + baseMod + ']</span>';
                                }
                            }

                            // 2. 戦慄
                            if (result.senritsu_dice_reduction && result.senritsu_dice_reduction > 0) {
                                displayText += '<br><span style="color:#666;font-size:0.9em;">(戦慄: ダイス-' + result.senritsu_dice_reduction + ')</span>';
                            }

                            // 3. その他補正 (物理/魔法/威力/追加威力)
                            if (result.correction_details && result.correction_details.length > 0) {
                                result.correction_details.forEach(function (d) {
                                    var sign = d.value > 0 ? '+' : '';
                                    displayText += '<br><span style="color:#666;font-size:0.9em;">[' + d.source + ' ' + sign + d.value + ']</span>';
                                });
                            }

                            resultDiv.innerHTML = displayText;
                            resultDiv.dataset.command = result.command;
                            resultDiv.dataset.minDamage = result.min;
                            resultDiv.dataset.maxDamage = result.max;
                        }

                        var declareBtn = document.getElementById('wide-attacker-declare-btn');
                        if (declareBtn) declareBtn.disabled = false;

                        console.log("✅ Attacker calc result (server):", result);
                    }
                });
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

                // ★ Optimistic UI Update (Phase 1.5)
                // 即座にパネルを閉じてメイン画面に戻る
                var wideContainer = document.getElementById('wide-match-container');
                var duelContainer = document.querySelector('.duel-container');
                if (wideContainer) wideContainer.style.display = 'none';
                if (duelContainer) duelContainer.style.display = '';

                // マッチパネル自体も閉じておく (state_updated が来るまでの一時的な措置)
                if (typeof collapseMatchPanel === 'function') collapseMatchPanel();

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
        // ★ 新しいマッチではボタンテキストを「実行」にリセット
        if (executeBtn.textContent === '実行中...') {
            // 既にマッチが終了している場合（新しいマッチの場合）はリセット
            executeBtn.textContent = '実行';
        }

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
