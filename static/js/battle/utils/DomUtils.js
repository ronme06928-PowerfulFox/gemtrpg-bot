export function formatWideResult(data) {
    if (data.error) return data.final_command || "Error";
    const min = (data.min_damage != null) ? data.min_damage : '?';
    const max = (data.max_damage != null) ? data.max_damage : '?';
    // 表示用: Range: X~Y (Command)
    return `Range: ${min}～${max} (${data.final_command})`;
}

export function formatSkillDetailHTML(skillData) {
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
}

// Global Bridge
window.formatWideResult = formatWideResult;
window.formatSkillDetailHTML = formatSkillDetailHTML;
