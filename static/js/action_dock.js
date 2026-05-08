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
function isPlacedCharacter(char) {
    if (!char) return false;
    const x = Number(char.x);
    const y = Number(char.y);
    return Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0;
}

function isExpiredSummonCharacter(char) {
    if (!char || !char.is_summoned) return false;
    const mode = String(char.summon_duration_mode || '').toLowerCase();
    if (mode !== 'duration_rounds') return false;
    const remaining = Number(char.remaining_summon_rounds);
    return Number.isFinite(remaining) && remaining <= 0;
}

function isSelectableCharacterForQuickEdit(char) {
    if (!char) return false;
    const hp = Number(char.hp || 0);
    if (!Number.isFinite(hp) || hp <= 0) return false;
    if (!isPlacedCharacter(char)) return false;
    if (isExpiredSummonCharacter(char)) return false;
    return true;
}

function isSoundFxEnabled() {
    if (!window.SoundFx || typeof window.SoundFx.getSettings !== 'function') return true;
    const settings = window.SoundFx.getSettings();
    return Boolean(settings && settings.enabled);
}

function refreshSoundDockIcon(icon) {
    if (!icon) return;
    const enabled = isSoundFxEnabled();
    icon.textContent = '♪';
    icon.title = enabled ? 'SE: ON（クリックでOFF）' : 'SE: OFF（クリックでON）';
    if (enabled) {
        icon.classList.add('active');
        icon.classList.remove('disabled');
        icon.style.opacity = '1.0';
    } else {
        icon.classList.remove('active');
        icon.classList.add('disabled');
        icon.style.opacity = '0.5';
    }
}

function toggleSoundFxFromDock(icon) {
    if (!window.SoundFx || typeof window.SoundFx.setEnabled !== 'function') return;
    const enabled = isSoundFxEnabled();
    const nextEnabled = !enabled;
    window.SoundFx.setEnabled(nextEnabled);
    if (typeof window.SoundFx.unlock === 'function') window.SoundFx.unlock();
    if (nextEnabled && typeof window.SoundFx.playDiceRoll === 'function') {
        void window.SoundFx.playDiceRoll({ force: true, bypassThrottle: true });
    }
    refreshSoundDockIcon(icon);
}

function updateActionDock() {
    // ★ Exploration Mode Check
    const mode = battleState ? (battleState.mode || 'battle') : 'unknown';
    const isGMUser = isCurrentUserGM();
    if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
        console.log(`[ActionDock] Update called. Mode: ${mode}`);
    }

    // ★ Unplaced Area (Shared Modal) Update
    // Always update this if it exists, regardless of mode
    const stagingList = document.getElementById('staging-overlay-list');
    if (stagingList) {
        renderStagingOverlayList(stagingList);
    }

    // Force Exploration Dock if mode is exploration
    if (mode === 'exploration') {
        const rStartBtn = document.getElementById('visual-round-start-btn');
        const rEndBtn = document.getElementById('visual-round-end-btn');
        if (rStartBtn) rStartBtn.style.display = 'none';
        if (rEndBtn) rEndBtn.style.display = 'none';

        const dock = document.getElementById('action-dock');

        // Ensure we don't have battle icons
        if (dock && !dock.classList.contains('exploration-mode')) {
            if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
                console.log('[ActionDock] Switching to Exploration Dock (Clearing content)');
            }
            dock.innerHTML = '';
            dock.className = 'action-dock exploration-mode';
        }

        if (window.ExplorationDock && typeof window.ExplorationDock.render === 'function') {
            if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
                console.log('[ActionDock] Rendering ExplorationDock content');
            }
            window.ExplorationDock.render();
        } else {
            // Script might not be loaded yet
            if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
                console.warn('[ActionDock] ExplorationDock not ready, retrying...');
            }
            setTimeout(updateActionDock, 200);
        }
        return; // Always return to prevent Battle Dock rendering
    }

    // Battle Mode Logic
    const rStartBtn = document.getElementById('visual-round-start-btn');
    const rEndBtn = document.getElementById('visual-round-end-btn');
    const isBattleOnlyMode = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
    const canShowRoundButtons = isGMUser && !isBattleOnlyMode;
    if (rStartBtn) rStartBtn.style.display = canShowRoundButtons ? 'inline-block' : 'none';
    if (rEndBtn) rEndBtn.style.display = canShowRoundButtons ? 'inline-block' : 'none';

    // Reset to Battle Dock (if switching back)
    const dock = document.getElementById('action-dock');
    if (dock && dock.classList.contains('exploration-mode')) {
        if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
            console.log('[ActionDock] Switching back to Battle Dock');
        }
        dock.className = 'action-dock';
        dock.innerHTML = `
            <div id="dock-match-icon" class="dock-icon" style="display: none;" title="マッチ実行">⚔️</div>
            <div id="dock-immediate-icon" class="dock-icon disabled" title="即時発動スキル">⚡</div>
            <div id="dock-item-icon" class="dock-icon" title="アイテム使用">🎒</div>
            <div id="dock-quick-edit-icon" class="dock-icon" title="簡易ステータス編集">📝</div>
            <div id="dock-add-char-icon" class="dock-icon" title="キャラクター追加">➕</div>
            <div id="dock-staging-icon" class="dock-icon" title="未配置キャラクター">📦</div>
            <div id="dock-arrow-toggle-icon" class="dock-icon" title="矢印表示切替">🏹</div>
            <div id="dock-glossary-icon" class="dock-icon" title="用語図鑑">📚</div>
            <div id="dock-sound-toggle-icon" class="dock-icon" title="SE切替">♪</div>
        `;
        // Re-initialize listeners
        initializeActionDock();

        // ★ Explorationから戻った場合にラウンドボタン表示を復帰させる
        // GMの場合のみ表示する (setupVisualSidebarControlsのロジックと同様)
        if (canShowRoundButtons) {
            const rStartBtn = document.getElementById('visual-round-start-btn');
            const rEndBtn = document.getElementById('visual-round-end-btn');
            if (rStartBtn) rStartBtn.style.display = 'inline-block';
            if (rEndBtn) rEndBtn.style.display = 'inline-block';
        }
    }

    // ★ Add Switch to Exploration Button for GM (if not exists)
    if (isGMUser && dock) {
        let expBtn = document.getElementById('dock-to-exploration-btn');
        if (!expBtn) {
            expBtn = document.createElement('div');
            expBtn.id = 'dock-to-exploration-btn';
            expBtn.className = 'dock-icon dock-icon--exploration';
            expBtn.textContent = '🗺️';
            expBtn.title = '探索パートへ切替';
            expBtn.onclick = async () => {
                if (await window.showAppConfirm('探索パートへ切り替えますか？', {
                    title: '探索パートへ切替',
                    confirmText: '切り替え',
                })) {
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
            body.innerHTML = '<div class="qe-empty-notice">あなたのキャラクターがいません</div>';
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

function logDockMissingElement(message) {
    if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
        console.warn(message);
    }
}

function isCurrentUserGM() {
    const attr = (typeof currentUserAttribute !== 'undefined')
        ? currentUserAttribute
        : (typeof window !== 'undefined' ? window.currentUserAttribute : null);
    const role = (typeof window !== 'undefined') ? window.currentUserRole : null;
    const user = (typeof currentUsername !== 'undefined')
        ? currentUsername
        : (typeof window !== 'undefined' ? (window.currentUsername || window.currentUserName) : '');
    const attrNorm = String(attr || '').trim().toUpperCase();
    const roleNorm = String(role || '').trim().toUpperCase();
    return attrNorm === 'GM' || roleNorm === 'GM' || (typeof user === 'string' && /\(GM\)/i.test(user));
}

function openGlossaryCatalogModal() {
    const existing = document.getElementById('glossary-catalog-backdrop');
    if (existing) {
        existing.style.display = (existing.style.display === 'none') ? 'flex' : 'none';
        if (existing.style.display === 'flex') {
            if (typeof existing._refreshGlossaryCatalog === 'function') {
                existing._refreshGlossaryCatalog();
            }
            const searchInput = existing.querySelector('#glossary-catalog-search');
            if (searchInput) searchInput.focus();
        }
        return;
    }

    const backdrop = document.createElement('div');
    backdrop.id = 'glossary-catalog-backdrop';
    backdrop.className = 'glossary-catalog-backdrop';
    backdrop.style.display = 'flex';

    const panel = document.createElement('div');
    panel.className = 'glossary-catalog-modal';
    panel.innerHTML = `
        <div class="glossary-catalog-header">
            <h3>用語図鑑</h3>
            <button type="button" class="glossary-catalog-close" aria-label="閉じる">×</button>
        </div>
        <div class="glossary-catalog-controls">
            <input id="glossary-catalog-search" type="text" placeholder="キーワード検索（ID・名称・説明）">
            <select id="glossary-catalog-category">
                <option value="all">全カテゴリ</option>
            </select>
            <select id="glossary-catalog-sort">
                <option value="sort_order">表示順</option>
                <option value="category">カテゴリ順</option>
                <option value="name">名称順</option>
                <option value="id" selected>ID順</option>
            </select>
        </div>
        <div class="glossary-catalog-status">
            <span id="glossary-catalog-count">読み込み中...</span>
        </div>
        <div id="glossary-catalog-list" class="glossary-catalog-list"></div>
    `;

    backdrop.appendChild(panel);
    document.body.appendChild(backdrop);

    const closeBtn = panel.querySelector('.glossary-catalog-close');
    const searchInput = panel.querySelector('#glossary-catalog-search');
    const categorySelect = panel.querySelector('#glossary-catalog-category');
    const sortSelect = panel.querySelector('#glossary-catalog-sort');
    const countEl = panel.querySelector('#glossary-catalog-count');
    const listEl = panel.querySelector('#glossary-catalog-list');

    const close = () => {
        backdrop.style.display = 'none';
    };
    if (closeBtn) closeBtn.onclick = close;
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) close();
    });

    function normalizeText(value) {
        return String(value ?? '').trim();
    }

    function escapeHtml(value) {
        const base = String(value ?? '');
        return base
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function parseCsvOrArray(value) {
        if (Array.isArray(value)) {
            return value.map((v) => normalizeText(v)).filter(Boolean);
        }
        return normalizeText(value)
            .split(',')
            .map((v) => normalizeText(v))
            .filter(Boolean);
    }

    function isEnabledTerm(term) {
        if (!term || typeof term !== 'object') return true;
        const raw = term.is_enabled;
        if (raw === undefined || raw === null || raw === '') return true;
        const v = normalizeText(raw).toLowerCase();
        return !(v === 'false' || v === '0' || v === 'off' || v === 'no' || v === 'disabled');
    }

    function toNum(value, fallback = 999999) {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    function resolveCategory(term) {
        const category = normalizeText(term?.category);
        return category || '未分類';
    }

    function resolveLabel(termId, term) {
        const label = normalizeText(term?.display_name || term?.name);
        return label || termId;
    }

    function toTermEntries(termsRaw) {
        const terms = (termsRaw && typeof termsRaw === 'object') ? termsRaw : {};
        return Object.keys(terms).map((termId) => {
            const term = terms[termId] || {};
            const label = resolveLabel(termId, term);
            const shortText = normalizeText(term.short || term.summary || term.short_desc);
            const longText = normalizeText(term.long || term.description || term.detail);
            const synonyms = parseCsvOrArray(term.synonyms);
            const links = parseCsvOrArray(term.links);
            const category = resolveCategory(term);
            const searchBlob = [
                termId,
                label,
                category,
                shortText,
                longText,
                synonyms.join(' '),
                links.join(' ')
            ].join(' ').toLowerCase();

            return {
                id: termId,
                label,
                category,
                shortText,
                longText,
                sortOrder: toNum(term.sort_order, 999999),
                enabled: isEnabledTerm(term),
                searchBlob
            };
        }).filter((entry) => entry.enabled);
    }

    function compareTextJa(a, b) {
        return String(a).localeCompare(String(b), 'ja');
    }

    function renderCategoryOptions(entries) {
        const current = categorySelect ? String(categorySelect.value || 'all') : 'all';
        const categories = Array.from(new Set(entries.map((entry) => entry.category))).sort(compareTextJa);
        if (categorySelect) {
            categorySelect.innerHTML = `<option value="all">全カテゴリ</option>${categories.map((cat) => `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`).join('')}`;
            if (categories.includes(current)) {
                categorySelect.value = current;
            } else {
                categorySelect.value = 'all';
            }
        }
    }

    let entries = [];
    function getVisibleEntries() {
        const query = normalizeText(searchInput?.value).toLowerCase();
        const category = normalizeText(categorySelect?.value || 'all');
        const sortMode = normalizeText(sortSelect?.value || 'id');

        let rows = entries.slice();
        if (category && category !== 'all') {
            rows = rows.filter((entry) => String(entry.category) === category);
        }
        if (query) {
            rows = rows.filter((entry) => entry.searchBlob.includes(query));
        }

        rows.sort((a, b) => {
            if (sortMode === 'name') {
                const byName = compareTextJa(a.label, b.label);
                return byName !== 0 ? byName : compareTextJa(a.id, b.id);
            }
            if (sortMode === 'id') {
                return compareTextJa(a.id, b.id);
            }
            if (sortMode === 'category') {
                const byCategory = compareTextJa(a.category, b.category);
                if (byCategory !== 0) return byCategory;
                if (a.sortOrder !== b.sortOrder) return a.sortOrder - b.sortOrder;
                const byName = compareTextJa(a.label, b.label);
                return byName !== 0 ? byName : compareTextJa(a.id, b.id);
            }
            if (a.sortOrder !== b.sortOrder) return a.sortOrder - b.sortOrder;
            const byName = compareTextJa(a.label, b.label);
            return byName !== 0 ? byName : compareTextJa(a.id, b.id);
        });

        return rows;
    }

    function renderList() {
        if (!listEl || !countEl) return;
        const visible = getVisibleEntries();
        countEl.textContent = `${visible.length} / ${entries.length} 件`;
        listEl.innerHTML = '';

        if (visible.length === 0) {
            listEl.innerHTML = '<div class="glossary-catalog-empty">該当する用語がありません。</div>';
            return;
        }

        visible.forEach((entry) => {
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'glossary-catalog-item';
            row.setAttribute('data-term-id', entry.id);

            const summary = entry.shortText || entry.longText || '説明未登録';
            row.innerHTML = `
                <div class="glossary-catalog-item-top">
                    <span class="glossary-catalog-item-name">${escapeHtml(entry.label)}</span>
                    <span class="glossary-catalog-item-id">${escapeHtml(entry.id)}</span>
                </div>
                <div class="glossary-catalog-item-meta">${escapeHtml(entry.category)}</div>
                <div class="glossary-catalog-item-summary">${escapeHtml(summary)}</div>
            `;

            row.addEventListener('click', () => {
                if (window.Glossary && typeof window.Glossary.showPopup === 'function') {
                    window.Glossary.showPopup(entry.id);
                }
            });

            listEl.appendChild(row);
        });
    }

    function renderLoading(text) {
        if (countEl) countEl.textContent = text || '読み込み中...';
        if (listEl) listEl.innerHTML = '<div class="glossary-catalog-empty">読み込み中...</div>';
    }

    function renderError(text) {
        if (countEl) countEl.textContent = '0 / 0 件';
        if (listEl) listEl.innerHTML = `<div class="glossary-catalog-empty">${escapeHtml(text || '読み込みに失敗しました。')}</div>`;
    }

    function refreshCatalog() {
        if (!window.Glossary || typeof window.Glossary.ensureDataLoaded !== 'function') {
            renderError('Glossary API が利用できません。');
            return;
        }

        renderLoading('読み込み中...');
        window.Glossary.ensureDataLoaded()
            .then((terms) => {
                entries = toTermEntries(terms || window.glossaryData || {});
                renderCategoryOptions(entries);
                renderList();
            })
            .catch((err) => {
                console.warn('[GlossaryCatalog] data load failed:', err);
                entries = [];
                renderError('用語データの読み込みに失敗しました。');
            });
    }

    if (searchInput) {
        searchInput.addEventListener('input', () => renderList());
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') close();
        });
    }
    if (categorySelect) categorySelect.addEventListener('change', () => renderList());
    if (sortSelect) sortSelect.addEventListener('change', () => renderList());

    backdrop._refreshGlossaryCatalog = refreshCatalog;
    refreshCatalog();
    if (searchInput) searchInput.focus();
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

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content qe-modal-content';

    modalContent.innerHTML += `
        <div class="modal-header qe-modal-header">
            <div class="qe-modal-header-left">
                <span class="qe-modal-icon">📝</span>
                <div>
                    <h3 class="qe-modal-title">簡易ステータス編集</h3>
                    <div class="qe-modal-subtitle">Combat Status Quick Editor</div>
                </div>
            </div>
            <button class="window-control-btn close-btn qe-close-btn">×</button>
        </div>
        <div class="modal-body qe-modal-body">
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


    const listContainer = document.getElementById('quick-edit-list');
    renderQuickEditList(listContainer);
    ensureQuickEditItemData().then(() => {
        const latestList = document.getElementById('quick-edit-list');
        if (latestList) renderQuickEditList(latestList);
    });
}

function getQuickEditBuffCatalog() {
    const catalog = (typeof window !== 'undefined' && window.buffCatalogData && typeof window.buffCatalogData === 'object')
        ? window.buffCatalogData
        : {};

    return Object.values(catalog)
        .filter((entry) => entry && typeof entry === 'object' && String(entry.id || '').trim())
        .sort((a, b) => {
            const idCompare = String(a.id || '').localeCompare(String(b.id || ''));
            if (idCompare !== 0) return idCompare;
            return String(a.display_name || a.name || '').localeCompare(String(b.display_name || b.name || ''));
        });
}

function getQuickEditBuffEntry(buffId) {
    const normalized = String(buffId || '').trim();
    if (!normalized) return null;
    const catalog = (typeof window !== 'undefined' && window.buffCatalogData && typeof window.buffCatalogData === 'object')
        ? window.buffCatalogData
        : {};
    return catalog[normalized] || null;
}

function formatQuickEditSignedValue(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return String(value || '');
    return num > 0 ? `+${num}` : String(num);
}

function describeQuickEditBuffEffect(entry) {
    if (!entry || typeof entry !== 'object') return '効果情報なし';
    const effect = entry.effect;
    if (!effect || typeof effect !== 'object') return '効果情報なし';

    const parts = [];
    if (effect.type === 'plugin') {
        if (effect.name) parts.push(`plugin:${effect.name}`);
        if (effect.category) parts.push(effect.category);
    }
    if (effect.type === 'stat_mod') {
        parts.push(`${effect.stat || 'parameter'} ${formatQuickEditSignedValue(effect.value)}`);
    }
    if (effect.stat && effect.value !== undefined && effect.type !== 'stat_mod') {
        parts.push(`${effect.stat} ${formatQuickEditSignedValue(effect.value)}`);
    }
    if (effect.damage_multiplier !== undefined) parts.push(`被ダメ倍率 ${effect.damage_multiplier}`);
    if (effect.incoming_damage_multiplier !== undefined) parts.push(`被ダメ補正 ${effect.incoming_damage_multiplier}`);
    if (effect.outgoing_damage_multiplier !== undefined) parts.push(`与ダメ補正 ${effect.outgoing_damage_multiplier}`);

    if (!parts.length) {
        const keys = Object.keys(effect);
        if (!keys.length) return '効果情報なし';
        parts.push(keys.join(', '));
    }
    return parts.join(' / ');
}

function describeQuickEditBuffTiming(lasting, delay, count) {
    const parts = [];
    if (Number.isFinite(lasting)) parts.push(lasting < 0 ? '継続: 永続/特殊' : `継続: ${lasting}R`);
    if (Number.isFinite(delay)) parts.push(delay <= 0 ? '発動: 即時' : `発動: ${delay}R後`);
    if (Number.isFinite(count) && count !== 0) parts.push(`スタック: ${count}`);
    return parts.join(' / ');
}

function formatQuickEditActiveBuffLabel(buff) {
    const entryData = (buff && buff.data && typeof buff.data === 'object') ? buff.data : {};
    const buffId = String((buff && buff.buff_id) || entryData.buff_id || '').trim();
    const name = String((buff && (buff.display_name || buff.name)) || '').trim() || buffId || '名称未設定';
    const lasting = Number.parseInt(buff && (buff.lasting ?? buff.round ?? buff.duration), 10);
    const delay = Number.parseInt(buff && buff.delay, 10);
    const count = Number.parseInt((buff && buff.count) ?? entryData.count, 10);
    const timing = describeQuickEditBuffTiming(lasting, delay, count);
    return timing ? `${name} [${buffId}] (${timing})` : `${name} [${buffId}]`;
}

async function ensureQuickEditItemData() {
    if (typeof window === 'undefined') return {};
    if (window.quickEditItemData && typeof window.quickEditItemData === 'object') {
        return window.quickEditItemData;
    }
    if (window.quickEditItemDataPromise) {
        return window.quickEditItemDataPromise;
    }

    window.quickEditItemDataPromise = fetch('/api/get_item_data')
        .then((res) => res.ok ? res.json() : {})
        .then((data) => {
            window.quickEditItemData = (data && typeof data === 'object') ? data : {};
            return window.quickEditItemData;
        })
        .catch(() => {
            window.quickEditItemData = {};
            return window.quickEditItemData;
        })
        .finally(() => {
            window.quickEditItemDataPromise = null;
        });

    return window.quickEditItemDataPromise;
}

function getQuickEditItemCatalog() {
    const catalog = (typeof window !== 'undefined' && window.quickEditItemData && typeof window.quickEditItemData === 'object')
        ? window.quickEditItemData
        : {};

    return Object.values(catalog)
        .filter((entry) => entry && typeof entry === 'object' && String(entry.id || '').trim())
        .sort((a, b) => {
            const idCompare = String(a.id || '').localeCompare(String(b.id || ''));
            if (idCompare !== 0) return idCompare;
            return String(a.name || a.id).localeCompare(String(b.name || b.id));
        });
}

function getQuickEditItemEntry(itemId) {
    const normalized = String(itemId || '').trim();
    if (!normalized) return null;
    const catalog = (typeof window !== 'undefined' && window.quickEditItemData && typeof window.quickEditItemData === 'object')
        ? window.quickEditItemData
        : {};
    return catalog[normalized] || null;
}

function getQuickEditStateCatalog() {
    return [
        { id: '出血', name: '出血', description: 'スタック値をそのまま加算します。' },
        { id: '破裂', name: '破裂', description: 'スタック値をそのまま加算します。' },
        { id: '亀裂', name: '亀裂', description: '通常はスタック加算。継続Rを指定すると亀裂ラウンド管理として付与します。' },
        { id: '戦慄', name: '戦慄', description: 'スタック値をそのまま加算します。' },
        { id: '荊棘', name: '荊棘', description: 'スタック値をそのまま加算します。' },
    ];
}

function renderQuickEditList(container) {
    if (!battleState || !battleState.characters) return;
    container.innerHTML = '';
    const isGMView = isCurrentUserGM();

    // First limit to eligible field characters, then apply ownership rules.
    const targetChars = battleState.characters.filter(c => {
        if (!isSelectableCharacterForQuickEdit(c)) return false;
        if (isGMView) return true;
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
            initial.classList.add('qe-icon-placeholder');
            initial.style.background = char.color || '#ccc';
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

        // Append base sections
        row.appendChild(iconDiv);
        row.appendChild(nameDiv);
        row.appendChild(statsDiv);
        row.appendChild(btnDiv);

        if (isGMView) {
            const gmToggle = document.createElement('details');
            gmToggle.className = 'qe-gm-toggle';

            const gmSummary = document.createElement('summary');
            gmSummary.className = 'qe-gm-summary';
            gmSummary.textContent = 'GM Buff / Item Control';
            gmToggle.appendChild(gmSummary);

            const gmPanel = document.createElement('div');
            gmPanel.className = 'qe-gm-panel';

            const createField = (labelText, control) => {
                const field = document.createElement('div');
                field.className = 'qe-gm-field';
                const label = document.createElement('label');
                label.textContent = labelText;
                field.appendChild(label);
                field.appendChild(control);
                return field;
            };

            const renderPreview = (target, options) => {
                const { title, buffId, description, meta } = options || {};
                if (!buffId) {
                    target.classList.add('is-empty');
                    target.innerHTML = '選択したバフの名称と効果がここに表示されます。';
                    return;
                }
                target.classList.remove('is-empty');
                target.innerHTML = `
                    <div class="qe-gm-preview-head">
                        <span class="qe-gm-preview-name">${title || buffId}</span>
                        <span class="qe-gm-preview-id">${buffId}</span>
                    </div>
                    ${meta ? `<div class="qe-gm-preview-meta">${meta}</div>` : ''}
                    <div class="qe-gm-preview-desc">${description || '効果情報なし'}</div>
                `;
            };

            const applySectionTitle = document.createElement('div');
            applySectionTitle.className = 'qe-gm-section-title';
            applySectionTitle.textContent = '付与';
            gmPanel.appendChild(applySectionTitle);

            const applyRow = document.createElement('div');
            applyRow.className = 'qe-gm-row';
            const applyBuffSelect = document.createElement('select');
            const applyDefault = document.createElement('option');
            applyDefault.value = '';
            applyDefault.textContent = '付与するバフを選択';
            applyBuffSelect.appendChild(applyDefault);
            getQuickEditBuffCatalog().forEach((entry) => {
                const option = document.createElement('option');
                option.value = entry.id;
                option.textContent = `${entry.id} - ${String(entry.display_name || entry.name || entry.id).trim()}`;
                applyBuffSelect.appendChild(option);
            });
            const applyLastingInput = document.createElement('input');
            applyLastingInput.type = 'number';
            applyLastingInput.value = '1';
            applyLastingInput.placeholder = '継続R';
            const applyDelayInput = document.createElement('input');
            applyDelayInput.type = 'number';
            applyDelayInput.value = '0';
            applyDelayInput.placeholder = 'ディレイ';
            const applyCountInput = document.createElement('input');
            applyCountInput.type = 'number';
            applyCountInput.placeholder = 'スタック';
            const applyValueInput = document.createElement('input');
            applyValueInput.type = 'number';
            applyValueInput.placeholder = 'Value(任意)';
            const applyBtn = document.createElement('button');
            applyBtn.className = 'btn-primary';
            applyBtn.textContent = '付与';
            applyRow.appendChild(createField('バフ', applyBuffSelect));
            applyRow.appendChild(createField('継続R', applyLastingInput));
            applyRow.appendChild(createField('ディレイ', applyDelayInput));
            applyRow.appendChild(createField('スタック', applyCountInput));
            gmPanel.appendChild(applyRow);

            const applyExtraRow = document.createElement('div');
            applyExtraRow.className = 'qe-gm-row items';
            applyExtraRow.appendChild(createField('Value', applyValueInput));
            const applyExtraSpacer = document.createElement('div');
            applyExtraRow.appendChild(applyExtraSpacer);
            applyExtraRow.appendChild(applyBtn);
            gmPanel.appendChild(applyExtraRow);

            const applyPreview = document.createElement('div');
            applyPreview.className = 'qe-gm-preview is-empty';
            gmPanel.appendChild(applyPreview);

            const stateSectionTitle = document.createElement('div');
            stateSectionTitle.className = 'qe-gm-section-title';
            stateSectionTitle.textContent = '状態異常付与';
            gmPanel.appendChild(stateSectionTitle);

            const stateRow = document.createElement('div');
            stateRow.className = 'qe-gm-row state';
            const stateSelect = document.createElement('select');
            const stateDefault = document.createElement('option');
            stateDefault.value = '';
            stateDefault.textContent = '付与する状態異常を選択';
            stateSelect.appendChild(stateDefault);
            getQuickEditStateCatalog().forEach((entry) => {
                const option = document.createElement('option');
                option.value = entry.id;
                option.textContent = entry.name;
                stateSelect.appendChild(option);
            });
            const stateAmountInput = document.createElement('input');
            stateAmountInput.type = 'number';
            stateAmountInput.value = '1';
            stateAmountInput.placeholder = 'スタック';
            const stateRoundsInput = document.createElement('input');
            stateRoundsInput.type = 'number';
            stateRoundsInput.placeholder = '亀裂のみ継続R';
            const stateBtn = document.createElement('button');
            stateBtn.className = 'btn-secondary';
            stateBtn.textContent = '付与';
            stateRow.appendChild(createField('状態異常', stateSelect));
            stateRow.appendChild(createField('スタック', stateAmountInput));
            stateRow.appendChild(createField('継続R', stateRoundsInput));
            stateRow.appendChild(stateBtn);
            gmPanel.appendChild(stateRow);

            const statePreview = document.createElement('div');
            statePreview.className = 'qe-gm-preview is-empty';
            gmPanel.appendChild(statePreview);

            const removeSectionTitle = document.createElement('div');
            removeSectionTitle.className = 'qe-gm-section-title';
            removeSectionTitle.textContent = '解除';
            gmPanel.appendChild(removeSectionTitle);

            const removeRow = document.createElement('div');
            removeRow.className = 'qe-gm-row';
            const removeSelect = document.createElement('select');
            const removeDefault = document.createElement('option');
            removeDefault.value = '';
            removeDefault.textContent = '解除するバフを選択';
            removeSelect.appendChild(removeDefault);
            const buffEntries = Array.isArray(char.special_buffs)
                ? char.special_buffs.filter((b) => b && typeof b === 'object')
                : [];
            buffEntries.forEach((buff, idx) => {
                const option = document.createElement('option');
                option.value = String(idx);
                option.textContent = formatQuickEditActiveBuffLabel(buff);
                removeSelect.appendChild(option);
            });
            const removeSpacer1 = document.createElement('input');
            removeSpacer1.disabled = true;
            removeSpacer1.style.visibility = 'hidden';
            const removeSpacer2 = document.createElement('input');
            removeSpacer2.disabled = true;
            removeSpacer2.style.visibility = 'hidden';
            const removeSpacer3 = document.createElement('input');
            removeSpacer3.disabled = true;
            removeSpacer3.style.visibility = 'hidden';
            const removeBtn = document.createElement('button');
            removeBtn.className = 'btn-danger';
            removeBtn.textContent = '解除';
            if (buffEntries.length === 0) {
                removeSelect.disabled = true;
                removeBtn.disabled = true;
            }
            removeRow.appendChild(createField('付与中のバフ', removeSelect));
            removeRow.appendChild(removeSpacer1);
            removeRow.appendChild(removeSpacer2);
            removeRow.appendChild(removeSpacer3);
            removeRow.appendChild(removeBtn);
            gmPanel.appendChild(removeRow);

            const removePreview = document.createElement('div');
            removePreview.className = 'qe-gm-preview is-empty';
            gmPanel.appendChild(removePreview);

            const itemSectionTitle = document.createElement('div');
            itemSectionTitle.className = 'qe-gm-section-title';
            itemSectionTitle.textContent = 'アイテム増減';
            gmPanel.appendChild(itemSectionTitle);

            const itemRow = document.createElement('div');
            itemRow.className = 'qe-gm-row items';
            const itemSelect = document.createElement('select');
            const itemDefault = document.createElement('option');
            itemDefault.value = '';
            itemDefault.textContent = '増減するアイテムを選択';
            itemSelect.appendChild(itemDefault);
            getQuickEditItemCatalog().forEach((entry) => {
                const option = document.createElement('option');
                option.value = entry.id;
                option.textContent = `${entry.id} - ${String(entry.name || entry.id).trim()}`;
                itemSelect.appendChild(option);
            });
            const itemDeltaInput = document.createElement('input');
            itemDeltaInput.type = 'number';
            itemDeltaInput.value = '1';
            itemDeltaInput.placeholder = 'delta (+/-)';
            const itemBtn = document.createElement('button');
            itemBtn.className = 'btn-ghost';
            itemBtn.textContent = 'アイテム増減';
            itemRow.appendChild(createField('アイテム', itemSelect));
            itemRow.appendChild(createField('増減数', itemDeltaInput));
            itemRow.appendChild(itemBtn);
            gmPanel.appendChild(itemRow);

            const itemPreview = document.createElement('div');
            itemPreview.className = 'qe-gm-preview is-empty';
            gmPanel.appendChild(itemPreview);

            const note = document.createElement('div');
            note.className = 'qe-gm-note';
            note.textContent = '送信先: GM専用API';
            gmPanel.appendChild(note);

            const getSocket = () => window.socket || (typeof socket !== 'undefined' ? socket : null);
            let applyValuesAutoFilled = true;

            const syncApplyPreview = () => {
                const buffId = String(applyBuffSelect.value || '').trim();
                const entry = getQuickEditBuffEntry(buffId);
                if (!entry) {
                    renderPreview(applyPreview, null);
                    return;
                }
                const defaultDuration = Number.parseInt(entry.default_duration, 10);
                const timingText = describeQuickEditBuffTiming(
                    Number.parseInt(applyLastingInput.value, 10),
                    Number.parseInt(applyDelayInput.value, 10),
                    Number.parseInt(applyCountInput.value, 10)
                );
                const metaParts = [];
                if (Number.isFinite(defaultDuration)) {
                    metaParts.push(defaultDuration < 0 ? '既定継続: 永続/特殊' : `既定継続: ${defaultDuration}R`);
                }
                const effectSummary = describeQuickEditBuffEffect(entry);
                if (timingText) metaParts.push(`今回の設定: ${timingText}`);
                if (effectSummary) metaParts.push(`要約: ${effectSummary}`);
                renderPreview(applyPreview, {
                    title: String(entry.display_name || entry.name || entry.id).trim(),
                    buffId: entry.id,
                    description: String(entry.description || '').trim(),
                    meta: metaParts.join(' / ')
                });
            };

            const syncRemovePreview = () => {
                const idx = Number.parseInt(removeSelect.value, 10);
                if (!Number.isFinite(idx) || idx < 0 || idx >= buffEntries.length) {
                    renderPreview(removePreview, null);
                    return;
                }
                const buff = buffEntries[idx];
                const entryData = (buff.data && typeof buff.data === 'object') ? buff.data : {};
                const buffId = String(buff.buff_id || entryData.buff_id || '').trim();
                const catalogEntry = getQuickEditBuffEntry(buffId);
                const title = String(
                    buff.display_name
                    || buff.name
                    || (catalogEntry && (catalogEntry.display_name || catalogEntry.name))
                    || buffId
                ).trim();
                renderPreview(removePreview, {
                    title,
                    buffId,
                    description: String((catalogEntry && catalogEntry.description) || buff.description || '').trim(),
                    meta: describeQuickEditBuffTiming(
                        Number.parseInt(buff.lasting ?? buff.round ?? buff.duration, 10),
                        Number.parseInt(buff.delay, 10),
                        Number.parseInt(buff.count ?? entryData.count, 10)
                    ) || '解除対象'
                });
            };

            const syncItemPreview = () => {
                const itemId = String(itemSelect.value || '').trim();
                const entry = getQuickEditItemEntry(itemId);
                if (!entry) {
                    renderPreview(itemPreview, null);
                    return;
                }
                const inventory = (char && char.inventory && typeof char.inventory === 'object') ? char.inventory : {};
                const owned = Number.parseInt(inventory[itemId], 10);
                const deltaVal = Number.parseInt(itemDeltaInput.value, 10);
                const metaParts = [];
                if (Number.isFinite(owned)) metaParts.push(`所持数: ${owned}`);
                if (Number.isFinite(deltaVal) && deltaVal !== 0) metaParts.push(`今回の増減: ${deltaVal > 0 ? '+' : ''}${deltaVal}`);
                if (entry.usable === false) metaParts.push('使用不可アイテム');
                renderPreview(itemPreview, {
                    title: String(entry.name || entry.id).trim(),
                    buffId: entry.id,
                    description: String(entry.description || '').trim(),
                    meta: metaParts.join(' / ')
                });
            };

            const syncStatePreview = () => {
                const stateId = String(stateSelect.value || '').trim();
                const entry = getQuickEditStateCatalog().find((row) => row.id === stateId);
                if (!entry) {
                    renderPreview(statePreview, null);
                    return;
                }
                const stateRow = Array.isArray(char.states)
                    ? char.states.find((row) => row && row.name === stateId)
                    : null;
                const currentVal = Number.parseInt(stateRow ? stateRow.value : 0, 10);
                const amountVal = Number.parseInt(stateAmountInput.value, 10);
                const roundsVal = Number.parseInt(stateRoundsInput.value, 10);
                const metaParts = [];
                if (Number.isFinite(currentVal)) metaParts.push(`現在値: ${currentVal}`);
                if (Number.isFinite(amountVal) && amountVal !== 0) metaParts.push(`今回の付与: +${amountVal}`);
                if (stateId === '亀裂') {
                    metaParts.push(Number.isFinite(roundsVal) && roundsVal > 0 ? `継続: ${roundsVal}R` : '継続: 未指定(通常加算)');
                }
                renderPreview(statePreview, {
                    title: entry.name,
                    buffId: entry.id,
                    description: entry.description,
                    meta: metaParts.join(' / ')
                });
            };

            applyBuffSelect.addEventListener('change', () => {
                const selected = getQuickEditBuffEntry(applyBuffSelect.value);
                if (selected && applyValuesAutoFilled) {
                    const defaultDuration = Number.parseInt(selected.default_duration, 10);
                    applyLastingInput.value = Number.isFinite(defaultDuration) ? String(defaultDuration) : '1';
                    applyDelayInput.value = '0';
                    applyCountInput.value = '';
                }
                syncApplyPreview();
            });
            [applyLastingInput, applyDelayInput, applyCountInput].forEach((input) => {
                input.addEventListener('input', () => {
                    applyValuesAutoFilled = false;
                    syncApplyPreview();
                });
            });
            applyValueInput.addEventListener('input', syncApplyPreview);
            removeSelect.addEventListener('change', syncRemovePreview);
            itemSelect.addEventListener('change', syncItemPreview);
            itemDeltaInput.addEventListener('input', syncItemPreview);
            stateSelect.addEventListener('change', syncStatePreview);
            stateAmountInput.addEventListener('input', syncStatePreview);
            stateRoundsInput.addEventListener('input', syncStatePreview);

            syncApplyPreview();
            syncRemovePreview();
            syncItemPreview();
            syncStatePreview();

            applyBtn.onclick = () => {
                const socketToUse = getSocket();
                if (!socketToUse) {
                    alert('Socket not found');
                    return;
                }
                const rawBuff = String(applyBuffSelect.value || '').trim();
                if (!rawBuff) {
                    alert('付与するバフを選択してください');
                    return;
                }
                const lastingVal = parseInt(applyLastingInput.value, 10);
                const delayVal = parseInt(applyDelayInput.value, 10);
                const payload = {
                    room: currentRoomName,
                    target_id: char.id,
                    buff_id: rawBuff,
                    lasting: Number.isFinite(lastingVal) ? lastingVal : 1,
                    delay: Number.isFinite(delayVal) ? delayVal : 0,
                };
                const countRaw = String(applyCountInput.value || '').trim();
                if (countRaw !== '') {
                    const countVal = parseInt(countRaw, 10);
                    if (Number.isFinite(countVal)) payload.count = countVal;
                }
                const valueRaw = String(applyValueInput.value || '').trim();
                if (valueRaw !== '') {
                    const valueVal = parseInt(valueRaw, 10);
                    if (Number.isFinite(valueVal)) {
                        payload.data = Object.assign({}, payload.data || {}, { value: valueVal });
                    }
                }
                socketToUse.emit('request_gm_apply_buff', payload);
                note.textContent = `送信: バフ付与 (${rawBuff})`;
            };

            stateBtn.onclick = () => {
                const socketToUse = getSocket();
                if (!socketToUse) {
                    alert('Socket not found');
                    return;
                }
                const stateName = String(stateSelect.value || '').trim();
                const amountVal = parseInt(stateAmountInput.value, 10);
                const roundsVal = parseInt(stateRoundsInput.value, 10);
                if (!stateName) {
                    alert('付与する状態異常を選択してください');
                    return;
                }
                if (!Number.isFinite(amountVal) || amountVal <= 0) {
                    alert('スタックは 1 以上の整数で指定してください');
                    return;
                }
                const payload = {
                    room: currentRoomName,
                    target_id: char.id,
                    state_name: stateName,
                    amount: amountVal,
                };
                if (stateName === '亀裂' && Number.isFinite(roundsVal) && roundsVal > 0) {
                    payload.rounds = roundsVal;
                }
                socketToUse.emit('request_gm_apply_state', payload);
                note.textContent = `送信: 状態異常付与 (${stateName}, ${amountVal}${payload.rounds ? `, ${payload.rounds}R` : ''})`;
            };

            removeBtn.onclick = () => {
                const socketToUse = getSocket();
                if (!socketToUse) {
                    alert('Socket not found');
                    return;
                }
                const idx = parseInt(removeSelect.value, 10);
                if (!Number.isFinite(idx) || idx < 0 || idx >= buffEntries.length) {
                    alert('解除するバフを選択してください');
                    return;
                }
                const buff = buffEntries[idx];
                const entryData = (buff.data && typeof buff.data === 'object') ? buff.data : {};
                const payload = {
                    room: currentRoomName,
                    target_id: char.id,
                };
                const resolvedBuffId = buff.buff_id || entryData.buff_id || '';
                if (!resolvedBuffId) {
                    alert('このバフは buff_id が不明なため解除できません');
                    return;
                }
                payload.buff_id = resolvedBuffId;
                socketToUse.emit('request_gm_remove_buff', payload);
                note.textContent = `送信: バフ解除 (${buff.name || payload.buff_id || 'unknown'})`;
            };

            itemBtn.onclick = () => {
                const socketToUse = getSocket();
                if (!socketToUse) {
                    alert('Socket not found');
                    return;
                }
                const itemId = String(itemSelect.value || '').trim();
                const deltaVal = parseInt(itemDeltaInput.value, 10);
                if (!itemId) {
                    alert('増減するアイテムを選択してください');
                    return;
                }
                if (!Number.isFinite(deltaVal) || deltaVal === 0) {
                    alert('delta は 0 以外の整数で指定してください');
                    return;
                }
                socketToUse.emit('request_gm_adjust_item', {
                    room: currentRoomName,
                    target_id: char.id,
                    item_id: itemId,
                    delta: deltaVal,
                });
                note.textContent = `送信: アイテム増減 (${itemId}, ${deltaVal})`;
            };

            gmToggle.appendChild(gmPanel);
            row.appendChild(gmToggle);
        }

        container.appendChild(row);
    });
}

// アクションドックの初期化（イベントリスナー設定のみ）
function initializeActionDock() {
    // If in Exploration Mode, do NOT initialize battle dock listeners.
    if (battleState && battleState.mode === 'exploration') {
        if (typeof window !== 'undefined' && window.BATTLE_DEBUG_VERBOSE) {
            console.log('[InitializeActionDock] Skipping Battle Dock init due to Exploration Mode.');
        }
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
    const glossaryIcon = document.getElementById('dock-glossary-icon');
    const soundToggleIcon = document.getElementById('dock-sound-toggle-icon');


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
        logDockMissingElement('dock-immediate-icon not found in DOM');
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
        logDockMissingElement('dock-add-char-icon not found in DOM');
    }

    if (stagingIcon) {
        stagingIcon.onclick = function (e) {

            toggleStagingAreaOverlay();
        };

    } else {
        logDockMissingElement('dock-staging-icon not found in DOM');
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
        logDockMissingElement('dock-match-icon not found in DOM');
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
        logDockMissingElement('dock-item-icon not found in DOM');
    }

    if (glossaryIcon) {
        glossaryIcon.onclick = () => {
            openGlossaryCatalogModal();
        };
    }

    if (soundToggleIcon) {
        refreshSoundDockIcon(soundToggleIcon);
        soundToggleIcon.onclick = () => {
            toggleSoundFxFromDock(soundToggleIcon);
        };
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

    const unplacedChars = battleState.characters.filter(c => {
        const isUnplaced = c.x < 0 || c.y < 0;
        if (!isUnplaced) return false;

        // 期限切れ/戦闘不能になった召喚物は未配置モーダルに出さない
        const isSummoned = !!c.is_summoned;
        if (!isSummoned) return true;

        const hp = Number(c.hp || 0);
        const mode = String(c.summon_duration_mode || '').toLowerCase();
        const remaining = Number(c.remaining_summon_rounds);
        const isExpiredDurationSummon =
            mode === 'duration_rounds' && Number.isFinite(remaining) && remaining <= 0;

        return !(hp <= 0 || isExpiredDurationSummon);
    });

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
        deleteBtn.onclick = async () => {
            if (await window.showAppConfirm(`「${char.name}」を削除しますか？`, {
                title: 'キャラクター削除',
                confirmText: '削除',
            })) {
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
