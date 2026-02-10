/* static/js/visual/visual_map.js */

/**
 * Updates the CSS transform of the map container based on current scale and offset.
 */
window.updateMapTransform = function () {
    const mapEl = document.getElementById('game-map');
    if (mapEl) mapEl.style.transform = `translate(${visualOffsetX}px, ${visualOffsetY}px) scale(${visualScale})`;
}

/**
 * Main Map Rendering Function
 * Handles background updates and token rendering (differential update).
 */
window.renderVisualMap = function () {
    const tokenLayer = document.getElementById('map-token-layer');
    if (!tokenLayer) return;

    updateMapTransform();

    // Background Image Handling
    const mapEl = document.getElementById('game-map');
    if (mapEl && battleState.battle_map_data) {
        const bgData = battleState.battle_map_data;
        if (bgData.background_image) {
            const newBg = `url('${bgData.background_image}')`;
            if (mapEl.style.backgroundImage !== newBg.replace(/'/g, '"') && mapEl.style.backgroundImage !== newBg) {
                mapEl.style.backgroundImage = newBg;
            }
            mapEl.style.backgroundSize = 'contain';
            mapEl.style.backgroundRepeat = 'no-repeat';
            mapEl.style.backgroundPosition = 'center';
        } else {
            mapEl.style.backgroundImage = '';
        }
    }

    if (typeof battleState === 'undefined' || !battleState.characters) return;
    const currentTurnId = battleState.turn_char_id || null;

    // 1. Map existing tokens
    const existingTokens = {};
    document.querySelectorAll('#map-token-layer .map-token').forEach(el => {
        if (el.dataset.id) {
            existingTokens[el.dataset.id] = el;
        }
    });

    // 2. Identify valid character IDs
    const validCharIds = new Set();

    battleState.characters.forEach(char => {
        if (char.x >= 0 && char.y >= 0 && char.hp > 0) {
            validCharIds.add(char.id);

            // Global Local State Override (Optimistic UI)
            if (window._localCharPositions && window._localCharPositions[char.id]) {
                const localMove = window._localCharPositions[char.id];
                const serverTS = char.last_move_ts || 0;

                if (serverTS < localMove.ts) {
                    char.x = localMove.x;
                    char.y = localMove.y;
                }
            }

            let token = existingTokens[char.id];

            if (token) {
                // Update Existing Token
                if (char.id === currentTurnId) {
                    if (!token.classList.contains('active-turn')) token.classList.add('active-turn');
                } else {
                    if (token.classList.contains('active-turn')) token.classList.remove('active-turn');
                }

                // Update Position (Skip if dragging)
                const isDragging = token.classList.contains('dragging');
                const inCooldown = window._dragEndTime && (Date.now() - window._dragEndTime < 100);

                if (!isDragging && !inCooldown) {
                    const left = char.x * GRID_SIZE + TOKEN_OFFSET;
                    const top = char.y * GRID_SIZE + TOKEN_OFFSET;
                    const newLeft = `${left}px`;
                    const newTop = `${top}px`;

                    if (token.style.left !== newLeft || token.style.top !== newTop) {
                        token.style.left = newLeft;
                        token.style.top = newTop;
                    }
                }

                // Update internals
                updateTokenVisuals(token, char);

            } else {
                // Create New Token
                token = createMapToken(char);
                if (char.id === currentTurnId) token.classList.add('active-turn');
                tokenLayer.appendChild(token);
            }
        }
    });

    // 3. Remove invalid tokens
    Object.keys(existingTokens).forEach(id => {
        if (!validCharIds.has(id)) {
            const el = existingTokens[id];
            el.remove();
        }
    });

    // Inject GM Background Settings Button
    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
    if (isGM && !document.getElementById('battle-bg-settings-btn')) {
        const zIn = document.getElementById('zoom-in-btn');
        if (zIn && zIn.parentElement) {
            const btn = document.createElement('button');
            btn.id = 'battle-bg-settings-btn';
            btn.innerHTML = '🖼️'; // Image Icon
            btn.title = '戦闘背景設定';
            btn.className = 'map-control-btn';
            btn.style.marginLeft = '5px';
            btn.onclick = () => {
                if (typeof openImagePicker === 'function') {
                    openImagePicker((selectedImage) => {
                        socket.emit('request_update_battle_background', {
                            room: currentRoomName,
                            imageUrl: selectedImage.url,
                            scale: 1.0,
                            offsetX: 0,
                            offsetY: 0
                        });
                    }, 'background');
                } else {
                    const url = prompt("背景画像のURLを入力してください:", battleState.battle_map_data?.background_image || "");
                    if (url) {
                        socket.emit('request_update_battle_background', {
                            room: currentRoomName,
                            imageUrl: url
                        });
                    }
                }
            };
            zIn.parentElement.appendChild(btn);
        }
    }
}

// Helper: Update token visual contents (bars, badges, etc)
function updateTokenVisuals(token, char) {
    // HP Bar
    const hpRow = token.querySelector('.token-stat-row[data-stat="HP"]');
    if (hpRow) {
        const bar = hpRow.querySelector('.token-bar-fill.hp');
        const val = hpRow.querySelector('.token-bar-value');
        if (bar) bar.style.width = `${Math.min(100, Math.max(0, (char.hp / char.maxHp) * 100))}%`;
        if (val) val.textContent = char.hp;
    }

    // MP Bar
    const mpRow = token.querySelector('.token-stat-row[data-stat="MP"]');
    if (mpRow) {
        const bar = mpRow.querySelector('.token-bar-fill.mp');
        const val = mpRow.querySelector('.token-bar-value');
        if (bar) bar.style.width = `${Math.min(100, Math.max(0, (char.mp / char.maxMp) * 100))}%`;
        if (val) val.textContent = char.mp;
    }

    // FP Badge Update
    const fpBadge = token.querySelector('.fp-badge');
    if (fpBadge) {
        let fpVal = char.fp;
        if (fpVal === undefined && char.states) {
            const s = char.states.find(st => st.name === 'FP');
            fpVal = s ? s.value : 0;
        }
        if (fpVal === undefined) fpVal = 0;

        const currentText = fpBadge.textContent.trim();
        if (currentText != fpVal) {
            fpBadge.textContent = fpVal;
            fpBadge.title = `FP: ${fpVal}`;
        }
    }

    // Image Update
    const bodyEl = token.querySelector('.token-body');
    if (bodyEl) {
        const currentImg = bodyEl.querySelector('img');
        if (char.image) {
            if (currentImg) {
                if (!currentImg.src.includes(char.image)) {
                    currentImg.src = char.image;
                }
            } else {
                const span = bodyEl.querySelector('span');
                if (span) span.remove();
                const img = document.createElement('img');
                img.src = char.image;
                img.loading = "lazy";
                img.style.width = "100%";
                img.style.height = "100%";
                img.style.objectFit = "cover";
                bodyEl.prepend(img);
            }
        } else {
            if (currentImg) currentImg.remove();
            let span = bodyEl.querySelector('span');
            if (!span) {
                span = document.createElement('span');
                span.style.cssText = "font-size: 3em; font-weight: bold; color: #555; display: flex; align-items: center; justify-content: center; height: 100%;";
                bodyEl.prepend(span);
            }
            if (span.textContent !== char.name.charAt(0)) {
                span.textContent = char.name.charAt(0);
            }
        }
    }

    // Badge Update
    const badgesContainer = token.querySelector('.token-badges');
    if (badgesContainer) {
        badgesContainer.innerHTML = generateMapTokenBadgesHTML(char);
    }

    // Name Label
    const nameLabel = token.querySelector('.token-name-label');
    if (nameLabel && nameLabel.textContent !== char.name) {
        nameLabel.textContent = char.name;
    }

    token.style.filter = 'none';
}

/**
 * Partial Update for Token Visuals (Stat Change Event)
 */
window.updateCharacterTokenVisuals = function (data) {
    console.log('[updateCharacterTokenVisuals] Called with data:', data);

    if (!data || !data.char_id) {
        console.warn('[updateCharacterTokenVisuals] Invalid data:', data);
        return;
    }

    const { char_id, stat, new_value, old_value, max_value, source } = data;
    console.log(`[updateCharacterTokenVisuals] Extracted: char_id=${char_id}, stat=${stat}, new=${new_value}, old=${old_value}, max=${max_value}, source=${source}`);

    const token = document.querySelector(`.map-token[data-id="${char_id}"]`);
    if (!token) {
        console.debug(`[updateCharacterTokenVisuals] Token not found for char_id: ${char_id}`);
        return;
    }

    // Update battleState cache
    if (typeof battleState !== 'undefined' && battleState.characters) {
        const char = battleState.characters.find(c => c.id === char_id);
        if (char) {
            if (stat === 'HP') char.hp = new_value;
            else if (stat === 'MP') char.mp = new_value;
            else {
                const stateObj = char.states?.find(s => s.name === stat);
                if (stateObj) stateObj.value = new_value;
            }
        }
    }

    if (stat === 'HP' || stat === 'MP') {
        const barClass = stat === 'HP' ? 'hp' : 'mp';
        const barFill = token.querySelector(`.token-bar-fill.${barClass}`);
        const barContainer = token.querySelector(`.token-bar[title^="${stat}:"]`);

        if (barFill && max_value) {
            const percentage = Math.max(0, Math.min(100, (new_value / max_value) * 100));
            barFill.style.width = `${percentage}%`;
            if (barContainer) {
                barContainer.title = `${stat}: ${new_value}/${max_value}`;
            }
        }

        if (old_value !== undefined && old_value !== new_value) {
            const diff = new_value - old_value;
            showFloatingText(token, diff, stat, source);
        }
    } else {
        const internalStats = ['hidden_skills', 'gmOnly', 'color', 'image', 'owner', 'commands', 'params'];
        if (internalStats.includes(stat)) return;

        if (old_value !== undefined && old_value !== new_value) {
            const diff = new_value - old_value;
            showFloatingText(token, diff, stat, source);
        }
        console.debug(`[updateCharacterTokenVisuals] State change detected: ${stat}, triggering partial re-render`);
    }
}

/**
 * Show Floating Text for Damage/Heal
 */
window.showFloatingText = function (token, diff, stat, source = null) {
    const mapViewport = document.getElementById('map-viewport');
    if (!mapViewport) return;

    const charId = token.dataset.id;
    if (!window.floatingTextCounters) window.floatingTextCounters = {};
    if (!window.floatingTextCounters[charId]) window.floatingTextCounters[charId] = 0;

    const currentOffset = window.floatingTextCounters[charId];
    window.floatingTextCounters[charId]++;

    const floatingText = document.createElement('div');
    floatingText.className = 'floating-damage-text';

    const isDamage = diff < 0;
    const absValue = Math.abs(diff);

    let displayText = '';
    if (stat === 'HP') {
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
        displayText = isDamage ? `${stat} -${absValue}` : `${stat} +${absValue}`;
        floatingText.classList.add('state-change');
    }
    floatingText.textContent = displayText;

    if (!source) {
        if (stat === 'HP') {
            floatingText.classList.add(isDamage ? 'damage' : 'heal');
        } else if (stat === 'MP') {
            floatingText.classList.add(isDamage ? 'mp-cost' : 'mp-heal');
        }
    } else {
        floatingText.classList.add(`src-${source}`);
    }

    const tokenRect = token.getBoundingClientRect();
    const viewportRect = mapViewport.getBoundingClientRect();

    const relativeLeft = tokenRect.left - viewportRect.left + mapViewport.scrollLeft + (tokenRect.width / 2);
    const verticalOffset = currentOffset * 25;
    const relativeTop = tokenRect.top - viewportRect.top + mapViewport.scrollTop + (tokenRect.height / 2) - verticalOffset;

    floatingText.style.left = `${relativeLeft}px`;
    floatingText.style.top = `${relativeTop}px`;

    mapViewport.appendChild(floatingText);

    setTimeout(() => {
        if (floatingText.parentNode) floatingText.parentNode.removeChild(floatingText);
        if (window.floatingTextCounters && window.floatingTextCounters[charId] > 0) {
            window.floatingTextCounters[charId]--;
        }
    }, 3000);
}

/**
 * Generates badge HTML for map tokens
 */
window.generateMapTokenBadgesHTML = function (char) {
    let iconsHtml = '';
    if (char.states) {
        let badgeCount = 0;
        const badgesPerRow = 3;

        char.states.forEach(s => {
            if (['HP', 'MP', 'FP'].includes(s.name)) return;
            if (s.value === 0) return;

            const config = STATUS_CONFIG[s.name];
            const row = Math.floor(badgeCount / badgesPerRow);
            const col = badgeCount % badgesPerRow;

            const rightPos = -10 + (col * 30);
            const topPos = -25 - (row * 36);

            const badgeStyle = `
                width: 34px; height: 34px;
                display: flex; align-items: center; justify-content: center;
                border-radius: 50%; box-shadow: 0 3px 5px rgba(0,0,0,0.5);
                background: #fff; border: 2px solid #ccc;
                position: absolute; right: ${rightPos}px; top: ${topPos}px; z-index: ${5 + row};
            `;
            const countStyle = `
                position: absolute; bottom: -5px; right: -5px;
                background: ${config ? config.color : (s.value > 0 ? '#28a745' : '#dc3545')};
                color: white; font-size: 12px; font-weight: bold;
                padding: 0 3px; border-radius: 44px; border: 1px solid white;
            `;

            if (config) {
                iconsHtml += `
                    <div class="status-badge" style="${badgeStyle} border-color: ${config.borderColor};" title="${s.name}: ${s.value}">
                        <img src="images/${config.icon}" loading="lazy" style="width:100%; height:100%; border-radius:50%;">
                        <div style="${countStyle}">${s.value}</div>
                    </div>`;
            } else {
                const arrow = s.value > 0 ? '▲' : '▼';
                const color = s.value > 0 ? '#28a745' : '#dc3545';
                iconsHtml += `
                    <div class="status-badge" style="${badgeStyle} color:${color}; border-color:${color}; font-weight:bold; background:#fff; font-size:20px;" title="${s.name}: ${s.value}">
                        ${arrow}
                        <div style="${countStyle}">${s.value}</div>
                    </div>`;
            }
            badgeCount++;
        });
    }
    return iconsHtml;
}

/**
 * Creates the DOM element for a map token
 */
window.createMapToken = function (char) {
    const token = document.createElement('div');

    let colorClass = 'NPC';
    let borderColor = '#999';

    if (char.name && char.name.includes('味方')) {
        colorClass = 'PC';
        borderColor = '#007bff';
    } else if (char.name && char.name.includes('敵')) {
        colorClass = 'Enemy';
        borderColor = '#dc3545';
    } else if (char.color) {
        colorClass = char.color;
        borderColor = char.color;
    }

    token.className = `map-token ${colorClass}`;
    token.dataset.id = char.id;

    const tokenScale = char.tokenScale || 1.0;
    const baseSize = 132;
    const scaledSize = baseSize * tokenScale;

    token.style.width = `${scaledSize}px`;
    token.style.height = `${scaledSize}px`;
    token.style.borderRadius = "18px 18px 0 0";
    token.style.border = `4px solid ${borderColor}`;
    token.style.boxShadow = "0 4px 8px rgba(0,0,0,0.4)";
    token.style.overflow = "visible";
    token.style.left = `${char.x * GRID_SIZE + TOKEN_OFFSET}px`;
    token.style.top = `${char.y * GRID_SIZE + TOKEN_OFFSET}px`;
    token.style.position = 'absolute';

    const maxHp = char.maxHp || 1; const hp = char.hp || 0;
    const hpPer = Math.max(0, Math.min(PERCENTAGE_MAX, (hp / maxHp) * PERCENTAGE_MAX));

    const maxMp = char.maxMp || 1; const mp = char.mp || 0;
    const mpPer = Math.max(0, Math.min(PERCENTAGE_MAX, (mp / maxMp) * PERCENTAGE_MAX));

    const fpState = char.states ? char.states.find(s => s.name === 'FP') : null;
    const fp = fpState ? fpState.value : 0;

    let iconsHtml = generateMapTokenBadgesHTML(char);
    const isCurrentTurn = (battleState.turn_char_id === char.id);

    // Wide Match Button
    let wideBtnHtml = '';
    const isWideMatchExecuting = battleState.active_match && battleState.active_match.is_active && battleState.active_match.match_type === 'wide';
    if (isCurrentTurn && char.isWideUser && !isWideMatchExecuting) {
        wideBtnHtml = '<button class="wide-attack-trigger-btn" style="transform: scale(1.2); top: -40px; font-size: 1.1em;" onclick="event.stopPropagation(); window._dragBlockClick = true; openSyncedWideMatchModal(\'' + char.id + '\');">⚡ 広域</button>';
    }

    let tokenBodyStyle = `width: 100%; height: 100%; border-radius: 14px 14px 0 0; overflow: hidden; position: relative; background: #eee;`;
    let tokenBodyContent = `<span style="font-size: 3em; font-weight: bold; color: #555; display: flex; align-items: center; justify-content: center; height: 100%;">${char.name.charAt(0)}</span>`;

    if (char.image) {
        tokenBodyContent = `<img src="${char.image}" loading="lazy" style="width:100%; height:100%; object-fit:cover;">`;
    }

    const statusOverlayStyle = `
        position: absolute; bottom: 0; left: 0; width: 100%;
        background: rgba(0, 0, 0, 0.75);
        padding: 5px; box-sizing: border-box;
        border-bottom-left-radius: 0; border-bottom-right-radius: 0;
        display: flex; flex-direction: column; gap: 4px;
        pointer-events: none;
    `;

    const nameLabelStyle = `
        position: absolute;
        top: ${scaledSize + 6}px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0,0,0,0.7);
        color: white;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 16px;
        font-weight: bold;
        white-space: nowrap;
        z-index: 101;
        text-shadow: 1px 1px 2px black;
        pointer-events: none;
    `;
    const nameLabelHtml = `<div class="token-name-label" style="${nameLabelStyle}">${char.name}</div>`;

    const createBar = (cls, per, val, max, label) => `
        <div class="token-stat-row" data-stat="${label}" style="display:flex; align-items:center; height: 14px; gap: 4px;">
            <div style="font-size:14px; font-weight:bold; color:#ccc; width:22px; text-align:left; line-height:1;">${label}</div>
            <div style="flex-grow:1; background:#444; height:100%; border-radius:3px; position:relative; overflow:hidden;">
                <div class="${cls}" style="width:${per}%; height:100%; position:absolute; left:0; top:0; border-radius:3px;"></div>
            </div>
            <div class="token-bar-value" style="font-size:18px; color:white; font-weight:bold; text-shadow:1px 1px 1px #000; min-width:30px; text-align:right; line-height:1;">${val}</div>
        </div>
    `;

    const statusHtml = `
        <div style="${statusOverlayStyle}">
            ${createBar('token-bar-fill hp', hpPer, hp, maxHp, 'HP')}
            ${createBar('token-bar-fill mp', mpPer, mp, maxMp, 'MP')}
        </div>
    `;

    const fpBadgeHtml = `
        <div class="fp-badge" style="
            position: absolute; top: -12px; left: -12px;
            width: 32px; height: 32px;
            background: #ff9800;
            border-radius: 50%;
            border: 3px solid white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.5);
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: bold; font-size: 16px;
            z-index: 20;
        " title="FP: ${fp}">
            ${fp}
        </div>
    `;

    token.innerHTML = `
        ${wideBtnHtml}
        ${fpBadgeHtml}
        <div class="token-body" style="${tokenBodyStyle}">
            ${tokenBodyContent}
            ${statusHtml}
        </div>
        ${nameLabelHtml}
        <div class="token-badges" style="position: absolute; top:0; right:0; width:0; height:0;">
            ${iconsHtml}
        </div>
    `;

    token.draggable = false;
    token.style.cursor = 'grab';

    token.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        exitAttackTargetingMode();
        showCharacterDetail(char.id);
    });

    token.addEventListener('click', (e) => {
        e.stopPropagation();
        console.log(`[Click] Token clicked: ${char.name} (${char.id})`);

        if (window._dragBlockClick) {
            console.log('[Click] ❌ Blocked due to recent drag');
            return;
        }

        document.querySelectorAll('.map-token').forEach(t => t.style.zIndex = '');
        token.style.zIndex = 500;

        // Active Match Expansion
        if (battleState.active_match && battleState.active_match.is_active) {
            const am = battleState.active_match;
            if (am.attacker_id === char.id || am.defender_id === char.id) {
                if (typeof expandMatchPanel === 'function') expandMatchPanel();
                return;
            }
        }

        // Targeting Mode
        if (window.attackTargetingState.isTargeting && window.attackTargetingState.attackerId) {
            const attackerId = window.attackTargetingState.attackerId;
            if (attackerId === char.id) return; // Self target

            const attackerChar = battleState.characters.find(c => c.id === attackerId);
            const attackerName = attackerChar ? attackerChar.name : "不明";
            const isOwner = attackerChar && attackerChar.owner === currentUsername;
            const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

            if (!isOwner && !isGM) {
                alert("キャラクターの所有者またはGMのみがマッチを開始できます。");
                exitAttackTargetingMode();
                return;
            }

            if (confirm(`【攻撃確認】\n「${attackerName}」が「${char.name}」に攻撃を仕掛けますか？`)) {
                openDuelModal(attackerId, char.id);
            }
            exitAttackTargetingMode();
            return;
        }

        // Activate Targeting Mode (Turn Player)
        const currentTurnCharId = battleState.turn_char_id;
        const isNowTurn = (currentTurnCharId === char.id);

        if (isNowTurn) {
            const isOwner = char.owner === currentUsername;
            const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

            if (!isOwner && !isGM) return;

            if (window.matchActionInitiated) {
                alert("1ターンに1回のみマッチを開始できます。\n次のターンまでお待ちください。");
                return;
            }

            const isWideMatchExecuting = battleState.active_match && battleState.active_match.is_active && battleState.active_match.match_type === 'wide';
            if (char.isWideUser && !isWideMatchExecuting) {
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

window.selectVisualToken = function (charId) {
    document.querySelectorAll('.map-token').forEach(el => el.classList.remove('selected'));
    const token = document.querySelector(`.map-token[data-id="${charId}"]`);
    if (token) token.classList.add('selected');
}

/**
 * Generate Status Icons (Used by Duel Panel as well)
 */
window.generateStatusIconsHTML = function (char) {
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

// --- Menu Functions ---

window.toggleCharSettingsMenu = function (charId, btnElement) {
    let menu = document.getElementById('char-settings-menu');
    if (menu) {
        menu.remove();
        return;
    }

    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    menu = document.createElement('div');
    menu.id = 'char-settings-menu';
    menu.style.cssText = 'position:absolute; background:white; border:1px solid #ccc; border-radius:4px; box-shadow:0 2px 10px rgba(0,0,0,0.2); z-index:10000; min-width:180px;';

    const rect = btnElement.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 5}px`;
    menu.style.left = `${rect.left + window.scrollX - 100}px`;

    const ownerName = char.owner || '不明';
    const ownerDisplay = document.createElement('div');
    ownerDisplay.style.cssText = 'padding:8px 12px; margin-bottom:4px; background:#f0f0f0; font-size:0.85em; border-bottom:1px solid #ddd;';
    ownerDisplay.innerHTML = `<strong>所有者:</strong> ${ownerName}`;
    menu.appendChild(ownerDisplay);

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

    const imageSection = document.createElement('div');
    imageSection.style.cssText = 'padding:8px 12px; margin-bottom:4px; border-bottom:1px solid #ddd;';
    imageSection.innerHTML = `
        <div style="margin-bottom:5px; font-size:0.9em; font-weight:bold;">立ち絵画像</div>
        <button id="settings-image-picker-btn" style="width:100%; padding:8px; background:#007bff; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">画像を変更</button>
    `;
    menu.appendChild(imageSection);

    const imagePickerBtn = imageSection.querySelector('#settings-image-picker-btn');
    if (imagePickerBtn) {
        imagePickerBtn.onclick = () => {
            openImagePicker((selectedImage) => {
                socket.emit('request_state_update', {
                    room: currentRoomName,
                    charId: charId,
                    statName: 'image',
                    newValue: selectedImage.url
                });
                menu.remove();
            });
        };
    }

    const styleMenuButton = (btn) => {
        btn.style.cssText = 'display:block; width:100%; padding:8px 12px; border:none; background:none; text-align:left; cursor:pointer;';
        btn.onmouseover = () => btn.style.background = '#f5f5f5';
        btn.onmouseout = () => btn.style.background = 'none';
        return btn;
    };

    const withdrawBtn = document.createElement('button');
    withdrawBtn.textContent = '未配置に戻す';
    styleMenuButton(withdrawBtn);
    withdrawBtn.onclick = () => {
        if (confirm('このキャラクターを未配置状態に戻しますか？')) {
            withdrawCharacter(charId);
            menu.remove();
            const backdrop = document.getElementById('char-detail-modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    };
    menu.appendChild(withdrawBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'キャラクターを削除';
    styleMenuButton(deleteBtn);
    deleteBtn.style.color = '#dc3545';
    deleteBtn.onclick = () => {
        if (confirm(`本当に「${char.name}」を削除しますか？`)) {
            socket.emit('request_delete_character', { room: currentRoomName, charId: charId });
            menu.remove();
            const backdrop = document.getElementById('char-detail-modal-backdrop');
            if (backdrop) backdrop.remove();
        }
    };
    menu.appendChild(deleteBtn);

    const transferBtn = document.createElement('button');
    transferBtn.textContent = '所有権を譲渡 ▶';
    styleMenuButton(transferBtn);
    transferBtn.onclick = (e) => {
        e.stopPropagation();
        showTransferSubMenu(charId, menu, transferBtn);
    };
    menu.appendChild(transferBtn);

    document.body.appendChild(menu);

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

window.withdrawCharacter = function (charId) {
    if (!charId || !currentRoomName) return;
    socket.emit('request_move_character', {
        room: currentRoomName,
        character_id: charId,
        x: -1,
        y: -1
    });
}

window.showTransferSubMenu = function (charId, parentMenu, parentBtn) {
    const existingSubMenu = document.getElementById('transfer-sub-menu');
    if (existingSubMenu) { existingSubMenu.remove(); return; }

    const subMenu = document.createElement('div');
    subMenu.id = 'transfer-sub-menu';
    subMenu.style.cssText = 'position:absolute; background:white; border:1px solid #ccc; border-radius:4px; box-shadow:0 2px 10px rgba(0,0,0,0.2); z-index:10001; min-width:200px;';

    const rect = parentBtn.getBoundingClientRect();
    subMenu.style.top = `${rect.top + window.scrollY}px`;
    subMenu.style.left = `${rect.right + window.scrollX + 5}px`;

    const styleSubMenuItem = (item) => {
        item.style.cssText = 'display:block; width:100%; padding:8px 12px; border:none; background:none; text-align:left; cursor:pointer;';
        item.onmouseover = () => item.style.background = '#f5f5f5';
        item.onmouseout = () => item.style.background = 'none';
        return item;
    };

    const allUsersBtn = document.createElement('button');
    allUsersBtn.textContent = '全ユーザーから選択';
    styleSubMenuItem(allUsersBtn);
    allUsersBtn.onclick = () => {
        openTransferOwnershipModal(charId, 'all');
        subMenu.remove();
        parentMenu.remove();
    };
    subMenu.appendChild(allUsersBtn);

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

window.openTransferOwnershipModal = function (charId, mode) {
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;

    const existing = document.getElementById('transfer-modal-backdrop');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'transfer-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.style.display = 'flex';

    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';
    modalContent.style.cssText = 'max-width:400px; width:90%; padding:20px;';

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

    modalContent.querySelector('#transfer-cancel-btn').onclick = () => backdrop.remove();
    backdrop.onclick = (e) => { if (e.target === backdrop) backdrop.remove(); };

    const userListContainer = modalContent.querySelector('#user-list-container');
    let fetchUrl = (mode === 'all') ? '/api/admin/users' : `/api/get_room_users?room=${encodeURIComponent(currentRoomName)}`;

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

window.toggleBuffDesc = function (elementId) {
    const el = document.getElementById(elementId);
    if (el) el.style.display = (el.style.display === 'none') ? 'block' : 'none';
}

console.log('[visual_map] Loaded.');
