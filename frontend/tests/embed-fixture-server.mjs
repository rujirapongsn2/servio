/** UI-only cross-origin fixture. No application backend, credentials or AI calls. */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const { WebSocketServer } = require('next/dist/compiled/ws');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const compiled = ts.transpileModule(fs.readFileSync(path.join(root, 'src/lib/embed-code.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const helpers = {};
vm.runInThisContext(`(function(exports){${compiled}\n})`)(helpers);
const KEY = 'fake-embed-fixture-only';
const theme = {
  version: 1, is_default: false, primary_color: '#0f766e', launcher_logo: true,
  logo_url: '/api/public/widget-logo/fake-logo.png',
  greeting: { en: { title: 'Hello from the fixture', subtitle: 'How can we help?' }, th: { title: 'สวัสดีจากระบบจำลอง', subtitle: 'ทดสอบหน้าตาเท่านั้น' } },
  palette: { primary: '#0f766e', primary_strong: '#115e59', on_primary: '#ffffff', accent_text: '#0f766e',
    bubble_from: '#0f766e', bubble_to: '#115e59', on_bubble: '#ffffff', tint_1: '#ccfbf1', tint_2: '#f0fdfa', tint_3: '#e0f2fe',
    base_1: '#f0fdfa', base_2: '#ffffff', base_3: '#ecfeff', frame_border: '#99f6e4', frame_bg: '#f0fdfa' },
};
const audit = { requests: [], websocketMessages: [], rejected: [] };
const json = (res, value, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(value)); };
function gateway(port) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://127.0.0.1:${port}`);
    audit.requests.push({ port, method: req.method, path: url.pathname });
    if (req.method !== 'GET') { audit.rejected.push({ method: req.method, path: url.pathname }); return json(res, { error: 'Fixture forbids writes' }, 403); }
    if (url.pathname === '/fixture-audit') return json(res, audit);
    if (url.pathname === '/api/public/widget-theme') return json(res, theme);
    if (url.pathname === theme.logo_url) { res.writeHead(200, { 'Content-Type': 'image/png', 'Access-Control-Allow-Origin': '*' }); return res.end(fs.readFileSync(path.join(root, 'tests/fixtures/embed-logo.png'))); }
    if (url.pathname.startsWith('/api/')) { audit.rejected.push({ method: req.method, path: url.pathname }); return json(res, { error: 'No real backend available' }, 403); }
    const upstream = http.request({ hostname: '127.0.0.1', port: 13183, path: req.url, method: 'GET' }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res); });
    upstream.on('error', () => { if (!res.headersSent) json(res, { error: 'Start the isolated frontend on port 13183' }, 502); else res.end(); });
    upstream.end();
  });
  const sockets = new WebSocketServer({ noServer: true });
  server.on('upgrade', (req, socket, head) => {
    if (new URL(req.url, 'http://fixture').pathname !== '/ws') return socket.destroy();
    sockets.handleUpgrade(req, socket, head, ws => {
      ws.send(JSON.stringify({ type: 'session.config', voice_response_enabled: false, knowledge_image_search_enabled: false, knowledge_video_enabled: false }));
      ws.send(JSON.stringify({ type: 'history.updated', inputs: [], agent_name: 'Fixture assistant' }));
      ws.on('message', raw => {
        const data = JSON.parse(String(raw));
        audit.websocketMessages.push(data.type);
        if (data.type !== 'a2ui.capabilities') { audit.rejected.push({ websocket: data.type }); ws.close(1008, 'UI fixture does not accept conversations'); }
      });
    });
  });
  server.listen(port, '127.0.0.1');
  return server;
}
const host = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:14184');
  if (url.pathname === '/favicon.ico') { res.writeHead(204); return res.end(); }
  const scenario = url.searchParams.get('case') || 'implicit';
  let code;
  if (scenario === 'snippet') code = helpers.widgetEmbedCode({ baseUrl: 'http://127.0.0.1:14183', apiKey: KEY, type: 'chat', position: 'bottom-right', allowToggle: false, lang: 'en', async: true });
  else code = `<script async src="http://127.0.0.1:14183/${scenario === 'alias' ? 'widget' : 'embed'}.js" data-api-key="${KEY}" data-type="chat" data-lang="en" data-allow-toggle="false"${scenario === 'override' ? ' data-server-url="http://127.0.0.1:14185"' : ''}></script>`;
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'self'; script-src 'self' http://127.0.0.1:14183; frame-src http://127.0.0.1:14183 http://127.0.0.1:14185; connect-src http://127.0.0.1:14183 http://127.0.0.1:14185; img-src 'self' http://127.0.0.1:14183 http://127.0.0.1:14185; style-src 'unsafe-inline'" });
  res.end(`<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Servio embed fixture</title>${code}<style>body{margin:0;background:#f8fafc;color:#0f172a;font:16px system-ui}main{max-width:760px;margin:12vh auto;padding:28px}h1{font-size:clamp(28px,6vw,44px)}p{color:#64748b;line-height:1.7}a{color:#0f766e;margin-right:16px;display:inline-block;padding:8px 0}.tag{font-size:13px;color:#0f766e}</style></head><body><main><div class="tag">Different-origin website · UI fixture</div><h1>A website with Servio chat</h1><p>The website runs on port 14184. Servio runs on another origin. Only fake theme and WebSocket responses are available.</p><nav><a href="?case=implicit">No server attribute</a><a href="?case=snippet">Generated snippet</a><a href="?case=alias">Legacy widget.js</a><a href="?case=override">Explicit server override</a></nav><p>Scenario: ${['implicit','snippet','alias','override'].includes(scenario) ? scenario : 'implicit'}</p></main></body></html>`);
});
const servers = [gateway(14183), gateway(14185), host];
host.listen(14184, '127.0.0.1', () => console.log('Fixture website http://127.0.0.1:14184 ; fake Servio gateways :14183/:14185; Next frontend :13183'));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { for (const server of servers) server.close(); process.exit(0); });
