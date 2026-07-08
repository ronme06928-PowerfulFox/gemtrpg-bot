/* static/js/common/log_core.js */
// ログ受信の入口。計画書32（戦闘UI一本化）Phase 1 で static/js/tab_battlefield.js から移設。
// visual/visual_socket.js の installBattleLogDeferHook が window.logToBattleLog を
// wrap するため、CLASSIC_SCRIPTS では visual_socket.js より前に読み込むこと。
// Phase 2 で旧テキスト戦闘（log-area）が完全撤去されたため、当該描画分岐は削除済み。

function _normalizeLogMessageForDisplay(logData) {
    if (!logData || typeof logData !== 'object') return '';
    return String(logData.message || '').trim();
}

function _isDuplicateBleedLogLine(prevLog, nextLog) {
    if (!prevLog || !nextLog) return false;
    if (String(prevLog.type || '') !== 'state-change' || String(nextLog.type || '') !== 'state-change') {
        return false;
    }
    const prevMessage = _normalizeLogMessageForDisplay(prevLog);
    const nextMessage = _normalizeLogMessageForDisplay(nextLog);
    if (!prevMessage || prevMessage !== nextMessage) {
        return false;
    }
    return prevMessage.startsWith('[出血]:') && prevMessage.includes('出血 (');
}

function logToBattleLog(logData) {
    // タイムスタンプが無い場合は追加（ログの順序を保証）
    if (!logData.timestamp) {
        logData.timestamp = Date.now();
    }

    // 1. データへの保存（常に実行）
    if (battleState && battleState.logs) {
        const prevLog = battleState.logs.length > 0 ? battleState.logs[battleState.logs.length - 1] : null;
        if (_isDuplicateBleedLogLine(prevLog, logData)) {
            return;
        }
        battleState.logs.push(logData);
    } else {
        console.warn('[LOG] battleState.logs is not available, log data may be lost:', logData);
    }

    // 2. Visualログが表示中なら即時反映する（diceログ遅延対策）
    const visualLogArea = document.getElementById('visual-log-area');
    if (visualLogArea) {
        if (typeof window.appendVisualLogBatch === 'function') {
            window.appendVisualLogBatch([logData]);
            window._lastLogCount = Number(window._lastLogCount || 0) + 1;
        } else if (typeof window.appendVisualLogLine === 'function') {
            const filter = window.currentVisualLogFilter || 'all';
            window.appendVisualLogLine(visualLogArea, logData, filter);
            window._lastLogCount = Number(window._lastLogCount || 0) + 1;
            visualLogArea.scrollTop = visualLogArea.scrollHeight;
        }
    }
}
