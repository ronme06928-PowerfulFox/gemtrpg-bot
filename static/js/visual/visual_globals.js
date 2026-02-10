/* static/js/visual/visual_globals.js */

// Global State Variables for Visual Battle

// Map Visualization
window.visualScale = window.visualScale || 1.0;
window.visualOffsetX = window.visualOffsetX || (typeof CENTER_OFFSET_X !== 'undefined' ? CENTER_OFFSET_X : -900);
window.visualOffsetY = window.visualOffsetY || (typeof CENTER_OFFSET_Y !== 'undefined' ? CENTER_OFFSET_Y : -900);

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
window.VISUAL_MAX_LOG_ITEMS = 100;

console.log('[visual_globals] Loaded.');
