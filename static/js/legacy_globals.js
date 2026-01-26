// --- Moved from tab_visual_battle.js for Refactoring Phase 1 ---

// --- 定数定義 ---
window.GRID_SIZE = 90; // マスのサイズ（ピクセル）
window.FIELD_SIZE = 25; // フィールドのグリッド数（25x25）
window.MAX_FP = 15; // FP（ファイトポイント）の最大値
window.TOKEN_OFFSET = 4; // トークンの位置調整オフセット（ピクセル）
window.PERCENTAGE_MAX = 100; // パーセンテージの最大値
window.CENTER_OFFSET_X = -900; // 25x25フィールドの中央表示用（X軸）
window.CENTER_OFFSET_Y = -900; // 25x25フィールドの中央表示用（Y軸）

window.STATUS_CONFIG = {
    '出血': { icon: 'bleed.png', color: '#dc3545', borderColor: '#ff0000' },
    '破裂': { icon: 'rupture.png', color: '#28a745', borderColor: '#00ff00' },
    '亀裂': { icon: 'fissure.png', color: '#007bff', borderColor: '#0000ff' },
    '戦慄': { icon: 'fear.png', color: '#17a2b8', borderColor: '#00ffff' },
    '荊棘': { icon: 'thorns.png', color: '#155724', borderColor: '#0f0' }
};

// --- ヘルパー: 広域スキル判定 ---
window.isWideSkillData = function (skillData) {
    if (!skillData) return false;
    const tags = skillData['tags'] || [];
    const cat = skillData['分類'] || '';
    const dist = skillData['距離'] || '';
    return (tags.includes('広域-個別') || tags.includes('広域-合算') ||
        cat.includes('広域') || dist.includes('広域'));
};

window.hasWideSkill = function (char) {
    if (!window.allSkillData || !char.commands) return false;
    const regex = /【(.*?)\s+(.*?)】/g;
    let match;
    while ((match = regex.exec(char.commands)) !== null) {
        const skillId = match[1];
        const skillData = window.allSkillData[skillId];
        if (skillData && window.isWideSkillData(skillData)) {
            return true;
        }
    }
    return false;
};

// --- ヘルパー: 結果表示フォーマット ---
window.formatWideResult = function (data) {
    if (data.error) return data.final_command || "Error";
    const min = (data.min_damage != null) ? data.min_damage : '?';
    const max = (data.max_damage != null) ? data.max_damage : '?';
    // 表示用: Range: X~Y (Command)
    return `Range: ${min}～${max} (${data.final_command})`;
};

// --- ★ 追加: スキル詳細HTML生成ヘルパー ---
// 2つのデータ形式に対応:
// 1) サーバー変換済み (socket_battle.py): コスト, 効果
// 2) 生データ (allSkillData): 使用時効果, 発動時効果
window.formatSkillDetailHTML = function (skillData) {
    if (!skillData) return "";

    const category = skillData['タイミング'] || skillData['分類'] || '';
    const range = skillData['射程'] || skillData['距離'] || '';
    const attribute = skillData['属性'] || '';
    const special = skillData['特記'] || '';

    // コスト: サーバー変換済み(コスト) OR 生データ(使用時効果)
    let cost = skillData['コスト'] || skillData['使用時効果'] || '';
    if (typeof cost === 'string') cost = cost.trim();
    if (!cost) cost = '';

    // 効果: サーバー変換済み(効果) OR 生データ(発動時効果)
    let effect = skillData['効果'] || skillData['発動時効果'] || '';
    if (typeof effect === 'string') effect = effect.trim();
    if (effect === 'なし') effect = '';

    let html = ``;

    // タグ行
    html += `<div style="display:flex; gap:4px; margin-bottom:8px; flex-wrap:wrap;">`;
    if (category) html += `<span style="background:#007bff; color:#fff; padding:2px 6px; border-radius:8px; font-size:0.75em; font-weight:bold;">${category}</span>`;
    if (range) html += `<span style="background:#6c757d; color:#fff; padding:2px 6px; border-radius:8px; font-size:0.75em; font-weight:bold;">射程:${range}</span>`;
    if (attribute && attribute !== '---') html += `<span style="background:#ffc107; color:#212529; padding:2px 6px; border-radius:8px; font-size:0.75em; font-weight:bold;">属性:${attribute}</span>`;
    html += `</div>`;

    // 詳細セクション
    const hasCost = cost && cost !== 'なし' && cost !== '';
    const hasEffect = effect && effect !== '';
    const hasSpecial = special && special !== 'なし' && special.trim() !== '';

    if (hasCost || hasEffect || hasSpecial) {
        html += `<hr style="margin:6px 0; border:0; border-top:1px solid #555;">`;
    }

    if (hasCost) {
        html += `<div style="margin-bottom:4px; font-size:0.85em;"><strong>【コスト】</strong>${cost}</div>`;
    }
    if (hasEffect) {
        html += `<div style="margin-bottom:4px; font-size:0.85em;"><strong>【効果】</strong><div style="white-space:pre-wrap; line-height:1.3; padding-left:1em;">${effect}</div></div>`;
    }
    if (hasSpecial) {
        html += `<div style="font-size:0.85em;"><strong>【特記】</strong><div style="white-space:pre-wrap; line-height:1.3; padding-left:1em;">${special}</div></div>`;
    }

    return html;
};

// --- 計算・ダイス関数 ---
window.safeMathEvaluate = function (expression) {
    try {
        const sanitized = expression.replace(/[^-()\d/*+.]/g, '');
        return new Function('return ' + sanitized)();
    } catch (e) { console.error("Safe math eval error:", e); return 0; }
};

window.rollDiceCommand = function (command) {
    let calculation = command.replace(/【.*?】/g, '').trim();
    calculation = calculation.replace(/^(\/sroll|\/sr|\/roll|\/r)\s*/i, '');
    let details = calculation;
    const diceRegex = /(\d+)d(\d+)/g;
    let match;
    const allDiceDetails = [];
    while ((match = diceRegex.exec(calculation)) !== null) {
        const numDice = parseInt(match[1]);
        const numFaces = parseInt(match[2]);
        let sum = 0;
        const rolls = [];
        for (let i = 0; i < numDice; i++) {
            const roll = Math.floor(Math.random() * numFaces) + 1;
            rolls.push(roll);
            sum += roll;
        }
        allDiceDetails.push({ original: match[0], details: `(${rolls.join('+')})`, sum: sum });
    }
    for (let i = allDiceDetails.length - 1; i >= 0; i--) {
        const roll = allDiceDetails[i];
        details = details.replace(roll.original, roll.details);
        calculation = calculation.replace(roll.original, String(roll.sum));
    }
    const total = window.safeMathEvaluate(calculation);
    return { total: total, details: details };
};
