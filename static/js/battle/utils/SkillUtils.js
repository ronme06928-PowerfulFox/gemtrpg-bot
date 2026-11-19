// キャラのチャットパレットの【ID 名前】（[ID 名前]・区切りの「:」「：」も可）から、そのスキルに付けた名前を返す。無ければ ''。
export function skillNameFromCommands(actor, skillId) {
    const sid = String(skillId || '').trim();
    if (!sid) return '';
    const regex = /[【\[]([^\s:：\]】]+)[\s:：]+([^】\]]+)[】\]]/g;
    for (const match of String(actor?.commands || '').matchAll(regex)) {
        const name = match[2].trim();
        if (match[1] === sid && name) return name;
    }
    return '';
}

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
if (typeof window !== 'undefined') {
    window.isWideSkillData = isWideSkillData;
    window.hasWideSkill = hasWideSkill;
    window.skillNameFromCommands = skillNameFromCommands;
}
