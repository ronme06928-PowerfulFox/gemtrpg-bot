/**
 * timeline.js
 * Handles Timeline rendering and updates for Mobile View
 */

export const Timeline = {
    container: null,

    init() {
        console.log("⏳ Timeline Module Initialized");
        // We'll insert the timeline container dynamically if not present
        this.setupUI();
    },

    setupUI() {
        const mapContainer = document.getElementById('mobile-map-container');
        if (!mapContainer) return;

        // Create Timeline Overlay/Drawer
        const timelineDiv = document.createElement('div');
        timelineDiv.id = 'mobile-timeline';
        timelineDiv.className = 'mobile-timeline'; // Visible by default

        timelineDiv.innerHTML = `
            <div class="timeline-header">
                <span>Timeline</span>
            </div>
            <div class="timeline-content" id="timeline-list">
                <!-- Items injected here -->
            </div>
        `;

        mapContainer.appendChild(timelineDiv);
        this.container = document.getElementById('timeline-list');
    },

    update(state) {
        if (!this.container || !state || !state.timeline) return;

        this.container.innerHTML = '';

        // Log for debugging
        // console.log("Timeline Update:", state.timeline);

        state.timeline.forEach(entry => {
            let charId, entryId, acted, speed;
            if (typeof entry === 'object' && entry !== null) {
                charId = entry.char_id;
                entryId = entry.id;
                acted = entry.acted;
                speed = entry.speed;
            } else {
                // Backward compatibility
                charId = entry;
                entryId = entry;
                acted = false;
                speed = '?';
            }

            const char = state.characters.find(c => c.id === charId);
            if (!char) return;
            if (char.x < 0) return; // Skip unplaced

            const isTurn = state.turn_entry_id ? (state.turn_entry_id === entryId) : (state.turn_char_id === charId);

            const item = document.createElement('div');
            item.className = `timeline-item ${isTurn ? 'active' : ''}`;
            if (acted) {
                item.style.opacity = '0.5';
                item.style.textDecoration = 'line-through';
            }

            // Initial letter if no image
            const bgStyle = char.image ? `background-image: url('${char.image}')` : 'background-color: #555; display:flex; align-items:center; justify-content:center; color:white; font-size:12px;';
            const bgContent = char.image ? '' : char.name.charAt(0);

            const speedDisplay = (speed !== undefined && speed !== '?') ? speed : (char.speedRoll || 0);

            item.innerHTML = `
                <div class="char-icon" style="${bgStyle}">${bgContent}</div>
                <div class="char-info">
                    <span class="char-name" style="color: ${char.color || '#fff'}">${char.name}</span>
                    <span class="char-init">SPD: ${speedDisplay}</span>
                </div>
            `;

            // Scroll into view if active
            if (isTurn) {
                setTimeout(() => item.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
            }

            this.container.appendChild(item);
        });
    }
};
