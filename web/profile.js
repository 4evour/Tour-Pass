const token = localStorage.getItem("tp_token");
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(path, { headers, ...opts });
  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { if (!res.ok) throw new Error("服务返回了无法解析的响应"); }
  }
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem("tp_token");
      throw new Error("登录已过期，请返回首页重新登录");
    }
    throw new Error(data?.error?.message || "请求失败 (" + res.status + ")");
  }
  return data;
}
function esc(t) { const d = document.createElement("div"); d.textContent = t || ""; return d.innerHTML; }

async function init() {
  if (!token) { document.getElementById("profileError").hidden = false; return; }
  try {
    const me = await api("/auth/me");
    document.getElementById("profileContent").hidden = false;

    document.getElementById("pUsername").textContent = me.username;
    document.getElementById("pEmail").textContent = me.email || "未绑定";
    document.getElementById("pId").textContent = me.id;
    var roleLabels = {user:"普通用户", guest:"游客", admin:"管理员"};
    var roleEl = document.getElementById("pRole");
    roleEl.innerHTML = '<span class="role-badge ' + me.role + '">' + (roleLabels[me.role] || me.role) + '</span>';
    document.getElementById("pCreated").textContent = (me.created_at || "").replace("T", " ").slice(0, 19);

    var limit = me.role === "guest" ? 3 : me.role === "admin" ? 999 : 10;
    var remaining = me.query_remaining || 0;
    var used = Math.max(0, limit - remaining);
    var pct = limit < 100 ? Math.min(100, (used / limit) * 100) : 0;
    var circumference = 176;
    var offset = circumference - (pct / 100) * circumference;
    var ring = document.getElementById("usageRing");
    ring.style.strokeDashoffset = offset;
    ring.style.stroke = remaining <= 3 ? "#c0392b" : "var(--accent)";
    document.getElementById("usageNum").textContent = remaining;
    var detail = document.getElementById("usageDetail");
    detail.innerHTML = me.role === "admin"
      ? '<strong>管理员</strong>，查询次数无限制'
      : '今日已用 <strong>' + used + '</strong> / ' + limit + ' 次<br>剩余 <strong class="' + (remaining <= 3 ? 'warn' : '') + '">' + remaining + '</strong> 次' + (remaining <= 3 ? ' ⚠️ 快用完了' : '');

    if (me.role === "guest") {
      document.getElementById("guestBanner").hidden = false;
      document.getElementById("changePwdCard").hidden = true;
      document.getElementById("dangerZone").hidden = false;
    }
    if (me.role === "admin") {
      document.getElementById("adminQuickLink").hidden = false;
    }
  } catch (e) {
    document.getElementById("profileError").hidden = false;
    console.error("Profile load error:", e);
  }

  // Load trips
  try {
    var trips = await api("/trips/list");
    if (trips.data && trips.data.length > 0) {
      var cityEmojis = {"长沙":"🏙","武汉":"🌉","大理":"🏔","丽江":"🏘","南京":"🏛","苏州":"🏡","北京":"🏯","成都":"🐼","重庆":"🔥","杭州":"🌊","西安":"🏛","上海":"🌃","广州":"🌺","深圳":"💎","厦门":"🏖","青岛":"🌊"};
      document.getElementById("tripList").innerHTML = trips.data.map(function(t) {
        var title = t.title || "未命名行程";
        var city = title.split("·")[0] || "";
        var emoji = cityEmojis[city] || "✈️";
        var date = (t.created_at||"").replace("T"," ").slice(0,16);
        var shareBtn = t.share_id
          ? '<button class="trip-btn" onclick="copyShareLink(\'' + t.share_id + '\', this)">📋 复制链接</button>'
          : '<button class="trip-btn" onclick="shareTrip(' + t.id + ')">🔗 分享</button>';
        return '<div class="trip-item">' +
          '<div class="trip-emoji">' + emoji + '</div>' +
          '<div class="trip-info">' +
            '<div class="trip-title">' + esc(title) + '</div>' +
            '<div class="trip-date">🕐 ' + date + '</div>' +
          '</div>' +
          '<div class="trip-actions">' + shareBtn + '</div>' +
        '</div>';
      }).join("");
    } else {
      document.getElementById("tripList").innerHTML =
        '<div class="empty-state-box"><div class="emoji">📂</div>' +
        '<p><strong>还没有保存过行程</strong></p>' +
        '<p><a href="/">去规划你的第一个行程</a></p></div>';
    }
  } catch (e) {
    console.error("Trip load error:", e);
    document.getElementById("tripList").innerHTML =
      '<div class="empty-state-box"><div class="emoji">⚠️</div>' +
      '<p><strong>加载行程失败</strong></p>' +
      '<p style="color:#c0392b">' + esc(e.message) + '</p>' +
      '<p><a href="/">返回首页重新登录</a></p></div>';
  }
}

function copyShareLink(shareId, btn) {
  navigator.clipboard.writeText(location.origin + '/s/' + shareId).then(function() {
    btn.textContent = '已复制!';
    setTimeout(function() { btn.textContent = '复制链接'; }, 2000);
  });
}

async function shareTrip(tripId) {
  try {
    var data = await api("/trips/" + tripId + "/share", { method: "POST", body: JSON.stringify({}) });
    var url = location.origin + data.share_url;
    try { await navigator.clipboard.writeText(url); } catch {}
    var msgEl = document.getElementById("shareMsg");
    msgEl.hidden = false;
    msgEl.textContent = "分享链接已复制";
    setTimeout(function() { msgEl.hidden = true; }, 2500);
    init();
  } catch (e) {
    var msgEl = document.getElementById("shareMsg");
    msgEl.hidden = false;
    msgEl.textContent = "分享失败：" + e.message;
    msgEl.className = "msg-err";
    setTimeout(function() { msgEl.hidden = true; msgEl.className = "msg-ok"; }, 3500);
  }
}

document.getElementById("changePwdBtn").addEventListener("click", async function() {
  var oldPwd = document.getElementById("oldPwd").value;
  var newPwd = document.getElementById("newPwd").value;
  var confirmPwd = document.getElementById("confirmPwd").value;
  var msg = document.getElementById("pwdMsg");
  msg.hidden = true;
  if (newPwd !== confirmPwd) { msg.textContent = "两次输入的密码不一致"; msg.className = "msg-err"; msg.hidden = false; return; }
  if (newPwd.length < 6) { msg.textContent = "新密码至少6位"; msg.className = "msg-err"; msg.hidden = false; return; }
  try {
    await api("/auth/password", { method: "PATCH", body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }) });
    msg.textContent = "✅ 密码修改成功！"; msg.className = "msg-ok"; msg.hidden = false;
    document.getElementById("oldPwd").value = "";
    document.getElementById("newPwd").value = "";
    document.getElementById("confirmPwd").value = "";
  } catch (e) { msg.textContent = e.message; msg.className = "msg-err"; msg.hidden = false; }
});

document.getElementById("logoutLink").addEventListener("click", function(e) {
  e.preventDefault();
  localStorage.removeItem("tp_token");
  location.href = "/";
});

init();
