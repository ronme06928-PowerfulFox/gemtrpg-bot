/* static/js/visual/visual_globals.js */

// Global State Variables for Visual Battle

// Map Visualization
// Map Visualization
// Initialize from localStorage or defaults
const storedScale = localStorage.getItem('gem_visualScale');
const storedX = localStorage.getItem('gem_visualOffsetX');
const storedY = localStorage.getItem('gem_visualOffsetY');

window.visualScale = storedScale ? parseFloat(storedScale) : 0.7; // Default to 0.7 as requested
window.visualOffsetX = storedX ? parseFloat(storedX) : (typeof CENTER_OFFSET_X !== 'undefined' ? CENTER_OFFSET_X : -900);
window.visualOffsetY = storedY ? parseFloat(storedY) : (typeof CENTER_OFFSET_Y !== 'undefined' ? CENTER_OFFSET_Y : -900);

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
window._visualBattleTurnListenerRegistered = false;
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
