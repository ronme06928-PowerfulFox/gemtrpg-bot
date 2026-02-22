export function formatWideResult(data) {
    if (data.error) return data.final_command || "Error";
    const min = (data.min_damage != null) ? data.min_damage : '?';
    const max = (data.max_damage != null) ? data.max_damage : '?';
    // 表示用: Range: X~Y (Command)
    return `Range: ${min}～${max} (${data.final_command})`;
}

export function formatSkillDetailHTML(skillData) {
    if (!skillData) return "";

    const escapeText = (value) => {
        if (window.Glossary && typeof window.Glossary.escapeHtml === 'function') {
            return window.Glossary.escapeHtml(value);
        }
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };
    const markupToHtml = (value) => {
        if (typeof window.formatGlossaryMarkupToHTML === 'function') {
            return window.formatGlossaryMarkupToHTML(value);
        }
        if (window.Glossary && typeof window.Glossary.parseMarkupToHTML === 'function') {
            return window.Glossary.parseMarkupToHTML(value);
        }
        return escapeText(value).replace(/\n/g, '<br>');
    };

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

    const hasCost = cost && cost !== 'なし' && cost !== '';
    const hasEffect = effect && effect !== '';
    const hasSpecial = special && special !== 'なし' && special.trim() !== '';
    const command = skillData['チャットパレット'] || '';

    let html = `<div class="skill-detail-card">`;
    html += `<div class="skill-detail-tags">`;
    if (category) html += `<span class="skill-detail-pill is-category">${escapeText(category)}</span>`;
    if (range) html += `<span class="skill-detail-pill is-range">射程:${escapeText(range)}</span>`;
    if (attribute && attribute !== '---') html += `<span class="skill-detail-pill is-attr">属性:${escapeText(attribute)}</span>`;
    html += `</div>`;

    if (command) {
        html += `
            <section class="skill-detail-section skill-detail-section-command">
                <div class="skill-detail-label">コマンド</div>
                <div class="skill-detail-command">${markupToHtml(command)}</div>
            </section>
        `;
    }

    if (hasCost || hasEffect || hasSpecial) {
        html += `<div class="skill-detail-divider"></div>`;
    }

    if (hasCost) {
        html += `
            <section class="skill-detail-section">
                <div class="skill-detail-label">【コスト】</div>
                <div class="skill-detail-main">${markupToHtml(cost)}</div>
            </section>
        `;
    }
    if (hasEffect) {
        html += `
            <section class="skill-detail-section">
                <div class="skill-detail-label">【効果】</div>
                <div class="skill-detail-main">${markupToHtml(effect)}</div>
            </section>
        `;
    }
    if (hasSpecial) {
        html += `
            <section class="skill-detail-section">
                <div class="skill-detail-label">【特記】</div>
                <div class="skill-detail-main">${markupToHtml(special)}</div>
            </section>
        `;
    }
    if (!hasCost && !hasEffect && !hasSpecial && !command) {
        html += `<div class="skill-detail-empty">説明未登録</div>`;
    }

    html += `</div>`;
    return html;
}

// Global Bridge
window.formatWideResult = formatWideResult;
window.formatSkillDetailHTML = formatSkillDetailHTML;
