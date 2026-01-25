/**
 * match.js
 * Handles Battle/Duel Logic and UI for Mobile
 * Strictly mirrors PC Version Logic for Filtering and Wide Attacks
 */

export const MobileMatch = {
    activeMatch: null,

    init() {
        console.log("⚔️ MobileMatch Module Initialized");
    },

    setupSocketListeners(socket) {
        if (!socket) return;
        socket.on('skill_declaration_result', (data) => {
            console.log("⚔️ MobileMatch Received Result:", data);
            this.updatePreview(data);
        });

        socket.on('open_wide_match_modal', (data) => {
            console.log("⚡ Open Wide Match Modal Signal:", data);
            this.openWideMatchModal(data);
        });

        socket.on('wide_skill_calculated', (data) => {
            this.handleWideSkillCalculated(data);
        });
    },

    // --- Helper Logic (Strictly Mirroring PC SkillUtils.js) ---
    // --- Helper Logic (Strictly Mirroring PC SkillUtils.js) ---
    isWideSkillData(skillData) {
        if (!skillData) return false;
        let tags = skillData['tags'] || [];
        if (typeof tags === 'string') tags = [tags];

        const cat = skillData['分類'] || '';
        const dist = skillData['距離'] || '';

        // Robust check: matches PC logic but safer for types
        const hasWideTag = tags.some(t => t.includes('広域-個別') || t.includes('広域-合算'));
        return (hasWideTag || cat.includes('広域') || dist.includes('広域'));
    },

    isImmediateSkillData(skillData) {
        if (!skillData) return false;
        let tags = skillData['tags'] || [];
        if (typeof tags === 'string') tags = [tags];

        const timing = skillData['タイミング'] || '';

        // Robust check
        const hasImmediateTag = tags.some(t => t.includes('即時'));
        return (hasImmediateTag || timing.includes('即時') || timing === 'immediate');
    },

    hasWideSkill(char) {
        if (!char || !char.commands) return false;
        // Regex to parse skills (Standard PC Regex)
        // Reset lastIndex not needed for local regex in loop, but safer to use matchAll or exec locally
        const regex = /【(.*?)[ 　]+(.*?)】/g;
        let match;

        while ((match = regex.exec(char.commands)) !== null) {
            const skillId = match[1];
            if (window.allSkillData) {
                const skillData = window.allSkillData[skillId];
                if (skillData && this.isWideSkillData(skillData)) {
                    return true;
                }
            } else {
                // Fallback text check
                if (match[0].includes('広域') || match[0].includes('Wide')) return true;
            }
        }
        return false;
    },

    startDuelSetup(attackerId) {
        this.showTargetSelection(attackerId);
    },

    showTargetSelection(attackerId) {
        const attacker = window.battleState.characters.find(c => c.id === attackerId);
        if (!attacker) return;

        let overlay = document.getElementById('mobile-target-selector');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'mobile-target-selector';
            overlay.className = 'mobile-overlay hidden';
            document.body.appendChild(overlay);
        }

        const targets = window.battleState.characters.filter(c => c.id !== attackerId && c.hp > 0 && c.x >= 0);

        overlay.innerHTML = `
            <div class="overlay-header">
                <h3>Select Target</h3>
                <button class="close-overlay" onclick="document.getElementById('mobile-target-selector').classList.add('hidden')">×</button>
            </div>
            <div class="overlay-content">
                <p>Attacker: <b>${attacker.name}</b></p>
                <ul class="mobile-list">
                    ${targets.map(t => `
                        <li class="mobile-list-item" onclick="window.MobileMatch.openDuel('${attackerId}', '${t.id}')">
                            <div style="display:flex; align-items:center;">
                                <div class="char-icon" style="background-image:url('${t.image || ''}');"></div>
                                <span>${t.name}</span>
                            </div>
                            <button class="mobile-btn accent sm">Select</button>
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
        overlay.classList.remove('hidden');
    },

    openDuel(attackerId, defenderId) {
        if (window.socket) {
            console.log("📡 Emitting open_match_modal to sync server state");
            window.socket.emit('open_match_modal', {
                room: window.currentRoomName,
                match_type: 'duel',
                attacker_id: attackerId,
                defender_id: defenderId
            });
        }

        document.querySelectorAll('.mobile-overlay').forEach(el => el.classList.add('hidden'));

        const attacker = window.battleState.characters.find(c => c.id === attackerId);
        const defender = window.battleState.characters.find(c => c.id === defenderId);

        let modal = document.getElementById('mobile-duel-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'mobile-duel-modal';
            modal.className = 'mobile-overlay hidden';
            document.body.appendChild(modal);
        }

        modal.innerHTML = `
            <div class="overlay-header">
                <h3>Duel</h3>
                <button class="close-overlay" onclick="document.getElementById('mobile-duel-modal').classList.add('hidden')">×</button>
            </div>
            <div class="overlay-content" style="padding: 10px;">
                <!-- Attacker Section -->
                <div class="duel-section attacker-bg">
                    <h4 onclick="window.Characters.showCharacterCard('${attacker.id}')" style="cursor:pointer; text-decoration:underline;">
                        Attacker: ${attacker.name} ℹ️
                    </h4>
                    <select id="duel-skill-select" class="mobile-select">
                        <option value="">-- Select Skill --</option>
                    </select>
                    <div id="duel-attacker-preview" class="duel-preview-box"></div>
                    <div class="duel-btn-row">
                        <button id="duel-calc-btn" class="mobile-btn secondary sm">Check</button>
                        <button id="duel-declare-btn" class="mobile-btn primary sm" disabled>Declare</button>
                    </div>
                </div>

                <div style="text-align:center; margin: 5px;">VS</div>

                <!-- Defender Section -->
                <div class="duel-section defender-bg">
                    <h4 onclick="window.Characters.showCharacterCard('${defender.id}')" style="cursor:pointer; text-decoration:underline;">
                        Target: ${defender.name} ℹ️
                    </h4>
                    <select id="duel-def-skill-select" class="mobile-select">
                        <option value="">-- Select Skill --</option>
                    </select>
                    <div id="duel-defender-preview" class="duel-preview-box"></div>
                    <div class="duel-btn-row">
                        <button id="duel-def-calc-btn" class="mobile-btn secondary sm">Check</button>
                        <button id="duel-def-declare-btn" class="mobile-btn primary sm" disabled>Declare</button>
                    </div>
                </div>

                <!-- Controls -->
                <div class="duel-controls" style="margin-top:15px;">
                    <button id="duel-exec-btn" class="mobile-btn accent" disabled style="width:100%;">Execute Match</button>
                </div>
            </div>
        `;

        modal.classList.remove('hidden');

        this.populateSkills(attackerId, 'duel-skill-select', 'duel');
        this.populateSkills(defenderId, 'duel-def-skill-select', 'duel');


        document.getElementById('duel-calc-btn').onclick = () => this.calculateDuel(attackerId, defenderId, 'attacker', false);
        document.getElementById('duel-declare-btn').onclick = () => this.calculateDuel(attackerId, defenderId, 'attacker', true);

        document.getElementById('duel-def-calc-btn').onclick = () => this.calculateDuel(attackerId, defenderId, 'defender', false);
        document.getElementById('duel-def-declare-btn').onclick = () => this.calculateDuel(attackerId, defenderId, 'defender', true);

        document.getElementById('duel-exec-btn').onclick = () => this.executeDuel(attackerId, defenderId);

        this.resetState();
    },

    resetState() {
        this.results = { attacker: null, defender: null };
        this.declarations = { attacker: false, defender: false };
    },

    populateSkills(charId, selectId, filterType = 'duel') {
        const char = window.battleState.characters.find(c => c.id === charId);
        if (!char || !char.commands) return;

        const select = document.getElementById(selectId);
        if (!select) return;
        select.innerHTML = '<option value="">-- Select Skill --</option>';

        const lines = char.commands.split('\n');

        lines.forEach(line => {
            line = line.trim();
            if (!line.includes('【') || !line.includes('】')) return;

            const match = line.match(/【(.*?)[ 　]+(.*?)】/);
            let skillId, name;

            if (match) {
                skillId = match[1];
                name = match[2];
            } else {
                const plainMatch = line.match(/【(.*?)】/);
                if (plainMatch) {
                    skillId = plainMatch[1];
                    name = plainMatch[1];
                } else {
                    return;
                }
            }

            // Filter Logic
            let shouldSkip = false;
            let skillData = null;
            if (window.allSkillData) skillData = window.allSkillData[skillId];

            const isWide = skillData ? this.isWideSkillData(skillData) : (line.includes('広域') || line.includes('Wide'));
            const isImmediate = skillData ? this.isImmediateSkillData(skillData) : (line.includes('即時') || line.includes('Immediate'));

            if (filterType === 'duel') {
                // Exclude Wide & Immediate
                if (isWide || isImmediate) shouldSkip = true;
            } else if (filterType === 'wide_attacker') {
                // ONLY Wide
                if (!isWide) shouldSkip = true;
            } else if (filterType === 'wide_defender') {
                // Exclude Wide & Immediate (same as duel usually, sometimes allowed depending on rules, but safer to block)
                if (isWide || isImmediate) shouldSkip = true;
            }

            if (shouldSkip) return;

            const opt = document.createElement('option');
            opt.value = skillId;
            opt.textContent = `${name} [${skillId}]`;
            select.appendChild(opt);
        });
    },

    calculateDuel(attackerId, defenderId, side, isCommit) {
        const selectId = side === 'attacker' ? 'duel-skill-select' : 'duel-def-skill-select';
        const skillId = document.getElementById(selectId).value;
        const prefix = side === 'attacker' ? 'visual_attacker' : 'visual_defender';

        if (!skillId) { alert(`Please select a skill for ${side}.`); return; }

        console.log(`Requesting ${isCommit ? 'Declaration' : 'Calculation'} (${side})...`, skillId);

        if (isCommit) {
            this.declarations[side] = true;
            this.updateExecutionState();
        }

        if (window.socket) {
            window.socket.emit('request_skill_declaration', {
                room: window.currentRoomName,
                prefix: prefix,
                actor_id: side === 'attacker' ? attackerId : defenderId,
                target_id: side === 'attacker' ? defenderId : attackerId,
                skill_id: skillId,
                custom_skill_name: "",
                commit: isCommit
            });
        }
    },

    results: { attacker: null, defender: null },
    declarations: { attacker: false, defender: false },

    updateExecutionState() {
        const execBtn = document.getElementById('duel-exec-btn');
        if (!execBtn) return;

        const attReady = this.declarations.attacker;
        const defReady = this.declarations.defender;

        const attHeader = document.querySelector('.duel-section.attacker-bg h4');
        if (attHeader) attHeader.style.color = attReady ? '#4caf50' : 'white';

        const defHeader = document.querySelector('.duel-section.defender-bg h4');
        if (defHeader) defHeader.style.color = defReady ? '#4caf50' : 'white';

        if (attReady && defReady) {
            execBtn.disabled = true;
            execBtn.classList.remove('secondary');
            execBtn.classList.add('accent', 'pulse');
            execBtn.textContent = "Auto Executing...";

            if (!this.autoExecTimer) {
                console.log("⚡ Both sides ready. Auto-executing in 1.5s...");
                this.autoExecTimer = setTimeout(() => {
                    this.executeDuel();
                }, 1500);
            }
        } else {
            execBtn.disabled = true;
            execBtn.classList.add('secondary');
            execBtn.classList.remove('accent', 'pulse');
            execBtn.textContent = "Waiting for Declarations...";
            if (this.autoExecTimer) {
                clearTimeout(this.autoExecTimer);
                this.autoExecTimer = null;
            }
        }
    },

    autoExecTimer: null,

    updatePreview(data) {
        if (!data || !data.prefix) return;

        let side = null;
        let previewElId = null;
        let declareBtnId = null;
        let isWide = false;

        if (data.prefix === 'visual_attacker') {
            side = 'attacker';
            previewElId = 'duel-attacker-preview';
            declareBtnId = 'duel-declare-btn';
        } else if (data.prefix === 'visual_defender') {
            side = 'defender';
            previewElId = 'duel-defender-preview';
            declareBtnId = 'duel-def-declare-btn';
        } else if (data.prefix === 'wide_attacker') {
            side = 'attacker';
            previewElId = 'wide-attacker-preview';
            declareBtnId = 'wide-att-declare-btn';
            isWide = true;
        } else if (data.prefix.startsWith('wide_defender_')) {
            side = 'defender';
            const defId = data.prefix.replace('wide_defender_', '');
            previewElId = `wide-def-preview-${defId}`;
            // Use querySelector because btn is inside dynamic item
            const item = document.getElementById(`wide-def-item-${defId}`);
            if (item) {
                const btn = item.querySelector('.btn-decl-def');
                if (btn) btn.disabled = false; // Enable directly here as we can't infer ID easily
            }
            isWide = true;
        }

        if (!side) return;

        if (!isWide) {
            this.results[side] = data; // Store for normal duel execution
        }

        const resultBox = document.getElementById(previewElId);

        // Setup declare btn variable for checks (only for those with explicit ID)
        const declareBtn = declareBtnId ? document.getElementById(declareBtnId) : null;

        if (!resultBox) return;

        if (data.error) {
            resultBox.innerHTML = `<div class="error-msg">Error: ${data.final_command || 'Unknown'}</div>`;
            if (declareBtn) declareBtn.disabled = true;
            if (!isWide) this.declarations[side] = false;
        } else {
            let html = `<div class="preview-cmd">${data.final_command}</div>`;
            if (data.min_damage !== undefined) {
                html += `<div class="preview-dmg">Range: <b>${data.min_damage}</b> ~ <b>${data.max_damage}</b></div>`;
            }

            let details = '';
            if (data.skill_details && data.skill_details.base_power_mod) {
                const mod = data.skill_details.base_power_mod;
                details += `<div>[基礎威力 ${mod > 0 ? '+' : ''}${mod}]</div>`;
            }
            if (data.correction_details && data.correction_details.length > 0) {
                data.correction_details.forEach(d => {
                    const sign = d.value > 0 ? '+' : '';
                    details += `<div>[${d.source} ${sign}${d.value}]</div>`;
                });
            }
            // 戦慄
            if (data.senritsu_dice_reduction) {
                details += `<div>(戦慄: ダイス-${data.senritsu_dice_reduction})</div>`;
            }

            if (details) html += `<div class="preview-details">${details}</div>`;

            if (data.skill_details && data.skill_details.description) {
                html += `<div class="skill-desc">${data.skill_details.description}</div>`;
            }

            resultBox.innerHTML = html;

            if (declareBtn && (!isWide ? !this.declarations[side] : !this.wideDeclarations?.attacker)) { // Only enable if not already declared
                // Logic tweak: For wide attacker, check separate state
                if (isWide && side === 'attacker' && !this.wideDeclarations.attacker) declareBtn.disabled = false;
                else if (!isWide && !this.declarations[side]) declareBtn.disabled = false;
            }
        }

        if (!isWide) this.updateExecutionState();
    },

    executeDuel() {
        const matchId = this.results.attacker ? this.results.attacker.match_id : (this.results.defender ? this.results.defender.match_id : null);

        if (!matchId) return;

        console.log("Executing Match (Auto)...");
        if (window.socket) {
            window.socket.emit('request_match', {
                match_id: matchId
            });
            document.getElementById('mobile-duel-modal').classList.add('hidden');
        }
    },

    // --- Wide Match Initiation ---
    startWideMatch(attackerId) {
        console.log("⚡ Starting Wide Match for:", attackerId);
        const attacker = window.battleState.characters.find(c => c.id === attackerId);
        if (!attacker) return;

        // Auto-detect targets (All enemies)
        // Note: PC version might allow selection, but for basic Wide execution, selecting all enemies is standard.
        // We filter by opposing type.
        const myType = attacker.type || 'ally'; // Default to ally if undefined? Or check owner.
        // Safer to check simple type equality if available, or assume 'ally' vs 'enemy'.
        // If attacker.type is 'ally', target 'enemy'. If 'enemy', target 'ally'.

        let targetType = 'enemy';
        if (myType === 'enemy') targetType = 'ally';

        const targets = window.battleState.characters.filter(c =>
            c.type === targetType && c.hp > 0 && c.x >= 0
        );
        const targetIds = targets.map(t => t.id);

        console.log(`⚡ Auto-targeting ${targetIds.length} enemies.`);

        // Sync with Server & PC
        if (window.socket) {
            window.socket.emit('open_wide_match_modal', {
                room: window.currentRoomName,
                attacker_id: attackerId,
                defender_ids: targetIds
            });
        }

        // Open Local UI
        this.openWideMatchModal({
            attacker_id: attackerId,
            defender_ids: targetIds
        });
    },

    // --- Wide Reservation Logic ---
    openWideReservationModal(activeChars) {
        console.log("⚡ Opening Wide Reservation Modal");

        let modal = document.getElementById('mobile-wide-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'mobile-wide-modal';
            modal.className = 'mobile-overlay hidden';
            document.body.appendChild(modal);
        }

        const myWideChars = window.battleState.characters.filter(c => {
            const isOwner = (c.owner === window.currentUsername) || (window.currentUserAttribute === 'GM');
            // Use strict check
            const hasWide = this.hasWideSkill(c);
            return isOwner && hasWide && c.hp > 0 && c.x >= 0;
        });

        modal.innerHTML = `
            <div class="overlay-header" style="background:var(--accent-color);">
                <h3>⚡ Wide Attack Reservation</h3>
            </div>
            <div class="overlay-content" style="padding:15px;">
                <p>Select characters to prepare Wide Attack for this round.</p>
                <div class="wide-list">
                    ${myWideChars.length > 0 ? myWideChars.map(c => `
                        <label class="mobile-list-item" style="display:flex; align-items:center; gap:10px;">
                            <input type="checkbox" value="${c.id}" class="wide-check" style="transform:scale(1.5);">
                            <span style="font-weight:bold;">${c.name}</span>
                        </label>
                    `).join('') : '<div style="padding:10px; color:#999;">No characters with Wide Skills found.</div>'}
                </div>
                <div class="duel-btn-row" style="margin-top:20px;">
                    <button id="wide-done-btn" class="mobile-btn primary" style="width:100%;">Confirm</button>
                </div>
            </div>
        `;

        modal.classList.remove('hidden');

        document.getElementById('wide-done-btn').onclick = () => {
            const checks = modal.querySelectorAll('.wide-check:checked');
            const ids = Array.from(checks).map(c => c.value);

            if (window.socket) {
                console.log("⚡ Sending Wide Reservation Confirmation:", ids);
                window.socket.emit('request_wide_modal_confirm', {
                    room: window.currentRoomName,
                    wideUserIds: ids // PC version uses 'wideUserIds'
                });
            }

            // UI Update to Wait State (Don't close immediately)
            const btn = document.getElementById('wide-done-btn');
            btn.disabled = true;
            btn.textContent = "Confirmed. Waiting for others...";
            btn.classList.remove('primary');
            btn.classList.add('secondary');

            // Note: The modal will be closed/reset when the round changes via state_updated
        };
    },

    closeWideReservationModal() {
        const modal = document.getElementById('mobile-wide-modal');
        if (modal && !modal.classList.contains('hidden')) {
            modal.classList.add('hidden');
        }
    },

    closeMatchModal() {
        const modal = document.getElementById('mobile-duel-modal');
        if (modal && !modal.classList.contains('hidden')) {
            modal.classList.add('hidden');
            this.resetState();
        }
        // Also close wide match
        const wideModal = document.getElementById('mobile-wide-match-modal');
        if (wideModal && !wideModal.classList.contains('hidden')) {
            wideModal.classList.add('hidden');
        }
    },

    // --- Wide Match Execution UI ---
    openWideMatchModal(data) {
        console.log("⚡ Opening Wide Match Execution UI", data);

        let modal = document.getElementById('mobile-wide-match-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'mobile-wide-match-modal';
            modal.className = 'mobile-overlay hidden';
            document.body.appendChild(modal);
        }

        const attackerId = data.attacker_id;
        const defenderIds = data.defender_ids || data.targets || [];
        // Save for later reference
        this.wideMatchData = { attackerId, defenderIds };
        this.wideDeclarations = { attacker: false, defenders: {} };
        defenderIds.forEach(id => this.wideDeclarations.defenders[id] = false);

        const attacker = window.battleState.characters.find(c => c.id === attackerId);

        // Build Defenders List HTML
        const defendersHtml = defenderIds.map(defId => {
            const def = window.battleState.characters.find(c => c.id === defId);
            if (!def) return '';
            return `
                <div class="wide-defender-item" id="wide-def-item-${defId}">
                    <div class="wide-def-header">
                        <span class="def-name" onclick="window.Characters.showCharacterCard('${defId}')">${def.name}</span>
                        <div class="def-status">Waiting...</div>
                    </div>
                    <select id="wide-def-skill-${defId}" class="mobile-select wide-def-select">
                        <option value="">-- Skill --</option>
                    </select>
                    <div id="wide-def-preview-${defId}" class="wide-preview-box"></div>
                    <div class="duel-btn-row">
                        <button class="mobile-btn secondary sm btn-calc-def" data-id="${defId}">Check</button>
                        <button class="mobile-btn primary sm btn-decl-def" data-id="${defId}" disabled>Declare</button>
                    </div>
                </div>
            `;
        }).join('');

        modal.innerHTML = `
            <div class="overlay-header" style="background:#d32f2f;">
                <h3>💥 Wide Match Execution</h3>
                <button class="close-overlay" onclick="window.MobileMatch.closeMatchModal()">×</button>
            </div>
            <div class="overlay-content" style="padding:10px; max-height:85vh; overflow-y:auto;">
                <!-- Attacker -->
                <div class="duel-section attacker-bg">
                    <h4 onclick="window.Characters.showCharacterCard('${attackerId}')" style="cursor:pointer; text-decoration:underline;">
                        Attacker: ${attacker ? attacker.name : 'Unknown'} ℹ️
                    </h4>
                    <select id="wide-attacker-skill" class="mobile-select">
                         <option value="">-- Wide Skill --</option>
                    </select>
                    <div id="wide-attacker-preview" class="duel-preview-box"></div>
                    <div class="duel-btn-row">
                        <button id="wide-att-calc-btn" class="mobile-btn secondary sm">Check</button>
                        <button id="wide-att-declare-btn" class="mobile-btn primary sm" disabled>Declare</button>
                    </div>
                </div>

                <div style="margin:10px 0; font-weight:bold; text-align:center;">
                    Targeting ${defenderIds.length} Defenders
                </div>

                <!-- Defenders List -->
                <div class="wide-defenders-list-container">
                    ${defendersHtml}
                </div>

                <div class="duel-controls" style="margin-top:15px; padding-bottom:20px;">
                     <button id="wide-exec-btn" class="mobile-btn accent" disabled style="width:100%;">Execute Wide Match</button>
                </div>
            </div>
        `;

        modal.classList.remove('hidden');

        // Populate Attacker (Wide Only)
        this.populateSkills(attackerId, 'wide-attacker-skill', 'wide_attacker');

        // Populate Defenders (Exclude Wide/Immediate)
        defenderIds.forEach(defId => {
            this.populateSkills(defId, `wide-def-skill-${defId}`, 'wide_defender');
        });

        // Event Listeners
        // Attacker
        document.getElementById('wide-att-calc-btn').onclick = () => this.calculateWide(attackerId, null, 'attacker', false);
        document.getElementById('wide-att-declare-btn').onclick = () => this.calculateWide(attackerId, null, 'attacker', true);

        // Defenders (Event Delegation)
        const defContainer = modal.querySelector('.wide-defenders-list-container');
        defContainer.onclick = (e) => {
            const defId = e.target.dataset.id;
            if (!defId) return;

            if (e.target.classList.contains('btn-calc-def')) {
                this.calculateWide(attackerId, defId, 'defender', false);
            } else if (e.target.classList.contains('btn-decl-def')) {
                this.calculateWide(attackerId, defId, 'defender', true);
            }
        };

        // Execute
        document.getElementById('wide-exec-btn').onclick = () => this.executeWideMatch();

        this.updateWideExecutionState();
    },

    // --- Wide Match Logic Methods ---

    calculateWide(attackerId, defenderId, role, isCommit) {
        let skillId, prefix, actorId, targetId;

        if (role === 'attacker') {
            skillId = document.getElementById('wide-attacker-skill').value;
            prefix = 'wide_attacker';
            actorId = attackerId;
            // For wide attacker, target_id can be first defender id or null depending on python logic
            // Usually, target_id is just a placeholder for range checks, let's use first defender
            targetId = defenderId || (this.wideMatchData.defenderIds[0]);
        } else {
            skillId = document.getElementById(`wide-def-skill-${defenderId}`).value;
            prefix = `wide_defender_${defenderId}`; // Standard PC logic prefix
            actorId = defenderId;
            targetId = attackerId; // Target is attacker
        }

        if (!skillId) { alert(`Please select a skill.`); return; }

        console.log(`Wide ${isCommit ? 'Declaration' : 'Calculation'} (${role})`, skillId);


        const storedKey = role === 'attacker' ? 'attacker' : `defender_${defenderId}`;

        if (isCommit) {
            // Retrieve stored result for command data
            const stored = this.wideResults ? this.wideResults[storedKey] : null;

            if (!stored) {
                alert("Please click 'Check' first to calculate the skill.");
                return;
            }

            if (role === 'attacker') {
                this.wideDeclarations.attacker = true;
                document.getElementById('wide-att-declare-btn').disabled = true;

                if (window.socket) {
                    window.socket.emit('wide_attacker_declare', {
                        room: window.currentRoomName,
                        attacker_id: actorId, // optional if server infers
                        skill_id: skillId,
                        command: stored.command,
                        min: stored.min,
                        max: stored.max
                    });
                }
            } else {
                this.wideDeclarations.defenders[defenderId] = true;
                const item = document.getElementById(`wide-def-item-${defenderId}`);
                if (item) {
                    item.querySelector('.btn-decl-def').disabled = true;
                    item.querySelector('.def-status').textContent = "Ready";
                    item.querySelector('.def-status').style.color = "#4caf50";
                    item.classList.add('ready');
                }

                if (window.socket) {
                    window.socket.emit('wide_declare_skill', {
                        room: window.currentRoomName,
                        defender_id: actorId,
                        skill_id: skillId,
                        command: stored.command,
                        min: stored.min,
                        max: stored.max,
                        damage_range_text: stored.damage_range_text
                    });
                }
            }
            this.updateWideExecutionState();
        } else {
            // Calculation (Check)
            if (window.socket) {
                window.socket.emit('calculate_wide_skill', {
                    room: window.currentRoomName,
                    char_id: actorId,
                    skill_id: skillId
                });
            }
        }
    },

    handleWideSkillCalculated(data) {
        if (data.error) {
            alert(data.error);
            return;
        }

        let prefix = null;
        let storedKey = null;

        if (this.wideMatchData && data.char_id === this.wideMatchData.attackerId) {
            prefix = 'wide_attacker';
            storedKey = 'attacker';
        } else {
            prefix = `wide_defender_${data.char_id}`;
            storedKey = `defender_${data.char_id}`;
        }

        if (!this.wideResults) this.wideResults = {};
        this.wideResults[storedKey] = data;

        const previewData = {
            prefix: prefix,
            final_command: data.command,
            min_damage: data.min,
            max_damage: data.max,
            skill_details: data.skill_details || { description: '' },
            correction_details: data.correction_details || [],
            senritsu_dice_reduction: data.senritsu_dice_reduction
        };

        this.updatePreview(previewData);
    },

    updateWideExecutionState() {
        const execBtn = document.getElementById('wide-exec-btn');
        if (!execBtn) return;

        const attReady = this.wideDeclarations.attacker;
        const defsReady = Object.values(this.wideDeclarations.defenders).every(v => v === true);

        if (attReady && defsReady) {
            execBtn.disabled = false;
            execBtn.classList.add('pulse');
            execBtn.innerHTML = "Execute Match (All Ready)";
        } else {
            execBtn.disabled = true;
            execBtn.classList.remove('pulse');
            const total = Object.keys(this.wideDeclarations.defenders).length;
            const readyCount = Object.values(this.wideDeclarations.defenders).filter(v => v).length;
            execBtn.innerHTML = `Waiting... (Attacker: ${attReady ? 'OK' : 'No'}, Def: ${readyCount}/${total})`;
        }
    },

    executeWideMatch() {
        console.log("⚡ Executing Wide Match!");
        if (window.socket && this.wideMatchData) {
            window.socket.emit('execute_synced_wide_match', {
                room: window.currentRoomName
            });
            this.closeMatchModal();
        }
    },
};

// Expose to window for onclick handlers
window.MobileMatch = MobileMatch;

// --- Add Initializer for Open Wide Match ---
if (window.socket) {
    if (!window._mobileWideListenerAttached) {
        window.socket.on('open_wide_match_modal', (data) => {
            console.log("⚡ Open Wide Match Modal Signal:", data);
            MobileMatch.openWideMatchModal(data);
        });
        window._mobileWideListenerAttached = true;
    }
}
