<script>
  // @ts-nocheck
  import { onMount } from 'svelte';
  import './Dashboard.css';
  import { installAppAlert, notifyAppAlert } from './app-alert.js';

  onMount(() => {
      const debug = (...args) => console.log("[dashboard-debug]", ...args);

      installAppAlert();
      debug("onMount:init");
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

      const API_BASE = (
        localStorage.getItem("api_base") || "http://localhost:8080"
      ).replace(/\/+$/, "");
      const POLL_LOGS_INTERVAL = 5000;
      let activeServerId = null;

      // ─── Supabase Auth ───────────────────────────────────────
      const SUPABASE_URL = localStorage.getItem("supabase_url") || "https://zcfrbhrqvneomseqmqam.supabase.co";
      const SUPABASE_ANON_KEY = localStorage.getItem("supabase_anon_key") || "sb_publishable_mF0UgfLvgZN5OupdpsSa0A_ibOcfzq4";
      let supabaseClient = null;
      let currentUser = null;
      let currentProfile = null;

      if (SUPABASE_URL && SUPABASE_ANON_KEY) {
        supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
      }

      function getAuthToken() {
        return localStorage.getItem("supabase_token") || "";
      }

      // ─── Loading Overlay ─────────────────────────────────
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
        if (!supabaseClient) return window.showAppAlert("Supabase não configurado.");
        showLoading("Redirecionando para " + provider + "...");
        const { error } = await supabaseClient.auth.signInWithOAuth({ provider });
        if (error) {
          hideLoading();
          console.error("Login error:", error);
        }
      }

      async function logout() {
        showLoading("Terminando sessão...");
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
        } catch {
          logout();
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

      let paypalRendered = false;
      function showPayPal() {
        const ppc = document.getElementById("paypal-button-container");
        if (!ppc) return;
        ppc.style.display = "block";
        if (typeof paypal !== "undefined" && currentUser && !paypalRendered) {
          paypalRendered = true;
          paypal.Buttons({
            createSubscription: function(data, actions) {
              return actions.subscription.create({
                plan_id: "P-26B313696D799031LNIFNUDQ",
                custom_id: currentUser.id,
              });
            },
            onApprove: function(data) {
              window.showAppAlert("Subscrição ativada!");
              document.getElementById("paypalModal").classList.remove("open");
            },
            onError: function(err) {
              console.error("PayPal error:", err);
              window.showAppAlert("Erro ao processar pagamento.");
            },
          }).render("#paypal-button-container");
        }
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

      // ─── Render Card ───────────────────────────────────────
      function renderServerCard(s) {
        const isActive = s.status === "active";
        const isMerged = s.is_merged === true;
        const card = document.createElement("div");
        let cls = `server-card${isActive ? " active-status" : ""}`;
        if (isMerged) cls += " server-card-merged";
        card.className = cls;
        card.dataset.serverId = s.server_id;
        card.dataset.serverName = s.name;
        card.dataset.apikey = s.apikey || "";
        card.dataset.transport = s.transport || "http";
        card.draggable = !isMerged;

        card.addEventListener("dragstart", (e) => {
          e.dataTransfer.setData("text/plain", s.server_id);
          card.classList.add("dragging");
        });
        card.addEventListener("dragend", () => {
          card.classList.remove("dragging");
          document.querySelectorAll(".server-card").forEach((c) => c.classList.remove("drag-over"));
        });
        card.addEventListener("dragover", (e) => {
          e.preventDefault();
          card.classList.add("drag-over");
        });
        card.addEventListener("dragleave", () => {
          card.classList.remove("drag-over");
        });
        card.addEventListener("drop", (e) => {
          e.preventDefault();
          card.classList.remove("drag-over");
          document.querySelectorAll(".server-card").forEach((c) => c.classList.remove("drag-over"));
        });

        const emoji = isActive
          ? `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="4" fill="#00d4aa"/><circle cx="8" cy="8" r="7" stroke="#00d4aa" stroke-width="1.5" stroke-opacity="0.3"/></svg>`
          : `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="4" fill="#ff5c35"/><circle cx="8" cy="8" r="7" stroke="#ff5c35" stroke-width="1.5" stroke-opacity="0.3"/></svg>`;

        card.addEventListener("click", () => selectServer(s.server_id));

        const mergeLabel = isMerged ? `<span class="merge-badge"><svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0l1.2 4.8L14 6l-4.8 1.2L8 12 6.8 7.2 2 6l4.8-1.2z"/></svg> Merged</span>` : "";

        card.innerHTML = `
          <div class="server-info">
            <div class="status-icon ${isActive ? "active" : "inactive"}">${emoji}</div>
            <div class="server-meta">
              <div class="server-name">${escapeHtml(s.name)} ${mergeLabel}</div>
              <div class="server-url">${escapeHtml(s.url_sse || s.server_id)}${s.merge_info ? ' · ' + escapeHtml(s.merge_info) : ''}</div>
            </div>
          </div>
          <div class="server-actions">
            <span class="status-chip ${isActive ? "active" : "inactive"}">
              <span class="status-chip-dot"></span>
              ${isActive ? "Online" : "Offline"}
            </span>
            <button class="btn-copy" ${isActive ? "" : "disabled"} onclick="copyUrl(this, '${escapeHtml(s.url_sse || "")}')">
              Copy URL
            </button>
            <div class="menu-wrapper">
              <button class="menu-btn" onclick="toggleMenu(this)" title="Mais opções">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                  <circle cx="7" cy="2" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="7" cy="12" r="1.3"/>
                </svg>
              </button>
              <div class="menu-dropdown">
                <button onclick="openInspector('${escapeHtml(s.url_sse || "")}', '${s.transport || "http"}'); closeMenu();">
                  <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.2"/><path d="M10.2 10.2L14 14"/></svg></span> Inspecionar
                </button>

                <button onclick="editServer('${s.server_id}', '${escapeHtml(s.name || "")}', '${s.transport || "http"}'); closeMenu();">
                  <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3l8-8z"/></svg></span> Editar
                </button>
                <button onclick="openMergeModalFromMenu('${s.server_id}', '${escapeHtml(s.name || "")}'); closeMenu();">
                  <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="8" cy="3" r="1.5"/><path d="M8 7v6M5 10h6"/></svg></span> Merge
                </button>
                <div class="menu-divider"></div>
                <button onclick="toggleServerStatus('${s.server_id}'); closeMenu();">
                  <span class="menu-icon">${isActive ? `<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><rect x="3" y="2" width="4" height="12" rx="1"/><rect x="9" y="2" width="4" height="12" rx="1"/></svg>` : `<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M4 2l10 6-10 6V2z"/></svg>`}</span>
                  ${isActive ? "Desativar" : "Ativar"}
                </button>
                ${isMerged ? `<div class="menu-divider"></div>
                <button data-action="unmerge" data-server-id="${s.server_id}">
                  <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M3 3l10 10M13 3l-10 10"/></svg></span> Desfazer Merge
                </button>` : ""}
                <div class="menu-divider"></div>
                <button class="menu-danger" data-action="delete" data-server-id="${s.server_id}">
                  <span class="menu-icon"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M2 4h12"/><path d="M5 4V2h6v2"/><path d="M6 7v5M10 7v5"/><path d="M3 4l1 10h8l1-10"/></svg></span> Remover
                </button>
              </div>
            </div>
          </div>
        `;
        return card;
      }

      // ─── Load Servers ──────────────────────────────────────
      async function loadServers() {
        const list = document.getElementById("serverList");
        if (!list) return;
        try {
          const servers = await apiFetch("/v1/servers");
          list.innerHTML = "";

          if (!servers || servers.length === 0) {
            list.innerHTML = `
              <div class="empty-state">
                <div class="empty-icon"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="14" rx="2"/><path d="M9 16v4M15 16v4M9 20h6"/><path d="M9 6h6M9 10h6"/></svg></div>
                <div>Nenhum servidor ainda.<br/>Clique em <strong>+ Novo Servidor</strong> para começar.</div>
              </div>
            `;
          } else {
            servers.forEach((s) => list.appendChild(renderServerCard(s)));
            _populateLogServerSelect(servers);
            selectServer(servers[0].server_id);
            _checkAllServerHealth(servers);
          }

          const sc = document.getElementById("serverCount");
          if (sc) sc.textContent = servers ? servers.length : 0;

        } catch (err) {
          list.innerHTML = `
            <div class="empty-state">
              <div class="empty-icon"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ff5c35" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div>
              <div style="color:var(--warn)">Erro ao carregar servidores:<br/>${escapeHtml(err.message)}</div>
              <button onclick="loadServers()" style="margin-top:1.2rem;padding:8px 18px;border:1px solid var(--border);border-radius:8px;background:white;cursor:pointer;font-family:var(--mono);font-size:0.78rem;transition:all 0.2s;">
                Tentar novamente
              </button>
            </div>
          `;
          const sc = document.getElementById("serverCount");
          if (sc) sc.textContent = "—";
        }
      }

      let _serverHealth = new Map();

      async function _checkAllServerHealth(servers) {
        _serverHealth = new Map();
        const active = servers.filter(s => s.status === "active");
        const results = await Promise.allSettled(
          active.map(s =>
            fetch(`${API_BASE}/v1/servers/${s.server_id}/health`).then(r => r.json())
          )
        );
        results.forEach((res, i) => {
          const srv = active[i];
          if (res.status === "fulfilled" && res.value.status === "ok") {
            _serverHealth.set(srv.server_id, "ok");
          } else {
            _serverHealth.set(srv.server_id, "error");
            const card = document.querySelector(`.server-card[data-server-id="${srv.server_id}"]`);
            if (card) {
              card.classList.add("health-error");
              const urlEl = card.querySelector(".server-url");
              if (urlEl) urlEl.innerHTML = '<span style="color:var(--danger)">API indisponível</span>';
              const statusIcon = card.querySelector(".status-icon");
              if (statusIcon) statusIcon.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="4" fill="#ff5c35"/><circle cx="8" cy="8" r="7" stroke="#ff5c35" stroke-width="1.5" stroke-opacity="0.3"/></svg>';
              const statusChip = card.querySelector(".status-chip");
              if (statusChip) {
                statusChip.className = "status-chip inactive";
                statusChip.innerHTML = '<span class="status-chip-dot"></span>API indisponível';
              }
            }
          }
        });
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
          await loadServers();
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
        showConfirmDialog("Remover este servidor permanentemente?", () => {
          debug("deleteServer:onConfirm", { serverId });
          const card = document.querySelector(
            `.server-card[data-server-id="${serverId}"]`,
          );
          debug("deleteServer:cardLookup", { serverId, found: !!card });
          if (!card) return;
          card.style.opacity = "0";
          card.style.transform = "translateX(20px)";
          card.style.transition = "all 0.3s";
          (async () => {
            try {
              debug("deleteServer:apiFetch", { serverId });
              await apiFetch(`/v1/servers/${serverId}`, { method: "DELETE" });
              debug("deleteServer:apiSuccess", { serverId });
              setTimeout(() => {
                debug("deleteServer:timeout-fired", { serverId });
                card.remove();
                const sc = document.getElementById("serverCount");
                if (sc) sc.textContent = document.querySelectorAll(".server-card").length;
                if (activeServerId === serverId) activeServerId = null;
                notifyAppAlert("Servidor removido com sucesso.");
              }, 300);
            } catch (err) {
              console.error("[dashboard-debug] deleteServer:apiError", err);
              card.style.opacity = "1";
              card.style.transform = "";
              notifyAppAlert("Erro ao remover: " + err.message);
            }
          })();
        });
      }

      // ─── Toggle Status ──────────────────────────────────────
      async function toggleServerStatus(serverId) {
        const card = document.querySelector(`.server-card[data-server-id="${serverId}"]`);
        if (!card) return;
        const isActive = card.classList.contains("active-status");
        try {
          await apiFetch(`/v1/servers/${serverId}`, {
            method: "PATCH",
            body: JSON.stringify({ status: isActive ? "inactive" : "active" }),
          });
          await loadServers();
          window.showAppAlert(`Servidor ${isActive ? "desativado" : "ativado"} com sucesso.`);
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
            await loadServers();
            debug("unmergeServer:loadServers:done", { serverId });
            notifyAppAlert("Merge desfeito com sucesso.");
          } catch (err) {
            console.error("[dashboard-debug] unmergeServer:apiError", err);
            notifyAppAlert("Erro ao desfazer merge: " + err.message);
          }
        });
      }

      // ─── Menu Portal ───────────────────────────────────────
      // ─── Menu Portal ───────────────────────────────────────
      const portal = document.getElementById("menuPortal");
      let activeMenu = null;
      let activeMenuOriginWrapper = null;

      function toggleMenu(btn) {
        debug("toggleMenu:click", {
          hasPortal: !!portal,
          hasButton: !!btn,
        });
        if (!portal) return;
        const wrapper = btn.closest(".menu-wrapper");
        if (!wrapper) return;
        const menu = wrapper.querySelector(".menu-dropdown");
        if (!menu) return;

        if (activeMenu === menu && portal.classList.contains("open")) {
          closeAllMenus();
          return;
        }
        closeAllMenus();

        portal.appendChild(menu);
        portal.classList.add("open");
        menu.classList.add("open");
        activeMenu = menu;
        activeMenuOriginWrapper = wrapper;
        debug("toggleMenu:opened", {
          serverId: wrapper.closest(".server-card")?.dataset?.serverId || null,
        });

        const rect = btn.getBoundingClientRect();
        const menuW = 200;
        let left = rect.right - menuW;
        let top = rect.bottom + 6;
        if (left < 8) left = 8;
        if (top + 240 > window.innerHeight) top = rect.top - 240;
        menu.style.position = "fixed";
        menu.style.left = left + "px";
        menu.style.top = top + "px";
        menu.style.minWidth = menuW + "px";
      }
      window.toggleMenu = toggleMenu;

      function closeMenu() {
        closeAllMenus();
      }
      window.closeMenu = closeMenu;

      function closeAllMenus() {
        if (!portal) return;
        if (activeMenu) {
          activeMenu.classList.remove("open");
          if (activeMenuOriginWrapper)
            activeMenuOriginWrapper.appendChild(activeMenu);
          activeMenu = null;
          activeMenuOriginWrapper = null;
        }
        portal.classList.remove("open");
      }
      window.closeAllMenus = closeAllMenus;

      document.addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-action]");
        if (!btn) return;
        const action = btn.dataset.action;
        const serverId = btn.dataset.serverId;
        debug("menu-action:captured", { action, serverId });
        if (!action || !serverId) return;
        if (action === "delete") {
          closeAllMenus();
          deleteServer(serverId);
          return;
        }
        if (action === "unmerge") {
          closeAllMenus();
          unmergeServer(serverId);
        }
      }, true);

      document.addEventListener("click", (e) => {
        if (
          !e.target.closest(".menu-wrapper") &&
          !e.target.closest("#menuPortal")
        )
          closeAllMenus();
      });
      window.addEventListener("scroll", closeAllMenus, true);
      window.addEventListener("resize", closeAllMenus);

      // ─── Merge ─────────────────────────────────────────────
      let mergeSourceId = null;
      let mergeTargetId = null;
      let mergeMode = "local";

      function populateMergeTargets(excludeId) {
        const sel = document.getElementById("mergeTargetSelect");
        if (!sel) return;
        sel.innerHTML = '<option value="">Selecione um servidor...</option>';
        document.querySelectorAll(".server-card").forEach((card) => {
          const sid = card.dataset.serverId;
          const sname = card.dataset.serverName || sid;
          if (sid && sid !== excludeId) {
            const opt = document.createElement("option");
            opt.value = sid;
            opt.textContent = sname;
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
          const labels = { local: "Fusão de servidores no rest2mcp com namespace automático", sandbox: "Instalação temporária de um servidor MCP via npx, pipx ou uv (ou JSON personalizado)" };
          mergeSub.textContent = labels[mode] || "";
        }
      }
      window.setMergeTab = setMergeTab;

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
      window.openMergeModalFromMenu = openMergeModalFromMenu;

      // Quick-select: preenche Config JSON com servidores pré-definidos
      //   uvx mcp-excel-server                                 → Excel
      //   npx @modelcontextprotocol/server-filesystem .        → File System
      //   pipx mcp-server-sqlite                               → SQLite
      //   uvx mcp-server-pdf                                   → PDF
      function fillSandbox(command, args, extra) {
        const cfg = { command, args: args.split(" ").filter(Boolean) };
        if (extra) cfg.args.push(extra);
        const ta = document.getElementById("mergeStdioJson");
        if (ta) ta.value = JSON.stringify(cfg, null, 2);
        closeStoreModal();
      }
      window.fillSandbox = fillSandbox;

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
      window.closeMergeModal = closeMergeModal;

      // ─── Store ─────────────────────────────────────────────
      let _storeAllServers = [];
      let _storeFacets = { hostingTypes: [], categories: [] };
      let _storeFilterHosting = "";
      let _storeFilterCategory = "";
      let _storePageInfo = { hasNextPage: false, endCursor: "" };
      let _storeLoading = false;
      let _storeEnvSchemas = {};

      function closeStoreModal() {
        document.getElementById("storeModal")?.classList.remove("open");
        const ss = document.getElementById("storeSearch");
        if (ss) ss.value = "";
      }
      window.closeStoreModal = closeStoreModal;

      async function openStoreModal() {
        const modal = document.getElementById("storeModal");
        const grid = document.getElementById("storeGrid");
        if (!modal || !grid) return;
        modal.classList.add("open");
        grid.innerHTML = "<div class='store-loading'>A carregar loja...</div>";
        _storeFilterHosting = "";
        _storeFilterCategory = "";
        _storeAllServers = [];
        _storePageInfo = { hasNextPage: false, endCursor: "" };
        _storeEnvSchemas = {};
        try {
          const res = await fetch("/v1/store/servers");
          if (!res.ok) throw new Error("Erro ao carregar loja");
          const data = await res.json();
          const servers = data.servers || [];
          _storeAllServers = servers;
          _storeFacets = data.facets || { hostingTypes: [], categories: [] };
          _storePageInfo = data.pageInfo || { hasNextPage: false, endCursor: "" };
          servers.forEach(s => {
            if (s.id && s.environmentVariablesJsonSchema) {
              _storeEnvSchemas[s.id] = s.environmentVariablesJsonSchema;
            }
          });
          _renderStoreFilters();
          searchStore();
        } catch (err) {
          grid.innerHTML = "<div class='store-loading store-error'>Erro ao carregar servidores. Tente novamente.</div>";
        }
      }
      window.openStoreModal = openStoreModal;

      async function loadMoreStore() {
        if (_storeLoading || !_storePageInfo.hasNextPage) return;
        _storeLoading = true;
        const btn = document.getElementById("storeLoadMore");
        if (btn) btn.textContent = "A carregar...";
        try {
          const res = await fetch("/v1/store/servers?cursor=" + encodeURIComponent(_storePageInfo.endCursor));
          if (!res.ok) throw new Error("Erro");
          const data = await res.json();
          const newServers = data.servers || [];
          _storeAllServers = _storeAllServers.concat(newServers);
          _storePageInfo = data.pageInfo || { hasNextPage: false, endCursor: "" };
          _renderStoreFilters();
          searchStore();
        } catch (err) {
          if (btn) btn.textContent = "Erro ao carregar. Tentar novamente";
        } finally {
          _storeLoading = false;
        }
      }
      window.loadMoreStore = loadMoreStore;

      function setStoreFilterHosting(type) {
        _storeFilterHosting = _storeFilterHosting === type ? "" : type;
        _renderStoreFilters();
        searchStore();
      }
      window.setStoreFilterHosting = setStoreFilterHosting;

      function setStoreFilterCategory(cat) {
        _storeFilterCategory = _storeFilterCategory === cat ? "" : cat;
        _renderStoreFilters();
        searchStore();
      }
      window.setStoreFilterCategory = setStoreFilterCategory;

      function _renderStoreFilters() {
        const bar = document.getElementById("storeFilterBar");
        const catBar = document.getElementById("storeCategoryBar");
        if (!bar) return;

        const hostIcons = {
          "remote-capable": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M11 2h2a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h2"/><path d="M8 11v1"/><path d="M5 5.5 8 2l3 3.5"/></svg>',
          "hybrid": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M13 8A5 5 0 1 1 8 3"/><path d="M13 3v3h-3"/><path d="M3 8A5 5 0 1 0 8 3"/></svg>',
          "local-only": '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="3" width="12" height="9" rx="1.5"/><path d="M6 14h4"/><path d="M8 12v2"/></svg>',
        };
        const hostLabels = { "remote-capable": "Remoto", "hybrid": "Híbrido", "local-only": "Local" };
        bar.innerHTML = _storeFacets.hostingTypes.map(t =>
          `<button class="store-filter-btn${_storeFilterHosting === t ? " active" : ""}" onclick="setStoreFilterHosting('${_escHtml(t)}')">${hostIcons[t] || ""}<span>${hostLabels[t] || t}</span></button>`
        ).join("");

        if (catBar) {
          catBar.innerHTML = _storeFacets.categories.map(c =>
            `<button class="store-cat-item${_storeFilterCategory === c.id ? " active" : ""}" onclick="setStoreFilterCategory('${_escHtml(c.id)}')"><span class="store-cat-name">${_escHtml(c.name)}</span><span class="store-cat-count">${c.count}</span></button>`
          ).join("");
        }
      }

      let _storeSort = "relevance";

      function setStoreSort(sort) {
        _storeSort = sort;
        const sel = document.getElementById("storeSort");
        if (sel) sel.value = sort;
        searchStore();
      }
      window.setStoreSort = setStoreSort;

      function searchStore() {
        const q = (document.getElementById("storeSearch")?.value || "").toLowerCase();
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
      window.searchStore = searchStore;

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
          grid.innerHTML = "<div class='store-loading'>Nenhum servidor encontrado.</div>";
          const loadMore = document.getElementById("storeLoadMore");
          if (loadMore) loadMore.style.display = "none";
          return;
        }
        const hostBadges = {
          "remote-capable": '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M11 2h2a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h2"/><path d="M8 11v1"/><path d="M5 5.5 8 2l3 3.5"/></svg> Remoto',
          "hybrid": '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M13 8A5 5 0 1 1 8 3"/><path d="M13 3v3h-3"/><path d="M3 8A5 5 0 1 0 8 3"/></svg> Híbrido',
          "local-only": '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="3" width="12" height="9" rx="1.5"/><path d="M6 14h4"/><path d="M8 12v2"/></svg> Local',
        };
        grid.innerHTML = servers.map(s => {
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
                ${stars > 0 ? `<span class="store-card-star"><svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1l2 4.5 4.9.5-3.7 3.2L12.5 14 8 11.5 3.5 14l1.3-4.8L1 6l4.9-.5z"/></svg> ${stars}</span>` : ""}
              </div>
            </div>
          </div>`;
        }).join("");;
        const loadMore = document.getElementById("storeLoadMore");
        if (loadMore) {
          const showMore = _storePageInfo.hasNextPage && !_storeFilterHosting && !_storeFilterCategory && !(document.getElementById("storeSearch")?.value || "");
          loadMore.style.display = showMore ? "" : "none";
          if (!_storeLoading) loadMore.textContent = "Carregar mais servidores (" + _storeAllServers.length + "+)";
        }
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
            let msg = "Pacote '" + pkg + "' não encontrado no npm. Fallback ativado.";
            if (data.alternatives && data.alternatives.length) {
              const alt = data.alternatives[0];
              msg += " A usar: " + alt.command + " " + (alt.args || []).join(" ");
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
        let html = '<div class="env-title">Variáveis de Ambiente / Headers</div>';
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
          html += '<p class="form-hint">Token de autenticação para servidores remotos</p>';
          html += '</div>';
        }
        envContainer.innerHTML = html;
      }
      window.installFromStore = installFromStore;

      async function confirmMerge() {
        const name = document.getElementById("mergeName")?.value?.trim();
        const errorEl = document.getElementById("mergeError");
        const btn = document.getElementById("btnMergeConfirm");
        if (errorEl) showModalError(errorEl, "");
        if (!name) { if (errorEl) showModalError(errorEl, "Informe o nome do servidor merged."); return; }

        if (mergeMode === "sandbox") {
          const jsonText = document.getElementById("mergeStdioJson")?.value?.trim();
          if (!jsonText) { if (errorEl) showModalError(errorEl, "Informe a configuração JSON do servidor."); return; }
          let cfg;
          try { cfg = JSON.parse(jsonText); } catch {
            if (errorEl) showModalError(errorEl, "JSON inválido. Verifique a sintaxe.");
            return;
          }
          const namespace = (cfg.name || "").toLowerCase().replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") ||
            (cfg.command || "").replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "sandbox";
          if (cfg.url) {
            const envContainer = document.getElementById("mergeEnvFields");
            const envInputs = envContainer ? envContainer.querySelectorAll(".env-input") : [];
            let missingReq = false;
            const headersVars = {};
            envInputs.forEach(inp => {
              const val = inp.value.trim();
              if (inp.hasAttribute("required") && !val) { missingReq = true; return; }
              if (val) headersVars[inp.id.replace("env_", "")] = val;
            });
            if (missingReq) {
              if (errorEl) showModalError(errorEl, "Preencha todos os campos obrigatórios de ambiente.");
              return;
            }
            if (btn) { btn.disabled = true; btn.innerHTML = '<span class="btn-spinner"></span> A criar...'; }
            try {
              await apiFetch("/v1/servers/merge", {
                method: "POST",
                body: JSON.stringify({ source_server_id: mergeSourceId, remote_url: cfg.url, remote_transport: cfg.type || "streamable-http", remote_headers: Object.keys(headersVars).length ? headersVars : undefined, namespace, merged_name: name }),
              });
              closeMergeModal();
              showLoading("Servidor merged criado! Carregando...", false);
              await loadServers();
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
          if (!cfg.command) { if (errorEl) showModalError(errorEl, "JSON precisa do campo 'command'."); return; }
          const envContainer = document.getElementById("mergeEnvFields");
          const envInputs = envContainer ? envContainer.querySelectorAll(".env-input") : [];
          let missingReq = false;
          const envVars = {};
          envInputs.forEach(inp => {
            const val = inp.value.trim();
            if (inp.hasAttribute("required") && !val) { missingReq = true; return; }
            if (val) envVars[inp.id.replace("env_", "")] = val;
          });
          if (missingReq) {
            if (errorEl) showModalError(errorEl, "Preencha todos os campos obrigatórios de ambiente.");
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
            await loadServers();
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
          await loadServers();
          hideLoading();
          window.showAppAlert("Servidor merged (local) criado com sucesso.");
        } catch (err) {
          if (errorEl) showModalError(errorEl, err.message);
          window.showAppAlert("Erro no merge local: " + err.message);
        } finally {
          if (btn) { btn.disabled = false; btn.textContent = "Criar Servidor Merged"; }
        }
      }

      window.confirmMerge = confirmMerge;
      const mergeModal = document.getElementById("mergeModal");
      if (mergeModal) mergeModal.addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeMergeModal();
      });

      // ─── Edit ──────────────────────────────────────────────
      let editingServerId = null;
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
          if (errorEl) showModalError(errorEl, "Nome não pode ficar vazio.");
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
          await loadServers();
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
      const editModal = document.getElementById("editModal");
      if (editModal) editModal.addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeEditModal();
      });

      // ─── Inspector ─────────────────────────────────────────
      function openInspector(url, transportType) {
        const transport = transportType === "http" ? "streamable-http" : "sse";
        navigator.clipboard.writeText(url).catch(() => {});
        fetch("http://127.0.0.1:6277/connect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, transportType: transport }),
        }).catch(() => {});
        window.open(
          `http://localhost:6274/?url=${encodeURIComponent(url)}&transportType=${transport}`,
          "_blank",
        );
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
      const createModal = document.getElementById("createModal");
      if (createModal) createModal.addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeCreateModal();
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

      // ─── Error helper ──────────────────────────────────────
      function showModalError(el, msg) {
        if (!el) return;
        el.textContent = msg;
        el.classList.toggle("visible", !!msg);
      }

      // ─── Logs ──────────────────────────────────────────────
      let logsInterval = null;
      let logDebounceTimer = null;

      function _populateLogServerSelect(servers) {
        const sel = document.getElementById("logServerSelect");
        if (!sel) return;
        sel.innerHTML = '<option value="">Servidor...</option>';
        servers.forEach((s) => {
          const opt = document.createElement("option");
          opt.value = s.server_id;
          opt.textContent = s.name;
          if (s.server_id === activeServerId) opt.selected = true;
          sel.appendChild(opt);
        });
      }

      function selectServer(serverId) {
        document.querySelectorAll(".server-card").forEach((c) => c.classList.remove("selected"));
        const card = document.querySelector(`.server-card[data-server-id="${serverId}"]`);
        if (card) card.classList.add("selected");
        activeServerId = serverId;
        const sel = document.getElementById("logServerSelect");
        if (sel) sel.value = serverId;
        pollLogs();
      }

      function switchLogServer(serverId) {
        selectServer(serverId || activeServerId);
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
        if (!activeServerId) return;
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
          const logs = await apiFetch(`/v1/servers/${activeServerId}/logs?${params}`);
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
        try {
          const detail = await apiFetch(`/v1/servers/${activeServerId}/logs/${log.id}`);
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
      const logDetailModal = document.getElementById("logDetailModal");
      if (logDetailModal) logDetailModal.addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeLogDetail();
      });

      async function exportLogs(format) {
        if (!activeServerId) return;
        window.open(`${API_BASE}/v1/servers/${activeServerId}/logs/export?format=${format}`, "_blank");
      }

      function clearLogs() {
        if (!activeServerId) return;
        showConfirmDialog("Limpar todos os logs deste servidor?", async () => {
          try {
            await apiFetch(`/v1/servers/${activeServerId}/logs`, { method: "DELETE" });
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

      function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
      }

      // ─── Init ──────────────────────────────────────────────
      (async function init() {
        await checkGateway();
        await restoreSession();
        await loadServers();
        startLogsPolling();

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
              loadServers();
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

      // Expose to window for inline HTML onclick handlers
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
      window.toggleMenu = toggleMenu;
      window.openInspector = openInspector;
      window.editServer = editServer;
      window.toggleServerStatus = toggleServerStatus;
      window.deleteServer = deleteServer;
      window.unmergeServer = unmergeServer;
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
      window.loadServers = loadServers;
      window.switchLogServer = switchLogServer;
      window.debouncePoll = debouncePoll;
        window.showPayPal = showPayPal;
        window.pollLogs = pollLogs;
        window.setMergeTab = setMergeTab;
        window.openMergeModalFromMenu = openMergeModalFromMenu;
        window.showConfirmDialog = showConfirmDialog;
        window.openResetPasswordModal = openResetPasswordModal;
        window.closeResetPasswordModal = closeResetPasswordModal;
        window.confirmResetPassword = confirmResetPassword;
        window.toggleChangePassword = toggleChangePassword;
        window.saveNewPassword = saveNewPassword;

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
          if (tokenInput) tokenInput.value = token || "(não autenticado)";

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

        const profileModal = document.getElementById("profileModal");
        if (profileModal) profileModal.addEventListener("click", (e) => {
          if (e.target === e.currentTarget) closeProfileModal();
        });

        function copyToken() {
          const val = document.getElementById("profileToken")?.value;
          if (!val || val === "(não autenticado)") return;
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
              loadServers();
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

        // Expose to window for inline HTML onclick handlers
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
        window.toggleMenu = toggleMenu;
        window.openInspector = openInspector;
        window.editServer = editServer;
        window.toggleServerStatus = toggleServerStatus;
        window.deleteServer = deleteServer;
        window.unmergeServer = unmergeServer;
        window.openCreateModal = openCreateModal;
        window.closeCreateModal = closeCreateModal;
        window.createServer = createServer;
        window.saveEdit = saveEdit;
        window.closeEditModal = closeEditModal;
        window.openMergeModalFromMenu = openMergeModalFromMenu;
        window.closeMergeModal = closeMergeModal;
        window.confirmMerge = confirmMerge;
        window.closeLogDetail = closeLogDetail;
        window.exportLogs = exportLogs;
        window.clearLogs = clearLogs;
        window.showConfirmDialog = showConfirmDialog;
        window.loadServers = loadServers;
        window.switchLogServer = switchLogServer;
        window.debouncePoll = debouncePoll;
        window.showPayPal = showPayPal;
        window.pollLogs = pollLogs;
        window.openResetPasswordModal = openResetPasswordModal;
        window.closeResetPasswordModal = closeResetPasswordModal;
        window.confirmResetPassword = confirmResetPassword;
        window.toggleChangePassword = toggleChangePassword;
        window.saveNewPassword = saveNewPassword;

        const _stdioTa = document.getElementById("mergeStdioJson");
        if (_stdioTa) _stdioTa.placeholder = '{\n  "command": "uvx",\n  "args": ["mcp-excel-server"]\n}';
    
  });
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
            <button class="user-profile-btn" id="userProfileBtn" onclick="openProfileModal()" title="Ver perfil">
              <img class="auth-avatar" id="authAvatar" src="" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
              <span class="auth-avatar-fallback" id="authAvatarFallback" style="display:none"></span>
              <span class="auth-name" id="authName"></span>
              <span class="auth-plan" id="authPlan"></span>
            </button>
            <button class="auth-btn logout-btn-nav" onclick="logout()" title="Sair da conta">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              Sair
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
            <h2>Meus Servidores</h2>
            <p class="sub">Gerencie suas pontes MCP na nuvem</p>
          </div>
          <button class="btn-add-server" onclick="openCreateModal()">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 1v12M1 7h12" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            Novo Servidor
          </button>
        </div>

        <div class="server-list" id="serverList">
          <div class="empty-state" id="loadingState">
            <div class="empty-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
                <path d="M5 3h14M5 21h14M7 3v4l5 5-5 5v4M17 3v4l-5 5 5 5v4" />
              </svg>
            </div>
            <div>Carregando servidores<span class="loading-dots"></span></div>
          </div>
        </div>
      </div>

      <!-- RIGHT: Sidebar -->
      <div class="dash-sidebar">
        <!-- Plan Card -->
        <div class="sidebar-card">
          <div class="sidebar-card-header">
            <span class="sidebar-label">Plano Atual</span>
            <span class="plan-badge">✦ Hobby</span>
          </div>
          <div class="stat-grid">
            <div class="stat-row">
              <span class="stat-label">Servidores ativos</span>
              <span class="stat-value num" id="serverCount">—</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">Retenção de logs</span>
              <span class="stat-value num">24h</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">Gateway</span>
              <span class="stat-value ok" id="gatewayStatus">---</span>
            </div>
            <div class="stat-row" id="quotaRowServers" style="display:none">
              <span class="stat-label">Servidores</span>
              <span class="stat-value" id="quotaServers">0/1</span>
            </div>
            <div class="stat-row" id="quotaRowPlan" style="display:none">
              <span class="stat-label">Plano</span>
              <span class="stat-value" id="quotaPlan">Free</span>
            </div>
          </div>
          <div class="sub-section" id="subSection" style="display:none">
            <div class="sub-title">Subscrição</div>
            <div class="sub-quota"><span>Servidores</span><span class="val" id="subServers">0 / 1</span></div>
            <div class="sub-quota"><span>RPM</span><span class="val" id="subRPM">10</span></div>
            <div class="sub-upgrade" id="subUpgrade">
              <button class="sub-upgrade-btn" onclick="showPayPal()">Assinar Pro — $9.90/mês</button>
            </div>
            <div id="paypal-button-container" style="display:none"></div>
          </div>
        </div>

        <!-- Live Logs -->
        <div class="sidebar-logs">
          <div class="sidebar-logs-header">
            <div class="logs-header-left">
              <span class="pulse-dot"></span>
              <span class="log-title">Logs</span>
              <select class="log-server-select" id="logServerSelect" onchange="switchLogServer(this.value)">
                <option value="">Servidor...</option>
              </select>
            </div>
            <div class="logs-header-actions">
              <button class="log-action-btn" title="Exportar JSON" onclick="exportLogs('json')">↓</button>
              <button class="log-action-btn" title="Exportar CSV" onclick="exportLogs('csv')">⇩</button>
              <button class="log-action-btn log-action-danger" title="Limpar logs" onclick="clearLogs()">✕</button>
              <button class="log-refresh-btn" title="Atualizar" onclick="pollLogs()">↻</button>
            </div>
          </div>
          <div class="log-filter-bar">
            <input type="text" class="log-filter-input" id="logToolFilter" placeholder="Filtrar tool..." oninput="debouncePoll()">
            <select class="log-filter-select" id="logStatusFilter" onchange="pollLogs()">
              <option value="">Todos</option>
              <option value="200-299">2xx Sucesso</option>
              <option value="400-499">4xx Erro</option>
              <option value="500-599">5xx Erro</option>
            </select>
          </div>
          <div class="sidebar-logs-body" id="liveLogs">
            <div style="color: rgba(255, 255, 255, 0.2)">
              Aguardando atividade...
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── MERGE MODAL ────────────────────────────────────────── -->
    <div class="modal-overlay" id="mergeModal">
      <div class="modal-box">
        <div class="modal-header">
          <h3>Merge de Servidores</h3>
          <p class="modal-sub" id="mergeSub">Fusão de dois servidores MCP com namespace automático</p>
        </div>
        <div class="merge-tabs">
          <button class="merge-tab active" id="mergeTabLocal" onclick="setMergeTab('local')">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="3" y="3" width="10" height="10" rx="2"/><path d="M8 6v4M6 8h4"/></svg>
            Servidores no rest2mcp
          </button>
          <button class="merge-tab" id="mergeTabSandbox" onclick="setMergeTab('sandbox')">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 8h6M8 5v6"/></svg>
            Sandbox / JSON
          </button>
        </div>
        <div class="form-group">
          <label for="mergeName">Nome do Servidor Merged</label>
          <input type="text" id="mergeName" placeholder="Ex: API Unificada" />
        </div>
        <div id="mergeLocalFields" style="display:block">
          <div class="form-group">
            <label for="mergeTargetSelect">Servidor alvo</label>
            <select id="mergeTargetSelect"><option value="">Selecione um servidor...</option></select>
            <p class="form-hint">Servidor rest2mcp que será fundido com o servidor fonte</p>
          </div>
        </div>
        <div id="mergeSandboxFields" style="display:none">
             <!-- QUICK-SELECT COMENTADO
            <div class="form-group">
            <label>Quick-select</label>
            <div class="sandbox-presets" aria-label="Quick-select de servidores MCP populares">
              <button class="sandbox-preset-btn" onclick="fillSandbox('uvx', 'mcp-excel-server')"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="2" y="2" width="12" height="12" rx="1.5"/><path d="M2 6h12M6 2v12"/></svg>Excel</button>
              <button class="sandbox-preset-btn" onclick="fillSandbox('npx', '@modelcontextprotocol/server-filesystem', '.')"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M2 4.5A2 2 0 014 3h2.5l2 2H14a1 1 0 011 1v5.5a2 2 0 01-2 2H4a2 2 0 01-2-2z"/></svg>File System</button>
              <button class="sandbox-preset-btn" onclick="fillSandbox('pipx', 'mcp-server-sqlite')"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><ellipse cx="8" cy="4" rx="6" ry="2"/><path d="M2 4v3c0 1.1 2.7 2 6 2s6-.9 6-2V4M2 7v3c0 1.1 2.7 2 6 2s6-.9 6-2V7"/></svg>SQLite</button>
              <button class="sandbox-preset-btn" onclick="fillSandbox('uvx', 'mcp-server-pdf')"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 2h5l4 4v8a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z"/><path d="M9 2v4h4M6 9h4M6 11.5h4"/></svg>PDF</button>
            </div>
          </div>
          -->
            <div class="store-divider"><span>ou</span></div>
            <button class="btn-store" onclick="openStoreModal()">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.2"/><path d="M10.2 10.2 14 14"/></svg>
              Instalar a partir da loja
            </button>
          
          <div class="form-group">
            <label for="mergeStdioJson">Config JSON</label>
            <textarea id="mergeStdioJson" rows="5" class="code-textarea"></textarea>
            <p class="form-hint">Comando e args do servidor MCP stdio. O ambiente é herdado do gateway.</p>
          </div>
          <div id="mergeEnvFields" style="display:none"></div>
          <div id="mergePackageWarning" class="store-warning" style="display:none"></div>
        </div>
        <div class="modal-error" id="mergeError"></div>
        <div class="modal-actions">
          <button class="btn-cancel" onclick="closeMergeModal()">Cancelar</button>
          <button class="btn-confirm" id="btnMergeConfirm" onclick="confirmMerge()">Criar Servidor Merged</button>
        </div>
      </div>
    </div>

    <!-- ── STORE MODAL ─────────────────────────────────────────── -->
    <div class="modal-overlay" id="storeModal">
      <div class="modal-box store-box">
        <div class="modal-header">
          <h3>MCP Server Store</h3>
          <p class="modal-sub">Encontre e instale servidores MCP públicos</p>
        </div>
        <div class="store-layout">
          <div class="store-sidebar">
            <div class="store-sidebar-section">
              <div class="store-sidebar-title">Hosting</div>
              <div class="store-filter-bar" id="storeFilterBar"></div>
            </div>
            <div class="store-sidebar-section">
              <div class="store-sidebar-title">Categorias</div>
              <div class="store-cat-list" id="storeCategoryBar"></div>
            </div>
          </div>
          <div class="store-main">
            <div class="store-toolbar">
              <div class="store-search">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.2"/><path d="M10.2 10.2 14 14"/></svg>
                <input type="text" id="storeSearch" placeholder="Buscar servidores MCP..." oninput="searchStore()" />
              </div>
              <select class="store-sort" id="storeSort" onchange="setStoreSort(this.value)">
                <option value="relevance">Relevância</option>
                <option value="stars">★ Estrelas GitHub</option>
                <option value="tools">🛠 Mais ferramentas</option>
                <option value="name">Nome A-Z</option>
                <option value="name_desc">Nome Z-A</option>
              </select>
            </div>
            <div class="store-grid" id="storeGrid">
              <div class="store-loading">A carregar loja...</div>
            </div>
            <button class="store-load-more" id="storeLoadMore" onclick="loadMoreStore()" style="display:none">Carregar mais servidores</button>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" onclick="closeStoreModal()">Fechar</button>
        </div>
      </div>
    </div>

    <!-- ── EDIT MODAL ────────────────────────────────────────── -->
    <div class="modal-overlay" id="editModal">
      <div class="modal-box">
        <div class="modal-header">
          <h3>Editar Servidor</h3>
          <p class="modal-sub">Altere as configurações do servidor MCP</p>
        </div>
        <div class="form-group">
          <label for="editName">Nome do Servidor</label>
          <input type="text" id="editName" placeholder="Ex: Minha API" />
        </div>
        <div class="form-group">
          <label for="editTransport">Transporte</label>
          <select id="editTransport">
            <option value="http">Streamable HTTP (recomendado)</option>
            <option value="sse">SSE (legado)</option>
          </select>
        </div>
        <div class="form-group">
          <label for="editStatus">Status</label>
          <select id="editStatus">
            <option value="active">Online</option>
            <option value="inactive">Offline</option>
          </select>
        </div>
        <div class="modal-error" id="editError"></div>
        <div class="modal-actions">
          <button class="btn-cancel" onclick="closeEditModal()">Cancelar</button>
          <button class="btn-confirm" id="btnEditConfirm" onclick="saveEdit()">Salvar</button>
        </div>
      </div>
    </div>

    <!-- ── CREATE MODAL ──────────────────────────────────────── -->
    <div class="modal-overlay" id="createModal">
      <div class="modal-box">
        <div class="modal-header">
          <h3>Novo Servidor</h3>
          <p class="modal-sub">Registre uma nova API para ser convertida em MCP</p>
        </div>
        <div class="form-group">
          <label for="inputName">Nome do Servidor</label>
          <input type="text" id="inputName" placeholder="Ex: Minha API Principal" />
        </div>
        <div class="form-group">
          <label for="inputSpecUrl">URL do OpenAPI Spec</label>
          <input type="url" id="inputSpecUrl" placeholder="https://api.exemplo.com/openapi.json" />
        </div>
        <div class="form-group">
          <label for="inputTransport">Transporte</label>
          <select id="inputTransport">
            <option value="http">Streamable HTTP (recomendado)</option>
            <option value="sse">SSE (legado)</option>
          </select>
        </div>
        <div class="modal-error" id="modalError"></div>
        <div class="modal-actions">
          <button class="btn-cancel" onclick="closeCreateModal()">Cancelar</button>
          <button class="btn-confirm" id="btnCreateConfirm" onclick="createServer()">Criar Servidor</button>
        </div>
      </div>
    </div>

    <!-- ── LOG DETAIL MODAL ──────────────────────────────────── -->
    <div class="modal-overlay" id="logDetailModal">
      <div class="modal-box log-detail-box">
        <div class="modal-header">
          <h3>Detalhe do Log</h3>
          <p class="modal-sub">Requisição e resposta completas</p>
        </div>
        <div class="log-detail-meta">
          <span class="log-detail-meta-item"><span class="label">Tool</span> <span id="detailTool">—</span></span>
          <span class="log-detail-meta-item"><span class="label">Method</span> <span id="detailMethod">—</span></span>
          <span class="log-detail-meta-item"><span class="label">Status</span> <span id="detailStatus" class="status-badge">—</span></span>
          <span class="log-detail-meta-item"><span class="label">Duração</span> <span id="detailDuration">—</span></span>
          <span class="log-detail-meta-item"><span class="label">Data</span> <span id="detailTime">—</span></span>
        </div>
        <div class="log-detail-scroll">
          <div class="log-detail-section">
            <h4>Request Body</h4>
            <div class="log-detail-body" id="detailReqBody">(vazio)</div>
          </div>
          <div class="log-detail-section">
            <h4>Response Body</h4>
            <div class="log-detail-body" id="detailResBody">(vazio)</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" onclick="closeLogDetail()">Fechar</button>
        </div>
      </div>
    </div>

    <!-- ── PROFILE MODAL ────────────────────────────────────────── -->
    <div class="modal-overlay" id="profileModal">
      <div class="modal-box profile-modal-box">
        <!-- Header -->
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
          <button class="profile-close-btn" onclick="closeProfileModal()" title="Fechar">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <!-- Stats row -->
        <div class="profile-stats-row">
          <div class="profile-stat">
            <span class="profile-stat-label">Servidores</span>
            <span class="profile-stat-value" id="profileServersCount">—</span>
          </div>
          <div class="profile-stat-divider"></div>
          <div class="profile-stat">
            <span class="profile-stat-label">RPM</span>
            <span class="profile-stat-value" id="profileRpm">—</span>
          </div>
          <div class="profile-stat-divider"></div>
          <div class="profile-stat">
            <span class="profile-stat-label">Membro desde</span>
            <span class="profile-stat-value profile-stat-date" id="profileCreatedAt">—</span>
          </div>
        </div>

        <!-- Token section -->
        <div class="profile-section">
          <div class="profile-section-title">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
            Token de Acesso (Bearer)
          </div>
          <div class="profile-token-field">
            <input type="password" id="profileToken" class="profile-token-input" readonly />
            <button class="profile-token-btn" id="toggleTokenBtn" onclick="toggleTokenVisibility()" title="Mostrar/ocultar token">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
            <button class="profile-token-btn profile-copy-btn" id="copyTokenBtn" onclick="copyToken()" title="Copiar token">Copiar</button>
          </div>
          <p class="profile-token-hint">Use este token no cabeçalho <code>Authorization: Bearer <token></code> para autenticar pedidos à API.</p>
        </div>

        <!-- Account details -->
        <div class="profile-section">
          <div class="profile-section-title">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93l-1.41 1.41M12 2v2M4.93 4.93l1.41 1.41M2 12h2M4.93 19.07l1.41-1.41M12 20v2M19.07 19.07l-1.41-1.41M20 12h2"/></svg>
            Detalhes da Conta
          </div>
          <div class="profile-details-grid">
            <div class="profile-detail-row">
              <span class="profile-detail-label">User ID</span>
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

        <!-- Change Password -->
        <div class="profile-section">
          <div class="profile-section-title" style="cursor:pointer;" onclick="toggleChangePassword()">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            Palavra-passe
            <button class="profile-token-btn" id="toggleChangePasswordBtn" style="margin-left:auto;font-size:0.72rem;padding:4px 10px;">Alterar Palavra-passe</button>
          </div>
          <div id="changePasswordSection" style="display:none;margin-top:10px;">
            <div class="profile-token-field" style="margin-bottom:8px;">
              <input type="password" id="newPasswordInput" class="profile-token-input" placeholder="Nova palavra-passe (mín. 6 caracteres)" style="width:100%;" />
            </div>
            <div class="modal-error" id="changePasswordError" style="margin-bottom:8px;"></div>
            <div style="display:flex;gap:8px;">
              <button class="btn-confirm" id="btnSavePassword" onclick="saveNewPassword()" style="flex:1;">Guardar</button>
              <button class="btn-cancel" onclick="toggleChangePassword()">Cancelar</button>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="profile-modal-actions">
          <button class="btn-cancel" onclick="closeProfileModal()">Fechar</button>
          <button class="profile-logout-btn" onclick="logoutFromProfile()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            Terminar Sessão
          </button>
        </div>
      </div>
    </div>

    <!-- ── RESET PASSWORD MODAL (recovery flow) ────────────────── -->
    <div class="modal-overlay" id="resetPasswordModal">
      <div class="modal-box" style="max-width:380px;">
        <div class="modal-header">
          <h3>Redefinir Palavra-passe</h3>
          <p class="modal-sub">Escolha uma nova palavra-passe para a sua conta</p>
        </div>
        <div class="form-group">
          <label for="resetPasswordInput">Nova Palavra-passe</label>
          <input type="password" id="resetPasswordInput" placeholder="Mínimo 6 caracteres" />
        </div>
        <div class="modal-error" id="resetPasswordError"></div>
        <div class="modal-actions">
          <button class="btn-confirm" id="btnResetPassword" onclick="confirmResetPassword()">Redefinir Palavra-passe</button>
        </div>
      </div>
    </div>

    <!-- Portal para dropdowns (evita overflow:hidden dos cards) -->
    <div id="menuPortal"></div>

    <!-- Loading Overlay -->
    <div class="loading-overlay" id="loadingOverlay">
      <div class="loading-spinner"></div>
      <div class="loading-text" id="loadingText">Aguarde...</div>
    </div>
