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
window.formatSkillDetailHTML = function (skillData) {
    if (!skillData) return "";

    const name = skillData['名称'] || skillData['デフォルト名称'] || skillData['name'] || 'Skill';
    const category = skillData['タイミング'] || skillData['分類'] || skillData['category'];
    const range = skillData['射程'] || skillData['range'] || skillData['distance'];
    const attribute = skillData['属性'] || skillData['attribute'] || '---';
    const special = skillData['特記'] || skillData['特記'] || skillData['special']; // 重複キー対応
    const cost = skillData['コスト'] || 'なし';
    const effect = skillData['効果'] || '';

    let html = ``; // タイトルは削除済み

    // タグ行
    html += `<div class="skill-tags" style="display:flex; gap:5px; margin-bottom:12px; flex-wrap:wrap;">`;
    if (category) html += `<span class="skill-tag category" style="background:#007bff; color:#fff; padding:3px 8px; border-radius:12px; font-size:0.85em; font-weight:bold;">${category}</span>`;
    if (range) html += `<span class="skill-tag range" style="background:#6c757d; color:#fff; padding:3px 8px; border-radius:12px; font-size:0.85em; font-weight:bold;">射程: ${range}</span>`;
    if (attribute) html += `<span class="skill-tag attribute" style="background:#ffc107; color:#212529; padding:3px 8px; border-radius:12px; font-size:0.85em; font-weight:bold;">属性: ${attribute}</span>`;
    html += `</div>`;

    // 区切り線
    if ((cost && cost !== '---') || effect || special) {
        html += `<hr style="margin: 8px 0; border: 0; border-top: 1px solid #444;">`;
    }

    // 詳細
    if (cost && cost !== '---') {
        html += `<div class="skill-detail-row" style="margin-bottom:6px;"><span class="label" style="font-weight:bold;">【コスト】</span> <span class="value">${cost}</span></div>`;
    }
    if (effect) {
        html += `<div class="skill-detail-section" style="margin-top:8px; margin-bottom:8px;"><div class="label" style="font-weight:bold;">【効果】</div><div class="text" style="white-space:pre-wrap; line-height:1.4;">${effect}</div></div>`;
    }
    if (special && special !== 'なし') {
        html += `<div class="skill-detail-section" style="margin-top:8px;"><div class="label" style="font-weight:bold;">【特記】</div><div class="text" style="white-space:pre-wrap; line-height:1.4;">${special}</div></div>`;
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
