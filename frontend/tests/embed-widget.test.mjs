import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../public/embed.js', import.meta.url), 'utf8');
function mount(attributes = {}) {
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
  }
  const script = new Element();
  for (const [key, value] of Object.entries(attributes)) script.setAttribute(key, value);
  const document = { currentScript: script, baseURI: 'https://shop.example/page', head: new Element(), body: new Element(), handlers: {}, createElement: () => new Element(), addEventListener(name, handler) { this.handlers[name] = handler; } };
  const window = { handlers: {}, addEventListener(name, handler) { this.handlers[name] = handler; } };
  vm.runInNewContext(source, { document, window, URL, Math });
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
