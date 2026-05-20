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
        container.innerHTML = `<p style="color:red;">エラー: ${e.message}</p>`;
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
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.innerHTML = `
        <tr style="background:#f8f8f8; text-align:left;">
            <th style="padding:10px;">名前 (クリックで詳細)</th>
            <th style="padding:10px;">ID (UUID)</th>
            <th style="padding:10px;">最終ログイン</th>
            <th style="padding:10px;">操作</th>
        </tr>
    `;

    users.forEach(u => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = '1px solid #eee';

        const isMe = (u.id === currentUserId);
        const nameStyle = isMe ? 'font-weight:bold; color:#007bff;' : 'color:#0056b3;';
        const meLabel = isMe ? ' (あなた)' : '';
        const adminLabel = u.is_app_admin ? '<span style="color:#6f42c1; font-weight:bold;"> 管理者</span>' : '';
        const toggleAdminText = u.is_app_admin ? '管理権限解除' : '管理権限付与';
        const actionHtml = `
            <button class="transfer-btn" data-id="${escapeUserManagementText(u.id)}" data-name="${escapeUserManagementText(u.name)}">${currentUserCanManageUsers ? '権限譲渡' : '譲渡(キー)'}</button>
            <button class="toggle-admin-btn" data-id="${escapeUserManagementText(u.id)}" data-enabled="${u.is_app_admin ? '0' : '1'}">${toggleAdminText}</button>
            <button class="delete-user-btn" data-id="${escapeUserManagementText(u.id)}" style="background:#dc3545; color:white; border:none; border-radius:3px; padding:4px 8px; margin-left:5px;">${currentUserCanManageUsers ? '削除' : '削除(キー)'}</button>
        `;

        tr.innerHTML = `
            <td style="padding:10px;">
                <span class="user-name-link" data-id="${escapeUserManagementText(u.id)}" style="cursor:pointer; text-decoration:underline; ${nameStyle}">
                    ${escapeUserManagementText(u.name)}${meLabel}${adminLabel}
                </span>
            </td>
            <td style="padding:10px; font-family:monospace; font-size:0.9em; color:#666;">${escapeUserManagementText(u.id)}</td>
            <td style="padding:10px; font-size:0.9em;">${escapeUserManagementText(u.last_login)}</td>
            <td style="padding:10px;">
                ${actionHtml}
            </td>
        `;
        table.appendChild(tr);
    });

    container.appendChild(table);

    // イベント設定
    container.querySelectorAll('.user-name-link').forEach(span => {
        span.onclick = () => showUserDetails(span.dataset.id, span.textContent.trim());
    });

    container.querySelectorAll('.delete-user-btn').forEach(btn => {
        btn.onclick = () => deleteUser(btn.dataset.id);
    });

    container.querySelectorAll('.transfer-btn').forEach(btn => {
        btn.onclick = () => openTransferModal(btn.dataset.id, btn.dataset.name);
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

        let roomsHtml = data.rooms.length ? data.rooms.map(r => `<li>${escapeUserManagementText(r.name)}</li>`).join('') : '<li style="color:#999;">なし</li>';
        let charsHtml = data.characters.length ? data.characters.map(c => `<li>${escapeUserManagementText(c.name)} <span style="font-size:0.8em; color:#666;">(in ${escapeUserManagementText(c.room)})</span></li>`).join('') : '<li style="color:#999;">なし</li>';

        overlay.innerHTML = `
            <div class="modal-content" style="width: 500px; padding: 20px;">
                <h3 style="margin-top:0;">${escapeUserManagementText(userName)} の詳細</h3>

                <h4 style="margin-bottom:5px;">所有ルーム</h4>
                <ul style="max-height:150px; overflow-y:auto; border:1px solid #eee; padding:10px 20px; margin-top:0;">
                    ${roomsHtml}
                </ul>

                <h4 style="margin-bottom:5px;">所有キャラクター</h4>
                <ul style="max-height:150px; overflow-y:auto; border:1px solid #eee; padding:10px 20px; margin-top:0;">
                    ${charsHtml}
                </ul>

                <div style="text-align:right; margin-top:20px;">
                    <button id="close-user-details" style="padding:5px 15px;">閉じる</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        document.getElementById('close-user-details').onclick = () => overlay.remove();

    } catch (e) {
        alert(e.message);
    }
}
// ▲▲▲ 追加ここまで ▲▲▲

async function deleteUser(userId) {
    if (!await window.showAppConfirm('このユーザーを削除しますか？\n所有していたルームやキャラの所有権は「空」になります。', {
        title: 'ユーザー削除',
        confirmText: '削除',
    })) return;

    let masterKey = '';
    if (!currentUserCanManageUsers) {
        masterKey = await requestMasterKey('ユーザー削除にはマスターキーが必要です。');
        if (!/^\d{8}$/.test(String(masterKey || '').trim())) {
            alert('マスターキーは8桁の数字で入力してください。');
            return;
        }
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
        alert('削除失敗: ' + e.message);
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
        title: '所有権移動の確認',
        confirmText: '譲渡',
    })) return;

    let masterKey = '';
    if (!currentUserCanManageUsers) {
        masterKey = await requestMasterKey('所有権譲渡にはマスターキーが必要です。');
        if (!/^\d{8}$/.test(String(masterKey || '').trim())) {
            alert('マスターキーは8桁の数字で入力してください。');
            return;
        }
    }

    fetchWithSession('/api/admin/transfer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ old_id: fromId, new_id: toId, master_key: String(masterKey || '').trim() })
    }).then(res => res.json())
      .then(data => {
          if (data.error) throw new Error(data.error);
          alert(data.message);
          loadUserList();
      })
      .catch(e => alert('譲渡失敗: ' + e.message));
}

async function toggleUserManagementAdmin(userId, enabled) {
    const masterKey = await requestMasterKey(enabled
        ? 'このユーザーへユーザー管理権限を付与します。マスターキーを入力してください。'
        : 'このユーザーのユーザー管理権限を解除します。マスターキーを入力してください。'
    );
    if (!/^\d{8}$/.test(String(masterKey || '').trim())) {
        alert('マスターキーは8桁の数字で入力してください。');
        return;
    }

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
        alert('管理権限の更新失敗: ' + e.message);
    }
}

document.getElementById('back-to-room-portal-btn').addEventListener('click', () => {
    document.getElementById('user-management-portal').style.display = 'none';
    document.getElementById('room-portal').style.display = 'block';
});
