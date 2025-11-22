// --- 7. スキル検索タブ ---
function setupSkillSearchTab() {
    setupSearchBox('1');
    setupSearchBox('2');
}

function setupSearchBox(boxId) {
    const container = document.getElementById(`search-box-${boxId}`);
    if (!container) return;
    const categorySelect = container.querySelector(`#category-${boxId}`);
    const numberInput = container.querySelector(`#number-${boxId}`);
    const searchSkillInput = container.querySelector(`#search-skill-${boxId}`);
    const physInput = container.querySelector(`#phys-${boxId}`);
    const magInput = container.querySelector(`#mag-${boxId}`);
    let currentSkillData = null;

    const searchSkill = async () => {
        const category = categorySelect.value;
        const number = numberInput.value;
        const numberPadded = String(number).padStart(2, '0');
        const skillId = `${category}-${numberPadded}`;
        searchSkillInput.value = skillId;
        try {
            const response = await fetchWithSession(`/get_skill?id=${skillId}`);
            const data = await response.json();
            if (response.ok) {
                currentSkillData = data;
                displaySkillInfo(data);
            } else {
                currentSkillData = null;
                displaySkillInfo(null, data.error);
            }
        } catch (error) {
            currentSkillData = null;
            displaySkillInfo(null, 'サーバーに接続できません。app.pyを確認してください。');
        }
        calculatePower();
    };

    const displaySkillInfo = (data, errorMsg = null) => {
        const fields = container.querySelectorAll('[data-field]');
        if (errorMsg) {
            fields.forEach(field => {
                field.textContent = (field.dataset.field === 'デフォルト名称') ? errorMsg : '---';
            });
            return;
        }
        fields.forEach(field => {
            const fieldName = field.dataset.field;
            field.textContent = data[fieldName] || '---';
        });
    };

    const calculatePower = () => {
        const minEl = container.querySelector(`#power-min-${boxId}`);
        const maxEl = container.querySelector(`#power-max-${boxId}`);
        if (!currentSkillData || !currentSkillData.基礎威力) {
            minEl.textContent = 0;
            maxEl.textContent = 0;
            return;
        }
        const basePower = parseInt(currentSkillData.基礎威力, 10) || 0;
        const diceRollStr = currentSkillData.ダイス威力 || "";
        const chatPalette = currentSkillData.チャットパレット || "";
        const physCorrection = parseInt(physInput.value, 10) || 0;
        const magCorrection = parseInt(magInput.value, 10) || 0;
        let diceMin = 0, diceMax = 0;
        if (diceRollStr.includes('d')) {
            const parts = diceRollStr.split('d');
            diceMin = 1;
            diceMax = parseInt(parts[1], 10) || 0;
        }
        let applicableCorrection = 0, correctionMin = 0;
        if (chatPalette.includes('{物理補正}')) {
            applicableCorrection = physCorrection;
            if (physCorrection >= 1) correctionMin = 1;
        } else if (chatPalette.includes('{魔法補正}')) {
            applicableCorrection = magCorrection;
            if (magCorrection >= 1) correctionMin = 1;
        }
        let minValue = basePower;
        if (basePower > 0 || diceMax > 0) {
             minValue += diceMin + correctionMin;
        }
        const maxValue = basePower + diceMax + applicableCorrection;
        minEl.textContent = minValue;
        maxEl.textContent = maxValue;
    };

    categorySelect.addEventListener('change', searchSkill);
    numberInput.addEventListener('change', searchSkill);
    numberInput.addEventListener('input', searchSkill);
    physInput.addEventListener('input', calculatePower);
    magInput.addEventListener('input', calculatePower);

    // 初期読み込み
    searchSkill();
}