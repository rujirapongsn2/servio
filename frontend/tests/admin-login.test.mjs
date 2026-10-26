import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';
import { adminLocale, SwitchableAdminLocale } from './admin-locale-context.mjs';

const dependency = createRequire(import.meta.url);
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function loadLogin(push) {
  const source = ts.transpileModule(fs.readFileSync(new URL('../src/app/admin/login/page.tsx', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`)(name => {
    if (name === '@/lib/admin-locale') return adminLocale;
    if (name === '@/lib/api') return { buildApiUrl: path => `http://test${path}` };
    if (name === 'next/navigation') return { useRouter: () => ({ push }) };
    return dependency(name);
  }, exports);
  return exports.default;
}
async function mount(response) {
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage };
  const calls = [], routes = [], stored = new Map();
  globalThis.fetch = async (...args) => { calls.push(args); return response; };
  globalThis.localStorage = { setItem: (key, value) => stored.set(key, value) };
  const Login = loadLogin(path => routes.push(path));
  let tree, setLocale;
  await act(async () => { tree = create(React.createElement(SwitchableAdminLocale, { onReady: setter => { setLocale = setter; } }, React.createElement(Login))); });
  return { tree, calls, routes, stored, switch: locale => act(async () => setLocale(locale)), async cleanup() { await act(async () => tree.unmount()); Object.assign(globalThis, previous); } };
}
async function enter(ui) {
  await act(async () => ui.tree.root.findByProps({ id: 'username' }).props.onChange({ target: { value: 'user1' } }));
  await act(async () => ui.tree.root.findByProps({ id: 'password' }).props.onChange({ target: { value: 'secret-for-test' } }));
}
async function submit(ui) { await act(async () => ui.tree.root.findByType('form').props.onSubmit({ preventDefault() {} })); }

test('login keeps entered credentials when revealing password and switching language', async () => {
  const ui = await mount({ ok: false, status: 401 });
  try {
    await enter(ui);
    await act(async () => ui.tree.root.findByProps({ 'aria-label': 'Show password' }).props.onClick());
    assert.equal(ui.tree.root.findByProps({ id: 'password' }).props.type, 'text');
    await ui.switch('th');
    assert.equal(ui.tree.root.findByProps({ id: 'username' }).props.value, 'user1');
    assert.equal(ui.tree.root.findByProps({ id: 'password' }).props.value, 'secret-for-test');
    assert.equal(ui.tree.root.findByProps({ 'aria-label': 'ซ่อนรหัสผ่าน' }).props.type, 'button');
    await submit(ui);
    assert.equal(ui.tree.root.findByProps({ role: 'alert' }).findByType('span').children.join(''), 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง');
    assert.equal(ui.stored.size, 0);
    assert.deepEqual(ui.routes, []);
  } finally { await ui.cleanup(); }
});
test('successful sign-in preserves the API payload, auth flags and dashboard destination', async () => {
  const ui = await mount({ ok: true, json: async () => ({ access_token: 'test-token', username: 'user1', is_super_admin: false, is_operator_only: false, is_viewer_only: true, can_manage_users: false }) });
  try {
    await enter(ui); await submit(ui);
    assert.equal(ui.calls[0][0], 'http://test/api/admin/auth/login');
    assert.equal(ui.calls[0][1].method, 'POST');
    assert.deepEqual(JSON.parse(ui.calls[0][1].body), { username: 'user1', password: 'secret-for-test' });
    assert.deepEqual(Object.fromEntries(ui.stored), { adminToken: 'test-token', adminUsername: 'user1', isSuperAdmin: '0', isOperatorOnly: '0', isViewerOnly: '1', canManageUsers: '0' });
    assert.deepEqual(ui.routes, ['/admin']);
  } finally { await ui.cleanup(); }
});
test('service errors present a localized alert and reenable submit', async () => {
  const ui = await mount({ ok: false, status: 503 });
  try {
    await enter(ui); await submit(ui);
    assert.match(ui.tree.root.findByProps({ role: 'alert' }).findByType('span').children.join(''), /Unable to sign in/);
    assert.equal(ui.tree.root.findByType('form').props['aria-busy'], false);
    assert.equal(ui.tree.root.findAllByType('button').find(button => button.props.type === 'submit').props.disabled, false);
  } finally { await ui.cleanup(); }
});
