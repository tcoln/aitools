async function loadUsers() {
    try {
        const users = await api.users.list();
        const tbody = document.getElementById('users-table-body');
        tbody.innerHTML = users.map(u => `
            <tr>
                <td>${escapeHtml(u.username)}</td>
                <td>${escapeHtml(u.display_name || '-')}</td>
                <td>${escapeHtml(u.email || '-')}</td>
                <td><span class="badge ${u.is_admin ? 'badge-admin' : ''}">${u.is_admin ? '管理员' : '用户'}</span></td>
                <td><span style="color:${u.is_active ? 'var(--success)' : 'var(--danger)'}">${u.is_active ? '启用' : '禁用'}</span></td>
                <td>${new Date(u.created_at).toLocaleString('zh-CN')}</td>
                <td>
                    <button class="btn-primary btn-sm btn-edit-user" data-id="${u.id}">编辑</button>
                    <button class="btn-danger btn-sm btn-delete-user" data-id="${u.id}">删除</button>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.btn-edit-user').forEach(btn => {
            btn.addEventListener('click', () => openEditUserModal(btn.dataset.id));
        });
        tbody.querySelectorAll('.btn-delete-user').forEach(btn => {
            btn.addEventListener('click', () => deleteUser(btn.dataset.id));
        });
    } catch (e) {
        alert('加载用户列表失败: ' + e.message);
    }
}

async function openEditUserModal(userId) {
    try {
        const user = await api.users.get(userId);
        document.getElementById('edit-user-id').value = user.id;
        document.getElementById('edit-display-name').value = user.display_name || '';
        document.getElementById('edit-email').value = user.email || '';
        document.getElementById('edit-password').value = '';
        document.getElementById('edit-is-admin').checked = user.is_admin;
        document.getElementById('edit-is-active').checked = user.is_active;
        document.getElementById('user-edit-modal').style.display = 'flex';
    } catch (e) {
        alert('获取用户信息失败: ' + e.message);
    }
}

async function saveUserEdit(e) {
    e.preventDefault();
    const userId = document.getElementById('edit-user-id').value;
    const data = {
        display_name: document.getElementById('edit-display-name').value || null,
        email: document.getElementById('edit-email').value || null,
        is_admin: document.getElementById('edit-is-admin').checked,
        is_active: document.getElementById('edit-is-active').checked,
    };
    const password = document.getElementById('edit-password').value;
    if (password) data.password = password;

    try {
        await api.users.update(userId, data);
        document.getElementById('user-edit-modal').style.display = 'none';
        loadUsers();
    } catch (e) {
        alert('更新用户失败: ' + e.message);
    }
}

async function deleteUser(userId) {
    if (!confirm('确定删除此用户？')) return;
    try {
        await api.users.delete(userId);
        loadUsers();
    } catch (e) {
        alert('删除用户失败: ' + e.message);
    }
}

function initUsers() {
    document.getElementById('user-edit-form').addEventListener('submit', saveUserEdit);
    document.getElementById('user-edit-modal').querySelector('.modal-close').addEventListener('click', () => {
        document.getElementById('user-edit-modal').style.display = 'none';
    });
    document.getElementById('user-edit-modal').addEventListener('click', (e) => {
        if (e.target === document.getElementById('user-edit-modal')) {
            document.getElementById('user-edit-modal').style.display = 'none';
        }
    });
}