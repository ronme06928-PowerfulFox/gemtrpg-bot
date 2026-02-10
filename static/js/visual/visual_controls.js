/* static/js/visual/visual_controls.js */

/**
 * Initializes map controls (zoom, pan, drag-and-drop)
 */
window.setupMapControls = function () {
    const mapViewport = document.getElementById('map-viewport');
    const gameMap = document.getElementById('game-map');
    if (!mapViewport || !gameMap) return;

    // Initialize Custom Drag Logic
    if (typeof setupBattleTokenDrag === 'function') setupBattleTokenDrag();

    if (window.visualMapHandlers.move) window.removeEventListener('mousemove', window.visualMapHandlers.move);
    if (window.visualMapHandlers.up) window.removeEventListener('mouseup', window.visualMapHandlers.up);

    mapViewport.ondragover = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; };
    mapViewport.ondrop = (e) => {
        e.preventDefault();
        // MouseEvent handles token dragging on map.
        // This handler receives drops from Action Dock (New Assignment).
        if (e.target.closest('.map-token')) return;

        const charId = e.dataTransfer.getData('text/plain');
        if (!charId) return;

        const rect = gameMap.getBoundingClientRect();
        const mapX = (e.clientX - rect.left) / visualScale;
        const mapY = (e.clientY - rect.top) / visualScale;

        let gridX = mapX / GRID_SIZE;
        let gridY = mapY / GRID_SIZE;

        if (gridX < 0) gridX = 0;
        if (gridY < 0) gridY = 0;

        gridX = Math.round(gridX * 100) / 100;
        gridY = Math.round(gridY * 100) / 100;

        if (typeof socket !== 'undefined' && currentRoomName) {
            // Optimistic UI Update
            const charIndex = battleState.characters.findIndex(c => c.id === charId);
            if (charIndex !== -1) {
                const char = battleState.characters[charIndex];
                char.x = gridX;
                char.y = gridY;
                renderVisualMap();
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

    // Cancel targeting mode on background click
    mapViewport.addEventListener('click', (e) => {
        if (e.target.closest('.map-token')) return;
        exitAttackTargetingMode();
    });
}

/**
 * Custom Drag Logic for Battle Tokens
 */
window.setupBattleTokenDrag = function () {
    const tokenLayer = document.getElementById('map-token-layer');
    if (!tokenLayer) return;

    let isDragging = false;
    let dragTarget = null;
    let startX, startY;
    let initialLeft, initialTop;
    let dragCharId = null;
    let hasMovedSignificantDistance = false;

    tokenLayer.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        const target = e.target.closest('.map-token');
        if (!target) return;
        if (e.target.closest('button')) return;
        if (e.target.closest('.token-badges')) return;

        e.preventDefault();
        dragTarget = target;
        dragCharId = target.dataset.id;

        const char = battleState.characters.find(c => c.id === dragCharId);
        if (!char) return;
        const isOwner = char.owner === currentUsername;
        const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
        if (!isOwner && !isGM) {
            dragTarget = null;
            return;
        }

        isDragging = true;
        hasMovedSignificantDistance = false;
        startX = e.clientX;
        startY = e.clientY;
        initialLeft = parseFloat(target.style.left || 0);
        initialTop = parseFloat(target.style.top || 0);

        target.style.zIndex = 1000;
        target.style.cursor = 'grabbing';
        target.classList.add('dragging');
        target.style.transition = 'none';
    });

    window.addEventListener('mousemove', (e) => {
        if (!isDragging || !dragTarget) return;
        e.preventDefault();

        const scale = window.visualScale || 1.0;
        const dx = (e.clientX - startX) / scale;
        const dy = (e.clientY - startY) / scale;

        if (!hasMovedSignificantDistance && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
            hasMovedSignificantDistance = true;
        }

        dragTarget.style.left = `${initialLeft + dx}px`;
        dragTarget.style.top = `${initialTop + dy}px`;
    });

    window.addEventListener('mouseup', (e) => {
        if (!isDragging || !dragTarget) return;
        isDragging = false;
        dragTarget.style.cursor = 'grab';
        dragTarget.classList.remove('dragging');

        const target = dragTarget;
        requestAnimationFrame(() => {
            target.style.transition = '';
        });

        if (hasMovedSignificantDistance) {
            window._dragBlockClick = true;
            setTimeout(() => { window._dragBlockClick = false; }, 100);
        }

        const currentLeft = parseFloat(dragTarget.style.left || 0);
        const currentTop = parseFloat(dragTarget.style.top || 0);

        let finalX = (currentLeft - TOKEN_OFFSET) / GRID_SIZE;
        let finalY = (currentTop - TOKEN_OFFSET) / GRID_SIZE;

        if (finalX < 0) finalX = 0;
        if (finalY < 0) finalY = 0;

        finalX = Math.round(finalX * 10000) / 10000;
        finalY = Math.round(finalY * 10000) / 10000;

        console.log(`[BattleDrag] Dropped at pixel(${currentLeft}, ${currentTop}) -> grid(${finalX}, ${finalY})`);

        // Check for collision with same position (optional, depending on logic)
        // Here we allow overlap.

        // Update Local State Optimistically
        const char = battleState.characters.find(c => c.id === dragCharId);
        if (char) {
            char.x = finalX;
            char.y = finalY;
        }

        if (typeof socket !== 'undefined' && currentRoomName) {
            const now = Date.now();
            if (!window._localCharPositions) window._localCharPositions = {};
            window._localCharPositions[dragCharId] = { x: finalX, y: finalY, ts: now };

            window._dragEndTime = Date.now();
            if (!window._lastSentMoveTS) window._lastSentMoveTS = {};
            window._lastSentMoveTS[dragCharId] = now;

            socket.emit('request_move_token', {
                room: currentRoomName,
                charId: dragCharId,
                x: finalX,
                y: finalY,
                ts: now
            });
        }

        dragTarget = null;
        dragCharId = null;
    });
}

/**
 * Enter Attack Targeting Mode
 */
window.enterAttackTargetingMode = function (attackerId) {
    if (window.attackTargetingState.isTargeting) return;

    window.attackTargetingState.isTargeting = true;
    window.attackTargetingState.attackerId = attackerId;

    const toast = document.createElement('div');
    toast.className = 'visual-toast info';
    toast.textContent = "攻撃対象を選択してください（対象をクリック）";
    toast.id = 'targeting-toast';
    toast.style.cssText = 'position:absolute; top:10%; left:50%; transform:translateX(-50%); padding:10px 20px; background:rgba(0,0,0,0.8); color:white; border-radius:20px; z-index:2000; pointer-events:none;';

    const viewport = document.getElementById('map-viewport') || document.body;
    viewport.appendChild(toast);

    const escHandler = (e) => {
        if (e.key === 'Escape') {
            exitAttackTargetingMode();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);

    if (typeof renderVisualMap === 'function') renderVisualMap();
};

/**
 * Exit Attack Targeting Mode
 */
window.exitAttackTargetingMode = function () {
    if (!window.attackTargetingState.isTargeting) return;

    window.attackTargetingState.isTargeting = false;
    window.attackTargetingState.attackerId = null;

    const toast = document.getElementById('targeting-toast');
    if (toast) toast.remove();

    if (typeof renderVisualMap === 'function') renderVisualMap();
};

console.log('[visual_controls] Loaded.');
