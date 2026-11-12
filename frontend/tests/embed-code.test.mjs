import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';
import { EnglishAdminLocale, adminLocale } from './admin-locale-context.mjs';

const dependencies = createRequire(import.meta.url);
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}, env = {}) {
  const exports = {};
  const source = fs.readFileSync(new URL('../' + file, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  vm.runInThisContext(`(function(require,exports,process){${code}\n})`, { filename: file })(name => Object.hasOwn(mocks, name) ? mocks[name] : dependencies(name), exports, { env });
  return exports;
}
const embed = load('src/lib/embed-code.ts');
const helpers = load('src/lib/workflow-channels.ts', { '@/lib/embed-code': embed });
const api = load('src/lib/api.ts', {}, { NEXT_PUBLIC_API_URL: 'https://gateway.example/service/' });
const labels = tree => tree.root.findAllByType('button').map(button => ({ button, text: button.findAllByType('svg').length ? button.children.filter(child => typeof child === 'string').join('') : button.children.join('') }));

test('snippets resolve the configured public gateway and preserve every existing option', () => {
  const code = embed.widgetEmbedCode({ baseUrl: api.getApiBaseUrl(), apiKey: 'fake-"<&-key', type: 'chat', position: 'bottom-left', allowToggle: false, lang: 'en', async: true });
  assert.match(code, /src="https:\/\/gateway.example\/service\/embed.js"/);
  assert.match(code, /data-server-url="https:\/\/gateway.example\/service"/);
  assert.match(code, /data-api-key="fake-&quot;&lt;&amp;-key"/);
  for (const attribute of ['data-type="chat"', 'data-position="bottom-left"', 'data-allow-toggle="false"', 'data-lang="en"', ' async>']) assert.ok(code.includes(attribute));
  assert.doesNotMatch(code, /widget\.js/);
  assert.throws(() => embed.widgetEmbedCode({ baseUrl: 'javascript:alert(1)', apiKey: 'fake' }));
  assert.throws(() => embed.widgetEmbedCode({ baseUrl: 'https://user:pass@example.com', apiKey: 'fake' }));
});

test('public base follows repository configuration across Dev and public environments', t => {
  const previous = globalThis.window;
  t.after(() => { globalThis.window = previous; });
  for (const [env, origin, expected] of [
    [{}, 'http://localhost:3000', 'http://localhost:3000'],
    [{ NEXT_PUBLIC_API_URL: 'https://localhost:18443' }, 'https://dev.example', 'https://dev.example'],
    [{ NEXT_PUBLIC_API_URL: 'https://gateway.example/' }, 'https://admin.example', 'https://gateway.example'],
  ]) {
    globalThis.window = { location: { origin } };
    const resolved = load('src/lib/api.ts', {}, env).getApiBaseUrl();
    assert.equal(resolved, expected);
    assert.ok(embed.widgetEmbedCode({ baseUrl: resolved, apiKey: 'fake' }).includes(`src="${expected}/embed.js"`));
  }
});

test('legacy widget.js is an internal rewrite to the single public implementation', async () => {
  const config = load('next.config.ts').default;
  const aliases = await config.rewrites();
  assert.deepEqual(aliases, [{ source: '/widget.js', destination: '/embed.js' }]);
  assert.equal(fs.existsSync(new URL('../public/widget.js', import.meta.url)), false);
});

test('Channels editor Copy code exactly matches the displayed snippet, with configured URL', async t => {
  const previous = { window: globalThis.window, navigator: globalThis.navigator };
  const copied = [];
  globalThis.window = { location: { origin: 'https://admin.example' }, addEventListener() {}, removeEventListener() {} };
  Object.defineProperty(globalThis, 'navigator', { value: { clipboard: { writeText: async text => copied.push(text) } }, configurable: true });
  t.after(() => { globalThis.window = previous.window; Object.defineProperty(globalThis, 'navigator', { value: previous.navigator, configurable: true }); });
  const draft = { name: 'Fixture channel', is_active: true, config: {}, allowed_domains: 'shop.example', voice_response_enabled: false, expires_at: null, updated_at: 'test', api_key: 'fake-only-key' };
  const Component = load('src/components/ChannelOverviewEditor.tsx', {
    '@/lib/api': api, '@/lib/embed-code': embed, '@/lib/admin-locale': adminLocale,
    '@/components/ui/Button': { Button: ({ children, ...props }) => React.createElement('button', props, children) },
    '@/components/WidgetThemeEditor': { default: () => null },
    '@/lib/channels-overview': { loadChannelDraft: async () => draft, saveChannelDraft: () => assert.fail('Unexpected write'), channelDate: () => '' },
  }).default;
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(EnglishAdminLocale, null, React.createElement(Component, { row: { kind: 'web', id: 7, name: 'Fixture', team_name: 'Fixture', slug: 'fake' }, onClose() {}, onSaved() {} }))); });
    const snippet = tree.root.findAllByType('textarea').find(node => node.props.readOnly).props.value;
    assert.match(snippet, /https:\/\/gateway.example\/service\/embed.js/);
    assert.match(snippet, /data-server-url=/);
    const copy = labels(tree).find(({ text }) => text === 'Copy code').button;
    await act(async () => copy.props.onClick());
    assert.deepEqual(copied, [snippet]);
  } finally { if (tree) await act(async () => tree.unmount()); }
});

test('Team Channels Copy code matches its displayed embed snippet', async t => {
  const previous = globalThis.navigator;
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', { value: { clipboard: { writeText: async text => copied.push(text) } }, configurable: true });
  t.after(() => { Object.defineProperty(globalThis, 'navigator', { value: previous, configurable: true }); });
  const Component = load('src/components/WorkflowChannels.tsx', {
    '@/lib/api': api, '@/lib/workflow-channels': helpers,
    '@/lib/team-workflow': { workflowRequest: async (_path, init) => { assert.equal(init?.method, undefined); return [{ id: 1, name: 'Fixture', slug: 'fake', key: 'fake-only-key', team_agent_id: 7, channel_type: 'web_widget', is_active: true }]; } },
    '@/components/WorkflowPanelDialog': { default: ({ children }) => React.createElement('div', null, children) },
  }).default;
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(Component, { teamId: 7, teamName: 'Fixture', canEdit: true, hasDrafts: false })); });
    await act(async () => labels(tree).find(({ text }) => text === 'Embed').button.props.onClick());
    const snippet = tree.root.findByType('textarea').props.value;
    await act(async () => labels(tree).find(({ text }) => text === 'Copy code').button.props.onClick());
    assert.deepEqual(copied, [snippet]);
    assert.match(snippet, /src="https:\/\/gateway.example\/service\/embed.js"/);
  } finally { if (tree) await act(async () => tree.unmount()); }
});

test('legacy widget setup Copy Code keeps its configured snippet and selected channel attributes', async t => {
  const previous = { navigator: globalThis.navigator, localStorage: globalThis.localStorage };
  const copied = [];
  Object.defineProperty(globalThis, 'navigator', { value: { clipboard: { writeText: async text => copied.push(text) } }, configurable: true });
  globalThis.localStorage = { getItem: () => 'fake-admin-only' };
  t.after(() => { Object.defineProperty(globalThis, 'navigator', { value: previous.navigator, configurable: true }); globalThis.localStorage = previous.localStorage; });
  const Component = load('src/app/admin/tools/widget/page.tsx', {
    '@/lib/api': api, '@/lib/embed-code': embed,
    '@/components/ui/Button': { Button: ({ children, ...props }) => React.createElement('button', props, children) },
    '@/components/icons/MicIcon': { default: () => null }, '@/components/icons/WriteIcon': { default: () => null },
    '@/components/WidgetThemeEditor': { default: () => null }, '@/components/ChannelConfigForm': { default: () => null },
    '@/components/ApiKeyManager': { ApiKeyManager: props => React.createElement('button', { onClick: () => props.onApiKeySelect('fake-only-key') }, 'Select fixture key') },
    '@/lib/team-context': { useTeam: () => ({ teams: [{ id: 7, name: 'Fixture' }], selectedTeam: { id: 7, name: 'Fixture' }, selectedTeamId: 7, setSelectedTeamId() {}, loading: false }) },
    '@/lib/channelConfigs': { getChannelConfigs: async () => [] }, '@/lib/apiKeys': { getAllApiKeys: async () => [{ id: 1, key: 'fake-only-key', is_active: true }] },
  }).default;
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(Component)); });
    await act(async () => labels(tree).find(({ text }) => text === 'Select fixture key').button.props.onClick());
    for (let step = 0; step < 3; step++) await act(async () => labels(tree).find(({ text }) => text === 'Next').button.props.onClick());
    const snippet = tree.root.findByType('textarea').props.value;
    await act(async () => labels(tree).find(({ text }) => text === 'Copy Code').button.props.onClick());
    assert.deepEqual(copied, [snippet]);
    assert.ok(tree.root.findAllByType('a').some(node => node.props.href?.startsWith('https://gateway.example/service/test_widget.html?')));
    for (const value of ['https://gateway.example/service/embed.js', 'data-server-url="https://gateway.example/service"', 'data-type="voice"', 'data-position="bottom-right"', 'data-allow-toggle="true"', 'data-api-key="fake-only-key"']) assert.ok(snippet.includes(value));
  } finally { if (tree) await act(async () => tree.unmount()); }
});
