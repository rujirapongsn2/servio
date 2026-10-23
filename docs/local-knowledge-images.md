# Local Knowledge image search

Users can upload JPG/JPEG and PNG alongside existing documents. A text query retrieves related images and displays source cards beside the assistant's normal answer. Select **ดูภาพต้นฉบับ** to view the validated original file. Escape or **ปิด** closes the image and returns focus.

Image similarity search remains independent of text retrieval. Optional OCR adds visible image text to the normal Knowledge source and Hybrid Search index. Optional image question answering reads authorized originals through a separately selected vision model. Answers use OCR and visual evidence with source labels, never filenames as evidence. Audio and video uploads are not supported.

## Configure OCR and image answers

In **Settings → LLM Providers → Models**, select **Add Model**, enter the provider's exact Model ID, and enable **Vision**. Model registration is manual and works even when a provider does not expose a models-list endpoint. Only super administrators can modify registrations and defaults.

Select an enabled vision model under **JPG/PNG OCR** and **Image Q&A**, then **Save Defaults**. These are separate task assignments; the provider and model used for ordinary agent chat are independent. Disabling a model, removing its Vision capability, or deleting it clears its image task assignments.

Enable the required tasks on the backend:

```dotenv
LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED=true
LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED=true
```

Both tasks default to disabled. No vision provider is selected automatically. Image bytes are sent to the provider assigned to the corresponding task, so choose a provider appropriate for the Knowledge data. The local 8092 image embedding service continues to handle visual retrieval separately.

New JPG/PNG imports and previews extract OCR text when configured. For existing images, use the Knowledge **Re-index** action to regenerate source text and vectors. **Re-index Vectors** alone embeds existing source text. Failed or truncated OCR reports a warning on import; a failed OCR refresh preserves the previous source. OCR can misread small or unclear text, so original images remain available for verification.

At query time, the vision model reads up to three retrieved, authorized originals. Its answer cites `[Image 1]` and the corresponding source label. A vision failure retains OCR/text retrieval and original-image cards. Models receive image bytes rather than signed asset links or administrator credentials. Existing document extraction and PDF OCR are unchanged.

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

The focused tests cover binary validation, EXIF orientation, original bytes, signed access, expiration, revoked teams, other teams, tampering, source changes, deletion, feature-off behavior, text fallback, client targeting, presentation parsing, and visible assistant answers alongside images. Run `tests/test_provider_models.py` and `tests/test_knowledge_vision.py` for catalog/default validation, OCR search, refresh preservation, incomplete completions and authorized image answers. Live acceptance additionally requires a real vision-enabled 8092 service, a configured vision provider, and PostgreSQL with pgvector.
