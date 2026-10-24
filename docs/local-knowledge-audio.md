# Run local audio knowledge

WAV and MP3 uploads become OKF sources with original assets and timestamped local transcripts. Native audio vectors use a separate 768-dimensional table. Transcript excerpts use the existing text and keyword search. The audio feature defaults to off.

## Start the local processor

Install `ffmpeg` and `ffprobe`. Build the official whisper.cpp CLI with CPU support, or Metal support for Apple Silicon. Download a local Whisper model and Silero VAD model. The processor requires VAD and never falls back to a hosted ASR service.

Set absolute paths and exact weight revisions in your shell.

```sh
export KNOWLEDGE_AUDIO_WHISPER_CLI=/absolute/path/whisper-cli
export KNOWLEDGE_AUDIO_WHISPER_MODEL=/absolute/path/ggml-medium.bin
export KNOWLEDGE_AUDIO_VAD_MODEL=/absolute/path/ggml-silero-v6.2.0.bin
export KNOWLEDGE_AUDIO_ASR_REVISION=whisper-medium-WEIGHTS_SHA-silero-v6.2.0-WEIGHTS_SHA
./scripts/run_audio_processor.sh
```

For Metal transcription, point `KNOWLEDGE_AUDIO_WHISPER_CLI` to a Metal-enabled build and set `KNOWLEDGE_AUDIO_USE_GPU=true` in the processor environment. The default is `false`, which explicitly disables GPU use. Accepted values are `true`/`1`/`yes` and `false`/`0`/`no`. Enabling this flag permits the CLI to use its compiled GPU backend; verify actual Metal initialization in a direct CLI acceptance run. It does not enable GPU offload for native audio embeddings.

To build Metal support from an existing whisper.cpp checkout, use a separate build directory. Keep the existing CPU build available for rollback.

```sh
export WHISPER_CPP_SRC=/absolute/path/whisper.cpp
cmake -S "$WHISPER_CPP_SRC" -B "$WHISPER_CPP_SRC/build-metal" -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON
cmake --build "$WHISPER_CPP_SRC/build-metal" --config Release --target whisper-cli -j 2
export KNOWLEDGE_AUDIO_WHISPER_CLI="$WHISPER_CPP_SRC/build-metal/bin/whisper-cli"
export KNOWLEDGE_AUDIO_USE_GPU=true
./scripts/run_audio_processor.sh
```

Keep the model, VAD, and revision exports above when running these commands. To return to CPU execution, select the previous CLI path and set `KNOWLEDGE_AUDIO_USE_GPU=false`.

The launcher uses `server/.venv/bin/python`. Set `KNOWLEDGE_AUDIO_PYTHON` to use another Python environment with the backend dependencies installed. The processor listens on `127.0.0.1:8094`. Keep this service on a trusted local interface. It accepts raw audio bytes at `/preview`, `/extract`, and `/normalize`.

### Keep the Mac mini processor running

The Mac mini uses the user LaunchAgent `ai.softnix.servio.audio-processor`, installed at `~/Library/LaunchAgents/ai.softnix.servio.audio-processor.plist`. It starts after login and restarts the processor if it exits. It does not start before a user logs in after reboot.

The plist also needs `KNOWLEDGE_AUDIO_USE_GPU=true` for Metal transcription, a Metal-enabled `KNOWLEDGE_AUDIO_WHISPER_CLI`, and the desired `KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS`. Shell exports do not change a loaded LaunchAgent. The plist sets the repository's Python executable and server working directory, the local Whisper and VAD paths, the ASR revision, and a `PATH` that includes `/opt/homebrew/bin` for FFmpeg. Current model assets are under `.audit/knowledge-audio/asr`; retain that directory while the service uses those paths. Update the plist before moving the repository, virtual environment, or model files.

Check the service and its dependencies:

```sh
launchctl print gui/$(id -u)/ai.softnix.servio.audio-processor
curl --fail http://127.0.0.1:8094/health
```

Health must return `ready: true`. Its `use_gpu` field reports the configured flag, rather than proof of GPU initialization. Logs are under `.audit/knowledge-upload-limits/audio-processor.*.log`. To restart the loaded service after a code change:

```sh
launchctl kickstart -k gui/$(id -u)/ai.softnix.servio.audio-processor
```

## Start native audio embeddings

Use the BF16 model and matching BF16 projector from [ggml-org/embeddinggemma-2-GGUF](https://huggingface.co/ggml-org/embeddinggemma-2-GGUF). Keep both files from the same pinned revision. For example, revision `bfcd298762cc34d0357ece5ebdd31791a3a374d8` contains `embeddinggemma-2-BF16.gguf` and `mmproj-embeddinggemma-2-BF16.gguf`.

Run the launcher with paths to your downloaded files.

```sh
AUDIO_MODEL_PATH=/absolute/path/embeddinggemma-2-BF16.gguf \
AUDIO_MMPROJ_PATH=/absolute/path/mmproj-embeddinggemma-2-BF16.gguf \
./scripts/start-knowledge-audio.sh
```

The launcher binds to `127.0.0.1:8093`, uses two CPU threads, and disables GPU offload for both files. It fixes the alias to `servio-embeddinggemma2-audio`. Set `LLAMA_SERVER_BIN` to select a compatible llama-server executable, or `AUDIO_SERVER_PORT` to change the port. Ports 8090, 8091, and 8092 are rejected. The launcher requires readable local files and does not download weights.

The native embedding request uses `input_audio` with base64 WAV data and expects 768 output dimensions. Text queries use `task: search result | query: `.

## Enable the backend

Set these backend environment values.

```dotenv
LOCAL_KNOWLEDGE_AUDIO_ENABLED=true
AUDIO_PROCESSOR_BASE_URL=http://host.docker.internal:8094
KNOWLEDGE_AUDIO_TIMEOUT_SECONDS=2220
AUDIO_EMBEDDING_BASE_URL=http://host.docker.internal:8093/v1
AUDIO_EMBEDDING_MODEL=servio-embeddinggemma2-audio
AUDIO_EMBEDDING_REVISION=EXACT_WEIGHTS_SHA-EXACT_AUDIO_PROJECTOR_SHA
```

For both BF16 files from the example revision, set `AUDIO_EMBEDDING_REVISION=ggml-org-embeddinggemma-2-GGUF-bfcd298762cc34d0357ece5ebdd31791a3a374d8-bf16-mmproj-bf16`. Update this value whenever either file changes.

For a backend running directly on the host, use `127.0.0.1` instead of `host.docker.internal`. The alias `KNOWLEDGE_AUDIO_PROCESSOR_URL` also works when `AUDIO_PROCESSOR_BASE_URL` is absent.

Rebuild the backend and frontend after installing this change. Restart the backend after changing environment values. Existing text and image services on ports 8090, 8091, and 8092 keep their current configuration.

## Import and refresh audio

Upload WAV or MP3 through Local Knowledge. Preview validates format and duration without ASR. The existing background import job performs local transcription and indexes the audio. An embedding failure preserves the imported original and transcript and reports an index warning. Use **Reindex vectors** to retry embeddings without retranscription.

Use **Reindex** to transcribe the original again. Audio and enabled text vectors build before source replacement. Decoder, ASR, embedding, concurrent edit, or database errors preserve the prior source. A successful refresh replaces the source and both indexes in one database transaction.

Queries combine native audio ranking and transcript ranking by canonical segment. Exact transcript matches receive higher weight. Overlapping or repeated windows collapse. Native audio similarity alone does not establish facts. A clip without recognized speech displays **ไม่มีบทถอดเสียง**.

## Limits

- The maximum upload is 50 MiB with one WAV or MP3 audio stream.
- All files in one Add Knowledge upload together must fit within 50 MiB, including documents, images, and audio. The interface shows the selected total and blocks review until excess files are removed.
- The default duration limit is 600 seconds. `KNOWLEDGE_AUDIO_MAX_SECONDS` can lower it.
- The default segment length is 20 seconds with 2 seconds of overlap. `KNOWLEDGE_AUDIO_SEGMENT_SECONDS` permits 5 to 60 seconds. `KNOWLEDGE_AUDIO_OVERLAP_SECONDS` permits 0 to 10 seconds, capped at half the segment length.
- The processor accepts one inference or decode operation at a time. A busy processor returns 429. Import or refresh fails clearly and can be retried.
- ASR uses two CPU threads, automatic language detection, and required local VAD. `KNOWLEDGE_AUDIO_USE_GPU` defaults to `false`; `true` allows a GPU-capable Whisper build to use its GPU backend. `KNOWLEDGE_AUDIO_ASR_TIMEOUT_SECONDS` defaults to 1200 seconds and clamps to 1 through 1800 seconds in the processor.
- Backend HTTP timeout `KNOWLEDGE_AUDIO_TIMEOUT_SECONDS` defaults to 2220 seconds and clamps to 2161 through 3600 seconds. The floor exceeds the processor's maximum ASR budget of 1800 seconds plus upload 60, probe 120, decode 120, and response margin 60. It covers the maximum even when backend and processor environments differ. Old values such as 1200 are raised to the floor with a warning. Preview and normalization use the same HTTP budget but skip ASR. Invalid or non-finite timeout settings fail safely.
- Import timeout errors identify upload, probe, decode, transcription, or the backend request stage. Refresh retains its existing generic error message. Logs include elapsed time and the effective timeout without subprocess output. A transcription timeout comes from the processor; a request timeout means the backend stopped waiting. Failed refreshes retain the previous source and index.
- Playback links expire after 15 minutes. Each request checks current team access, source hash, original asset hash, and contained paths without symlinks. Full and single byte-range requests are supported.
- Transcript accuracy depends on the recording and local model. Recognized Thai and English samples do not guarantee correct facts in every recording.

Changing the ASR model, VAD model, segmentation, or preprocessing requires a source refresh. Switching CPU/Metal execution alone keeps the same fingerprint and does not require a refresh; newly generated transcripts may differ slightly. Changing native weights or projector requires a new `AUDIO_EMBEDDING_REVISION` and vector reindex. The fingerprint includes the model alias, explicit weight revision, query prefix, preprocessing, segmentation, and ASR revision.

## Verify changes

From `server`, run the isolated tests.

```sh
python -m pytest tests/test_knowledge_audio.py tests/test_audio_processor.py tests/test_knowledge_images.py tests/test_local_rag.py tests/test_local_rag_coverage.py -q
```

From `frontend`, run `npm run test:regression` and `npx tsc --noEmit --incremental false`. Real model acceptance also needs a dedicated PostgreSQL database and the local processor and native embedding service.
