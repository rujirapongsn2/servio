# Native Metal Decision Maker for Intent Detection

Servio can classify conversation status through database keywords, a native MediaPipe Decision Maker, then the configured Intent LLM when the local result is uncertain or unavailable. Results update Monitor status only. This integration does not select an Agent, change conversation mode or perform handoff.

## Install the native service

Use native macOS on Apple Silicon. The service requests the GPU delegate and has no CPU fallback. A Linux Docker container cannot use the host's Metal runtime. Keep the service separate from the Backend and the Knowledge embedding service on port 8090.

From the repository root:

```sh
uv venv --python 3.11 server/decision_service/.venv
uv pip install --python server/decision_service/.venv/bin/python \
  -r server/decision_service/requirements.txt
mkdir -p server/decision_service/models
curl --fail --location \
  https://huggingface.co/litert-community/embeddinggemma-2-text-270m-litert-lm/resolve/main/embeddinggemma-2-text-270m.litertlm \
  --output server/decision_service/models/embeddinggemma-2-text-270m.litertlm
shasum -a 256 server/decision_service/models/embeddinggemma-2-text-270m.litertlm
```

The tested asset SHA256 is `2d079ee2f6f066b1f368e8d7c819f55214eaef1d0513b312321901f30ab286fb`. Startup rejects other weights. The profile also pins the ordered criteria, instructions and normalization. A model or question change requires a new profile and evaluation before enabling acceptance.

In the root `.env`, set a dedicated random key shared by the Backend and this service. Do not reuse an LLM or Embedding key. Generate a value with `openssl rand -hex 32` and save it locally.

```dotenv
INTENT_DECISION_API_KEY=<dedicated-random-value>
INTENT_DECISION_BIND=127.0.0.1
INTENT_DECISION_PORT=8095
# Optional. Blank uses the models/ path above.
INTENT_DECISION_MODEL_PATH=
```

Start in a native terminal:

```sh
./scripts/run_intent_decision.sh
```

The launcher uses the isolated Python environment and reads only `INTENT_DECISION_*` values from the root `.env`. It starts one model process, verifies the asset, prewarms a fixed five-choice question and completes a warmup inference before accepting requests. Use a service manager for automatic startup on reboot. The command itself stays in the foreground and does not install a startup job.

Read native logs for `Metal Residency Set successfully initialized` and `Initializing Metal-based API from graph`, followed by successful authenticated inference. `delegate_requested=GPU` alone does not prove Metal execution, and some runtime operations still use CPU.

## Configure the Backend

For a native Backend on the same Mac:

```dotenv
INTENT_DECISION_ENABLED=true
INTENT_DECISION_BASE_URL=http://127.0.0.1:8095
INTENT_DECISION_API_KEY=<same-dedicated-random-value>
INTENT_DECISION_TIMEOUT_SECONDS=1.5
INTENT_DECISION_MIN_CONFIDENCE=0.75
INTENT_DECISION_MIN_PROBABILITY=0.85
INTENT_DECISION_MIN_MARGIN=0.30
```

A Docker Backend on Docker Desktop uses `http://host.docker.internal:8095` when that host route can reach the native listener. For a separate machine, use the service's reachable HTTPS endpoint and the same dedicated key. Configure routing and firewall access deliberately; the default listener is loopback only.

Existing installations remain on keywords then LLM unless `INTENT_DECISION_ENABLED=true` is set. Keep `INTENT_MODEL`, `INTENT_BASE_URL` and `INTENT_API_KEY` as the existing LLM fallback configuration. Restart the Backend after environment changes; rebuild when installing the code in a container. Start or restart the native service separately. No change to 8090 is required. The Backend Docker build excludes `decision_service/`; its model and native environment stay on the Mac.

The three gates must all pass. SDK confidence must meet its threshold, the winning probability must meet its threshold, and the gap to second place must meet the margin. These are conservative starting settings, not a measured probability of correctness. Validate with separately labeled Thai conversation data before lowering them.

## Check health and inference

Both endpoints require `Authorization: Bearer <INTENT_DECISION_API_KEY>`. This example reads the key locally without printing it:

```sh
server/.venv/bin/python - <<'PY'
from dotenv import dotenv_values
import httpx
settings = dotenv_values('.env')
headers = {'Authorization': 'Bearer ' + settings['INTENT_DECISION_API_KEY']}
with httpx.Client(base_url='http://127.0.0.1:8095', headers=headers) as client:
    health = client.get('/health')
    health.raise_for_status()
    print(health.json())
    response = client.post('/v1/intent', json={
        'schema_version': 1,
        'context': 'user: ไม่ต้องการคืนเงินครับ ปัญหาหายแล้ว ขอบคุณครับ',
    })
    response.raise_for_status()
    print(response.json())
PY
```

Health reports readiness, busy state, expected profile, model checksum and requested delegate. The inference endpoint returns the selected group, confidence and all five probabilities. The Backend derives colors from its local canonical groups and validates the response profile and scores before using it.

The Backend sends only plain user/assistant text from its recent six entries. It excludes tool/system messages, identifiers and metadata. Context over 2048 UTF-8 bytes goes directly to the existing LLM path rather than being silently truncated. The existing LLM context behavior remains unchanged.

Low confidence, a small margin, invalid scores/profile, bad credentials, oversized content, a busy model, timeout or network failure all fall through to LLM. There are no native retries or per-message health probes. The service admits one inference at a time and rejects extra work promptly. If a caller disconnects, the admission slot stays occupied until that native inference finishes.

With INFO logging enabled for `app.intent_service`, Backend logs record `Intent classification source=keywords`, `source=decision` or `source=llm` after successful status updates. They do not log conversation text or credentials. If native inference fails, health becomes unavailable until restart; the Backend can continue through its LLM fallback.

## Regression checks

```sh
PYTHONPATH=server OPENAI_API_KEY=test-no-network \
  server/.venv/bin/python -m pytest -q \
  server/tests/test_intent_service.py \
  server/tests/test_intent_decision.py \
  server/tests/test_intent_decision_service.py
```

These tests use boundary fakes and do not prove GPU execution. Verify the real native logs, authenticated requests, accepted results and LLM fallback separately. Synthetic A/B results are diagnostic evidence, not a production accuracy guarantee.

When the native stage is enabled, Settings > System Information shows Intent Decision Maker as Configured or Configuration required. This row checks configuration only. Use the authenticated native health endpoint to check availability and the expected profile.

## Start automatically at user login

Install the native runtime and user LaunchAgent after configuring the dedicated key and downloading the verified model:

```sh
server/.venv/bin/python scripts/install_intent_decision_macos.py
```

The installer copies only the native service, shared decision contract, model and dedicated credentials into `~/Library/Application Support/Servio/IntentDecision`. This avoids macOS background access restrictions on Documents, Desktop and Downloads. Each installation prepares a separate release and Python environment before stopping the existing job. A startup failure restores the previous job. It keeps credentials in a private `.env`, outside the LaunchAgent plist. It does not copy the Backend's other keys.

The job starts after user login. It does not enable automatic macOS login or run before a user session exists. Stop any foreground instance before installing so only one process owns the port. The installer checks ownership before replacing an existing job.

Rerun the installer after changing native source, requirements or service environment values. It refreshes the runtime copy and restarts the owned job. To restart without changing installed files:

```sh
launchctl kickstart -k "gui/$(id -u)/ai.softnix.servio.intent-decision"
```

Recheck authenticated health and inference after installation. Inspect `server/decision_service/.cache/service.stderr.log` inside the installed release for Metal initialization and successful startup. `deployment.json` in the runtime directory records the active release, source hashes and originating checkout. Previous releases remain available for rollback.
