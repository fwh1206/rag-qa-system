"""将 index.html 的样式层整体替换为浅色极简主题（飞书/Notion 风格）。"""

path = r"C:\Users\wang0\Documents\rag问答系统\static\index.html"
with open(path, "r", encoding="utf-8") as f:
    html = f.read()

NEW_CSS = """<style>
/* ============ 全局重置与主题变量 ============ */
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
:root {
    --bg: #f5f6f8;            /* 页面底色 */
    --panel: #ffffff;         /* 卡片/面板 */
    --panel-hover: #f7f8fa;   /* 悬停底色 */
    --line: #e5e7eb;          /* 常规边框 */
    --line-strong: #cfd3da;   /* 强调边框 */
    --accent: #2563eb;        /* 主色（克制的蓝） */
    --accent-soft: #eef4ff;   /* 主色浅底 */
    --accent-strong: #1d4ed8; /* 主色按下态 */
    --text: #1f2329;          /* 主文字 */
    --muted: #8f959e;         /* 次要文字 */
    --green: #34c724;         /* 成功 */
    --red: #f53f3f;           /* 危险 */
    --amber: #b45309;         /* 警告 */
    --radius: 8px;
    --radius-sm: 6px;
    --shadow: 0 1px 3px rgba(0,0,0,0.05);
    --mono: "Cascadia Mono", Consolas, "Courier New", monospace;
}
body {
    display: flex;
    overflow: hidden;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, "PingFang SC", "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.6;
}
button { font-family: inherit; cursor: pointer; }
svg { flex: none; }
input, textarea, select { font-family: inherit; }
.hidden { display: none !important; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: #d3d7de; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #b9bfc9; }
::-webkit-scrollbar-track { background: transparent; }

/* ============ 侧边栏 ============ */
.sidebar {
    width: 280px;
    flex: none;
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px 14px;
    background: var(--panel);
    border-right: 1px solid var(--line);
    overflow-y: auto;
}
.brand { display: flex; align-items: center; gap: 10px; padding: 2px 2px 12px; border-bottom: 1px solid var(--line); }
.brand-mark {
    width: 34px; height: 34px; flex: none;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 15px; color: #fff;
    background: var(--accent);
    border-radius: 8px;
}
.brand-name { font-size: 15px; font-weight: 600; color: var(--text); }
.brand-sub { font-size: 10px; color: var(--muted); font-family: var(--mono); margin-top: 2px; letter-spacing: 0.5px; }

/* 拖拽上传区 */
.drop-zone {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 6px; min-height: 92px;
    border: 1px dashed var(--line-strong);
    border-radius: var(--radius);
    background: var(--panel-hover);
    color: var(--muted);
    font-size: 13px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
}
.drop-zone svg { color: var(--accent); opacity: 0.75; }
.drop-zone.dragover { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.drop-sub { font-size: 11px; color: var(--muted); }

.side-actions { display: flex; gap: 8px; flex-wrap: wrap; }

/* ============ 按钮 ============ */
.btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 7px 14px;
    font-size: 13px;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    transition: background 0.15s, border-color 0.15s, color 0.15s;
    white-space: nowrap;
}
.btn:hover { background: var(--panel-hover); border-color: var(--line-strong); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { background: var(--accent-strong); }
.btn.danger-ghost { color: var(--red); border-color: #f4b8b8; background: #fff; }
.btn.danger-ghost:hover { background: #fdf1f1; border-color: var(--red); }

.icon-text-btn {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; font-size: 12.5px;
    color: var(--muted);
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    transition: all 0.15s;
}
.icon-text-btn:hover { color: var(--accent); background: var(--accent-soft); border-color: transparent; }
.icon-btn {
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px; padding: 0;
    color: var(--muted);
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    transition: all 0.15s;
}
.icon-btn:hover { color: var(--text); background: var(--panel-hover); }

/* ============ 表单控件 ============ */
.file-input { display: none; }
.field-label { font-size: 12px; color: var(--muted); }
.field-input, .session-input {
    width: 100%;
    padding: 7px 10px;
    font-size: 13px;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    outline: none;
    transition: border-color 0.15s;
}
.field-input:focus, .session-input:focus { border-color: var(--accent); }
.category-select, .session-select {
    padding: 6px 10px;
    font-size: 13px;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    outline: none;
    cursor: pointer;
}
.category-select:focus { border-color: var(--accent); }

/* 上传进度 */
.upload-progress { display: flex; flex-direction: column; gap: 6px; }
.upload-progress-bar { height: 4px; background: #e9ecf1; border-radius: 2px; overflow: hidden; }
.upload-progress-fill { height: 100%; width: 0; background: var(--accent); border-radius: 2px; transition: width 0.2s; }
.upload-progress-text { font-size: 11px; color: var(--muted); }

/* ============ 知识库面板 ============ */
.panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    display: flex; flex-direction: column;
    min-height: 0;
}
.panel-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 12px;
    border-bottom: 1px solid var(--line);
    font-size: 13px; font-weight: 600;
}
.panel-count {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 20px; height: 20px; padding: 0 6px;
    font-size: 11px; font-weight: 500;
    color: var(--accent);
    background: var(--accent-soft);
    border-radius: 10px;
}
.file-list { overflow-y: auto; flex: 1; min-height: 60px; padding: 4px; }
.file-row {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 8px;
    border-radius: var(--radius-sm);
    transition: background 0.12s;
}
.file-row:hover { background: var(--panel-hover); }
.file-icon { color: var(--muted); flex: none; }
.file-info { flex: 1; min-width: 0; }
.file-name {
    font-size: 13px; color: var(--text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.file-meta { font-size: 11px; color: var(--muted); }
.file-category {
    display: inline-block; font-size: 10px; color: var(--accent);
    background: var(--accent-soft); border-radius: 4px; padding: 1px 6px; margin-left: 4px;
}
.file-tools { display: flex; gap: 2px; flex: none; }

/* 分页 */
.pager { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 8px; }
.pager-btn { padding: 4px 12px; font-size: 12px; }
.pager-info { font-size: 12px; color: var(--muted); font-family: var(--mono); }
.upload-status { font-size: 12px; color: var(--muted); padding: 0 2px; }

/* ============ 主区域 ============ */
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; padding: 12px 20px;
    background: var(--panel);
    border-bottom: 1px solid var(--line);
    flex-wrap: wrap;
}
.chat-title { font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.online-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--green);
    display: inline-block;
}
.session-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.session-tag { font-size: 12px; color: var(--muted); font-family: var(--mono); }
.session-input { width: 140px; }
.chat-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

/* ============ 消息区 ============ */
.messages {
    flex: 1; overflow-y: auto; padding: 24px 20px;
    display: flex; flex-direction: column; gap: 16px;
}
.empty-tip {
    margin: auto; text-align: center;
    color: var(--muted); font-size: 14px;
}
.message { display: flex; flex-direction: column; max-width: 78%; }
.message.user { align-self: flex-end; align-items: flex-end; }
.message.assistant { align-self: flex-start; align-items: flex-start; }
.bubble {
    padding: 10px 14px;
    border-radius: var(--radius);
    font-size: 14px;
    line-height: 1.7;
    word-break: break-word;
    white-space: pre-wrap;
}
.message.user .bubble {
    background: var(--accent);
    color: #fff;
    border-bottom-right-radius: 2px;
}
.message.assistant .bubble {
    background: var(--panel);
    border: 1px solid var(--line);
    border-bottom-left-radius: 2px;
    box-shadow: var(--shadow);
}

/* 思考过程块 */
.thinking-box {
    background: var(--panel-hover);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    margin-bottom: 10px;
    font-size: 12.5px;
    color: var(--muted);
}
.thinking-head {
    display: flex; align-items: center; gap: 6px;
    padding: 8px 12px; cursor: pointer; user-select: none;
    font-size: 12px; color: var(--muted);
}
.thinking-title { font-weight: 600; }
.thinking-text { padding: 2px 12px 10px; white-space: pre-wrap; max-height: 260px; overflow-y: auto; }
.thinking-text.collapsed { display: none; }
.thinking-ring { width: 12px; height: 12px; border: 2px solid var(--line-strong); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }

/* 流式光标 */
.stream-cursor::after {
    content: "\258d";
    margin-left: 2px;
    color: var(--accent);
    animation: cursorBlink 0.9s steps(2) infinite;
}
@keyframes cursorBlink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
@keyframes spin { to { transform: rotate(360deg); } }

/* 打字动画 */
.typing-dots { display: inline-flex; align-items: center; gap: 4px; padding: 12px 16px; }
.typing-dots span {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--muted);
    animation: dot-bounce 1.2s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.15s; }
.typing-dots span:nth-child(3) { animation-delay: 0.3s; }
@keyframes dot-bounce { 0%, 80%, 100% { transform: scale(0.7); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }

/* ============ 来源卡片 ============ */
.sources {
    margin-top: 8px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    overflow: hidden;
}
.sources-title {
    display: flex; align-items: center; gap: 6px;
    width: 100%;
    padding: 9px 12px;
    font-size: 12.5px; font-weight: 600;
    color: var(--text);
    background: transparent;
    border: none;
    cursor: pointer;
}
.sources-title:hover { background: var(--panel-hover); }
.src-chevron { transition: transform 0.2s; color: var(--muted); }
.src-count {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 18px; height: 18px; padding: 0 5px;
    font-size: 11px;
    color: var(--accent);
    background: var(--accent-soft);
    border-radius: 9px;
}
.sources-list { border-top: 1px solid var(--line); }
.source-item { padding: 10px 12px; border-bottom: 1px solid var(--line); transition: background 0.12s; }
.source-item:last-child { border-bottom: none; }
.source-item:hover { background: var(--panel-hover); }
.source-item.source-active { background: var(--accent-soft); border-left: 3px solid var(--accent); }
.source-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.source-name { font-size: 12.5px; font-weight: 600; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-meta { font-size: 11px; color: var(--muted); display: flex; align-items: center; gap: 6px; }
.source-meta .rerank-badge {
    font-size: 10px; color: var(--accent);
    background: var(--accent-soft);
    border-radius: 4px; padding: 1px 5px;
    font-family: var(--mono);
}
.source-preview {
    font-size: 12.5px; color: var(--muted);
    line-height: 1.6;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.source-preview.expanded { -webkit-line-clamp: unset; }
.source-jump {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11.5px; color: var(--accent);
    background: transparent; border: none; padding: 2px 0;
    cursor: pointer;
}
.source-jump:hover { text-decoration: underline; }
.source-toggle { font-size: 11.5px; color: var(--muted); background: none; border: none; padding: 2px; cursor: pointer; }
.source-toggle:hover { color: var(--text); }

/* ============ 回答操作 ============ */
.answer { position: relative; }
.answer-actions {
    display: flex; gap: 4px;
    margin-top: 6px;
    opacity: 0;
    transition: opacity 0.15s;
}
.message.assistant:hover .answer-actions { opacity: 1; }
.copy-btn {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 8px;
    font-size: 11.5px;
    color: var(--muted);
    background: transparent;
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    transition: all 0.15s;
}
.copy-btn:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }

/* 来源内跳转链接（正文中的 [来源N]） */
.src-link { color: var(--accent); text-decoration: none; font-size: 12px; }
.src-link:hover { text-decoration: underline; }

/* ============ 输入区 ============ */
.input-area {
    padding: 14px 20px 18px;
    background: var(--panel);
    border-top: 1px solid var(--line);
}
.mode-switch {
    display: inline-flex; gap: 2px;
    background: #eceef2;
    border-radius: var(--radius-sm);
    padding: 2px;
    margin-bottom: 10px;
}
.mode-btn {
    padding: 4px 14px; font-size: 12.5px;
    color: var(--muted);
    background: transparent;
    border: none;
    border-radius: 5px;
    transition: all 0.15s;
}
.mode-btn:hover { color: var(--text); }
.mode-btn.active { background: var(--panel); color: var(--text); box-shadow: 0 1px 2px rgba(0,0,0,0.08); font-weight: 500; }
.input-shell {
    display: flex; align-items: flex-end; gap: 10px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 10px 12px;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.input-shell:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12); }
#questionInput {
    flex: 1;
    border: none; outline: none; resize: none;
    background: transparent;
    font-size: 14px;
    color: var(--text);
    line-height: 1.6;
    max-height: 160px;
    font-family: inherit;
}
#questionInput::placeholder { color: var(--muted); }
#questionInput:disabled { opacity: 0.6; }
.send-btn {
    display: inline-flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; flex: none;
    background: var(--accent);
    border: none; border-radius: var(--radius-sm);
    color: #fff;
    transition: background 0.15s, opacity 0.15s;
}
.send-btn:hover { background: var(--accent-strong); }
.send-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* ============ 登录页 ============ */
.login-overlay {
    position: fixed; inset: 0; z-index: 100;
    display: flex; align-items: center; justify-content: center;
    background: rgba(31, 35, 41, 0.45);
    backdrop-filter: blur(4px);
}
.login-card {
    width: 380px; max-width: 92vw;
    background: var(--panel);
    border-radius: 12px;
    padding: 32px 32px 28px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.14);
}
.login-title { font-size: 20px; font-weight: 700; text-align: center; color: var(--text); }
.login-sub { font-size: 11px; color: var(--muted); text-align: center; letter-spacing: 2px; margin: 6px 0 22px; font-family: var(--mono); }
.login-tabs {
    display: flex; gap: 2px;
    background: #eceef2;
    border-radius: var(--radius-sm);
    padding: 2px;
    margin-bottom: 18px;
}
.login-tab {
    flex: 1; padding: 6px 0; font-size: 13px;
    color: var(--muted);
    background: transparent; border: none; border-radius: 5px;
    transition: all 0.15s;
}
.login-tab.active { background: var(--panel); color: var(--text); font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
.auth-form { display: flex; flex-direction: column; gap: 12px; }
.login-field {
    width: 100%;
    padding: 9px 12px;
    font-size: 14px;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    outline: none;
    transition: border-color 0.15s;
}
.login-field:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12); }
.login-btn { width: 100%; padding: 9px; font-size: 14px; }
.login-error { font-size: 12.5px; color: var(--red); text-align: center; }
.auth-link { font-size: 12.5px; color: var(--accent); text-align: center; background: none; border: none; cursor: pointer; }
.auth-link:hover { text-decoration: underline; }

/* ============ 弹窗 ============ */
.modal-overlay {
    position: fixed; inset: 0; z-index: 90;
    display: flex; align-items: center; justify-content: center;
    background: rgba(31, 35, 41, 0.45);
    backdrop-filter: blur(3px);
}
.modal {
    width: 520px; max-width: 94vw;
    background: var(--panel);
    border-radius: 12px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.14);
    display: flex; flex-direction: column;
    max-height: 86vh;
}
.modal-wide { width: 760px; }
.modal-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 20px;
    border-bottom: 1px solid var(--line);
    font-size: 15px; font-weight: 600;
}
.modal textarea {
    width: 100%; padding: 10px 12px;
    font-size: 13px; line-height: 1.6;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    outline: none; resize: vertical;
    font-family: inherit;
}
.modal textarea:focus { border-color: var(--accent); }
.modal-actions {
    display: flex; justify-content: flex-end; gap: 8px;
    padding: 14px 20px;
    border-top: 1px solid var(--line);
}
.prompt-area { min-height: 180px; font-family: var(--mono); font-size: 12.5px !important; }

/* ============ 设置 ============ */
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 20px; padding: 18px 20px; }
.settings-grid label { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--muted); }
.settings-grid input[type="text"], .settings-grid input[type="number"] {
    padding: 7px 10px;
    font-size: 13px;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    outline: none;
}
.settings-grid input:focus { border-color: var(--accent); }
.settings-grid input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent); cursor: pointer; }

/* ============ 文件预览 ============ */
.preview-body { padding: 16px 20px; overflow-y: auto; white-space: pre-wrap; font-size: 13px; line-height: 1.8; color: var(--text); font-family: inherit; }
.preview-meta { font-size: 12px; color: var(--muted); padding: 0 20px 12px; }

/* ============ 检索测试 ============ */
.retrieval-head { padding: 14px 20px; display: flex; flex-direction: column; gap: 10px; }
.retrieval-results { padding: 0 20px 18px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
.retrieval-item {
    background: var(--panel-hover);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 10px 12px;
}
.retrieval-text { font-size: 12.5px; color: var(--text); white-space: pre-wrap; max-height: 200px; overflow-y: auto; }

/* ============ 用户管理 ============ */
.user-list { padding: 10px 20px; max-height: 380px; overflow-y: auto; }
.user-row {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 8px;
    border-radius: var(--radius-sm);
    transition: background 0.12s;
}
.user-row:hover { background: var(--panel-hover); }
.user-role {
    font-size: 11px; padding: 2px 8px;
    border-radius: 4px;
    color: var(--accent); background: var(--accent-soft);
}
.user-actions { margin-left: auto; display: flex; gap: 4px; }

/* ============ Toast ============ */
.toast {
    position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
    z-index: 200;
    padding: 9px 18px;
    font-size: 13px;
    color: #fff;
    background: rgba(31, 35, 41, 0.92);
    border-radius: var(--radius-sm);
    box-shadow: 0 4px 16px rgba(0,0,0,0.18);
    animation: toast-in 0.25s ease-out;
}
.toast.success { background: rgba(23, 160, 80, 0.95); }
.toast.error { background: rgba(216, 44, 44, 0.95); }
.toast.info { background: rgba(31, 35, 41, 0.92); }
@keyframes toast-in { from { opacity: 0; transform: translate(-50%, -8px); } to { opacity: 1; transform: translate(-50%, 0); } }

/* ============ 响应式 ============ */
@media (max-width: 900px) {
    .sidebar { width: 220px; }
    .message { max-width: 92%; }
    .chat-head { flex-direction: column; align-items: flex-start; }
    .settings-grid { grid-template-columns: 1fr; }
    .modal-wide { width: 94vw; }
}
</style>
"""

start = html.index("<style>")
end = html.rindex("</style>") + len("</style>")
new_html = html[:start] + NEW_CSS + html[end:]

with open(path, "w", encoding="utf-8") as f:
    f.write(new_html)

print("done, total len:", len(new_html))
