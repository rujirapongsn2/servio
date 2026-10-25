import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const exports = {};
const source = ts.transpileModule(fs.readFileSync(new URL('../src/components/SystemInformation.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
vm.runInThisContext(`(function(require,exports){${source}\n})`)(require, exports);
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const snapshot = {
  services: [{ id: 'db', label: 'PostgreSQL', status: 'healthy', detail: 'Health check passed' }],
  checked_at: '2026-10-25T12:00:00Z', backend_url: 'https://test', frontend_origin: null,
  server_time: '2026-10-25T12:00:00Z', python_version: '3.11', mcp_enabled: true,
  openai_api_key_set: true, agents_count: 1, tools_count: 2,
};

test('refresh retains stale results on failure, skips overlap and cleans up hidden/unmounted requests', async () => {
  const previous = { fetch: globalThis.fetch, document: globalThis.document, localStorage: globalThis.localStorage,
    setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval };
  let visibility;
  let tick;
  let activeTimers = 0;
  const requests = [];
  globalThis.document = {
    visibilityState: 'visible',
    addEventListener: (event, callback) => { visibility = callback; },
    removeEventListener: (event, callback) => { assert.equal(callback, visibility); visibility = null; },
  };
  globalThis.localStorage = { getItem: () => 'test-only' };
  globalThis.setInterval = (callback, delay) => { assert.equal(delay, 30000); tick = callback; activeTimers++; return 1; };
  globalThis.clearInterval = id => { if (id) activeTimers = 0; };
  globalThis.fetch = (url, options) => new Promise(resolve => requests.push({ url, options, resolve }));
  let tree;
  const renderText = () => JSON.stringify(tree.toJSON());
  try {
    await act(async () => { tree = create(React.createElement(exports.SystemInformation, { apiBaseUrl: '' })); });
    assert.equal(requests.length, 1);
    assert.equal(requests[0].options.cache, 'no-store');
    await act(async () => tick());
    assert.equal(requests.length, 1);
    await act(async () => requests[0].resolve({ ok: true, json: async () => snapshot }));
    assert.match(renderText(), /Healthy/);
    const button = tree.root.findByType('button');
    await act(async () => button.props.onClick());
    await act(async () => requests[1].resolve({ ok: false }));
    assert.match(renderText(), /Showing last successful check/);
    assert.match(renderText(), /PostgreSQL/);
    await act(async () => tick());
    assert.equal(requests.length, 3);
    await act(async () => { document.visibilityState = 'hidden'; visibility(); });
    assert.equal(activeTimers, 0);
    assert.equal(requests[2].options.signal.aborted, true);
    await act(async () => requests[2].resolve({ ok: true, json: async () => ({ ...snapshot, services: [] }) }));
    assert.match(renderText(), /PostgreSQL/);
    await act(async () => tick());
    assert.equal(requests.length, 3);
    await act(async () => { document.visibilityState = 'visible'; visibility(); });
    assert.equal(requests.length, 4);
    await act(async () => tree.unmount());
    tree = null;
    assert.equal(requests[3].options.signal.aborted, true);
    assert.equal(activeTimers, 0);
    assert.equal(visibility, null);
    await act(async () => requests[3].resolve({ ok: true, json: async () => snapshot }));
  } finally {
    if (tree) await act(async () => tree.unmount());
    Object.assign(globalThis, previous);
  }
});

test('settings removes all initial credentials and mounts monitoring only under General', () => {
  const page = fs.readFileSync(new URL('../src/app/admin/settings/page.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(page, /Initial Admin Credentials|admin123|Fresh database only|Existing deployments keep|const \[sys/);
  assert.match(page, /activeTab === "general" \? \([\s\S]*<SystemInformation apiBaseUrl=\{apiBaseUrl\}/);
});

test('a stalled check expires, preserves the previous snapshot and allows retry', async () => {
  const previous = { fetch: globalThis.fetch, document: globalThis.document, localStorage: globalThis.localStorage,
    setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout };
  const requests = [];
  let deadline;
  globalThis.document = { visibilityState: 'visible', addEventListener() {}, removeEventListener() {} };
  globalThis.localStorage = { getItem: () => 'test-only' };
  globalThis.setTimeout = (callback, delay, ...args) => {
    if (delay === 8000) { deadline = callback; return 888; }
    return previous.setTimeout(callback, delay, ...args);
  };
  globalThis.clearTimeout = id => { if (id !== 888) previous.clearTimeout(id); };
  globalThis.fetch = (url, options) => new Promise(resolve => requests.push({ options, resolve }));
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(exports.SystemInformation, { apiBaseUrl: '' })); });
    await act(async () => requests[0].resolve({ ok: true, json: async () => snapshot }));
    await act(async () => tree.root.findByType('button').props.onClick());
    assert.equal(typeof deadline, 'function', 'a request deadline must be scheduled');
    await act(async () => deadline());
    assert.equal(requests[1].options.signal.aborted, true);
    assert.match(JSON.stringify(tree.toJSON()), /Showing last successful check/);
    assert.match(JSON.stringify(tree.toJSON()), /PostgreSQL/);
    assert.equal(tree.root.findByType('button').props.disabled, false);
    await act(async () => tree.root.findByType('button').props.onClick());
    await act(async () => requests[2].resolve({ ok: true, json: async () => snapshot }));
    assert.doesNotMatch(JSON.stringify(tree.toJSON()), /Showing last successful check/);
  } finally {
    if (tree) await act(async () => tree.unmount());
    Object.assign(globalThis, previous);
  }
});

test('rendered Settings removes credentials and switching tabs aborts monitoring', async () => {
  const previous = { fetch: globalThis.fetch, document: globalThis.document, localStorage: globalThis.localStorage };
  const pageExports = {};
  const source = ts.transpileModule(fs.readFileSync(new URL('../src/app/admin/settings/page.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInThisContext(`(function(require,exports){${source}\n})`)(name => {
    if (name === '@/components/SystemInformation') return exports;
    if (name === '@/lib/api') return { getApiBaseUrl: () => '' };
    if (name === 'next/link') return { default: props => React.createElement('a', props) };
    return require(name);
  }, pageExports);
  let signal;
  let removed = false;
  globalThis.document = {
    visibilityState: 'visible', addEventListener() {}, removeEventListener() { removed = true; },
  };
  globalThis.localStorage = { getItem: () => 'test-only' };
  globalThis.fetch = (url, options) => {
    if (url.endsWith('system-info')) { signal = options.signal; return new Promise(() => {}); }
    return Promise.resolve({ ok: true, json: async () => [
      { id: 1, group: 'urgent', keywords: ['urgent'], color: 'red', description: '' },
    ] });
  };
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(pageExports.default)); });
    const text = JSON.stringify(tree.toJSON());
    assert.doesNotMatch(text, /Initial Admin Credentials|admin123|Fresh database only|Existing deployments keep/);
    assert.doesNotMatch(text, /Change Password|Current Password|New Password|Confirm New Password/);
    assert.equal(tree.root.findAllByType('input').filter(input => input.props.type === 'password').length, 0);
    assert.match(text, /Manage LLM Providers/);
    assert.match(text, /System Information/);
    const tab = tree.root.findAllByType('button').find(button => button.children.includes('Intent Detection Rules'));
    await act(async () => tab.props.onClick());
    assert.equal(signal.aborted, true);
    assert.equal(removed, true);
    assert.doesNotMatch(JSON.stringify(tree.toJSON()), /System Information/);
  } finally {
    if (tree) await act(async () => tree.unmount());
    Object.assign(globalThis, previous);
  }
});

test('Settings exposes mobile navigation that opens and closes', async () => {
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage };
  const layoutExports = {};
  const router = { push() {} };
  const source = ts.transpileModule(fs.readFileSync(new URL('../src/app/admin/layout.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInThisContext(`(function(require,exports){${source}\n})`)(name => {
    if (name === 'next/navigation') return { usePathname: () => '/admin/settings', useRouter: () => router };
    if (name === 'next/link') return { default: props => React.createElement('a', props) };
    if (name === '@/components/ui/Button') return { Button: props => React.createElement('button', props) };
    if (name === '@/lib/team-context') return { TeamProvider: ({ children }) => children };
    if (name === '@/components/TeamSwitcher') return { default: () => null };
    return require(name);
  }, layoutExports);
  globalThis.localStorage = { getItem: key => key === 'adminToken' ? 'fixture' : null, setItem() {} };
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ is_super_admin: true }) });
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(layoutExports.default, {}, 'Settings content')); });
    const navigation = () => tree.root.findByProps({ 'aria-label': 'Open navigation' });
    assert.equal(navigation().props['aria-expanded'], false);
    await act(async () => navigation().props.onClick());
    assert.equal(navigation().props['aria-expanded'], true);
    await act(async () => tree.root.findByProps({ 'aria-label': 'Close navigation' }).props.onClick());
    assert.equal(navigation().props['aria-expanded'], false);
  } finally {
    if (tree) await act(async () => tree.unmount());
    Object.assign(globalThis, previous);
  }
});
