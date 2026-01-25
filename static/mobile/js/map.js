/**
 * map.js
 * Handles Map Rendering and Interaction (Panning/Zooming) for Mobile
 */

export const MobileMap = {
    viewport: null,
    isDragging: false,
    startX: 0,
    startY: 0,
    initialOffsetX: 0,
    initialOffsetY: 0,

    init() {
        console.log("🗺️ MobileMap Module Initialized");
        this.viewport = document.getElementById('map-viewport');

        // Default Zoom
        window.visualScale = 1.0;

        this.setupControls();
        this.centerMap();
        window.addEventListener('resize', () => this.centerMap());

        // Bind UI Buttons
        const zIn = document.getElementById('btn-zoom-in');
        const zOut = document.getElementById('btn-zoom-out');
        const zFocus = document.getElementById('btn-focus-token');

        if (zIn) zIn.onclick = () => this.zoomMap(0.2);
        if (zOut) zOut.onclick = () => this.zoomMap(-0.2);
        if (zFocus) zFocus.onclick = () => this.focusMyToken();
    },

    setupControls() {
        if (!this.viewport) return;

        let initialPinchDistance = null;
        let initialScale = 1.0;

        // Touch Events
        this.viewport.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                // Pinch Start
                this.isDragging = false; // Disable panning while pinching
                initialPinchDistance = this.getDistance(e.touches);
                initialScale = window.visualScale || 1.0;
                e.preventDefault();
            } else if (e.touches.length === 1) {
                // Pan Start
                this.isDragging = true;
                this.startX = e.touches[0].clientX;
                this.startY = e.touches[0].clientY;
                this.initialOffsetX = window.visualOffsetX || 0;
                this.initialOffsetY = window.visualOffsetY || 0;
            }
        }, { passive: false });

        this.viewport.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2 && initialPinchDistance) {
                // Pinch Move
                e.preventDefault();
                const dist = this.getDistance(e.touches);
                const delta = dist - initialPinchDistance;

                // Sensitivity adjustment
                const newScale = Math.max(0.2, Math.min(3.0, initialScale + (delta * 0.005)));

                // Apply Zoom centered (simplified: zoom around center of viewport)
                // To do proper focal zoom is complex, sticking to center limit for now or just direct update
                window.visualScale = newScale;
                this.updateTransform();

            } else if (e.touches.length === 1 && this.isDragging) {
                // Pan Move
                e.preventDefault(); // Prevent scrolling page
                const dx = e.touches[0].clientX - this.startX;
                const dy = e.touches[0].clientY - this.startY;
                this.applyMove(dx, dy);
            }
        }, { passive: false });

        this.viewport.addEventListener('touchend', (e) => {
            this.isDragging = false;
            if (e.touches.length < 2) {
                initialPinchDistance = null;
            }
        });

        // Mouse Events (for PC testing)
        // ... (Keep existing mouse for panning, add wheel for zoom?)
        this.viewport.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.startX = e.clientX;
            this.startY = e.clientY;
            this.initialOffsetX = window.visualOffsetX || 0;
            this.initialOffsetY = window.visualOffsetY || 0;
            this.viewport.style.cursor = 'grabbing';
        });

        this.viewport.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;
            e.preventDefault();
            const dx = e.clientX - this.startX;
            const dy = e.clientY - this.startY;
            this.applyMove(dx, dy);
        });

        this.viewport.addEventListener('mouseup', () => {
            this.isDragging = false;
            this.viewport.style.cursor = 'default';
        });

        // Mouse Wheel Zoom
        this.viewport.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            this.zoomMap(delta);
        }, { passive: false });
    },

    getDistance(touches) {
        const dx = touches[0].clientX - touches[1].clientX;
        const dy = touches[0].clientY - touches[1].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    },

    zoomMap(amount) {
        let current = window.visualScale || 1.0;
        let next = Math.max(0.2, Math.min(3.0, current + amount));
        window.visualScale = next;
        this.updateTransform();
    },

    applyMove(dx, dy) {
        window.visualOffsetX = this.initialOffsetX + dx;
        window.visualOffsetY = this.initialOffsetY + dy;
        this.updateTransform();
    },

    centerMap() {
        const screenW = window.innerWidth;
        const screenH = window.innerHeight;

        if (window.visualOffsetX === 0 && window.visualOffsetY === 0) {
            window.visualOffsetX = (screenW / 2) - (2250 * window.visualScale / 2); // Center of 2250px map? No, center logic 2250/2 = 1125
            // Start centered on middle of map (1125, 1125)
            // Offset needs to put (1125, 1125) at (screenW/2, screenH/2)
            // x = screenW/2 - 1125 * scale
            // Let's rely on standard logic
            window.visualOffsetX = (screenW / 2) - 1125;
            window.visualOffsetY = (screenH / 2) - 1125;
        }
        this.updateTransform();
    },

    focusMyToken() {
        // Find my token or first ally
        if (!window.battleState || !window.battleState.characters) return;

        let char = window.battleState.characters.find(c => c.owner === window.currentUsername);
        if (!char) {
            // Fallback: active turn char
            char = window.battleState.characters.find(c => c.id === window.battleState.turn_char_id);
        }

        if (char) {
            const gridSize = 90;
            const charX = char.x * gridSize + (gridSize / 2); // Center of char
            const charY = char.y * gridSize + (gridSize / 2);

            const screenW = window.innerWidth;
            const screenH = window.innerHeight;

            // We want charX, charY to be at screenW/2, screenH/2
            // visualOffsetX + charX * scale = screenW/2
            // visualOffsetX = screenW/2 - charX * scale

            const scale = window.visualScale || 1.0;
            window.visualOffsetX = (screenW / 2) - (charX * scale); // Wait, transform scale applies at origin 0,0?
            // "transform-origin: 0 0" is set in CSS
            // So yes, coordinate X on screen is mapX * scale + visualOffsetX

            // Wait, scaling applies to the map element. Translate applies before or after?
            // transform = translate(...) scale(...) implies:
            // 1. Translate
            // 2. Scale
            // CSS standard: functions are applied from right to left?
            // "transform: translate(x, y) scale(s)" -> Translate first, then Scale?
            // No, standard matrix multiplication order is left to right visually.
            // translate moves the origin. scale scales from the new origin? OR scale scales axes then translate moves?
            // "transform: translate(100px, 100px) scale(2)"
            // -> Moves 100px right, then scales by 2.

            // Let's stick to our updateTransform logic: `translate(${x}px, ${y}px) scale(${scale})`
            // If origin is 0,0 (top-left of element), and element is absolute at 0,0.

            // ScreenPos = Offset + (LocalPos) ? NO.
            // If transform-origin is 0,0.
            // ScreenPos = Offset + (LocalPos * Scale)??
            // Usually: Translate moves the element. Scale scales usage of internal space?
            // Text: `translate(tx, ty) scale(sx, sy)`
            // Matrix: [sx 0 0] [1 0 tx]
            //         [0 sy 0] [0 1 ty]
            //         [0  0 1] [0 0  1]
            // Actually it depends on browser implementation detail if we don't know matrix math by heart.
            // BUT, usually:
            // Element TopLeft is at (tx, ty).
            // Content inside is scaled by s.
            // So yes: ScreenX = tx + (MapX * s)

            window.visualOffsetX = (screenW / 2) - (charX * scale);
            window.visualOffsetY = (screenH / 2) - (charY * scale);

            this.updateTransform();

            // Flash effect?
            // Implementation of flash effect on token is handled by CSS classes usually
        } else {
            alert("No character found to focus.");
        }
    },

    updateTransform() {
        const mapEl = document.getElementById('game-map');
        if (mapEl) {
            const scale = window.visualScale || 1.0;
            const x = window.visualOffsetX || 0;
            const y = window.visualOffsetY || 0;
            mapEl.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
        }
    }
};
