import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ts from 'typescript';

const dependency = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}) {
  const source = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename: file })(name => Object.hasOwn(mocks, name) ? mocks[name] : dependency(name), exports);
  return exports;
}
const presentations = load('src/lib/product-presentations.ts');
const helpers = load('src/lib/workflow-preview.ts', { '@/lib/product-presentations': presentations });
const workflowApi = load('src/lib/team-workflow.ts');
const agent = { id: 1, name: 'Support', instructions: 'Help', model: 'model', llm_provider_id: null, tool_ids: [1], handoff_agent_ids: [], shared: false, updated_at: 'today' };
const workflow = { team_id: 1, team_name: 'Team', can_edit: true, fallback_agent_id: 1, agents: [agent, { ...agent, id: 2, name: 'Sales' }], tools: [], providers: [] };
const session = id => ({ id, target_agent_id: null, has_drafts: false, blocked_tools: ['SendEmail'], expires_in_seconds: 1800 });
const reply = response => ({ response, agent_name: 'Support', presentations: {}, tool_calls: [], citations: [] });
const text = node => typeof node === 'string' ? node : (node.children ?? []).map(text).join(' ');
const button = (renderer, label) => renderer.root.findAllByType('button').find(node => text(node).trim() === label);
function deferred() { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
async function setup(t, request, extra = {}, strict = false) {
  const originalWindow = global.window;
  global.window = { confirm: () => true };
  const Component = load('src/components/WorkflowPreviewChat.tsx', {
    '@/lib/workflow-preview': helpers, '@/lib/team-workflow': { workflowRequest: request },
    'react-markdown': { default: ReactMarkdown }, 'remark-gfm': { default: remarkGfm },
    '@/lib/markdown': { normalizeMarkdownForChat: value => value },
    '@/components/KnowledgeImages': { KnowledgeImages: props => React.createElement('images-test', props) },
    '@/components/KnowledgeAudio': { KnowledgeAudio: props => React.createElement('audio-test', props) },
    '@/components/ProductCarousel': { ProductCarousel: props => React.createElement('carousel-test', props) },
  }).default;
  const props = { teamId: 1, workflow, drafts: {}, targetAgentId: null, visible: true, onTargetChange() {}, onEditAgent() {}, onOpenKnowledge() {}, ...extra };
  const render = () => strict ? React.createElement(React.StrictMode, null, React.createElement(Component, props)) : React.createElement(Component, props);
  let renderer;
  await act(async () => { renderer = create(render()); });
  t.after(async () => { await act(async () => renderer.unmount()); global.window = originalWindow; });
  return {
    renderer, props,
    async update(next) { Object.assign(props, next); await act(async () => renderer.update(render())); },
    async compose(value) { await act(async () => renderer.root.findByType('textarea').props.onChange({ target: { value } })); },
    async send() { await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} })); },
  };
}

test('preview requests freeze drafts and settings changes have a stable signature', () => {
  const draft = workflowApi.createAgentDraft(agent, 1);
  const drafts = { 1: draft, 99: draft };
  const snapshot = helpers.previewDrafts(workflow, drafts);
  assert.deepEqual(snapshot.map(item => item.agent_id), [1]);
  assert.equal('expected_updated_at' in snapshot[0].draft, false);
  assert.equal('expected_fallback_agent_id' in snapshot[0].draft, false);
  const before = helpers.previewSignature(workflow, drafts);
  draft.instructions = 'Changed';
  draft.tool_ids.push(2);
  assert.equal(snapshot[0].draft.instructions, 'Help');
  assert.deepEqual(snapshot[0].draft.tool_ids, [1]);
  assert.notEqual(helpers.previewSignature(workflow, drafts), before);
  assert.equal(helpers.previewSignature(workflow, {}), helpers.previewSignature({ ...workflow, agents: [...workflow.agents].reverse() }, {}));
  assert.notEqual(helpers.previewTargetKey(1, null), helpers.previewTargetKey(1, 1));
  assert.notEqual(helpers.previewTargetKey(1, 1), helpers.previewTargetKey(2, 1));
  const a = helpers.createPreviewConversation(); const b = helpers.createPreviewConversation();
  a.composer = 'Team question'; a.messages.push({ kind: 'user', content: 'Hi' });
  assert.equal(b.composer, ''); assert.deepEqual(b.messages, []);
});

test('session parsing validates the boundary and expiry errors require restart', () => {
  assert.equal(helpers.parsePreviewSession(session('one'), 1000).expiresAt, 1801000);
  for (const invalid of [{}, { ...session('one'), expires_in_seconds: -1 }, { ...session('one'), target_agent_id: '1' }, { ...session('one'), blocked_tools: [4] }]) {
    assert.throws(() => helpers.parsePreviewSession(invalid));
  }
  assert.equal(helpers.previewError(new Error('Preview session expired')).expired, true);
  assert.match(helpers.previewError(new Error('Preview not found')).message, /Restart/);
  assert.equal(helpers.previewError(new Error('Network failed')).expired, false);
  assert.throws(() => helpers.parsePreviewReply({ response: 'unsafe' }));
});

test('product inquiry generates a local chat message for a validated card', () => {
  const cards = { call: { type: 'product_carousel', version: 1, summary: 'Found', products: [{ id: 'one', title: 'Pump', part_number: 'P1' }] } };
  assert.equal(helpers.previewProductInquiry(cards, 'call', 'one'), 'Tell me more about Pump (P1).');
  assert.equal(helpers.previewProductInquiry(cards, 'call', 'missing'), null);
  assert.equal(helpers.previewProductInquiry(cards, 'missing', 'one'), null);
});

test('targets preserve separate composer and conversation while replies are pending', async t => {
  const pending = deferred(); const calls = [];
  const ui = await setup(t, async (url, init) => {
    calls.push({ url, init });
    if (init.method === 'DELETE') return { success: true };
    if (url.endsWith('/messages')) return pending.promise;
    return session('team-session');
  });
  await ui.compose('Team hello'); await ui.send();
  await ui.update({ targetAgentId: 1 });
  assert.equal(ui.renderer.root.findByType('textarea').props.value, '');
  await ui.compose('Direct unsent');
  await act(async () => pending.resolve(reply('Team reply')));
  assert.doesNotMatch(text(ui.renderer.toJSON()), /Team reply/);
  await ui.update({ targetAgentId: null, visible: false });
  assert.match(text(ui.renderer.toJSON()), /Team reply/);
  await ui.update({ targetAgentId: 1, visible: true });
  assert.equal(ui.renderer.root.findByType('textarea').props.value, 'Direct unsent');
  assert.equal(calls.filter(call => call.init.method === 'POST').length, 2);
});

test('late session creation after restart is discarded and deleted', async t => {
  const pending = deferred(); const calls = [];
  const ui = await setup(t, async (url, init) => {
    calls.push({ url, init });
    if (init.method === 'DELETE') return { success: true };
    return pending.promise;
  });
  await ui.compose('Hello'); await ui.send();
  await act(async () => button(ui.renderer, 'Restart').props.onClick());
  await act(async () => pending.resolve(session('late')));
  assert.equal(calls.some(call => call.url.endsWith('/late') && call.init.method === 'DELETE'), true);
  assert.equal(calls.some(call => call.url.endsWith('/messages')), false);
  assert.equal(ui.renderer.root.findByType('textarea').props.value, 'Hello');
  assert.doesNotMatch(text(ui.renderer.toJSON()), /Thinking/);
});

test('expired conversations never silently recreate or replay and restart uses current drafts', async t => {
  const calls = [];
  const ui = await setup(t, async (url, init) => {
    calls.push({ url, init });
    if (init.method === 'DELETE') return { success: true };
    if (url.endsWith('/messages')) throw new Error('Preview expired');
    return session(`session-${calls.length}`);
  });
  await ui.compose('Hello'); await ui.send();
  assert.match(text(ui.renderer.toJSON()), /Restart.*continue/);
  await ui.compose('Retry'); await ui.send();
  assert.equal(calls.length, 2);
  const draft = workflowApi.createAgentDraft(agent, 1); draft.instructions = 'New instructions';
  await ui.update({ drafts: { 1: draft } });
  assert.match(text(ui.renderer.toJSON()), /settings changed/);
  await act(async () => button(ui.renderer, 'Restart').props.onClick());
  await ui.send();
  const creates = calls.filter(call => call.init.method === 'POST' && !call.url.endsWith('/messages'));
  assert.equal(creates.length, 2);
  assert.equal(JSON.parse(creates[1].init.body).drafts[0].draft.instructions, 'New instructions');
});

test('Strict Mode lifecycle retains a usable session and unmount deletes it', async t => {
  const calls = [];
  const ui = await setup(t, async (url, init) => {
    calls.push({ url, init });
    return url.endsWith('/messages') ? reply('Ready') : session('strict-session');
  }, {}, true);
  await ui.compose('Hi'); await ui.send();
  assert.match(text(ui.renderer.toJSON()), /Ready/);
  await act(async () => { ui.renderer.unmount(); await new Promise(resolve => setImmediate(resolve)); });
  assert.equal(calls.some(call => call.url.endsWith('/strict-session') && call.init.method === 'DELETE'), true, JSON.stringify(calls));
});

test('changing teams discards pending replies and removes the previous session', async t => {
  const pending = deferred(); const calls = [];
  const ui = await setup(t, async (url, init) => {
    calls.push({ url, init });
    if (init.method === 'DELETE') return { success: true };
    if (url.endsWith('/messages')) return pending.promise;
    return session('old-team');
  });
  await ui.compose('Old question'); await ui.send();
  await ui.update({ teamId: 2, workflow: { ...workflow, team_id: 2 } });
  await act(async () => pending.resolve(reply('Old answer')));
  assert.doesNotMatch(text(ui.renderer.toJSON()), /Old answer|Old question/);
  assert.equal(calls.some(call => call.url === '/team-agents/1/workflow/previews/old-team' && call.init.method === 'DELETE'), true);
});

test('Markdown and product actions stay inside preview while Knowledge and edit use workspace callbacks', async t => {
  const calls = []; let knowledge = 0; const edits = [];
  const cards = { lookup: { type: 'product_carousel', version: 1, summary: 'Found pump', products: [{ id: 'pump', title: 'Pump', description: 'Product details' }] } };
  const ui = await setup(t, async (url, init) => {
    calls.push({ url, init });
    if (init.method === 'DELETE') return { success: true };
    return url.endsWith('/messages') ? { ...reply('## Result\n\n**A pump**'), presentations: cards, citations: [{ title: 'Catalog' }] } : session('products');
  }, { onOpenKnowledge: () => knowledge++, onEditAgent: id => edits.push(id) });
  assert.equal(calls.length, 0);
  await ui.compose('Find pump'); await ui.send();
  assert.equal(ui.renderer.root.findByType('h2').children.join(''), 'Result');
  assert.equal(ui.renderer.root.findByType('strong').children.join(''), 'A pump');
  const carousel = ui.renderer.root.findByType('carousel-test');
  assert.equal(carousel.props.disabled, false);
  await act(async () => carousel.props.onInquire('pump'));
  const last = calls.filter(call => call.url.endsWith('/messages')).at(-1);
  assert.equal(JSON.parse(last.init.body).message, 'Tell me more about Pump.');
  await act(async () => ui.renderer.root.findAllByType('button').find(node => text(node).startsWith('Knowledge sources')).props.onClick());
  await act(async () => button(ui.renderer, 'Edit agent').props.onClick());
  assert.equal(knowledge, 1);
  assert.deepEqual(edits, [1]);
  assert.equal(calls.every(call => call.url.startsWith('/team-agents/1/workflow/previews')), true);
});

test('canceling restart retains the conversation and the original frozen settings', async t => {
  const calls = [];
  const ui = await setup(t, async (url, init) => {
    calls.push({ url, init });
    return url.endsWith('/messages') ? reply('Keep this answer') : session('kept');
  });
  await ui.compose('Hello'); await ui.send();
  global.window.confirm = () => false;
  await act(async () => button(ui.renderer, 'Restart').props.onClick());
  assert.match(text(ui.renderer.toJSON()), /Keep this answer/);
  assert.equal(calls.filter(call => call.init.method === 'DELETE').length, 0);
  await ui.compose('Next'); await ui.send();
  assert.equal(calls.filter(call => call.init.method === 'POST' && !call.url.endsWith('/messages')).length, 1);
});
