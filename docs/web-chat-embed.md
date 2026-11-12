# Embed Web Chat on another website

Copy the installation code from Team Channels, the Channels overview editor,
or the widget setup page. Each uses `widgetEmbedCode()` in
`frontend/src/lib/embed-code.ts` and points to `/embed.js` with an explicit
`data-server-url`. The Copy code action copies the same string displayed in
the textarea.

```html
<script src="https://servio.example.com/embed.js"
  data-server-url="https://servio.example.com"
  data-api-key="YOUR_CHANNEL_KEY"
  data-type="chat"
  data-position="bottom-right"
  data-allow-toggle="true"
  async></script>
```

Replace the example gateway and key with the values for your channel. Do not
put an administrator token, provider key or sample customer key in source
control. Channel domain restrictions and authentication still apply.

## Public URL configuration

Snippet generators use the existing `getApiBaseUrl()` resolver. Set
`NEXT_PUBLIC_API_URL` to the public Servio gateway serving both the frontend
assets/pages (`/embed.js`, `/widget`, `/c/...`) and `/api`. This matches the
repository's Nginx deployment. A backend-only URL that cannot serve the widget
is not a valid public gateway for these snippets.

The resolver uses the configured URL, falls back to browser origin when no URL
is set, and replaces a localhost configuration with the current public browser
origin when opened on a public host. This preserves the existing Dev behavior.
`NEXT_PUBLIC_*` values are embedded during frontend build; rebuild when changing
them. No Production domain is hardcoded in snippet generation. Trailing slashes
are normalized, a configured path prefix is preserved, and attribute values
are HTML-escaped. Any path prefix still needs matching gateway/frontend routing.

The widget setup page's Test Widget link also points to that configured gateway.
The static `test_widget.html` demo then loads the script from its own origin.

## Loader URL and compatibility

`embed.js` resolves its server in this order:

1. Nonempty explicit `data-server-url`, including an explicitly configured path.
2. The origin of its own script URL, resolved against the embedding document.

It does not fall back to localhost or to the embedding website's origin.
The selected base is used for iframe, launcher theme and launcher logo requests.
The iframe's own API/WebSocket endpoints still follow that Servio frontend's
build configuration. A script CDN serving no Servio endpoints must use an
explicit server URL.

The loader captures its script element and waits for the document body if an
async script arrives in the page head. Existing key, mode, position, toggle,
language, accessibility, theme and close-message behavior is retained.

Next.js internally rewrites `/widget.js` to `/embed.js` for older snippets.
There is no duplicate JavaScript implementation and no redirect dependency.
The `/widget` page remains a separate route. This alias requires a frontend
rebuild/release; it does not change an already running Production deployment.

## Regression coverage

- `tests/embed-code.test.mjs`: configuration across environments, attribute
  preservation/escaping, alias configuration, and rendered Copy code behavior
  for the Channels editor, Team Channels and widget setup page.
- `tests/embed-widget.test.mjs`: script-origin fallback across websites,
  explicit override for iframe/theme/logo, legacy script URL, async head loading,
  and existing accessibility/open/close/theme behavior.
- `tests/workflow-channels.test.mjs` and `tests/workflow.test.mjs`: existing
  channel selection, creation and wizard behavior with the shared helper.

Run from the repository root:

```sh
node --test --test-concurrency=1 frontend/tests/*.test.mjs
cd frontend
npx tsc --noEmit
```

## Repeat the isolated browser check

Use three terminals and a temporary localhost-only PinchTab profile. These
ports are for the fixture; do not replace the existing application services.

Build and start the frontend in terminal 1:

```sh
cd frontend
NEXT_DIST_DIR=.next-embed-review NEXT_PUBLIC_API_URL=http://127.0.0.1:14183 NEXT_PUBLIC_WEBSOCKET_ENDPOINT=ws://127.0.0.1:14183/ws npm run build
NEXT_DIST_DIR=.next-embed-review npm run start -- --hostname 127.0.0.1 --port 13183
```

Start the fake services and embedding website in terminal 2:

```sh
node frontend/tests/embed-fixture-server.mjs
```

The embedding site is port 14184. Port 14183 is the fake Servio gateway and
14185 is the explicit-override gateway. Both proxy frontend pages/assets only
to the isolated Next.js server. APIs are allowlisted to fake theme/logo reads;
other API requests and writes are rejected. The fake WebSocket accepts only
`a2ui.capabilities` and returns an empty session. No application backend,
database, real key, LLM, MCP, transcription or integration is used.

With a dedicated PinchTab instance on port 19884, restricted to localhost,
run in terminal 3:

```sh
SERVIO_EMBED_BROWSER_URL=http://127.0.0.1:19884 SERVIO_EMBED_EVIDENCE_DIR=/tmp/servio-embed-review node frontend/tests/check-embed-browser.mjs
```

The driver checks generated snippets, implicit server resolution, legacy alias
and explicit override at 1280×900 and 390×844. It verifies visible iframe URLs,
fake session readiness, open/close, theme/logo requests, identical script
responses, and absence of conversation messages or API writes. It saves open
and closed screenshots plus `browser-results.json`. Stop only the fixture
processes and temporary browser instance afterward.

## Verification on Dev, 2026-11-12

- Frontend regression suite: 302 tests passed.
- TypeScript, isolated frontend build, workflow release check and diff check passed.
- Both script endpoints returned HTTP 200 JavaScript and identical bytes from
  the real Next.js build. A separate local `linux/amd64` frontend Docker build
  passed; the same endpoint/byte check passed inside its read-only runtime
  container with networking disabled and no published host ports.
- All eight cross-origin desktop/mobile browser cases passed. Screenshots show
  the actual Servio widget frontend with a fake logo, palette and WebSocket.
- Removed an embedded key literal from the old public `test.html` example and
  replaced it with a placeholder. Its validity was not tested and no key was
  rotated or changed on Production.
- A browser-driver text wait initially could not observe the cross-origin frame.
  The driver now checks its accessibility snapshot and treats CLI errors on
  stderr as failures. The complete final browser matrix passed.

Review evidence is stored locally under
`.audit/embed-review-20261112/screenshots/`. These screenshots/audits contain
fixture data only and are not published. Existing `nginx/tls-front.conf` remains
untouched. No Production deployment/restart, Allowed domains/channel change,
automatic-deploy change, commit or push is part of this task. Real conversation
and integration behavior was intentionally not tested.
