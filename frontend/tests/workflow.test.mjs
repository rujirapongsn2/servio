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
const loadDependency = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const frontend = path.resolve(__dirname, '..');
function load(relativePath, mocks) {
  const filename = path.join(frontend, relativePath);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  const localRequire = (name) => {
    if (Object.hasOwn(mocks, name)) return mocks[name];
    if (name.startsWith('@/') || name.startsWith('next/')) throw new Error(`Unmocked import: ${name}`);
    return loadDependency(name);
  };
  vm.runInThisContext(`(function(require, exports) {${code}\n})`, { filename })(localRequire, exports);
  return exports.default;
}
function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}
function response(data) { return { ok: true, json: async () => data }; }
function text(node) {
  if (typeof node === 'string') return node;
  return (node.children || []).map(text).join(' ');
}
function button(renderer, label) {
  return renderer.root.findAllByType('button').find((node) => text(node).trim() === label);
}
async function click(renderer, label) {
  const node = button(renderer, label);
  assert.ok(node, `Missing button ${label}`);
  assert.ok(!node.props.disabled, `Button ${label} is disabled`);
  await act(async () => node.props.onClick());
}
function setup(t) {
  const originals = { fetch: global.fetch, localStorage: global.localStorage, sessionStorage: global.sessionStorage, window: global.window };
  const storage = new Map();
  global.localStorage = { getItem: () => 'test-token' };
  global.sessionStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
  global.window = { location: { origin: 'http://localhost', hostname: 'localhost' } };
  global.fetch = () => { throw new Error('Unexpected network request'); };
  const renderers = [];
  t.after(async () => {
    await act(async () => { for (const renderer of renderers) renderer.unmount(); });
    Object.assign(global, originals);
  });
  return { storage, async mount(Component) {
    let renderer;
    await act(async () => { renderer = create(React.createElement(Component)); });
    renderers.push(renderer);
    return renderer;
  } };
}
const Button = (props) => React.createElement('button', props, props.children);
const Placeholder = () => null;
const commonMocks = {
  '@/components/ui/Button': { Button },
  '@/components/WorkflowNavigator': { __esModule: true, default: Placeholder },
  'next/link': { __esModule: true, default: (props) => React.createElement('a', props, props.children) },
  '@/lib/api': { getApiBaseUrl: () => '' },
  '@/components/icons/MicIcon': { __esModule: true, default: Placeholder },
  '@/components/icons/WriteIcon': { __esModule: true, default: Placeholder },
};
const agentData = { id: 7, name: 'Saved agent', instructions: 'Saved instructions', model: 'old-model', is_starting_agent: false, tools: [], handoffs: [], llm_provider: { id: 1 } };
function agentSetup(t, { isNew = false, autoSelect = true } = {}) {
  const env = setup(t);
  const routes = [];
  const navigation = {
    search: new URLSearchParams(`team_agent_id=1&draft_id=draft1${autoSelect ? '&select_provider_id=99' : ''}`),
    router: { push: (href) => routes.push(href), replace: () => {} },
  };
  const mocks = {
    ...commonMocks,
    'next/navigation': { useParams: () => ({ id: isNew ? 'new' : '7' }), useSearchParams: () => navigation.search, useRouter: () => navigation.router },
    '@/lib/team-context': { useTeam: () => ({ selectedTeamId: 1, setSelectedTeamId: () => {} }) },
  };
  const Agent = load('src/app/admin/agents/[id]/page.tsx', mocks);
  return { ...env, Agent, navigation, routes };
}
function providerSelect(renderer) { return renderer.root.findAllByType('select')[0]; }
function agentFetch(delays = {}) {
  return async (url, options) => {
    if (options?.method === 'PUT') return response({ message: 'Agent updated' });
    if (url.endsWith('/models')) return delays.models?.(url) ?? response([{ id: url.includes('/99/') ? 'new-model' : 'old-model' }]);
    if (url === '/api/admin/llm-providers') return delays.providers?.promise ?? response([{ id: 1, name: 'Old provider' }, { id: 99, name: 'New provider' }]);
    if (url.startsWith('/api/admin/tools')) return delays.tools?.promise ?? response([]);
    if (url === '/api/admin/agents?team_agent_id=1') return delays.agents?.promise ?? response([]);
    if (url === '/api/admin/agents/7?team_agent_id=1') return delays.agent?.promise ?? response(agentData);
    throw new Error(`Unexpected request: ${url}`);
  };
}
for (const isNew of [false, true]) {
  test(`provider return waits for ${isNew ? 'draft hydration' : 'agent response'} and respects later manual choice`, async (t) => {
    const env = agentSetup(t, { isNew });
    const late = deferred();
    if (isNew) env.storage.set('agent-draft:draft1', JSON.stringify({ name: 'Draft', instructions: 'Unsaved', model: 'old-model', llm_provider_id: 1, tool_ids: [], handoff_ids: [] }));
    global.fetch = agentFetch(isNew ? { tools: late } : { agent: late });
    const renderer = await env.mount(env.Agent);
    await act(async () => late.resolve(response(isNew ? [] : agentData)));
    assert.equal(providerSelect(renderer).props.value, 99);
    await act(async () => providerSelect(renderer).props.onChange({ target: { value: '1' } }));
    assert.equal(providerSelect(renderer).props.value, 1);
  });
}
test('late models from the old provider cannot replace the newly selected provider models', async (t) => {
  const env = agentSetup(t);
  const oldModels = deferred();
  global.fetch = agentFetch({ models: (url) => url.includes('/1/') ? oldModels.promise : response([{ id: 'new-model' }]) });
  const renderer = await env.mount(env.Agent);
  await act(async () => oldModels.resolve(response([{ id: 'obsolete-model' }])));
  const modelOptions = renderer.root.findAllByType('select')[1].findAllByType('option').map((node) => node.props.value);
  assert.ok(modelOptions.includes('new-model'));
  assert.ok(!modelOptions.includes('obsolete-model'));
});
test('existing agent edits survive provider navigation and are removed only after successful save', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  global.fetch = agentFetch();
  let renderer = await env.mount(env.Agent);
  await act(async () => renderer.root.findAllByType('input')[0].props.onChange({ target: { value: 'Unsaved name' } }));
  await act(async () => renderer.root.findAllByType('textarea')[0].props.onChange({ target: { value: 'Unsaved instructions' } }));
  await act(async () => providerSelect(renderer).props.onChange({ target: { value: '__new_provider__' } }));
  assert.equal(new URL(env.routes.at(-1), 'http://localhost').searchParams.get('draft_id'), 'draft1');
  await act(async () => renderer.unmount());
  env.navigation.search = new URLSearchParams('team_agent_id=1&draft_id=draft1&select_provider_id=99');
  renderer = await env.mount(env.Agent);
  assert.equal(renderer.root.findAllByType('input')[0].props.value, 'Unsaved name');
  assert.equal(renderer.root.findAllByType('textarea')[0].props.value, 'Unsaved instructions');
  assert.equal(providerSelect(renderer).props.value, 99);
  assert.ok(env.storage.has('agent-draft:1:7:draft1'));
  await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  assert.ok(!env.storage.has('agent-draft:1:7:draft1'));
});
for (const channelType of ['line', 'facebook']) {
  test(`${channelType} wizard requires a successful save, retains input across steps and blocks failed saves`, async (t) => {
    const env = setup(t);
    const cfg = { id: 1, type: channelType, name: 'Saved channel', config: {}, is_active: false, updated_at: '2026-10-19' };
    let failSave = true;
    const team = { selectedTeamId: 1, selectedTeam: { id: 1, name: 'Team 1' }, teams: [{ id: 1, name: 'Team 1' }], loading: false, setSelectedTeamId() {} };
    const channelApi = { getChannelConfigs: async () => [cfg], updateChannelConfig: async (_token, _type, data) => {
      if (failSave) throw new Error('Save failed');
      return { ...cfg, ...data };
    } };
    const mocks = { ...commonMocks, '@/lib/team-context': { useTeam: () => team }, '@/lib/channelConfigs': channelApi };
    const ChannelForm = load('src/components/ChannelConfigForm.tsx', mocks);
    const Wizard = load('src/app/admin/tools/widget/page.tsx', { ...mocks, '@/components/ChannelConfigForm': { __esModule: true, default: ChannelForm }, '@/components/ApiKeyManager': { ApiKeyManager: Placeholder }, '@/lib/apiKeys': { getAllApiKeys: async () => [] } });
    const renderer = await env.mount(Wizard);
    await click(renderer, 'Next');
    const label = channelType === 'line' ? 'LINE Official Account' : 'Facebook Messenger';
    await act(async () => renderer.root.findAllByType('button').find((node) => text(node).includes(label)).props.onClick());
    await click(renderer, 'Next');
    const form = () => renderer.root.findByType(ChannelForm);
    await act(async () => form().findAllByType('input')[0].props.onChange({ target: { value: 'Unsaved channel' } }));
    assert.equal(button(renderer, 'Next').props.disabled, true);
    await click(renderer, 'Previous');
    await click(renderer, 'Next');
    assert.equal(form().findAllByType('input')[0].props.value, 'Unsaved channel');
    await click(renderer, 'Save Draft');
    assert.equal(button(renderer, 'Next').props.disabled, true);
    assert.equal(form().findAllByType('input')[0].props.value, 'Unsaved channel');
    failSave = false;
    await click(renderer, 'Save Draft');
    assert.equal(button(renderer, 'Next').props.disabled, false);
    await click(renderer, 'Next');
    assert.equal(renderer.root.findAllByType(ChannelForm).length, 1);
    await click(renderer, 'Previous');
    assert.equal(form().findAllByType('input')[0].props.value, 'Unsaved channel');
  });
}
test('existing agent creates a draft id while retaining its edit route', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  env.navigation.search.delete('draft_id');
  env.navigation.router.replace = (href) => {
    env.routes.push(href);
    env.navigation.search = new URL(href, 'http://localhost').searchParams;
  };
  global.fetch = agentFetch();
  await env.mount(env.Agent);
  const route = new URL(env.routes.at(-1), 'http://localhost');
  assert.equal(route.pathname, '/admin/agents/7');
  const draftId = route.searchParams.get('draft_id');
  assert.ok(draftId);
  assert.ok(env.storage.has(`agent-draft:1:7:${draftId}`));
});
test('switching draft query restores the selected draft without overwriting it with the previous form', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  global.fetch = agentFetch();
  const renderer = await env.mount(env.Agent);
  await act(async () => renderer.root.findAllByType('input')[0].props.onChange({ target: { value: 'First draft' } }));
  env.storage.set('agent-draft:1:7:draft2', JSON.stringify({ name: 'Second draft', instructions: 'Other instructions', model: 'old-model', llm_provider_id: 1, tool_ids: [], handoff_ids: [] }));
  env.navigation.search = new URLSearchParams('team_agent_id=1&draft_id=draft2');
  await act(async () => renderer.update(React.createElement(env.Agent)));
  assert.equal(renderer.root.findAllByType('input')[0].props.value, 'Second draft');
  assert.equal(JSON.parse(env.storage.get('agent-draft:1:7:draft1')).name, 'First draft');
  assert.equal(JSON.parse(env.storage.get('agent-draft:1:7:draft2')).name, 'Second draft');
});
