# Configure product image matching

Enable category verification to find catalog products from a different photograph or model of the same functional product type. The query image and a bounded set of catalog candidates go to the effective Image Q&A vision provider. Returned cards always use existing, authorized catalog originals.

## Configure the vision provider

Select a vision-capable Image Q&A model in Settings > Providers, or use its existing environment mode:

```dotenv
IMAGE_QA_MODEL_SOURCE=environment
IMAGE_QA_MODEL=your-vision-model
IMAGE_QA_BASE_URL=https://your-provider.example/v1
IMAGE_QA_API_KEY=your-private-key
```

A database selection remains the default. The matching feature uses the effective Image Q&A assignment and does not select a different provider automatically. The assignment must accept images and OpenAI-compatible Chat Completions requests with JSON object responses (`response_format: json_object`). Configuring the optional image-answering feature alone does not enable product matching.

## Enable category verification

Set these backend runtime values in `.env`:

```dotenv
MULTIMODAL_IMAGE_RERANK_ENABLED=true
MULTIMODAL_IMAGE_RERANK_CANDIDATES=20
MULTIMODAL_IMAGE_RERANK_CANDIDATE_MIN_SCORE=0.2
MULTIMODAL_IMAGE_RERANK_MIN_CONFIDENCE=0.8
MULTIMODAL_IMAGE_RERANK_TIMEOUT_SECONDS=25
```

Run `./services.sh restart backend` in Docker after changing configuration. Rebuild the backend first when deploying the Python code. For a native host deployment, relaunch the backend with the updated environment.

Candidate similarity is a recall filter, not proof of product relevance. The vision decision identifies a specific functional type for the query and each candidate. Code requires those types to match and meet the configured confidence threshold before a candidate can appear; broad labels such as “chair” are rejected. Different color, material, viewpoint and model are allowed. A bookshelf must not return a sofa; a dining chair must not return an office swivel chair or bar stool. The final ranking uses visual similarity among accepted candidates, with embedding similarity as a tie-breaker. No unrelated products are added to fill empty result slots.

An exact original-file hash can return its authorized catalog match without a vision request. Other queries use at most one bounded vision request. An unidentifiable query or no accepted type match returns no match. Missing configuration, timeout or malformed vision output returns unavailable, rather than falling back to unchecked low-score candidates.

The vision timeout covers that provider call. It does not include image embedding, source validation or network transit. Model output is evidence, not a guarantee for all unseen photographs; validate representative product types before deployment.

## Keep the catalog and access checks

No vector reindex or new category table is required. Existing team/tool assignments, source hashes and signed image grants still apply. Model decisions are cached briefly in process memory; query images are not added to the catalog or stored by this feature. Changing a model assignment or candidate source invalidates reuse, and source access is checked again before returning results.

The current implementation inspects at most 20 authorized candidates from the nearest-neighbor pool. That covers a 20-image corpus, but it is not an exhaustive category search over an arbitrarily large catalog. Larger corpora may need a category index or another candidate retrieval stage.

When `MULTIMODAL_IMAGE_RERANK_ENABLED=false`, the previous strict embedding threshold and score-gap policy remain in effect. A false setting favors near-identical photographs and does not promise category matching.

## Verify through the public widget protocol

Use real photos that were never added to the catalog, including alternate models, different backgrounds, and unrelated products. Keep exact/cropped original cases as a separate regression group. Inspect every fixture visually; a filename alone does not establish its contents.

Run the standalone verifier with a local case manifest:

```bash
server/.venv/bin/python scripts/check-product-image-matching.py \
  --base-url http://127.0.0.1:18000 \
  --widget-slug your-widget-slug \
  --origin https://your-public-host.example \
  --cases /absolute/path/to/cases.json \
  --output /absolute/path/to/results.json
```

The manifest is a list of objects containing `name`, `image` and `expected_sources`. Image paths resolve relative to the manifest. List expected catalog source labels in order; use an empty list for no-match cases. The verifier checks WebSocket results and downloads each signed original to verify its asset hash. It does not modify the catalog.
