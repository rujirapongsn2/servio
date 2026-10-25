import test from 'node:test';
import assert from 'node:assert/strict';
import React, { useState } from 'react';
import TestRenderer from 'react-test-renderer';
import { adminCopy, adminLocale } from './admin-locale-context.mjs';

const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function Probe() {
  const { locale, copy, setLocale } = adminLocale.useAdminLocale();
  const [draft, setDraft] = useState('');
  return React.createElement('probe', { locale, label: copy.teamAgents, setLocale, draft, setDraft });
}
async function mount(saved, failStorage = false) {
  const previous = { window: globalThis.window, document: globalThis.document };
  const writes = [];
  const storage = {
    getItem() { if (failStorage) throw Error('blocked'); return saved; },
    setItem(key, value) { if (failStorage) throw Error('blocked'); writes.push([key, value]); },
  };
  globalThis.window = { localStorage: storage };
  globalThis.document = { documentElement: { lang: 'en' } };
  let tree;
  await act(async () => { tree = create(React.createElement(adminLocale.AdminLocaleProvider, null, React.createElement(Probe))); });
  return { tree, writes, async cleanup() { await act(async () => tree.unmount()); assert.equal(document.documentElement.lang, 'en'); Object.assign(globalThis, previous); } };
}
test('Thai is the deterministic admin default and document language restores after exit', async () => {
  const ui = await mount(null);
  try {
    assert.equal(ui.tree.root.findByType('probe').props.locale, 'th');
    assert.equal(ui.tree.root.findByType('probe').props.label, 'ทีมผู้ช่วย AI');
    assert.equal(document.documentElement.lang, 'th');
    assert.deepEqual(ui.writes, []);
  } finally { await ui.cleanup(); }
});
test('saved English restores after mount and a switch persists without remounting draft state', async () => {
  const ui = await mount('en');
  try {
    const probe = () => ui.tree.root.findByType('probe');
    assert.equal(probe().props.locale, 'en');
    assert.equal(document.documentElement.lang, 'en');
    await act(async () => probe().props.setDraft('Unsaved instructions'));
    await act(async () => probe().props.setLocale('th'));
    assert.equal(probe().props.locale, 'th');
    assert.equal(probe().props.draft, 'Unsaved instructions');
    assert.equal(document.documentElement.lang, 'th');
    assert.deepEqual(ui.writes, [[adminLocale.ADMIN_LOCALE_STORAGE_KEY, 'th']]);
  } finally { await ui.cleanup(); }
});
test('invalid or inaccessible storage keeps Thai and switching still works', async () => {
  for (const [saved, fail] of [['invalid', false], [null, true]]) {
    const ui = await mount(saved, fail);
    try {
      const probe = () => ui.tree.root.findByType('probe');
      assert.equal(probe().props.locale, 'th');
      await act(async () => probe().props.setLocale('en'));
      assert.equal(probe().props.locale, 'en');
      assert.equal(document.documentElement.lang, 'en');
    } finally { await ui.cleanup(); }
  }
});
test('catalogs have identical keys and interpolation stays locale specific', () => {
  assert.deepEqual(Object.keys(adminCopy.th).sort(), Object.keys(adminCopy.en).sort());
  assert.equal(adminCopy.th.agentsCount(2), '2 ผู้ช่วย');
  assert.equal(adminCopy.en.agentsCount(2), '2 agents');
  assert.match(adminCopy.th.confirmDeleteTeam('ฝ่ายขาย'), /ฝ่ายขาย/);
});
