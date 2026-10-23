/** v1 persists JSON as a parsed value. Only {{query}} explicitly binds agent input. */
export type Parameter = { name: string; value: string };
export type RequestBody = { kind: 'none' } | { kind: 'json'; value: unknown } | { kind: 'text'; value: string } | { kind: 'form'; fields: Parameter[] };
export type CustomApiRequest = { version: 1; headers: Parameter[]; query: Parameter[]; body: RequestBody };
export type RequestDraft = { endpoint: string; method: string; auth_token: string; timeout_seconds: string; headers: Parameter[]; query: Parameter[]; bodyKind: RequestBody['kind']; bodyText: string; fields: Parameter[] };
export const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
const fail = (message = 'Unsupported cURL syntax or option. Use a single HTTP request with literal values.'): never => { throw new Error(message); };
const rows = (value: unknown): Parameter[] => {
  if (!Array.isArray(value)) return fail('Invalid request parameters.');
  return value.map(row => {
    if (!row || typeof row !== 'object' || typeof row.name !== 'string' || typeof row.value !== 'string' || Object.keys(row).sort().join(',') !== 'name,value') return fail('Invalid request parameters.');
    return { name: row.name, value: row.value };
  });
};
export function validateEndpoint(endpoint: string) {
  try {
    const url = new URL(endpoint);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || /^[a-z]+:\/\/[^/]*@/i.test(endpoint) || url.hash || /[\s\x00-\x1f]/.test(endpoint)) return fail('Use an HTTP(S) URL without embedded credentials or a fragment.');
    return url;
  } catch { return fail('Use an HTTP(S) URL without embedded credentials or a fragment.'); }
}
export function serializeRequest(draft: RequestDraft): CustomApiRequest {
  validateEndpoint(draft.endpoint);
  if (!methods.includes(draft.method)) return fail('Choose a supported HTTP method.');
  if (!Number.isFinite(Number(draft.timeout_seconds)) || Number(draft.timeout_seconds) <= 0) return fail('Timeout must be greater than zero.');
  if (/[\r\n]/.test(draft.auth_token)) return fail('Invalid bearer token.');
  const seen = new Set<string>();
  const headers = rows(draft.headers);
  for (const row of headers) {
    const name = row.name.toLowerCase();
    if (!/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/.test(row.name) || /[\r\n]/.test(row.value) || seen.has(name)) return fail('Headers need unique valid names and single-line values.');
    if (name === 'authorization' && draft.auth_token) return fail('Use either an Authorization header or a bearer token.');
    seen.add(name);
  }
  const query = rows(draft.query);
  const fields = rows(draft.fields);
  if (query.some(row => !row.name) || (draft.bodyKind === 'form' && fields.some(row => !row.name))) return fail('Parameter names cannot be empty.');
  let body: RequestBody;
  switch (draft.bodyKind) {
    case 'none': body = { kind: 'none' }; break;
    case 'text': body = { kind: 'text', value: draft.bodyText }; break;
    case 'form': body = { kind: 'form', fields }; break;
    case 'json':
      try { body = { kind: 'json', value: JSON.parse(draft.bodyText) }; }
      catch { return fail('Body must contain valid JSON.'); }
      break;
    default: return fail('Unknown body format.');
  }
  return { version: 1, headers, query, body };
}
export function requestDraft(config: Record<string, unknown> = {}): RequestDraft {
  const draft: RequestDraft = { endpoint: typeof config.endpoint === 'string' ? config.endpoint : '', method: typeof config.method === 'string' ? config.method : 'POST', auth_token: typeof config.auth_token === 'string' ? config.auth_token : '', timeout_seconds: String(config.timeout_seconds ?? 60), headers: [], query: [], bodyKind: 'json', bodyText: JSON.stringify({ query: '{{query}}' }, null, 2), fields: [] };
  if ('request' in config) {
    const request = config.request;
    if (!request || typeof request !== 'object' || !('version' in request) || request.version !== 1) return fail('Unsupported Custom API request version.');
    if (!('headers' in request) || !('query' in request) || !('body' in request)) return fail('Invalid Custom API request.');
    const body = request.body;
    if (!body || typeof body !== 'object' || !('kind' in body)) return fail('Invalid Custom API body.');
    draft.headers = rows(request.headers); draft.query = rows(request.query);
    if (body.kind === 'none') { draft.bodyKind = 'none'; draft.bodyText = ''; }
    else if (body.kind === 'json' && 'value' in body) { draft.bodyKind = 'json'; draft.bodyText = JSON.stringify(body.value, null, 2); }
    else if (body.kind === 'text' && 'value' in body && typeof body.value === 'string') { draft.bodyKind = 'text'; draft.bodyText = body.value; }
    else if (body.kind === 'form' && 'fields' in body) { draft.bodyKind = 'form'; draft.fields = rows(body.fields); }
    else return fail('Unsupported Custom API body.');
    serializeRequest(draft);
  } else if (Object.keys(config).length) {
    draft.headers = [{ name: 'Content-Type', value: 'application/json' }];
    if (draft.method.toUpperCase() === 'GET') { draft.bodyKind = 'none'; draft.query = [{ name: 'query', value: '{{query}}' }]; }
    else {
      const payload = config.payload_template;
      const object = payload && typeof payload === 'object' && !Array.isArray(payload) ? { ...payload } : { query: '{{query}}' };
      for (const key of ['query', 'message', 'text', 'input']) {
        if (key in object) { Object.assign(object, { [key]: '{{query}}' }); break; }
      }
      draft.bodyText = JSON.stringify(object, null, 2);
    }
  }
  return draft;
}

/** Shell lexing only: no execution, expansion, network access, storage or logging. */
function shellWords(command: string): string[] {
  const words: string[] = []; let word = ''; let started = false; let quote = '';
  const input = command.trim();
  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (quote === "'") { if (char === "'") quote = ''; else word += char; continue; }
    if (char === '\\') {
      const next = input[++i];
      if (next === undefined) return fail();
      if (next === '\n') continue;
      if (next === '\r' && input[i + 1] === '\n') { i++; continue; }
      if (quote === '"' && !['$', '`', '"', '\\'].includes(next)) word += '\\';
      word += next; started = true; continue;
    }
    if (char === '$' || char === '`') return fail('Shell expansions are not supported. Use literal values.');
    if (quote === '"') { if (char === '"') quote = ''; else word += char; continue; }
    if (char === "'" || char === '"') { quote = char; started = true; continue; }
    if (/[;&|<>\n\r]/.test(char)) return fail('Use one cURL command without shell operators.');
    if (/\s/.test(char)) { if (started) { words.push(word); word = ''; started = false; } }
    else { word += char; started = true; }
  }
  if (quote) return fail('Close all quotes before parsing.');
  if (started) words.push(word);
  return words;
}
export function parseCurl(command: string): RequestDraft {
  const words = shellWords(command);
  if (!['curl', 'curl.exe'].includes(words.shift() || '')) return fail('Start with curl or curl.exe.');
  let endpoint = ''; let explicitMethod = ''; let get = false; let head = false;
  let globoff = false; let jsonMode = false; const data: string[] = []; const encoded: string[] = []; const headers: Parameter[] = [];
  const setUrl = (value: string) => { if (endpoint) return fail('Only one URL is supported.'); endpoint = value; };
  for (let i = 0; i < words.length; i++) {
    const token = words[i];
    if (!token.startsWith('-')) { setUrl(token); continue; }
    if (['-G', '--get'].includes(token)) { get = true; continue; }
    if (['-I', '--head'].includes(token)) { head = true; continue; }
    if (['-g', '--globoff'].includes(token)) { globoff = true; continue; }
    if (['-s', '--silent', '-S', '--show-error'].includes(token)) continue;
    let option = token; let value: string | undefined;
    if (token.startsWith('--') && token.includes('=')) { const split = token.indexOf('='); option = token.slice(0, split); value = token.slice(split + 1); }
    else if (/^-[XHdu].+/.test(token)) { option = token.slice(0, 2); value = token.slice(2); }
    if (!['--url', '-X', '--request', '-H', '--header', '-d', '--data', '--data-raw', '--data-binary', '--json', '--data-urlencode'].includes(option)) return fail('Unsupported cURL option. Use request, header, data or URL options.');
    if (value === undefined) value = words[++i];
    if (value === undefined) return fail('An option is missing its value.');
    if (option === '--url') setUrl(value);
    else if (['-X', '--request'].includes(option)) { if (explicitMethod) return fail(); explicitMethod = value.toUpperCase(); }
    else if (['-H', '--header'].includes(option)) {
      if (value.startsWith('@')) return fail('File inputs are not supported.');
      const colon = value.indexOf(':');
      if (colon < 1 || !value.slice(colon + 1).trim()) return fail('Headers need a name and value.');
      headers.push({ name: value.slice(0, colon).trim(), value: value.slice(colon + 1).trim() });
    } else {
      if ((value.startsWith('@') && option !== '--data-raw') || (option === '--data-urlencode' && value.split('=')[0].includes('@'))) return fail('File inputs are not supported.');
      if (option === '--data-urlencode') {
        const equal = value.indexOf('=');
        encoded.push(equal < 0 ? encodeURIComponent(value) : equal === 0 ? encodeURIComponent(value.slice(1)) : value.slice(0, equal) + '=' + encodeURIComponent(value.slice(equal + 1)));
      } else { if (option === '--json') jsonMode = true; data.push(value); }
    }
  }
  if (!endpoint) return fail('Provide one HTTP(S) URL.');
  const url = validateEndpoint(endpoint);
  // cURL expands URL globs unless --globoff; these are too ambiguous to import.
  if (!globoff && /[{}\[\]]/.test((url.pathname + url.search).replace(/\{\{query\}\}/g, ''))) return fail('URL globs are not supported.');
  if ((jsonMode && (encoded.length || data.length !== 1)) || (encoded.length && data.length) || (head && (get || data.length || encoded.length))) return fail('Conflicting request options.');
  const draft = requestDraft();
  draft.endpoint = url.origin + url.pathname;
  draft.query = Array.from(url.searchParams, ([name, value]) => ({ name, value }));
  draft.headers = headers; draft.auth_token = ''; draft.bodyKind = 'none'; draft.bodyText = '';
  draft.method = explicitMethod || (head ? 'HEAD' : get ? 'GET' : data.length || encoded.length ? 'POST' : 'GET');
  const combined = [...data, ...encoded].join('&');
  if (get && combined) draft.query.push(...Array.from(new URLSearchParams(combined), ([name, value]) => ({ name, value })));
  else if (data.length || encoded.length) {
    const contentType = headers.find(row => row.name.toLowerCase() === 'content-type');
    if (jsonMode) {
      if (!contentType) headers.push({ name: 'Content-Type', value: 'application/json' });
      if (!headers.some(row => row.name.toLowerCase() === 'accept')) headers.push({ name: 'Accept', value: 'application/json' });
    } else if (!contentType) headers.push({ name: 'Content-Type', value: 'application/x-www-form-urlencoded' });
    if (jsonMode || contentType?.value.toLowerCase().includes('application/json')) {
      try { draft.bodyText = JSON.stringify(JSON.parse(combined), null, 2); draft.bodyKind = 'json'; }
      catch { if (jsonMode) return fail('The --json body must be valid JSON.'); draft.bodyKind = 'text'; draft.bodyText = combined; }
    } else { draft.bodyKind = 'text'; draft.bodyText = combined; }
  }
  const authorization = headers.find(row => row.name.toLowerCase() === 'authorization');
  if (authorization && /^Bearer\s+/i.test(authorization.value)) {
    serializeRequest(draft);
    draft.auth_token = authorization.value.replace(/^Bearer\s+/i, '');
    draft.headers = headers.filter(row => row !== authorization);
  }
  serializeRequest(draft);
  return draft;
}
