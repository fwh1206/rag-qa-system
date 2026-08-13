"""index.html 多页面化改造：引用 app.css、插入顶部导航、包 app-body 布局层。"""
import re

path = r"C:\Users\wang0\Documents\rag问答系统\static\index.html"
with open(path, encoding="utf-8") as f:
    html = f.read()

# 1. 替换内联 <style>...</style> 为外部样式引用
m = re.search(r"<style>.*?</style>", html, re.DOTALL)
assert m, "未找到 <style> 块"
html = html.replace(
    m.group(0),
    '    <link rel="stylesheet" href="/static/css/app.css">  <!-- 公共样式 -->',
)

# 2. body 标签加 data-page 标识
html = html.replace(
    "<body>  <!-- 页面主体开始 -->",
    '<body data-page="chat">  <!-- 页面主体开始（多页：chat/kb/stats/history/settings） -->',
)

# 3. body 开头插入顶部导航，并包一层 .app-body 承载 sidebar+main
m = re.search(r"<body[^>]*>", html)
assert m
body_open_end = m.end()
nav_html = (
    '\n    <nav class="topnav"></nav>  <!-- 顶部导航（由页面脚本渲染） -->\n'
    '    <div class="app-body">  <!-- 侧边栏 + 主内容区 -->\n'
)
html = html[:body_open_end] + nav_html + html[body_open_end:]

# 4. 在 </body> 前闭合 .app-body
html = html.replace(
    "\n</body>",
    '\n    </div>  <!-- app-body 结束 -->\n</body>',
)

# 5. 登录成功后同步写入 authToken / username 键（供其他页面 common.js 使用）
html = html.replace(
    'localStorage.setItem("rag_token", authToken);  // 持久化 token',
    'localStorage.setItem("rag_token", authToken);  // 持久化 token\n'
    '                localStorage.setItem("authToken", authToken);  // 同步键（多页通用）\n'
    '                localStorage.setItem("username", username);  // 同步用户名（多页通用）',
)

# 6. 退出登录时清理两套键
html = html.replace(
    'localStorage.removeItem("rag_token");  // 删除本地 token',
    'localStorage.removeItem("rag_token");  // 删除本地 token\n'
    '            localStorage.removeItem("authToken");  // 同步清理\n'
    '            localStorage.removeItem("username");  // 同步清理',
)

# 7. 页面加载时：若已有 token，渲染导航栏（内联实现，避免依赖 common.js 的键冲突）
nav_script = (
    "\n        // ===== 多页导航渲染（内联） =====\n"
    "        function renderTopNav() {\n"
    "            const pages = [\n"
    '                { id: "chat", href: "/index.html", label: "对话工作台" },\n'
    '                { id: "kb", href: "/kb.html", label: "知识库" },\n'
    '                { id: "stats", href: "/stats.html", label: "数据统计" },\n'
    '                { id: "history", href: "/history.html", label: "历史记录" },\n'
    '                { id: "settings", href: "/settings.html", label: "系统设置" },\n'
    "            ];\n"
    "            const nav = document.querySelector(\".topnav\");\n"
    "            if (!nav) return;\n"
    "            const links = pages.map(function (p) {\n"
    '                return \'<a class="nav-link\' + (p.id === "chat" ? " active" : "") + \'" href="\' + p.href + \'">\' + p.label + "</a>";\n'
    "            }).join(\"\");\n"
    "            const user = (localStorage.getItem(\"username\") || \"\").replace(/[<>&\"]/g, \"\");\n"
    '            nav.innerHTML = \'<div class="nav-brand"><div class="brand-mark">知</div><span>智答工作台</span></div>\' +\n'
    '                \'<div class="nav-links">\' + links + \'</div>\' +\n'
    '                \'<div class="nav-user"><span class="user-chip">\' + user + \'</span>\' +\n'
    '                \'<button class="btn" onclick="doLogout()">退出</button></div>\';\n'
    "        }\n"
    "        if (localStorage.getItem(\"rag_token\")) renderTopNav();\n"
    "\n"
)
html = html.replace(
    '        let authToken = localStorage.getItem("rag_token") || "";  // 从本地存储读取登录 token',
    nav_script
    + '        let authToken = localStorage.getItem("rag_token") || "";  // 从本地存储读取登录 token',
)

with open(path, "w", encoding="utf-8") as f:
    f.write(html)
print("index.html 改造完成，长度:", len(html))
