<script>
  import { onMount } from 'svelte';
  import Landing from './Landing.svelte';
  import Dashboard from './Dashboard.svelte';
  import { lang, toggleLang } from './stores/lang.js';

  let currentRoute = 'landing';

  function handleRoute() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('page') === 'dashboard') {
      currentRoute = 'dashboard';
    } else {
      currentRoute = 'landing';
    }
  }

  onMount(() => {
    window.addEventListener('popstate', handleRoute);
    handleRoute();

    const handleLinkClick = (e) => {
      const anchor = e.target.closest('a');
      if (anchor && anchor.href) {
        const href = anchor.getAttribute('href') || '';
        const url = new URL(href, window.location.origin);
        const params = new URLSearchParams(url.search);
        if (params.get('page') === 'dashboard') {
          e.preventDefault();
          window.history.pushState({}, '', href);
          handleRoute();
        }
      }
    };

    document.addEventListener('click', handleLinkClick);

    return () => {
      window.removeEventListener('popstate', handleRoute);
      document.removeEventListener('click', handleLinkClick);
    };
  });
</script>

<button class="lang-toggle" onclick={toggleLang}>
  {$lang === 'pt' ? '🇬🇧 EN' : '🇵🇹 PT'}
</button>

{#if currentRoute === 'dashboard'}
  <Dashboard />
{:else}
  <Landing />
{/if}

<style>
  .lang-toggle {
    position: fixed;
    top: 12px;
    right: 12px;
    z-index: 99999;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 14px;
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 100px;
    background: rgba(12,12,20,0.55);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    color: white;
    font-family: Inter, sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s;
    user-select: none;
  }
  .lang-toggle:hover {
    background: rgba(12,12,20,0.8);
    border-color: rgba(255,255,255,0.5);
  }
</style>
