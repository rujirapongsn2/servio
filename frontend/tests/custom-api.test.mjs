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
const { act, create } = TestRenderer;
const dependency = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, mocks = {}) {
  const filename = path.join(root, file);
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInThisContext(`(function(require,exports){${source}\n})`, { filename })(name => Object.hasOwn(mocks, name) ? mocks[name] : dependency(name), exports);
  return exports;
}
const api = load('src/lib/custom-api.ts');
const Editor = load('src/components/CustomApiRequestEditor.tsx', { '@/lib/custom-api': api }).default;
const event = value => ({ target: { value } });
const request = input => api.serializeRequest(api.parseCurl(input));

test('cURL imports quoted Thai JSON, duplicate query, bearer, escaped quotes and explicit method', () => {
  const draft = api.parseCurl(`curl.exe --url='https://example.com/path?tag=a&tag=b' -X=PATCH -H 'Content-Type: application/json' -H 'Authorization: Bearer secret' --data-raw '{"query":"literal","search":"{{query}}","thai":"ไทย; $literal"}'`.replace('-X=PATCH', '--request=PATCH'));
  assert.equal(draft.method, 'PATCH'); assert.equal(draft.auth_token, 'secret');
  assert.deepEqual(draft.query, [{ name: 'tag', value: 'a' }, { name: 'tag', value: 'b' }]);
  assert.equal(draft.headers.length, 1);
  assert.deepEqual(api.serializeRequest(draft).body.value, { query: 'literal', search: '{{query}}', thai: 'ไทย; $literal' });
  const escaped = api.parseCurl('curl https://example.com \\\n --json "{\\"text\\":\\"hello\\"}"');
  assert.equal(escaped.method, 'POST'); assert.equal(api.serializeRequest(escaped).body.value.text, 'hello');
  assert.equal(api.parseCurl(`curl https://example.com -d 'it'\\''s'`).bodyText, "it's");
});
test('infers methods and preserves curl data, raw content type, form encoding and GET query order', () => {
  assert.equal(api.parseCurl('curl https://example.com').method, 'GET');
  assert.equal(api.parseCurl('curl -I https://example.com').method, 'HEAD');
  assert.equal(api.parseCurl('curl -XDELETE https://example.com').method, 'DELETE');
  const data = request(`curl https://example.com -d '{"query":"literal"}'`);
  assert.equal(data.body.kind, 'text'); assert.equal(data.headers[0].value, 'application/x-www-form-urlencoded');
  assert.equal(request(`curl https://example.com -HContent-Type:text/plain --data-binary 'a b'`).body.value, 'a b');
  const form = api.parseCurl(`curl 'https://example.com/?tag=first' -G --data-urlencode 'tag=two words' --data-urlencode 'q=ไทย'`);
  assert.equal(form.method, 'GET'); assert.deepEqual(form.query.map(row => row.value), ['first', 'two words', 'ไทย']);
  const encoded = api.parseCurl(`curl https://example.com --data-urlencode 'q=a&b' --data-urlencode 'q=two'`);
  assert.equal(encoded.bodyText, 'q=a%26b&q=two');
  assert.equal(api.parseCurl(`curl https://example.com --data-urlencode '=hello world'`).bodyText, 'hello%20world');
  assert.equal(request(`curl https://example.com --data=a --data=b`).body.value, 'a&b');
  assert.equal(request(`curl https://example.com --json=null`).body.value, null);
  assert.equal(request(`curl https://example.com --data-raw '@literal'`).body.value, '@literal');
  assert.deepEqual(api.parseCurl(`curl -g 'https://example.com/?tag[]=one&tag[]=two'`).query, [{ name: 'tag[]', value: 'one' }, { name: 'tag[]', value: 'two' }]);
  assert.equal(api.parseCurl('curl http://[::1]/path').endpoint, 'http://[::1]/path');
});
test('unsupported shell, expansion, files, flags and ambiguous requests fail without side effects or secrets', () => {
  let fetched = 0; const previous = globalThis.fetch; globalThis.fetch = () => { fetched++; throw Error(); };
  try {
    for (const suffix of ['; echo secret', ' && echo secret', ' | sh', ' > secret', ' --location', ' --compressed', ' --insecure', ' -F file=@secret', ' --config secret', ' --cookie-jar secret', ' --upload-file secret', ' https://other.example', ' -H @secret', ' -d @secret', ' --data-urlencode name@secret', ' -u user:secret', ' -XTRACE', ' -H "X-Test: $secret"', ' -d `secret`', ' -d $(secret)', ' -d "${secret}"', '\necho secret']) {
      assert.throws(() => api.parseCurl('curl https://example.com' + suffix), error => !error.message.includes('secret'), suffix);
    }
    assert.throws(() => api.parseCurl('wget https://example.com'));
    assert.throws(() => api.parseCurl(`curl https://user:secret@example.com`), error => !error.message.includes('secret'));
    assert.throws(() => api.parseCurl(`curl https://example.com -H 'X-Test: a' -H 'x-test: b'`));
    assert.throws(() => api.parseCurl(`curl https://example.com -H 'Authorization: Bearer a' -H 'authorization: Bearer b'`));
    assert.equal(fetched, 0);
  } finally { globalThis.fetch = previous; }
});
test('legacy hydration preserves explicit agent binding and v1 round trips structurally', () => {
  for (const key of ['query', 'message', 'text', 'input']) {
    const original = { endpoint: 'https://example.com', method: 'POST', payload_template: { [key]: 'old', fixed: true } };
    assert.deepEqual(api.serializeRequest(api.requestDraft(original)).body.value, { [key]: '{{query}}', fixed: true });
    assert.equal(original.payload_template[key], 'old');
  }
  assert.deepEqual(api.requestDraft({ method: 'GET' }).query, [{ name: 'query', value: '{{query}}' }]);
  for (const body of [{ kind: 'none' }, { kind: 'text', value: 'hello' }, { kind: 'json', value: { query: 'literal', nested: ['{{query}}', false, null, 3] } }, { kind: 'form', fields: [{ name: 'q', value: 'a' }, { name: 'q', value: 'b' }] }]) {
    const original = { endpoint: 'https://example.com', method: 'PUT', request: { version: 1, headers: [], query: [], body } };
    assert.deepEqual(api.serializeRequest(api.requestDraft(original)), original.request);
  }
  assert.throws(() => api.requestDraft({ request: { version: 2 } }), /version/);
  const draft = api.parseCurl('curl https://example.com');
  assert.throws(() => api.serializeRequest({ ...draft, headers: [{ name: '', value: 'a' }] }));
  assert.throws(() => api.serializeRequest({ ...draft, bodyKind: 'json', bodyText: '{' }));
});
test('editor parse is transactional, apply changes request only and clears pasted command', async () => {
  const original = api.parseCurl('curl https://example.com/old'); const changes = [];
  let renderer;
  await act(async () => { renderer = create(React.createElement(Editor, { value: original, onChange: draft => changes.push(draft) })); });
  const button = label => renderer.root.findAllByType('button').find(node => node.children.join('') === label);
  const command = () => renderer.root.findAllByType('textarea')[0];
  const timeout = renderer.root.findByProps({ type: 'number' });
  assert.equal(timeout.props.min, 0);
  assert.equal(timeout.props.step, 'any');
  await act(async () => command().props.onChange(event('curl https://example.com --insecure')));
  await act(async () => button('Parse cURL').props.onClick());
  assert.equal(changes.length, 0); assert.equal(button('Apply request'), undefined);
  await act(async () => command().props.onChange(event('curl https://example.com/new -XPUT --json \'{"query":"literal"}\'')));
  await act(async () => button('Parse cURL').props.onClick());
  assert.equal(changes.length, 0);
  await act(async () => button('Apply request').props.onClick());
  assert.equal(changes[0].endpoint, 'https://example.com/new'); assert.equal(changes[0].method, 'PUT');
  assert.equal(changes[0].auth_token, ''); assert.equal(command().props.value, ''); assert.equal(button('Apply request'), undefined);
  assert.equal('name' in changes[0], false); assert.equal('description' in changes[0], false);
  await act(async () => renderer.unmount());
});

async function pageHarness({ edit = false, config = null, type = 'custom_api' } = {}) {
  const saved = [];
  globalThis.localStorage = { getItem: () => 'admin-token' };
  globalThis.fetch = async (url, options) => {
    if (options?.method) { saved.push(JSON.parse(options.body)); return { ok: true, json: async () => ({ message: 'ID 9', tool_id: 9 }) }; }
    return { ok: true, json: async () => ({ name: 'original_name', type, config: JSON.stringify(config), icon: 'Wrench', visibility: 'team' }) };
  };
  const mocks = {
    'next/navigation': { useRouter: () => ({ push() {} }), useSearchParams: () => new URLSearchParams(), useParams: () => ({ id: '1' }) },
    '@/components/IconPicker': { IconPicker: () => null }, '@/components/WorkflowNavigator': { default: () => null },
    '@/lib/api': { getApiBaseUrl: () => '' }, '@/lib/team-context': { useTeam: () => ({ selectedTeamId: 3, setSelectedTeamId() {} }) },
    '@/lib/ui-copy': { UI_COPY: { tools: { navLabel: 'Integrations' } } }, '@/lib/custom-api': api,
    '@/components/CustomApiRequestEditor': { default: Editor },
  };
  mocks['@/components/CreateToolForm'] = { default: load('src/components/CreateToolForm.tsx', { ...mocks, '@/lib/tool-creation': load('src/lib/tool-creation.ts') }).default };
  mocks['@/components/EditToolForm'] = { default: load('src/components/EditToolForm.tsx', mocks).default };
  const Page = load(`src/app/admin/tools/${edit ? '[id]' : 'new'}/page.tsx`, mocks).default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(Page)); });
  const submit = () => act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  return { renderer, saved, submit };
}
test('edit untouched legacy retains full config and changing request initializes v1 without replacing payload', async () => {
  const config = { type: 'custom_api', endpoint: 'https://example.com', method: 'POST', auth_token: 'old', description: 'Original', timeout_seconds: 60, api_type: 'other', payload_template: { message: 'old', fixed: 5 }, extra: { preserve: true } };
  const { renderer, saved, submit } = await pageHarness({ edit: true, config });
  await submit(); assert.deepEqual(saved[0].config, config);
  await act(async () => renderer.root.findByType(Editor).props.onChange({ ...renderer.root.findByType(Editor).props.value, method: 'PATCH' }));
  await submit(); assert.equal(saved[1].config.method, 'PATCH'); assert.deepEqual(saved[1].config.payload_template, config.payload_template);
  assert.deepEqual(saved[1].config.request.body.value, { message: '{{query}}', fixed: 5 });
  assert.equal(saved[1].name, 'original_name'); assert.equal(saved[1].config.api_type, 'other');
  await act(async () => renderer.unmount());
});
test('new saves reviewed request and edit v1 round trips; MCP serializes existing fields', async () => {
  const page = await pageHarness();
  const draft = api.parseCurl(`curl https://example.com --json '{"query":"literal"}'`);
  await act(async () => page.renderer.root.findByType(Editor).props.onChange(draft));
  await page.submit(); assert.deepEqual(page.saved[0].config.request.body.value, { query: 'literal' });
  const config = { ...page.saved[0].config, timeout_seconds: 1.5, extra: 'keep' };
  delete config.description;
  await act(async () => page.renderer.unmount());
  const edit = await pageHarness({ edit: true, config }); await edit.submit(); assert.deepEqual(edit.saved[0].config, config);
  await act(async () => edit.renderer.unmount());
  const mcpConfig = { type: 'mcp_streamable_http', endpoint: 'https://example.com/mcp', description: 'MCP', auth_token: 'token', timeout_seconds: 45, transport: 'streamable_http', auth_mode: 'query', auth_param_name: 'key', auth_header_name: 'X-Key', tools: ['weather'] };
  const mcp = await pageHarness({ edit: true, config: mcpConfig, type: 'mcp_streamable_http' });
  assert.equal(mcp.renderer.root.findAllByType(Editor).length, 0); await mcp.submit(); assert.deepEqual(mcp.saved[0].config, mcpConfig);
  await act(async () => mcp.renderer.unmount());
});

test('request tabs navigate with keyboard and expose only the selected panel', async () => {
  let renderer; const focused = [];
  await act(async () => {
    renderer = create(React.createElement(Editor, { value: api.parseCurl('curl https://example.com'), onChange() {} }), {
      createNodeMock: node => node.props.role === 'tab' ? { focus: () => focused.push(node.props.id) } : null,
    });
  });
  const tabs = () => renderer.root.findAllByProps({ role: 'tab' });
  const selected = () => tabs().find(tab => tab.props['aria-selected']);
  const navigate = async (key, expected) => {
    let prevented = false;
    await act(async () => selected().props.onKeyDown({ key, preventDefault() { prevented = true; } }));
    assert.equal(prevented, true);
    assert.equal(selected().children.join(''), expected);
    assert.equal(focused.at(-1), selected().props.id);
    const panel = renderer.root.findByProps({ role: 'tabpanel' });
    assert.equal(panel.props.id, selected().props['aria-controls']);
    assert.equal(panel.props['aria-labelledby'], selected().props.id);
    assert.deepEqual(tabs().map(tab => tab.props.tabIndex), tabs().map(tab => tab === selected() ? 0 : -1));
  };
  assert.equal(selected().children.join(''), 'Query (0)');
  assert.equal(renderer.root.findAllByType('fieldset').length, 1);
  await navigate('ArrowLeft', 'Body');
  assert.equal(renderer.root.findAllByType('fieldset').length, 0);
  await navigate('ArrowRight', 'Query (0)');
  await navigate('End', 'Body');
  await navigate('Home', 'Query (0)');
  await navigate('ArrowRight', 'Headers (0)');
  await act(async () => renderer.unmount());
});

test('tab counts and edited parameter values persist across panel switches', async () => {
  let renderer;
  function Harness() {
    const [value, setValue] = React.useState(api.parseCurl("curl 'https://example.com?q=first' -H 'X-Trace: original'"));
    return React.createElement(Editor, { value, onChange: setValue });
  }
  await act(async () => { renderer = create(React.createElement(Harness)); });
  const tab = label => renderer.root.findAllByProps({ role: 'tab' }).find(node => node.children.join('') === label);
  const button = label => renderer.root.findAllByType('button').find(node => node.children.join('') === label);
  const labelledInput = text => {
    const label = renderer.root.findAllByType('label').find(node => node.children.join('') === text);
    assert.equal(label.props.className, 'sr-only');
    return renderer.root.findByProps({ id: label.props.htmlFor });
  };
  await act(async () => labelledInput('Query parameter value 1').props.onChange(event('edited')));
  await act(async () => button('+ Add parameter').props.onClick());
  assert.ok(tab('Query (2)'));
  await act(async () => tab('Headers (1)').props.onClick());
  assert.equal(renderer.root.findAllByType('fieldset').length, 1);
  await act(async () => labelledInput('Header value 1').props.onChange(event('updated')));
  await act(async () => tab('Query (2)').props.onClick());
  assert.equal(labelledInput('Query parameter value 1').props.value, 'edited');
  assert.equal(labelledInput('Query parameter name 2').props.value, '');
  await act(async () => tab('Headers (1)').props.onClick());
  assert.equal(labelledInput('Header value 1').props.value, 'updated');
  await act(async () => renderer.unmount());
});

test('initial body and imported requests select the relevant panel and clear command on apply', async () => {
  let renderer;
  function Harness() {
    const [value, setValue] = React.useState(api.parseCurl("curl https://example.com --json '{}'"));
    return React.createElement(Editor, { value, onChange: setValue });
  }
  await act(async () => { renderer = create(React.createElement(Harness)); });
  const selected = () => renderer.root.findAllByProps({ role: 'tab' }).find(tab => tab.props['aria-selected']).children.join('');
  const button = label => renderer.root.findAllByType('button').find(node => node.children.join('') === label);
  const command = () => renderer.root.findAllByType('textarea').find(node => node.props.id.endsWith('-curl'));
  assert.equal(selected(), 'Body');
  for (const [curl, panel] of [
    ["curl 'https://example.com?q=a' -H 'X-Test: a' --json '{}'", 'Body'],
    ["curl 'https://example.com?q=a' -H 'X-Test: a'", 'Query (1)'],
    ["curl https://example.com -H 'X-Test: a'", 'Headers (1)'],
    ['curl https://example.com', 'Query (0)'],
  ]) {
    await act(async () => command().props.onChange(event(curl)));
    await act(async () => button('Parse cURL').props.onClick());
    await act(async () => button('Apply request').props.onClick());
    assert.equal(selected(), panel);
    assert.equal(command().props.value, '');
    assert.equal(button('Apply request'), undefined);
  }
  await act(async () => renderer.unmount());
});
