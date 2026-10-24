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
const source = ts.transpileModule(fs.readFileSync(new URL('../src/components/ProviderModels.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
vm.runInThisContext(`(function(require,exports){${source}\n})`)(name => {
  if (name === '@/lib/api') return { getApiBaseUrl: () => '' };
  if (name === '@/components/ui/Button') return { Button: props => React.createElement('button', props) };
  return require(name);
}, exports);
const { act, create } = TestRenderer;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test('environment-managed image purpose is visibly locked while database purpose saves only IDs', async () => {
  const previous = { fetch: globalThis.fetch, document: globalThis.document, localStorage: globalThis.localStorage, HTMLElement: globalThis.HTMLElement };
  const writes = [];
  globalThis.document = { activeElement: null };
  globalThis.HTMLElement = class {};
  globalThis.localStorage = { getItem: () => 'test-only' };
  globalThis.fetch = async (url, options) => {
    if (options.method === 'PUT') writes.push(JSON.parse(options.body));
    return { ok: true, status: 200, json: async () => url.includes('registered-models') ? [
      { id: 4, provider_id: 1, model_id: 'db-vision', display_name: null, capabilities: ['vision'], enabled: true },
    ] : {
      image_ocr: 4, image_qa: null,
      sources: { image_ocr: { source: 'environment', model_id: 'local-env-vision', configured: true },
        image_qa: { source: 'database', model_id: null, configured: false } },
    } };
  };
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(exports.ProviderModels, {
      provider: { id: 1, name: 'Local' }, providers: [{ id: 1, name: 'Local' }], onClose() {},
    })); });
    const ocr = tree.root.findByProps({ id: 'default-image_ocr' });
    const qa = tree.root.findByProps({ id: 'default-image_qa' });
    assert.equal(ocr.props.disabled, true);
    assert.equal(ocr.props.value, 'environment');
    assert.equal(qa.props.disabled, false);
    assert.match(JSON.stringify(tree.toJSON()), /Managed in .env/);
    assert.match(JSON.stringify(tree.toJSON()), /local-env-vision/);
    await act(async () => qa.props.onChange({ target: { value: '4' } }));
    const save = tree.root.findAllByType('button').find(button => button.children.includes('Save Defaults'));
    await act(async () => save.props.onClick());
    assert.deepEqual(writes, [{ image_ocr: 4, image_qa: 4 }]);
  } finally {
    if (tree) await act(async () => tree.unmount());
    Object.assign(globalThis, previous);
  }
});
