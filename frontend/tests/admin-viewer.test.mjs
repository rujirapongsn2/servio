import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';
import { adminLocale } from './admin-locale-context.mjs';

const dependency = createRequire(import.meta.url);
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
class FakeButton {
  constructor(label) { this.textContent = label; this.dataset = { adminWrite: 'true' }; this.disabled = false; this.attributes = new Map(); this.classes = new Set(); this.classList = { add: token => this.classes.add(token), remove: token => this.classes.delete(token), contains: token => this.classes.has(token) }; }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  setAttribute(name, value) { this.attributes.set(name, value); }
  removeAttribute(name) { this.attributes.delete(name); }
}
function loadLayout() {
  const source = ts.transpileModule(fs.readFileSync(new URL('../src/app/admin/layout.tsx', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`)(name => {
    if (name === '@/lib/admin-locale') return adminLocale;
    if (name === '@/lib/team-context') return { TeamProvider: ({ children }) => children };
    if (name === '@/components/TeamSwitcher') return { default: () => null };
    if (name === '@/components/ui/Button') return { Button: props => React.createElement('button', props) };
    if (name === 'next/navigation') return { useRouter: () => ({ push() {} }), usePathname: () => '/admin/teams' };
    if (name === 'next/link') return { default: props => React.createElement('a', props) };
    return dependency(name);
  }, exports);
  return exports.default;
}
for (const [locale, actionLabel] of [['th', 'สร้างทีม'], ['en', 'Create team']]) {
  test(`viewer locks semantic ${locale} write controls and relocks after React enables them`, async () => {
    const prior = { window: globalThis.window, document: globalThis.document, localStorage: globalThis.localStorage, HTMLButtonElement: globalThis.HTMLButtonElement, MutationObserver: globalThis.MutationObserver, fetch: globalThis.fetch };
    const action = new FakeButton(actionLabel);
    const read = new FakeButton('Open'); read.dataset.adminWrite = 'false';
    const observers = [];
    globalThis.HTMLButtonElement = FakeButton;
    globalThis.MutationObserver = class { constructor(callback) { this.callback = callback; observers.push(this); } observe() {} disconnect() {} };
    globalThis.document = { documentElement: { lang: 'en' }, body: {}, querySelectorAll: () => [action, read] };
    globalThis.localStorage = { getItem: key => key === 'adminToken' ? 'token' : key === 'isViewerOnly' ? '1' : key === adminLocale.ADMIN_LOCALE_STORAGE_KEY ? locale : null, setItem() {} };
    globalThis.window = { localStorage: globalThis.localStorage, location: { origin: 'http://localhost' } };
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ is_viewer_only: true }) });
    const Layout = loadLayout();
    let tree;
    try {
      await act(async () => { tree = create(React.createElement(Layout, null, 'Admin')); });
      assert.equal(document.documentElement.lang, locale);
      assert.equal(action.disabled, true);
      assert.equal(read.disabled, false);
      action.disabled = false;
      await act(async () => observers.at(-1).callback());
      assert.equal(action.disabled, true);
      action.dataset.adminWrite = 'false'; action.textContent = 'Open';
      await act(async () => observers.at(-1).callback());
      assert.equal(action.disabled, false);
    } finally {
      if (tree) await act(async () => tree.unmount());
      assert.equal(document.documentElement.lang, 'en');
      Object.assign(globalThis, prior);
    }
  });
}
