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
  const modelExports = {};
  const modelSource = ts.transpileModule(fs.readFileSync(path.join(frontend, 'src/lib/provider-models.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  vm.runInThisContext(`(function(exports) {${modelSource}\n})`)(modelExports);
  mocks['@/lib/provider-models'] = modelExports;
  const Agent = load('src/app/admin/agents/[id]/page.tsx', mocks);
  return { ...env, Agent, navigation, routes };
}
function providerSelect(renderer) { return renderer.root.findAllByType('select')[0]; }
function agentFetch(delays = {}) {
  return async (url, options) => {
    if (url === '/api/admin/default-chat-models') return delays.defaults?.() ?? response({ default_model: 'gpt-6-luna', models: ['gpt-6-luna', 'gpt-5.4-mini'], available_models: ['gpt-6-luna', 'gpt-5.4-mini', 'gpt-4.1-mini'] });
    if (options?.method === 'PUT' || options?.method === 'POST') return response({ message: 'Agent updated' });
    if (url.endsWith('/registered-models')) return delays.registered?.(url) ?? response([]);
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
  await act(async () => renderer.root.findAllByType('select')[1].props.onChange({ target: { value: 'new-model' } }));
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
    const Wizard = load('src/app/admin/tools/widget/page.tsx', { ...mocks, '@/components/ChannelConfigForm': { __esModule: true, default: ChannelForm }, '@/components/ApiKeyManager': { ApiKeyManager: Placeholder }, '@/components/WidgetThemeEditor': { __esModule: true, default: Placeholder }, '@/lib/apiKeys': { getAllApiKeys: async () => [] } });
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

function modelSelect(renderer) { return renderer.root.findByProps({ id: 'agent-model' }); }
function modelIds(renderer) { return modelSelect(renderer).findAllByType('option').map((node) => node.props.value); }
async function selectValue(node, value) {
  await act(async () => node.props.onChange({ target: { value } }));
}
async function submitAgent(renderer) {
  await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
}
function captureSaves(fetcher) {
  const saves = [];
  global.fetch = async (url, options) => {
    if (options?.method === 'PUT' || options?.method === 'POST') saves.push(JSON.parse(options.body));
    return fetcher(url, options);
  };
  return saves;
}
test('registered text models merge with discovery, deduplicate IDs, and save model_id rather than catalog id', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  const saves = captureSaves(agentFetch({
    models: () => response([{ id: 'shared' }, 'upstream-only', { id: 'disabled' }, { id: 123 }]),
    registered: () => response([
      { id: 21, model_id: 'manual/text-model', enabled: true, capabilities: ['text'] },
      { id: 22, model_id: 'shared', enabled: true, capabilities: ['text', 'vision'] },
      { id: 23, model_id: 'disabled', enabled: false, capabilities: ['text'] },
      { id: 24, model_id: 'disabled-only', enabled: false, capabilities: ['text'] },
      { id: 25, model_id: 'vision-only', enabled: true, capabilities: ['vision'] },
      { id: 26, model_id: 'missing-capabilities', enabled: true },
      { id: 27, model_id: 27, enabled: true, capabilities: ['text'] },
    ]),
  }));
  const renderer = await env.mount(env.Agent);
  const ids = modelIds(renderer);
  assert.equal(ids.filter((id) => id === 'shared').length, 1);
  for (const id of ['manual/text-model', 'upstream-only', 'disabled', 'old-model']) assert.ok(ids.includes(id), id);
  for (const id of [21, 123, 'disabled-only', 'vision-only', 'missing-capabilities']) assert.ok(!ids.includes(id), String(id));
  await selectValue(modelSelect(renderer), 'manual/text-model');
  await submitAgent(renderer);
  assert.equal(saves.at(-1).model, 'manual/text-model');
});
for (const failure of ['http', 'network', 'malformed']) {
  test(`registered models remain selectable when discovery has ${failure} failure`, async (t) => {
    const env = agentSetup(t, { autoSelect: false });
    global.fetch = agentFetch({
      models: () => {
        if (failure === 'network') throw new Error('Offline');
        return failure === 'http' ? { ok: false } : response({ detail: 'Invalid response' });
      },
      registered: () => response([{ id: 17, model_id: 'manual-model', enabled: true, capabilities: ['text'] }]),
    });
    const renderer = await env.mount(env.Agent);
    assert.ok(modelIds(renderer).includes('manual-model'));
    assert.ok(modelIds(renderer).includes('old-model'));
    assert.equal(modelSelect(renderer).props.disabled, false);
    assert.match(text(renderer.root.findByProps({ role: 'status' })), /could not be loaded/);
  });
}
test('default provider permits only catalog models and saves an eligible selection', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  const saves = captureSaves(agentFetch());
  const renderer = await env.mount(env.Agent);
  await selectValue(providerSelect(renderer), 'default');
  assert.ok(modelIds(renderer).includes('__custom_model__'));
  assert.equal(renderer.root.findAllByProps({ id: 'custom-model-id' }).length, 0);
  await selectValue(modelSelect(renderer), 'mistyped-model');
  await submitAgent(renderer);
  assert.equal(saves.length, 0);
  assert.equal(modelSelect(renderer).props.value, '');
  await selectValue(modelSelect(renderer), 'gpt-5.4-mini');
  await submitAgent(renderer);
  assert.equal(saves.at(-1).model, 'gpt-5.4-mini');
  assert.equal(saves.at(-1).llm_provider_id, null);
});
for (const nextProvider of ['default', '']) {
  test(`pending provider results and errors cannot replace ${nextProvider || 'placeholder'} choices`, async (t) => {
    const env = agentSetup(t, { autoSelect: false });
    const models = deferred();
    const registry = deferred();
    global.fetch = agentFetch({ models: () => models.promise, registered: () => registry.promise });
    const renderer = await env.mount(env.Agent);
    assert.equal(modelSelect(renderer).props.disabled, false);
    await selectValue(modelSelect(renderer), '__custom_model__');
    assert.ok(renderer.root.findByProps({ id: 'custom-model-id' }));
    await selectValue(providerSelect(renderer), nextProvider);
    await act(async () => {
      models.resolve(response([{ id: 'stale-model' }]));
      registry.resolve({ ok: false });
    });
    assert.ok(!modelIds(renderer).includes('stale-model'));
    assert.equal(renderer.root.findAllByProps({ role: 'status' }).length, 0);
    assert.equal(modelSelect(renderer).props.disabled, nextProvider === '');
    if (nextProvider === 'default') assert.ok(modelIds(renderer).includes('gpt-6-luna'));
    assert.equal(renderer.root.findAllByProps({ id: 'custom-model-id' }).length, 0);
  });
}

test('registered models and custom entry are available while discovery is still pending', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  const discovery = deferred();
  const saves = captureSaves(agentFetch({
    models: () => discovery.promise,
    registered: () => response([{ id: 18, model_id: 'manual-during-discovery', enabled: true, capabilities: ['text'] }]),
  }));
  const renderer = await env.mount(env.Agent);
  assert.ok(modelIds(renderer).includes('manual-during-discovery'));
  assert.equal(modelSelect(renderer).props.disabled, false);
  assert.ok(modelIds(renderer).includes('__custom_model__'));
  await selectValue(modelSelect(renderer), 'manual-during-discovery');
  await submitAgent(renderer);
  assert.equal(saves.at(-1).model, 'manual-during-discovery');
  await act(async () => discovery.resolve(response([])));
});


test('Workflow agent setup keeps its destination through provider and capability links', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  env.navigation.search.set('return_to', 'workflow');
  env.navigation.search.set('return_team_id', '1');
  global.fetch = agentFetch();
  const renderer = await env.mount(env.Agent);
  const capabilityHref = renderer.root.findAllByType('a').find((node) => text(node).includes('Manage Capabilities')).props.href;
  assert.equal(new URL(capabilityHref, 'http://localhost').searchParams.get('return_workspace'), 'workflow');
  await selectValue(providerSelect(renderer), '__new_provider__');
  assert.equal(new URL(env.routes.at(-1), 'http://localhost').searchParams.get('return_workspace'), 'workflow');
  env.navigation.search.delete('return_to');
  env.navigation.search.set('return_workspace', 'workflow');
  await act(async () => renderer.update(React.createElement(env.Agent)));
  await submitAgent(renderer);
  assert.equal(env.routes.at(-1), '/admin/teams/1/workflow');
});


test('new legacy Agent chooses only an eligible default from the filtered catalog', async (t) => {
  const env = agentSetup(t, { isNew: true, autoSelect: false });
  const saves = captureSaves(agentFetch());
  const renderer = await env.mount(env.Agent);
  await selectValue(providerSelect(renderer), 'default');
  assert.equal(modelSelect(renderer).props.value, 'gpt-6-luna');
  assert.deepEqual(modelIds(renderer), ['', 'gpt-6-luna', 'gpt-5.4-mini', '__custom_model__']);
  await submitAgent(renderer);
  assert.equal(saves.at(-1).model, 'gpt-6-luna');
});

test('late default catalog cannot replace a custom provider or its typed ID', async (t) => {
  const env = agentSetup(t, { isNew: true, autoSelect: false });
  const pending = deferred();
  global.fetch = agentFetch({ defaults: () => pending.promise });
  const renderer = await env.mount(env.Agent);
  await selectValue(providerSelect(renderer), 'default');
  assert.equal(modelSelect(renderer).props.disabled, true);
  await selectValue(providerSelect(renderer), '1');
  await selectValue(modelSelect(renderer), '__custom_model__');
  await selectValue(renderer.root.findByProps({ id: 'custom-model-id' }), 'my/model');
  await act(async () => pending.resolve(response({ default_model: 'gpt-6-luna', models: ['gpt-6-luna'], available_models: ['gpt-6-luna'] })));
  assert.equal(renderer.root.findByProps({ id: 'custom-model-id' }).props.value, 'my/model');
  assert.ok(!modelIds(renderer).includes('gpt-6-luna'));
});

test('default catalog outage blocks new default assignments and recovers through Retry', async (t) => {
  const env = agentSetup(t, { isNew: true, autoSelect: false });
  let offline = true;
  const saves = captureSaves(agentFetch({ defaults: () => offline ? { ok: false } : response({ default_model: null, models: ['gpt-6-luna'], available_models: ['gpt-6-luna'] }) }));
  const renderer = await env.mount(env.Agent);
  await selectValue(providerSelect(renderer), 'default');
  assert.match(text(renderer.root.findByProps({ role: 'status' })), /Unable to load OpenAI models/);
  assert.equal(modelSelect(renderer).props.disabled, true);
  assert.ok(modelIds(renderer).includes('__custom_model__'));
  await submitAgent(renderer);
  assert.equal(saves.length, 0);
  offline = false;
  await click(renderer, 'Retry');
  assert.equal(modelSelect(renderer).props.disabled, false);
  await selectValue(modelSelect(renderer), 'gpt-6-luna');
  await submitAgent(renderer);
  assert.equal(saves.at(-1).model, 'gpt-6-luna');
});

test('saved legacy default model remains visible and unrelated edits save during catalog outage', async (t) => {
  const env = agentSetup(t, { autoSelect: false });
  const fetcher = agentFetch({ defaults: () => ({ ok: false }) });
  const saves = captureSaves((url, options) => url === '/api/admin/agents/7?team_agent_id=1' && !options?.method ? response({ ...agentData, model: 'gpt-6-sol', llm_provider: null }) : fetcher(url, options));
  const renderer = await env.mount(env.Agent);
  assert.equal(providerSelect(renderer).props.value, 'default');
  assert.equal(modelSelect(renderer).props.value, 'gpt-6-sol');
  const previous = modelSelect(renderer).findAllByType('option').find(node => node.props.value === 'gpt-6-sol');
  assert.equal(previous.props.disabled, true);
  await selectValue(renderer.root.findAllByType('input')[0], 'Renamed legacy');
  await submitAgent(renderer);
  assert.equal(saves.at(-1).model, 'gpt-6-sol');
  assert.equal(saves.at(-1).name, 'Renamed legacy');
});

test('legacy OpenAI manual entry validates catalog membership before saving', async t => {
  const env = agentSetup(t, { isNew: true, autoSelect: false });
  const saves = captureSaves(agentFetch()); const renderer = await env.mount(env.Agent);
  await selectValue(providerSelect(renderer), 'default');
  await selectValue(modelSelect(renderer), '__custom_model__');
  assert.equal(modelSelect(renderer).props.value, '__custom_model__');
  for (const model of ['mistyped', 'gpt-6-sol', 'gpt-6-astra', 'gpt-audio-mini']) {
    await selectValue(renderer.root.findByProps({ id: 'custom-model-id' }), model);
    await submitAgent(renderer);
    assert.equal(saves.length, 0);
    assert.equal(renderer.root.findByProps({ id: 'custom-model-id' }).props['aria-invalid'], true);
  }
  await selectValue(renderer.root.findByProps({ id: 'custom-model-id' }), ' gpt-4.1-mini ');
  await submitAgent(renderer);
  assert.equal(saves.at(-1).model, 'gpt-4.1-mini');
});

test('legacy restored manual OpenAI draft remains editable through catalog outage and retry', async t => {
  const env = agentSetup(t, { isNew: true, autoSelect: false });
  env.storage.set('agent-draft:draft1', JSON.stringify({ name: 'Draft', instructions: 'Helpful', model: 'gpt-4.1-mini', llm_provider_id: null, tool_ids: [], handoff_ids: [] }));
  let offline = true;
  const saves = captureSaves(agentFetch({ defaults: () => offline ? {ok:false} : response({models: [], available_models: ['gpt-4.1-mini'], default_model:null}) }));
  const renderer = await env.mount(env.Agent);
  await submitAgent(renderer); assert.equal(saves.length, 0);
  offline = false; await click(renderer, 'Retry');
  assert.equal(renderer.root.findByProps({id:'custom-model-id'}).props.value, 'gpt-4.1-mini');
  assert.ok(!JSON.stringify(renderer.toJSON()).includes('No suitable chatbot models'));
  await submitAgent(renderer); assert.equal(saves.at(-1).model, 'gpt-4.1-mini');
});

test('saved manual legacy OpenAI model opens its editable Model ID field', async t => {
  const env = agentSetup(t, {autoSelect:false}); const fetcher = agentFetch();
  global.fetch = (url, options) => url === '/api/admin/agents/7?team_agent_id=1' && !options?.method ? response({...agentData,model:'gpt-4.1-mini',llm_provider:null}) : fetcher(url,options);
  const renderer = await env.mount(env.Agent);
  assert.equal(renderer.root.findByProps({id:'custom-model-id'}).props.value,'gpt-4.1-mini');
  assert.equal(modelSelect(renderer).props.value,'__custom_model__');
});
