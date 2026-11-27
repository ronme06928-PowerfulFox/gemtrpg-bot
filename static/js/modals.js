// --- モーダル関連の関数 ---

/**
 * ユーザー設定モーダルを開く
 */
const _MODAL_STATE_NAME_ALIASES = {
    '\u8703\uff7a\u9666\u0080': '出血',
    '\u9050\uff74\u966c\u30fb': '亀裂',
    '\u83a0\u0080\u966c\u30fb': '破裂',
    '\u8b0c\uff66\u8af7\u30fb': '戦慄',
    '\u95d5\u9811\uff63\u30fb': '荊棘',
};

function normalizeModalStateName(name) {
    const key = String(name || '').trim();
    return _MODAL_STATE_NAME_ALIASES[key] || key;
}

function escapeUserSettingsText(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[ch]));
}

function openUserSettingsModal(allowAttributeChange = false) {
    const oldName = currentUsername;
    const oldAttr = currentUserAttribute;
    let attributeHtml = `
        <label>あなたの属性:</label>
        <input type="text" value="${escapeUserSettingsText(oldAttr)}" readonly disabled
               title="GM/プレイヤーの切り替えはルーム入室時に行ってください">
    `;
    const modalHtml = `
        <div class="modal-backdrop" id="user-settings-modal-backdrop" data-theme="paper">
            <div class="modal-content paper-dialog user-settings-modal">
                <button class="modal-close-btn" type="button" aria-label="閉じる">×</button>
                <div class="user-settings-panel-header">
                    <h2 class="user-settings-panel-title">ユーザー情報変更</h2>
                </div>
                <div class="auth-form user-settings-panel-body">
                    <label for="modal-username">あなたの名前:</label>
                    <input type="text" id="modal-username" value="${escapeUserSettingsText(oldName)}">
                    ${attributeHtml}
                    <button id="modal-user-update-btn">表示名を更新</button>
                    <button id="modal-password-change-btn" type="button">パスワード変更</button>
                    <button id="modal-recovery-regenerate-btn" type="button">復旧コード再発行</button>
                    <div class="user-settings-admin-card ${currentUserIsAppAdmin ? 'is-admin' : ''}">
                        <h3>ユーザー管理権限</h3>
                        <p>${currentUserIsAppAdmin
                            ? 'このユーザーには現在、ユーザー管理権限があります。'
                            : '管理キーを入力すると、このユーザーにユーザー管理権限を付与できます。APIを直接操作する必要はありません。'}</p>
                        <button id="modal-admin-grant-btn" type="button">${currentUserIsAppAdmin ? '管理権限を確認済み' : '管理キーで権限を付与'}</button>
                    </div>
                    <div id="modal-user-message" class="auth-message"></div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const backdrop = document.getElementById('user-settings-modal-backdrop');
    if (appSurfaceTheme() === 'marble') {
        delete backdrop.dataset.theme;
        const panel = backdrop.querySelector('.user-settings-modal');
        panel.classList.remove('paper-dialog');
        applySystemWindow(panel);
    }
    const updateBtn = document.getElementById('modal-user-update-btn');
    const recoveryBtn = document.getElementById('modal-recovery-regenerate-btn');
    const adminGrantBtn = document.getElementById('modal-admin-grant-btn');
    const msgEl = document.getElementById('modal-user-message');

    const closeModal = () => {
        backdrop.remove();
    };
    backdrop.querySelector('.modal-close-btn').addEventListener('click', closeModal);
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeModal();
    });

    updateBtn.addEventListener('click', async () => {
        const newName = document.getElementById('modal-username').value.trim();
        if (!newName) {
            msgEl.textContent = '名前は必須です。';
            msgEl.className = 'auth-message error';
            return;
        }
        try {
            // 表示名変更は専用APIへ（/api/entry は使わない）。
            const response = await fetchWithSession('/api/change_display_name', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name: newName })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error);
            if (typeof currentUsername !== 'undefined') { currentUsername = newName; window.currentUsername = newName; }
            if (typeof socket !== 'undefined' && socket) {
                socket.emit('request_update_user_info', { username: newName });
            }
            msgEl.textContent = '表示名を更新しました。';
            msgEl.className = 'auth-message success';
            setTimeout(closeModal, 1000);
        } catch (error) {
            msgEl.textContent = `更新失敗: ${error.message}`;
            msgEl.className = 'auth-message error';
        }
    });

    const passwordBtn = document.getElementById('modal-password-change-btn');
    passwordBtn?.addEventListener('click', async () => {
        const current = await window.showAppPrompt('現在のパスワードを入力してください。', {
            title: 'パスワード変更', confirmText: '次へ', required: true,
        });
        if (!current) return;
        const next = await window.showAppPrompt('新しいパスワード（10〜128文字）を入力してください。', {
            title: 'パスワード変更', confirmText: '変更する', required: true,
        });
        if (!next) return;
        try {
            const response = await fetchWithSession('/api/set_password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_password: current, password: next })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || '変更に失敗しました');
            msgEl.textContent = 'パスワードを変更しました。';
            msgEl.className = 'auth-message success';
        } catch (error) {
            msgEl.textContent = `変更失敗: ${error.message}`;
            msgEl.className = 'auth-message error';
        }
    });

    recoveryBtn?.addEventListener('click', async () => {
        const ok = await window.showAppConfirm('復旧コードを再発行します。古い復旧コードは使えなくなります。', {
            danger: true,
            title: '復旧コード再発行',
            confirmText: '再発行',
        });
        if (!ok) return;

        try {
            const response = await fetchWithSession('/api/regenerate_recovery_code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || '再発行に失敗しました');
            if (typeof saveRecoveryTokenFromResponse === 'function') {
                saveRecoveryTokenFromResponse(data);
            }
            await window.showAppConfirm(`新しい復旧コードを控えてください。\n\n${data.recovery_code}\n\nこのコードは再表示できません。`, {
                title: '復旧コード',
                confirmText: '控えました',
            });
            msgEl.textContent = '復旧コードを再発行しました。';
            msgEl.className = 'auth-message success';
        } catch (error) {
            msgEl.textContent = `再発行失敗: ${error.message}`;
            msgEl.className = 'auth-message error';
        }
    });

    adminGrantBtn?.addEventListener('click', async () => {
        if (currentUserIsAppAdmin) {
            msgEl.textContent = 'このユーザーには既にユーザー管理権限があります。';
            msgEl.className = 'auth-message success';
            return;
        }
        const masterKey = await window.showAppPrompt('管理キーを入力してください。入力したキーは保存されず、この確認にだけ使用されます。', {
            title: 'ユーザー管理権限の付与',
            placeholder: '8桁の管理キー',
            confirmText: '権限を付与',
            required: true,
        });
        if (!/^\d{8}$/.test(String(masterKey || '').trim())) {
            msgEl.textContent = '管理キーは8桁の数字で入力してください。';
            msgEl.className = 'auth-message error';
            return;
        }
        try {
            const response = await fetchWithSession('/api/admin/set_user_management_admin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: currentUserId,
                    enabled: true,
                    master_key: String(masterKey).trim(),
                })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || '管理権限の付与に失敗しました');
            currentUserIsAppAdmin = true;
            window.currentUserIsAppAdmin = true;
            adminGrantBtn.textContent = '管理権限を確認済み';
            adminGrantBtn.closest('.user-settings-admin-card')?.classList.add('is-admin');
            msgEl.textContent = 'ユーザー管理権限を付与しました。ルーム一覧では「ユーザー管理」ボタンが表示されます。';
            msgEl.className = 'auth-message success';
        } catch (error) {
            msgEl.textContent = `権限付与失敗: ${error.message}`;
            msgEl.className = 'auth-message error';
        }
    });
}

/**
 * 参加者一覧モーダル
 */
function openUserListModal() {
    const existingBackdrop = document.getElementById('user-list-modal-backdrop');
    if (existingBackdrop) {
        existingBackdrop.remove();
    }
    let listHtml = '';
    if (currentRoomUserList.length === 0) {
        listHtml = '<p>現在、他の参加者はいません。</p>';
    } else {
        currentRoomUserList.forEach(user => {
            const attrClass = user.attribute === 'GM' ? 'gm' : 'player';

            // オーナー判定ロジック
            let ownerBadge = '';
            if (battleState.owner_id && user.user_id && user.user_id === battleState.owner_id) {
                ownerBadge = ' <span style="color:#e67e22; font-weight:bold; font-size:0.9em;">(オーナー)</span>';
            }

            listHtml += `
                <li class="user-list-item">
                    <span class="user-list-name">${user.username}</span>
                    <span class="user-list-attribute ${attrClass}">${user.attribute}</span>
                    ${ownerBadge} </li>
            `;
        });
    }
    const modalHtml = `
        <div class="modal-backdrop" id="user-list-modal-backdrop">
            <div class="modal-content user-list-modal-content">
                <button class="modal-close-btn" style="float: right;">×</button>
                <h2>参加者一覧 (${currentRoomUserList.length}名)</h2>
                <ul class="user-list-container">
                    ${listHtml}
                </ul>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    applySystemWindow(document.querySelector('#user-list-modal-backdrop > .modal-content'));
    const backdrop = document.getElementById('user-list-modal-backdrop');
    backdrop.querySelector('.modal-close-btn').addEventListener('click', () => backdrop.remove());
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) backdrop.remove();
    });
}

/**
 * キャラクター詳細モーダルを閉じる
 */
function closeCharacterModal() {
    const modal = document.getElementById('char-modal-backdrop');
    if (modal) {
        window.HiddenPassiveFx?.stopObserving(modal.querySelector('.character-modal-passives'));
        modal.remove();
    }
}

// 表示専用の集計。状態値を正とし、期限別データが矛盾しても状態を書き換えない。
function buildFissureDetailView(char) {
  const states = Array.isArray(char.states) ? char.states : [];
  const state = states.find(s => normalizeModalStateName(s.name) === '亀裂');
  const stateValue = Number(state ? state.value : 0);
  const total = Number.isSafeInteger(stateValue) && stateValue >= 0 ? stateValue : 0;
  const buckets = (Array.isArray(char.special_buffs) ? char.special_buffs : [])
    .filter(b => b && b.buff_id === 'Bu-Fissure');
  const groups = new Map();
  let bucketTotal = 0;
  let inconsistent = total !== stateValue;
  for (const b of buckets) {
    const count = Number(b.count);
    const lasting = Number(b.lasting);
    const delay = Number(b.delay ?? 0);
    if (!Number.isSafeInteger(count) || count < 0
      || !Number.isSafeInteger(lasting) || lasting <= 0
      || !Number.isSafeInteger(delay) || delay < 0) {
      inconsistent = true;
      continue;
    }
    bucketTotal += count;
    if (count === 0) continue;
    const key = `${delay}:${lasting}`;
    const group = groups.get(key) || {delay, lasting, count: 0};
    group.count += count;
    groups.set(key, group);
  }
  inconsistent ||= bucketTotal > total || !Number.isSafeInteger(bucketTotal);
  const rows = [];
  if (!inconsistent) {
    const sorted = [...groups.values()].sort((a, b) => a.delay - b.delay || a.lasting - b.lasting);
    sorted.forEach(g => rows.push({
      label: g.delay > 0
        ? `発動まで${g.delay}ラウンド / 持続${g.lasting}ラウンド`
        : `${g.lasting}ラウンド`,
      count: g.count,
    }));
    if (total > bucketTotal) rows.push({label: '期限なし', count: total - bucketTotal});
  }
  return {total, visible: total > 0 || buckets.length > 0, inconsistent, rows};
}

function renderFissureDetail(view) {
  if (!view.visible) return '';
  const breakdown = view.inconsistent
    ? '<p class="fissure-detail-unavailable">残りラウンドの内訳を確認できません</p>'
    : `<table class="fissure-detail-table">
        <thead><tr><th scope="col">残りラウンド</th><th scope="col">重数</th></tr></thead>
        <tbody>${view.rows.map(row => `<tr><td>${row.label}</td><td>${row.count}重</td></tr>`).join('')}</tbody>
      </table>`;
  return `<details class="buff-accordion" data-fissure-detail>
    <summary class="buff-summary">
      <div class="buff-summary-body fissure-detail-summary">
        <span class="buff-name">亀裂</span><span class="fissure-detail-total">${view.total}重</span>
      </div>
      <span class="buff-arrow">▼</span>
    </summary>
    <div class="buff-body">
      <div class="buff-desc-row">スキルで受けるダメージに、亀裂の重数を加算する。各重は、それぞれの残りラウンドが尽きると消失する。期限なしの分は、ラウンド経過では消失しない。</div>
      ${breakdown}
    </div>
  </details>`;
}

/**
 * キャラクター詳細カードHTML生成 (統合版)
 *
 * 【復旧仕様】
 * 1. 歯車設定UI: 以前のリスト形式（垂直配置）＋スライダーUIを復元
 * 2. バフ表示: スキル定義等から継承された flavor/description を優先表示
 *    (Gouged Wound等が動的定義のデフォルトテキストに上書きされないようにする)
 */
function renderCharacterSkills(char) {
    let skillsHtml = '';
    const hiddenSkills = char.hidden_skills || [];
    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

    const grantedSkillRows = Array.isArray(char.granted_skills) ? char.granted_skills : [];
    const grantedBySkillId = {};
    grantedSkillRows.forEach((row) => {
        if (!row || typeof row !== 'object') return;
        const sid = String(row.skill_id || '').trim();
        if (!sid) return;
        grantedBySkillId[sid] = row;
    });

    if (char.commands) {
        const regex = /【(.*?)\s+(.*?)】/g;
        let match;
        let skillItems = [];
        const escAttr = (value) => String(value ?? '').replace(/"/g, '&quot;');

        while ((match = regex.exec(char.commands)) !== null) {
            const skillId = match[1];
            const skillName = match[2];
            const isHidden = hiddenSkills.includes(skillId);
            const granted = grantedBySkillId[skillId] || null;
            const isGranted = !!granted;
            const grantMode = isGranted ? String(granted.mode || '').trim() : '';
            const remainingRounds = isGranted && granted.remaining_rounds != null ? parseInt(granted.remaining_rounds, 10) : NaN;
            const remainingUses = isGranted && granted.remaining_uses != null ? parseInt(granted.remaining_uses, 10) : NaN;

            if (!isGM && isHidden) continue;

            let toggleHtml = '';
            if (isGM) {
                const checked = !isHidden ? 'checked' : '';
                toggleHtml = `
                    <label class="skill-visibility-checkbox" onclick="event.stopPropagation();" style="font-size:0.8em; display:flex; align-items:center; cursor:pointer; margin-left:auto;">
                        <input type="checkbox" class="skill-public-toggle" data-skill-id="${skillId}" ${checked}>
                        <span style="margin-left:2px; font-weight:normal; color:var(--ui-text);">公開</span>
                    </label>
                `;
            }

            let itemClass = 'char-skill-item skill-item';
            if (isGM && isHidden) itemClass += ' hidden';
            if (isGranted) itemClass += ' granted';

            skillItems.push(`
                <div class="${itemClass}" data-skill-id="${escAttr(skillId)}" data-skill-name="${escAttr(skillName)}" data-is-granted="${isGranted ? '1' : '0'}" data-grant-mode="${escAttr(grantMode)}" data-grant-rounds="${Number.isFinite(remainingRounds) ? remainingRounds : ''}" data-grant-uses="${Number.isFinite(remainingUses) ? remainingUses : ''}">
                    <div style="display:flex; flex-direction:column; overflow:hidden;">
                        <span style="font-size:0.75em; color:var(--ui-sub);">${skillId}</span>
                        <span style="font-weight:bold; font-size:0.9em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${skillName}</span>
                    </div>
                    ${isGranted ? '<span style="background:#ffe08a; color:#5a4300; border:1px solid #f3c34a; border-radius:10px; font-size:0.72em; padding:1px 6px; margin-right:6px; white-space:nowrap;">付与</span>' : ''}
                    ${toggleHtml}
                </div>
            `);
        }
        if (skillItems.length > 0) {
            skillsHtml = `<div class="char-skills-grid">${skillItems.join('')}</div>`;
        } else {
            skillsHtml = `<div style="color:var(--ui-sub); font-size:0.9em;">なし</div>`;
        }
    }
    return skillsHtml;
}

function escapeDetailHtml(value) {
    if (window.Glossary && typeof window.Glossary.escapeHtml === 'function') {
        return window.Glossary.escapeHtml(value);
    }
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function markupToHtml(value) {
    if (typeof window.formatGlossaryMarkupToHTML === 'function') {
        return window.formatGlossaryMarkupToHTML(value);
    }
    return escapeDetailHtml(value).replace(/\n/g, '<br>');
}

function renderCharacterPassives(char, breakingIds = []) {
    const effects = window.HiddenPassiveFx;
    const active = (Array.isArray(char.SPassive) ? char.SPassive : []).map(pid => {
        const passive = window.allPassiveData?.[pid] || char.special_buffs?.find(buff => buff.passive_id === pid);
        const radiance = window.radianceSkillData?.[pid];
        const data = passive || radiance;
        const name = escapeDetailHtml(data?.name || pid);
        const label = passive ? 'パッシブ' : radiance ? '輝化' : '特殊';
        const color = passive ? '#6a1b9a' : radiance ? '#0b7285' : 'var(--ui-sub)';
        const room = typeof currentRoomName === 'undefined' ? '' : currentRoomName;
        const cover = breakingIds.includes(pid)
            ? effects?.cover(true, JSON.stringify([room, char.id, char.passive_revealed_round, pid])) : '';
        return `<div class="character-passive-row" style="--passive-color:${color}">
            <details class="character-passive">
                <summary class="character-passive-heading">
                    <span aria-hidden="true">★</span>
                    <span class="character-passive-name" title="${name}">${name}</span>
                    <span class="character-passive-kind">${label}</span>
                    <span class="character-passive-chevron" aria-hidden="true">▼</span>
                    ${cover || ''}
                </summary>
                <div class="character-passive-body">
                    <div class="buff-desc-row">${markupToHtml(data?.description || '詳細情報なし')}</div>
                    ${data?.flavor ? `<div class="buff-flavor-row">${markupToHtml(data.flavor)}</div>` : ''}
                </div>
            </details></div>`;
    });
    const hidden = Array.isArray(char.hidden_passives)
        ? char.hidden_passives.map(({passive_id: id, reveal_when: condition}) => {
            const conditions = [];
            if (condition?.hp_percent_lte != null) conditions.push(`HP ${condition.hp_percent_lte}% 以下`);
            if (condition?.round_gte != null) conditions.push(`${condition.round_gte} ラウンド目以降`);
            const name = window.allPassiveData?.[id]?.name || id;
            return `<div class="hidden-passive-cover"><span>伏せ札 · ${escapeDetailHtml(name)}</span>${conditions.length
                ? `<small>${escapeDetailHtml(conditions.join(' かつ '))}</small>` : ''}</div>`;
        })
        : Array.from({length: Number(char.hidden_passive_count) || 0}, () => effects?.cover() || '');
    return active.concat(hidden).join('');
}

function passiveDetailSignature(char) {
    return JSON.stringify([char?.SPassive, char?.hidden_passives, char?.hidden_passive_count]);
}

async function refreshOpenCharacterPassives(previousState, nextState) {
    const modal = document.querySelector('#char-modal-backdrop .char-detail-modal-content');
    if (!modal) {
        if (nextState?.characters?.some(char => char.passive_revealed_ids?.some(id => !window.allPassiveData?.[id])
                && window.HiddenPassiveFx?.newThisRound(char, nextState))) {
            await reloadResourceCatalogData('passive', currentRoomName);
        }
        return;
    }
    const id = modal.dataset.charId;
    const before = previousState?.characters?.find(char => char.id === id);
    const after = nextState?.characters?.find(char => char.id === id);
    if (!after) return;
    const hp = modal.querySelector('.hp-box .detail-hp-current');
    const maxHp = modal.querySelector('.hp-box .detail-stat-max');
    if (hp) hp.textContent = after.hp;
    if (maxHp) maxHp.textContent = `/ ${after.maxHp}`;
    const signature = passiveDetailSignature(after);
    if (signature === passiveDetailSignature(before)) return;
    if (after.SPassive?.some(key => key.startsWith('Pa-') && !window.allPassiveData?.[key])) {
        await reloadResourceCatalogData('passive', currentRoomName);
    }
    if (!modal.isConnected || passiveDetailSignature(battleState?.characters?.find(char => char.id === id)) !== signature) return;
    const newIds = window.HiddenPassiveFx?.newThisRound(after, nextState)
        ? (after.passive_revealed_ids || []) : [];
    const region = modal.querySelector('.character-modal-passives');
    region.innerHTML = renderCharacterPassives(after, newIds)
        || (region.dataset.hasOther === 'true' ? '' : '<span class="cat-caption">なし</span>');
    window.HiddenPassiveFx?.observe(region);
}

function renderCharacterCard(char) {
    const ownerName = char.owner || '不明';
    const fpState = char.states.find(s => s.name === 'FP');
    const fpVal = fpState ? fpState.value : 0;

    // --- Params ---
    const coreStats = ['筋力', '生命力', '体格', '精神力', '敏捷', '直感', '経験', '物理補正', '魔法補正'];
    const explorationStats = ['五感', '採取', '本能', '鑑定', '対話', '尋問', '諜報', '窃取', '隠密', '運動', '制作', '回避'];

    // Normalize params to array of objects
    let charParams = [];
    if (Array.isArray(char.params)) {
        charParams = char.params;
    } else if (char.params && typeof char.params === 'object') {
        charParams = Object.entries(char.params).map(([k, v]) => ({ label: k, value: v }));
    }

    // 旧ラベル -> 正規ラベル。サーバ側 STATUS_NAME_ALIASES と揃える。
    // 正規化を通らない経路のデータが来ても 0 表示にならないようにする。
    const statusNameAliases = { '速度': '敏捷' };
    const canonicalLabel = (label) => statusNameAliases[label] || label;

    // Helper to generate grid HTML
    const renderParamsGrid = (labels) => {
        const items = labels.map(stat => {
            const p = charParams.find(cp => canonicalLabel(cp.label) === stat);
            const val = p ? p.value : 0;
            return `
                <div class="char-param-item">
                    <span class="param-label">${stat}</span>
                    <span class="param-value">${val}</span>
                </div>
            `;
        });
        return `<div class="char-params-grid">${items.join('')}</div>`;
    };

    // Determine default view mode based on global BattleState
    const isExploration = (typeof battleState !== 'undefined' && battleState.mode === 'exploration');
    const displayBattle = isExploration ? 'none' : 'block';
    const displayExploration = isExploration ? 'block' : 'none';
    const btnText = isExploration ? '戦闘ステータスへ' : '探索技能へ';
    const currentMode = isExploration ? 'exploration' : 'battle';

    const paramsHtml = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
             <h4 style="margin:0; color:#333; font-size:1em;">Parameters</h4>
             <button class="params-toggle-btn action-btn secondary"
                style="font-size:0.8em; padding:2px 8px; cursor:pointer;"
                data-mode="${currentMode}">
                ${btnText}
             </button>
        </div>
        <div class="params-container params-battle" style="display:${displayBattle};">
            ${renderParamsGrid(coreStats)}
        </div>
        <div class="params-container params-exploration" style="display:${displayExploration};">
            ${renderParamsGrid(explorationStats)}
        </div>
    `;

    // ... (rest of renderCharacterCard) ...

    /* Note: Ideally we shouldn't have to duplicate the logic, but since we are modifying lines far apart,
       we will handle the event listener replacement in a separate chunk within this same tool call or if needed separately.
       Wait, I can't modify multiple non-contiguous blocks in one 'replace_file_content'.
       Ill use this block for the HTML generation part first.
    */

    const applyBuffTemplateText = (text, buff) => {
        if (text === null || text === undefined) return text;
        const source = String(text);
        const data = (buff && typeof buff === 'object' && buff.data && typeof buff.data === 'object')
            ? buff.data
            : {};

        const value = (buff && buff.value !== undefined && buff.value !== null)
            ? String(buff.value)
            : ((data.value !== undefined && data.value !== null) ? String(data.value) : '');
        const count = (buff && buff.count !== undefined && buff.count !== null)
            ? String(buff.count)
            : ((data.count !== undefined && data.count !== null) ? String(data.count) : '');

        let duration = '';
        let durationVal = buff ? buff.lasting : undefined;
        if (durationVal === undefined && buff) durationVal = buff.round;
        if (durationVal === undefined && buff) durationVal = buff.duration;
        if (durationVal !== undefined && durationVal !== null && !Number.isNaN(Number(durationVal))) {
            duration = String(durationVal);
        }

        return source
            .replace(/{{\s*value\s*}}/gi, value)
            .replace(/{{\s*count\s*}}/gi, count)
            .replace(/{{\s*duration\s*}}/gi, duration);
    };
    const charIdAttr = escapeDetailHtml((char && char.id != null) ? char.id : '');
    const normalizeDetailTagIds = (values) => {
        if (!Array.isArray(values)) return [];
        const seen = new Set();
        return values.map((value) => String(value).trim()).filter((value) => {
            if (!value || seen.has(value)) return false;
            seen.add(value);
            return true;
        });
    };
    const detailTagIds = normalizeDetailTagIds(char.tag_ids);
    const knownDetailTagIds = new Set(detailTagIds);
    const disabledDetailTagIds = new Set(
        normalizeDetailTagIds(char.disabled_tag_ids).filter((tagId) => knownDetailTagIds.has(tagId))
    );
    const characterTagsHtml = detailTagIds.length > 0
        ? `<div class="character-detail-tags">${detailTagIds.map((tagId) => {
            const disabledClass = disabledDetailTagIds.has(tagId) ? ' is-disabled' : '';
            const title = disabledDetailTagIds.has(tagId) ? ' title="無効化中"' : '';
            return `<span class="character-detail-tag${disabledClass}"${title}>${escapeDetailHtml(tagId)}</span>`;
        }).join('')}</div>`
        : '';

    // --- States (Stack) ---
    let statesHtml = '';
    char.states.forEach(s => {
        const normalizedName = normalizeModalStateName(s.name);
        if (['HP', 'MP', 'FP'].includes(normalizedName)) return;
        if (s.value === 0) return;
        const config = (typeof STATUS_CONFIG !== 'undefined') ? STATUS_CONFIG[normalizedName] : null;
        const colorStyle = config ? `color: ${config.color}; font-weight:bold;` : '';
        statesHtml += `<div class="detail-buff-item" style="${colorStyle}">${normalizedName}: ${s.value}</div>`;
    });
    if (!statesHtml) statesHtml = '<span style="color:var(--ui-sub); font-size:0.9em;">なし</span>';

    // --- Buffs (Flavor Text Handling Fix) ---
    const fissureView = buildFissureDetailView(char);
    let specialBuffsHtml = '';
    let fissureRendered = false;
    const summonDurationMode = String(char.summon_duration_mode || '').toLowerCase();
    const summonRemainingRounds = parseInt(char.remaining_summon_rounds, 10);
    if (
        char.is_summoned
        && summonDurationMode === 'duration_rounds'
        && Number.isFinite(summonRemainingRounds)
        && summonRemainingRounds > 0
    ) {
        specialBuffsHtml += `
            <details class="detail-buff-item" style="border: 1px solid #ffc078; border-radius: 4px; margin-bottom: 5px; overflow: hidden; background: var(--ui-bg);">
                <summary style="background: #fff3bf; padding: 8px 10px; cursor: pointer; font-weight: bold; font-size: 0.95em; display: flex; align-items: center; justify-content: space-between; outline: none;">
                    <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 5px;">
                        <span>召喚継続</span>
                        <span class="buff-duration-badge" style="background:var(--ui-sub); color:var(--ui-bg); padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:8px; white-space: nowrap;">残り${summonRemainingRounds}R</span>
                    </div>
                    <span style="font-size: 0.8em; color: var(--ui-sub);">▼</span>
                </summary>
                <div style="padding: 10px; background: var(--ui-bg); border-top: 1px solid #ffe8a1;">
                    <div class="buff-desc-row" style="font-weight: bold; color: #212529; font-size: 0.9em; margin-bottom: 5px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word;">この召喚体はラウンド終了時に残り継続ラウンドが減少し、0で消滅します。</div>
                </div>
            </details>
        `;
    }
    const sPassiveIds = new Set();
    const sPassiveNames = new Set();
    const normalizePassiveName = (value) => String(value || '').trim().replace(/_.+$/, '');
    if (char.SPassive && Array.isArray(char.SPassive)) {
        char.SPassive.forEach((pid) => {
            const key = String(pid || '').trim();
            if (!key) return;
            sPassiveIds.add(key);
            const pData = (window.allPassiveData && window.allPassiveData[key]) ? window.allPassiveData[key] : null;
            const pName = normalizePassiveName(pData && pData.name);
            if (pName) sPassiveNames.add(pName);
            const rData = (window.radianceSkillData && window.radianceSkillData[key]) ? window.radianceSkillData[key] : null;
            const rName = normalizePassiveName(rData && rData.name);
            if (rName) sPassiveNames.add(rName);
        });
    }

    if (char.special_buffs && char.special_buffs.length > 0) {
        char.special_buffs.forEach((b) => {
            if (b.buff_id === 'Bu-Fissure') {
                if (!fissureRendered) {
                    specialBuffsHtml += renderFissureDetail(fissureView);
                    fissureRendered = true;
                }
                return;
            }
            const buffSkillId = String(b.skill_id || '').trim();
            const buffName = normalizePassiveName(b.name);
            const duplicatedBySPassive = (
                (buffSkillId && sPassiveIds.has(buffSkillId))
                || (buffName && sPassiveNames.has(buffName))
                || (b.passive_id && sPassiveIds.has(b.passive_id))
            );
            if (duplicatedBySPassive) {
                return;
            }

            const rawBuffCatalogId = b.buff_id || (b.data && b.data.buff_id) || null;
            const stackVariant = String(b.variant || (b.data && b.data.variant) || '').trim().toLowerCase();
            // 凝魔-血漿variant時は、表示用の参照ソースをBu-48へ切り替える。
            const buffCatalogId = (
                String(rawBuffCatalogId || '').trim() === 'Bu-31'
                && stackVariant === 'blood_plasma'
            ) ? 'Bu-48' : (
                String(rawBuffCatalogId || '').trim() === 'Bu-30'
                && ['burst_guidance', 'explosion_guidance', 'induce_burst', 'induced_burst'].includes(stackVariant)
            ) ? 'Bu-49' : rawBuffCatalogId;
            let descriptionText = b.description;
            let flavorText = b.flavor;
            const explicitDisplayName = String(
                (b.display_name || (b.data && b.data.display_name) || '')
            ).trim();
            let nameDisplay = explicitDisplayName || b.name;
            const hasExplicitDisplayName = !!explicitDisplayName;
            const isBloodPlasmaView = String(buffCatalogId || '').trim() === 'Bu-48';
            if (isBloodPlasmaView) {
                nameDisplay = '凝魔-血漿';
            }
            const isBurstGuidanceView = String(buffCatalogId || '').trim() === 'Bu-49';
            if (isBurstGuidanceView) {
                nameDisplay = '蓄力-誘爆';
            }

            // バフ図鑑が引けるならそちらを正として使う
            if (typeof BUFF_DATA !== 'undefined' && typeof BUFF_DATA.get === 'function') {
                const foundById = BUFF_DATA.get(b.name, buffCatalogId);
                if (foundById) {
                    if (!hasExplicitDisplayName) {
                        if (foundById.display_name) {
                            nameDisplay = foundById.display_name;
                        } else if (foundById.name) {
                            nameDisplay = foundById.name;
                        }
                    }
                    if (foundById.description) descriptionText = foundById.description;
                    if (typeof foundById.flavor === 'string') flavorText = foundById.flavor;
                }
            }

            // If description/flavor not present in instance, look up in BUFF_DATA
            if (!descriptionText || !flavorText) {
                let lookupName = b.name;
                if (lookupName.includes('_')) lookupName = lookupName.split('_')[0];

                if (typeof BUFF_DATA !== 'undefined' && typeof BUFF_DATA.get === 'function') {
                    const found = BUFF_DATA.get(b.name, buffCatalogId);
                    if (found) {
                        if (!descriptionText) descriptionText = found.description;
                        if (!flavorText) flavorText = found.flavor;
                    } else {
                        const foundBase = BUFF_DATA.get(lookupName, buffCatalogId);
                        if (foundBase) {
                            if (!descriptionText) descriptionText = foundBase.description;
                            if (!flavorText) flavorText = foundBase.flavor;
                        }
                    }
                }
            }

            descriptionText = applyBuffTemplateText(descriptionText, b);
            flavorText = applyBuffTemplateText(flavorText, b);

            if (!descriptionText) descriptionText = "説明なし";
            if (!flavorText) flavorText = "";

            if (!hasExplicitDisplayName && nameDisplay && nameDisplay.includes('_')) {
                nameDisplay = nameDisplay.split('_')[0];
            }

            let durationVal = b.lasting;
            if (durationVal === undefined) durationVal = b.round;
            if (durationVal === undefined) durationVal = b.duration;

            let durationHtml = "";
            const sourceBadgeId = String(buffCatalogId || '').trim();
            if (sourceBadgeId) {
                durationHtml += `<span class="buff-source-badge" style="background:#495057; color:var(--ui-bg); padding:1px 6px; border-radius:10px; font-size:0.72em; margin-left:4px; white-space: nowrap;">src:${sourceBadgeId}</span>`;
            }

            // 1. 持続ラウンド表示 (無限(-1)の場合は非表示)
            if (durationVal !== null && durationVal !== undefined && !isNaN(durationVal)) {
                if (durationVal > 0 && durationVal < 99) {
                    durationHtml += `<span class="buff-duration-badge" style="background:var(--ui-sub); color:var(--ui-bg); padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:8px; white-space: nowrap;">残り${durationVal}R</span>`;
                }
                // -1 (無限) の場合は何も追加しない
            }

            // 2. 残り回数表示 (count > 0 なら表示)
            const countVal = b.count;
            if (countVal !== undefined && countVal !== null && countVal > 0) {
                durationHtml += `<span class="buff-count-badge" style="background:#0dcaf0; color:#000; padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:4px; white-space: nowrap; font-weight:bold;">残${countVal}回</span>`;
            }

            const delayVal = parseInt(b.delay, 10) || 0;
            const speedBuffId = String(b.buff_id || (b.data && b.data.buff_id) || '').trim();
            const isSpeedModBuff = (speedBuffId === 'Bu-11' || speedBuffId === 'Bu-12');
            if (isSpeedModBuff) {
                if (delayVal > 0) {
                    durationHtml += `<span class="buff-speed-state-badge" style="background:#d63384; color:var(--ui-bg); padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:4px; white-space: nowrap;">予約中(${delayVal}R)</span>`;
                } else {
                    durationHtml += `<span class="buff-speed-state-badge" style="background:#198754; color:var(--ui-bg); padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:4px; white-space: nowrap;">適用中</span>`;
                }
            }
            if (delayVal > 0) {
                durationHtml += `<span class="buff-delay-badge" style="background:#d63384; color:var(--ui-bg); padding:1px 6px; border-radius:10px; font-size:0.8em; margin-left:4px; white-space: nowrap;">発動まで${delayVal}R</span>`;
            }

            specialBuffsHtml += `
                <details class="buff-accordion">
                    <summary class="buff-summary">
                        <div class="buff-summary-body">
                            <span class="buff-name">${nameDisplay}</span>
                            ${durationHtml ? `<div class="buff-meta">${durationHtml}</div>` : ''}
                        </div>
                        <span class="buff-arrow">▼</span>
                    </summary>
                    <div class="buff-body">
                        <div class="buff-desc-row">${markupToHtml(descriptionText)}</div>
                        ${flavorText ? `<div class="buff-flavor-row">${markupToHtml(flavorText)}</div>` : ''}
                    </div>
                </details>
            `;
        });
    }

    if (!fissureRendered) specialBuffsHtml += renderFissureDetail(fissureView);

    const state = typeof battleState !== 'undefined' ? battleState : null;
    const newPassiveIds = window.HiddenPassiveFx?.newThisRound(char, state) ? (char.passive_revealed_ids || []) : [];
    const passivesHtml = renderCharacterPassives(char, newPassiveIds)
        || (specialBuffsHtml ? '' : '<span class="cat-caption">なし</span>');

    // --- Inline CSS ---
    const inlineStyle = `
        <style>
            .char-detail-modal-content {
                width: min(780px, 92vw);
                box-sizing: border-box;
                overflow-x: hidden;
            }
            .char-skills-grid {
                display: grid !important;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
            }
            .char-skill-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                border: 1px solid var(--ui-line);
                padding: 6px 10px;
                border-radius: 4px;
                background: var(--ui-bg);
                cursor: pointer;
                transition: background 0.2s;
            }
            .char-skill-item:hover {
                background: #f0f8ff;
                border-color: #baddff;
            }
            .char-skill-item.hidden {
                background: var(--ui-soft);
                opacity: 0.7;
                border: 1px dashed var(--ui-control);
            }
            .char-skill-item.granted {
                background: #fff8dc;
                border-color: #f1cf67;
            }
            .char-skill-item.granted:hover,
            .char-skill-item.granted.selected {
                background: #ffefb0;
                border-color: #dfb33f;
            }
            /* Parameter Grid Styles */
            .char-params-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 8px;
                width: 100%;
            }
            .char-param-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                border: 1px solid var(--ui-control);
                padding: 6px 10px;
                border-radius: 4px;
                background: var(--ui-soft);
                font-size: 0.9em;
            }
            .param-label {
                color: var(--ui-text);
                font-weight: bold;
            }
            .param-value {
                font-weight: bold;
                font-size: 1.1em;
                color: #222;
            }

            /* Section titles */
            .detail-section-title {
                margin: 0 0 10px 0;
                font-size: 0.78em;
                font-weight: 700;
                letter-spacing: 0.1em;
                text-transform: uppercase;
                color: var(--ui-text);
                padding-left: 8px;
                border-left: 3px solid var(--accent-gold, #c8a84b);
                line-height: 1.6;
            }
            /* Stat boxes */
            .detail-stat-box {
                flex: 1;
                text-align: center;
                padding: 12px 10px 10px;
                background: var(--ui-bg);
                border: 1px solid #e8e8e8;
                border-top: 3px solid #e8e8e8;
                border-radius: 6px;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
            }
            .detail-stat-box.hp-box { border-top-color: var(--color-hp, #28a745); }
            .detail-stat-box.mp-box { border-top-color: var(--color-mp, #4a90d9); }
            .detail-stat-box.fp-box { border-top-color: var(--color-fp, #e0b84a); }
            .detail-stat-label {
                display: block;
                font-size: 0.72em;
                color: var(--ui-sub);
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                margin-bottom: 6px;
            }
            .detail-stat-val {
                font-size: 1.5em;
                font-weight: 800;
                line-height: 1;
            }
            .detail-stat-max {
                font-size: 0.6em;
                color: #aaa;
                font-weight: 400;
            }
            /* Buff accordion - stable layout */
            details > summary { list-style: none; }
            details > summary::-webkit-details-marker { display: none; }
            .buff-accordion {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-bottom: 6px;
                overflow: hidden;
            }
            .buff-summary {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 8px;
                padding: 9px 12px;
                background: #f1f5f9;
                cursor: pointer;
                outline: none;
                user-select: none;
            }
            .buff-accordion[open] > .buff-summary {
                border-bottom: 1px solid #e2e8f0;
            }
            .buff-summary-body {
                flex: 1;
                min-width: 0;
            }
            .buff-name {
                display: block;
                font-weight: 700;
                font-size: 0.95em;
                color: #1e293b;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                line-height: 1.4;
            }
            .buff-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 4px;
                margin-top: 4px;
                align-items: center;
            }
            .fissure-detail-summary {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }
            .fissure-detail-total {
                font-weight: 700;
                color: #1e293b;
                white-space: nowrap;
            }
            .fissure-detail-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 12px;
                font-size: 0.9em;
                color: #334155;
            }
            .fissure-detail-table th, .fissure-detail-table td {
                padding: 6px 0;
                border-bottom: 1px solid #e2e8f0;
                text-align: left;
                overflow-wrap: anywhere;
            }
            .fissure-detail-table th {
                color: #64748b;
                font-weight: 500;
            }
            .fissure-detail-table th:last-child, .fissure-detail-table td:last-child {
                text-align: right;
                padding-left: 12px;
                white-space: nowrap;
            }
            .fissure-detail-unavailable {
                margin: 12px 0 0;
                font-size: 0.9em;
                color: #64748b;
            }
            .buff-arrow {
                flex-shrink: 0;
                font-size: 0.7em;
                color: #94a3b8;
                transition: transform 0.2s ease;
                padding-top: 4px;
            }
            .buff-accordion[open] .buff-arrow {
                transform: rotate(180deg);
            }
            .buff-body {
                padding: 10px 12px;
                background: var(--ui-bg);
            }
            .buff-desc-row {
                font-weight: 600;
                color: #334155;
                font-size: 0.9em;
                line-height: 1.5;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            .buff-flavor-row {
                color: #64748b;
                font-size: 0.85em;
                font-style: italic;
                line-height: 1.4;
                white-space: pre-wrap;
                word-wrap: break-word;
                border-top: 1px dashed #e2e8f0;
                margin-top: 6px;
                padding-top: 6px;
            }
        </style>
    `;

    return `
        ${inlineStyle}
        <div class="char-detail-modal-content" data-char-id="${charIdAttr}">
            <div class="detail-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; padding-bottom:14px; ">
                <div class="character-detail-identity">
                    <h2 style="margin:0; font-size:1.6em; font-weight:800; border-left:5px solid ${char.color}; padding-left:12px; letter-spacing:0; line-height:1.3;">${char.name}</h2>
                    ${characterTagsHtml}
                </div>
                <div style="display:flex; gap:15px; align-items:center;">
                    <button class="modal-settings-btn" id="modal-settings-trigger" style="background:none; border:none; font-size:1.5em; cursor:pointer; color:var(--ui-text);" title="設定">⚙</button>
                    <button class="modal-close-btn" style="background:none; border:none; font-size:2em; cursor:pointer; color:var(--ui-sub); line-height:1;">&times;</button>
                </div>
            </div>

            <div class="clasp" aria-hidden="true"><i></i></div>
            <div id="char-image-preview" style="text-align:center; ${char.image ? '' : 'display: none;'} margin-bottom:15px;">
                <img id="char-preview-img" src="${char.image || ''}" style="max-height: 120px; border: 1px solid var(--ui-control); border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            </div>

            <div class="detail-stat-grid" style="display:flex; gap:10px; margin-bottom:20px;">
                <div class="detail-stat-box hp-box">
                    <span class="detail-stat-label">HP</span>
                    <span class="detail-stat-val" style="color:var(--ui-add);"><span class="detail-hp-current">${char.hp}</span> <span class="detail-stat-max">/ ${char.maxHp}</span></span>
                </div>
                <div class="detail-stat-box mp-box">
                    <span class="detail-stat-label">MP</span>
                    <span class="detail-stat-val" style="color:var(--ui-primary);">${char.mp} <span class="detail-stat-max">/ ${char.maxMp}</span></span>
                </div>
                <div class="detail-stat-box fp-box">
                    <span class="detail-stat-label">FP</span>
                    <span class="detail-stat-val" style="color:var(--ui-warn);">${fpVal}</span>
                </div>
            </div>

            <div class="detail-section" style="margin-bottom:20px;">
                ${paramsHtml}
            </div>

            <div class="detail-section" style="margin-bottom:20px;">
                <h4 class="detail-section-title">状態異常</h4>
                <div class="detail-buff-list">${statesHtml}</div>
            </div>

            <div class="detail-section" style="margin-bottom:20px;">
                <h4 class="detail-section-title">特殊効果 / バフ</h4>
                <div class="detail-buff-accordion-list">${specialBuffsHtml}
                    <div class="character-modal-passives" data-has-other="${Boolean(specialBuffsHtml)}">${passivesHtml}</div>
                </div>
            </div>

            <div class="detail-section" style="margin-bottom:20px;">
                <details open style="border: 1px solid var(--ui-line); border-radius: 4px;">
                    <summary style="background: var(--ui-soft); padding: 10px; cursor: pointer; font-weight: bold; font-size: 1.1em; outline: none; display: flex; justify-content: space-between; align-items: center; user-select: none;">
                        <span>Skills</span>
                        <span style="font-size: 0.8em; color: var(--ui-sub);">▼</span>
                    </summary>
                    <div class="character-modal-skills" style="padding: 10px; background: var(--ui-bg);">
                        ${renderCharacterSkills(char)}
                    </div>
                </details>
            </div>
        </div>
    `;
}

function bindCharacterSkills(region, char) {
    const skillItems = region.querySelectorAll('.skill-item');
    skillItems.forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.closest('.skill-visibility-checkbox') || e.target.classList.contains('skill-public-toggle')) return;
            skillItems.forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            const skillId = item.dataset.skillId;
            const isGranted = item.dataset.isGranted === '1';
            const grantRoundsRaw = parseInt(item.dataset.grantRounds, 10);
            const grantUsesRaw = parseInt(item.dataset.grantUses, 10);
            const granted = isGranted ? {
                mode: item.dataset.grantMode || '',
                remaining_rounds: Number.isFinite(grantRoundsRaw) ? grantRoundsRaw : null,
                remaining_uses: Number.isFinite(grantUsesRaw) ? grantUsesRaw : null,
            } : null;
            openSkillDetailModal(skillId, item.dataset.skillName, { granted, ownerCharId: char.id });
        });
    });

    const skillToggles = region.querySelectorAll('.skill-public-toggle');
    skillToggles.forEach(chk => {
        chk.addEventListener('change', (e) => {
            const skillId = chk.dataset.skillId;
            const isPublic = chk.checked;

            const hidden = char.hidden_skills || [];
            const currentHidden = isPublic ? hidden.filter(id => id !== skillId) : [...new Set([...hidden, skillId])];
            socket.emit('request_state_update', {
                room: currentRoomName,
                charId: char.id,
                changes: { hidden_skills: currentHidden }
            });
        });
    });
}

function refreshOpenCharacterSkills(previousState, nextState) {
    const modal = document.querySelector('#char-modal-backdrop .char-detail-modal-content');
    if (!modal) return;
    const charId = modal.dataset.charId;
    const before = previousState?.characters?.find(char => char.id === charId);
    const after = nextState?.characters?.find(char => char.id === charId);
    if (!after || JSON.stringify(before?.hidden_skills || []) === JSON.stringify(after.hidden_skills || [])) return;
    const region = modal.querySelector('.character-modal-skills');
    region.innerHTML = renderCharacterSkills(after);
    bindCharacterSkills(region, after);
}

function openCharacterModal(charId) {
    closeCharacterModal();
    const char = battleState.characters.find(c => c.id === charId);
    if (!char) return;
    const modalBackdrop = document.createElement('div');
    modalBackdrop.id = 'char-modal-backdrop';
    modalBackdrop.className = 'modal-backdrop';
    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';
    modalContent.style.overflowX = 'hidden';
    modalContent.style.scrollbarGutter = 'stable';

    // Call the single unified renderer
    modalContent.innerHTML = renderCharacterCard(char);

    applySystemWindow(modalContent);
    modalBackdrop.appendChild(modalContent);
    document.body.appendChild(modalBackdrop);
    window.HiddenPassiveFx?.observe(modalContent.querySelector('.character-modal-passives'));
    modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) closeCharacterModal();
    });
    modalContent.querySelector('.modal-close-btn').addEventListener('click', closeCharacterModal);

    // --- Context Menu for Settings ---
    const settingsBtn = modalContent.querySelector('#modal-settings-trigger');
    settingsBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // Stop propagation
        createSettingsContextMenu(e.target, char);
    });

    // Input Debouncing for States
    let debounceTimer = null;
    let pendingChanges = {};
    modalContent.addEventListener('input', (e) => {
        const target = e.target;
        // Skip inputs managed by other handlers
        if (target.type === 'file' || target.classList.contains('settings-input')) return;

        const newValue = parseInt(target.value, 10) || 0;
        let statName = null;
        if (target.classList.contains('hp-input')) statName = 'HP';
        else if (target.classList.contains('mp-input')) statName = 'MP';
        else if (target.classList.contains('state-value-input')) statName = target.dataset.stateName;

        if (statName) {
            pendingChanges[statName] = newValue;
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                socket.emit('request_state_update', {
                    room: currentRoomName,
                    charId: char.id,
                    changes: pendingChanges
                });
                pendingChanges = {};
            }, 2000);
        }
    });

    bindCharacterSkills(modalContent.querySelector('.character-modal-skills'), char);

    // --- Parameter Toggle Listener ---
    const paramToggleBtn = modalContent.querySelector('.params-toggle-btn');
    if (paramToggleBtn) {
        paramToggleBtn.addEventListener('click', () => {
            const currentMode = paramToggleBtn.dataset.mode;
            const battleContainer = modalContent.querySelector('.params-battle');
            const explorationContainer = modalContent.querySelector('.params-exploration');

            if (currentMode === 'exploration') {
                // Switch TO Battle
                if (battleContainer) battleContainer.style.display = 'block';
                if (explorationContainer) explorationContainer.style.display = 'none';
                paramToggleBtn.textContent = '探索技能へ';
                paramToggleBtn.dataset.mode = 'battle';
            } else {
                // Switch TO Exploration
                if (battleContainer) battleContainer.style.display = 'none';
                if (explorationContainer) explorationContainer.style.display = 'block';
                paramToggleBtn.textContent = '戦闘ステータスへ';
                paramToggleBtn.dataset.mode = 'exploration';
            }
        });
    }
}

/**
 * 設定コンテキストメニューを作成・表示
 */
function createSettingsContextMenu(triggerEl, char) {
    const playMode = String(battleState.play_mode || 'normal').trim().toLowerCase();
    const canReflectRadiance = playMode === 'normal';
    const latestChar = window.getLatestCharacterForBehaviorEditor(char);
    if (latestChar && typeof latestChar === 'object') {
        char = latestChar;
    }
    // 既存のメニューがあれば削除
    const existing = document.getElementById('char-settings-context-menu');
    if (existing) existing.remove();

    const isGM = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');
    const ownerName = char.owner || '不明';
    const baseBehaviorProfile = (
        char.flags
        && typeof char.flags === 'object'
        && char.flags.behavior_profile
        && typeof char.flags.behavior_profile === 'object'
    )
        ? char.flags.behavior_profile
        : {
            enabled: false,
            version: 1,
            slot_generation_mode: 'step_actions',
            initial_loop_id: null,
            loops: {}
        };

    // 譲渡先リスト
    let ownerOptions = '';
    if (typeof currentRoomUserList !== 'undefined') {
        currentRoomUserList.forEach(u => {
            ownerOptions += `<option value="${u.user_id}">${u.username}</option>`;
        });
    }

    const menuHtml = `
        <div id="char-settings-context-menu" style="position:absolute; z-index:10000; background:#fff; border:1px solid #ced4da; box-shadow:0 4px 15px rgba(0,0,0,0.15); border-radius:6px; padding:15px; width:280px; font-size:0.95em; color: #333;">
            <div style="font-weight:bold; border-bottom:2px solid #f8f9fa; padding-bottom:8px; margin-bottom:12px; color: #495057; font-size: 1.1em;">${char.name} 設定</div>

            <div style="margin-bottom:15px;">
                <label style="display:block; color:#6c757d; margin-bottom:4px; font-size: 0.85em; font-weight: bold;">所有権の譲渡</label>
                <div style="display:flex; gap:5px;">
                     <select id="ctx-transfer-select" class="settings-input" style="flex:1; padding:4px; border: 1px solid #ced4da; border-radius: 4px;">
                         <option value="">(選択)</option>
                         ${ownerOptions}
                     </select>
                     <button id="ctx-transfer-btn" style="padding:4px 10px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">実行</button>
                </div>
                <div style="font-size:0.8em; color:#adb5bd; margin-top:2px;">現在の所有者: ${ownerName}</div>
            </div>

            <div style="margin-bottom:15px;">
                <label style="display:block; color:#6c757d; margin-bottom:4px; font-size: 0.85em; font-weight: bold;">駒サイズ: <span id="ctx-scale-val">${char.tokenScale || 1.0}</span>倍</label>
                <input type="range" id="ctx-scale-slider" class="settings-input" min="0.5" max="2.0" step="0.1" value="${char.tokenScale || 1.0}" style="width:100%;">
            </div>

            <div style="margin-bottom:15px;">
                 <label style="display:block; color:#6c757d; margin-bottom:4px; font-size: 0.85em; font-weight: bold;">立ち絵</label>
                 <button id="ctx-image-btn" style="width:100%; padding: 8px; background: #0d6efd; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; transition: background 0.2s;">画像を変更</button>
            </div>

            <div style="margin-bottom:15px;">
                 <button id="ctx-return-btn" style="width:100%; background:#f8f9fa; color: #495057; border: 1px solid #ced4da; padding: 8px; border-radius: 4px; cursor: pointer; font-weight: bold;">未配置に戻す</button>
            </div>

            ${isGM ? `
            <div style="margin-bottom:15px; padding: 5px; background: #f8f9fa; border-radius: 4px;">
                <label style="display:flex; align-items:center; cursor: pointer;">
                    <input type="checkbox" id="ctx-gm-only" class="settings-input" ${char.gmOnly ? 'checked' : ''} style="margin-right: 8px;"> <span style="font-size: 0.9em; color: #495057;">GMのみ操作可能</span>
                </label>
            </div>
            ` : ''}

            <div style="margin-bottom:15px; padding: 5px; background: #fff8e1; border-radius: 4px;">
                <label style="display:flex; align-items:center; cursor: pointer;">
                    <input type="checkbox" id="ctx-show-planned" class="settings-input" ${(char.flags && char.flags.show_planned_skill) ? 'checked' : ''} style="margin-right: 8px;">
                    <span style="font-size: 0.9em; color: #495057;">予約スキルを公開 (AI用)</span>
                </label>
            </div>

            ${isGM ? `
            <div style="margin-bottom:15px; padding: 8px; background: #eef6ff; border-radius: 4px; border:1px solid #d0e2ff;">
                <label style="display:flex; align-items:center; cursor: pointer; margin-bottom:8px;">
                    <input type="checkbox" id="ctx-behavior-enabled" class="settings-input" ${baseBehaviorProfile.enabled ? 'checked' : ''} style="margin-right: 8px;">
                    <span style="font-size: 0.9em; color: #2f4858;">行動チャート有効</span>
                </label>
                <button id="ctx-behavior-edit-btn" style="width:100%; padding: 6px 8px; background:#2f7fbf; color:#fff; border:none; border-radius:4px; cursor:pointer;">行動チャート編集（フロー）</button>
            </div>
            ` : ''}

            ${char.owned_character_id && playMode !== 'hollow' ? `
            <div style="margin-bottom:15px; padding: 8px; background: #f0fdf4; border-radius: 4px; border:1px solid #bbf7d0;">
                <div style="font-size: 0.85em; font-weight:bold; color:#166534; margin-bottom:6px;">持ちキャラへ成果を反映</div>
                ${(char.flags && char.flags.results_reflected) ? `
                <div style="font-size:0.85em; color:#166534;">このセッションの成果は反映済みです。</div>
                ` : `
                <label style="display:block; font-size:0.8em; color:#166534; margin-bottom:2px;">獲得経験値</label>
                <input type="number" id="ctx-reflect-exp" class="settings-input" value="0" min="0" style="width:100%; padding:4px; border:1px solid #bbf7d0; border-radius:4px; margin-bottom:6px;">
                ${canReflectRadiance ? `
                <label style="display:block; font-size:0.8em; color:#166534; margin-bottom:2px;">獲得通過点</label>
                <input type="number" id="ctx-reflect-radiance" class="settings-input" value="0" min="0" step="1" style="width:100%; padding:4px; border:1px solid #bbf7d0; border-radius:4px; margin-bottom:6px;">
                ` : ''}
                <label style="display:block; font-size:0.8em; color:#166534; margin-bottom:2px;">獲得アイテム（例: item-heal:2, item-key:1）</label>
                <input type="text" id="ctx-reflect-items" class="settings-input" placeholder="item_id:個数, ..." style="width:100%; padding:4px; border:1px solid #bbf7d0; border-radius:4px; margin-bottom:8px; box-sizing:border-box;">
                <button id="ctx-reflect-btn" style="width:100%; padding:6px 8px; background:#16a34a; color:#fff; border:none; border-radius:4px; cursor:pointer;">成果を反映</button>
                `}
            </div>
            ` : ''}

            <hr style="border:0; border-top:1px solid #e9ecef; margin:10px 0 15px 0;">
            <button id="ctx-delete-btn" style="width:100%; background:#dc3545; color:white; border:none; padding:10px; border-radius:4px; font-weight:bold; cursor: pointer; transition: background 0.2s;">削除</button>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', menuHtml);
    const menu = document.getElementById('char-settings-context-menu');
    if (battleState.play_mode === 'hollow' && window.HollowParty) {
        menu.dataset.characterId = char.id;
        window.refreshHollowTokenControls();
    }

    // Positioning (Near the trigger button)
    const rect = triggerEl.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    menu.style.top = `${rect.bottom + scrollTop + 5}px`;
    menu.style.left = `${rect.left - 200}px`; // Shift left to keep in viewport usually

    // Event Listeners

    // Close on clicking outside
    const closeMenu = () => menu.remove();
    setTimeout(() => document.addEventListener('click', closeMenu, { once: true }), 0);
    menu.addEventListener('click', (e) => e.stopPropagation()); // Prevent closing when clicking inside

    // Transfer
    const transferBtn = menu.querySelector('#ctx-transfer-btn');
    transferBtn.addEventListener('click', async () => {
        const select = menu.querySelector('#ctx-transfer-select');
        const newOwnerId = select.value;
        const newOwnerName = select.options[select.selectedIndex].text;
        if (!newOwnerId) return;
        if (await window.showAppConfirm(`所有権を「${newOwnerName}」に譲渡しますか？`, {
            defaultFocus: 'cancel',
            title: '所有権譲渡',
            confirmText: '譲渡',
        })) {
            socket.emit('request_transfer_character_ownership', {
                room: currentRoomName, character_id: char.id, new_owner_id: newOwnerId, new_owner_name: newOwnerName
            });
            closeMenu();
        }
    });

    // Scale
    const scaleSlider = menu.querySelector('#ctx-scale-slider');
    const scaleValDisplay = menu.querySelector('#ctx-scale-val');
    scaleSlider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        scaleValDisplay.textContent = val.toFixed(1);
        socket.emit('request_update_token_scale', {
            room: currentRoomName, charId: char.id, scale: val
        });
    });

    // Image
    const imgBtn = menu.querySelector('#ctx-image-btn');
    imgBtn.addEventListener('click', () => {
        openImagePicker((selectedImage) => {
            const battleImage = selectedImage.croppedUrl || selectedImage.url;
            const explorationImage = selectedImage.originalUrl || selectedImage.url;
            socket.emit('request_state_update', {
                room: currentRoomName,
                charId: char.id,
                changes: {
                    image: battleImage,
                    imageOriginal: explorationImage
                }
            });
            // Update modal preview immediately if possible
            const previewImg = document.getElementById('char-preview-img');
            const previewArea = document.getElementById('char-image-preview');
            if (previewImg) {
                previewImg.src = battleImage;
                previewArea.style.display = 'block';
            }
            closeMenu();
        });
    });

    // Return
    const returnBtn = menu.querySelector('#ctx-return-btn');
    returnBtn.addEventListener('click', async () => {
        if (await window.showAppConfirm('未配置に戻しますか？', {
            title: '未配置に戻す',
            confirmText: '戻す',
        })) {
            socket.emit('request_move_character', { room: currentRoomName, character_id: char.id, x: -1, y: -1 });
            closeGameModal('char-modal-backdrop'); // Helper or manually remove
            const modal = document.getElementById('char-modal-backdrop');
            if (modal) modal.remove();
            closeMenu();
        }
    });

    // 計画36 Phase 4: 持ちキャラへの成果反映
    const reflectBtn = menu.querySelector('#ctx-reflect-btn');
    if (reflectBtn) {
        reflectBtn.addEventListener('click', () => {
            const expInput = menu.querySelector('#ctx-reflect-exp');
            const itemsInput = menu.querySelector('#ctx-reflect-items');
            const expGain = Math.max(0, parseInt(expInput?.value, 10) || 0);
            const radianceGain = canReflectRadiance ? Number(menu.querySelector('#ctx-reflect-radiance')?.value || 0) : 0;
            if (!Number.isInteger(radianceGain) || radianceGain < 0) {
                if (typeof logToBattleLog === 'function') {
                    logToBattleLog({ type: 'info', message: '獲得通過点は0以上の整数で入力してください。', timestamp: Date.now() });
                }
                return;
            }
            const items = {};
            (itemsInput?.value || '').split(',').forEach((entry) => {
                const [rawId, rawQty] = entry.split(':').map((s) => (s || '').trim());
                const qty = parseInt(rawQty, 10) || 0;
                if (rawId && qty > 0) items[rawId] = qty;
            });
            if (typeof socket.once === 'function') {
                socket.once('reflect_session_results_result', (result) => {
                    if (!result || !result.skipped) return;
                    // 成功時は既にサーバー側のbroadcast_logで通知済みなので、スキップ時のみここで案内する。
                    const reasonMsg = {
                        forbidden: 'この操作を行う権限がありません。',
                        not_owned_character: 'このキャラは持ちキャラ由来ではないため反映できません。',
                        already_reflected: 'このセッションの成果は既に反映済みです。',
                        char_not_found: 'キャラクターが見つかりませんでした。',
                        owned_character_not_found: '持ちキャラが見つかりませんでした。',
                        invalid_radiance_gain: '獲得通過点は0以上の整数で入力してください。',
                        hollow_automatic: 'ホロウの成果は遠征終了時に自動で反映されます。',
                    }[result.reason] || '成果を反映できませんでした。';
                    if (typeof logToBattleLog === 'function') {
                        logToBattleLog({ type: 'info', message: reasonMsg, timestamp: Date.now() });
                    }
                });
            }
            socket.emit('request_reflect_session_results', {
                room: currentRoomName, char_id: char.id, exp_gain: expGain, items,
                ...(canReflectRadiance ? { radiance_gain: radianceGain } : {})
            });
            closeMenu();
        });
    }

    // Delete
    const delBtn = menu.querySelector('#ctx-delete-btn');
    delBtn.addEventListener('click', async () => {
        if (await window.showAppConfirm('完全に削除しますか？', {
            defaultFocus: 'cancel',
            title: 'キャラクター削除',
            confirmText: '削除',
        })) {
            socket.emit('request_delete_character', { room: currentRoomName, charId: char.id });
            const modal = document.getElementById('char-modal-backdrop');
            if (modal) modal.remove();
            closeMenu();
        }
    });

    // GM Only
    const gmToggle = menu.querySelector('#ctx-gm-only');
    if (gmToggle) {
        gmToggle.addEventListener('change', (e) => {
            socket.emit('request_state_update', {
                room: currentRoomName, charId: char.id, statName: 'gmOnly', newValue: e.target.checked
            });
        });
    }

    // Show Planned Skill Toggle (For AI)
    const planToggle = menu.querySelector('#ctx-show-planned');
    if (planToggle) {
        planToggle.addEventListener('change', (e) => {
            const targetChar = window.getLatestCharacterForBehaviorEditor(char.id) || char;
            const currentFlags = (targetChar.flags && typeof targetChar.flags === 'object') ? targetChar.flags : {};
            const newFlags = Object.assign({}, currentFlags, { show_planned_skill: e.target.checked });
            targetChar.flags = newFlags;
            char.flags = newFlags;
            socket.emit('request_state_update', {
                room: currentRoomName, charId: char.id, statName: 'flags', newValue: newFlags
            });
        });
    }

    const behaviorToggle = menu.querySelector('#ctx-behavior-enabled');
    if (behaviorToggle) {
        behaviorToggle.addEventListener('change', (e) => {
            const targetChar = window.getLatestCharacterForBehaviorEditor(char.id) || char;
            const currentFlags = (targetChar.flags && typeof targetChar.flags === 'object') ? targetChar.flags : {};
            const currentProfile = (currentFlags.behavior_profile && typeof currentFlags.behavior_profile === 'object')
                ? currentFlags.behavior_profile
                : {
                    version: 1,
                    slot_generation_mode: 'step_actions',
                    initial_loop_id: null,
                    loops: {}
                };
            const nextProfile = Object.assign({}, currentProfile, { enabled: !!e.target.checked });
            const newFlags = Object.assign({}, currentFlags, { behavior_profile: nextProfile });
            targetChar.flags = newFlags;
            char.flags = newFlags;
            socket.emit('request_state_update', {
                room: currentRoomName, charId: char.id, statName: 'flags', newValue: newFlags
            });
        });
    }

    const behaviorEditBtn = menu.querySelector('#ctx-behavior-edit-btn');
    if (behaviorEditBtn) {
        behaviorEditBtn.addEventListener('click', () => {
            const targetChar = window.getLatestCharacterForBehaviorEditor(char.id) || char;
            window.openBehaviorFlowEditorModal(targetChar);
            closeMenu();
        });
    }
}

window.refreshHollowTokenControls = function () {
    const menu = document.getElementById('char-settings-context-menu');
    if (!menu) return;
    const disabled = !window.HollowParty.canControlCharacter(menu.dataset.characterId);
    menu.querySelectorAll('#ctx-scale-slider, #ctx-return-btn, #ctx-delete-btn').forEach(control => {
        control.disabled = disabled;
    });
};

// Helper to close modal by ID (if not exists in global scope, defined here just in case)
function closeGameModal(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}


function openSkillDetailModal(skillId, skillName, options = {}) {
    // スキルデータを取得
    const skillData = (window.allSkillData && window.allSkillData[skillId]) ? window.allSkillData[skillId] : null;
    const granted = (options && typeof options === 'object' && options.granted && typeof options.granted === 'object')
        ? options.granted
        : null;
    const ownerCharId = (options && typeof options === 'object' && options.ownerCharId != null)
        ? String(options.ownerCharId || '').trim()
        : '';
    const isGranted = !!granted;

    // 既存のスキル詳細モーダルがあれば削除
    const existing = document.getElementById('skill-detail-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'skill-detail-modal-backdrop';
    overlay.className = 'modal-backdrop book-modal-backdrop';

    const content = document.createElement('div');
    content.className = 'modal-content book-skill-detail-modal';
    if (ownerCharId) {
        content.setAttribute('data-owner-char-id', ownerCharId);
    }
    content.style.maxWidth = '680px';
    content.style.padding = '20px';
    if (isGranted) {
        content.style.borderColor = '#dfb33f';
        content.style.boxShadow = '0 18px 45px rgba(120, 88, 22, 0.40)';
    }

    let grantInfoHtml = '';
    if (isGranted) {
        const mode = String(granted.mode || '').toLowerCase();
        const rounds = parseInt(granted.remaining_rounds, 10);
        const uses = parseInt(granted.remaining_uses, 10);
        let statusHtml = '<span style="background:#ffe08a; color:#5a4300; border:1px solid #f3c34a; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em;">付与スキル</span>';
        if (mode === 'permanent') {
            statusHtml += '<span style="background:#f6f6f6; color:#555; border:1px solid #ddd; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em; margin-left:6px;">永続</span>';
        }
        if (Number.isFinite(rounds) && rounds > 0) {
            statusHtml += `<span style="background:#fff3bf; color:#5a4300; border:1px solid #f3c34a; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em; margin-left:6px;">残り${rounds}R</span>`;
        }
        if (Number.isFinite(uses) && uses >= 0) {
            statusHtml += `<span style="background:#fff3bf; color:#5a4300; border:1px solid #f3c34a; border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.82em; margin-left:6px;">残り${uses}回</span>`;
        }
        grantInfoHtml = `
            <div style="margin: 0 0 10px 0; padding: 8px 10px; border: 1px solid #f3c34a; border-radius: 8px; background: #fff8dc;">
                ${statusHtml}
            </div>
        `;
    }

    let bodyHtml = '';
    if (skillData) {
        bodyHtml = `
            <div class="book-skill-meta">
                <span class="book-skill-id">[${skillId}]</span>
                <span class="book-skill-category">${skillData['分類'] || '---'}</span>
            </div>
            ${grantInfoHtml}
            <div class="skill-detail-body book-reading-body">
                ${formatSkillDetailHTML(skillData)}
            </div>
        `;
    } else {
        bodyHtml = `<p class="book-reading-body">スキルデータが見つかりません: ${skillId}</p>`;
    }

    content.innerHTML = `
        <div class="book-modal-header">
            <h3 class="book-modal-title" style="${isGranted ? 'color:#7a5a16;' : ''}">${skillName ? `${skillName} [${skillId}]` : skillId}</h3>
            <button class="modal-close-btn book-modal-close" aria-label="閉じる">×</button>
        </div>
        ${bodyHtml}
    `;

    overlay.appendChild(content);
    document.body.appendChild(overlay);

    const closeFunc = () => overlay.remove();
    window.attachEncyclopediaLink?.(content, skillId, closeFunc);
    content.querySelector('.modal-close-btn').addEventListener('click', closeFunc);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeFunc();
    });
}

// 互換性のためのエイリアス
// 過去のコードが renderBeautifulCharacterCard を呼んでいても、統合版が動くようにする
function renderBeautifulCharacterCard(char) {
    return renderCharacterCard(char);
}
// V2も同様
function renderBeautifulCharacterCardV2(char) {
    return renderCharacterCard(char);
}

function openCharLoadModal() {
    closeCharacterModal();

    const modalHtml = `
        <div class="modal-backdrop" id="char-load-modal-backdrop">
            <div class="modal-content char-load-modal-content">
                <div class="char-load-modal">
                    <button class="modal-close-btn" type="button" aria-label="閉じる">×</button>
                    <div id="char-load-modal-body"></div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const panel = document.querySelector('#char-load-modal-backdrop > .modal-content');
    applySystemWindow(panel);
    const backdrop = document.getElementById('char-load-modal-backdrop');
    const body = document.getElementById('char-load-modal-body');
    const isGMUser = (typeof currentUserAttribute !== 'undefined' && currentUserAttribute === 'GM');

    backdrop.querySelector('.modal-close-btn').addEventListener('click', () => backdrop.remove());
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
            backdrop.remove();
        }
    });

    const sideLabel = (type) => (type === 'ally' ? '味方' : '敵');
    const sideClass = (type) => (type === 'ally' ? 'ally' : 'enemy');

    const renderChoiceStep = () => {
        body.innerHTML = `
            <h2>キャラクターを追加</h2>
            <p class="char-load-lead">追加先を選んでください。次の画面でJSONの貼り付け、またはローカルJSONファイルから読み込めます。</p>
            <div class="char-load-choice-grid">
                <button id="char-load-choice-ally" type="button" class="char-load-choice-card ally">
                    <span class="char-load-choice-title">味方を追加</span>
                    <span class="char-load-choice-desc">プレイヤー側・同行NPCなどを追加します。</span>
                </button>
                <button id="char-load-choice-enemy" type="button" class="char-load-choice-card enemy">
                    <span class="char-load-choice-title">敵を追加</span>
                    <span class="char-load-choice-desc">敵、障害物、対戦相手などを追加します。</span>
                </button>
            </div>
        `;
        if (panel.dataset.theme === 'marble') addSystemWindowHeadingMark(body.querySelector('h2'));
        body.querySelector('#char-load-choice-ally')?.addEventListener('click', () => renderJsonStep('ally'));
        body.querySelector('#char-load-choice-enemy')?.addEventListener('click', () => renderJsonStep('enemy'));
    };

    const renderJsonStep = (type) => {
        const label = sideLabel(type);
        const klass = sideClass(type);
        const debugHtml = isGMUser ? `
            <div class="char-load-debug-panel ${klass}">
                <div>
                    <div class="char-load-debug-title">GM専用: デバッグ${label}生成</div>
                    <div class="char-load-debug-desc">全スキル、HP999、MP/FP1000の検証用キャラクターを生成します。</div>
                </div>
                <div class="char-load-debug-controls">
                    <label for="modal-debug-count">追加人数</label>
                    <select id="modal-debug-count">
                        <option value="1">1体</option>
                        <option value="2">2体</option>
                        <option value="3">3体</option>
                        <option value="4">4体</option>
                        <option value="5">5体</option>
                    </select>
                    <button id="modal-debug-generate-btn" type="button" class="room-action-btn ${klass === 'enemy' ? 'danger' : ''}">
                        デバッグ${label}を生成
                    </button>
                </div>
            </div>
        ` : '';

        body.innerHTML = `
            <div class="char-load-step-header">
                <button id="char-load-back-btn" type="button" class="char-load-back-btn">← 追加先を選び直す</button>
                <span class="char-load-side-badge ${klass}">${label}</span>
            </div>
            <h2>${label}キャラクターJSONの読み込み</h2>
            <p class="char-load-lead">スプレッドシート等で生成したJSONを貼り付けるか、ローカルのJSONファイルから読み込んでください。</p>
            <div class="char-load-file-row">
                <button id="modal-char-json-file-btn" type="button" class="room-action-btn char-load-file-btn">ファイルから読み込み</button>
                <span id="modal-char-json-file-name" class="char-load-file-name">ファイル未選択</span>
                <input id="modal-char-json-file-input" type="file" accept=".json,application/json" style="display:none;">
            </div>
            <textarea id="modal-char-json-input" placeholder='{"kind":"character","data":{...}}'></textarea>
            <div class="char-load-buttons">
                <button id="modal-load-character-btn" type="button" class="${klass}">${label}として追加</button>
            </div>
            <p id="modal-load-result-msg" class="char-load-result-msg"></p>

            <div class="char-load-divider"><span>または</span></div>

            <div class="char-load-owned-section">
                <div class="char-load-owned-label">📋 保存済みの持ちキャラから選ぶ</div>
                <div class="char-load-owned-row">
                    <select id="modal-owned-char-select">
                        <option value="">持ちキャラを読み込み中...</option>
                    </select>
                    <button id="modal-owned-char-add-btn" type="button" class="room-action-btn char-load-owned-btn">追加</button>
                </div>
            </div>
            ${debugHtml}
        `;

        if (panel.dataset.theme === 'marble') addSystemWindowHeadingMark(body.querySelector('h2'));
        const jsonInput = body.querySelector('#modal-char-json-input');
        const resultMsg = body.querySelector('#modal-load-result-msg');
        const fileInput = body.querySelector('#modal-char-json-file-input');
        const fileBtn = body.querySelector('#modal-char-json-file-btn');
        const fileName = body.querySelector('#modal-char-json-file-name');

        body.querySelector('#char-load-back-btn')?.addEventListener('click', renderChoiceStep);
        body.querySelector('#modal-load-character-btn')?.addEventListener('click', () => {
            if (loadCharacterFromJSON(type, jsonInput.value, resultMsg)) {
                jsonInput.value = '';
                setTimeout(() => backdrop.remove(), 1000);
            }
        });

        // 計画36 Phase 3: 持ちキャラから選んで投入するタブ。
        const ownedSelect = body.querySelector('#modal-owned-char-select');
        const ownedAddBtn = body.querySelector('#modal-owned-char-add-btn');
        let ownedCharactersCache = [];
        (async () => {
            try {
                const fetcher = (typeof fetchWithSession === 'function') ? fetchWithSession : fetch;
                const resp = await fetcher('/api/owned_characters');
                if (!resp.ok) throw new Error('取得に失敗しました');
                const body2 = await resp.json();
                ownedCharactersCache = Array.isArray(body2.characters) ? body2.characters : [];
                if (!ownedCharactersCache.length) {
                    ownedSelect.innerHTML = '<option value="">持ちキャラはまだありません</option>';
                    ownedAddBtn.disabled = true;
                    return;
                }
                ownedSelect.innerHTML = '<option value="">-- 持ちキャラを選択 --</option>' + ownedCharactersCache
                    .map((c) => `<option value="${c.id}">${c.name}</option>`)
                    .join('');
            } catch (err) {
                ownedSelect.innerHTML = '<option value="">読み込みに失敗しました</option>';
                ownedAddBtn.disabled = true;
            }
        })();

        ownedAddBtn?.addEventListener('click', () => {
            const id = ownedSelect.value;
            const character = ownedCharactersCache.find((c) => c.id === id);
            if (!character) {
                resultMsg.textContent = '持ちキャラを選択してください。';
                resultMsg.style.color = 'red';
                return;
            }
            const jsonString = JSON.stringify({ kind: 'character', data: character.data });
            if (loadCharacterFromJSON(type, jsonString, resultMsg, { ownedCharacterId: character.id })) {
                setTimeout(() => backdrop.remove(), 1000);
            }
        });

        fileBtn?.addEventListener('click', () => {
            if (!fileInput) return;
            fileInput.value = '';
            fileInput.click();
        });

        fileInput?.addEventListener('change', () => {
            const file = fileInput.files && fileInput.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                jsonInput.value = String(reader.result || '');
                fileName.textContent = file.name;
                resultMsg.textContent = 'JSONファイルを読み込みました。内容を確認して追加してください。';
                resultMsg.style.color = 'green';
            };
            reader.onerror = () => {
                resultMsg.textContent = 'ファイルの読み込みに失敗しました。';
                resultMsg.style.color = 'red';
            };
            reader.readAsText(file, 'utf-8');
        });

        body.querySelector('#modal-debug-generate-btn')?.addEventListener('click', () => {
            const countEl = body.querySelector('#modal-debug-count');
            const count = Number.parseInt(countEl ? countEl.value : '1', 10) || 1;
            socket.emit('request_add_debug_character', {
                room: currentRoomName,
                type,
                count
            });
            resultMsg.textContent = `デバッグキャラ(${label}) ${count}体の生成をリクエストしました...`;
            resultMsg.style.color = (type === 'ally') ? 'blue' : 'red';
            setTimeout(() => backdrop.remove(), 1000);
        });
    };

    renderChoiceStep();
}

function openResetTypeModal(callback) {
    const existing = document.getElementById('reset-type-modal-backdrop');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'reset-type-modal-backdrop';
    overlay.className = 'modal-backdrop';

    overlay.innerHTML = `
        <div class="modal-content" style="width: 450px; padding: 25px;">
            <h3 style="margin-top: 0; color: var(--ui-danger); border-bottom: 2px solid var(--ui-line); padding-bottom: 10px;">
                戦闘リセット設定
            </h3>

            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 10px 0; color: var(--ui-text);">ステータスリセットの対象</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; background: var(--ui-soft); padding: 15px; border-radius: 4px; border: 1px solid var(--ui-line);">
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-hp" checked> <span style="margin-left: 5px;">HP全快</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-mp" checked> <span style="margin-left: 5px;">MP全快</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-fp" checked> <span style="margin-left: 5px;">FP/蓄積値リセット</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center;">
                        <input type="checkbox" id="reset-opt-bad" checked> <span style="margin-left: 5px;">状態異常解除</span>
                    </label>
                    <label style="cursor: pointer; display: flex; align-items: center; grid-column: span 2;">
                        <input type="checkbox" id="reset-opt-buffs" checked> <span style="margin-left: 5px;">バフ・特殊状態リセット</span>
                    </label>
                </div>
                <div style="font-size: 0.85em; color: var(--ui-sub); margin-top: 5px;">
                    ※「バフリセット」は初期所持バフ（パッシブ由来など）を除き削除します。
                </div>
            </div>

            <div style="display: flex; flex-direction: column; gap: 10px;">
                <button id="reset-status-exec-btn" class="btn-set is-danger">
                    上記の内容でステータスのみリセット
                </button>

                <button id="reset-logs-exec-btn" class="btn-set is-danger">
                    ログのみリセット
                </button>

                <hr style="width: 100%; border: 0; border-top: 1px solid #ddd; margin: 15px 0;">

                <button id="reset-full-exec-btn" class="btn-set is-danger">
                    ⚠️ 完全リセット (全キャラ削除・初期化)
                </button>
            </div>

            <div style="margin-top: 20px; text-align: right;">
                <button id="reset-cancel-btn" class="btn-set">キャンセル</button>
            </div>
        </div>
    `;

    applySystemWindow(overlay.querySelector('.modal-content'));
    document.body.appendChild(overlay);

    const closeFunc = () => overlay.remove();
    document.getElementById('reset-cancel-btn').onclick = closeFunc;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeFunc();
    });

    // ステータスリセット実行
    document.getElementById('reset-status-exec-btn').onclick = async () => {
        const options = {
            hp: document.getElementById('reset-opt-hp').checked,
            mp: document.getElementById('reset-opt-mp').checked,
            fp: document.getElementById('reset-opt-fp').checked,
            states: document.getElementById('reset-opt-fp').checked, // 蓄積値はFPと一緒に扱う簡易実装
            bad_states: document.getElementById('reset-opt-bad').checked,
            buffs: document.getElementById('reset-opt-buffs').checked,
            timeline: true // ステータスリセット時にタイムラインもクリア
        };

        if (await window.showAppConfirm('選択した内容でステータスをリセットしますか？', {
            defaultFocus: 'cancel',
            title: 'ステータスリセット',
            confirmText: 'リセット',
        })) {
            callback('status', options);
            closeFunc();
        }
    };

    // ログのみリセット実行
    document.getElementById('reset-logs-exec-btn').onclick = async () => {
        if (await window.showAppConfirm('ログだけを削除しますか？', {
            defaultFocus: 'cancel',
            title: 'ログ削除',
            confirmText: '削除',
        })) {
            callback('logs', null);
            closeFunc();
        }
    };

    // 完全リセット実行
    document.getElementById('reset-full-exec-btn').onclick = async () => {
        if (await window.showAppConfirm('本当にキャラクターを全員削除し、戦闘を初期化しますか？\nこの操作は取り消せません。', {
            defaultFocus: 'cancel',
            title: '完全リセット',
            confirmText: '完全リセット',
        })) {
            callback('full', null); // オプションなし=デフォルト
            closeFunc();
        }
    };
}

// Global Alias for Character Detail Modal (Used by Battle/Exploration views)
window.showCharacterDetail = openCharacterModal;
window.openSkillDetailModal = openSkillDetailModal;
