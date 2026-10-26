(function () {
  const script = document.currentScript;
  const serverUrl = (script.getAttribute('data-server-url') || 'http://localhost:3000').replace(/\/$/, '');
  const position = script.getAttribute('data-position') === 'bottom-left' ? 'bottom-left' : 'bottom-right';
  const type = script.getAttribute('data-type') || 'voice';
  const allowToggle = script.getAttribute('data-allow-toggle') !== 'false';
  const lang = script.getAttribute('data-lang') === 'en' ? 'en' : 'th';
  const url = new URL(serverUrl + '/widget', document.baseURI);
  url.searchParams.set('type', type);
  url.searchParams.set('allowToggle', String(allowToggle));
  url.searchParams.set('apiKey', script.getAttribute('data-api-key') || '');
  if (lang !== 'th') url.searchParams.set('lang', lang);
  const serverOrigin = url.origin;
  const frameId = 'servio-chat-' + Math.random().toString(36).slice(2);

  const style = document.createElement('style');
  style.textContent = `
    .dvoice-widget-container {
      position: fixed; z-index: 9999; display: flex; flex-direction: column;
      bottom: max(20px, env(safe-area-inset-bottom)); font-family: system-ui, sans-serif;
    }
    .dvoice-widget-container.bottom-right { right: max(20px, env(safe-area-inset-right)); align-items: flex-end; }
    .dvoice-widget-container.bottom-left { left: max(20px, env(safe-area-inset-left)); align-items: flex-start; }
    .dvoice-widget-frame {
      box-sizing: border-box; width: min(400px, calc(100vw - 40px));
      height: min(640px, calc(100vh - 112px)); height: min(640px, calc(100dvh - 112px));
      border: 1px solid var(--servio-frame-border, #dce8f1); border-radius: 24px;
      box-shadow: 0 20px 70px -18px rgba(13,27,42,.28), 0 2px 10px rgba(39,134,194,.08);
      background: var(--servio-frame-bg, #f5faff); position: absolute; bottom: 74px;
      opacity: 0; transform: translateY(12px); pointer-events: none;
      transition: opacity .2s ease, transform .2s ease;
    }
    .dvoice-widget-frame[hidden] { display: none !important; }
    .dvoice-widget-frame.visible { opacity: 1; transform: translateY(0); pointer-events: auto; }
    .dvoice-widget-button {
      box-sizing: border-box; width: 56px; height: 56px; padding: 0;
      border-radius: 50%; border: 1px solid rgba(255,255,255,.65);
      background: linear-gradient(145deg, var(--servio-primary, #2786c2), var(--servio-strong, #1a5a8a)); color: var(--servio-on-primary, #fff);
      box-shadow: 0 8px 24px rgba(39,134,194,.28); cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: transform .2s ease, box-shadow .2s ease;
    }
    .dvoice-widget-button:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(39,134,194,.35); }
    .dvoice-widget-button:focus-visible { outline: 3px solid var(--servio-focus, #1a5a8a); outline-offset: 4px; }
    .dvoice-widget-button.has-logo:not(.open) { background: #fff; border-color: var(--servio-frame-border, #dce8f1); }
    .dvoice-widget-logo { display: block; max-width: 38px; max-height: 38px; object-fit: contain; }
    .dvoice-widget-icon { width: 25px; height: 25px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    @media (max-width: 480px) {
      .dvoice-widget-container { bottom: max(12px, env(safe-area-inset-bottom)); }
      .dvoice-widget-container.bottom-right { right: max(12px, env(safe-area-inset-right)); }
      .dvoice-widget-container.bottom-left { left: max(12px, env(safe-area-inset-left)); }
      .dvoice-widget-frame { width: calc(100vw - 24px); height: min(640px, calc(100vh - 100px)); height: min(640px, calc(100dvh - 100px)); bottom: 68px; border-radius: 20px; }
    }
    @media (prefers-reduced-motion: reduce) {
      .dvoice-widget-frame, .dvoice-widget-button { transition: none; }
    }
  `;
  document.head.appendChild(style);

  const container = document.createElement('div');
  container.className = 'dvoice-widget-container ' + position;
  const iframe = document.createElement('iframe');
  iframe.id = frameId;
  iframe.className = 'dvoice-widget-frame';
  iframe.title = 'สนทนากับ Servio';
  iframe.hidden = true;
  iframe.inert = true;
  iframe.tabIndex = -1;
  if (allowToggle || type === 'voice') iframe.allow = 'microphone';

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'dvoice-widget-button';
  button.setAttribute('aria-controls', frameId);
  const chatIcon = '<svg class="dvoice-widget-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/><path d="M8 10h8M8 14h5"/></svg>';
  const closeIcon = '<svg class="dvoice-widget-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6"/></svg>';
  let isOpen = false;
  let launcherLogo = null;
  function renderLauncher() {
    if (isOpen) { button.innerHTML = closeIcon; return; }
    if (launcherLogo) {
      button.textContent = '';
      const img = document.createElement('img');
      img.className = 'dvoice-widget-logo';
      img.alt = '';
      img.src = launcherLogo;
      button.appendChild(img);
      return;
    }
    button.innerHTML = chatIcon;
  }
  // Customer theme (colour, logo). Values are validated before touching the page.
  const HEX = /^#[0-9a-f]{6}$/i;
  function applyTheme(theme) {
    const palette = theme && theme.palette;
    if (!palette) return;
    const vars = { '--servio-primary': palette.primary, '--servio-strong': palette.primary_strong, '--servio-on-primary': palette.on_primary,
      '--servio-focus': palette.accent_text, '--servio-frame-border': palette.frame_border, '--servio-frame-bg': palette.frame_bg };
    for (const name in vars) if (HEX.test(vars[name] || '')) container.style.setProperty(name, vars[name]);
    const logo = theme.launcher_logo && typeof theme.logo_url === 'string' && /^\/api\/public\/widget-logo\/[A-Za-z0-9_-]+\.png$/.test(theme.logo_url) ? theme.logo_url : null;
    launcherLogo = logo ? serverUrl + logo : null;
    button.classList.toggle('has-logo', Boolean(launcherLogo));
    renderLauncher();
  }
  function setOpen(open) {
    isOpen = open;
    if (open && !iframe.getAttribute('src')) iframe.src = url.href;
    iframe.hidden = !open;
    iframe.inert = !open;
    iframe.tabIndex = open ? 0 : -1;
    iframe.classList.toggle('visible', open);
    button.classList.toggle('open', open);
    renderLauncher();
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? 'ปิดหน้าต่างสนทนา' : 'เปิดสนทนากับ Servio');
    button.title = open ? 'ปิดหน้าต่างสนทนา' : 'สนทนากับ Servio';
    if (open) iframe.focus();
    else button.focus();
  }
  button.innerHTML = chatIcon;
  button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-label', 'เปิดสนทนากับ Servio');
  button.title = 'สนทนากับ Servio';
  button.addEventListener('click', () => setOpen(!isOpen));
  document.addEventListener('keydown', event => {
    if (isOpen && event.key === 'Escape') setOpen(false);
  });
  window.addEventListener('message', event => {
    if (isOpen && event.source === iframe.contentWindow && event.origin === serverOrigin && event.data && event.data.type === 'servio.widget.close') setOpen(false);
  });
  container.appendChild(iframe);
  container.appendChild(button);
  document.body.appendChild(container);
  const apiKey = script.getAttribute('data-api-key') || '';
  if (apiKey && typeof fetch === 'function') {
    fetch(serverUrl + '/api/public/widget-theme?api_key=' + encodeURIComponent(apiKey), { credentials: 'omit' })
      .then(response => response.ok ? response.json() : null)
      .then(applyTheme)
      .catch(() => { /* keep the default Servio look */ });
  }
})();
