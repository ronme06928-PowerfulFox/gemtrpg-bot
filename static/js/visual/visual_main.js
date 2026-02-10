/* static/js/visual/visual_main.js */

/**
 * Main Entry Point for Visual Battle Tab
 */
window.setupVisualBattleTab = async function () {
    console.log("🚀 Initializing Visual Battle Tab (Modularized)...");

    // 1. Initialize Components (Legacy & New)
    if (window.TimelineComponent && typeof window.TimelineComponent.initialize === 'function') {
        window.TimelineComponent.initialize('visual-timeline-list');
    }
    if (window.ActionDockComponent && typeof window.ActionDockComponent.initialize === 'function') {
        window.ActionDockComponent.initialize();
    }
    if (window.VisualMapComponent && typeof window.VisualMapComponent.initialize === 'function') {
        window.VisualMapComponent.initialize();
    }
    if (window.MatchPanelComponent && typeof window.MatchPanelComponent.initialize === 'function') {
        window.MatchPanelComponent.initialize();
    }

    // 2. Setup Controls & UI
    if (typeof setupMapControls === 'function') setupMapControls();
    if (typeof setupVisualSidebarControls === 'function') setupVisualSidebarControls();
    if (typeof initializeTimelineToggle === 'function') initializeTimelineToggle();

    // 3. Register Socket Handlers
    if (typeof setupVisualSocketHandlers === 'function') setupVisualSocketHandlers();

    // 4. Initial Render (if state exists)
    if (typeof battleState !== 'undefined') {
        const mode = battleState.mode || 'battle';
        console.log(`[VisualMain] Initial Render. Mode: ${mode}`);

        const mapViewport = document.getElementById('map-viewport');
        const expViewport = document.getElementById('exploration-viewport');

        if (mode === 'exploration') {
            if (mapViewport) mapViewport.style.display = 'none';
            if (expViewport) expViewport.style.display = 'block';
            if (window.ExplorationView && typeof window.ExplorationView.render === 'function') {
                // Optimization: Setup once
                if (typeof window.ExplorationView.setup === 'function') window.ExplorationView.setup();
                window.ExplorationView.render(battleState);
            }
        } else {
            if (mapViewport) mapViewport.style.display = 'block';
            if (expViewport) expViewport.style.display = 'none';
            if (typeof renderVisualMap === 'function') renderVisualMap();
        }

        if (battleState.logs && typeof renderVisualLogHistory === 'function') {
            renderVisualLogHistory(battleState.logs);
        }
        if (typeof updateVisualRoundDisplay === 'function') {
            updateVisualRoundDisplay(battleState.round);
        }
        if (typeof renderMatchPanelFromState === 'function') {
            renderMatchPanelFromState(battleState.active_match);
        }
    }

    // 5. Action Dock Lazy Init
    if (!window.actionDockInitialized) {
        if (battleState && battleState.mode === 'exploration') {
            if (typeof updateActionDock === 'function') setTimeout(updateActionDock, 100);
        } else if (typeof initializeActionDock === 'function') {
            initializeActionDock();
        }
        window.actionDockInitialized = true;
    }

    console.log("✅ Visual Battle Tab Initialized.");
}

// Auto-init if DOM is ready and we are not waiting for tab switch
// However, main.js usually calls setupVisualBattleTab() when tab is clicked.
// So we just define it here.
