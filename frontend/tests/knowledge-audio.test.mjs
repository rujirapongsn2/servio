import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import TestRenderer from 'react-test-renderer';
import ts from 'typescript';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependencies = createRequire(import.meta.url);
function load(file, mocks = {}) {
  const filename = path.join(root, file);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })((name) => Object.hasOwn(mocks, name) ? mocks[name] : dependencies(name), exports);
  return exports;
}
const parser = load('src/lib/product-presentations.ts');
const clip = { asset_id: 'a'.repeat(64), title: 'Thai clip', source_label: 'cats.wav', segment_id: 's0001', start_ms: 18000, end_ms: 27000, transcript: 'แมวชอบนอน', transcript_status: 'ready', audio_url: `/api/knowledge-audio/${'a'.repeat(64)}?token=valid.token.signature` };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test('audio parser validates local URLs, intervals and bounded content', () => {
  assert.equal(parser.parseKnowledgeAudio([clip])[0].start_ms, 18000);
  for (const patch of [{ audio_url: 'https://foreign.test/audio' }, { audio_url: '/api/knowledge-audio/other?token=x' }, { start_ms: -1 }, { end_ms: 18000 }, { end_ms: 9999999 }, { transcript: 'x'.repeat(20001) }, { transcript_status: 'failed' }, { segment_id: 'bad' }, { extra: 'x' }]) {
    assert.deepEqual(parser.parseKnowledgeAudio([{ ...clip, ...patch }]), []);
  }
  assert.deepEqual(parser.parseKnowledgeAudio(Array(6).fill(clip)), []);
});

test('mixed image and audio presentation preserves both card collections', () => {
  const image = { asset_id: 'b'.repeat(64), title: 'Image', source_label: 'image.png', image_url: `/api/knowledge-images/${'b'.repeat(64)}?token=a.b.c` };
  const media = { type: 'knowledge_media', version: 1, response: 'Evidence', images: [image], audio: [clip] };
  const parsed = parser.parseProductPresentations({ invocation: media }).invocation;
  assert.equal(parsed.audio.length, 1);
  assert.equal(parsed.images.length, 1);
  assert.equal(parser.parseKnowledgeMedia({ ...media, version: true }), null);
});

test('player seeks to canonical timestamp, exposes native controls and expandable transcript', async () => {
  const { KnowledgeAudio } = load('src/components/KnowledgeAudio.tsx', { '@/lib/api': { buildApiUrl: (value) => value } });
  let played = 0;
  const element = { currentTime: 0, play: async () => { played++; } };
  let renderer;
  await TestRenderer.act(async () => { renderer = TestRenderer.create(React.createElement(KnowledgeAudio, { audio: [clip] }), { createNodeMock: (node) => node.type === 'audio' ? element : null }); });
  const player = renderer.root.findByType('audio');
  assert.equal(player.props.controls, true);
  assert.equal(player.props.preload, 'metadata');
  assert.ok(player.props['aria-label']);
  await TestRenderer.act(async () => player.props.onLoadedMetadata());
  assert.equal(element.currentTime, 18);
  await TestRenderer.act(async () => renderer.root.findByType('button').props.onClick());
  assert.equal(played, 1);
  assert.equal(renderer.root.findAllByType('details').length, 1);
  await TestRenderer.act(async () => player.props.onError());
  assert.equal(renderer.root.findAllByType('audio').length, 0);
  assert.equal(renderer.root.findByProps({ role: 'status' }).children.length, 1);
  await TestRenderer.act(async () => renderer.unmount());
});

for (const { body, isAudio } of [{ body: '[00:00] Cats purr.', isAudio: true }, { body: '', isAudio: true }, { body: '', isAudio: false }]) {
  test(`document editor handles metadata save with ${body ? 'ready' : 'empty'} ${isAudio ? 'audio' : 'ordinary'} body`, async () => {
    const { default: Drawer } = load('src/components/OKFBundleDetailDrawer.tsx', {
      '@/components/KnowledgeAudio': { KnowledgeAudio: () => null },
      '@/components/KnowledgeImages': { KnowledgeImages: () => null },
      '@/lib/product-presentations': parser,
      '@/lib/api': { getApiBaseUrl: () => '' },
    });
    const concept = { id: 1, bundle_id: 1, concept_id: 'audio', file_path: 'audio.md', type: 'knowledge', title: 'Cats', tags: ['cats'], body, frontmatter: isAudio ? { audio: { transcript_status: body ? 'ready' : 'empty' } } : {}, links: [] };
    const previousFetch = global.fetch;
    const previousStorage = global.localStorage;
    global.localStorage = { getItem: () => 'test-token' };
    const patches = [];
    global.fetch = async (url, options) => {
      if (options?.method === 'PATCH') {
        const patch = JSON.parse(options.body);
        patches.push(patch);
        Object.assign(concept, patch);
      }
      return { ok: true, json: async () => url.includes('/concepts/audio') ? concept : url.includes('/concepts') ? [concept] : { id: 1, status: 'ready', concept_count: 1, link_count: 0 } };
    };
    let renderer;
    try {
      await TestRenderer.act(async () => { renderer = TestRenderer.create(React.createElement(Drawer, { tool: { id: 1, name: 'Knowledge', config: '{"okf_bundle_id":1}' }, teamAgentId: 1, onClose() {} })); });
      const documents = renderer.root.findAllByType('button').find((button) => button.children.some((child) => typeof child === 'string' && child.includes('Documents')));
      assert.ok(documents);
      await TestRenderer.act(async () => documents.props.onClick());
      const edit = renderer.root.findAllByType('button').find((button) => button.children.includes('Edit'));
      await TestRenderer.act(async () => edit.props.onClick());
      assert.equal(renderer.root.findByType('textarea').props.readOnly, isAudio);
      assert.equal(JSON.stringify(renderer.toJSON()).includes('Generated transcript (Re-index to refresh)'), isAudio);
      const title = renderer.root.findAllByType('input').find((input) => input.props.value === 'Cats');
      const tags = renderer.root.findAllByType('input').find((input) => input.props.value === 'cats');
      assert.equal(title.props.readOnly, undefined);
      assert.equal(tags.props.readOnly, undefined);
      await TestRenderer.act(async () => {
        title.props.onChange({ target: { value: 'Quiet recording' } });
        tags.props.onChange({ target: { value: 'quiet' } });
      });
      const save = renderer.root.findAllByType('button').find((button) => button.children.includes('Save'));
      assert.equal(save.props.disabled, !isAudio && !body);
      assert.equal(renderer.root.findByType('textarea').props.readOnly, isAudio);
      await TestRenderer.act(async () => save.props.onClick());
      assert.equal(patches.length, isAudio ? 1 : 0);
      if (!isAudio) return;
      assert.equal(patches[0].title, 'Quiet recording');
      assert.deepEqual(patches[0].tags, ['quiet']);
      assert.equal(patches[0].body, body);
    } finally {
      if (renderer) await TestRenderer.act(async () => renderer.unmount());
      global.fetch = previousFetch;
      global.localStorage = previousStorage;
    }
  });
}
