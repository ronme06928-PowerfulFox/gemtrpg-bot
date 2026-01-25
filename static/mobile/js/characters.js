/**
 * characters.js
 * Handles Character Token Rendering and Interactions for Mobile
 */

import { Timeline } from './timeline.js';

export const Characters = {
    tokenLayer: null,

    init() {
        console.log("♟️ Characters Module Initialized");
        this.tokenLayer = document.getElementById('map-token-layer');
    },

    renderTokens(characters) {
        if (!this.tokenLayer) return;
        this.tokenLayer.innerHTML = ''; // Clear existing

        if (!characters) return;

        console.log("♟️ Rendering Tokens:", characters.map(c => `${c.name} (${c.x},${c.y}) sz:${c.size}`));

        characters.forEach(char => {
            // Only render placed characters
            if (char.x < 0 || char.y < 0) {
                console.log(`Skipping ${char.name} (Not placed)`);
                return;
            }

            const token = document.createElement('div');
            token.className = 'map-token';
            token.id = `token-${char.id}`;
            token.dataset.id = char.id;

            // Check turn
            if (window.battleState && window.battleState.turn_char_id === char.id) {
                token.classList.add('current-turn');
            }

            // Position
            const gridSize = 90; // Standard Grid Size
            const size = char.size || 1; // Default to 1 if undefined

            token.style.left = `${char.x * gridSize}px`;
            token.style.top = `${char.y * gridSize}px`;
            token.style.width = `${size * gridSize}px`;
            token.style.height = `${size * gridSize}px`;
            token.style.borderColor = char.color || '#white';

            if (char.image) {
                token.style.backgroundImage = `url('${char.image}')`;
                token.style.backgroundSize = 'cover';
            } else {
                token.style.background = '#333';
                token.textContent = char.name.charAt(0);
                token.style.display = 'flex';
                token.style.alignItems = 'center';
                token.style.justifyContent = 'center';
                token.style.color = 'white';
                token.style.fontSize = `${(size * gridSize) / 2}px`;
            }

            // Status Bars (HP/MP/FP)
            const statsContainer = document.createElement('div');
            statsContainer.className = 'token-stats-bars';
            statsContainer.style.position = 'absolute';
            statsContainer.style.bottom = '-12px'; // Below token
            statsContainer.style.left = '0';
            statsContainer.style.width = '100%';
            statsContainer.style.display = 'flex';
            statsContainer.style.flexDirection = 'column';
            statsContainer.style.gap = '1px';

            // Helper to make a bar
            const createBar = (current, max, colorClass) => {
                if (max <= 0) return null;
                const bar = document.createElement('div');
                bar.className = `token-bar ${colorClass}`;
                bar.style.width = '100%';
                bar.style.height = '3px';
                bar.style.background = '#333';
                const fill = document.createElement('div');
                fill.style.width = `${Math.max(0, Math.min(100, (current / max) * 100))}%`;
                fill.style.height = '100%';
                if (colorClass === 'hp') fill.style.background = current < max * 0.3 ? '#f44336' : '#4caf50'; // Red if low, Green otherwise
                if (colorClass === 'mp') fill.style.background = '#2196f3'; // Blue
                if (colorClass === 'fp') fill.style.background = '#ffc107'; // Amber
                bar.appendChild(fill);
                return bar;
            };

            const hpBar = createBar(char.hp, char.maxHp, 'hp');
            if (hpBar) statsContainer.appendChild(hpBar);

            const mpBar = createBar(char.mp, char.maxMp, 'mp');
            if (mpBar) statsContainer.appendChild(mpBar);

            // FP is a state, find it
            const fpState = char.states.find(s => s.name === 'FP');
            const fpVal = fpState ? fpState.value : 0;
            // Assuming Max FP is something like 10 or 100? Legacy code seemed to assume 15-20 or purely value based.
            // Let's assume max 10 for bar visualization or just show if > 0
            if (fpVal > 0) {
                const fpBar = createBar(fpVal, 10, 'fp'); // Visualizing relative to 10 for now
                statsContainer.appendChild(fpBar);
            }

            token.appendChild(statsContainer);

            // Interaction
            this.setupTokenInteraction(token, char);

            this.tokenLayer.appendChild(token);
        });
    },

    setupTokenInteraction(token, char) {
        let isDragging = false;
        let startX, startY;
        let initialLeft, initialTop;
        let moved = false;

        const gridSize = 90;

        const onStart = (e) => {
            // Check if owner or GM
            const isOwner = char.owner === window.currentUsername;
            const isGM = window.currentUserAttribute === 'GM';
            if (!isOwner && !isGM) return;

            isDragging = true;
            moved = false;
            e.stopPropagation(); // Stop map panning

            const clientX = e.type.includes('touch') ? e.touches[0].clientX : e.clientX;
            const clientY = e.type.includes('touch') ? e.touches[0].clientY : e.clientY;

            startX = clientX;
            startY = clientY;
            initialLeft = parseFloat(token.style.left) || 0;
            initialTop = parseFloat(token.style.top) || 0;

            token.style.zIndex = 100; // Bring to front
            token.classList.add('dragging');
        };

        const onMove = (e) => {
            if (!isDragging) return;
            e.preventDefault();
            e.stopPropagation();

            const clientX = e.type.includes('touch') ? e.touches[0].clientX : e.clientX;
            const clientY = e.type.includes('touch') ? e.touches[0].clientY : e.clientY;

            const dx = (clientX - startX) / window.visualScale; // Adjust for map scale
            const dy = (clientY - startY) / window.visualScale;

            if (Math.abs(dx) > 5 || Math.abs(dy) > 5) moved = true;

            token.style.left = `${initialLeft + dx}px`;
            token.style.top = `${initialTop + dy}px`;
        };

        const onEnd = (e) => {
            if (!isDragging) return;
            isDragging = false;
            token.style.zIndex = '';
            token.classList.remove('dragging');
            e.stopPropagation();

            if (!moved) {
                // It was a click/tap, handled by onclick
                // Revert position change if any slight movement
                token.style.left = `${initialLeft}px`;
                token.style.top = `${initialTop}px`;
                return;
            }

            // Snap to grid
            const gridSize = 90; // PC matches 90px
            const currentLeft = parseFloat(token.style.left) || 0;
            const currentTop = parseFloat(token.style.top) || 0;

            const newX = Math.round(currentLeft / gridSize);
            const newY = Math.round(currentTop / gridSize);

            // Optimistic update
            token.style.left = `${newX * gridSize}px`;
            token.style.top = `${newY * gridSize}px`;

            console.log(`[Token] Moved to Grid(${newX}, ${newY})`);

            // Emit Move
            if (window.socket) {
                // Use PC-compatible event name and payload
                window.socket.emit('request_move_token', {
                    room: window.currentRoomName,
                    charId: char.id, // Server expects 'charId'
                    x: newX,
                    y: newY
                });
            }
        };

        // Touch
        token.addEventListener('touchstart', onStart, { passive: false });
        token.addEventListener('touchmove', onMove, { passive: false });
        token.addEventListener('touchend', onEnd);

        // Mouse (for PC/Testing)
        token.addEventListener('mousedown', onStart);
        window.addEventListener('mousemove', (e) => {
            if (isDragging) onMove(e);
        });
        window.addEventListener('mouseup', (e) => {
            if (isDragging) onEnd(e);
        });

        // Click for Viewing Details (Available to ALL)
        token.onclick = (e) => {
            e.stopPropagation();
            // Allow checking card for everyone
            this.showCharacterCard(char);
        };
    },

    showCharacterCard(charOrId) {
        let char = charOrId;
        if (typeof charOrId === 'string') {
            char = window.battleState.characters.find(c => c.id === charOrId);
        }
        if (!char) return;

        // Remove existing if any
        let existing = document.getElementById('mobile-char-card-overlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'mobile-char-card-overlay';
        overlay.className = 'mobile-overlay';
        overlay.style.zIndex = '2000'; // High z-index

        // Build Content for States
        let statesHtml = '';
        if (char.states) {
            char.states.forEach(s => {
                if (['HP', 'MP', 'FP'].includes(s.name)) return;
                if (s.value === 0) return;
                statesHtml += `<span class="buff-chip">${s.name}: ${s.value}</span>`;
            });
        }

        // Build Content for Special Buffs
        let specialBuffsHtml = '';
        if (char.special_buffs && char.special_buffs.length > 0) {
            char.special_buffs.forEach(b => {
                specialBuffsHtml += `<div class="special-buff-item">
                    <b>${b.name}</b> (${b.duration || b.round || 'INF'}R)
                    <div style="font-size:0.8em; color:#bbb;">${b.description || ''}</div>
                 </div>`;
            });
        }

        // Build Content for Params
        let paramsHtml = '<table class="props-table">';
        if (Array.isArray(char.params)) {
            char.params.forEach(p => {
                paramsHtml += `<tr><th>${p.label}</th><td>${p.value}</td></tr>`;
            });
        } else if (char.params && typeof char.params === 'object') {
            Object.entries(char.params).forEach(([k, v]) => {
                paramsHtml += `<tr><th>${k}</th><td>${v}</td></tr>`;
            });
        }
        paramsHtml += '</table>';

        const fpVal = (char.states.find(s => s.name === 'FP') || {}).value || 0;

        const isTurn = (window.battleState && window.battleState.turn_char_id === char.id);
        const canControl = (char.owner === window.currentUsername || window.currentUserAttribute === 'GM');

        // Check if any match modal is open to prevent recursion
        const wideModal = document.getElementById('mobile-wide-match-modal');
        const duelModal = document.getElementById('mobile-duel-modal');
        const isMatchOpen = (wideModal && !wideModal.classList.contains('hidden')) ||
            (duelModal && !duelModal.classList.contains('hidden'));

        let actionBtnHtml = '';
        if (isTurn && canControl && !isMatchOpen) {
            actionBtnHtml = `
                <div style="margin-bottom:15px;">
                    <button id="card-action-btn" class="mobile-btn primary pulse" style="width:100%; padding: 12px; font-size:1.1em;">⚔️ Action / Match</button>
                </div>
            `;
        }

        overlay.innerHTML = `
            <div class="overlay-header">
                <h3>${char.name}</h3>
                <button class="close-overlay" onclick="document.getElementById('mobile-char-card-overlay').remove()">×</button>
            </div>
            <div class="overlay-content" style="padding:15px;">
                ${actionBtnHtml}

                <div class="card-status-row">
                    <div class="stat-box hp">
                        <span class="label">HP</span>
                        <span class="val">${char.hp} / ${char.maxHp}</span>
                    </div>
                    <div class="stat-box mp">
                        <span class="label">MP</span>
                        <span class="val">${char.mp} / ${char.maxMp}</span>
                    </div>
                    <div class="stat-box fp">
                        <span class="label">FP</span>
                        <span class="val">${fpVal}</span>
                    </div>
                </div>

                ${statesHtml ? `<div class="card-section"><h4>States</h4><div class="buff-list">${statesHtml}</div></div>` : ''}

                ${specialBuffsHtml ? `<div class="card-section"><h4>Special Buffs</h4>${specialBuffsHtml}</div>` : ''}

                <div class="card-section">
                    <h4>Parameters</h4>
                    ${paramsHtml}
                </div>

                <div class="card-section">
                    <h4>Skills</h4>
                    <div class="skill-list-text" style="white-space: pre-wrap; font-size: 0.8em; color: #ccc;">${char.commands || 'None'}</div>
                </div>

                <!-- ID/System Info -->
                <div style="margin-top:20px; font-size:0.75em; color:#666; text-align:right;">
                    ID: ${char.id} | Owner: ${char.owner || 'None'}
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        // Bind Action Button
        if (isTurn && canControl) {
            const actBtn = document.getElementById('card-action-btn');
            if (actBtn) {
                // Check Active Match State for Resume
                const am = window.battleState.active_match;
                if (am && am.is_active && am.attacker_id === char.id) {
                    if (am.match_type === 'wide') {
                        // Wide Match Resume
                        actBtn.textContent = "⚡ Wide Match Execution";
                        actBtn.classList.remove('primary', 'pulse');
                        actBtn.classList.add('accent', 'pulse'); // Warning/Active color
                        actBtn.onclick = () => {
                            overlay.remove();
                            if (window.MobileMatch) window.MobileMatch.openWideMatchModal(am);
                        };
                    } else {
                        // Duel Resume (Simple Re-open for now)
                        actBtn.textContent = "⚔️ Resume Match";
                        actBtn.onclick = () => {
                            overlay.remove();
                            // Logic to re-open duel modal
                            if (window.MobileMatch) window.MobileMatch.openDuel(char.id, am.defender_id || (am.targets && am.targets[0]));
                        };
                    }
                } else if (char.isWideUser) {
                    // ★ Wide Match Execution (Initiation)
                    actBtn.textContent = "⚡ Wide Match Execution";
                    actBtn.classList.remove('primary', 'pulse');
                    actBtn.classList.add('accent', 'pulse');
                    actBtn.onclick = () => {
                        overlay.remove();
                        if (window.MobileMatch) window.MobileMatch.startWideMatch(char.id);
                    };
                } else {
                    // Normal Start
                    actBtn.textContent = "⚔️ Action / Match";
                    actBtn.classList.add('primary');
                    actBtn.classList.remove('accent');
                    actBtn.onclick = () => {
                        overlay.remove();
                        if (window.MobileMatch) {
                            window.MobileMatch.startDuelSetup(char.id);
                        }
                    };
                }
            }
        }
    }
};
