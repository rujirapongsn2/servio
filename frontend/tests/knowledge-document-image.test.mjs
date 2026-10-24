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
const dependencies = createRequire(import.meta.url);
const filename = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src/components/KnowledgeDocumentImage.tsx');
const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const exports = {};
vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })((name) => name === '@/lib/api' ? { getApiBaseUrl: () => 'https://backend.test' } : dependencies(name), exports);
const { KnowledgeDocumentImage } = exports;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const props = { bundleId: 42, conceptId: 'photos/red & white', title: 'Red mug', teamAgentId: 7 };
const response = (type = 'image/png') => ({ ok: true, blob: async () => new Blob(['image'], { type }) });
const button = (renderer, text) => renderer.root.findAllByType('button').find((node) => node.children.includes(text));

async function fixture(run) {
  const original = { fetch: globalThis.fetch, storage: globalThis.localStorage, observer: globalThis.IntersectionObserver, create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  const requests = [];
  const revoked = [];
  let nextId = 0;
  let renderer;
  globalThis.localStorage = { getItem(key) { assert.equal(key, 'adminToken'); return 'admin-secret'; } };
  globalThis.fetch = async (url, options) => { requests.push({ url, options }); return response(); };
  delete globalThis.IntersectionObserver;
  URL.createObjectURL = () => `blob:image-${++nextId}`;
  URL.revokeObjectURL = (url) => revoked.push(url);
  try {
    await run({ requests, revoked, async mount(changes = {}, options = {}) { await act(async () => { renderer = create(React.createElement(KnowledgeDocumentImage, { ...props, ...changes }), options); }); return renderer; } });
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = original.fetch;
    globalThis.localStorage = original.storage;
    if (original.observer === undefined) delete globalThis.IntersectionObserver;
    else globalThis.IntersectionObserver = original.observer;
    URL.createObjectURL = original.create;
    URL.revokeObjectURL = original.revoke;
  }
}

test('original uses authenticated scoped admin endpoint and a blob image', async () => fixture(async ({ mount, requests }) => {
  const renderer = await mount();
  assert.equal(requests.length, 1);
  const url = new URL(requests[0].url);
  assert.equal(url.origin, 'https://backend.test');
  assert.equal(url.pathname, '/api/admin/okf-bundles/42/image');
  assert.equal(url.searchParams.get('concept_id'), props.conceptId);
  assert.equal(url.searchParams.get('team_agent_id'), '7');
  assert.equal(url.searchParams.has('thumbnail'), false);
  assert.equal(url.searchParams.has('token'), false);
  assert.equal(requests[0].options.headers.Authorization, 'Bearer admin-secret');
  assert.equal(renderer.root.findByType('img').props.src, 'blob:image-1');
  assert.equal(renderer.root.findByType('img').props.alt, props.title);
  assert.match(renderer.root.findByType('img').props.className, /50dvh/);
}));

test('thumbnail waits for intersection, is decorative, and has no nested button', async () => fixture(async ({ mount, requests }) => {
  let intersect;
  let disconnected = 0;
  globalThis.IntersectionObserver = class {
    constructor(callback) { intersect = callback; }
    observe() {}
    disconnect() { disconnected++; }
  };
  const renderer = await mount({ thumbnail: true }, { createNodeMock: () => ({}) });
  assert.equal(requests.length, 0);
  assert.equal(renderer.root.findAllByType('button').length, 0);
  await act(async () => intersect([{ isIntersecting: false }]));
  assert.equal(requests.length, 0);
  await act(async () => intersect([{ isIntersecting: true }]));
  assert.equal(requests.length, 1);
  assert.equal(new URL(requests[0].url).searchParams.get('thumbnail'), 'true');
  assert.equal(renderer.root.findByType('img').props.alt, '');
  assert.ok(disconnected > 0);
  await act(async () => renderer.root.findByType('img').props.onError());
  assert.equal(renderer.root.findAllByType('button').length, 0);
}));

test('thumbnail falls back when observers are unavailable and omits absent team scope', async () => fixture(async ({ mount, requests }) => {
  const renderer = await mount({ thumbnail: true, teamAgentId: null });
  assert.equal(requests.length, 1);
  assert.equal(new URL(requests[0].url).searchParams.has('team_agent_id'), false);
  assert.equal(renderer.root.findAllByType('img').length, 1);
}));

test('fetch failure and image decode failure each retry the request', async () => fixture(async ({ mount, revoked }) => {
  let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? { ok: false } : response('image/jpeg');
  const renderer = await mount();
  assert.equal(renderer.root.findAllByType('img').length, 0);
  assert.equal(button(renderer, 'Expand').props.disabled, true);
  await act(async () => button(renderer, 'Retry').props.onClick());
  assert.equal(calls, 2);
  assert.equal(renderer.root.findByType('img').props.src, 'blob:image-1');
  await act(async () => renderer.root.findByType('img').props.onError());
  assert.equal(renderer.root.findAllByType('img').length, 0);
  await act(async () => button(renderer, 'Retry').props.onClick());
  assert.equal(calls, 3);
  assert.deepEqual(revoked, ['blob:image-1']);
  assert.equal(renderer.root.findByType('img').props.src, 'blob:image-2');
}));

test('only PNG and JPEG responses become object URLs', async () => fixture(async ({ mount }) => {
  globalThis.fetch = async () => response('image/svg+xml');
  const renderer = await mount();
  assert.equal(renderer.root.findAllByType('img').length, 0);
  assert.ok(button(renderer, 'Retry'));
}));

test('changing concepts aborts stale requests, hides old images and revokes blobs', async () => fixture(async ({ mount, revoked }) => {
  const renderer = await mount();
  let finish;
  let pendingSignal;
  globalThis.fetch = (_, options) => {
    pendingSignal = options.signal;
    return new Promise((resolve) => { finish = resolve; });
  };
  await act(async () => renderer.update(React.createElement(KnowledgeDocumentImage, { ...props, conceptId: 'pending' })));
  assert.deepEqual(revoked, ['blob:image-1']);
  assert.equal(renderer.root.findAllByType('img').length, 0);
  globalThis.fetch = async () => response();
  await act(async () => renderer.update(React.createElement(KnowledgeDocumentImage, { ...props, conceptId: 'current' })));
  assert.equal(pendingSignal.aborted, true);
  assert.equal(renderer.root.findByType('img').props.src, 'blob:image-2');
  await act(async () => finish(response()));
  assert.equal(renderer.root.findByType('img').props.src, 'blob:image-2');
  await act(async () => renderer.unmount());
  assert.deepEqual(revoked, ['blob:image-1', 'blob:image-2']);
}));

test('native dialog shares original blob, closes on Escape and restores focus', async () => fixture(async ({ mount, requests }) => {
  let opened = 0;
  let closed = 0;
  let focused = 0;
  const renderer = await mount({}, { createNodeMock: (node) => node.type === 'dialog' ? { showModal() { opened++; }, close() { closed++; } } : null });
  await act(async () => button(renderer, 'Expand').props.onClick({ currentTarget: { focus() { focused++; } } }));
  assert.equal(opened, 1);
  const images = renderer.root.findAllByType('img');
  assert.equal(images.length, 2);
  assert.equal(images[0].props.src, images[1].props.src);
  assert.equal(requests.length, 1);
  let prevented = 0;
  let stopped = 0;
  const dialog = renderer.root.findByType('dialog');
  dialog.props.onKeyDown({ key: 'Escape', stopPropagation() { stopped++; } });
  await act(async () => dialog.props.onCancel({ preventDefault() { prevented++; }, stopPropagation() { stopped++; } }));
  assert.equal(prevented, 1);
  assert.equal(stopped, 2);
  assert.equal(closed, 1);
  assert.equal(focused, 1);
  assert.equal(renderer.root.findAllByType('img').length, 1);
}));
