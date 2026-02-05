// static/js/exploration/exploration_dock.js

// グローバル変数
if (!window.ExplorationDock) {
    window.ExplorationDock = {};
}

(function (scope) {
    // 探索パラメータ定数
    const EXPLORATION_PARAMS = ['五感', '採取', '本能', '鑑定', '対話', '尋問', '諜報', '窃取', '隠密', '運動', '制作', '回避'];

    function setupExplorationDock() {
        console.log("Setting up Exploration Dock...");
        // 既存のアクションドックは main.js / action_dock.js で制御されているが
        // 探索モード時は中身を入れ替えるか、別ドックを表示するか
        // ここでは action_dock.js と連携して、モードに応じて updateActionDock をフックする形が良いが
        // 簡易的に、Exploration Viewport内に専用ドックを表示する、あるいはAction Dockエリアを書き換える

        // main.js の updateActionDock で呼び出してもらう想定で関数を公開
    }

    function renderExplorationDock() {
        const dock = document.getElementById('action-dock');
        if (!dock) return;

        dock.innerHTML = '';
        dock.className = 'action-dock exploration-mode'; // クラス追加でCSS切り替え可能に

        const userAttr = (typeof currentUserAttribute !== 'undefined') ? currentUserAttribute : 'Player';
        console.log('[ExplorationDock] Rendering dock. User Attribute:', userAttr);

        // 1. 背景設定ボタン (GMのみ)
        if (userAttr === 'GM') {
            const bgBtn = createDockIcon('🖼️', '背景変更', openExplorationBgPicker);
            // bgBtn.style.background = '#e74c3c';
            dock.appendChild(bgBtn);
        }

        // 2. 探索判定ボタン
        const rollBtn = createDockIcon('🎲', '探索判定', openExplorationRollModal);
        dock.appendChild(rollBtn);

        // 3. 簡易ステータス編集ボタン
        const quickEditBtn = createDockIcon('📝', '簡易ステータス編集', () => {
            if (typeof openQuickEditModal === 'function') {
                openQuickEditModal();
            } else {
                alert("ステータス編集機能が見つかりません");
            }
        });
        dock.appendChild(quickEditBtn);

        // 4. キャラクター追加ボタン (共通モーダル)
        const loadCharBtn = createDockIcon('➕', 'キャラクター読み込み', () => {
            if (typeof openCharLoadModal === 'function') {
                openCharLoadModal();
            } else {
                alert("キャラクター読み込み機能が見つかりません");
            }
        });
        dock.appendChild(loadCharBtn);

        // 5. 未配置キャラボタン (共通モーダル)
        const stagingBtn = createDockIcon('📦', '未配置キャラクター', () => {
            if (typeof toggleStagingAreaOverlay === 'function') {
                toggleStagingAreaOverlay();
            } else {
                alert("未配置キャラクター機能が見つかりません");
            }
        });
        dock.appendChild(stagingBtn);

        // 6. 戦闘へ戻るボタン (GMのみ) - 一番下へ配置
        if (userAttr === 'GM') {
            const backBtn = createDockIcon('⚔️', '戦闘パートへ戻る', () => {
                if (confirm('戦闘パートに戻りますか？')) {
                    socket.emit('request_change_mode', {
                        room: currentRoomName,
                        mode: 'battle'
                    });
                }
            });
            backBtn.style.background = '#e74c3c';
            dock.appendChild(backBtn);
        }

        // ★ Exploration Modeではラウンド進行ボタンを非表示にする
        const rStartBtn = document.getElementById('visual-round-start-btn');
        const rEndBtn = document.getElementById('visual-round-end-btn');
        if (rStartBtn) rStartBtn.style.display = 'none';
        if (rEndBtn) rEndBtn.style.display = 'none';

    }

    function createDockIcon(emoji, title, onClick) {
        const div = document.createElement('div');
        div.className = 'dock-icon';
        div.textContent = emoji;
        div.title = title;
        div.onclick = onClick;
        return div;
    }

    // --- 背景変更モーダル ---
    function openExplorationBgPicker() {
        if (typeof openImagePicker === 'function') {
            openImagePicker((selectedImage) => {
                socket.emit('request_update_exploration_bg', {
                    room: currentRoomName,
                    image_url: selectedImage.url
                });
            }, 'background'); // ★ 背景モード
        } else {
            alert("画像ピッカーが見つかりません");
        }
    }

    // --- 探索判定モーダル ---
    function openExplorationRollModal() {
        // キャラクター選択 -> 技能選択 -> 難易度設定 -> ロール
        const modalHtml = `
            <div id="exp-roll-modal" class="modal-backdrop" style="display:flex;">
                <div class="modal-content" style="width:450px; border-radius:12px; border:none; box-shadow:0 10px 25px rgba(0,0,0,0.5); overflow:hidden; padding:0; display:flex; flex-direction:column;">

                    <div class="modal-header" style="background: linear-gradient(135deg, #8e44ad 0%, #9b59b6 100%); color: white; padding: 15px 20px; display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center;">
                            <span style="font-size: 1.5em; margin-right: 10px;">🎲</span>
                            <h3 style="margin:0; font-size: 1.2em;">探索判定</h3>
                        </div>
                        <button id="exp-roll-close" style="border:none; background:rgba(255,255,255,0.2); color:white; width: 30px; height: 30px; border-radius: 50%; cursor:pointer; font-size:1.2em; display:flex; align-items:center; justify-content:center;">×</button>
                    </div>

                    <div style="padding: 25px; background: #fff;">

                        <div style="margin-bottom:20px;">
                            <label style="display:block; font-weight:bold; color:#555; margin-bottom:5px;">キャラクター</label>
                            <select id="exp-roll-char-select" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:6px; background:#f9f9f9; font-size:1em;">
                                <!-- Options populated by JS -->
                            </select>
                        </div>

                        <div style="margin-bottom:20px;">
                            <label style="display:block; font-weight:bold; color:#555; margin-bottom:5px;">使用技能</label>
                            <select id="exp-roll-skill-select" style="width:100%; padding:10px; border:1px solid #ddd; border-radius:6px; background:#f9f9f9; font-size:1em;">
                                ${EXPLORATION_PARAMS.map(p => `<option value="${p}">${p}</option>`).join('')}
                            </select>
                        </div>

                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-bottom:25px;">
                            <div>
                                <label style="display:block; font-weight:bold; color:#555; margin-bottom:5px;">ダイス数</label>
                                <input type="number" id="exp-roll-dice-count" value="2" min="1" max="10"
                                    style="width:100%; padding:10px; border:1px solid #ddd; border-radius:6px; font-weight:bold; text-align:center; font-size:1.1em;">
                            </div>
                            <div>
                                <label style="display:block; font-weight:bold; color:#555; margin-bottom:5px;">目標値 (任意)</label>
                                <input type="number" id="exp-roll-difficulty" value="0" min="0" placeholder="なし"
                                    style="width:100%; padding:10px; border:1px solid #ddd; border-radius:6px; font-weight:bold; text-align:center; font-size:1.1em;">
                            </div>
                        </div>

                        <div style="display:flex; justify-content: flex-end; gap: 10px; border-top: 1px solid #eee; padding-top: 20px;">
                            <button id="exp-roll-cancel" style="padding: 10px 20px; border: 1px solid #ddd; background: white; border-radius: 6px; cursor: pointer; color:#555;">キャンセル</button>
                            <button id="exp-roll-execute" style="padding: 10px 25px; border: none; background: linear-gradient(to bottom, #8e44ad, #9b59b6); color: white; border-radius: 6px; cursor: pointer; font-weight:bold; box-shadow: 0 4px 6px rgba(142, 68, 173, 0.3);">判定を実行</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = document.getElementById('exp-roll-modal');
        const charSelect = document.getElementById('exp-roll-char-select');

        // キャラクターリスト設定
        let hasChar = false;
        if (battleState && battleState.characters) {
            battleState.characters.forEach(c => {
                // 自分のキャラ or GMなら全員
                // ★ 修正: 未配置でも配置済みでも判定は可能とするか、配置済みのみにするか。ここでは一旦全員。
                if (currentUserAttribute === 'GM' || c.owner_id === currentUserId || c.owner === currentUsername) {
                    const opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = c.name;
                    charSelect.appendChild(opt);
                    hasChar = true;
                }
            });
        }

        if (!hasChar) {
            const opt = document.createElement('option');
            opt.textContent = "対象キャラクターがいません";
            charSelect.appendChild(opt);
            charSelect.disabled = true;
            document.getElementById('exp-roll-execute').disabled = true;
            document.getElementById('exp-roll-execute').style.opacity = 0.5;
        }

        // イベント
        const closeFunc = () => modal.remove();
        document.getElementById('exp-roll-cancel').onclick = closeFunc;
        document.getElementById('exp-roll-close').onclick = closeFunc;

        // 背景クリックで閉じる
        modal.onclick = (e) => {
            if (e.target === modal) closeFunc();
        };

        // ボタンのホバーエフェクト
        const closeBtn = document.getElementById('exp-roll-close');
        closeBtn.onmouseenter = () => closeBtn.style.background = 'rgba(255,255,255,0.4)';
        closeBtn.onmouseleave = () => closeBtn.style.background = 'rgba(255,255,255,0.2)';

        document.getElementById('exp-roll-execute').onclick = () => {
            const charId = charSelect.value;
            const skillName = document.getElementById('exp-roll-skill-select').value;
            const diceCount = document.getElementById('exp-roll-dice-count').value;
            const difficulty = document.getElementById('exp-roll-difficulty').value;

            if (!charId || charSelect.disabled) {
                alert("キャラクターを選択してください");
                return;
            }

            // 技能レベルを取得
            const char = battleState.characters.find(c => c.id === charId);
            let skillLevel = 0;
            if (char && char.params) {
                // params の構造チェック (Array vs Object)
                if (Array.isArray(char.params)) {
                    const p = char.params.find(obj => obj.label === skillName);
                    if (p) skillLevel = parseInt(p.value, 10) || 0;
                } else {
                    skillLevel = parseInt(char.params[skillName], 10) || 0;
                }
            }

            // バリデーション
            if (diceCount < 1) {
                alert("ダイス数は1以上である必要があります");
                return;
            }

            socket.emit('request_exploration_roll', {
                room: currentRoomName,
                char_id: charId,
                skill_name: skillName,
                skill_level: skillLevel,
                dice_count: diceCount,
                difficulty: difficulty
            });
            modal.remove();
        };
    }

    // --- 立ち絵追加モーダル (GM Only) ---
    function openTachieAddModal() {
        // 未配置のキャラクターから選択して Exploration View に追加（初期位置中央）
        // 簡易実装: 未配置リストを表示し、選択すると (100, 100) あたりに配置

        // ... (staging overlay の流用か、新規作成)
        // ここでは簡易的にプロンプトや単純なリストで実装
        const chars = battleState.characters.filter(c => {
            // まだ探索ビューにいないキャラ
            const locs = (battleState.exploration && battleState.exploration.tachie_locations) || {};
            return !locs[c.id];
        });

        if (chars.length === 0) {
            alert("追加できるキャラクターがいません（全員配置済みか、キャラがいません）");
            return;
        }

        // 簡易モーダル
        let listHtml = chars.map(c => `
            <div class="tachie-select-item" data-id="${c.id}" style="padding:10px; border-bottom:1px solid #eee; cursor:pointer;">
                ${c.name}
            </div>
        `).join('');

        const modalHtml = `
            <div id="exp-add-modal" class="modal-backdrop" style="display:flex;">
                <div class="modal-content" style="width:300px; padding:20px;">
                    <h3>立ち絵追加</h3>
                    <div style="max-height:300px; overflow-y:auto;">${listHtml}</div>
                    <button id="exp-add-cancel" style="margin-top:10px; width:100%;">キャンセル</button>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = document.getElementById('exp-add-modal');
        modal.querySelectorAll('.tachie-select-item').forEach(item => {
            item.onclick = () => {
                const charId = item.dataset.id;
                socket.emit('request_update_tachie_location', {
                    room: currentRoomName,
                    char_id: charId,
                    x: 100,
                    y: 100,
                    scale: 1.0
                });
                modal.remove();
            };
        });
        document.getElementById('exp-add-cancel').onclick = () => modal.remove();
    }

    // --- Public API ---
    scope.render = renderExplorationDock;

})(window.ExplorationDock);
