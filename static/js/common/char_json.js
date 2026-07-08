/* static/js/common/char_json.js */
// キャラクターJSON読込（➕キャラ追加モーダルから使用）。計画書32（戦闘UI一本化）
// Phase 1 で static/js/tab_battlefield.js から移設。ロジックは移設前と同一（機能変更なし）。

function parseCharacterJsonToCharacterData(type, jsonString, options = {}) {
    if (!jsonString) {
        return { ok: false, message: 'JSONを貼り付けてください。' };
    }
    try {
        const charJson = JSON.parse(jsonString);
        const data = (charJson && typeof charJson.data === 'object') ? charJson.data : null;
        if (!data) {
            return { ok: false, message: 'character JSONの data が見つかりません。' };
        }

        const toInt = (value, fallback = 0) => {
            const n = Number.parseInt(value, 10);
            return Number.isFinite(n) ? n : fallback;
        };
        const clone = (obj) => JSON.parse(JSON.stringify(obj));

        const rawStatuses = Array.isArray(data.status) ? clone(data.status) : [];
        const normalizedStatuses = rawStatuses.map((row) => {
            if (!row || typeof row !== 'object') return null;
            const label = String(row.label || row.name || '').trim();
            if (!label) return null;
            const value = toInt(row.value, 0);
            const max = toInt((row.max !== undefined ? row.max : value), value);
            return { label, value, max };
        }).filter(Boolean);

        const statusByLabel = new Map();
        normalizedStatuses.forEach((row) => statusByLabel.set(row.label, row));
        const hpStatus = statusByLabel.get('HP') || null;
        const mpStatus = statusByLabel.get('MP') || null;

        const states = normalizedStatuses
            .filter((row) => row.label !== 'HP' && row.label !== 'MP')
            .map((row) => ({
                name: row.label,
                value: row.value,
                max: row.max,
            }));

        const requiredStates = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘'];
        requiredStates.forEach((name) => {
            if (!states.some((s) => String(s.name || '').trim() === name)) {
                states.push({ name, value: 0, max: 0 });
            }
        });

        const forcedType = (type === 'ally') ? 'ally' : 'enemy';
        const gmOnly = (options && typeof options.gmOnly === 'boolean')
            ? options.gmOnly
            : (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

        const charData = clone(data);
        charData.name = String(data.name || '名前不明');
        charData.type = forcedType;
        charData.color = (data.color && typeof data.color === 'string')
            ? data.color
            : ((forcedType === 'ally') ? '#007bff' : '#dc3545');
        charData.hp = hpStatus ? hpStatus.value : toInt(data.hp, 0);
        charData.maxHp = hpStatus ? hpStatus.max : toInt(data.maxHp, charData.hp);
        charData.mp = mpStatus ? mpStatus.value : toInt(data.mp, 0);
        charData.maxMp = mpStatus ? mpStatus.max : toInt(data.maxMp, charData.mp);
        charData.params = Array.isArray(data.params) ? clone(data.params) : [];
        charData.commands = String(data.commands || '');
        charData.states = states;
        charData.status = normalizedStatuses;
        charData.initial_status = clone(normalizedStatuses);
        charData.speedRoll = toInt(data.speedRoll, 0);
        charData.hasActed = false;
        charData.gmOnly = gmOnly;
        charData.SPassive = Array.isArray(data.SPassive) ? clone(data.SPassive) : [];
        charData.inventory = (data.inventory && typeof data.inventory === 'object') ? clone(data.inventory) : {};
        if (!Array.isArray(charData.hidden_skills)) charData.hidden_skills = [];
        if (!Array.isArray(charData.radiance_skills)) charData.radiance_skills = [];
        if (!Array.isArray(charData.special_buffs)) charData.special_buffs = [];
        if (!charData.flags || typeof charData.flags !== 'object') charData.flags = {};

        return { ok: true, charData };
    } catch (error) {
        return { ok: false, message: 'JSONの形式が正しくありません。エラー: ' + error.message };
    }
}

if (typeof window !== 'undefined') {
    window.parseCharacterJsonToCharacterData = parseCharacterJsonToCharacterData;
}

function loadCharacterFromJSON(type, jsonString, resultElement) {
    const parsed = parseCharacterJsonToCharacterData(type, jsonString, { gmOnly: (currentUserAttribute === 'GM') });
    if (!parsed.ok) {
        resultElement.textContent = parsed.message;
        resultElement.style.color = 'red';
        return false;
    }
    socket.emit('request_add_character', {
        room: currentRoomName,
        charData: parsed.charData
    });
    resultElement.textContent = `読込成功: ${parsed.charData.name} を ${type === 'ally' ? '味方' : '敵'}として追加リクエスト`;
    resultElement.style.color = 'green';
    return true;
}
