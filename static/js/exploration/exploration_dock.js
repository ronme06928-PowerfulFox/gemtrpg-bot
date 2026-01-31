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

        // 1. 戦闘へ戻るボタン (GMのみ)
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

        // 2. 背景設定ボタン (GMのみ)
        if (userAttr === 'GM') {
            const bgBtn = createDockIcon('🖼️', '背景変更', openExplorationBgPicker);
            // bgBtn.style.background = '#e74c3c';
            dock.appendChild(bgBtn);
        }

        // 3. 探索判定ボタン
        const rollBtn = createDockIcon('🎲', '探索判定', openExplorationRollModal);
        dock.appendChild(rollBtn);

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
                <div class="modal-content" style="width:400px; padding:20px;">
                    <h3>🎲 探索判定</h3>
                    <div style="margin-bottom:15px;">
                        <label>キャラクター:</label>
                        <select id="exp-roll-char-select" style="width:100%; padding:5px;"></select>
                    </div>
                    <div style="margin-bottom:15px;">
                        <label>技能:</label>
                        <select id="exp-roll-skill-select" style="width:100%; padding:5px;">
                            ${EXPLORATION_PARAMS.map(p => `<option value="${p}">${p}</option>`).join('')}
                        </select>
                    </div>
                    <div style="margin-bottom:15px; display:flex; gap:10px;">
                        <div style="flex:1;">
                            <label>ダイス数:</label>
                            <input type="number" id="exp-roll-dice-count" value="2" min="1" max="10" style="width:100%;">
                        </div>
                        <div style="flex:1;">
                            <label>難易度 (任意):</label>
                            <input type="number" id="exp-roll-difficulty" value="0" min="0" style="width:100%;">
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <button id="exp-roll-cancel" style="margin-right:10px;">キャンセル</button>
                        <button id="exp-roll-execute" style="background:#007bff; color:white; border:none; padding:5px 15px; border-radius:4px;">判定</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = document.getElementById('exp-roll-modal');
        const charSelect = document.getElementById('exp-roll-char-select');

        // キャラクターリスト設定
        if (battleState && battleState.characters) {
            battleState.characters.forEach(c => {
                // 自分のキャラ or GMなら全員
                if (currentUserAttribute === 'GM' || c.owner_id === currentUserId) {
                    const opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = c.name;
                    charSelect.appendChild(opt);
                }
            });
        }

        // イベント
        document.getElementById('exp-roll-cancel').onclick = () => modal.remove();
        document.getElementById('exp-roll-execute').onclick = () => {
            const charId = charSelect.value;
            const skillName = document.getElementById('exp-roll-skill-select').value;
            const diceCount = document.getElementById('exp-roll-dice-count').value;
            const difficulty = document.getElementById('exp-roll-difficulty').value;

            if (!charId) {
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

        // 背景クリックで閉じる
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
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
