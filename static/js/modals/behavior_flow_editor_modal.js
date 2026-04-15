// Extracted from modals.js to keep file size manageable.
(function (global) {
// Shared globals: socket, currentRoomName, battleState, allSkillData.

function coerceBehaviorConditionValue(rawValue) {
    const text = String(rawValue ?? '').trim();
    if (!text) return '';
    if (/^-?\d+$/.test(text)) return parseInt(text, 10);
    if (/^-?\d+\.\d+$/.test(text)) return parseFloat(text);
    if (text.toLowerCase() === 'true') return true;
    if (text.toLowerCase() === 'false') return false;
    return text;
}

function escapeBehaviorEditorHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => (
        {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[ch]
    ));
}

function normalizeBehaviorProfileForEditor(rawProfile) {
    const profile = (rawProfile && typeof rawProfile === 'object') ? rawProfile : {};
    const loopsRaw = (profile.loops && typeof profile.loops === 'object') ? profile.loops : {};
    const loops = {};

    Object.keys(loopsRaw).forEach((rawLoopId) => {
        const loopId = String(rawLoopId || '').trim();
        if (!loopId) return;
        const loopData = (loopsRaw[rawLoopId] && typeof loopsRaw[rawLoopId] === 'object') ? loopsRaw[rawLoopId] : {};

        const steps = Array.isArray(loopData.steps)
            ? loopData.steps.map((step) => {
                const stepObj = (step && typeof step === 'object') ? step : {};
                const actionsRaw = Array.isArray(stepObj.actions) ? stepObj.actions : [];
                const actions = [];
                const inlineTargets = [];
                actionsRaw.forEach((action) => {
                    if (action && typeof action === 'object') {
                        const id = String(action.skill_id || action.skill || action.id || '').trim();
                        actions.push(coerceBehaviorStepSkillId(id));
                        inlineTargets.push(coerceBehaviorStepTargetPolicy(action.target_policy || action.target || action.target_selector));
                        return;
                    }
                    const txt = String(action ?? '').trim();
                    actions.push(coerceBehaviorStepSkillId(txt));
                    inlineTargets.push(BEHAVIOR_STEP_TARGET_POLICY_DEFAULT);
                });

                const rawTargets = Array.isArray(stepObj.targets) ? stepObj.targets : [];
                const baseTargets = rawTargets.length ? rawTargets : inlineTargets;
                const targets = actions.map((_, idx) => coerceBehaviorStepTargetPolicy(baseTargets[idx]));
                const nextLoopIdRaw = String(stepObj.next_loop_id || stepObj.after_step_to_loop_id || '').trim();
                const nextResetRaw = (stepObj.next_reset_step_index !== undefined)
                    ? stepObj.next_reset_step_index
                    : stepObj.after_step_reset_step_index;
                const nextResetStepIndex = (nextResetRaw !== false);
                return {
                    actions,
                    targets,
                    next_loop_id: nextLoopIdRaw || null,
                    next_reset_step_index: nextResetStepIndex
                };
            })
            : [];

        const transitions = Array.isArray(loopData.transitions)
            ? loopData.transitions
                .map((tr) => {
                    const trObj = (tr && typeof tr === 'object') ? tr : {};
                    const toLoopId = String(trObj.to_loop_id || '').trim();
                    if (!toLoopId) return null;
                    const whenAll = Array.isArray(trObj.when_all)
                        ? trObj.when_all
                            .filter((cond) => cond && typeof cond === 'object')
                            .map((cond) => ({
                                source: String(cond.source || 'self').trim() || 'self',
                                param: String(cond.param || '').trim(),
                                operator: String(cond.operator || 'EQUALS').trim().toUpperCase() || 'EQUALS',
                                value: (cond.value === undefined) ? '' : cond.value
                            }))
                        : [];
                    return {
                        priority: Number.isFinite(Number(trObj.priority)) ? parseInt(trObj.priority, 10) : 0,
                        to_loop_id: toLoopId,
                        reset_step_index: trObj.reset_step_index !== false,
                        when_all: whenAll
                    };
                })
                .filter(Boolean)
                .sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0))
            : [];

        loops[loopId] = {
            repeat: loopData.repeat !== false,
            steps,
            transitions
        };
    });

    if (Object.keys(loops).length === 0) {
        loops.loop_1 = {
            repeat: true,
            steps: [{
                actions: [null],
                targets: [BEHAVIOR_STEP_TARGET_POLICY_DEFAULT],
                next_loop_id: null,
                next_reset_step_index: true
            }],
            transitions: []
        };
    }

    const validLoopIds = new Set(Object.keys(loops));
    Object.values(loops).forEach((loopObj) => {
        if (!loopObj || !Array.isArray(loopObj.steps)) return;
        loopObj.steps.forEach((step) => {
            if (!step || typeof step !== 'object') return;
            const nextLoopId = String(step.next_loop_id || '').trim();
            if (!nextLoopId || !validLoopIds.has(nextLoopId)) {
                step.next_loop_id = null;
                step.next_reset_step_index = true;
                return;
            }
            step.next_loop_id = nextLoopId;
            step.next_reset_step_index = (step.next_reset_step_index !== false);
        });
    });

    const loopIds = Object.keys(loops);
    let initialLoopId = String(profile.initial_loop_id || '').trim();
    if (!initialLoopId || !loops[initialLoopId]) initialLoopId = loopIds[0];

    return {
        enabled: !!profile.enabled,
        version: 1,
        initial_loop_id: initialLoopId,
        loops
    };
}

function getCharacterOwnedSkillsForBehaviorEditor(char) {
    const out = [];
    const seen = new Set();
    const add = (skillId, skillName, source) => {
        const id = String(skillId || '').trim();
        if (!id || seen.has(id)) return;
        const all = window.allSkillData || {};
        const dataName = all[id] && all[id].name ? String(all[id].name) : '';
        const name = String(skillName || dataName || id).trim();
        out.push({ id, name, source: source || 'unknown' });
        seen.add(id);
    };

    if (char && typeof char.commands === 'string') {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        while ((match = regex.exec(char.commands)) !== null) {
            add(match[1], match[2], 'commands');
        }
    }

    const granted = Array.isArray(char?.granted_skills) ? char.granted_skills : [];
    granted.forEach((row) => {
        if (!row || typeof row !== 'object') return;
        add(row.skill_id, '', 'granted');
    });

    return out;
}

function getLatestCharacterForBehaviorEditor(charOrId) {
    const targetId = (typeof charOrId === 'string')
        ? String(charOrId || '').trim()
        : String((charOrId && charOrId.id) || '').trim();
    if (!targetId) return (charOrId && typeof charOrId === 'object') ? charOrId : null;
    const chars = (typeof battleState !== 'undefined' && Array.isArray(battleState.characters))
        ? battleState.characters
        : [];
    const latest = chars.find((row) => String((row && row.id) || '').trim() === targetId);
    return (latest && typeof latest === 'object') ? latest : ((charOrId && typeof charOrId === 'object') ? charOrId : null);
}

const BEHAVIOR_STEP_ACTION_RANDOM_USABLE = '__RANDOM_USABLE__';

function coerceBehaviorStepSkillId(rawValue) {
    if (rawValue === null || rawValue === undefined) return null;
    const text = String(rawValue || '').trim();
    if (!text) return null;
    const lower = text.toLowerCase();
    if ([
        '__random_usable__',
        'random_usable',
        '__random_skill__',
        'random_skill',
        '__random__',
        'random',
    ].includes(lower)) {
        return BEHAVIOR_STEP_ACTION_RANDOM_USABLE;
    }
    return text;
}

function formatBehaviorConditionSpec(whenAll) {
    if (!Array.isArray(whenAll) || whenAll.length === 0) return '';
    return whenAll.map((cond) => {
        const src = String(cond?.source || 'self').trim();
        const param = String(cond?.param || '').trim();
        const op = String(cond?.operator || 'EQUALS').trim().toUpperCase();
        const value = String(cond?.value ?? '').trim();
        return `${src}:${param}:${op}:${value}`;
    }).join(' && ');
}

function parseBehaviorConditionSpec(specText) {
    const raw = String(specText || '').trim();
    if (!raw) return [];
    return raw
        .split('&&')
        .map((chunk) => String(chunk || '').trim())
        .filter(Boolean)
        .map((chunk) => {
            const parts = chunk.split(':').map((v) => String(v || '').trim());
            const source = parts[0] || 'self';
            const param = parts[1] || '';
            const operator = (parts[2] || 'EQUALS').toUpperCase();
            const value = coerceBehaviorConditionValue(parts.slice(3).join(':'));
            return { source, param, operator, value };
        });
}

const BEHAVIOR_STEP_TARGET_POLICY_DEFAULT = 'target_enemy_random';
const BEHAVIOR_STEP_TARGET_POLICIES = [
    { value: 'target_enemy_random', label: '敵をランダム' },
    { value: 'target_enemy_fastest', label: '敵の最速' },
    { value: 'target_enemy_slowest', label: '敵の最遅' },
    { value: 'target_ally_random', label: '味方をランダム' },
    { value: 'target_ally_fastest', label: '味方の最速' },
    { value: 'target_ally_slowest', label: '味方の最遅' },
];

const BEHAVIOR_STEP_TARGET_POLICY_KNOWN_VALUES = [
    ...BEHAVIOR_STEP_TARGET_POLICIES.map((row) => row.value),
    'target_self',
];

function coerceBehaviorStepTargetPolicy(rawValue) {
    const text = String(rawValue || '').trim().toLowerCase();
    if (!text) return BEHAVIOR_STEP_TARGET_POLICY_DEFAULT;
    const aliasMap = {
        enemy_random: 'target_enemy_random',
        random_enemy: 'target_enemy_random',
        enemy_fastest: 'target_enemy_fastest',
        enemy_slowest: 'target_enemy_slowest',
        ally_random: 'target_ally_random',
        random_ally: 'target_ally_random',
        ally_fastest: 'target_ally_fastest',
        ally_slowest: 'target_ally_slowest',
        self: 'target_self'
    };
    const normalized = aliasMap[text] || text;
    if (BEHAVIOR_STEP_TARGET_POLICY_KNOWN_VALUES.includes(normalized)) return normalized;
    return BEHAVIOR_STEP_TARGET_POLICY_DEFAULT;
}

const BEHAVIOR_CONDITION_SOURCES = [
    { value: 'self', label: '自身' },
    { value: 'battle', label: '戦闘全体' }
];

const BEHAVIOR_CONDITION_OPERATORS = [
    { value: 'EQUALS', label: '一致 (=)' },
    { value: 'GTE', label: '以上 (>=)' },
    { value: 'LTE', label: '以下 (<=)' },
    { value: 'GT', label: 'より大きい (>)' },
    { value: 'LT', label: 'より小さい (<)' },
    { value: 'CONTAINS', label: '含む' }
];

const BEHAVIOR_CONDITION_PARAM_PRESETS = {
    self: [
        { value: 'HP', label: 'HP' },
        { value: 'MP', label: 'MP' },
        { value: 'FP', label: 'FP' },
        { value: '出血', label: '出血' },
        { value: '破裂', label: '破裂' },
        { value: '亀裂', label: '亀裂' },
        { value: '戦慄', label: '戦慄' },
        { value: '荊棘', label: '荊棘' }
    ],
    battle: [
        { value: 'round', label: 'ラウンド' },
        { value: 'phase', label: 'フェーズ' }
    ]
};

function normalizeBehaviorConditionRow(raw) {
    const cond = (raw && typeof raw === 'object') ? raw : {};
    const source = String(cond.source || 'self').trim().toLowerCase();
    const safeSource = (source === 'battle') ? 'battle' : 'self';
    const operatorRaw = String(cond.operator || 'EQUALS').trim().toUpperCase();
    const safeOperator = BEHAVIOR_CONDITION_OPERATORS.some((op) => op.value === operatorRaw) ? operatorRaw : 'EQUALS';
    return {
        source: safeSource,
        param: String(cond.param || '').trim(),
        operator: safeOperator,
        value: (cond.value === undefined) ? '' : cond.value
    };
}

function getBehaviorConditionParamPresets(source) {
    const key = String(source || 'self').trim().toLowerCase();
    return Array.isArray(BEHAVIOR_CONDITION_PARAM_PRESETS[key])
        ? BEHAVIOR_CONDITION_PARAM_PRESETS[key]
        : BEHAVIOR_CONDITION_PARAM_PRESETS.self;
}

function openBehaviorFlowEditorModal(char, options = {}) {
    const cfg = (options && typeof options === 'object') ? options : {};
    const onSave = (typeof cfg.onSave === 'function') ? cfg.onSave : null;
    const latestChar = getLatestCharacterForBehaviorEditor(char);
    const workingChar = (latestChar && typeof latestChar === 'object') ? latestChar : char;
    if (!workingChar || typeof workingChar !== 'object') return;
    const hasCharId = !!workingChar.id;
    if (!hasCharId && !onSave) return;
    const charId = hasCharId ? String(workingChar.id) : '';
    const existing = document.getElementById('behavior-flow-editor-backdrop');
    if (existing) existing.remove();

    const currentFlags = (workingChar.flags && typeof workingChar.flags === 'object') ? workingChar.flags : {};
    const draft = normalizeBehaviorProfileForEditor(currentFlags.behavior_profile);
    const ownedSkills = getCharacterOwnedSkillsForBehaviorEditor(workingChar);
    let selectedLoopId = String(draft.initial_loop_id || Object.keys(draft.loops)[0] || '');
    const nodeLayout = {};
    let connectFromLoopId = null;
    let isDirty = false;
    const titleText = escapeBehaviorEditorHtml(String(cfg.title || '行動チャート編集（フローチャート）'));
    const subtitleText = escapeBehaviorEditorHtml(String(cfg.subtitle || `${workingChar.name} の行動チャートを視覚的に編集します（内部保存はJSON）。`));
    const contextRows = Array.isArray(cfg.contextRows)
        ? cfg.contextRows.map((row) => String(row || '').trim()).filter((row) => !!row)
        : [];
    const contextHtml = contextRows.length
        ? `<div style="display:flex; flex-wrap:wrap; gap:6px; margin:0 0 10px 0;">
            ${contextRows.map((row) => `
                <span style="display:inline-flex; align-items:center; padding:3px 8px; border-radius:999px; border:1px solid #cfe1f1; background:#fff; color:#35556d; font-size:0.78em;">${escapeBehaviorEditorHtml(row)}</span>
            `).join('')}
        </div>`
        : '';

    function loopIds() {
        return Object.keys(draft.loops || {});
    }

    function buildOwnedSkillOptions(selectedSkillId) {
        const options = [
            { id: '', name: '(未指定)' },
            { id: BEHAVIOR_STEP_ACTION_RANDOM_USABLE, name: '(使用可能スキルからランダム)' },
            ...ownedSkills
        ];
        const selected = String(coerceBehaviorStepSkillId(selectedSkillId) || '').trim();
        if (selected && !options.some((row) => row.id === selected)) {
            options.push({ id: selected, name: `${selected} (所持外)` });
        }
        return options;
    }
    function ensureSelection() {
        const ids = loopIds();
        if (!ids.length) {
            draft.loops.loop_1 = {
                repeat: true,
                steps: [{
                    actions: [null],
                    targets: [BEHAVIOR_STEP_TARGET_POLICY_DEFAULT],
                    next_loop_id: null,
                    next_reset_step_index: true
                }],
                transitions: []
            };
            selectedLoopId = 'loop_1';
            draft.initial_loop_id = 'loop_1';
            return;
        }
        if (!draft.loops[selectedLoopId]) selectedLoopId = ids[0];
        if (!draft.loops[draft.initial_loop_id]) draft.initial_loop_id = ids[0];
    }
    function uniqueLoopId(base) {
        const seed = String(base || 'loop').trim() || 'loop';
        const ids = new Set(loopIds());
        if (!ids.has(seed)) return seed;
        let i = 1;
        while (ids.has(`${seed}_${i}`)) i += 1;
        return `${seed}_${i}`;
    }

    function markDirty() {
        isDirty = true;
        const indicator = content.querySelector('#behavior-dirty-indicator');
        if (indicator) indicator.textContent = '保存状態: 未保存の変更あり';
    }

    function clearDirty() {
        isDirty = false;
        const indicator = content.querySelector('#behavior-dirty-indicator');
        if (indicator) indicator.textContent = '保存状態: 保存済み';
    }

    const overlay = document.createElement('div');
    overlay.id = 'behavior-flow-editor-backdrop';
    overlay.className = 'modal-backdrop';

    const content = document.createElement('div');
    content.className = 'modal-content';
    content.style.maxWidth = '1280px';
    content.style.width = '98vw';
    content.style.maxHeight = '94vh';
    content.style.height = '94vh';
    content.style.overflow = 'auto';
    content.style.padding = '16px';
    content.style.border = '1px solid #cfe1f1';
    content.style.background = '#f7fbff';
    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <h3 style="margin:0; color:#1e4766;">${titleText}</h3>
            <div style="display:flex; align-items:center; gap:8px;">
                <span id="behavior-dirty-indicator" style="font-size:0.8em; color:#5a758b;">保存状態: 保存済み</span>
                <button id="behavior-flow-close-x" style="border:none; background:#dbe9f5; color:#1e4766; padding:6px 10px; border-radius:6px; cursor:pointer;">閉じる</button>
            </div>
        </div>
        <div style="font-size:0.9em; color:#35556d; margin-bottom:10px;">${subtitleText}</div>
        ${contextHtml}
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:10px;">
            <label style="display:flex; align-items:center; gap:6px; background:#fff; border:1px solid #cfe1f1; padding:6px 10px; border-radius:6px;">
                <input type="checkbox" id="behavior-enabled">
                <span>有効化</span>
            </label>
            <label style="display:flex; align-items:center; gap:6px; background:#fff; border:1px solid #cfe1f1; padding:6px 10px; border-radius:6px;">
                <span>初期ループ</span>
                <select id="behavior-initial-loop" style="padding:4px;"></select>
            </label>
            <div style="margin-left:auto; display:flex; gap:6px;">
                <input id="behavior-new-loop-id" placeholder="新規ループ名" style="padding:6px; min-width:180px;">
                <button id="behavior-add-loop-btn" style="padding:6px 10px; border:none; background:#2f7fbf; color:#fff; border-radius:6px; cursor:pointer;">追加</button>
                <button id="behavior-reset-profile-btn" style="padding:6px 10px; border:none; background:#c23b3b; color:#fff; border-radius:6px; cursor:pointer;">チャート初期化</button>
            </div>
        </div>
        <details style="margin-bottom:10px; background:#fff; border:1px solid #cfe1f1; border-radius:8px; padding:8px;" open>
            <summary style="cursor:pointer; font-weight:bold; color:#2a516c;">仕様ガイド（条件分岐・スキル使用）</summary>
                <div style="font-size:0.83em; color:#37596f; margin-top:6px; line-height:1.55;">
                    <div>・<strong>手順</strong>: 1ラウンドごとに現在の手順を参照して行動します（ラウンド終了時に次の手順へ進行）。</div>
                <div>・<strong>手順内スキル</strong>: スロット数より多い場合はランダム抽選、少ない場合は最後のスキルを繰り返します。</div>
                <div>・<strong>ランダム予約</strong>: 「使用可能スキルからランダム」を選ぶと、その手順で使用可能な所持スキルから都度ランダムに選びます。</div>
                <div>・<strong>対象選択</strong>: 行ごとに「相手陣営/同陣営（従来: 敵/味方）」「最速/最遅/ランダム」を指定できます。</div>
                <div>・<strong>手順遷移</strong>: 手順ごとに「スキル使用後にループ遷移」を有効化すると、次ラウンドから指定ループへ進みます。</div>
                <div>・<strong>同陣営対象の指定</strong>: 新規定義は <code>target_scope: "same_team"</code> を推奨。互換として <code>同陣営対象</code> / <code>同陣営指定</code> / <code>味方対象</code> / <code>味方指定</code> / <code>ally_target</code> / <code>target_ally</code> を受理します。</div>
                <div>・<strong>条件遷移</strong>: 優先度が高い順に判定し、最初に成立した遷移だけ適用します。</div>
                <div>・<strong>判定元</strong>: 自身（HP/MP/状態値）または戦闘全体（ラウンド/フェーズなど）。</div>
                <div>・<strong>未保存確認</strong>: 変更後に閉じると確認ダイアログが表示されます。</div>
            </div>
        </details>
        <div style="display:grid; grid-template-columns: 1.15fr 1fr; gap:10px;">
            <div style="background:#fff; border:1px solid #cfe1f1; border-radius:8px; padding:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <div style="font-weight:bold; color:#1e4766;">フローチャート表示</div>
                    <div style="display:flex; gap:6px;">
                        <button id="behavior-connect-start-btn" style="padding:4px 8px; border:none; background:#2f7fbf; color:#fff; border-radius:5px; cursor:pointer; font-size:0.82em;">接続開始</button>
                        <button id="behavior-connect-cancel-btn" style="padding:4px 8px; border:1px solid #b9cddd; background:#fff; color:#2f4858; border-radius:5px; cursor:pointer; font-size:0.82em;">接続解除</button>
                    </div>
                </div>
                <div id="behavior-flow-connect-hint" style="font-size:0.8em; color:#5f7a8f; margin-bottom:5px;">ノードをドラッグで移動。接続開始後に接続先ノードをクリック。</div>
                <div id="behavior-flow-preview"></div>
            </div>
            <div style="background:#fff; border:1px solid #cfe1f1; border-radius:8px; padding:8px;">
                <div style="font-weight:bold; color:#1e4766; margin-bottom:6px;">編集</div>
                <div id="behavior-loop-tabs" style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px;"></div>
                <div id="behavior-loop-editor"></div>
            </div>
        </div>
        <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:12px;">
            <button id="behavior-cancel-btn" style="padding:8px 12px; background:#fff; border:1px solid #b9cddd; border-radius:6px; cursor:pointer;">キャンセル</button>
            <button id="behavior-save-btn" style="padding:8px 12px; background:#2f7fbf; border:none; color:#fff; border-radius:6px; cursor:pointer;">${String(cfg.saveLabel || '保存')}</button>
        </div>
    `;
    overlay.appendChild(content);
    document.body.appendChild(overlay);

    const enabledEl = content.querySelector('#behavior-enabled');
    const initialEl = content.querySelector('#behavior-initial-loop');
    const addLoopBtn = content.querySelector('#behavior-add-loop-btn');
    const resetProfileBtn = content.querySelector('#behavior-reset-profile-btn');
    const newLoopInput = content.querySelector('#behavior-new-loop-id');
    const tabsEl = content.querySelector('#behavior-loop-tabs');
    const previewEl = content.querySelector('#behavior-flow-preview');
    const connectStartBtn = content.querySelector('#behavior-connect-start-btn');
    const connectCancelBtn = content.querySelector('#behavior-connect-cancel-btn');
    const connectHintEl = content.querySelector('#behavior-flow-connect-hint');
    const editorEl = content.querySelector('#behavior-loop-editor');

    clearDirty();
    const closeModal = (force = false) => {
        if (!force && isDirty) {
            const ok = confirm('未保存の変更があります。保存せずに閉じますか？');
            if (!ok) return;
        }
        overlay.remove();
    };
    content.querySelector('#behavior-flow-close-x')?.addEventListener('click', () => closeModal());
    content.querySelector('#behavior-cancel-btn')?.addEventListener('click', () => closeModal());
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });

    function renderInitialLoopOptions() {
        initialEl.innerHTML = '';
        loopIds().forEach((id) => {
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = id;
            if (id === draft.initial_loop_id) opt.selected = true;
            initialEl.appendChild(opt);
        });
    }

    function renderLoopTabs() {
        tabsEl.innerHTML = '';
        loopIds().forEach((id) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = id;
            btn.style.padding = '5px 8px';
            btn.style.border = '1px solid #8fb5d2';
            btn.style.borderRadius = '999px';
            btn.style.cursor = 'pointer';
            btn.style.background = (id === selectedLoopId) ? '#2f7fbf' : '#eef6ff';
            btn.style.color = (id === selectedLoopId) ? '#fff' : '#234c67';
            btn.addEventListener('click', () => {
                selectedLoopId = id;
                renderAll();
            });
            tabsEl.appendChild(btn);
        });
    }

    function ensureNodeLayout() {
        const ids = loopIds();
        const valid = new Set(ids);
        Object.keys(nodeLayout).forEach((id) => {
            if (!valid.has(id)) delete nodeLayout[id];
        });
        ids.forEach((id, idx) => {
            if (!nodeLayout[id]) {
                const col = idx % 2;
                const row = Math.floor(idx / 2);
                nodeLayout[id] = { x: 30 + (col * 210), y: 30 + (row * 130) };
            }
        });
    }

    function renderPreview() {
        previewEl.innerHTML = '';
        const ids = loopIds();
        if (!ids.length) {
            previewEl.innerHTML = '<div style="color:#789; font-size:0.9em;">ループがありません。</div>';
            return;
        }
        ensureNodeLayout();
        const boardW = Math.max(520, Math.min(860, (previewEl?.clientWidth || 640) - 12));
        const boardH = Math.max(300, (Math.ceil(ids.length / 2) * 130) + 90);

        const board = document.createElement('div');
        board.style.position = 'relative';
        board.style.width = `${boardW}px`;
        board.style.height = `${boardH}px`;
        board.style.border = '1px solid #d7e8f6';
        board.style.borderRadius = '8px';
        board.style.background = 'linear-gradient(180deg, #fbfdff 0%, #f3f8fd 100%)';
        board.style.overflow = 'hidden';

        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', String(boardW));
        svg.setAttribute('height', String(boardH));
        svg.style.position = 'absolute';
        svg.style.left = '0';
        svg.style.top = '0';
        svg.style.pointerEvents = 'none';

        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        marker.setAttribute('id', 'behavior-flow-arrow');
        marker.setAttribute('markerWidth', '8');
        marker.setAttribute('markerHeight', '8');
        marker.setAttribute('refX', '7');
        marker.setAttribute('refY', '4');
        marker.setAttribute('orient', 'auto');
        const arrowPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arrowPath.setAttribute('d', 'M0,0 L8,4 L0,8 z');
        arrowPath.setAttribute('fill', '#5e88a6');
        marker.appendChild(arrowPath);
        defs.appendChild(marker);
        svg.appendChild(defs);

        const nodeW = 170;
        const nodeH = 78;
        ids.forEach((fromId) => {
            const from = nodeLayout[fromId];
            const fromLoop = draft.loops[fromId] || {};
            const transitions = Array.isArray(fromLoop.transitions) ? fromLoop.transitions : [];
            transitions.forEach((tr) => {
                const toId = String(tr.to_loop_id || '').trim();
                if (!toId || !nodeLayout[toId]) return;
                const to = nodeLayout[toId];
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', String(from.x + nodeW));
                line.setAttribute('y1', String(from.y + (nodeH / 2)));
                line.setAttribute('x2', String(to.x));
                line.setAttribute('y2', String(to.y + (nodeH / 2)));
                line.setAttribute('stroke', '#5e88a6');
                line.setAttribute('stroke-width', '1.8');
                line.setAttribute('marker-end', 'url(#behavior-flow-arrow)');
                svg.appendChild(line);
            });
        });
        board.appendChild(svg);

        ids.forEach((id) => {
            const loop = draft.loops[id] || { repeat: true, steps: [], transitions: [] };
            const pos = nodeLayout[id];
            const node = document.createElement('div');
            node.style.position = 'absolute';
            node.style.left = `${pos.x}px`;
            node.style.top = `${pos.y}px`;
            node.style.width = `${nodeW}px`;
            node.style.minHeight = `${nodeH}px`;
            node.style.borderRadius = '8px';
            node.style.border = (id === selectedLoopId) ? '2px solid #2f7fbf' : '1px solid #c6dbeb';
            node.style.background = (id === selectedLoopId) ? '#f1f8ff' : '#ffffff';
            node.style.padding = '6px';
            node.style.cursor = 'move';
            node.style.boxShadow = '0 2px 6px rgba(0,0,0,0.08)';
            node.dataset.loopId = id;

            const actionsCount = (Array.isArray(loop.steps) ? loop.steps.length : 0);
            const trCount = (Array.isArray(loop.transitions) ? loop.transitions.length : 0);
            const initialTag = (id === draft.initial_loop_id) ? '初期' : '';
            const connectTag = (connectFromLoopId === id) ? '接続元' : '';
            node.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <strong style="font-size:0.84em; color:#214a67;">${id}</strong>
                    <button data-connect-from="${id}" style="padding:1px 5px; border:none; background:#2f7fbf; color:#fff; border-radius:4px; cursor:pointer; font-size:0.75em;">→</button>
                </div>
                <div style="font-size:0.75em; color:#55748c; margin-bottom:3px;">手順:${actionsCount} / 遷移:${trCount}</div>
                <div style="font-size:0.73em; color:#6b879b;">${loop.repeat ? 'ループ' : '停止'} ${initialTag ? `/ ${initialTag}` : ''} ${connectTag ? `/ ${connectTag}` : ''}</div>
            `;

            let dragStartX = 0;
            let dragStartY = 0;
            let startNodeX = 0;
            let startNodeY = 0;
            const onMouseMove = (ev) => {
                const dx = ev.clientX - dragStartX;
                const dy = ev.clientY - dragStartY;
                const nx = Math.max(5, Math.min(boardW - nodeW - 5, startNodeX + dx));
                const ny = Math.max(5, Math.min(boardH - nodeH - 5, startNodeY + dy));
                nodeLayout[id].x = nx;
                nodeLayout[id].y = ny;
                renderPreview();
            };
            const onMouseUp = () => {
                window.removeEventListener('mousemove', onMouseMove);
                window.removeEventListener('mouseup', onMouseUp);
            };
            node.addEventListener('mousedown', (ev) => {
                if (ev.target && ev.target.closest('[data-connect-from]')) return;
                dragStartX = ev.clientX;
                dragStartY = ev.clientY;
                startNodeX = nodeLayout[id].x;
                startNodeY = nodeLayout[id].y;
                window.addEventListener('mousemove', onMouseMove);
                window.addEventListener('mouseup', onMouseUp);
            });

            node.addEventListener('click', (ev) => {
                if (ev.target && ev.target.closest('[data-connect-from]')) return;
                if (connectFromLoopId && connectFromLoopId !== id) {
                    const srcLoop = draft.loops[connectFromLoopId];
                    if (srcLoop && Array.isArray(srcLoop.transitions)) {
                        srcLoop.transitions.push({
                            priority: 10,
                            to_loop_id: id,
                            reset_step_index: true,
                            when_all: []
                        });
                        markDirty();
                    }
                    connectFromLoopId = null;
                    selectedLoopId = id;
                    renderAll();
                    return;
                }
                if (connectFromLoopId === id) {
                    connectFromLoopId = null;
                    renderPreview();
                    if (connectHintEl) connectHintEl.textContent = 'ノードをドラッグで移動。接続開始後に接続先ノードをクリック。';
                    return;
                }
                selectedLoopId = id;
                renderAll();
            });

            node.querySelector('[data-connect-from]')?.addEventListener('click', (ev) => {
                ev.stopPropagation();
                connectFromLoopId = id;
                if (connectHintEl) connectHintEl.textContent = `接続元: ${id}。接続先ノードをクリックしてください。`;
                renderPreview();
            });

            board.appendChild(node);
        });

        previewEl.appendChild(board);
    }

    function renderLoopEditor() {
        const loop = draft.loops[selectedLoopId];
        if (!loop) {
            editorEl.innerHTML = '<div style="color:#789;">編集対象ループがありません。</div>';
            return;
        }
        const steps = Array.isArray(loop.steps) ? loop.steps : [];
        const transitions = Array.isArray(loop.transitions) ? loop.transitions : [];
        const toLoopOptions = loopIds().map((id) => `<option value="${id}">${id}</option>`).join('');

        editorEl.innerHTML = `
            <div style="display:grid; grid-template-columns: 1fr auto auto; gap:6px; align-items:end; margin-bottom:8px;">
                <label style="font-size:0.85em; color:#2f566f;">ループID
                    <input id="behavior-loop-id" value="${selectedLoopId}" style="width:100%; padding:5px; margin-top:2px;">
                </label>
                <label style="display:flex; align-items:center; gap:5px; font-size:0.84em; border:1px solid #d5e6f4; border-radius:6px; padding:6px 8px;">
                    <input type="checkbox" id="behavior-loop-repeat" ${loop.repeat ? 'checked' : ''}> ループする
                </label>
                <button id="behavior-loop-delete-btn" style="padding:6px 8px; border:none; background:#c23b3b; color:#fff; border-radius:6px; cursor:pointer;">削除</button>
            </div>
            <div style="border:1px solid #dbeaf6; border-radius:7px; padding:8px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                    <div style="font-weight:bold; color:#2f566f; font-size:0.88em;">手順</div>
                    <button id="behavior-step-add-btn" style="padding:4px 8px; border:none; background:#2f7fbf; color:#fff; border-radius:5px; cursor:pointer;">追加</button>
                </div>
                <div style="font-size:0.77em; color:#5b7890; margin-bottom:5px;">※所持スキルと対象選択（相手陣営/同陣営）を行ごとに設定します。</div>
                <div id="behavior-step-list"></div>
            </div>
            <div style="border:1px solid #dbeaf6; border-radius:7px; padding:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                    <div style="font-weight:bold; color:#2f566f; font-size:0.88em;">条件遷移</div>
                    <button id="behavior-tr-add-btn" style="padding:4px 8px; border:none; background:#2f7fbf; color:#fff; border-radius:5px; cursor:pointer;">追加</button>
                </div>
                <div style="font-size:0.77em; color:#5b7890; margin-bottom:5px;">各条件は「判定元・項目・比較・値」を行単位で追加します。</div>
                <div id="behavior-tr-list"></div>
            </div>
        `;

        const stepListEl = editorEl.querySelector('#behavior-step-list');
        if (!steps.length) {
            stepListEl.innerHTML = '<div style="font-size:0.84em; color:#7b94a6;">stepなし</div>';
        } else {
            steps.forEach((step, idx) => {
                const row = document.createElement('div');
                row.style.display = 'grid';
                row.style.gridTemplateColumns = '42px 1fr auto';
                row.style.gap = '6px';
                row.style.marginBottom = '6px';
                row.innerHTML = `<div style="font-size:0.82em; color:#3f637b; align-self:start; padding-top:4px;">S${idx + 1}</div>`;

                const actionsWrap = document.createElement('div');
                actionsWrap.style.display = 'grid';
                actionsWrap.style.gap = '4px';
                const actionItems = (Array.isArray(step.actions) && step.actions.length) ? step.actions : [null];
                const knownLoopIds = loopIds();
                const stepNextLoopRaw = String((step && step.next_loop_id) || '').trim();
                const stepNextEnabled = !!stepNextLoopRaw;
                const stepNextDefault = knownLoopIds.find((id) => id !== selectedLoopId) || selectedLoopId || '';
                const stepNextLoopId = stepNextLoopRaw || stepNextDefault;
                actionItems.forEach((actionSkillId, actionIdx) => {
                    const actionTargetPolicy = coerceBehaviorStepTargetPolicy(
                        (Array.isArray(step.targets) ? step.targets[actionIdx] : null)
                    );
                    const actionRow = document.createElement('div');
                    actionRow.style.display = 'grid';
                    actionRow.style.gridTemplateColumns = '1fr 160px auto';
                    actionRow.style.gap = '4px';

                    const select = document.createElement('select');
                    select.dataset.stepAction = `${idx}:${actionIdx}`;
                    select.style.width = '100%';
                    select.style.padding = '4px';
                    const options = buildOwnedSkillOptions(actionSkillId);
                    options.forEach((optData) => {
                        const opt = document.createElement('option');
                        opt.value = optData.id;
                        opt.textContent = optData.id ? `${optData.id} / ${optData.name}` : optData.name;
                        if (String(actionSkillId || '') === optData.id) opt.selected = true;
                        select.appendChild(opt);
                    });

                    const targetSelect = document.createElement('select');
                    targetSelect.dataset.stepTarget = `${idx}:${actionIdx}`;
                    targetSelect.style.width = '100%';
                    targetSelect.style.padding = '4px';
                    BEHAVIOR_STEP_TARGET_POLICIES.forEach((row) => {
                        const opt = document.createElement('option');
                        opt.value = row.value;
                        opt.textContent = row.label;
                        if (row.value === actionTargetPolicy) opt.selected = true;
                        targetSelect.appendChild(opt);
                    });

                    const delActionBtn = document.createElement('button');
                    delActionBtn.type = 'button';
                    delActionBtn.dataset.stepActionDel = `${idx}:${actionIdx}`;
                    delActionBtn.textContent = 'x';
                    delActionBtn.style.padding = '3px 6px';
                    delActionBtn.style.border = 'none';
                    delActionBtn.style.background = '#c23b3b';
                    delActionBtn.style.color = '#fff';
                    delActionBtn.style.borderRadius = '4px';
                    delActionBtn.style.cursor = 'pointer';
                    delActionBtn.title = 'このスキル指定を削除';

                    actionRow.appendChild(select);
                    actionRow.appendChild(targetSelect);
                    actionRow.appendChild(delActionBtn);
                    actionsWrap.appendChild(actionRow);
                });
                if (!ownedSkills.length) {
                    const msg = document.createElement('div');
                    msg.style.fontSize = '0.76em';
                    msg.style.color = '#a35c33';
                    msg.textContent = '所持スキルを取得できません。char.commands を確認してください。';
                    actionsWrap.appendChild(msg);
                }

                const actionAddBtn = document.createElement('button');
                actionAddBtn.type = 'button';
                actionAddBtn.dataset.stepActionAdd = `${idx}`;
                actionAddBtn.textContent = 'スキル指定追加';
                actionAddBtn.style.padding = '3px 8px';
                actionAddBtn.style.border = 'none';
                actionAddBtn.style.background = '#5f9ec9';
                actionAddBtn.style.color = '#fff';
                actionAddBtn.style.borderRadius = '4px';
                actionAddBtn.style.cursor = 'pointer';
                actionAddBtn.style.width = 'fit-content';
                actionsWrap.appendChild(actionAddBtn);

                const nextWrap = document.createElement('div');
                nextWrap.style.display = 'flex';
                nextWrap.style.alignItems = 'center';
                nextWrap.style.gap = '6px';
                nextWrap.style.marginTop = '4px';
                nextWrap.style.fontSize = '0.8em';

                const nextCheckLabel = document.createElement('label');
                nextCheckLabel.style.display = 'flex';
                nextCheckLabel.style.alignItems = 'center';
                nextCheckLabel.style.gap = '5px';
                nextCheckLabel.style.color = '#2f566f';

                const nextCheck = document.createElement('input');
                nextCheck.type = 'checkbox';
                nextCheck.dataset.stepNextEnabled = String(idx);
                nextCheck.checked = stepNextEnabled;
                nextCheckLabel.appendChild(nextCheck);
                nextCheckLabel.appendChild(document.createTextNode('スキル使用後にループ遷移'));

                const nextSelect = document.createElement('select');
                nextSelect.dataset.stepNextLoop = String(idx);
                nextSelect.style.padding = '3px 5px';
                nextSelect.style.display = stepNextEnabled ? '' : 'none';
                const loopOptions = knownLoopIds.slice();
                if (stepNextLoopId && !loopOptions.includes(stepNextLoopId)) {
                    loopOptions.push(stepNextLoopId);
                }
                loopOptions.forEach((loopId) => {
                    const opt = document.createElement('option');
                    opt.value = loopId;
                    opt.textContent = loopId;
                    if (loopId === stepNextLoopId) opt.selected = true;
                    nextSelect.appendChild(opt);
                });

                nextWrap.appendChild(nextCheckLabel);
                nextWrap.appendChild(nextSelect);
                actionsWrap.appendChild(nextWrap);

                row.appendChild(actionsWrap);

                const delStepBtn = document.createElement('button');
                delStepBtn.type = 'button';
                delStepBtn.dataset.stepDel = String(idx);
                delStepBtn.textContent = '削除';
                delStepBtn.style.padding = '4px 8px';
                delStepBtn.style.border = 'none';
                delStepBtn.style.background = '#c23b3b';
                delStepBtn.style.color = '#fff';
                delStepBtn.style.borderRadius = '5px';
                delStepBtn.style.cursor = 'pointer';
                row.appendChild(delStepBtn);
                stepListEl.appendChild(row);
            });
        }

        const ensureStepTargetList = (stepObj) => {
            if (!stepObj || typeof stepObj !== 'object') return [];
            const actions = (Array.isArray(stepObj.actions) && stepObj.actions.length) ? stepObj.actions : [null];
            const targets = Array.isArray(stepObj.targets) ? stepObj.targets.slice(0, actions.length) : [];
            while (targets.length < actions.length) {
                targets.push(BEHAVIOR_STEP_TARGET_POLICY_DEFAULT);
            }
            stepObj.targets = targets.map((row) => coerceBehaviorStepTargetPolicy(row));
            stepObj.actions = actions;
            return stepObj.targets;
        };

        const trListEl = editorEl.querySelector('#behavior-tr-list');
        if (!transitions.length) {
            trListEl.innerHTML = '<div style="font-size:0.84em; color:#7b94a6;">遷移なし</div>';
        } else {
            const buildSourceOptions = (selectedValue) => BEHAVIOR_CONDITION_SOURCES.map((row) => {
                const selected = (row.value === selectedValue) ? 'selected' : '';
                return `<option value="${row.value}" ${selected}>${row.label}</option>`;
            }).join('');
            const buildOperatorOptions = (selectedValue) => BEHAVIOR_CONDITION_OPERATORS.map((row) => {
                const selected = (row.value === selectedValue) ? 'selected' : '';
                return `<option value="${row.value}" ${selected}>${row.label}</option>`;
            }).join('');
            const buildParamOptions = (source, selectedParam) => {
                const presets = getBehaviorConditionParamPresets(source);
                const selected = String(selectedParam || '').trim();
                const hasSelectedInPreset = presets.some((row) => row.value === selected);
                let html = presets.map((row) => {
                    const selectedTag = (row.value === selected) ? 'selected' : '';
                    return `<option value="${row.value}" ${selectedTag}>${row.label}</option>`;
                }).join('');
                html += `<option value="__custom__" ${hasSelectedInPreset ? '' : 'selected'}>自由入力</option>`;
                return html;
            };
            transitions.forEach((tr, tIdx) => {
                const whenAll = Array.isArray(tr.when_all) ? tr.when_all.map(normalizeBehaviorConditionRow) : [];
                const condRows = whenAll.length
                    ? whenAll.map((cond, cIdx) => {
                        const param = String(cond.param || '').trim();
                        const presets = getBehaviorConditionParamPresets(cond.source);
                        const hasPreset = presets.some((row) => row.value === param);
                        return `
                            <div style="display:grid; grid-template-columns: 120px 150px 170px 140px 1fr auto; gap:6px; align-items:end; margin-bottom:6px; padding:6px; border:1px solid #e2edf7; border-radius:6px; background:#fafdff;">
                                <label style="font-size:0.8em;">判定元
                                    <select data-tr-cond-source="${tIdx}:${cIdx}" style="width:100%;">
                                        ${buildSourceOptions(cond.source)}
                                    </select>
                                </label>
                                <label style="font-size:0.8em;">項目
                                    <select data-tr-cond-param-select="${tIdx}:${cIdx}" style="width:100%;">
                                        ${buildParamOptions(cond.source, cond.param)}
                                    </select>
                                </label>
                                <label style="font-size:0.8em; ${hasPreset ? 'display:none;' : ''}">項目名
                                    <input data-tr-cond-param-custom="${tIdx}:${cIdx}" value="${hasPreset ? '' : param}" placeholder="例: 破裂" style="width:100%;">
                                </label>
                                <label style="font-size:0.8em;">比較
                                    <select data-tr-cond-op="${tIdx}:${cIdx}" style="width:100%;">
                                        ${buildOperatorOptions(cond.operator)}
                                    </select>
                                </label>
                                <label style="font-size:0.8em;">値
                                    <input data-tr-cond-value="${tIdx}:${cIdx}" value="${String(cond.value ?? '')}" placeholder="例: 50" style="width:100%;">
                                </label>
                                <button data-tr-cond-del="${tIdx}:${cIdx}" style="padding:4px 7px; border:none; background:#c23b3b; color:#fff; border-radius:5px; cursor:pointer;">削除</button>
                            </div>
                        `;
                    }).join('')
                    : '<div style="font-size:0.8em; color:#7b94a6; margin-bottom:6px;">条件がありません（常に遷移）。</div>';
                const box = document.createElement('div');
                box.style.border = '1px solid #d5e6f4';
                box.style.borderRadius = '6px';
                box.style.padding = '6px';
                box.style.marginBottom = '6px';
                box.innerHTML = `
                    <div style="display:grid; grid-template-columns: 78px 1fr auto auto; gap:6px; align-items:end; margin-bottom:5px;">
                        <label style="font-size:0.8em;">優先度<input data-tr-priority="${tIdx}" type="number" value="${Number(tr.priority || 0)}" style="width:100%;"></label>
                        <label style="font-size:0.8em;">遷移先ループ<select data-tr-to="${tIdx}" style="width:100%;">${toLoopOptions}</select></label>
                        <label style="display:flex; align-items:center; gap:4px; font-size:0.8em;"><input data-tr-reset="${tIdx}" type="checkbox" ${tr.reset_step_index !== false ? 'checked' : ''}>先頭手順へ戻す</label>
                        <button data-tr-del="${tIdx}" style="padding:4px 7px; border:none; background:#c23b3b; color:#fff; border-radius:5px; cursor:pointer;">削除</button>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                        <div style="font-size:0.8em; color:#385c73; font-weight:bold;">判定条件（すべて成立で遷移）</div>
                        <button data-tr-cond-add="${tIdx}" style="padding:3px 8px; border:none; background:#5f9ec9; color:#fff; border-radius:4px; cursor:pointer;">条件追加</button>
                    </div>
                    <div>${condRows}</div>
                `;
                const select = box.querySelector(`[data-tr-to="${tIdx}"]`);
                if (select) select.value = String(tr.to_loop_id || '');
                trListEl.appendChild(box);
            });
        }

        editorEl.querySelector('#behavior-loop-id')?.addEventListener('change', (e) => {
            const newId = String(e.target.value || '').trim();
            if (!newId || newId === selectedLoopId) {
                e.target.value = selectedLoopId;
                return;
            }
            if (draft.loops[newId]) {
                alert('同名のループIDが既に存在します。');
                e.target.value = selectedLoopId;
                return;
            }
            const oldId = selectedLoopId;
            draft.loops[newId] = draft.loops[oldId];
            delete draft.loops[oldId];
            if (nodeLayout[oldId]) {
                nodeLayout[newId] = nodeLayout[oldId];
                delete nodeLayout[oldId];
            }
            Object.values(draft.loops).forEach((lp) => {
                if (!lp) return;
                if (Array.isArray(lp.transitions)) {
                    lp.transitions.forEach((tr) => {
                        if (tr.to_loop_id === oldId) tr.to_loop_id = newId;
                    });
                }
                if (Array.isArray(lp.steps)) {
                    lp.steps.forEach((step) => {
                        if (!step || typeof step !== 'object') return;
                        if (String(step.next_loop_id || '').trim() === oldId) {
                            step.next_loop_id = newId;
                        }
                    });
                }
            });
            if (draft.initial_loop_id === oldId) draft.initial_loop_id = newId;
            if (connectFromLoopId === oldId) connectFromLoopId = newId;
            selectedLoopId = newId;
            markDirty();
            renderAll();
        });
        editorEl.querySelector('#behavior-loop-repeat')?.addEventListener('change', (e) => {
            loop.repeat = !!e.target.checked;
            markDirty();
            renderPreview();
        });
        editorEl.querySelector('#behavior-loop-delete-btn')?.addEventListener('click', () => {
            if (loopIds().length <= 1) {
                alert('最低1つのループは必要です。');
                return;
            }
            if (!confirm(`ループ「${selectedLoopId}」を削除しますか？`)) return;
            const removed = selectedLoopId;
            delete draft.loops[removed];
            delete nodeLayout[removed];
            if (connectFromLoopId === removed) connectFromLoopId = null;
            Object.values(draft.loops).forEach((lp) => {
                if (!lp) return;
                if (Array.isArray(lp.transitions)) {
                    lp.transitions = lp.transitions.filter((tr) => tr.to_loop_id !== removed);
                }
                if (Array.isArray(lp.steps)) {
                    lp.steps.forEach((step) => {
                        if (!step || typeof step !== 'object') return;
                        if (String(step.next_loop_id || '').trim() === removed) {
                            step.next_loop_id = null;
                            step.next_reset_step_index = true;
                        }
                    });
                }
            });
            ensureSelection();
            markDirty();
            renderAll();
        });

        editorEl.querySelector('#behavior-step-add-btn')?.addEventListener('click', () => {
            loop.steps.push({
                actions: [null],
                targets: [BEHAVIOR_STEP_TARGET_POLICY_DEFAULT],
                next_loop_id: null,
                next_reset_step_index: true
            });
            markDirty();
            renderAll();
        });
        editorEl.querySelectorAll('[data-step-action]').forEach((select) => {
            select.addEventListener('change', (e) => {
                const [stepIdxRaw, actionIdxRaw] = String(e.target.dataset.stepAction || '').split(':');
                const stepIdx = parseInt(stepIdxRaw, 10);
                const actionIdx = parseInt(actionIdxRaw, 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep) return;
                const actions = Array.isArray(targetStep.actions) ? targetStep.actions : [null];
                actions[actionIdx] = coerceBehaviorStepSkillId(e.target.value);
                targetStep.actions = actions;
                ensureStepTargetList(targetStep);
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-step-target]').forEach((select) => {
            select.addEventListener('change', (e) => {
                const [stepIdxRaw, actionIdxRaw] = String(e.target.dataset.stepTarget || '').split(':');
                const stepIdx = parseInt(stepIdxRaw, 10);
                const actionIdx = parseInt(actionIdxRaw, 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep) return;
                const targets = ensureStepTargetList(targetStep);
                targets[actionIdx] = coerceBehaviorStepTargetPolicy(e.target.value);
                targetStep.targets = targets;
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-step-next-enabled]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const stepIdx = parseInt(String(e.target.dataset.stepNextEnabled || ''), 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep || typeof targetStep !== 'object') return;
                const enabled = !!e.target.checked;
                if (!enabled) {
                    targetStep.next_loop_id = null;
                    targetStep.next_reset_step_index = true;
                } else {
                    const candidates = loopIds();
                    const fallback = candidates.find((id) => id !== selectedLoopId) || selectedLoopId || '';
                    targetStep.next_loop_id = String(targetStep.next_loop_id || '').trim() || fallback || null;
                    targetStep.next_reset_step_index = true;
                }
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-step-next-loop]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const stepIdx = parseInt(String(e.target.dataset.stepNextLoop || ''), 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep || typeof targetStep !== 'object') return;
                const nextLoopId = String(e.target.value || '').trim();
                targetStep.next_loop_id = nextLoopId || null;
                targetStep.next_reset_step_index = true;
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-step-action-add]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const stepIdx = parseInt(e.currentTarget.dataset.stepActionAdd, 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep) return;
                const actions = Array.isArray(targetStep.actions) ? targetStep.actions : [null];
                actions.push(null);
                targetStep.actions = actions;
                const targets = ensureStepTargetList(targetStep);
                targetStep.targets = targets.slice(0, actions.length);
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-step-action-del]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const [stepIdxRaw, actionIdxRaw] = String(e.currentTarget.dataset.stepActionDel || '').split(':');
                const stepIdx = parseInt(stepIdxRaw, 10);
                const actionIdx = parseInt(actionIdxRaw, 10);
                const targetStep = loop.steps[stepIdx];
                if (!targetStep) return;
                const actions = Array.isArray(targetStep.actions) ? targetStep.actions : [null];
                actions.splice(actionIdx, 1);
                targetStep.actions = actions.length ? actions : [null];
                const targets = ensureStepTargetList(targetStep);
                targets.splice(actionIdx, 1);
                targetStep.targets = (actions.length ? targets.slice(0, actions.length) : [BEHAVIOR_STEP_TARGET_POLICY_DEFAULT]);
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-step-del]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.dataset.stepDel, 10);
                loop.steps.splice(idx, 1);
                markDirty();
                renderAll();
            });
        });

        editorEl.querySelector('#behavior-tr-add-btn')?.addEventListener('click', () => {
            const toLoop = loopIds().find((id) => id !== selectedLoopId) || selectedLoopId;
            loop.transitions.push({
                priority: 10,
                to_loop_id: toLoop,
                reset_step_index: true,
                when_all: []
            });
            markDirty();
            renderAll();
        });
        editorEl.querySelectorAll('[data-tr-priority]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.trPriority, 10);
                loop.transitions[idx].priority = Number.isFinite(Number(e.target.value)) ? parseInt(e.target.value, 10) : 0;
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-to]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.trTo, 10);
                loop.transitions[idx].to_loop_id = String(e.target.value || '').trim();
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-reset]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.trReset, 10);
                loop.transitions[idx].reset_step_index = !!e.target.checked;
                markDirty();
                renderPreview();
            });
        });
        const readConditionRef = (token) => {
            const [trIdxRaw, condIdxRaw] = String(token || '').split(':');
            const trIdx = parseInt(trIdxRaw, 10);
            const condIdx = parseInt(condIdxRaw, 10);
            if (!Number.isFinite(trIdx) || !Number.isFinite(condIdx)) return null;
            const trObj = loop.transitions[trIdx];
            if (!trObj || typeof trObj !== 'object') return null;
            if (!Array.isArray(trObj.when_all)) trObj.when_all = [];
            const rawCond = trObj.when_all[condIdx];
            const cond = normalizeBehaviorConditionRow(rawCond);
            trObj.when_all[condIdx] = cond;
            return { trObj, cond, trIdx, condIdx };
        };
        editorEl.querySelectorAll('[data-tr-cond-add]').forEach((el) => {
            el.addEventListener('click', (e) => {
                const trIdx = parseInt(e.currentTarget.dataset.trCondAdd, 10);
                const trObj = loop.transitions[trIdx];
                if (!trObj || typeof trObj !== 'object') return;
                if (!Array.isArray(trObj.when_all)) trObj.when_all = [];
                const presets = getBehaviorConditionParamPresets('self');
                trObj.when_all.push({
                    source: 'self',
                    param: presets[0] ? presets[0].value : 'HP',
                    operator: 'LTE',
                    value: 50
                });
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-source]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondSource);
                if (!ref) return;
                ref.cond.source = (String(e.target.value || '').trim() === 'battle') ? 'battle' : 'self';
                const presets = getBehaviorConditionParamPresets(ref.cond.source);
                const hasCurrent = presets.some((row) => row.value === ref.cond.param);
                if (!hasCurrent && presets[0]) ref.cond.param = presets[0].value;
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-param-select]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondParamSelect);
                if (!ref) return;
                const selected = String(e.target.value || '').trim();
                if (selected !== '__custom__') {
                    ref.cond.param = selected;
                } else if (!String(ref.cond.param || '').trim()) {
                    ref.cond.param = '';
                }
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-param-custom]').forEach((el) => {
            el.addEventListener('input', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondParamCustom);
                if (!ref) return;
                ref.cond.param = String(e.target.value || '').trim();
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-op]').forEach((el) => {
            el.addEventListener('change', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondOp);
                if (!ref) return;
                ref.cond.operator = String(e.target.value || '').trim().toUpperCase() || 'EQUALS';
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-value]').forEach((el) => {
            el.addEventListener('input', (e) => {
                const ref = readConditionRef(e.target.dataset.trCondValue);
                if (!ref) return;
                ref.cond.value = coerceBehaviorConditionValue(e.target.value);
                markDirty();
                renderPreview();
            });
        });
        editorEl.querySelectorAll('[data-tr-cond-del]').forEach((el) => {
            el.addEventListener('click', (e) => {
                const ref = readConditionRef(e.currentTarget.dataset.trCondDel);
                if (!ref) return;
                ref.trObj.when_all.splice(ref.condIdx, 1);
                markDirty();
                renderAll();
            });
        });
        editorEl.querySelectorAll('[data-tr-del]').forEach((el) => {
            el.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.dataset.trDel, 10);
                loop.transitions.splice(idx, 1);
                markDirty();
                renderAll();
            });
        });
    }

    function renderAll() {
        ensureSelection();
        ensureNodeLayout();
        enabledEl.checked = !!draft.enabled;
        renderInitialLoopOptions();
        renderLoopTabs();
        renderPreview();
        renderLoopEditor();
        if (connectHintEl) {
            connectHintEl.textContent = connectFromLoopId
                ? `接続元: ${connectFromLoopId}。接続先ノードをクリックしてください。`
                : 'ノードをドラッグで移動。接続開始後に接続先ノードをクリック。';
        }
    }

    enabledEl.addEventListener('change', (e) => {
        draft.enabled = !!e.target.checked;
        markDirty();
        renderPreview();
    });
    initialEl.addEventListener('change', (e) => {
        draft.initial_loop_id = String(e.target.value || '').trim() || draft.initial_loop_id;
        markDirty();
        renderPreview();
    });
    addLoopBtn.addEventListener('click', () => {
        const loopId = uniqueLoopId(newLoopInput.value || 'loop');
        draft.loops[loopId] = {
            repeat: true,
            steps: [{
                actions: [null],
                targets: [BEHAVIOR_STEP_TARGET_POLICY_DEFAULT],
                next_loop_id: null,
                next_reset_step_index: true
            }],
            transitions: []
        };
        if (!nodeLayout[loopId]) nodeLayout[loopId] = { x: 30, y: 30 };
        selectedLoopId = loopId;
        if (!draft.initial_loop_id) draft.initial_loop_id = loopId;
        newLoopInput.value = '';
        markDirty();
        renderAll();
    });
    resetProfileBtn?.addEventListener('click', () => {
        const ok = confirm('このキャラの行動チャートを初期化します。よろしいですか？');
        if (!ok) return;
        draft.enabled = false;
        draft.initial_loop_id = 'loop_1';
        draft.loops = {
            loop_1: {
                repeat: true,
                steps: [{
                    actions: [null],
                    targets: [BEHAVIOR_STEP_TARGET_POLICY_DEFAULT],
                    next_loop_id: null,
                    next_reset_step_index: true
                }],
                transitions: []
            }
        };
        selectedLoopId = 'loop_1';
        connectFromLoopId = null;
        Object.keys(nodeLayout).forEach((id) => { delete nodeLayout[id]; });
        nodeLayout.loop_1 = { x: 30, y: 30 };
        markDirty();
        renderAll();
    });
    newLoopInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addLoopBtn.click();
        }
    });

    connectStartBtn?.addEventListener('click', () => {
        ensureSelection();
        connectFromLoopId = selectedLoopId || loopIds()[0] || null;
        renderAll();
    });
    connectCancelBtn?.addEventListener('click', () => {
        connectFromLoopId = null;
        renderAll();
    });

    content.querySelector('#behavior-save-btn')?.addEventListener('click', () => {
        const normalized = normalizeBehaviorProfileForEditor(draft);
        if (onSave) {
            try {
                const handled = onSave(normalized, { char: workingChar, ownedSkills });
                if (handled === false) return;
            } catch (e) {
                const msg = (e && e.message) ? String(e.message) : '保存に失敗しました。';
                alert(msg);
                return;
            }
            clearDirty();
            closeModal(true);
            return;
        }
        const latestOnSave = getLatestCharacterForBehaviorEditor(charId) || workingChar || {};
        const latestFlags = (latestOnSave.flags && typeof latestOnSave.flags === 'object') ? latestOnSave.flags : {};
        const nextFlags = Object.assign({}, latestFlags, { behavior_profile: normalized });
        socket.emit('request_state_update', {
            room: currentRoomName,
            charId,
            statName: 'flags',
            newValue: nextFlags
        });
        if (workingChar && typeof workingChar === 'object') workingChar.flags = nextFlags;
        const latestRef = getLatestCharacterForBehaviorEditor(charId);
        if (latestRef && typeof latestRef === 'object') latestRef.flags = nextFlags;
        clearDirty();
        closeModal(true);
    });

    renderAll();
}

/**
 * 設定コンテキストメニューを作成・表示
 */
global.openBehaviorFlowEditorModal = openBehaviorFlowEditorModal;
})(window);
