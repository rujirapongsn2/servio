import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load(request = async () => null) {
  const exports = {};
  const source = fs.readFileSync(new URL('../src/lib/channels-overview.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInThisContext(`(function(require,exports){${code}\n})`)(() => ({ workflowRequest: request }), exports);
  return exports;
}
const row = (change = {}) => ({ kind: 'web', channel_type: 'web_widget', id: 5, name: 'Tak Web Chat', team_id: 27,
  team_name: 'Tak', team_active: true, can_edit: true, is_active: true, status: 'active', updated_at: '2026-10-30T02:00:00',
  slug: 'tak-chat', allowed_domains: ['example.com'], voice_response_enabled: true, expires_at: null, usage_count: 10, ...change });
const detail = (change = {}) => ({ id: 5, name: 'Tak Web Chat', team_agent_id: 27, is_active: true,
  updated_at: '2026-10-30T02:00:00', key: 'test-only-secret', allowed_domains: ['example.com'], voice_response_enabled: true, expires_at: null, ...change });

test('overview keeps multiple team records and strips unexpected secrets', () => {
  const api = load();
  const parsed = api.parseChannelOverview([row({ key: 'must-not-render' }), row({ id: 6, team_id: 28, team_name: 'Other', status: 'expired' })]);
  assert.equal(parsed.length, 2);
  assert.equal(parsed[1].status, 'expired');
  assert.equal(JSON.stringify(parsed).includes('must-not-render'), false);
  assert.throws(() => api.parseChannelOverview([row({ slug: 'x"><script>' })]));
  assert.throws(() => api.parseChannelOverview([row({ kind: 'unknown' })]));
  assert.throws(() => api.parseChannelOverview({ error: 'fetch failed' }));
});
test('editor refuses data from a different team or channel', () => {
  const api = load();
  assert.throws(() => api.parseChannelDraft(detail({ team_agent_id: 99 }), row()), /scope/);
  assert.throws(() => api.parseChannelDraft(detail({ id: 8 }), row()), /scope/);
  const messaging = row({ kind: 'messaging', channel_type: 'line' });
  assert.equal(api.detailPath(messaging), '/channel-configs/line?team_agent_id=27');
  assert.throws(() => api.parseChannelDraft(detail({ type: 'facebook', config: {} }), messaging), /type/);
});
test('saving updates only the selected row and does not resend API secrets or team reassignment', async () => {
  const calls = [];
  const api = load(async (path, init) => { calls.push({ path, init }); return detail(); });
  const draft = api.parseChannelDraft(detail(), row());
  await api.saveChannelDraft(row(), { ...draft, name: 'Renamed', allowed_domains: 'a.example, b.example' }, '');
  const write = calls.find(c => c.init?.method === 'PUT');
  assert.equal(write.path, '/api-keys/5');
  const body = JSON.parse(write.init.body);
  assert.equal(body.name, 'Renamed');
  assert.deepEqual(body.allowed_domains, ['a.example', 'b.example']);
  assert.equal('key' in body, false);
  assert.equal('team_agent_id' in body, false);
});
test('stale editor does not overwrite a changed channel', async () => {
  let writes = 0;
  const api = load(async (path, init) => { if (init?.method === 'PUT') writes++; return detail({ updated_at: '2026-10-30T03:00:00' }); });
  await assert.rejects(api.saveChannelDraft(row(), api.parseChannelDraft(detail(), row()), ''), /changed/);
  assert.equal(writes, 0);
});
