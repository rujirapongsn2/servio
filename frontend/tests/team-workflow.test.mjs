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

const requireDependency = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function modules(mocks = {}) {
  const cache = new Map();
  function load(relative) {
    const filename = path.join(root, relative);
    if (cache.has(filename)) return cache.get(filename);
    const exports = {};
    cache.set(filename, exports);
    const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;
    function localRequire(name) {
      if (Object.hasOwn(mocks, name)) return mocks[name];
      if (name.endsWith('.css')) return {};
      if (name.startsWith('@/')) {
        const stem = `src/${name.slice(2)}`;
        return load(fs.existsSync(path.join(root, `${stem}.tsx`)) ? `${stem}.tsx` : `${stem}.ts`);
      }
      return requireDependency(name);
    }
    vm.runInThisContext(`(function(require, exports) {${code}\n})`, { filename })(localRequire, exports);
    return exports;
  }
  return load;
}
function response(data, status = 200) { return { ok: status < 400, status, json: async () => structuredClone(data) }; }
function text(node) { return typeof node === 'string' ? node : (node.children ?? []).map(text).join(' '); }
function button(renderer, label) { return renderer.root.findAllByType('button').find((node) => text(node).trim() === label); }
function snapshot() {
  return { team_id: 1, team_name: 'Support', default_agent_model: 'runtime-agent-model', can_edit: true, fallback_agent_id: 1,
    agents: [
      { id: 1, name: 'Support agent', instructions: 'Handle support', model: 'test-model', llm_provider_id: null, tool_ids: [1], handoff_agent_ids: [2], shared: false, updated_at: '2026-10-23T01:00:00' },
      { id: 2, name: 'Sales agent', instructions: 'Handle sales', model: 'test-model', llm_provider_id: 1, tool_ids: [], handoff_agent_ids: [], shared: false, updated_at: '2026-10-23T01:00:00' },
    ], tools: [{ id: 1, name: 'DateTimeTool', type: 'builtin' }, { id: 2, name: 'Product data', type: 'okf_knowledge_graph' }], providers: [{ id: 1, name: 'Provider' }] };
}
function setup(t, saved = snapshot()) {
  const original = { fetch: global.fetch, localStorage: global.localStorage, sessionStorage: global.sessionStorage, window: global.window, document: global.document };
  const storage = new Map();
  const routes = [];
  const navigation = { search: new URLSearchParams() };
  const saves = [];
  const creates = [];
  const createReceipts = new Map();
  const context = { setSelectedTeamId() {}, refreshTeams: async () => {}, teams: [], loading: false };
  const controls = { saved, failSave: false, saveGate: null, loseCreateResponse: false, failRefresh: false };
  global.localStorage = { getItem: () => 'test-token' };
  global.sessionStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
  global.window = { addEventListener() {}, removeEventListener() {}, confirm: () => true, location: { search: '', reload() {} } };
  global.document = { addEventListener() {}, removeEventListener() {}, getElementById: () => null };
  global.fetch = async (url, init) => {
    if (url.endsWith('/model-defaults')) return response({ default_agent_model: 'runtime-agent-model', agent_models: ['runtime-agent-model', 'runtime-second-model'] });
    if (url.endsWith('/auth/me')) return response({is_super_admin: true});
    if (url.endsWith('/models')) return response([{ id: 'discovered-model' }]);
    if (url.endsWith('/registered-models')) return response([{ model_id: 'registered-model', enabled: true, capabilities: ['text'] }]);
    if (url.endsWith('/workflow')) {
      if (controls.failRefresh) throw Error('Refresh offline');
      return response(controls.saved);
    }
    if (url.endsWith('/workflow/members') && init?.method === 'PUT') {
      const body = JSON.parse(init.body); saves.push(body);
      if (controls.failSave) return response({ detail: 'Membership changed. Reload before saving.' }, 409);
      controls.saved.agents = body.member_agent_ids.map(id => controls.saved.agents.find(agent => agent.id === id));
      controls.saved.fallback_agent_id = body.fallback_agent_id;
      return response({success:true});
    }
    if (init?.method === 'DELETE' && url.includes('/workflow/agents/')) {
      const id = Number(url.split('/').at(-1)); const body = JSON.parse(init.body); saves.push(body);
      controls.saved.agents = controls.saved.agents.filter(agent => agent.id !== id);
      if (controls.saved.fallback_agent_id === id) controls.saved.fallback_agent_id = body.replacement_fallback_agent_id;
      return response({success:true});
    }
    if (url.includes('/agents/optimize-prompt?team_agent_id=1')) return response({ optimized_instructions: 'Reviewed optimized instructions' });
    if (url.endsWith('/llm-providers')) return response([{ id: 1, name: 'Provider' }, {id: 3, name: 'New provider'}]);
    if (init?.method === 'POST' && url.endsWith('/workflow/agents')) {
      const body = JSON.parse(init.body); creates.push(body);
      let id = createReceipts.get(body.request_id);
      if (!id) {
        id = Math.max(0, ...controls.saved.agents.map(agent => agent.id)) + 1;
        controls.saved.agents.push({ ...body, id, shared: false, updated_at: '2026-10-23T03:00:00' });
        if (body.is_fallback || controls.saved.fallback_agent_id === null) controls.saved.fallback_agent_id = id;
        createReceipts.set(body.request_id, id);
      }
      if (controls.loseCreateResponse) { controls.loseCreateResponse = false; throw Error('Connection lost'); }
      return response({ agent_id: id });
    }
    if (init?.method === 'PUT') {
      const body = JSON.parse(init.body); saves.push(body);
      if (controls.saveGate) await controls.saveGate;
      if (controls.failSave) return response({ detail: 'Conflict: reload before saving.' }, 409);
      const id = Number(url.split('/').at(-1));
      const agent = controls.saved.agents.find((agent) => agent.id === id);
      Object.assign(agent, body, { updated_at: '2026-10-23T02:00:00' });
      if (body.is_fallback) controls.saved.fallback_agent_id = id;
      return response({ agent_id: id });
    }
    throw new Error(`Unexpected network request ${url}`);
  };
  const load = modules({
    '@/lib/api': { getApiBaseUrl: () => '' },
    '@/lib/team-context': { useTeam: () => context },
    'next/navigation': { useRouter: () => ({ push: (href) => routes.push(href), replace() {} }), useSearchParams: () => navigation.search },
    'next/dynamic': { __esModule: true, default: () => (props) => React.createElement('workflow-graph', props) },
    '@/components/WorkflowCapabilitiesPanel': { __esModule: true, default: (props) => React.createElement('capabilities-panel', props) },
    '@/components/WorkflowMembersPanel': { __esModule: true, default: (props) => React.createElement('members-panel', props) },
    '@/components/WorkflowProviderModal': { __esModule: true, default: (props) => React.createElement('provider-modal', props) },
    '@/components/WorkflowToolModal': { __esModule: true, default: (props) => React.createElement('tool-creator', props) },
    '@/components/CreateOKFBundleModal': { __esModule: true, default: (props) => React.createElement('knowledge-creator', props) },
    '@/components/ProviderModels': { ProviderModels: () => null },
    '@/components/WorkflowNavigator': { __esModule: true, default: () => null },
  });
  const Component = load('src/components/TeamWorkflowWorkspace.tsx').default;
  const renderers = [];
  t.after(async () => {
    await act(async () => { renderers.forEach((renderer) => renderer.unmount()); });
    Object.assign(global, original);
  });
  return { storage, controls, saves, creates, routes, context, navigation, load, async mount() {
    let renderer;
    await act(async () => { renderer = create(React.createElement(Component, { teamId: 1 })); });
    renderers.push(renderer); return renderer;
  } };
}
async function change(renderer, id, value) {
  await act(async () => renderer.root.findByProps({ id }).props.onChange({ target: { value } }));
}
async function select(renderer, id) {
  await act(async () => renderer.root.findByType('workflow-graph').props.onSelect(id));
}
async function save(renderer) {
  await act(async () => renderer.root.findByProps({ 'aria-label': 'Agent settings' }).props.onSubmit({ preventDefault() {} }));
}

test('Workflow switches between design and private chat without saving drafts or losing composers', async t => {
  const env = setup(t); const renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Draft support');
  await act(async () => button(renderer, 'Try draft').props.onClick());
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Private workflow preview' }).props.hidden, false);
  await change(renderer, 'preview-message-1', 'Remember this team question');
  await act(async () => button(renderer, 'Design').props.onClick());
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Draft support');
  await act(async () => button(renderer, 'Private chat').props.onClick());
  assert.equal(renderer.root.findByProps({ id: 'preview-message-1' }).props.value, 'Remember this team question');
  await change(renderer, 'preview-target-1', '1');
  assert.equal(renderer.root.findByProps({ id: 'preview-message-1' }).props.value, '');
  await change(renderer, 'preview-message-1', 'Direct question');
  await change(renderer, 'preview-target-1', 'team');
  assert.equal(renderer.root.findByProps({ id: 'preview-message-1' }).props.value, 'Remember this team question');
  assert.equal(env.saves.length, 0);
  assert.equal(env.creates.length, 0);
});

test('Canceling a live Agent save keeps its draft and performs no write', async t => {
  const env = setup(t); const renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Do not publish');
  global.window.confirm = () => false;
  await save(renderer);
  assert.equal(env.saves.length, 0);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Do not publish');
});

test('agent edits save in the active team and refresh the diagram', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  assert.equal(renderer.root.findByType('workflow-graph').props.fallbackAgentId, 1);
  await change(renderer, 'workflow-agent-name', ' Updated support ');
  await change(renderer, 'workflow-model', 'custom/model');
  await save(renderer);
  assert.equal(env.saves[0].name, 'Updated support');
  assert.equal(env.saves[0].model, 'custom/model');
  assert.equal(env.saves[0].expected_fallback_agent_id, 1);
  assert.equal(env.saves[0].expected_updated_at, '2026-10-23T01:00:00');
  assert.equal(renderer.root.findByType('workflow-graph').props.agents[0].name, 'Updated support');
  assert.ok(!env.storage.has('team-workflow-drafts:1'));
  assert.equal(button(renderer, 'Save agent').props.disabled, true);
});

test('drafts survive selection and reload, and failed saves retain input', async (t) => {
  const env = setup(t); let renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Unsaved support');
  await select(renderer, 2);
  await change(renderer, 'workflow-agent-name', 'Unsaved sales');
  await select(renderer, 1);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Unsaved support');
  await act(async () => renderer.unmount());
  renderer = await env.mount();
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Unsaved support');
  env.controls.failSave = true;
  await save(renderer);
  assert.match(text(renderer.root.findByProps({ role: 'alert' })), /Conflict/);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Unsaved support');
  assert.equal(JSON.parse(env.storage.get('team-workflow-drafts:1')).length, 2);
});

test('stale restored drafts require discard before they can be saved', async (t) => {
  const env = setup(t);
  env.storage.set('team-workflow-drafts:1', JSON.stringify([{ agent_id: 1, draft: {
    name: 'Stale name', instructions: 'Old draft', model: 'old', llm_provider_id: null, tool_ids: [], handoff_agent_ids: [],
    is_fallback: true, expected_updated_at: 'old-revision', expected_fallback_agent_id: 1,
  } }]));
  const renderer = await env.mount();
  assert.match(text(renderer.root.findByProps({ role: 'alert' })), /older version/);
  assert.equal(button(renderer, 'Save agent').props.disabled, true);
  await act(async () => button(renderer, 'Discard').props.onClick());
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Support agent');
  assert.ok(!env.storage.has('team-workflow-drafts:1'));
});

test('shared agents and viewer access keep the inspector read-only', async (t) => {
  const data = snapshot(); data.agents[0].shared = true; data.can_edit = false;
  const env = setup(t, data); const renderer = await env.mount();
  assert.equal(renderer.root.findByType('fieldset').props.disabled, true);
  assert.match(text(renderer.root), /Shared agent/);
  assert.equal(button(renderer, 'Save agent'), undefined);
  assert.equal(renderer.root.findAllByType('button').filter((node) => !node.props.role && text(node).trim() === 'Agent').length, 0);
});

test('knowledge and handoffs are assigned through inspector tabs', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => renderer.root.findAllByProps({ role: 'tab' }).find(node => text(node).trim() === 'Knowledge').props.onClick());
  const knowledge = renderer.root.findAllByType('input').find((node) => node.props.type === 'checkbox');
  await act(async () => knowledge.props.onChange({ target: { checked: true } }));
  await act(async () => button(renderer, 'Handoffs').props.onClick());
  const handoff = renderer.root.findAllByType('input').find((node) => node.props.type === 'checkbox');
  await act(async () => handoff.props.onChange({ target: { checked: false } }));
  await save(renderer);
  assert.deepEqual(env.saves[0].tool_ids, [1, 2]);
  assert.deepEqual(env.saves[0].handoff_agent_ids, []);
});

test('saving blocks agent changes until the request finishes', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Changed');
  let finish;
  env.controls.saveGate = new Promise((resolve) => { finish = resolve; });
  await save(renderer);
  assert.equal(button(renderer, 'Saving…').props.disabled, true);
  await select(renderer, 2);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Changed');
  await act(async () => finish());
  assert.equal(button(renderer, 'Save agent').props.disabled, true);
});

test('empty teams create an Agent without leaving Workflow', async (t) => {
  const data = snapshot(); data.agents = []; data.fallback_agent_id = null;
  const env = setup(t, data); const renderer = await env.mount();
  await act(async () => button(renderer, 'Create agent').props.onClick());
  await change(renderer, 'workflow-agent-name', 'First agent');
  await change(renderer, 'workflow-instructions', 'Handle incoming requests');
  await save(renderer);
  assert.equal(env.routes.length, 0);
  assert.equal(env.creates.length, 1);
  assert.equal(env.creates[0].is_fallback, true);
  assert.equal(env.creates[0].expected_fallback_agent_id, null);
  assert.equal(renderer.root.findByType('workflow-graph').props.agents[0].name, 'First agent');
  assert.equal(renderer.root.findByType('workflow-graph').props.fallbackAgentId, 1);
  assert.ok(!env.storage.has('team-workflow-new:1'));
});

test('team cards retain Manage and open Workflow as a full page', async (t) => {
  const env = setup(t); env.context.teams = [{ id: 1, name: 'Support', slug: 'support', status: 'active', member_count: 2 }];
  const Teams = env.load('src/app/admin/teams/page.tsx').default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(Teams)); });
  t.after(async () => { await act(async () => renderer.unmount()); });
  assert.ok(button(renderer, 'Manage'));
  await act(async () => button(renderer, 'Workflow').props.onClick());
  assert.equal(env.routes[0], '/admin/teams/1/workflow');
});

test('diagram routes Coordinator to every member and keeps handoffs directed', async () => {
  const load = modules({ reactflow: {
    __esModule: true, default: (props) => React.createElement('flow', props),
    Background: () => null, Controls: () => null, Handle: () => null,
    MarkerType: { ArrowClosed: 'closed' }, Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
  } });
  const Graph = load('src/components/AgentFlowGraph.tsx').default;
  const data = snapshot();
  let renderer;
  await act(async () => { renderer = create(React.createElement(Graph, { agents: data.agents, tools: data.tools, fallbackAgentId: 1, selectedAgentId: 1, onSelect() {} })); });
  const edges = renderer.root.findByType('flow').props.edges;
  assert.deepEqual(edges.filter((edge) => edge.source === 'coordinator').map((edge) => edge.target), ['1', '2']);
  assert.deepEqual(edges.filter((edge) => edge.source !== 'coordinator').map((edge) => [edge.source, edge.target]), [['1', '2']]);
  await act(async () => renderer.unmount());
});

test('invalid API snapshots and malformed drafts are rejected safely', () => {
  const load = modules(); const api = load('src/lib/team-workflow.ts');
  assert.throws(() => api.parseTeamWorkflow({ ...snapshot(), agents: [{ id: 'wrong' }] }), /Invalid workflow/);
  assert.deepEqual(api.restoreWorkflowDrafts('bad JSON', snapshot()), {});
  assert.deepEqual(api.restoreWorkflowDrafts(JSON.stringify([{ agent_id: 999, draft: {} }]), snapshot()), {});
});


test('provider navigation preserves the final Workflow destination', async (t) => {
  const env = setup(t);
  env.navigation.search = new URLSearchParams('return_to=agent_edit&return_workspace=workflow&return_agent_id=new&return_team_id=1&team_agent_id=1&draft_id=work-draft');
  global.fetch = async () => response([]);
  const Providers = env.load('src/app/admin/providers/page.tsx').default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(Providers)); });
  await act(async () => button(renderer, 'Back to Edit Agent').props.onClick());
  const url = new URL(env.routes[0], 'http://localhost');
  assert.equal(url.pathname, '/admin/agents/new');
  assert.equal(url.searchParams.get('return_workspace'), 'workflow');
  assert.equal(url.searchParams.get('draft_id'), 'work-draft');
  await act(async () => renderer.unmount());
});

test('tool creation preserves the Workflow destination and selects the new tool', async (t) => {
  const env = setup(t);
  env.navigation.search = new URLSearchParams('return_workspace=workflow&return_agent_id=new&return_team_id=1&team_agent_id=1&draft_id=work-draft');
  global.fetch = async () => response({ message: 'Tool created with ID 42', tool_id: 42 });
  const NewTool = env.load('src/app/admin/tools/new/page.tsx').default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(NewTool)); });
  await act(async () => renderer.root.findAllByType('select')[0].props.onChange({ target: { value: 'mcp_streamable_http' } }));
  await act(async () => renderer.root.findByProps({ placeholder: 'https://mcp-server.example.com/mcp' }).props.onChange({ target: { value: 'https://mcp.example/mcp' } }));
  await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  const url = new URL(env.routes[0], 'http://localhost');
  assert.equal(url.pathname, '/admin/agents/new');
  assert.equal(url.searchParams.get('return_workspace'), 'workflow');
  assert.equal(url.searchParams.get('auto_select_tool_id'), '42');
  assert.equal(url.searchParams.get('draft_id'), 'work-draft');
  await act(async () => renderer.unmount());
});


test('new Agent drafts survive selection and reload with the same request ID', async (t) => {
  const env = setup(t); let renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Existing draft');
  await act(async () => renderer.root.findByType('workflow-graph').props.onAddAgent());
  await change(renderer, 'workflow-agent-name', 'New specialist');
  await change(renderer, 'workflow-instructions', 'Handle specialist requests');
  const requestId = JSON.parse(env.storage.get('team-workflow-new:1')).requestId;
  await select(renderer, 1);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Existing draft');
  await act(async () => renderer.unmount());
  renderer = await env.mount();
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'New specialist');
  assert.equal(JSON.parse(env.storage.get('team-workflow-new:1')).requestId, requestId);
  await save(renderer);
  assert.equal(env.creates[0].request_id, requestId);
  assert.ok(env.storage.has('team-workflow-drafts:1'));
});

test('an uncertain Agent creation retries the same request without duplicate Agents', async (t) => {
  const data = snapshot(); data.agents = []; data.fallback_agent_id = null;
  const env = setup(t, data); const renderer = await env.mount();
  await act(async () => button(renderer, 'Create agent').props.onClick());
  await change(renderer, 'workflow-agent-name', 'Only one');
  await change(renderer, 'workflow-instructions', 'Handle requests');
  env.controls.loseCreateResponse = true;
  await save(renderer);
  assert.match(text(renderer.root.findByProps({ role: 'alert' })), /Connection lost/);
  await save(renderer);
  assert.equal(env.creates.length, 2);
  assert.equal(env.creates[0].request_id, env.creates[1].request_id);
  assert.equal(renderer.root.findByType('workflow-graph').props.agents.length, 1);
});

test('a successful create with failed refresh can refresh without posting again', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => renderer.root.findByType('workflow-graph').props.onAddAgent());
  await change(renderer, 'workflow-agent-name', 'Created once');
  await change(renderer, 'workflow-instructions', 'Handle requests');
  env.controls.failRefresh = true;
  await save(renderer);
  assert.match(text(renderer.root.findByProps({ role: 'alert' })), /saved.*could not be refreshed/);
  assert.equal(renderer.root.findByType('fieldset').props.disabled, true);
  env.controls.failRefresh = false;
  await act(async () => button(renderer, 'Refresh workflow').props.onClick());
  assert.equal(env.creates.length, 1);
  assert.equal(renderer.root.findByType('workflow-graph').props.agents.length, 3);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Created once');
});

test('created resources attach to the captured draft and preserve other Agent edits', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Support draft');
  await act(async () => button(renderer, 'Tool').props.onClick());
  await select(renderer, 2);
  await change(renderer, 'workflow-agent-name', 'Sales draft');
  await act(async () => renderer.root.findByType('tool-creator').props.onCreated({ tool_id: 42, name: 'Order lookup', type: 'custom_api' }));
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Sales draft');
  await select(renderer, 1);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Support draft');
  await save(renderer);
  assert.deepEqual(env.saves[0].tool_ids, [1, 42]);
  assert.equal(env.saves[0].expected_updated_at, '2026-10-23T01:00:00');
  assert.ok(env.storage.has('team-workflow-drafts:1'));
});

test('new Agent knowledge is staged without binding to a persisted Agent', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => renderer.root.findByType('workflow-graph').props.onAddAgent());
  await change(renderer, 'workflow-agent-name', 'Knowledge expert');
  await change(renderer, 'workflow-instructions', 'Use assigned knowledge');
  await act(async () => renderer.root.findAllByType('button').find(node => !node.props.role && text(node).trim() === 'Knowledge').props.onClick());
  const modal = renderer.root.findByType('knowledge-creator');
  assert.equal(modal.props.teamAgentId, 1);
  assert.equal(modal.props.assignAgentId, null);
  await act(async () => modal.props.onSuccess({ tool_id: 43, bundle_id: 4, job_id: 'job', display_name: 'Policy' }));
  await act(async () => renderer.root.findByType('knowledge-creator').props.onClose());
  assert.equal(env.saves.length, 0);
  await save(renderer);
  assert.deepEqual(env.creates[0].tool_ids, [1, 43]);
  assert.equal(env.routes.length, 0);
});

test('canvas handoffs update source drafts and Discard restores the saved graph', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Keep these edits');
  await act(async () => renderer.root.findByType('workflow-graph').props.onHandoffChange({ sourceId: 2, targetId: 1, connected: true }));
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Sales agent');
  assert.deepEqual(renderer.root.findByType('workflow-graph').props.agents[1].handoff_agent_ids, [1]);
  await save(renderer);
  assert.deepEqual(env.saves[0].handoff_agent_ids, [1]);
  await select(renderer, 1);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Keep these edits');
  await act(async () => renderer.root.findByType('workflow-graph').props.onHandoffChange({ sourceId: 1, targetId: 2, connected: false }));
  assert.deepEqual(renderer.root.findByType('workflow-graph').props.agents[0].handoff_agent_ids, []);
  await act(async () => button(renderer, 'Discard').props.onClick());
  assert.deepEqual(renderer.root.findByType('workflow-graph').props.agents[0].handoff_agent_ids, [2]);
});

test('shared sources, duplicates, self handoffs and nonmember edges cannot change drafts', async (t) => {
  const data = snapshot(); data.agents[1].shared = true;
  const env = setup(t, data); const renderer = await env.mount();
  for (const edge of [{ sourceId: 2, targetId: 1 }, { sourceId: 1, targetId: 2 }, { sourceId: 1, targetId: 1 }, { sourceId: 1, targetId: 999 }, { sourceId: 0, targetId: 1 }]) {
    await act(async () => renderer.root.findByType('workflow-graph').props.onHandoffChange({ ...edge, connected: true }));
  }
  assert.deepEqual(renderer.root.findByType('workflow-graph').props.pendingAgentIds, []);
  assert.ok(!env.storage.has('team-workflow-drafts:1'));
});

test('knowledge jobs for discarded new drafts cannot attach to a different new Agent', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  const start = async () => act(async () => renderer.root.findByType('workflow-graph').props.onAddAgent());
  const knowledge = async () => act(async () => renderer.root.findAllByType('button').find(node => !node.props.role && text(node).trim() === 'Knowledge').props.onClick());
  await start(); await knowledge();
  const firstKey = renderer.root.findByType('knowledge-creator').props.jobStorageKey;
  await act(async () => renderer.root.findByType('knowledge-creator').props.onClose());
  await act(async () => button(renderer, 'Discard').props.onClick());
  await start(); await knowledge();
  const nextKey = renderer.root.findByType('knowledge-creator').props.jobStorageKey;
  assert.notEqual(firstKey, nextKey);
});

test('mouse handoff drags suppress native selection and only completed valid connections change drafts', async () => {
  const Flow = () => null;
  const stub = () => null;
  const load = modules({ reactflow: { __esModule: true, default: Flow, Background: stub, Controls: stub, Handle: stub, MarkerType: { ArrowClosed: 'arrowclosed' }, Position: { Bottom: 'bottom', Top: 'top', Left: 'left', Right: 'right' } } });
  const Graph = load('src/components/AgentFlowGraph.tsx').default;
  const changes = []; const data = snapshot(); let tree;
  try {
    await act(async () => { tree = create(React.createElement(Graph, { agents: data.agents, tools: data.tools, fallbackAgentId: 1, selectedAgentId: 1, onSelect() {}, canEdit: true, onHandoffChange: change => changes.push(change) })); });
    const props = tree.root.findByType(Flow).props;
    for (const type of ['mousedown', 'touchstart']) {
      const event = new Event(type, { cancelable: true });
      await act(async () => props.onConnectStart?.(event, { nodeId: '2', handleId: 'handoff-out-left', handleType: 'source' }));
      assert.equal(event.defaultPrevented, type === 'mousedown', `${type} cancellation must match the gesture`);
      assert.equal(event.cancelBubble, false);
      await act(async () => props.onConnectEnd?.(new Event(type === 'mousedown' ? 'mouseup' : 'touchend')));
      assert.deepEqual(changes, []);
    }
    const connection = { source: '2', target: '1', sourceHandle: 'handoff-out-left', targetHandle: 'handoff-in-right' };
    for (const invalid of [{ ...connection, target: '2' }, { ...connection, target: '999' }, { ...connection, sourceHandle: 'routing' }, { ...connection, source: '1', target: '2' }]) {
      await act(async () => props.onConnect(invalid));
    }
    assert.deepEqual(changes, []);
    await act(async () => props.onConnect(connection));
    assert.deepEqual(changes, [{ sourceId: 2, targetId: 1, connected: true }]);
  } finally { if (tree) await act(async () => tree.unmount()); }
});

test('selected editable handoffs expose a mouse delete action without deleting protected edges', async () => {
  const Flow = () => null;
  const stub = () => null;
  const load = modules({ reactflow: { __esModule: true, default: Flow, Background: stub, Controls: stub, Handle: stub, MarkerType: { ArrowClosed: 'arrowclosed' }, Position: { Bottom: 'bottom', Top: 'top', Left: 'left', Right: 'right' } } });
  const Graph = load('src/components/AgentFlowGraph.tsx').default;
  const changes = []; const data = snapshot(); let tree; let added = 0;
  const props = { agents: data.agents, tools: data.tools, fallbackAgentId: 1, selectedAgentId: 1, onSelect() {}, canEdit: true, onHandoffChange: change => changes.push(change), onAddAgent: () => added++ };
  try {
    await act(async () => { tree = create(React.createElement(Graph, props)); });
    assert.equal(button(tree, 'Delete handoff'), undefined);
    await act(async () => tree.root.findByType(Flow).props.onEdgesChange([{ id: 'routing-1', type: 'select', selected: true }]));
    assert.equal(button(tree, 'Delete handoff'), undefined);
    await act(async () => tree.root.findByType(Flow).props.onEdgesChange([{ id: 'handoff-1-2', type: 'select', selected: true }]));
    assert.ok(button(tree, 'Delete handoff'));
    assert.deepEqual(changes, []);
    await act(async () => button(tree, 'Add agent').props.onClick());
    assert.equal(added, 1);
    assert.deepEqual(changes, []);
    assert.ok(button(tree, 'Delete handoff'));
    await act(async () => tree.update(React.createElement(Graph, { ...props, disabled: true })));
    assert.equal(button(tree, 'Delete handoff'), undefined);
    await act(async () => tree.update(React.createElement(Graph, { ...props, agents: data.agents.map(agent => ({ ...agent, shared: true })) })));
    assert.equal(button(tree, 'Delete handoff'), undefined);
    await act(async () => tree.update(React.createElement(Graph, props)));
    await act(async () => button(tree, 'Delete handoff').props.onClick());
    assert.deepEqual(changes, [{ sourceId: 1, targetId: 2, connected: false }]);
    assert.equal(button(tree, 'Delete handoff'), undefined);
  } finally { if (tree) await act(async () => tree.unmount()); }
});

test('controlled canvas edges retain selection for keyboard deletion and protect routing edges', async () => {
  const Flow = () => null;
  const stub = () => null;
  const load = modules({ reactflow: { __esModule: true, default: Flow, Background: stub, Controls: stub, Handle: stub, MarkerType: { ArrowClosed: 'arrowclosed' }, Position: { Bottom: 'bottom', Top: 'top', Left: 'left', Right: 'right' } } });
  const Graph = load('src/components/AgentFlowGraph.tsx').default;
  const changes = []; const data = snapshot(); let tree;
  try {
    await act(async () => { tree = create(React.createElement(Graph, { agents: data.agents, tools: data.tools, fallbackAgentId: 1, selectedAgentId: 1, onSelect() {}, canEdit: true, onHandoffChange: change => changes.push(change) })); });
    await act(async () => tree.root.findByType(Flow).props.onEdgesChange([{ id: 'handoff-1-2', type: 'select', selected: true }]));
    const props = tree.root.findByType(Flow).props;
    const edge = props.edges.find(edge => edge.id === 'handoff-1-2');
    assert.equal(edge.selected, true);
    const routing = props.edges.find(edge => edge.id === 'routing-1');
    assert.equal(routing.deletable, false);
    await act(async () => props.onEdgesDelete([edge, routing]));
    assert.deepEqual(changes, [{ sourceId: 1, targetId: 2, connected: false }]);
  } finally { if (tree) await act(async () => tree.unmount()); }
});


test('membership changes preserve Agent fields and revisions while reconciling team fallback', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Keep drafted name');
  await act(async () => button(renderer, 'Members').props.onClick());
  await act(async () => renderer.root.findByType('members-panel').props.onSave([2, 1], 2, [1, 2], 1));
  assert.deepEqual(env.saves[0].expected_member_agent_ids, [1, 2]);
  assert.equal(env.saves[0].expected_fallback_agent_id, 1);
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Keep drafted name');
  await save(renderer);
  assert.equal(env.saves[1].expected_updated_at, '2026-10-23T01:00:00');
  assert.equal(env.saves[1].expected_fallback_agent_id, 2);
  assert.equal(env.saves[1].is_fallback, false);
});

test('membership failures retain member panel and Agent drafts', async (t) => {
  const env = setup(t); const renderer = await env.mount(); env.controls.failSave = true;
  await change(renderer, 'workflow-agent-name', 'Keep on conflict');
  await act(async () => button(renderer, 'Members').props.onClick());
  await act(async () => { await assert.rejects(renderer.root.findByType('members-panel').props.onSave([1], 1, [1, 2], 1), /Membership changed/); });
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Keep on conflict');
  assert.ok(renderer.root.findByType('members-panel'));
});

test('resource deletion removes only that tool from all drafts and preserves revisions', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await change(renderer, 'workflow-agent-name', 'Keep resource draft');
  await act(async () => button(renderer, 'Library').props.onClick());
  env.controls.saved.tools = [];
  await act(async () => renderer.root.findByType('capabilities-panel').props.onMutation({kind:'deleted',toolId:1}));
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Keep resource draft');
  await save(renderer);
  assert.deepEqual(env.saves[0].tool_ids, []);
  assert.equal(env.saves[0].expected_updated_at, '2026-10-23T01:00:00');
});

for (const canEdit of [true, false]) {
  test(`workflow removes diagnostics and duplicate toolbar creation for can_edit=${canEdit}`, async (t) => {
    const data = snapshot(); data.can_edit = canEdit;
    const env = setup(t, data); const renderer = await env.mount();
    assert.doesNotMatch(text(renderer.root), /Advanced diagnostics|Test saved agent/);
    assert.equal(renderer.root.findAllByType('button').filter(node => !node.props.role && text(node).trim() === 'Agent').length, 0);
    assert.ok(button(renderer, 'Library'));
    await act(async () => renderer.root.findByType('workflow-graph').props.onAddAgent());
    assert.equal(renderer.root.findByType('workflow-graph').props.hasNewAgentDraft, canEdit);
    if (canEdit) {
      await change(renderer, 'workflow-agent-name', 'Canvas draft');
      assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Canvas draft');
    } else {
      assert.equal(button(renderer, 'Members'), undefined);
    }
  });
}

test('optimization is reviewed before applying and cannot overwrite newer instructions', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => button(renderer, 'Optimize').props.onClick());
  assert.equal(renderer.root.findByProps({ id:'workflow-instructions' }).props.value, 'Handle support');
  assert.equal(renderer.root.findByProps({'aria-label':'Suggested instructions'}).props.value, 'Reviewed optimized instructions');
  await change(renderer, 'workflow-instructions', 'Newer draft');
  assert.equal(button(renderer, 'Apply suggestion').props.disabled, true);
  assert.equal(env.saves.length, 0);
});

test('permanent Agent deletion uses concurrency tokens and replacement fallback', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => renderer.root.findByProps({'aria-label':'Delete agent'}).props.onClick());
  await act(async () => button(renderer, 'Confirm permanent delete').props.onClick());
  assert.equal(env.saves[0].replacement_fallback_agent_id, 2);
  assert.equal(env.saves[0].expected_updated_at, '2026-10-23T01:00:00');
  assert.deepEqual(renderer.root.findByType('workflow-graph').props.agents.map(agent => agent.id), [2]);
});

test('provider creation updates only the captured draft without navigation', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => renderer.root.findByProps({'aria-label':'Create provider'}).props.onClick());
  await select(renderer, 2);
  await act(async () => renderer.root.findByType('provider-modal').props.onCreated(3));
  assert.equal(renderer.root.findByProps({id:'workflow-provider'}).props.value, 1);
  await select(renderer, 1);
  assert.equal(renderer.root.findByProps({id:'workflow-provider'}).props.value, 3);
  assert.deepEqual(env.routes, []);
});

test('membership refresh drops drafts for removed or newly shared agents and preserves new drafts', async (t) => {
  const env = setup(t); const library = env.load('src/lib/workflow-authoring.ts');
  const domain = env.load('src/lib/team-workflow.ts'); const old = snapshot();
  const first = domain.createAgentDraft(old.agents[0], old.fallback_agent_id); first.name = 'Draft one';
  const second = domain.createAgentDraft(old.agents[1], old.fallback_agent_id); second.name = 'Draft two';
  const newAgent = library.createNewWorkflowAgent(old); newAgent.draft.instructions = 'Keep new draft';
  const state = {status:'ready',workflow:old,drafts:{1:first,2:second},selection:{kind:'agent',agentId:1},newAgent};
  const updated = structuredClone(old); updated.agents = [updated.agents[1]]; updated.agents[0].shared = true; updated.fallback_agent_id = 2;
  const result = library.reconcileWorkflow(state, updated);
  assert.deepEqual(result.drafts, {}); assert.equal(result.newAgent.requestId, newAgent.requestId);
  assert.equal(result.newAgent.draft.instructions, 'Keep new draft'); assert.deepEqual(result.selection,{kind:'agent',agentId:2});
});

test('membership refresh keeps an independently drafted fallback guarded by its original snapshot', async (t) => {
  const env = setup(t); const library = env.load('src/lib/workflow-authoring.ts'); const domain = env.load('src/lib/team-workflow.ts');
  const old = snapshot(); const draft = domain.createAgentDraft(old.agents[1], 1); draft.is_fallback = true;
  const next = structuredClone(old); next.fallback_agent_id = 2;
  const result = library.reconcileWorkflow({status:'ready',workflow:old,drafts:{2:draft},selection:{kind:'agent',agentId:2},newAgent:null}, next);
  assert.equal(result.drafts[2].is_fallback, true); assert.equal(result.drafts[2].expected_fallback_agent_id, 1);
});

test('reviewed optimization applies to the draft without automatically saving', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => button(renderer, 'Optimize').props.onClick());
  await act(async () => button(renderer, 'Apply suggestion').props.onClick());
  assert.equal(renderer.root.findByProps({id:'workflow-instructions'}).props.value, 'Reviewed optimized instructions');
  assert.equal(env.saves.length,0); assert.equal(button(renderer,'Save agent').props.disabled,false);
});

test('membership commit with failed refresh retries only the snapshot request', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await act(async () => button(renderer,'Members').props.onClick()); env.controls.failRefresh = true;
  await act(async () => { await assert.rejects(renderer.root.findByType('members-panel').props.onSave([2,1],2,[1,2],1)); });
  assert.equal(env.saves.length,1); assert.equal(button(renderer,'Members').props.disabled,true);
  env.controls.failRefresh = false;
  await act(async () => button(renderer,'Refresh workflow').props.onClick());
  assert.equal(env.saves.length,1); assert.equal(renderer.root.findByType('workflow-graph').props.fallbackAgentId,2);
});

test('deleting a non-fallback Agent retains the existing team fallback', async (t) => {
  const env = setup(t); const renderer = await env.mount();
  await select(renderer, 2);
  await act(async () => renderer.root.findByProps({'aria-label':'Delete agent'}).props.onClick());
  await act(async () => button(renderer, 'Confirm permanent delete').props.onClick());
  assert.equal(env.saves[0].replacement_fallback_agent_id, 1);
  assert.deepEqual(renderer.root.findByType('workflow-graph').props.agents.map(agent => agent.id), [1]);
});


test('Workflow creates with runtime defaults and preserves restored custom drafts', async (t) => {
  const data = snapshot(); data.agents = []; data.fallback_agent_id = null;
  const env = setup(t, data); let renderer = await env.mount();
  await act(async () => button(renderer, 'Create agent').props.onClick());
  assert.equal(renderer.root.findByProps({ id: 'workflow-model' }).props.value, 'runtime-agent-model');
  assert.deepEqual(renderer.root.findByProps({ id: 'workflow-models' }).findAllByType('option').map(node => node.props.value), ['runtime-agent-model', 'runtime-second-model']);
  await change(renderer, 'workflow-model', 'saved/custom-model');
  await act(async () => renderer.unmount());
  data.default_agent_model = 'changed-server-default';
  renderer = await env.mount();
  assert.equal(renderer.root.findByProps({ id: 'workflow-model' }).props.value, 'saved/custom-model');
});

test('Workflow without a runtime default leaves the new model blank', () => {
  const load = modules();
  const data = snapshot(); delete data.default_agent_model;
  const parsed = load('src/lib/team-workflow.ts').parseTeamWorkflow(data);
  const draft = load('src/lib/workflow-authoring.ts').createNewWorkflowAgent(parsed);
  assert.equal(draft.draft.model, '');
  assert.throws(() => load('src/lib/team-workflow.ts').parseTeamWorkflow({ ...data, default_agent_model: 42 }), /Invalid workflow/);
});

test('runtime model defaults validate the boundary and preserve arbitrary IDs', () => {
  const parse = modules()('src/lib/provider-models.ts').parseAgentModelDefaults;
  assert.deepEqual(parse({ default_agent_model: ' local/model-v9 ', agent_models: [' other/v3 ', 'local/model-v9'] }), {
    default_agent_model: 'local/model-v9', agent_models: ['local/model-v9', 'other/v3'],
  });
  for (const invalid of [null, [], { default_agent_model: '', agent_models: [] }, { default_agent_model: 'id', agent_models: [1] }]) {
    assert.throws(() => parse(invalid), /Invalid model defaults/);
  }
});

test('late Workflow defaults cannot replace options for a different provider', async (t) => {
  const env = setup(t);
  const originalFetch = global.fetch;
  let finish;
  global.fetch = (url, init) => url.endsWith('/model-defaults') ? new Promise(resolve => { finish = resolve; }) : originalFetch(url, init);
  const renderer = await env.mount();
  await change(renderer, 'workflow-provider', '1');
  await change(renderer, 'workflow-model', 'typed/custom-model');
  await act(async () => finish(response({ default_agent_model: 'late/default', agent_models: ['late/default'] })));
  const options = renderer.root.findByProps({ id: 'workflow-models' }).findAllByType('option').map(node => node.props.value);
  assert.deepEqual(options.sort(), ['discovered-model', 'registered-model']);
  assert.equal(renderer.root.findByProps({ id: 'workflow-model' }).props.value, 'typed/custom-model');
});

test('Workflow keeps manual model entry usable when defaults are unavailable', async (t) => {
  const env = setup(t);
  const originalFetch = global.fetch;
  global.fetch = (url, init) => url.endsWith('/model-defaults') ? Promise.resolve(response({ detail: 'Unavailable' }, 503)) : originalFetch(url, init);
  const renderer = await env.mount();
  assert.ok(renderer.root.findAllByProps({ role: 'status' }).some(node => /enter a model ID/.test(text(node))));
  await change(renderer, 'workflow-model', 'manual/local-model');
  await save(renderer);
  assert.equal(env.saves[0].model, 'manual/local-model');
});

test('canvas Add agent is a native action independent of handoff editing', async () => {
  const Flow = () => null; const stub = () => null;
  const load = modules({ reactflow: { __esModule: true, default: Flow, Background: stub, Controls: stub, Handle: stub, MarkerType: { ArrowClosed: 'arrowclosed' }, Position: { Bottom: 'bottom', Top: 'top', Left: 'left', Right: 'right' } } });
  const Graph = load('src/components/AgentFlowGraph.tsx').default;
  const data = snapshot(); let calls = 0; let tree;
  const props = { agents: data.agents, tools: data.tools, fallbackAgentId: 1, selectedAgentId: 1, onSelect() {}, canEdit: true, onAddAgent: () => calls++ };
  try {
    await act(async () => { tree = create(React.createElement(Graph, props)); });
    const action = button(tree, 'Add agent');
    assert.ok(action, 'Editable canvas must expose Add agent without a handoff callback');
    assert.equal(action.props.type, 'button');
    assert.equal(action.props['aria-controls'], 'workflow-agent-inspector');
    assert.equal(tree.root.findByType(Flow).props.nodes.length, 3);
    await act(async () => action.props.onClick());
    assert.equal(calls, 1);
    await act(async () => tree.update(React.createElement(Graph, { ...props, hasNewAgentDraft: true, disabled: true })));
    assert.equal(button(tree, 'Continue new agent').props.disabled, true);
    await act(async () => tree.update(React.createElement(Graph, { ...props, canEdit: false })));
    assert.equal(button(tree, 'Add agent'), undefined);
    await act(async () => tree.update(React.createElement(Graph, { ...props, onAddAgent: undefined })));
    assert.equal(button(tree, 'Add agent'), undefined);
  } finally { if (tree) await act(async () => tree.unmount()); }
});

test('canvas creation preserves one unsaved draft across repeat and resume actions', async t => {
  const env = setup(t); const renderer = await env.mount();
  const graph = () => renderer.root.findByType('workflow-graph');
  assert.equal(graph().props.hasNewAgentDraft, false);
  await act(async () => graph().props.onAddAgent());
  const requestId = JSON.parse(env.storage.get('team-workflow-new:1')).requestId;
  await change(renderer, 'workflow-agent-name', 'Canvas draft');
  await act(async () => graph().props.onAddAgent());
  await select(renderer, 2);
  await act(async () => graph().props.onAddAgent());
  assert.equal(renderer.root.findByProps({ id: 'workflow-agent-name' }).props.value, 'Canvas draft');
  assert.equal(JSON.parse(env.storage.get('team-workflow-new:1')).requestId, requestId);
  assert.equal(graph().props.hasNewAgentDraft, true);
  assert.deepEqual(graph().props.agents.map(agent => agent.id), [1, 2]);
  assert.equal(env.creates.length, 0); assert.equal(env.saves.length, 0);
  await act(async () => button(renderer, 'Discard').props.onClick());
  assert.equal(graph().props.hasNewAgentDraft, false);
  await act(async () => graph().props.onAddAgent());
  await change(renderer, 'workflow-agent-name', 'Saved canvas agent');
  await change(renderer, 'workflow-instructions', 'Handle canvas requests');
  await save(renderer);
  assert.equal(env.creates.length, 1);
  assert.equal(graph().props.hasNewAgentDraft, false);
});

test('canvas creation obeys resource editor, saving, and refresh error guards', async t => {
  const env = setup(t); const renderer = await env.mount();
  const graph = () => renderer.root.findByType('workflow-graph');
  await act(async () => button(renderer, 'Tool').props.onClick());
  assert.equal(graph().props.disabled, true);
  await act(async () => graph().props.onAddAgent());
  assert.equal(graph().props.hasNewAgentDraft, false);
  await act(async () => renderer.root.findByType('tool-creator').props.onClose());
  await change(renderer, 'workflow-agent-name', 'Save pending');
  let release; env.controls.saveGate = new Promise(resolve => { release = resolve; });
  let pending;
  await act(async () => { pending = renderer.root.findByProps({ 'aria-label': 'Agent settings' }).props.onSubmit({ preventDefault() {} }); });
  assert.equal(graph().props.disabled, true);
  await act(async () => graph().props.onAddAgent());
  assert.equal(graph().props.hasNewAgentDraft, false);
  env.controls.failRefresh = true;
  await act(async () => { release(); await pending; });
  assert.equal(graph().props.disabled, true);
  await act(async () => graph().props.onAddAgent());
  assert.equal(graph().props.hasNewAgentDraft, false);
});

test('new agent actions focus the committed inspector and scroll on mobile only on request', async t => {
  const data = snapshot(); data.agents = []; data.fallback_agent_id = null;
  const env = setup(t, data); const renderer = await env.mount();
  const calls = [];
  global.window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
  global.document.getElementById = id => {
    assert.ok(renderer.root.findByProps({ id }), `${id} must be committed before focus`);
    return { focus: options => calls.push(['focus', id, options]), scrollIntoView: options => calls.push(['scroll', id, options]) };
  };
  await act(async () => button(renderer, 'Create agent').props.onClick());
  assert.deepEqual(calls, [['focus', 'workflow-agent-name', { preventScroll: true }], ['scroll', 'workflow-agent-inspector', { behavior: 'smooth', block: 'start' }]]);
  const inspector = renderer.root.findByProps({ id: 'workflow-agent-inspector' });
  assert.equal(inspector.props.tabIndex, -1);
  assert.equal(inspector.props.role, 'region');
  await change(renderer, 'workflow-agent-name', 'Keep typing');
  assert.equal(calls.length, 2);
  await act(async () => renderer.unmount());
  global.document.getElementById = () => { throw Error('Restored drafts must not take focus'); };
  await env.mount();
});

test('canvas creation focuses the inspector fallback without scrolling desktop', async t => {
  const env = setup(t); const renderer = await env.mount(); const calls = [];
  global.window.matchMedia = () => ({ matches: false });
  global.document.getElementById = id => id === 'workflow-agent-name' ? null : {
    focus: options => calls.push(['focus', options]), scrollIntoView: () => calls.push(['scroll']),
  };
  await act(async () => renderer.root.findByType('workflow-graph').props.onAddAgent());
  assert.deepEqual(calls, [['focus', { preventScroll: true }]]);
  assert.equal(renderer.root.findByType('workflow-graph').props.hasNewAgentDraft, true);
});

test('read only canvas callback cannot create a new Agent', async t => {
  const data = snapshot(); data.can_edit = false;
  const env = setup(t, data); const renderer = await env.mount();
  await act(async () => renderer.root.findByType('workflow-graph').props.onAddAgent());
  assert.equal(renderer.root.findByType('workflow-graph').props.hasNewAgentDraft, false);
  assert.equal(env.storage.has('team-workflow-new:1'), false);
  assert.equal(env.creates.length, 0);
});
