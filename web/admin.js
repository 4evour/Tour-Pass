// Tour Pass Admin Panel
async function api(path, opts = {}) {
  const token = localStorage.getItem("tp_token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(path, { headers, ...opts });
  const data = await res.json();
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem("tp_token");
      throw new Error("登录已过期，请返回首页重新登录");
    }
    throw new Error(data.error?.message || "请求失败");
  }
  return data;
}

// ---- Init ----
async function init() {
  if (!localStorage.getItem("tp_token")) { showLoginError(); return; }
  try {
    const me = await api("/auth/me");
    if (me.role !== "admin") { showLoginError(); return; }
    document.getElementById("adminUser").textContent = me.username;
    document.getElementById("adminContent").hidden = false;
    loadDashboard();
  } catch { showLoginError(); }
}

function showLoginError() {
  document.getElementById("adminLogin").hidden = false;
}

// ---- Tab navigation ----
document.querySelectorAll(".admin-nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".admin-nav button").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".admin-section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("sec-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "dashboard") loadDashboard();
    if (btn.dataset.tab === "users") loadUsers();
    if (btn.dataset.tab === "feedback") loadFeedback();
  });
});

// ---- Dashboard ----
async function loadDashboard() {
  try {
    const stats = await api("/admin/stats");
    document.getElementById("statsGrid").innerHTML = `
      <div class="stat-card"><div class="num">${stats.total_users || 0}</div><div class="label">总用户数</div></div>
      <div class="stat-card"><div class="num">${stats.today_active_users || 0}</div><div class="label">今日活跃</div></div>
      <div class="stat-card"><div class="num">${stats.total_queries || 0}</div><div class="label">总查询量</div></div>
      <div class="stat-card"><div class="num">${stats.pending_feedback || 0}</div><div class="label">待处理反馈</div></div>
    `;
    // Load chart data
    const chartData = await api("/admin/query-stats?days=14");
    drawChart(chartData.data || []);
  } catch (e) {
    document.getElementById("statsGrid").innerHTML = `<div class="admin-error">加载失败：${e.message}</div>`;
  }
}

function drawChart(data) {
  const canvas = document.getElementById("queryChart");
  if (!canvas || !data.length) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const W = rect.width, H = rect.height;
  const pad = { top: 20, right: 20, bottom: 30, left: 40 };
  const chartW = W - pad.left - pad.right;
  const chartH = H - pad.top - pad.bottom;

  const maxVal = Math.max(1, ...data.map(d => d.total_queries || 0));
  const stepX = chartW / Math.max(1, data.length - 1);

  // Grid
  ctx.strokeStyle = "#e0e0e0";
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (chartH / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
    ctx.fillStyle = "#999"; ctx.font = "11px sans-serif"; ctx.textAlign = "right";
    ctx.fillText(Math.round(maxVal * (4 - i) / 4), pad.left - 6, y + 4);
  }

  // Line
  ctx.beginPath();
  ctx.strokeStyle = "#146b5d";
  ctx.lineWidth = 2;
  data.forEach((d, i) => {
    const x = pad.left + i * stepX;
    const y = pad.top + chartH - ((d.total_queries || 0) / maxVal) * chartH;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Fill
  ctx.lineTo(pad.left + (data.length - 1) * stepX, pad.top + chartH);
  ctx.lineTo(pad.left, pad.top + chartH);
  ctx.closePath();
  ctx.fillStyle = "rgba(20, 107, 93, 0.1)";
  ctx.fill();

  // Labels
  ctx.fillStyle = "#999"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  data.forEach((d, i) => {
    const x = pad.left + i * stepX;
    const label = (d.date || "").slice(5); // MM-DD
    if (i % Math.ceil(data.length / 7) === 0 || i === data.length - 1) {
      ctx.fillText(label, x, H - 8);
    }
    // Dot
    const y = pad.top + chartH - ((d.total_queries || 0) / maxVal) * chartH;
    ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fillStyle = "#146b5d"; ctx.fill();
  });
}

// ---- Users ----
async function loadUsers() {
  try {
    const data = await api("/admin/users?limit=100");
    const tbody = document.getElementById("usersTable");
    tbody.innerHTML = (data.data || []).map(u => `
      <tr>
        <td>${u.id}</td>
        <td>${escHtml(u.username)}</td>
        <td><span class="fb-badge ${u.role === 'admin' ? 'reviewed' : u.role === 'guest' ? '' : 'resolved'}">${u.role}</span></td>
        <td>${u.total_queries || 0}</td>
        <td>${(u.created_at || "").replace("T"," ").slice(0, 16)}</td>
        <td>
          ${u.role !== 'admin' ? `<button class="promote-btn" data-user-id="${u.id}" data-role="admin" style="padding:3px 8px;border:1px solid var(--accent);border-radius:4px;background:transparent;cursor:pointer;font-size:11px;color:var(--accent);">设为管理员</button>` : `<button class="promote-btn" data-user-id="${u.id}" data-role="user" style="padding:3px 8px;border:1px solid #c0392b;border-radius:4px;background:transparent;cursor:pointer;font-size:11px;color:#c0392b;">取消管理员</button>`}
        </td>
      </tr>
    `).join("") || '<tr><td colspan="6" style="text-align:center;color:var(--muted);">暂无用户</td></tr>';
  } catch (e) {
    document.getElementById("usersTable").innerHTML = `<tr><td colspan="6">加载失败：${e.message}</td></tr>`;
  }
}

async function promoteUser(userId, newRole) {
  if (!confirm(`确定要将用户 #${userId} 的角色改为 ${newRole} 吗？`)) return;
  try {
    await api(`/admin/users/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role: newRole }) });
    loadUsers();
  } catch (e) { alert("操作失败：" + e.message); }
}

// ---- Feedback ----
let currentFbStatus = "";

async function loadFeedback(status) {
  if (status !== undefined) currentFbStatus = status;
  try {
    const url = "/admin/feedback?limit=50" + (currentFbStatus ? "&status=" + currentFbStatus : "");
    const data = await api(url);
    const list = document.getElementById("feedbackList");
    list.innerHTML = (data.data || []).map(fb => `
      <div class="fb-item" data-id="${fb.id}">
        <div class="fb-item-header">
          <strong>${escHtml(fb.category)} — ${escHtml(fb.username || "匿名")}</strong>
          <span class="fb-badge ${fb.status}">${statusLabel(fb.status)}</span>
        </div>
        <div class="fb-content">${escHtml(fb.content)}</div>
        <div class="fb-meta">${(fb.created_at || "").slice(0, 16)}${fb.contact ? " · 联系：" + escHtml(fb.contact) : ""}</div>
        ${fb.admin_reply ? `<div class="fb-content" style="color:var(--accent);">管理员回复：${escHtml(fb.admin_reply)}</div>` : ""}
        <div class="fb-reply">
          <input placeholder="管理员回复..." value="${escHtml(fb.admin_reply || "")}" />
          <button class="fb-action-btn" data-fb-id="${fb.id}" data-status="reviewed">已查看</button>
          <button class="fb-action-btn" data-fb-id="${fb.id}" data-status="resolved" style="background:var(--accent);color:#fff;">已解决</button>
        </div>
      </div>
    `).join("") || '<div class="admin-error">暂无反馈</div>';
  } catch (e) {
    document.getElementById("feedbackList").innerHTML = `<div class="admin-error">加载失败：${e.message}</div>`;
  }
}

async function updateFeedback(id, status, btn) {
  const replyInput = btn.parentElement.querySelector("input");
  const reply = replyInput ? replyInput.value.trim() : "";
  try {
    await api(`/admin/feedback/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status, admin_reply: reply }),
    });
    loadFeedback();
  } catch (e) { alert("更新失败：" + e.message); }
}

// Feedback filter buttons
document.querySelectorAll("#fbFilter button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#fbFilter button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    loadFeedback(btn.dataset.status);
  });
});

function statusLabel(s) {
  return { pending: "待处理", reviewed: "已查看", resolved: "已解决" }[s] || s;
}

function escHtml(t) {
  const d = document.createElement("div"); d.textContent = t || ""; return d.innerHTML;
}

// Event delegation for dynamically rendered buttons (CSP-safe)
document.addEventListener("click", (e) => {
  const promoteBtn = e.target.closest(".promote-btn");
  if (promoteBtn) {
    promoteUser(promoteBtn.dataset.userId, promoteBtn.dataset.role);
    return;
  }
  const fbBtn = e.target.closest(".fb-action-btn");
  if (fbBtn) {
    updateFeedback(fbBtn.dataset.fbId, fbBtn.dataset.status, fbBtn);
    return;
  }
});

document.getElementById("adminLogoutBtn")?.addEventListener("click", () => {
  localStorage.removeItem("tp_token");
  window.location.href = "/";
});

init();
