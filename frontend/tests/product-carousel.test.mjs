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
const requireDependency = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}) {
  const filename = path.join(root, file);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  const require = (name) => Object.hasOwn(mocks, name) ? mocks[name] : requireDependency(name);
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })(require, exports);
  return exports;
}
const parsing = load('src/lib/product-presentations.ts');
const envelope = { type: 'product_carousel', version: 1, summary: 'พบสินค้า 2 รายการ', products: [
  { id: 'sku-a', title: 'หัวเทียน', part_number: '9807B', brand: 'HONDA', description: 'รายละเอียดจริงจาก catalog', image_url: 'https://example.com/broken.png' },
  { id: 'sku-b', title: 'กรองอากาศ', price_text: '250 บาท' },
] };

test('validates source envelope and rejects unsafe or ambiguous cards', () => {
  assert.equal(parsing.parseProductCarousel(envelope).products[0].part_number, '9807B');
  for (const input of [null, { data: envelope }, { ...envelope, version: true }, { ...envelope, products: [] }, { ...envelope, products: [envelope.products[0], envelope.products[0]] }]) {
    assert.equal(parsing.parseProductCarousel(input), null);
  }
  for (const url of ['http://example.com/x', 'javascript:alert(1)', 'https://127.0.0.1/x', 'https://10.0.0.1/x', 'https://192.0.2.1/x', 'https://localhost./x', 'https://user:pass@example.com/x', 'https://example.com/\\x']) {
    assert.equal(parsing.parseProductCarousel({ ...envelope, products: [{ id: 'a', title: 'x', image_url: url }] }), null, url);
  }
  assert.deepEqual(Object.keys(parsing.parseProductPresentations({ valid: envelope, invalid: { products: [] } })), ['valid']);
});

test('renders source cards, image fallback, details and selected product action', async () => {
  const { ProductCarousel } = load('src/components/ProductCarousel.tsx', { '@/lib/product-presentations': parsing, '@/lib/api': { buildApiUrl: (value) => value } });
  let opened = 0;
  const inquiries = [];
  let renderer;
  await act(async () => { renderer = create(React.createElement(ProductCarousel, { presentation: envelope, disabled: false, onInquire: (id) => inquiries.push(id) }), { createNodeMock: (element) => element.type === 'dialog' ? { showModal() { opened++; }, close() {} } : null }); });
  assert.equal(renderer.root.findAllByType('article').length, 2);
  await act(async () => renderer.root.findByType('img').props.onError());
  assert.equal(renderer.root.findAllByType('img').length, 0);
  const details = renderer.root.findAllByType('button').find((node) => node.props['aria-label'] === 'ดูรายละเอียด หัวเทียน');
  await act(async () => details.props.onClick({ currentTarget: { focus() {} } }));
  assert.equal(opened, 1);
  let focused = '';
  let prevented = 0;
  const first = { focus() { focused = 'first'; } };
  const last = { focus() { focused = 'last'; } };
  const modal = { querySelectorAll: () => [first, last], ownerDocument: { activeElement: last } };
  renderer.root.findByType('dialog').props.onKeyDown({ key: 'Tab', shiftKey: false, currentTarget: modal, preventDefault() { prevented++; } });
  assert.equal(focused, 'first');
  modal.ownerDocument.activeElement = first;
  renderer.root.findByType('dialog').props.onKeyDown({ key: 'Tab', shiftKey: true, currentTarget: modal, preventDefault() { prevented++; } });
  assert.equal(focused, 'last');
  assert.equal(prevented, 2);
  assert.ok(JSON.stringify(renderer.toJSON()).includes('รายละเอียดจริงจาก catalog'));
  const inquiry = renderer.root.findAllByType('button').find((node) => node.props['aria-label'] === 'สอบถามสินค้านี้ กรองอากาศ');
  await act(async () => inquiry.props.onClick());
  assert.deepEqual(inquiries, ['sku-b']);
  await act(async () => renderer.update(React.createElement(ProductCarousel, { presentation: envelope, disabled: true, onInquire() {} })));
  assert.ok(renderer.root.findAllByType('button').filter((node) => node.props['aria-label']?.startsWith('สอบถาม')).every((node) => node.props.disabled));
  await act(async () => renderer.unmount());
});

test('WebSocket sidecars persist across snapshots, actions send IDs only and reset clears state', async () => {
  const original = globalThis.WebSocket;
  const sockets = [];
  class Socket {
    static OPEN = 1;
    readyState = 1;
    handlers = {};
    sent = [];
    constructor(url) { this.url = url; sockets.push(this); }
    addEventListener(name, callback) { this.handlers[name] = callback; }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() {}
    emit(data) { this.handlers.message({ data: JSON.stringify(data) }); }
  }
  globalThis.WebSocket = Socket;
  try {
    const { useWebsocket } = load('src/hooks/useWebsocket.ts', {
      '@/lib/product-presentations': parsing,
      '@/lib/types': {},
      '@/lib/utils': {},
      '@/lib/api': { getWebsocketBaseUrl: () => 'ws://test/ws' },
    });
    let state;
    function Probe({ url = 'ws://test/ws' }) { state = useWebsocket({ url }); return null; }
    let renderer;
    await act(async () => { renderer = create(React.createElement(Probe)); });
    const socket = sockets[0];
    await act(async () => socket.handlers.open());
    const inputs = [{ type: 'function_call_output', call_id: 'call-a', output: JSON.stringify(envelope) }];
    await act(async () => socket.emit({ type: 'history.updated', reason: 'response.done', inputs, presentations: { 'call-a': envelope } }));
    assert.equal(state.presentations['call-a'].products.length, 2);
    assert.deepEqual(state.history, inputs);
    await act(async () => state.sendProductInquiry('call-a', 'sku-a'));
    assert.deepEqual(socket.sent.at(-1), { type: 'product.inquire', call_id: 'call-a', product_id: 'sku-a' });
    assert.equal(state.isLoading, true);
    await act(async () => socket.emit({ type: 'product.action.error', message: 'stale selection' }));
    assert.equal(state.isLoading, false);
    assert.equal(state.productActionError, 'stale selection');
    for (const reason of ['assistant.message', 'admin.message']) {
      await act(async () => state.sendProductInquiry('call-a', 'sku-a'));
      assert.equal(state.isLoading, true);
      await act(async () => socket.emit({ type: 'history.updated', reason, inputs, presentations: { 'call-a': envelope } }));
      assert.equal(state.isLoading, false);
      assert.equal(state.presentations['call-a'].products.length, 2);
    }
    await act(async () => state.sendProductInquiry('call-a', 'sku-a'));
    assert.equal(state.isLoading, true);
    await act(async () => renderer.update(React.createElement(Probe, { url: 'ws://other/ws' })));
    const replacement = sockets.at(-1);
    await act(async () => replacement.handlers.open());
    assert.equal(state.isLoading, false);
    assert.equal(state.agentName, null);
    assert.equal(Object.keys(state.presentations).length, 0);
    await act(async () => state.sendTextMessage('New channel question'));
    assert.equal(replacement.sent.at(-1).inputs.at(-1).content, 'New channel question');
    await act(async () => state.resetHistory());
    assert.equal(Object.keys(state.presentations).length, 0);
    assert.equal(state.productActionError, null);
    assert.deepEqual(replacement.sent.at(-1).inputs, []);
    await act(async () => renderer.unmount());
  } finally { globalThis.WebSocket = original; }
});


test('product search keeps extra model text collapsed and selected-product reply readable', async () => {
  const { ChatHistory } = load('src/components/ChatDialog.tsx', {
  '@/lib/chat-flow': load('src/lib/chat-flow.ts', {}),
    '@/components/KnowledgeAudio': load('src/components/KnowledgeAudio.tsx', { '@/lib/api': { buildApiUrl: (value) => value } }),
    '@/components/KnowledgeImages': { KnowledgeImages: () => null },
    clsx: { default: (...values) => values.filter((value) => typeof value === 'string').join(' ') },
    '@/components/ChatLoadingDots': { default: () => null },
    '@/components/MessageBubble': { MessageBubble: ({ message }) => React.createElement('p', null, message.content) },
    '@/components/ProductCarousel': { ProductCarousel: () => React.createElement('section', null, 'Product cards') },
    '@/lib/types': {},
    '@/lib/product-presentations': parsing,
  });
  const messages = [
    { type: 'message', role: 'user', content: 'Search products' },
    { type: 'function_call_output', call_id: 'call-a', output: JSON.stringify(envelope) },
    { type: 'message', role: 'assistant', content: 'Extra product list text' },
    { type: 'message', role: 'user', content: 'Ask about sku-a' },
    { type: 'message', role: 'assistant', content: 'Selected product answer' },
  ];
  let renderer;
  await act(async () => { renderer = create(React.createElement(ChatHistory, { messages, isLoading: false, presentations: { 'call-a': envelope } })); });
  const extra = renderer.root.findByType('details');
  assert.ok(!extra.props.open);
  assert.ok(JSON.stringify(extra.toJSON?.() ?? extra.findByType('p').children).includes('Extra product list text'));
  const reply = renderer.root.findAllByType('p').find((node) => node.children.includes('Selected product answer'));
  assert.ok(reply);
  assert.ok(!extra.findAllByType('p').some((node) => node.children.includes('Selected product answer')));
  await act(async () => renderer.unmount());
});

const imageEnvelope = { type: 'knowledge_images', version: 1, response: 'Related visual sources', images: [{ asset_id: 'a'.repeat(64), title: 'ต้นฉบับ', source_label: 'reference.png', image_url: `/api/knowledge-images/${'a'.repeat(64)}?token=header.payload.signature` }] };
test('accepts signed local image references and rejects foreign or ambiguous image URLs', () => {
  assert.equal(parsing.parseKnowledgeImages(imageEnvelope).images.length, 1);
  assert.equal(parsing.parseProductPresentations({ images: imageEnvelope }).images.type, 'knowledge_images');
  for (const url of ['https://example.com/image.png', '//evil.test/image', '/api/knowledge-images/' + 'b'.repeat(64) + '?token=x', imageEnvelope.images[0].image_url + '&admin_key=secret']) {
    assert.equal(parsing.parseKnowledgeImages({ ...imageEnvelope, images: [{ ...imageEnvelope.images[0], image_url: url }] }), null);
  }
});
test('image results retain a visible assistant answer and have no product inquiry action', async () => {
  const { ChatHistory } = load('src/components/ChatDialog.tsx', {
  '@/lib/chat-flow': load('src/lib/chat-flow.ts', {}),
    clsx: { default: (...values) => values.filter((value) => typeof value === 'string').join(' ') },
    '@/components/KnowledgeAudio': load('src/components/KnowledgeAudio.tsx', { '@/lib/api': { buildApiUrl: (value) => value } }),
    '@/components/KnowledgeImages': { KnowledgeImages: ({ images }) => React.createElement('section', { 'aria-label': 'image-results' }, images[0].title) },
    '@/components/ProductCarousel': { ProductCarousel: () => null },
    '@/components/ChatLoadingDots': { default: () => null },
    '@/components/MessageBubble': { MessageBubble: () => React.createElement('div', null, 'visible-answer') },
  });
  let renderer;
  await act(async () => { renderer = create(React.createElement(ChatHistory, { messages: [{ type: 'function_call_output', call_id: 'images', output: '{}' }, { type: 'message', role: 'assistant', content: [] }], isLoading: false, presentations: { images: imageEnvelope } })); });
  assert.equal(renderer.root.findAllByType('details').length, 0);
  assert.equal(renderer.root.findAllByType('button').length, 0);
  assert.equal(renderer.root.findAllByType('section').length, 1);
  assert.match(JSON.stringify(renderer.toJSON()), /visible-answer/);
  await act(async () => renderer.unmount());
});

test('image originals report expired links and empty sources render nothing', async () => {
  const { KnowledgeImages } = load('src/components/KnowledgeImages.tsx', { '@/lib/api': { buildApiUrl: (value) => value } });
  let renderer;
  await act(async () => { renderer = create(React.createElement(KnowledgeImages, { images: [] })); });
  assert.equal(renderer.toJSON(), null);
  const image = { asset_id: 'a'.repeat(64), title: 'Source', source_label: 'source.png', image_url: '/api/knowledge-images/source?token=test' };
  await act(async () => { renderer.update(React.createElement(KnowledgeImages, { images: [image] })); });
  const trigger = renderer.root.findAllByType('button')[0];
  await act(async () => trigger.props.onClick({ currentTarget: { focus() {} } }));
  const original = renderer.root.findByType('dialog').findByType('img');
  await act(async () => original.props.onError());
  assert.match(JSON.stringify(renderer.toJSON()), /ภาพหมดอายุ กรุณาค้นหาใหม่/);
  assert.equal(renderer.root.findByType('dialog').findAllByType('img').length, 0);
  await act(async () => renderer.unmount());
});

test('Knowledge test modal displays validated source images from query results', async () => {
  const previousFetch = globalThis.fetch;
  const previousStorage = globalThis.localStorage;
  globalThis.localStorage = { getItem: () => 'disposable-test-token' };
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ response: 'Matched image', response_time: .1, concepts: [], images: imageEnvelope.images }) });
  const { KnowledgeImages } = load('src/components/KnowledgeImages.tsx', { '@/lib/api': { buildApiUrl: (value) => value } });
  const { default: TestKnowledge } = load('src/components/TestOKFBundleModal.tsx', {
    '@/lib/api': { getApiBaseUrl: () => 'http://localhost' },
    '@/components/KnowledgeAudio': load('src/components/KnowledgeAudio.tsx', { '@/lib/api': { buildApiUrl: (value) => value } }),
    '@/components/KnowledgeImages': { KnowledgeImages },
    '@/lib/product-presentations': parsing,
  });
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(TestKnowledge, { tool: { id: 1, name: 'Images', config: JSON.stringify({ okf_bundle_id: 1 }) }, teamAgentId: 1, onClose() {} })); });
    await act(async () => renderer.root.findByType('textarea').props.onChange({ target: { value: 'red circle' } }));
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(renderer.root.findAllByType('article').length, 1);
    assert.equal(renderer.root.findByType('img').props.alt, imageEnvelope.images[0].title);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = previousFetch;
    globalThis.localStorage = previousStorage;
  }
});
