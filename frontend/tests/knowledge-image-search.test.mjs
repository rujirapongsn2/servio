import { localModule } from './helpers/local-module.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';

const { act, create } = TestRenderer;
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}) {
  const filename = path.join(root, file);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  const require = (name) => Object.hasOwn(mocks, name) ? mocks[name] : localModule(name);
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })(require, exports);
  return exports;
}
const parsing = load('src/lib/product-presentations.ts');
const card = { id: 'a'.repeat(32), asset_id: 'b'.repeat(64), title: 'Red mug', part_number: 'RM1', brand: 'Acme', source_label: 'mug.png', description: 'Verified product description', image_url: `/api/knowledge-images/${'b'.repeat(64)}?token=signed.token` };
const carousel = { type: 'knowledge_product_carousel', version: 1, summary: 'Found one product', products: [card] };

test('knowledge carousel validates signed sources without relaxing external product URLs', () => {
  assert.equal(parsing.parseKnowledgeProductCarousel(carousel).products[0].description, card.description);
  assert.equal(parsing.parseKnowledgeProductCarousel(carousel).products[0].part_number, 'RM1');
  assert.equal(parsing.parseProductPresentations({ message: carousel }).message.type, carousel.type);
  for (const changed of [{ ...card, id: 'sku' }, { ...card, price_text: 'FREE' }, { ...card, image_url: 'https://example.com/image' }, { ...card, asset_id: 'c'.repeat(64) }]) {
    assert.equal(parsing.parseKnowledgeProductCarousel({ ...carousel, products: [changed] }), null);
  }
  assert.equal(parsing.parseKnowledgeProductCarousel({ ...carousel, products: [card, card] }), null);
  assert.equal(parsing.parseProductCarousel({ type: 'product_carousel', version: 1, summary: 'Found', products: [{ id: card.id, title: card.title, image_url: card.image_url }] }), null);
});

test('knowledge cards show source and details, resolve signed images and send only opaque ID', async () => {
  const { ProductCarousel } = load('src/components/ProductCarousel.tsx', { '@/lib/product-presentations': parsing, '@/lib/api': { buildApiUrl: (value) => 'http://backend.test' + value } });
  const selected = [];
  let renderer;
  await act(async () => { renderer = create(React.createElement(ProductCarousel, { presentation: carousel, disabled: false, onInquire: (id) => selected.push(id) }), { createNodeMock: (element) => element.type === 'dialog' ? { showModal() {}, close() {} } : null }); });
  assert.equal(renderer.root.findByType('img').props.src, 'http://backend.test' + card.image_url);
  assert.doesNotMatch(JSON.stringify(renderer.toJSON()), /mug.png/);
  assert.match(JSON.stringify(renderer.toJSON()), /RM1/);
  assert.doesNotMatch(JSON.stringify(renderer.toJSON()), /รหัสสินค้า/);
  await act(async () => renderer.root.findAllByType('button').find((button) => button.props['aria-label']?.startsWith('ดูรายละเอียด')).props.onClick({ currentTarget: { focus() {} } }));
  assert.match(JSON.stringify(renderer.toJSON()), /Verified product description/);
  assert.match(JSON.stringify(renderer.toJSON()), /mug.png/);
  await act(async () => renderer.root.findAllByType('button').find((button) => button.props['aria-label']?.startsWith('สอบถามสินค้านี้')).props.onClick());
  assert.deepEqual(selected, [card.id]);
  await act(async () => renderer.unmount());
});

test('search socket requests are bounded to one pending image and ignore reset/disconnect stale results', async () => {
  const original = globalThis.WebSocket;
  const sockets = [];
  class Socket {
    static OPEN = 1;
    readyState = 1;
    handlers = {};
    sent = [];
    constructor() { sockets.push(this); }
    addEventListener(name, callback) { this.handlers[name] = callback; }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() {}
    emit(value) { this.handlers.message({ data: JSON.stringify(value) }); }
  }
  globalThis.WebSocket = Socket;
  try {
    const { useWebsocket } = load('src/hooks/useWebsocket.ts', { '@/lib/product-presentations': parsing, '@/lib/types': {}, '@/lib/utils': {}, '@/lib/api': { getWebsocketBaseUrl: () => 'ws://test/ws' } });
    let state;
    function Probe() { state = useWebsocket(); return null; }
    let renderer;
    await act(async () => { renderer = create(React.createElement(Probe)); });
    const socket = sockets[0];
    await act(async () => { socket.handlers.open(); socket.emit({ type: 'session.config', knowledge_image_search_enabled: true }); });
    assert.equal(state.imageSearchAvailable, true);
    const beforeInvalid = socket.sent.length;
    await act(async () => assert.equal(state.sendImageSearch({ mime: 'image/png', base64: 'YWJj' }, 'x'.repeat(2001)), false));
    assert.equal(socket.sent.length, beforeInvalid);
    const send = socket.send;
    socket.send = () => { throw new Error('closed during send'); };
    await act(async () => assert.equal(state.sendImageSearch({ mime: 'image/png', base64: 'YWJj' }, 'Retry query'), false));
    assert.equal(state.imageSearchState.kind, 'error');
    assert.equal(state.isLoading, false);
    socket.send = send;
    await act(async () => { assert.equal(state.sendImageSearch({ mime: 'image/png', base64: 'YWJj' }, '  red mug  '), true); assert.equal(state.sendImageSearch({ mime: 'image/png', base64: 'YWJj' }), false); });
    const command = socket.sent.at(-1);
    assert.deepEqual(command, { type: 'knowledge.image.search', request_id: command.request_id, image: { mime: 'image/png', base64: 'YWJj' }, query: 'red mug' });
    assert.deepEqual(state.history, []);
    await act(async () => socket.emit({ type: 'knowledge.image.error', request_id: command.request_id, code: 'unavailable', message: 'Retry search', retryable: true }));
    assert.equal(state.imageSearchState.kind, 'error');
    assert.equal(state.isLoading, false);
    await act(async () => state.sendImageSearch({ mime: 'image/png', base64: 'YWJj' }));
    const active = socket.sent.at(-1);
    assert.equal(Object.hasOwn(active, 'query'), false);
    assert.notEqual(active.request_id, command.request_id);
    await act(async () => socket.emit({ type: 'history.updated', reason: 'knowledge.image.result', request_id: active.request_id, inputs: [{ type: 'message', role: 'assistant', id: 'msg_' + '1'.repeat(32), content: carousel.summary }], presentations: { ['msg_' + '1'.repeat(32)]: carousel } }));
    await act(async () => socket.emit({ type: 'knowledge.image.result', request_id: active.request_id, status: 'matched' }));
    assert.equal(state.imageSearchState.kind, 'complete');
    assert.equal(state.history.length, 1);
    await act(async () => state.sendKnowledgeInquiry('msg_' + '1'.repeat(32), card.id));
    assert.deepEqual(socket.sent.at(-1), { type: 'knowledge.product.inquire', message_id: 'msg_' + '1'.repeat(32), card_id: card.id });
    await act(async () => state.resetHistory());
    assert.deepEqual(state.history, []);
    await act(async () => socket.emit({ type: 'history.updated', reason: 'knowledge.image.result', request_id: active.request_id, inputs: [{ role: 'assistant', content: 'stale' }], presentations: {} }));
    assert.deepEqual(state.history, []);
    await act(async () => state.sendImageSearch({ mime: 'image/png', base64: 'YWJj' }));
    const disconnected = socket.sent.at(-1);
    await act(async () => socket.handlers.close());
    assert.equal(state.imageSearchState.kind, 'error');
    await act(async () => socket.emit({ type: 'knowledge.image.result', request_id: disconnected.request_id, status: 'matched' }));
    assert.equal(state.imageSearchState.kind, 'error');
    await act(async () => renderer.unmount());
  } finally { globalThis.WebSocket = original; }
});

test('composer accepts optional image query, retains rejected/failed drafts and clears accepted text once', async () => {
  const original = { Image: globalThis.Image, FileReader: globalThis.FileReader, create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  let revoked = [];
  globalThis.Image = class { naturalWidth = 10; naturalHeight = 10; set src(_) { this.onload(); } };
  globalThis.FileReader = class { result = 'data:image/png;base64,cGljdHVyZQ=='; readAsDataURL() { this.onload(); } };
  URL.createObjectURL = (file) => 'blob:' + file.name;
  URL.revokeObjectURL = (value) => revoked.push(value);
  try {
    const { ImageSearchComposer } = load('src/components/ImageSearchComposer.tsx');
    const sent = [];
    const text = [];
    let accepted = false;
    const props = { available: true, disabled: false, searchState: { kind: 'idle' }, onImageSearch: (image, query) => { sent.push({ image, query }); return accepted; }, onTextMessage: (value) => text.push(value) };
    let renderer;
    await act(async () => { renderer = create(React.createElement(ImageSearchComposer, props)); });
    const field = () => renderer.root.findAllByType('input').find((input) => input.props.type === 'text');
    const picker = () => renderer.root.findAllByType('input').find((input) => input.props.type === 'file');
    await act(async () => field().props.onChange({ target: { value: 'Keep this question' } }));
    await act(async () => picker().props.onChange({ target: { files: [{ name: 'first.png', type: 'image/png', size: 120 }], value: 'x' } }));
    assert.equal(field().props.disabled, false);
    assert.equal(field().props.maxLength, 2000);
    await act(async () => field().props.onChange({ target: { value: '  Keep this question  ' } }));
    assert.equal(renderer.root.findByType('img').props.src, 'blob:first.png');
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.deepEqual(sent, [{ image: { mime: 'image/png', base64: 'cGljdHVyZQ==' }, query: 'Keep this question' }]);
    assert.equal(field().props.value, '  Keep this question  ');
    assert.equal(renderer.root.findAllByType('img').length, 1);
    accepted = true;
    await act(async () => {
      renderer.root.findByType('form').props.onSubmit({ preventDefault() {} });
      renderer.root.findByType('form').props.onSubmit({ preventDefault() {} });
    });
    assert.equal(sent.length, 2);
    assert.equal(field().props.value, '');
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(sent.length, 2);
    assert.deepEqual(text, []);
    await act(async () => renderer.update(React.createElement(ImageSearchComposer, { ...props, searchState: { kind: 'error', message: 'Service unavailable', retryable: true } })));
    assert.equal(renderer.root.findAllByType('img').length, 1);
    assert.match(JSON.stringify(renderer.toJSON()), /Service unavailable/);
    assert.equal(field().props.value, 'Keep this question');
    assert.equal(field().props.disabled, false);
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(sent.at(-1).query, 'Keep this question');
    assert.equal(field().props.value, '');
    await act(async () => renderer.update(React.createElement(ImageSearchComposer, { ...props, disabled: true, searchState: { kind: 'error', message: 'Disconnected', retryable: true } })));
    assert.equal(field().props.value, 'Keep this question');
    assert.equal(renderer.root.findByType('img').props.src, 'blob:first.png');
    await act(async () => renderer.update(React.createElement(ImageSearchComposer, { ...props, searchState: { kind: 'error', message: 'Disconnected', retryable: true } })));
    await act(async () => picker().props.onChange({ target: { files: [{ name: 'second.png', type: 'image/png', size: 120 }], value: 'x' } }));
    assert.ok(revoked.includes('blob:first.png'));
    assert.equal(renderer.root.findByType('img').props.src, 'blob:second.png');
    await act(async () => renderer.root.findAllByType('button').find((button) => button.props['aria-label'] === 'นำรูปภาพออก').props.onClick());
    assert.equal(renderer.root.findAllByType('img').length, 0);
    assert.equal(field().props.value, 'Keep this question');
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.deepEqual(text, ['Keep this question']);
    await act(async () => picker().props.onChange({ target: { files: [{ name: 'bad.gif', type: 'image/gif', size: 120 }], value: 'x' } }));
    assert.equal(renderer.root.findAllByType('img').length, 0);
    assert.match(JSON.stringify(renderer.toJSON()), /10 MB/);
    await act(async () => picker().props.onChange({ target: { files: [{ name: 'last.png', type: 'image/png', size: 120 }], value: 'x' } }));
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(sent.at(-1).query, '');
    await act(async () => field().props.onChange({ target: { value: 'New follow-up' } }));
    await act(async () => renderer.update(React.createElement(ImageSearchComposer, { ...props, searchState: { kind: 'complete', status: 'matched' } })));
    assert.equal(field().props.value, 'New follow-up');
    assert.equal(renderer.root.findAllByType('img').length, 0);
    await act(async () => renderer.unmount());
    assert.ok(revoked.includes('blob:last.png'));
  } finally { globalThis.Image = original.Image; globalThis.FileReader = original.FileReader; URL.createObjectURL = original.create; URL.revokeObjectURL = original.revoke; }
});
