const API_BASE = '/api';

const api = {
    token: localStorage.getItem('token'),

    setToken(token) {
        this.token = token;
        localStorage.setItem('token', token);
    },

    clearToken() {
        this.token = null;
        localStorage.removeItem('token');
    },

    async request(method, path, body = null) {
        const headers = {
            'Content-Type': 'application/json',
        };
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const options = { method, headers };
        if (body) {
            const cleaned = {};
            for (const [key, value] of Object.entries(body)) {
                cleaned[key] = value === '' ? null : value;
            }
            options.body = JSON.stringify(cleaned);
        }

        const response = await fetch(API_BASE + path, options);
        if (response.status === 204) return null;

        const data = await response.json();
        if (!response.ok) {
            let msg = '请求失败';
            if (typeof data.detail === 'string') {
                msg = data.detail;
            } else if (Array.isArray(data.detail)) {
                msg = data.detail.map(d => d.msg).join('; ');
            }
            throw new Error(msg);
        }
        return data;
    },

    auth: {
        login(username, password) {
            return api.request('POST', '/auth/login', { username, password });
        },
        register(username, password, displayName, email) {
            return api.request('POST', '/auth/register', { username, password, display_name: displayName, email });
        },
    },

    users: {
        list() {
            return api.request('GET', '/users/');
        },
        get(id) {
            return api.request('GET', `/users/${id}`);
        },
        update(id, data) {
            return api.request('PUT', `/users/${id}`, data);
        },
        delete(id) {
            return api.request('DELETE', `/users/${id}`);
        },
        me() {
            return api.request('GET', '/users/me');
        },
        updateMe(data) {
            return api.request('PUT', '/users/me', data);
        },
    },

    mcp: {
        list() {
            return api.request('GET', '/mcp-services/');
        },
        get(id) {
            return api.request('GET', `/mcp-services/${id}`);
        },
        create(data) {
            return api.request('POST', '/mcp-services/', data);
        },
        update(id, data) {
            return api.request('PUT', `/mcp-services/${id}`, data);
        },
        delete(id) {
            return api.request('DELETE', `/mcp-services/${id}`);
        },
        test(id) {
            return api.request('POST', `/mcp-services/${id}/test`);
        },
    },

    chat: {
        async sendStream(message, conversationId, onEvent, model) {
            const headers = {};
            if (api.token) {
                headers['Authorization'] = `Bearer ${api.token}`;
            }
            headers['Content-Type'] = 'application/json';

            const body = { message, conversation_id: conversationId };
            if (model) body.model = model;

            const response = await fetch(API_BASE + '/chat/send', {
                method: 'POST',
                headers,
                body: JSON.stringify(body),
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            onEvent(data);
                        } catch (e) {
                            console.error('Parse error:', e);
                        }
                    }
                }
            }
        },

        getModels() {
            return api.request('GET', '/chat/models');
        },

        async uploadFile(file) {
            const formData = new FormData();
            formData.append('file', file);

            const headers = {};
            if (api.token) {
                headers['Authorization'] = `Bearer ${api.token}`;
            }

            const response = await fetch(API_BASE + '/chat/upload', {
                method: 'POST',
                headers,
                body: formData,
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || '上传失败');
            }
            return data;
        },

        getConversations() {
            return api.request('GET', '/chat/conversations');
        },

        getConversation(id) {
            return api.request('GET', `/chat/conversations/${id}`);
        },

        deleteConversation(id) {
            return api.request('DELETE', `/chat/conversations/${id}`);
        },

        getTools() {
            return api.request('GET', '/chat/tools');
        },
    },
};