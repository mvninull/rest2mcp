<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { servers, serversLoading, serversError, serverHealth, activeServerId, serverCount } from './stores/servers.js';
  import { t } from './stores/lang.js';
  import './Dashboard.css';
  import { installAppAlert, notifyAppAlert } from './app-alert.js';

  const __ = (key) => get(t)(key);

  const API_BASE = (
    localStorage.getItem("api_base") ||
    (location.hostname === "localhost" || location.hostname === "127.0.0.1"
      ? "http://localhost:8080"
      : "https://rest2mcp.fly.dev")
  ).replace(/\/+$/, "");
  const POLL_LOGS_INTERVAL = 5000;

  const SUPABASE_URL = localStorage.getItem("supabase_url") || "https://zcfrbhrqvneomseqmqam.supabase.co";
  const SUPABASE_ANON_KEY = localStorage.getItem("supabase_anon_key") || "sb_publishable_mF0UgfLvgZN5OupdpsSa0A_ibOcfzq4";

  let activeMenu = null;
  let activeMenuServer = null;
  let mergeSourceId = null;
  let mergeTargetId = null;
  let mergeMode = "local";
  let editingServerId = null;
  let _initialized = false;
  let _inspecting = false;
  let logsInterval = null;
  let logDebounceTimer = null;
  let supabaseClient = null;
  let currentUser = null;
  let currentProfile = null;
  let showToolsModal = false;
  let toolsList = [];
  let toolsLoading = false;
  let toolsError = null;
  let toolsModalServer = null;
  let expandedTool = null;
  let toolArgs = {};
  let toolCalling = false;
  let toolResult = null;
  let toolResultError = null;
  let toolRawData = null;
  let toolShowRaw = {};
  // Auth state for MCP server login
  let serverAuth = null;
  let authFields = [];
  let authValues = {};
  let authLoggingIn = false;
  let authSuccess = false;
  let authError = null;
  let serverAuthState = {};
  let showSecurityInfo = false;

  let _storeAllServers = [];
  let _storeFacets = { hostingTypes: [], categories: [] };
  let _storeFilterHosting = "";
  let _storeFilterCategory = "";
  let _storePageInfo = { hasNextPage: false, endCursor: "" };
  let _storeLoading = false;
  let _storeEnvSchemas = {};
  let _storeCacheFetched = false;
  let _storeSort = "relevance";
  let _storePage = 1;
  let _storePerPage = 20;

  function debug(...args) {
    console.log("[dashboard-debug]", ...args);
  }

  if (SUPABASE_URL && SUPABASE_ANON_KEY) {
    try {
      if (typeof supabase === 'undefined') {
        throw new Error('window.supabase indefinido — o SDK do Supabase não foi carregado (verifica o <script> no index.html ou usa import npm).');
      }
      supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    } catch (err) {
      // Isto corre à construção do componente, ANTES de qualquer DOM.
      // Sem este try/catch, uma falha aqui impede o Dashboard inteiro
      // de montar (nada renderiza, nenhum botão existe).
      console.error('[Dashboard] Falha ao inicializar Supabase:', err);
    }
  }

  function getAuthToken() {
    return localStorage.getItem("supabase_token") || "";
  }

  function showLoading(text = "Aguarde...", blur = true) {
    const overlay = document.getElementById("loadingOverlay");
    const textEl = document.getElementById("loadingText");
    if (!overlay) return;
    overlay.classList.toggle("no-blur", !blur);
    if (textEl) textEl.textContent = text;
    overlay.classList.add("open");
  }
  function hideLoading() {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay) overlay.classList.remove("open");
  }

  function showConfirmDialog(msg, onConfirm, onCancel) {
    debug("showConfirmDialog:open", { msg });
    const existing = document.getElementById("appConfirmOverlay");
    if (existing) existing.remove();
    const overlay = document.createElement("div");
    overlay.id = "appConfirmOverlay";
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(12,12,20,0.62);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;z-index:1000000;padding:16px;";

    const box = document.createElement("div");
    box.style.cssText = "background:#fff;border-radius:18px;padding:32px;max-width:400px;width:min(100%,400px);text-align:center;box-shadow:0 24px 80px rgba(0,0,0,0.28);border:1px solid rgba(12,12,20,0.08);";

    const icon = document.createElement("h3");
    icon.textContent = "Confirmar";
    icon.style.cssText = "margin:0;font-family:Inter,sans-serif;font-size:20px;font-weight:800;color:#0c0c14;";

    const text = document.createElement("p");
    text.textContent = msg;
    text.style.cssText = "margin:14px 0 0;font-family:Inter,sans-serif;font-size:14px;line-height:1.6;color:#4b5563;";

    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;justify-content:center;gap:8px;margin-top:20px;";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "Cancelar";
    cancelBtn.style.cssText = "border:1px solid rgba(12,12,20,0.12);background:#fff;color:#0c0c14;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;";

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.textContent = "Confirmar";
    confirmBtn.style.cssText = "border:none;background:#1a56ff;color:#fff;padding:10px 24px;border-radius:10px;cursor:pointer;font-weight:700;";

    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    box.appendChild(icon);
    box.appendChild(text);
    box.appendChild(actions);
    overlay.appendChild(box);

    confirmBtn.addEventListener("click", () => {
      debug("showConfirmDialog:confirm", { msg });
      overlay.remove();
      if (onConfirm) onConfirm();
    });
    cancelBtn.addEventListener("click", () => {
      debug("showConfirmDialog:cancel", { msg });
      overlay.remove();
      if (onCancel) onCancel();
    });
    overlay.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) {
        debug("showConfirmDialog:backdrop-cancel", { msg });
        overlay.remove();
        if (onCancel) onCancel();
      }
    });
    document.body.appendChild(overlay);
    debug("showConfirmDialog:mounted", {
      hasOverlay: !!document.getElementById("appConfirmOverlay"),
    });
    requestAnimationFrame(() => {
      const style = window.getComputedStyle(overlay);
      const rect = box.getBoundingClientRect();
      debug("showConfirmDialog:layout", {
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        zIndex: style.zIndex,
        boxWidth: Math.round(rect.width),
        boxHeight: Math.round(rect.height),
      });
    });
  }

  async function loginWith(provider) {
    if (!supabaseClient) return window.showAppAlert(__("notifications.supabase_not_configured"));
    showLoading("Redirecionando para " + provider + "...");
    const { error } = await supabaseClient.auth.signInWithOAuth({ provider });
    if (error) {
      hideLoading();
      console.error("Login error:", error);
    }
  }

  async function logout() {
    showLoading(__("auth.ending_session"));
    try {
      if (supabaseClient) await supabaseClient.auth.signOut({ scope: 'global' });
    } catch (e) {
      console.error("Erro ao terminar sessão Supabase:", e);
    }
    localStorage.removeItem("supabase_token");
    localStorage.removeItem("supabase.auth.token");
    sessionStorage.removeItem("supabase.auth.token");
    currentUser = null;
    currentProfile = null;
    window.location.href = window.location.origin;
  }

  async function restoreSession() {
    if (!supabaseClient) return;
    const token = getAuthToken();
    if (!token) return;
    try {
      const { data, error } = await supabaseClient.auth.getUser(token);
      if (error || !data?.user) {
        logout();
        return;
      }
      currentUser = data.user;
      await fetchProfile();
      try { await verifyPendingCheckout(); } catch {}
    } catch {
      logout();
    }
  }

  async function verifyPendingCheckout() {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id");
    if (!sessionId || !currentUser) return;
    try {
      await apiFetch("/v1/checkout-session/verify", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, user_id: currentUser.id }),
      });
      const cleanUrl = window.location.origin + window.location.pathname;
      window.history.replaceState({}, "", cleanUrl);
      await fetchProfile();
    } catch (err) {
      console.error("Verify checkout error:", err);
    }
  }

  async function fetchProfile() {
    if (!currentUser) return;
    try {
      const resp = await apiFetch("/v1/me");
      currentProfile = resp;
    } catch {
      currentProfile = null;
    }
    renderAuthUI();
    renderProfile();
  }

  function renderAuthUI() {
    const loginEl = document.getElementById("authLogin");
    const userEl = document.getElementById("authUser");
    if (!loginEl || !userEl) return;
    if (currentUser) {
      loginEl.style.display = "none";
      userEl.style.display = "flex";
      const nameEl = document.getElementById("authName");
      const avatarEl = document.getElementById("authAvatar");
      const planEl = document.getElementById("authPlan");
      if (nameEl) nameEl.textContent = currentProfile?.name || currentUser.email?.split("@")[0] || currentUser.email || "";
      if (avatarEl) avatarEl.src = currentProfile?.avatar_url || currentUser.user_metadata?.avatar_url || "";
      if (planEl) {
        const plan = (currentProfile?.plan_tier || "free").toLowerCase();
        planEl.textContent = plan;
        planEl.className = `auth-plan ${plan}`;
      }
    } else {
      loginEl.style.display = "none";
      userEl.style.display = "none";
    }
  }

  function renderProfile() {
    const qrs = document.getElementById("quotaRowServers");
    const qrp = document.getElementById("quotaRowPlan");
    const sub = document.getElementById("subSection");
    if (!currentProfile) {
      if (qrs) qrs.style.display = "none";
      if (qrp) qrp.style.display = "none";
      if (sub) sub.style.display = "none";
      return;
    }
    const profile = currentProfile;
    if (qrs) qrs.style.display = "flex";
    if (qrp) qrp.style.display = "flex";
    const qs = document.getElementById("quotaServers");
    const qp = document.getElementById("quotaPlan");
    if (qs) {
      qs.textContent = `${profile.servers_count} / ${profile.servers_limit}`;
      qs.className = "stat-value" + (profile.servers_count >= profile.servers_limit ? " warn" : "");
    }
    if (qp) qp.textContent = profile.plan_tier;

    if (sub) sub.style.display = "block";
    const ss = document.getElementById("subServers");
    if (ss) {
      ss.textContent = `${profile.servers_count} / ${profile.servers_limit}`;
      ss.className = "val" + (profile.servers_count >= profile.servers_limit ? " warn" : "");
    }

    const isPro = profile.plan_tier === "pro";
    const sRpm = document.getElementById("subRPM");
    if (sRpm) sRpm.textContent = isPro ? "100" : "10";
    const upg = document.getElementById("subUpgrade");
    if (upg) upg.style.display = isPro ? "none" : "block";
  }

  async function handleStripePro() {
    if (!currentUser) return;
    const btn = document.getElementById("subUpgradeBtn");
    if (btn) { btn.disabled = true; btn.textContent = "A redirecionar..."; }
    const STRIPE_PUBLISHABLE_KEY = "pk_test_51TbKmaQdlPUKQK2wfBNfhgwltyLsxwfV2smHoPIxyp15rqsEjNbUM0nV1rmyZ2DFQHGm7Ee0RHAy2gzerqGJ5MJA00VAAqjNDO";
    const STRIPE_PRO_PRICE_ID = "price_1TbKy7QdlPUKQK2wQmXUzWOM";
    try {
      const payload = {
        price_id: STRIPE_PRO_PRICE_ID,
        user_id: currentUser.id,
        email: currentUser.email,
        success_url: window.location.origin + "/?page=dashboard",
        cancel_url: window.location.origin
      };
      const resp = await fetch(`${API_BASE}/v1/checkout-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${resp.status} do servidor`);
      }
      const data = await resp.json();
      if (data.url) { window.location.href = data.url; return; }
      if (data.sessionId || data.session_id) {
        const stripe = Stripe(STRIPE_PUBLISHABLE_KEY);
        const { error } = await stripe.redirectToCheckout({ sessionId: data.sessionId || data.session_id });
        if (error) throw new Error(error.message);
        return;
      }
      throw new Error("Resposta inesperada do servidor");
    } catch (err) {
      console.error("Stripe error:", err);
      window.showAppAlert("Erro: " + (err.message || err));
    }
    if (btn) { btn.disabled = false; btn.textContent = __("pricing.pro.cta"); }
  }

  // ─── API ───────────────────────────────────────────────
  async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const headers = { "Content-Type": "application/json", ...options.headers };
    const token = getAuthToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(url, {
      headers,
      ...options,
    });
    if (res.status === 204) return null;
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Erro ${res.status}`);
    return data;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ─── Load Servers (store-based) ────────────────────────
  async function loadServers(forceRefresh) {
    if (get(servers).length > 0 && !forceRefresh) return;
    serverAuthState = {};
    serversLoading.set(true);
    serversError.set(null);
    try {
      const data = await apiFetch("/v1/servers");
      console.log("[loadServers] GET /v1/servers recebido com", data?.length, "servidores");
      servers.set(data || []);
      serversError.set(null);
      _populateLogServerSelect(data || []);
      const currentId = get(activeServerId);
      const stillExists = currentId && data.some(s => s.server_id === currentId);
      if (stillExists) {
        selectServer(currentId);
      } else if (data && data.length > 0) {
        selectServer(data[0].server_id);
      }
      _checkAllServerHealth(data || []);
      _checkAllServerAuth(data || []);
    } catch (err) {
      console.error("[loadServers] erro:", err);
      serversError.set(err.message);
    } finally {
      serversLoading.set(false);
    }
  }

  // ─── Health Checks (store-based) ───────────────────────
  async function _checkAllServerHealth(srvList) {
    const health = {};
    const active = srvList.filter(s => s.status === "active");
    console.log("[health] health checks iniciados para", active.length, "servidores ativos (em background)");
    if (active.length === 0) {
      serverHealth.set(health);
      return;
    }
    const token = getAuthToken();
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const results = await Promise.allSettled(
      active.map(s => {
        console.log("[health] a verificar", s.server_id, s.name);
        return fetch(`${API_BASE}/v1/servers/${s.server_id}/health`, { headers }).then(r => r.json());
      })
    );
    results.forEach((res, i) => {
      const srv = active[i];
      if (res.status === "fulfilled" && res.value.status === "ok") {
        console.log("[health]", srv.server_id, srv.name, "→ OK");
        health[srv.server_id] = "ok";
      } else {
        console.log("[health]", srv.server_id, srv.name, "→ ERROR", res.status === "fulfilled" ? res.value.detail : "fetch failed");
        health[srv.server_id] = "error";
      }
    });
    serverHealth.set(health);
    console.log("[health] todos os health checks concluídos");
  }

  async function _checkAllServerAuth(srvList) {
    const active = srvList.filter(s => s.status === "active");
    if (active.length === 0) return;
    const results = await Promise.allSettled(
      active.map(s => apiFetch(`/v1/servers/${s.server_id}/auth`))
    );
    for (let i = 0; i < results.length; i++) {
      const res = results[i];
      const srv = active[i];
      if (res.status === "fulfilled" && res.value?.required_fields?.length) {
        serverAuthState = {
          ...serverAuthState,
          [srv.server_id]: { required: true, authenticated: !!res.value.authenticated },
        };
      } else if (res.status === "fulfilled") {
        serverAuthState = {
          ...serverAuthState,
          [srv.server_id]: { required: false },
        };
      }
    }
  }

  // ─── Create Server ─────────────────────────────────────
  async function createServer() {
    const name = document.getElementById("inputName")?.value?.trim();
    const specUrl = document.getElementById("inputSpecUrl")?.value?.trim();
    const transport = document.getElementById("inputTransport")?.value;
    const errorEl = document.getElementById("modalError");
    const btn = document.getElementById("btnCreateConfirm");

    if (errorEl) showModalError(errorEl, "");

    if (!name) {
      if (errorEl) showModalError(errorEl, "Informe o nome do servidor.");
      return;
    }
    if (!specUrl) {
      if (errorEl) showModalError(errorEl, "Informe a URL do OpenAPI Spec.");
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="btn-spinner"></span> Criando...';
    }

    try {
      await apiFetch("/v1/servers", {
        method: "POST",
        body: JSON.stringify({ name, spec_url: specUrl, transport }),
      });
      closeCreateModal();
      showLoading("Servidor criado! Carregando...", false);
      await loadServers(true);
      hideLoading();
      window.showAppAlert("Servidor criado com sucesso.");
      const cards = document.querySelectorAll(".server-card");
      if (cards.length > 0)
        cards[0].scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (err) {
      if (errorEl) showModalError(errorEl, err.message);
      window.showAppAlert("Erro ao criar servidor: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Criar Servidor";
      }
    }
  }

  // ─── Delete Server ─────────────────────────────────────
  function deleteServer(serverId) {
    debug("deleteServer:start", { serverId });
    const card = document.querySelector(`.server-card[data-server-id="${serverId}"]`);
    if (card) {
      card.style.opacity = "0";
      card.style.transform = "translateX(20px)";
      card.style.transition = "all 0.3s";
    }
    showConfirmDialog("Remover este servidor permanentemente?", async () => {
      try {
        debug("deleteServer:apiFetch", { serverId });
        await apiFetch(`/v1/servers/${serverId}`, { method: "DELETE" });
        debug("deleteServer:apiSuccess", { serverId });
        await loadServers(true);
        const currentId = get(activeServerId);
        if (currentId === serverId) activeServerId.set(null);
        notifyAppAlert("Servidor removido com sucesso.");
      } catch (err) {
        console.error("[dashboard-debug] deleteServer:apiError", err);
        const card2 = document.querySelector(`.server-card[data-server-id="${serverId}"]`);
        if (card2) {
          card2.style.opacity = "1";
          card2.style.transform = "";
        }
        notifyAppAlert("Erro ao remover: " + err.message);
      }
    }, () => {
      const card2 = document.querySelector(`.server-card[data-server-id="${serverId}"]`);
      if (card2) {
        card2.style.opacity = "1";
        card2.style.transform = "";
      }
    });
  }

  // ─── Toggle Status ──────────────────────────────────────
  async function toggleServerStatus(serverId) {
    const srvList = get(servers);
    const srv = srvList.find(s => s.server_id === serverId);
    const isActive = srv?.status === "active";
    if (isActive) {
      try {
        await apiFetch(`/v1/servers/${serverId}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "inactive" }),
        });
        await loadServers(true);
        window.showAppAlert("Servidor desativado com sucesso.");
      } catch (err) {
        window.showAppAlert("Erro ao alterar status: " + err.message);
      }
      return;
    }
    // Activating
    try {
      await apiFetch(`/v1/servers/${serverId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "active" }),
      });
      await loadServers(true);
      // Check if this server requires auth
      try {
        const authData = await apiFetch(`/v1/servers/${serverId}/auth`);
        if (authData?.required_fields?.length) {
          openToolsModal(serverId);
          return;
        }
      } catch (_) {
        // If auth check fails, just activate normally
      }
      window.showAppAlert("Servidor ativado com sucesso.");
    } catch (err) {
      window.showAppAlert("Erro ao alterar status: " + err.message);
    }
  }

  // ─── Unmerge ────────────────────────────────────────────
  function unmergeServer(serverId) {
    debug("unmergeServer:start", { serverId });
    showConfirmDialog("Desfazer merge deste servidor?", async () => {
      try {
        debug("unmergeServer:apiFetch", { serverId });
        await apiFetch(`/v1/servers/${serverId}/unmerge`, { method: "POST" });
        debug("unmergeServer:apiSuccess", { serverId });
        await loadServers(true);
        debug("unmergeServer:loadServers:done", { serverId });
        notifyAppAlert("Merge desfeito com sucesso.");
      } catch (err) {
        console.error("[dashboard-debug] unmergeServer:apiError", err);
        notifyAppAlert("Erro ao desfazer merge: " + err.message);
      }
    });
  }

  // ─── Menu Portal ───────────────────────────────────────
  function toggleMenu(serverId, btn) {
    const rect = btn.getBoundingClientRect();
    const menuW = 200;
    let left = rect.right - menuW;
    let top = rect.bottom + 6;
    if (left < 8) left = 8;
    if (top + 240 > window.innerHeight) top = rect.top - 240;

    if (activeMenu && activeMenu.serverId === serverId) {
      closeAllMenus();
      return;
    }
    closeAllMenus();

    activeMenuServer = get(servers).find(s => s.server_id === serverId) || null;
    if (!activeMenuServer) return;

    activeMenu = { serverId, x: left, y: top };
  }

  function closeMenu() {
    closeAllMenus();
  }

  function closeAllMenus() {
    activeMenu = null;
  }

  // ─── Merge ─────────────────────────────────────────────
  function populateMergeTargets(excludeId) {
    const sel = document.getElementById("mergeTargetSelect");
    if (!sel) return;
    const srvList = get(servers);
    sel.innerHTML = '<option value="">Selecione um servidor...</option>';
    srvList.forEach((s) => {
      if (s.server_id !== excludeId) {
        const opt = document.createElement("option");
        opt.value = s.server_id;
        opt.textContent = s.name;
        sel.appendChild(opt);
      }
    });
  }

  function setMergeTab(mode) {
    mergeMode = mode;
    const localTab = document.getElementById("mergeTabLocal");
    const sandboxTab = document.getElementById("mergeTabSandbox");
    const localFields = document.getElementById("mergeLocalFields");
    const sandboxFields = document.getElementById("mergeSandboxFields");
    if (localTab) localTab.classList.toggle("active", mode === "local");
    if (sandboxTab) sandboxTab.classList.toggle("active", mode === "sandbox");
    if (localFields) localFields.style.display = mode === "local" ? "" : "none";
    if (sandboxFields) sandboxFields.style.display = mode === "sandbox" ? "" : "none";
    const mergeSub = document.getElementById("mergeSub");
    if (mergeSub) {
      const labels = { local: __("merge.local_desc"), sandbox: __("merge.sandbox_desc") };
      mergeSub.textContent = labels[mode] || "";
    }
  }

  function openMergeModalFromMenu(serverId, serverName) {
    mergeMode = "local";
    mergeSourceId = serverId;
    mergeTargetId = null;
    populateMergeTargets(serverId);
    setMergeTab("local");
    const mm = document.getElementById("mergeModal");
    const mn = document.getElementById("mergeName");
    const me = document.getElementById("mergeError");
    const bc = document.getElementById("btnMergeConfirm");
    const sj = document.getElementById("mergeStdioJson");
    if (mn) {
      mn.value = "";
      mn.placeholder = `Ex: ${serverName} (Merged)`;
    }
    if (sj) sj.value = "";
    if (me) showModalError(me, "");
    if (bc) {
      bc.disabled = false;
      bc.textContent = "Criar Servidor Merged";
    }
    if (mm) mm.classList.add("open");
    setTimeout(() => { const f = document.getElementById("mergeTargetSelect"); if (f) f.focus(); }, 120);
  }

  async function openToolsModal(serverId) {
    const srv = get(servers).find(s => s.server_id === serverId);
    if (!srv) return;
    toolsModalServer = srv;
    showToolsModal = true;
    toolsLoading = true;
    toolsError = null;
    toolsList = [];
    authFields = [];
    authValues = {};
    authLoggingIn = false;
    authSuccess = false;
    authError = null;
    try {
      const [toolsData, authData] = await Promise.all([
        apiFetch(`/v1/servers/${serverId}/tools`),
        apiFetch(`/v1/servers/${serverId}/auth`),
      ]);
      if (toolsData.tools) {
        toolsList = toolsData.tools;
      }
      serverAuth = authData;
      if (authData?.required_fields?.length) {
        authFields = authData.required_fields;
        for (const f of authFields) authValues[f] = "";
        serverAuthState[serverId] = { required: true, authenticated: !!authData.authenticated };
      } else {
        serverAuth = null;
        serverAuthState[serverId] = { required: false };
      }
    } catch (err) {
      toolsError = err.message || "Erro ao listar tools";
    } finally {
      toolsLoading = false;
    }
  }

  function closeToolsModal() {
    showToolsModal = false;
    toolsList = [];
    toolsError = null;
    toolsModalServer = null;
    serverAuth = null;
    authFields = [];
    authValues = {};
    authLoggingIn = false;
    authSuccess = false;
    authError = null;
    showSecurityInfo = false;
    expandedTool = null;
    toolResult = null;
    toolResultError = null;
    toolRawData = null;
    toolShowRaw = {};
  }

  function toggleToolExpand(tool) {
    if (expandedTool?.name === tool.name) {
      expandedTool = null;
      toolResult = null;
      toolResultError = null;
      toolRawData = null;
      toolShowRaw = {};
      return;
    }
    expandedTool = tool;
    toolArgs = {};
    toolResult = null;
    toolResultError = null;
    toolRawData = null;
    toolShowRaw = {};
    if (tool.inputSchema?.properties) {
      for (const [k, v] of Object.entries(tool.inputSchema.properties)) {
        const typ = v.type || "";
        if (typ === "boolean") {
          toolArgs[k] = v.default ?? false;
        } else if (typ === "number" || typ === "integer") {
          toolArgs[k] = v.default ?? "";
        } else {
          toolArgs[k] = v.default ?? "";
        }
      }
    }
  }

  function formatContentItem(item) {
    if (item.type === "image" && item.data) {
      return `<div class="tool-result-content-image"><img src="data:${item.mimeType || "image/png"};base64,${item.data}" alt="Imagem retornada" /></div>`;
    }
    if (item.type === "resource" && item.resource) {
      const r = item.resource;
      if (r.text) {
        const formatted = tryFormatJson(r.text);
        return `<div class="tool-result-content-resource"><pre style="margin:0;white-space:pre-wrap;word-break:break-word">${escapeHtml(formatted)}</pre></div>`;
      }
      if (r.blob && r.mimeType) {
        return `<div class="tool-result-content-image"><img src="data:${r.mimeType};base64,${r.blob}" alt="Recurso" /></div>`;
      }
      return `<div class="tool-result-content-resource"><pre style="margin:0;white-space:pre-wrap;word-break:break-word">${escapeHtml(JSON.stringify(r, null, 2))}</pre></div>`;
    }
    const text = item.text || (item.type === "text" ? "" : JSON.stringify(item));
    const formatted = tryFormatJson(text);
    return `<div class="tool-result-content-text">${escapeHtml(formatted)}</div>`;
  }

  function tryFormatJson(text) {
    if (!text) return text || "";
    const trimmed = text.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch { /* not valid JSON, fall through */ }
    }
    return text;
  }

  function parseArgValue(value, schema) {
    if (!schema || !value) return value;
    const typ = schema.type || "";
    if (typ === "array") {
      if (Array.isArray(value)) return value;
      try { const p = JSON.parse(value); return Array.isArray(p) ? p : [p]; }
      catch { return value.split(",").map(s => s.trim()).filter(Boolean); }
    }
    if (typ === "object" || typ === "json") {
      if (typeof value === "object") return value;
      try { return JSON.parse(value); }
      catch { return value; }
    }
    return value;
  }

  async function callTool(toolName) {
    toolCalling = true;
    toolResult = null;
    toolResultError = null;
    try {
      const props = expandedTool?.inputSchema?.properties || {};
      const parsedArgs = {};
      for (const [k, v] of Object.entries(toolArgs)) {
        parsedArgs[k] = parseArgValue(v, props[k]);
      }
      const data = await apiFetch(`/v1/servers/${toolsModalServer.server_id}/tools/call`, {
        method: "POST",
        body: JSON.stringify({ name: toolName, arguments: parsedArgs }),
      });
      toolRawData = data;
      if (data.content) {
        toolResult = data.content.map(formatContentItem).join("\n");
      }
      if (data.isError) {
        toolResultError = "Tool retornou erro";
      }
    } catch (err) {
      toolResultError = err.message || "Erro ao executar tool";
    } finally {
      toolCalling = false;
    }
  }

  async function loginToServer() {
    if (!toolsModalServer) return;
    authLoggingIn = true;
    authError = null;
    authSuccess = false;
    try {
      const data = await apiFetch(`/v1/servers/${toolsModalServer.server_id}/auth/login`, {
        method: "POST",
        body: JSON.stringify(authValues),
      });
      if (data.token) {
        await apiFetch(`/v1/servers/${toolsModalServer.server_id}/tools/call`, {
          method: "POST",
          body: JSON.stringify({ name: "set_token", arguments: { token: data.token } }),
        });
        authSuccess = true;
        serverAuthState[toolsModalServer.server_id] = { required: true, authenticated: true };
        for (const f of authFields) authValues[f] = "";
      } else {
        authError = "Resposta inesperada do servidor";
      }
    } catch (err) {
      let msg = err.message || "Erro ao fazer login";
      try {
        const parsed = JSON.parse(msg);
        if (parsed.detail) {
          msg = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail);
        }
      } catch (_) {
        if (msg.includes("Object object")) msg = "Erro ao fazer login";
      }
      authError = msg;
    } finally {
      authLoggingIn = false;
    }
  }

  function fillSandbox(command, args, extra) {
    const cfg = { command, args: args.split(" ").filter(Boolean) };
    if (extra) cfg.args.push(extra);
    const ta = document.getElementById("mergeStdioJson");
    if (ta) ta.value = JSON.stringify(cfg, null, 2);
    closeStoreModal();
  }

  function autoNamespaceFromUrl(url) {
    try {
      const u = new URL(url);
      return u.hostname.replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "remote";
    } catch {
      return "remote";
    }
  }

  function closeMergeModal() {
    const mm = document.getElementById("mergeModal");
    if (mm) mm.classList.remove("open");
    mergeSourceId = null;
    mergeTargetId = null;
    mergeMode = "local";
    const mn = document.getElementById("mergeName");
    if (mn) mn.value = "";
    const sj = document.getElementById("mergeStdioJson");
    if (sj) sj.value = "";
    const warn = document.getElementById("mergePackageWarning");
    if (warn) warn.style.display = "none";
    const env = document.getElementById("mergeEnvFields");
    if (env) { env.style.display = "none"; env.innerHTML = ""; }
  }

  // ─── Store ─────────────────────────────────────────────
  function closeStoreModal() {
    document.getElementById("storeModal")?.classList.remove("open");
    const ss = document.getElementById("storeSearch");
    if (ss) ss.value = "";
  }

  async function openStoreModal() {
    const modal = document.getElementById("storeModal");
    const grid = document.getElementById("storeGrid");
    if (!modal || !grid) return;
    modal.classList.add("open");
    _storeFilterHosting = "";
    _storeFilterCategory = "";
    if (_storeAllServers.length) {
      _renderStoreFilters();
      searchStore();
      return;
    }
    grid.innerHTML = "<div class='store-loading'>A carregar loja...</div>";
    _storeEnvSchemas = {};
    try {
      const data = await apiFetch("/v1/store/servers");
      const servers = data.servers || [];
      _storeAllServers = servers;
      _storeFacets = data.facets || { hostingTypes: [], categories: [] };
      _storePageInfo = data.pageInfo || { hasNextPage: false, endCursor: "" };
      servers.forEach(s => {
        if (s.id && s.environmentVariablesJsonSchema) {
          _storeEnvSchemas[s.id] = s.environmentVariablesJsonSchema;
        }
      });
      _storeCacheFetched = true;
      _renderStoreFilters();
      searchStore();
    } catch (err) {
      grid.innerHTML = "<div class='store-loading store-error'>Erro ao carregar servidores. Tente novamente.</div>";
    }
  }

  async function _fetchStoreServers() {
    if (_storeCacheFetched) return;
    try {
      let cursor = "";
      let hasNext = true;
      while (hasNext) {
        const url = cursor ? "/v1/store/servers?cursor=" + encodeURIComponent(cursor) : "/v1/store/servers";
        const data = await apiFetch(url);
        const batch = data.servers || [];
        _storeAllServers = _storeAllServers.concat(batch);
        _storeFacets = data.facets || _storeFacets;
        batch.forEach(s => {
          if (s.id && s.environmentVariablesJsonSchema) {
            _storeEnvSchemas[s.id] = s.environmentVariablesJsonSchema;
          }
        });
        const grid = document.getElementById("storeGrid");
        const modal = document.getElementById("storeModal");
        if (grid && modal && modal.classList.contains("open")) {
          _renderStoreFilters();
          const q = (document.getElementById("storeSearch")?.value || "").toLowerCase();
          let filtered = _storeAllServers;
          if (q) filtered = filtered.filter(s => (s.name || "").toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q) || (s.namespace || "").toLowerCase().includes(q) || (s.slug || "").toLowerCase().includes(q));
          if (_storeFilterHosting) filtered = filtered.filter(s => (s.attributes || []).includes("hosting:" + _storeFilterHosting));
          if (_storeFilterCategory) filtered = filtered.filter(s => (s.categories || []).includes(_storeFilterCategory));
          const savedPage = _storePage;
          _renderStoreGrid(_sortServers(filtered, _storeSort));
          if (_storePage !== savedPage) {
            _storePage = Math.min(savedPage, Math.ceil(_storeAllServers.length / _storePerPage));
            _renderStoreGrid(_sortServers(filtered, _storeSort));
          }
        }
        const info = data.pageInfo || { hasNextPage: false, endCursor: "" };
        hasNext = info.hasNextPage && !!info.endCursor;
        cursor = info.endCursor || "";
      }
      _storePageInfo = { hasNextPage: false, endCursor: "" };
      _storeCacheFetched = true;
    } catch (_) {}
  }

  async function loadMoreStore() {}

  function setStoreFilterHosting(type) {
    _storeFilterHosting = _storeFilterHosting === type ? "" : type;
    _renderStoreFilters();
    searchStore();
  }

  function setStoreFilterCategory(cat) {
    _storeFilterCategory = _storeFilterCategory === cat ? "" : cat;
    _renderStoreFilters();
    searchStore();
  }

  function _renderStoreFilters() {
    const bar = document.getElementById("storeFilterBar");
    const catBar = document.getElementById("storeCategoryBar");
    if (!bar) return;

    const hostIcons = {
      "remote-capable": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M11 2h2a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h2"/><path d="M8 11v1"/><path d="M5 5.5 8 2l3 3.5"/></svg>',
      "hybrid": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M13 8A5 5 0 1 1 8 3"/><path d="M13 3v3h-3"/><path d="M3 8A5 5 0 1 0 8 3"/></svg>',
      "local-only": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="3" width="12" height="9" rx="1.5"/><path d="M6 14h4"/><path d="M8 12v2"/></svg>',
    };
    const hostLabels = { "remote-capable": __("store.remote"), "hybrid": __("store.hybrid"), "local-only": __("store.local") };
    bar.innerHTML = _storeFacets.hostingTypes.map(t =>
      `<button class="store-filter-btn${_storeFilterHosting === t ? " active" : ""}" onclick="setStoreFilterHosting('${_escHtml(t)}')">${hostIcons[t] || ""}<span>${hostLabels[t] || t}</span></button>`
    ).join("");

    if (catBar) {
      catBar.innerHTML = _storeFacets.categories.map(c =>
        `<button class="store-cat-item${_storeFilterCategory === c.id ? " active" : ""}" onclick="setStoreFilterCategory('${_escHtml(c.id)}')"><span class="store-cat-name">${_escHtml(c.name)}</span><span class="store-cat-count">${c.count}</span></button>`
      ).join("");
    }
  }

  function setStoreSort(sort) {
    _storeSort = sort;
    const sel = document.getElementById("storeSort");
    if (sel) sel.value = sort;
    searchStore();
  }

  function searchStore() {
    const q = (document.getElementById("storeSearch")?.value || "").toLowerCase();
    _storePage = 1;
    let filtered = _storeAllServers;
    if (q) {
      filtered = filtered.filter(s =>
        (s.name || "").toLowerCase().includes(q) ||
        (s.description || "").toLowerCase().includes(q) ||
        (s.namespace || "").toLowerCase().includes(q) ||
        (s.slug || "").toLowerCase().includes(q)
      );
    }
    if (_storeFilterHosting) {
      filtered = filtered.filter(s =>
        (s.attributes || []).includes("hosting:" + _storeFilterHosting)
      );
    }
    if (_storeFilterCategory) {
      filtered = filtered.filter(s =>
        (s.categories || []).includes(_storeFilterCategory)
      );
    }
    const sorted = _sortServers(filtered, _storeSort);
    _renderStoreGrid(sorted);
  }

  function _sortServers(arr, sortKey) {
    const copy = [...arr];
    switch (sortKey) {
      case "name": return copy.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
      case "name_desc": return copy.sort((a, b) => (b.name || "").localeCompare(a.name || ""));
      case "stars": return copy.sort((a, b) => (b.stars || 0) - (a.stars || 0));
      case "tools": return copy.sort((a, b) => (b.tools || []).length - (a.tools || []).length);
      default: return copy;
    }
  }

  function _renderStoreGrid(servers) {
    const grid = document.getElementById("storeGrid");
    if (!grid) return;
    if (!servers.length) {
      const q = (document.getElementById("storeSearch")?.value || "").trim();
      if (q && !_storeCacheFetched) {
        grid.innerHTML = "<div class='store-loading'>A pesquisar em mais servidores...</div>";
      } else {
        grid.innerHTML = "<div class='store-loading'>Nenhum servidor encontrado.</div>";
      }
      const loadMore = document.getElementById("storeLoadMore");
      if (loadMore) loadMore.style.display = "none";
      _renderStorePagination(servers);
      return;
    }
    const totalPages = Math.ceil(servers.length / _storePerPage);
    if (_storePage > totalPages) _storePage = totalPages;
    const start = (_storePage - 1) * _storePerPage;
    const page = servers.slice(start, start + _storePerPage);
    const hostBadges = {
      "remote-capable": '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M11 2h2a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h2"/><path d="M8 11v1"/><path d="M5 5.5 8 2l3 3.5"/></svg> ' + __("store.remote"),
      "hybrid": '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M13 8A5 5 0 1 1 8 3"/><path d="M13 3v3h-3"/><path d="M3 8A5 5 0 1 0 8 3"/></svg> ' + __("store.hybrid"),
      "local-only": '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="3" width="12" height="9" rx="1.5"/><path d="M6 14h4"/><path d="M8 12v2"/></svg> ' + __("store.local"),
    };
    grid.innerHTML = page.map(s => {
      const name = s.name || s.slug || "MCP Server";
      const desc = s.description || "";
      const hostType = (s.attributes || []).find(a => a.startsWith("hosting:"))?.split(":")[1] || "";
      const badge = hostBadges[hostType] || "";
      const namespace = s.namespace || "";
      const toolCount = (s.tools || []).length;
      const stars = s.stars || 0;
      const repoUrl = (s.repository && s.repository.url) || "";
      return `<div class="store-card" onclick="installFromStore('${_escHtml(s.id || "")}', '${_escHtml(namespace)}', '${_escHtml(s.slug || "")}', '${_escHtml(name)}', '${_escHtml(hostType)}', '${_escHtml(repoUrl)}')">
        <div class="store-card-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></div>
        <div class="store-card-body">
          <div class="store-card-name">${_escHtml(name)}</div>
          <div class="store-card-desc">${_escHtml(desc)}</div>
          <div class="store-card-footer">
            ${badge ? `<span class="store-card-badge">${badge}</span>` : ""}
            ${namespace ? `<span class="store-card-cmd">${_escHtml(namespace)}</span>` : ""}
            ${toolCount > 0 ? `<span class="store-card-tag">${toolCount} tools</span>` : ""}
            ${stars > 0 ? `<span class="store-card-star"><svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1l2 4.5 4.9.5-3.7 3.2L12.5 14 8 11.5 3.5 14l1.3-4.8L 1 6l4.9-.5z"/></svg> ${stars}</span>` : ""}
          </div>
        </div>
      </div>`;
    }).join("");;
    const loadMore = document.getElementById("storeLoadMore");
    if (loadMore) loadMore.style.display = "none";
    _renderStorePagination(servers);
  }

  function _renderStorePagination(servers) {
    const el = document.getElementById("storePagination");
    if (!el) return;
    const total = servers.length;
    const totalPages = Math.ceil(total / _storePerPage);
    if (totalPages <= 1) { el.style.display = "none"; return; }
    el.style.display = "flex";
    let html = `<button class="store-page-btn" onclick="window._prevPage()"${_storePage <= 1 ? ' disabled' : ''}>&#9664; ${__('pagination.prev')}</button>`;
    html += `<span class="store-page-info">${_storePage} / ${totalPages}</span>`;
    html += `<button class="store-page-btn" onclick="window._nextPage()"${_storePage >= totalPages ? ' disabled' : ''}>${__('pagination.next')} &#9654;</button>`;
    el.innerHTML = html;
  }

  function _prevPage() {
    if (_storePage <= 1) return;
    _storePage--;
    const q = (document.getElementById("storeSearch")?.value || "").toLowerCase();
    let filtered = _storeAllServers;
    if (q) filtered = filtered.filter(s => (s.name || "").toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q) || (s.namespace || "").toLowerCase().includes(q) || (s.slug || "").toLowerCase().includes(q));
    _renderStoreGrid(filtered);
  }

  function _nextPage() {
    const q = (document.getElementById("storeSearch")?.value || "").toLowerCase();
    let filtered = _storeAllServers;
    if (q) filtered = filtered.filter(s => (s.name || "").toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q) || (s.namespace || "").toLowerCase().includes(q) || (s.slug || "").toLowerCase().includes(q));
    const totalPages = Math.ceil(filtered.length / _storePerPage);
    if (_storePage >= totalPages) return;
    _storePage++;
    _renderStoreGrid(filtered);
  }

  function _escHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function installFromStore(serverId, namespace, slug, name, hostType, repoUrl) {
    closeStoreModal();
    const tab = document.getElementById("mergeTabSandbox");
    if (tab) tab.click();
    let pkg;
    if (namespace && slug) {
      pkg = `@${namespace}/${slug}`;
    } else if (slug) {
      pkg = slug;
    } else {
      pkg = serverId;
    }
    const isRemoteHost = hostType === "remote-capable" && !namespace && !slug;
    const warning = document.getElementById("mergePackageWarning");
    if (warning) warning.style.display = "none";
    const cfg = { command: "npx", args: [pkg] };
    const ta = document.getElementById("mergeStdioJson");
    if (ta) ta.value = JSON.stringify(cfg, null, 2);
    fetch("/v1/store/check-package?name=" + encodeURIComponent(pkg) + "&namespace=" + encodeURIComponent(namespace || "") + "&slug=" + encodeURIComponent(slug || "") + "&repo_url=" + encodeURIComponent(repoUrl || "")).then(r => r.json()).then(data => {
      if (data.remote_urls && data.remote_urls.length) {
        const remoteCfg = { url: data.remote_urls[0], type: "streamable-http" };
        if (ta) ta.value = JSON.stringify(remoteCfg, null, 2);
        return;
      }
      if (data.command && data.args) {
        const newCfg = { command: data.command, args: data.args };
        if (ta) ta.value = JSON.stringify(newCfg, null, 2);
      }
      if (!data.exists && warning) {
        warning.style.display = "";
        let msg = __("store.package_not_found").replace("{pkg}", pkg);
        if (data.alternatives && data.alternatives.length) {
          const alt = data.alternatives[0];
          msg += " " + __("store.using_alternative") + " " + alt.command + " " + (alt.args || []).join(" ");
        }
        warning.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><path d="M8 5v3"/><circle cx="8" cy="11" r="0.5" fill="currentColor"/></svg> ' + _escHtml(msg);
      }
    }).catch(() => {});
    const schema = _storeEnvSchemas[serverId];
    const envContainer = document.getElementById("mergeEnvFields");
    if (!envContainer) return;
    const props = (schema && schema.properties) || {};
    const required = (schema && schema.required) || [];
    const keys = Object.keys(props);
    if (!keys.length && !isRemoteHost) {
      envContainer.style.display = "none";
      return;
    }
    envContainer.style.display = "";
    let html = '<div class="env-title">' + __("env.title") + '</div>';
    if (keys.length) {
      html += keys.map(k => {
        const p = props[k];
        const isReq = required.includes(k);
        const desc = (p && p.description) || "";
        const ph = (p && p.placeholder) || (p && p.default != null ? p.default : "");
        return `<div class="form-group env-field">
          <label for="env_${_escHtml(k)}">${_escHtml(k)}${isReq ? ' <span class="env-req">*</span>' : ''}</label>
          <input type="text" id="env_${_escHtml(k)}" class="env-input" placeholder="${_escHtml(ph || desc)}" ${isReq ? 'required' : ''} />
          ${desc ? `<p class="form-hint">${_escHtml(desc)}</p>` : ""}
        </div>`;
      }).join("");
    }
    if (isRemoteHost && !keys.length) {
      html += '<div class="form-group env-field">';
      html += '<label for="env_Authorization">Authorization <span class="env-opt">(opcional)</span></label>';
      html += '<input type="text" id="env_Authorization" class="env-input" placeholder="Bearer seu-token-aqui" />';
      html += '<p class="form-hint">' + __("env.auth_desc") + '</p>';
      html += '</div>';
    }
    envContainer.innerHTML = html;
  }

  async function confirmMerge() {
    const name = document.getElementById("mergeName")?.value?.trim();
    const errorEl = document.getElementById("mergeError");
    const btn = document.getElementById("btnMergeConfirm");
    if (errorEl) showModalError(errorEl, "");
    if (!name) { if (errorEl) showModalError(errorEl, "Informe o nome do servidor merged."); return; }

    if (mergeMode === "sandbox") {
      const jsonText = document.getElementById("mergeStdioJson")?.value?.trim();
      if (!jsonText) { if (errorEl) showModalError(errorEl, __("server.merge_config_required")); return; }
      let cfg;
      try { cfg = JSON.parse(jsonText); } catch {
        if (errorEl) showModalError(errorEl, __("server.merge_error_json"));
        return;
      }

      const hasMcpServers = !!cfg.mcpServers;
      const getNamespace = (cfg) => {
        let ns = (cfg.name || "").toLowerCase().replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
        if (!ns && cfg.command) ns = cfg.command.replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
        if (!ns && cfg.url) ns = (() => { try { return new URL(cfg.url).hostname.replace(/[^a-z0-9]/g, "_"); } catch { return "remote"; } })();
        return ns || "sandbox";
      };
      const namespace = getNamespace(cfg);

      const envContainer = document.getElementById("mergeEnvFields");
      const envInputs = envContainer ? envContainer.querySelectorAll(".env-input") : [];
      const collectEnv = () => {
        let missingReq = false;
        const vars = {};
        envInputs.forEach(inp => {
          const val = inp.value.trim();
          if (inp.hasAttribute("required") && !val) { missingReq = true; return; }
          if (val) vars[inp.id.replace("env_", "")] = val;
        });
        return { missingReq, vars };
      };

      if (hasMcpServers) {
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="btn-spinner"></span> A criar...'; }
        try {
          const { missingReq, vars: envVars } = collectEnv();
          if (missingReq) throw new Error(__("server.merge_error_env"));
          if (Object.keys(envVars).length) {
            const name = Object.keys(cfg.mcpServers)[0];
            cfg.mcpServers[name] = { ...cfg.mcpServers[name], env: { ...(cfg.mcpServers[name].env || {}), ...envVars } };
          }
          await apiFetch("/v1/servers/merge", {
            method: "POST",
            body: JSON.stringify({ source_server_id: mergeSourceId, stdio_config: cfg, namespace, merged_name: name }),
          });
          closeMergeModal();
          showLoading("Servidor merged criado! Carregando...", false);
          await loadServers(true);
          hideLoading();
          window.showAppAlert("Servidor merged (config) criado com sucesso.");
        } catch (err) {
          if (errorEl) showModalError(errorEl, err.message);
          window.showAppAlert("Erro no merge: " + err.message);
        } finally {
          if (btn) { btn.disabled = false; btn.textContent = "Criar Servidor Merged"; }
        }
        return;
      }

      if (cfg.url) {
        const { missingReq, vars: headersVars } = collectEnv();
        if (missingReq) {
          if (errorEl) showModalError(errorEl, __("server.merge_error_env"));
          return;
        }
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="btn-spinner"></span> A criar...'; }
        try {
          const body = {
            source_server_id: mergeSourceId,
            remote_url: cfg.url,
            remote_transport: cfg.type || "streamable-http",
            remote_headers: Object.keys(headersVars).length ? headersVars : undefined,
            namespace,
            merged_name: name,
          };
          if (cfg.tools) body.remote_tools = cfg.tools;
          await apiFetch("/v1/servers/merge", { method: "POST", body: JSON.stringify(body) });
          closeMergeModal();
          showLoading("Servidor merged criado! Carregando...", false);
          await loadServers(true);
          hideLoading();
          window.showAppAlert("Servidor merged (remoto) criado com sucesso.");
        } catch (err) {
          if (errorEl) showModalError(errorEl, err.message);
          window.showAppAlert("Erro no merge remoto: " + err.message);
        } finally {
          if (btn) { btn.disabled = false; btn.textContent = "Criar Servidor Merged"; }
        }
        return;
      }
      if (!cfg.command) { if (errorEl) showModalError(errorEl, "JSON precisa do campo 'command' ou 'mcpServers'."); return; }
      const { missingReq, vars: envVars } = collectEnv();
      if (missingReq) {
        if (errorEl) showModalError(errorEl, __("server.merge_error_env"));
        return;
      }
      if (Object.keys(envVars).length) {
        cfg = { ...cfg, env: { ...(cfg.env || {}), ...envVars } };
      }
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="btn-spinner"></span> A criar...'; }
      try {
        await apiFetch("/v1/servers/merge", {
          method: "POST",
          body: JSON.stringify({ source_server_id: mergeSourceId, stdio_config: cfg, namespace, merged_name: name }),
        });
        closeMergeModal();
        showLoading("Servidor merged criado! Carregando...", false);
        await loadServers(true);
        hideLoading();
        window.showAppAlert("Servidor merged (sandbox) criado com sucesso.");
      } catch (err) {
        if (errorEl) showModalError(errorEl, err.message);
        window.showAppAlert("Erro no merge sandbox: " + err.message);
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = "Criar Servidor Merged"; }
      }
      return;
    }

    // Local merge (select box)
    const targetId = document.getElementById("mergeTargetSelect")?.value;
    if (!targetId) { if (errorEl) showModalError(errorEl, "Selecione um servidor alvo."); return; }
    mergeTargetId = targetId;

    const srcCard = document.querySelector(`.server-card[data-server-id="${mergeSourceId}"]`);
    const srcName = srcCard?.dataset?.serverName || mergeSourceId;
    const namespace = String(srcName).toLowerCase().replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "merged";
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="btn-spinner"></span> A criar...'; }
    try {
      await apiFetch("/v1/servers/merge", {
        method: "POST",
        body: JSON.stringify({ source_server_id: mergeSourceId, target_server_id: targetId, namespace, merged_name: name }),
      });
      closeMergeModal();
      showLoading("Servidor merged criado! Carregando...", false);
      await loadServers(true);
      hideLoading();
      window.showAppAlert("Servidor merged (local) criado com sucesso.");
    } catch (err) {
      if (errorEl) showModalError(errorEl, err.message);
      window.showAppAlert("Erro no merge local: " + err.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Criar Servidor Merged"; }
    }
  }

  // ─── Edit ──────────────────────────────────────────────
  function editServer(serverId, name, transportType) {
    editingServerId = serverId;
    const en = document.getElementById("editName");
    const et = document.getElementById("editTransport");
    const es = document.getElementById("editStatus");
    const ee = document.getElementById("editError");
    const em = document.getElementById("editModal");
    if (en) en.value = name;
    if (et) et.value = transportType === "sse" ? "sse" : "http";
    if (es) es.value = "active";
    if (ee) showModalError(ee, "");
    if (em) em.classList.add("open");
  }
  async function saveEdit() {
    const name = document.getElementById("editName")?.value?.trim();
    const transport = document.getElementById("editTransport")?.value;
    const status = document.getElementById("editStatus")?.value;
    const errorEl = document.getElementById("editError");
    const btn = document.getElementById("btnEditConfirm");
    if (errorEl) showModalError(errorEl, "");
    if (!name) {
      if (errorEl) showModalError(errorEl, __("server.edit_name_required"));
      return;
    }
    if (btn) btn.disabled = true;
    if (btn) btn.textContent = "Salvando...";
    try {
      await apiFetch(`/v1/servers/${editingServerId}`, {
        method: "PATCH",
        body: JSON.stringify({ name, status, transport }),
      });
      closeEditModal();
      await loadServers(true);
      window.showAppAlert("Servidor atualizado com sucesso.");
    } catch (err) {
      if (errorEl) showModalError(errorEl, err.message);
      window.showAppAlert("Erro ao atualizar servidor: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Salvar";
      }
    }
  }
  function closeEditModal() {
    const em = document.getElementById("editModal");
    if (em) em.classList.remove("open");
    editingServerId = null;
  }

  // ─── Inspector ─────────────────────────────────────────
  async function openInspector(serverId) {
    if (!serverId) { window.showAppAlert(__("server.not_found")); return; }
    if (_inspecting) return;
    _inspecting = true;
    showLoading("A iniciar MCP Inspector...", false);
    // Open a blank window synchronously while still inside the user-gesture call
    // stack. Browsers block window.open() after an await (async break), so we
    // must open the window BEFORE the network call and then navigate it.
    const inspectorWin = window.open("", "_blank");
    if (inspectorWin) {
      inspectorWin.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>A iniciar MCP Inspector...</title>
          <style>
            body {
              margin: 0;
              height: 100vh;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              background: #f8fafc;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
              color: #0f172a;
            }
            .spinner {
              width: 36px;
              height: 36px;
              border: 3px solid #e2e8f0;
              border-top-color: #6366f1;
              border-radius: 50%;
              animation: spin 0.8s linear infinite;
            }
            h3 {
              margin: 16px 0 6px 0;
              font-size: 1rem;
              font-weight: 600;
            }
            p {
              margin: 0;
              font-size: 0.85rem;
              color: #64748b;
            }
            @keyframes spin {
              to { transform: rotate(360deg); }
            }
          </style>
        </head>
        <body>
          <div class="spinner"></div>
          <h3>A iniciar MCP Inspector</h3>
          <p>Por favor, aguarde enquanto o gateway inicializa o processo...</p>
        </body>
        </html>
      `);
      inspectorWin.document.close();
    }
    try {
      const data = await apiFetch("/v1/servers/" + serverId + "/inspector", { method: "POST" });
      if (data && data.inspector_url) {
        if (inspectorWin && !inspectorWin.closed) {
          inspectorWin.location.href = data.inspector_url;
        } else {
          // Fallback: popup was blocked, try again (will likely be blocked too,
          // but at least the user gets a clear error from showAppAlert below)
          const w = window.open(data.inspector_url, "_blank");
          if (!w) {
            window.showAppAlert(
              "O popup blocker impediu a abertura do MCP Inspector.\n" +
              "Abra manualmente: " + data.inspector_url
            );
          }
        }
      } else {
        if (inspectorWin && !inspectorWin.closed) inspectorWin.close();
        window.showAppAlert(__("server.inspector_no_url"));
      }
    } catch (err) {
      if (inspectorWin && !inspectorWin.closed) inspectorWin.close();
      window.showAppAlert("Erro ao iniciar inspector: " + err.message);
    } finally {
      hideLoading();
      _inspecting = false;
    }
  }

  // ─── Copy URL ──────────────────────────────────────────
  function copyUrl(btn, url) {
    if (!url) return;
    navigator.clipboard.writeText(url).then(() => {
      btn.textContent = "Copiado ✓";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = "Copy URL";
        btn.classList.remove("copied");
      }, 2000);
    });
  }

  // ─── Modals ─────────────────────────────────────────────
  function openCreateModal() {
    const cm = document.getElementById("createModal");
    const inEl = document.getElementById("inputName");
    const isEl = document.getElementById("inputSpecUrl");
    const me = document.getElementById("modalError");
    const bcc = document.getElementById("btnCreateConfirm");
    if (cm) cm.classList.add("open");
    if (inEl) inEl.value = "";
    if (isEl) isEl.value = "";
    if (me) showModalError(me, "");
    if (bcc) {
      bcc.disabled = false;
      bcc.textContent = "Criar Servidor";
    }
    setTimeout(() => {
      const f = document.getElementById("inputName");
      if (f) f.focus();
    }, 120);
  }
  function closeCreateModal() {
    const cm = document.getElementById("createModal");
    if (cm) cm.classList.remove("open");
  }

  function showModalError(el, msg) {
    if (!el) return;
    el.textContent = msg;
    el.classList.toggle("visible", !!msg);
  }

  // ─── Logs ──────────────────────────────────────────────
  function _populateLogServerSelect(srvList) {
    const sel = document.getElementById("logServerSelect");
    if (!sel) return;
    sel.innerHTML = '<option value="">Servidor...</option>';
    srvList.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.server_id;
      opt.textContent = s.name;
      if (s.server_id === get(activeServerId)) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function selectServer(serverId) {
    document.querySelectorAll(".server-card").forEach((c) => c.classList.remove("selected"));
    const card = document.querySelector(`.server-card[data-server-id="${serverId}"]`);
    if (card) card.classList.add("selected");
    activeServerId.set(serverId);
    const sel = document.getElementById("logServerSelect");
    if (sel) sel.value = serverId;
    pollLogs();
  }

  function switchLogServer(serverId) {
    selectServer(serverId || get(activeServerId));
  }

  function debouncePoll() {
    clearTimeout(logDebounceTimer);
    logDebounceTimer = setTimeout(pollLogs, 300);
  }

  function relativeTime(isoStr) {
    const now = Date.now();
    const t = new Date(isoStr).getTime();
    const diff = now - t;
    const sec = Math.floor(diff / 1000);
    if (sec < 5) return "agora";
    if (sec < 60) return `${sec}s`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h}h`;
    return `${Math.floor(h / 24)}d`;
  }

  function methodBadge(method) {
    const colors = {GET:'#00d4aa',POST:'#1a56ff',PUT:'#ff9f1c',PATCH:'#ff9f1c',DELETE:'#ff5c35'};
    const color = colors[method] || '#7a7a8a';
    return `<span style="display:inline-block;font-size:0.58rem;font-weight:700;padding:1px 5px;border-radius:3px;background:${color}22;color:${color};margin-right:4px">${escapeHtml(method || '?')}</span>`;
  }

  async function pollLogs() {
    const currentId = get(activeServerId);
    if (!currentId) return;
    try {
      const toolFilter = document.getElementById("logToolFilter")?.value?.trim() || "";
      const statusFilter = document.getElementById("logStatusFilter")?.value || "";
      let params = `limit=20`;
      if (toolFilter) params += `&tool=${encodeURIComponent(toolFilter)}`;
      if (statusFilter) {
        const [smin, smax] = statusFilter.split("-");
        if (smin) params += `&status_min=${smin}`;
        if (smax) params += `&status_max=${smax}`;
      }
      const logs = await apiFetch(`/v1/servers/${currentId}/logs?${params}`);
      const container = document.getElementById("liveLogs");
      if (!container) return;
      container.innerHTML = "";

      if (!logs || logs.length === 0) {
        container.innerHTML = '<div style="color:rgba(255,255,255,0.2)">Nenhuma chamada ainda...</div>';
        return;
      }
      logs.forEach((log) => {
        const isSuccess = log.status_code >= 200 && log.status_code < 300;
        const row = document.createElement("div");
        row.className = "log-entry";
        row.style.cursor = "pointer";
        row.onclick = () => openLogDetail(log);

        const line1 = document.createElement("div");
        line1.className = "log-line1";
        line1.innerHTML = `${methodBadge(log.method)}<span class="${isSuccess ? "hl" : "log-err"}">${escapeHtml(log.tool_called)}</span>`;

        const line2 = document.createElement("div");
        line2.className = "log-line2";
        line2.innerHTML = `<span class="${isSuccess ? "" : "log-err"}">[${log.status_code}]</span> ${log.duration_ms.toFixed(0)}ms · <span class="log-time">${relativeTime(log.timestamp)}</span>`;

        row.appendChild(line1);
        row.appendChild(line2);
        container.appendChild(row);
      });
      container.scrollTop = container.scrollHeight;
    } catch {}
  }

  async function openLogDetail(log) {
    const currentId = get(activeServerId);
    if (!currentId) return;
    try {
      const detail = await apiFetch(`/v1/servers/${currentId}/logs/${log.id}`);
      const dt = document.getElementById("detailTool");
      const dm = document.getElementById("detailMethod");
      const stEl = document.getElementById("detailStatus");
      const dd = document.getElementById("detailDuration");
      const dti = document.getElementById("detailTime");
      const reqBody = document.getElementById("detailReqBody");
      const resBody = document.getElementById("detailResBody");
      const ldm = document.getElementById("logDetailModal");
      if (dt) dt.textContent = detail.tool_called || "—";
      if (dm) dm.textContent = detail.method || "—";
      if (stEl) {
        stEl.textContent = detail.status_code;
        stEl.className = detail.status_code >= 200 && detail.status_code < 300 ? "status-badge success" : "status-badge error";
      }
      if (dd) dd.textContent = `${detail.duration_ms.toFixed(1)}ms`;
      if (dti) dti.textContent = new Date(detail.timestamp).toLocaleString();

      if (reqBody) {
        if (detail.request_body) {
          try { reqBody.textContent = JSON.stringify(JSON.parse(detail.request_body), null, 2); }
          catch { reqBody.textContent = detail.request_body; }
        } else {
          reqBody.textContent = "(vazio)";
        }
      }

      if (resBody) {
        if (detail.response_body) {
          try { resBody.textContent = JSON.stringify(JSON.parse(detail.response_body), null, 2); }
          catch { resBody.textContent = detail.response_body; }
        } else {
          resBody.textContent = "(vazio)";
        }
      }

      if (ldm) ldm.classList.add("open");
    } catch (err) {
      console.error("Erro ao carregar detalhe do log:", err);
    }
  }

  function closeLogDetail() {
    const ldm = document.getElementById("logDetailModal");
    if (ldm) ldm.classList.remove("open");
  }

  async function exportLogs(format) {
    const currentId = get(activeServerId);
    if (!currentId) return;
    window.open(`${API_BASE}/v1/servers/${currentId}/logs/export?format=${format}`, "_blank");
  }

  function clearLogs() {
    const currentId = get(activeServerId);
    if (!currentId) return;
    showConfirmDialog("Limpar todos os logs deste servidor?", async () => {
      try {
        await apiFetch(`/v1/servers/${currentId}/logs`, { method: "DELETE" });
        pollLogs();
        window.showAppAlert("Logs limpos com sucesso.");
      } catch (err) {
        window.showAppAlert("Erro ao limpar logs: " + err.message);
      }
    });
  }

  function startLogsPolling() {
    if (logsInterval) clearInterval(logsInterval);
    pollLogs();
    logsInterval = setInterval(pollLogs, POLL_LOGS_INTERVAL);
  }

  // ─── Gateway ───────────────────────────────────────────
  async function checkGateway() {
    try {
      const h = await apiFetch("/health");
      const el = document.getElementById("gatewayStatus");
      if (!el) return;
      el.textContent = `ok · ${h.active_servers} ativos`;
      el.className = "stat-value ok";
    } catch {
      const el = document.getElementById("gatewayStatus");
      if (!el) return;
      el.textContent = "offline";
      el.className = "stat-value";
      el.style.color = "var(--warn)";
    }
  }

  // ─── Profile Modal ─────────────────────────────────────
  function openProfileModal() {
    if (!currentUser) return;
    const token = getAuthToken();
    const email = currentUser.email || "";
    const name = currentProfile?.name || currentUser.user_metadata?.full_name || currentUser.user_metadata?.name || email.split("@")[0] || "";
    const avatarUrl = currentProfile?.avatar_url || currentUser.user_metadata?.avatar_url || "";
    const plan = (currentProfile?.plan_tier || "free");
    const userId = currentUser.id || "";
    const createdAt = currentUser.created_at ? new Date(currentUser.created_at).toLocaleDateString("pt-PT", { year: "numeric", month: "long", day: "numeric" }) : "—";
    const provider = (currentUser.app_metadata?.provider || "email").toUpperCase();

    const initials = name ? name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2) : email[0]?.toUpperCase() || "U";

    const avatarHtml = avatarUrl
      ? `<img src="${escapeHtml(avatarUrl)}" alt="" class="profile-modal-avatar-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" /><span class="profile-modal-avatar-initials" style="display:none">${initials}</span>`
      : `<span class="profile-modal-avatar-initials">${initials}</span>`;

    const paw = document.getElementById("profileAvatarWrap");
    const pn = document.getElementById("profileName");
    const pe = document.getElementById("profileEmail");
    const pp = document.getElementById("profilePlan");
    const ppr = document.getElementById("profileProvider");
    const pui = document.getElementById("profileUserId");
    const pca = document.getElementById("profileCreatedAt");
    const tokenInput = document.getElementById("profileToken");
    const psc = document.getElementById("profileServersCount");
    const prpm = document.getElementById("profileRpm");
    const pm = document.getElementById("profileModal");

    if (paw) paw.innerHTML = avatarHtml;
    if (pn) pn.textContent = name || "Utilizador";
    if (pe) pe.textContent = email;
    if (pp) {
      pp.textContent = plan;
      pp.className = `profile-plan-badge ${plan}`;
    }
    if (ppr) ppr.textContent = provider;
    if (pui) pui.textContent = userId;
    if (pca) pca.textContent = createdAt;
    if (tokenInput) tokenInput.value = token || __("profile.not_authenticated");

    if (currentProfile) {
      if (psc) psc.textContent = `${currentProfile.servers_count ?? 0} / ${currentProfile.servers_limit ?? 1}`;
      if (prpm) prpm.textContent = plan === "pro" ? "100" : "10";
    } else {
      if (psc) psc.textContent = "—";
      if (prpm) prpm.textContent = "—";
    }

    if (pm) pm.classList.add("open");
  }

  function closeProfileModal() {
    const pm = document.getElementById("profileModal");
    if (pm) pm.classList.remove("open");
  }

  function copyToken() {
    const val = document.getElementById("profileToken")?.value;
    if (!val || val === __("profile.not_authenticated")) return;
    navigator.clipboard.writeText(val).then(() => {
      const btn = document.getElementById("copyTokenBtn");
      if (!btn) return;
      btn.textContent = "Copiado ✓";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = "Copiar";
        btn.classList.remove("copied");
      }, 2000);
    });
  }

  function toggleTokenVisibility() {
    const input = document.getElementById("profileToken");
    const btn = document.getElementById("toggleTokenBtn");
    if (!input || !btn) return;
    if (input.type === "password") {
      input.type = "text";
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
    } else {
      input.type = "password";
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
    }
  }

  async function logoutFromProfile() {
    closeProfileModal();
    await logout();
  }

  // ─── Reset Password (recovery flow) ──────────────────
  function openResetPasswordModal() {
    const rm = document.getElementById("resetPasswordModal");
    const rp = document.getElementById("resetPasswordInput");
    const re = document.getElementById("resetPasswordError");
    const rb = document.getElementById("btnResetPassword");
    if (rp) rp.value = "";
    if (re) re.textContent = "";
    if (rb) { rb.disabled = false; rb.textContent = "Redefinir Palavra-passe"; }
    if (rm) rm.classList.add("open");
    setTimeout(() => { if (rp) rp.focus(); }, 120);
  }

  function closeResetPasswordModal() {
    const rm = document.getElementById("resetPasswordModal");
    if (rm) rm.classList.remove("open");
  }

  async function confirmResetPassword() {
    const password = document.getElementById("resetPasswordInput")?.value;
    const errorEl = document.getElementById("resetPasswordError");
    const btn = document.getElementById("btnResetPassword");
    if (errorEl) errorEl.textContent = "";
    if (!password || password.length < 6) {
      if (errorEl) errorEl.textContent = "A palavra-passe deve ter pelo menos 6 caracteres.";
      return;
    }
    if (!supabaseClient) {
      window.showAppAlert(__("profile.service_unavailable"));
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = "A redefinir..."; }
    try {
      const { error } = await supabaseClient.auth.updateUser({ password });
      if (error) {
        if (errorEl) errorEl.textContent = error.message;
        window.showAppAlert("Erro ao redefinir: " + error.message);
      } else {
        window.showAppAlert("Palavra-passe redefinida com sucesso!");
        closeResetPasswordModal();
        fetchProfile();
        loadServers(true);
      }
    } catch (err) {
      if (errorEl) errorEl.textContent = err.message;
      window.showAppAlert("Erro ao redefinir: " + err.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Redefinir Palavra-passe"; }
    }
  }

  // ─── Change Password (profile) ────────────────────────
  function toggleChangePassword() {
    const section = document.getElementById("changePasswordSection");
    const btn = document.getElementById("toggleChangePasswordBtn");
    if (!section) return;
    const isHidden = section.style.display === "none" || !section.style.display;
    section.style.display = isHidden ? "block" : "none";
    if (btn) btn.textContent = isHidden ? "Cancelar" : "Alterar Palavra-passe";
    if (isHidden) {
      const np = document.getElementById("newPasswordInput");
      if (np) { np.value = ""; setTimeout(() => np.focus(), 100); }
    }
  }

  async function saveNewPassword() {
    const password = document.getElementById("newPasswordInput")?.value;
    const errorEl = document.getElementById("changePasswordError");
    const btn = document.getElementById("btnSavePassword");
    if (errorEl) errorEl.textContent = "";
    if (!password || password.length < 6) {
      if (errorEl) errorEl.textContent = "A nova palavra-passe deve ter pelo menos 6 caracteres.";
      return;
    }
    if (!supabaseClient) {
      window.showAppAlert(__("profile.service_unavailable"));
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = "A guardar..."; }
    try {
      const { error } = await supabaseClient.auth.updateUser({ password });
      if (error) {
        if (errorEl) errorEl.textContent = error.message;
        window.showAppAlert("Erro ao alterar: " + error.message);
      } else {
        window.showAppAlert("Palavra-passe alterada com sucesso!");
        toggleChangePassword();
      }
    } catch (err) {
      if (errorEl) errorEl.textContent = err.message;
      window.showAppAlert("Erro ao alterar: " + err.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Guardar"; }
    }
  }

  // ─── Init ──────────────────────────────────────────────
  onMount(() => {
    installAppAlert();

    window.loginWith = loginWith;
    window.logout = logout;
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    window.openProfileModal = openProfileModal;
    window.closeProfileModal = closeProfileModal;
    window.copyToken = copyToken;
    window.toggleTokenVisibility = toggleTokenVisibility;
    window.logoutFromProfile = logoutFromProfile;
    window.copyUrl = copyUrl;
    window.openInspector = openInspector;
    window.editServer = editServer;
    window.toggleServerStatus = toggleServerStatus;
    window.deleteServer = (serverId) => {
      try {
        debug("window.deleteServer", { serverId });
        return deleteServer(serverId);
      } catch (e) {
        console.error("[dashboard-debug] window.deleteServer:error", e);
        notifyAppAlert("Erro ao executar Remover servidor.");
        throw e;
      }
    };
    window.unmergeServer = (serverId) => {
      try {
        debug("window.unmergeServer", { serverId });
        return unmergeServer(serverId);
      } catch (e) {
        console.error("[dashboard-debug] window.unmergeServer:error", e);
        notifyAppAlert("Erro ao executar Desfazer merge.");
        throw e;
      }
    };
    window.openCreateModal = openCreateModal;
    window.closeCreateModal = closeCreateModal;
    window.createServer = createServer;
    window.saveEdit = saveEdit;
    window.closeEditModal = closeEditModal;
    window.closeMergeModal = closeMergeModal;
    window.confirmMerge = confirmMerge;
    window.closeLogDetail = closeLogDetail;
    window.exportLogs = exportLogs;
    window.clearLogs = clearLogs;
    window.loadServers = () => loadServers(true);
    window.switchLogServer = switchLogServer;
    window.debouncePoll = debouncePoll;
    window.handleStripePro = handleStripePro;
    window.pollLogs = pollLogs;
    window.setMergeTab = setMergeTab;
    window.openMergeModalFromMenu = openMergeModalFromMenu;
    window.toggleMenu = toggleMenu;
    window.closeMenu = closeMenu;
    window.closeAllMenus = closeAllMenus;
    window.showConfirmDialog = showConfirmDialog;
    window.openResetPasswordModal = openResetPasswordModal;
    window.closeResetPasswordModal = closeResetPasswordModal;
    window.confirmResetPassword = confirmResetPassword;
    window.toggleChangePassword = toggleChangePassword;
    window.saveNewPassword = saveNewPassword;

    // Store functions referenced in raw HTML/DOM templates (e.g. innerHTML dynamically generated strings)
    window.openStoreModal = openStoreModal;
    window.closeStoreModal = closeStoreModal;
    window.installFromStore = installFromStore;
    window.searchStore = searchStore;
    window.loadMoreStore = loadMoreStore;
    window._prevPage = _prevPage;
    window._nextPage = _nextPage;
    window.setStoreSort = setStoreSort;
    window.setStoreFilterHosting = setStoreFilterHosting;
    window.setStoreFilterCategory = setStoreFilterCategory;

    const mergeModal = document.getElementById("mergeModal");
    if (mergeModal) mergeModal.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeMergeModal();
    });

    const editModal = document.getElementById("editModal");
    if (editModal) editModal.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeEditModal();
    });

    const createModal = document.getElementById("createModal");
    if (createModal) createModal.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeCreateModal();
    });

    const logDetailModal = document.getElementById("logDetailModal");
    if (logDetailModal) logDetailModal.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeLogDetail();
    });

    const profileModal = document.getElementById("profileModal");
    if (profileModal) profileModal.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) closeProfileModal();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeCreateModal();
        closeEditModal();
        closeMergeModal();
      }
      if (
        e.key === "Enter" &&
        document.getElementById("createModal")?.classList.contains("open")
      )
        createServer();
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest("#menuPortal") && !e.target.closest(".menu-btn")) {
        closeAllMenus();
      }
    });

    window.addEventListener("scroll", closeAllMenus, true);
    window.addEventListener("resize", closeAllMenus);

    const _stdioTa = document.getElementById("mergeStdioJson");
    if (_stdioTa) _stdioTa.placeholder = '{\n  "command": "uvx",\n  "args": ["mcp-excel-server"],\n  "env": { "KEY": "val" },\n  "tools": { "tool_name": { "name": "novo_nome", "description": "...", "arguments": { "param": { "default": "x", "hide": true } } } }\n}';

    (async function init() {
      await checkGateway();
      await restoreSession();
      await loadServers(true);
      _initialized = true;
      startLogsPolling();
      _fetchStoreServers();

      if (supabaseClient) {
        const { data: listener } = supabaseClient.auth.onAuthStateChange((event, session) => {
          if (session?.access_token) {
            localStorage.setItem("supabase_token", session.access_token);
            currentUser = session.user;

            if (event === "PASSWORD_RECOVERY") {
              openResetPasswordModal();
              return;
            }

            fetchProfile();
          } else if (event === "SIGNED_OUT") {
            localStorage.removeItem("supabase_token");
            localStorage.removeItem("supabase.auth.token");
            sessionStorage.removeItem("supabase.auth.token");
            currentUser = null;
            currentProfile = null;
            window.location.href = window.location.origin;
          }
        });
      }
    })();
  });

  let draggingId = null;

  function handleDragStart(e, serverId) {
    draggingId = serverId;
    e.dataTransfer.setData("text/plain", serverId);
    e.target.classList.add("dragging");
  }
  function handleDragEnd(e) {
    draggingId = null;
    document.querySelectorAll(".server-card").forEach((c) => c.classList.remove("dragging", "drag-over"));
  }
  function handleDragOver(e) {
    e.preventDefault();
    e.currentTarget.classList.add("drag-over");
  }
  function handleDragLeave(e) {
    e.currentTarget.classList.remove("drag-over");
  }
  function handleDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove("drag-over");
    document.querySelectorAll(".server-card").forEach((c) => c.classList.remove("drag-over"));
  }
</script>

<!-- ── NAVBAR ───────────────────────────────────────────── -->
<nav>
  <div class="nav-inner">
    <a href="index.html" class="logo">
      <span class="logo-mark">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <rect x="1" y="1" width="5" height="5" rx="1.5" fill="white" opacity="0.9" />
          <rect x="8" y="1" width="5" height="5" rx="1.5" fill="white" opacity="0.6" />
          <rect x="1" y="8" width="5" height="5" rx="1.5" fill="white" opacity="0.6" />
          <rect x="8" y="8" width="5" height="5" rx="1.5" fill="white" opacity="0.35" />
        </svg>
      </span>
      rest2mcp
    </a>

    <div class="nav-right" id="navAuth">
      <div class="auth-user" id="authUser" style="display:none">
        <button class="user-profile-btn" id="userProfileBtn" onclick={() => window.openProfileModal()} title={$t('profile.view_profile')}>
          <img class="auth-avatar" id="authAvatar" src="" alt="" onerror={(e) => { e.currentTarget.style.display='none'; e.currentTarget.nextElementSibling.style.display='flex' }} />
          <span class="auth-avatar-fallback" id="authAvatarFallback" style="display:none"></span>
          <span class="auth-name" id="authName"></span>
          <span class="auth-plan" id="authPlan"></span>
        </button>
        <button class="auth-btn logout-btn-nav" onclick={() => window.logout()} title={$t('profile.sign_out_title')}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          {$t('profile.logout')}
        </button>
      </div>
      <div class="auth-login-buttons" id="authLogin" style="display:none"></div>
    </div>
  </div>
</nav>

<!-- ── MAIN LAYOUT ──────────────────────────────────────── -->
<div class="dash-layout">
  <!-- LEFT: Servers -->
  <div class="dash-main">
    <div class="page-header">
      <div class="page-header-text">
        <h2>{$t('dashboard.nav.title')}</h2>
        <p class="sub">{$t('dashboard.page_sub')}</p>
      </div>
      <button class="btn-add-server" onclick={() => window.openCreateModal()}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M7 1v12M1 7h12" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        {$t('dashboard.new_server')}
      </button>
    </div>

    <div class="server-list" id="serverList">
      {#if $serversLoading}
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
              <path d="M5 3h14M5 21h14M7 3v4l5 5-5 5v4M17 3v4l-5 5 5 5v4" />
            </svg>
          </div>
          <div>{$t('dashboard.loading_servers')}<span class="loading-dots"></span></div>
        </div>
      {:else if $serversError}
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ff5c35" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <div style="color:var(--warn)">{$t('dashboard.load_error')}<br/>{$serversError}</div>
          <button onclick={() => loadServers(true)} style="margin-top:1.2rem;padding:8px 18px;border:1px solid var(--border);border-radius:8px;background:white;cursor:pointer;font-family:var(--mono);font-size:0.78rem;transitionall 0.2s;">
            {$t('dashboard.retry')}
          </button>
        </div>
      {:else if $servers.length === 0}
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="14" rx="2"/><path d="M9 16v4M15 16v4M9 20h6"/><path d="M9 6h6M9 10h6"/></svg>
          </div>
          <div>{$t('dashboard.empty')}<br/>{$t('dashboard.empty_hint')}</div>
        </div>
      {:else}
        {#each $servers as s (s.server_id)}
          {@const health = $serverHealth[s.server_id]}
          {@const isActive = s.status === "active"}
          {@const healthError = isActive && health === "error"}
          {@const isMerged = s.is_merged === true}
          {@const authState = serverAuthState[s.server_id]}
          {@const needsAuth = authState?.required && !authState?.authenticated}
          <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
          <div class="server-card"
            class:active-status={isActive}
            class:health-error={healthError}
            class:server-card-merged={isMerged}
            role="button"
            tabindex="0"
            data-server-id={s.server_id}
            data-server-name={s.name}
            data-apikey={s.apikey || ""}
            data-transport={s.transport || "http"}
            draggable={!isMerged}
            ondragstart={(e) => handleDragStart(e, s.server_id)}
            ondragend={handleDragEnd}
            ondragover={handleDragOver}
            ondragleave={handleDragLeave}
            ondrop={handleDrop}
            onclick={() => selectServer(s.server_id)}
            onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') selectServer(s.server_id); }}>
            <div class="server-info">
              <div class="status-icon" class:active={isActive && !healthError} class:inactive={!isActive || healthError}>
                {#if healthError}
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="4" fill="#ff5c35"/><circle cx="8" cy="8" r="7" stroke="#ff5c35" stroke-width="1.5" stroke-opacity="0.3"/></svg>
                {:else if isActive}
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="4" fill="#00d4aa"/><circle cx="8" cy="8" r="7" stroke="#00d4aa" stroke-width="1.5" stroke-opacity="0.3"/></svg>
                {:else}
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="4" fill="#ff5c35"/><circle cx="8" cy="8" r="7" stroke="#ff5c35" stroke-width="1.5" stroke-opacity="0.3"/></svg>
                {/if}
              </div>
              <div class="server-meta">
                <div class="server-name">
                  {escapeHtml(s.name)}
                  {#if isMerged}
                    <span class="merge-badge">
                      <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0l1.2 4.8L14 6l-4.8 1.2L8 12 6.8 7.2 2 6l4.8-1.2z"/></svg>
                      {$t('dashboard.merged_badge')}
                    </span>
                  {/if}
                </div>
                <div class="server-url">
                  {#if healthError}
                    <span style="color:var(--danger)">{$t('dashboard.api_unavailable')}</span>
                  {:else}
                    {escapeHtml(s.url_sse || s.server_id)}
                  {/if}
                  {#if s.merge_info}
                    <span> · {escapeHtml(s.merge_info)}</span>
                  {/if}
                </div>
              </div>
            </div>
            <div class="server-actions">
              <span class="status-chip" class:active={isActive && !healthError && !needsAuth} class:inactive={!isActive || healthError || needsAuth}>
                <span class="status-chip-dot"></span>
                {healthError ? $t('dashboard.api_unavailable') : needsAuth ? $t('auth.needs_login') : isActive ? $t('dashboard.online') : $t('dashboard.offline')}
              </span>
              <button class="btn-copy" disabled={!isActive} onclick={(e) => copyUrl(e.currentTarget, s.url_sse || '')}>
                {$t('dashboard.copy_url')}
              </button>
              <div class="menu-wrapper">
                <button class="menu-btn" onclick={(e) => toggleMenu(s.server_id, e.currentTarget)} title={$t('dashboard.options')}>
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                    <circle cx="7" cy="2" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="7" cy="12" r="1.3"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        {/each}
      {/if}
    </div>
  </div>

  <!-- RIGHT: Sidebar -->
  <div class="dash-sidebar">
    <!-- Plan Card -->
    <div class="sidebar-card">
      <div class="sidebar-card-header">
        <span class="sidebar-label">{$t('dashboard.current_plan')}</span>
        <span class="plan-badge">{$t('dashboard.hobby_badge')}</span>
      </div>
      <div class="stat-grid">
        <div class="stat-row">
          <span class="stat-label">{$t('dashboard.active_servers')}</span>
          <span class="stat-value num">{$serverCount}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">{$t('dashboard.log_retention')}</span>
          <span class="stat-value num">24h</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">{$t('dashboard.gateway')}</span>
          <span class="stat-value ok" id="gatewayStatus">---</span>
        </div>
        <div class="stat-row" id="quotaRowServers" style="display:none">
          <span class="stat-label">{$t('dashboard.servers_label')}</span>
          <span class="stat-value" id="quotaServers">0/1</span>
        </div>
        <div class="stat-row" id="quotaRowPlan" style="display:none">
          <span class="stat-label">{$t('dashboard.plan_label')}</span>
          <span class="stat-value" id="quotaPlan">Free</span>
        </div>
      </div>
      <div class="sub-section" id="subSection" style="display:none">
        <div class="sub-title">{$t('dashboard.subscription')}</div>
        <div class="sub-quota"><span>{$t('dashboard.servers_label')}</span><span class="val" id="subServers">0 / 1</span></div>
        <div class="sub-quota"><span>{$t('profile.rpm_label')}</span><span class="val" id="subRPM">10</span></div>
        <div class="sub-upgrade" id="subUpgrade">
          <button class="sub-upgrade-btn" id="subUpgradeBtn" onclick={() => window.handleStripePro()}>{$t('dashboard.subscribe')}</button>
        </div>
      </div>
    </div>

    <!-- Live Logs -->
    <div class="sidebar-logs">
      <div class="sidebar-logs-header">
        <div class="logs-header-left">
          <span class="pulse-dot"></span>
          <span class="log-title">{$t('dashboard.logs_title')}</span>
          <select class="log-server-select" id="logServerSelect" onchange={() => window.switchLogServer(this.value)}>
            <option value="">{$t('dashboard.log_server_placeholder')}</option>
          </select>
        </div>
        <div class="logs-header-actions">
          <button class="log-action-btn" title={$t('dashboard.export_json')} onclick={() => window.exportLogs('json')}>↓</button>
          <button class="log-action-btn" title={$t('dashboard.export_csv')} onclick={() => window.exportLogs('csv')}>⇩</button>
          <button class="log-action-btn log-action-danger" title={$t('dashboard.clear_logs_btn')} onclick={() => window.clearLogs()}>✕</button>
          <button class="log-refresh-btn" title={$t('dashboard.refresh')} onclick={() => window.pollLogs()}>↻</button>
        </div>
      </div>
      <div class="log-filter-bar">
        <input type="text" class="log-filter-input" id="logToolFilter" placeholder={$t('dashboard.filter_tool')} oninput={() => window.debouncePoll()}>
        <select class="log-filter-select" id="logStatusFilter" onchange={() => window.pollLogs()}>
          <option value="">{$t('dashboard.all')}</option>
          <option value="200-299">{$t('dashboard.success_2xx')}</option>
          <option value="400-499">{$t('dashboard.error_4xx')}</option>
          <option value="500-599">{$t('dashboard.error_5xx')}</option>
        </select>
      </div>
      <div class="sidebar-logs-body" id="liveLogs">
        <div style="color: rgba(255, 255, 255, 0.2)">
          {$t('dashboard.waiting_logs')}
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ── MENU PORTAL ──────────────────────────────────────── -->
<div id="menuPortal">
  {#if activeMenu && activeMenuServer}
    {@const s = activeMenuServer}
    <!-- stopPropagation prevents the global document click-outside listener from
         closing the menu (and destroying this {#if} block) before the button
         handlers have a chance to run. -->
    <div class="menu-dropdown open"
         style="position: fixed; left: {activeMenu.x}px; top: {activeMenu.y}px; z-index: 1000000; min-width: 200px;"
         onclick={(e) => e.stopPropagation()}>
      <button onclick={() => { openInspector(s.server_id); closeAllMenus(); }}>
        <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.2"/><path d="M10.2 10.2L14 14"/></svg></span> {$t('menu.inspect')}
      </button>
      <button onclick={() => { editServer(s.server_id, s.name || '', s.transport || 'http'); closeAllMenus(); }}>
        <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3l8-8z"/></svg></span> {$t('menu.edit')}
      </button>
      <button onclick={() => { openMergeModalFromMenu(s.server_id, s.name || ''); closeAllMenus(); }}>
        <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="8" cy="3" r="1.5"/><path d="M8 7v6M5 10h6"/></svg></span> {$t('menu.merge')}
      </button>
      <button onclick={() => { openToolsModal(s.server_id); closeAllMenus(); }}>
        <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M3 5h10M3 8h10M3 11h7"/></svg></span> {$t('menu.tools')}
      </button>
      <div class="menu-divider"></div>
      <button onclick={() => { toggleServerStatus(s.server_id); closeAllMenus(); }}>
        <span class="menu-icon">
          {#if s.status === "active"}
            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><rect x="3" y="2" width="4" height="12" rx="1"/><rect x="9" y="2" width="4" height="12" rx="1"/></svg>
          {:else}
            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M4 2l10 6-10 6V2z"/></svg>
          {/if}
        </span>
        {s.status === "active" ? $t('menu.deactivate') : $t('menu.activate')}
      </button>
      {#if s.is_merged === true}
        <div class="menu-divider"></div>
        <button onclick={() => { unmergeServer(s.server_id); closeAllMenus(); }}>
          <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M3 3l10 10M13 3l-10 10"/></svg></span> {$t('menu.unmerge')}
        </button>
      {/if}
      <div class="menu-divider"></div>
      <button class="menu-danger" onclick={() => { deleteServer(s.server_id); closeAllMenus(); }}>
        <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M2 4h12"/><path d="M5 4V2h6v2"/><path d="M6 7v5M10 7v5"/><path d="M3 4l1 10h8l1-10"/></svg></span> {$t('menu.delete')}
      </button>
    </div>
  {/if}
</div>

<!-- ── TOOLS MODAL ─────────────────────────────────────────── -->
<div class="modal-overlay" class:open={showToolsModal} onclick={() => closeToolsModal()}>
  <div class="modal-box tools-box" onclick={(e) => e.stopPropagation()}>
    <div class="modal-header">
      <h3>{$t('tools.modal.title')} {toolsModalServer?.name || ""}</h3>
      <p class="modal-sub">{toolsModalServer?.server_id || ""}</p>
    </div>
    {#if serverAuth && !authSuccess && !serverAuth.authenticated}
      <div style="padding:0 0 1rem;border-bottom:1px solid var(--border);margin-bottom:1rem;">
        <div style="font-size:0.85rem;font-weight:600;margin-bottom:0.75rem;display:flex;align-items:center;gap:6px;">
          {$t('auth.login_title')}
          <button class="security-info-btn" onclick={() => showSecurityInfo = !showSecurityInfo}>?</button>
        </div>
        <div style="font-size:0.75rem;color:#9ca3af;margin-bottom:0.75rem;line-height:1.4;">{$t('auth.login_desc')}</div>
        {#if showSecurityInfo}
          <div style="margin-bottom:1rem;padding:0.85rem;background:rgba(0,212,170,0.05);border:1px solid rgba(0,212,170,0.12);border-radius:10px;font-size:0.75rem;color:#9ca3af;line-height:1.6;">
            <div style="font-weight:700;color:var(--accent2);margin-bottom:0.4rem;">{$t('auth.security_full_title')}</div>
            <p style="margin:0 0 0.6rem;">{$t('auth.security_full_desc')}</p>
            <div style="font-weight:600;color:var(--ink);margin-bottom:0.3rem;">{$t('auth.security_why_safer')}</div>
            <ul style="margin:0 0 0.6rem;padding-left:1.2rem;">
              <li style="margin-bottom:0.3rem;"><strong style="color:var(--ink);">{$t('auth.security_zero_exposure')}</strong></li>
              <li><strong style="color:var(--ink);">{$t('auth.security_full_control')}</strong></li>
            </ul>
            <div style="font-weight:600;color:var(--ink);margin-bottom:0.3rem;">{$t('auth.security_token_title')}</div>
            <p style="margin:0 0 0.6rem;">{$t('auth.security_token_desc')}</p>
            <p style="margin:0;font-style:italic;">{$t('auth.security_peace')}</p>
          </div>
        {/if}
        {#each authFields as field}
          <div class="tool-arg-group">
            <label class="tool-arg-label">{field}</label>
            <input class="tool-arg-input" type={["password", "senha", "pwd", "pass", "secret", "palavra-passe", "passwd"].includes(field.toLowerCase()) ? "password" : "text"} placeholder={field} value={authValues[field] ?? ""} oninput={(e) => authValues[field] = e.target.value} />
          </div>
        {/each}
        {#if authError}
          <div style="color:var(--warn);font-size:0.8rem;margin:0.5rem 0;">{authError}</div>
        {/if}
        <button class="btn-confirm" style="margin-top:0.5rem;" onclick={loginToServer} disabled={authLoggingIn}>
          {authLoggingIn ? $t('auth.authenticating') : $t('auth.authenticate')}
        </button>
      </div>
    {/if}
    {#if toolsLoading}
      <div style="padding:2rem;text-align:center;color:#6b7280;">{$t('tools.modal.loading')}</div>
    {:else if toolsError}
      <div class="modal-error" style="display:block">{toolsError}</div>
    {:else if toolsList.length === 0}
      <div style="padding:2rem;text-align:center;color:#6b7280;">{$t('tools.modal.empty')}</div>
    {:else}
      <div class="tools-list">
        {#each toolsList as tool}
          <div class="tool-item" class:expanded={expandedTool?.name === tool.name}>
            <div class="tool-item-header" onclick={() => toggleToolExpand(tool)}>
              <div>
                <div class="tool-name">{tool.name}</div>
                {#if tool.description}
                  <div class="tool-desc">{tool.description}</div>
                {/if}
                {#if tool.annotations}
                  <div class="tool-annotations">
                    {#each formatToolAnnotations(tool.annotations) as anno}
                      <span class="tool-anno-badge {anno.cls}">{anno.label}</span>
                    {/each}
                  </div>
                {/if}
              </div>
              <span class="tool-chevron">{expandedTool?.name === tool.name ? "▲" : "▼"}</span>
            </div>
            {#if expandedTool?.name === tool.name}
              <div class="tool-body">
                {#if tool.inputSchema?.properties}
                  {#each Object.entries(tool.inputSchema.properties) as [paramName, paramSchema]}
                    <div class="tool-arg-group">
                      <label class="tool-arg-label">
                        {paramName}
                        {#if (tool.inputSchema.required || []).includes(paramName)}<span class="tool-required">*</span>{/if}
                        {#if paramSchema.type}
                          <span class="tool-arg-type-hint">({paramSchema.type}{#if paramSchema.enum}, enum{/if})</span>
                        {/if}
                      </label>
                      <!-- svelte-ignore a11y-no-static-element-interactions -->
                      <div onclick={(e) => e.stopPropagation()} oninput={(e) => e.stopPropagation()} onchange={(e) => e.stopPropagation()}>
                        {#if paramSchema.enum && Array.isArray(paramSchema.enum) && paramSchema.enum.length > 0}
                          <select class="tool-arg-select" value={toolArgs[paramName] ?? ""} onchange={(e) => toolArgs[paramName] = e.target.value}>
                            {#each paramSchema.enum as opt}
                              <option value={opt}>{opt}</option>
                            {/each}
                          </select>
                        {:else if paramSchema.type === "boolean"}
                          <label class="tool-arg-checkbox">
                            <input type="checkbox" checked={toolArgs[paramName] ?? false} onchange={(e) => toolArgs[paramName] = e.target.checked} />
                            <span>{paramSchema.description || "Boolean"}</span>
                          </label>
                        {:else if paramSchema.type === "number" || paramSchema.type === "integer"}
                          <input class="tool-arg-number" type="number" step={paramSchema.type === "integer" ? "1" : "any"} placeholder={paramSchema.description || ""} value={toolArgs[paramName] ?? ""} oninput={(e) => toolArgs[paramName] = e.target.value} />
                        {:else if paramSchema.type === "array"}
                          <input class="tool-arg-input" type="text" placeholder={paramSchema.description || `["item1", "item2"]`} value={toolArgs[paramName] ?? ""} oninput={(e) => toolArgs[paramName] = e.target.value} />
                          <div style="font-size:0.62rem;color:#9ca3af;margin-top:2px;">{$t('tool.array_hint')}</div>
                        {:else if paramSchema.type === "object"}
                          <textarea class="tool-arg-input" rows="3" placeholder={paramSchema.description || '{"key": "value"}'} oninput={(e) => toolArgs[paramName] = e.target.value}>{toolArgs[paramName] ?? ""}</textarea>
                        {:else}
                          <input class="tool-arg-input" type="text" placeholder={paramSchema.description || paramSchema.type || ""} value={toolArgs[paramName] ?? ""} oninput={(e) => toolArgs[paramName] = e.target.value} />
                        {/if}
                      </div>
                    </div>
                  {/each}
                {:else}
                  <div style="color:#9ca3af;font-size:0.8rem;padding:0.5rem 0;">{$t('tool.no_args')}</div>
                {/if}
                <button class="btn-confirm tool-run-btn" onclick={() => callTool(tool.name)} disabled={toolCalling}>
                  {toolCalling ? $t('tool.running') : $t('tool.run')}
                </button>
                {#if toolResult !== null || toolResultError}
                  <div class="tool-result" class:tool-result-error={!!toolResultError}>
                    {#if toolResult !== null}
                      <div class="tool-result-header">
                        <span>{$t('tool.result')}</span>
                        <button class="tool-result-toggle" onclick={() => toolShowRaw[tool.name] = !toolShowRaw[tool.name]}>
                          {toolShowRaw[tool.name] ? $t('tool.formatted') : $t('tool.raw')}
                        </button>
                      </div>
                      {#if toolShowRaw[tool.name]}
                        <div class="tool-result-raw">{toolRawData ? JSON.stringify(toolRawData, null, 2) : toolResult}</div>
                      {:else}
                        <div class="tool-result-content">{@html toolResult}</div>
                      {/if}
                    {:else if toolResultError}
                      <div class="tool-result-content tool-result-content-text">{toolResultError}</div>
                    {/if}
                  </div>
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
    <div class="modal-actions">
      <button class="btn-cancel" onclick={() => closeToolsModal()}>{$t('tools.modal.close')}</button>
    </div>
  </div>
</div>

<!-- ── MERGE MODAL ────────────────────────────────────────── -->
<div class="modal-overlay" id="mergeModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3>{$t('modal.merge.title')}</h3>
      <p class="modal-sub" id="mergeSub">{mergeMode === 'local' ? $t('modal.merge.local') : $t('modal.merge.sandbox')}</p>
    </div>
    <div class="merge-tabs">
      <button class="merge-tab active" id="mergeTabLocal" onclick={() => window.setMergeTab('local')}>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="3" y="3" width="10" height="10" rx="2"/><path d="M8 6v4M6 8h4"/></svg>
        {$t('merge.local_title')}
      </button>
      <button class="merge-tab" id="mergeTabSandbox" onclick={() => window.setMergeTab('sandbox')}>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 8h6M8 5v6"/></svg>
        {$t('merge.sandbox_title')}
      </button>
    </div>
    <div class="form-group">
      <label for="mergeName">{$t('merge.merge_label')}</label>
      <input type="text" id="mergeName" placeholder={$t('merge.merge_placeholder')} />
    </div>
    <div id="mergeLocalFields" style="display:block">
      <div class="form-group">
        <label for="mergeTargetSelect">{$t('merge.target_label')}</label>
        <select id="mergeTargetSelect"><option value="">{$t('merge.target_placeholder')}</option></select>
        <p class="form-hint">{$t('merge.target_hint')}</p>
      </div>
    </div>
    <div id="mergeSandboxFields" style="display:none">
      <div class="store-divider"><span>ou</span></div>
      <button class="btn-store" onclick={() => window.openStoreModal()}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.2"/><path d="M10.2 10.2 14 14"/></svg>
        {$t('store.install_btn')}
      </button>
      <div class="form-group">
        <label for="mergeStdioJson">{$t('merge.config_label')}</label>
        <textarea id="mergeStdioJson" rows="5" class="code-textarea"></textarea>
        <p class="form-hint">{$t('merge.config_hint')}</p>
      </div>
      <div id="mergeEnvFields" style="display:none"></div>
      <div id="mergePackageWarning" class="store-warning" style="display:none"></div>
    </div>
    <div class="modal-error" id="mergeError"></div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick={() => window.closeMergeModal()}>{$t('common.cancel')}</button>
      <button class="btn-confirm" id="btnMergeConfirm" onclick={() => window.confirmMerge()}>{$t('modal.merge.btn')}</button>
    </div>
  </div>
</div>

<!-- ── STORE MODAL ─────────────────────────────────────────── -->
<div class="modal-overlay" id="storeModal">
  <div class="modal-box store-box">
    <div class="modal-header">
      <h3>{$t('store.modal.title')}</h3>
      <p class="modal-sub">{$t('store.modal_sub')}</p>
    </div>
    <div class="store-layout">
      <div class="store-sidebar">
        <div class="store-sidebar-section">
          <div class="store-sidebar-title">{$t('store.hosting')}</div>
          <div class="store-filter-bar" id="storeFilterBar"></div>
        </div>
        <div class="store-sidebar-section">
          <div class="store-sidebar-title">{$t('store.categories')}</div>
          <div class="store-cat-list" id="storeCategoryBar"></div>
        </div>
      </div>
      <div class="store-main">
        <div class="store-toolbar">
          <div class="store-search">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.2"/><path d="M10.2 10.2 14 14"/></svg>
            <input type="text" id="storeSearch" placeholder={$t('store.search_placeholder')} oninput={() => window.searchStore()} />
          </div>
          <select class="store-sort" id="storeSort" onchange={() => window.setStoreSort(this.value)}>
            <option value="relevance">{$t('store.sort_relevance')}</option>
            <option value="stars">{$t('store.sort_stars')}</option>
            <option value="tools">{$t('store.sort_tools')}</option>
            <option value="name">{$t('store.sort_name_asc')}</option>
            <option value="name_desc">{$t('store.sort_name_desc')}</option>
          </select>
        </div>
        <div class="store-grid" id="storeGrid">
          <div class="store-loading">{$t('store.loading')}</div>
        </div>
        <div class="store-pagination" id="storePagination" style="display:none"></div>
        <button class="store-load-more" id="storeLoadMore" onclick={() => window.loadMoreStore()} style="display:none">{$t('store.load_more')}</button>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick={() => window.closeStoreModal()}>{$t('common.close')}</button>
    </div>
  </div>
</div>

<!-- ── EDIT MODAL ────────────────────────────────────────── -->
<div class="modal-overlay" id="editModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3>{$t('modal.edit.title')}</h3>
      <p class="modal-sub">{$t('modal.edit.sub')}</p>
    </div>
    <div class="form-group">
      <label for="editName">{$t('modal.edit.name_label')}</label>
      <input type="text" id="editName" placeholder={$t('modal.edit.name_placeholder')} />
    </div>
    <div class="form-group">
      <label for="editTransport">{$t('modal.edit.transport_label')}</label>
      <select id="editTransport">
        <option value="http">{$t('modal.create.transport_http')}</option>
        <option value="sse">{$t('modal.create.transport_sse')}</option>
      </select>
    </div>
    <div class="form-group">
      <label for="editStatus">{$t('modal.edit.status_label')}</label>
      <select id="editStatus">
        <option value="active">{$t('modal.edit.status_online')}</option>
        <option value="inactive">{$t('modal.edit.status_offline')}</option>
      </select>
    </div>
    <div class="modal-error" id="editError"></div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick={() => window.closeEditModal()}>{$t('common.cancel')}</button>
      <button class="btn-confirm" id="btnEditConfirm" onclick={() => window.saveEdit()}>{$t('common.save')}</button>
    </div>
  </div>
</div>

<!-- ── CREATE MODAL ──────────────────────────────────────── -->
<div class="modal-overlay" id="createModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3>{$t('dashboard.new_server')}</h3>
      <p class="modal-sub">{$t('modal.create.sub')}</p>
    </div>
    <div class="form-group">
      <label for="inputName">{$t('modal.create.name')}</label>
      <input type="text" id="inputName" placeholder={$t('modal.create.name_placeholder')} />
    </div>
    <div class="form-group">
      <label for="inputSpecUrl">{$t('modal.create.spec_url')}</label>
      <input type="url" id="inputSpecUrl" placeholder={$t('modal.create.url_placeholder')} />
    </div>
    <div class="form-group">
      <label for="inputTransport">{$t('modal.create.transport')}</label>
      <select id="inputTransport">
        <option value="http">{$t('modal.create.transport_http')}</option>
        <option value="sse">{$t('modal.create.transport_sse')}</option>
      </select>
    </div>
    <div class="modal-error" id="modalError"></div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick={() => window.closeCreateModal()}>{$t('common.cancel')}</button>
      <button class="btn-confirm" id="btnCreateConfirm" onclick={() => window.createServer()}>{$t('modal.create.btn')}</button>
    </div>
  </div>
</div>

<!-- ── LOG DETAIL MODAL ──────────────────────────────────── -->
<div class="modal-overlay" id="logDetailModal">
  <div class="modal-box log-detail-box">
    <div class="modal-header">
      <h3>{$t('dashboard.log_detail_title')}</h3>
      <p class="modal-sub">{$t('dashboard.log_detail_sub')}</p>
    </div>
    <div class="log-detail-meta">
      <span class="log-detail-meta-item"><span class="label">{$t('dashboard.log_meta_tool')}</span> <span id="detailTool">—</span></span>
      <span class="log-detail-meta-item"><span class="label">{$t('dashboard.log_meta_method')}</span> <span id="detailMethod">—</span></span>
      <span class="log-detail-meta-item"><span class="label">{$t('dashboard.log_meta_status')}</span> <span id="detailStatus" class="status-badge">—</span></span>
      <span class="log-detail-meta-item"><span class="label">{$t('dashboard.log_meta_duration')}</span> <span id="detailDuration">—</span></span>
      <span class="log-detail-meta-item"><span class="label">{$t('dashboard.log_meta_date')}</span> <span id="detailTime">—</span></span>
    </div>
    <div class="log-detail-scroll">
      <div class="log-detail-section">
        <h4>{$t('dashboard.request_body_label')}</h4>
        <div class="log-detail-body" id="detailReqBody">{$t('dashboard.empty_body')}</div>
      </div>
      <div class="log-detail-section">
        <h4>{$t('dashboard.response_body_label')}</h4>
        <div class="log-detail-body" id="detailResBody">{$t('dashboard.empty_body')}</div>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick={() => window.closeLogDetail()}>{$t('common.close')}</button>
    </div>
  </div>
</div>

<!-- ── PROFILE MODAL ────────────────────────────────────────── -->
<div class="modal-overlay" id="profileModal">
  <div class="modal-box profile-modal-box">
    <div class="profile-modal-header">
      <div class="profile-avatar-section">
        <div class="profile-modal-avatar" id="profileAvatarWrap">
          <span class="profile-modal-avatar-initials">U</span>
        </div>
        <div class="profile-header-info">
          <h3 id="profileName">—</h3>
          <span id="profileEmail" class="profile-email">—</span>
          <div class="profile-badges">
            <span id="profilePlan" class="profile-plan-badge free">free</span>
            <span class="profile-provider-badge" id="profileProvider">EMAIL</span>
          </div>
        </div>
      </div>
      <button class="profile-close-btn" onclick={() => window.closeProfileModal()} title={$t('common.close')}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>

    <div class="profile-stats-row">
      <div class="profile-stat">
        <span class="profile-stat-label">{$t('profile.servers_label')}</span>
        <span class="profile-stat-value" id="profileServersCount">—</span>
      </div>
      <div class="profile-stat-divider"></div>
      <div class="profile-stat">
        <span class="profile-stat-label">{$t('profile.rpm_label')}</span>
        <span class="profile-stat-value" id="profileRpm">—</span>
      </div>
      <div class="profile-stat-divider"></div>
      <div class="profile-stat">
        <span class="profile-stat-label">{$t('profile.member_since')}</span>
        <span class="profile-stat-value profile-stat-date" id="profileCreatedAt">—</span>
      </div>
    </div>

    <div class="profile-section">
      <div class="profile-section-title">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
        {$t('profile.token')}
      </div>
      <div class="profile-token-field">
        <input type="password" id="profileToken" class="profile-token-input" readonly />
        <button class="profile-token-btn" id="toggleTokenBtn" onclick={() => window.toggleTokenVisibility()} title="Mostrar/ocultar token">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
        <button class="profile-token-btn profile-copy-btn" id="copyTokenBtn" onclick={() => window.copyToken()} title={$t('profile.copy')}>{$t('profile.copy')}</button>
      </div>
      <p class="profile-token-hint">{$t('profile.token_hint')}</p>
    </div>

    <div class="profile-section">
      <div class="profile-section-title">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93l-1.41 1.41M12 2v2M4.93 4.93l1.41 1.41M2 12h2M4.93 19.07l1.41-1.41M12 20v2M19.07 19.07l-1.41-1.41M20 12h2"/></svg>
        {$t('profile.account_details')}
      </div>
      <div class="profile-details-grid">
        <div class="profile-detail-row">
          <span class="profile-detail-label">{$t('profile.user_id')}</span>
          <span class="profile-detail-value profile-detail-mono" id="profileUserId">—</span>
        </div>
        <div class="profile-detail-row">
          <span class="profile-detail-label">Email</span>
          <span class="profile-detail-value" id="profileEmailDetail">—</span>
        </div>
        <div class="profile-detail-row">
          <span class="profile-detail-label">Fornecedor</span>
          <span class="profile-detail-value" id="profileProviderDetail">—</span>
        </div>
      </div>
    </div>

    <div class="profile-section">
      <div class="profile-section-title" style="cursor:pointer;" onclick={() => window.toggleChangePassword()}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        Palavra-passe
        <button class="profile-token-btn" id="toggleChangePasswordBtn" style="margin-left:auto;font-size:0.72rem;padding:4px 10px;">{$t('profile.change_password')}</button>
      </div>
      <div id="changePasswordSection" style="display:none;margin-top:10px;">
        <div class="profile-token-field" style="margin-bottom:8px;">
          <input type="password" id="newPasswordInput" class="profile-token-input" placeholder={$t('profile.new_password')} style="width:100%;" />
        </div>
        <div class="modal-error" id="changePasswordError" style="margin-bottom:8px;"></div>
        <div style="display:flex;gap:8px;">
          <button class="btn-confirm" id="btnSavePassword" onclick={() => window.saveNewPassword()} style="flex:1;">{$t('common.save')}</button>
          <button class="btn-cancel" onclick={() => window.toggleChangePassword()}>{$t('common.cancel')}</button>
        </div>
      </div>
    </div>

    <div class="profile-modal-actions">
      <button class="btn-cancel" onclick={() => window.closeProfileModal()}>{$t('profile.close_btn')}</button>
      <button class="profile-logout-btn" onclick={() => window.logoutFromProfile()}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        {$t('profile.logout')}
      </button>
    </div>
  </div>
</div>

<!-- ── RESET PASSWORD MODAL (recovery flow) ────────────────── -->
<div class="modal-overlay" id="resetPasswordModal">
  <div class="modal-box" style="max-width:380px;">
    <div class="modal-header">
      <h3>{$t('profile.reset_password_title')}</h3>
      <p class="modal-sub">{$t('profile.reset_password_sub')}</p>
    </div>
    <div class="form-group">
      <label for="resetPasswordInput">{$t('profile.new_password_field')}</label>
      <input type="password" id="resetPasswordInput" placeholder={$t('profile.password_min_chars')} />
    </div>
    <div class="modal-error" id="resetPasswordError"></div>
    <div class="modal-actions">
      <button class="btn-confirm" id="btnResetPassword" onclick={() => window.confirmResetPassword()}>Redefinir Palavra-passe</button>
    </div>
  </div>
</div>

<!-- Loading Overlay -->
<div class="loading-overlay" id="loadingOverlay">
  <div class="loading-spinner"></div>
  <div class="loading-text" id="loadingText">Aguarde...</div>
</div>