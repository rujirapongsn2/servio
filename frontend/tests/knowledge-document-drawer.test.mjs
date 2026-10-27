import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import { act, create } from 'react-test-renderer';
import ts from 'typescript';
const dependencies = createRequire(import.meta.url);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function drawer() {
  const filename = new URL('../src/components/OKFBundleDetailDrawer.tsx', import.meta.url);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  const mocks = {
    '@/components/KnowledgeTablePanel': { KnowledgeTablePanel: () => null }, '@/lib/admin-locale': { AdminLocaleContext: React.createContext(null) },
    '@/components/KnowledgeImageSearchSettings': { KnowledgeImageSearchSettings: props => React.createElement('image-search-settings', props) },
    'react-dom': { createPortal: (children, host) => React.createElement('drawer-portal', { host }, children) },
    '@/components/KnowledgeDocumentImage': { KnowledgeDocumentImage: props => React.createElement('document-image', props) },
    '@/components/KnowledgeImages': { KnowledgeImages: () => null },
    '@/components/KnowledgeAudio': { KnowledgeAudio: () => null },
    '@/lib/product-presentations': { parseKnowledgeAudio: () => [], parseKnowledgeImages: () => [] },
    '@/lib/api': { getApiBaseUrl: () => '' },
  };
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename: filename.pathname })(name => mocks[name] ?? dependencies(name), exports);
  return exports.default;
}
function text(node) { return typeof node === 'string' ? node : (node.children ?? []).map(text).join(''); }
function button(tree, label) { return tree.root.findAllByType('button').find(node => text(node).trim() === label); }
const concepts = [
  { id: 1, bundle_id: 1, concept_id: 'sofa', file_path: 'sofa.md', title: 'Sofa', has_image: true, body: 'Sofa extracted text', tags: [], links: [] },
  { id: 2, bundle_id: 1, concept_id: 'chair', file_path: 'chair.md', title: 'Chair', has_image: true, body: 'Chair extracted text', tags: [], links: [] },
  { id: 3, bundle_id: 1, concept_id: 'policy', file_path: 'policy.md', title: 'Policy', has_image: false, body: 'Ordinary document content', tags: [], links: [] },
];
test('image documents show scoped previews and expandable text while ordinary documents stay readable', async () => {
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, document: globalThis.document };
  globalThis.document = { body: {} };
  globalThis.localStorage = { getItem: () => 'test-token' };
  globalThis.fetch = async url => ({ ok: true, json: async () => url.includes('/concepts/') ? concepts.find(item => url.includes(`/concepts/${item.concept_id}`)) : url.includes('/concepts') ? concepts : { id: 1, status: 'ready' } });
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(drawer(), { tool: { id: 1, name: 'Products', config: '{"okf_bundle_id":1}' }, teamAgentId: 21, onClose() {} })); });
    assert.equal(tree.root.findAllByType('image-search-settings').length, 1);
    assert.equal(tree.root.findByType('image-search-settings').props.bundleId, 1);
    await act(async () => button(tree, 'Documents (3)').props.onClick());
    assert.equal(tree.root.findByType('drawer-portal').props.host, globalThis.document.body);
    assert.equal(tree.root.findAllByType('document-image').filter(node => node.props.thumbnail).length, 2);
    const preview = () => tree.root.findAllByType('document-image').find(node => !node.props.thumbnail);
    assert.equal(preview().props.conceptId, 'sofa');
    assert.equal(preview().props.teamAgentId, 21);
    assert.equal(text(tree.toJSON()).includes('Sofa extracted text'), false);
    await act(async () => button(tree, 'Extracted text').props.onClick());
    assert.equal(text(tree.toJSON()).includes('Sofa extracted text'), true);
    await act(async () => tree.root.findAllByType('button').find(node => node.props['aria-pressed'] === false && text(node).includes('Policy')).props.onClick());
    assert.equal(preview(), undefined);
    assert.equal(text(tree.toJSON()).includes('Ordinary document content'), true);
    assert.ok(tree.root.findByProps({ 'aria-label': 'Search documents' }));
  } finally {
    if (tree) await act(async () => tree.unmount());
    Object.assign(globalThis, previous);
  }
});

for (const sourceStatus of ['missing', 'partial']) {
  test(`${sourceStatus} sources retain navigation, explain recovery and disable reindex`, async () => {
    const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, document: globalThis.document };
    globalThis.document = { body: {} };
    globalThis.localStorage = { getItem: () => 'test-token' };
    const message = 'Restore source files from backup or reimport the originals.';
    globalThis.fetch = async url => {
      if (url.includes('/concepts/sofa')) return { ok: false, status: 409, json: async () => ({ detail: message }) };
      return { ok: true, json: async () => url.includes('/concepts/') ? concepts.find(item => url.includes(`/concepts/${item.concept_id}`)) : url.includes('/concepts') ? concepts : { id: 1, status: 'ready', source_availability: { status: sourceStatus, missing_file_count: 1, message } } };
    };
    let tree;
    try {
      await act(async () => { tree = create(React.createElement(drawer(), { tool: { id: 1, name: 'Products', config: '{"okf_bundle_id":1}' }, teamAgentId: 21, onClose() {} })); });
      assert.equal(button(tree, 'Re-index').props.disabled, true);
      assert.ok(text(tree.toJSON()).includes(message));
      assert.equal(text(tree.toJSON()).includes('This knowledge is ready to use'), false);
      await act(async () => button(tree, 'Documents (3)').props.onClick());
      assert.ok(tree.root.findByProps({ 'aria-label': 'Search documents' }));
      assert.ok(text(tree.toJSON()).includes(message));
      await act(async () => tree.root.findAllByType('button').find(node => node.props['aria-pressed'] === false && text(node).includes('Policy')).props.onClick());
      assert.ok(text(tree.toJSON()).includes('Ordinary document content'));
      assert.equal(button(tree, 'Edit').props.disabled, true);
      await act(async () => button(tree, 'Issues (1)').props.onClick());
      assert.equal(text(tree.toJSON()).includes('No issues found'), false);
    } finally {
      if (tree) await act(async () => tree.unmount());
      Object.assign(globalThis, previous);
    }
  });
}

test('text-only knowledge does not show image search controls', async () => {
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, document: globalThis.document };
  globalThis.document = { body: {} };
  globalThis.localStorage = { getItem: () => 'test-token' };
  globalThis.fetch = async url => ({ ok: true, json: async () => url.includes('/concepts/') ? concepts[2] : url.includes('/concepts') ? [concepts[2]] : { id: 1, status: 'ready' } });
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(drawer(), { tool: { id: 1, name: 'Policy', config: '{"okf_bundle_id":1}' }, onClose() {} })); });
    assert.equal(tree.root.findAllByType('image-search-settings').length, 0);
  } finally { if (tree) await act(async () => tree.unmount()); Object.assign(globalThis, previous); }
});
