/* Outbound AI console — vanilla JS SPA served by FastAPI */
"use strict";

const state = {
  token: localStorage.getItem("obai_token") || null,
  me: null,
  cfg: { supabase_url: "", anon_key: "" },
  screen: "dashboard",
};

/* ---------------- helpers ---------------- */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, isErr = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.toggle("err", isErr);
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), isErr ? 7000 : 4000);
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  if (state.me?.role === "super_admin") {
    const ws = document.getElementById("ws-input").value.trim();
    if (ws) headers["X-Workspace-Id"] = ws;
  }
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
  }
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) { logout(true); throw new Error("Session expired — sign in again."); }
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw new Error(typeof data === "object" && data?.detail ? data.detail : `HTTP ${res.status}`);
  return data;
}

/* ---------------- auth ---------------- */

let signupMode = false;

function toggleSignup(ev) {
  ev.preventDefault();
  signupMode = !signupMode;
  document.getElementById("signup-fields").classList.toggle("hidden", !signupMode);
  document.getElementById("login-btn").textContent = signupMode ? "Create account" : "Sign in";
  document.getElementById("toggle-signup").textContent =
    signupMode ? "← Already have an account? Sign in" : "No account yet? Create one →";
}

async function doLogin(ev) {
  ev.preventDefault();
  const btn = document.getElementById("login-btn");
  const errBox = document.getElementById("login-error");
  btn.disabled = true;
  errBox.classList.add("hidden");
  try {
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    if (signupMode) {
      const name = document.getElementById("signup-name").value.trim();
      if (!name) throw new Error("Display name is required");
      const r = await fetch("/auth/signup", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, display_name: name }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || "Sign-up failed");
    }

    const res = await fetch(`${state.cfg.supabase_url}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: { apikey: state.cfg.anon_key, "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error_description || data.msg || "Login failed");
    state.token = data.access_token;
    localStorage.setItem("obai_token", state.token);
    await enterApp();
    toast(signupMode ? "Welcome! Your agent account is ready 🎉" : "Signed in ✅");
  } catch (e) {
    errBox.textContent = e.message;
    errBox.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = signupMode ? "Create account" : "Sign in";
  }
  return false;
}

function logout(expired = false) {
  localStorage.removeItem("obai_token");
  state.token = null; state.me = null;
  document.getElementById("app-shell").classList.add("hidden");
  document.getElementById("login-screen").classList.remove("hidden");
}

/* ---------------- shell + navigation ---------------- */

const TABS = [
  { id: "dashboard",  label: "Dashboard",   roles: ["agent", "admin", "super_admin"] },
  { id: "tickets",    label: "Tickets",     roles: ["agent", "admin", "super_admin"] },
  { id: "calls",      label: "Calls",       roles: ["agent", "admin", "super_admin"] },
  { id: "kb",         label: "Knowledge Base", roles: ["admin", "super_admin"] },
  { id: "users",      label: "Users",       roles: ["super_admin"] },
  { id: "callcenter", label: "Call Center", roles: ["admin", "super_admin"] },
];

function showScreen(id) {
  state.screen = id;
  document.querySelectorAll(".screen").forEach(s => s.classList.add("hidden"));
  document.getElementById(`screen-${id}`).classList.remove("hidden");
  document.querySelectorAll("#nav-tabs button").forEach(b =>
    b.classList.toggle("active", b.dataset.screen === id));
  const loaders = {
    dashboard: loadDashboard, tickets: loadTickets, calls: loadCalls,
    kb: loadKb,
    users: () => Promise.all([loadUsers(), state.me.role === "super_admin" ? loadWorkspaces() : Promise.resolve()]),
    callcenter: () => {},
  };
  (loaders[id] || (() => {}))().catch(e => toast(e.message, true));
}

function buildNav() {
  const nav = document.getElementById("nav-tabs");
  nav.innerHTML = "";
  TABS.filter(t => t.roles.includes(state.me.role)).forEach(t => {
    const b = document.createElement("button");
    b.textContent = t.label;
    b.dataset.screen = t.id;
    b.onclick = () => showScreen(t.id);
    nav.appendChild(b);
  });
}

async function enterApp() {
  state.me = await api("/health/auth");
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-shell").classList.remove("hidden");
  document.getElementById("chip-name").textContent = state.me.email;
  const chip = document.getElementById("chip-role");
  chip.textContent = state.me.role;
  chip.className = `badge ${state.me.role}`;
  const wsBar = document.getElementById("ws-bar");
  wsBar.classList.toggle("hidden", state.me.role !== "super_admin");
  buildNav();
  showScreen(state.screen);
}

function applyWorkspace() {
  document.getElementById("ws-hint").textContent =
    document.getElementById("ws-input").value.trim() ? "scoped ✓" : "";
  showScreen(state.screen); // reload current view under new scope
}

/* ---------------- dashboard ---------------- */

async function loadDashboard() {
  const cards = [];
  try { const t = await api("/tickets"); cards.push(["Tickets visible to you", t.length]); } catch {}
  try { const c = await api("/calls");    cards.push(["Calls visible to you", c.length]); } catch {}
  if (["admin", "super_admin"].includes(state.me.role)) {
    try { const k = await api("/kb/documents"); cards.push(["KB documents", k.length]); } catch {}
  }
  if (state.me.role === "super_admin") {
    try { const u = await api("/admin/users"); cards.push(["Users on platform", u.length]); } catch {}
  }
  document.getElementById("dash-cards").innerHTML = cards.map(([l, n]) =>
    `<div class="card"><div class="num">${esc(n)}</div><div class="lbl">${esc(l)}</div></div>`).join("");
  document.getElementById("identity-json").textContent =
    JSON.stringify(state.me, null, 2);
}

/* ---------------- tables ---------------- */

function renderTable(elId, rows, cols) {
  const el = document.getElementById(elId);
  if (!rows.length) { el.innerHTML = `<tr><td class="muted">No rows visible to your role.</td></tr>`; return; }
  el.innerHTML =
    `<thead><tr>${cols.map(c => `<th>${c.h}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr>${cols.map(c => `<td>${c.f(r)}</td>`).join("")}</tr>`).join("") +
    `</tbody>`;
}

async function loadTickets() {
  const rows = await api("/tickets");
  renderTable("tickets-table", rows, [
    { h: "ID",        f: r => esc(r.id).slice(0, 8) },
    { h: "Title",     f: r => `<span dir="rtl">${esc(r.title)}</span>` },
    { h: "Status",    f: r => esc(r.status ?? "-") },
    { h: "Category",  f: r => esc(r.kb_category ?? "-") },
    { h: "Assigned",  f: r => r.assigned_to ? esc(r.assigned_to.slice(0, 8)) : '<span class="muted">unassigned</span>' },
  ]);
}

async function loadCalls() {
  const rows = await api("/calls");
  renderTable("calls-table", rows, [
    { h: "Call ID",     f: r => esc((r.vonage_call_id ?? r.id ?? "").toString().slice(0, 12)) },
    { h: "Outcome",     f: r => esc(r.call_outcome ?? "-") },
    { h: "Intent",      f: r => esc(r.intent ?? "-") },
    { h: "KB answer?",  f: r => r.kb_answer_given ? "✅" : "—" },
    { h: "Escalated",   f: r => r.escalated ? "🚨" : "—" },
    { h: "Summary",     f: r => `<span dir="rtl">${esc((r.call_summary ?? "").slice(0, 90))}</span>` },
  ]);
}

/* ---------------- knowledge base ---------------- */

async function kbUpload() {
  const category = document.getElementById("kb-category").value.trim();
  if (!category) return toast("Category is required", true);
  const fileInput = document.getElementById("kb-file");
  const content = document.getElementById("kb-content").value.trim();
  if (!fileInput.files.length && !content) return toast("Attach a file or paste content", true);

  const fd = new FormData();
  fd.append("category", category);
  if (document.getElementById("kb-title").value.trim())
    fd.append("title", document.getElementById("kb-title").value.trim());
  if (fileInput.files.length) fd.append("file", fileInput.files[0]);
  else fd.append("content", content);

  try {
    const res = await api("/kb/documents", { method: "POST", body: fd });
    toast(`Ingested "${res.source}" — ${res.chunks} chunk(s) embedded ✅`);
    document.getElementById("kb-content").value = "";
    fileInput.value = "";
    loadKb();
  } catch (e) { toast(e.message, true); }
}

async function loadKb() {
  const docs = await api("/kb/documents");
  const el = document.getElementById("kb-table");
  if (!docs.length) { el.innerHTML = `<tr><td class="muted">No documents yet.</td></tr>`; return; }
  el.innerHTML =
    `<thead><tr><th>Document</th><th>Chunks</th><th>Category</th><th></th></tr></thead><tbody>` +
    docs.map(d =>
      `<tr><td dir="rtl">${esc(d.source)}</td><td>${d.chunks}</td><td>${esc(d.category ?? "-")}</td>` +
      `<td><button class="btn danger sm" onclick="kbDelete('${esc(d.source)}')">delete</button></td></tr>`)
      .join("") + `</tbody>`;
}

async function kbDelete(source) {
  if (!confirm(`Delete every chunk of "${source}"?`)) return;
  try {
    const res = await api(`/kb/documents/${encodeURIComponent(source)}`, { method: "DELETE" });
    toast(`Deleted ${res.chunks_deleted} chunk(s)`);
    loadKb();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- user management ---------------- */

async function createUser() {
  const body = {
    email: document.getElementById("nu-email").value.trim(),
    display_name: document.getElementById("nu-name").value.trim(),
    role: document.getElementById("nu-role").value,
  };
  const ws = document.getElementById("nu-workspace").value.trim();
  if (ws) body.workspace_id = ws;
  const pw = document.getElementById("nu-password").value;
  if (pw) body.password = pw;
  if (!body.email || !body.display_name) return toast("Email and name are required", true);
  try {
    const res = await api("/admin/users", { method: "POST", json: body });
    const box = document.getElementById("nu-result");
    box.textContent = JSON.stringify(res, null, 2);
    box.classList.remove("hidden");
    if (res.generated_password)
      toast(`User created — generated password shown ONCE below ⚠️`, true);
    else toast("User created ✅");
    loadUsers();
  } catch (e) { toast(e.message, true); }
}

async function loadUsers() {
  if (state.me.role !== "super_admin") return;
  const rows = await api("/admin/users");
  renderTable("users-table", rows, [
    { h: "Email",    f: r => esc(r.email) },
    { h: "Name",     f: r => esc(r.display_name ?? "-") },
    { h: "Platform role", f: r => `<span class="badge ${esc(r.platform_role)}">${esc(r.platform_role)}</span>` },
    { h: "Make admin", f: r => r.platform_role !== "admin"
        ? `<button class="btn sm" onclick="setRole('${esc(r.id)}','admin')">promote</button>`
        : `<span class="muted">current</span>` },
  ]);
}

async function setRole(userId, role) {
  try {
    await api(`/admin/users/${userId}/platform-role?new_role=${role}`, { method: "PATCH" });
    toast(`Role updated to ${role} ✅`);
    loadUsers();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- workspaces (super_admin) ---------------- */

async function loadWorkspaces() {
  const rows = await api("/admin/workspaces");
  renderTable("workspaces-table", rows, [
    { h: "Name",     f: r => esc(r.name) },
    { h: "Slug",     f: r => `<code>${esc(r.slug)}</code>` },
    { h: "Plan",     f: r => esc(r.plan) },
    { h: "Members",  f: r => `${r.members ?? 0} (${r.admins ?? 0} admin)` },
    { h: "ID",       f: r => `<span class="muted">${esc(r.id).slice(0, 13)}…</span>` },
  ]);
}

async function createWorkspace() {
  const name = document.getElementById("nw-name").value.trim();
  const slug = document.getElementById("nw-slug").value.trim().toLowerCase();
  if (!name || !slug) return toast("Name and slug are required", true);
  try {
    await api("/admin/workspaces", {
      method: "POST",
      json: { name, slug, plan: document.getElementById("nw-plan").value },
    });
    toast(`Workspace "${name}" created ✅`);
    document.getElementById("nw-name").value = "";
    document.getElementById("nw-slug").value = "";
    loadWorkspaces();
  } catch (e) { toast(e.message, true); }
}

/* ---------------- call center ---------------- */

async function startCall() {
  const phone = document.getElementById("cc-phone").value.trim();
  if (!phone) return toast("Phone number is required", true);
  const body = { phone };
  const t = document.getElementById("cc-ticket").value.trim();
  const ti = document.getElementById("cc-title").value.trim();
  if (t) body.ticket_id = t;
  if (ti) body.ticket_title = ti;
  body.category = document.getElementById("cc-category").value;
  try {
    const res = await api("/start-call", { method: "POST", json: body });
    const box = document.getElementById("cc-result");
    box.textContent = JSON.stringify(res, null, 2);
    box.classList.remove("hidden");
    toast("📞 Call placed — pick up your phone!");
  } catch (e) { toast(e.message, true); }
}

/* ---------------- boot ---------------- */

(async function boot() {
  try {
    state.cfg = await fetch("/api/config").then(r => r.json());
  } catch { toast("Cannot reach API — is uvicorn running?", true); return; }

  document.getElementById("login-screen").classList.remove("hidden");
  document.querySelector("form.login-card").onsubmit = doLogin;
  document.getElementById("toggle-signup").onclick = toggleSignup;

  if (state.token) {
    try { await enterApp(); }
    catch { /* token dead — login form already visible */ }
  }
})();
