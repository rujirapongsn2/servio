import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../public/embed.js', import.meta.url), 'utf8');
function mount(attributes = {}, { fetch, scriptUrl = 'https://widgets.example/embed.js', delayBody = false } = {}) {
  let focused;
  class Element {
    attributes = new Map(); children = []; handlers = {}; className = ''; contentWindow = {};
    classList = { toggle: (name, enabled) => { const tokens = new Set(this.className.split(' ').filter(Boolean)); if (enabled) tokens.add(name); else tokens.delete(name); this.className = [...tokens].join(' '); } };
    setAttribute(key, value) { this.attributes.set(key, value); }
    getAttribute(key) { return this.attributes.get(key) ?? null; }
    set src(value) { this.setAttribute('src', value); }
    get src() { return this.getAttribute('src'); }
    appendChild(child) { this.children.push(child); }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    focus() { focused = this; }
    style = { values: {}, setProperty(name, value) { this.values[name] = value; } };
    set textContent(value) { this.children = []; this._text = value; }
    get textContent() { return this._text; }
  }
  const script = new Element();
  script.src = scriptUrl;
  for (const [key, value] of Object.entries(attributes)) script.setAttribute(key, value);
  const document = { currentScript: script, baseURI: 'https://shop.example/page', head: new Element(), body: new Element(), handlers: {}, createElement: () => new Element(), addEventListener(name, handler) { this.handlers[name] = handler; } };
  const pendingBody = document.body;
  if (delayBody) document.body = null;
  const window = { handlers: {}, addEventListener(name, handler) { this.handlers[name] = handler; } };
  vm.runInNewContext(source, { document, window, URL, Math, encodeURIComponent, ...(fetch ? { fetch } : {}) });
  if (delayBody) {
    document.currentScript = null;
    document.body = pendingBody;
    document.handlers.DOMContentLoaded();
  }
  const container = document.body.children[0];
  return { document, window, container, frame: container.children[0], button: container.children[1], focus: () => focused };
}

test('closed embed is named, inaccessible and does not initialize a voice iframe', () => {
  const ui = mount();
  assert.equal(ui.frame.src, null);
  assert.equal(ui.frame.hidden, true);
  assert.equal(ui.frame.inert, true);
  assert.equal(ui.frame.tabIndex, -1);
  assert.equal(ui.frame.allow, 'microphone');
  assert.equal(ui.frame.title, 'สนทนากับ Servio');
  assert.equal(ui.button.type, 'button');
  assert.equal(ui.button.getAttribute('aria-expanded'), 'false');
  assert.equal(ui.button.getAttribute('aria-controls'), ui.frame.id);
});
test('opening preserves embed configuration and encodes arbitrary API keys', () => {
  const ui = mount({ 'data-server-url': 'https://chat.example/service/', 'data-position': 'bottom-left', 'data-api-key': 'key&? ก', 'data-type': 'chat', 'data-allow-toggle': 'false' });
  assert.match(ui.container.className, /bottom-left/);
  assert.equal(ui.frame.allow, undefined);
  ui.button.handlers.click();
  const url = new URL(ui.frame.src);
  assert.equal(url.pathname, '/service/widget');
  assert.equal(url.searchParams.get('apiKey'), 'key&? ก');
  assert.equal(url.searchParams.get('type'), 'chat');
  assert.equal(url.searchParams.get('allowToggle'), 'false');
  assert.equal(ui.frame.hidden, false);
  assert.equal(ui.frame.inert, false);
  assert.equal(ui.button.getAttribute('aria-expanded'), 'true');
  assert.equal(ui.focus(), ui.frame);
  const firstUrl = ui.frame.src;
  ui.button.handlers.click();
  assert.equal(ui.frame.hidden, true);
  assert.equal(ui.focus(), ui.button);
  ui.button.handlers.click();
  assert.equal(ui.frame.src, firstUrl);
});
test('Escape closes the panel and restores launcher focus', () => {
  const ui = mount();
  ui.button.handlers.click();
  ui.document.handlers.keydown({ key: 'Escape' });
  assert.equal(ui.frame.hidden, true);
  assert.equal(ui.frame.inert, true);
  assert.equal(ui.button.getAttribute('aria-expanded'), 'false');
  assert.equal(ui.focus(), ui.button);
});
test('only the configured origin and exact iframe may request closing', () => {
  const ui = mount({ 'data-server-url': 'https://chat.example' });
  ui.button.handlers.click();
  for (const event of [
    { source: {}, origin: 'https://chat.example', data: { type: 'servio.widget.close' } },
    { source: ui.frame.contentWindow, origin: 'https://evil.example', data: { type: 'servio.widget.close' } },
    { source: ui.frame.contentWindow, origin: 'https://chat.example', data: { type: 'other' } },
  ]) { ui.window.handlers.message(event); assert.equal(ui.frame.hidden, false); }
  ui.window.handlers.message({ source: ui.frame.contentWindow, origin: 'https://chat.example', data: { type: 'servio.widget.close' } });
  assert.equal(ui.frame.hidden, true);
  assert.equal(ui.focus(), ui.button);
});

const PALETTE = { primary: '#0f8a5f', primary_strong: '#0c714e', on_primary: '#ffffff', accent_text: '#0d7954', frame_border: '#d8ede5', frame_bg: '#f6fbf9' };
async function themed(theme) {
  const requests = [];
  const ui = mount({ 'data-server-url': 'https://chat.example/', 'data-api-key': 'sk key' }, { fetch: async (url, init) => { requests.push([url, init]); return { ok: true, json: async () => theme }; } });
  await new Promise((resolve) => setTimeout(resolve, 0));
  return { ui, requests };
}
test('launcher fetches the key theme without credentials and applies validated colours', async () => {
  const { ui, requests } = await themed({ palette: { ...PALETTE, frame_bg: 'url(javascript:x)' }, launcher_logo: false, logo_url: null });
  assert.equal(requests[0][0], 'https://chat.example/api/public/widget-theme?api_key=sk%20key');
  assert.equal(requests[0][1].credentials, 'omit');
  assert.equal(ui.container.style.values['--servio-primary'], '#0f8a5f');
  assert.equal(ui.container.style.values['--servio-on-primary'], '#ffffff');
  assert.equal(ui.container.style.values['--servio-frame-bg'], undefined, 'non-hex values are ignored');
  assert.match(ui.button.innerHTML, /dvoice-widget-icon/);
});
test('launcher shows the customer logo only for same-server logo URLs', async () => {
  const { ui } = await themed({ palette: PALETTE, launcher_logo: true, logo_url: '/api/public/widget-logo/k1-abcdefghijklmnopqrstuv.png' });
  assert.match(ui.button.className, /has-logo/);
  assert.equal(ui.button.children[0].src, 'https://chat.example/api/public/widget-logo/k1-abcdefghijklmnopqrstuv.png');
  ui.button.handlers.click();
  assert.match(ui.button.innerHTML, /m6 6 12 12/, 'open state still shows the close icon');
  const foreign = await themed({ palette: PALETTE, launcher_logo: true, logo_url: 'https://evil.example/x.png' });
  assert.doesNotMatch(foreign.ui.button.className, /has-logo/);
});
test('no API key means no theme request', () => {
  let called = false;
  mount({}, { fetch: async () => { called = true; } });
  assert.equal(called, false);
});

test('without an override, iframe, theme and logo use the script origin across sites', async () => {
  const requests = [];
  const ui = mount({ 'data-api-key': 'fake-channel-only', 'data-type': 'chat' }, {
    scriptUrl: 'https://servio.example/embed.js?revision=2',
    fetch: async (url, init) => { requests.push({ url, init }); return { ok: true, json: async () => ({ palette: PALETTE, launcher_logo: true, logo_url: '/api/public/widget-logo/fake-logo.png' }) }; },
  });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(requests[0].url, 'https://servio.example/api/public/widget-theme?api_key=fake-channel-only');
  assert.equal(ui.button.children[0].src, 'https://servio.example/api/public/widget-logo/fake-logo.png');
  ui.button.handlers.click();
  assert.equal(new URL(ui.frame.src).origin, 'https://servio.example');
  assert.doesNotMatch(ui.frame.src, /shop\.example|localhost/);
});

test('explicit server URL wins over script and embedding page origins for all requests', async () => {
  const requests = [];
  const ui = mount({ 'data-server-url': ' https://override.example/service/// ', 'data-api-key': 'fake-only' }, {
    scriptUrl: 'https://cdn.example/embed.js', fetch: async url => { requests.push(url); return { ok: true, json: async () => ({ palette: PALETTE, launcher_logo: true, logo_url: '/api/public/widget-logo/fake-logo.png' }) }; },
  });
  await new Promise(resolve => setTimeout(resolve, 0));
  ui.button.handlers.click();
  assert.equal(new URL(ui.frame.src).pathname, '/service/widget');
  assert.equal(requests[0], 'https://override.example/service/api/public/widget-theme?api_key=fake-only');
  assert.equal(ui.button.children[0].src, 'https://override.example/service/api/public/widget-logo/fake-logo.png');
  assert.match(ui.button.innerHTML, /m6 6 12 12/);
});

test('legacy script URL and async head placement still retain the actual script origin', () => {
  for (const scriptUrl of ['https://servio.example/widget.js', '//servio.example/embed.js']) {
    const ui = mount({ 'data-type': 'chat' }, { scriptUrl, delayBody: true });
    ui.button.handlers.click();
    assert.equal(new URL(ui.frame.src).origin, 'https://servio.example');
  }
});
