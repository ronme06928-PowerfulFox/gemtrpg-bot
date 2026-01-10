export function isWideSkillData(skillData) {
    if (!skillData) return false;
    const tags = skillData['tags'] || [];
    const cat = skillData['分類'] || '';
    const dist = skillData['距離'] || '';
    return (tags.includes('広域-個別') || tags.includes('広域-合算') ||
        cat.includes('広域') || dist.includes('広域'));
}

export function hasWideSkill(char) {
    if (!window.allSkillData || !char.commands) return false;
    const regex = /【(.*?)\s+(.*?)】/g;
    let match;
    while ((match = regex.exec(char.commands)) !== null) {
        const skillId = match[1];
        const skillData = window.allSkillData[skillId];
        if (skillData && isWideSkillData(skillData)) {
            return true;
        }
    }
    return false;
}

// Global Bridge
window.isWideSkillData = isWideSkillData;
window.hasWideSkill = hasWideSkill;
