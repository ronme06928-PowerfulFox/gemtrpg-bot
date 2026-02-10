/* static/js/visual/visual_arrows.js */

/**
 * 矢印表示フラグ
 * visual_globals.js で定義されていない場合のフォールバック
 */
window.VISUAL_SHOW_ARROWS = (typeof window.VISUAL_SHOW_ARROWS !== 'undefined') ? window.VISUAL_SHOW_ARROWS : true;

/**
 * 矢印を描画するメイン関数
 * map-arrow-layer (SVG) をクリアして再描画する
 */
window.renderArrows = function () {
    const layer = document.getElementById('map-arrow-layer');
    if (!layer) return;
    layer.style.zIndex = "9999"; // Force z-index to ensure visibility

    // クリア
    while (layer.lastChild) {
        layer.removeChild(layer.lastChild);
    }

    if (!window.VISUAL_SHOW_ARROWS) return;

    // ★ Added: Hide arrows if not in PvE mode (User requirement)
    if (battleState.battle_mode !== 'pve') return;

    if (!battleState || !battleState.ai_target_arrows) return;

    const currentTurnCharId = battleState.turn_char_id;

    // 定義: 矢印マーカー(Arrowhead)
    // SVG内で再利用するために一度だけ定義するか、都度パスを描くか。
    // シンプルに都度パスを描くか、defsを追加するか。defsの方が綺麗。
    if (!document.getElementById('arrow-defs')) {
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        defs.id = 'arrow-defs';

        // 赤マーカー
        const markerRed = createMarker('arrowhead-red', '#dc3545', 0.9);
        defs.appendChild(markerRed);

        // 警告マーカー
        const markerWarn = createMarker('arrowhead-warn', '#ffc107', 0.9);
        defs.appendChild(markerWarn);

        // デフォルトマーカー
        const markerGray = createMarker('arrowhead-gray', '#888', 0.5);
        defs.appendChild(markerGray);

        // 青マーカー (Enemy Intent) ★追加
        const markerBlue = createMarker('arrowhead-blue', '#1e90ff', 0.9);
        defs.appendChild(markerBlue);

        layer.appendChild(defs);
    }

    battleState.ai_target_arrows.forEach(arrow => {
        if (!arrow.visible) return;

        const fromId = arrow.from_id;
        const toId = arrow.to_id;

        const fromEl = document.querySelector(`.map-token[data-id="${fromId}"]`);
        const toEl = document.querySelector(`.map-token[data-id="${toId}"]`);

        if (!fromEl || !toEl) return;

        // ★ Added: Has acted check (Display nothing)
        const fromChar = battleState.characters.find(c => String(c.id) === String(fromId));
        if (fromChar && fromChar.hasActed) return;

        // 座標計算 (Tokenの中心)
        // offsetLeft/Top は relative parent (game-map) からの座標なのでそのまま使える
        const fromX = parseFloat(fromEl.style.left) + (fromEl.offsetWidth / 2);
        const fromY = parseFloat(fromEl.style.top) + (fromEl.offsetHeight / 2);

        const toX = parseFloat(toEl.style.left) + (toEl.offsetWidth / 2);
        const toY = parseFloat(toEl.style.top) + (toEl.offsetHeight / 2);

        // 距離が近すぎる場合は描画しない
        const dx = toX - fromX;
        const dy = toY - fromY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 20) return;

        // ターゲットの縁で止める (オプション: トークン半径分引く)
        const targetRadius = (toEl.offsetWidth / 2) + 5;
        const sourceRadius = (fromEl.offsetWidth / 2) + 5;

        const angle = Math.atan2(dy, dx);
        const endX = toX - Math.cos(angle) * targetRadius;
        const endY = toY - Math.sin(angle) * targetRadius;

        const startX = fromX + Math.cos(angle) * sourceRadius;
        const startY = fromY + Math.sin(angle) * sourceRadius;

        // 色決定
        let color = '#888';
        let markerId = 'arrowhead-gray';
        let strokeWidth = 2;
        let opacity = 0.5; // Slightly more visible for gray
        let strokeDashArray = "5,5"; // Default dotted for planned actions

        // 判定ロジック
        // 1. 攻撃者の手番 (Active Enemy/Ally)
        if (currentTurnCharId === fromId) {
            color = '#dc3545'; // Red
            markerId = 'arrowhead-red';
            strokeWidth = 4;
            opacity = 0.9;
            strokeDashArray = "none"; // Solid for active
        }
        // 2. 防御者の手番 かつ 自分がターゲット (Warning)
        else if (currentTurnCharId === toId) {
            color = '#ffc107'; // Warning Yellow
            markerId = 'arrowhead-warn';
            strokeWidth = 4;
            opacity = 0.9;
            strokeDashArray = "none";
        }
        // 3. 敵の非手番 (Enemy Intent - Blue) ★追加
        // char.type判定: 'enemy', 'boss' など (ally, player 以外)
        else if (fromChar && fromChar.type !== 'ally' && fromChar.type !== 'player') {
            color = '#1e90ff'; // DodgerBlue
            markerId = 'arrowhead-blue'; // Need to create this marker
            strokeWidth = 3;
            opacity = 0.9; // Explicitly visible
            strokeDashArray = "none"; // Solid line to be "firmly recognized"
        }

        // SVG要素作成
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', startX);
        line.setAttribute('y1', startY);
        line.setAttribute('x2', endX);
        line.setAttribute('y2', endY);
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-width', strokeWidth);
        line.setAttribute('opacity', opacity);
        if (strokeDashArray !== "none") {
            line.setAttribute('stroke-dasharray', strokeDashArray);
        }
        line.setAttribute('marker-end', `url(#${markerId})`);

        // アニメーション (Active時のみ破線アニメーション等)
        if (opacity === 1.0) {
            // line.classList.add('active-arrow'); // CSSでアニメーション定義が必要
            // 簡易的に dasharray で動きをつけるならJSで...だが重くなるので一旦静的
        }

        layer.appendChild(line);
    });
};

function createMarker(id, color, opacity = 1.0) {
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', id);
    marker.setAttribute('markerWidth', '10');
    marker.setAttribute('markerHeight', '10');
    marker.setAttribute('refX', '7'); // 先端位置
    marker.setAttribute('refY', '3');
    marker.setAttribute('orient', 'auto');
    marker.setAttribute('markerUnits', 'strokeWidth');

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M0,0 L0,6 L9,3 z');
    path.setAttribute('fill', color);
    path.setAttribute('fill-opacity', opacity);

    marker.appendChild(path);
    return marker;
}
