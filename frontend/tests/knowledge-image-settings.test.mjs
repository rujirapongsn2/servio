import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import { act, create } from 'react-test-renderer';
import ts from 'typescript';
const dependencies = createRequire(import.meta.url);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load() {
  const file = new URL('../src/components/KnowledgeImageSearchSettings.tsx', import.meta.url);
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename: file.pathname })(name => name === '@/lib/api' ? { getApiBaseUrl: () => '' } : dependencies(name), exports);
  return exports.KnowledgeImageSearchSettings;
}
function text(node) { return typeof node === 'string' ? node : (node?.children ?? []).map(text).join(''); }
async function harness({ canEdit = true, settings = {}, getFailure = false } = {}) {
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage };
  let saved = { mode: 'rerank', default_min_score: .2, override_min_score: null, effective_min_score: .2, can_edit: true, ...settings };
  const requests = [];
  let failure = 0;
  globalThis.localStorage = { getItem: () => 'private-test-token' };
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, ...options });
    if (options.method === 'PATCH') {
      if (failure) return { ok: false, status: failure };
      const body = JSON.parse(options.body);
      saved = { ...saved, override_min_score: body.min_score, effective_min_score: body.min_score ?? saved.default_min_score };
    } else if (getFailure) return { ok: false, status: 503 };
    return { ok: true, status: 200, json: async () => saved };
  };
  let tree;
  await act(async () => { tree = create(React.createElement(load(), { bundleId: 4, teamAgentId: 21, canEdit })); });
  return {
    tree, requests,
    input: () => tree.root.findByType('input'),
    button: label => tree.root.findAllByType('button').find(n => n.props['aria-label'] === label || text(n).trim() === label),
    change: value => act(async () => tree.root.findByType('input').props.onChange({ target: { value } })),
    fail: code => { failure = code; },
    setDefault: value => { saved = { ...saved, default_min_score: value }; },
    retryGet: () => { getFailure = false; },
    close: async () => { await act(async () => tree.unmount()); Object.assign(globalThis, previous); },
  };
}

test('active mode uses server defaults, saves bundle-specific score and resets inheritance', async () => {
  const h = await harness();
  try {
    assert.equal(h.input().props.value, '20');
    assert.ok(text(h.tree.toJSON()).includes('คะแนนคัดภาพเบื้องต้นขั้นต่ำ'));
    assert.equal(h.requests[0].url, '/api/admin/okf-bundles/4/image-search-settings?team_agent_id=21');
    assert.equal(h.button('บันทึกเกณฑ์ค้นหารูปภาพ').props.disabled, true);
    await h.change('35.5');
    await act(async () => h.button('บันทึกเกณฑ์ค้นหารูปภาพ').props.onClick());
    assert.deepEqual(JSON.parse(h.requests.at(-1).body), { mode: 'rerank', min_score: .355 });
    assert.equal(h.input().props.value, '35.5');
    assert.ok(text(h.tree.toJSON()).includes('กำหนดเฉพาะแหล่งความรู้นี้'));
    h.setDefault(.25);
    await act(async () => h.button('ใช้ค่าเริ่มต้นระบบ').props.onClick());
    assert.deepEqual(JSON.parse(h.requests.at(-1).body), { mode: 'rerank', min_score: null });
    assert.equal(h.input().props.value, '25');
    assert.ok(text(h.tree.toJSON()).includes('ค่าเริ่มต้นระบบ'));
  } finally { await h.close(); }
});

test('plain similarity mode uses its own label and env default', async () => {
  const h = await harness({ settings: { mode: 'similarity', default_min_score: .82, effective_min_score: .82 } });
  try {
    assert.equal(h.input().props.value, '82');
    assert.ok(text(h.tree.toJSON()).includes('คะแนนความใกล้เคียงขั้นต่ำ'));
    await h.change('-10');
    await act(async () => h.button('บันทึกเกณฑ์ค้นหารูปภาพ').props.onClick());
    assert.deepEqual(JSON.parse(h.requests.at(-1).body), { mode: 'similarity', min_score: -.1 });
  } finally { await h.close(); }
});

for (const value of ['', '101', '-101', 'NaN', 'Infinity']) {
  test(`invalid threshold ${JSON.stringify(value)} cannot be saved`, async () => {
    const h = await harness();
    try {
      await h.change(value);
      assert.equal(h.button('บันทึกเกณฑ์ค้นหารูปภาพ').props.disabled, true);
      assert.equal(h.input().props['aria-invalid'], true);
      assert.equal(h.requests.length, 1);
    } finally { await h.close(); }
  });
}

test('failed saves preserve draft; stale mode requires reload', async () => {
  const h = await harness();
  try {
    await h.change('45'); h.fail(500);
    await act(async () => h.button('บันทึกเกณฑ์ค้นหารูปภาพ').props.onClick());
    assert.equal(h.input().props.value, '45');
    assert.ok(text(h.tree.toJSON()).includes('บันทึกไม่สำเร็จ'));
    h.fail(409);
    await act(async () => h.button('บันทึกเกณฑ์ค้นหารูปภาพ').props.onClick());
    assert.equal(h.input().props.disabled, true);
    assert.equal(h.button('บันทึกเกณฑ์ค้นหารูปภาพ').props.disabled, true);
    await act(async () => h.button('โหลดค่าล่าสุด').props.onClick());
    assert.equal(h.input().props.value, '20');
    assert.equal(h.input().props.disabled, false);
  } finally { await h.close(); }
});

for (const permissions of [{ canEdit: false }, { settings: { can_edit: false } }]) {
  test(`read-only settings respect ${JSON.stringify(permissions)}`, async () => {
    const h = await harness(permissions);
    try {
      assert.equal(h.input().props.readOnly, true);
      assert.equal(h.button('บันทึกเกณฑ์ค้นหารูปภาพ'), undefined);
      assert.equal(h.button('ใช้ค่าเริ่มต้นระบบ'), undefined);
    } finally { await h.close(); }
  });
}

test('settings load errors show retry instead of an invented fallback', async () => {
  const h = await harness({ getFailure: true });
  try {
    assert.equal(h.tree.root.findAllByType('input').length, 0);
    assert.ok(text(h.tree.toJSON()).includes('โหลดการตั้งค่าไม่สำเร็จ'));
    h.retryGet();
    await act(async () => h.button('ลองอีกครั้ง').props.onClick());
    assert.equal(h.input().props.value, '20');
  } finally { await h.close(); }
});

test('malformed server defaults are rejected rather than enabling an unsafe editor', async () => {
  const h = await harness({ settings: { default_min_score: '0.2' } });
  try {
    assert.equal(h.tree.root.findAllByType('input').length, 0);
    assert.ok(text(h.tree.toJSON()).includes('โหลดการตั้งค่าไม่สำเร็จ'));
  } finally { await h.close(); }
});
