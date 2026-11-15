// static/js/user_management.js

function escapeUserManagementText(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[ch]));
}

let currentUserCanManageUsers = false;

async function showUserManagement() {
    document.getElementById('room-portal').style.display = 'none';
    document.getElementById('user-management-portal').style.display = 'block';

    await loadUserList();
}

async function loadUserList() {
    const container = document.getElementById('user-list-container');
    container.innerHTML = '<p>読み込み中...</p>';

    try {
        const res = await fetchWithSession('/api/admin/users');
        if (!res.ok) throw new Error('ユーザー一覧の取得に失敗しました');

        const payload = await res.json();
        const users = Array.isArray(payload) ? payload : (payload.users || []);
        currentUserCanManageUsers = !!payload.can_manage_users;
        if (typeof window !== 'undefined') {
            window.currentUserIsAppAdmin = currentUserCanManageUsers;
        }
        renderUserList(users);
    } catch (e) {
        container.innerHTML = `<p class="screen-error">エラー: ${escapeUserManagementText(e.message)}</p>`;
    }
}

function renderUserList(users) {
    const container = document.getElementById('user-list-container');
    container.innerHTML = '';

    if (users.length === 0) {
        container.innerHTML = '<p>ユーザーがいません。</p>';
        return;
    }

    const table = document.createElement('table');
    table.className = 'user-table';
    table.innerHTML = `
        <tr>
            <th>名前（クリックで詳細）</th>
            <th>ID</th>
            <th>最終ログイン</th>
            <th>操作</th>
        </tr>
    `;

    users.forEach(u => {
        const tr = document.createElement('tr');

        const isMe = (u.id === currentUserId);
        const meLabel = isMe ? ' (あなた)' : '';
        const adminLabel = u.is_app_admin ? '<span class="user-badge" data-gem="amethyst">管理者</span>' : '';
        const authorLabel = (u.is_catalog_author || u.is_app_admin) ? '<span class="user-badge" data-gem="emerald">制作者</span>' : '';
        const toggleAdminText = u.is_app_admin ? '管理権限解除' : '管理権限付与';
        const authorAction = u.is_app_admin ? '' : `<button class="toggle-author-btn" data-id="${escapeUserManagementText(u.id)}" data-enabled="${u.is_catalog_author ? '0' : '1'}">${u.is_catalog_author ? '制作者を外す' : '制作者に指名'}</button>`;
        const actionHtml = `
            ${authorAction}
            <button class="transfer-btn" data-id="${escapeUserManagementText(u.id)}" data-name="${escapeUserManagementText(u.name)}">${currentUserCanManageUsers ? '権限譲渡' : '譲渡(キー)'}</button>
            <button class="toggle-admin-btn" data-id="${escapeUserManagementText(u.id)}" data-enabled="${u.is_app_admin ? '0' : '1'}">${toggleAdminText}</button>
            <button class="delete-user-btn is-danger" data-id="${escapeUserManagementText(u.id)}">${currentUserCanManageUsers ? '削除' : '削除(キー)'}</button>
        `;

        tr.innerHTML = `
            <td>
                <span class="user-name-link${isMe ? ' is-me' : ''}" data-id="${escapeUserManagementText(u.id)}">${escapeUserManagementText(u.name)}${meLabel}</span>
                ${adminLabel}${authorLabel}
            </td>
            <td class="user-id">${escapeUserManagementText(u.id)}</td>
            <td class="user-login">${escapeUserManagementText(u.last_login)}</td>
            <td class="user-actions">
                ${actionHtml}
            </td>
        `;
        table.appendChild(tr);
    });

    container.appendChild(table);

    // イベント設定
    container.querySelectorAll('.user-name-link').forEach(span => {
        span.onclick = () => showUserDetails(span.dataset.id, span.textContent.trim());
        span.tabIndex = 0;
        span.setAttribute('role', 'button');
        span.onkeydown = event => { if (event.key === 'Enter') span.onclick(); };
    });

    container.querySelectorAll('.delete-user-btn').forEach(btn => {
        btn.onclick = () => deleteUser(btn.dataset.id);
    });

    container.querySelectorAll('.transfer-btn').forEach(btn => {
        btn.onclick = () => openTransferModal(btn.dataset.id, btn.dataset.name);
    });

    container.querySelectorAll('.toggle-author-btn').forEach(btn => {
        btn.onclick = () => toggleCatalogAuthor(btn.dataset.id, btn.dataset.enabled === '1');
    });

    container.querySelectorAll('.toggle-admin-btn').forEach(btn => {
        btn.onclick = () => toggleUserManagementAdmin(btn.dataset.id, btn.dataset.enabled === '1');
    });
}

async function requestMasterKey(reason) {
    return await window.showAppPrompt(reason || 'マスターキーを入力してください。', {
        title: 'マスターキー認証',
        placeholder: '8桁マスターキー',
        confirmText: '認証',
        required: true,
        validate: value => /^\d{8}$/.test(value) ? '' : 'マスターキーは8桁の数字で入力してください。',
    });
}

// ▼▼▼ 追加: ユーザー詳細表示機能 ▼▼▼
async function showUserDetails(userId, userName) {
    try {
        const res = await fetchWithSession(`/api/admin/user_details?user_id=${userId}`);
        if (!res.ok) throw new Error('詳細情報の取得に失敗しました');
        const data = await res.json();

        // モーダル表示
        const existing = document.getElementById('user-details-modal');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'user-details-modal';
        overlay.className = 'modal-backdrop';
        overlay.dataset.theme = 'paper';

        let roomsHtml = data.rooms.length ? data.rooms.map(r => `<li>${escapeUserManagementText(r.name)}</li>`).join('') : '<li class="user-detail-none">なし</li>';
        let charsHtml = data.characters.length ? data.characters.map(c => `<li>${escapeUserManagementText(c.name)} <span class="user-detail-room">(in ${escapeUserManagementText(c.room)})</span></li>`).join('') : '<li class="user-detail-none">なし</li>';

        overlay.innerHTML = `
            <div class="modal-content paper-dialog user-detail">
                <h3>${escapeUserManagementText(userName)} の詳細</h3>

                <h4>所有ルーム</h4>
                <ul>
                    ${roomsHtml}
                </ul>

                <h4>所有キャラクター</h4>
                <ul>
                    ${charsHtml}
                </ul>

                <div class="paper-dialog__actions">
                    <button id="close-user-details" type="button">閉じる</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        document.getElementById('close-user-details').onclick = () => overlay.remove();

    } catch (e) {
        showAppAlert(e.message, { title: 'エラー' });
    }
}
// ▲▲▲ 追加ここまで ▲▲▲

async function deleteUser(userId) {
    if (!await window.showAppConfirm('このユーザーを削除しますか？\n所有していたルームやキャラの所有権は「空」になります。', {
        defaultFocus: 'cancel',
        title: 'ユーザー削除',
        confirmText: '削除',
    })) return;

    let masterKey = '';
    if (!currentUserCanManageUsers) {
        masterKey = await requestMasterKey('ユーザー削除にはマスターキーが必要です。');
        if (masterKey === null) return;  // キャンセル
    }

    try {
        const res = await fetchWithSession('/api/admin/delete_user', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ user_id: userId, master_key: String(masterKey || '').trim() })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || '削除に失敗しました');
        }
        loadUserList();
    } catch(e) {
        showAppAlert('削除失敗: ' + e.message, { title: 'エラー' });
    }
}

async function openTransferModal(fromId, fromName) {
    const toId = await window.showAppPrompt(`「${fromName}」の全所有権(ルーム・キャラ)を移動します。\n\n移動先のユーザーID(UUID)を入力してください:`, {
        title: '所有権移動',
        placeholder: '移動先ユーザーID(UUID)',
        confirmText: '次へ',
        required: true,
    });
    if (!toId) return;

    if (!await window.showAppConfirm(`本当に ${fromName} の全データを ID:${toId} に譲渡しますか？\nこの操作は取り消せません。`, {
        defaultFocus: 'cancel',
        title: '所有権移動の確認',
        confirmText: '譲渡',
    })) return;

    let masterKey = '';
    if (!currentUserCanManageUsers) {
        masterKey = await requestMasterKey('所有権譲渡にはマスターキーが必要です。');
        if (masterKey === null) return;  // キャンセル
    }

    fetchWithSession('/api/admin/transfer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ old_id: fromId, new_id: toId, master_key: String(masterKey || '').trim() })
    }).then(res => res.json())
      .then(data => {
          if (data.error) throw new Error(data.error);
          showAppAlert(data.message, { title: '所有権移動' });
          loadUserList();
      })
      .catch(e => showAppAlert('譲渡失敗: ' + e.message, { title: 'エラー' }));
}

async function toggleUserManagementAdmin(userId, enabled) {
    const masterKey = await requestMasterKey(enabled
        ? 'このユーザーへユーザー管理権限を付与します。マスターキーを入力してください。'
        : 'このユーザーのユーザー管理権限を解除します。マスターキーを入力してください。'
    );
    if (masterKey === null) return;  // キャンセル

    try {
        const res = await fetchWithSession('/api/admin/set_user_management_admin', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: userId,
                enabled,
                master_key: String(masterKey).trim(),
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '更新に失敗しました');
        loadUserList();
    } catch (e) {
        showAppAlert('管理権限の更新失敗: ' + e.message, { title: 'エラー' });
    }
}



async function toggleCatalogAuthor(userId, enabled) {
  try {
    const response = await fetchWithSession('/api/admin/set_catalog_author', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: userId, enabled}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '更新に失敗しました');
    await loadUserList();
  } catch (error) {
    showAppAlert('制作者の更新失敗: ' + error.message, { title: 'エラー' });
  }
}
