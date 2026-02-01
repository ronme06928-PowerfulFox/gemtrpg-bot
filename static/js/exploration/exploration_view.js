// static/js/exploration/exploration_view.js

// グローバル変数
if (!window.ExplorationView) {
    window.ExplorationView = {};
}

(function (scope) {
    let explorationState = null;
    let tachieElements = {}; // id -> element
    let dragTarget = null;
    let currentScale = 1.0; // Viewport scale (not implemented yet)

    // Panning & Zoom State
    let panX = 0;
    let panY = 0;
    let viewScale = 1.0;
    let isInitialized = false; // ★ Idempotency flag

    function setupExplorationView() {
        const viewport = document.getElementById('exploration-viewport');
        if (!viewport) return;

        // Prevent double setup on the SAME element
        if (viewport.dataset.isInitialized === 'true') {
            return;
        }
        viewport.dataset.isInitialized = 'true';

        // ★ State Reset (Fix for re-entry ghost elements)
        // SPA遷移でJS変数が残ってしまうため、DOM再生成時は変数もリセットする
        tachieElements = {};
        dragTarget = null;
        panX = 0;
        panY = 0;
        viewScale = 1.0;
        explorationState = null;

        console.log("Setting up Exploration View (State Reset Done)...");
        const world = document.getElementById('exploration-world');
        const layer = document.getElementById('exploration-token-layer'); // Use 'layer' to match setupDragEvents
        const bgUpdateBtn = document.getElementById('exp-bg-update-btn');

        // Safety check for critical elements
        if (!viewport || !world || !layer) {
            console.error("[ExplorationView] Critical elements missing during setup:", { viewport, world, layer });
            return;
        }

        // Zoom/Reset Controls
        const zoomInBtn = document.getElementById('exp-zoom-in-btn');
        const zoomOutBtn = document.getElementById('exp-zoom-out-btn');
        const resetBtn = document.getElementById('exp-reset-view-btn');

        // 背景変更ボタン (GMのみ)
        if (currentUserAttribute === 'GM') {
            if (bgUpdateBtn) bgUpdateBtn.style.display = 'block';
            if (bgUpdateBtn) bgUpdateBtn.onclick = openExplorationBgPicker;
        }

        // ドラッグイベント (トークン移動) - GMのみ
        // 戦闘モードと異なり、自由配置なのでピクセル単位で管理
        if (currentUserAttribute === 'GM') {
            setupDragEvents(layer);
        }

        // ★ Zoom Logic
        const updateTransform = () => {
            if (world) {
                world.style.transform = `translate(${panX}px, ${panY}px) scale(${viewScale})`;
            }
        };

        if (zoomInBtn) {
            zoomInBtn.onclick = () => {
                viewScale = Math.min(viewScale + 0.1, 5.0);
                updateTransform();
            };
        }
        if (zoomOutBtn) {
            zoomOutBtn.onclick = () => {
                viewScale = Math.max(viewScale - 0.1, 0.2);
                updateTransform();
            };
        }
        if (resetBtn) {
            resetBtn.onclick = () => {
                panX = 0; panY = 0; viewScale = 1.0;
                updateTransform();
            };
        }

        // ★ Pan Logic (Viewport Drag)
        if (viewport && world) {
            let isPanning = false;
            let startPanX, startPanY;
            let initialPanX, initialPanY;

            viewport.addEventListener('mousedown', (e) => {
                // Ignore if clicking on a tachie, control, or resize handle
                if (e.target.closest('.exploration-tachie') || e.target.closest('.map-btn') || e.target.closest('.resize-handle')) {
                    return;
                }
                e.preventDefault();
                isPanning = true;
                viewport.style.cursor = 'grabbing';
                startPanX = e.clientX;
                startPanY = e.clientY;
                initialPanX = panX;
                initialPanY = panY;
            });

            window.addEventListener('mousemove', (e) => {
                if (!isPanning) return;
                const dx = e.clientX - startPanX;
                const dy = e.clientY - startPanY;
                panX = initialPanX + dx;
                panY = initialPanY + dy;
                updateTransform();
            });

            window.addEventListener('mouseup', () => {
                if (isPanning) {
                    isPanning = false;
                    viewport.style.cursor = 'grab';
                }
            });

            // Wheel Zoom
            viewport.addEventListener('wheel', (e) => {
                if (e.target.closest('.exploration-tachie')) return;
                e.preventDefault();
                const delta = -Math.sign(e.deltaY) * 0.1;
                const newScale = Math.min(Math.max(viewScale + delta, 0.2), 5.0);
                viewScale = newScale;
                updateTransform();
            });

            isInitialized = true; // Mark as initialized
        }
    }

    function renderExplorationState(state) {
        if (!state.exploration) return; // Should be handled by main
        explorationState = state.exploration;

        updateBackground(state.exploration.backgroundImage);

        try {
            updateTachies(state);
        } catch (e) {
            console.error("[ExplorationView] Error updating tachies:", e);
        }
    }

    function updateBackground(url) {
        const bgDiv = document.getElementById('exploration-background');
        if (!bgDiv) return;

        if (url) {
            bgDiv.style.backgroundImage = `url('${url}')`;
            // ★ Improve quality
            bgDiv.style.backgroundSize = 'contain';
            bgDiv.style.backgroundPosition = 'center';
            bgDiv.style.backgroundRepeat = 'no-repeat';
            // bgDiv.style.imageRendering = 'auto'; // Optimize for photos, not pixel art
        } else {
            bgDiv.style.backgroundImage = 'none'; // またはデフォルト画像
            bgDiv.style.backgroundColor = '#202020';
        }
    }

    function updateTachies(state) {
        const layer = document.getElementById('exploration-token-layer');
        if (!layer) return;

        if (!state.characters) return;

        const locs = (state.exploration && state.exploration.tachie_locations) || {};
        const currentIds = new Set();

        // ★ Placed characters only (Sync with Battle Mode placement)
        // Hardened check: Ensure numeric comparison
        const validChars = state.characters.filter(c => {
            const cx = parseFloat(c.x);
            const cy = parseFloat(c.y);
            return !isNaN(cx) && !isNaN(cy) && cx >= 0 && cy >= 0;
        });

        console.log(`[ExplorationView] UpdateTachies. Total: ${state.characters.length}, Valid(Placed): ${validChars.length}`);

        // Safety: Ensure layer is on top
        if (layer) layer.style.zIndex = '100';

        validChars.forEach((char, index) => {
            currentIds.add(char.id);

            // ロケーション取得 (または自動配置)
            let loc = locs[char.id];

            // ★ Sync Position Logic: If Battle Grid Position exists but no Exploration Position, translate Grid -> Pixel
            if (!loc) {
                // Option 3: Place at the CENTER of the current view (User Viewport)
                // This ensures the token is always visible to the user, regardless of background size or pan.
                const viewport = document.getElementById('exploration-viewport');
                if (viewport) {
                    const vw = viewport.clientWidth;
                    const vh = viewport.clientHeight;

                    // Convert Screen Center (vw/2, vh/2) to World Coordinates
                    // WorldX = (ScreenX - panX) / viewScale
                    // Note: panX/panY/viewScale are available in the closure scope
                    const centerX = (vw / 2 - panX) / viewScale;
                    const centerY = (vh / 2 - panY) / viewScale;

                    // Apply a small random offset to prevent perfect stacking if multiple spawn
                    const offset = (index * 20);

                    loc = {
                        x: centerX + offset - 100, // -100 to center the 200px token roughly? No, origin is top-left
                        y: centerY + offset - 100,
                        scale: 1.0
                    };
                    console.log(`[ExplorationView] New placement for ${char.name} at View Center: (${loc.x}, ${loc.y})`);
                } else {
                    // Fallback if viewport missing (shouldn't happen)
                    const gridX = parseFloat(char.x);
                    const gridY = parseFloat(char.y);
                    loc = { x: gridX * 64, y: gridY * 64, scale: 1.0 };
                }

                // ★ Auto-Save this position to Backend (Idempotent: only if missing)
                const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
                const isOwner = (char.owner === currentUsername);

                if (isGM || isOwner) {
                    console.log(`[ExplorationView] Auto-saving initial pixel location for ${char.name}`);
                    if (window.socket) {
                        window.socket.emit('request_update_tachie_location', {
                            room: currentRoomName,
                            char_id: char.id,
                            x: loc.x,
                            y: loc.y,
                            scale: 1.0
                        });
                    }
                }
            }

            let el = tachieElements[char.id];
            if (!el) {
                console.log(`[ExplorationView] Creating new tachie for ${char.name}`);
                el = createTachieElement(char);
                layer.appendChild(el);
                tachieElements[char.id] = el;
            } else {
                // Determine current state
                const img = el.querySelector('img');
                const hasImage = !!img;
                const shouldHaveImage = !!char.image;

                // State Transition Check: Image <-> Placeholder OR Image URL Changed
                if (hasImage !== shouldHaveImage) {
                    console.log(`[ExplorationView] State transition for ${char.name} (hasImg: ${hasImage} -> ${shouldHaveImage}). Re-rendering content.`);
                    renderTachieContent(el, char); // Re-build internal structure
                } else if (hasImage && shouldHaveImage) {
                    // Both have image, check if src changed
                    const currentSrc = img.getAttribute('src');
                    // Handle relative/absolute path differences loosely or strict?
                    // Since we control setting, checking exact match of attribute is best.
                    if (currentSrc !== char.image) {
                        console.log(`[ExplorationView] Updating image for ${char.name}. Old: ${currentSrc}, New: ${char.image}`);
                        img.src = char.image;
                    }
                }
            }

            // Name Update (Always check)
            const nameLabel = el.querySelector('.exploration-tachie-label'); // Use class for safety
            if (nameLabel && nameLabel.textContent !== char.name) {
                nameLabel.textContent = char.name;
            }

            // 位置更新 (Ensure numbers)
            const x = parseFloat(loc.x) || 0;
            const y = parseFloat(loc.y) || 0;
            el.style.left = `${x}px`;
            el.style.top = `${y}px`;

            // スケール (Container Width Strategy)
            // char.tokenScale が未設定の場合は1.0
            const charSize = parseFloat(char.tokenScale) || 1.0;
            const BASE_WIDTH = 200; // Reduced from 250 to 200 (0.8x)
            const newWidth = BASE_WIDTH * charSize;

            el.style.width = `${newWidth}px`;
            el.style.height = 'auto'; // Allow height to adjust naturally

            // Remove old transform logic and ensure img/placeholder styles are correct
            const img = el.querySelector('img');
            if (img) {
                img.style.width = '100%';
                img.style.height = 'auto';
                img.style.transform = 'none';
            }
        });

        // ★ Removal Logic (Garbage Collection)
        // Remove elements for characters that are no longer in validChars (e.g. unplaced or deleted)
        Object.keys(tachieElements).forEach(id => {
            if (!currentIds.has(id)) {
                console.log(`[ExplorationView] Removing tachie for unplaced/deleted char ID: ${id}`);
                const el = tachieElements[id];
                if (el && el.parentNode) {
                    el.parentNode.removeChild(el);
                }
                delete tachieElements[id];
            }
        });
    }

    // Helper to render inner content
    function renderTachieContent(div, char) {
        div.innerHTML = ''; // Clear existing

        // Image or Placeholder
        if (char.image) {
            const img = document.createElement('img');
            img.src = char.image;
            img.setAttribute('src', char.image); // Explicitly set attribute for diffing
            img.style.width = '100%';
            img.style.height = 'auto';
            img.style.pointerEvents = 'none';
            img.style.userSelect = 'none';
            img.style.display = 'block';
            div.appendChild(img);
        } else {
            const placeholder = document.createElement('div');
            placeholder.style.width = '80px'; // 1/3 of ~240px, enough for text
            placeholder.style.height = '120px'; // Slightly smaller height too
            placeholder.style.background = 'rgba(255,255,255,0.5)';
            placeholder.style.display = 'flex';
            placeholder.style.alignItems = 'center';
            placeholder.style.justifyContent = 'center';
            placeholder.textContent = 'No Image';
            placeholder.style.borderRadius = '4px'; // Nice touch
            div.appendChild(placeholder);
        }

        // Name Label
        const nameLabel = document.createElement('div');
        nameLabel.className = 'exploration-tachie-label';
        nameLabel.textContent = char.name;
        nameLabel.style.background = 'rgba(0, 0, 0, 0.6)';
        nameLabel.style.color = 'white';
        nameLabel.style.padding = '2px 6px';
        nameLabel.style.borderRadius = '4px';
        nameLabel.style.marginTop = '0px';
        nameLabel.style.fontSize = '14px';
        nameLabel.style.whiteSpace = 'nowrap';
        nameLabel.style.textAlign = 'center';
        nameLabel.style.pointerEvents = 'none';
        nameLabel.style.userSelect = 'none';
        div.appendChild(nameLabel);
    }

    function createTachieElement(char) {
        const div = document.createElement('div');
        div.className = 'exploration-tachie';
        div.dataset.charId = char.id;
        div.style.position = 'absolute';
        div.style.display = 'flex';
        div.style.flexDirection = 'column';
        div.style.alignItems = 'center';

        // Safe Attribute Check
        const userAttr = (typeof currentUserAttribute !== 'undefined') ? currentUserAttribute : 'Player';
        div.style.cursor = (userAttr === 'GM') ? 'move' : 'default';
        div.style.zIndex = 10;

        renderTachieContent(div, char);

        // Double-click to show details
        div.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            if (window.showCharacterDetail) {
                window.showCharacterDetail(char.id);
            }
        });

        return div;
    }

    // --- ドラッグ処理 (GM Only) ---
    function setupDragEvents(layer) {
        let isDragging = false;
        let startX, startY;
        let initialLeft, initialTop;

        layer.addEventListener('mousedown', (e) => {
            const target = e.target.closest('.exploration-tachie');
            if (!target) return;

            e.preventDefault();
            dragTarget = target;
            isDragging = true;

            startX = e.clientX;
            startY = e.clientY;

            initialLeft = parseFloat(target.style.left || 0);
            initialTop = parseFloat(target.style.top || 0);

            target.style.zIndex = 100; // 最前面へ
        });

        window.addEventListener('mousemove', (e) => {
            if (!isDragging || !dragTarget) return;

            const dx = e.clientX - startX;
            const dy = e.clientY - startY;

            dragTarget.style.left = `${initialLeft + dx}px`;
            dragTarget.style.top = `${initialTop + dy}px`;
        });

        window.addEventListener('mouseup', (e) => {
            if (!isDragging || !dragTarget) return;

            isDragging = false;

            // 位置確定・送信
            const charId = dragTarget.dataset.charId;
            const finalX = parseFloat(dragTarget.style.left || 0);
            const finalY = parseFloat(dragTarget.style.top || 0);

            // Get current scale
            let currentScale = 1.0;
            const img = dragTarget.querySelector('img');
            if (img) {
                const transform = img.style.transform;
                const match = transform.match(/scale\(([^)]+)\)/);
                if (match) {
                    currentScale = parseFloat(match[1]);
                }
            }

            dragTarget.style.zIndex = 10;
            dragTarget = null;

            socket.emit('request_update_tachie_location', {
                room: currentRoomName,
                char_id: charId,
                x: finalX,
                y: finalY,
                scale: currentScale
            });
        });
    }

    // --- 背景変更モーダル ---
    function openExplorationBgPicker() {
        // 既存の image_picker.js を再利用
        // type="background" で背景画像のみを表示・アップロード
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

    // --- Public API ---
    scope.setup = setupExplorationView;
    scope.render = renderExplorationState;

})(window.ExplorationView);
