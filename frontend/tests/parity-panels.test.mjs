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
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
const { act, create } = TestRenderer;
const dependency = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}) { const source = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText; const exports = {}; vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename: file })(name => Object.hasOwn(mocks, name) ? mocks[name] : dependency(name), exports); return exports; }
const noop = () => null;
const Dialog = ({ children, ...props }) => React.createElement('dialog-test', props, children);
const Edit = props => React.createElement('edit-test', props);
const Knowledge = props => React.createElement('knowledge-test', props);
const mocks = { '@/lib/api': { getApiBaseUrl: () => '' }, '@/components/WorkflowPanelDialog': { default: Dialog }, '@/components/EditToolForm': { default: Edit } };
for (const name of ['WorkflowToolModal','CreateOKFBundleModal','TestOKFBundleModal','CreateFileStoreModal','FileStoreDetailModal','TestFileStoreModal']) mocks[`@/components/${name}`] = { default: noop };
mocks['@/components/OKFBundleDetailDrawer'] = { default: Knowledge };
const library = load('src/components/WorkflowCapabilitiesPanel.tsx', mocks);
const presentations = load('src/lib/product-presentations.ts');
const imageComponents = load('src/components/KnowledgeImages.tsx', { '@/lib/api': { buildApiUrl: value => value } });
const Content = load('src/components/AgentTestContent.tsx', {
  'react-markdown': { default: ReactMarkdown }, 'remark-gfm': { default: remarkGfm },
  '@/lib/markdown': { normalizeMarkdownForChat: text => text },
  '@/components/KnowledgeImages': imageComponents,
  '@/components/KnowledgeAudio': { KnowledgeAudio: props => React.createElement('audio-test', props) },
  '@/components/ProductCarousel': { ProductCarousel: props => React.createElement('carousel-test', props) },
});
const agentTest = load('src/components/WorkflowAgentTestPanel.tsx', {
  ...mocks, '@/components/AgentTestContent': Content, '@/lib/product-presentations': presentations,
});
const libraryImage = { asset_id: 'a'.repeat(64), title: 'Sofa', source_label: '01_sofa.jpg', image_url: `/api/knowledge-images/${'a'.repeat(64)}?token=signed.token` };
const libraryPresentations = { lookup: { type: 'knowledge_images', version: 1, response: 'Found', images: [libraryImage] } };
const response = (data, ok = true) => ({ ok, json: async () => data });
const text = tree => JSON.stringify(tree.toJSON());
const button = (tree, value) => tree.root.findAllByType('button').find(node => node.children.includes(value));
function globals() { const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, window: globalThis.window }; globalThis.localStorage = { getItem: () => 'token' }; globalThis.window = { confirm: () => true }; return () => Object.assign(globalThis, previous); }
const tools = [{ id: 1, name: 'Own API', type: 'custom_api', owner_team_agent_id: 5, config: '{}', visibility: 'team', agent_usage_count: 2 }, { id: 2, name: 'Foreign API', type: 'custom_api', owner_team_agent_id: 9, config: '{}', visibility: 'global' }, { id: 3, name: 'Foreign knowledge', type: 'okf_knowledge_graph', owner_team_agent_id: 9, config: '{"okf_bundle_id":3}', visibility: 'global' }];
async function mountLibrary(onMutation = async () => {}, canEdit = true) { let tree; await act(async () => { tree = create(React.createElement(library.default, { teamId: 5, canEdit, onClose() {}, onMutation })); }); return tree; }
test('library scopes reads and exposes write controls only for editable resources', async () => { const restore = globals(); let tree; const urls = []; globalThis.fetch = async url => { urls.push(url); return response(tools); }; try { tree = await mountLibrary(); assert.deepEqual(urls, ['/api/admin/tools?team_agent_id=5']); assert.equal(tree.root.findAllByProps({ 'aria-label': 'Edit Own API' }).length, 1); assert.equal(tree.root.findAllByProps({ 'aria-label': 'Edit Foreign API' }).length, 0); assert.equal(tree.root.findAllByProps({ 'aria-label': 'Delete Foreign knowledge' }).length, 0); await act(async () => tree.root.findByProps({ 'aria-label': 'Open Foreign knowledge' }).props.onClick()); assert.equal(tree.root.findByType('knowledge-test').props.canEdit, false); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });
test('deleted resource refresh retry never repeats DELETE and preserves receipt', async () => { const restore = globals(); let tree; let deletes = 0; const mutations = []; globalThis.fetch = async (url, options) => { if (options?.method === 'DELETE') { deletes++; return response({ success: true }); } return response(deletes ? [] : tools); }; try { tree = await mountLibrary(async mutation => { mutations.push(mutation); if (mutations.length === 1) throw Error('snapshot offline'); }); await act(async () => tree.root.findByProps({ 'aria-label': 'Delete Own API' }).props.onClick()); assert.equal(deletes, 1); assert.match(text(tree), /snapshot offline/); assert.equal(tree.root.findByType('dialog-test').props.busy, true); await act(async () => button(tree, 'Retry refresh').props.onClick()); assert.equal(deletes, 1); assert.deepEqual(mutations, [{ kind: 'deleted', toolId: 1 }, { kind: 'deleted', toolId: 1 }]); assert.doesNotMatch(text(tree), /Retry refresh/); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });
test('updated integration refresh retry calls snapshot callback without saving the form again', async () => { const restore = globals(); let tree; let attempts = 0; globalThis.fetch = async () => response(tools); try { tree = await mountLibrary(async () => { if (++attempts === 1) throw Error('refresh unavailable'); }); await act(async () => tree.root.findByProps({ 'aria-label': 'Edit Own API' }).props.onClick()); await act(async () => { await assert.rejects(tree.root.findByType('edit-test').props.onSaved(), /refresh unavailable/); }); assert.equal(tree.root.findAllByType('fieldset')[0].props.disabled, true); await act(async () => button(tree, 'Retry refresh').props.onClick()); assert.equal(attempts, 2); assert.equal(tree.root.findAllByType('edit-test').length, 0); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });
test('malformed resource config reports an error and readonly team cannot create', async () => { const restore = globals(); let tree; globalThis.fetch = async () => response([{ ...tools[2], config: '{bad' }]); try { tree = await mountLibrary(async () => {}, false); assert.equal(button(tree, 'Integration'), undefined); await act(async () => tree.root.findByProps({ 'aria-label': 'Open Foreign knowledge' }).props.onClick()); assert.equal(tree.root.findAllByProps({ role: 'alert' }).length, 1); assert.equal(tree.root.findAllByType('knowledge-test').length, 0); for (const config of ['[]', 'null', '1']) assert.throws(() => library.parseResourceConfig(config)); assert.equal(library.canEditWorkflowResource({ type: 'custom_api', owner_team_agent_id: null }, 5, true), true); assert.equal(library.canEditWorkflowResource({ type: 'okf_knowledge_graph', owner_team_agent_id: null }, 5, true), false); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });
test('forced tool arguments preserve JSON objects and accept key=value pairs', () => { assert.deepEqual(agentTest.parseForcedToolArguments('{"count":2}'), { count: 2 }); assert.deepEqual(agentTest.parseForcedToolArguments('city=Bangkok, units=metric'), { city: 'Bangkok', units: 'metric' }); assert.deepEqual(agentTest.parseForcedToolArguments('question'), { query: 'question' }); });
async function mountTest() { let tree; await act(async () => { tree = create(React.createElement(agentTest.default, { teamId: 5, agent: { id: 7, name: 'Support' }, hasUnsavedChanges: true, onClose() {} })); }); return tree; }
async function send(tree, value) { await act(async () => tree.root.findByProps({ 'aria-label': 'Test message' }).props.onChange({ target: { value } })); await act(async () => tree.root.findByType('form').props.onSubmit({ preventDefault() {} })); }
test('Agent tests call team-scoped saved settings and expose outputs and citations', async () => { const restore = globals(); let tree; const requests = []; globalThis.fetch = async (url, options) => { requests.push({ url, body: JSON.parse(options.body) }); return response({ response: 'Answer', citations: ['policy.md'], tool_calls: [{ name: 'lookup' }], tool_outputs: [{ name: 'lookup', output: { price: 4 } }] }); }; try { tree = await mountTest(); assert.match(text(tree), /Unsaved changes are excluded/); await send(tree, 'Hello'); assert.deepEqual(requests, [{ url: '/api/admin/agents/7/test?team_agent_id=5', body: { message: 'Hello' } }]); assert.match(text(tree), /policy.md/); assert.match(text(tree), /price/); assert.match(text(tree), /Answer/); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });
test('Reset aborts in-flight Agent test and ignores late response', async () => { const restore = globals(); let tree; let resolve; let signal; globalThis.fetch = (url, options) => { signal = options.signal; return new Promise(done => { resolve = done; }); }; try { tree = await mountTest(); await act(async () => tree.root.findByProps({ 'aria-label': 'Test message' }).props.onChange({ target: { value: 'Hello' } })); let pending; await act(async () => { pending = tree.root.findByType('form').props.onSubmit({ preventDefault() {} }); }); await act(async () => button(tree, 'Reset').props.onClick()); assert.equal(signal.aborted, true); await act(async () => { resolve(response({ response: 'Late answer', presentations: libraryPresentations })); await pending; }); assert.doesNotMatch(text(tree), /Late answer|01_sofa/); assert.equal(tree.root.findAllByType('article').length, 0); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });
test('switching Agent aborts request and clears old Agent results', async () => { const restore = globals(); let tree; let resolve; let signal; globalThis.fetch = (url, options) => { signal = options.signal; return new Promise(done => { resolve = done; }); }; try { tree = await mountTest(); await act(async () => tree.root.findByProps({ 'aria-label': 'Test message' }).props.onChange({ target: { value: 'Old' } })); let pending; await act(async () => { pending = tree.root.findByType('form').props.onSubmit({ preventDefault() {} }); }); await act(async () => tree.update(React.createElement(agentTest.default, { teamId: 5, agent: { id: 8, name: 'Sales' }, hasUnsavedChanges: false, onClose() {} }))); assert.equal(signal.aborted, true); await act(async () => { resolve(response({ response: 'Old agent result', presentations: libraryPresentations })); await pending; }); assert.doesNotMatch(text(tree), /Old agent result|01_sofa/); assert.equal(tree.root.findAllByType('article').length, 0); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });
const Drawer = load('src/components/OKFBundleDetailDrawer.tsx', { '@/lib/api': { getApiBaseUrl: () => '' }, '@/components/KnowledgeAudio': { KnowledgeAudio: noop }, '@/components/KnowledgeImages': { KnowledgeImages: noop }, '@/lib/product-presentations': { parseKnowledgeAudio: () => [], parseKnowledgeImages: () => null } }).default;
test('foreign knowledge remains browsable while edit, reindex and source refresh handlers are guarded', async () => { const restore = globals(); let tree; const writes = []; const concept = { id: 1, bundle_id: 3, concept_id: 'document', file_path: 'doc.md', type: 'document', title: 'Policy document', tags: [], body: 'Saved policy', frontmatter: { source_url: 'https://example.com/policy' }, links: [] }; globalThis.fetch = async (url, options) => { if (options?.method) { writes.push(options.method); return response({}); } if (url.includes('/concepts/document')) return response(concept); if (url.includes('/concepts')) return response([concept]); return response({ id: 3, name: 'knowledge', display_name: 'Knowledge', status: 'ready', concept_count: 1, link_count: 0 }); }; try { await act(async () => { tree = create(React.createElement(Drawer, { tool: tools[2], teamAgentId: 5, canEdit: false, onClose() {} })); }); const reindex = tree.root.findAllByType('button').find(node => node.children.includes('Re-index')); assert.equal(reindex.props.disabled, true); await act(async () => reindex.props.onClick()); await act(async () => button(tree, 'Documents (1)').props.onClick()); const conceptButton = tree.root.findAllByType('button').find(node => node.findAllByType('div').some(child => child.children.includes('Policy document'))); assert.equal(conceptButton.props.disabled, false); const edit = tree.root.findAllByType('button').find(node => node.children.includes('Edit')); assert.ok(edit); assert.equal(edit.props.disabled, true); await act(async () => edit.props.onClick()); const source = tree.root.findByProps({ id: 'document-source-url' }); assert.equal(source.props.disabled, true); const refresh = tree.root.findAllByType('button').find(node => node.children.includes(' Re-index URL')); assert.equal(refresh.props.disabled, true); await act(async () => refresh.props.onClick()); assert.deepEqual(writes, []); } finally { if (tree) await act(async () => tree.unmount()); restore(); } });

const FileStoreDetail = load('src/components/FileStoreDetailModal.tsx', {
  './MultiFileUploader': { default: noop },
  '@/lib/api': { getApiBaseUrl: () => '' },
  '@/lib/fileStoreUpload': { pollFileUploadJob: noop, uploadFileToStore: noop },
}).default;
test('read-only document library keeps both Close buttons usable', async () => {
  const restore = globals(); let tree; let closed = 0;
  globalThis.fetch = async () => response([]);
  const close = () => { closed++; };
  try {
    await act(async () => { tree = create(React.createElement(FileStoreDetail, {
      store: { id: 3, name: 'Library', gemini_store_id: 'stores/test', display_name: 'Library', file_count: 0, created_at: '' },
      canEdit: false, onClose: close,
    })); });
    const buttons = tree.root.findAllByType('button').filter(button => button.props.onClick === close);
    assert.equal(buttons.length, 2);
    for (const button of buttons) { assert.equal(button.props.disabled, false); await act(async () => button.props.onClick()); }
    assert.equal(closed, 2);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});

test('Escape preserves a busy nested import dialog and closes it when idle', async () => {
  const previous = { document: globalThis.document, MutationObserver: globalThis.MutationObserver, Node: globalThis.Node, HTMLElement: globalThis.HTMLElement };
  let tree; let busy = true; let closed = 0; const listeners = new Map();
  class ElementNode { isConnected = true; focus() {} closest() { return null; } }
  globalThis.Node = ElementNode; globalThis.HTMLElement = ElementNode;
  const nested = new ElementNode();
  nested.contains = target => target === nested;
  nested.getAttribute = name => name === 'aria-busy' ? String(busy) : null;
  globalThis.document = { activeElement: null, body: { style: { overflow: '' }, querySelectorAll: () => [nested] }, addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) };
  globalThis.MutationObserver = class { observe() {} disconnect() {} };
  const Panel = load('src/components/WorkflowPanelDialog.tsx', { 'react-dom': { createPortal: children => children } }).default;
  try {
    await act(async () => { tree = create(React.createElement(Panel, { title: 'Library', onClose() { assert.fail('Parent must stay open'); }, onChildClose() { closed++; } })); });
    const key = { key: 'Escape', target: nested, preventDefault() {}, stopPropagation() {} };
    await act(async () => listeners.get('keydown')(key));
    assert.equal(closed, 0);
    busy = false;
    await act(async () => listeners.get('keydown')(key));
    assert.equal(closed, 1);
  } finally { if (tree) await act(async () => tree.unmount()); Object.assign(globalThis, previous); }
});

test('knowledge library displays its readable source name', async () => {
  const restore = globals(); let tree;
  globalThis.fetch = async () => response([{ ...tools[2], name: 'Product_guide_okf_3', config: '{"okf_bundle_id":3,"display_name":"Product guide"}' }]);
  try {
    tree = await mountLibrary();
    assert.equal(tree.root.findAllByProps({ 'aria-label': 'Open Product guide' }).length, 1);
    assert.doesNotMatch(text(tree), /Product_guide_okf_3/);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});

test('Agent Test renders signed library images with source labels and suppresses generated image URLs', async () => {
  const restore = globals(); let tree;
  globalThis.fetch = async () => response({
    response: 'Sofa **200 cm** ![invented](01_sofa.jpg) ![external](https://example.com/sofa.jpg)',
    presentations: libraryPresentations,
  });
  try {
    tree = await mountTest(); await send(tree, 'Show the sofa');
    assert.deepEqual(tree.root.findAllByType('img').map(node => node.props.src), [libraryImage.image_url]);
    assert.match(text(tree), /01_sofa.jpg/);
    assert.equal(tree.root.findAllByType('strong')[0].children[0], '200 cm');
    assert.equal(tree.root.findAllByProps({ 'aria-label': 'ดูภาพต้นฉบับ Sofa' }).length, 1);
    await act(async () => button(tree, 'Reset').props.onClick());
    assert.equal(tree.root.findAllByType('img').length, 0);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
test('Agent Test rejects forged library URLs and never renders raw tool image claims', async () => {
  const restore = globals(); let tree;
  globalThis.fetch = async () => response({ response: 'Answer ![fake](06_bed.jpg)',
    presentations: { lookup: { ...libraryPresentations.lookup, images: [{ ...libraryImage, image_url: 'https://example.com/forged.jpg' }] } },
    tool_outputs: [{ output: JSON.stringify(libraryPresentations.lookup) }],
  });
  try {
    tree = await mountTest(); await send(tree, 'Show a bed');
    assert.equal(tree.root.findAllByType('img').length, 0);
    assert.equal(tree.root.findAllByProps({ 'aria-label': 'รูปภาพอ้างอิง' }).length, 0);
    assert.match(text(tree), /Tool outputs/);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
test('switching Team clears previously rendered library images', async () => {
  const restore = globals(); let tree;
  globalThis.fetch = async () => response({ response: 'Sofa', presentations: libraryPresentations });
  try {
    tree = await mountTest(); await send(tree, 'Show sofa');
    assert.equal(tree.root.findAllByType('img').length, 1);
    await act(async () => tree.update(React.createElement(agentTest.default, { teamId: 6, agent: { id: 7, name: 'Support' }, hasUnsavedChanges: false, onClose() {} })));
    assert.equal(tree.root.findAllByType('img').length, 0);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});

test('native image dialog retains Escape and Tab without closing Workflow Test', async () => {
  const previous = { document: globalThis.document, MutationObserver: globalThis.MutationObserver, Node: globalThis.Node, HTMLElement: globalThis.HTMLElement };
  let tree; const listeners = new Map();
  class ElementNode { isConnected = true; focus() {} closest(selector) { return selector === 'dialog[open]' ? this : null; } }
  globalThis.Node = ElementNode; globalThis.HTMLElement = ElementNode;
  const imageDialog = new ElementNode();
  const parentDialog = { contains: () => true, getAttribute: () => null, querySelectorAll: () => [], focus() {} };
  globalThis.document = { activeElement: imageDialog, body: { style: { overflow: '' }, querySelectorAll: () => [parentDialog] }, addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) };
  globalThis.MutationObserver = class { observe() {} disconnect() {} };
  const Panel = load('src/components/WorkflowPanelDialog.tsx', { 'react-dom': { createPortal: children => children } }).default;
  try {
    await act(async () => { tree = create(React.createElement(Panel, { title: 'Test', onClose() { assert.fail('Test must remain open'); } })); });
    for (const key of ['Escape', 'Tab']) {
      await act(async () => listeners.get('keydown')({ key, target: imageDialog, preventDefault() { assert.fail('Native dialog handles its own keyboard'); }, stopPropagation() {} }));
    }
  } finally { if (tree) await act(async () => tree.unmount()); Object.assign(globalThis, previous); }
});

test('comparison photos from separate calls share one gallery without duplicate assets', async () => {
  const restore = globals(); let tree;
  const bed = { ...libraryImage, asset_id: 'b'.repeat(64), title: 'Bed', source_label: '06_bed.jpg', image_url: `/api/knowledge-images/${'b'.repeat(64)}?token=signed.token` };
  globalThis.fetch = async () => response({ response: 'Compare', presentations: {
    ...libraryPresentations,
    second: { ...libraryPresentations.lookup, images: [bed, libraryImage] },
  } });
  try {
    tree = await mountTest(); await send(tree, 'Compare');
    assert.equal(tree.root.findAllByProps({ 'aria-label': 'รูปภาพอ้างอิง' }).length, 1);
    assert.deepEqual(tree.root.findAllByType('img').map(node => node.props.alt), ['Sofa', 'Bed']);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
