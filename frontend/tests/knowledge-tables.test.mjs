import { adminLocale, EnglishAdminLocale } from './admin-locale-context.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { File } from 'node:buffer';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencies = createRequire(import.meta.url);
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const filename = path.join(root, file), exports = {};
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const require = name => name === '@/lib/admin-locale' ? adminLocale : name === '@/lib/api' ? { getApiBaseUrl: () => '' } : name === 'react-dom' ? { createPortal: children => children } : name.startsWith('@/') ? load(`src/${name.slice(2)}${name.endsWith('KnowledgeTableEditor') || name.endsWith('KnowledgeTablePanel') ? '.tsx' : '.ts'}`) : dependencies(name);
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })(require, exports);
  cache.set(file, exports); return exports;
}
const lib = load('src/lib/knowledge-tables.ts');
const { KnowledgeTableEditor: Editor } = load('src/components/KnowledgeTableEditor.tsx');
const { KnowledgeTablePanel: Panel } = load('src/components/KnowledgeTablePanel.tsx');
const { default: Modal } = load('src/components/CreateOKFBundleModal.tsx');
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.File = File;
globalThis.localStorage = { getItem: () => 'test-token' };
globalThis.document = { body: { style: { overflow: '' } } };
globalThis.window = { confirm: () => true, addEventListener() {}, removeEventListener() {} };
const response = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const text = node => typeof node === 'string' ? node : (node?.children ?? []).map(text).join('');
const button = (tree, name) => tree.root.findAllByType('button').find(node => text(node).trim() === name);
const change = (tree, label, value) => act(async () => tree.root.findByProps({ 'aria-label': label }).props.onChange({ target: { value } }));
async function mount(component) { let tree; await act(async () => { tree = create(React.createElement(EnglishAdminLocale, null, component)); }); return tree; }
const table = (rows = [['001', '2']]) => ({ table_name: 'data_1', name: 'Products', columns: ['code', 'qty'], rows });
function Grid({ initial }) { const [tables, setTables] = React.useState(initial); return React.createElement(Editor, { tables, onChange: setTables, teamAgentId: 21 }); }

test('draft parser rejects malformed cells and CSV serialization preserves identifiers and quoted data', async () => {
  assert.throws(() => lib.parseTableDrafts([{ ...table(), rows: [[1, 2]] }]));
  const files = lib.tablesToFiles([table([['001', '2'], ['A,"B', '3']])]);
  assert.equal(files.length, 1);
  assert.equal(files[0].name, 'Products.csv');
  assert.match(await files[0].text(), /"001","2"/);
  assert.match(await files[0].text(), /"A,""B","3"/);
  assert.equal(lib.tableDraftIssue([{ ...table(), columns: ['qty', 'qty'] }]), 'headers');
});

test('Excel clipboard values retain quoted tabs and multiline cells and expand within limits', () => {
  const matrix = lib.parseClipboardTable('"A\tB"\t"line1\nline2"\r\n001\t3\r\n');
  assert.deepEqual(matrix, [['A\tB', 'line1\nline2'], ['001', '3']]);
  const next = lib.pasteTableCells(table(), 1, 1, matrix);
  assert.deepEqual(next.columns, ['code', 'qty', 'Column 3']);
  assert.deepEqual(next.rows, [['001', '2', ''], ['', 'A\tB', 'line1\nline2'], ['', '001', '3']]);
  assert.throws(() => lib.pasteTableCells(table(), 0, 200, [['overflow']]));
});

test('grid editing, headings, row and column actions and paste update controlled data', async () => {
  const tree = await mount(React.createElement(Grid, { initial: [table()] }));
  try {
    await change(tree, 'qty, row 1', '4');
    await change(tree, 'Column name 2', 'count');
    assert.equal(tree.root.findByProps({ 'aria-label': 'count, row 1' }).props.value, '4');
    await act(async () => button(tree, 'Add row').props.onClick());
    await act(async () => button(tree, 'Add column').props.onClick());
    let prevented = false;
    await act(async () => tree.root.findByProps({ 'aria-label': 'code, row 2' }).props.onPaste({ clipboardData: { getData: () => 'A\t10\nB\t20' }, preventDefault() { prevented = true; } }));
    assert.equal(prevented, true);
    assert.equal(tree.root.findByProps({ 'aria-label': 'count, row 3' }).props.value, '20');
    await act(async () => tree.root.findByProps({ 'aria-label': 'Delete column 3' }).props.onClick());
    await act(async () => tree.root.findByProps({ 'aria-label': 'Delete row 2' }).props.onClick());
    assert.equal(tree.root.findByProps({ 'aria-label': 'code, row 2' }).props.value, 'B');
  } finally { await act(async () => tree.unmount()); }
});

test('pagination and sheet switching preserve edits without rendering all rows', async () => {
  const tree = await mount(React.createElement(Grid, { initial: [table(Array.from({ length: 101 }, (_, i) => [String(i), '1'])), { ...table(), table_name: 'data_2', name: 'Other' }] }));
  try {
    assert.equal(tree.root.findAllByType('tbody')[0].findAllByType('tr').length, 50);
    await change(tree, 'qty, row 1', 'changed');
    await act(async () => tree.root.findByProps({ 'aria-label': 'Next rows' }).props.onClick());
    assert.ok(tree.root.findByProps({ 'aria-label': 'code, row 51' }));
    await act(async () => button(tree, 'Other').props.onClick());
    await act(async () => button(tree, 'Products').props.onClick());
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.value, 'changed');
  } finally { await act(async () => tree.unmount()); }
});

test('draft import uses server parsing and opens imported sheets', async () => {
  const requests = [];
  globalThis.fetch = async (url, options) => { requests.push({ url, options }); return response({ tables: [table()] }); };
  const tree = await mount(React.createElement(Grid, { initial: [lib.emptyTable()] }));
  try {
    await act(async () => tree.root.findByProps({ 'aria-label': 'Import Excel / CSV' }).props.onChange({ target: { files: [new File(['bytes'], 'sales.xlsx')] }, currentTarget: { value: 'selected' } }));
    assert.match(requests[0].url, /table-drafts\/import\?team_agent_id=21$/);
    assert.equal(requests[0].options.body.get('files').name, 'sales.xlsx');
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.value, '2');
  } finally { await act(async () => tree.unmount()); }
});

test('new Table mode submits generated CSV with queryable flag while file mode remains opt-in', async () => {
  const sent = [];
  globalThis.fetch = async (url, options) => {
    if (url.includes('import-capabilities')) return response({ documents: { status: 'ready' }, images: { status: 'disabled' }, audio: { status: 'disabled' }, image_ocr: { status: 'not_configured' } });
    sent.push(options.body);
    if (url.includes('/preview')) return response({ source_count: 1, concept_count: 1, warnings: [], documents: [], tables: [] });
    return response({ job_id: 'table-job', status: 'succeeded', message: 'ready', warnings: [], bundle: { id: 1, tool_id: 2, display_name: 'Products', concept_count: 1, link_count: 0 } });
  };
  const tree = await mount(React.createElement(Modal, { teamAgentId: 21, onClose() {}, onSuccess() {} }));
  try {
    await act(async () => button(tree, 'Tables').props.onClick());
    await act(async () => tree.root.findByProps({ id: 'knowledge-name' }).props.onChange({ target: { value: 'Products' } }));
    await change(tree, 'Column 1, row 1', '001');
    await act(async () => tree.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(sent[0].get('queryable'), 'true');
    assert.equal(sent[0].get('import_mode'), 'knowledge');
    assert.match(await sent[0].get('files').text(), /"001"/);
    await act(async () => tree.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(sent[1].get('queryable'), 'true');
  } finally { await act(async () => tree.unmount()); }
});

test('saved table conflict retains edits and cancel restores the saved snapshot', async () => {
  const writes = [], dirty = [];
  globalThis.fetch = async (url, options) => options?.method === 'PUT' ? (writes.push(JSON.parse(options.body)), response({}, 409)) : response({ revision: 'v1', tables: [table()], can_edit: true });
  const tree = await mount(React.createElement(Panel, { bundleId: 3, teamAgentId: 21, canEdit: true, onDirtyChange: value => dirty.push(value) }));
  try {
    await change(tree, 'qty, row 1', '8');
    await act(async () => button(tree, 'Save tables').props.onClick());
    assert.equal(writes[0].expected_revision, 'v1');
    assert.equal(writes[0].tables[0].rows[0][1], '8');
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.value, '8');
    assert.match(text(tree.toJSON()), /changed elsewhere/);
    await act(async () => button(tree, 'Cancel').props.onClick());
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.value, '2');
    assert.ok(dirty.includes(true));
    assert.equal(dirty.at(-1), false);
  } finally { await act(async () => tree.unmount()); }
});

test('saved table honors server read-only permission and successful saves advance revision', async () => {
  globalThis.fetch = async () => response({ revision: 'v1', tables: [table()], can_edit: false });
  let tree = await mount(React.createElement(Panel, { bundleId: 3, canEdit: true, onDirtyChange() {} }));
  try {
    assert.equal(button(tree, 'Save tables'), undefined);
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.readOnly, true);
    assert.equal(tree.root.findAllByProps({ 'aria-label': 'Import Excel / CSV' }).length, 0);
  } finally { await act(async () => tree.unmount()); }
  globalThis.fetch = async (url, options) => response(options?.method === 'PUT' ? { revision: 'v2', tables: [table([['001', '9']])], can_edit: true } : { revision: 'v1', tables: [table()], can_edit: true });
  tree = await mount(React.createElement(Panel, { bundleId: 3, canEdit: true, onDirtyChange() {} }));
  try {
    await change(tree, 'qty, row 1', '9');
    await act(async () => button(tree, 'Save tables').props.onClick());
    assert.match(text(tree.toJSON()), /Tables saved/);
    assert.equal(button(tree, 'Save tables').props.disabled, true);
  } finally { await act(async () => tree.unmount()); }
});

test('delayed table imports lock create and save and aborted imports do not overwrite drafts', async () => {
  let resolveImport, importSignal;
  globalThis.fetch = async (url, options) => {
    if (url.includes('import-capabilities')) return response({ documents: { status: 'ready' }, images: { status: 'disabled' }, audio: { status: 'disabled' }, image_ocr: { status: 'not_configured' } });
    if (url.includes('table-drafts/import')) { importSignal = options.signal; return new Promise(resolve => { resolveImport = resolve; }); }
    return response({ revision: 'v1', tables: [table()], can_edit: true });
  };
  let tree = await mount(React.createElement(Modal, { teamAgentId: 21, onClose() {}, onSuccess() {} }));
  try {
    await act(async () => button(tree, 'Tables').props.onClick());
    await act(async () => tree.root.findByProps({ id: 'knowledge-name' }).props.onChange({ target: { value: 'Products' } }));
    await change(tree, 'Column 1, row 1', 'local');
    await act(async () => tree.root.findByProps({ 'aria-label': 'Import Excel / CSV' }).props.onChange({ target: { files: [new File(['xlsx'], 'data.xlsx')] }, currentTarget: { value: 'x' } }));
    assert.equal(button(tree, 'Review Knowledge').props.disabled, true);
    assert.equal(button(tree, 'Files').props.disabled, true);
    await act(async () => tree.unmount()); tree = null;
    assert.equal(importSignal.aborted, true);
    await act(async () => resolveImport(response({ tables: [table()] })));
  } finally { if (tree) await act(async () => tree.unmount()); }
  tree = await mount(React.createElement(Panel, { bundleId: 3, canEdit: true, onDirtyChange() {} }));
  try {
    await change(tree, 'qty, row 1', 'local');
    await act(async () => tree.root.findByProps({ 'aria-label': 'Import Excel / CSV' }).props.onChange({ target: { files: [new File(['csv'], 'data.csv')] }, currentTarget: { value: 'x' } }));
    assert.equal(button(tree, 'Save tables').props.disabled, true);
    await act(async () => resolveImport(response({ tables: [table()] })));
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.value, '2');
    assert.equal(button(tree, 'Save tables').props.disabled, false);
  } finally { await act(async () => tree.unmount()); }
});


test('table CSV filenames preserve Thai vowel marks and avoid duplicate upload names', () => {
  const source = { ...table(), name: 'สินค้า' };
  const files = lib.tablesToFiles([source, { ...source, table_name: 'data_2' }]);
  assert.deepEqual(files.map(file => file.name), ['สินค้า.csv', 'สินค้า-2.csv']);
});


test('expanded create view and Escape preserve the table draft and primary action', async () => {
  globalThis.fetch = async () => response({ documents: { status: 'ready' }, images: { status: 'disabled' }, audio: { status: 'disabled' }, image_ocr: { status: 'not_configured' } });
  const tree = await mount(React.createElement(Modal, { teamAgentId: 21, onClose() {}, onSuccess() {} }));
  try {
    await act(async () => button(tree, 'Tables').props.onClick());
    await change(tree, 'Column 1, row 1', 'retained draft');
    await act(async () => button(tree, 'Expand table').props.onClick());
    assert.equal(button(tree, 'Restore view').props['aria-expanded'], true);
    assert.equal(tree.root.findByProps({ 'aria-label': 'Column 1, row 1' }).props.value, 'retained draft');
    assert.ok(button(tree, 'Review Knowledge'));
    let prevented = false;
    await act(async () => tree.root.findByProps({ role: 'dialog' }).props.onKeyDown({ key: 'Escape', preventDefault() { prevented = true; }, stopPropagation() {} }));
    assert.equal(prevented, true);
    assert.equal(button(tree, 'Expand table').props['aria-expanded'], false);
    assert.equal(tree.root.findByProps({ 'aria-label': 'Column 1, row 1' }).props.value, 'retained draft');
    await act(async () => button(tree, 'Expand table').props.onClick());
    await act(async () => button(tree, 'Restore view').props.onClick());
    assert.equal(tree.root.findByProps({ 'aria-label': 'Column 1, row 1' }).props.value, 'retained draft');
  } finally { await act(async () => tree.unmount()); }
});

test('saved table expansion retains edits and is available to read-only viewers', async () => {
  function ExpandablePanel() {
    const [expanded, setExpanded] = React.useState(false);
    return React.createElement(Panel, { bundleId: 3, canEdit: true, onDirtyChange() {}, expanded, onToggleExpanded: () => setExpanded(value => !value) });
  }
  globalThis.fetch = async () => response({ revision: 'v1', tables: [table()], can_edit: true });
  let tree = await mount(React.createElement(ExpandablePanel));
  try {
    await change(tree, 'qty, row 1', '12');
    await act(async () => button(tree, 'Expand table').props.onClick());
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.value, '12');
    assert.equal(button(tree, 'Save tables').props.disabled, false);
    await act(async () => button(tree, 'Restore view').props.onClick());
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.value, '12');
  } finally { await act(async () => tree.unmount()); }
  globalThis.fetch = async () => response({ revision: 'v1', tables: [table()], can_edit: false });
  tree = await mount(React.createElement(ExpandablePanel));
  try {
    await act(async () => button(tree, 'Expand table').props.onClick());
    assert.equal(button(tree, 'Restore view').props['aria-expanded'], true);
    assert.equal(button(tree, 'Save tables'), undefined);
    assert.equal(tree.root.findByProps({ 'aria-label': 'qty, row 1' }).props.readOnly, true);
  } finally { await act(async () => tree.unmount()); }
});
