# Private Chat runtime parity

Private Chat tests an authorized team without a Channel or Channel API key. It runs saved configuration or a captured draft. Customer conversations remain separate.

## Root causes in 87021bc

The shared agent factory did not provide execution parity. `preview_tools.protect_tools` added Private-only evidence instructions, and `workflow_preview._run` replaced replies when an integration agent had no successful tool call in the current turn. Greetings, clarification, and answers based on earlier results could become `unverified`. A failed tool retired the session. Private-only message, turn, and timeout rules further restricted testing.

The messaging handler retained assistant prose but discarded SDK tool calls and outputs. Its follow-up context therefore differed from Web Chat and Private Chat. Private input accepted text only, and it did not use the Web Chat presentation renderer.

The historical failed Private EPC session's arguments are unavailable. This change does not claim that the earlier failure was caused by VIN formatting.

## Execution comparison

| Concern | Shared behavior after this change | Necessary difference |
| --- | --- | --- |
| Factory, model, provider, settings | `agent_config.get_runtime_starting_agent`, including strict tool construction and provider settings | Private can select one member or capture drafts. Channel uses saved settings. |
| Instructions and context | Same factory instructions and `agent_execution.TOOL_EVIDENCE_POLICY`; shared knowledge context builder | Draft instructions can intentionally differ. |
| Tool request and result | Same tool schemas, credentials, request templates, adapters, validation, and `tool_execution` guards | Private requires explicit real-action consent before session creation. |
| Routing and handoff | Same coordinator, fallback, members, and SDK handoffs | Direct-member testing bypasses initial coordinator routing by design. |
| SDK execution | Shared hooks, tracing policy, run budget, authorization, and history checks | Private and messaging collect a result. Web Chat streams SDK events. |
| History | Full SDK messages, tool calls, results, and handoffs | Private history is owned by its admin session. Web Chat maintains customer analytics. |
| Retrieval | Same assigned tools and knowledge adapters | Draft image search derives authorized bundles from the captured draft. Knowledge contents are current. |
| Presentations | Same Web Chat hydration, citations, media, products, and A2UI renderers | An HTTP reply contains only current-turn surfaces. The presenter retains prior surfaces for actions. |
| Tool failure | Safe error returned to the model, activity status, retained conversation, no blanket answer replacement | Transport errors use HTTP status or WebSocket events. |
| Recovery | Failed writes are not automatically repeated within a run, even with changed arguments | Private HTTP wait expiry retains ongoing work and offers status recovery without resending. |
| Persistence | Shared execution checks | Private sessions and private media are ephemeral. Messaging and Web Chat retain their existing channel-specific lifecycle. |

The SDK requests are compared after removing only streaming fields and the dynamic server clock. Tests inspect serialized OpenAI-compatible requests, actual loopback API requests, and fake MCP calls. They do not compare only final model prose.

## Inputs and outputs

| Input or output | Private Chat implementation | Verification |
| --- | --- | --- |
| Text | Shared agent runner and full history | Real authenticated HTTP and WebSocket entry points; browser |
| JPG, PNG | Shared MIME validation and native image model input; catalog search uses the existing image-search pipeline | HTTP and WebSocket request comparison; draft bundle and no-match regression |
| Audio | WAV, MP3, OGG, WebM, and M4A uploads; shared STT provider and model settings | Real ffmpeg decode, SDK STT WAV requests, native Channel voice path with fake provider |
| Spoken output | Shared TTS provider, model, and voice; private WAV player | Fake TTS and authenticated media retrieval tests |
| Files | UTF-8 TXT, CSV, JSON, Markdown, and unencrypted text-layer PDF | TXT fixture through HTTP and WebSocket; same outgoing model content. PDF-specific extraction is not covered by that paired test. |
| Video | MP4, MOV, WebM; full existing Channel sampled-frame processor and evidence cards | Private HTTP and actual Channel upload, job, and inquiry paths with fake processor |
| Knowledge citations and tables | Shared `AnswerSession` and `AnswerSurface` | Paired entry-point tests; browser source expansion |
| Product and media presentations | Shared presenter, signed assets, product inquiry, A2UI actions | Paired presenter tests; product browser rendering |

The existing Channel image-search, native voice, and video-upload protocols remain supported. The WebSocket also accepts `chat.input` with shared attachments. Its generic file API does not add a new file picker to the existing customer Widget UI.

Video evidence remains sampled frames. This patch does not add continuous video understanding or audio-track transcription. Files with no text layer require page images. Office formats and arbitrary raw binary files are not added. Model and service configuration still determine supported inference capabilities.

## Authorization and secrets

Private creation requires team-admin access and `confirm_real_tools: true`. Canceling the UI confirmation sends no session or tool request. The UI states that tools can change external data.

Every private request verifies its owner and team. Execution hooks and tool guards recheck team membership, tool grants, captured configuration, and provider credentials. Drafts cannot grant access to another team's tools or knowledge. Channel checks its API key and team, and uses the same runtime grant checks. Configuration changes require a new runtime session.

Private media requires a signed asset token and the matching session-scoped HttpOnly cookie. The endpoint checks session ownership and current access. A copied token alone, another user, or an expired session cannot read the asset. Private media does not use customer upload storage or analytics.

Tool activity includes names and status, not credentials or raw outbound requests. Shared guards redact configured secrets and credential-labelled JSON fields before results reach the model. Transport and history redaction protect rendered output. SDK tracing is disabled. The messaging error logger does not print external exceptions outside the redaction scope.

Web Chat accepts only a new user message, not a replacement transcript containing fabricated tool evidence. Empty history reset remains supported.

## Budgets and lifecycle

`agent_execution.py` owns shared defaults:

| Environment variable | Default |
| --- | --- |
| `AGENT_MAX_TURNS` | 30 SDK iterations per run |
| `AGENT_MAX_HISTORY_BYTES` | 80 MiB |
| `AGENT_MAX_MESSAGE_CHARS` | 32,000 |
| `AGENT_MAX_ACTIVE_RUNS` | 4 per worker |
| `AGENT_SESSION_IDLE_SECONDS` | 7,200 for ephemeral Private sessions |
| `AGENT_RUN_TIMEOUT_SECONDS` | 180-second Private HTTP wait budget |

The HTTP wait budget is not a cancellation deadline. Work continues after HTTP 504. The session remains busy until completion, and GET session status returns the eventual reply with its request ID. The UI checks status instead of replaying a potentially mutating request. WebSocket streaming has no equivalent HTTP response wait. Provider and tool timeouts remain configured at their shared adapters.

Private has no 24-user-turn cap. Cache protections remain: four sessions per user, 100 per worker, eight attachments, 50 MiB combined attachment request, 10 MiB per image, and 10 minutes of audio. Closing a session does not undo external actions. A failed write blocks another invocation of that tool in the same model run. A later user-requested operation remains possible.

Private sessions require worker affinity because state is in memory. Restarting a backend worker clears its private history and media. Shared durable private sessions are outside this patch.

## EPC contracts

Custom API keeps legacy `query` behavior unless the administrator opts into `input_schema` on a versioned request. Structured parameters bind explicit `{{args.field}}` placeholders. JSON Schema validates arguments before HTTP.

An optional `result_contract` maps a configured status path to success, not-found, invalid-input, or service-error, including HTTP 200 responses. The tool result and activity expose that business outcome. Unknown outcomes do not become verified success. These contracts are editable in the collapsed advanced section of the Custom API editor.

No VIN, vehicle name, or EPC-specific mapping is hardcoded in application code. Tests use the supplied VIN and a fake vehicle response. The fake assigns code 2004 to invalid input to reproduce the reported distinction. This is not evidence of the real provider's definition of 2004. Existing EPC configuration is not rewritten automatically and must be reviewed against its actual API contract before release.

## Verification on 2026-11-10

All service calls use fakes and an isolated SQLite database. No Production connection, real EPC request, real model request, commit, push, or deployment was performed.

The final affected backend run passed 232 tests. The paired entry-point suite accounts for 15 tests, including parametrized cases. The frontend regression run passed 291 tests with `node --test --test-concurrency=1 tests/*.test.mjs`. One parallel rerun failed inside Node IPC deserialization, without a test assertion failure. The serial rerun passed. TypeScript, the separate Next.js build, the workflow release check, and the separately tagged backend Docker build passed. Backend tests report existing FastAPI lifespan and `audioop` deprecations. The Docker build reports the existing `FROM`/`as` casing warning.

The regression commands and release steps are in [Deploy Private Chat parity](private-chat-deploy.md).

## Changed files by responsibility

- `server/app/agent_execution.py`, `tool_execution.py`, and `runtime_access.py` own execution budgets, evidence policy, tool recovery, redaction, and grant checks. `preview_tools.py` retains compatibility imports.
- `server/app/agent_config.py` and `custom_api.py` own shared construction and optional request/result contracts. `server/pyproject.toml` and `uv.lock` declare JSON Schema validation.
- `server/app/workflow_preview.py`, `chat_inputs.py`, `chat_media.py`, and `chat_presentations.py` implement private transport, shared attachments, scoped media, and shared presentations. `knowledge_image_search.py` accepts authorized draft bundle scope.
- `server/server.py`, `app/utils.py`, `app/voice_config.py`, and `app/messaging/handler.py` use shared execution, media, history, and transport protection.
- `frontend/src/components/WorkflowPreviewChat.tsx`, `src/lib/workflow-preview.ts`, `src/lib/chat-inputs.ts`, `src/hooks/useWebsocket.ts`, `src/lib/product-presentations.ts`, `src/lib/team-workflow.ts`, and `src/lib/admin-copy.ts` implement private attachments, shared surfaces, consent, and pending-result recovery.
- `frontend/src/components/CreateToolForm.tsx`, `EditToolForm.tsx`, `CustomApiRequestEditor.tsx`, and `src/lib/custom-api.ts` expose and preserve optional contracts.
- `server/tests/parity_fakes.py`, `test_private_channel_parity.py`, and `test_workflow_preview.py` cover backend behavior. `frontend/tests/workflow-preview.test.mjs`, `custom-api.test.mjs`, and `team-workflow.test.mjs` cover UI behavior and compatibility.
- This reference, `private-chat-deploy.md`, and `docs/workflow-deployment.md` replace obsolete preview restrictions.

Browser testing used a disposable profile at localhost with fake accounts and services. It covered consent cancellation, team routing, greetings, clarification, EPC response, previous-result follow-up, source expansion, product cards, and desktop and mobile layouts. Browser screenshots exposed and led to fixes for cumulative answers and dark-mode contrast.

Browser file upload was blocked by PinchTab's disabled upload endpoint. The browser check therefore does not establish file-picker or audio/video playback correctness. Automated tests exercise those backend paths with real encoded fixtures and fake inference services. Browser upload and playback remain a release acceptance check.

This patch cannot prove that arbitrary model prose always follows evidence. The shared policy, structured results, and tests remove the preview-only blanket rule without claiming a general factuality guarantee.
