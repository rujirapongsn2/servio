import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { File } from 'node:buffer';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import { renderToString } from 'react-dom/server';
import ts from 'typescript';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencies = createRequire(import.meta.url);
function load(file, mocks = {}) {
  const filename = path.join(root, file);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })((name) => Object.hasOwn(mocks, name) ? mocks[name] : dependencies(name), exports);
  return exports;
}
const helpers = load('src/lib/knowledge-import.ts');
const portalHosts = [];
const { default: Modal } = load('src/components/CreateOKFBundleModal.tsx', { '@/lib/api': { getApiBaseUrl: () => '' }, '@/lib/knowledge-import': helpers, 'react-dom': { createPortal(children, host) { portalHosts.push(host); return children; } } });
const ready = { documents: { status: 'ready' }, images: { status: 'ready' }, audio: { status: 'ready' }, image_ocr: { status: 'not_configured' } };
const response = (body, ok = true) => ({ ok, json: async () => body });
const props = { teamAgentId: 1, onClose() {}, onSuccess() {} };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.localStorage = { getItem: () => 'token' };
globalThis.document = { body: { style: { overflow: '' } } };
function text(node) { const flatten = (value) => typeof value === 'string' ? value : Array.isArray(value) ? value.map(flatten).join('') : value && typeof value === 'object' ? flatten(value.children) : ''; return flatten(node.toJSON()); }
function button(renderer, label) { return renderer.root.findAllByType('button').find((item) => item.children.some((child) => child === label)); }
async function create(fetcher = async () => response(ready)) {
  globalThis.fetch = fetcher;
  let renderer;
  await TestRenderer.act(async () => { renderer = TestRenderer.create(React.createElement(Modal, props)); });
  return renderer;
}
async function pick(renderer, label, files) {
  await TestRenderer.act(async () => renderer.root.findByProps({ 'aria-label': label }).props.onChange({ target: { files }, currentTarget: { value: 'selected' } }));
}

test('modal portals to the body, exposes its dialog name and restores prior body scrolling', async () => {
  const body = globalThis.document.body;
  body.style.overflow = 'scroll';
  portalHosts.length = 0;
  const renderer = await create();
  try {
    assert.ok(portalHosts.length > 0, 'modal content must leave the admin content stacking context');
    assert.ok(portalHosts.every((host) => host === body));
    assert.equal(body.style.overflow, 'hidden');
    const dialog = renderer.root.findByProps({ role: 'dialog' });
    assert.equal(dialog.props['aria-modal'], true);
    const heading = renderer.root.findByType('h2');
    assert.equal(dialog.props['aria-labelledby'], heading.props.id);
    assert.ok(heading.props.id);
    assert.match(heading.children.join(''), /Add Knowledge/);
  } finally {
    await TestRenderer.act(async () => renderer.unmount());
  }
  assert.equal(body.style.overflow, 'scroll');
  body.style.overflow = '';
});

test('modal initial server render needs no document or portal host', () => {
  const document = globalThis.document;
  delete globalThis.document;
  portalHosts.length = 0;
  try {
    assert.equal(renderToString(React.createElement(Modal, props)), '');
    assert.equal(portalHosts.length, 0);
  } finally {
    globalThis.document = document;
  }
});

test('file boundary validates media readiness, extension and limits while documents remain usable', () => {
  const document = new File(['policy'], 'policy.txt');
  const image = new File(['png'], 'scan.png');
  assert.equal(helpers.fileIssue(document, { status: 'unknown' }), null);
  assert.match(helpers.fileIssue(image, { status: 'unknown' }), /not been confirmed/);
  assert.equal(helpers.fileIssue(image, { status: 'loaded', value: ready }), null);
  assert.match(helpers.fileIssue(new File(['bad'], 'renamed.exe'), { status: 'loaded', value: ready }), /Unsupported/);
  assert.match(helpers.fileIssue({ name: 'big.png', size: 11 * 1024 * 1024 }, { status: 'loaded', value: ready }), /10 MB/);
  assert.throws(() => helpers.parseCapabilities({ ...ready, audio: { status: 'unavailable', reason: 12 } }));
});

test('mixed queue preserves files across pickers and modes, previews metadata and revokes object URLs', async () => {
  const created = [], revoked = [];
  const oldCreate = URL.createObjectURL, oldRevoke = URL.revokeObjectURL;
  URL.createObjectURL = (file) => { const url = `blob:${file.name}:${created.length}`; created.push(url); return url; };
  URL.revokeObjectURL = (url) => revoked.push(url);
  let renderer;
  try {
    renderer = await create();
    const document = new File(['policy'], 'very-long-policy-name.txt');
    const image = new File(['png'], 'scan.png');
    const audio = new File(['wav'], 'speech.wav');
    await pick(renderer, 'Add documents', [document]);
    await pick(renderer, 'Add images', [image]);
    await pick(renderer, 'Add audio', [audio]);
    assert.match(text(renderer), /3 files/);
    assert.equal(renderer.root.findAllByType('img').length, 1);
    assert.equal(renderer.root.findByType('audio').props.controls, true);
    await TestRenderer.act(async () => renderer.root.findByType('audio').props.onLoadedMetadata({ currentTarget: { duration: 65 } }));
    assert.match(text(renderer), /1:05/);
    await TestRenderer.act(async () => button(renderer, 'Paste Text').props.onClick());
    await TestRenderer.act(async () => button(renderer, 'Files').props.onClick());
    assert.match(text(renderer), /3 files/);
    await TestRenderer.act(async () => renderer.root.findByProps({ 'aria-label': 'Remove scan.png' }).props.onClick());
    assert.match(text(renderer), /2 files/);
    await TestRenderer.act(async () => button(renderer, 'Prepared OKF archive').props.onClick());
    await pick(renderer, 'Add prepared OKF archive', [new File(['archive'], 'prepared.zip')]);
    await TestRenderer.act(async () => button(renderer, 'Files').props.onClick());
    assert.match(text(renderer), /2 files/);
    assert.doesNotMatch(text(renderer), /prepared.zip/);
    await TestRenderer.act(async () => renderer.unmount());
    assert.deepEqual([...revoked].sort(), [...created].sort());
  } finally {
    if (renderer?.toJSON()) await TestRenderer.act(async () => renderer.unmount());
    URL.createObjectURL = oldCreate; URL.revokeObjectURL = oldRevoke;
  }
});

test('readiness failure allows documents, rejects dropped media and retry retains queue', async () => {
  let succeeds = false;
  const renderer = await create(async () => { if (!succeeds) throw new Error('offline'); return response(ready); });
  await pick(renderer, 'Add documents', [new File(['policy'], 'policy.txt')]);
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Add images' }).props.disabled, true);
  const zone = renderer.root.findAllByType('label').find((item) => item.props.onDrop);
  await TestRenderer.act(async () => zone.props.onDrop({ preventDefault() {}, dataTransfer: { files: [new File(['image'], 'image.png')] } }));
  assert.match(text(renderer), /not been confirmed/);
  assert.match(text(renderer), /policy.txt/);
  succeeds = true;
  await TestRenderer.act(async () => button(renderer, 'Retry').props.onClick());
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Add images' }).props.disabled, false);
  assert.match(text(renderer), /policy.txt/);
  await TestRenderer.act(async () => renderer.unmount());
});

test('stale readiness response is ignored after team changes and fetch aborts on unmount', async () => {
  const pending = [];
  const renderer = await create((url, options) => new Promise((resolve) => pending.push({ url, options, resolve })));
  await TestRenderer.act(async () => renderer.update(React.createElement(Modal, { ...props, teamAgentId: 2 })));
  assert.equal(pending[0].options.signal.aborted, true);
  await TestRenderer.act(async () => pending[1].resolve(response(ready)));
  await TestRenderer.act(async () => pending[0].resolve(response({ ...ready, images: { status: 'disabled' } })));
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Add images' }).props.disabled, false);
  await TestRenderer.act(async () => renderer.unmount());
  assert.equal(pending[1].options.signal.aborted, true);
});

test('existing queue is revalidated when readiness changes', async () => {
  const oldCreate = URL.createObjectURL, oldRevoke = URL.revokeObjectURL;
  URL.createObjectURL = () => 'blob:image'; URL.revokeObjectURL = () => {};
  let enabled = true;
  const renderer = await create(async () => response(enabled ? ready : { ...ready, images: { status: 'disabled' } }));
  try {
    await pick(renderer, 'Add images', [new File(['png'], 'image.png')]);
    enabled = false;
    await TestRenderer.act(async () => renderer.update(React.createElement(Modal, { ...props, teamAgentId: 2 })));
    assert.match(text(renderer), /Image import disabled/);
    assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, true);
    assert.match(text(renderer), /image.png/);
  } finally {
    await TestRenderer.act(async () => renderer.unmount());
    URL.createObjectURL = oldCreate; URL.revokeObjectURL = oldRevoke;
  }
});

test('review text is preserved in collapsed reading details and audio does not claim failed transcription', async () => {
  const preview = { source_count: 2, concept_count: 2, warnings: ['Optional OCR is not configured.'], documents: [
    { title: 'Policy', source_file: 'policy.txt', document_type: 'txt', media_kind: 'document', character_count: 23, text_status: 'ready', text: 'First line\nSecond line', text_truncated: false, duration_ms: null },
    { title: 'Audio', source_file: 'speech.wav', document_type: 'wav', media_kind: 'audio', character_count: 0, text_status: 'not_requested', text: '', text_truncated: false, duration_ms: 65000 },
  ] };
  const renderer = await create(async (url) => response(url.includes('preview') ? preview : ready));
  await pick(renderer, 'Add documents', [new File(['policy'], 'policy.txt')]);
  await TestRenderer.act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  const notes = renderer.root.findAllByType('summary').find((item) => item.children.join('') === 'Review notes (1)');
  assert.ok(notes, 'review notes have a compact disclosure with their count');
  assert.equal(notes.parent.type, 'details');
  assert.notEqual(notes.parent.props.open, true);
  assert.match(text(renderer), /Optional OCR is not configured/);
  const pre = renderer.root.findByType('pre');
  assert.equal(pre.children[0], 'First line\nSecond line');
  assert.equal(pre.parent.type, 'details');
  assert.notEqual(pre.parent.props.open, true);
  assert.match(text(renderer), /Transcript generated during import/);
  assert.match(text(renderer), /1:05/);
  await TestRenderer.act(async () => renderer.unmount());
});


test('file pickers expose visible keyboard focus only when available', async () => {
  const renderer = await create(async () => response({ ...ready, audio: { status: 'disabled' } }));
  try {
    for (const label of ['Add documents', 'Add images', 'Add knowledge files']) {
      const input = renderer.root.findByProps({ 'aria-label': label });
      assert.equal(input.props.disabled, false);
      assert.match(input.parent.props.className, /focus-within:ring-2/);
      assert.match(input.parent.props.className, /focus-within:ring-emerald-500/);
    }
    const disabled = renderer.root.findByProps({ 'aria-label': 'Add audio' });
    assert.equal(disabled.props.disabled, true);
    assert.doesNotMatch(disabled.parent.props.className, /cursor-pointer|focus-within:ring/);
  } finally {
    await TestRenderer.act(async () => renderer.unmount());
  }
});

test('queued file sizes remain readable for bytes, kilobytes and megabytes', async () => {
  const renderer = await create();
  try {
    await pick(renderer, 'Add documents', [new File(['abc'], 'tiny.txt'), new File([new Uint8Array(2048)], 'small.txt'), new File([new Uint8Array(1258291)], 'large.txt')]);
    assert.match(text(renderer), /3 B/);
    assert.match(text(renderer), /2 KB/);
    assert.match(text(renderer), /1\.2 MB/);
    assert.doesNotMatch(text(renderer), /0\.00 MB/);
  } finally {
    await TestRenderer.act(async () => renderer.unmount());
  }
});

function sizedFile(name, bytes) {
  const file = new File(['content'], name, { lastModified: 1 });
  Object.defineProperty(file, 'size', { value: bytes });
  return file;
}

test('file upload aggregate limit blocks review and direct submission before any request', async () => {
  const requests = [];
  const renderer = await create(async (url) => { requests.push(url); return response(ready); });
  try {
    await pick(renderer, 'Add documents', [sizedFile('first.txt', 30 * 1024 * 1024), sizedFile('second.txt', 21 * 1024 * 1024)]);
    assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, true, '51 MB across valid files must block review');
    assert.match(text(renderer), /50 MB total per upload/);
    assert.match(text(renderer), /51 MB selected/);
    assert.match(text(renderer), /Remove files.*50 MB/i);
    await TestRenderer.act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(requests.length, 1, 'over-limit submission must not send a preview or import request');
  } finally {
    await TestRenderer.act(async () => renderer.unmount());
  }
});

test('incremental mixed selections count unique files, allow exactly 50 MB and recover after removal', async () => {
  const preview = { source_count: 2, concept_count: 2, warnings: [], documents: [] };
  const requests = [];
  const renderer = await create(async (url) => { requests.push(url); return response(url.includes('preview') ? preview : ready); });
  try {
    const document = sizedFile('policy.txt', 30 * 1024 * 1024);
    await pick(renderer, 'Add documents', [document]);
    await pick(renderer, 'Add audio', [sizedFile('speech.wav', 20 * 1024 * 1024)]);
    await pick(renderer, 'Add documents', [document]);
    assert.match(text(renderer), /2 files/);
    assert.match(text(renderer), /50 MB selected/);
    assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, false);
    await TestRenderer.act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(requests.filter((url) => url.includes('preview')).length, 1);
    assert.ok(button(renderer, 'Add Knowledge'));
    await pick(renderer, 'Add images', [sizedFile('scan.png', 1)]);
    assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, true, 'one byte above the aggregate limit must block import');
    await TestRenderer.act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(requests.length, 2);
    for (const mode of ['Paste Text', 'URLs', 'Prepared OKF archive']) {
      await TestRenderer.act(async () => button(renderer, mode).props.onClick());
      assert.doesNotMatch(text(renderer), /Remove files.*50 MB/i);
      if (mode !== 'Prepared OKF archive') {
        await TestRenderer.act(async () => renderer.root.findByType('textarea').props.onChange({ target: { value: mode === 'URLs' ? 'https://example.com' : 'Policy text' } }));
        assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, false);
      }
    }
    await pick(renderer, 'Add prepared OKF archive', [sizedFile('prepared.zip', 50 * 1024 * 1024)]);
    assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, false);
    await TestRenderer.act(async () => button(renderer, 'Files').props.onClick());
    assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, true);
    await TestRenderer.act(async () => renderer.root.findByProps({ 'aria-label': 'Remove scan.png' }).props.onClick());
    assert.equal(renderer.root.findByProps({ type: 'submit' }).props.disabled, false);
    assert.doesNotMatch(text(renderer), /Remove files.*50 MB/i);
    assert.match(text(renderer), /50 MB selected/);
  } finally {
    await TestRenderer.act(async () => renderer.unmount());
  }
});
