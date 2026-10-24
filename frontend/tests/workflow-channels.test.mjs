import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';

const dependency = createRequire(import.meta.url);
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(name, mocks = {}) {
  const exports = {};
  const source = fs.readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const require = id => Object.hasOwn(mocks, id) ? mocks[id] : dependency(id);
  vm.runInThisContext(`(function(require,exports){${code}\n})`)(require, exports);
  return exports;
}
const helpers = load('lib/workflow-channels.ts');
const key = (changes = {}) => ({ id: 1, name: 'Existing shop', slug: 'shop', key: 'sk_test', team_agent_id: 7, channel_type: 'web_widget', is_active: true, expires_at: null, ...changes });
test('Web Chat choices exclude other teams, channels, inactive and expired links', () => {
  const data = [key(), key({ id: 2, team_agent_id: 8 }), key({ id: 3, channel_type: 'line' }), key({ id: 4, is_active: false }), key({ id: 5, expires_at: '2026-10-23T00:00:00' }), key({ id: 6, slug: '"><script>' })];
  assert.deepEqual(helpers.parseWorkflowWebChats(data, 7, Date.parse('2026-10-24T00:00:00Z')).map(item => item.id), [1]);
  assert.equal(helpers.workflowChatUrl('https://example.com', helpers.parseWorkflowWebChats(data, 7)[0]), 'https://example.com/c/shop?type=chat');
  assert.match(helpers.workflowChatEmbed('https://example.com', helpers.parseWorkflowWebChats(data, 7)[0]), /data-type="chat"/);
  assert.throws(() => helpers.parseWorkflowWebChats({}, 7));
});
const text = node => typeof node === 'string' ? node : (node.children ?? []).map(text).join(' ');
function button(view, label) { return view.root.findAllByType('button').find(node => text(node).trim() === label); }
test('Visiting and choosing existing channels never creates one; new channel requires confirmation', async t => {
  const prior = global.window;
  global.window = { location: { origin: 'https://example.com' } };
  t.after(() => { global.window = prior; });
  const calls = [];
  let data = [key()];
  const Component = load('components/WorkflowChannels.tsx', {
    '@/lib/team-workflow': { workflowRequest: async (path, init) => {
      calls.push({ path, init });
      if (init?.method === 'POST') { data = [...data, key({ id: 9, name: 'Top Web Chat', slug: 'new-shop' })]; return { message: 'created' }; }
      return data;
    } },
    '@/lib/workflow-channels': helpers,
    '@/components/WorkflowPanelDialog': { default: ({ children }) => React.createElement('div', null, children) },
  }).default;
  let view;
  await act(async () => { view = create(React.createElement(Component, { teamId: 7, teamName: 'Top', canEdit: true, hasDrafts: true })); });
  assert.equal(calls.filter(call => call.init?.method === 'POST').length, 0);
  assert.equal(view.root.findAllByType('a')[0].props.href, 'https://example.com/c/shop?type=chat');
  await act(async () => button(view, 'New Web Chat').props.onClick());
  assert.equal(calls.filter(call => call.init?.method === 'POST').length, 0);
  await act(async () => view.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  const writes = calls.filter(call => call.init?.method === 'POST');
  assert.equal(writes.length, 1);
  assert.deepEqual(JSON.parse(writes[0].init.body), { name: 'Top Web Chat', team_agent_id: 7, channel_type: 'web_widget', voice_response_enabled: false });
  assert.equal(view.root.findAllByType('a')[0].props.href, 'https://example.com/c/new-shop?type=chat');
  await act(async () => view.unmount());
});
test('An uncertain creation disables re-submission until channels have been refreshed', async t => {
  const prior = global.window;
  global.window = { location: { origin: 'https://example.com' } };
  t.after(() => { global.window = prior; });
  let writes = 0;
  const Component = load('components/WorkflowChannels.tsx', {
    '@/lib/team-workflow': { workflowRequest: async (_path, init) => { if (init?.method === 'POST') { writes++; throw Error('lost response'); } return [key()]; } },
    '@/lib/workflow-channels': helpers,
    '@/components/WorkflowPanelDialog': { default: ({ children }) => React.createElement('div', null, children) },
  }).default;
  let view;
  await act(async () => { view = create(React.createElement(Component, { teamId: 7, teamName: 'Top', canEdit: true, hasDrafts: false })); });
  await act(async () => button(view, 'New Web Chat').props.onClick());
  await act(async () => view.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  assert.equal(writes, 1);
  assert.equal(button(view, 'Create Web Chat'), undefined);
  await act(async () => view.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  assert.equal(writes, 1);
  assert.ok(button(view, 'Refresh channels'));
  await act(async () => view.unmount());
});
