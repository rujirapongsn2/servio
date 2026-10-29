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

Both tasks default to disabled. No vision provider is selected automatically. Image bytes are sent to the provider assigned to the corresponding task, so choose a provider appropriate for the Knowledge data. The configured local image embedding service handles visual retrieval separately.

JPG/PNG review validates file size, format, image decoding and duplicates without calling OCR or product models. Image text and product observations are extracted during background import, which reports progress per file. This keeps multi-image review requests short enough for the web proxy and avoids paying for the same inference during both review and import. URL image reviews follow the same rule. For existing images, use the Knowledge **Re-index** action to regenerate source text and vectors. **Re-index Vectors** alone embeds existing source text. Failed or truncated OCR reports a warning on import; a failed OCR refresh preserves the previous source. OCR can misread small or unclear text, so original images remain available for verification.

### Product names, models and colors

When Image Q&A is enabled and assigned a model, JPG/PNG imports also extract structured product observations. Each image can contain multiple products, with separate name, model, SKU, visual category (English `category` and Thai `category_th`), color labels, broad color families and identifying evidence. Recognizable products without labels are included by category: an unlabeled red sofa can have category `sofa` / `โซฟา` and red visual color while name, model and SKU remain null. Official names and identifiers must be visible. Color evidence distinguishes a visible product color from colors explicitly listed in catalog text. Background and packaging colors must not be used as product colors. Extraction remains fallible and records start as `unreviewed`.

OCR uses a validated JSON response with `text` and `status` (`ready` or `empty`). Empty images produce empty text, not a sentence describing the absence of text. Plain conversational replies, malformed responses and inconsistent statuses are treated as unavailable and are not cached as successful OCR. A failed import retains the image and warns; a failed refresh preserves the previous source. Stored `image_text_status` distinguishes valid text, empty text and unavailable extraction. The assigned provider must support images and OpenAI-compatible JSON object responses. Structured extraction does not request image-answer citations, which would conflict with its JSON schema.

Observations are stored in the image concept's `image_products` frontmatter with a schema version, original image hash, model ID and extraction time. A readable copy is included in the body for existing lexical and hybrid retrieval. Image previews return `text_status=not_requested`, empty text and `image_products=null`. No database migration or new provider task assignment is required; this uses the existing Image Q&A model and feature flag and adds up to two vision requests per imported image, in addition to optional OCR.

Extraction first identifies products, then runs a separate body-color inspection using their identities without supplying the initial color guesses. Only the second pass supplies visual colors. Catalog text colors are retained only when their literal labels also occur in OCR text; enable OCR to retain these listed variants. Failure or incomplete product coverage in color verification rejects the extraction instead of publishing partial color claims. This reduces background-color contamination but does not guarantee correctness; both passes still use the assigned vision model.

Material swatches (tile, stone, flooring, fabric and paint) may fill the entire image. Their surface is the product face, even when no separate object outline or label is visible. The user-supplied collection name accompanies extraction as `catalog_context`; `category_basis=catalog_context` records context-assisted classification. It never establishes a brand, model, SKU, material composition or color. Colors still require the separate visual inspection. Repeated shapes within one swatch stay together as one product pattern. Re-index uses the collection's current name and preserves the original image as evidence.

Agent knowledge searches match stored names, English/Thai categories and exact model/SKU identifiers before image similarity. Known product lookups combine their structured records with lexical excerpts without depending on either text or image embeddings. Exact identifiers take precedence over generic name or category matches, and requested color families help rank variants. Categories never establish an official name or model number. Returned product records retain their own colors and original-image references, bypassing the embedding service's default one-image limit. Color questions with stored color evidence do not require another live vision request. Other image questions retain the existing Image Q&A path. Broad family matches (for example, red and burgundy) do not prove an exact shade match. Missing records never establish that a variant does not exist, and catalog observations never establish current stock.

For older images, run **Re-index** with Image Q&A enabled; **Re-index Vectors** does not extract products. Extraction failure on import retains the image and reports a warning. Extraction failure during Re-index preserves the previous source. OCR-only refreshes preserve product observations; product-only refreshes preserve OCR. If any product in an image has been explicitly marked `confirmed` in its source metadata, automatic refresh preserves that image's complete product set. A dedicated product review editor is not included in this backend change.

Knowledge tools reuse identical text searches within one SDK Agent run, including concurrent duplicate requests. Reuse is scoped to the runtime team, bundle and tool settings, and ends with that run. A new user turn searches again. Failed searches remain retryable, and SQL and schema requests keep their existing freshness behavior. Query normalization preserves spaces inside quoted filenames. This prevents duplicate retrieval work even when a model emits redundant tool calls.

Agents with Knowledge tools receive customer reply guidance: answer simple product/color questions in one or two short sentences, state the catalog match first, mention unknown stock briefly, and omit internal processing descriptions and generic closing invitations. Longer explanations and comparisons remain available when requested. Source references and required image presentation markers remain supported.

When both document knowledge and an image library are assigned, product browsing and color questions search the image library even without an explicit request for photos. Document or table results alone cannot display images. Official names and specifications may be supplemented from documents using exact source filenames. Image cards provide source attribution for simple shopping replies, avoiding long filename lists in customer text; evidence questions still cite sources explicitly.

Run `cd server && .venv/bin/python -m pytest tests/test_knowledge_products.py tests/test_knowledge_vision.py tests/test_knowledge_images.py` for mocked extraction, stored-product lookup, variant separation, access and source integrity regressions. Evaluate real catalog images separately to measure model accuracy.

Run `cd server && .venv/bin/python -m pytest tests/test_knowledge_turn.py tests/test_knowledge_runtime_scope.py tests/test_queryable_knowledge.py` to check duplicate lookup reuse, per-turn freshness and team isolation.

Run `docker compose exec -T backend .venv/bin/python < scripts/check-image-products.py` from the repository root for a live synthetic regression using the configured model. It checks two distinct model identifiers and a blue product on a red background without writing catalog records. A passing synthetic case does not measure accuracy on real catalogs.

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

Image-to-image product search uses separate settings:

```dotenv
MULTIMODAL_IMAGE_QUERY_MIN_SCORE=0.82
MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP=0.06
MULTIMODAL_IMAGE_QUERY_MAX_RESULTS=5
```

A product must meet the absolute similarity floor and remain within the score gap of the best available source. The result limit is a maximum, so search can return fewer products or no match. Scores must be finite cosine similarities between -1 and 1. The floor accepts that same range, and the gap accepts 0 through 2. Recalibrate these settings against matching and unrelated query images when the encoder or catalog changes.

Change `MULTIMODAL_EMBEDDING_SPACE` whenever the weights, projector, image token budget, or other encoder settings change. Rebuild image vectors through **Re-index Vectors** before querying the changed space. Existing text vectors remain in `okf_rag_chunks`; image vectors use the separate `okf_image_vectors` table.

## Use a shared GPU service on 8090

An existing text embedding service can also serve image embeddings when it loads the matching vision projector. A text-only service started with `--no-mmproj` cannot encode images. Keep its text embedding endpoint available when adding image support.

For the shared EmbeddingGemma 2 service whose model ID is `ggml-org/embeddinggemma-2-GGUF:BF16`, configure the backend as follows:

```dotenv
LOCAL_KNOWLEDGE_IMAGES_ENABLED=true
MULTIMODAL_EMBEDDING_BASE_URL=http://host.docker.internal:8090/v1
MULTIMODAL_EMBEDDING_MODEL=ggml-org/embeddinggemma-2-GGUF:BF16
MULTIMODAL_EMBEDDING_SPACE=embeddinggemma2-bf16-mmproj-shared8090-v1
```

Use `http://127.0.0.1:8090/v1` for a native backend. Use the model ID exposed by your service if it differs. Keep text retrieval settings unchanged. The standalone CPU launcher and its 8092 defaults remain available as a fallback.

Before switching, check the candidate encoder against every stored image vector in the bundles you plan to use. Provide `DATABASE_URL` and the absolute `OKF_STORAGE_DIR` through the operator environment. The script does not load `.env`, modify the database, or change a running service.

```sh
server/.venv/bin/python scripts/check-image-embedding-compatibility.py \
  --bundle-id 16 \
  --base-url http://127.0.0.1:8090/v1 \
  --model ggml-org/embeddinggemma-2-GGUF:BF16
```

Repeat `--bundle-id` for each bundle. The command uses the application's image validation, EXIF orientation, RGB conversion, and 1536-pixel resize. It verifies the source and asset hashes before sending image bytes to the candidate service. A successful check exits with code 0, reports a cosine similarity of at least 0.995 for every image, and retrieves the same original asset as the nearest stored vector. Duplicate concepts containing the same asset are allowed. Missing vectors, stale sources, dimension mismatches, or a wrong nearest asset fail the check. Output contains identifiers and numeric results, without image bytes, signed links, or credentials.

A passing comparison establishes agreement on the checked corpus. It does not establish compatibility for every possible image. Test real image searches and text queries after the switch, including near-duplicate products.

The client space includes the model ID, query prefix, encoder space, and image preprocessing version. Changing only the model alias therefore changes the space even when measured vectors agree. Use **Re-index Vectors** for each affected bundle after selecting the candidate configuration. This regenerates image vectors from validated originals already in the Knowledge bundle. Re-upload and OCR are unnecessary. Do not relabel old vectors to bypass the space check. If compatibility fails, rebuild vectors before serving searches through the new encoder. Changing the encoder space also requires a rebuild.

The index stores one encoder space per image. Coordinate the index replacement and backend restart in a short maintenance window, or validate a staged index first, so requests do not use mismatched settings. Restart the backend after changing its environment, then verify image search returns the expected source cards. To return to the CPU service, restore its URL and model settings and rebuild the affected image vectors for that space.

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

Product carousel labels can use assigned catalog tables with `product_name` and `sha256` columns. The image byte hash must match exactly. Optional `sku_or_color_code` and `brand` values appear on the card; source filenames remain in the details dialog. Conflicting labels for the same hash fall back to the existing image title. Catalog metadata changes display identity only, never visual color evidence or stock.


### Tile surface similarity

Assigned, source-validated tile observations expand the reranker candidate pool without treating the vector cutoff as a final rejection. A query is independently checked for a hard material surface before comparing tile candidates. Each image is classified independently; multi-product vision comparisons are not used. Ranking combines the stored pattern family, foreground HSV color/tone, rotation-invariant local binary patterns, and repeated straight grout joints. Image margins are removed only in derived comparison views. Model-generated candidate identities are never accepted. No image or text preference can establish model identity, material composition or stock.

Results prefer matching pattern and color, otherwise show one explicitly labeled partial group (similar color with a different pattern, or similar pattern with unconfirmed color). Unrelated/uncertain inputs and insufficient comparisons return no match; model failures remain unavailable errors. Each surface result carries its comparison note in details. Import also records optional surface_pattern and pattern_description observations for subsequent text retrieval; existing tile records can use visual comparison without reimporting. Original evidence bytes are preserved.
