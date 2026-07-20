let currentConversationId = null;
let isStreaming = false;
let attachments = [];

const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnNewChat = document.getElementById('btn-new-chat');
const conversationList = document.getElementById('conversation-list');
const btnAttach = document.getElementById('btn-attach');
const fileInput = document.getElementById('file-input');
const attachmentsPreview = document.getElementById('attachments-preview');

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
        chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
    });
    btnAttach.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);
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
        if (data.messages.length > 0) {
            hideToolsGrid();
        } else {
            showToolsGrid();
        }
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
            chatMessages.innerHTML = '<div class="chat-welcome"><h2>欢迎使用AI工具箱</h2><p>选择一个对话或创建新对话开始聊天</p></div>';
            showToolsGrid();
        }
        loadConversations();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

function newChat() {
    currentConversationId = null;
    chatMessages.innerHTML = '<div class="chat-welcome"><h2>欢迎使用AI工具箱</h2><p>选择一个对话或创建新对话开始聊天</p></div>';
    showToolsGrid();
    loadConversations();
}

async function sendMessage() {
    if (isStreaming) return;
    const message = chatInput.value.trim();
    if (!message && attachments.length === 0) return;

    let fullMessage = message;
    let displayMessage = message;
    if (attachments.length > 0) {
        const fileContents = [];
        const fileNames = [];
        for (const att of attachments) {
            const isError = att.content && (att.content.startsWith('[解析失败') || att.content.startsWith('[不支持') || att.content.startsWith('[无法解码') || att.content.startsWith('[旧版'));
            if (att.content && !isError) {
                fileContents.push(`\n\n[文件: ${att.name}]\n${att.content}`);
            } else if (isError) {
                fileContents.push(`\n\n[附件: ${att.name} (${att.content})]`);
            } else {
                fileContents.push(`\n\n[附件: ${att.name}]`);
            }
            fileNames.push(`📎 ${att.name}`);
        }
        fullMessage += fileContents.join('');
        displayMessage = (message ? message + '\n' : '') + fileNames.join('\n');
    }

    chatInput.value = '';
    chatInput.style.height = 'auto';
    clearAttachments();

    if (chatMessages.querySelector('.chat-welcome')) {
        chatMessages.innerHTML = '';
    }

    hideToolsGrid();

    addMessage('user', displayMessage);

    const assistantMsgDiv = addMessage('assistant', '', null, true);
    const contentDiv = assistantMsgDiv.querySelector('.message-content');

    isStreaming = true;
    btnSend.disabled = true;

    let fullContent = '';
    let toolCallsInfo = [];

    try {
        await api.chat.sendStream(fullMessage, currentConversationId, (event) => {
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

async function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    const textExtensions = ['.txt', '.md', '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.csv', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.log', '.html', '.css', '.sql', '.sh', '.bash', '.env', '.gitignore', '.java', '.c', '.cpp', '.h', '.rs', '.go', '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.lua', '.vim', '.conf'];
    const officeExtensions = ['.xlsx', '.xlsm', '.xltx', '.xltm', '.docx', '.docm', '.dotx', '.dotm', '.wpsx'];
    const MAX_TEXT_SIZE = 2 * 1024 * 1024;

    for (const file of files) {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        console.log(`[附件] 处理文件: ${file.name}, 扩展名: ${ext}, 类型: ${file.type}, 大小: ${file.size}`);
        let content = null;

        if (textExtensions.includes(ext) || file.type.startsWith('text/')) {
            if (file.size > MAX_TEXT_SIZE) {
                content = `[解析失败: 文件过大 (${(file.size / 1024 / 1024).toFixed(1)}MB)，文本文件最大支持 2MB]`;
                console.warn(`[附件] ${file.name} 文件过大: ${file.size}`);
            } else {
                try {
                    content = await file.text();
                    if (!content || !content.trim()) {
                        content = `[解析失败: 文件内容为空]`;
                    }
                    console.log(`[附件] ${file.name} 文本读取成功, 长度: ${content.length}`);
                } catch (err) {
                    console.error(`[附件] ${file.name} 文本读取失败:`, err);
                    content = `[解析失败: ${err.message || '无法读取文件'}]`;
                }
            }
        } else if (officeExtensions.includes(ext)) {
            console.log(`[附件] ${file.name} 上传到后端解析...`);
            try {
                const result = await api.chat.uploadFile(file);
                content = result.content;
                console.log(`[附件] ${file.name} 解析成功, 长度: ${content.length}`);
            } catch (err) {
                console.error('Failed to parse office file:', err);
                content = `[解析失败: ${err.message}]`;
            }
        } else {
            console.log(`[附件] ${file.name} 格式不支持，仅显示文件名`);
        }
        attachments.push({ name: file.name, content: content });
    }
    fileInput.value = '';
    renderAttachments();
}

function removeAttachment(index) {
    attachments.splice(index, 1);
    renderAttachments();
}

function clearAttachments() {
    attachments = [];
    renderAttachments();
}

function renderAttachments() {
    if (attachments.length === 0) {
        attachmentsPreview.style.display = 'none';
        attachmentsPreview.innerHTML = '';
        return;
    }
    attachmentsPreview.style.display = 'flex';
    attachmentsPreview.innerHTML = attachments.map((att, i) => {
        const isError = att.content && (att.content.startsWith('[解析失败') || att.content.startsWith('[不支持') || att.content.startsWith('[无法解码') || att.content.startsWith('[旧版'));
        const cls = isError ? 'attachment-chip attachment-error' : 'attachment-chip';
        const icon = isError ? '⚠️' : (att.content ? '📄' : '📁');
        return `
        <div class="${cls}" title="${isError ? att.content : ''}">
            <span>${icon} ${att.name}</span>
            <button class="remove-attach" onclick="removeAttachment(${i})">×</button>
        </div>
    `}).join('');
}

let allTools = [];
let toolsPage = 0;
const TOOLS_PER_PAGE = 3;
let toolsGridShouldHide = false;

function hideToolsGrid() {
    toolsGridShouldHide = true;
    const grid = document.getElementById('chat-tools-grid');
    if (grid) {
        grid.style.setProperty('display', 'none', 'important');
    }
}

function showToolsGrid() {
    toolsGridShouldHide = false;
    const grid = document.getElementById('chat-tools-grid');
    if (grid && allTools.length > 0) {
        grid.style.setProperty('display', 'flex', 'important');
    }
}

async function loadChatTools() {
    try {
        const tools = await api.chat.getTools();
        allTools = tools;
        toolsPage = 0;
        renderToolsGrid();
    } catch (err) {
        console.error('加载工具列表失败:', err);
        const grid = document.getElementById('chat-tools-grid');
        if (grid) grid.style.setProperty('display', 'none', 'important');
    }
}

function renderToolsGrid() {
    const grid = document.getElementById('chat-tools-grid');
    const inner = document.getElementById('tools-grid-inner');
    const arrowLeft = document.getElementById('tools-arrow-left');
    const arrowRight = document.getElementById('tools-arrow-right');

    if (!grid || !inner) return;

    if (allTools.length === 0) {
        grid.style.setProperty('display', 'none', 'important');
        return;
    }

    if (toolsGridShouldHide) {
        grid.style.setProperty('display', 'none', 'important');
        return;
    }

    grid.style.setProperty('display', 'flex', 'important');

    const totalPages = Math.ceil(allTools.length / TOOLS_PER_PAGE);
    const start = toolsPage * TOOLS_PER_PAGE;
    const pageTools = allTools.slice(start, start + TOOLS_PER_PAGE);

    let html = '';
    for (let i = 0; i < TOOLS_PER_PAGE; i++) {
        if (i < pageTools.length) {
            const tool = pageTools[i];
            html += `
            <div class="tool-chip ${tool.type}" title="${tool.description}">
                <span class="tool-chip-icon">${tool.icon}</span>
                <span class="tool-chip-name">${tool.name}</span>
                <span class="tool-chip-desc">${tool.description}</span>
            </div>`;
        } else {
            html += '<div class="tool-chip-placeholder"></div>';
        }
    }
    inner.innerHTML = html;

    if (arrowLeft) arrowLeft.disabled = toolsPage === 0;
    if (arrowRight) arrowRight.disabled = toolsPage >= totalPages - 1;
}

document.addEventListener('DOMContentLoaded', () => {
    const arrowLeft = document.getElementById('tools-arrow-left');
    const arrowRight = document.getElementById('tools-arrow-right');

    if (arrowLeft) {
        arrowLeft.addEventListener('click', () => {
            if (toolsPage > 0) {
                toolsPage--;
                renderToolsGrid();
            }
        });
    }

    if (arrowRight) {
        arrowRight.addEventListener('click', () => {
            const totalPages = Math.ceil(allTools.length / TOOLS_PER_PAGE);
            if (toolsPage < totalPages - 1) {
                toolsPage++;
                renderToolsGrid();
            }
        });
    }
});