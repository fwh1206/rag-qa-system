/* 登录页：支持邮箱/用户名密码登录、邮箱验证码登录，以及邮箱验证码注册。 */

const $ = (id) => document.getElementById(id);
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
let loginMode = "pass";

function saveSession(data) {
    localStorage.setItem("authToken", data.token || "");
    localStorage.setItem("rag_token", data.token || "");
    localStorage.setItem("username", data.username || "");
    localStorage.setItem("role", data.role || "");
}

function showError(id, message) {
    const el = $(id);
    if (!el) return;
    el.textContent = message;
    el.classList.remove("hidden");
}

function showInfo(id, message) {
    const el = $(id);
    if (!el) return;
    el.textContent = message;
    el.classList.remove("hidden");
}

function hideMessages() {
    ["loginError", "loginInfo", "regError", "regInfo", "resetError", "resetInfo"].forEach((id) => {
        const el = $(id);
        if (el) el.classList.add("hidden");
    });
}

function startCodeCountdown(btn) {
    stopCodeCountdown(btn);
    let remaining = 60;
    btn.disabled = true;
    btn.textContent = remaining + "s 后重发";
    btn._timer = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
            stopCodeCountdown(btn);
            btn.disabled = false;
            btn.textContent = "获取验证码";
            return;
        }
        btn.textContent = remaining + "s 后重发";
    }, 1000);
}

function stopCodeCountdown(btn) {
    if (btn._timer) {
        clearInterval(btn._timer);
        btn._timer = null;
    }
}

async function sendCode(email, purpose, btn, infoId, errorId) {
    const value = (email || "").trim().toLowerCase();
    if (!EMAIL_RE.test(value)) {
        showError(errorId, "请输入正确的邮箱地址");
        return;
    }
    btn.disabled = true;
    btn.textContent = "发送中...";
    hideMessages();
    try {
        const data = await api("/auth/send-code", {
            method: "POST",
            body: JSON.stringify({ email: value, purpose }),
        });
        if (data.dev_mode) {
            showInfo(infoId, "开发模式验证码：" + data.dev_code);
        } else {
            showInfo(infoId, data.msg || "验证码已发送");
        }
        startCodeCountdown(btn);
    } catch (e) {
        showError(errorId, e.message);
        btn.disabled = false;
        btn.textContent = "获取验证码";
    }
}

async function doLogin() {
    hideMessages();
    $("loginBtn").disabled = true;
    try {
        let data;
        if (loginMode === "code") {
            const email = $("loginEmail").value.trim().toLowerCase();
            const code = $("loginCode").value.trim();
            if (!EMAIL_RE.test(email)) {
                showError("loginError", "请输入正确的邮箱地址");
                return;
            }
            if (code.length !== 6) {
                showError("loginError", "请输入 6 位验证码");
                return;
            }
            data = await api("/auth/login-code", {
                method: "POST",
                body: JSON.stringify({ email, code }),
            });
        } else {
            const account = $("loginAccount").value.trim();
            const password = $("loginPass").value;
            if (!account || !password) {
                showError("loginError", "请输入邮箱/用户名和密码");
                return;
            }
            data = await api("/auth/login", {
                method: "POST",
                body: JSON.stringify({ username: account, password }),
            });
        }
        saveSession(data);
        window.location.href = "/";
    } catch (e) {
        showError("loginError", e.message);
    } finally {
        $("loginBtn").disabled = false;
    }
}

async function doRegister() {
    hideMessages();
    const email = $("regEmail").value.trim().toLowerCase();
    const code = $("regCode").value.trim();
    const username = $("regUser").value.trim();
    const password = $("regPass").value;
    const confirm = $("regPass2").value;
    if (!EMAIL_RE.test(email)) return showError("regError", "请输入正确的邮箱地址");
    if (code.length !== 6) return showError("regError", "请输入 6 位验证码");
    if (!username) return showError("regError", "请输入用户名");
    if (password.length < 4) return showError("regError", "密码至少需要 4 位");
    if (password !== confirm) return showError("regError", "两次输入的密码不一致");

    $("regBtn").disabled = true;
    try {
        await api("/auth/register", {
            method: "POST",
            body: JSON.stringify({ email, code, username, password }),
        });
        toast("注册成功，正在登录...");
        $("loginAccount").value = email;
        $("loginPass").value = password;
        switchAuthMode("login");
        switchLoginMode("pass");
        await doLogin();
    } catch (e) {
        showError("regError", e.message);
    } finally {
        $("regBtn").disabled = false;
    }
}

async function doResetPassword() {
    hideMessages();
    const email = $("resetEmail").value.trim().toLowerCase();
    const code = $("resetCode").value.trim();
    const password = $("resetPass").value;
    const confirm = $("resetPass2").value;
    if (!EMAIL_RE.test(email)) return showError("resetError", "请输入正确的邮箱地址");
    if (code.length !== 6) return showError("resetError", "请输入 6 位验证码");
    if (password.length < 4) return showError("resetError", "新密码至少需要 4 位");
    if (password !== confirm) return showError("resetError", "两次输入的新密码不一致");

    $("resetBtn").disabled = true;
    try {
        await api("/auth/reset-password", {
            method: "POST",
            body: JSON.stringify({ email, code, new_password: password }),
        });
        toast("密码已重置，请使用新密码登录");
        $("loginAccount").value = email;
        $("loginPass").value = password;
        switchAuthMode("login");
        switchLoginMode("pass");
    } catch (e) {
        showError("resetError", e.message);
    } finally {
        $("resetBtn").disabled = false;
    }
}

function switchLoginMode(mode) {
    loginMode = mode;
    $("passLoginFields").classList.toggle("hidden", mode !== "pass");
    $("codeLoginFields").classList.toggle("hidden", mode !== "code");
    $("passLoginTab").classList.toggle("active", mode === "pass");
    $("codeLoginTab").classList.toggle("active", mode === "code");
    hideMessages();
    if (mode === "pass") $("loginAccount").focus();
    else $("loginEmail").focus();
}

function switchAuthMode(mode) {
    const login = mode === "login";
    const register = mode === "register";
    const reset = mode === "reset";
    $("loginForm").classList.toggle("hidden", !login);
    $("registerForm").classList.toggle("hidden", !register);
    $("resetForm").classList.toggle("hidden", !reset);
    $("loginTabBtn").classList.toggle("active", login);
    $("registerTabBtn").classList.toggle("active", register);
    $("resetTabBtn").classList.toggle("active", reset);
    $("authTitle").textContent = login ? "欢迎回来" : register ? "创建账号" : "找回密码";
    $("authSub").textContent = login
        ? "登录后继续你的知识库问答"
        : register
            ? "使用邮箱验证码注册，登录时支持邮箱或用户名"
            : "输入注册邮箱，通过验证码设置新密码";
    hideMessages();
    if (login) {
        if (loginMode === "pass") $("loginAccount").focus();
        else $("loginEmail").focus();
    } else if (register) {
        $("regEmail").focus();
    } else {
        $("resetEmail").focus();
    }
}

document.addEventListener("DOMContentLoaded", function () {
    if (getAuthToken()) {
        window.location.href = "/";
        return;
    }
    $("loginTabBtn").addEventListener("click", () => switchAuthMode("login"));
    $("registerTabBtn").addEventListener("click", () => switchAuthMode("register"));
    $("resetTabBtn").addEventListener("click", () => switchAuthMode("reset"));
    $("forgotPassLink").addEventListener("click", () => switchAuthMode("reset"));
    $("passLoginTab").addEventListener("click", () => switchLoginMode("pass"));
    $("codeLoginTab").addEventListener("click", () => switchLoginMode("code"));
    $("loginForm").addEventListener("submit", (e) => { e.preventDefault(); doLogin(); });
    $("registerForm").addEventListener("submit", (e) => { e.preventDefault(); doRegister(); });
    $("resetForm").addEventListener("submit", (e) => { e.preventDefault(); doResetPassword(); });
    $("sendLoginCodeBtn").addEventListener("click", () => sendCode($("loginEmail").value, "login", $("sendLoginCodeBtn"), "loginInfo", "loginError"));
    $("sendRegCodeBtn").addEventListener("click", () => sendCode($("regEmail").value, "register", $("sendRegCodeBtn"), "regInfo", "regError"));
    $("sendResetCodeBtn").addEventListener("click", () => sendCode($("resetEmail").value, "reset", $("sendResetCodeBtn"), "resetInfo", "resetError"));
});
