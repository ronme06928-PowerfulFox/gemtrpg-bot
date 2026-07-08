/* static/js/visual/visual_wide.js */

// ============================================
// Wide Match Logic (Visual)
// ============================================

window.visualWideState = {
    attackerId: null,
    isDeclared: false
};

/**
 * 広域宣言モーダル (Visual版)
 * 誰が広域攻撃を行うかを予約する画面
 */
window.openVisualWideDeclarationModal = function () {
    const existing = document.getElementById('visual-wide-decl-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'visual-wide-decl-modal';
    backdrop.className = 'modal-backdrop';

    let listHtml = '';
    battleState.characters.forEach(char => {
        if (char.hp <= 0) return;
        // 未配置キャラクターは除外
        if (char.x < 0 || char.y < 0) return;

        // hasWideSkill check (Assumed Global or Utility)
        if (typeof hasWideSkill === 'function' && !hasWideSkill(char)) return;

        const typeColor = char.type === 'ally' ? '#007bff' : '#dc3545';
        listHtml += `
            <div style="padding: 10px; border-bottom: 1px solid #eee; display:flex; align-items:center;">
                <input type="checkbox" class="visual-wide-check" value="${char.id}" style="transform:scale(1.3); margin-right:15px;">
                <span style="font-weight:bold; color:${typeColor}; font-size:1.1em;">${char.name}</span>
                <span style="margin-left:auto; color:#666;">SPD: ${char.totalSpeed || char.speedRoll || 0}</span>
            </div>
        `;
    });

    if (!listHtml) listHtml = '<div style="padding:15px; color:#666;">広域スキルを所持するキャラクターがいません</div>';

    backdrop.innerHTML = `
        <div class="modal-content" style="width: 500px; padding: 0;">
            <div style="padding: 15px; background: #6f42c1; color: white; border-radius: 8px 8px 0 0;">
                <h3 style="margin:0;">⚡ 広域攻撃予約 (Visual)</h3>
            </div>
            <div style="padding: 20px; max-height: 60vh; overflow-y: auto;">
                <p>今ラウンド、広域攻撃を行うキャラクターを選択してください。<br>
                ※GMまたは全員が確認ボタンを押すと確定します。</p>
                <div style="border: 1px solid #ddd; border-radius: 4px;">${listHtml}</div>
            </div>
            <div style="padding: 15px; background: #f8f9fa; text-align: right; border-radius: 0 0 8px 8px;">
                <button id="visual-wide-confirm" class="duel-btn primary" style="width:100%;">決定 (確認)</button>
            </div>
        </div>
    `;

    document.body.appendChild(backdrop);
    const confirmBtn = document.getElementById('visual-wide-confirm');
    confirmBtn.onclick = () => {
        const checks = backdrop.querySelectorAll('.visual-wide-check');
        const ids = Array.from(checks).filter(c => c.checked).map(c => c.value);

        socket.emit('request_wide_modal_confirm', { room: currentRoomName, wideUserIds: ids });

        confirmBtn.disabled = true;
        confirmBtn.textContent = "確認済み: 他プレイヤー待機中...";
        confirmBtn.classList.remove('primary');
        confirmBtn.classList.add('secondary');
    };
}

// openVisualWideMatchModal / renderVisualWideDefenders は計画書32 Phase 3 で削除。
// 呼び出し元が皆無の死にコードで、内部の socket.emit('request_wide_match', ...) も
// サーバ側ハンドラが存在しない no-op イベントだった（広域攻撃の実処理は
// wide_match_synced.js の wide_declare_skill / execute_synced_wide_match 経由）。
console.log('[visual_wide] Loaded.');
