import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';
const { act, create } = TestRenderer;
const dependency = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}) {
  const filename = path.join(root, file);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })((name) => Object.hasOwn(mocks, name) ? mocks[name] : dependency(name), exports);
  return exports;
}
const { ImageSearchComposer } = load('src/components/ImageSearchComposer.tsx');
const { Composer } = load('src/components/Composer.tsx');
const chatTheme = load('src/lib/chat-theme.ts', { '@/lib/api': { buildApiUrl: (path) => `https://servio.test${path}` } });
async function harness(props = {}, { framed = false, query = {}, saved = null, themeResponse = null } = {}) {
  const previous = { document: globalThis.document, window: globalThis.window, localStorage: globalThis.localStorage, fetch: globalThis.fetch };
  const themeRequests = [];
  globalThis.fetch = async (url) => { themeRequests.push(String(url)); return { ok: Boolean(themeResponse), json: async () => themeResponse }; };
  let modalOpen = false;
  globalThis.document = { querySelector: () => modalOpen ? {} : null };
  const sent = [], inquiries = [], listeners = new Map(), storage = new Map(saved ? [['servio-widget-mode', saved]] : []);
  globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
  globalThis.window = { parent: { postMessage: (...args) => sent.push(args) }, location: { origin: 'https://servio.test' }, setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (id) => clearTimeout(id), addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: (name) => listeners.delete(name) };
  if (!framed) globalThis.window.parent = globalThis.window;
  let socketMounts = 0, audioMounts = 0, audioEnabled, resetCount = 0, socketOptions;
  let reconnects = 0;
  const state = { isReady: true, connection: { kind: 'open' }, reconnect: () => { reconnects++; }, sendAudioMessage() {}, sendTextMessage: (text) => sent.push(text), history: [], resetHistory: () => { resetCount++; }, presentations: {}, sendProductInquiry: (...args) => inquiries.push(['product', ...args]), sendKnowledgeInquiry: (...args) => inquiries.push(['knowledge', ...args]), imageSearchAvailable: true, imageSearchState: { kind: 'idle' }, imageComposerEpoch: 0, sendImageSearch: () => true, productActionError: null, isLoading: false, agentName: 'ฝ่ายบริการ', voiceResponseEnabled: true };
  const { default: WidgetContent } = load('src/components/WidgetContent.tsx', {
    './ChatSurface.module.css': { default: new Proxy({}, { get: (_, key) => String(key) }) },
    'next/image': { default: (props) => React.createElement('img', props) },
    'next/navigation': { useSearchParams: () => new URLSearchParams(query) },
    '@/components/icons/WriteIcon': { default: () => null }, '@/components/icons/MicIcon': { default: () => null },
    '@/lib/chat-theme': chatTheme,
    '@/components/AudioChat': { default: (props) => React.createElement('audio-probe', props) },
    '@/components/Composer': { Composer }, '@/components/ImageSearchComposer': { ImageSearchComposer },
    '@/components/ChatDialog': { ChatHistory: (props) => React.createElement('history-probe', props) },
    '@/hooks/useAudio': { useAudio: ({ enabled }) => { audioEnabled = enabled; React.useEffect(() => { audioMounts++; }, []); return { isReady: true, playAudio() {}, startRecording() {}, stopRecording() {}, frequencies: [] }; } },
    '@/hooks/useWebsocket': { useWebsocket: (options) => { socketOptions = options; React.useEffect(() => { socketMounts++; }, []); return state; } },
  });
  let renderer;
  await act(async () => { renderer = create(React.createElement(WidgetContent, props)); });
  return { setModalOpen: (value) => { modalOpen = value; }, renderer, state, sent, inquiries, listeners, storage,
    field: () => renderer.root.findAllByType('input').find((node) => node.props.type === 'text'),
    update: () => act(async () => renderer.update(React.createElement(WidgetContent, props))),
    button: (label) => renderer.root.findAllByType('button').find((node) => node.props['aria-label'] === label),
    themeRequests, get reconnects() { return reconnects; },
    text: () => JSON.stringify(renderer.toJSON()),
    get socketMounts() { return socketMounts; }, get audioMounts() { return audioMounts; }, get audioEnabled() { return audioEnabled; }, get resetCount() { return resetCount; }, get socketOptions() { return socketOptions; },
    async close() { await act(async () => renderer.unmount()); globalThis.document = previous.document; globalThis.window = previous.window; globalThis.localStorage = previous.localStorage; globalThis.fetch = previous.fetch; },
  };
}

test('page welcome transitions preserve real image/text drafts and one hook instance', async () => {
  const original = { Image: globalThis.Image, create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  globalThis.Image = class { naturalWidth = 10; naturalHeight = 10; set src(_) { this.onload(); } };
  URL.createObjectURL = () => 'blob:customer-photo'; URL.revokeObjectURL = () => {};
  const h = await harness({ variant: 'page', overrideType: 'chat' });
  try {
    assert.equal(h.renderer.root.findByType('section').props['data-variant'], 'page');
    const composer = h.renderer.root.findByType(ImageSearchComposer);
    await act(async () => h.field().props.onChange({ target: { value: 'คำถามที่กำลังพิมพ์' } }));
    await act(async () => h.renderer.root.findAllByType('input').find((node) => node.props.type === 'file').props.onChange({ target: { files: [{ name: 'photo.png', type: 'image/png', size: 100 }], value: 'x' } }));
    for (const next of [{ isLoading: true }, { history: [{ type: 'function_call', call_id: 'tool', name: 'search', arguments: '{}' }], isLoading: false }, { history: [], productActionError: 'ลองอีกครั้ง' }, { productActionError: null }]) {
      Object.assign(h.state, next); await h.update();
      assert.equal(h.renderer.root.findByType(ImageSearchComposer), composer);
      assert.equal(h.field().props.value, 'คำถามที่กำลังพิมพ์');
      assert.equal(h.renderer.root.findAllByType('img').some((node) => node.props.src === 'blob:customer-photo'), true);
      assert.equal(h.renderer.root.findAllByType('h1').length, h.state.history.length === 0 && !h.state.isLoading && !h.state.productActionError ? 1 : 0);
    }
    assert.equal(h.socketMounts, 1); assert.equal(h.audioMounts, 1); assert.equal(h.audioEnabled, false);
  } finally { await h.close(); globalThis.Image = original.Image; URL.createObjectURL = original.create; URL.revokeObjectURL = original.revoke; }
});

test('widget forwards inquiries, loading, readiness, errors, credentials and reset', async () => {
  const h = await harness({ overrideType: 'chat', overrideApiKey: 'override-key' }, { query: { apiKey: 'url-key' } });
  try {
    Object.assign(h.state, { history: [{ type: 'message', role: 'user', content: 'hello' }], isReady: false, isLoading: true, productActionError: 'Unavailable' }); await h.update();
    assert.equal(h.renderer.root.findByType('section').props['data-variant'], 'widget');
    const history = h.renderer.root.findByType('history-probe').props;
    assert.equal(history.messages, h.state.history); assert.equal(history.presentations, h.state.presentations);
    assert.equal(history.isLoading, true); assert.equal(history.productActionsDisabled, true); assert.equal(history.productActionError, 'Unavailable');
    history.onProductInquiry('call-1', 'product-1'); history.onKnowledgeInquiry('message-1', 'card-1');
    assert.deepEqual(h.inquiries, [['product', 'call-1', 'product-1'], ['knowledge', 'message-1', 'card-1']]);
    assert.equal(h.field().props.disabled, true);
    await act(async () => h.button('เริ่มแชตใหม่').props.onClick());
    assert.equal(h.resetCount, 1); assert.equal(h.socketOptions.apiKey, 'override-key');
  } finally { await h.close(); }
});

test('collapse only applies to voice; override, URL and saved mode precedence survive', async () => {
  const h = await harness({ overrideType: 'voice' }, { query: { type: 'chat' }, saved: 'chat' });
  try {
    h.state.history = [{ type: 'message', role: 'assistant', content: 'hello' }]; await h.update();
    assert.equal(h.audioEnabled, true);
    await act(async () => h.button('ซ่อนบทสนทนา').props.onClick());
    assert.equal(h.renderer.root.findByType('history-probe').props.collapsed, true);
    await act(async () => h.button('เปลี่ยนเป็นแชต').props.onClick());
    assert.equal(h.renderer.root.findByType('history-probe').props.collapsed, false);
    assert.equal(h.storage.get('servio-widget-mode'), 'chat'); assert.equal(h.audioEnabled, false);
    h.state.voiceResponseEnabled = false; await h.update(); assert.equal(h.button('เปลี่ยนเป็นเสียง'), undefined);
  } finally { await h.close(); }
  for (const [props, options, enabled] of [[{}, { saved: 'chat' }, false], [{ overrideAllowToggle: false }, { saved: 'chat', query: { allowToggle: 'true' } }, true], [{}, { saved: 'voice', query: { type: 'chat', allowToggle: 'false' } }, false]]) {
    const h = await harness(props, options);
    try { assert.equal(h.audioEnabled, enabled); if (props.overrideAllowToggle === false || options.query?.allowToggle === 'false') assert.equal(h.button(enabled ? 'เปลี่ยนเป็นแชต' : 'เปลี่ยนเป็นเสียง'), undefined); } finally { await h.close(); }
  }
});

test('close button and Escape send minimal close command only from framed widgets', async () => {
  for (const [props, framed, closable] of [[{}, false, false], [{ variant: 'page' }, true, false], [{}, true, true]]) {
    const h = await harness(props, { framed });
    try {
      assert.equal(Boolean(h.button('ปิดแชต')), closable); assert.equal(h.listeners.has('keydown'), closable);
      if (closable) {
        await act(async () => h.button('ปิดแชต').props.onClick());
        h.listeners.get('keydown')({ key: 'Escape', defaultPrevented: false });
        h.listeners.get('keydown')({ key: 'Escape', defaultPrevented: true });
        h.setModalOpen(true);
        h.listeners.get('keydown')({ key: 'Escape', defaultPrevented: false });
        assert.deepEqual(h.sent, [[{ type: 'servio.widget.close' }, '*'], [{ type: 'servio.widget.close' }, '*']]);
      }
    } finally { await h.close(); }
    assert.equal(h.listeners.has('keydown'), false);
  }
});

test('voice controls retain start, recording and end transitions without microphone access', async () => {
  const utils = load('src/components/ui/utils.ts');
  const button = load('src/components/ui/Button.tsx', { '@/components/ui/utils': utils });
  const { default: AudioChat } = load('src/components/AudioChat.tsx', {
    '@/components/ui/utils': utils,
    '@/components/ui/Button': button,
    '@/components/AudioPlayback': { AudioPlayback: () => null },
    ...Object.fromEntries(['PhoneIcon', 'PhoneOffIcon', 'MicIcon'].map((name) => [`@/components/icons/${name}`, { default: () => null }])),
  });
  const sent = [];
  let starts = 0, stops = 0, renderer;
  const audio = new Int16Array([1, 2, 3]);
  await act(async () => { renderer = create(React.createElement(AudioChat, { isReady: true, frequencies: [], startRecording: async () => { starts++; }, stopRecording: async () => { stops++; return audio; }, sendAudioMessage: (value) => sent.push(value) })); });
  const control = (label) => renderer.root.findAllByType('button').find((node) => node.props['aria-label'] === label);
  try {
    await act(async () => control('Start Call').props.onClick());
    await act(async () => control('Hold to speak').props.onMouseDown());
    assert.ok(control('Recording...'));
    await act(async () => control('End Call').props.onClick());
    assert.ok(control('Start Call'));
    assert.equal(starts, 1); assert.equal(stops, 1); assert.deepEqual(sent, [audio]);
  } finally { await act(async () => renderer.unmount()); }
});

const THEME = {
  version: 1, is_default: false, primary_color: '#0f8a5f', logo_url: '/api/public/widget-logo/k1-abcdefghijklmnopqrstuvwx.png', launcher_logo: false,
  greeting: { th: { title: 'ยินดีต้อนรับสู่ร้านเรา', subtitle: '<b>ถามได้</b>ทุกเรื่อง' }, en: {} },
  palette: { primary: '#0f8a5f', primary_strong: '#0c714e', on_primary: '#ffffff', accent_text: '#0d7954', bubble_from: '#0e7f58', bubble_to: '#0d7753', on_bubble: '#ffffff',
    tint_1: '#b7dccf', tint_2: '#c9e6db', tint_3: '#d8ede5', base_1: '#ebf5f1', base_2: '#f0f8f5', base_3: '#e7f3ef', frame_border: '#d8ede5', frame_bg: '#f6fbf9' },
};

test('server rejections show an inline banner instead of a silent disabled composer', async () => {
  const h = await harness({ overrideType: 'chat', theme: null });
  try {
    assert.equal(h.socketOptions.inlineErrors, true);
    Object.assign(h.state, { isReady: false, connection: { kind: 'error', reason: 'auth', message: 'แชตนี้ยังไม่พร้อมใช้งาน กรุณาติดต่อผู้ดูแลเว็บไซต์' } }); await h.update();
    const alert = h.renderer.root.findAll((node) => node.props.role === 'alert')[0];
    assert.ok(alert, 'auth failures are announced');
    assert.match(h.text(), /แชตยังไม่พร้อมใช้งาน/);
    assert.equal(h.renderer.root.findAllByType('button').some((node) => node.props.children === 'ลองอีกครั้ง'), false, 'retrying a bad key cannot help');
    Object.assign(h.state, { connection: { kind: 'error', reason: 'network', message: 'เชื่อมต่อกับผู้ช่วยไม่สำเร็จ' } }); await h.update();
    const retry = h.renderer.root.findAllByType('button').find((node) => node.props.children === 'ลองอีกครั้ง');
    await act(async () => retry.props.onClick());
    assert.equal(h.reconnects, 1);
    Object.assign(h.state, { isReady: true, connection: { kind: 'open' } }); await h.update();
    assert.equal(h.renderer.root.findAll((node) => node.props.role === 'alert').length, 0);
  } finally { await h.close(); }
});

test('header and welcome use distinct icons for chat, restart and the assistant', async () => {
  const h = await harness({ overrideType: 'voice', theme: null });
  try {
    const toggle = h.button('เปลี่ยนเป็นแชต'), restart = h.button('เริ่มแชตใหม่');
    const iconOf = (node) => node.findAll((child) => typeof child.type === 'object' || typeof child.type === 'function')[0]?.type;
    assert.notEqual(iconOf(toggle), iconOf(restart));
  } finally { await h.close(); }
});

test('surface pins light scheme so OS dark mode cannot leak into the widget', async () => {
  const h = await harness({ overrideType: 'voice', theme: null });
  try { assert.equal(h.renderer.root.findByType('section').props['data-color-scheme'], 'light'); } finally { await h.close(); }
});

test('customer theme sets CSS variables, logo and escaped greeting', async () => {
  const h = await harness({ overrideType: 'chat', theme: chatTheme.parseChatTheme(THEME) });
  try {
    const section = h.renderer.root.findByType('section');
    assert.equal(section.props.style['--chat-primary'], '#0f8a5f');
    assert.equal(section.props.style['--chat-on-bubble'], '#ffffff');
    assert.equal(section.props['data-theme-ready'], true);
    assert.equal(h.themeRequests.length, 0, 'a provided theme is not fetched again');
    assert.equal(h.renderer.root.findByType('h1').props.children, 'ยินดีต้อนรับสู่ร้านเรา');
    assert.equal(h.renderer.root.findAllByType('p').some((node) => node.props.children === '<b>ถามได้</b>ทุกเรื่อง'), true);
    assert.equal(h.renderer.root.findAllByType('img').some((node) => node.props.src === 'https://servio.test/api/public/widget-logo/k1-abcdefghijklmnopqrstuvwx.png'), true);
  } finally { await h.close(); }
});

test('embedded widget fetches its theme by key and falls back to Servio defaults', async () => {
  const h = await harness({ overrideType: 'chat' }, { query: { apiKey: 'sk_live key' }, themeResponse: THEME });
  try {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    assert.deepEqual(h.themeRequests, ['https://servio.test/api/public/widget-theme?api_key=sk_live%20key']);
    assert.equal(h.renderer.root.findByType('section').props.style['--chat-primary'], '#0f8a5f');
  } finally { await h.close(); }
  const fallback = await harness({ overrideType: 'chat' }, { query: { apiKey: 'k' }, themeResponse: null });
  try {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    const section = fallback.renderer.root.findByType('section');
    assert.equal(section.props.style, undefined);
    assert.equal(section.props['data-theme-ready'], true);
    assert.equal(fallback.renderer.root.findByType('h1').props.children, 'สวัสดีค่ะ ให้เราช่วยอะไรดีคะ');
  } finally { await fallback.close(); }
});

test('admin preview never opens a socket and only trusts its same-origin parent', async () => {
  const h = await harness({}, { framed: true, query: { preview: '1', type: 'chat' } });
  try {
    assert.equal(h.socketOptions.enabled, false);
    assert.equal(h.button('ปิดแชต'), undefined);
    assert.deepEqual(h.sent.at(-1), [{ type: 'servio.theme.preview.ready' }, 'https://servio.test']);
    const message = h.listeners.get('message');
    await act(async () => message({ source: {}, origin: 'https://evil.test', data: { type: 'servio.theme.preview', theme: THEME } }));
    assert.equal(h.renderer.root.findByType('section').props.style, undefined);
    await act(async () => message({ source: globalThis.window.parent, origin: 'https://servio.test', data: { type: 'servio.theme.preview', theme: THEME, sample: 'conversation' } }));
    assert.equal(h.renderer.root.findByType('section').props.style['--chat-primary'], '#0f8a5f');
    assert.equal(h.renderer.root.findByType('history-probe').props.messages.length, 2);
  } finally { await h.close(); }
});

test('theme parser rejects malformed colours and foreign logo URLs', () => {
  assert.equal(chatTheme.parseChatTheme({ ...THEME, palette: { ...THEME.palette, primary: 'red;background:url(x)' } }), null);
  assert.equal(chatTheme.parseChatTheme({ ...THEME, logo_url: 'https://evil.test/x.png' }).logo_url, null);
  assert.equal(chatTheme.parseChatTheme({ ...THEME, logo_url: '/api/public/widget-logo/../x.png' }).logo_url, null);
  assert.equal(chatTheme.resolveGreeting(null, 'en').title, 'Hi there, how can we help?');
});

