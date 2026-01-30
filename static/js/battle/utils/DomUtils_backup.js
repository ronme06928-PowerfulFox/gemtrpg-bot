export function formatWideResult(data) {
    if (data.error) return data.final_command || "Error";
    const min = (data.min_damage != null) ? data.min_damage : '?';
    const max = (data.max_damage != null) ? data.max_damage : '?';
    // 表示用: Range: X~Y (Command)
    return `Range: ${min}～${max} (${data.final_command})`;
}

export function formatSkillDetailHTML(skillData) {
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
        html += `<div style="margin-bottom:4px; font-size:0.85em;"><strong>【効果】</strong><div style="white-space:pre-wrap; line-height:1.3;">${effect}</div></div>`;
    }
    if (hasSpecial) {
        html += `<div style="font-size:0.85em;"><strong>【特記】</strong><div style="white-space:pre-wrap; line-height:1.3;">${special}</div></div>`;
    }

    return html;
}

// Global Bridge
window.formatWideResult = formatWideResult;
window.formatSkillDetailHTML = formatSkillDetailHTML;
