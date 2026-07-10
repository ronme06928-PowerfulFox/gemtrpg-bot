/* static/js/visual/visual_ui.js */

// --- Log Rendering ---

const _escapeResolveLogHtml = (value) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const _appendRichVisualSystemLogMessage = (parent, text) => {
    const template = document.createElement('template');
    template.innerHTML = String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/&amp;gt;/g, '&gt;')
        .replace(/&amp;lt;/g, '&lt;')
        .replace(/&amp;amp;/g, '&amp;')
        .replace(/&amp;quot;/g, '&quot;')
        .replace(/&amp;#39;/g, '&#39;')
        .replace(/&amp;#x27;/gi, '&#x27;')
        .replace(/&lt;br\s*\/?&gt;/gi, '<br>')
        .replace(/&lt;(\/?)strong&gt;/gi, '<$1strong>')
        .replace(/&lt;(\/?)b&gt;/gi, '<$1b>')
        // request_log is client-controlled, so only restore the exact numeric dice-result markup.
        .replace(
            /&lt;span\s+class=(?:"|'|&quot;|&#39;|&#x27;)dice-result-total(?:"|'|&quot;|&#39;|&#x27;)&gt;(-?\d+|-)&lt;\/span&gt;/gi,
            '<span class="dice-result-total">$1</span>'
        );
    parent.appendChild(template.content.cloneNode(true));
};

const _toResolveNum = (value, fallback = 0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
};

const _signedResolveNum = (value) => {
    const n = _toResolveNum(value, 0);
    return (n >= 0) ? `+${n}` : `${n}`;
};

const _isHiddenResolveTraceLog = (logData) => {
    if (!logData || typeof logData !== 'object') return false;
    if (String(logData.source || '') !== 'resolve_trace') return false;
    const detail = (logData.resolve_trace_detail && typeof logData.resolve_trace_detail === 'object')
        ? logData.resolve_trace_detail
        : null;
    if (!detail) return false;
    const kind = String(detail.kind || '').trim();
    const notes = String(detail.notes || '').trim();
    const attackerSkillId = String(detail?.attacker?.skill_id || '').trim();
    return kind === 'fizzle' && notes === 'no_intent' && !attackerSkillId;
};

const _normalizeVisualLogMessage = (logData) => {
    if (!logData || typeof logData !== 'object') return '';
    return String(logData.message || '').trim();
};

const _isDuplicateVisualBleedLog = (prevLog, nextLog) => {
    if (!prevLog || !nextLog) return false;
    if (String(prevLog.type || '') !== 'state-change' || String(nextLog.type || '') !== 'state-change') {
        return false;
    }
    const prevMessage = _normalizeVisualLogMessage(prevLog);
    const nextMessage = _normalizeVisualLogMessage(nextLog);
    if (!prevMessage || prevMessage !== nextMessage) {
        return false;
    }
    return prevMessage.startsWith('[\u51fa\u8840]:') && prevMessage.includes('\u51fa\u8840 (');
};

const _resolveSidePowerLines = (side) => {
    const snapshot = (side && typeof side.power_snapshot === 'object') ? side.power_snapshot : {};
    const breakdown = (side && typeof side.power_breakdown === 'object') ? side.power_breakdown : {};

    const hasSnapshot = Object.keys(snapshot).length > 0;
    const hasBreakdown = Object.keys(breakdown).length > 0;
    if (!hasSnapshot && !hasBreakdown) {
        return {
            line1: '計算データなし',
            line2: '補正: 基礎威力+0 / ダイス威力+0 / 最終威力+0'
        };
    }

    const base = _toResolveNum(snapshot.base_power_after_mod, 0);
    const dice = _toResolveNum(snapshot.dice_power_after_roll, 0);
    const physical = _toResolveNum(snapshot.physical_power, 0);
    const magical = _toResolveNum(snapshot.magical_power, 0);
    const attr = physical + magical;
    const flatBonus = _toResolveNum(snapshot.flat_power_bonus, 0);
    const final = _toResolveNum(snapshot.final_power, 0);
    const ruleBase = _toResolveNum(breakdown.rule_power_bonus, 0);

    const baseShown = base + ruleBase;
    const flatShown = flatBonus - ruleBase;
    const baseMod = _toResolveNum(breakdown.base_power_mod, 0);
    const diceMod = _toResolveNum(breakdown.dice_bonus_power, 0);
    const finalMod = _toResolveNum(breakdown.final_power_mod, flatShown);

    return {
        line1: `基礎${baseShown} + ダイス${dice} + 属性${_signedResolveNum(attr)} + 定数${_signedResolveNum(flatShown)} = 合計${final}`,
        line2: `補正: 基礎威力${_signedResolveNum(baseMod)} / ダイス威力${_signedResolveNum(diceMod)} / 最終威力${_signedResolveNum(finalMod)}`
    };
};

window.openResolveTraceDetailModal = function (logData) {
    const detail = (logData && typeof logData.resolve_trace_detail === 'object') ? logData.resolve_trace_detail : null;
    if (!detail) return;

    const existing = document.getElementById('resolve-trace-detail-modal');
    if (existing) existing.remove();

    const attacker = (detail.attacker && typeof detail.attacker === 'object') ? detail.attacker : {};
    const defender = (detail.defender && typeof detail.defender === 'object') ? detail.defender : {};
    const attackerLines = _resolveSidePowerLines(attacker);
    const defenderLines = _resolveSidePowerLines(defender);
    const oneSided = !!detail.one_sided;

    const renderSide = (side, lines, roleClass) => {
        const name = _escapeResolveLogHtml(side?.name || '-');
        const command = _escapeResolveLogHtml(side?.command || '-');
        return `
            <div class="resolve-trace-side ${roleClass}">
                <div class="resolve-trace-side-name">${name}</div>
                <div class="resolve-trace-side-command">${command}</div>
                <div class="resolve-trace-side-power-main">${_escapeResolveLogHtml(lines.line1)}</div>
                <div class="resolve-trace-side-power-sub">${_escapeResolveLogHtml(lines.line2)}</div>
            </div>
        `;
    };

    const overlay = document.createElement('div');
    overlay.id = 'resolve-trace-detail-modal';
    overlay.className = 'resolve-trace-modal-backdrop';
    overlay.innerHTML = `
        <div class="resolve-trace-modal">
            <div class="resolve-trace-modal-header">
                <div class="resolve-trace-modal-title">${_escapeResolveLogHtml(detail.kind_label || '解決ログ詳細')}</div>
                <button type="button" class="resolve-trace-modal-close">×</button>
            </div>
            <div class="resolve-trace-modal-meta">
                <span>結果: ${_escapeResolveLogHtml(detail.outcome_label || '-')}</span>
                <span>総ダメージ: ${_escapeResolveLogHtml(String(_toResolveNum(detail.total_damage, 0)))}</span>
            </div>
            <div class="resolve-trace-modal-body">
                ${renderSide(attacker, attackerLines, 'attacker')}
                <div class="resolve-trace-side-vs">VS</div>
                ${oneSided
            ? `<div class="resolve-trace-side defender"><div class="resolve-trace-side-name">${_escapeResolveLogHtml(defender?.name || '-')}</div><div class="resolve-trace-side-command">一方攻撃のため対抗ロールなし</div><div class="resolve-trace-side-power-main">-</div><div class="resolve-trace-side-power-sub">-</div></div>`
            : renderSide(defender, defenderLines, 'defender')}
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const close = () => {
        document.removeEventListener('keydown', onKeydown, true);
        overlay.remove();
    };
    const onKeydown = (evt) => {
        if (evt.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKeydown, true);

    overlay.addEventListener('click', (evt) => {
        if (evt.target === overlay) close();
    });
    const closeBtn = overlay.querySelector('.resolve-trace-modal-close');
    if (closeBtn) closeBtn.addEventListener('click', close);
};

window.appendVisualLogLine = function (container, logData, filterType) {
    const isChat = logData.type === 'chat';
    if (filterType === 'chat' && !isChat) return;
    if (filterType === 'system' && isChat) return;
    if (_isHiddenResolveTraceLog(logData)) return;
    const isHistoryView = container && container.dataset && container.dataset.fullHistory === '1';

    const logLine = document.createElement('div');
    let className = `log-line ${logData.type}`;
    let displayMessage = String(logData.message || '');
    let secretVisible = false;

    if (logData.secret) {
        className += ' secret-log';
        const isSender = (typeof currentUsername !== 'undefined' && logData.user === currentUsername);
        const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
        secretVisible = isGM || isSender;
        if (!secretVisible) displayMessage = '（シークレットダイス）';
    }

    logLine.className = className;
    if (isHistoryView) {
        logLine.classList.add('visual-log-history-row');
        const meta = document.createElement('span');
        meta.className = 'visual-log-history-meta';
        const typeLabel = ({
            chat: 'CHAT',
            info: 'INFO',
            system: 'SYSTEM',
            match: 'MATCH',
            round: 'ROUND',
            'state-change': 'STATE',
        })[String(logData.type || '')] || String(logData.type || 'LOG').toUpperCase();
        const time = logData.timestamp
            ? new Date(logData.timestamp).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            : '--:--:--';
        meta.textContent = `${time} ${typeLabel}`;
        logLine.appendChild(meta);
    }
    if (logData.type === 'chat') {
        if (logData.secret && secretVisible) {
            const secretMark = document.createElement('span');
            secretMark.className = 'secret-mark';
            secretMark.textContent = '[SECRET]';
            logLine.appendChild(secretMark);
            logLine.appendChild(document.createTextNode(' '));
        } else if (logData.secret) {
            const masked = document.createElement('span');
            masked.className = 'secret-masked';
            masked.textContent = displayMessage;
            logLine.appendChild(masked);
        }
        if (!logData.secret || secretVisible) {
            const user = document.createElement('span');
            user.className = 'chat-user';
            user.textContent = `${String(logData.user || '匿名')}:`;
            const message = document.createElement('span');
            message.className = 'chat-message';
            message.textContent = String(logData.message || '');
            logLine.appendChild(user);
            logLine.appendChild(document.createTextNode(' '));
            logLine.appendChild(message);
        }
    } else if (!logData.secret && String(logData.source || '') === 'resolve_trace') {
        const detail = (logData && typeof logData.resolve_trace_detail === 'object')
            ? logData.resolve_trace_detail
            : null;
        const kindLabel = String(detail?.kind_label || '解決');
        const attackerName = String(detail?.attacker?.name || '攻撃側');
        const defenderName = String(detail?.defender?.name || (detail?.one_sided ? '対象' : '防御側'));
        const matchupLabel = detail?.one_sided
            ? `${attackerName} -> ${defenderName}`
            : `${attackerName} vs ${defenderName}`;
        const buttonLabel = `[${kindLabel}] ${matchupLabel} / 詳細を表示`;
        logLine.innerHTML = `<button type="button" class="resolve-trace-log-btn">${_escapeResolveLogHtml(buttonLabel)}</button>`;
        const btn = logLine.querySelector('.resolve-trace-log-btn');
        if (btn) {
            if (!detail) {
                btn.disabled = true;
            } else {
                btn.addEventListener('click', () => {
                    if (typeof window.openResolveTraceDetailModal === 'function') {
                        window.openResolveTraceDetailModal(logData);
                    }
                });
            }
        }
    } else {
        _appendRichVisualSystemLogMessage(logLine, displayMessage);
    }
    logLine.style.borderBottom = "1px dotted #eee";
    logLine.style.padding = "2px 5px";
    logLine.style.fontSize = "0.9em";
    container.appendChild(logLine);

    if (container.dataset.fullHistory !== '1') {
        while (container.children.length > VISUAL_MAX_LOG_ITEMS) {
            container.removeChild(container.firstElementChild);
        }
    }
}
window.renderVisualLogHistory = function (logs) {
    const logArea = document.getElementById('visual-log-area');
    if (!logArea) return;
    logArea.innerHTML = '';
    if (!logs || logs.length === 0) {
        logArea.innerHTML = '<div style="padding:10px; color:#999;">ログはありません</div>';
        return;
    }
    const filter = window.currentVisualLogFilter || 'all';
    let previousRenderedLog = null;
    logs.forEach(log => {
        if (_isDuplicateVisualBleedLog(previousRenderedLog, log)) {
            return;
        }
        appendVisualLogLine(logArea, log, filter);
        previousRenderedLog = log;
    });
    window._lastLogCount = Array.isArray(logs) ? logs.length : 0;
    logArea.scrollTop = logArea.scrollHeight;
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 30);
    setTimeout(() => { logArea.scrollTop = logArea.scrollHeight; }, 80);
}

window.appendVisualLogBatch = function (logs) {
    const logArea = document.getElementById('visual-log-area');
    if (!logArea || !Array.isArray(logs) || logs.length === 0) return;

    const filter = window.currentVisualLogFilter || 'all';
    const existingLogs = Array.isArray(window.battleState?.logs) ? window.battleState.logs : [];
    let previousRenderedLog = existingLogs.length > logs.length
        ? existingLogs[existingLogs.length - logs.length - 1]
        : null;
    logs.forEach(log => {
        if (_isDuplicateVisualBleedLog(previousRenderedLog, log)) {
            previousRenderedLog = log;
            return;
        }
        appendVisualLogLine(logArea, log, filter);
        previousRenderedLog = log;
    });
    window._lastLogCount = Number(window._lastLogCount || 0) + logs.length;
    logArea.scrollTop = logArea.scrollHeight;
};

function _visualLogMatchesQuery(log, query, typeFilter) {
    if (!log || typeof log !== 'object') return false;
    const logType = String(log.type || '').toLowerCase();
    if (typeFilter && typeFilter !== 'all') {
        if (typeFilter === 'chat') {
            if (logType !== 'chat') return false;
        } else if (typeFilter === 'system') {
            if (logType === 'chat') return false;
        } else if (logType !== typeFilter) {
            return false;
        }
    }
    const needle = String(query || '').trim().toLowerCase();
    if (!needle) return true;
    const haystack = [
        log.message,
        log.type,
        log.user,
        log.source,
        log.resolve_step_key,
    ].map(v => String(v || '').toLowerCase()).join('\n');
    return haystack.includes(needle);
}

function _downloadVisualLogFile(filename, content, contentType) {
    const blob = new Blob([String(content || '')], { type: contentType || 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `room_logs_${Date.now()}.txt`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
        URL.revokeObjectURL(url);
        a.remove();
    }, 0);
}

async function _exportVisualRoomLogs(format) {
    const roomName = String(typeof currentRoomName !== 'undefined' ? currentRoomName : '').trim();
    if (!roomName) return;
    const fmt = format === 'text' ? 'text' : 'json';
    const url = `/api/room/export_logs?room_name=${encodeURIComponent(roomName)}&format=${encodeURIComponent(fmt)}`;
    const response = await fetchWithSession(url);
    if (!response.ok) {
        let message = 'ログのエクスポートに失敗しました。';
        try {
            const data = await response.json();
            if (data && data.error) message = data.error;
        } catch (_e) { }
        throw new Error(message);
    }
    const content = await response.text();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : `room_logs.${fmt === 'json' ? 'json' : 'txt'}`;
    _downloadVisualLogFile(filename, content, response.headers.get('Content-Type') || undefined);
}

window.openVisualLogHistoryModal = function () {
    const existing = document.getElementById('visual-log-history-modal-backdrop');
    if (existing) existing.remove();

    const logs = Array.isArray(battleState?.logs) ? battleState.logs : [];
    const canExport = String(
        (typeof currentUserAttribute !== 'undefined')
            ? currentUserAttribute
            : (typeof window !== 'undefined' ? window.currentUserAttribute : '')
    ).trim().toUpperCase() === 'GM';
    const backdrop = document.createElement('div');
    backdrop.id = 'visual-log-history-modal-backdrop';
    backdrop.className = 'modal-backdrop';
    backdrop.innerHTML = `
        <div class="modal-content visual-log-history-modal" role="dialog" aria-modal="true" aria-labelledby="visual-log-history-title">
            <style>
                .visual-log-history-modal {
                    width: min(980px, calc(100vw - 28px));
                    max-height: 88vh;
                    padding: 0;
                    overflow: hidden;
                    display: flex;
                    flex-direction: column;
                    border: 1px solid rgba(36, 48, 56, 0.16);
                    border-radius: 14px;
                    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.28);
                    background: #f7f5ef;
                }
                .visual-log-history-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 14px;
                    padding: 18px 20px 14px;
                    border-bottom: 1px solid rgba(72, 58, 35, 0.12);
                    background: linear-gradient(180deg, #fffaf0 0%, #f3efe4 100%);
                }
                .visual-log-history-title {
                    margin: 0;
                    font-size: 1.22rem;
                    color: #2b2d2f;
                    letter-spacing: 0;
                }
                .visual-log-history-subtitle {
                    margin-top: 4px;
                    font-size: 0.86rem;
                    color: #6f6a60;
                }
                .visual-log-history-close {
                    width: 34px;
                    height: 34px;
                    border: 1px solid #c7beb0;
                    border-radius: 8px;
                    background: #fff;
                    color: #342f29;
                    font-size: 1.15rem;
                    cursor: pointer;
                }
                .visual-log-history-toolbar {
                    display: grid;
                    grid-template-columns: minmax(180px, 1fr) 150px auto;
                    gap: 10px;
                    align-items: center;
                    padding: 14px 20px;
                    border-bottom: 1px solid rgba(72, 58, 35, 0.1);
                    background: #fbfaf6;
                }
                .visual-log-history-input,
                .visual-log-history-select {
                    box-sizing: border-box;
                    width: 100%;
                    height: 40px;
                    border: 1px solid #c8c0b5;
                    border-radius: 8px;
                    background: #fff;
                    color: #2f3437;
                    padding: 0 12px;
                    font-size: 0.95rem;
                }
                .visual-log-history-actions {
                    display: flex;
                    align-items: center;
                    justify-content: flex-end;
                    gap: 8px;
                    min-width: 220px;
                }
                .visual-log-history-count {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    min-width: 70px;
                    height: 30px;
                    padding: 0 10px;
                    border-radius: 999px;
                    background: #e8e2d5;
                    color: #4c463d;
                    font-size: 0.85rem;
                    font-weight: 700;
                }
                .visual-log-history-export {
                    height: 34px;
                    border: 1px solid #a77135;
                    border-radius: 8px;
                    background: #b8722e;
                    color: #fff;
                    padding: 0 12px;
                    cursor: pointer;
                    font-weight: 700;
                }
                .visual-log-history-export.secondary {
                    border-color: #8a8f86;
                    background: #59665d;
                }
                .visual-log-history-status {
                    min-height: 1.2em;
                    padding: 0 20px 10px;
                    background: #fbfaf6;
                    color: #6b6257;
                    font-size: 0.86rem;
                }
                .visual-log-history-list {
                    margin: 0 20px 20px;
                    min-height: 300px;
                    max-height: 58vh;
                    overflow: auto;
                    border: 1px solid #d7d0c5;
                    border-radius: 10px;
                    background: #fffdf8;
                    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
                }
                .visual-log-history-list .visual-log-history-row {
                    display: grid;
                    grid-template-columns: 116px 1fr;
                    align-items: start;
                    gap: 10px;
                    padding: 9px 12px !important;
                    border-bottom: 1px solid #eee6da !important;
                    font-size: 0.94rem !important;
                    line-height: 1.55;
                }
                .visual-log-history-list .visual-log-history-meta {
                    font-family: Consolas, "Courier New", monospace;
                    font-size: 0.75rem;
                    color: #7b7065;
                    white-space: nowrap;
                }
                .visual-log-history-empty {
                    padding: 30px 16px;
                    color: #82786c;
                    text-align: center;
                }
                @media (max-width: 720px) {
                    .visual-log-history-toolbar {
                        grid-template-columns: 1fr;
                    }
                    .visual-log-history-actions {
                        justify-content: flex-start;
                        min-width: 0;
                        flex-wrap: wrap;
                    }
                    .visual-log-history-list .visual-log-history-row {
                        grid-template-columns: 1fr;
                    }
                }
            </style>
            <div class="visual-log-history-header">
                <div>
                    <h2 id="visual-log-history-title" class="visual-log-history-title">ログ履歴</h2>
                    <div class="visual-log-history-subtitle">現在のルームログを検索・確認します。GMは保存済みアーカイブを含めて書き出せます。</div>
                </div>
                <button class="visual-log-history-close modal-close-btn" type="button" aria-label="閉じる">×</button>
            </div>
            <div class="visual-log-history-toolbar">
                <input id="visual-log-history-search" class="visual-log-history-input" type="search" placeholder="ログを検索">
                <select id="visual-log-history-filter" class="visual-log-history-select">
                    <option value="all">全て</option>
                    <option value="chat">チャット</option>
                    <option value="system">システム</option>
                    <option value="match">戦闘</option>
                    <option value="state-change">状態変更</option>
                </select>
                <div class="visual-log-history-actions">
                    <span id="visual-log-history-count" class="visual-log-history-count"></span>
                    ${canExport ? `
                        <button id="visual-log-export-json-btn" type="button" class="visual-log-history-export">JSON保存</button>
                        <button id="visual-log-export-text-btn" type="button" class="visual-log-history-export secondary">TXT保存</button>
                    ` : ''}
                </div>
            </div>
            <div id="visual-log-history-export-status" class="visual-log-history-status">${canExport ? 'ログエクスポートは右上の JSON保存 / TXT保存 から実行できます。' : 'ログエクスポートはGM権限のユーザーにのみ表示されます。'}</div>
            <div id="visual-log-history-list" class="battle-log visual-log-history-list"></div>
        </div>
    `;
    document.body.appendChild(backdrop);

    const listEl = backdrop.querySelector('#visual-log-history-list');
    listEl.dataset.fullHistory = '1';
    const searchEl = backdrop.querySelector('#visual-log-history-search');
    const filterEl = backdrop.querySelector('#visual-log-history-filter');
    const countEl = backdrop.querySelector('#visual-log-history-count');
    const statusEl = backdrop.querySelector('#visual-log-history-export-status');

    const render = () => {
        const query = searchEl.value || '';
        const filter = filterEl.value || 'all';
        const matched = logs.filter(log => _visualLogMatchesQuery(log, query, filter));
        listEl.innerHTML = '';
        if (!matched.length) {
            listEl.innerHTML = '<div class="visual-log-history-empty">該当するログはありません</div>';
        } else {
            matched.forEach(log => appendVisualLogLine(listEl, log, 'all'));
        }
        countEl.textContent = `${matched.length} / ${logs.length}`;
        listEl.scrollTop = listEl.scrollHeight;
    };

    backdrop.querySelector('.modal-close-btn')?.addEventListener('click', () => backdrop.remove());
    backdrop.addEventListener('click', (event) => {
        if (event.target === backdrop) backdrop.remove();
    });
    searchEl.addEventListener('input', render);
    filterEl.addEventListener('change', render);

    const bindExport = (id, format) => {
        const btn = backdrop.querySelector(id);
        if (!btn) return;
        btn.addEventListener('click', async () => {
            btn.disabled = true;
            statusEl.textContent = 'エクスポート中...';
            try {
                await _exportVisualRoomLogs(format);
                statusEl.textContent = 'ダウンロードしました。';
            } catch (error) {
                statusEl.textContent = error.message || 'エクスポートに失敗しました。';
            } finally {
                btn.disabled = false;
            }
        });
    };
    bindExport('#visual-log-export-json-btn', 'json');
    bindExport('#visual-log-export-text-btn', 'text');

    render();
    searchEl.focus();
};

// --- Resolve Trace Modal Enhancement ---
;(() => {
    const sidePower = (side) => {
        const snapshot = (side && typeof side.power_snapshot === 'object') ? side.power_snapshot : {};
        const breakdown = (side && typeof side.power_breakdown === 'object') ? side.power_breakdown : {};
        const base = _toResolveNum(snapshot.base_power_after_mod, 0);
        const dice = _toResolveNum(snapshot.dice_power_after_roll, 0);
        const physical = _toResolveNum(snapshot.physical_power, 0);
        const magical = _toResolveNum(snapshot.magical_power, 0);
        const attr = physical + magical;
        const flatBonus = _toResolveNum(snapshot.flat_power_bonus, 0);
        const final = _toResolveNum(snapshot.final_power, 0);
        const ruleBase = _toResolveNum(breakdown.rule_power_bonus, 0);
        const baseShown = base + ruleBase;
        const flatShown = flatBonus - ruleBase;
        const baseMod = _toResolveNum(breakdown.base_power_mod, 0);
        const diceMod = _toResolveNum(breakdown.dice_bonus_power, 0);
        const finalMod = _toResolveNum(breakdown.final_power_mod, flatShown);
        return {
            final,
            line1: `基礎${baseShown} + ダイス${dice} + 属性${_signedResolveNum(attr)} + 定数${_signedResolveNum(flatShown)} = 合計${final}`,
            line2: `補正: 基礎威力${_signedResolveNum(baseMod)} / ダイス威力${_signedResolveNum(diceMod)} / 最終威力${_signedResolveNum(finalMod)}`
        };
    };

    const winnerRole = (detail) => {
        const outcome = String(detail?.outcome || '');
        if (outcome === 'attacker_win') return 'attacker';
        if (outcome === 'defender_win') return 'defender';
        return null;
    };

    const outcomeClass = (detail) => {
        const outcome = String(detail?.outcome || '');
        if (outcome === 'draw') return 'is-draw';
        if (outcome === 'attacker_win' || outcome === 'defender_win') return 'is-win';
        return 'is-neutral';
    };

    const skillMeta = (side) => {
        const sideObj = (side && typeof side === 'object') ? side : {};
        const meta = (sideObj.skill_meta && typeof sideObj.skill_meta === 'object') ? sideObj.skill_meta : {};
        const all = (window.allSkillData && typeof window.allSkillData === 'object') ? window.allSkillData : {};
        const skillId = String(sideObj.skill_id || meta.id || '').trim();
        const fallback = (skillId && all[String(skillId)] && typeof all[String(skillId)] === 'object')
            ? all[String(skillId)]
            : {};

        const pick = (...keys) => {
            for (const key of keys) {
                const raw = meta[key] ?? fallback[key] ?? '';
                const s = String(raw || '').trim();
                if (s) return s;
            }
            return '';
        };

        const effects = [];
        const metaEffects = Array.isArray(meta.effects) ? meta.effects : [];
        metaEffects.forEach((e) => {
            if (!e || typeof e !== 'object') return;
            const label = String(e.label || '').trim() || '効果';
            const text = String(e.text || '').trim();
            if (!text) return;
            effects.push({ label, text });
        });

        if (effects.length <= 0) {
            [
                ['コスト', 'cost'],
                ['発動条件', 'activation_cost'],
                ['効果', 'effect'],
                ['発動時効果', 'activation_effect'],
                ['特殊', 'special']
            ].forEach(([label, key]) => {
                const text = String(fallback[key] || '').trim();
                if (!text) return;
                effects.push({ label, text });
            });
        }

        return {
            id: skillId,
            name: String(sideObj.skill_name || pick('name') || '').trim(),
            category: pick('category'),
            distance: pick('distance', 'range'),
            attribute: pick('attribute'),
            effects,
            raw: (fallback && typeof fallback === 'object' && Object.keys(fallback).length > 0) ? fallback : null
        };
    };

    const formatGlossaryText = (value) => {
        const text = String(value || '').trim();
        if (!text) return '';
        if (typeof window.formatGlossaryMarkupToHTML === 'function') {
            return window.formatGlossaryMarkupToHTML(text);
        }
        return _escapeResolveLogHtml(text).replace(/\n/g, '<br>');
    };

    const renderSkill = (meta) => {
        const hasMeta = !!meta?.id || !!meta?.name || !!meta?.category || !!meta?.distance || !!meta?.attribute || (Array.isArray(meta?.effects) && meta.effects.length > 0);
        if (!hasMeta) return '<div class="resolve-trace-skill-empty">スキル詳細なし</div>';

        const skillTitle = [meta.id ? `[${meta.id}]` : '', meta.name || ''].filter(Boolean).join(' ');

        if (meta.raw && typeof window.formatSkillDetailHTML === 'function') {
            const detailHtml = String(window.formatSkillDetailHTML(meta.raw) || '').trim();
            if (detailHtml) {
                return `
                    <details class="resolve-trace-skill-details">
                        <summary>スキル詳細: ${_escapeResolveLogHtml(skillTitle || '表示')}</summary>
                        <div class="resolve-trace-skill-card">
                            ${detailHtml}
                        </div>
                    </details>
                `;
            }
        }

        const chips = [];
        if (meta.category) chips.push(`<span class="resolve-trace-chip">${_escapeResolveLogHtml(meta.category)}</span>`);
        if (meta.distance) chips.push(`<span class="resolve-trace-chip">${_escapeResolveLogHtml(meta.distance)}</span>`);
        if (meta.attribute) chips.push(`<span class="resolve-trace-chip">${_escapeResolveLogHtml(meta.attribute)}</span>`);
        const effects = Array.isArray(meta.effects) ? meta.effects : [];
        const effectsHtml = effects.length > 0
            ? effects.map((e) => `<li><strong>${_escapeResolveLogHtml(e.label || '効果')}</strong>: ${formatGlossaryText(e.text || '')}</li>`).join('')
            : '<li>効果説明なし</li>';

        return `
            <details class="resolve-trace-skill-details">
                <summary>スキル詳細: ${_escapeResolveLogHtml(skillTitle || '表示')}</summary>
                <div class="resolve-trace-skill-card">
                    <div class="resolve-trace-skill-details-body">
                        <div class="resolve-trace-skill-chips">${chips.join('')}</div>
                        <ul class="resolve-trace-skill-effects">${effectsHtml}</ul>
                    </div>
                </div>
            </details>
        `;
    };

    const renderSide = (side, role, detail) => {
        const power = sidePower(side);
        const wRole = winnerRole(detail);
        const sideClass = (wRole === role) ? 'is-winner' : (wRole ? 'is-loser' : 'is-neutral');
        const sMeta = skillMeta(side);
        const slotIndex = _toResolveNum(side?.slot_index_in_actor, NaN);
        const spd = _toResolveNum(side?.slot_speed ?? side?.slot_initiative, NaN);
        return `
            <div class="resolve-trace-side ${role} ${sideClass}">
                <div class="resolve-trace-side-name">${_escapeResolveLogHtml(side?.name || '-')}</div>
                <div class="resolve-trace-side-meta">
                    <span class="resolve-trace-chip strong">合計威力: ${_escapeResolveLogHtml(String(power.final))}</span>
                    <span class="resolve-trace-chip">SPD: ${_escapeResolveLogHtml(Number.isFinite(spd) ? String(spd) : '-')}</span>
                    ${Number.isFinite(slotIndex) ? `<span class="resolve-trace-chip">スロット: #${slotIndex + 1}</span>` : ''}
                </div>
                <div class="resolve-trace-side-command">${_escapeResolveLogHtml(side?.command || '-')}</div>
                <div class="resolve-trace-side-power-main">${_escapeResolveLogHtml(power.line1)}</div>
                <div class="resolve-trace-side-power-sub">${_escapeResolveLogHtml(power.line2)}</div>
                ${renderSkill(sMeta)}
            </div>
        `;
    };

    window.openResolveTraceDetailModal = function (logData) {
        const detail = (logData && typeof logData.resolve_trace_detail === 'object') ? logData.resolve_trace_detail : null;
        if (!detail) return;

        const existing = document.getElementById('resolve-trace-detail-modal');
        if (existing) existing.remove();

        const attacker = (detail.attacker && typeof detail.attacker === 'object') ? detail.attacker : {};
        const defender = (detail.defender && typeof detail.defender === 'object') ? detail.defender : {};
        const oneSided = !!detail.one_sided;
        const attackerFinal = sidePower(attacker).final;
        const defenderFinal = sidePower(defender).final;

        const overlay = document.createElement('div');
        overlay.id = 'resolve-trace-detail-modal';
        overlay.className = 'resolve-trace-modal-backdrop';
        overlay.innerHTML = `
            <div class="resolve-trace-modal">
                <div class="resolve-trace-modal-header">
                    <div class="resolve-trace-modal-title">${_escapeResolveLogHtml(detail.kind_label || '解決ログ詳細')}</div>
                    <button type="button" class="resolve-trace-modal-close">×</button>
                </div>
                <div class="resolve-trace-modal-meta">
                    <span class="resolve-trace-pill ${outcomeClass(detail)}">結果: ${_escapeResolveLogHtml(detail.outcome_label || '-')}</span>
                    <span class="resolve-trace-pill">総ダメージ: ${_escapeResolveLogHtml(String(_toResolveNum(detail.total_damage, 0)))}</span>
                    <span class="resolve-trace-pill">攻撃側合計: ${_escapeResolveLogHtml(String(attackerFinal))}</span>
                    <span class="resolve-trace-pill">防御側合計: ${_escapeResolveLogHtml(String(defenderFinal))}</span>
                </div>
                <div class="resolve-trace-modal-body">
                    ${renderSide(attacker, 'attacker', detail)}
                    <div class="resolve-trace-side-vs">VS</div>
                    ${oneSided
            ? `<div class="resolve-trace-side defender is-neutral"><div class="resolve-trace-side-name">${_escapeResolveLogHtml(defender?.name || '-')}</div><div class="resolve-trace-side-command">一方攻撃のため対抗ロールなし</div><div class="resolve-trace-side-power-main">-</div><div class="resolve-trace-side-power-sub">-</div></div>`
            : renderSide(defender, 'defender', detail)}
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const skillPanels = Array.from(overlay.querySelectorAll('.resolve-trace-skill-details'));
        if (skillPanels.length > 1) {
            let syncing = false;
            skillPanels.forEach((panel) => {
                panel.addEventListener('toggle', () => {
                    if (syncing) return;
                    syncing = true;
                    const nextOpen = !!panel.open;
                    skillPanels.forEach((other) => {
                        if (other !== panel) other.open = nextOpen;
                    });
                    syncing = false;
                });
            });
        }

        const close = () => {
            document.removeEventListener('keydown', onKeydown, true);
            overlay.remove();
        };
        const onKeydown = (evt) => {
            if (evt.key === 'Escape') close();
        };
        document.addEventListener('keydown', onKeydown, true);
        overlay.addEventListener('click', (evt) => {
            if (evt.target === overlay) close();
        });
        const closeBtn = overlay.querySelector('.resolve-trace-modal-close');
        if (closeBtn) closeBtn.addEventListener('click', close);
    };
})();

// --- Round Display ---

window.updateVisualRoundDisplay = function (round) {
    const el = document.getElementById('visual-round-counter');
    if (el) el.textContent = round || 0;
}

// --- Sidebar Controls ---

window.setupVisualSidebarControls = function () {
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');
    const resolveIsGM = () => {
        const attr = (typeof currentUserAttribute !== 'undefined')
            ? currentUserAttribute
            : (typeof window !== 'undefined' ? window.currentUserAttribute : null);
        const role = (typeof window !== 'undefined') ? window.currentUserRole : null;
        const user = (typeof currentUsername !== 'undefined')
            ? currentUsername
            : (typeof window !== 'undefined' ? (window.currentUsername || window.currentUserName) : '');
        const attrNorm = String(attr || '').trim().toUpperCase();
        const roleNorm = String(role || '').trim().toUpperCase();
        return attrNorm === 'GM' || roleNorm === 'GM' || (typeof user === 'string' && /\(GM\)/i.test(user));
    };
    const isGM = resolveIsGM();
    const isBattleOnlyForRoundControls = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';

    if (isGM && !isBattleOnlyForRoundControls) {
        if (startRBtn) {
            startRBtn.style.display = 'inline-block';
            startRBtn.onclick = async () => {
                if (await window.showAppConfirm("次ラウンドを開始しますか？", {
                    title: '次ラウンド開始',
                    confirmText: '開始',
                })) socket.emit('request_new_round', { room: currentRoomName });
            };
        }
        if (endRBtn) {
            endRBtn.style.display = 'inline-block';
            endRBtn.onclick = async () => {
                if (await window.showAppConfirm("ラウンドを終了しますか？", {
                    title: 'ラウンド終了',
                    confirmText: '終了',
                })) socket.emit('request_end_round', { room: currentRoomName });
            };
        }
    } else {
        if (startRBtn) startRBtn.style.display = 'none';
        if (endRBtn) endRBtn.style.display = 'none';
    }

    const chatInput = document.getElementById('visual-chat-input');
    const chatSend = document.getElementById('visual-chat-send');
    const diceCommandRegex = /^((\/sroll|\/sr|\/roll|\/r)\s+)?((\d+)?d\d+([\+\-]\d+)?(\s*[\+\-]\s*(\d+)?d\d+([\+\-]\d+)?)*)/i;

    const sendChat = () => {
        let msg = chatInput.value.trim();
        if (!msg) return;
        let isSecret = false;
        if (/^(\/sroll|\/sr)(\s+|$)/i.test(msg)) isSecret = true;

        if (diceCommandRegex.test(msg)) {
            const result = rollDiceCommand(msg);
            const cleanCmd = msg.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');
            const resultHtml = `${cleanCmd} = ${result.details} = <span class="dice-result-total">${result.total}</span>`;
            socket.emit('request_log', {
                room: currentRoomName,
                message: `[${currentUsername}] ${resultHtml}`,
                type: 'dice',
                secret: isSecret,
                user: currentUsername
            });
        } else {
            msg = msg.replace(/^(\/roll|\/r)(\s+|$)/i, '');
            if (isSecret) msg = msg.replace(/^(\/sroll|\/sr)(\s+|$)/i, '');
            if (!msg && isSecret) { alert("シークレットメッセージの内容を入力してください。"); return; }
            if (msg) {
                socket.emit('request_chat', {
                    room: currentRoomName, user: currentUsername, message: msg, secret: isSecret
                });
            }
        }
        chatInput.value = '';
    };

    if (chatSend) chatSend.onclick = sendChat;
    if (chatInput) {
        chatInput.onkeydown = (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); }
        };
    }

    const filters = document.querySelectorAll('.filter-btn[data-target="visual-log"]');
    filters.forEach(btn => {
        btn.onclick = () => {
            filters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            window.currentVisualLogFilter = btn.dataset.filter;
            if (battleState && battleState.logs) renderVisualLogHistory(battleState.logs);
        };
    });

    const vHistoryBtn = document.getElementById('visual-show-history-btn');
    if (vHistoryBtn) {
        vHistoryBtn.onclick = () => {
            if (typeof openVisualLogHistoryModal === 'function') {
                openVisualLogHistoryModal();
            } else {
                console.warn('openVisualLogHistoryModal not defined');
            }
        };
    }

    const saveBtn = document.getElementById('visual-save-btn');
    const presetBtn = document.getElementById('visual-preset-btn');
    const roomPresetBtn = document.getElementById('visual-room-preset-btn');
    const boBtn = document.getElementById('visual-bo-btn');
    const resetBtn = document.getElementById('visual-reset-btn');
    const statusMsg = document.getElementById('visual-status-msg');
    const isBattleOnlyMode = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
    const canUseResetInRoom = isGM || isBattleOnlyMode;
    const centerCtaId = 'visual-bo-center-cta';
    const stageEffectCardId = 'visual-stage-effect-card';
    const runtimeGlobal = (typeof window !== 'undefined') ? window : globalThis;

    // 追加ボタンを表示できるよう、ルーム操作エリアのレイアウトを拡張
    const actionContainer = document.getElementById('visual-room-actions');
    if (roomPresetBtn) {
        roomPresetBtn.style.display = isBattleOnlyMode ? 'none' : 'inline-flex';
    }
    if (actionContainer && !document.getElementById('visual-pve-btn')) {
        // 2カラム固定から折り返し可能なflexレイアウトに変更
        actionContainer.style.display = 'flex';
        actionContainer.style.flexWrap = 'wrap';
        actionContainer.style.gap = '5px';

        actionContainer.style.gap = '5px';

        // PvE/PvP切替はGMのみ表示
        if (isGM) {
            const pveBtn = document.createElement('button');
            pveBtn.id = 'visual-pve-btn';

            const updateBtnText = () => {
                const boMode = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
                const mode = boMode ? 'pve' : ((battleState && battleState.battle_mode) ? battleState.battle_mode : 'pvp');
                pveBtn.textContent = (mode === 'pve') ? '戦闘モード: PvE' : '戦闘モード: PvP';
                pveBtn.style.background = (mode === 'pve') ? '#28a745' : '#6c757d'; // Green for PvE, Gray for PvP
                pveBtn.style.color = 'white';
                pveBtn.disabled = boMode;
                pveBtn.style.opacity = boMode ? '0.75' : '1';
                pveBtn.style.cursor = boMode ? 'not-allowed' : 'pointer';
            };

            // 初期表示を遅延反映
            setTimeout(updateBtnText, 500);
            // battleState更新を拾って表示を同期するため、簡易的に定期更新する

            pveBtn.style.cssText = "padding: 5px; font-size: 0.8em; cursor: pointer; border: none; border-radius: 3px; background: #6c757d; color: white; flex: 1; min-width: 60px;";
            pveBtn.onclick = async () => {
                const boMode = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
                if (boMode) return;
                const currentMode = (battleState && battleState.battle_mode) ? battleState.battle_mode : 'pvp';
                const nextMode = (currentMode === 'pve') ? 'pvp' : 'pve';
                if (await window.showAppConfirm(`戦闘モードを変更しますか？\n${currentMode.toUpperCase()} -> ${nextMode.toUpperCase()}`, {
                    title: '戦闘モード変更',
                    confirmText: '変更',
                })) {
                    socket.emit('request_switch_battle_mode', { room: currentRoomName, mode: nextMode });
                    // Optimistic update
                    pveBtn.textContent = (nextMode === 'pve') ? '戦闘モード: PvE' : '戦闘モード: PvP';
                }
            };
            actionContainer.appendChild(pveBtn);

            // 状態変化を追従
            setInterval(updateBtnText, 2000);
        }
    }

    function removeBattleOnlyCenterCta() {
        const exists = document.getElementById(centerCtaId);
        if (exists) exists.remove();
    }
    runtimeGlobal.removeBattleOnlyCenterCta = removeBattleOnlyCenterCta;

    function isBattleOnlyPreparationView() {
        const bs = (battleState && typeof battleState === 'object') ? battleState : {};
        const boMode = String(bs.play_mode || 'normal').toLowerCase() === 'battle_only';
        const bo = (bs.battle_only && typeof bs.battle_only === 'object') ? bs.battle_only : {};
        const status = String(bo.status || 'lobby').trim().toLowerCase();
        const isPreparation = (status === 'lobby' || status === 'draft');
        return boMode && isPreparation;
    }

    function shouldShowBattleOnlyCenterCta() {
        const roomName = String((typeof currentRoomName !== 'undefined' ? currentRoomName : runtimeGlobal.currentRoomName) || '').trim();
        const roomPortal = document.getElementById('room-portal');
        const mainApp = document.getElementById('main-app-container');
        const inRoomView = !!(mainApp && mainApp.style.display !== 'none' && (!roomPortal || roomPortal.style.display === 'none'));
        const hasOpenModal = Array.from(document.querySelectorAll('.modal-backdrop')).some((el) => {
            if (!el || !el.isConnected) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const opacity = Number(style.opacity || '1');
            if (Number.isFinite(opacity) && opacity <= 0) return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        });
        const isVisualTab = !!document.querySelector('.tab-button.active[data-tab="visual"]');
        return !!roomName && inRoomView && isVisualTab && !isGM && isBattleOnlyPreparationView() && !hasOpenModal;
    }

    function openBattleOnlyDraftFromUi() {
        removeBattleOnlyCenterCta();
        const boModeNow = String((battleState && battleState.play_mode) || 'normal').toLowerCase() === 'battle_only';
        if (boModeNow && !isGM && typeof openBattleOnlyQuickStartModal === 'function') {
            openBattleOnlyQuickStartModal();
            return;
        }
        if (typeof openBattleOnlyDraftModal === 'function') {
            openBattleOnlyDraftModal();
            return;
        }
        statusMsg.textContent = "戦闘専用モーダルを読み込めませんでした。";
    }

    function syncBattleOnlyCenterCta() {
        const exists = document.getElementById(centerCtaId);
        const shouldShow = shouldShowBattleOnlyCenterCta();
        if (!shouldShow) {
            removeBattleOnlyCenterCta();
            return;
        }

        const bo = (battleState && typeof battleState.battle_only === 'object') ? battleState.battle_only : {};
        const status = String(bo.status || 'lobby').trim();
        const statusLabel = (status === 'in_battle') ? '戦闘中' : (status === 'draft' ? '編成中' : '待機');
        const formationId = String(bo.enemy_formation_id || '').trim();

        const cta = exists || document.createElement('div');
        cta.id = centerCtaId;
        cta.style.position = 'fixed';
        cta.style.left = '50%';
        cta.style.top = '50%';
        cta.style.transform = 'translate(-50%, -50%)';
        cta.style.zIndex = '900';
        cta.style.background = 'rgba(17, 24, 39, 0.86)';
        cta.style.color = '#fff';
        cta.style.padding = '10px 12px';
        cta.style.borderRadius = '10px';
        cta.style.border = '1px solid rgba(255,255,255,0.18)';
        cta.style.boxShadow = '0 10px 24px rgba(0,0,0,0.30)';
        cta.style.backdropFilter = 'blur(2px)';
        cta.style.textAlign = 'center';
        cta.innerHTML = `
            <div style="font-size:12px; opacity:0.9; margin-bottom:6px;">戦闘専用モード / ${statusLabel}${formationId ? ` / 敵編成:${formationId}` : ''}</div>
            <button id="visual-bo-center-cta-btn" style="padding:7px 12px; font-size:13px; border:0; border-radius:8px; cursor:pointer; background:#2563eb; color:#fff;">
                かんたん戦闘突入
            </button>
        `;
        if (!exists) document.body.appendChild(cta);
        const btn = document.getElementById('visual-bo-center-cta-btn');
        if (btn) btn.onclick = openBattleOnlyDraftFromUi;
    }

    function removeStageEffectCard() {
        const exists = document.getElementById(stageEffectCardId);
        if (exists) exists.remove();
    }

    function _normalizeStageAvatarProfile(raw) {
        const src = (raw && typeof raw === 'object') ? raw : {};
        return {
            enabled: !!src.enabled,
            name: String(src.name || '').trim(),
            description: String(src.description || '').trim(),
            icon: String(src.icon || '').trim(),
        };
    }

    if (typeof runtimeGlobal.openStageFieldEffectDetailModal !== 'function') {
        runtimeGlobal.openStageFieldEffectDetailModal = function (payload) {
            const data = (payload && typeof payload === 'object') ? payload : {};
            const stageId = String(data.stage_id || '').trim();
            const stageName = String(data.stage_name || '').trim() || stageId || 'ステージ';
            const profile = (data.stage_field_effect_profile && typeof data.stage_field_effect_profile === 'object')
                ? data.stage_field_effect_profile
                : {};
            const rules = Array.isArray(profile.rules) ? profile.rules.filter((row) => row && typeof row === 'object') : [];
            const avatar = _normalizeStageAvatarProfile(data.stage_avatar_profile);
            const effectEnabled = !!data.stage_field_effect_enabled;
            const avatarEnabled = !!data.stage_avatar_enabled;

            const existing = document.getElementById('stage-field-effect-modal-backdrop');
            if (existing) existing.remove();
            const backdrop = document.createElement('div');
            backdrop.id = 'stage-field-effect-modal-backdrop';
            backdrop.className = 'modal-backdrop';
            const modal = document.createElement('div');
            modal.className = 'modal-content';
            modal.style.cssText = 'max-width:920px; width:96vw; max-height:86vh; overflow:auto; padding:22px;';
            modal.innerHTML = `
                <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
                    <div>
                        <div style="font-size:18px; font-weight:700; color:#111827;">ステージ効果詳細</div>
                        <div style="font-size:12px; color:#4b5563; margin-top:3px;">${_escapeResolveLogHtml(stageName)}${stageId ? ` (ID: ${_escapeResolveLogHtml(stageId)})` : ''}</div>
                    </div>
                    <button type="button" id="stage-field-effect-modal-close" class="bo-btn bo-btn--sm">閉じる</button>
                </div>
                <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap; font-size:12px;">
                    <span style="padding:4px 8px; border-radius:999px; border:1px solid #d1d5db; background:${effectEnabled ? '#ecfdf5' : '#f9fafb'}; color:${effectEnabled ? '#166534' : '#6b7280'};">ステージ効果: ${effectEnabled ? 'ON' : 'OFF'}</span>
                    <span style="padding:4px 8px; border-radius:999px; border:1px solid #d1d5db; background:${avatarEnabled ? '#eff6ff' : '#f9fafb'}; color:${avatarEnabled ? '#1d4ed8' : '#6b7280'};">ステージアバター: ${avatarEnabled ? 'ON' : 'OFF'}</span>
                    <span style="padding:4px 8px; border-radius:999px; border:1px solid #d1d5db; background:#fff; color:#374151;">ルール数: ${rules.length}</span>
                </div>
                <div style="display:${avatarEnabled ? 'block' : 'none'}; margin-top:14px; border:1px solid #e5e7eb; border-radius:10px; padding:12px; background:#f8fafc;">
                    <div style="font-size:12px; color:#6b7280;">ステージアバター（表示用）</div>
                    <div style="margin-top:6px; display:flex; gap:10px; align-items:flex-start;">
                        <div style="min-width:54px; height:54px; border-radius:10px; border:1px solid #d1d5db; display:flex; align-items:center; justify-content:center; font-weight:700; background:#fff; color:#1f2937;">
                            ${_escapeResolveLogHtml(avatar.icon || '場')}
                        </div>
                        <div style="min-width:0;">
                            <div style="font-size:15px; font-weight:700; color:#111827;">${_escapeResolveLogHtml(avatar.name || stageName)}</div>
                            <div style="font-size:13px; color:#374151; margin-top:4px;">${_escapeResolveLogHtml(avatar.description || '説明はありません。')}</div>
                        </div>
                    </div>
                </div>
                <div style="margin-top:14px; border:1px solid #e5e7eb; border-radius:10px; padding:12px; background:#fff;">
                    <div style="font-size:14px; font-weight:700; color:#111827;">効果ルール</div>
                    ${rules.length
                        ? `<ul style="margin:10px 0 0 0; padding-left:0; list-style:none;">${rules.map((row, idx) => {
                            const rid = String(row.rule_id || '').trim() || `rule_${idx + 1}`;
                            const type = String(row.type || '').trim() || 'UNKNOWN';
                            const scope = String(row.scope || 'ALL').trim().toUpperCase() || 'ALL';
                            const value = (row.value === undefined || row.value === null) ? '-' : String(row.value);
                            const stateName = String(row.state_name || '').trim();
                            const displayName = String(row.display_name || row.name || '').trim();
                            const title = displayName || rid || type || `効果ルール ${idx + 1}`;
                            const description = String(row.description || '').trim();
                            const flavor = String(row.flavor_text || row.flavor || '').trim();
                            const cond = (row.condition && typeof row.condition === 'object') ? ` / 条件: ${_escapeResolveLogHtml(JSON.stringify(row.condition))}` : '';
                            const statePart = stateName ? ` / 状態: ${_escapeResolveLogHtml(stateName)}` : '';
                            const descriptionHtml = description ? `<div style="margin-top:6px; color:#374151;">${_escapeResolveLogHtml(description)}</div>` : '';
                            const flavorHtml = flavor ? `<div style="margin-top:8px; padding:8px 10px; border-left:3px solid #93c5fd; background:#eff6ff; color:#1e3a8a; font-style:italic;">${_escapeResolveLogHtml(flavor)}</div>` : '';
                            return `<li style="margin-bottom:10px; padding:10px 12px; border:1px solid #e5e7eb; border-radius:10px; background:#f9fafb;"><div style="font-weight:700; color:#111827;">${_escapeResolveLogHtml(title)}</div><div style="margin-top:4px; font-size:12px; color:#4b5563;">ID:${_escapeResolveLogHtml(rid)} / 種類:${_escapeResolveLogHtml(type)} / 対象:${_escapeResolveLogHtml(scope)} / 値:${_escapeResolveLogHtml(value)}${statePart}${cond}</div>${descriptionHtml}${flavorHtml}</li>`;
                        }).join('')}</ul>`
                        : '<div style="margin-top:8px; color:#6b7280;">ステージ効果ルールは設定されていません。</div>'
                    }
                </div>
            `;
            backdrop.appendChild(modal);
            document.body.appendChild(backdrop);
            const close = () => backdrop.remove();
            modal.querySelector('#stage-field-effect-modal-close')?.addEventListener('click', close);
            backdrop.addEventListener('click', (evt) => {
                if (evt.target === backdrop) close();
            });
        };
    }

    function getBattleOnlyStageDisplayState() {
        const bs = (battleState && typeof battleState === 'object') ? battleState : {};
        const boMode = String(bs.play_mode || 'normal').toLowerCase() === 'battle_only';
        const bo = (bs.battle_only && typeof bs.battle_only === 'object') ? bs.battle_only : {};
        const status = String(bo.status || 'lobby').trim().toLowerCase();
        const stageProfile = (bo.stage_field_effect_profile && typeof bo.stage_field_effect_profile === 'object')
            ? bo.stage_field_effect_profile
            : ((bs.stage_field_effect_profile && typeof bs.stage_field_effect_profile === 'object') ? bs.stage_field_effect_profile : {});
        const avatarProfile = (bo.stage_avatar_profile && typeof bo.stage_avatar_profile === 'object')
            ? bo.stage_avatar_profile
            : ((bs.stage_avatar_profile && typeof bs.stage_avatar_profile === 'object') ? bs.stage_avatar_profile : {});
        const stageAvatarEnabled = Object.prototype.hasOwnProperty.call(bo, 'stage_avatar_enabled')
            ? !!bo.stage_avatar_enabled
            : (Object.prototype.hasOwnProperty.call(bs, 'stage_avatar_enabled') ? !!bs.stage_avatar_enabled : avatarProfile.enabled !== false);
        const stageId = String(bo.selected_stage_id || '').trim();
        const stageName = String(avatarProfile.name || stageId || '').trim() || 'ステージ';
        const rules = Array.isArray(stageProfile.rules) ? stageProfile.rules.filter((row) => row && typeof row === 'object') : [];
        return {
            boMode,
            status,
            stageId,
            stageName,
            rules,
            stage_field_effect_enabled: !!bo.stage_field_effect_enabled,
            stage_avatar_enabled: stageAvatarEnabled,
            stage_field_effect_profile: stageProfile,
            stage_avatar_profile: avatarProfile,
        };
    }

    function syncStageEffectCard() {
        const info = getBattleOnlyStageDisplayState();
        const roomName = String((typeof currentRoomName !== 'undefined' ? currentRoomName : runtimeGlobal.currentRoomName) || '').trim();
        const hasRules = Array.isArray(info.rules) && info.rules.length > 0;
        const hasAvatarContent = !!(
            info.stage_avatar_enabled &&
            (info.stageId || info.stage_avatar_profile.name || info.stage_avatar_profile.description || info.stage_avatar_profile.icon)
        );
        const hasStageContent = !!((info.stage_field_effect_enabled && hasRules) || hasAvatarContent);
        const shouldShow = !!(roomName && info.boMode && info.status === 'in_battle' && hasStageContent);
        if (!shouldShow) {
            removeStageEffectCard();
            return;
        }
        const exists = document.getElementById(stageEffectCardId);
        const card = exists || document.createElement('div');
        const sidebar = document.getElementById('visual-sidebar');
        const sidebarWidth = Math.max(0, Math.round(sidebar?.getBoundingClientRect?.().width || 350));
        const viewportWidth = Math.max(0, Math.round(window.innerWidth || document.documentElement?.clientWidth || 0));
        const compactCard = viewportWidth > 0 && viewportWidth < (sidebarWidth + 360);
        const cardWidth = compactCard
            ? Math.max(180, Math.min(260, viewportWidth - 96))
            : 260;
        card.id = stageEffectCardId;
        card.style.position = 'fixed';
        card.style.left = compactCard ? '84px' : 'auto';
        card.style.right = compactCard ? 'auto' : `${sidebarWidth + 16}px`;
        card.style.top = compactCard ? '84px' : '72px';
        card.style.zIndex = '860';
        card.style.width = `${cardWidth}px`;
        card.style.minWidth = '0';
        card.style.maxWidth = compactCard ? 'calc(100vw - 96px)' : '320px';
        card.style.background = 'rgba(255,255,255,0.96)';
        card.style.border = '1px solid rgba(17,24,39,0.16)';
        card.style.borderRadius = '10px';
        card.style.boxShadow = '0 10px 24px rgba(0,0,0,0.18)';
        card.style.padding = '10px';
        const icon = _escapeResolveLogHtml(String(info.stage_avatar_enabled ? (info.stage_avatar_profile.icon || '場') : '場'));
        const statusColor = info.stage_field_effect_enabled ? '#166534' : '#6b7280';
        card.innerHTML = `
            <div style="display:flex; gap:8px; align-items:center;">
                <div style="width:36px; min-width:36px; height:36px; border-radius:8px; border:1px solid #d1d5db; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; color:#111827; background:#fff;">${icon}</div>
                <div style="min-width:0; flex:1;">
                    <div style="font-size:12px; color:#6b7280;">ステージ効果</div>
                    <div style="font-size:14px; font-weight:700; color:#111827; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${_escapeResolveLogHtml(info.stageName)}</div>
                </div>
            </div>
            <div style="margin-top:8px; display:flex; justify-content:space-between; gap:6px; font-size:12px; flex-wrap:wrap;">
                <span style="color:${statusColor};">効果: ${info.stage_field_effect_enabled ? 'ON' : 'OFF'}</span>
                <span style="color:${info.stage_avatar_enabled ? '#1d4ed8' : '#6b7280'};">アバター: ${info.stage_avatar_enabled ? 'ON' : 'OFF'}</span>
                <span style="color:#374151;">ルール数: ${info.rules.length}</span>
            </div>
            <div style="margin-top:8px;">
                <button type="button" id="visual-stage-effect-detail-btn" class="bo-btn bo-btn--sm" style="width:100%;">詳細</button>
            </div>
        `;
        if (!exists) document.body.appendChild(card);
        const btn = card.querySelector('#visual-stage-effect-detail-btn');
        if (btn) {
            btn.onclick = () => runtimeGlobal.openStageFieldEffectDetailModal({
                stage_id: info.stageId,
                stage_name: info.stageName,
                stage_field_effect_enabled: info.stage_field_effect_enabled,
                stage_avatar_enabled: info.stage_avatar_enabled,
                stage_field_effect_profile: info.stage_field_effect_profile,
                stage_avatar_profile: info.stage_avatar_profile,
            });
        }
    }

    syncBattleOnlyCenterCta();
    if (runtimeGlobal.__boCenterCtaTimer) {
        clearInterval(runtimeGlobal.__boCenterCtaTimer);
    }
    runtimeGlobal.__boCenterCtaTimer = setInterval(syncBattleOnlyCenterCta, 1200);
    syncStageEffectCard();
    if (runtimeGlobal.__boStageEffectCardTimer) {
        clearInterval(runtimeGlobal.__boStageEffectCardTimer);
    }
    runtimeGlobal.__boStageEffectCardTimer = setInterval(syncStageEffectCard, 1200);

    if (isGM) {
        if (saveBtn) {
            saveBtn.style.display = 'inline-block';
            saveBtn.onclick = async () => {
                statusMsg.textContent = "保存中...";
                try {
                    await fetchWithSession('/save_room', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ room_name: currentRoomName, state: battleState })
                    });
                    statusMsg.textContent = "保存しました。";
                    setTimeout(() => statusMsg.textContent = "", 2000);
                } catch (e) { statusMsg.textContent = "保存に失敗しました。"; }
            };
        }
        if (presetBtn) {
            presetBtn.style.display = isBattleOnlyMode ? 'none' : 'inline-block';
            presetBtn.textContent = '敵一覧保存';
            presetBtn.title = isBattleOnlyMode ? '' : '現在の敵一覧を保存/読込する旧式の補助機能です';
            presetBtn.onclick = () => {
                if (isBattleOnlyMode) return;
                if (typeof openPresetManagerModal === 'function') openPresetManagerModal();
            };
        }
        if (roomPresetBtn) {
            roomPresetBtn.style.display = isBattleOnlyMode ? 'none' : 'inline-block';
            roomPresetBtn.onclick = () => {
                if (isBattleOnlyMode) return;
                if (typeof openRoomPresetApplyModal === 'function') {
                    openRoomPresetApplyModal();
                }
            };
        }
        if (boBtn) {
            boBtn.style.display = isBattleOnlyMode ? 'inline-block' : 'none';
            boBtn.textContent = '戦闘専用編成';
            boBtn.onclick = openBattleOnlyDraftFromUi;
        }
    } else {
        if (saveBtn) saveBtn.style.display = 'none';
        if (presetBtn) presetBtn.style.display = 'none';
        if (roomPresetBtn) roomPresetBtn.style.display = 'none';
        if (boBtn) {
            boBtn.style.display = isBattleOnlyMode ? 'inline-block' : 'none';
            boBtn.textContent = 'かんたん戦闘突入';
            boBtn.onclick = openBattleOnlyDraftFromUi;
        }
    }
    if (resetBtn) {
        if (canUseResetInRoom) {
            resetBtn.style.display = 'inline-block';
            resetBtn.onclick = async () => {
                if (typeof openResetTypeModal === 'function') {
                    openResetTypeModal((type, options) => { socket.emit('request_reset_battle', { room: currentRoomName, mode: type, options: options }); });
                } else if (await window.showAppConfirm("戦闘をリセットしますか？", {
                    title: '戦闘リセット',
                    confirmText: 'リセット',
                })) {
                    socket.emit('request_reset_battle', { room: currentRoomName, mode: 'full' });
                }
            };
        } else {
            resetBtn.style.display = 'none';
        }
    }
}

// --- Timeline Controls ---

const VISUAL_TIMELINE_COLLAPSED_KEY = 'visual-timeline-collapsed';
const VISUAL_TIMELINE_USER_SET_KEY = 'visual-timeline-collapsed-user-set';

window.initializeTimelineToggle = function () {
    const timelineArea = document.getElementById('visual-timeline-area');
    const header = timelineArea ? timelineArea.querySelector('.sidebar-header') : null;
    const startRBtn = document.getElementById('visual-round-start-btn');
    const endRBtn = document.getElementById('visual-round-end-btn');

    if (!header) return;

    const currentState = (window.BattleStore && window.BattleStore.state)
        ? window.BattleStore.state
        : (typeof battleState !== 'undefined' ? battleState : {});
    const isSelectPhase = (currentState && currentState.phase === 'select');
    const userSet = localStorage.getItem(VISUAL_TIMELINE_USER_SET_KEY) === '1';
    let collapsedRaw = localStorage.getItem(VISUAL_TIMELINE_COLLAPSED_KEY);

    // Default behavior for Select phase: collapsed unless user explicitly chose otherwise.
    if (isSelectPhase && !userSet) {
        collapsedRaw = 'true';
        localStorage.setItem(VISUAL_TIMELINE_COLLAPSED_KEY, collapsedRaw);
    } else {
        if (startRBtn) startRBtn.style.display = 'none';
        if (endRBtn) endRBtn.style.display = 'none';
    }
    if (collapsedRaw === null) {
        collapsedRaw = 'true';
        localStorage.setItem(VISUAL_TIMELINE_COLLAPSED_KEY, collapsedRaw);
    }

    const isCollapsed = collapsedRaw === 'true';
    if (isCollapsed) {
        timelineArea.classList.add('collapsed');
    } else {
        timelineArea.classList.remove('collapsed');
    }

    header.addEventListener('click', () => {
        const nowCollapsed = timelineArea.classList.toggle('collapsed');
        localStorage.setItem(VISUAL_TIMELINE_COLLAPSED_KEY, String(nowCollapsed));
        localStorage.setItem(VISUAL_TIMELINE_USER_SET_KEY, '1');
    });
}


/**
 * Legacy Timeline Renderer (Use Timeline.js component usually)
 */
window.renderVisualTimeline = function () {
    const timelineEl = document.getElementById('visual-timeline-list');
    if (!timelineEl) return;

    // If Timeline Component is active, let it handle rendering
    if (window.TimelineComponent && typeof window.TimelineComponent.render === 'function') {
        const componentCtn = document.getElementById('visual-timeline-list');
        // Ensure component checks this container
        if (window.TimelineComponent._containerEl === componentCtn) {
            return;
        }
    }

    timelineEl.innerHTML = '';
    if (!battleState.timeline || battleState.timeline.length === 0) {
        timelineEl.innerHTML = '<div style="color:#888; padding:5px;">データなし</div>';
        return;
    }
    const slotMode = Array.isArray(battleState.timeline) &&
        battleState.timeline.length > 0 &&
        typeof battleState.timeline[0] === 'string' &&
        battleState.slots &&
        battleState.slots[battleState.timeline[0]];

    if (slotMode) {
        const selectedSlotId = battleState.selectedSlotId || null;
        battleState.timeline.forEach(slotId => {
            const slot = battleState.slots[slotId];
            if (!slot) return;
            const char = battleState.characters.find(c => String(c.id) === String(slot.actor_id));
            const intent = (battleState.intents || {})[slotId] || {};
            const item = document.createElement('div');
            item.className = `timeline-item ${slot.team || 'NPC'}`;
            item.style.cssText = "display:flex; justify-content:space-between; gap:8px; padding:6px 8px; border-bottom:1px solid #eee; cursor:pointer; background:#fff;";
            if (String(slotId) === String(selectedSlotId)) {
                item.style.background = '#e8f4ff';
                item.style.border = '1px solid #66a3ff';
            }
            const actorName = char ? char.name : slot.actor_id;
            item.innerHTML = `
                <span class="name">${actorName}</span>
                <span class="speed" style="font-size:0.85em; color:#666;">SPD:${slot.initiative}</span>
            `;
            item.addEventListener('click', () => {
                if (char && typeof showCharacterDetail === 'function') {
                    showCharacterDetail(char.id);
                }
            });
            timelineEl.appendChild(item);
        });
        return;
    }

    const currentTurnId = battleState.turn_char_id;
    battleState.timeline.forEach(entry => {
        let charId = entry;
        if (typeof entry === 'object' && entry !== null) {
            charId = entry.char_id;
        }
        const char = battleState.characters.find(c => String(c.id) === String(charId));
        if (!char) return;
        const item = document.createElement('div');
        item.className = `timeline-item ${char.type || 'NPC'}`;
        item.style.cssText = "display:flex; justify-content:space-between; padding:6px 8px; border-bottom:1px solid #eee; cursor:pointer; background:#fff;";
        const typeColor = (char.type === 'ally') ? '#007bff' : '#dc3545';
        item.style.borderLeft = `3px solid ${typeColor}`;
        if (char.id === currentTurnId) {
            item.style.background = "#fff8e1";
            item.style.fontWeight = "bold";
            item.style.borderLeft = `6px solid ${typeColor}`;
            item.style.borderTop = "1px solid #ff9800";
            item.style.borderBottom = "1px solid #ff9800";
            item.style.borderRight = "1px solid #ff9800";
        }
        if (char.hasActed) {
            item.style.opacity = "0.5";
            item.style.textDecoration = "line-through";
        }
        if (char.hp <= 0) {
            item.style.opacity = "0.3";
            item.style.background = "#ccc";
        }
        item.innerHTML = `
            <span class="name">${char.name}</span>
            <span class="speed" style="font-size:0.85em; color:#666;">SPD:${char.totalSpeed || char.speedRoll || 0}</span>
        `;
        // Use Global Helper for Detail
        item.addEventListener('click', () => {
            if (typeof showCharacterDetail === 'function') showCharacterDetail(char.id)
        });
        timelineEl.appendChild(item);
    });
}

console.log('[visual_ui] Loaded.');
