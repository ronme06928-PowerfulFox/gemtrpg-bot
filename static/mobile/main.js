/**
 * main.js
 * Entry point for Mobile View
 * Orchestrates Portal, Map, and UI modules.
 */

import { Portal } from './js/portal.js';
import { MobileMap } from './js/map.js';
import { MobileUI } from './js/ui.js';
import { Timeline } from './js/timeline.js';
import { Characters } from './js/characters.js';
import { MobileMatch } from './js/match.js';

// Global overrides for mobile context
window.isMobileView = true;
window.visualScale = 1.0;
window.visualOffsetX = 0;
window.visualOffsetY = 0;

// Disable legacy renderers to prevent conflict
// Block Legacy UI handlers
window.renderVisualMap = function () { console.log("Legacy renderVisualMap blocked"); };
window.setupMapControls = function () { console.log("Legacy setupMapControls blocked"); };
window.renderTokenList = function () { console.log("Legacy renderTokenList blocked"); };
window.updateDuelUI = function () { console.log("Legacy updateDuelUI blocked"); };
window.closeDuelModal = function () { console.log("Legacy closeDuelModal blocked"); };
// CRITICAL: Block setupVisualBattleTab because it clears socket listeners!
window.setupVisualBattleTab = async function () {
    console.log("Legacy setupVisualBattleTab blocked to protect mobile listeners");
};

// Fetch skill data for mobile usage
async function loadMobileSkillData() {
    if (!window.allSkillData) {
        try {
            console.log("📥 Fetching Skill Data for Mobile...");
            const res = await fetch('/api/get_skill_data');
            if (res.ok) {
                window.allSkillData = await res.json();
                console.log("✅ Skill Data Loaded:", Object.keys(window.allSkillData).length);
            }
        } catch (e) { console.error("Failed to load skill data:", e); }
    }
}
// Also block updateCharacterTokenVisuals if it conflicts, but it might be useful for partial updates.
// For now, let Characters.renderTokens handle full updates.

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', async () => {
    console.log("📱 Mobile App Starting...");

    // Load data immediately
    loadMobileSkillData();

    // Initialize Modules
    Portal.init();
    MobileUI.init();
    MobileMap.init();
    Timeline.init();
    Characters.init();
    MobileMatch.init();

    // Expose for inline handlers
    window.Characters = Characters;

    // Global Socket Init Helper (called by Portal after login)
    window.initializeMobileSocket = () => {
        // Ensure socket exists
        if (!window.socket) {
            window.socket = io();

            window.socket.on('connect', () => {
                console.log("✅ Socket Connected");
                Portal.showScreen('room');
                Portal.fetchRoomList();
            });
        }

        // Always attach mobile listeners (idempotent check inside listeners if needed,
        // but simple .on is additive so we should be careful not to duplicate if called multiple times.
        // However, initializeMobileSocket usually called once on login.

        // Listen for state updates to update Timeline & Map & Characters
        // Remove old listener if exists to prevent duplicates?
        // socket.off('state_updated') might disable legacy ones too if they use same event.
        // Better to just attach once.
        if (!window._mobileListenersAttached) {
            window._mobileListenersAttached = true;

            // Listen for state updates to update Timeline & Map & Characters
            window.socket.on('state_updated', (newState) => {
                window.battleState = newState;
                Timeline.update(newState);
                Characters.renderTokens(newState.characters);
                MobileUI.renderLogs(newState.logs);

                // Sync Match Modal State
                if (MobileMatch) {
                    if (newState.active_match && newState.active_match.is_active) {
                        // Match active: if we are attacker/defender and modal not open, maybe open it?
                        // Or rely on open_match_modal event?
                        // Usually rely on event. But if we reload page, we might need state.
                        // For now, just handle CLOSING.
                    } else {
                        // Match NOT active: Ensure modal is closed
                        MobileMatch.closeMatchModal();
                    }
                }
            });

            // Listen for new logs (Real-time update)
            window.socket.on('new_log', (logData) => {
                MobileUI.appendLog(logData);
            });

            // Match/Skill Declaration Results
            window.socket.on('skill_declaration_result', (data) => {
                console.log("Skill Declaration Result:", data);
                if (MobileMatch && typeof MobileMatch.updatePreview === 'function') {
                    MobileMatch.updatePreview(data);
                }
            });

            // Wide Reservation Request (Round Start)
            window.socket.on('open_wide_declaration_modal', (data) => {
                console.log("⚡ Wide Reservation Requested (open_wide_declaration_modal)");
                if (MobileMatch && typeof MobileMatch.openWideReservationModal === 'function') {
                    MobileMatch.openWideReservationModal();
                }
            });

            // Close Wide Declaration Modal (Phase End)
            window.socket.on('close_wide_declaration_modal', () => {
                console.log("⚡ Close Wide Reservation Signal");
                if (MobileMatch && typeof MobileMatch.closeWideReservationModal === 'function') {
                    MobileMatch.closeWideReservationModal();
                }
            });

            // Legacy naming might be different, let's catch 'start_reservation_phase' just in case?
            // But 'request_wide_reservation_check' is most likely based on legacy code patterns.

            // Initialize Match Module Listeners
            if (MobileMatch) {
                MobileMatch.setupSocketListeners(window.socket);
            }
        }
    };

    // Begin Session Check
    const isLoggedIn = await Portal.checkSession();
    if (isLoggedIn) {
        window.initializeMobileSocket();
    }
});
