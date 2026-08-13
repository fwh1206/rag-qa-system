/* ============ 公共 JS：登录态 / API 封装 / 导航 / 工具 ============ */

const API_PREFIX = "";

function sessionStorageKey() {
    const u = localStorage.getItem("username") || "guest";
    return "rag_session_" + u;
}

function getAuthToken() {
    return localStorage.getItem("authToken") || localStorage.getItem("rag_token") || "";
}

function getUsername() {
    return localStorage.getItem("username") || "";
}

function getUserRole() {
    return localStorage.getItem("role") || "";
}

/* 轻提示 */
function toast(msg, type = "success") {
    const old = document.querySelector(".toast");
    if (old) old.remove();
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2600);
}

/* 统一请求封装 */
async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
        headers.set("Content-Type", "application/json");
    }
    const token = getAuthToken();
    if (token) headers.set("X-Auth-Token", token);
    const resp = await fetch(API_PREFIX + path, { ...options, headers });
    const isAuthAttempt = path === "/auth/login" || path === "/auth/register";
    if (resp.status === 401 && !isAuthAttempt) {
        localStorage.removeItem("authToken");
        localStorage.removeItem("rag_token");
        localStorage.removeItem("username");
        localStorage.removeItem("role");
        window.location.href = "/login";
        throw new Error("未登录或登录已过期");
    }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || "请求失败 (" + resp.status + ")");
    return data;
}

/* 文件大小格式化 */
function formatSize(size) {
    if (size == null) return "-";
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
    return (size / 1024 / 1024).toFixed(2) + " MB";
}

/* HTML 转义，防 XSS */
function escapeHtml(value) {
    return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/* 时间格式化 */
function formatTime(ts) {
    if (!ts) return "-";
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/* 渲染顶部导航栏，active 为当前页标识 */
function renderNav(active) {
    const pages = [
        { id: "chat", href: "/", label: "对话工作台", icon: "M8 10h8M8 14h5M21 12a9 9 0 1 1-9-9" },
        { id: "kb", href: "/kb", label: "知识库", icon: "M4 7h16M4 12h16M4 17h10" },
        { id: "stats", href: "/stats", label: "数据统计", icon: "M4 20V10M10 20V4M16 20v-8M22 20H2" },
        { id: "history", href: "/history", label: "历史记录", icon: "M12 8v4l3 3M21 12a9 9 0 1 1-9-9" },
        { id: "profile", href: "/profile", label: "个人中心", icon: "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8" },
        { id: "settings", href: "/settings", label: "系统设置", icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" },
    ];
    const nav = document.querySelector(".topnav");
    if (!nav) return;
    const links = pages
        .map(
            (p) =>
                `<a class="nav-link ${p.id === active ? "active" : ""}" href="${p.href}">` +
                `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="15" height="15"><path d="${p.icon}"/></svg>` +
                `${p.label}</a>`
        )
        .join("");
    const loggedIn = !!getAuthToken();
    const userHtml = loggedIn
        ? `<div class="nav-user">` +
          `<div class="user-menu" id="userMenu">` +
          `<button class="user-trigger" type="button" onclick="toggleUserMenu(event)">` +
          `<span class="user-avatar">${escapeHtml((getUsername() || "U").slice(0, 1).toUpperCase())}</span>` +
          `<span class="user-chip">${escapeHtml(getUsername())}</span>` +
          `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="m6 9 6 6 6-6"/></svg>` +
          `</button>` +
          `<div class="user-dropdown hidden" id="userDropdown">` +
          `<div class="user-drop-label">账号</div>` +
          `<a href="/profile">个人中心</a>` +
          `<a href="/settings">系统设置</a>` +
          `<a href="/history">历史记录</a>` +
          `<div class="user-drop-divider"></div>` +
          `<button type="button" onclick="doLogout()">退出登录</button>` +
          `</div></div></div>`
        : `<div class="nav-user"><a class="btn" href="/login">登录</a></div>`;
    nav.innerHTML =
        `<div class="nav-brand"><div class="brand-mark">知</div><span>智答工作台</span></div>` +
        `<div class="nav-links">${links}</div>` +
        userHtml;
}

window.toggleUserMenu = function (e) {
    if (e) e.stopPropagation();
    const dd = document.getElementById("userDropdown");
    const menu = document.getElementById("userMenu");
    if (!dd || !menu) return;
    dd.classList.toggle("hidden");
    menu.classList.toggle("open", !dd.classList.contains("hidden"));
};

document.addEventListener("click", function (e) {
    const dd = document.getElementById("userDropdown");
    const menu = document.getElementById("userMenu");
    if (dd && !e.target.closest(".user-menu")) dd.classList.add("hidden");
    if (menu && !e.target.closest(".user-menu")) menu.classList.remove("open");
});

/* 退出登录 */
async function doLogout() {
    try {
        await api("/auth/logout", { method: "POST" });
    } catch (e) { /* ignore */ }
    localStorage.removeItem("authToken");
    localStorage.removeItem("rag_token");
    localStorage.removeItem("username");
    localStorage.removeItem("role");
    window.location.href = "/login";
}

/* 页面级鉴权：未登录跳转登录页 */
async function requireAuth(redirect = "/login") {
    if (!getAuthToken()) {
        window.location.href = redirect;
        return false;
    }
    try {
        const me = await api("/auth/me");
        if (me && me.username) {
            localStorage.setItem("role", me.role || "");
            return me;
        }
        return false;
    } catch (e) {
        localStorage.removeItem("authToken");
        localStorage.removeItem("rag_token");
        localStorage.removeItem("role");
        window.location.href = redirect;
        return false;
    }
}

/* 初始化公共导航（每个页面 body 内需含 <nav class="topnav"></nav>） */
document.addEventListener("DOMContentLoaded", function () {
    renderNav(document.body.dataset.page || "chat");
});
