const TOKEN_KEY = "qic_rag_token";

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const sourcesEl = $("#sources");

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
function setToken(t) {
  localStorage.setItem(TOKEN_KEY, t);
}
function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` };
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(opts.headers || {}) },
  });
  if (res.status === 401) {
    clearToken();
    showLogin();
    throw new Error("Unauthorized");
  }
  return res;
}

function showLogin() {
  $("#login").classList.remove("hidden");
  $("#app").classList.add("hidden");
}
function showApp() {
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  refreshStatus();
}

$("#login-btn").addEventListener("click", async () => {
  const t = $("#token-input").value.trim();
  if (!t) return;
  setToken(t);
  const r = await fetch("/api/status", { headers: authHeaders() });
  if (r.ok) {
    showApp();
  } else {
    $("#login-error").textContent = "Invalid token.";
    clearToken();
  }
});

$("#logout").addEventListener("click", () => {
  clearToken();
  showLogin();
});

$("#reindex").addEventListener("click", async () => {
  if (!confirm("Recrawl both sites and rebuild the index? This can take a while.")) return;
  await api("/api/ingest?background=true", { method: "POST" });
  alert("Reindex started in background.");
  setTimeout(refreshStatus, 2000);
});

async function refreshStatus() {
  try {
    const r = await api("/api/status");
    if (!r.ok) return;
    const data = await r.json();
    $("#chunk-count").textContent = data.chunks;
    $("#source-count").textContent = data.sources;
    const last = data.last_ingest?.finished_at;
    $("#last-run").textContent = last ? new Date(last * 1000).toLocaleString() : "never";
  } catch (e) {
    /* ignore */
  }
}

function addMessage(role, content) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = content;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function renderSources(sources) {
  sourcesEl.innerHTML = "";
  for (const s of sources) {
    const li = document.createElement("li");
    li.value = s.n;
    const a = document.createElement("a");
    a.href = s.url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = s.title || s.url;
    li.appendChild(a);
    if (s.page_start) {
      const span = document.createElement("span");
      span.className = "ext";
      span.textContent = s.page_end && s.page_end !== s.page_start ? `pp.${s.page_start}–${s.page_end}` : `p.${s.page_start}`;
      li.appendChild(document.createTextNode(" "));
      li.appendChild(span);
    }
    if (s.is_external) {
      const span = document.createElement("span");
      span.className = "ext";
      span.textContent = "external";
      li.appendChild(document.createTextNode(" "));
      li.appendChild(span);
    }
    sourcesEl.appendChild(li);
  }
}

const history = [];

$("#composer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $("#input");
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  addMessage("user", q);
  history.push({ role: "user", content: q });
  const assistantEl = addMessage("assistant", "");
  let buf = "";

  const res = await api("/api/chat", {
    method: "POST",
    body: JSON.stringify({ messages: history, stream: true }),
  });
  if (!res.ok || !res.body) {
    assistantEl.textContent = "Request failed.";
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let leftover = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    leftover += decoder.decode(value, { stream: true });
    const parts = leftover.split("\n\n");
    leftover = parts.pop();
    for (const p of parts) {
      const line = p.trim();
      if (!line.startsWith("data:")) continue;
      try {
        const obj = JSON.parse(line.slice(5).trim());
        if (obj.event === "sources") renderSources(obj.data);
        else if (obj.event === "token") {
          buf += obj.data;
          assistantEl.textContent = buf;
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (obj.event === "error") {
          assistantEl.textContent = obj.data;
        }
      } catch (e) {
        /* skip malformed line */
      }
    }
  }
  history.push({ role: "assistant", content: buf });
});

if (getToken()) {
  fetch("/api/status", { headers: authHeaders() }).then((r) => {
    if (r.ok) showApp();
    else {
      clearToken();
      showLogin();
    }
  });
} else {
  showLogin();
}
