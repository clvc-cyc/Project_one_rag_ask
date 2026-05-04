// ========== 1. 获取页面元素 ==========
const apiKeyInput = document.getElementById('apiKeyInput');
const saveApiKeyBtn = document.getElementById('saveApiKeyBtn');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const uploadStatus = document.getElementById('uploadStatus');
const fileDropPrimary = document.getElementById('fileDropPrimary');
const fileDropSecondary = document.getElementById('fileDropSecondary');
const sessionIdInput = document.getElementById('sessionIdInput');
const newSessionBtn = document.getElementById('newSessionBtn');
const chatMessages = document.getElementById('chatMessages');
const promptInput = document.getElementById('promptInput');
const sendBtn = document.getElementById('sendBtn');

// 与当前页面同源请求后端，避免写死端口导致 Failed to fetch；用 file:// 打开页面时回退本机默认端口
function getApiBase() {
    if (typeof window === 'undefined') return 'http://localhost:8000';
    const { protocol, hostname, port } = window.location;
    if (protocol === 'file:' || !hostname) return 'http://localhost:8000';
    return `${protocol}//${hostname}${port ? ':' + port : ''}`;
}
const API_BASE = getApiBase();

function formatFetchError(err) {
    if (err && (err.message === 'Failed to fetch' || err.name === 'TypeError')) {
        return `无法连接后端（${API_BASE}）。请在本目录启动服务（如 uvicorn），并确保 Redis 已运行；页面地址端口须与 API 一致。`;
    }
    return err.message;
}

// 当前使用的会话ID（用于多轮对话）
let currentSessionId = '';

// ========== 2. 初始化：从浏览器本地存储读取之前保存的 API Key 和 session_id ==========
function loadStoredData() {
    const storedKey = localStorage.getItem('api_key');
    if (storedKey) apiKeyInput.value = storedKey;
    const storedSession = localStorage.getItem('session_id');
    if (storedSession) {
        currentSessionId = storedSession;
        sessionIdInput.value = storedSession;
    } else {
        generateNewSession();       // 没有则新建一个会话
    }
}

// 生成一个新的随机会话ID（使用浏览器内置的 crypto.randomUUID）
function generateNewSession() {
    currentSessionId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15);
    sessionIdInput.value = currentSessionId;
    localStorage.setItem('session_id', currentSessionId);
    chatMessages.innerHTML = '';    // 清空聊天区域
}

// ========== 3. 保存 API Key ==========
saveApiKeyBtn.addEventListener('click', () => {
    const key = apiKeyInput.value.trim();
    if (key) {
        localStorage.setItem('api_key', key);
        uploadStatus.textContent = 'API Key 已保存';
        setTimeout(() => uploadStatus.textContent = '', 2000);
    } else {
        alert('请输入 API Key');
    }
});

// 新会话按钮：重新生成一个会话ID
newSessionBtn.addEventListener('click', () => {
    generateNewSession();
});

// ========== 4. 构造请求头，里面带上 X-API-Key（后端认证） ==========
function getHeaders() {
    const apiKey = localStorage.getItem('api_key');
    if (!apiKey) {
        alert('请先保存 API Key');
        throw new Error('No API Key');
    }
    return {
        'X-API-Key': apiKey,
        'Content-Type': 'application/json'
    };
}

// 选择文件后，在入库区域内显示文件名
function updateFileDropLabel() {
    const file = fileInput.files[0];
    if (file) {
        fileDropPrimary.textContent = file.name;
        fileDropSecondary.textContent = '点击更换文件';
    } else {
        fileDropPrimary.textContent = '点击选择';
        fileDropSecondary.textContent = '或拖入文件';
    }
}

fileInput.addEventListener('change', updateFileDropLabel);

// ========== 5. 上传文档到 /upload 接口 ==========
uploadBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) {
        uploadStatus.textContent = '请选择文件';
        return;
    }
    const apiKey = localStorage.getItem('api_key');
    if (!apiKey) {
        uploadStatus.textContent = '请先保存 API Key';
        return;
    }

    const formData = new FormData();
    formData.append('file', file);      // 字段名必须与后端 UploadFile 参数名一致（file）

    try {
        uploadStatus.textContent = '上传中...';
        // 注意：上传接口使用 multipart/form-data，所以 Content-Type 不需要手动设置，fetch 会自动处理
        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            headers: {
                'X-API-Key': apiKey      // 仅需认证头，不需要 Content-Type
            },
            body: formData
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '上传失败');
        }
        const data = await response.json();
        uploadStatus.textContent = `成功！${data.filename ? data.filename + '，' : ''}共 ${data.total_chunks} 个文档块。`;
        setTimeout(() => uploadStatus.textContent = '', 3000);
        fileInput.value = '';
        updateFileDropLabel();
    } catch (err) {
        uploadStatus.textContent = `错误: ${formatFetchError(err)}`;
    }
});

// ========== 6. 聊天界面显示消息（简单防 XSS） ==========
function appendMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    // 防止用户输入 HTML 标签被当作代码执行
    const escaped = escapeHtml(content);
    messageDiv.innerHTML = `<div class="bubble">${escaped}</div>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight; // 自动滚动到底部
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ========== 7. 发送聊天消息 ==========
sendBtn.addEventListener('click', async () => {
    const prompt = promptInput.value.trim();
    if (!prompt) return;

    // 获取当前会话ID（优先用输入框的值，没有则用 currentSessionId）
    let sessionId = sessionIdInput.value.trim();
    if (!sessionId) {
        if (!currentSessionId) generateNewSession();
        sessionId = currentSessionId;
        sessionIdInput.value = sessionId;
    } else {
        currentSessionId = sessionId;
        localStorage.setItem('session_id', currentSessionId);
    }

    // 显示用户消息
    appendMessage('user', prompt);
    promptInput.value = '';

    // 构造请求体
    const body = {
        prompt: prompt,
        max_tokens: 1024,
        session_id: currentSessionId   // 关键：带上会话ID，后端才能取到历史
    };

    try {
        const headers = getHeaders();   // 包含 X-API-Key
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(body)
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '请求失败');
        }
        const data = await response.json();
        appendMessage('assistant', data.response);

        // 如果后端返回了新的 session_id（理论上不会变，但万一变了就更新）
        if (data.session_id && data.session_id !== currentSessionId) {
            currentSessionId = data.session_id;
            sessionIdInput.value = currentSessionId;
            localStorage.setItem('session_id', currentSessionId);
        }
    } catch (err) {
        appendMessage('assistant', `错误: ${formatFetchError(err)}`);
    }
});

// 允许回车发送（Ctrl+Enter 换行）
promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.ctrlKey) {
        e.preventDefault();
        sendBtn.click();
    }
});

// 启动初始化
loadStoredData();
if (!currentSessionId) generateNewSession();