# Configure production models

Start a new installation with the root [.env.example](../.env.example). Keep an existing `.env` and add only the settings you need. Set a stable, randomly generated `JWT_SECRET_KEY` before starting. Never copy credentials into Git.

## Set runtime defaults

Set the required model IDs and compatible provider endpoints in `.env`. The following settings are read by the backend at startup.

| Work | Model setting | Endpoint and credentials |
| --- | --- | --- |
| New Agent | `DEFAULT_AGENT_MODEL` | `OPENAI_BASE_URL`, `OPENAI_API_KEY`, or the selected saved provider |
| Default provider choices | `DEFAULT_AGENT_MODELS` | Comma-separated model IDs; the default is always included |
| Coordinator | `COORDINATOR_MODEL` | The team's selected provider; otherwise the global OpenAI provider |
| Intent classification | `INTENT_MODEL` | `INTENT_BASE_URL`, `INTENT_API_KEY` |
| Conversation enrichment | `ENRICHMENT_MODEL` | `ENRICHMENT_BASE_URL`, `ENRICHMENT_API_KEY` |
| Optimize without an explicit Agent model | `PROMPT_OPTIMIZE_MODEL` | `PROMPT_OPTIMIZE_BASE_URL`, `PROMPT_OPTIMIZE_API_KEY` |
| Gemini File Search | `GEMINI_FILE_SEARCH_MODEL` | `GEMINI_API_KEY` |
| Live speech recognition | `VOICE_STT_MODEL` | `VOICE_BASE_URL`, `VOICE_API_KEY` |
| Live speech synthesis | `VOICE_TTS_MODEL`, `VOICE_TTS_VOICE` | `VOICE_BASE_URL`, `VOICE_API_KEY` |
| Welcome speech | `VOICE_WELCOME_TTS_MODEL`, `VOICE_WELCOME_TTS_VOICE` | `VOICE_BASE_URL`, `VOICE_API_KEY` |

Blank endpoint/key overrides for intent, enrichment, Optimize and voice use `OPENAI_BASE_URL` / `OPENAI_API_KEY`. If the global URL is blank, the SDK uses its OpenAI default.

Saved Agent models and provider records remain authoritative. Changing `DEFAULT_AGENT_MODEL` affects new Agents and missing-value fallbacks; it does not rewrite existing Agents such as Sales. An explicit model in a Gemini tool also remains authoritative. Newly generated Gemini tools follow the deployment default.

Leave `COORDINATOR_MODEL` blank to preserve the team's fallback Agent model/provider. Set it only when that provider supports the chosen routing model. Optimize uses the model/provider selected in the Agent editor when supplied, so an explicit selection takes precedence over its environment default.

Set a model ID that the target API actually serves. Changing an ID does not add Responses, Chat Completions, image, speech or tool-call support to a provider. Default OpenAI Agents use the SDK's Responses API; configured custom providers use the existing Chat Completions integration.

## Choose the OCR and image QA source

Keep `IMAGE_OCR_MODEL_SOURCE=database` and `IMAGE_QA_MODEL_SOURCE=database` to select models through Settings > Providers. Clearing or disabling a saved selection keeps that task unavailable.

To manage a task from `.env`, set its source to `environment` and supply all three corresponding values. For example, for a local OpenAI-compatible vision server:

```dotenv
IMAGE_OCR_MODEL_SOURCE=environment
IMAGE_OCR_MODEL=your-vision-model
IMAGE_OCR_BASE_URL=http://host.docker.internal:8095/v1
IMAGE_OCR_API_KEY=not-required
LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED=true
```

Use the `IMAGE_QA_` prefix for QA. Environment mode requires dedicated credentials, including a nonempty local token when authentication is unnecessary. It never borrows a database provider key or the global OpenAI key. Settings shows the effective source and locks that task's database selector. The other task can still use a database selection.

The feature flags `LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED` and `LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED` control whether the tasks run. Setting a model alone does not enable them.

## Configure embedding and transcription services

Set text embedding with `EMBEDDING_BASE_URL` and `EMBEDDING_MODEL`, image embedding with `MULTIMODAL_EMBEDDING_BASE_URL` and `MULTIMODAL_EMBEDDING_MODEL`, and audio embedding with `AUDIO_EMBEDDING_BASE_URL` and `AUDIO_EMBEDDING_MODEL`.

For the shared GPU service on the current Mac host, point the image endpoint at `http://host.docker.internal:8090/v1` in Docker, or `http://127.0.0.1:8090/v1` for native Python. Use a model ID served by that instance. The sample's separate service ports are defaults for other installations, not a requirement to start extra services.

All three vector stores require **768 dimensions**. When changing embedding weights, projection or query prefixes, reindex the corresponding corpus. Change `MULTIMODAL_EMBEDDING_SPACE` for a new image vector space and `AUDIO_EMBEDDING_REVISION` for a new audio space. Matching dimensions alone does not make old and new embeddings comparable. Text embeddings also require reindexing after a model change.

The separate audio processor uses `KNOWLEDGE_AUDIO_WHISPER_CLI`, `KNOWLEDGE_AUDIO_WHISPER_MODEL`, `KNOWLEDGE_AUDIO_VAD_MODEL` and `KNOWLEDGE_AUDIO_ASR_REVISION` in its own process environment. Restart that processor after changing them. `AUDIO_PROCESSOR_BASE_URL` tells the backend where it runs.

Image query filtering uses `MULTIMODAL_IMAGE_QUERY_MIN_SCORE`, `MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP` and `MULTIMODAL_IMAGE_QUERY_MAX_RESULTS`. Keep their validated values when changing unrelated model defaults. The application currently has no runtime reranker integration.

## Apply configuration

After editing `.env` in a Docker deployment, run:

```bash
./services.sh restart backend
./services.sh status
```

The restart command recreates the selected container so Docker applies the new environment. It preserves database volumes. Restarting only the backend also refreshes nginx upstream resolution. Use `./services.sh rebuild backend` after Python source or dependency changes.

For native Python, stop and relaunch the backend from the same checkout. The backend loads the root `.env` before application modules, while variables already supplied by the process take precedence. Remove or update conflicting service-manager variables if a `.env` edit appears ineffective.

Workflow and the legacy Agent editor fetch model defaults from the backend at runtime. Changing these defaults does not require a frontend rebuild. Changes to `NEXT_PUBLIC_*` URLs still require rebuilding the frontend because Next.js embeds them during the build.

Check the authenticated `/api/admin/model-defaults` and `/api/admin/image-model-defaults` responses for model IDs and effective sources. These endpoints do not return credentials. Test a new Agent, Optimize, image retrieval and any enabled voice features against the selected provider before routing production traffic.
