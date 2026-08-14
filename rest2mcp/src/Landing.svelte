<script>
  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { createClient as createSupabaseClient } from "@supabase/supabase-js";
  import "./Landing.css";
  import r2mcpLogo from "./assets/r2mcp_logo.png";
  import { t } from "./stores/lang.js";
  const __ = (key) => get(t)(key);

  // ─── Scroll-Storytelling: Advantages section ───────────────────
  // Cards are stacked with position:absolute in the same spot inside a
  // sticky wrapper, so IntersectionObserver can't distinguish which
  // card should be "active" — they all share the same bounding box and
  // enter/leave the viewport together. Instead we track scroll
  // progress through the tall container and pick the active index
  // directly from that progress.
  let advantagesContainer;
  let activeAdvantage = 0;
  let advantagesProgress = 0; // continuous 0–1, for the thin progress line
  const ADVANTAGES_COUNT = 5;
  let advantagesTicking = false;

  const advantages = [
    {
      file: "01_instant.setup",
      tag: "SEM CÓDIGO",
      title: "1. Do Zero Código à IA em Segundos",
      body: "Esqueça a complexidade de configurar servidores, gerir dependências e escrever código de integração. Basta colar o link da documentação da sua API na nossa interface e clicar em criar. Transformamos qualquer API numa ferramenta pronta para a Inteligência Artificial, de forma instantânea, sem que você precise escrever uma única linha de código.",
      icon: "bolt"
    },
    {
      file: "02_auth.guard",
      tag: "AUTENTICAÇÃO ISOLADA",
      title: "2. Autenticação Segura e Multiusuário",
      body: "Proteja as credenciais dos seus clientes e da sua empresa. Em vez de delegar logins e senhas para a IA — o que gera riscos graves de segurança —, a nossa plataforma gere a autenticação de forma isolada. O login é feito diretamente pela nossa interface web, e o token de acesso é injetado de forma invisível e segura nas chamadas subsequentes. A IA apenas executa as ações, mas nunca \"vê\" nem armazena as suas senhas.",
      icon: "lock"
    },
    {
      file: "03_logs.stream",
      tag: "LOGS EM TEMPO REAL",
      title: "3. Transparência Total e Observabilidade",
      body: "Diga adeus às \"caixas pretas\". Saber exatamente o que a IA está a fazer é fundamental para a confiança do negócio. A nossa plataforma oferece um painel de logs em tempo real onde você pode visualizar exatamente qual ferramenta foi chamada, quais dados foram enviados, o tempo de resposta e o status de cada requisição. Tenha controle e auditoria total sobre as ações da Inteligência Artificial.",
      icon: "activity"
    },
    {
      file: "04_gateway.proxy",
      tag: "GATEWAY SEGURO",
      title: "4. Gateway Inteligente e Isolamento de Rede",
      body: "Pare de lutar contra erros de CORS, bloqueios de firewall ou limites de requisições. A nossa plataforma atua como um Gateway seguro entre a IA e as suas APIs. O tráfego é roteado e gerido pelos nossos servidores, garantindo que a Inteligência Artificial consiga aceder a serviços internos ou corporativos de forma fluida, sem expor a sua infraestrutura diretamente à internet.",
      icon: "network"
    },
    {
      file: "05_merge.apis",
      tag: "MULTI-API",
      title: "5. Ecossistema Unificado (Merge de APIs)",
      body: "Não se limite a conectar uma API de cada vez. A nossa plataforma permite fundir múltiplas APIs e serviços diferentes numa única interface conectada à IA. Crie ecossistemas complexos de ferramentas com organização inteligente, permitindo que a Inteligência Artificial tenha acesso a um leque completo de capacidades do seu negócio num só lugar, trabalhando de forma integrada.",
      icon: "layers"
    }
  ];

  function updateActiveAdvantage() {
    if (!advantagesContainer) return;
    const rect = advantagesContainer.getBoundingClientRect();
    const scrollableDistance = rect.height - window.innerHeight;
    if (scrollableDistance <= 0) {
      activeAdvantage = 0;
      advantagesProgress = 0;
      return;
    }
    const progress = Math.min(1, Math.max(0, -rect.top / scrollableDistance));
    advantagesProgress = progress;
    activeAdvantage = Math.min(
      ADVANTAGES_COUNT - 1,
      Math.floor(progress * ADVANTAGES_COUNT)
    );
  }

  // Lets someone click a tab to jump straight to that card, like
  // switching tabs in a code editor.
  function jumpToAdvantage(i) {
    if (!advantagesContainer) return;
    const rect = advantagesContainer.getBoundingClientRect();
    const scrollableDistance = rect.height - window.innerHeight;
    if (scrollableDistance <= 0) return;
    const targetProgress = (i + 0.5) / ADVANTAGES_COUNT;
    const targetY = window.scrollY + rect.top + targetProgress * scrollableDistance;
    window.scrollTo({ top: targetY, behavior: "smooth" });
  }

  function onAdvantagesScroll() {
    if (advantagesTicking) return;
    advantagesTicking = true;
    window.requestAnimationFrame(() => {
      updateActiveAdvantage();
      advantagesTicking = false;
    });
  }

  onMount(() => {
    updateActiveAdvantage();
    window.addEventListener("scroll", onAdvantagesScroll, { passive: true });
    window.addEventListener("resize", onAdvantagesScroll, { passive: true });
  });

  onDestroy(() => {
    if (typeof window === "undefined") return;
    window.removeEventListener("scroll", onAdvantagesScroll);
    window.removeEventListener("resize", onAdvantagesScroll);
  });

  onMount(() => {
    // ─── Expor já os handlers ao window, ANTES de qualquer coisa
    // que possa lançar erro (ex: Supabase indisponível). Como são
    // todas `function` declarations, o hoisting garante que já
    // existem aqui em cima mesmo estando definidas mais abaixo. ───
    window.loginWith = loginWith;
    window.openLoginModal = openLoginModal;
    window.closeLoginModal = closeLoginModal;
    window.loginWithEmail = loginWithEmail;
    window.handleStripePro = handleStripePro;
    window.handleFreePlan = handleFreePlan;
    window.handleProPlan = handleProPlan;
    window.toggleAuthMode = toggleAuthMode;
    window.openForgotPasswordModal = openForgotPasswordModal;
    window.closeForgotPasswordModal = closeForgotPasswordModal;
    window.sendForgotPasswordEmail = sendForgotPasswordEmail;
    window.scrollToSection = (id) => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: "smooth" });
    };

    // ─── CONFIGURAÇÃO SUPABASE ─────────────────────────────
    // Defina VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY em rest2mcp/.env
    const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || "";
    const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || "";
    let supabaseClient = null;
    try {
      if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
        throw new Error(
          "VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY não definidos (verifica rest2mcp/.env).",
        );
      }
      supabaseClient = createSupabaseClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    } catch (err) {
      console.error("[Landing] Falha ao inicializar Supabase:", err);
    }

    window.sendContactEmail = async function () {
      const name = document
        .getElementById("contact-name")
        ?.value?.trim();
      const email = document
        .getElementById("contact-email")
        ?.value?.trim();
      const subject = document
        .getElementById("contact-subject")
        ?.value?.trim();
      const message = document
        .getElementById("contact-message")
        ?.value?.trim();

      if (!name || !email || !message) {
        window.showAppAlert("Preencha o nome, email e mensagem.");
        return;
      }
      if (!email.includes("@")) {
        window.showAppAlert("Insira um email válido.");
        return;
      }

      const btn = document.querySelector(".contact-form .btn-primary");
      const originalText = btn ? btn.textContent : "";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "A enviar…";
      }

      try {
        const resp = await fetch("https://formspree.io/f/xkodoywg", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, email, subject, message }),
        });
        if (resp.ok) {
          window.showAppAlert(
            "Mensagem enviada com sucesso! Responderemos em breve.",
          );
          document.getElementById("contact-name").value = "";
          document.getElementById("contact-email").value = "";
          document.getElementById("contact-subject").value = "";
          document.getElementById("contact-message").value = "";
        } else {
          const data = await resp.json().catch(() => ({}));
          window.showAppAlert(
            "Erro ao enviar: " + (data?.error || "tente novamente."),
          );
        }
      } catch (err) {
        window.showAppAlert("Erro de rede: " + (err.message || err));
      }
      if (btn) {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    };

    const API_BASE = (
      localStorage.getItem("api_base") ||
      (location.hostname === "localhost" || location.hostname === "127.0.0.1"
        ? "http://localhost:8080"
        : "https://rest2mcp.fly.dev")
    ).replace(/\/+$/, "");

    function showLoading(btn) {
      if (!btn) return;
      btn.disabled = true;
      const spinner = btn.querySelector(".spinner");
      if (spinner) spinner.style.display = "inline-block";
      const text = btn.querySelector(".btn-text");
      if (text) text.style.opacity = "0";
    }
    function hideLoading(btn) {
      if (!btn) return;
      btn.disabled = false;
      const spinner = btn.querySelector(".spinner");
      if (spinner) spinner.style.display = "none";
      const text = btn.querySelector(".btn-text");
      if (text) text.style.opacity = "1";
    }

    // Função de Login com Provedor Social
    async function loginWith(provider) {
      if (!supabaseClient) {
        window.showAppAlert(
          "Serviço de login indisponível de momento. Tente recarregar a página.",
        );
        return;
      }
      const btn = document.querySelector(`.${provider}-btn`);
      showLoading(btn);
      const { error } = await supabaseClient.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: window.location.origin,
        },
      });
      if (error) {
        hideLoading(btn);
        window.showAppAlert("Erro no login: " + error.message);
      }
    }

    // Alternar entre modo Entrar e Registar
    let isRegisterMode = false;

    function toggleAuthMode() {
      isRegisterMode = !isRegisterMode;
      const title = document.querySelector(".modal-header h3");
      const sub = document.querySelector(".modal-sub");
      const btnText = document.querySelector(".auth-submit .btn-text");
      const toggleEl = document.getElementById("authToggle");
      const forgotLink = document.getElementById("forgotLink");
      const confirmInput = document.getElementById("loginPasswordConfirm");
      if (isRegisterMode) {
        if (title) title.textContent = __("login.register_title");
        if (sub) sub.textContent = __("login.register_sub");
        if (btnText) btnText.textContent = __("login.register_btn");
        if (toggleEl)
          toggleEl.innerHTML =
            __("login.toggle_login") +
            ' <a href="#" onclick="toggleAuthMode(); return false;">' +
            __("login.submit") +
            "</a>";
        if (forgotLink) forgotLink.style.display = "none";
        if (confirmInput) confirmInput.style.display = "block";
      } else {
        if (title) title.textContent = __("login.title");
        if (sub) sub.textContent = __("login.sub");
        if (btnText) btnText.textContent = __("login.submit");
        if (toggleEl)
          toggleEl.innerHTML =
            __("login.toggle_register") +
            ' <a href="#" onclick="toggleAuthMode(); return false;">' +
            __("login.register_btn") +
            "</a>";
        if (forgotLink) forgotLink.style.display = "";
        if (confirmInput) confirmInput.style.display = "none";
      }
    }

    // Função de Login/Registo com Email/Senha
    async function loginWithEmail(e) {
      e.preventDefault();
      const btn = e.target.querySelector(".auth-submit");
      if (!supabaseClient) {
        window.showAppAlert(
          "Serviço de login indisponível de momento. Tente recarregar a página.",
        );
        return;
      }
      showLoading(btn);
      try {
        const email = document.getElementById("loginEmail").value;
        const password = document.getElementById("loginPassword").value;
        if (!email || !password) {
          hideLoading(btn);
          window.showAppAlert("Preencha o email e a palavra-passe.");
          return;
        }
        if (isRegisterMode) {
          const confirmPw = document.getElementById(
            "loginPasswordConfirm",
          ).value;
          if (password !== confirmPw) {
            hideLoading(btn);
            window.showAppAlert("As palavras-passe não coincidem.");
            return;
          }
          const { data, error } = await supabaseClient.auth.signUp({
            email,
            password,
          });
          hideLoading(btn);
          if (error) {
            window.showAppAlert(error.message);
          } else if (data?.user && !data?.session) {
            window.showAppAlert(
              "Confirme o seu email. Verifique a caixa de entrada (e spam).",
            );
            toggleAuthMode();
          } else {
            window.showAppAlert("Registo efetuado com sucesso!");
            toggleAuthMode();
          }
          return;
        }
        const { error } = await supabaseClient.auth.signInWithPassword({
          email,
          password,
        });
        hideLoading(btn);
        if (error) {
          window.showAppAlert(error.message);
        } else {
          closeLoginModal();
          if (localStorage.getItem("pending_pro")) {
            localStorage.removeItem("pending_pro");
            setTimeout(handleStripePro, 300);
          } else {
            window.history.pushState({}, "", "?page=dashboard");
            window.dispatchEvent(new PopStateEvent("popstate"));
          }
        }
      } catch (err) {
        hideLoading(btn);
        window.showAppAlert("Erro inesperado: " + (err.message || err));
      }
    }

    // Verifica se existe sessão ativa
    function restoreSession() {
      const token = localStorage.getItem("supabase_token");
      if (token) {
        // Utilizador já autenticado -> Ajusta botões
        const dbBtn = document.getElementById("dashboardBtn");
        if (dbBtn) {
          dbBtn.textContent = __("nav.go_to_dashboard");
          dbBtn.onclick = (e) => {
            e.preventDefault();
            window.history.pushState({}, "", "?page=dashboard");
            window.dispatchEvent(new PopStateEvent("popstate"));
          };
        }
        const createBtn = document.getElementById("createServerBtn");
        if (createBtn) {
          createBtn.textContent = __("nav.go_to_dashboard");
          createBtn.href = "?page=dashboard";
        }
      }
    }

    // Intercepta e escuta alterações de autenticação
    supabaseClient?.auth?.onAuthStateChange((event, session) => {
      if (session?.access_token) {
        localStorage.setItem("supabase_token", session.access_token);
        if (session.user) {
          localStorage.setItem("supabase_user_id", session.user.id);
          if (session.user.email)
            localStorage.setItem("supabase_user_email", session.user.email);
        }
        if (event === "SIGNED_IN" || event === "INITIAL_SESSION") {
          if (localStorage.getItem("pending_pro")) {
            localStorage.removeItem("pending_pro");
            restoreSession();
            closeLoginModal();
            setTimeout(handleStripePro, 300);
          } else {
            restoreSession();
          }
        } else if (event === "PASSWORD_RECOVERY") {
          sessionStorage.setItem("pw_recovery", "1");
          window.history.pushState({}, "", "?page=dashboard&reset=password");
          window.dispatchEvent(new PopStateEvent("popstate"));
        } else {
          restoreSession();
        }
      }
    });

    // Inicializa sessão
    restoreSession();

    // ─── Esqueci a palavra-passe ────────────────────────────
    function openForgotPasswordModal() {
      closeLoginModal();
      setTimeout(() => {
        const fm = document.getElementById("forgotPasswordModal");
        if (fm) fm.classList.add("open");
        const fi = document.getElementById("forgotEmailInput");
        if (fi) {
          fi.value = document.getElementById("loginEmail")?.value || "";
          setTimeout(() => fi.focus(), 120);
        }
      }, 200);
    }

    function closeForgotPasswordModal() {
      const fm = document.getElementById("forgotPasswordModal");
      if (fm) fm.classList.remove("open");
    }

    async function sendForgotPasswordEmail() {
      if (!supabaseClient) {
        window.showAppAlert(
          "Serviço indisponível de momento. Tente recarregar a página.",
        );
        return;
      }
      const email = document.getElementById("forgotEmailInput")?.value?.trim();
      const btn = document.getElementById("btnForgotSend");
      const errorEl = document.getElementById("forgotError");
      if (errorEl) errorEl.textContent = "";
      if (!email || !email.includes("@")) {
        if (errorEl) errorEl.textContent = "Insira um email válido.";
        return;
      }
      if (btn) {
        btn.disabled = true;
        btn.textContent = __("forgot.sending");
      }
      const { error } = await supabaseClient.auth.resetPasswordForEmail(email, {
        redirectTo: window.location.origin + "?page=dashboard&reset=password",
      });
      if (btn) {
        btn.disabled = false;
        btn.textContent = __("forgot.send");
      }
      if (error) {
        if (errorEl) errorEl.textContent = error.message;
        window.showAppAlert("Erro ao enviar email: " + error.message);
      } else {
        window.showAppAlert(
          "Email enviado! Verifique a sua caixa de entrada (e spam).",
        );
        closeForgotPasswordModal();
      }
    }

    const forgotModal = document.getElementById("forgotPasswordModal");
    if (forgotModal)
      forgotModal.addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeForgotPasswordModal();
      });

    // Modal de login dinâmico
    function openLoginModal() {
      if (localStorage.getItem("supabase_token")) {
        window.history.pushState({}, "", "?page=dashboard");
        window.dispatchEvent(new PopStateEvent("popstate"));
        return;
      }
      document.getElementById("loginModal").classList.add("open");
    }

    function closeLoginModal() {
      document.getElementById("loginModal").classList.remove("open");
    }

    async function handleStripePro() {
      const token = localStorage.getItem("supabase_token");
      if (!token) return;
      const API_BASE = (
        localStorage.getItem("api_base") ||
        (location.hostname === "localhost" || location.hostname === "127.0.0.1"
          ? "http://localhost:8080"
          : "https://rest2mcp.fly.dev")
      ).replace(/\/+$/, "");
      const STRIPE_PUBLISHABLE_KEY = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || "";
      const STRIPE_PRO_PRICE_ID = import.meta.env.VITE_STRIPE_PRO_PRICE_ID || "";
      try {
        const payload = {
          price_id: STRIPE_PRO_PRICE_ID,
          user_id: localStorage.getItem("supabase_user_id") || token,
          email: localStorage.getItem("supabase_user_email") || "",
          success_url: window.location.origin + "/?page=dashboard",
          cancel_url: window.location.origin,
        };
        const resp = await fetch(`${API_BASE}/v1/checkout-session`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || `Erro ${resp.status} do servidor`);
        }
        const data = await resp.json();
        if (data.url) {
          window.location.href = data.url;
          return;
        }
        if (data.sessionId || data.session_id) {
          const stripe = Stripe(STRIPE_PUBLISHABLE_KEY);
          const { error } = await stripe.redirectToCheckout({
            sessionId: data.sessionId || data.session_id,
          });
          if (error) throw new Error(error.message);
          return;
        }
        throw new Error("Resposta inesperada do servidor");
      } catch (err) {
        console.error("Stripe error:", err);
        window.showAppAlert("Erro: " + (err.message || err));
      }
    }

    function handleFreePlan() {
      if (localStorage.getItem("supabase_token")) {
        window.history.pushState({}, "", "?page=dashboard");
        window.dispatchEvent(new PopStateEvent("popstate"));
      } else {
        openLoginModal();
      }
    }
    function handleProPlan() {
      if (localStorage.getItem("supabase_token")) {
        handleStripePro();
      } else {
        localStorage.setItem("pending_pro", "true");
        openLoginModal();
      }
    }

    // Configura os botões da UI para abrirem o modal
    document
      .getElementById("dashboardBtn")
      ?.addEventListener("click", function (e) {
        if (!localStorage.getItem("supabase_token")) {
          e.preventDefault();
          openLoginModal();
        } else {
          window.history.pushState({}, "", "?page=dashboard");
          window.dispatchEvent(new PopStateEvent("popstate"));
        }
      });

    document
      .getElementById("createServerBtn")
      ?.addEventListener("click", function (e) {
        if (!localStorage.getItem("supabase_token")) {
          e.preventDefault();
          openLoginModal();
        } else {
          e.preventDefault();
          window.history.pushState({}, "", "?page=dashboard");
          window.dispatchEvent(new PopStateEvent("popstate"));
        }
      });
  });
</script>

<!-- NAV -->
<nav>
  <div class="nav-inner">
    <div class="logo"><img src={r2mcpLogo} alt="rest2mcp" class="logo-img" /></div>
    <ul class="nav-links">
      <li>
        <button
          class="nav-link-btn"
          onclick={() => window.scrollToSection("about")}
          >{$t("nav.about")}</button
        >
      </li>
      <li>
        <button
          class="nav-link-btn"
          onclick={() => window.scrollToSection("features")}
          >{$t("nav.features")}</button
        >
      </li>
      <li>
        <button
          class="nav-link-btn"
          onclick={() => window.scrollToSection("pricing")}
          >{$t("nav.pricing")}</button
        >
      </li>
      <li>
        <button
          class="nav-link-btn"
          onclick={() => window.scrollToSection("faq")}>{$t("nav.faq")}</button
        >
      </li>
      <li>
        <button
          class="nav-link-btn"
          onclick={() => window.scrollToSection("contacts")}
          >{$t("nav.contact")}</button
        >
      </li>
    </ul>
    <div class="nav-actions">
      <button class="nav-btn" id="dashboardBtn">{$t("nav.login")}</button>
    </div>
  </div>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="hero-bg"></div>
  <div class="hero-grid"></div>
  <div class="hero-inner">
    <div class="hero-tag"><span></span>{$t("hero.tag")}</div>
    <h1>{$t("hero.title")}</h1>
    <p class="hero-sub">
      {$t("hero.sub")}
    </p>
    <div class="hero-ctas">
      <a href="#" role="button" class="btn-primary" id="createServerBtn"
        >{$t("hero.cta")}</a
      >
    </div>
    <div class="hero-badges">
      <div class="badge">
        <span class="svg-icon"
          ><svg
            width="13"
            height="13"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            ><path
              d="M9 1L3 9h6l-2 6 8-8H9l2-8z"
              fill="currentColor"
              stroke="none"
            /></svg
          ></span
        > <b>{$t("hero.badge.seconds")}</b>
      </div>
      <div class="badge">
        <span class="svg-icon"
          ><svg width="11" height="11" viewBox="0 0 12 12" fill="currentColor"
            ><path
              d="M6 0l1.2 4.8L12 6l-4.8 1.2L6 12 4.8 7.2 0 6l4.8-1.2z"
            /></svg
          ></span
        > <b>{$t("hero.badge.zero")}</b>
      </div>
      <div class="badge">
        <span class="svg-icon"
          ><svg
            width="13"
            height="13"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.9"
            stroke-linecap="round"
            ><path d="M13 8A5 5 0 112 5.5" /><path d="M2 2v4h4" /></svg
          ></span
        > <b>{$t("hero.badge.openapi")}</b>
      </div>
      <div class="badge">
        <span class="svg-icon"
          ><svg
            width="13"
            height="13"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.9"
            stroke-linecap="round"><path d="M2 5l4 4 8-8" /></svg
          ></span
        > <b>{$t("hero.badge.auth")}</b>
      </div>
    </div>
  </div>
</section>

<!-- ABOUT -->
<section class="section" id="about">
  <div class="section-label">{$t("about.label")}</div>
  <h2>{$t("about.title")}</h2>
  <div class="about-layout">
    <div>
      <p style="color: var(--muted); margin-bottom: 1rem; font-weight: 300">
        {$t("about.p1")}
      </p>
      <p style="color: var(--muted); margin-bottom: 1.5rem; font-weight: 300">
        <strong style="color: var(--ink)">rest2mcp</strong>
        {$t("about.p2")}
      </p>

      <div class="callout problem">
        <strong
          ><span style="display:inline-flex;align-items:center;gap:5px;"
            ><svg
              width="12"
              height="12"
              viewBox="0 0 16 16"
              fill="none"
              stroke="var(--warn)"
              stroke-width="2.2"
              stroke-linecap="round"
              ><line x1="3" y1="3" x2="13" y2="13" /><line
                x1="13"
                y1="3"
                x2="3"
                y2="13"
              /></svg
            > Problema</span
          ></strong
        >
        {$t("about.problem")}
      </div>
      <div class="callout solution">
        <strong
          ><span style="display:inline-flex;align-items:center;gap:5px;"
            ><svg
              width="12"
              height="12"
              viewBox="0 0 16 16"
              fill="none"
              stroke="#00d4aa"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round"><path d="M2 8l4 4 8-8" /></svg
            > Solução</span
          ></strong
        >
        {$t("about.solution")}
      </div>
    </div>

    <div class="how-it-works">
      <h3>{$t("about.how")}</h3>
      {$t("about.how_desc")}
    </div>
  </div>
</section>

<!-- ARCHITECTURE & SECURITY -->
<section class="section" id="security">
  <div class="section-label">{$t("security.label")}</div>
  <h2>{$t("security.title")}</h2>
  <div style="margin-bottom: 2rem;">
    <span class="zk-badge"
      ><span style="display:inline-flex;align-items:center;gap:5px;"
        ><svg width="10" height="10" viewBox="0 0 12 12" fill="currentColor"
          ><path
            d="M6 0l1.2 4.8L12 6l-4.8 1.2L6 12 4.8 7.2 0 6l4.8-1.2z"
          /></svg
        >
        {$t("security.badge")}</span
      ></span
    >
  </div>
  <div
    class="sec-grid"
    style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem;"
  >
    <div class="callout solution" style="margin: 0;">
      <strong>{$t("security.stateless")}</strong>
      {$t("security.stateless_desc")}
    </div>
    <div class="callout solution" style="margin: 0;">
      <strong>{$t("security.e2e")}</strong>
      {$t("security.e2e_desc")}
    </div>
    <div class="callout solution" style="margin: 0;">
      <strong>{$t("security.audit")}</strong>
      {$t("security.audit_desc")}
    </div>
  </div>

  <!-- Human-in-the-loop Auth Explanation -->
  <div style="margin-top: 2.5rem; padding-top: 2rem; border-top: 1px solid var(--border);">
    <h3 style="font-size: 1.15rem; margin-bottom: 0.75rem;">{$t("auth.why_title")}</h3>
    <p style="color: var(--muted); margin-bottom: 1.5rem; font-weight: 300;">
      {$t("auth.why_desc")}
    </p>
    <div class="how-it-works" style="margin-top: 0;">
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; margin-bottom: 1.5rem;">
        <div class="callout solution" style="margin: 0;">
          <strong>{$t("auth.step1_title")}</strong>
          {$t("auth.step1_desc")}
        </div>
        <div class="callout solution" style="margin: 0;">
          <strong>{$t("auth.step2_title")}</strong>
          {$t("auth.step2_desc")}
        </div>
        <div class="callout solution" style="margin: 0;">
          <strong>{$t("auth.step3_title")}</strong>
          {$t("auth.step3_desc")}
        </div>
      </div>
      <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
        <span class="zk-badge"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg> {$t("auth.zero_exposure")}</span>
        <span class="zk-badge"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg> {$t("auth.full_control")}</span>
      </div>
    </div>
    <div style="margin-top: 1.25rem; padding: 1rem 1.25rem; background: rgba(0, 212, 170, 0.06); border-radius: 12px; border: 1px solid rgba(0, 212, 170, 0.12);">
      <p style="margin: 0; font-size: 0.85rem; color: var(--muted);">
        <strong style="color: var(--accent2);"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="vertical-align:middle;margin-right:3px;"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0018 8 6 6 0 006 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 018.91 14"/></svg> {$t("auth.token_management")}</strong>
      </p>
    </div>
  </div>
</section>

<!-- ADVANTAGES (Scroll-Storytelling) -->
<section class="advantages-scroll-container" bind:this={advantagesContainer}>
  <div class="advantages-sticky-wrapper">
    <div class="advantages-intro">
      <div class="section-label">// 02 — Vantagens</div>
      <h2 class="advantages-heading">Por que escolher o rest2mcp?</h2>
    </div>

    <div class="advantages-window">
      <div class="advantages-window-bar">
        <div class="window-dots" aria-hidden="true">
          <span></span><span></span><span></span>
        </div>
        <div class="advantages-tabs" role="tablist" aria-label="Vantagens">
          {#each advantages as adv, i}
            <button
              type="button"
              class="advantages-tab"
              class:active={activeAdvantage === i}
              role="tab"
              aria-selected={activeAdvantage === i}
              onclick={() => jumpToAdvantage(i)}
            >
              <span class="tab-dot" aria-hidden="true"></span>
              <span class="tab-file">{adv.file}</span>
            </button>
          {/each}
        </div>
        <div class="window-status" aria-hidden="true">
          <span class="status-dot"></span>live
        </div>
      </div>

      <div class="advantages-progress-track" aria-hidden="true">
        <div class="advantages-progress-fill" style="width: {advantagesProgress * 100}%"></div>
      </div>

      <div class="advantages-cards-stack">
        {#each advantages as adv, i}
          <div class="advantage-card" class:is-visible={activeAdvantage === i}>
            <div class="advantage-card-top">
              <span class="advantage-icon">
                {#if adv.icon === "bolt"}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 3 4 14h6l-1 7 9-11h-6l1-7Z"/></svg>
                {:else if adv.icon === "lock"}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
                {:else if adv.icon === "activity"}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2 7 4-14 2 7h6"/></svg>
                {:else if adv.icon === "network"}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2.4"/><circle cx="4" cy="6" r="1.8"/><circle cx="4" cy="18" r="1.8"/><circle cx="20" cy="12" r="1.8"/><path d="M9.8 10.6 5.6 7M9.8 13.4 5.6 17M14.4 12H18"/></svg>
                {:else if adv.icon === "layers"}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="M3 13l9 5 9-5"/><path d="M3 17.5l9 5 9-5"/></svg>
                {/if}
              </span>
              <span class="advantage-number">0{i + 1}</span>
            </div>
            <h3>{adv.title}</h3>
            <p>{adv.body}</p>
            <span class="advantage-tag">{adv.tag}</span>
          </div>
        {/each}
      </div>
    </div>
  </div>
</section>

<!-- FEATURES -->
<div class="features-bg">
  <div class="features-section" id="features">
    <div class="section-label">{$t("features.label")}</div>
    <h2 style="color: white">{$t("features.title")}</h2>
    <p class="section-desc">
      {$t("features.desc")}
    </p>

    <div class="features-grid">
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            ><circle cx="12" cy="12" r="10" /><path
              d="M2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20"
            /></svg
          >
        </div>
        <h3>{$t("feat.anyapi")}</h3>
        <p>{$t("feat.anyapi_desc")}</p>
      </div>
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            ><rect x="3" y="11" width="18" height="11" rx="2" /><path
              d="M7 11V7a5 5 0 0110 0v4"
            /></svg
          >
        </div>
        <h3>{$t("feat.auth")}</h3>
        <p>{$t("feat.auth_desc")}</p>
      </div>
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            ><path d="M21 2v6h-6" /><path d="M3 12a9 9 0 0115-6.7L21 8" /><path
              d="M3 22v-6h6"
            /><path d="M21 12a9 9 0 01-15 6.7L3 16" /></svg
          >
        </div>
        <h3>{$t("feat.merge")}</h3>
        <p>{$t("feat.merge_desc")}</p>
      </div>
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            ><rect x="2" y="3" width="20" height="14" rx="2" /><path
              d="M8 21h8M12 17v4"
            /></svg
          >
        </div>
        <h3>{$t("feat.compat")}</h3>
        <p>{$t("feat.compat_desc")}</p>
      </div>
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            ><circle cx="11" cy="11" r="7" /><path d="M16.5 16.5L21 21" /></svg
          >
        </div>
        <h3>{$t("feat.logs")}</h3>
        <p>{$t("feat.logs_desc")}</p>
      </div>
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            ><path d="M12 2L2 7l10 5 10-5-10-5z" /><path
              d="M2 17l10 5 10-5"
            /><path d="M2 12l10 5 10-5" /></svg
          >
        </div>
        <h3>{$t("feat.proxy")}</h3>
        <p>{$t("feat.proxy_desc")}</p>
      </div>
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            ><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle
              cx="12"
              cy="7"
              r="4"
            /></svg
          >
        </div>
        <h3>{$t("feat.secure")}</h3>
        <p>{$t("feat.secure_desc")}</p>
      </div>
      <div class="feat-card">
        <div class="feat-icon">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            stroke-width="1.6"
            stroke-linecap="round"
            ><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z" /><line
              x1="3"
              y1="6"
              x2="21"
              y2="6"
            /><path d="M16 10a4 4 0 01-8 0" /></svg
          >
        </div>
        <h3>{$t("feat.stripe")}</h3>
        <p>{$t("feat.stripe_desc")}</p>
      </div>
    </div>
  </div>
</div>

<!-- PRICING -->
<div class="features-bg">
  <div class="features-section" id="pricing">
    <div class="section-label">{$t("pricing.label")}</div>
    <h2 style="color: white">{$t("pricing.title")}</h2>
    <p class="section-desc">{$t("pricing.desc")}</p>
    <div class="pricing-grid">
      <div class="feat-card pricing-card">
        <div class="pricing-name">{$t("pricing.hobby")}</div>
        <div class="pricing-price">{$t("pricing.hobby_price")}</div>
        <div class="pricing-desc">{$t("pricing.hobby_desc")}</div>
        <ul class="pricing-features">
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.hobby.feat1")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.hobby.feat2")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.hobby.feat3")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.hobby.feat4")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.hobby.feat5")}
          </li>
        </ul>
        <button
          class="btn-ghost"
          style="display: block; text-align: center; color: white; border-color: rgba(255,255,255,0.2); width: 100%; cursor: pointer;"
          onclick={() => window.handleFreePlan()}
          >{$t("pricing.hobby.cta")}</button
        >
      </div>
      <div class="feat-card pricing-card popular">
        <span class="pricing-popular-badge">{$t("pricing.popular")}</span>
        <div class="pricing-name">{$t("pricing.pro")}</div>
        <div class="pricing-price">
          {$t("pricing.pro_price")}<span style="font-size: 0.9rem;"
            >{$t("pricing.pro_month")}</span
          >
        </div>
        <div class="pricing-desc">{$t("pricing.pro_desc")}</div>
        <ul class="pricing-features">
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.pro.feat1")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.pro.feat2")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.pro.feat3")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.pro.feat4")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.pro.feat5")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.pro.feat6")}
          </li>
        </ul>
        <button
          class="btn-primary"
          style="display: block; text-align: center; width: 100%; cursor: pointer;"
          onclick={() => window.handleProPlan()}>{$t("pricing.pro.cta")}</button
        >
      </div>
      <div class="feat-card pricing-card">
        <div class="pricing-name">{$t("pricing.enterprise")}</div>
        <div class="pricing-price" style="font-size: 1.8rem;">
          {$t("pricing.enterprise_price")}
        </div>
        <div class="pricing-desc">{$t("pricing.enterprise_desc")}</div>
        <ul class="pricing-features">
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.enterprise.feat1")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.enterprise.feat2")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.enterprise.feat3")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.enterprise.feat4")}
          </li>
          <li>
            <span class="check-icon"
              ><svg
                width="12"
                height="12"
                viewBox="0 0 14 14"
                fill="none"
                stroke="#00d4aa"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M1.5 7l4 4 7-7" /></svg
              ></span
            >
            {$t("pricing.enterprise.feat5")}
          </li>
        </ul>
        <button
          class="btn-ghost"
          style="display: block; width: 100%; text-align: center; color: white; border-color: rgba(255,255,255,0.2); cursor: pointer;"
          onclick={() => window.scrollToSection("contacts")}
          >{$t("pricing.enterprise.cta")}</button
        >
      </div>
    </div>
  </div>
</div>

<!-- DASHBOARD PREVIEW -->
<section class="section" id="dashboard-preview">
  <div class="section-label">{$t("dashboard.label")}</div>
  <h2>{$t("dashboard.title")}</h2>
  <p class="section-desc">{$t("dashboard.desc")}</p>
  <div
    style="background: #0d0d14; border-radius: 16px; padding: 2rem; border: 1px solid rgba(255,255,255,0.08);"
  >
    <div
      style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem;"
    >
      <div
        style="font-family: var(--display); font-size: 1.1rem; font-weight: 700; color: white;"
      >
        {$t("dashboard.my_servers")}
      </div>
      <div style="display: flex; gap: 8px;">
        <span
          style="font-family: var(--mono); font-size: 0.65rem; color: var(--accent2); background: rgba(0,212,170,0.1); padding: 4px 10px; border-radius: 100px;"
          >2 {$t("dashboard.online")}</span
        >
        <span
          style="font-family: var(--mono); font-size: 0.65rem; color: var(--muted); background: rgba(255,255,255,0.05); padding: 4px 10px; border-radius: 100px;"
          >1 {$t("dashboard.offline")}</span
        >
      </div>
    </div>
    <div
      style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 1.5rem;"
    >
      <div class="dash-card">
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="dash-status-dot online"></span>
          <span
            style="font-family: var(--display); font-weight: 600; color: white; font-size: 0.9rem;"
            >Minha API Principal</span
          >
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span
            style="font-family: var(--mono); font-size: 0.7rem; color: var(--accent2);"
            >SSE · Online</span
          >
          <button class="dash-copy-btn">Copy Connection URL</button>
        </div>
      </div>
      <div class="dash-card">
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="dash-status-dot online"></span>
          <span
            style="font-family: var(--display); font-weight: 600; color: white; font-size: 0.9rem;"
            >Loja API (Merge)</span
          >
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span
            style="font-family: var(--mono); font-size: 0.7rem; color: var(--accent2);"
            >HTTP · Online</span
          >
          <button class="dash-copy-btn">Copy Connection URL</button>
        </div>
      </div>
      <div class="dash-card">
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="dash-status-dot offline"></span>
          <span
            style="font-family: var(--display); font-weight: 600; color: white; font-size: 0.9rem;"
            >API Legada (Swagger 2.0)</span
          >
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span
            style="font-family: var(--mono); font-size: 0.7rem; color: var(--warn);"
            >Offline</span
          >
          <button class="dash-copy-btn" disabled>Copy Connection URL</button>
        </div>
      </div>
    </div>
    <div class="dash-logs">
      <div class="dash-logs-header">
        <span class="log-dot"></span>
        <span
          style="font-family: var(--mono); font-size: 0.7rem; color: rgba(255,255,255,0.4);"
          >Live Logs</span
        >
      </div>
      <div class="dash-logs-body">
        <div class="info-line">
          [INFO] IA chamou tool: 'get_user_by_id' — 145ms
        </div>
        <div>[200 OK] Resposta: &#123;"id": 1, "nome": "João"&#125;</div>
        <div class="info-line" style="margin-top: 4px;">
          [INFO] IA chamou tool: 'list_products' — 89ms
        </div>
        <div>
          [200 OK] Resposta: [&#123;"id": 1, "nome": "Produto A"&#125;, ...]
        </div>
      </div>
    </div>
  </div>
</section>

<!-- FAQ -->
<section class="section" id="faq">
  <div class="section-label">{$t("faq.label")}</div>
  <h2>{$t("faq.title")}</h2>
  <p class="section-desc">{$t("faq.desc")}</p>
  <div class="faq-grid">
    <div class="qs-step">
      <div class="qs-step-head"><h3>{$t("faq.q1")}</h3></div>
      <div class="qs-step-body"><p>{$t("faq.a1")}</p></div>
    </div>
    <div class="qs-step">
      <div class="qs-step-head"><h3>{$t("faq.q2")}</h3></div>
      <div class="qs-step-body"><p>{$t("faq.a2")}</p></div>
    </div>
    <div class="qs-step">
      <div class="qs-step-head"><h3>{$t("faq.q3")}</h3></div>
      <div class="qs-step-body"><p>{$t("faq.a3")}</p></div>
    </div>
    <div class="qs-step">
      <div class="qs-step-head"><h3>{$t("faq.q4")}</h3></div>
      <div class="qs-step-body"><p>{$t("faq.a4")}</p></div>
    </div>
    <div class="qs-step">
      <div class="qs-step-head"><h3>{$t("faq.q5")}</h3></div>
      <div class="qs-step-body"><p>{$t("faq.a5")}</p></div>
    </div>
    <div class="qs-step">
      <div class="qs-step-head"><h3>{$t("faq.q6")}</h3></div>
      <div class="qs-step-body"><p>{$t("faq.a6")}</p></div>
    </div>
    <div class="qs-step">
      <div class="qs-step-head"><h3>{$t("faq.q7")}</h3></div>
      <div class="qs-step-body"><p>{$t("faq.a7")}</p></div>
    </div>
  </div>
</section>

<!-- CONTACTS -->
<section class="section" id="contacts">
  <div class="section-label">{$t("contact.label")}</div>
  <h2>{@html $t("contact.title")}</h2>
  <p class="section-desc">
    {$t("contact.desc")}
  </p>

  <div
    style="margin-top: 2.5rem; display: flex; flex-direction: column; gap: 2rem;"
  >
    <div class="contact-form">
      <div class="contact-row">
        <input
          type="text"
          id="contact-name"
          placeholder={$t("contact.name")}
          class="contact-input"
        />
        <input
          type="email"
          id="contact-email"
          placeholder={$t("contact.email")}
          class="contact-input"
        />
      </div>
      <input
        type="text"
        id="contact-subject"
        placeholder={$t("contact.subject")}
        class="contact-input"
      />
      <textarea
        id="contact-message"
        placeholder={$t("contact.message")}
        class="contact-textarea"
      ></textarea>
      <button
        type="button"
        class="btn-primary"
        style="align-self: flex-start; padding: 12px 30px; cursor: pointer; border: none;"
        onclick={() => window.sendContactEmail()}
      >
        {$t("contact.send")}
      </button>
    </div>

    <div
      style="font-size: 0.9rem; color: var(--muted); border-top: 1px solid var(--border); padding-top: 1.5rem;"
    >
      <p>
        {$t("contact.or")}
        <strong
          ><a
            href="mailto:m4codexp@gmail.com"
            style="color: var(--accent); text-decoration: none;"
            >m4codexp@gmail.com</a
          ></strong
        >
      </p>
    </div>
  </div>
</section>

<hr class="divider" />

<!-- CONFIG -->
<section class="section" id="config">
  <div class="section-label">{$t("config.label")}</div>
  <h2>{@html $t("config.title")}</h2>
  <p class="section-desc">
    {$t("config.desc")}
  </p>
  <div class="mcp-clients">
    <div
      class="mcp-client"
      title="Visual Studio Code — suporte MCP via GitHub Copilot"
    >
      <img src="/logos/vscode-icon.svg" alt="VS Code" />
      <span>VS Code</span>
    </div>
    <div class="mcp-client" title="Claude Desktop by Anthropic">
      <img src="/logos/claude-icon.svg" alt="Claude Desktop" />
      <span>Claude Desktop</span>
    </div>
    <div class="mcp-client" title="Cursor — AI Code Editor">
      <img src="https://cdn.simpleicons.org/cursor/00C2FF" alt="Cursor" />
      <span>Cursor</span>
    </div>
    <div class="mcp-client" title="Cline — MCP Client">
      <img src="https://cdn.simpleicons.org/cline/EC4899" alt="Cline" />
      <span>Cline</span>
    </div>
    <div
      class="mcp-client"
      title="Continue.dev — Open-source AI code assistant"
    >
      <img
        src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/continue.svg"
        alt="Continue"
      />
      <span>Continue</span>
    </div>
    <div class="mcp-client" title="Windsurf — AI Code Editor">
      <img src="/logos/windsurf-icon.svg" alt="Windsurf" />
      <span>Windsurf</span>
    </div>
    <div
      class="mcp-client"
      title="Claude Code — Terminal AI agent by Anthropic"
    >
      <img
        src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/claude.svg"
        alt="Claude Code"
      />
      <span>Claude Code</span>
    </div>
    <div class="mcp-client" title="Gemini CLI — Google AI assistant">
      <img src="/logos/gemini-cli-icon.svg" alt="Gemini CLI" />
      <span>Gemini CLI</span>
    </div>
    <div class="mcp-client" title="OpenCode — CLI AI coding agent">
      <img src="/logos/opencode-icon.svg" alt="OpenCode" />
      <span>OpenCode</span>
    </div>
    <div class="mcp-client" title="Antigravity — MCP client by Google">
      <img src="/logos/antigravity-icon.png" alt="Antigravity" />
      <span>Antigravity</span>
    </div>
    <div class="mcp-client" title="Qualquer cliente compatível com MCP">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        ><rect x="2" y="2" width="20" height="8" rx="2" ry="2" /><rect
          x="2"
          y="14"
          width="20"
          height="8"
          rx="2"
          ry="2"
        /><line x1="6" y1="6" x2="6.01" y2="6" /><line
          x1="6"
          y1="18"
          x2="6.01"
          y2="18"
        /></svg
      >
      <span>{$t("config.more")}</span>
    </div>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <div class="footer-inner">
    <div class="footer-logo"><img src={r2mcpLogo} alt="rest2mcp" class="footer-logo-img" /></div>
    <p style="color: rgba(255, 255, 255, 0.35); font-size: 0.85rem">
      {$t("footer.desc")}
    </p>
    <ul class="footer-links">
      <li>
        <a
          href="#"
          role="button"
          onclick={() => window.scrollToSection("about")}
          >{$t("footer.about")}</a
        >
      </li>
      <li>
        <a
          href="#"
          role="button"
          onclick={() => window.scrollToSection("features")}
          >{$t("nav.features")}</a
        >
      </li>
      <li>
        <a
          href="#"
          role="button"
          onclick={() => window.scrollToSection("pricing")}
          >{$t("nav.pricing")}</a
        >
      </li>
      <li>
        <a href="#" role="button" onclick={() => window.scrollToSection("faq")}
          >{$t("nav.faq")}</a
        >
      </li>
      <li>
        <a
          href="#"
          role="button"
          onclick={() => window.scrollToSection("contacts")}
          >{$t("nav.contact")}</a
        >
      </li>
      <li><a href="mailto:m4codexp@gmail.com">{$t("footer.support")}</a></li>
    </ul>
    <p class="footer-copy">
      {$t("footer.rights")}
    </p>
  </div>
</footer>

<!-- MODAL DE LOGIN SOCIAL -->
<div class="modal-overlay" id="loginModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3>{$t("login.title")}</h3>
      <p class="modal-sub">{$t("login.sub")}</p>
    </div>
    <div class="social-login-container">
      <button
        class="social-btn google-btn"
        onclick={() => window.loginWith("google")}
      >
        <svg viewBox="0 0 24 24" class="social-icon" fill="currentColor"
          ><path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
          /><path
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
          /><path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
          /><path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
          /></svg
        >
        <span class="btn-text">{$t("login.google")}</span>
        <span class="spinner" style="display:none;"
          ><svg
            class="spinner-svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            ><path
              d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
            /></svg
          ></span
        >
      </button>
      <button
        class="social-btn github-btn"
        onclick={() => window.loginWith("github")}
      >
        <svg viewBox="0 0 24 24" class="social-icon" fill="currentColor"
          ><path
            d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.385-1.335-1.755-1.335-1.755-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12 24 5.37 18.63 0 12 0z"
          /></svg
        >
        <span class="btn-text">{$t("login.github")}</span>
        <span class="spinner" style="display:none;"
          ><svg
            class="spinner-svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            ><path
              d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
            /></svg
          ></span
        >
      </button>
      <!--
          <button class="social-btn apple-btn" onclick={() => window.loginWith('apple')}>
            <svg viewBox="0 0 24 24" class="social-icon" fill="currentColor"><path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/></svg>
            Entrar com a Apple
          </button>
          -->
      <div class="email-login-divider">
        <span>{$t("login.email_divider")}</span>
      </div>
      <form
        class="email-login-form"
        onsubmit={() => window.loginWithEmail(event)}
      >
        <input
          type="email"
          id="loginEmail"
          placeholder={$t("login.email_placeholder")}
          required
          class="auth-input"
        />
        <input
          type="password"
          id="loginPassword"
          placeholder={$t("login.password_placeholder")}
          required
          class="auth-input"
        />
        <input
          type="password"
          id="loginPasswordConfirm"
          placeholder={$t("login.confirm_placeholder")}
          class="auth-input"
          style="display:none;"
          onpaste={(e) => e.preventDefault()}
        />
        <div style="text-align: right; margin-top: -8px; margin-bottom: 8px;">
          <a
            href="#"
            role="button"
            id="forgotLink"
            onclick={(e) => {
              e.preventDefault();
              window.openForgotPasswordModal();
            }}
            style="font-size: 0.8rem; color: var(--accent); text-decoration: none;"
            >{$t("login.forgot")}</a
          >
        </div>
        <button type="submit" class="btn-primary auth-submit"
          ><span class="btn-text">{$t("login.submit")}</span><span
            class="spinner"
            style="display:none;"
            ><svg
              class="spinner-svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              ><path
                d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
              /></svg
            ></span
          ></button
        >
        <div
          style="text-align: center; margin-top: 12px; font-size: 0.85rem; color: var(--muted);"
        >
          <span id="authToggle"
            >{$t("login.toggle_register")}
            <a href="#" onclick={window.toggleAuthMode}
              >{$t("login.register_btn")}</a
            ></span
          >
        </div>
      </form>
    </div>
    <div
      class="modal-actions"
      style="margin-top: 1.5rem; display: flex; justify-content: center;"
    >
      <button class="btn-cancel" onclick={() => window.closeLoginModal()}
        >{$t("login.cancel")}</button
      >
    </div>
  </div>
</div>

<!-- STRIPE CHECKOUT MODAL -->
<div class="modal-overlay" id="stripeModal">
  <div class="modal-box" style="text-align:center;">
    <div class="modal-header">
      <h3>{$t("paypal.title")}</h3>
      <p class="modal-sub">{$t("paypal.sub")}</p>
    </div>
    <div
      class="modal-actions"
      style="justify-content:center;margin-top:1.5rem;"
    >
      <button
        class="btn-confirm"
        onclick={() => window.handleStripePro()}
        style="padding:0.7rem 2rem;">{$t("pricing.pro.cta")}</button
      >
      <button
        class="btn-cancel"
        onclick={() =>
          document.getElementById("stripeModal").classList.remove("open")}
        >{$t("common.cancel")}</button
      >
    </div>
  </div>
</div>

<!-- MODAL ESQUECI A PALAVRA-PASSE -->
<div class="modal-overlay" id="forgotPasswordModal">
  <div class="modal-box" style="max-width:380px;">
    <div class="modal-header">
      <h3>{$t("forgot.title")}</h3>
      <p class="modal-sub">{$t("forgot.sub")}</p>
    </div>
    <div class="form-group">
      <label for="forgotEmailInput">Email</label>
      <input
        type="email"
        id="forgotEmailInput"
        placeholder={$t("forgot.email_placeholder")}
        class="auth-input"
      />
    </div>
    <div class="modal-error" id="forgotError"></div>
    <div class="modal-actions" style="flex-direction:column;gap:8px;">
      <button
        class="btn-confirm"
        id="btnForgotSend"
        onclick={() => window.sendForgotPasswordEmail()}
        style="width:100%;">{$t("forgot.send")}</button
      >
      <button
        class="btn-cancel"
        onclick={() => window.closeForgotPasswordModal()}
        style="width:100%;">{$t("forgot.cancel")}</button
      >
    </div>
  </div>
</div>

<!-- Supabase SDK e Código de Autenticação -->

<a href="https://ko-fi.com/F1F81ZH0QM" target="_blank" class="kofi-btn">
  <img
    height="36"
    style="border:0px;height:36px;"
    src="https://storage.ko-fi.com/cdn/kofi5.png?v=6"
    border="0"
    alt="Buy Me a Coffee at ko-fi.com"
  />
</a>

<style>
  /* ─── ADVANTAGES: Scroll-Storytelling ─────────────────────── */

  /* Tall container that provides the scroll distance for the effect.
     100vh per card gives each one a full screen of scroll to "own"
     before the next one takes over. */
  .advantages-scroll-container {
    height: 500vh;
    position: relative;
  }

  /* Pinned viewport-height window while scrolling through the section */
  .advantages-sticky-wrapper {
    position: sticky;
    top: 0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding: 2rem 1.5rem;
  }

  .advantages-intro {
    text-align: center;
    margin-bottom: 2rem;
  }

  .advantages-intro .section-label {
    margin-bottom: 0.75rem;
  }

  .advantages-heading {
    font-size: 2.2rem;
    font-weight: 800;
    margin: 0;
  }

  /* The whole thing reads as a single "code editor" window: dark
     chrome on top, light content pane below — echoing the dashboard
     mockup used elsewhere on the page, so the section feels native to
     the product rather than a generic card grid. */
  .advantages-window {
    width: 100%;
    max-width: 820px;
border-radius: var(--radius);
    overflow: hidden;
    box-shadow: 0 30px 70px rgba(0, 0, 0, 0.4);
    border: 1px solid var(--border);
  }

  .advantages-window-bar {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    background: #0d0d14;
    padding: 0.85rem 1.1rem;
  }

  .window-dots {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
  }

  .window-dots span {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.15);
  }

  .advantages-tabs {
    display: flex;
    flex: 1;
    gap: 0.35rem;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .advantages-tabs::-webkit-scrollbar {
    display: none;
  }

  .advantages-tab {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    padding: 0.4rem 0.7rem;
    cursor: pointer;
    font-family: var(--mono, monospace);
    font-size: 0.7rem;
    color: rgba(255, 255, 255, 0.4);
    white-space: nowrap;
    transition: background 0.3s ease, color 0.3s ease;
  }

  .advantages-tab:hover {
    color: rgba(255, 255, 255, 0.7);
    background: rgba(255, 255, 255, 0.05);
  }

  .advantages-tab.active {
    color: white;
    background: rgba(255, 255, 255, 0.08);
  }

  .tab-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.2);
    flex-shrink: 0;
    transition: background 0.3s ease;
  }

  .advantages-tab.active .tab-dot {
    background: var(--accent2, #00d4aa);
  }

  .window-status {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--mono, monospace);
    font-size: 0.65rem;
    color: rgba(255, 255, 255, 0.35);
    flex-shrink: 0;
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent2, #00d4aa);
    box-shadow: 0 0 0 0 rgba(0, 212, 170, 0.5);
    animation: advantages-pulse 2s ease-in-out infinite;
  }

  @keyframes advantages-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(0, 212, 170, 0.4); }
    50% { box-shadow: 0 0 0 4px rgba(0, 212, 170, 0); }
  }

  .advantages-progress-track {
    height: 2px;
    background: rgba(255, 255, 255, 0.08);
  }

  .advantages-progress-fill {
    height: 100%;
    background: var(--accent, #2f6fed);
    transition: width 0.1s linear;
  }

  .advantages-cards-stack {
    position: relative;
    width: 100%;
    height: 380px;
    background: var(--card-bg);
  }

  .advantage-card {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    box-sizing: border-box;
    padding: 2.75rem 3rem;
    display: flex;
    flex-direction: column;
    background: var(--card-bg);
    opacity: 0;
    transform: translateY(28px) scale(0.97);
    transition: opacity 0.7s cubic-bezier(0.16, 1, 0.3, 1),
      transform 0.7s cubic-bezier(0.16, 1, 0.3, 1);
    pointer-events: none;
  }

  .advantage-card.is-visible {
    opacity: 1;
    transform: translateY(0) scale(1);
    pointer-events: auto;
  }

  .advantage-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  .advantage-icon {
    width: 44px;
    height: 44px;
border-radius: var(--radius-sm);
    background: rgba(0, 212, 170, 0.1);
    color: var(--accent2, #00d4aa);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .advantage-icon svg {
    width: 22px;
    height: 22px;
  }

  .advantage-number {
    font-family: var(--mono, monospace);
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.25);
    letter-spacing: 0.05em;
  }

  .advantage-card h3 {
    font-size: 1.6rem;
    font-weight: 800;
    margin: 0 0 0.85rem;
    color: var(--ink);
  }

  .advantage-card p {
    font-size: 1.02rem;
    line-height: 1.6;
    color: var(--muted);
    margin: 0;
    flex: 1;
  }

  .advantage-tag {
    align-self: flex-start;
    margin-top: 1.5rem;
    font-family: var(--mono, monospace);
    font-size: 0.65rem;
    letter-spacing: 0.03em;
    color: var(--accent2, #00d4aa);
    background: rgba(0, 212, 170, 0.1);
    padding: 4px 10px;
    border-radius: 100px;
  }

  @media (max-width: 640px) {
    .advantages-window-bar {
      gap: 0.75rem;
    }
    .tab-file {
      display: none;
    }
    .advantages-cards-stack {
      height: 460px;
    }
    .advantage-card {
      padding: 2rem 1.5rem;
    }
    .advantage-card h3 {
      font-size: 1.3rem;
    }
    .advantage-card p {
      font-size: 0.95rem;
    }
  }
</style>