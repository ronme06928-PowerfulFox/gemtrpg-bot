
// ============================================================
// ★ Wide Match Dock Icon Handler (Phase 11.3)
// ============================================================

// 広域マッチアイコンの初期化とクリックハンドラー
function initializeWideMatchDockIcon() {
    const wideMatchIcon = document.getElementById('dock-wide-match-icon');
    if (!wideMatchIcon) return;

    wideMatchIcon.onclick = () => {
        // 簡易実装: 攻撃者と防御者をアラートで選択
        // 本格実装ではマップ上でクリック選択するモードを実装

        if (!battleState || !battleState.characters) {
            alert('キャラクターが存在しません。');
            return;
        }

        // テスト用: 最初のキャラを攻撃者、残りを防御者として設定
        const chars = battleState.characters.filter(c => c.hp > 0);
        if (chars.length < 2) {
            alert('広域マッチには2人以上のキャラクターが必要です。');
            return;
        }

        const attackerId = chars[0].id;
        const defenderIds = chars.slice(1).map(c => c.id);

        // 広域マッチ開始
        if (typeof openWideMatchPanel === 'function') {
            openWideMatchPanel(attackerId, defenderIds, true);
        } else {
            console.error('openWideMatchPanel function not found');
        }
    };
}

// Add to initialization
if (typeof window !== 'undefined') {
    window.initializeWideMatchDockIcon = initializeWideMatchDockIcon;
}
