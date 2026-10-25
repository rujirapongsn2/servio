import asyncio
import importlib
import itertools
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


GROUPS = [
    ("Critical / Human Required", "คืนเงิน", "#8E0E00"),
    ("Frustrated / Escalating", "หงุดหงิด", "#E74C3C"),
    ("Repetitive / Looping", "อีกครั้ง", "#F39C12"),
    ("Confused / Unclear Intent", "สับสน", "#F1C40F"),
    ("Smooth Resolution", "ขอบคุณ", "#2ECC71"),
]


@pytest.fixture
def intent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-no-network")
    module = importlib.import_module("app.intent_service")
    import app
    from app.session_manager import SessionInfo, SessionManager

    rules = [dict(group=group, keywords=[keyword], color=color)
             for group, keyword, color in GROUPS]
    monkeypatch.setattr(app, "database", SimpleNamespace(
        get_all_intent_rules=lambda: rules,
    ), raising=False)
    manager = SessionManager()
    manager.sessions["test"] = SessionInfo(
        session_id="test", start_time=0, last_message_time=0, team_agent_id=22,
    )
    manager.broadcast_sessions_list = AsyncMock()
    manager.set_mode = AsyncMock()
    monkeypatch.setattr(module, "session_manager", manager)
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps({
            "group": "Smooth Resolution", "color": "#2ECC71",
        })),
    )]))
    monkeypatch.setattr(module, "AsyncOpenAI", lambda **_: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    return module.IntentService(), rules, manager, create


def analyze(intent, text, history=None):
    service, _, manager, _ = intent
    asyncio.run(service.analyze_and_update(
        "test", (history or []) + [{"role": "user", "content": text}],
    ))
    return manager.sessions["test"]


def test_thai_is_sent_as_readable_json_with_recent_context(intent):
    history = [{"role": "user", "content": f"ข้อความก่อนหน้า {i}"} for i in range(8)]
    text = 'ทำตามขั้นตอนแล้วใช้งานได้ตามปกติครับ "สินค้า"\nทดสอบ'
    analyze(intent, text, history)
    create = intent[3]
    sent = create.call_args.kwargs["messages"][1]["content"]
    assert "ใช้งานได้ตามปกติครับ" in sent
    assert json.loads(sent) == (history + [{"role": "user", "content": text}])[-6:]


@pytest.mark.parametrize("higher,lower", list(itertools.combinations(GROUPS, 2)))
@pytest.mark.parametrize("reverse", [False, True])
def test_keyword_priority_does_not_depend_on_database_order(intent, higher, lower, reverse):
    _, rules, manager, create = intent
    rules.sort(key=lambda rule: rule["group"], reverse=reverse)
    session = analyze(intent, f"{lower[1]}ครับ แต่{higher[1]}")
    assert session.intent_group == higher[0]
    assert session.intent_color == higher[2]
    create.assert_not_awaited()
    assert session.mode == "AI"
    assert session.team_agent_id == 22
    manager.set_mode.assert_not_awaited()


@pytest.mark.parametrize("text", [
    "ไม่ต้องการคืนเงินครับ ปัญหาหายแล้ว ขอบคุณครับ",
    "ไม่ได้โกรธหรือหงุดหงิดครับ แค่ยังสับสนว่าต้องกรอกอะไร",
    "เข้าใจแล้วครับ ไม่ต้องคุยกับคนแล้ว",
    "Thank you, I do not want a refund.",
])
def test_negated_keyword_messages_use_contextual_analysis(intent, text):
    session = analyze(intent, text)
    intent[3].assert_awaited_once()
    assert session.intent_group == "Smooth Resolution"
    assert session.mode == "AI"
    intent[2].set_mode.assert_not_awaited()


def test_blank_keywords_cannot_match_every_message(intent):
    intent[1][0]["keywords"] = ["", "   "]
    analyze(intent, "ต้องการทราบข้อมูลสินค้า")
    intent[3].assert_awaited_once()


def test_empty_history_does_not_update_or_call_model(intent):
    asyncio.run(intent[0].analyze_and_update("test", []))
    assert intent[2].sessions["test"].intent_group is None
    intent[2].broadcast_sessions_list.assert_not_awaited()
    intent[3].assert_not_awaited()
