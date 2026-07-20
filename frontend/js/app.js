let currentUser = null;
let currentModel = '';

const loginPage = document.getElementById('login-page');
const mainPage = document.getElementById('main-page');
const authError = document.getElementById('auth-error');
const currentUsername = document.getElementById('current-username');
const adminBadge = document.getElementById('admin-badge');
const modelSelect = document.getElementById('model-select');

document.addEventListener('DOMContentLoaded', () => {
    initAuth();
    initChat();
    initUsers();
    initMCP();
    initNavigation();

    if (api.token) {
        checkAuth();
    }
});

function initAuth() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const tab = btn.dataset.tab;
            document.getElementById('login-form').classList.toggle('active', tab === 'login');
            document.getElementById('register-form').classList.toggle('active', tab === 'register');
            authError.textContent = '';
        });
    });

    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        authError.textContent = '';
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;
        try {
            const result = await api.auth.login(username, password);
            api.setToken(result.access_token);
            onLoginSuccess(result.user);
        } catch (e) {
            authError.textContent = e.message;
        }
    });

    document.getElementById('register-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        authError.textContent = '';
        const username = document.getElementById('register-username').value.trim();
        const password = document.getElementById('register-password').value;
        const displayName = document.getElementById('register-display-name').value.trim();
        const email = document.getElementById('register-email').value.trim();

        if (!username || !password) {
            authError.textContent = '用户名和密码不能为空';
            return;
        }
        if (username.length < 3) {
            authError.textContent = '用户名至少3个字符';
            return;
        }
        if (password.length < 6) {
            authError.textContent = '密码至少6个字符';
            return;
        }

        try {
            const result = await api.auth.register(username, password, displayName, email);
            api.setToken(result.access_token);
            onLoginSuccess(result.user);
        } catch (e) {
            authError.textContent = e.message;
        }
    });

    document.getElementById('btn-logout').addEventListener('click', () => {
        api.clearToken();
        currentUser = null;
        loginPage.style.display = 'flex';
        mainPage.style.display = 'none';
    });
}

async function checkAuth() {
    try {
        const user = await api.users.me();
        onLoginSuccess(user);
    } catch (e) {
        api.clearToken();
    }
}

function onLoginSuccess(user) {
    currentUser = user;
    currentUsername.textContent = user.display_name || user.username;
    adminBadge.style.display = user.is_admin ? 'inline' : 'none';
    document.getElementById('nav-users').style.display = user.is_admin ? 'block' : 'none';
    document.getElementById('nav-tools').style.display = user.is_admin ? 'block' : 'none';

    loginPage.style.display = 'none';
    mainPage.style.display = 'flex';

    loadModels();
    navigateTo('chat');
    loadConversations();
}

async function loadModels() {
    try {
        const models = await api.chat.getModels();
        modelSelect.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = `${m.name} (${m.provider})`;
            if (m.id === currentModel) opt.selected = true;
            modelSelect.appendChild(opt);
        });
        if (!currentModel && models.length > 0) {
            currentModel = models[0].id;
            modelSelect.value = currentModel;
        }
    } catch (e) {
        modelSelect.innerHTML = '<option value="">加载失败</option>';
    }
    modelSelect.addEventListener('change', () => {
        currentModel = modelSelect.value;
    });
}

function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const page = btn.dataset.page;
            if (page === 'users' && !currentUser?.is_admin) return;
            if (page === 'tools' && !currentUser?.is_admin) return;
            if (page === 'chat' && document.getElementById('page-chat').classList.contains('active')) {
                newChat();
                return;
            }
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.nav-btn[data-page="${page}"]`)?.classList.add('active');

    document.querySelectorAll('.page-content').forEach(p => p.classList.remove('active'));
    const pageEl = document.getElementById(`page-${page}`);
    if (pageEl) pageEl.classList.add('active');

    if (page === 'users') loadUsers();
    if (page === 'tools') loadMCPServices();
    if (page === 'chat') loadConversations();
}