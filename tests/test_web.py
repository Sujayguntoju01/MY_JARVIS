from datetime import timedelta

import pytest

from assistant.web import create_app
from conftest import NOW, reply


@pytest.fixture
def web(make_assistant):
    def _web(*responses):
        assistant, _ = make_assistant(*responses)
        return create_app(assistant).test_client()
    return _web


def test_page_loads(web):
    page = web().get("/")
    assert page.status_code == 200
    assert b"Testy" in page.data and b"fake-model" in page.data


def test_chat_round_trip_and_history(web):
    client = web(reply(calls=[("add_todo", {"task": "Water plants"})]), reply("Done!"))
    assert client.post("/api/chat", json={"message": "add water plants"}).get_json() == {"reply": "Done!"}
    assert [m["role"] for m in client.get("/api/history").get_json()] == ["user", "assistant"]

    state = client.get("/api/state").get_json()
    assert state["todos"] == [{"id": 1, "text": "Water plants", "done": 0}]

    assert client.post("/api/todos/1/toggle", json={"done": True}).status_code == 200
    assert client.get("/api/state").get_json()["todos"][0]["done"] == 1
    assert client.post("/api/todos/99/toggle", json={"done": True}).status_code == 404

    assert client.post("/api/clear").get_json() == {"ok": True}
    assert client.get("/api/history").get_json() == []


def test_empty_message_is_rejected(web):
    assert web().post("/api/chat", json={"message": "  "}).status_code == 400
    assert web().post("/api/chat", data="not json").status_code == 400


def test_ollama_problems_are_shown_not_500(web):
    response = web(ConnectionError("refused")).post("/api/chat", json={"message": "hi"})
    assert response.status_code == 503
    assert "can't reach Ollama" in response.get_json()["error"]


def test_due_reminders_endpoint(web, store, clock):
    client = web()
    store.add_reminder("Stand up", NOW + timedelta(minutes=1))
    assert client.get("/api/state").get_json()["reminders"][0]["when"] == "Tue Oct 6, 2026 at 3:01 PM"
    assert client.get("/api/reminders/due").get_json() == []
    clock.moment = NOW + timedelta(minutes=2)
    assert [r["text"] for r in client.get("/api/reminders/due").get_json()] == ["Stand up"]
    assert client.get("/api/reminders/due").get_json() == []
