let currentConversationId = null;
let isStreaming = false;

const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnNewChat = document.getElementById('btn-new-chat');
const conversationList = document.getElementById('conversation-list');

function initChat() {
    btnSend.addEventListener('click', sendMessage);
    btnNewChat.addEventListener('click', newChat);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });
}

async function loadConversations() {
    try {
        const conversations = await api.chat.getConversations();
        conversationList.innerHTML = '';
        conversations.forEach(conv => {
            const div = document.createElement('div');
            div.className = 'conversation-item' + (conv.id === currentConversationId ? ' active' : '');
            div.innerHTML = `
                <span class="conv-title">${escapeHtml(conv.first_message || '新对话')}</span>
                <button class="conv-delete" data-id="${conv.id}">×</button>
            `;
            div.addEventListener('click', (e) => {
                if (e.target.classList.contains('conv-delete')) return;
                selectConversation(conv.id);
            });
            div.querySelector('.conv-delete').addEventListener('click', (e) => {
                e.stopPropagation();
                deleteConversation(conv.id);
            });
            conversationList.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load conversations:', e);
    }
}

async function selectConversation(id) {
    currentConversationId = id;
    chatMessages.innerHTML = '<div class="chat-welcome"><h2>加载中...</h2></div>';
    try {
        const data = await api.chat.getConversation(id);
        chatMessages.innerHTML = '';
        data.messages.forEach(msg => addMessage(msg.role, msg.content, msg.tool_calls));
        scrollToBottom();
    } catch (e) {
        chatMessages.innerHTML = '<div class="chat-welcome"><h2>加载失败</h2></div>';
    }
    loadConversations();
}

async function deleteConversation(id) {
    if (!confirm('确定删除此对话？')) return;
    try {
        await api.chat.deleteConversation(id);
        if (currentConversationId === id) {
            currentConversationId = null;
            chatMessages.innerHTML = '<div class="chat-welcome"><h2>欢迎使用 AI Tools</h2><p>选择一个对话或创建新对话开始聊天</p></div>';
        }
        loadConversations();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

function newChat() {
    currentConversationId = null;
    chatMessages.innerHTML = '<div class="chat-welcome"><h2>欢迎使用 AI Tools</h2><p>选择一个对话或创建新对话开始聊天</p></div>';
    loadConversations();
}

async function sendMessage() {
    if (isStreaming) return;
    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value = '';
    chatInput.style.height = 'auto';

    if (chatMessages.querySelector('.chat-welcome')) {
        chatMessages.innerHTML = '';
    }

    addMessage('user', message);

    const assistantMsgDiv = addMessage('assistant', '', null, true);
    const contentDiv = assistantMsgDiv.querySelector('.message-content');

    isStreaming = true;
    btnSend.disabled = true;

    let fullContent = '';
    let toolCallsInfo = [];

    try {
        await api.chat.sendStream(message, currentConversationId, (event) => {
            switch (event.type) {
                case 'content':
                    fullContent += event.content;
                    contentDiv.innerHTML = marked.parse(fullContent);
                    hljs.highlightAll();
                    scrollToBottom();
                    break;
                case 'tool_calls':
                    toolCallsInfo = event.tool_calls;
                    const toolInfo = document.createElement('div');
                    toolInfo.className = 'tool-call-info';
                    toolInfo.innerHTML = event.tool_calls.map(tc =>
                        `🔧 调用工具: <span class="tool-name">${escapeHtml(tc.function.name)}</span>`
                    ).join('<br>');
                    contentDiv.appendChild(toolInfo);
                    scrollToBottom();
                    break;
                case 'tool_start':
                    const startDiv = document.createElement('div');
                    startDiv.className = 'tool-call-info';
                    startDiv.innerHTML = `⚙️ 执行: <span class="tool-name">${escapeHtml(event.tool_name)}</span>`;
                    contentDiv.appendChild(startDiv);
                    scrollToBottom();
                    break;
                case 'tool_result':
                    const resultDiv = document.createElement('div');
                    resultDiv.className = 'tool-call-info';
                    resultDiv.innerHTML = `✅ 完成: <span class="tool-name">${escapeHtml(event.tool_name)}</span>`;
                    contentDiv.appendChild(resultDiv);
                    scrollToBottom();
                    break;
                case 'done':
                    currentConversationId = event.conversation_id;
                    loadConversations();
                    break;
                case 'error':
                    contentDiv.innerHTML += `<div class="error-message">错误: ${escapeHtml(event.error)}</div>`;
                    break;
            }
        }, currentModel);
    } catch (e) {
        contentDiv.innerHTML += `<div class="error-message">请求失败: ${escapeHtml(e.message)}</div>`;
    }

    isStreaming = false;
    btnSend.disabled = false;
    chatInput.focus();
}

function addMessage(role, content, toolCalls, isStreaming = false) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    if (role === 'user') {
        div.innerHTML = `<div class="message-content">${escapeHtml(content)}</div>`;
    } else {
        div.innerHTML = `<div class="message-content">${isStreaming ? '<div class="typing-indicator"><span></span><span></span><span></span></div>' : marked.parse(content)}</div>`;
    }

    chatMessages.appendChild(div);
    if (!isStreaming) {
        hljs.highlightAll();
    }
    scrollToBottom();
    return div;
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}