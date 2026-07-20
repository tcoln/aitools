async function loadMCPServices() {
    try {
        const services = await api.mcp.list();
        const list = document.getElementById('mcp-service-list');
        list.innerHTML = services.map(s => `
            <div class="mcp-card">
                <div class="mcp-card-header">
                    <span class="mcp-card-name">${escapeHtml(s.name)}</span>
                    <div>
                        <span class="mcp-card-badge ${s.transport_type}">${s.transport_type}</span>
                        <span class="mcp-card-badge ${s.is_active ? 'active' : 'inactive'}">${s.is_active ? '启用' : '禁用'}</span>
                    </div>
                </div>
                <div class="mcp-card-desc">${escapeHtml(s.description || '无描述')}</div>
                ${s.transport_type === 'stdio' ? `
                    <div class="mcp-card-detail">命令: ${escapeHtml(s.command || '-')}</div>
                    <div class="mcp-card-detail">参数: ${escapeHtml(s.args || '-')}</div>
                ` : `
                    <div class="mcp-card-detail">URL: ${escapeHtml(s.url || '-')}</div>
                `}
                <div class="mcp-card-actions">
                    <button class="btn-primary btn-sm btn-edit-mcp" data-id="${s.id}">编辑</button>
                    <button class="btn-secondary btn-sm btn-test-mcp" data-id="${s.id}">测试连接</button>
                    <button class="btn-danger btn-sm btn-delete-mcp" data-id="${s.id}">删除</button>
                </div>
            </div>
        `).join('');

        list.querySelectorAll('.btn-edit-mcp').forEach(btn => {
            btn.addEventListener('click', () => openEditMCPModal(btn.dataset.id));
        });
        list.querySelectorAll('.btn-test-mcp').forEach(btn => {
            btn.addEventListener('click', () => testMCPConnection(btn.dataset.id));
        });
        list.querySelectorAll('.btn-delete-mcp').forEach(btn => {
            btn.addEventListener('click', () => deleteMCPService(btn.dataset.id));
        });
    } catch (e) {
        alert('加载MCP服务列表失败: ' + e.message);
    }
}

function openAddMCPModal() {
    document.getElementById('mcp-modal-title').textContent = '添加MCP服务';
    document.getElementById('edit-mcp-id').value = '';
    document.getElementById('edit-mcp-name').value = '';
    document.getElementById('edit-mcp-description').value = '';
    document.getElementById('edit-mcp-transport').value = 'stdio';
    document.getElementById('edit-mcp-command').value = '';
    document.getElementById('edit-mcp-args').value = '';
    document.getElementById('edit-mcp-env-vars').value = '';
    document.getElementById('edit-mcp-url').value = '';
    document.getElementById('edit-mcp-headers').value = '';
    document.getElementById('edit-mcp-is-active').checked = true;
    toggleMCPTransportFields();
    document.getElementById('mcp-edit-modal').style.display = 'flex';
}

async function openEditMCPModal(serviceId) {
    try {
        const service = await api.mcp.get(serviceId);
        document.getElementById('mcp-modal-title').textContent = '编辑MCP服务';
        document.getElementById('edit-mcp-id').value = service.id;
        document.getElementById('edit-mcp-name').value = service.name;
        document.getElementById('edit-mcp-description').value = service.description || '';
        document.getElementById('edit-mcp-transport').value = service.transport_type;
        document.getElementById('edit-mcp-command').value = service.command || '';
        document.getElementById('edit-mcp-args').value = service.args || '';
        document.getElementById('edit-mcp-env-vars').value = service.env_vars || '';
        document.getElementById('edit-mcp-url').value = service.url || '';
        document.getElementById('edit-mcp-headers').value = service.headers || '';
        document.getElementById('edit-mcp-is-active').checked = service.is_active;
        toggleMCPTransportFields();
        document.getElementById('mcp-edit-modal').style.display = 'flex';
    } catch (e) {
        alert('获取MCP服务信息失败: ' + e.message);
    }
}

async function saveMCPEdit(e) {
    e.preventDefault();
    const serviceId = document.getElementById('edit-mcp-id').value;
    const data = {
        name: document.getElementById('edit-mcp-name').value,
        description: document.getElementById('edit-mcp-description').value || null,
        transport_type: document.getElementById('edit-mcp-transport').value,
        command: document.getElementById('edit-mcp-command').value || null,
        args: document.getElementById('edit-mcp-args').value || null,
        env_vars: document.getElementById('edit-mcp-env-vars').value || null,
        url: document.getElementById('edit-mcp-url').value || null,
        headers: document.getElementById('edit-mcp-headers').value || null,
        is_active: document.getElementById('edit-mcp-is-active').checked,
    };

    try {
        if (serviceId) {
            await api.mcp.update(serviceId, data);
        } else {
            await api.mcp.create(data);
        }
        document.getElementById('mcp-edit-modal').style.display = 'none';
        loadMCPServices();
    } catch (e) {
        alert('保存MCP服务失败: ' + e.message);
    }
}

async function deleteMCPService(serviceId) {
    if (!confirm('确定删除此MCP服务？')) return;
    try {
        await api.mcp.delete(serviceId);
        loadMCPServices();
    } catch (e) {
        alert('删除MCP服务失败: ' + e.message);
    }
}

async function testMCPConnection(serviceId) {
    const btn = document.querySelector(`.btn-test-mcp[data-id="${serviceId}"]`);
    const originalText = btn.textContent;
    btn.textContent = '测试中...';
    btn.disabled = true;
    try {
        const result = await api.mcp.test(serviceId);
        if (result.success) {
            alert(`连接成功！发现 ${result.tool_count} 个工具:\n${result.tools.map(t => `- ${t.name}: ${t.description}`).join('\n')}`);
        } else {
            alert('连接失败: ' + result.error);
        }
    } catch (e) {
        alert('测试失败: ' + e.message);
    }
    btn.textContent = originalText;
    btn.disabled = false;
}

function toggleMCPTransportFields() {
    const transport = document.getElementById('edit-mcp-transport').value;
    document.getElementById('mcp-stdio-fields').style.display = transport === 'stdio' ? 'block' : 'none';
    document.getElementById('mcp-sse-fields').style.display = transport === 'sse' ? 'block' : 'none';
}

function initMCP() {
    document.getElementById('btn-add-mcp').addEventListener('click', openAddMCPModal);
    document.getElementById('edit-mcp-transport').addEventListener('change', toggleMCPTransportFields);
    document.getElementById('mcp-edit-form').addEventListener('submit', saveMCPEdit);
    document.getElementById('mcp-edit-modal').querySelector('.modal-close').addEventListener('click', () => {
        document.getElementById('mcp-edit-modal').style.display = 'none';
    });
    document.getElementById('mcp-edit-modal').addEventListener('click', (e) => {
        if (e.target === document.getElementById('mcp-edit-modal')) {
            document.getElementById('mcp-edit-modal').style.display = 'none';
        }
    });
}