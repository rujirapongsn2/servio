/** Run after starting embed-fixture-server and an isolated localhost PinchTab instance. */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const server = process.env.SERVIO_EMBED_BROWSER_URL || 'http://127.0.0.1:19884';
assert.equal(new URL(server).hostname, '127.0.0.1', 'Use an isolated loopback browser instance');
const output = path.resolve(process.env.SERVIO_EMBED_EVIDENCE_DIR || '/tmp/servio-embed-review');
fs.mkdirSync(output, { recursive: true });
let tab;
function browser(...args) {
  const result = spawnSync('pinchtab', ['--server', server, ...(tab ? ['--tab', tab] : []), ...args], { encoding: 'utf8', timeout: 30000 });
  assert.equal(result.status, 0, 'PinchTab command failed');
  assert.doesNotMatch((result.stdout || '') + (result.stderr || ''), /Error [45]\d\d:|^ERROR:/m, 'PinchTab reported an error');
  return result.stdout;
}
const results = [];
for (const [size, width, height] of [['desktop', 1280, 900], ['mobile', 390, 844]]) {
  for (const scenario of ['implicit', 'snippet', 'alias', 'override']) {
    const navigated = browser('nav', `http://127.0.0.1:14184/?case=${scenario}`, '--snap');
    tab = navigated.match(/^[A-F0-9]{32}$/m)?.[0] || tab;
    assert.ok(tab, 'Expected temporary tab ID');
    browser('set', 'viewport', String(width), String(height), ...(size === 'mobile' ? ['--mobile'] : []));
    browser('wait', '.dvoice-widget-button.has-logo');
    browser('screenshot', '-o', path.join(output, `${size}-${scenario}-closed.png`));
    const opened = browser('click', '[aria-label="เปิดสนทนากับ Servio"]', '--snap-diff');
    const frame = opened.match(/^(e\d+):Iframe/m)?.[1];
    assert.ok(frame, 'Visible iframe missing');
    const src = browser('attr', frame, 'src').trim();
    const url = new URL(src);
    assert.equal(url.origin, `http://127.0.0.1:${scenario === 'override' ? 14185 : 14183}`);
    assert.equal(url.pathname, '/widget');
    assert.equal(url.searchParams.get('apiKey'), 'fake-embed-fixture-only');
    assert.equal(url.searchParams.get('type'), 'chat');
    assert.equal(url.searchParams.get('allowToggle'), 'false');
    // Wait for fake session readiness without sending any chat message.
    let ready = '';
    for (let attempt = 0; attempt < 20; attempt++) {
      ready = browser('snap');
      if (ready.includes('Fixture assistant')) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.match(ready, /Fixture assistant/, 'Fake WebSocket session never became ready');
    browser('screenshot', '-o', path.join(output, `${size}-${scenario}-open.png`));
    const closed = browser('click', '[aria-label="ปิดหน้าต่างสนทนา"]', '--snap-diff');
    assert.doesNotMatch(closed.split('# removed:')[0], /^e\d+:Iframe/m);
    results.push({ size, scenario, iframe: src, opened: true, closed: true });
  }
}
const audit = await (await fetch('http://127.0.0.1:14183/fixture-audit')).json();
assert.deepEqual(audit.rejected, []);
assert.ok(audit.websocketMessages.length > 0);
assert.ok(audit.websocketMessages.every(type => type === 'a2ui.capabilities'));
for (const port of [14183, 14185]) {
  assert.ok(audit.requests.some(request => request.port === port && request.path === '/api/public/widget-theme'));
  assert.ok(audit.requests.some(request => request.port === port && request.path === '/api/public/widget-logo/fake-logo.png'));
}
const embed = await fetch('http://127.0.0.1:14183/embed.js');
const alias = await fetch('http://127.0.0.1:14183/widget.js');
assert.equal(embed.status, 200); assert.equal(alias.status, 200);
assert.equal(await embed.text(), await alias.text());
fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify({ results, audit }, null, 2));
console.log(`Passed ${results.length} cross-origin desktop/mobile cases. Only fake capability messages; no conversation, API writes or real AI calls.`);
