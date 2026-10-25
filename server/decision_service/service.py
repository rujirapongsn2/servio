from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import threading

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from app.intent_contract import (
    DECISION_CRITERIA, DECISION_INSTRUCTIONS, DECISION_MAX_CONTEXT_BYTES,
    DECISION_MODEL_SHA256, DECISION_PROFILE, valid_decision_result,
)

class IntentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: StrictInt = Field(ge=1, le=1)
    context: StrictStr = Field(min_length=1, max_length=DECISION_MAX_CONTEXT_BYTES)


class MetalEngine:
    def __init__(self):
        if platform.system() != 'Darwin' or platform.machine() != 'arm64':
            raise RuntimeError('Intent Decision service requires native Apple Silicon Metal')
        model = Path(os.getenv('INTENT_DECISION_MODEL_PATH', '').strip() or str(
            Path(__file__).parent / 'models/embeddinggemma-2-text-270m.litertlm',
        ))
        with model.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != DECISION_MODEL_SHA256:
            raise RuntimeError('Intent Decision model checksum does not match the tested profile')
        from mediapipe.tasks.python import decision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        options = decision.DecisionMakerOptions(base_options=BaseOptions(
            model_asset_path=str(model), delegate=BaseOptions.Delegate.GPU,
        ), max_num_tokens=4096)
        self.maker = decision.DecisionMaker.create_from_options(options)
        try:
            self.question = decision.ChoiceQuestion(
                criteria=DECISION_CRITERIA, instructions=DECISION_INSTRUCTIONS,
                normalize_prior=True,
            )
            self.maker.prewarm_choice(self.question)
            self.evaluate('user: ทดสอบการจำแนกสถานะบทสนทนา')
        except BaseException:
            self.maker.close()
            raise

    def evaluate(self, context):
        result = self.maker.evaluate_choice(context, self.question)
        payload = {
            'schema_version': 1, 'profile': DECISION_PROFILE,
            'selected_key': result.selected_key, 'confidence': result.confidence,
            'probabilities': dict(result.probabilities),
        }
        if not valid_decision_result(payload):
            raise RuntimeError('Decision model produced invalid scores')
        return payload

    def close(self):
        self.maker.close()


def create_app(engine=None, *, api_key=None):
    key = api_key if api_key is not None else os.getenv('INTENT_DECISION_API_KEY', '').strip()
    lane = threading.BoundedSemaphore(1)

    @asynccontextmanager
    async def lifespan(application):
        if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise RuntimeError('INTENT_DECISION_API_KEY is required')
        application.state.engine = engine if engine is not None else MetalEngine()
        application.state.ready = True
        application.state.inflight = None
        try:
            yield
        finally:
            application.state.ready = False
            future = application.state.inflight
            try:
                if future is not None and not future.done():
                    await asyncio.shield(future)
            finally:
                application.state.engine.close()

    application = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def authorize(request):
        supplied = request.headers.get('authorization', '')
        if not key or not secrets.compare_digest(supplied.encode(), ('Bearer ' + key).encode()):
            raise HTTPException(401, 'Unauthorized')

    @application.get('/health')
    async def health(request: Request):
        authorize(request)
        ready = bool(getattr(application.state, 'ready', False))
        future = getattr(application.state, 'inflight', None)
        return JSONResponse({
            'ready': ready, 'profile': DECISION_PROFILE,
            'model_sha256': DECISION_MODEL_SHA256, 'delegate_requested': 'GPU',
            'busy': future is not None and not future.done(),
            'max_context_bytes': DECISION_MAX_CONTEXT_BYTES,
        }, status_code=200 if ready else 503)

    @application.post('/v1/intent')
    async def classify(request: Request):
        authorize(request)
        if not getattr(application.state, 'ready', False):
            raise HTTPException(503, 'Decision service unavailable')
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            raise HTTPException(400, 'Use application/json')
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                raise HTTPException(413, 'Intent request too large')
            body.extend(chunk)
        try:
            payload = IntentRequest.model_validate_json(body)
        except ValidationError:
            raise HTTPException(400, 'Invalid intent request') from None
        if not payload.context.strip() or len(payload.context.encode('utf-8')) > DECISION_MAX_CONTEXT_BYTES:
            raise HTTPException(413, 'Intent context empty or too large')
        if not lane.acquire(blocking=False):
            raise HTTPException(503, 'Decision service busy')

        def infer():
            try:
                result = application.state.engine.evaluate(payload.context)
                return JSONResponse(result)
            except Exception:
                application.state.ready = False
                raise
            finally:
                lane.release()

        try:
            future = asyncio.get_running_loop().run_in_executor(None, infer)
        except BaseException:
            lane.release()
            raise
        application.state.inflight = future
        future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.shield(future)
        except Exception:
            raise HTTPException(503, 'Decision inference failed') from None

    return application


if __name__ == '__main__':
    import uvicorn
    for name, value in dotenv_values(Path(__file__).resolve().parents[2] / '.env').items():
        if value is not None and name.startswith('INTENT_DECISION_'):
            os.environ.setdefault(name, value)
    uvicorn.run(create_app(), host=os.getenv('INTENT_DECISION_BIND', '127.0.0.1'),
                port=int(os.getenv('INTENT_DECISION_PORT', '8095')), workers=1,
                limit_concurrency=8, timeout_keep_alive=5, access_log=False)
