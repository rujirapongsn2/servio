import { localModule } from './helpers/local-module.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import React from 'react';
import { act, create } from 'react-test-renderer';
import ts from 'typescript';
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}) {
  const filename = new URL(`../${file}`, import.meta.url);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${code}\n})`, { filename: filename.pathname })(name => Object.hasOwn(mocks, name) ? mocks[name] : localModule(name), exports);
  return exports;
}
const parser = load('src/lib/product-presentations.ts');
const jobs = load('src/lib/video-attachments.ts', { '@/lib/product-presentations': parser });
const imports = load('src/lib/knowledge-import.ts');
const asset = 'a'.repeat(64);
const attachmentId = '12345678-1234-1234-1234-123456789abc';
const video = { asset_id: asset, title: 'Door camera', source_label: 'door.mp4', video_url: `/api/video-attachments/${attachmentId}/media?token=signed.token`, poster_url: null, time_basis: 'frame_order', duration_ms: null, complete: false, warnings: ['Partial sampling'], events: [{ event_id: 'event-1', description: 'คนเปิดประตูแล้วเดินเข้าไป', start_frame: 10, end_frame: 20, start_ms: null, end_ms: null, frames: [{ frame_index: 10, offset_ms: null, image_url: `/api/video-attachments/${attachmentId}/media?token=signed.token&frame=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb` }] }] };
const presentation = videos => ({ type: 'knowledge_video', version: 1, response: 'Observed event', videos });
const job = (status = 'ready') => ({ attachment_id: attachmentId, status, phase: status, ...(status === 'ready' ? { presentation: presentation([video]) } : {}) });
const text = tree => JSON.stringify(tree.toJSON());
const response = body => ({ ok: true, json: async () => body });

test('video parser keeps missing media time and rejects forged URLs, impossible intervals and overflow', () => {
  assert.equal(parser.parseProductPresentations({ event: presentation([video]) }).event.videos[0].time_basis, 'frame_order');
  for (const changed of [
    { video_url: 'https://external.test/private.mp4' }, { poster_url: 'javascript:alert(1)' },
    { video_url: `/api/video-attachments/${attachmentId}/media?api_key=secret` },
    { video_url: `/api/video-attachments/${attachmentId}/media?token=x&redirect=https://bad.test` },
    { duration_ms: 0 }, { complete: 'true' }, { warnings: [false] },
    { events: [{ ...video.events[0], end_frame: 9 }] },
    { events: [{ ...video.events[0], start_ms: 100, end_ms: 200 }] },
    { events: [{ ...video.events[0], frames: [{ ...video.events[0].frames[0], offset_ms: 10 }] }] },
  ]) assert.equal(parser.parseKnowledgeVideo(presentation([{ ...video, ...changed }])), null);
  assert.equal(parser.parseKnowledgeVideo(presentation([{ ...video, duration_ms: 1000 }])).videos[0].events[0].start_ms, null);
  assert.equal(parser.parseKnowledgeVideo(presentation(Array(4).fill(video))), null);
  assert.throws(() => jobs.parseVideoAttachmentJob({ ...job(), presentation: null }));
});

test('video import stays disabled unless server confirms readiness; timestamps are not required', () => {
  const base = { images: { status: 'ready' }, audio: { status: 'ready' }, image_ocr: { status: 'disabled' } };
  const file = { name: 'unknown-time.MOV', size: 10, type: 'video/quicktime' };
  assert.equal(imports.fileMediaKind(file.name), 'video');
  assert.equal(imports.fileIssue(file, { status: 'loaded', value: imports.parseCapabilities(base) }), 'Video import disabled');
  assert.equal(imports.fileIssue(file, { status: 'loaded', value: imports.parseCapabilities({ ...base, videos: { status: 'ready' } }) }), null);
  assert.equal(jobs.videoUploadIssue(file), null);
  assert.equal(jobs.videoUploadIssue({ ...file, size: 50 * 1024 * 1024 + 1 }), 'size');
  assert.equal(jobs.videoUploadIssue({ ...file, type: 'text/html' }), 'type');
});

const players = load('src/components/KnowledgeVideos.tsx', { '@/lib/api': { buildApiUrl: value => value } });
test('unknown-time references open evidence frames without seeking and allow full video playback', async () => {
  const element = { currentTime: 0, readyState: 1, play: async () => undefined, pause() {} };
  let tree;
  await act(async () => { tree = create(React.createElement(players.KnowledgeVideos, { videos: [video] }), { createNodeMock: node => node.type === 'video' ? element : null }); });
  try {
    assert.equal(tree.root.findAllByType('video').length, 0);
    await act(async () => tree.root.findByProps({ 'aria-label': 'เปิดวิดีโออ้างอิง Door camera' }).props.onClick());
    assert.match(text(tree), /ไม่ทราบเวลา/);
    assert.match(text(tree), /ภาพอ้างอิงลำดับ 11/);
    assert.equal(tree.root.findAllByType('video').length, 0);
    assert.equal(element.currentTime, 0);
    await act(async () => tree.root.findAllByType('button').find(b => b.children.includes('ดูวิดีโอเต็ม')).props.onClick());
    assert.ok(tree.root.findByType('video').props.controls);
    assert.ok(tree.root.findByType('video').props.playsInline);
    assert.equal(element.currentTime, 0);
    await act(async () => tree.root.findByType('video').props.onError());
    assert.equal(tree.root.findAllByType('video').length, 0);
    assert.match(text(tree), /วิดีโอไม่พร้อมใช้งาน/);
  } finally { await act(async () => tree.unmount()); }
});

function composer() { return load('src/components/VideoAttachmentComposer.tsx', { '@/lib/api': { buildApiUrl: value => value }, '@/lib/video-attachments': jobs, '@/components/KnowledgeVideos': players }).VideoAttachmentComposer; }
test('HTTP upload uses the session grant and WS inquiry receives only the ready attachment reference', async () => {
  const beforeFetch = globalThis.fetch;
  const requests = [], inquiries = [];
  globalThis.fetch = async (url, options) => { requests.push({ url, options }); return response(job()); };
  const Component = composer();
  let tree;
  await act(async () => { tree = create(React.createElement(Component, { token: 'private-session-grant', disabled: false, onInquire: (...args) => { inquiries.push(args); return true; } })); });
  try {
    await act(async () => tree.root.findByType('input').props.onChange({ currentTarget: { files: [new File(['video'], 'door.mp4', { type: 'video/mp4' })], value: 'selected' } }));
    assert.match(tree.root.findByType('section').props.className, /max-h-\[55dvh\].*overflow-y-auto/);
    assert.equal(requests[0].url, '/api/video-attachments');
    assert.equal(requests[0].options.headers.Authorization, 'Bearer private-session-grant');
    assert.deepEqual([...requests[0].options.body.keys()], ['file']);
    await act(async () => tree.update(React.createElement(Component, { token: 'renewed-session-grant', disabled: false, onInquire: (...args) => { inquiries.push(args); return true; } })));
    assert.equal(tree.root.findAllByType('textarea').length, 1);
    await act(async () => tree.root.findByType('select').props.onChange({ target: { value: 'events' } }));
    await act(async () => tree.root.findByType('form').props.onSubmit({ preventDefault() {} }));
    assert.equal(inquiries[0][0], attachmentId);
    assert.match(inquiries[0][1], /ลำดับเฟรม/);
    assert.equal(inquiries[0].length, 2);
    await act(async () => tree.root.findAllByType('button').find(button => button.props['aria-label'] === 'นำวิดีโอออก').props.onClick());
    assert.equal(requests.at(-1).options.method, 'DELETE');
    assert.equal(tree.root.findAllByType('textarea').length, 0);
  } finally { await act(async () => tree.unmount()); globalThis.fetch = beforeFetch; }
});

test('cancelled and disconnected uploads ignore late responses and cannot resurrect an attachment', async () => {
  const beforeFetch = globalThis.fetch;
  let finish;
  globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
  const Component = composer();
  let tree;
  await act(async () => { tree = create(React.createElement(Component, { token: 'session', disabled: false, onInquire: () => true })); });
  try {
    await act(async () => tree.root.findByType('input').props.onChange({ currentTarget: { files: [new File(['video'], 'door.mp4', { type: 'video/mp4' })], value: 'selected' } }));
    assert.match(text(tree), /กำลังอัปโหลด/);
    await act(async () => tree.update(React.createElement(Component, { token: null, disabled: true, onInquire: () => true })));
    await act(async () => finish(response(job())));
    assert.equal(tree.toJSON(), null);
    await act(async () => tree.update(React.createElement(Component, { token: 'new-session', disabled: false, onInquire: () => true })));
    assert.equal(tree.root.findAllByType('textarea').length, 0);
    assert.equal(tree.root.findAllByType('video').length, 0);
  } finally { await act(async () => tree.unmount()); globalThis.fetch = beforeFetch; }
});

test('socket video requests are matched, do not send raw video, and reset revokes frontend capability', async () => {
  const beforeSocket = globalThis.WebSocket;
  const intervals = { set: globalThis.setInterval, clear: globalThis.clearInterval };
  let refresh, cleared = false;
  globalThis.setInterval = (callback, delay) => { assert.equal(delay, 30 * 60 * 1000); refresh = callback; return 7821; };
  globalThis.clearInterval = id => { if (id === 7821) cleared = true; else intervals.clear(id); };
  const sockets = [];
  class Socket { static OPEN = 1; readyState = 1; handlers = {}; sent = []; constructor() { sockets.push(this); } addEventListener(name, callback) { this.handlers[name] = callback; } send(value) { this.sent.push(JSON.parse(value)); } close() {} emit(value) { this.handlers.message({ data: JSON.stringify(value) }); } }
  globalThis.WebSocket = Socket;
  const { useWebsocket } = load('src/hooks/useWebsocket.ts', { '@/lib/product-presentations': parser, '@/lib/types': {}, '@/lib/utils': {}, '@/lib/api': { getWebsocketBaseUrl: () => 'ws://test/ws' } });
  let state, tree;
  function Probe() { state = useWebsocket(); return null; }
  try {
    await act(async () => { tree = create(React.createElement(Probe)); });
    const socket = sockets[0];
    await act(async () => { socket.handlers.open(); refresh(); });
    assert.deepEqual(socket.sent.map(message => message.type), ["a2ui.capabilities"]);
    await act(async () => socket.emit({ type: 'session.config', knowledge_video_enabled: true, video_upload_token: 'session' }));
    await act(async () => refresh());
    assert.equal(socket.sent.at(-1).type, 'knowledge.video.refresh');
    await act(async () => { assert.equal(state.sendVideoInquiry(attachmentId, '  เปิดประตูเมื่อไร  '), true); assert.equal(state.sendVideoInquiry(attachmentId, 'duplicate'), false); });
    const command = socket.sent.at(-1);
    assert.deepEqual(Object.keys(command).sort(), ['attachment_id', 'query', 'request_id', 'type']);
    assert.equal(command.query, 'เปิดประตูเมื่อไร');
    await act(async () => socket.emit({ type: 'knowledge.video.error', request_id: 'stale', message: 'wrong' }));
    assert.equal(state.isLoading, true);
    await act(async () => socket.emit({ type: 'history.updated', reason: 'response.done', request_id: command.request_id, inputs: [{ type: 'function_call_output', call_id: command.request_id, output: 'evidence' }], presentations: { [command.request_id]: presentation([video]) } }));
    assert.equal(state.isLoading, false);
    assert.equal(state.presentations[command.request_id].type, 'knowledge_video');
    await act(async () => state.resetHistory());
    assert.equal(state.videoUploadToken, null);
    await act(async () => socket.emit({ type: 'history.updated', reason: 'response.done', request_id: command.request_id, inputs: [{ type: 'message', role: 'assistant', content: 'stale response' }], presentations: { [command.request_id]: presentation([video]) } }));
    assert.deepEqual(state.history, []);
    assert.deepEqual(Object.keys(state.presentations), []);
    assert.equal(state.sendVideoInquiry(attachmentId, 'retry'), false);
  } finally { if (tree) await act(async () => tree.unmount()); globalThis.WebSocket = beforeSocket; globalThis.setInterval = intervals.set; globalThis.clearInterval = intervals.clear; }
  assert.equal(cleared, true);
});

test('queued upload polls status with the same private grant and cancel stops polling', async () => {
  const before = { fetch: globalThis.fetch, setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout };
  const scheduled = new Map(); let next = 1;
  globalThis.setTimeout = (callback, milliseconds, ...args) => {
    if (milliseconds !== 1200) return before.setTimeout(callback, milliseconds, ...args);
    const id = next++; scheduled.set(id, callback); return id;
  };
  globalThis.clearTimeout = id => { if (!scheduled.delete(id)) before.clearTimeout(id); };
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return response(job(options.method === 'DELETE' ? 'cancelled' : options.method === 'POST' ? 'queued' : 'processing'));
  };
  const Component = composer(); let tree;
  try {
    await act(async () => { tree = create(React.createElement(Component, { token: 'session-grant', disabled: false, onInquire: () => true })); });
    await act(async () => tree.root.findByType('input').props.onChange({ currentTarget: { files: [new File(['video'], 'door.mp4', { type: 'video/mp4' })], value: 'selected' } }));
    assert.equal(scheduled.size, 1);
    const [id, callback] = [...scheduled][0]; scheduled.delete(id);
    await act(async () => callback());
    assert.equal(requests[1].url, `/api/video-attachments/${attachmentId}`);
    assert.equal(requests[1].options.headers.Authorization, 'Bearer session-grant');
    assert.equal(tree.root.findAllByType('form').length, 0);
    await act(async () => tree.root.findByProps({ 'aria-label': 'นำวิดีโอออก' }).props.onClick());
    assert.equal(requests.at(-1).options.method, 'DELETE');
    assert.equal(scheduled.size, 0);
  } finally { if (tree) await act(async () => tree.unmount()); Object.assign(globalThis, before); }
});

test('chat renders video evidence linked by assistant ID or tool call ID without changing the answer', async () => {
  const { ChatHistory } = load('src/components/ChatDialog.tsx', { clsx: { default: (...values) => values.filter(Boolean).join(' ') },
    '@/lib/chat-flow': load('src/lib/chat-flow.ts'), '@/components/KnowledgeVideos': players,
    '@/components/KnowledgeAudio': { KnowledgeAudio: () => null }, '@/components/KnowledgeImages': { KnowledgeImages: () => null },
    '@/components/ProductCarousel': { ProductCarousel: () => null }, '@/components/ChatLoadingDots': { default: () => null },
    '@/components/MessageBubble': { MessageBubble: ({ message }) => React.createElement('p', null, typeof message.content === 'string' ? message.content : '') },
  });
  for (const source of [{ type: 'message', role: 'assistant', id: attachmentId, content: 'หลักฐานจากคลิปที่แนบ' }, { type: 'function_call_output', call_id: attachmentId, output: 'evidence' }]) {
    let tree;
    await act(async () => { tree = create(React.createElement(ChatHistory, { messages: [source, { type: 'message', role: 'assistant', content: 'พบคนเปิดประตู แต่ไม่ทราบเวลานาฬิกา' }], presentations: { [attachmentId]: presentation([video]) }, isLoading: false })); });
    try { assert.equal(tree.root.findAllByProps({ 'aria-label': 'เปิดวิดีโออ้างอิง Door camera' }).length, 1, text(tree)); assert.match(text(tree), /พบคนเปิดประตู/); }
    finally { await act(async () => tree.unmount()); }
  }
});

test('imported video detail displays signed evidence and preserves generated observations when editing metadata', async () => {
  const before = { fetch: globalThis.fetch, document: globalThis.document, localStorage: globalThis.localStorage };
  globalThis.document = { body: {} }; globalThis.localStorage = { getItem: () => 'admin-token' };
  const concept = { id: 1, bundle_id: 1, concept_id: 'door', file_path: 'door.md', title: 'Door camera', tags: [], links: [], body: 'Generated observations', frontmatter: { video: { profile: 'hybrid_frames' } }, video_presentation: presentation([video]) };
  globalThis.fetch = async url => response(url.includes('/concepts/door') ? concept : url.includes('/concepts') ? [concept] : { id: 1, status: 'ready', concept_count: 1 });
  const Component = load('src/components/OKFBundleDetailDrawer.tsx', {
    '@/lib/admin-locale': { AdminLocaleContext: React.createContext(null) }, '@/lib/api': { getApiBaseUrl: () => '' },
    'react-dom': { createPortal: content => content }, '@/lib/product-presentations': parser,
    '@/components/KnowledgeVideos': { KnowledgeVideos: props => React.createElement('video-evidence', props) },
    '@/components/KnowledgeAudio': { KnowledgeAudio: () => null }, '@/components/KnowledgeImages': { KnowledgeImages: () => null },
    '@/components/KnowledgeTablePanel': { KnowledgeTablePanel: () => null }, '@/components/KnowledgeImageSearchSettings': { KnowledgeImageSearchSettings: () => null }, '@/components/KnowledgeDocumentImage': { KnowledgeDocumentImage: () => null },
  }).default;
  let tree;
  try {
    await act(async () => { tree = create(React.createElement(Component, { tool: { id: 1, name: 'Door', config: '{"okf_bundle_id":1}' }, teamAgentId: 1, onClose() {} })); });
    await act(async () => tree.root.findAllByType('button').find(node => node.children.some(child => typeof child === 'string' && child.includes('Documents'))).props.onClick());
    assert.equal(tree.root.findByType('video-evidence').props.videos[0].time_basis, 'frame_order');
    await act(async () => tree.root.findAllByType('button').find(node => node.children.includes('Edit')).props.onClick());
    assert.equal(tree.root.findByType('textarea').props.readOnly, true);
    assert.equal(tree.root.findByType('textarea').props.value, 'Generated observations');
  } finally { if (tree) await act(async () => tree.unmount()); Object.assign(globalThis, before); }
});

test('Thai coverage warnings are translated once without repeating the visible timestamp and sampling notices', () => {
  const warnings = [
    'Sampled frames may miss short events. Event counts are not exhaustive.',
    'Audio is not analyzed in hybrid_frames mode. Native video/Metal inference is not enabled.',
    'Only a bounded portion was processed; later events may be missing.',
    'Reliable media timestamps unavailable; use frame order only.',
    'Frame analysis runs when the video is imported.',
  ];
  assert.deepEqual(players.videoWarnings({ ...video, warnings }, 'th'), ['รุ่นนี้วิเคราะห์เฉพาะภาพในคลิป ไม่วิเคราะห์เสียง', 'เริ่มวิเคราะห์เมื่อบันทึกแหล่งความรู้']);
  assert.equal(players.videoWarnings({ ...video, warnings }, 'en')[0], warnings[1]);
});

test('reference cards defer players until opened and stop at the selected interval', async () => {
  const element = { currentTime: 0, readyState: 1, play: async () => {}, pause() { this.paused = true; } };
  const timed = { ...video, time_basis: 'media', duration_ms: 10000, events: [{ ...video.events[0], start_ms: 2000, end_ms: 4000 }] };
  let tree;
  await act(async () => { tree = create(React.createElement(players.KnowledgeVideos, { videos: [timed] }), { createNodeMock: node => node.type === 'video' ? element : null }); });
  try {
    assert.equal(tree.root.findAllByType('video').length, 0, 'collapsed reference must not mount a video player');
    await act(async () => tree.root.findAllByType('button').find(b => b.props['aria-label'] === 'เปิดวิดีโออ้างอิง Door camera').props.onClick());
    assert.equal(tree.root.findAllByType('dialog').length, 1);
    assert.equal(element.currentTime, 2);
    element.currentTime = 4.2;
    await act(async () => tree.root.findByType('video').props.onTimeUpdate());
    assert.equal(element.paused, true);
    assert.equal(element.currentTime, 4);
    assert.match(text(tree), /ดูซ้ำ/);
    await act(async () => tree.root.findAllByType('button').find(b => b.children.includes('ดูต่อทั้งคลิป')).props.onClick());
    element.paused = false; element.currentTime = 5;
    await act(async () => tree.root.findByType('video').props.onTimeUpdate());
    assert.equal(element.paused, false);
    await act(async () => tree.root.findByProps({ 'aria-label': 'กลับสู่แชต' }).props.onClick());
    assert.equal(tree.root.findAllByType('video').length, 0);
  } finally { await act(async () => tree.unmount()); }
});

test('reference playback waits for metadata and changes ranges without using frame numbers as time', async () => {
  const element = { currentTime: 0, readyState: 0, play: async () => {}, pause() {} };
  const timed = { ...video, time_basis: 'media', duration_ms: 20000, events: [
    { ...video.events[0], start_ms: 2000, end_ms: 4000 },
    { ...video.events[0], event_id: 'second', start_ms: 8000, end_ms: 10000 },
  ] };
  let tree;
  await act(async () => { tree = create(React.createElement(players.KnowledgeVideos, { videos: [timed] }), { createNodeMock: node => node.type === 'video' ? element : null }); });
  try {
    await act(async () => tree.root.findByProps({ 'aria-label': 'เปิดวิดีโออ้างอิง Door camera' }).props.onClick());
    assert.equal(element.currentTime, 0);
    element.readyState = 1;
    await act(async () => tree.root.findByType('video').props.onLoadedMetadata());
    assert.equal(element.currentTime, 2);
    await act(async () => tree.root.findAllByType('button').find(b => b.findAllByType('span').some(span => span.children.some(child => typeof child === 'string' && child.includes('0:08')))).props.onClick());
    assert.equal(element.currentTime, 8);
    assert.equal(tree.root.findAllByType('dialog').length, 1);
    await act(async () => tree.root.findByType('dialog').props.onCancel());
    assert.equal(tree.root.findAllByType('dialog').length, 0);
  } finally { await act(async () => tree.unmount()); }
});

test('video sources appear once after their answer and never move into the next user turn', async () => {
  const { ChatHistory } = load('src/components/ChatDialog.tsx', {
    clsx: { default: (...values) => values.filter(Boolean).join(' ') }, '@/lib/chat-flow': load('src/lib/chat-flow.ts'),
    '@/components/KnowledgeVideos': { KnowledgeVideos: ({ videos }) => React.createElement('references', null, videos.map(v => v.title).join(',')) },
    '@/components/KnowledgeAudio': { KnowledgeAudio: () => null }, '@/components/KnowledgeImages': { KnowledgeImages: () => null },
    '@/components/ProductCarousel': { ProductCarousel: () => null }, '@/components/ChatLoadingDots': { default: () => null },
    '@/components/MessageBubble': { MessageBubble: ({ message }) => React.createElement('p', null, message.content || '') },
  });
  const messages = [
    { type: 'message', role: 'user', content: 'first question' },
    { type: 'function_call_output', call_id: 'call', output: 'evidence' },
    { type: 'message', role: 'assistant', id: 'answer', content: 'first answer' },
    { type: 'message', role: 'user', content: 'second question' },
    { type: 'message', role: 'assistant', content: 'second answer' },
  ];
  let tree;
  await act(async () => { tree = create(React.createElement(ChatHistory, { messages, presentations: { call: presentation([video]), answer: presentation([video]) }, isLoading: false })); });
  try {
    assert.equal(tree.root.findAllByType('references').length, 1);
    assert.equal(tree.root.findByType('references').children.join(''), 'Door camera');
    const nodes = tree.toJSON().children[0].children;
    const index = nodes.findIndex(node => node.type === 'references');
    assert.equal(nodes[index - 1].children.join(''), 'first answer');
    assert.equal(nodes[index + 1].children.join(''), 'second question');
  } finally { await act(async () => tree.unmount()); }
});
