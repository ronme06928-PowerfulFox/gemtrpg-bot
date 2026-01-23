/* static/js/tab_visual_battle.js */

// --- 定数定義 (Moved to legacy_globals.js for Phase 1 Refactoring) ---
// Constants are now loaded from static/js/legacy_globals.js

// --- グローバル変数 (Phase 5: MapState に移行) ---
// visualScale, visualOffsetX/Y は MapState.js で管理
// 後方互換性のため window.visualScale 等を参照
let visualScale = window.visualScale || 1.0;
// グローバル変数: ターン制御用
window.matchActionInitiated = false;
window.lastTurnCharId = null;

let visualOffsetX = window.visualOffsetX || (typeof CENTER_OFFSET_X !== 'undefined' ? CENTER_OFFSET_X : -900);
let visualOffsetY = window.visualOffsetY || (typeof CENTER_OFFSET_Y !== 'undefined' ? CENTER_OFFSET_Y : -900);
window.currentVisualLogFilter = 'all';
window.visualMapHandlers = window.visualMapHandlers || { move: null, up: null };

// --- 広域攻撃用の一時変数 (状態管理) ---
let visualWideState = {
    attackerId: null,
    isDeclared: false
};

// --- 攻撃ターゲット選択状態管理 ---
let attackTargetingState = {
    attackerId: null,  // 選択中の攻撃者ID
    isTargeting: false // ターゲット選択モードかどうか
};

// --- ヘルパー: 広域スキル判定 (Moved to legacy_globals.js) ---
// isWideSkillData is now global

// hasWideSkill is now global

// --- ヘルパー: 結果表示フォーマット (Moved to legacy_globals.js) ---
// formatWideResult is now global

// --- ★ 追加: スキル詳細HTML生成ヘルパー (Moved to legacy_globals.js) ---
// formatSkillDetailHTML is now global

// --- 計算・ダイス関数 (Moved to legacy_globals.js) ---
// safeMathEvaluate is now global

// rollDiceCommand is now global

// STATUS_CONFIG is now global (Moved to legacy_globals.js)

// duelState is now managed by MatchPanelState (Phase 3b)
// 後方互換性のため window.duelState を参照（MatchPanelState.js が自動同期）
let duelState = window.duelState || {
    attackerId: null, defenderId: null,
    attackerLocked: false, defenderLocked: false,
    isOneSided: false,
    attackerCommand: null, defenderCommand: null
};

// --- ターゲット選択モード管理関数 ---

// ターゲット選択モードに入る
function enterAttackTargetingMode(attackerId) {
    attackTargetingState.attackerId = attackerId;
    attackTargetingState.isTargeting = true;

    // カーソルをクロスヘアに変更
    document.body.style.cursor = 'crosshair';

    // マップビューポートに視覚的フィードバックを追加
    const mapViewport = document.getElementById('map-viewport');
    if (mapViewport) {
        mapViewport.classList.add('targeting-mode');
    }

    // 選択中の攻撃者トークンにハイライトを追加
    const attackerToken = document.querySelector(`.map-token[data-id="${attackerId}"]`);
    if (attackerToken) {
        attackerToken.classList.add('targeting-source');
    }
}

// ターゲット選択モードを解除
function exitAttackTargetingMode() {
    attackTargetingState.attackerId = null;
    attackTargetingState.isTargeting = false;

    // カーソルを元に戻す
    document.body.style.cursor = '';

    // マップビューポートのクラスを削除
    const mapViewport = document.getElementById('map-viewport');
    if (mapViewport) {
        mapViewport.classList.remove('targeting-mode');
    }

    // ハイライトを削除
    document.querySelectorAll('.map-token.targeting-source').forEach(token => {
        token.classList.remove('targeting-source');
    });
}

// --- ログ描画ヘルパー ---
function appendVisualLogLine(container, logData, filterType) {
    const isChat = logData.type === 'chat';
    if (filterType === 'chat' && !isChat) return;
    if (filterType === 'system' && isChat) return;

    const logLine = document.createElement('div');
    let className = `log-line ${logData.type}`;
    let displayMessage = logData.message;

    if (logData.secret) {
        className += ' secret-log';
        const isSender = (typeof currentUsername !== 'undefined' && logData.user === currentUsername);
        const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
        if (isGM || isSender) displayMessage = `<span class="secret-mark">[SECRET]</span> ${logData.message}`;
        else displayMessage = `<span class="secret-masked">（シークレットダイス）</span>`;
    }

    logLine.className = className;
    if (logData.type === 'chat' && !logData.secret) {
        logLine.innerHTML = `<span class="chat-user">${logData.user}:</span> <span class="chat-message">${logData.message}</span>`;
    } else {
        logLine.innerHTML = displayMessage;
    }
    logLine.style.borderBottom = "1px dotted #eee";
    logLine.style.padding = "2px 5px";
    logLine.style.fontSize = "0.9em";
    container.appendChild(logLine);
}

function renderVisualLogHistory(logs) {
    const logArea = document.getElementById('visual-log-area');
    if (!logArea) return;
    logArea.innerHTML = '';
    if (!logs || logs.length === 0) {
        logArea.innerHTML = '<div style="padding:10px; color:#999;">ログはありません</div>';
        return;
    }
    const filter = window.currentVisualLogFilter || 'all';
    logs.forEach(log => appendVisualLogLine(logArea, log, filter));
    logArea.scrollTop = logArea.scrollHeight;
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 30);
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 80);
}

// --- ★初期化関数 ---
/**
 * ビジュアルバトルタブの初期化
 * Socket.IOイベントハンドラの登録、UI要素の初期化、アクションドックのセットアップを行う
 * @async
 * @returns {Promise<void>}
 */
async function setupVisualBattleTab() {


    if (typeof socket !== 'undefined') {
        console.log('📡 socket is defined, setting up handlers');

        // 1. 重複防止: 一度だけ登録すればよいイベント (socket handlers)
        if (!window.visualBattleSocketHandlersRegistered) {

            window.visualBattleSocketHandlersRegistered = true;
            console.log('📡 Registering socket event handlers');

            // Socket handlers are registered below (state_updated, etc.)
        }

        // 2. DOM初期化: タブ切り替えのたびに実行（DOM要素が再作成されるため）
        if (!window.actionDockInitialized && typeof initializeActionDock === 'function') {
            console.log('🔧 Calling initializeActionDock on page load');
            initializeActionDock();
            window.actionDockInitialized = true;
        }

        // ★ Phase 3: Timeline コンポーネントの初期化
        if (window.TimelineComponent && typeof window.TimelineComponent.initialize === 'function') {
            window.TimelineComponent.initialize('visual-timeline-list');
        }

        // ★ Phase 3: ActionDock コンポーネントの初期化
        if (window.ActionDockComponent && typeof window.ActionDockComponent.initialize === 'function') {
            window.ActionDockComponent.initialize();
        }

        // ★ Phase 5: VisualMap コンポーネントの初期化
        if (window.VisualMapComponent && typeof window.VisualMapComponent.initialize === 'function') {
            window.VisualMapComponent.initialize();
        }

        // ★ Phase 6: MatchPanel コンポーネントの初期化
        if (window.MatchPanelComponent && typeof window.MatchPanelComponent.initialize === 'function') {
            window.MatchPanelComponent.initialize();
        }

        // 3. ソケットハンドラ登録（一度だけ）
        if (!window._socketHandlersActuallyRegistered) {
            window._socketHandlersActuallyRegistered = true;

            socket.on('state_updated', (state) => {
                console.log('📡 state_updated received', {
                    hasActiveMatch: !!state.active_match,
                    isActive: state.active_match?.is_active,
                    charactersCount: state.characters?.length
                });
                // グローバルなbattleStateを最新の状態に更新
                if (typeof battleState !== 'undefined') {
                    battleState = state;
                }


                if (document.getElementById('visual-battle-container')) {
                    renderVisualMap();
                    renderVisualTimeline();

                    // ★ ログ描画を改善: logsの存在を確実にチェック
                    if (state.logs && Array.isArray(state.logs) && state.logs.length > 0) {
                        console.log(`📜 Rendering ${state.logs.length} log entries from state_updated`);
                        renderVisualLogHistory(state.logs);
                    } else {
                        console.debug('📜 No logs to render in state_updated (logs array is empty or not present)');
                    }

                    updateVisualRoundDisplay(state.round);



                    // ★ 修正: 初回state_updated後にアクションドック初期化（battleState読み込み後）
                    // Initialization must happen BEFORE restoring the modal to ensure listeners are ready
                    if (!window.actionDockInitialized && typeof initializeActionDock === 'function') {
                        console.log('🔧 Calling initializeActionDock from state_updated');
                        initializeActionDock();
                        window.actionDockInitialized = true;
                    } else if (typeof updateActionDock === 'function') {
                        // Initial update is handled by initializeActionDock, subsequent updates need explicit call
                        try {
                            updateActionDock();
                        } catch (e) {
                            console.error("Error updating action dock:", e);
                        }
                    }

                    // ★ リファクタリング: サーバー状態からパネルを描画
                    renderMatchPanelFromState(state.active_match);

                }
            });

            socket.on('open_wide_declaration_modal', () => {
                openVisualWideDeclarationModal();
            });

            // ★ Phase 2: 差分更新イベントのハンドラ
            // char:stat:updated イベントをリッスンして、DOM を部分更新
            // 重複登録を防ぐため、フラグでチェック
            if (typeof window.EventBus !== 'undefined' && !window._charStatUpdatedListenerRegistered) {
                window._charStatUpdatedListenerRegistered = true;
                console.log('✅ Registering char:stat:updated listener');
                window.EventBus.on('char:stat:updated', (data) => {
                    console.log('⚡ Diff Update Received:', data);
                    updateCharacterTokenVisuals(data);
                });
            } else if (!window.EventBus) {
                console.error('❌ EventBus not found. Diff updates will not work.');
            } else {
                console.log('ℹ️ char:stat:updated listener already registered');
            }

            socket.on('close_wide_declaration_modal', () => {
                const el = document.getElementById('visual-wide-decl-modal');
                if (el) el.remove();
            });

            // ★ 追加: マッチモーダル関連イベント
            socket.on('match_modal_opened', (data) => {
                // data: { match_type, attacker_id, defender_id, targets, ... }
                if (data.match_type === 'duel') {
                    // 受信によるオープンのため、再送信はしない (emitSync = false)
                    openDuelModal(data.attacker_id, data.defender_id, false, false);
                } else {
                    // 他のマッチタイプがあればここで処理
                }
            });

            // ★ 追加: マッチエラーハンドラ（挑発チェック等）
            socket.on('match_error', (data) => {
                alert(data.error || 'マッチを開始できません。');
            });

            // match_data_updated は廃止 - state_updated で統一したため不要

            socket.on('match_modal_closed', () => {
                // ★ ワイドマッチ状態をリセット（次のマッチ用）
                if (typeof window.resetWideMatchState === 'function') {
                    window.resetWideMatchState();
                }
                closeMatchPanel(false);
            });

            // ★ 廃止: サーバー側で直接マッチを実行するため、このハンドラは不要
            // match_auto_executeイベントは送信されなくなりました
            /*
            socket.on('match_auto_execute', (data) => {
                const statusEl = document.getElementById('duel-status-message');
                if (statusEl) {
                    statusEl.textContent = '両側の宣言が完了しました。マッチを実行します...';
                    statusEl.style.color = '#28a745';
                }

                // ★ 厳密なチェック: 攻撃側キャラのオーナーのみが実行
                // GMは両方を操作できるため、オーナーで判断する
                const attackerId = data.actorIdA;
                const attacker = battleState.characters?.find(c => c.id === attackerId);
                const isOwner = attacker && attacker.owner === currentUsername;

                // 攻撃側のオーナーか、またはGMなら実行可能
                const shouldExecute = isOwner || currentUserAttribute === 'GM';

                if (shouldExecute) {
                    console.log('[MATCH] Executing match as attacker owner/GM');
                    // ★ マッチIDを含めて送信（重複実行防止用）
                    socket.emit('request_match', {
                        ...data,
                        match_id: data.match_id  // サーバーから受信したマッチIDをそのまま送信
                    });
                } else {
                    console.log('[MATCH] Not attacker owner, skipping request_match');
                }
            });
            */



        }

        // 2. 強制更新: 計算ロジックなどは修正を即時反映させるため毎回更新する
        socket.off('skill_declaration_result');

        // --- ★計算結果/宣言結果の受信 (統合ハンドラ) ---
        socket.on('skill_declaration_result', (data) => {
            if (!data.prefix) return;

            // A. 広域攻撃 (攻撃側)
            if (data.prefix === 'visual_wide_attacker') {
                const cmdInput = document.getElementById('v-wide-attacker-cmd');
                const declareBtn = document.getElementById('v-wide-declare-btn');
                const modeBadge = document.getElementById('v-wide-mode-badge');
                const descArea = document.getElementById('v-wide-attacker-desc');

                // ★ エラー時のアラート表示 (広域攻撃でもエラーなら出す)
                if (data.error) {
                    alert(data.final_command || "エラーが発生しました");
                }

                if (cmdInput && declareBtn) {
                    if (data.error) {
                        cmdInput.value = data.final_command || "エラー";
                        cmdInput.style.color = "red";
                        if (descArea) descArea.innerHTML = "<span style='color:red;'>エラー</span>";
                    } else {
                        // 表示用フォーマットをセット
                        cmdInput.value = formatWideResult(data);
                        // 計算用の生データを属性に保存
                        cmdInput.dataset.raw = data.final_command;

                        cmdInput.style.color = "black";
                        cmdInput.style.fontWeight = "bold";

                        if (modeBadge) modeBadge.style.display = 'inline-block';

                        // 宣言ボタン有効化
                        declareBtn.disabled = false;
                        declareBtn.textContent = "宣言";
                        declareBtn.classList.remove('locked');
                        declareBtn.classList.remove('btn-outline-danger');
                        declareBtn.classList.add('btn-danger');

                        // スキル詳細表示
                        if (descArea && data.skill_details) {
                            descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
                        }
                    }
                }
                return;
            }

            // B. 広域攻撃 (防御側個別)
            if (data.prefix.startsWith('visual_wide_def_')) {
                const charId = data.prefix.replace('visual_wide_def_', '');
                const row = document.querySelector(`.wide-defender-row[data-id="${charId}"]`);
                if (row) {
                    const cmdInput = row.querySelector('.v-wide-def-cmd');
                    const statusSpan = row.querySelector('.v-wide-status');
                    const declareBtn = row.querySelector('.v-wide-def-declare');
                    const descArea = row.querySelector('.v-wide-def-desc');

                    if (data.error) {
                        cmdInput.value = data.final_command;
                        cmdInput.style.color = "red";
                        statusSpan.textContent = "エラー";
                        statusSpan.style.color = "red";
                    } else {
                        // 表示用フォーマットと生データの分離
                        cmdInput.value = formatWideResult(data);
                        cmdInput.dataset.raw = data.final_command;

                        cmdInput.style.color = "green";
                        cmdInput.style.fontWeight = "bold";
                        statusSpan.textContent = "OK";
                        statusSpan.style.color = "green";

                        // 防御側の宣言ボタン有効化
                        if (declareBtn) {
                            declareBtn.disabled = false;
                            declareBtn.classList.remove('btn-outline-success');
                            declareBtn.classList.add('btn-success');
                        }

                        // スキル詳細表示
                        if (descArea && data.skill_details) {
                            descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
                        }
                    }
                }
                return;
            }

            // ★ 追加: 即時発動スキル (immediate_) や 宝石スキル (gem_) のエラーハンドリング
            // これらはここに到達する前に他の条件に引っかからない前提（visual_wide_... ではない）
            if (data.prefix && (data.prefix.startsWith('immediate_') || data.prefix.startsWith('gem_'))) {
                if (data.error) {
                    alert(data.final_command || "エラーが発生しました");
                }
                return;
            }

            // C. 即時発動スキル
            if (data.is_instant_action && data.prefix.startsWith('visual_')) {
                if (typeof closeDuelModal === 'function') closeDuelModal();
                return;
            }

            // D. 通常1vs1対決UI更新
            if (data.prefix === 'visual_attacker' || data.prefix === 'visual_defender') {
                const side = data.prefix.replace('visual_', '');
                if (typeof updateDuelUI === 'function') updateDuelUI(side, { ...data, enableButton: true });
            }
        });
    }

    // 2. DOM操作とイベント登録
    window.currentVisualLogFilter = 'all';
    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        btn.onclick = () => {
            filters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.currentVisualLogFilter = btn.dataset.filter;
            if (battleState && battleState.logs) renderVisualLogHistory(battleState.logs);
        };
    });

    if (typeof battleState !== 'undefined' && battleState.logs) renderVisualLogHistory(battleState.logs);

    setupMapControls();
    setupVisualSidebarControls();
    renderVisualMap();
    renderVisualMap();
    // === End of Main Functions ===

    // ★ 追加: ターン変更時のフラグリセット用リスナー
    if (typeof socket !== 'undefined' && !window._visualBattleTurnListenerRegistered) {
        window._visualBattleTurnListenerRegistered = true;
        socket.on('state_updated', (newState) => {
            if (!newState) return;

            // ターンキャラクターが変わったらフラグリセット
            if (window.lastTurnCharId !== newState.turn_char_id) {
                console.log(`[TurnChange] ${window.lastTurnCharId} -> ${newState.turn_char_id}. Resetting match flag.`);
                window.lastTurnCharId = newState.turn_char_id;
                window.matchActionInitiated = false;
            }
        });
    }
    // renderStagingArea(); // Removed
    renderVisualTimeline();
    renderVisualTimeline();
    updateVisualRoundDisplay(battleState ? battleState.round : 0);

    // 3. スキルデータロード
    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        try {
            const res = await fetch('/api/get_skill_data');
            if (res.ok) window.allSkillData = await res.json();
        } catch (e) { console.error("Failed to load skill data:", e); }
    }

    // 4. アクションドックの初期化
    // ★ 修正: initializeActionDockはstate_updated後に実行
    // battleStateロード前にアイコンが押せてしまう問題を防ぐため、初期化を遅延
    // initializeActionDock自体は後で呼ばれる

    // 5. マッチパネルのボタンイベントリスナーを設定
    const panelToggleBtn = document.getElementById('panel-toggle-btn');
    const panelReloadBtn = document.getElementById('panel-reload-btn');

    if (panelToggleBtn) {
        panelToggleBtn.addEventListener('click', () => {
            toggleMatchPanel();
        });
    }


    if (panelReloadBtn) {
        panelReloadBtn.addEventListener('click', () => {
            console.log('🔄 Reload button clicked');
            reloadMatchPanel();
        });
    }

    // 6. タイムライン折り畳み機能の初期化
    initializeTimelineToggle();
}

// タイムライン折り畳み機能
function initializeTimelineToggle() {
    const timelineArea = document.getElementById('visual-timeline-area');
    const header = timelineArea ? timelineArea.querySelector('.sidebar-header') : null;

    if (!header) return;

    // ローカルストレージから状態を復元
    const isCollapsed = localStorage.getItem('visual-timeline-collapsed') === 'true';
    if (isCollapsed) {
        timelineArea.classList.add('collapsed');
    }

    // クリックイベント
    header.addEventListener('click', () => {
        const nowCollapsed = timelineArea.classList.toggle('collapsed');
        localStorage.setItem('visual-timeline-collapsed', nowCollapsed);
    });
}

// --- サイドバー ---
function setupVisualSidebarControls() {
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');

    // 広域予約ボタンは削除（ラウンド開始時に自動表示されるため不要）


    if (currentUserAttribute === 'GM') {
        if (startRBtn) {
            startRBtn.style.display = 'inline-block';
            startRBtn.onclick = () => {
                if (confirm("次ラウンドを開始しますか？")) socket.emit('request_new_round', { room: currentRoomName });
            };
        }
        if (endRBtn) {
            endRBtn.style.display = 'inline-block';
            endRBtn.onclick = () => {
                if (confirm("ラウンドを終了しますか？")) socket.emit('request_end_round', { room: currentRoomName });
            };
        }
    }

    const chatInput = document.getElementById('visual-chat-input');
    const chatSend = document.getElementById('visual-chat-send');
    const diceCommandRegex = /^((\/sroll|\/sr|\/roll|\/r)\s+)?((\d+)?d\d+([\+\-]\d+)?(\s*[\+\-]\s*(\d+)?d\d+([\+\-]\d+)?)*)/i;

    const sendChat = () => {
        let msg = chatInput.value.trim();
        if (!msg) return;
        let isSecret = false;
        if (/^(\/sroll|\/sr)(\s+|$)/i.test(msg)) isSecret = true;

        if (diceCommandRegex.test(msg)) {
            const result = rollDiceCommand(msg);
            const cleanCmd = msg.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');
            const resultHtml = `${cleanCmd} = ${result.details} = <span class="dice-result-total">${result.total}</span>`;
            socket.emit('request_log', {
                room: currentRoomName,
                message: `[${currentUsername}] ${resultHtml}`,
                type: 'dice',
                secret: isSecret,
                user: currentUsername
            });
        } else {
            msg = msg.replace(/^(\/roll|\/r)(\s+|$)/i, '');
            if (isSecret) msg = msg.replace(/^(\/sroll|\/sr)(\s+|$)/i, '');
            if (!msg && isSecret) { alert("シークレットメッセージの内容を入力してください。"); return; }
            if (msg) {
                socket.emit('request_chat', {
                    room: currentRoomName, user: currentUsername, message: msg, secret: isSecret
                });
            }
        }
        chatInput.value = '';
    };

    if (chatSend) chatSend.onclick = sendChat;
    if (chatInput) {
        chatInput.onkeydown = (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); }
        };
    }

    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        btn.onclick = () => {
            filters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.currentVisualLogFilter = btn.dataset.filter;
            if (battleState && battleState.logs) renderVisualLogHistory(battleState.logs);
        };
    });

    const saveBtn = document.getElementById('visual-save-btn');
    const presetBtn = document.getElementById('visual-preset-btn');
    const resetBtn = document.getElementById('visual-reset-btn');
    const statusMsg = document.getElementById('visual-status-msg');

    // GMの場合のみボタンを表示・有効化、それ以外は非表示
    if (currentUserAttribute === 'GM') {
        if (saveBtn) {
            saveBtn.style.display = 'inline-block';
            saveBtn.onclick = async () => {
                statusMsg.textContent = "保存中...";
                try {
                    await fetchWithSession('/save_room', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ room_name: currentRoomName, state: battleState })
                    });
                    statusMsg.textContent = "保存完了";
                    setTimeout(() => statusMsg.textContent = "", 2000);
                } catch (e) { statusMsg.textContent = "保存失敗"; }
            };
        }
        if (presetBtn) {
            presetBtn.style.display = 'inline-block';
            presetBtn.onclick = () => { if (typeof openPresetManagerModal === 'function') openPresetManagerModal(); };
        }
        if (resetBtn) {
            resetBtn.style.display = 'inline-block';
            resetBtn.onclick = () => {
                if (typeof openResetTypeModal === 'function') {
                    openResetTypeModal((type) => { socket.emit('request_reset_battle', { room: currentRoomName, mode: type }); });
                } else if (confirm("戦闘をリセットしますか？")) {
                    socket.emit('request_reset_battle', { room: currentRoomName, mode: 'full' });
                }
            };
        }
    } else {
        // GMでない場合は非表示にする
        if (saveBtn) saveBtn.style.display = 'none';
        if (presetBtn) presetBtn.style.display = 'none';
        if (resetBtn) resetBtn.style.display = 'none';
    }

    // 退室ボタン(leaveBtn)はHTMLから削除されたため、イベントリスナーも削除
}

function updateVisualRoundDisplay(round) {
    const el = document.getElementById('visual-round-counter');
    if (el) el.textContent = round || 0;
}

/**
 * マップの拡大縮小・移動変換を適用
 * visualScale, visualOffsetX/Y の値を元にCSS transformを更新
 * @returns {void}
 */
function updateMapTransform() {
    const mapEl = document.getElementById('game-map');
    if (mapEl) mapEl.style.transform = `translate(${visualOffsetX}px, ${visualOffsetY}px) scale(${visualScale})`;
}

/**
 * ビジュアルマップの描画
 * 全キャラクターのトークンをマップ上に配置し、現在のターンを視覚的に表示
 * @returns {void}
 */
function renderVisualMap() {
    const tokenLayer = document.getElementById('map-token-layer');
    if (!tokenLayer) return;
    tokenLayer.innerHTML = '';
    renderVisualTimeline();
    updateMapTransform();
    if (typeof battleState === 'undefined' || !battleState.characters) return;
    const currentTurnId = battleState.turn_char_id || null;
    battleState.characters.forEach(char => {
        if (char.x >= 0 && char.y >= 0 && char.hp > 0) {
            const token = createMapToken(char);
            if (char.id === currentTurnId) token.classList.add('active-turn');
            tokenLayer.appendChild(token);
        }
    });
}

/**
 * マップコントロールの初期化
 * ズームボタン、パン操作、トークンドロップなどのイベントハンドラを設定
 * @returns {void}
 */
function setupMapControls() {
    const mapViewport = document.getElementById('map-viewport');
    const gameMap = document.getElementById('game-map');
    if (!mapViewport || !gameMap) return;

    if (window.visualMapHandlers.move) window.removeEventListener('mousemove', window.visualMapHandlers.move);
    if (window.visualMapHandlers.up) window.removeEventListener('mouseup', window.visualMapHandlers.up);

    mapViewport.ondragover = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; };
    mapViewport.ondrop = (e) => {
        e.preventDefault();
        if (e.target.closest('.map-token')) return;
        const charId = e.dataTransfer.getData('text/plain');
        if (!charId) return;
        const rect = gameMap.getBoundingClientRect();
        const mapX = (e.clientX - rect.left) / visualScale;
        const mapY = (e.clientY - rect.top) / visualScale;

        // グリッド座標に変換（90px単位）
        const gridX = Math.floor(mapX / GRID_SIZE);
        const gridY = Math.floor(mapY / GRID_SIZE);

        if (typeof socket !== 'undefined' && currentRoomName) {
            // ★ Optimistic UI Update (Phase 1.5)
            // サーバー応答を待たずにローカルで即座に位置を更新して描画する
            const charIndex = battleState.characters.findIndex(c => c.id === charId);
            if (charIndex !== -1) {
                const char = battleState.characters[charIndex];
                // 位置情報を更新
                char.x = gridX;
                char.y = gridY;

                // マップを再描画（即座に反映）
                renderVisualMap();

                // タイムラインも更新（未配置→配置の場合に表示されるようになるため）
                renderVisualTimeline();
            }

            socket.emit('request_move_token', { room: currentRoomName, charId, x: gridX, y: gridY });
        }
    };

    const zIn = document.getElementById('zoom-in-btn');
    const zOut = document.getElementById('zoom-out-btn');
    const rView = document.getElementById('reset-view-btn');
    if (zIn) zIn.onclick = () => { visualScale = Math.min(visualScale + 0.1, 3.0); updateMapTransform(); };
    if (zOut) zOut.onclick = () => { visualScale = Math.max(visualScale - 0.1, 0.5); updateMapTransform(); };
    if (rView) rView.onclick = () => { visualScale = 1.0; visualOffsetX = 0; visualOffsetY = 0; updateMapTransform(); };

    let isPanning = false, startX, startY;
    mapViewport.onmousedown = (e) => {
        if (e.target.closest('.map-token')) return;
        isPanning = true;
        startX = e.clientX - visualOffsetX;
        startY = e.clientY - visualOffsetY;
    };
    const onMouseMove = (e) => {
        if (!isPanning) return;
        e.preventDefault();
        visualOffsetX = e.clientX - startX;
        visualOffsetY = e.clientY - startY;
        updateMapTransform();
    };
    const onMouseUp = () => { isPanning = false; };
    window.visualMapHandlers.move = onMouseMove;
    window.visualMapHandlers.up = onMouseUp;
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);

    // マップの空白部分をクリックしたときにターゲット選択モードを解除
    mapViewport.addEventListener('click', (e) => {
        // トークンをクリックした場合は何もしない
        if (e.target.closest('.map-token')) return;

        // ターゲット選択モードを解除
        exitAttackTargetingMode();
    });
}

function renderVisualTimeline() {
    const timelineEl = document.getElementById('visual-timeline-list');
    if (!timelineEl) return;
    timelineEl.innerHTML = '';
    if (!battleState.timeline || battleState.timeline.length === 0) {
        timelineEl.innerHTML = '<div style="color:#888; padding:5px;">No Data</div>';
        return;
    }
    const currentTurnId = battleState.turn_char_id;
    battleState.timeline.forEach(charId => {
        const char = battleState.characters.find(c => c.id === charId);
        if (!char) return;
        const item = document.createElement('div');
        item.className = `timeline-item ${char.type || 'NPC'}`;
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.padding = "6px 8px";
        item.style.borderBottom = "1px solid #eee";
        item.style.cursor = "pointer";
        item.style.background = "#fff";
        const typeColor = (char.type === 'ally') ? '#007bff' : '#dc3545';
        item.style.borderLeft = `3px solid ${typeColor}`;
        if (char.id === currentTurnId) {
            item.style.background = "#fff8e1";
            item.style.fontWeight = "bold";
            item.style.borderLeft = `6px solid ${typeColor}`;
            item.style.borderTop = "1px solid #ff9800";
            item.style.borderBottom = "1px solid #ff9800";
            item.style.borderRight = "1px solid #ff9800";
        }
        if (char.hasActed) {
            item.style.opacity = "0.5";
            item.style.textDecoration = "line-through";
        }
        if (char.hp <= 0) {
            item.style.opacity = "0.3";
            item.style.background = "#ccc";
        }
        item.innerHTML = `
            <span class="name">${char.name}</span>
            <span class="speed" style="font-size:0.85em; color:#666;">SPD:${char.totalSpeed || char.speedRoll || 0}</span>
        `;
        item.addEventListener('click', () => showCharacterDetail(char.id));
        timelineEl.appendChild(item);
    });
}

// function renderStagingArea() {} // Removed

/**
 * ★ Phase 2: キャラクタートークンの視覚的な部分更新
 * サーバーから char_stat_updated イベントを受信したときに、
 * フルレンダリングせずに該当トークンのDOM要素だけを更新する
 * @param {Object} data - { char_id, stat, new_value, old_value, max_value }
 */
function updateCharacterTokenVisuals(data) {
    console.log('[updateCharacterTokenVisuals] Called with data:', data);

    if (!data || !data.char_id) {
        console.warn('[updateCharacterTokenVisuals] Invalid data:', data);
        return;
    }

    const { char_id, stat, new_value, old_value, max_value, source } = data;
    console.log(`[updateCharacterTokenVisuals] Extracted: char_id=${char_id}, stat=${stat}, new=${new_value}, old=${old_value}, max=${max_value}, source=${source}`);

    // 対象トークンを取得
    const token = document.querySelector(`.map-token[data-id="${char_id}"]`);
    if (!token) {
        console.debug(`[updateCharacterTokenVisuals] Token not found for char_id: ${char_id}`);
        return;
    }

    // battleState から該当キャラクターを取得して最新値を反映
    if (typeof battleState !== 'undefined' && battleState.characters) {
        const char = battleState.characters.find(c => c.id === char_id);
        if (char) {
            // ステータスを更新（battleState を最新に保つ）
            if (stat === 'HP') char.hp = new_value;
            else if (stat === 'MP') char.mp = new_value;
            else {
                // 状態異常などの場合
                const stateObj = char.states?.find(s => s.name === stat);
                if (stateObj) stateObj.value = new_value;
            }
        }
    }

    // HP/MP バーの更新
    if (stat === 'HP' || stat === 'MP') {
        const barClass = stat === 'HP' ? 'hp' : 'mp';
        const barFill = token.querySelector(`.token-bar-fill.${barClass}`);
        const barContainer = token.querySelector(`.token-bar[title^="${stat}:"]`);

        if (barFill && max_value) {
            const percentage = Math.max(0, Math.min(100, (new_value / max_value) * 100));

            // CSS transition でスムーズに幅を変更
            barFill.style.width = `${percentage}%`;

            // title 属性を更新（ホバー時の表示）
            if (barContainer) {
                barContainer.title = `${stat}: ${new_value}/${max_value}`;
            }
        }

        // フローティングテキスト表示（ダメージ/回復の視覚的フィードバック）
        if (old_value !== undefined && old_value !== new_value) {
            const diff = new_value - old_value;
            showFloatingText(token, diff, stat, source);
        }
    } else {
        // ★ 状態異常の場合もフローティングテキストを表示
        if (old_value !== undefined && old_value !== new_value) {
            const diff = new_value - old_value;
            showFloatingText(token, diff, stat, source);
        }

        // 状態異常アイコンの更新は複雑なため、必要に応じて renderVisualMap を呼ぶ
        // （ただし頻繁に呼ぶと差分更新の意味が薄れるため、重要な変更のみ）
        console.debug(`[updateCharacterTokenVisuals] State change detected: ${stat}, triggering partial re-render`);
        // ここでは全体再描画を避けるため、アイコン部分のみ更新する処理を追加可能
        // 現状は次の state_updated で反映されるため、スキップ
    }
}

/**
 * ★ Phase 2: フローティングテキスト表示
 * ダメージや回復を視覚的にポップアップ表示する
 * @param {HTMLElement} token - 対象トークン要素
 * @param {number} diff - 変化量（正: 回復、負: ダメージ）
 * @param {string} stat - ステータス名 ('HP', 'MP', '出血' など)
 * @param {string|null} source - ダメージ発生源 ('bleed', 'match_loss' など)
 */
function showFloatingText(token, diff, stat, source = null) {
    console.log(`[FloatingText] Calling showFloatingText: diff=${diff}, stat=${stat}, source=${source}, token=`, token);

    // ★ 重要: トークンではなく map-viewport に追加することで、
    // renderVisualMap() による再描画の影響を受けないようにする
    const mapViewport = document.getElementById('map-viewport');
    if (!mapViewport) {
        console.warn('[FloatingText] map-viewport not found');
        return;
    }

    // ★ トークンごとのフローティングテキスト数を管理
    const charId = token.dataset.id;
    if (!window.floatingTextCounters) {
        window.floatingTextCounters = {};
    }
    if (!window.floatingTextCounters[charId]) {
        window.floatingTextCounters[charId] = 0;
    }

    // 現在のカウントを取得し、インクリメント
    const currentOffset = window.floatingTextCounters[charId];
    window.floatingTextCounters[charId]++;

    const floatingText = document.createElement('div');
    floatingText.className = 'floating-damage-text';

    // ダメージか回復かで基本クラスを決定
    const isDamage = diff < 0;
    const absValue = Math.abs(diff);

    // HP/MP以外（状態異常）の場合はステータス名も表示
    let displayText = '';
    if (stat === 'HP') {
        // ★ 破裂爆発・亀裂崩壊の場合はラベルを追加
        if (source === 'rupture') {
            displayText = isDamage ? `破裂爆発！ -${absValue}` : `破裂爆発！ +${absValue}`;
        } else if (source === 'fissure') {
            displayText = isDamage ? `亀裂崩壊！ -${absValue}` : `亀裂崩壊！ +${absValue}`;
        } else {
            displayText = isDamage ? `-${absValue}` : `+${absValue}`;
        }
    } else if (stat === 'MP') {
        displayText = isDamage ? `-${absValue}` : `+${absValue}`;
    } else {
        // 状態異常の場合
        displayText = isDamage ? `${stat} -${absValue}` : `${stat} +${absValue}`;
        floatingText.classList.add('state-change');
    }
    floatingText.textContent = displayText;

    // 基本的な色分け（source指定がない場合）
    if (!source) {
        if (stat === 'HP') {
            floatingText.classList.add(isDamage ? 'damage' : 'heal');
        } else if (stat === 'MP') {
            floatingText.classList.add(isDamage ? 'mp-cost' : 'mp-heal');
        }
    } else {
        // ★ source指定がある場合は、発生源別クラスを適用
        floatingText.classList.add(`src-${source}`);
    }

    // ★ トークンの絶対位置を計算して、フローティングテキストを配置
    const tokenRect = token.getBoundingClientRect();
    const viewportRect = mapViewport.getBoundingClientRect();

    // map-viewport 内での相対位置を計算（スクロール考慮）
    const relativeLeft = tokenRect.left - viewportRect.left + mapViewport.scrollLeft + (tokenRect.width / 2);
    // ★ 複数のテキストを縦に並べるため、オフセットを追加（25pxずつ上にずらす）
    const verticalOffset = currentOffset * 25;
    const relativeTop = tokenRect.top - viewportRect.top + mapViewport.scrollTop + (tokenRect.height / 2) - verticalOffset;

    floatingText.style.left = `${relativeLeft}px`;
    floatingText.style.top = `${relativeTop}px`;

    mapViewport.appendChild(floatingText);

    // アニメーション終了後に要素を削除し、カウンターをデクリメント
    setTimeout(() => {
        if (floatingText.parentNode) {
            floatingText.parentNode.removeChild(floatingText);
        }
        // カウンターをデクリメント
        if (window.floatingTextCounters && window.floatingTextCounters[charId] > 0) {
            window.floatingTextCounters[charId]--;
        }
    }, 3000);  // ★ CSSアニメーション(3s)と同期
}

/**
 * キャラクター用のマップトークンを生成
 * HP/MP/FPバー、ステータスアイコン、ドラッグ&ドロップ機能を持つDOM要素を作成
 * @param {Object} char - キャラクター情報オブジェクト
 * @param {string} char.id - キャラクターID
 * @param {string} char.name - キャラクター名
 * @param {number} char.x - X座標（グリッド単位）
 * @param {number} char.y - Y座標（グリッド単位）
 * @param {number} char.hp - 現在のHP
 * @param {number} char.maxHp - 最大HP
 * @param {Array} [char.states] - ステータス効果の配列
 * @returns {HTMLElement} 生成されたトークン要素
 */
function createMapToken(char) {
    const token = document.createElement('div');

    // 色分けの判定: 名前に「味方」「敵」が含まれているかをチェック
    let colorClass = 'NPC'; // デフォルト
    if (char.name && char.name.includes('味方')) {
        colorClass = 'PC';
    } else if (char.name && char.name.includes('敵')) {
        colorClass = 'Enemy';
    } else if (char.color) {
        colorClass = char.color;
    }

    token.className = `map-token ${colorClass}`;
    token.dataset.id = char.id;

    // 駒サイズスケールを適用
    const tokenScale = char.tokenScale || 1.0;
    const scaledSize = 82 * tokenScale; // 基本サイズ82px
    token.style.width = `${scaledSize}px`;
    token.style.height = `${scaledSize}px`;


    // グリッド座標をピクセル座標に変換（90px単位）
    token.style.left = `${char.x * GRID_SIZE + TOKEN_OFFSET}px`;
    token.style.top = `${char.y * GRID_SIZE + TOKEN_OFFSET}px`;
    const maxHp = char.maxHp || 1; const hp = char.hp || 0;
    const hpPer = Math.max(0, Math.min(PERCENTAGE_MAX, (hp / maxHp) * PERCENTAGE_MAX));
    const maxMp = char.maxMp || 1; const mp = char.mp || 0;
    const mpPer = Math.max(0, Math.min(PERCENTAGE_MAX, (mp / maxMp) * PERCENTAGE_MAX));
    const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
    const fp = fpState ? fpState.value : 0;
    const fpPer = Math.min(PERCENTAGE_MAX, (fp / MAX_FP) * PERCENTAGE_MAX);
    let iconsHtml = '';
    if (char.states) {
        char.states.forEach(s => {
            if (['HP', 'MP', 'FP'].includes(s.name)) return;
            if (s.value === 0) return;
            const config = STATUS_CONFIG[s.name];
            if (config) {
                iconsHtml += `
                    <div class="mini-status-icon" style="background-color: #fff; border-color: ${config.borderColor};">
                        <img src="images/${config.icon}" alt="${s.name}">
                        <div class="mini-status-badge" style="background-color: ${config.color};">${s.value}</div>
                    </div>`;
            } else {
                const arrow = s.value > 0 ? '▲' : '▼';
                const color = s.value > 0 ? '#28a745' : '#dc3545';
                iconsHtml += `
                    <div class="mini-status-icon" style="color:${color}; font-weight:bold; border-color:${color};">
                        ${arrow}
                        <div class="mini-status-badge" style="background:${color}; border-color:${color};">${s.value}</div>
                    </div>`;
            }
        });
    }

    const isCurrentTurn = (battleState.turn_char_id === char.id);
    let wideBtnHtml = '';
    // ★ 修正: 既に広域マッチが進行中ならボタンを表示しない (誤リセット防止)
    const isWideMatchExecuting = battleState.active_match && battleState.active_match.is_active && battleState.active_match.match_type === 'wide';

    // DEBUG: Wide Button Condition
    if (char.isWideUser) {
        console.log(`[WideButtonDebug] ${char.name}: isTurn=${isCurrentTurn}, isWideUser=${char.isWideUser}, Executing=${isWideMatchExecuting}`);
    }

    if (isCurrentTurn && char.isWideUser && !isWideMatchExecuting) {
        wideBtnHtml = '<button class="wide-attack-trigger-btn" onclick="event.stopPropagation(); openSyncedWideMatchModal(\'' + char.id + '\');">⚡ 広域攻撃</button>';
    }

    // ★ 画像URLがある場合は背景として設定
    let tokenBodyStyle = '';
    let tokenBodyContent = `<span>${char.name.charAt(0)}</span>`;

    if (char.image) {
        tokenBodyStyle = `style="background-image: url('${char.image}'); background-size: cover; background-position: center; background-repeat: no-repeat;"`;
        tokenBodyContent = ''; // 画像がある場合はテキストを表示しない
    }

    token.innerHTML = `
        ${wideBtnHtml}
        <div class="token-bars">
            <div class="token-bar" title="HP: ${hp}/${maxHp}">
                <div class="token-bar-fill hp" style="width: ${hpPer}%"></div>
            </div>
            <div class="token-bar" title="MP: ${mp}/${maxMp}">
                <div class="token-bar-fill mp" style="width: ${mpPer}%"></div>
            </div>
            <div class="token-bar" title="FP: ${fp}">
                <div class="token-bar-fill fp" style="width: ${fpPer}%"></div>
            </div>
        </div>
        <div class="token-body" ${tokenBodyStyle}>${tokenBodyContent}</div>
        <div class="token-info-container">
            <div class="token-label">${char.name}</div>
            <div class="token-status-overlay">${iconsHtml}</div>
        </div>
    `;
    token.draggable = true;
    token.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', char.id);
        e.dataTransfer.effectAllowed = 'move';
        token.classList.add('dragging');
    });
    token.addEventListener('dragend', () => token.classList.remove('dragging'));
    // ダブルクリックで詳細モーダルを表示
    token.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        exitAttackTargetingMode(); // ターゲット選択モードを解除
        showCharacterDetail(char.id);
    });

    token.addEventListener('click', (e) => {
        e.stopPropagation();

        // ★修正: アクティブなマッチがある場合の挙動
        if (battleState.active_match && battleState.active_match.is_active) {
            const am = battleState.active_match;
            // 自分が攻撃者 or 防御者なら、ターゲットモードには入らずパネルを開く
            if (am.attacker_id === char.id || am.defender_id === char.id) {
                // パネルが閉じていれば開く
                if (typeof expandMatchPanel === 'function') expandMatchPanel();
                return;
            }
            // 他のキャラをクリックした場合は、現在進行中のマッチを無視してターゲットモードに入るべきか？
            // ユーザー要望「ハンドキャラをクリック...リセットされてしまう」-> 誤操作防止のため、
            // 進行中はハンドキャラクリックでパネル表示のみにするのが安全。
        }

        // ターゲット選択モード中の場合
        if (attackTargetingState.isTargeting && attackTargetingState.attackerId) {
            const attackerId = attackTargetingState.attackerId;

            // 自分自身は選択できない
            if (attackerId === char.id) {
                return;
            }

            // 攻撃確認
            const attackerChar = battleState.characters.find(c => c.id === attackerId);
            const attackerName = attackerChar ? attackerChar.name : "不明";

            // ★ 権限チェック: 攻撃者の所有者またはGMのみが実行可能
            const isOwner = attackerChar && attackerChar.owner === currentUsername;
            const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

            if (!isOwner && !isGM) {
                alert("キャラクターの所有者またはGMのみがマッチを開始できます。");
                exitAttackTargetingMode();
                return;
            }


            // ★修正: 1ターン1回制限のチェック
            // ここでconfirmを出す前にチェックしても良いが、openDuelModal内でもフラグを立てる
            /*
            if (window.matchActionInitiated) {
                alert("このターンは既にマッチを開始しています。(1ターン1回制限)");
                exitAttackTargetingMode();
                return;
            }
            */
            // ↑ ここでチェックすると、ターゲットクリック時に弾かれる。
            // しかし、ユーザー要望は「再発動の防止」。

            if (confirm(`【攻撃確認】\n「${attackerName}」が「${char.name}」に攻撃を仕掛けますか？`)) {
                openDuelModal(attackerId, char.id);
            }

            // ターゲット選択モードを解除
            exitAttackTargetingMode();
            return;
        }

        // 手番キャラの場合
        const isCurrentTurn = (battleState.turn_char_id === char.id);
        if (isCurrentTurn) {
            // ★ 権限チェック: 攻撃者の所有者またはGMのみがターゲットモードに入れる
            const isOwner = char.owner === currentUsername;
            const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

            if (!isOwner && !isGM) {
                // 所有者以外はここは何もしない (クリックで特に反応しない)
                // あるいは「操作権限がありません」と出すか？
                // 誤操作防止のため、何も出さないほうがユーザー体験は良いかもしれないが、
                // 明示的に行動しようとしてクリックしたなら出すべき。
                // 現状、手番キャラをクリック＝攻撃意志 とみなすUIなので、権限なければ警告。
                // ただし、単に詳細を見ようとしてダブルクリック手前で反応するのも鬱陶しい。
                // ここでは、一旦 return するのみとする（反応しない）。
                // 要望は「ロジックが組まれているか確認」-> 組まれてなければ組む。
                return;
            }

            // ★修正: 1ターン1回制限
            if (window.matchActionInitiated) {
                // マッチが終了しているが、このターン既に一度やっている場合
                alert("1ターンに1回のみマッチを開始できます。\n次のターンまでお待ちください。");
                return;
            }

            // ★追加: 広域攻撃ボタンが表示されている場合は広域マッチを開始
            // (isWideUserかつ、広域マッチが進行中でない場合)
            const isWideMatchExecuting = battleState.active_match && battleState.active_match.is_active && battleState.active_match.match_type === 'wide';
            if (char.isWideUser && !isWideMatchExecuting) {
                // 広域マッチを開始（広域攻撃ボタンと同じ処理）
                if (typeof openSyncedWideMatchModal === 'function') {
                    openSyncedWideMatchModal(char.id);
                }
                return;
            }

            enterAttackTargetingMode(char.id);
        }
    });

    return token;
}

function showCharacterDetail(charId) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;
    const existing = document.getElementById('char-detail-modal-backdrop');
    if (existing) existing.remove();
    const backdrop = document.createElement('div');
    backdrop.id = 'char-detail-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';
    backdrop.onclick = (e) => {
        if (e.target === backdrop) backdrop.remove();
    };

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.style.maxWidth = '500px';
    content.style.width = '90%';
    content.style.padding = '20px';
    content.style.position = 'relative';

    // パラメータHTML生成
    let paramsHtml = '';
    if (Array.isArray(char.params)) paramsHtml = char.params.map(p => `${p.label}:${p.value}`).join(' / ');
    else if (char.params && typeof char.params === 'object') paramsHtml = Object.entries(char.params).map(([k, v]) => `${k}:${v}`).join(' / ');
    else paramsHtml = 'なし';

    const fpVal = (char.states.find(s => s.name === 'FP') || {}).value || 0;

    let statesHtml = '';
    char.states.forEach(s => {
        if (['HP', 'MP', 'FP'].includes(s.name)) return;
        if (s.value === 0) return;
        const config = STATUS_CONFIG[s.name];
        const colorStyle = config ? `color: ${config.color}; font-weight:bold;` : '';
        statesHtml += `<div class="detail-buff-item" style="${colorStyle}">${s.name}: ${s.value}</div>`;
    });
    if (!statesHtml) statesHtml = '<span style="color:#999; font-size:0.9em;">なし</span>';

    let specialBuffsHtml = '';
    if (char.special_buffs && char.special_buffs.length > 0) {
        char.special_buffs.forEach((b, index) => {
            let buffInfo = { name: b.name, description: b.description || "", flavor: b.flavor || "" };

            // 輝化スキルの場合、skill_idから詳細情報を取得
            if (b.source === 'radiance' && b.skill_id) {
                // radianceデータから情報を取得（グローバルに保存されている想定）
                if (window.radianceSkillData && window.radianceSkillData[b.skill_id]) {
                    const radianceInfo = window.radianceSkillData[b.skill_id];
                    buffInfo.description = radianceInfo.description || buffInfo.description;
                    buffInfo.flavor = radianceInfo.flavor || buffInfo.flavor;
                }
            }

            // 通常バフの場合、BUFF_DATAから情報を取得
            if (!b.source || b.source !== 'radiance') {
                if (window.BUFF_DATA && typeof window.BUFF_DATA.get === 'function') {
                    const info = window.BUFF_DATA.get(b.name);
                    if (info) {
                        buffInfo.name = info.name || b.name;
                        if (!buffInfo.description && info.description) buffInfo.description = info.description;
                    }
                }
            }

            if (buffInfo.name.includes('_')) buffInfo.name = buffInfo.name.split('_')[0];
            let durationVal = null;
            if (b.lasting !== undefined && b.lasting !== null) durationVal = b.lasting;
            else if (b.round !== undefined && b.round !== null) durationVal = b.round;
            else if (b.duration !== undefined && b.duration !== null) durationVal = b.duration;
            let durationHtml = "";
            // ★修正: duration=0（永続）の場合は表示しない
            if (durationVal !== null && !isNaN(durationVal) && durationVal > 0 && durationVal < 99) {
                durationHtml = `<span class="buff-duration-badge" style="background:#666; color:#fff; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:8px; display:inline-block;">${durationVal}R</span>`;
            }

            // ★追加: デバッグログとディレイ表示
            console.log("Visual Battle Buff Data:", b);
            const delayVal = parseInt(b.delay, 10) || 0;
            if (delayVal > 0) {
                durationHtml += ` <span style="color: #d63384; font-weight:bold; margin-left:5px;">(発動まで ${delayVal}R)</span>`;
            }

            // 輝化スキルの場合はアイコンを追加
            const radianceIcon = (b.source === 'radiance') ? '✨ ' : '';

            const buffUniqueId = `buff-detail-${char.id}-${index}`;

            // 説明文とフレーバーテキストを組み合わせ
            let descriptionContent = '';
            if (buffInfo.description) {
                descriptionContent += `<div style="margin-bottom: 8px;">${buffInfo.description}</div>`;
            }
            if (buffInfo.flavor) {
                descriptionContent += `<div style="font-style: italic; color: #888; font-size: 0.85em;">${buffInfo.flavor}</div>`;
            }
            if (!descriptionContent) {
                descriptionContent = '(説明文なし)';
            }

            specialBuffsHtml += `
                <div style="width: 100%; margin-bottom: 4px;">
                    <div class="detail-buff-item special" onclick="toggleBuffDesc('${buffUniqueId}')" style="cursor: pointer; background: #f0f0f0; border-radius: 4px; padding: 6px 10px; display:flex; align-items:center;">
                        <span style="font-weight:bold; color:#333;">${radianceIcon}${buffInfo.name}</span>
                        ${durationHtml}
                        <span style="font-size:0.8em; opacity:0.7; margin-left:auto;">▼</span>
                    </div>
                    <div id="${buffUniqueId}" class="buff-desc-box" style="display:none; padding:8px; font-size:0.9em; background:#fff; border:1px solid #ddd; border-top:none; border-radius: 0 0 4px 4px; color:#555;">
                        ${descriptionContent}
                    </div>
                </div>`;
        });
    }
    if (!specialBuffsHtml) specialBuffsHtml = '<span style="color:#999; font-size:0.9em;">なし</span>';

    backdrop.innerHTML = `
        <div class="char-detail-modal">
            <div class="detail-header" style="display:flex; justify-content:space-between; align-items:center;">
                <h2 style="margin:0;">${char.name}</h2>
                <div style="display:flex; gap:10px; align-items:center;">
                    <button class="detail-setting-btn" style="background:none; border:none; font-size:1.4em; cursor:pointer;" title="設定">⚙</button>
                    <button class="detail-close-btn" style="background:none; border:none; font-size:1.8em; cursor:pointer;" title="閉じる">&times;</button>
                </div>
            </div>
            <div class="detail-stat-grid">
                <div class="detail-stat-box"><span class="detail-stat-label">HP</span><span class="detail-stat-val" style="color:#28a745;">${char.hp} / ${char.maxHp}</span></div>
                <div class="detail-stat-box"><span class="detail-stat-label">MP</span><span class="detail-stat-val" style="color:#007bff;">${char.mp} / ${char.maxMp}</span></div>
                <div class="detail-stat-box"><span class="detail-stat-label">FP</span><span class="detail-stat-val" style="color:#ffc107;">${fpVal}</span></div>
            </div>
            <div class="detail-section"><h4>Parameters</h4><div style="font-family:monospace; background:#f9f9f9; padding:8px; border-radius:4px; font-weight:bold;">${paramsHtml}</div></div>
            <div class="detail-section"><h4>状態異常 (Stack)</h4><div class="detail-buff-list">${statesHtml}</div></div>
            <div class="detail-section"><h4>特殊効果 / バフ (Click for Info)</h4><div class="detail-buff-list" style="display:block;">${specialBuffsHtml}</div></div>
            <div class="detail-section"><h4>Skills</h4><div style="font-size:0.9em; max-height:100px; overflow-y:auto; border:1px solid #eee; padding:5px; white-space: pre-wrap;">${char.commands || "なし"}</div></div>
        </div>
    `;

    document.body.appendChild(backdrop);

    const closeFunc = () => backdrop.remove();
    backdrop.querySelector('.detail-close-btn').onclick = closeFunc;

    // 歯車ボタンのイベント設定
    const settingBtn = backdrop.querySelector('.detail-setting-btn');
    if (settingBtn) {
        settingBtn.onclick = (e) => {
            e.stopPropagation();
            toggleCharSettingsMenu(char.id, settingBtn);
        };
    }

    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closeFunc(); });
}

// 歯車メニューの表示/非表示
function toggleCharSettingsMenu(charId, btnElement) {
    let menu = document.getElementById('char-settings-menu');

    // 既に開いていれば閉じる
    if (menu) {
        menu.remove();
        return;
    }

    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    menu = document.createElement('div');
    menu.id = 'char-settings-menu';
    menu.style.position = 'absolute';
    menu.style.background = 'white';
    menu.style.border = '1px solid #ccc';
    menu.style.borderRadius = '4px';
    menu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
    menu.style.zIndex = '10000';
    menu.style.minWidth = '180px';

    // ボタンの位置に合わせて表示
    const rect = btnElement.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 5}px`;
    menu.style.left = `${rect.left + window.scrollX - 100}px`; // 少し左にずらす

    // 所有者情報表示
    const ownerName = char.owner || '不明';
    const ownerDisplay = document.createElement('div');
    ownerDisplay.style.cssText = 'padding:8px 12px; margin-bottom:4px; background:#f0f0f0; font-size:0.85em; border-bottom:1px solid #ddd;';
    ownerDisplay.innerHTML = `<strong>所有者:</strong> ${ownerName}`;
    menu.appendChild(ownerDisplay);

    // 駒サイズスライダー
    const tokenScale = char.tokenScale || 1.0;
    const sizeSection = document.createElement('div');
    sizeSection.style.cssText = 'padding:8px 12px; margin-bottom:4px; border-bottom:1px solid #ddd;';
    sizeSection.innerHTML = `
        <div style="margin-bottom:5px; font-size:0.9em; font-weight:bold;">駒のサイズ</div>
        <div style="display:flex; align-items:center; gap:8px;">
            <input type="range" id="settings-token-scale-slider" min="0.5" max="2.0" step="0.1" value="${tokenScale}" style="flex:1;">
            <span id="settings-token-scale-display" style="min-width:35px; font-size:0.85em;">${tokenScale.toFixed(1)}x</span>
        </div>
    `;
    menu.appendChild(sizeSection);

    // スライダーイベント
    const scaleSlider = sizeSection.querySelector('#settings-token-scale-slider');
    const scaleDisplay = sizeSection.querySelector('#settings-token-scale-display');
    if (scaleSlider && scaleDisplay) {
        scaleSlider.oninput = () => {
            const newScale = parseFloat(scaleSlider.value);
            scaleDisplay.textContent = `${newScale.toFixed(1)}x`;

            if (typeof socket !== 'undefined' && currentRoomName) {
                socket.emit('request_update_token_scale', {
                    room: currentRoomName,
                    charId: charId,
                    scale: newScale
                });
            }
        };
    }

    // ★ 画像変更ボタン
    const imageSection = document.createElement('div');
    imageSection.style.cssText = 'padding:8px 12px; margin-bottom:4px; border-bottom:1px solid #ddd;';
    imageSection.innerHTML = `
        <div style="margin-bottom:5px; font-size:0.9em; font-weight:bold;">立ち絵画像</div>
        <button id="settings-image-picker-btn" style="width:100%; padding:8px; background:#007bff; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">画像を変更</button>
    `;
    menu.appendChild(imageSection);

    // 画像変更ボタンのイベント
    const imagePickerBtn = imageSection.querySelector('#settings-image-picker-btn');
    if (imagePickerBtn) {
        imagePickerBtn.onclick = () => {
            // Image Pickerモーダルを開く
            openImagePicker((selectedImage) => {
                // 画像選択時のコールバック
                console.log('[Settings] Image selected for char:', charId, selectedImage);

                // サーバーに保存
                socket.emit('request_state_update', {
                    room: currentRoomName,
                    charId: charId,
                    statName: 'image',
                    newValue: selectedImage.url
                });

                console.log('[Settings] Image updated on server');

                // メニューを閉じる
                menu.remove();
            });
        };
    }

    // メニューボタンの共通スタイルを適用する関数
    const styleMenuButton = (btn) => {
        btn.style.display = 'block';
        btn.style.width = '100%';
        btn.style.padding = '8px 12px';
        btn.style.border = 'none';
        btn.style.background = 'none';
        btn.style.textAlign = 'left';
        btn.style.cursor = 'pointer';
        btn.onmouseover = () => btn.style.background = '#f5f5f5';
        btn.onmouseout = () => btn.style.background = 'none';
        return btn;
    };

    // 未配置に戻すボタン
    const withdrawBtn = document.createElement('button');
    withdrawBtn.textContent = '未配置に戻す';
    styleMenuButton(withdrawBtn);
    withdrawBtn.onclick = () => {
        if (confirm('このキャラクターを未配置状態に戻しますか？')) {
            withdrawCharacter(charId);
            menu.remove();
            // 親モーダルも閉じる
            const backdrop = document.getElementById('char-detail-modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    };
    menu.appendChild(withdrawBtn);

    // 削除ボタン
    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'キャラクターを削除';
    styleMenuButton(deleteBtn);
    deleteBtn.style.color = '#dc3545';
    deleteBtn.onclick = () => {
        if (confirm(`本当に「${char.name}」を削除しますか？`)) {
            socket.emit('request_delete_character', {
                room: currentRoomName,
                charId: charId
            });
            menu.remove();
            const backdrop = document.getElementById('char-detail-modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    };
    menu.appendChild(deleteBtn);

    // 所有権譲渡ボタン
    const transferBtn = document.createElement('button');
    transferBtn.textContent = '所有権を譲渡 ▶';
    styleMenuButton(transferBtn);
    transferBtn.onclick = (e) => {
        e.stopPropagation();
        showTransferSubMenu(charId, menu, transferBtn);
    };
    menu.appendChild(transferBtn);

    document.body.appendChild(menu);

    // メニュー外クリックで閉じる
    setTimeout(() => {
        const closeHandler = (e) => {
            if (!menu.contains(e.target) && e.target !== btnElement) {
                menu.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        document.addEventListener('click', closeHandler);
    }, 0);
}


// キャラクターを未配置に戻す
function withdrawCharacter(charId) {
    if (!charId || !currentRoomName) return;



    // 座標 (-1, -1) に移動リクエスト
    socket.emit('request_move_character', {
        room: currentRoomName,
        character_id: charId,
        x: -1,
        y: -1
    });
}

// 所有権譲渡サブメニューの表示
function showTransferSubMenu(charId, parentMenu, parentBtn) {
    // 既存のサブメニューを削除
    const existingSubMenu = document.getElementById('transfer-sub-menu');
    if (existingSubMenu) {
        existingSubMenu.remove();
        return;
    }

    const subMenu = document.createElement('div');
    subMenu.id = 'transfer-sub-menu';
    subMenu.style.position = 'absolute';
    subMenu.style.background = 'white';
    subMenu.style.border = '1px solid #ccc';
    subMenu.style.borderRadius = '4px';
    subMenu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
    subMenu.style.zIndex = '10001';
    subMenu.style.minWidth = '200px';

    // 親ボタンの位置に合わせて右側に表示
    const rect = parentBtn.getBoundingClientRect();
    subMenu.style.top = `${rect.top + window.scrollY}px`;
    subMenu.style.left = `${rect.right + window.scrollX + 5}px`;

    // メニュー項目の共通スタイル
    const styleSubMenuItem = (item) => {
        item.style.display = 'block';
        item.style.width = '100%';
        item.style.padding = '8px 12px';
        item.style.border = 'none';
        item.style.background = 'none';
        item.style.textAlign = 'left';
        item.style.cursor = 'pointer';
        item.onmouseover = () => item.style.background = '#f5f5f5';
        item.onmouseout = () => item.style.background = 'none';
        return item;
    };

    // 全ユーザーから選択
    const allUsersBtn = document.createElement('button');
    allUsersBtn.textContent = '全ユーザーから選択';
    styleSubMenuItem(allUsersBtn);
    allUsersBtn.onclick = () => {
        openTransferOwnershipModal(charId, 'all');
        subMenu.remove();
        parentMenu.remove();
    };
    subMenu.appendChild(allUsersBtn);

    // 同じルームのユーザーから選択
    const roomUsersBtn = document.createElement('button');
    roomUsersBtn.textContent = '同じルームのユーザーから選択';
    styleSubMenuItem(roomUsersBtn);
    roomUsersBtn.onclick = () => {
        openTransferOwnershipModal(charId, 'room');
        subMenu.remove();
        parentMenu.remove();
    };
    subMenu.appendChild(roomUsersBtn);

    document.body.appendChild(subMenu);

    // サブメニュー外クリックで閉じる
    setTimeout(() => {
        const closeHandler = (e) => {
            if (!subMenu.contains(e.target) && e.target !== parentBtn) {
                subMenu.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        document.addEventListener('click', closeHandler);
    }, 0);
}

// 所有権譲渡モーダルを開く
function openTransferOwnershipModal(charId, mode) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    // 既存のモーダルを削除
    const existing = document.getElementById('transfer-modal-backdrop');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'transfer-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';
    modalContent.style.maxWidth = '400px';
    modalContent.style.width = '90%';
    modalContent.style.padding = '20px';

    const title = mode === 'all' ? '全ユーザーから選択' : '同じルームのユーザーから選択';

    modalContent.innerHTML = `
        <h3 style="margin-top:0;">所有権譲渡: ${title}</h3>
        <p style="font-size:0.9em; color:#666;">「${char.name}」の所有権を譲渡するユーザーを選択してください。</p>
        <div id="user-list-container" style="max-height:300px; overflow-y:auto; border:1px solid #ddd; border-radius:4px; margin:15px 0;">
            <div style="padding:20px; text-align:center; color:#999;">読み込み中...</div>
        </div>
        <div style="text-align:right; margin-top:15px;">
            <button id="transfer-cancel-btn" style="padding:8px 16px; margin-right:10px;">キャンセル</button>
        </div>
    `;

    backdrop.appendChild(modalContent);
    document.body.appendChild(backdrop);

    // キャンセルボタン
    modalContent.querySelector('#transfer-cancel-btn').onclick = () => backdrop.remove();
    backdrop.onclick = (e) => {
        if (e.target === backdrop) backdrop.remove();
    };

    // ユーザー一覧を取得
    const userListContainer = modalContent.querySelector('#user-list-container');
    let fetchUrl;

    if (mode === 'all') {
        fetchUrl = '/api/admin/users';
    } else {
        fetchUrl = `/api/get_room_users?room=${encodeURIComponent(currentRoomName)}`;
    }

    fetchWithSession(fetchUrl)
        .then(res => res.json())
        .then(users => {
            if (!users || users.length === 0) {
                userListContainer.innerHTML = '<div style="padding:20px; text-align:center; color:#999;">ユーザーが見つかりません。</div>';
                return;
            }

            userListContainer.innerHTML = '';
            users.forEach(user => {
                const userItem = document.createElement('div');
                userItem.style.cssText = 'padding:10px 15px; border-bottom:1px solid #eee; cursor:pointer; display:flex; justify-content:space-between; align-items:center;';
                userItem.onmouseover = () => userItem.style.background = '#f5f5f5';
                userItem.onmouseout = () => userItem.style.background = 'white';

                const userName = mode === 'all' ? user.name : user.username;
                const userId = user.id || user.user_id;

                userItem.innerHTML = `
                    <span style="font-weight:bold;">${userName}</span>
                    <span style="font-size:0.85em; color:#666;">${user.attribute || '不明'}</span>
                `;

                userItem.onclick = () => {
                    if (confirm(`「${char.name}」の所有権を「${userName}」に譲渡しますか？`)) {
                        socket.emit('request_transfer_character_ownership', {
                            room: currentRoomName,
                            character_id: charId,
                            new_owner_id: userId,
                            new_owner_name: userName
                        });
                        backdrop.remove();
                    }
                };

                userListContainer.appendChild(userItem);
            });
        })
        .catch(err => {
            console.error('Failed to fetch users:', err);
            userListContainer.innerHTML = '<div style="padding:20px; text-align:center; color:#dc3545;">ユーザー一覧の取得に失敗しました。</div>';
        });
}



function toggleBuffDesc(elementId) {
    const el = document.getElementById(elementId);
    if (el) el.style.display = (el.style.display === 'none') ? 'block' : 'none';
}

function selectVisualToken(charId) {
    document.querySelectorAll('.map-token').forEach(el => el.classList.remove('selected'));
    const token = document.querySelector(`.map-token[data-id="${charId}"]`);
    if (token) token.classList.add('selected');
}

/**
 * キャラクターのステータスアイコンHTMLを生成
 * @param {Object} char - キャラクター情報
 * @param {Array} [char.states] - ステータス効果の配列
 * @returns {string} ステータスアイコンのHTML
 */
function generateStatusIconsHTML(char) {
    if (!char.states) return '';

    let iconsHtml = '';
    char.states.forEach(s => {
        if (['HP', 'MP', 'FP'].includes(s.name)) return;
        if (s.value === 0) return;

        const config = STATUS_CONFIG[s.name];
        if (config) {
            iconsHtml += `
                <div class="duel-status-icon">
                    <img src="images/${config.icon}" alt="${s.name}">
                    <div class="duel-status-badge" style="background-color: ${config.color};">${s.value}</div>
                </div>`;
        }
    });
    return iconsHtml;
}

// ============================================
// Render Match Panel from Server State
// ============================================
// この関数は state_updated のたびに呼ばれ、パネルの内容を更新する
// パネルの開閉は行わず、内容の同期のみを担当
function renderMatchPanelFromState(matchData) {
    const panel = document.getElementById('match-panel');
    if (!panel) return;

    console.log('📋 renderMatchPanelFromState called:', {
        matchData: matchData ? { is_active: matchData.is_active, match_type: matchData.match_type } : null,
        panelExpanded: panel.classList.contains('expanded'),
        charactersCount: battleState.characters?.length
    });

    // マッチが非アクティブなら内容をクリアして折りたたむ
    if (!matchData || !matchData.is_active) {
        if (panel.classList.contains('expanded')) {
            clearMatchPanelContent();
            collapseMatchPanel();
        }
        // Hide both containers
        var wideContainer = document.getElementById('wide-match-container');
        var duelContainer = document.querySelector('.duel-container');
        if (wideContainer) wideContainer.style.display = 'none';
        if (duelContainer) duelContainer.style.display = '';
        return;
    }

    // ★ Wide Match branch - use separate wide_match_synced.js
    if (matchData.match_type === 'wide') {
        var wideContainer = document.getElementById('wide-match-container');
        var duelContainer = document.querySelector('.duel-container');
        if (wideContainer) wideContainer.style.display = '';
        if (duelContainer) duelContainer.style.display = 'none';

        if (panel.classList.contains('collapsed')) {
            expandMatchPanel();
            window._matchPanelAutoExpanded = true;
        }

        if (typeof window.populateWideMatchPanel === 'function') {
            window.populateWideMatchPanel(matchData);
        }
        return;
    }

    // ★ Duel Match - show duel container, hide wide container
    var wideContainer = document.getElementById('wide-match-container');
    var duelContainer = document.querySelector('.duel-container');
    if (wideContainer) wideContainer.style.display = 'none';
    if (duelContainer) duelContainer.style.display = '';

    // マッチがアクティブで、パネルが折りたたまれている場合は展開
    // （ただし、ユーザーが手動で閉じた可能性もあるため、初回のみ展開）
    const shouldAutoExpand = !window._matchPanelAutoExpanded;
    if (shouldAutoExpand && panel.classList.contains('collapsed')) {
        // キャラクターデータとスキルデータが揃っているか確認
        let attacker = battleState.characters?.find(c => c.id === matchData.attacker_id);
        let defender = battleState.characters?.find(c => c.id === matchData.defender_id);

        // ★ Phase 7/8: Snapshot Priority & Merge
        // 基本的にスナップショットがあればそれをベースにする（マッチ開始時の状態を正とするため）
        // ただしHPなどは現在の状態(attacker/defender)があればそちらを参照したいが、
        // 名前やコマンド(スキル)はスナップショットを優先すべき。
        if (matchData.attacker_snapshot) {
            if (!attacker) {
                attacker = matchData.attacker_snapshot;
            } else {
                // マージ: 名前とコマンドはスナップショット優先
                attacker = { ...attacker, name: matchData.attacker_snapshot.name, commands: matchData.attacker_snapshot.commands };
            }
        }
        if (matchData.defender_snapshot) {
            if (!defender) {
                defender = matchData.defender_snapshot;
            } else {
                defender = { ...defender, name: matchData.defender_snapshot.name, commands: matchData.defender_snapshot.commands };
            }
        }

        if (!attacker || !defender) {
            console.warn('renderMatchPanelFromState: Character data not ready yet');
            return;
        }

        // スキルデータがない場合はロードしてから再試行
        if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
            console.log('📋 Loading skill data before expanding panel...');
            fetch('/api/get_skill_data')
                .then(res => res.json())
                .then(data => {
                    window.allSkillData = data;
                    console.log('📋 Skill data loaded, retrying panel render');
                    renderMatchPanelFromState(matchData);
                })
                .catch(e => console.error('Failed to load skill data:', e));
            return;
        }

        // openDuelModal を使ってパネル内容を設定し、展開
        openDuelModal(matchData.attacker_id, matchData.defender_id, false, false, attacker, defender);
        window._matchPanelAutoExpanded = true;
    }

    // 計算結果と宣言状態をUIに反映
    // ★ Phase 10 Safety: reload時など、openDuelModalがスキップされた場合でも
    // duelStateを確実に復元する（Calculateボタンが動作するために必須）
    if (matchData.is_active && matchData.attacker_id && matchData.defender_id) {
        if (!duelState.attackerId || !duelState.defenderId) {
            console.log('[MatchPanel] Re-hydrating duelState from matchData');
            duelState.attackerId = matchData.attacker_id;
            duelState.defenderId = matchData.defender_id;
            duelState.isOneSided = matchData.is_one_sided || false; // 必要なら
        }
    }

    updateMatchPanelContent(matchData);

    // アクションドックを更新
    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }

    // ★ GM用 強制終了ボタンの注入（ヘッダーボタン群に配置）
    // 重複防止のため、両方のIDを削除
    const existingBtn = document.getElementById('force-end-match-btn');
    if (existingBtn) existingBtn.remove();
    const existingWideBtn = document.getElementById('wide-force-end-match-btn');
    if (existingWideBtn) existingWideBtn.remove();

    // ★修正: DOM要素ではなくグローバル変数でGM判定（リロード後も正しく動作）
    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

    if (isGM) {
        const headerButtons = document.querySelector('.panel-header-buttons');
        const reloadBtn = document.getElementById('panel-reload-btn');

        // 既に存在しない場合のみ追加
        if (headerButtons && reloadBtn && !document.getElementById('force-end-match-btn')) {
            const btn = document.createElement('button');
            btn.id = 'force-end-match-btn';
            btn.className = 'panel-reload-btn'; // 更新ボタンと同じクラスを使用
            btn.innerHTML = '⚠️';
            btn.title = 'GM権限でマッチを強制終了します';
            btn.style.cssText = 'background-color:#dc3545; color:white; border:1px solid #bd2130;';

            btn.onclick = function (e) {
                e.stopPropagation();
                if (confirm('【GM権限】マッチを強制終了しますか？\n現在行われているマッチ、または意図せず開いているマッチ画面を閉じます。\nこの操作は元に戻せません。')) {
                    // ★ Optimistic UI Update (Phase 1.5)
                    // 即座にパネルを閉じる
                    clearMatchPanelContent();
                    collapseMatchPanel();
                    document.getElementById('wide-match-container').style.display = 'none';
                    document.querySelector('.duel-container').style.display = ''; // Default reset

                    if (socket) socket.emit('request_force_end_match', { room: currentRoomName });
                }
            };

            // 更新ボタンの前に挿入
            headerButtons.insertBefore(btn, reloadBtn);
        }
    }
}

// ★ キャラクターの簡易ステータスバーを生成するヘルパー関数
window.renderCharacterStatsBar = function (char, containerOrId, options = {}) {
    const container = (typeof containerOrId === 'string')
        ? document.getElementById(containerOrId)
        : containerOrId;

    if (!container) return;

    if (!char) {
        container.innerHTML = '';
        return;
    }

    const hp = char.hp || 0;
    const maxHp = char.maxHp || 1;
    const mp = char.mp || 0;
    const maxMp = char.maxMp || 1;
    const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
    const fp = fpState ? fpState.value : 0;

    // オプション
    const isCompact = options.compact || false;
    const theme = options.theme || 'dark';

    // スタイル定義
    const wrapperDisplay = isCompact ? "inline-flex" : "flex";
    const wrapperMargin = isCompact ? "margin-left: 10px;" : "margin-bottom: 8px;";

    // テーマ別カラー設定
    let wrapperBg, hpColor, mpColor, fpColor, textColor, textShadow;
    const borderColor = (theme === 'light') ? "rgba(0,0,0,0.1)" : "rgba(255,255,255,0.2)";

    if (theme === 'light') {
        wrapperBg = "rgba(0, 0, 0, 0.05)";
        hpColor = "#28a745";
        mpColor = "#007bff";
        fpColor = "#d39e00";
        textColor = "#555";
        textShadow = "none";
    } else {
        wrapperBg = isCompact ? "rgba(0, 0, 0, 0.7)" : "rgba(0, 0, 0, 0.4)";
        hpColor = "#76ff93";
        mpColor = "#76cfff";
        fpColor = "#ffe676";
        textColor = "#ccc";
        textShadow = "1px 1px 0 #000";
    }

    const fontSizeVal = isCompact ? "0.95em" : "1.1em";
    const fontSizeLabel = isCompact ? "0.6em" : "0.7em";
    const padding = isCompact ? "1px 6px" : "2px 5px";

    const barStyle = `flex: 1; padding: ${padding}; text-align: center; border-right: 1px solid ${borderColor}; display: flex; align-items: baseline; justify-content: center; gap: 3px;`;

    // ラベルと値を横並びにする (Compact時) または 積み重ねる (通常時)
    // 視認性向上のため、Compact時は "HP 999" のように横並び推奨
    const contentLayout = isCompact ? "flex-direction: row; align-items: baseline;" : "flex-direction: column;";

    const labelStyle = `font-size: ${fontSizeLabel}; color: ${textColor}; font-weight: normal; line-height: 1; opacity: 0.8;`;
    const valStyle = `font-weight: bold; font-size: ${fontSizeVal}; line-height: 1; text-shadow: ${textShadow};`;

    // 枠全体
    const wrapperStyle = `display: ${wrapperDisplay}; align-items: center; gap: 0; ${wrapperMargin} background: ${wrapperBg}; border-radius: 4px; border: 1px solid ${borderColor}; overflow: hidden; vertical-align: middle; min-width: max-content;`;

    // 内部コンテンツ生成ヘルパー
    const makeBlock = (label, val, max, color, isLast) => {
        const borderStyle = isLast ? "border-right: none;" : "";
        const maxPart = max ? `<span style="font-size: 0.7em; color: #888; margin-left: 2px;">/${max}</span>` : "";

        if (isCompact) {
            // Compact: Label Val/Max (横並び)
            return `
                <div style="${barStyle} ${borderStyle} flex-direction: row; align-items: baseline;">
                    <span style="${labelStyle} margin-right: 2px;">${label}</span>
                    <span style="${valStyle} color: ${color};">${val}${maxPart}</span>
                </div>
             `;
        } else {
            // Normal: Label / Val/Max (縦積み)
            return `
                <div style="${barStyle} ${borderStyle} flex-direction: column;">
                    <span style="${labelStyle} margin-bottom: 2px;">${label}</span>
                    <span style="${valStyle} color: ${color};">${val}${maxPart}</span>
                </div>
             `;
        }
    };

    container.innerHTML = `
        <div style="${wrapperStyle}">
            ${makeBlock("HP", hp, maxHp, hpColor, false)}
            ${makeBlock("MP", mp, maxMp, mpColor, false)}
            ${makeBlock("FP", fp, null, fpColor, true)}
        </div>
    `;
}

// マッチパネルの内容を matchData に基づいて更新
function updateMatchPanelContent(matchData) {
    console.log('[MatchPanel] Updating content:', matchData);
    ['attacker', 'defender'].forEach(side => {
        const sideData = matchData[`${side}_data`];
        const isDeclared = matchData[`${side}_declared`] || false;
        const charId = side === 'attacker' ? matchData.attacker_id : matchData.defender_id;

        console.log(`[MatchPanel] ${side} data:`, sideData);

        // 計算結果の表示
        if (sideData) {
            // ★ Phase 10: Idempotent Name & Skill Sync (自己修復同期)
            // 名前がまだ初期値(Character A/B)や空なら、スナップショット等から強制更新する
            const nameEl = document.getElementById(`duel-${side}-name`);
            const currentName = nameEl ? nameEl.textContent : "";
            // 正しい名前の取得: スナップショット > sideDataの名前(あれば) > attacker/defenderオブジェクト
            let correctName = "";
            let correctChar = null;
            if (side === 'attacker') {
                if (matchData.attacker_snapshot) {
                    correctName = matchData.attacker_snapshot.name;
                    correctChar = matchData.attacker_snapshot;
                }
            } else {
                if (matchData.defender_snapshot) {
                    correctName = matchData.defender_snapshot.name;
                    correctChar = matchData.defender_snapshot;
                }
            }

            // 名前が不一致、かつ正しい名前があるなら更新
            if (correctName && (!currentName || currentName.startsWith('Character') || currentName !== correctName)) {
                console.log(`[Sync] Fixing name for ${side}: ${currentName} -> ${correctName}`);
                if (nameEl) nameEl.textContent = correctName;

                if (nameEl) nameEl.textContent = correctName;

                // ステータスアイコンも更新
                const statusEl = document.getElementById(`duel-${side}-status`);
                if (statusEl && correctChar) {
                    statusEl.innerHTML = generateStatusIconsHTML(correctChar);
                }

                // ★ HP/MP/FP ステータスバーの更新 (Sync時)
                renderCharacterStatsBar(correctChar, `duel-${side}-stats`);

                // ★プルダウンも空なら再生成
                const skillSelect = document.getElementById(`duel-${side}-skill`);
                if (skillSelect && skillSelect.options.length <= 1 && correctChar && correctChar.commands) {
                    console.log(`[Sync] Repopulating skills for ${side}`);
                    populateCharSkillSelect(correctChar, `duel-${side}-skill`);
                }
            }

            // ★ HP/MP/FP ステータスバーの更新 (通常時)
            const targetId = side === 'attacker' ? matchData.attacker_id : matchData.defender_id;
            const charObj = battleState.characters.find(c => c.id === targetId);
            if (charObj) {
                renderCharacterStatsBar(charObj, `duel-${side}-stats`);
            }

            // ★ クリックで詳細を開くイベントの設定
            if (nameEl && targetId) {
                nameEl.style.cursor = "pointer";
                nameEl.title = "クリックで詳細を表示";
                nameEl.onclick = (e) => {
                    e.stopPropagation();
                    showCharacterDetail(targetId);
                };
            }

            // コマンドプレビュー
            if (sideData.final_command) {
                const previewEl = document.getElementById(`duel-${side}-preview`);
                if (previewEl) {
                    const cmdEl = previewEl.querySelector('.preview-command');
                    const rangeEl = previewEl.querySelector('.preview-damage');

                    if (cmdEl) cmdEl.textContent = sideData.final_command;
                    // ... (省略なしで既存コード維持)
                    if (rangeEl) {
                        if (sideData.min_damage !== undefined && sideData.max_damage !== undefined) {
                            // ★ Phase 3: 補正内訳を改行形式で表示
                            let damageText = `Range: ${sideData.min_damage} ~ ${sideData.max_damage}`;

                            // ★ 基礎威力補正の取得（power_breakdown または skill_details から）
                            let basePowerMod = 0;
                            if (sideData.power_breakdown && sideData.power_breakdown.base_power_mod) {
                                basePowerMod = sideData.power_breakdown.base_power_mod;
                            } else if (sideData.skill_details && sideData.skill_details.base_power_mod) {
                                basePowerMod = sideData.skill_details.base_power_mod;
                            }

                            // 基礎威力補正を表示
                            if (basePowerMod !== 0) {
                                damageText += `\n[基礎威力 ${basePowerMod > 0 ? '+' : ''}${basePowerMod}]`;
                            }

                            // その他の補正（power_breakdownから）
                            if (sideData.power_breakdown) {
                                // const pb = sideData.power_breakdown;
                                // if (pb.additional_power && pb.additional_power !== 0) {
                                //     damageText += `\n(追加威力${pb.additional_power > 0 ? '+' : ''}${pb.additional_power})`;
                                // }
                            }

                            // ★ 戦慄によるダイス減少を表示
                            if (sideData.senritsu_dice_reduction && sideData.senritsu_dice_reduction > 0) {
                                damageText += `\n(戦慄: ダイス-${sideData.senritsu_dice_reduction})`;
                            }

                            // ★ 追加: 補正内訳を表示 (updateDuelUIと同様)
                            if (sideData.correction_details && sideData.correction_details.length > 0) {
                                sideData.correction_details.forEach(d => {
                                    const sign = d.value > 0 ? '+' : '';
                                    damageText += `\n[${d.source} ${sign}${d.value}]`;
                                });
                            }

                            rangeEl.style.whiteSpace = 'pre-line';
                            rangeEl.textContent = damageText;
                        } else {
                            rangeEl.textContent = "";
                        }
                    }
                    previewEl.classList.add('ready');
                }
                if (side === 'attacker') duelState.attackerCommand = sideData.final_command;
                else duelState.defenderCommand = sideData.final_command;
            }

            // スキル選択の復元
            if (sideData.skill_id) {
                const skillSelect = document.getElementById(`duel-${side}-skill`);
                if (skillSelect) {
                    // 値が異なる場合のみセット
                    if (skillSelect.value !== sideData.skill_id) {
                        skillSelect.value = sideData.skill_id;
                    }
                    // 詳細更新
                    let skillDataToUse = null;
                    if (sideData.skill_details) {
                        skillDataToUse = sideData.skill_details;
                    } else if (window.allSkillData && sideData.skill_id) {
                        skillDataToUse = window.allSkillData[sideData.skill_id];
                    }
                    if (skillDataToUse) {
                        // ★ 修正: 計算済み（final_commandあり）なら詳細をフル表示、そうでなければ空白
                        if (sideData.final_command) {
                            const descArea = document.getElementById(`duel-${side}-skill-desc`);
                            if (descArea) descArea.innerHTML = formatSkillDetailHTML(skillDataToUse);
                        } else {
                            updateSkillDescription(side, skillDataToUse);
                        }
                    }
                }
            }
        }

        // 宣言状態の反映
        const declareBtn = document.getElementById(`duel-${side}-declare-btn`);
        const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
        const skillSelect = document.getElementById(`duel-${side}-skill`);

        if (isDeclared) {
            // 宣言済み → ロック
            if (declareBtn) {
                declareBtn.textContent = 'Locked';
                declareBtn.classList.add('locked');
                declareBtn.disabled = true;
            }
            if (calcBtn) calcBtn.disabled = true;
            if (skillSelect) skillSelect.disabled = true;
            if (side === 'attacker') duelState.attackerLocked = true;
            else duelState.defenderLocked = true;
        } else {
            // 未宣言 → 権限チェック
            const canControl = canControlCharacter(charId);

            // ★ Phase 12: local cache からの復元チェック (他人の宣言による同期で自分の計算結果が消えるのを防ぐ)
            const skillSelect = document.getElementById(`duel-${side}-skill`);
            const currentSkillId = skillSelect ? skillSelect.value : "";
            let hasCalcResult = !!(sideData && sideData.final_command);

            if (!hasCalcResult && canControl && window._duelLocalCalcCache && window._duelLocalCalcCache[side]) {
                const cached = window._duelLocalCalcCache[side];
                // キャラクターIDとスキルIDが一致している場合のみ復元
                if (cached.char_id === charId && cached.skill_id === currentSkillId) {
                    console.log(`[Sync] Restoring local calc result for ${side}`);
                    // updateDuelUIを直接呼ぶと再帰や無限ループの恐れがあるため、最低限の反映を行う
                    // または updateDuelUI(side, { ...cached.data, enableButton: true });
                    // ただし、updateDuelUI内でも duelState を更新するため、そのまま呼んで良い
                    updateDuelUI(side, { ...cached.data, enableButton: true });
                    hasCalcResult = true;
                }
            }

            if (declareBtn) {
                declareBtn.textContent = '宣言';
                declareBtn.classList.remove('locked');
                declareBtn.disabled = !(hasCalcResult && canControl);
            }
            if (calcBtn) calcBtn.disabled = !canControl;
            if (skillSelect) skillSelect.disabled = !canControl;
            if (side === 'attacker') duelState.attackerLocked = false;
            else duelState.defenderLocked = false;
        }
    });
}

// --- 修正: openDuelModal 関数 ---
function openDuelModal(attackerId, defenderId, isOneSided = false, emitSync = true, attackerObj = null, defenderObj = null) {
    let attacker = attackerObj || battleState.characters.find(c => c.id === attackerId);
    let defender = defenderObj || battleState.characters.find(c => c.id === defenderId);

    // ★ Phase 7: Snapshot fallback (主にリロード時用)
    if (!attacker && battleState.active_match?.attacker_snapshot?.id === attackerId) {
        console.log('Using attacker snapshot for modal');
        attacker = battleState.active_match.attacker_snapshot;
    }
    if (!defender && battleState.active_match?.defender_snapshot?.id === defenderId) {
        console.log('Using defender snapshot for modal');
        defender = battleState.active_match.defender_snapshot;
    }


    if (!attacker || !defender) return;

    // ★ 修正: emitSync=trueの場合はサーバーにリクエストを送るだけで、
    // クライアント側ではまだ開かない (サーバーからの match_modal_opened を待つ)
    if (emitSync) {
        // ★修正: マッチ開始フラグを立てる (1ターン1回制限)
        // window.matchActionInitiated = true; // REMOVED

        socket.emit('open_match_modal', {
            room: currentRoomName,
            match_type: 'duel',
            attacker_id: attackerId,
            defender_id: defenderId
        });
        return; // ★ ここで終了し、ローカルでは開かない
    }

    // ★ 以下はサーバーからの通知で開く場合のみ実行される (emitSync = false)
    duelState = {
        attackerId, defenderId,
        attackerLocked: false, defenderLocked: false,
        isOneSided: false,
        attackerCommand: null, defenderCommand: null
    };

    // ★ 新規マッチ時はローカルキャッシュをリセット
    window._duelLocalCalcCache = { attacker: null, defender: null };

    // ★ 追加: マッチ開催フラグを設定
    if (!battleState.active_match) {
        battleState.active_match = {
            is_active: false,
            match_type: 'duel',
            attacker_id: null,
            defender_id: null,
            targets: [],
            attacker_data: {},
            defender_data: {}
        };
    }
    battleState.active_match.is_active = true;
    battleState.active_match.match_type = 'duel';
    battleState.active_match.attacker_id = attackerId;
    battleState.active_match.defender_id = defenderId;

    // アイコンの状態を更新
    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }

    resetDuelUI();
    duelState.isOneSided = isOneSided;
    document.getElementById('duel-attacker-name').textContent = attacker.name;
    document.getElementById('duel-attacker-status').innerHTML = generateStatusIconsHTML(attacker);
    populateCharSkillSelect(attacker, 'duel-attacker-skill');
    if (isOneSided) {
        document.getElementById('duel-defender-name').textContent = `${defender.name} (行動済み)`;
        document.getElementById('duel-defender-status').innerHTML = generateStatusIconsHTML(defender);
    } else {
        document.getElementById('duel-defender-name').textContent = defender.name;
        document.getElementById('duel-defender-status').innerHTML = generateStatusIconsHTML(defender);
    }

    const isDefenderWideUser = defender.isWideUser;
    const hasReEvasion = defender.special_buffs && defender.special_buffs.some(b => b.name === '再回避ロック');

    if ((defender.hasActed && !hasReEvasion) || isDefenderWideUser) {
        duelState.isOneSided = true;
        duelState.defenderLocked = true;
        if (isDefenderWideUser) {
            duelState.defenderCommand = "【広域待機（防御放棄）】";
            document.getElementById('duel-defender-lock-msg').textContent = "広域攻撃待機中のため防御スキル使用不可";
        } else {
            duelState.defenderCommand = "【一方攻撃（行動済）】";
            document.getElementById('duel-defender-lock-msg').textContent = "行動済みのため防御不可";
        }
        document.getElementById('duel-defender-controls').style.display = 'none';
        document.getElementById('duel-defender-lock-msg').style.display = 'block';
        document.getElementById('duel-defender-preview').querySelector('.preview-command').textContent = "No Guard";
    } else {
        document.getElementById('duel-defender-controls').style.display = 'block';
        document.getElementById('duel-defender-lock-msg').style.display = 'none';
        populateCharSkillSelect(defender, 'duel-defender-skill');
    }
    setupDuelListeners();

    // ★ 変更: モーダルではなくパネルを展開
    expandMatchPanel();

    // ★ 追加: ロック状態なら初期表示時にUIをロックする
    if (duelState.attackerLocked) lockSide('attacker');
    if (duelState.defenderLocked) lockSide('defender');

}

// Match Panel Control Functions
// ============================================

function expandMatchPanel() {
    const panel = document.getElementById('match-panel');
    if (!panel) return;

    panel.classList.remove('collapsed');
    panel.classList.add('expanded');

    // Update action dock icon
    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }
}

function collapseMatchPanel() {
    const panel = document.getElementById('match-panel');
    if (!panel) return;

    panel.classList.remove('expanded');
    panel.classList.add('collapsed');

    // Update action dock icon
    if (typeof updateActionDock === 'function') {
        updateActionDock();
    }
}

function toggleMatchPanel() {
    const panel = document.getElementById('match-panel');
    if (!panel) return;

    if (panel.classList.contains('collapsed')) {
        expandMatchPanel();
    } else {
        collapseMatchPanel();
    }
}

function reloadMatchPanel() {
    console.log('🔄 Reloading match panel from current state');

    if (!battleState || !battleState.active_match) {
        console.warn('No active match to reload');
        return;
    }

    const matchData = battleState.active_match;

    // マッチがアクティブな場合のみリロード
    if (matchData.is_active) {
        // 一旦 auto-expand フラグをリセット
        window._matchPanelAutoExpanded = false;

        // renderMatchPanelFromState を呼び出して再描画
        renderMatchPanelFromState(matchData);
    } else {
        console.log('Match is not active, nothing to reload');
    }
}

function closeMatchPanel(emitSync = false) {
    // Clear panel content
    clearMatchPanelContent();

    // Collapse panel
    collapseMatchPanel();

    // Clear match state
    if (battleState.active_match) {
        battleState.active_match.is_active = false;
    }

    // Notify server
    if (emitSync) {
        socket.emit('close_match_modal', { room: currentRoomName });
    }
}

function clearMatchPanelContent() {
    // Reset UI to initial state
    resetDuelUI();

    // Clear character names
    document.getElementById('duel-attacker-name').textContent = 'Character A';
    document.getElementById('duel-defender-name').textContent = 'Character B';

    // Clear duel state
    duelState = {
        attackerId: null, defenderId: null,
        attackerLocked: false, defenderLocked: false,
        isOneSided: false,
        attackerCommand: null, defenderCommand: null
    };
}


// --- 修正: resetDuelUI 関数 ---
function resetDuelUI() {
    ['attacker', 'defender'].forEach(side => {
        const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
        const declBtn = document.getElementById(`duel-${side}-declare-btn`);
        const preview = document.getElementById(`duel-${side}-preview`);
        const skillSelect = document.getElementById(`duel-${side}-skill`);

        // ★修正: 詳細エリアは隠さず、中身だけ空にする
        const descArea = document.getElementById(`duel-${side}-skill-desc`);
        if (descArea) {
            descArea.innerHTML = "";
            // descArea.classList.remove('visible'); // 削除
        }

        if (calcBtn) calcBtn.disabled = false;
        if (declBtn) {
            declBtn.disabled = true; declBtn.textContent = "宣言";
            declBtn.classList.remove('locked');
            declBtn.dataset.isImmediate = 'false';
        }
        if (skillSelect) skillSelect.disabled = false;
        if (preview) {
            preview.querySelector('.preview-command').textContent = "---";
            preview.querySelector('.preview-damage').textContent = "";
            preview.classList.remove('ready');
        }
    });
    const statusMsg = document.getElementById('duel-status-message');
    if (statusMsg) statusMsg.textContent = "Setup Phase";
}

function populateCharSkillSelect(char, elementId) {
    const select = document.getElementById(elementId);
    select.innerHTML = '';
    /*
       ★修正: allSkillDataがなくても続行する (char.commandsから名前が取れるため)
       リロード直後にプルダウンが空になる問題を修正
    */
    /*
    if (!window.allSkillData || Object.keys(window.allSkillData).length === 0) {
        const opt = document.createElement('option');
        opt.value = ""; opt.text = "(Skill Data Loading...)";
        select.appendChild(opt);
        return;
    }
    */
    let count = 0;
    const commandsStr = char.commands || "";
    const selectEl = document.getElementById(elementId);
    if (!selectEl || !char.commands) return;
    selectEl.innerHTML = '';
    const regex = /【(.*?)\s+(.*?)】/g;
    let match;

    // ★ Phase 10: 混乱(Confusion)判定
    // 混乱バフがある場合、スキル選択肢を「混乱 (行動不能)」のみにする
    let isConfused = false;
    if (char.special_buffs && Array.isArray(char.special_buffs)) {
        isConfused = char.special_buffs.some(b =>
            (b.buff_id === 'Bu-02' || b.name === '混乱' || b.buff_id === 'Bu-03' || b.name.includes('混乱')) &&
            (b.lasting > 0)
        );
    }

    if (isConfused) {
        const option = document.createElement('option');
        option.value = 'S-Confusion';
        option.textContent = '混乱 (行動不能)';
        selectEl.appendChild(option);

        // スキル選択時のイベントリスナーを追加（ダミーデータ用）
        selectEl.onchange = () => {
            updateSkillDescription(elementId.includes('attacker') ? 'attacker' : 'defender', {
                name: '混乱 (行動不能)',
                description: '行動不能です。ターンをスキップします。'
            });
        };
        return;
    }

    // ★ Phase 9.2: 再回避ロック判定 (UIフィルタリング)
    let lockedSkillId = null;
    if (char.special_buffs && Array.isArray(char.special_buffs)) {
        // IDまたは名前で判定（サーバー側の堅牢化に合わせて両方チェック）
        const lockBuff = char.special_buffs.find(b =>
            (b.buff_id === 'Bu-05' || b.name === '再回避ロック') &&
            (b.delay === 0 || b.delay === '0') &&
            (b.lasting > 0 || b.lasting === '1') // lastingチェックは緩めに
        );

        if (lockBuff && lockBuff.skill_id) {
            lockedSkillId = lockBuff.skill_id;
            console.log(`[UI Filter] Dodge Lock active for ${char.name}. Only allowing: ${lockedSkillId}`);
        }
    }

    while ((match = regex.exec(char.commands)) !== null) {
        const skillId = match[1];
        const skillName = match[2];

        // ★ 再回避ロックフィルタ: ロック中は指定ID以外を除外
        if (lockedSkillId && skillId !== lockedSkillId) {
            continue;
        }

        // ★ Phase 12.3: 広域スキルと即時発動スキルは通常のデュエルモーダルでは除外
        const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
        if (skillData) {
            // 広域スキルを除外
            if (isWideSkillData(skillData)) {
                continue;
            }
            // 即時発動タグのスキルを除外
            if (skillData.tags && skillData.tags.includes('即時発動')) {
                continue;
            }
        }

        const option = document.createElement('option');
        option.value = skillId;
        option.textContent = `${skillId}: ${skillName}`;
        selectEl.appendChild(option);
    }
    if (selectEl.options.length === 0) {
        const placeholder = document.createElement('option');
        placeholder.textContent = '(スキルなし)';
        placeholder.disabled = true;
        selectEl.appendChild(placeholder);
        selectEl.appendChild(placeholder);
    }

    // スキル選択時のイベントリスナーを追加
    selectEl.onchange = () => {
        const skillId = selectEl.value;
        const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
        if (skillData) {
            updateSkillDescription(elementId.includes('attacker') ? 'attacker' : 'defender', skillData);
        }
    };
}

// ★修正: 選択時は詳細を隠す (ユーザー要望)
function updateSkillDescription(side, skillData) {
    const descArea = document.getElementById(`duel-${side}-skill-desc`);
    if (descArea) {
        // ★修正: 選択直後は空白にする（ユーザー要望「威力計算をするまでスキル詳細欄は空白のままで構いません」）
        descArea.innerHTML = "";
    }
}

// formatSkillDetailHTML is now active in legacy_globals.js

function setupDuelListeners() {
    const minimizeBtn = document.getElementById('duel-minimize-btn');

    // マッチ開催状態を確認して最小化ボタンの表示を制御
    if (minimizeBtn) {
        // ... (省略) ...
    }

    const attCalcBtn = document.getElementById('duel-attacker-calc-btn');
    if (attCalcBtn) {
        attCalcBtn.onclick = () => {
            sendSkillDeclaration('attacker', false);
        };
    } else {
    }

    const defCalcBtn = document.getElementById('duel-defender-calc-btn');
    if (defCalcBtn) {
        defCalcBtn.onclick = () => {
            sendSkillDeclaration('defender', false);
        };
    }

    const attDeclBtn = document.getElementById('duel-attacker-declare-btn');
    if (attDeclBtn) {
        attDeclBtn.onclick = () => {
            const btn = document.getElementById('duel-attacker-declare-btn');
            const isImmediate = btn.dataset.isImmediate === 'true';
            sendSkillDeclaration('attacker', true);
            if (!isImmediate) lockSide('attacker');
        };
    }

    const defDeclBtn = document.getElementById('duel-defender-declare-btn');
    if (defDeclBtn) {
        defDeclBtn.onclick = () => {
            const btn = document.getElementById('duel-defender-declare-btn');
            const isImmediate = btn.dataset.isImmediate === 'true';
            sendSkillDeclaration('defender', true);
            if (!isImmediate) lockSide('defender');
        };
    }
}

// ★ Phase 10: Stateless Declaration
function sendSkillDeclaration(side, isCommit) {
    if (!battleState || !battleState.active_match) {
        return;
    }
    const match = battleState.active_match;
    const isAttacker = (side === 'attacker');

    // UIのduelStateではなく、サーバーから同期された確定情報を使用する
    const actorId = isAttacker ? match.attacker_id : match.defender_id;
    const targetId = isAttacker ? match.defender_id : match.attacker_id;

    const skillSelect = document.getElementById(`duel-${side}-skill`);
    const skillId = skillSelect ? skillSelect.value : "";

    if (!skillId) { alert("スキルを選択してください。"); return; }

    // ★ コストチェック
    const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
    const actor = battleState.characters.find(c => c.id === actorId);
    if (skillData && actor && skillData['特記処理']) {
        try {
            const rule = JSON.parse(skillData['特記処理']);
            const tags = skillData.tags || [];
            if (rule.cost && !tags.includes('即時発動')) {
                // ヘルパー関数: 値を検索
                const findStatusValue = (obj, targetKey) => {
                    // 1. ルートプロパティ (hp, mp, sanなど)
                    if (obj[targetKey] !== undefined) return parseInt(obj[targetKey]);
                    if (obj[targetKey.toLowerCase()] !== undefined) return parseInt(obj[targetKey.toLowerCase()]);

                    // 2. states配列 (FPなど)
                    if (obj.states) {
                        const state = obj.states.find(s => s.name === targetKey || s.name === targetKey.toUpperCase());
                        if (state) return parseInt(state.value);
                    }

                    // 3. params配列 (その他)
                    if (obj.params) {
                        const param = obj.params.find(p => p.label === targetKey);
                        if (param) return parseInt(param.value);
                    }
                    return 0;
                };

                for (const c of rule.cost) {
                    const type = c.type;
                    const val = parseInt(c.value || 0);
                    if (val > 0 && type) {
                        const current = findStatusValue(actor, type);

                        if (current < val) {
                            // インラインエラー表示に変更
                            const previewEl = document.getElementById(`duel-${side}-preview`);
                            const descEl = document.getElementById(`duel-${side}-skill-desc`);

                            if (previewEl) {
                                previewEl.textContent = "Cost Error";
                                previewEl.style.color = "red";
                            }
                            if (descEl) {
                                descEl.innerHTML = `<div style="color: #ff4444; font-weight: bold; padding: 5px; border: 1px solid #ff4444; background: rgba(255,0,0,0.1); border-radius: 4px;">
                                    ${type}が不足しています<br>
                                    (必要: ${val}, 現在: ${current})
                                </div>`;
                            }
                            return;
                        }
                    }
                }
            }
        } catch (e) { console.error("Cost check error:", e); }
    }

    socket.emit('request_skill_declaration', {
        room: currentRoomName,
        actor_id: actorId, target_id: targetId,
        skill_id: skillId, modifier: 0,
        prefix: `visual_${side}`,
        commit: isCommit, custom_skill_name: ""
    });
}

// --- 修正: updateDuelUI 関数 ---
function updateDuelUI(side, data) {
    const previewEl = document.getElementById(`duel-${side}-preview`);
    const cmdEl = previewEl.querySelector('.preview-command');
    const dmgEl = previewEl.querySelector('.preview-damage');
    const declareBtn = document.getElementById(`duel-${side}-declare-btn`);

    // ★追加: 詳細表示エリアの更新処理
    const descArea = document.getElementById(`duel-${side}-skill-desc`);

    if (data.error) {
        cmdEl.textContent = "Error";
        dmgEl.textContent = data.final_command;

        // エラー時は枠を残しつつエラーメッセージ
        if (descArea) descArea.innerHTML = "<div style='color:red;'>計算エラー</div>";
        return;
    }

    cmdEl.innerHTML = data.final_command;
    if (data.min_damage !== undefined) {
        let damageText = `Range: ${data.min_damage} ~ ${data.max_damage}`;

        // ★ 基礎威力補正を表示
        if (data.skill_details && data.skill_details.base_power_mod) {
            const mod = data.skill_details.base_power_mod;
            damageText += `\n[基礎威力 ${mod > 0 ? '+' : ''}${mod}]`;
        }

        // ★追加: 物理/魔法補正の内訳を表示
        if (data.correction_details && data.correction_details.length > 0) {
            data.correction_details.forEach(d => {
                const sign = d.value > 0 ? '+' : '';
                damageText += `\n[${d.source} ${sign}${d.value}]`;
            });
        }

        // ★ 戦慄によるダイス減少を表示
        if (data.senritsu_dice_reduction && data.senritsu_dice_reduction > 0) {
            damageText += `\n[ダイス威力 -${data.senritsu_dice_reduction}] (戦慄)`;
        }

        dmgEl.style.whiteSpace = 'pre-line';
        dmgEl.textContent = damageText;
    } else {
        dmgEl.textContent = "Ready";
    }
    previewEl.classList.add('ready');

    // ★修正: スキル詳細の表示 (クラス操作なし)
    if (descArea && data.skill_details) {
        descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
    }

    // ★追加: 即時発動かどうかをボタンに保存
    if (declareBtn && data.is_immediate) {
        declareBtn.dataset.isImmediate = 'true';
        declareBtn.textContent = '即時発動 (Execute)';
        declareBtn.classList.add('immediate-btn');
    } else if (declareBtn) {
        declareBtn.dataset.isImmediate = 'false';
        declareBtn.textContent = '宣言';
        declareBtn.classList.remove('immediate-btn');
    }



    // ★ 修正: enableButton引数で制御（デフォルトはtrue = 有効化）
    // skill_declaration_resultの場合はtrue、match_data_updated（同期）の場合はfalse
    // さらに、既にロックされている（宣言済み）場合は強制的に無効化する
    const shouldEnable = data.enableButton !== undefined ? data.enableButton : true;
    const isLocked = (side === 'attacker' && duelState.attackerLocked) || (side === 'defender' && duelState.defenderLocked);

    if (declareBtn) {
        if (isLocked) {
            declareBtn.disabled = true; // 既に宣言済みなので無効のまま
            declareBtn.textContent = "Locked"; // 表示もLockedを維持
            // data.final_command で上書きされている場合があるのでロック状態を優先
        } else if (shouldEnable) {
            declareBtn.disabled = false; // 自分が計算したので有効化
        } else {
            declareBtn.disabled = true; // 同期データなので無効のまま
            declareBtn.title = '相手が計算したスキルです';
        }
    }

    // ★追加: 恐怖などのペナルティ情報を保存（マッチ実行時に使用）
    if (previewEl && data.senritsu_penalty !== undefined) {
        previewEl.dataset.senritsuPenalty = data.senritsu_penalty;
    }
    // ★ local cache への保存 (自分が計算した場合)
    if (data.enableButton) {
        if (!window._duelLocalCalcCache) window._duelLocalCalcCache = { attacker: null, defender: null };
        window._duelLocalCalcCache[side] = {
            data: data,
            skill_id: data.skill_id,
            char_id: side === 'attacker' ? duelState.attackerId : duelState.defenderId
        };
    }

    if (side === 'attacker') duelState.attackerCommand = data.final_command;
    else duelState.defenderCommand = data.final_command;
}

// 権限チェックヘルパー
function canControlCharacter(charId) {
    if (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM') return true;
    if (typeof battleState === 'undefined' || !battleState.characters) return false;
    const char = battleState.characters.find(c => c.id === charId);
    // currentUserId check covers most cases, username is fallback
    return char && (char.owner === currentUsername || (typeof currentUserId !== 'undefined' && char.owner_id === currentUserId));
}

// ★ 追加: 同期データを受信してUIを更新
function applyMatchDataSync(side, data) {
    // スキル選択の同期
    if (data.skill_id !== undefined) {
        const skillSelect = document.getElementById(`duel-${side}-skill`);
        if (skillSelect && skillSelect.value !== data.skill_id) {
            skillSelect.value = data.skill_id;
        }
    }

    // 計算結果の同期（権限エラーを回避するため、結果を直接UIに適用）
    if (data.final_command !== undefined) {
        updateDuelUI(side, {
            prefix: `visual_${side}`,
            final_command: data.final_command,
            min_damage: data.min_damage,
            max_damage: data.max_damage,
            is_immediate: data.is_immediate,
            skill_details: data.skill_details,
            senritsu_penalty: data.senritsu_penalty,
            correction_details: data.correction_details,
            // ★ 修正: 宣言済みの場合はボタンを無効、そうでなければ権限チェック
            enableButton: data.declared ? false : canControlCharacter(side === 'attacker' ? duelState.attackerId : duelState.defenderId),
            error: false
        });

        // internal stateも更新
        if (side === 'attacker') duelState.attackerCommand = data.final_command;
        else duelState.defenderCommand = data.final_command;

        // ★ 追加: 宣言済み（declared=true）ならロック状態にする
        if (data.declared) {
            console.log(`🔒 locking ${side} side via sync`);
            lockSide(side);
        }
    }
}

function lockSide(side) {
    const btn = document.getElementById(`duel-${side}-declare-btn`);
    const calcBtn = document.getElementById(`duel-${side}-calc-btn`);
    const select = document.getElementById(`duel-${side}-skill`);
    if (btn) { btn.textContent = "Locked"; btn.classList.add('locked'); btn.disabled = true; }
    if (calcBtn) calcBtn.disabled = true;
    if (select) select.disabled = true;
    if (side === 'attacker') duelState.attackerLocked = true;
    if (side === 'defender') duelState.defenderLocked = true;

    // ★ 修正: checkAndExecuteMatchは呼ばない（両側宣言が完了したらサーバーから通知が来る）
    // checkAndExecuteMatch(); // 削除
}

function checkAndExecuteMatch() {
    const statusEl = document.getElementById('duel-status-message');
    if (duelState.isOneSided) {
        if (duelState.attackerLocked) {
            statusEl.textContent = "Executing One-sided Attack...";
            executeMatch();
        } else {
            statusEl.textContent = "Waiting for Attacker...";
        }
    } else {
        if (duelState.attackerLocked && duelState.defenderLocked) {
            statusEl.textContent = "Executing Duel...";
            executeMatch();
        } else if (duelState.attackerLocked) statusEl.textContent = "Waiting for Defender...";
        else if (duelState.defenderLocked) statusEl.textContent = "Waiting for Attacker...";
    }
}

function executeMatch() {
    setTimeout(() => {
        if (!battleState || !battleState.active_match) return;
        const match = battleState.active_match;
        const attackerName = document.getElementById('duel-attacker-name').textContent;
        const defenderName = document.getElementById('duel-defender-name').textContent;
        const stripTags = (str) => str ? str.replace(/<[^>]*>?/gm, '') : "2d6";

        // ★ Phase 10: Use battleState (SSOT)
        socket.emit('request_match', {
            room: currentRoomName,
            actorIdA: match.attacker_id, actorIdD: match.defender_id, // duelState.attackerId -> match.attacker_id
            actorNameA: attackerName, actorNameD: defenderName,
            commandA: stripTags(duelState.attackerCommand), // Command is still UI state updated by sync
            commandD: stripTags(duelState.defenderCommand),
            senritsuPenaltyA: parseInt(document.getElementById('duel-attacker-preview')?.dataset?.senritsuPenalty || 0),
            senritsuPenaltyD: parseInt(document.getElementById('duel-defender-preview')?.dataset?.senritsuPenalty || 0)
        });

        // マッチ完了後、モーダルを閉じる
        setTimeout(() => {
            closeDuelModal();
        }, 500);

        // 手番を更新
        setTimeout(() => {
            socket.emit('request_next_turn', { room: currentRoomName });
        }, 1000);
    }, 300);
}

// --- 広域宣言モーダル (Visual版) ---
function openVisualWideDeclarationModal() {
    const existing = document.getElementById('visual-wide-decl-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'visual-wide-decl-modal';
    backdrop.className = 'modal-backdrop';

    let listHtml = '';
    battleState.characters.forEach(char => {
        if (char.hp <= 0) return;
        // ★ 未配置キャラクターは除外
        if (char.x < 0 || char.y < 0) return;
        if (!hasWideSkill(char)) return;

        const typeColor = char.type === 'ally' ? '#007bff' : '#dc3545';
        listHtml += `
            <div style="padding: 10px; border-bottom: 1px solid #eee; display:flex; align-items:center;">
                <input type="checkbox" class="visual-wide-check" value="${char.id}" style="transform:scale(1.3); margin-right:15px;">
                <span style="font-weight:bold; color:${typeColor}; font-size:1.1em;">${char.name}</span>
                <span style="margin-left:auto; color:#666;">SPD: ${char.totalSpeed || char.speedRoll || 0}</span>
            </div>
        `;
    });

    if (!listHtml) listHtml = '<div style="padding:15px; color:#666;">広域スキルを所持するキャラクターがいません</div>';

    backdrop.innerHTML = `
        <div class="modal-content" style="width: 500px; padding: 0;">
            <div style="padding: 15px; background: #6f42c1; color: white; border-radius: 8px 8px 0 0;">
                <h3 style="margin:0;">⚡ 広域攻撃予約 (Visual)</h3>
            </div>
            <div style="padding: 20px; max-height: 60vh; overflow-y: auto;">
                <p>今ラウンド、広域攻撃を行うキャラクターを選択してください。<br>
                ※GMまたは全員が確認ボタンを押すと確定します。</p>
                <div style="border: 1px solid #ddd; border-radius: 4px;">${listHtml}</div>
            </div>
            <div style="padding: 15px; background: #f8f9fa; text-align: right; border-radius: 0 0 8px 8px;">
                <!-- キャンセルボタン削除 -->
                <button id="visual-wide-confirm" class="duel-btn primary" style="width:100%;">決定 (確認)</button>
            </div>
        </div>
    `;

    document.body.appendChild(backdrop);
    // document.getElementById('visual-wide-cancel').onclick = () => backdrop.remove(); // Removed
    const confirmBtn = document.getElementById('visual-wide-confirm');
    confirmBtn.onclick = () => {
        const checks = backdrop.querySelectorAll('.visual-wide-check');
        const ids = Array.from(checks).filter(c => c.checked).map(c => c.value);

        // Confirm Button Action
        socket.emit('request_wide_modal_confirm', { room: currentRoomName, wideUserIds: ids });

        // Disable button to prevent double submit / show waiting state
        confirmBtn.disabled = true;
        confirmBtn.textContent = "確認済み: 他プレイヤー待機中...";
        confirmBtn.classList.remove('primary');
        confirmBtn.classList.add('secondary');
    };
}

// --- ★広域攻撃実行モーダル (Visual版) - 抜本修正版 ---
function openVisualWideMatchModal(attackerId) {
    const char = battleState.characters.find(c => c.id === attackerId);
    if (!char) return;

    // グローバル状態管理変数へのセット
    visualWideState.attackerId = attackerId;
    visualWideState.isDeclared = false;

    const existing = document.getElementById('visual-wide-match-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'visual-wide-match-modal';
    backdrop.className = 'modal-backdrop';

    // スキル選択肢作成
    let skillOptions = '<option value="">-- スキルを選択 --</option>';

    // ★ Phase 9.2: 再回避ロック判定 (UIフィルタリング - 広域攻撃側)
    let lockedSkillId = null;
    if (char.special_buffs && Array.isArray(char.special_buffs)) {
        const lockBuff = char.special_buffs.find(b =>
            (b.buff_id === 'Bu-05' || b.name === '再回避ロック') &&
            (b.delay === 0 || b.delay === '0') &&
            (b.lasting > 0 || b.lasting === '1')
        );
        if (lockBuff && lockBuff.skill_id) {
            lockedSkillId = lockBuff.skill_id;
        }
    }

    if (char.commands && window.allSkillData) {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        while ((match = regex.exec(char.commands)) !== null) {
            const sId = match[1];
            const sName = match[2];

            // ★ 再回避ロックフィルタ
            if (lockedSkillId && sId !== lockedSkillId) {
                continue;
            }

            const sData = window.allSkillData[sId];
            if (sData && isWideSkillData(sData)) {
                skillOptions += `<option value="${sId}">${sId}: ${sName}</option>`;
            }
        }
    }

    // UI構築 (data-raw属性を追加)
    backdrop.innerHTML = `
        <div class="modal-content wide-visual-modal">
            <div class="wide-visual-header">
                <h3 style="margin:0;">⚡ 広域攻撃実行: ${char.name} <span style="opacity:0.5; margin:0 10px;">|</span> 対象キャラクター (Defenders)</h3>
                <button class="detail-close-btn" style="color:white;" onclick="document.getElementById('visual-wide-match-modal').remove()">×</button>
            </div>
            <div class="wide-visual-body">
                <div class="wide-col-attacker">
                    <div class="wide-attacker-section">
                        <div style="margin-bottom:5px;">
                            <label style="font-weight:bold; display:block;">使用スキル:</label>
                            <select id="v-wide-skill-select" class="duel-select" style="width:100%; margin-top:5px;">${skillOptions}</select>
                        </div>

                        <div style="display:flex; gap:10px; margin-top:10px; align-items:center;">
                            <button id="v-wide-calc-btn" class="duel-btn calc" style="width: 100px; flex-shrink:0;">威力計算</button>
                            <span id="v-wide-mode-badge" class="wide-mode-badge" style="display:none;">MODE</span>
                        </div>

                        <div style="margin-top:10px; font-weight:bold; font-size:1.1em; display:flex; align-items:center; gap:10px;">
                            <span style="flex-shrink:0;">結果: </span>
                            <input type="text" id="v-wide-attacker-cmd" class="duel-input" style="flex:1; min-width:0;" readonly placeholder="[計算結果]" data-raw="">
                            <button id="v-wide-declare-btn" class="duel-btn declare" disabled style="width: 100px; flex-shrink:0;">宣言</button>
                        </div>

                        <div id="v-wide-attacker-desc" class="skill-detail-display" style="margin-top:10px;"></div>
                    </div>
                </div>

                <div class="wide-col-defenders">
                    <div id="v-wide-defenders-area" class="wide-defenders-grid">
                        <div style="grid-column:1/-1; padding:20px; text-align:center; color:#999;">
                            スキルを選択して「威力計算」を行うと対象が表示されます
                        </div>
                    </div>
                </div>
            </div>
            <div style="padding:15px; background:#eee; text-align:right;">
                <button id="v-wide-execute-btn" class="duel-btn declare" disabled>広域攻撃を実行</button>
            </div>
        </div>
    `;

    document.body.appendChild(backdrop);

    const skillSelect = document.getElementById('v-wide-skill-select');
    const calcBtn = document.getElementById('v-wide-calc-btn');
    const declareBtn = document.getElementById('v-wide-declare-btn');
    const executeBtn = document.getElementById('v-wide-execute-btn');
    const defendersArea = document.getElementById('v-wide-defenders-area');
    const modeBadge = document.getElementById('v-wide-mode-badge');
    const attackerCmdInput = document.getElementById('v-wide-attacker-cmd');
    const attackerDescArea = document.getElementById('v-wide-attacker-desc');

    let currentMode = null;

    // --- 1. 威力計算ボタン ---
    calcBtn.onclick = () => {
        const skillId = skillSelect.value;
        if (!skillId) return alert("スキルを選択してください");

        // UIリセット
        attackerCmdInput.value = "計算中...";
        attackerCmdInput.style.color = "#888";
        attackerCmdInput.dataset.raw = ""; // リセット
        if (attackerDescArea) attackerDescArea.innerHTML = ""; // 詳細エリアリセット

        // 再計算時は宣言状態解除
        visualWideState.isDeclared = false;
        if (declareBtn) {
            declareBtn.disabled = true;
            declareBtn.textContent = "宣言";
            declareBtn.classList.remove('locked', 'btn-danger');
            declareBtn.classList.add('btn-outline-danger');
        }
        executeBtn.disabled = true;


        // 重要: ターゲットに自分自身を指定して、TargetNotSelectedエラーを回避しつつ威力のみ計算させる
        socket.emit('request_skill_declaration', {
            room: currentRoomName,
            prefix: 'visual_wide_attacker',
            actor_id: attackerId,
            target_id: attackerId,
            skill_id: skillId,
            commit: false // 計算のみ
        });

        // モード表示と対象リスト更新 (ローカル処理)
        const skillData = window.allSkillData ? window.allSkillData[skillId] : null;
        if (skillData) {
            const cat = skillData['分類'] || '';
            const dist = skillData['距離'] || '';
            const tags = skillData['tags'] || [];

            if ((cat.includes('合算') || dist.includes('合算') || tags.includes('広域-合算'))) {
                currentMode = 'combined';
                modeBadge.textContent = "合算 (Combined)";
                modeBadge.style.backgroundColor = "#28a745";
            } else {
                currentMode = 'individual';
                modeBadge.textContent = "個別 (Individual)";
                modeBadge.style.backgroundColor = "#17a2b8";
            }
            modeBadge.style.display = 'inline-block';
            renderVisualWideDefenders(attackerId, currentMode);
        }
    };

    // --- 2. 宣言ボタン (Socket受信後に有効化される) ---
    declareBtn.onclick = () => {
        if (!attackerCmdInput.value || attackerCmdInput.value.includes("計算中") || attackerCmdInput.value.startsWith("エラー")) {
            return;
        }

        // 状態更新
        visualWideState.isDeclared = true;

        // UIロック
        skillSelect.disabled = true;
        calcBtn.disabled = true;
        declareBtn.disabled = true;
        declareBtn.textContent = "宣言済";
        declareBtn.classList.add('locked');
        attackerCmdInput.style.backgroundColor = "#e8f0fe";

        // 実行ボタン有効化
        executeBtn.disabled = false;
    };

    // --- 3. 実行ボタン ---
    executeBtn.onclick = () => {
        if (!visualWideState.isDeclared) {
            return alert("攻撃側の宣言が完了していません");
        }

        // 修正: 新しい行クラスに対応
        const defenderRows = defendersArea.querySelectorAll('.wide-defender-row');
        const defendersData = [];
        defenderRows.forEach(row => {
            const defId = row.dataset.id;
            const cmdInput = row.querySelector('.v-wide-def-cmd');
            const skillId = row.querySelector('.v-wide-def-skill').value;

            // 重要: 防御側も生データを送信する
            // 生データがない(計算していない/防御放棄)場合は空文字
            const rawCmd = cmdInput.dataset.raw || "";

            // 防御側は宣言必須ではないが、計算結果があればそれを採用
            defendersData.push({ id: defId, skillId: skillId || "", command: rawCmd });
        });

        // 重要: 攻撃側も生データ(dataset.raw)を送信する
        const attackerRawCmd = attackerCmdInput.dataset.raw;
        if (!attackerRawCmd) {
            return alert("攻撃側の計算結果が不正です。再計算してください。");
        }

        if (confirm(`【${currentMode === 'combined' ? '合算' : '個別'}】広域攻撃を実行しますか？`)) {
            socket.emit('request_wide_match', {
                room: currentRoomName,
                actorId: attackerId,
                skillId: skillSelect.value,
                mode: currentMode,
                commandActor: attackerRawCmd, // 生データを送信
                defenders: defendersData
            });
            backdrop.remove();

            // 追加: 通常マッチと同様に、少し待ってからターン終了リクエストを送る
            setTimeout(() => {

                socket.emit('request_next_turn', { room: currentRoomName });
            }, 1000);
        }
    };
}

// --- ★防御側カード生成 (宣言ボタン追加版 + スキル名表示修正) ---
function renderVisualWideDefenders(attackerId, mode) {
    const area = document.getElementById('v-wide-defenders-area');
    area.innerHTML = '';
    const attacker = battleState.characters.find(c => c.id === attackerId);
    const targetType = attacker.type === 'ally' ? 'enemy' : 'ally';
    // ★ 修正: 未配置キャラクター（x < 0 または y < 0）を除外
    const targets = battleState.characters.filter(c => c.type === targetType && c.hp > 0 && c.x >= 0 && c.y >= 0);

    if (targets.length === 0) {
        area.innerHTML = '<div style="padding:20px;">対象がいません</div>';
        return;
    }

    targets.forEach(tgt => {
        const isWideUser = tgt.isWideUser;
        const hasActed = tgt.hasActed;
        const hasReEvasion = tgt.special_buffs && tgt.special_buffs.some(b => b.name === '再回避ロック');
        const isDefenseLocked = (hasActed && !hasReEvasion) || isWideUser;

        let opts = '';
        if (isDefenseLocked) {
            if (isWideUser) opts = '<option value="">(防御放棄:広域待機)</option>';
            else opts = '<option value="">(防御放棄:行動済)</option>';
        } else {
            opts = '<option value="">(防御なし)</option>';
            if (tgt.commands) {
                const r = /【(.*?)\s+(.*?)】/g;
                let m;
                while ((m = r.exec(tgt.commands)) !== null) {
                    const skillId = m[1];
                    const skillName = m[2];

                    // ★ フィルタリング: 即時発動スキルと広域スキルを除外
                    if (window.allSkillData && window.allSkillData[skillId]) {
                        const skillData = window.allSkillData[skillId];

                        // 即時発動スキルを除外
                        if (skillData.tags && skillData.tags.includes('即時発動')) {
                            continue;
                        }

                        // 広域スキルを除外（広域に対する広域迎撃は不可）
                        if (skillData.tags && (skillData.tags.includes('広域-個別') || skillData.tags.includes('広域-合算'))) {
                            continue;
                        }
                    }

                    // 修正: スキル名も表示する (ID: Name)
                    opts += `<option value="${skillId}">${skillId}: ${skillName}</option>`;
                }
            }
        }

        // 修正: .wide-defender-row クラスを使用し、新しいレイアウトに刷新
        const row = document.createElement('div');
        row.className = 'wide-defender-row';
        row.dataset.id = tgt.id;
        if (isDefenseLocked) row.style.background = "#f0f0f0";

        // data-raw属性を追加
        row.innerHTML = `
            <div class="wide-def-info">
                <div>${tgt.name}</div>
                <div class="v-wide-status" style="font-size:0.8em; color:#999;">${isDefenseLocked ? '不可' : '未計算'}</div>
            </div>
            <div class="wide-def-controls">
                <select class="v-wide-def-skill duel-select" style="width:100%; margin-bottom:5px; font-size:12px;" ${isDefenseLocked ? 'disabled' : ''}>${opts}</select>
                <div style="display:flex; gap:5px; align-items:center;">
                    <button class="v-wide-def-calc duel-btn secondary" style="padding:4px 8px; font-size:12px;" ${isDefenseLocked ? 'disabled' : ''}>Calc</button>
                    <input type="text" class="v-wide-def-cmd duel-input" readonly placeholder="Result" style="flex:1; font-size:12px;" value="${isDefenseLocked ? (isWideUser ? '【防御放棄】' : '【一方攻撃（行動済）】') : ''}" data-raw="">
                    <button class="v-wide-def-declare duel-btn outline-success" style="padding:4px 8px; font-size:12px;" disabled>宣言</button>
                </div>
            </div>
            <div class="v-wide-def-desc wide-def-desc skill-detail-display" style="margin-top:0; min-height:80px;"></div>
        `;
        area.appendChild(row);

        const btnCalc = row.querySelector('.v-wide-def-calc');
        const btnDeclare = row.querySelector('.v-wide-def-declare');
        const skillSel = row.querySelector('.v-wide-def-skill');
        const cmdInput = row.querySelector('.v-wide-def-cmd');
        const statusSpan = row.querySelector('.v-wide-status');
        const descArea = row.querySelector('.v-wide-def-desc');

        // Calc Logic
        btnCalc.onclick = () => {
            const sId = skillSel.value;
            statusSpan.textContent = "計算中...";
            // 計算時には宣言状態をリセット
            btnDeclare.disabled = true;
            btnDeclare.classList.remove('btn-success');
            btnDeclare.classList.add('btn-outline-success');
            btnDeclare.textContent = "宣言";
            cmdInput.style.backgroundColor = "";
            cmdInput.dataset.raw = ""; // リセット
            if (descArea) descArea.innerHTML = ""; // 詳細リセット

            socket.emit('request_skill_declaration', {
                room: currentRoomName,
                prefix: `visual_wide_def_${tgt.id}`,
                actor_id: tgt.id,
                target_id: attackerId,
                skill_id: sId,
                commit: false
            });
        };

        // Declare Logic
        btnDeclare.onclick = () => {
            // UI Lock
            skillSel.disabled = true;
            btnCalc.disabled = true;
            btnDeclare.disabled = true;
            btnDeclare.textContent = "宣言済";
            btnDeclare.classList.remove('btn-outline-success');
            btnDeclare.classList.add('btn-success'); // 緑色確定
            cmdInput.style.backgroundColor = "#e0ffe0"; // 薄緑背景
            statusSpan.textContent = "宣言済";
        };
    });
}

document.addEventListener('DOMContentLoaded', () => {
    // 画面ロード時にDOMがまだ完全に構築されていない可能性があるため、
    // ポーリングでボタンの存在を確認してからリスナーを登録する
    const checkInterval = setInterval(() => {
        const btn = document.getElementById('duel-attacker-calc-btn');
        if (btn) {
            setupDuelListeners();
            clearInterval(checkInterval);

            // ★ Refinement: DOMが見つかり次第、即座に同期リクエストを送る (Auto-Sync)
            console.log('🔄 DOM Ready. Triggering immediate room state sync...');
            const roomName = document.getElementById('room-name-display')?.textContent || 'ROOM 1';

            // Socket接続確認とリクエスト
            if (typeof socket !== 'undefined' && socket.connected) {
                socket.emit('request_room_state', { room: roomName });
            } else {
                const checkSocket = setInterval(() => {
                    if (typeof socket !== 'undefined' && socket.connected) {
                        socket.emit('request_room_state', { room: roomName });
                        clearInterval(checkSocket);
                    }
                }, 500);
            }
        }
    }, 100);

    // タイムアウト (5秒)
    setTimeout(() => clearInterval(checkInterval), 5000);
});