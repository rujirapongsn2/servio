# Local Knowledge image search

Users can upload JPG/JPEG and PNG alongside existing documents. A text query retrieves related images and displays source cards beside the assistant's normal answer. Select **ดูภาพต้นฉบับ** to view the validated original file. Escape or **ปิด** closes the image and returns focus.

This feature searches visual similarity. It does not perform OCR or pass image pixels to the answer model. The answer must not infer visual details from a filename. Text documents continue to supply ordinary excerpts. Audio and video uploads are not supported.

## Enable the isolated service

Run the standalone CPU launcher with an EmbeddingGemma 2 GGUF and matching vision projector.

```sh
MULTIMODAL_MODEL_PATH=/absolute/path/embeddinggemma-2-BF16.gguf \
MULTIMODAL_MMPROJ_PATH=/absolute/path/mmproj-BF16.gguf \
./scripts/start-knowledge-multimodal.sh
```

The launcher binds to `127.0.0.1` on port 8092 and uses two CPU threads. It does not stop or change the existing text embedding service on 8090 or the reranker on 8091. Use `LLAMA_SERVER_BIN`, `MULTIMODAL_PORT`, and `MULTIMODAL_THREADS` to override the executable, port, or thread count. Check that Docker can reach the host service before enabling this feature in a container.

Configure the backend and recreate or restart its container.

```dotenv
LOCAL_KNOWLEDGE_IMAGES_ENABLED=true
MULTIMODAL_EMBEDDING_BASE_URL=http://host.docker.internal:8092/v1
MULTIMODAL_EMBEDDING_MODEL=servio-embeddinggemma2-images
MULTIMODAL_EMBEDDING_SPACE=embeddinggemma2-bf16-mmproj-vision256-v1
MULTIMODAL_EMBEDDING_TIMEOUT_SECONDS=180
MULTIMODAL_IMAGE_MIN_SCORE=0.15
MULTIMODAL_IMAGE_MAX_RESULTS=1
```

For a native backend, use `http://127.0.0.1:8092/v1`. The feature is disabled by default. Retrieval shows the best matching image by default; `MULTIMODAL_IMAGE_MAX_RESULTS` allows up to five candidates. The image model must return finite 768-dimensional vectors for both images and text queries. Only base64 image bytes are sent to inference. The inference client never forwards a user URL or filesystem path.

Change `MULTIMODAL_EMBEDDING_SPACE` whenever the weights, projector, image token budget, or other encoder settings change. Rebuild image vectors through **Re-index Vectors** before querying the changed space. Existing text vectors remain in `okf_rag_chunks`; image vectors use the separate `okf_image_vectors` table.

## Import and query

1. Open **Add Knowledge**, select **Upload Files**, and choose JPG/PNG files and any text documents.
2. Review the import result. Image inference runs sequentially after the source bundle commits. Failed indexing retains the uploaded source and reports a warning. Retry **Re-index Vectors** when inference is ready.
3. Assign the generated Knowledge capability to an agent. Ask a text question in Web Chat, or use the Knowledge test panel.
4. Open an image reference to inspect its original source.

Images are limited to 10 MB and 20 megapixels. The server decodes actual JPG/PNG data and rejects malformed or animated images. Embedding input is resized to fit 1536 pixels with EXIF orientation applied; stored originals retain their exact validated bytes. Image-only bundles contain descriptive source metadata, not invented visual descriptions.

## Access and retention

Knowledge and active-team access are checked before image inference. Only authorized retrieval mints original-image links. Model-visible tool output contains unsigned source references. The WebSocket layer validates each reference against its current team before issuing signed UI links, keeping the bearer grants out of model history. These bearer links expire after 15 minutes and contain a purpose-scoped signature, never API keys or administrator credentials. Anyone holding an unexpired link can view its one image while the signed team still has access. Do not share a link outside its intended audience.

The asset endpoint checks signature, expiry, current bundle/team access, concept source hash, original byte hash, and path containment. Responses use `private, no-store`, `nosniff`, and `no-referrer`. Configure access logs to omit query strings for `/api/knowledge-images/`, since the query contains a short-lived bearer token. For disposable local acceptance servers, use Uvicorn `--no-access-log`.

Deleting a bundle removes its files and image vectors. Source changes invalidate old references immediately. A failed or concurrent re-index cannot replace the complete index with a partial one, and stale source hashes are filtered at query time. If image retrieval is unavailable, text retrieval still responds and clearly states that images were not searched.

Original links already displayed in old chat messages expire. Ask the question again to retrieve new links.

## Tests

```sh
cd server
uv run --with pytest pytest tests/test_knowledge_images.py
cd ../frontend
node --test tests/product-carousel.test.mjs
npx tsc --noEmit
```

The focused tests cover binary validation, EXIF orientation, original bytes, signed access, expiration, revoked teams, other teams, tampering, source changes, deletion, feature-off behavior, text fallback, client targeting, presentation parsing, and visible assistant answers alongside images. Live acceptance additionally requires a real vision-enabled 8092 service and PostgreSQL with pgvector.
