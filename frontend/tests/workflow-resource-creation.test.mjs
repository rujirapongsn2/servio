import { adminLocale, EnglishAdminLocale } from './admin-locale-context.mjs';
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
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })(name => Object.hasOwn(mocks, name) ? mocks[name] : dependency(name), exports);
  return exports;
}
const customApi = load('src/lib/custom-api.ts');
const creation = load('src/lib/tool-creation.ts');
const noop = () => null;
const RequestEditor = () => null;
const Form = load('src/components/CreateToolForm.tsx', {
  '@/components/IconPicker': { IconPicker: noop }, '@/components/CustomApiRequestEditor': { default: RequestEditor },
  '@/lib/api': { getApiBaseUrl: () => '' }, '@/lib/custom-api': customApi, '@/lib/tool-creation': creation,
}).default;
function storage() { const values = new Map(); return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }; }
const change = value => ({ target: { value } });
const response = (data, ok = true) => ({ ok, json: async () => data });
function globals() {
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, sessionStorage: globalThis.sessionStorage, document: globalThis.document };
  globalThis.localStorage = storage(); globalThis.sessionStorage = storage();
  globalThis.document = { body: { style: { overflow: '' } } };
  return () => Object.assign(globalThis, previous);
}
async function filled(context, onCreated = () => {}) {
  let tree;
  await act(async () => { tree = create(React.createElement(Form, { context, onCreated, onCancel: () => {} })); });
  await act(async () => { tree.root.findByProps({ 'aria-label': 'Integration Type' }).props.onChange(change('mcp_streamable_http')); });
  await act(async () => {
    tree.root.findByProps({ id: 'integration-name' }).props.onChange(change('Weather'));
  });
  await act(async () => {
    tree.root.findByProps({ id: 'integration-description' }).props.onChange(change('Forecast'));
  });
  await act(async () => {
    tree.root.findByProps({ 'aria-label': 'MCP Server Endpoint' }).props.onChange(change('https://example.com/mcp'));
  });
  return tree;
}
async function submit(tree) { await act(async () => { await tree.root.findByType('form').props.onSubmit({ preventDefault() {} }); }); }

test('structured tool responses require a positive integer ID and reject failed results', () => {
  assert.equal(creation.parseCreatedTool({ tool_id: 7 }), 7);
  for (const value of [{ message: 'Created ID 7' }, { tool_id: 0 }, { tool_id: -1 }, { tool_id: '7' }, { tool_id: 1.5 }, { tool_id: 7, success: false }]) assert.throws(() => creation.parseCreatedTool(value));
});
test('workflow retries retain request ID and never create an agent binding or global tool', async () => {
  const restore = globals(); let tree; const requests = []; const created = [];
  globalThis.fetch = async (url, init) => { requests.push({ url, body: JSON.parse(init.body) }); if (requests.length === 1) throw Error('Connection lost'); return response({ tool_id: 19 }); };
  try {
    tree = await filled({ kind: 'workflow', teamId: 4 }, result => created.push(result));
    await submit(tree);
    assert.match(JSON.stringify(tree.toJSON()), /Connection lost/);
    assert.equal(tree.root.findByProps({ id: 'integration-name' }).props.value, 'Weather');
    await submit(tree);
    assert.equal(requests[0].body.request_id, requests[1].body.request_id);
    assert.equal(requests[0].url, '/api/admin/team-agents/4/workflow/tools');
    assert.equal(requests[0].body.visibility, 'team');
    assert.equal('assign_agent_id' in requests[0].body, false);
    assert.equal(requests[0].body.config.transport, 'streamable_http');
    assert.deepEqual(created, [{ tool_id: 19, name: 'Weather', type: 'mcp_streamable_http' }]);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
test('legacy tool creation preserves explicit team, assignment and visibility', async () => {
  const restore = globals(); let tree; let request;
  globalThis.fetch = async (url, init) => { request = { url, body: JSON.parse(init.body) }; return response({ success: true, tool_id: 8, message: 'created' }); };
  try {
    tree = await filled({ kind: 'tools-page', teamId: 3, assignAgentId: 12 });
    await act(async () => tree.root.findByProps({ 'aria-label': 'Visibility' }).props.onChange(change('global')));
    await submit(tree);
    assert.equal(request.url, '/api/admin/tools?team_agent_id=3');
    assert.equal(request.body.assign_agent_id, 12); assert.equal(request.body.visibility, 'global');
    assert.equal('request_id' in request.body, false);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
test('pending submissions lock fields and reject duplicate submits', async () => {
  const restore = globals(); let tree; let finish; let count = 0;
  globalThis.fetch = () => { count++; return new Promise(resolve => { finish = resolve; }); };
  try {
    tree = await filled({ kind: 'workflow', teamId: 4 });
    let pending;
    await act(async () => { pending = tree.root.findByType('form').props.onSubmit({ preventDefault() {} }); });
    assert.equal(tree.root.findByType('fieldset').props.disabled, true);
    await submit(tree); assert.equal(count, 1);
    await act(async () => { finish(response({ tool_id: 22 })); await pending; });
    assert.equal(tree.root.findByType('fieldset').props.disabled, false);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
const knowledge = load('src/lib/knowledge-import.ts');
const Knowledge = load('src/components/CreateOKFBundleModal.tsx', {
  '@/lib/admin-locale': adminLocale, '@/lib/knowledge-tables': load('src/lib/knowledge-tables.ts'), '@/components/KnowledgeTableEditor': { KnowledgeTableEditor: () => null },
  'react-dom': { createPortal: children => children }, '@/lib/api': { getApiBaseUrl: () => '' }, '@/lib/knowledge-import': knowledge,
}).default;
for (const scenario of ['success', 'failed', 'invalid-result']) test(`knowledge resumes a stored job with ${scenario}`, async () => {
  const restore = globals(); let tree; const results = []; let jobReads = 0;
  sessionStorage.setItem('team-4-agent-8-import', 'job-19');
  globalThis.fetch = async url => {
    if (url.includes('import-capabilities')) return response({}, false);
    jobReads++;
    return response({ job_id: 'job-19', status: scenario === 'failed' ? 'failed' : 'succeeded', error: 'Import failed', bundle: { id: 3, tool_id: scenario === 'invalid-result' ? 0 : 19, display_name: 'Policy', concept_count: 4, link_count: 2 }, warnings: [] });
  };
  try {
    await act(async () => { tree = create(React.createElement(EnglishAdminLocale, null, React.createElement(Knowledge, { teamAgentId: 4, assignAgentId: null, jobStorageKey: 'team-4-agent-8-import', onClose() {}, onSuccess: result => results.push(result) }))); });
    assert.equal(jobReads, 1);
    if (scenario === 'success') assert.deepEqual(results, [{ job_id: 'job-19', bundle_id: 3, tool_id: 19, display_name: 'Policy' }]);
    else assert.equal(results.length, 0);
    assert.equal(sessionStorage.getItem('team-4-agent-8-import'), scenario === 'invalid-result' ? 'job-19' : null);
    if (scenario === 'failed') assert.match(JSON.stringify(tree.toJSON()), /Import failed/);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});

test('Custom API creation serializes the reviewed request, headers and literal body', async () => {
  const restore = globals(); let tree; let saved;
  globalThis.fetch = async (_url, init) => { saved = JSON.parse(init.body); return response({ tool_id: 31 }); };
  try {
    await act(async () => { tree = create(React.createElement(Form, { context: { kind: 'workflow', teamId: 4 }, onCreated() {}, onCancel() {} })); });
    const draft = customApi.requestDraft();
    draft.endpoint = 'https://example.com/orders'; draft.method = 'PATCH'; draft.bodyText = '{"literal":"unchanged","input":"{{query}}"}'; draft.headers = [{ name: 'X-API-Key', value: 'secret' }];
    await act(async () => tree.root.findByType(RequestEditor).props.onChange(draft));
    await submit(tree);
    assert.deepEqual(saved.config.request, customApi.serializeRequest(draft));
    assert.equal(saved.config.endpoint, draft.endpoint); assert.equal(saved.config.method, 'PATCH');
    assert.equal(saved.config.request.body.value.literal, 'unchanged');
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
test('unmounting a resumed knowledge import aborts its pending status request', async () => {
  const restore = globals(); let tree; let signal;
  sessionStorage.setItem('team-import', 'job-20');
  globalThis.fetch = (url, init) => {
    if (url.includes('import-capabilities')) return Promise.resolve(response({}, false));
    signal = init.signal;
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true }));
  };
  try {
    await act(async () => { tree = create(React.createElement(EnglishAdminLocale, null, React.createElement(Knowledge, { teamAgentId: 4, assignAgentId: null, jobStorageKey: 'team-import', onClose() {}, onSuccess() { assert.fail('Aborted job must not be delivered'); } }))); });
    assert.equal(signal.aborted, false);
    await act(async () => tree.unmount()); tree = null;
    assert.equal(signal.aborted, true);
    assert.equal(sessionStorage.getItem('team-import'), 'job-20');
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});

test('a restored import can retry status without name or source and without starting another import', async () => {
  const restore = globals(); let tree; let reads = 0; const results = [];
  sessionStorage.setItem('retry-import', 'job-retry');
  globalThis.fetch = async url => {
    if (url.includes('import-capabilities')) return response({}, false);
    assert.match(url, /import-jobs\/job-retry$/);
    if (++reads === 1) throw Error('Temporary connection failure');
    return response({ job_id: 'job-retry', status: 'succeeded', bundle: { id: 5, tool_id: 32, display_name: 'Products' }, warnings: [] });
  };
  try {
    await act(async () => { tree = create(React.createElement(EnglishAdminLocale, null, React.createElement(Knowledge, { teamAgentId: 4, assignAgentId: null, jobStorageKey: 'retry-import', onClose() {}, onSuccess: result => results.push(result) }))); });
    const retry = tree.root.findAllByType('button').find(button => button.children.includes('Retry status'));
    assert.ok(retry);
    await act(async () => retry.props.onClick());
    assert.equal(reads, 2); assert.equal(results.length, 1);
    assert.equal(sessionStorage.getItem('retry-import'), null);
  } finally { if (tree) await act(async () => tree.unmount()); restore(); }
});
