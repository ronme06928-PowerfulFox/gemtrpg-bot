/**
 * actions.js
 * Handles Mobile Action Dock Features:
 * - Immediate Skills
 * - Items
 * - Unplaced Characters (Staging)
 * - Add Character (JSON)
 * - Match Toggle
 */

export const MobileActions = {
    itemData: null,

    init() {
        console.log("⚡ MobileActions Module Initialized");
        // Pre-fetch item data if possible, or wait till needed
        this.fetchItemData();
    },

    async fetchItemData() {
        if (this.itemData) return;
        try {
            const res = await fetch('/api/get_item_data');
            if (res.ok) {
                this.itemData = await res.json();
                console.log("🎒 Item Data Loaded:", Object.keys(this.itemData).length);
            }
        } catch (e) {
            console.error("Failed to load item data:", e);
        }
    },

    // --- Utility: Open Generic Modal ---
    createModal(id, title, contentHtml, onClose) {
        let overlay = document.getElementById(id);
        if (overlay) overlay.remove();

        overlay = document.createElement('div');
        overlay.id = id;
        overlay.className = 'mobile-overlay';
        overlay.style.zIndex = '3000'; // Higher than others

        overlay.innerHTML = `
            <div class="overlay-header">
                <h3>${title}</h3>
                <button class="close-overlay">×</button>
            </div>
            <div class="overlay-content" style="padding:15px;">
                ${contentHtml}
            </div>
        `;

        document.body.appendChild(overlay);

        // Bind Close
        const closeBtn = overlay.querySelector('.close-overlay');
        closeBtn.onclick = () => {
            overlay.classList.add('hidden');
            setTimeout(() => overlay.remove(), 300); // Wait for transition
            if (onClose) onClose();
        };

        // Animate In
        requestAnimationFrame(() => {
            overlay.classList.remove('hidden'); // Ensure CSS handles default hidden state if needed, but here we append active
        });

        return overlay.querySelector('.overlay-content');
    },

    // --- 1. Match Toggle ---
    toggleMatchModal() {
        if (window.MobileMatch && typeof window.MobileMatch.toggleModal === 'function') {
            window.MobileMatch.toggleModal();
        } else {
            console.warn("MobileMatch module not ready.");
        }
    },

    // --- 2. Immediate Skills ---
    openImmediateModal() {
        const myChars = this.getMyPlacedCharacters();
        if (myChars.length === 0) {
            alert("配置済みの自分のキャラクターがいません。");
            return;
        }

        // Filter for characters that actually have immediate skills
        const charsWithSkills = myChars.filter(c => this.hasImmediateSkill(c));

        let html = '';
        if (charsWithSkills.length === 0) {
            html = '<div class="empty-msg">即時発動スキルを持つキャラクターがいません。</div>';
        } else {
            html = `<div class="action-list"></div>`;
        }

        const content = this.createModal('mobile-immediate-modal', '⚡ 即時発動スキル', html);
        const listContainer = content.querySelector('.action-list');

        if (listContainer) {
            charsWithSkills.forEach(char => {
                const row = document.createElement('div');
                row.className = 'action-row-item';

                const isUsed = char.flags && char.flags.immediate_action_used;

                let skillsHtml = '';
                const skills = this.getImmediateSkills(char);

                if (skills.length > 0) {
                    skills.forEach(skill => {
                        skillsHtml += `<button class="mobile-btn primary sm" data-char="${char.id}" data-skill="${skill.id}" ${isUsed ? 'disabled' : ''}>${skill.name}</button>`;
                    });
                }

                row.innerHTML = `
                    <div class="char-header">
                        <span class="char-name">${char.name}</span>
                        ${isUsed ? '<span class="status-badge used">使用済</span>' : ''}
                    </div>
                    <div class="skill-actions" style="display:flex; gap:10px; flex-wrap:wrap; margin-top:5px;">
                        ${skillsHtml}
                    </div>
                `;

                // Bind buttons
                const btns = row.querySelectorAll('button');
                btns.forEach(btn => {
                    btn.onclick = () => {
                        if (confirm(`${char.name}で「${btn.textContent}」を使用しますか？`)) {
                            this.executeImmediate(char.id, btn.dataset.skill);
                            // Close modal? Maybe keep open for multiple? Usually one per round?
                            document.getElementById('mobile-immediate-modal').querySelector('.close-overlay').click();
                        }
                    };
                });

                listContainer.appendChild(row);
            });
        }
    },

    hasImmediateSkill(char) {
        const skills = this.getImmediateSkills(char);
        return skills.length > 0;
    },

    getImmediateSkills(char) {
        if (!char.commands || !window.allSkillData) return [];
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        const results = [];
        while ((match = regex.exec(char.commands)) !== null) {
            const skillId = match[1];
            const skillName = match[2];
            const skillData = window.allSkillData[skillId];
            if (skillData && skillData.tags && skillData.tags.includes('即時発動')) {
                results.push({ id: skillId, name: skillName });
            }
        }
        return results;
    },

    executeImmediate(charId, skillId) {
        if (!window.socket) return;
        window.socket.emit('request_skill_declaration', {
            room: window.currentRoomName,
            actor_id: charId,
            target_id: charId,
            skill_id: skillId,
            commit: true,
            prefix: `immediate_${charId}`
        });
    },

    // --- 3. Items ---
    async openItemModal() {
        if (!this.itemData) await this.fetchItemData();

        const myChars = this.getMyPlacedCharacters();
        if (myChars.length === 0) {
            alert("配置済みの自分のキャラクターがいません。");
            return;
        }

        let html = '<div class="action-list"></div>';
        const content = this.createModal('mobile-item-modal', '🎒 アイテム', html);
        const listContainer = content.querySelector('.action-list');

        // Initial View: Character List
        this.renderItemCharacterList(listContainer, myChars);
    },

    renderItemCharacterList(container, chars) {
        container.innerHTML = '';
        const title = document.createElement('h4');
        title.textContent = "キャラクターを選択";
        container.appendChild(title);

        chars.forEach(char => {
            const inventory = char.inventory || {};
            const itemCount = Object.values(inventory).reduce((a, b) => a + b, 0);

            const row = document.createElement('div');
            row.className = 'action-list-row';
            row.innerHTML = `
                <div class="row-info">
                    <strong>${char.name}</strong>
                    <small>Items: ${itemCount}</small>
                </div>
                <span>▶</span>
            `;
            row.onclick = () => {
                this.renderPlayerInventory(container, char);
            };
            container.appendChild(row);
        });
    },

    renderPlayerInventory(container, char) {
        container.innerHTML = '';

        // Header with Back Button
        const header = document.createElement('div');
        header.style.display = 'flex';
        header.style.alignItems = 'center';
        header.style.marginBottom = '10px';
        header.innerHTML = `
            <button class="mobile-btn sm secondary" id="item-back-btn">←</button>
            <h4 style="margin:0 0 0 10px;">${char.name}のアイテム</h4>
        `;
        container.appendChild(header);

        container.querySelector('#item-back-btn').onclick = () => {
            this.renderItemCharacterList(container, this.getMyPlacedCharacters());
        };

        const inventory = char.inventory || {};
        const itemIds = Object.keys(inventory);

        if (itemIds.length === 0) {
            const empty = document.createElement('div');
            empty.textContent = "アイテムを持っていません";
            empty.className = "empty-msg";
            container.appendChild(empty);
            return;
        }

        itemIds.forEach(itemId => {
            const count = inventory[itemId];
            const data = this.itemData[itemId];
            if (!data) return;

            const card = document.createElement('div');
            card.className = 'mobile-card item-card';
            card.innerHTML = `
                <div class="card-head">
                    <strong>${data.name}</strong>
                    <span class="badge">${count}</span>
                </div>
                <div class="card-desc">${data.description || ''}</div>
                <div class="card-actions" style="margin-top:8px; text-align:right;">
                    <button class="mobile-btn sm primary use-btn">使用</button>
                </div>
            `;

            card.querySelector('.use-btn').onclick = () => {
                this.openItemTargetModal(char, itemId, data);
            };

            container.appendChild(card);
        });
    },

    openItemTargetModal(actor, itemId, itemData) {
        // Close item modal first? Or toggle content? simpler to replace content
        // But for target selection, modal stack or replace content is better.
        // Let's replace content of the current modal if possible, but structure prevents easy finding.
        // Let's create a new modal on top (stacking z-index logic in createModal handles simple override or new one)

        const targetType = (itemData.effect && itemData.effect.target) || 'single';

        let targets = [];
        const charType = actor.type || 'ally';

        if (targetType === 'single') {
            // Filter allies
            targets = window.battleState.characters.filter(c => c.type === charType && c.hp > 0 && c.x >= 0);
        } else {
            // All targets handling
            if (targetType === 'all_allies') {
                targets = window.battleState.characters.filter(c => c.type === charType && c.hp > 0 && c.x >= 0);
            } else if (targetType === 'all_enemies') {
                const enemyType = charType === 'ally' ? 'enemy' : 'ally';
                targets = window.battleState.characters.filter(c => c.type === enemyType && c.hp > 0 && c.x >= 0);
            }
        }

        let html = `
            <div style="margin-bottom:10px;">
                <strong>${itemData.name}</strong> を使用します。
                <p style="font-size:0.9em; color:#ccc;">${itemData.description}</p>
            </div>
        `;

        if (targetType === 'single') {
            html += `<h4>対象を選択</h4><div class="target-list">`;
            targets.forEach(t => {
                html += `
                    <label class="target-option-row" style="display:block; padding:10px; border-bottom:1px solid #444;">
                        <input type="radio" name="item_target" value="${t.id}">
                        ${t.name} (HP:${t.hp})
                    </label>
                `;
            });
            html += `</div>`;
        } else {
            html += `<h4>対象: 全体</h4><div class="target-summry">
                ${targets.map(t => t.name).join(', ')}
             </div>`;
        }

        html += `
            <div style="margin-top:15px; display:flex; gap:10px;">
                <button class="mobile-btn secondary" id="cancel-use-item" style="flex:1;">キャンセル</button>
                <button class="mobile-btn primary" id="confirm-use-item" style="flex:1;">使用する</button>
            </div>
        `;

        const content = this.createModal('mobile-item-confirm-modal', 'アイテム使用確認', html);

        content.querySelector('#cancel-use-item').onclick = () => {
            document.getElementById('mobile-item-confirm-modal').querySelector('.close-overlay').click();
        };

        content.querySelector('#confirm-use-item').onclick = () => {
            let targetId = null;
            if (targetType === 'single') {
                const radio = content.querySelector('input[name="item_target"]:checked');
                if (!radio) {
                    alert("対象を選択してください。");
                    return;
                }
                targetId = radio.value;
            }

            this.executeItemUse(actor.id, targetId, itemId);
            // Close all
            if (document.getElementById('mobile-item-confirm-modal')) document.getElementById('mobile-item-confirm-modal').remove();
            if (document.getElementById('mobile-item-modal')) document.getElementById('mobile-item-modal').remove();
        };
    },

    executeItemUse(userId, targetId, itemId) {
        if (!window.socket) return;
        window.socket.emit('request_use_item', {
            room: window.currentRoomName,
            user_id: userId,
            target_id: targetId,
            item_id: itemId
        });
    },

    // --- 4. Staging (Unplaced) ---
    openStagingModal() {
        if (!window.battleState || !window.battleState.characters) return;
        const unplaced = window.battleState.characters.filter(c => c.x < 0 || c.y < 0);

        if (unplaced.length === 0) {
            alert("未配置のキャラクターはいません。");
            return;
        }

        let html = '<div class="action-list"></div>';
        const content = this.createModal('mobile-staging-modal', '📦 未配置キャラクター', html);
        const list = content.querySelector('.action-list');

        unplaced.forEach(char => {
            const isDead = char.hp <= 0;
            const row = document.createElement('div');
            row.className = `action-list-row ${isDead ? 'dead' : ''}`;
            row.innerHTML = `
                <div class="row-info">
                    <strong>${char.name}</strong>
                    <small>${isDead ? '戦闘不能' : `HP: ${char.hp}`}</small>
                </div>
                <div class="row-actions">
                    ${!isDead ? `<button class="mobile-btn sm primary place-btn">配置</button>` : ''}
                    <button class="mobile-btn sm danger delete-btn">削除</button>
                </div>
            `;

            row.querySelector('.delete-btn').onclick = () => {
                if (confirm(`${char.name}を削除しますか？`)) {
                    this.executeDelete(char.id);
                    // Refresh handled by state update
                }
            };

            if (!isDead) {
                row.querySelector('.place-btn').onclick = () => {
                    this.autoPlaceCharacter(char);
                    document.getElementById('mobile-staging-modal').querySelector('.close-overlay').click();
                };
            }

            list.appendChild(row);
        });
    },

    executeDelete(charId) {
        window.socket.emit('request_delete_character', {
            room: window.currentRoomName,
            charId: charId
        });
    },

    autoPlaceCharacter(char) {
        // Logic from PC: findEmptyPosition
        // Center is roughly 12, 12
        const startX = 12;
        const startY = 12;

        const pos = this.findEmptyPosition(startX, startY);

        window.socket.emit('request_move_character', { // Note: Server uses 'request_move_character' for placement? Or 'request_move_token'?
            // PC: socket.emit('request_move_character', ...)
            // Mobile move token used 'request_move_token'.
            // Let's check common_routes.py.
            // It has 'request_move_token' calling move_token_logic.
            // PC 'request_move_character' calls move_character_logic (which likely does same or calls move_token).
            // Let's safely use 'request_move_token' which we verified works for mobile,
            // OR use 'request_move_character' if that's what PC uses for initial placement logic (might include "spawn" checks).
            // Checking action_dock.js line 616: socketToUse.emit('request_move_character', ...)
            // So PC uses request_move_character. I verified request_move_token works for updates.
            // Let's try request_move_character to match PC placement logic.
            room: window.currentRoomName,
            character_id: char.id, // PC uses character_id
            x: pos.x,
            y: pos.y
        });
    },

    findEmptyPosition(startX, startY) {
        const isOccupied = (x, y) => {
            return window.battleState.characters.some(c => c.x === x && c.y === y);
        };

        if (!isOccupied(startX, startY)) return { x: startX, y: startY };

        const directions = [
            [1, 0], [0, 1], [-1, 0], [0, -1],
            [1, 1], [1, -1], [-1, 1], [-1, -1]
        ];

        for (let radius = 1; radius <= 5; radius++) {
            for (const [dx, dy] of directions) {
                const x = startX + dx * radius;
                const y = startY + dy * radius;
                if (x >= 0 && x < 25 && y >= 0 && y < 25 && !isOccupied(x, y)) {
                    return { x, y };
                }
            }
        }
        return { x: startX, y: startY }; // Fallback
    },

    // --- 5. Add Character ---
    openLoadCharacterModal() {
        const isGM = (window.currentUserAttribute === 'GM');

        let gmHtml = '';
        if (isGM) {
            gmHtml = `
                <div style="margin-top:20px; padding-top:15px; border-top:1px solid #444;">
                    <p style="font-size:0.9em; color:#aaa; margin-bottom:10px;">★ GM専用: デバッグキャラ生成 (全スキル所持)</p>
                    <div style="display:flex; gap:10px;">
                        <button class="mobile-btn sm primary" id="btn-debug-ally" style="flex:1;">Debug Ally</button>
                        <button class="mobile-btn sm danger" id="btn-debug-enemy" style="flex:1;">Debug Enemy</button>
                    </div>
                </div>
            `;
        }

        const html = `
            <div style="margin-bottom:10px;">
                <p style="font-size:0.9em; color:#ccc;">キャラクターデータのJSONを貼り付けてください。</p>
                <textarea id="char-json-input" class="mobile-textarea" rows="8" placeholder='{"name": "...", ...}'></textarea>
            </div>
            <div style="display:flex; gap:10px;">
                 <button class="mobile-btn primary" id="btn-load-ally" style="flex:1;">味方として追加</button>
                 <button class="mobile-btn danger" id="btn-load-enemy" style="flex:1;">敵として追加</button>
            </div>
            ${gmHtml}
        `;

        const content = this.createModal('mobile-add-char-modal', '➕ キャラクター追加', html);

        // JSON Load Handlers
        const handleLoad = (type) => {
            const jsonText = document.getElementById('char-json-input').value;
            if (!jsonText.trim()) {
                alert("JSONデータを入力してください。");
                return;
            }
            try {
                let data = JSON.parse(jsonText);
                // Handle different JSON structures roughly (if top level is "data" or direct)
                if (data.kind === 'character' && data.data) {
                    data = data.data;
                }

                data.type = type; // Force type

                window.socket.emit('add_character', {
                    room: window.currentRoomName,
                    character_data: data
                });

                alert(`${type === 'ally' ? '味方' : '敵'}キャラクター追加リクエストを送信しました。`);
                document.getElementById('mobile-add-char-modal').querySelector('.close-overlay').click();

            } catch (e) {
                alert("JSONの形式が正しくありません。\n" + e.message);
            }
        };

        content.querySelector('#btn-load-ally').onclick = () => handleLoad('ally');
        content.querySelector('#btn-load-enemy').onclick = () => handleLoad('enemy');

        // GM Debug Handlers
        if (isGM) {
            const debugAdd = (type) => {
                if (confirm(`${type === 'ally' ? '味方' : '敵'}のデバッグキャラを生成しますか？`)) {
                    window.socket.emit('request_add_debug_character', {
                        room: window.currentRoomName,
                        type: type
                    });
                    document.getElementById('mobile-add-char-modal').querySelector('.close-overlay').click();
                }
            };

            content.querySelector('#btn-debug-ally').onclick = () => debugAdd('ally');
            content.querySelector('#btn-debug-enemy').onclick = () => debugAdd('enemy');
        }
    },

    // Helper
    getMyPlacedCharacters() {
        if (!window.battleState || !window.battleState.characters) return [];
        return window.battleState.characters.filter(c => {
            return (c.x >= 0 && c.y >= 0) && (c.owner === window.currentUsername || c.owner === 'System'); // Allow System testing?
            // Strict: c.owner === window.currentUsername
        });
    }
};
