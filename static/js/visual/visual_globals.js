/* static/js/visual/visual_globals.js */

// Global State Variables for Visual Battle

// Restore a complete saved view; otherwise center after the viewport is visible.
const storedScale = localStorage.getItem('gem_visualScale');
const storedX = localStorage.getItem('gem_visualOffsetX');
const storedY = localStorage.getItem('gem_visualOffsetY');

const visualStoredViewValid = [storedScale, storedX, storedY].every(
  value => value !== null && value.trim() !== '' && Number.isFinite(Number(value))
) && Number(storedScale) >= 0.5 && Number(storedScale) <= 3;
window.visualScale = visualStoredViewValid ? Number(storedScale) : 0.6;
window.visualOffsetX = visualStoredViewValid ? Number(storedX) : 0;
window.visualOffsetY = visualStoredViewValid ? Number(storedY) : 0;
window.visualViewNeedsCenter = !visualStoredViewValid;

// Turn & Action Tracking
window.matchActionInitiated = false;
window.lastTurnCharId = null;

// Targeting State
window.attackTargetingState = {
    isTargeting: false,
    attackerId: null
};

// UI State
window.currentVisualLogFilter = 'all';
window._lastLogCount = 0;
window.actionDockInitialized = false;
window._matchPanelAutoExpanded = false;

// Socket Handler Flags
window._socketHandlersActuallyRegistered = false;
window._charStatUpdatedListenerRegistered = false;

// Optimization Flags
window._dragBlockClick = false;

// Event Handlers Storage (for cleanup)
window.visualMapHandlers = {};

// Constants
// Constants
window.VISUAL_MAX_LOG_ITEMS = 100;
window.VISUAL_SHOW_ARROWS = true; // Default: Show arrows
window.GRID_SIZE = 90; // Sync with Constants.js
window.TOKEN_OFFSET = 4; // Sync with Constants.js

console.log('[visual_globals] Loaded.');
