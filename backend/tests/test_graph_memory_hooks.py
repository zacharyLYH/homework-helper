from langchain_core.messages import AIMessage, HumanMessage

from app.graph import memory_loader, memory_updater, route_after_agent


def test_memory_loader_skips_when_disabled(monkeypatch):
    called = {"count": 0}

    def _fake_loader(*, user_id: int, subject_id: int) -> str:
        called["count"] += 1
        return "memory summary"

    monkeypatch.setattr("app.graph.load_memory_context", _fake_loader)

    out = memory_loader(
        {
            "messages": [],
            "model": "unknown",
            "pending_tool_calls": 0,
            "pending_tool_calls_data": [],
            "called_tools": [],
            "user_id": 1,
            "subject_id": 1,
            "memory_context": "",
            "memory_loaded": False,
            "memory_enabled": False,
        }
    )

    assert out == {"memory_context": "", "memory_loaded": False}
    assert called["count"] == 0


def test_memory_loader_loads_when_enabled(monkeypatch):
    called = {"count": 0}

    def _fake_loader(*, user_id: int, subject_id: int) -> str:
        called["count"] += 1
        assert user_id == 22
        assert subject_id == 7
        return "memory summary"

    monkeypatch.setattr("app.graph.load_memory_context", _fake_loader)

    out = memory_loader(
        {
            "messages": [],
            "model": "unknown",
            "pending_tool_calls": 0,
            "pending_tool_calls_data": [],
            "called_tools": [],
            "user_id": 22,
            "subject_id": 7,
            "memory_context": "",
            "memory_loaded": False,
            "memory_enabled": True,
        }
    )

    assert called["count"] == 1
    assert out["memory_context"] == "memory summary"
    assert out["memory_loaded"] is True


def test_memory_updater_noop_when_disabled(monkeypatch):
    called = {"count": 0}

    def _fake_enqueue(**kwargs):
        called["count"] += 1
        return 1

    monkeypatch.setattr("app.graph.enqueue_memory_update", _fake_enqueue)

    out = memory_updater(
        {
            "messages": [HumanMessage(content="hello"), AIMessage(content="hi")],
            "model": "unknown",
            "pending_tool_calls": 0,
            "pending_tool_calls_data": [],
            "called_tools": [],
            "user_id": 1,
            "subject_id": 2,
            "memory_context": "",
            "memory_loaded": False,
            "memory_enabled": False,
        }
    )

    assert out == {}
    assert called["count"] == 0


def test_route_after_agent_preserves_tool_loop_and_exits_via_updater():
    to_tool = route_after_agent(
        {
            "messages": [],
            "model": "unknown",
            "pending_tool_calls": 1,
            "pending_tool_calls_data": [{"name": "foo", "args": {}, "id": "1"}],
            "called_tools": [],
            "user_id": None,
            "subject_id": None,
            "memory_context": "",
            "memory_loaded": False,
            "memory_enabled": False,
        }
    )
    to_updater = route_after_agent(
        {
            "messages": [],
            "model": "unknown",
            "pending_tool_calls": 0,
            "pending_tool_calls_data": [],
            "called_tools": [],
            "user_id": None,
            "subject_id": None,
            "memory_context": "",
            "memory_loaded": False,
            "memory_enabled": False,
        }
    )

    assert to_tool == "tool_executor"
    assert to_updater == "memory_updater"
