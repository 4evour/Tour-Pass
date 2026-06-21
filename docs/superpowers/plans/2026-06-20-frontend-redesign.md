# Tour Pass 前端重设计实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Tour Pass 从单页顶部导航布局重构为左侧导航栏 + 右侧内容区的应用布局，重点重建 AI 规划页的结构化表单。

**Architecture:** 在现有原生 HTML/CSS/JS 架构上重构。侧边栏作为固定左侧导航，右侧内容区通过 hash 路由切换 6 个页面。翡翠旅途配色通过 CSS 变量统一管理。

**Tech Stack:** 原生 HTML/CSS/JS，Leaflet (地图)，html2canvas (截图)，无新框架依赖。

**Spec:** `docs/superpowers/specs/2026-06-20-frontend-redesign-design.md`

---

### Task 1: 翡翠旅途配色系统

**Files:**
- Modify: `web/styles.css:1-43` (CSS 变量区)

- [ ] **Step 1: 更新 CSS 变量为翡翠旅途配色**

在 `web/styles.css` 的 `:root` 块中替换现有变量为翡翠旅途配色系统：

```css
:root {
  color-scheme: light;
  /* 翡翠旅途 - Emerald Journey */
  --emerald-50: #ecfdf5;
  --emerald-100: #d1fae5;
  --emerald-400: #34d399;
  --emerald-500: #10b981;
  --emerald-600: #059669;
  --emerald-700: #047857;
  --amber-400: #fbbf24;
  --amber-500: #f59e0b;
  /* 语义色映射 */
  --bg: #f8fffe;
  --surface: #ffffff;
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --accent: #059669;
  --accent-dark: #047857;
  --warn: #f59e0b;
  --soft: #ecfdf5;
  --blue-soft: #eaf1f8;
  /* 导航栏 */
  --sidebar-bg: #ffffff;
  --sidebar-active: #ecfdf5;
  --sidebar-active-border: #059669;
  --sidebar-width: 240px;
  /* 通用 */
  --radius: 8px;
  --radius-sm: 4px;
  --radius-lg: 12px;
}
```

同时更新 `[data-theme="dark"]` 和 `@media (prefers-color-scheme: dark)` 块中的暗色变量：

```css
[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0f172a;
  --surface: #1e293b;
  --ink: #f1f5f9;
  --muted: #94a3b8;
  --line: #334155;
  --accent: #34d399;
  --accent-dark: #10b981;
  --warn: #fbbf24;
  --soft: #1e293b;
  --blue-soft: #1a2330;
  --sidebar-bg: #1e293b;
  --sidebar-active: #064e3b;
  --sidebar-active-border: #34d399;
}
```

- [ ] **Step 2: 验证配色生效**

在浏览器中打开页面，确认：
- 背景色为浅绿白色 (#f8fffe)
- 按钮/accent 色为翡翠绿 (#059669)
- 暗色模式切换正常

- [ ] **Step 3: Commit**

```bash
git add web/styles.css
git commit -m "style: update CSS variables to Emerald Journey theme"
```

---

### Task 2: 侧边栏 HTML 结构

**Files:**
- Modify: `web/index.html:65-80` (main app shell 区域)

- [ ] **Step 1: 在 auth overlay 之后、main app-shell 之前插入侧边栏**

在 `web/index.html` 第 64 行 `</div>` (auth overlay 结束) 之后插入：

```html
    <!-- Sidebar Navigation -->
    <nav id="sidebar" class="sidebar" hidden>
      <div class="sidebar-brand">
        <div class="sidebar-logo">🟢</div>
        <span class="sidebar-brand-text">Tour Pass</span>
      </div>

      <div class="sidebar-nav">
        <a href="#/plan" class="sidebar-item active" data-route="plan">
          <span class="sidebar-icon">🤖</span>
          <span class="sidebar-label">AI 规划</span>
        </a>
        <a href="#/trips" class="sidebar-item" data-route="trips">
          <span class="sidebar-icon">📋</span>
          <span class="sidebar-label">我的行程</span>
        </a>
        <a href="#/editor" class="sidebar-item" data-route="editor">
          <span class="sidebar-icon">✏️</span>
          <span class="sidebar-label">行程编辑器</span>
        </a>
        <a href="#/xhs" class="sidebar-item" data-route="xhs">
          <span class="sidebar-icon">📕</span>
          <span class="sidebar-label">小红书解析</span>
          <span class="sidebar-badge">即将上线</span>
        </a>
      </div>

      <div class="sidebar-divider"></div>

      <div class="sidebar-nav">
        <a href="#/profile" class="sidebar-item" data-route="profile">
          <span class="sidebar-icon">👤</span>
          <span class="sidebar-label">个人中心</span>
        </a>
        <a href="#/contact" class="sidebar-item" data-route="contact">
          <span class="sidebar-icon">📧</span>
          <span class="sidebar-label">联系我们</span>
        </a>
      </div>

      <div class="sidebar-footer">
        <div class="sidebar-user" id="sidebarUser">
          <span class="sidebar-user-name" id="sidebarUserName"></span>
        </div>
        <button id="sidebarThemeToggle" class="sidebar-theme-toggle" type="button" title="切换暗色模式">🌙</button>
        <button id="sidebarLogoutBtn" class="sidebar-logout" type="button">退出登录</button>
      </div>
    </nav>
```

- [ ] **Step 2: 将现有 topbar 中的用户控件迁移到侧边栏**

从 `<header class="topbar">` 中移除以下内容（它们现在在侧边栏中）：
- `#themeToggle` 按钮
- `#userBadge`
- `#logoutBtn`
- `#adminLink`
- "个人中心" 链接

保留 `<header class="topbar">` 但简化为页面标题栏：

```html
<header class="topbar">
  <h1 id="pageTitle" class="page-title">AI 智能规划</h1>
  <div class="topbar-right">
    <span class="query-counter" id="queryCounter" title="今日剩余查询次数"></span>
  </div>
</header>
```

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat: add sidebar navigation HTML structure"
```

---

### Task 3: 侧边栏 CSS 样式

**Files:**
- Create: `web/css/sidebar.css`

- [ ] **Step 1: 创建侧边栏样式文件**

```css
/* Sidebar Navigation */
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: var(--sidebar-width, 240px);
  height: 100vh;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  z-index: 100;
  overflow-y: auto;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 16px;
  border-bottom: 1px solid var(--line);
}

.sidebar-logo {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.sidebar-brand-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--ink);
}

.sidebar-nav {
  padding: 8px 0;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  color: var(--muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  border-left: 3px solid transparent;
  transition: all 0.15s ease;
  cursor: pointer;
}

.sidebar-item:hover {
  color: var(--ink);
  background: var(--soft);
}

.sidebar-item.active {
  color: var(--accent);
  background: var(--sidebar-active);
  border-left-color: var(--sidebar-active-border);
  font-weight: 600;
}

.sidebar-icon {
  font-size: 18px;
  width: 24px;
  text-align: center;
  flex-shrink: 0;
}

.sidebar-label {
  flex: 1;
}

.sidebar-badge {
  font-size: 10px;
  padding: 2px 6px;
  background: var(--amber-500);
  color: white;
  border-radius: 10px;
  font-weight: 500;
}

.sidebar-divider {
  height: 1px;
  background: var(--line);
  margin: 4px 16px;
}

.sidebar-footer {
  margin-top: auto;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar-user-name {
  font-size: 13px;
  color: var(--ink);
  font-weight: 500;
}

.sidebar-theme-toggle {
  background: none;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 14px;
  color: var(--muted);
  text-align: center;
}

.sidebar-theme-toggle:hover {
  background: var(--soft);
}

.sidebar-logout {
  background: none;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 13px;
  color: var(--muted);
}

.sidebar-logout:hover {
  color: #dc2626;
  border-color: #dc2626;
}

/* Main content area offset */
.app-shell {
  margin-left: var(--sidebar-width, 240px);
  padding: 24px;
  min-height: 100vh;
}

/* Responsive: tablet */
@media (max-width: 1023px) and (min-width: 768px) {
  :root {
    --sidebar-width: 60px;
  }
  .sidebar-brand-text,
  .sidebar-label,
  .sidebar-badge,
  .sidebar-user-name,
  .sidebar-logout {
    display: none;
  }
  .sidebar-item {
    justify-content: center;
    padding: 12px;
    border-left: none;
    border-bottom: 3px solid transparent;
  }
  .sidebar-item.active {
    border-bottom-color: var(--sidebar-active-border);
    border-left-color: transparent;
  }
  .sidebar-brand {
    justify-content: center;
    padding: 16px 8px;
  }
  .sidebar-footer {
    align-items: center;
  }
}

/* Responsive: mobile */
@media (max-width: 767px) {
  .sidebar {
    transform: translateX(-100%);
    transition: transform 0.25s ease;
  }
  .sidebar.open {
    transform: translateX(0);
  }
  .app-shell {
    margin-left: 0;
  }
  .mobile-menu-btn {
    display: block;
  }
}

.mobile-menu-btn {
  display: none;
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 200;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 8px 12px;
  font-size: 20px;
  cursor: pointer;
}
```

- [ ] **Step 2: 在 index.html 中引入新 CSS 文件**

在 `web/index.html` 的 `<head>` 中添加：

```html
<link rel="stylesheet" href="/css/sidebar.css" />
```

- [ ] **Step 3: 验证侧边栏显示**

打开浏览器确认：
- 侧边栏固定在左侧，宽 240px
- 主内容区自动右移
- 导航项点击有高亮效果

- [ ] **Step 4: Commit**

```bash
git add web/css/sidebar.css web/index.html
git commit -m "style: add sidebar CSS with responsive breakpoints"
```

---

### Task 4: Hash 路由系统

**Files:**
- Modify: `web/app.js` (在文件顶部 state 定义之后添加路由模块)

- [ ] **Step 1: 添加路由模块到 app.js**

在 `web/app.js` 中 `restoreTripState()` 函数之后添加路由系统：

```javascript
// ---- Hash Router ----
const ROUTES = {
  plan:    { title: "AI 智能规划",   panel: "planPanel" },
  trips:   { title: "我的行程",     panel: "tripsPanel" },
  editor:  { title: "行程编辑器",   panel: "editorPanel" },
  xhs:     { title: "小红书解析",   panel: "xhsPanel" },
  profile: { title: "个人中心",     panel: "profilePanel" },
  contact: { title: "联系我们",     panel: "contactPanel" },
};

function getRoute() {
  const hash = location.hash.replace("#/", "") || "plan";
  return ROUTES[hash] ? hash : "plan";
}

function navigateTo(route) {
  location.hash = `#/${route}`;
}

function applyRoute() {
  const route = getRoute();
  const config = ROUTES[route];

  // Update sidebar active state
  document.querySelectorAll(".sidebar-item").forEach(el => {
    el.classList.toggle("active", el.dataset.route === route);
  });

  // Update page title
  const titleEl = document.getElementById("pageTitle");
  if (titleEl) titleEl.textContent = config.title;

  // Show/hide panels
  document.querySelectorAll("[data-panel]").forEach(el => {
    el.hidden = el.dataset.panel !== config.panel;
  });

  // Special: editor panel loads iframe
  if (route === "editor") {
    loadEditorPanel();
  }

  // Close mobile sidebar
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.classList.remove("open");
}

window.addEventListener("hashchange", applyRoute);
```

- [ ] **Step 2: 将现有内容区包裹在路由面板中**

在 `web/index.html` 中，将现有 `<main class="app-shell">` 内部内容包裹在 `data-panel="planPanel"` 容器中，并添加其他面板：

```html
<main class="app-shell" id="mainApp" hidden>
  <!-- Page title bar -->
  <header class="topbar">
    <h1 id="pageTitle" class="page-title">AI 智能规划</h1>
    <div class="topbar-right">
      <span class="query-counter" id="queryCounter" title="今日剩余查询次数"></span>
    </div>
  </header>

  <!-- Route panels -->
  <div data-panel="planPanel">
    <!-- 现有 chat-hero + result-area 内容移入此处 -->
  </div>

  <div data-panel="tripsPanel" hidden>
    <div id="tripsList" class="trips-list"></div>
  </div>

  <div data-panel="editorPanel" hidden>
    <iframe id="editorIframe" class="editor-iframe" src="about:blank"></iframe>
  </div>

  <div data-panel="xhsPanel" hidden>
    <div class="placeholder-page">
      <div class="placeholder-icon">📕</div>
      <h2>小红书解析</h2>
      <p>功能开发中，敬请期待</p>
    </div>
  </div>

  <div data-panel="profilePanel" hidden>
    <!-- 现有 profileView 内容移入此处 -->
  </div>

  <div data-panel="contactPanel" hidden>
    <!-- 联系我们表单 -->
  </div>
</main>
```

- [ ] **Step 3: 在登录成功后初始化路由**

在 app.js 的登录成功回调中调用 `applyRoute()`，并显示侧边栏：

```javascript
// 登录成功后
document.getElementById("sidebar").hidden = false;
applyRoute();
```

- [ ] **Step 4: 验证路由切换**

在浏览器中点击侧边栏各项，确认：
- URL hash 变化 (#/plan, #/trips 等)
- 内容区正确切换
- 侧边栏高亮跟随
- 浏览器前进/后退正常

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat: add hash router with 6 route panels"
```

---

### Task 5: AI 规划结构化表单

**Files:**
- Create: `web/css/plan-form.css`
- Modify: `web/index.html` (planPanel 内部)
- Modify: `web/app.js` (表单处理逻辑)

- [ ] **Step 1: 创建 plan-form.css 样式文件**

创建 `web/css/plan-form.css`，包含结构化表单所有样式：城市卡片网格、数字按钮组、chip 按钮组、滑块、tag input 等。核心样式约 300 行。

关键样式：
- `.plan-form` — 表单容器，max-width 720px
- `.city-grid` — 4 列网格
- `.city-card` — 城市卡片，选中态绿色边框
- `.day-buttons` — 天数圆形按钮组
- `.chip-group` — chip 容器 (flex wrap)
- `.chip` — 单个 chip，选中态绿色背景
- `.range-slider` — 双滑块容器
- `.tag-input` — tag 输入容器
- `.tag` — 已选 tag 标签
- `.submit-btn` — 翡翠绿渐变提交按钮

- [ ] **Step 2: 在 index.html planPanel 中添加结构化表单 HTML**

在 planPanel 内，在现有 chat-hero 之前添加结构化表单区域。使用 tab 切换"结构化表单"和"自然语言"两种模式。

表单包含 spec 中定义的全部 9 个字段：城市、天数、人群、侧重、节奏、预算、酒店预算、必去景点、特殊要求。

- [ ] **Step 3: 在 app.js 中添加表单处理逻辑**

添加以下功能：
- 城市卡片从 `/cities` API 动态加载
- 表单数据收集 → 调用现有 plan API
- 城市搜索自动补全 (tag input)
- 表单验证（城市必选）
- 提交按钮状态管理

- [ ] **Step 4: 验证表单交互**

- 城市卡片正确显示并可点击选中
- 天数/人群/侧重/节奏/预算 chip 正常切换
- 酒店预算双滑块正常工作
- 必去景点 tag input 自动补全
- 提交后正确调用 API 并显示结果

- [ ] **Step 5: Commit**

```bash
git add web/css/plan-form.css web/index.html web/app.js
git commit -m "feat: add structured plan form with city cards and chip inputs"
```

---

### Task 6: 我的行程页面

**Files:**
- Modify: `web/index.html` (tripsPanel)
- Modify: `web/app.js`
- Modify: `web/styles.css` 或 `web/css/plan-form.css`

- [ ] **Step 1: 实现行程列表页面**

将现有 profileView 中的 `#pvTripList` 行程列表逻辑提取到 tripsPanel。

添加"导入到编辑器"按钮，点击后跳转到 `#/editor?tripId=xxx`。

- [ ] **Step 2: 添加行程列表样式**

行程卡片样式：白色卡片 + 阴影 + 城市标签 + 日期 + 操作按钮（查看/编辑/删除/导入编辑器）。

- [ ] **Step 3: 验证**

- 行程列表正确加载
- "导入到编辑器"跳转到编辑器页面并传递 tripId

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/app.js web/styles.css
git commit -m "feat: add My Trips page with import-to-editor"
```

---

### Task 7: 编辑器集成与导入功能

**Files:**
- Modify: `web/app.js` (loadEditorPanel 函数)

- [ ] **Step 1: 实现编辑器 iframe 加载**

```javascript
function loadEditorPanel() {
  const iframe = document.getElementById("editorIframe");
  if (!iframe) return;
  const tripId = new URLSearchParams(location.hash.split("?")[1] || "").get("tripId");
  const src = tripId ? `/editor/index.html?tripId=${tripId}` : "/editor/index.html";
  if (iframe.src !== new URL(src, location.origin).href) {
    iframe.src = src;
  }
}
```

- [ ] **Step 2: 添加 editor-iframe 样式**

```css
.editor-iframe {
  width: 100%;
  height: calc(100vh - 80px);
  border: none;
  border-radius: var(--radius);
}
```

- [ ] **Step 3: 验证**

- 点击侧边栏"行程编辑器"正确加载编辑器
- 从"我的行程"导入行程时，编辑器加载对应行程

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/styles.css
git commit -m "feat: integrate editor via iframe with trip import"
```

---

### Task 8: 联系我们页面 + 小红书占位

**Files:**
- Modify: `web/index.html` (contactPanel)

- [ ] **Step 1: 添加联系我们表单**

将现有 feedbackModal 的内容迁移到 contactPanel 中，作为独立的联系页面。

表单字段：分类 (Bug/功能建议/体验问题/其他)、内容、联系方式。

- [ ] **Step 2: 确认小红书占位页**

xhsPanel 已在 Task 4 中创建了 placeholder，确认显示"功能开发中，敬请期待"。

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat: add Contact page and XHS placeholder"
```

---

### Task 9: 响应式适配与最终测试

**Files:**
- Modify: `web/css/sidebar.css` (已在 Task 3 包含响应式规则)
- Modify: `web/index.html` (添加移动端汉堡菜单按钮)

- [ ] **Step 1: 添加移动端汉堡菜单按钮**

在 `<main class="app-shell">` 之前添加：

```html
<button id="mobileMenuBtn" class="mobile-menu-btn" type="button" hidden>☰</button>
```

在 app.js 中添加点击事件：

```javascript
document.getElementById("mobileMenuBtn")?.addEventListener("click", () => {
  document.getElementById("sidebar")?.classList.toggle("open");
});
```

- [ ] **Step 2: 全功能回归测试**

- 桌面端 (≥1024px)：侧边栏 240px + 内容区正常
- 平板端 (768-1023px)：侧边栏折叠为图标模式
- 移动端 (<768px)：汉堡菜单触发侧边栏滑出
- 所有 6 个导航项路由正常
- AI 规划表单所有控件正常
- 暗色模式切换正常
- 行程编辑器 iframe 正常

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat: responsive sidebar + final integration"
```
