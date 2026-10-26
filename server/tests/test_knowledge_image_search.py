import base64
import hashlib
import io
from contextlib import contextmanager

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import knowledge_image_search as search, local_image_rag as images, okf_service
from app.orm_models import Base, Agent, AgentTool, OKFBundle, OKFConceptIndex, TeamAgent, TeamAgentMember, TeamToolAssignment, Tool


def image_bytes(color="red", format="PNG"):
    out = io.BytesIO()
    Image.new("RGB", (12, 12), color).save(out, format=format)
    return out.getvalue()


def request(data=None, mime="image/png", request_id="query_1"):
    return search.ImageSearchRequest.model_validate({"type": "knowledge.image.search", "request_id": request_id,
        "image": {"mime": mime, "base64": base64.b64encode(data or image_bytes()).decode()}})


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    @contextmanager
    def get_db():
        with sessions.begin() as db:
            yield db

    monkeypatch.setattr(search, "get_db", get_db)
    monkeypatch.setattr(images, "get_db", get_db)
    monkeypatch.setattr(okf_service, "get_db", get_db)
    monkeypatch.setattr(images, "enabled", lambda: True)
    monkeypatch.setattr(images, "ensure_schema", lambda: None)
    monkeypatch.delenv("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", raising=False)
    monkeypatch.delenv("MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP", raising=False)
    monkeypatch.setenv("MULTIMODAL_IMAGE_QUERY_MAX_RESULTS", "5")
    with get_db() as db:
        db.add_all([TeamAgent(id=1, name="Owner", slug="owner"), TeamAgent(id=2, name="Other", slug="other"),
            Agent(id=7, name="Member", instructions="Search"),
            TeamAgentMember(team_agent_id=1, agent_id=7), TeamAgentMember(team_agent_id=2, agent_id=7),
            OKFBundle(id=1, name="catalog", display_name="Catalog", owner_team_agent_id=1, storage_path=str(tmp_path)),
            Tool(id=1, name="catalog", type="okf_knowledge_graph", config={"okf_bundle_id": 1}, owner_team_agent_id=1),
            AgentTool(agent_id=7, tool_id=1)])
    yield get_db, tmp_path
    engine.dispose()


def add_concept(runtime, name="mug", color="red"):
    get_db, root = runtime
    data = image_bytes(color)
    asset_id = hashlib.sha256(data).hexdigest()
    (root / "assets").mkdir(exist_ok=True)
    (root / "assets" / asset_id).write_bytes(data)
    markdown = f"---\ntype: document\ntitle: {name}\ndocument_type: png\nimage_asset_id: {asset_id}\nimage_asset_path: assets/{asset_id}\n---\n\n{name} source evidence.\n"
    (root / (name + ".md")).write_text(markdown)
    source_hash = hashlib.sha256(markdown.encode()).hexdigest()
    with get_db() as db:
        db.add(OKFConceptIndex(bundle_id=1, concept_id=name, type="document", search_text=name, title=name, description="Verified description", resource="source.png", file_path=name + ".md", content_hash=source_hash))
    return {"bundle_id": 1, "concept_id": name, "asset_id": asset_id, "source_hash": source_hash,
        "title": name, "description": "Verified description", "resource": "source.png", "score": 0.9}


def test_rejects_bad_encoding_mime_and_real_image_bounds(monkeypatch):
    assert request().image_bytes().startswith(b"\x89PNG")
    assert request(image_bytes(format="JPEG"), "image/jpeg").image_bytes().startswith(b"\xff\xd8")
    with pytest.raises(search.InvalidSearchImage, match="type"):
        request(mime="image/jpeg").image_bytes()
    for value in ["@@@@", "YQ==\n", "abcd===", "data:image/png;base64,abc"]:
        with pytest.raises(search.InvalidSearchImage):
            search.ImageSearchRequest(type="knowledge.image.search", request_id="x", image={"mime": "image/png", "base64": value}).image_bytes()
    with pytest.raises(search.InvalidSearchImage):
        request(b"not an image").image_bytes()
    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    with pytest.raises(search.InvalidSearchImage):
        request().image_bytes()
    with pytest.raises(ValidationError):
        search.ImageSearchRequest(type="knowledge.image.search", request_id="x", image={"mime": "image/png", "base64": "A" * (4 * ((10 * 1024 * 1024 + 2) // 3) + 4)})
    with pytest.raises(ValidationError):
        search.ImageSearchRequest(type="knowledge.image.search", request_id="x", image={"mime": "image/png", "base64": "AAAA"}, filename="../../x")


def test_current_member_assignment_is_required_even_for_global_bundles(runtime):
    get_db, _ = runtime
    assert search.assigned_bundles(1) == {1}
    assert search.assigned_bundles(2) == set()
    with get_db() as db:
        db.get(OKFBundle, 1).visibility = "global"
    assert search.assigned_bundles(2) == set()
    with get_db() as db:
        db.get(Tool, 1).visibility = "global"
    assert search.assigned_bundles(2) == {1}
    with get_db() as db:
        db.query(AgentTool).delete()
    assert search.assigned_bundles(1) == search.assigned_bundles(2) == set()


def test_explicit_share_and_revocation(runtime):
    get_db, _ = runtime
    with get_db() as db:
        db.add(TeamToolAssignment(tool_id=1, team_agent_id=2, relationship="shared_in"))
    assert search.assigned_bundles(2) == {1}
    with get_db() as db:
        db.query(TeamToolAssignment).delete()
    assert search.assigned_bundles(2) == set()
    with get_db() as db:
        db.get(TeamAgent, 1).status = "archived"
    assert search.assigned_bundles(1) == set()


def test_embeds_once_across_bundles_and_rechecks_assignment(runtime, monkeypatch):
    get_db, root = runtime
    row = add_concept(runtime)
    with get_db() as db:
        db.add_all([OKFBundle(id=2, name="second", display_name="Second", owner_team_agent_id=1, storage_path=str(root)),
            Tool(id=2, name="second", type="okf_knowledge_graph", config={"okf_bundle_id": 2}, owner_team_agent_id=1),
            AgentTool(agent_id=7, tool_id=2)])
    calls = []

    class Client:
        space = "test"
        def image(self, data):
            calls.append(data)
            return [1.0] * 768

    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    seen = []
    monkeypatch.setattr(search, "_nearest", lambda bundles, space, vector: seen.append(bundles) or [row])
    result = search.search_image(1, request())
    assert result.status == "matched"
    assert len(calls) == 1
    assert seen == [{1, 2}]

    class RevokingClient(Client):
        def image(self, data):
            with get_db() as db:
                db.query(AgentTool).delete()
            return super().image(data)

    monkeypatch.setattr(images, "LocalImageEmbeddingClient", RevokingClient)
    seen.clear()
    assert search.search_image(1, request()).status == "unavailable"
    assert seen == []


def test_qualifying_unique_results_are_capped_never_padded_and_source_checked(runtime, monkeypatch):
    rows = [add_concept(runtime, f"item-{i}", color) for i, color in enumerate(["red", "green", "blue", "yellow", "pink", "white", "black"])]
    class Client:
        space = "test"
        def image(self, _): return [1.0] * 768
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    monkeypatch.setattr(search, "_nearest", lambda *_: [rows[0], rows[0], *rows[1:]])
    assert len(search.search_image(1, request()).matches) == 5
    monkeypatch.setattr(search, "_nearest", lambda *_: [rows[0], {**rows[1], "score": 0.1}])
    assert len(search.search_image(1, request()).matches) == 1
    (runtime[1] / "item-0.md").write_text("changed")
    assert search.search_image(1, request()).status == "no_match"


@pytest.fixture
def nearest_rows(runtime, monkeypatch):
    class Client:
        space = "test"
        def image(self, _): return [1.0] * 768
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    rows = []
    monkeypatch.setattr(search, "_nearest", lambda *_: rows)
    return rows


def test_bookshelf_search_excludes_unrelated_chair(runtime, nearest_rows):
    nearest_rows.extend([
        {**add_concept(runtime, "bookshelf", "red"), "score": .99},
        {**add_concept(runtime, "chair", "green"), "score": .764},
    ])
    assert [match.title for match in search.search_image(1, request()).matches] == ["bookshelf"]


def test_search_keeps_close_matches_without_filling_result_limit(runtime, nearest_rows):
    nearest_rows.extend([
        {**add_concept(runtime, "bookshelf", "red"), "score": .90},
        {**add_concept(runtime, "similar-shelf", "green"), "score": .87},
        {**add_concept(runtime, "distant", "blue"), "score": .83},
    ])
    assert [match.title for match in search.search_image(1, request()).matches] == ["bookshelf", "similar-shelf"]


def test_similarity_gap_and_result_limit_are_configurable(runtime, nearest_rows, monkeypatch):
    nearest_rows.extend([
        {**add_concept(runtime, "bookshelf", "red"), "score": .90},
        {**add_concept(runtime, "similar-shelf", "green"), "score": .87},
        {**add_concept(runtime, "distant", "blue"), "score": .83},
    ])
    monkeypatch.setenv("MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP", "0.08")
    assert len(search.search_image(1, request()).matches) == 3
    monkeypatch.setenv("MULTIMODAL_IMAGE_QUERY_MAX_RESULTS", "2")
    assert [match.title for match in search.search_image(1, request()).matches] == ["bookshelf", "similar-shelf"]


def test_low_similarity_returns_no_match(runtime, nearest_rows):
    nearest_rows.append({**add_concept(runtime), "score": .79})
    result = search.search_image(1, request())
    assert result.status == "no_match" and result.matches == ()


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf"), 1.1, -1.1])
def test_invalid_candidate_score_cannot_anchor_results(runtime, nearest_rows, score):
    nearest_rows.extend([
        {**add_concept(runtime, "invalid", "red"), "score": score},
        {**add_concept(runtime, "valid", "green"), "score": .90},
    ])
    assert [match.title for match in search.search_image(1, request()).matches] == ["valid"]


def test_stale_high_score_does_not_hide_valid_matches(runtime, nearest_rows):
    stale = {**add_concept(runtime, "stale", "red"), "score": .99}
    (runtime[1] / "stale.md").write_text("changed")
    nearest_rows.extend([stale, {**add_concept(runtime, "valid", "green"), "score": .87}])
    assert [match.title for match in search.search_image(1, request()).matches] == ["valid"]


def test_inaccessible_high_score_does_not_hide_valid_matches(runtime, nearest_rows):
    nearest_rows.extend([
        {**add_concept(runtime, "other", "red"), "bundle_id": 2, "score": .99},
        {**add_concept(runtime, "valid", "green"), "score": .87},
    ])
    assert [match.title for match in search.search_image(1, request()).matches] == ["valid"]


@pytest.mark.parametrize("setting,value", [
    ("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", "nan"),
    ("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", "1.1"),
    ("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", "invalid"),
    ("MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP", "nan"),
    ("MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP", "-0.1"),
    ("MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP", "2.1"),
    ("MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP", "invalid"),
])
def test_invalid_similarity_settings_fail_explicitly(runtime, nearest_rows, monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    nearest_rows.append(add_concept(runtime))
    with pytest.raises(ValueError):
        search.search_image(1, request())


def test_refs_are_session_owned_expire_reset_and_lookup_current_source(runtime, monkeypatch):
    row = add_concept(runtime)
    ref = search.KnowledgeCardRef(1, row["concept_id"], row["source_hash"], row["asset_id"])
    result = search.SearchResult("matched", (search.SearchMatch(ref, "Mug", "source.png", "Description", .9),))
    monkeypatch.setattr(images, "_grant", lambda *_: "signed.token")
    session = search.ImageSearchSession()
    message_id, carousel = session.presentation(result, 1)
    inquiry = search.KnowledgeInquiryRequest(type="knowledge.product.inquire", message_id=message_id, card_id=carousel.products[0].id)
    assert session.reference(inquiry) == ref
    text, source = search.resolve_inquiry(1, ref)
    assert "mug" in text and "mug source evidence" in source
    with pytest.raises(ValueError): search.ImageSearchSession().reference(inquiry)
    with pytest.raises(ValueError): session.reference(inquiry.model_copy(update={"card_id": "0" * 32}))
    now = search.time.monotonic()
    monkeypatch.setattr(search.time, "monotonic", lambda: now + 901)
    with pytest.raises(ValueError): session.reference(inquiry)
    session.reset()
    with pytest.raises(ValueError): session.reference(inquiry)
    with runtime[0]() as db: db.query(AgentTool).delete()
    with pytest.raises(ValueError): search.resolve_inquiry(1, ref)


def test_request_and_ref_caches_are_bounded(runtime, monkeypatch):
    session = search.ImageSearchSession()
    assert session.begin("first") == 0
    with pytest.raises(ValueError): session.begin("first")
    for i in range(110): session.begin(str(i))
    assert len(session.requests) == 100
    row = add_concept(runtime)
    ref = search.KnowledgeCardRef(1, row["concept_id"], row["source_hash"], row["asset_id"])
    result = search.SearchResult("matched", (search.SearchMatch(ref, "Mug", "source", "Description", .9),))
    monkeypatch.setattr(images, "_grant", lambda *_: "signed")
    for _ in range(25): session.presentation(result, 1)
    assert len(session.refs) == 20
    session.reset()
    assert session.generation == 1 and not session.refs and not session.requests


@pytest.fixture
def socket_runtime(monkeypatch):
    import ast
    import asyncio
    import json
    from contextlib import nullcontext
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from agents import Agent as RuntimeAgent
    from fastapi import WebSocketDisconnect
    from app import db_config

    with monkeypatch.context() as imports:
        imports.setattr(db_config, "init_database", lambda: None)
        from app import database, utils, session_manager as sessions

    class Analytics:
        start_conversation = lambda *args, **kwargs: "test"
        end_conversation = AsyncMock()
        track_message = lambda *args, **kwargs: None

    monkeypatch.setattr(utils, "AnalyticsService", Analytics)
    monkeypatch.setattr(database, "validate_api_key", lambda *args, **kwargs: {"team_agent_id": 1})
    monkeypatch.setattr(database, "increment_api_key_usage", lambda *_: None)
    monkeypatch.setattr(database, "get_team_agent_by_id", lambda *_: {"name": "Test"})
    monkeypatch.setattr(search, "assigned_bundles", lambda _: {1})
    workflows = []
    connections = []
    manager = SimpleNamespace(connect=AsyncMock(), register_helper=lambda _, helper: connections.append(helper),
        disconnect=lambda *_: None, sessions={}, update_session=AsyncMock())
    monkeypatch.setattr(sessions, "session_manager", manager)

    class Workflow:
        def __init__(self, *_): pass
        async def run(self, text, **kwargs):
            workflows.append(text)
            if False:
                yield ""

    class Socket:
        headers = {}
        def __init__(self, messages):
            self.sent = []
            self.messages = iter(messages)
        async def receive_json(self):
            await asyncio.sleep(0)
            try:
                message = next(self.messages)
            except StopIteration:
                raise WebSocketDisconnect()
            return await message(self) if callable(message) else message
        async def send_json(self, value):
            self.sent.append(json.loads(json.dumps(value)))
        async def send_text(self, value): self.sent.append(json.loads(value))

    source = Path(__file__).parents[1] / "server.py"
    node = next(item for item in ast.parse(source.read_text()).body if isinstance(item, ast.AsyncFunctionDef) and item.name == "websocket_endpoint")
    node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node], type_ignores=[])
    globals_ = {"Query": lambda *_: None, "asyncio": asyncio, "session_manager": manager, "uuid": __import__('uuid'),
        "trace": lambda *_: nullcontext(), "get_runtime_starting_agent": lambda *_: RuntimeAgent(name="Test"),
        "WebsocketHelper": utils.WebsocketHelper, "Workflow": Workflow, "WebSocketDisconnect": WebSocketDisconnect,
        "is_sync_message": utils.is_sync_message, "is_new_text_message": utils.is_new_text_message,
        "process_inputs": utils.process_inputs}
    exec(compile(ast.fix_missing_locations(module), str(source), "exec"), globals_)
    return SimpleNamespace(endpoint=globals_["websocket_endpoint"], Socket=Socket, manager=manager,
        connections=connections, workflows=workflows, utils=utils)


async def wait_for(predicate):
    import asyncio
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.001)


def test_socket_rejects_concurrent_text_and_drops_result_after_reset(socket_runtime, monkeypatch):
    import asyncio
    import threading
    rt = socket_runtime
    release = threading.Event()
    started = threading.Event()

    def slow_search(*_):
        started.set()
        assert release.wait(3)
        return search.SearchResult("no_match")

    monkeypatch.setattr(rt.utils, "search_image", slow_search)

    async def concurrent_text(_):
        await wait_for(started.is_set)
        return {"type": "history.update", "inputs": [{"role": "user", "content": "concurrent text"}]}

    async def disconnect(_):
        release.set()
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect()

    socket = rt.Socket([request().model_dump(), concurrent_text,
        {"type": "knowledge.product.inquire", "message_id": "msg_" + "a" * 32, "card_id": "b" * 32},
        {"type": "input_audio_buffer.commit"}, {"type": "history.update", "inputs": [], "reset_agent": True}, disconnect])
    try:
        asyncio.run(rt.endpoint(socket, api_key="test"))
    finally:
        release.set()
    assert rt.workflows == []
    assert sum(item["type"] == "product.action.error" for item in socket.sent) == 3
    assert not any(item["type"] in {"knowledge.image.result", "history.updated"} for item in socket.sent)


def test_reset_accepts_fresh_text_and_image_while_retired_native_search_runs(socket_runtime, monkeypatch):
    import asyncio
    import threading
    rt = socket_runtime
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_first(_, image_request):
        calls.append(image_request.request_id)
        if image_request.request_id == "old":
            started.set()
            assert release.wait(3)
        return search.SearchResult("no_match")

    monkeypatch.setattr(rt.utils, "search_image", slow_first)

    async def reset(_):
        await wait_for(started.is_set)
        return {"type": "history.update", "inputs": [], "reset_agent": True}

    async def finish(socket):
        assert rt.workflows == ["fresh text"]
        assert not any(item.get("code") == "busy" for item in socket.sent)
        await wait_for(lambda: any(item["type"] == "knowledge.image.result" for item in socket.sent))
        assert not release.is_set()
        release.set()
        await wait_for(lambda: rt.utils._IMAGE_SEARCH_WORKERS._value == 2)
        return {"type": "history.update", "inputs": []}

    socket = rt.Socket([request(request_id="old").model_dump(), reset,
        {"type": "history.update", "inputs": [{"role": "user", "content": "fresh text"}]},
        request(request_id="new").model_dump(), finish])
    try:
        asyncio.run(rt.endpoint(socket, api_key="test"))
    finally:
        release.set()
    assert calls == ["old", "new"]
    assert [item["request_id"] for item in socket.sent if item["type"] == "knowledge.image.result"] == ["new"]
    assert not any(item["type"] in {"product.action.error", "knowledge.image.error"} for item in socket.sent)
    histories = [item for item in socket.sent if item["type"] == "history.updated"]
    assert len(histories) == 1
    assert len(histories[0]["inputs"]) == 2


@pytest.mark.parametrize("status", ["matched", "no_match", "unavailable"])
def test_search_history_converts_through_installed_chat_completions_sdk(socket_runtime, monkeypatch, status):
    import asyncio
    from agents.models.openai_chatcompletions import _Converter
    from unittest.mock import Mock
    rt = socket_runtime
    tracked = Mock()
    monkeypatch.setattr(rt.utils.AnalyticsService, "track_message", tracked)
    ref = search.KnowledgeCardRef(1, "mug", "hash", "asset")
    result = search.SearchResult(status, (search.SearchMatch(ref, "Mug", "source", "Description", .9),) if status == "matched" else ())
    monkeypatch.setattr(rt.utils, "search_image", lambda *_: result)
    monkeypatch.setattr(images, "_grant", lambda *_: "signed")

    async def check(socket):
        await wait_for(lambda: any(item["type"] == "knowledge.image.result" for item in socket.sent))
        helper = rt.connections[0]
        converted = _Converter.items_to_messages(helper.history)
        assert converted[-1]["role"] == "assistant"
        assert converted[-1]["content"] == helper.history[-1]["content"][0]["text"]
        assert [call.kwargs["role"] for call in tracked.call_args_list] == ["user", "assistant"]
        assert rt.manager.update_session.await_count == 2
        assert [call.kwargs["is_user"] for call in rt.manager.update_session.await_args_list] == [True, False]
        assert all("base64" not in str(call) for call in tracked.call_args_list)
        if status == "matched":
            assert helper.history[-1]["id"] in helper.presentations
        return {"type": "history.update", "inputs": []}

    asyncio.run(rt.endpoint(rt.Socket([request().model_dump(), check]), api_key="test"))


@pytest.mark.parametrize("inflight", [False, True])
@pytest.mark.parametrize("caption", ["", "blue shelves"])
def test_manual_mode_records_input_without_automated_cards(socket_runtime, monkeypatch, inflight, caption):
    import asyncio
    import threading
    from types import SimpleNamespace
    rt = socket_runtime
    started = threading.Event()
    release = threading.Event()
    calls = []
    ref = search.KnowledgeCardRef(1, "mug", "hash", "asset")

    def slow_search(*_):
        calls.append(True)
        started.set()
        assert release.wait(3)
        return search.SearchResult("matched", (search.SearchMatch(ref, "Mug", "source", "Description", .9),))

    monkeypatch.setattr(rt.utils, "search_image", slow_search)

    async def set_manual(_):
        rt.manager.sessions[rt.connections[0].session_id] = SimpleNamespace(mode="AI" if inflight else "MANUAL")
        return caption_request(caption).model_dump()

    async def finish(socket):
        if inflight:
            await wait_for(started.is_set)
            rt.manager.sessions[rt.connections[0].session_id].mode = "MANUAL"
        release.set()
        await wait_for(lambda: any(item["type"] in {"knowledge.image.result", "knowledge.image.error"} for item in socket.sent))
        terminal = next(item for item in socket.sent if item["type"] in {"knowledge.image.result", "knowledge.image.error"})
        assert terminal.get("code") == "manual_mode"
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect()

    socket = rt.Socket([set_manual, finish])
    try:
        asyncio.run(rt.endpoint(socket, api_key="test"))
    finally:
        release.set()
    assert len(calls) == int(inflight)
    assert rt.manager.update_session.await_args.kwargs == {"is_user": True}
    assert [item["role"] for item in rt.connections[0].history] == ["user"]
    user_content = rt.connections[0].history[0]["content"]
    assert user_content == "ค้นหาสินค้าจากรูปภาพ" + (f"\n{caption}" if caption else "")
    assert rt.manager.update_session.await_args.args[1]["content"] == user_content
    assert rt.connections[0].presentations == {}
    assert not any(item["type"] == "knowledge.image.result" for item in socket.sent)
    error = next(item for item in socket.sent if item.get("code") == "manual_mode")
    assert error["request_id"] == "query_1"


def test_native_search_capacity_is_bounded_and_released_after_cancellation(socket_runtime, monkeypatch):
    import asyncio
    import threading
    from agents import Agent as RuntimeAgent
    rt = socket_runtime
    started = []
    release = threading.Event()

    def slow_search(_, image_request):
        started.append(image_request.request_id)
        assert release.wait(3)
        return search.SearchResult("no_match")

    monkeypatch.setattr(rt.utils, "search_image", slow_search)

    async def run():
        socket = rt.Socket([])
        helper = rt.utils.WebsocketHelper(socket, [], RuntimeAgent(name="Test"), "capacity", team_agent_id=1)
        tasks = [asyncio.create_task(helper.search_knowledge_image(request(request_id=str(i)), 0)) for i in range(2)]
        try:
            await wait_for(lambda: len(started) == 2)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await helper.search_knowledge_image(request(request_id="overflow"), 0)
            assert len(started) == 2
            assert socket.sent[-1]["code"] == "busy"
            assert socket.sent[-1]["retryable"] is True
            assert socket.sent[-1]["request_id"] == "overflow"
        finally:
            release.set()
        await wait_for(lambda: rt.utils._IMAGE_SEARCH_WORKERS._value == 2)
        await helper.search_knowledge_image(request(request_id="after"), 0)
        assert socket.sent[-1]["status"] == "no_match"
        assert socket.sent[-1]["request_id"] == "after"

    asyncio.run(run())


def test_reranking_accepts_new_photo_same_type_and_rejects_higher_scoring_wrong_type(runtime, nearest_rows, monkeypatch):
    nearest_rows.extend([
        {**add_concept(runtime, "sofa", "green"), "score": .91},
        {**add_concept(runtime, "bookshelf", "blue"), "score": .64},
    ])
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "true")
    seen = []
    monkeypatch.setattr(search.reranker, "rerank", lambda query, candidates, settings: seen.append(candidates) or ("c02",))
    result = search.search_image(1, request())
    assert [match.title for match in result.matches] == ["bookshelf"]
    assert len(seen[0]) == 2


def test_reranking_exact_valid_original_bypasses_model(runtime, nearest_rows, monkeypatch):
    nearest_rows.append(add_concept(runtime, "bookshelf", "red"))
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "true")
    monkeypatch.setattr(search.reranker, "rerank", lambda *_: pytest.fail("Exact original needs no model"))
    assert search.search_image(1, request()).status == "matched"
    (runtime[1] / "bookshelf.md").write_text("stale source")
    assert search.search_image(1, request()).status == "no_match"


def test_reranking_rechecks_revocation_and_source_changes_after_inference(runtime, nearest_rows, monkeypatch):
    nearest_rows.append(add_concept(runtime, "bookshelf", "blue"))
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "true")
    def mutate(*_):
        (runtime[1] / "bookshelf.md").write_text("stale source")
        return ("c01",)
    monkeypatch.setattr(search.reranker, "rerank", mutate)
    assert search.search_image(1, request()).status == "no_match"
    nearest_rows.clear()
    nearest_rows.append(add_concept(runtime, "replacement", "green"))
    def revoke(*_):
        with runtime[0]() as db: db.query(AgentTool).delete()
        return ("c01",)
    monkeypatch.setattr(search.reranker, "rerank", revoke)
    assert search.search_image(1, request()).status == "unavailable"


def test_reranking_unavailable_never_falls_back_to_broad_candidates(runtime, nearest_rows, monkeypatch):
    nearest_rows.append(add_concept(runtime, "sofa", "blue"))
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "true")
    def unavailable(*_): raise search.reranker.RerankUnavailable("not configured")
    monkeypatch.setattr(search.reranker, "rerank", unavailable)
    result = search.search_image(1, request())
    assert result.status == "unavailable" and result.matches == ()


def test_reranking_resolves_stale_rows_before_candidate_cap(runtime, nearest_rows, monkeypatch):
    nearest_rows.extend([
        add_concept(runtime, "stale", "green"),
        {**add_concept(runtime, "bookshelf", "blue"), "score": .6},
    ])
    (runtime[1] / "stale.md").write_text("source changed")
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "true")
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_CANDIDATES", "1")
    seen = []
    monkeypatch.setattr(search.reranker, "rerank", lambda query, candidates, settings: seen.append(candidates) or ("c01",))
    assert [match.title for match in search.search_image(1, request()).matches] == ["bookshelf"]
    assert [candidate.title for candidate in seen[0]] == ["bookshelf"]


def caption_request(query):
    return search.ImageSearchRequest.model_validate({**request().model_dump(), "query": query})


def test_image_caption_is_optional_trimmed_bounded_and_strict():
    assert request().query == ""
    assert caption_request("  blue shelves  ").query == "blue shelves"
    assert caption_request(" \n\t ").query == ""
    assert len(caption_request("x" * 2000).query) == 2000
    for invalid in [None, True, 42, "x" * 2001]:
        with pytest.raises(ValidationError):
            caption_request(invalid)


def test_caption_sorts_only_image_eligible_authorized_pool(runtime, monkeypatch):
    rows = [
        {**add_concept(runtime, "inaccessible", "black"), "bundle_id": 2, "score": .99, "text_score": 1.0},
        {**add_concept(runtime, "best-image", "red"), "score": .94, "text_score": .1},
        {**add_concept(runtime, "blue", "blue"), "score": .90, "text_score": .9},
        {**add_concept(runtime, "outside-gap", "green"), "score": .86, "text_score": .99},
        {**add_concept(runtime, "below-threshold", "pink"), "score": .79, "text_score": 1.0},
    ]
    calls = []
    class Client:
        space = "test"
        def image(self, _): return [1.0] * 768
        def query(self, query):
            calls.append(query)
            return [2.0] * 768
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    def nearest(bundles, space, vector, text_vector):
        assert bundles == {1} and space == "test"
        assert vector == [1.0] * 768 and text_vector == [2.0] * 768
        return rows
    monkeypatch.setattr(search, "_nearest", nearest)
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "false")
    result = search.search_image(1, caption_request(" blue "))
    assert calls == ["blue"]
    assert [(match.title, match.score) for match in result.matches] == [("blue", .90), ("best-image", .94)]


def test_caption_embedding_failure_is_not_silently_ignored(runtime, monkeypatch):
    class Client:
        space = "test"
        def image(self, _): return [1.0] * 768
        def query(self, _): raise ValueError("embedding unavailable")
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "false")
    monkeypatch.setattr(search, "_nearest", lambda *_: pytest.fail("Do not search without requested caption"))
    with pytest.raises(ValueError, match="embedding unavailable"):
        search.search_image(1, caption_request("blue"))


def test_caption_embedding_revocation_is_rechecked_before_nearest(runtime, monkeypatch):
    class Client:
        space = "test"
        def image(self, _): return [1.0] * 768
        def query(self, _):
            with runtime[0]() as db: db.query(AgentTool).delete()
            return [2.0] * 768
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "false")
    monkeypatch.setattr(search, "_nearest", lambda *_: pytest.fail("Assignment was revoked"))
    assert search.search_image(1, caption_request("blue")).status == "unavailable"


def test_caption_disables_exact_image_bypass_and_reaches_reranker(runtime, nearest_rows, monkeypatch):
    nearest_rows.append(add_concept(runtime, "bookshelf", "red"))
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "true")
    seen = []
    def rank(data, candidates, settings, query=""):
        seen.append(query)
        return ("c01",)
    monkeypatch.setattr(search.reranker, "rerank", rank)
    assert search.search_image(1, caption_request("blue")).status == "matched"
    assert seen == ["blue"]


@pytest.mark.parametrize("status", ["matched", "no_match", "unavailable"])
def test_caption_is_one_user_turn_in_history_analytics_and_monitoring(socket_runtime, monkeypatch, status):
    import asyncio
    from unittest.mock import Mock
    rt = socket_runtime
    tracked = Mock()
    monkeypatch.setattr(rt.utils.AnalyticsService, "track_message", tracked)
    ref = search.KnowledgeCardRef(1, "mug", "hash", "asset")
    result = search.SearchResult(status, (search.SearchMatch(ref, "Mug", "source", "Description", .9),) if status == "matched" else ())
    received = []
    monkeypatch.setattr(rt.utils, "search_image", lambda _, request: received.append(request.query) or result)
    monkeypatch.setattr(images, "_grant", lambda *_: "signed")
    async def check(socket):
        await wait_for(lambda: any(item["type"] == "knowledge.image.result" for item in socket.sent))
        history = rt.connections[0].history
        users = [item["content"] for item in history if item["role"] == "user"]
        assert len(users) == 1 and "blue shelves" in users[0]
        assert received == ["blue shelves"] and rt.workflows == []
        assert [call.kwargs["content"] for call in tracked.call_args_list if call.kwargs["role"] == "user"] == users
        assert rt.manager.update_session.await_args_list[0].args[1]["content"] == users[0]
        assert rt.manager.update_session.await_count == 2
        return {"type": "history.update", "inputs": []}
    asyncio.run(rt.endpoint(rt.Socket([caption_request(" blue shelves ").model_dump(), check]), api_key="test"))


def test_socket_rejects_overlong_caption_before_search(socket_runtime, monkeypatch):
    import asyncio
    rt = socket_runtime
    monkeypatch.setattr(rt.utils, "search_image", lambda *_: pytest.fail("Invalid caption reached search"))
    payload = {**request().model_dump(), "query": "x" * 2001}
    socket = rt.Socket([payload])
    asyncio.run(rt.endpoint(socket, api_key="test"))
    assert any(item.get("type") == "knowledge.image.error" and item.get("retryable") is False for item in socket.sent)
    assert rt.workflows == []


def test_whitespace_caption_uses_unchanged_image_only_call(runtime, monkeypatch):
    row = add_concept(runtime)
    class Client:
        space = "test"
        def image(self, _): return [1.0] * 768
        def query(self, _): pytest.fail("Whitespace caption is image-only")
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "false")
    monkeypatch.setattr(search, "_nearest", lambda bundles, space, vector: [row])
    assert search.search_image(1, caption_request(" \t\n")).status == "matched"


def test_caption_ranks_before_result_cap_and_breaks_text_ties_by_image_score(runtime, monkeypatch):
    colors = ["red", "green", "blue", "yellow", "pink", "white", "black"]
    rows = [{**add_concept(runtime, f"item-{i}", color), "score": .95 - i * .005,
             "text_score": .1 if i < 5 else .9} for i, color in enumerate(colors)]
    class Client:
        space = "test"
        def image(self, _): return [1.0] * 768
        def query(self, _): return [2.0] * 768
    monkeypatch.setattr(images, "LocalImageEmbeddingClient", Client)
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", "false")
    monkeypatch.setattr(search, "_nearest", lambda *_: rows)
    assert [match.title for match in search.search_image(1, caption_request("blue")).matches] == [
        "item-5", "item-6", "item-0", "item-1", "item-2"]


@pytest.mark.parametrize("caption", ["", "blue shelves"])
def test_nearest_caption_score_keeps_image_candidate_selection(monkeypatch, caption):
    from types import SimpleNamespace
    calls = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))
            return self
        def mappings(self): return self
        def all(self): return []
    monkeypatch.setattr(images, "engine", SimpleNamespace(connect=Connection))
    text_vector = [0.0] * 768 if caption else None
    search._nearest({2, 1}, "test", [1.0] * 768, text_vector)
    sql, parameters = calls[0]
    assert "ORDER BY v.embedding <=> CAST(:vector AS vector),v.bundle_id,v.concept_id LIMIT 100" in sql
    assert "WHERE v.bundle_id IN" in sql and "v.space=:space" in sql
    assert parameters["bundles"] == [1, 2]
    assert ("AS text_score" in sql) == bool(caption)
    assert ("text_vector" in parameters) == bool(caption)
    if caption:
        assert "1-(v.embedding <=> CAST(:text_vector AS vector)) AS text_score" in sql


def test_caption_embedding_error_uses_existing_socket_unavailable_flow(socket_runtime, monkeypatch):
    import asyncio
    rt = socket_runtime
    def unavailable(*_): raise ValueError("text embedding unavailable")
    monkeypatch.setattr(rt.utils, "search_image", unavailable)
    async def check(socket):
        await wait_for(lambda: any(item["type"] == "knowledge.image.error" for item in socket.sent))
        error = next(item for item in socket.sent if item["type"] == "knowledge.image.error")
        assert error["code"] == "unavailable" and error["retryable"] is True
        assert rt.connections[0].history == []
        return {"type": "history.update", "inputs": []}
    asyncio.run(rt.endpoint(rt.Socket([caption_request("blue").model_dump(), check]), api_key="test"))


def assign_second_bundle(runtime, source_row):
    get_db, root = runtime
    with get_db() as db:
        db.add_all([OKFBundle(id=2, name="second", display_name="Second", owner_team_agent_id=1, storage_path=str(root)),
            Tool(id=2, name="second", type="okf_knowledge_graph", config={"okf_bundle_id": 2}, owner_team_agent_id=1),
            AgentTool(agent_id=7, tool_id=2),
            OKFConceptIndex(bundle_id=2, concept_id=source_row["concept_id"], type="document", search_text="product",
                title=source_row["title"], description=source_row["description"], resource=source_row["resource"],
                file_path=source_row["concept_id"] + ".md", content_hash=source_row["source_hash"])])
    return {**source_row, "bundle_id": 2}


@pytest.mark.parametrize("rerank", [False, True])
def test_threshold_is_per_bundle_in_both_search_modes(runtime, nearest_rows, monkeypatch, rerank):
    from app import knowledge_image_policy as policy
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", str(rerank).lower())
    first = {**add_concept(runtime, "strict", "green"), "score": .65}
    second = assign_second_bundle(runtime, {**add_concept(runtime, "relaxed", "blue"), "score": .64})
    mode = "rerank" if rerank else "similarity"
    with runtime[0]() as db:
        policy.set_override(db, 1, mode, .7)
        policy.set_override(db, 2, mode, .6)
    candidates = []
    def reranker(_, supplied, settings):
        candidates.extend(supplied)
        assert settings.min_confidence == .8
        return tuple(item.id for item in supplied)
    monkeypatch.setattr(search.reranker, "rerank", reranker)
    nearest_rows.extend([first, second])
    result = search.search_image(1, request())
    assert [match.reference.bundle for match in result.matches] == [2]
    if rerank: assert [item.asset_hash for item in candidates] == [second["asset_id"]]
    with runtime[0]() as db:
        policy.set_override(db, 2, mode, .8)
    assert search.search_image(1, request()).status == "no_match"


@pytest.mark.parametrize("rerank", [False, True])
def test_rejected_duplicate_does_not_hide_qualifying_bundle(runtime, nearest_rows, monkeypatch, rerank):
    from app import knowledge_image_policy as policy
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_ENABLED", str(rerank).lower())
    first = {**add_concept(runtime, "shared-asset", "blue"), "score": .65}
    second = assign_second_bundle(runtime, first)
    mode = "rerank" if rerank else "similarity"
    with runtime[0]() as db:
        policy.set_override(db, 1, mode, .7)
        policy.set_override(db, 2, mode, .6)
    monkeypatch.setattr(search.reranker, "rerank", lambda _, supplied, settings: tuple(item.id for item in supplied))
    nearest_rows.extend([first, second])
    assert [match.reference.bundle for match in search.search_image(1, request()).matches] == [2]
