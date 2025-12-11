// static/js/user_management.js

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
        if (!res.ok) throw new Error('権限がありません (GM専用機能です)');

        const users = await res.json();
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

        tr.innerHTML = `
            <td style="padding:10px;">
                <span class="user-name-link" data-id="${u.id}" style="cursor:pointer; text-decoration:underline; ${nameStyle}">
                    ${u.name}${meLabel}
                </span>
            </td>
            <td style="padding:10px; font-family:monospace; font-size:0.9em; color:#666;">${u.id}</td>
            <td style="padding:10px; font-size:0.9em;">${u.last_login}</td>
            <td style="padding:10px;">
                <button class="transfer-btn" data-id="${u.id}" data-name="${u.name}">権限譲渡</button>
                <button class="delete-user-btn" data-id="${u.id}" style="background:#dc3545; color:white; border:none; border-radius:3px; padding:4px 8px; margin-left:5px;">削除</button>
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

        let roomsHtml = data.rooms.length ? data.rooms.map(r => `<li>${r.name}</li>`).join('') : '<li style="color:#999;">なし</li>';
        let charsHtml = data.characters.length ? data.characters.map(c => `<li>${c.name} <span style="font-size:0.8em; color:#666;">(in ${c.room})</span></li>`).join('') : '<li style="color:#999;">なし</li>';

        overlay.innerHTML = `
            <div class="modal-content" style="width: 500px; padding: 20px;">
                <h3 style="margin-top:0;">${userName} の詳細</h3>

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
    if(!confirm('このユーザーを削除しますか？\n所有していたルームやキャラの所有権は「空」になります。')) return;

    try {
        await fetchWithSession('/api/admin/delete_user', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ user_id: userId })
        });
        loadUserList();
    } catch(e) {
        alert('削除失敗: ' + e.message);
    }
}

function openTransferModal(fromId, fromName) {
    const toId = prompt(`「${fromName}」の全所有権(ルーム・キャラ)を移動します。\n\n移動先のユーザーID(UUID)を入力してください:`);
    if (!toId) return;

    if(!confirm(`本当に ${fromName} の全データを ID:${toId} に譲渡しますか？\nこの操作は取り消せません。`)) return;

    fetchWithSession('/api/admin/transfer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ old_id: fromId, new_id: toId })
    }).then(res => res.json())
      .then(data => {
          alert(data.message);
          loadUserList();
      })
      .catch(e => alert('譲渡失敗: ' + e.message));
}

document.getElementById('back-to-room-portal-btn').addEventListener('click', () => {
    document.getElementById('user-management-portal').style.display = 'none';
    document.getElementById('room-portal').style.display = 'block';
});