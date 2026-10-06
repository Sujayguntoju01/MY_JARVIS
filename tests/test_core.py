import pytest

from assistant.core import AssistantError
from conftest import reply


def test_plain_reply_is_returned_and_remembered(make_assistant, store):
    assistant, model = make_assistant(reply("Hi there!"))
    assert assistant.ask("hello") == "Hi there!"
    assert [(m["role"], m["content"]) for m in store.recent_messages()] == [
        ("user", "hello"), ("assistant", "Hi there!")]

    sent = model.requests[0]
    assert sent["model"] == "fake-model"
    assert sent["messages"][0]["role"] == "system"
    assert "Tue Oct 6, 2026 at 3:00 PM" in sent["messages"][0]["content"]
    assert len(sent["tools"]) == 12


def test_tool_call_runs_and_result_goes_back_to_model(make_assistant, store):
    assistant, model = make_assistant(
        reply(calls=[("add_todo", {"task": "Buy milk"})]),
        reply("Added milk to your list."),
    )
    assert assistant.ask("add milk to my list") == "Added milk to your list."
    assert [t["text"] for t in store.list_todos()] == ["Buy milk"]

    followup = model.requests[1]["messages"]
    assert followup[-2]["role"] == "assistant" and followup[-2]["tool_calls"]
    assert followup[-1] == {"role": "tool", "tool_name": "add_todo", "content": "Added to-do #1: Buy milk"}


def test_several_tools_across_several_steps(make_assistant, store):
    assistant, _ = make_assistant(
        reply(calls=[("add_todo", {"task": "A"}), ("add_todo", {"task": "B"})]),
        reply(calls=[("set_reminder", {"message": "Do A", "when": "2026-10-06 16:00"})]),
        reply("All set."),
    )
    assert assistant.ask("add A and B and remind me about A at 4") == "All set."
    assert len(store.list_todos()) == 2
    assert store.list_reminders()[0]["due_at"] == "2026-10-06T16:00:00"


def test_bad_tool_calls_are_reported_to_the_model_not_crashed_on(make_assistant):
    assistant, model = make_assistant(
        reply(calls=[("launch_rocket", {}), ("add_todo", {"wrong": "x"})]),
        reply("Sorry, I couldn't do that."),
    )
    assert assistant.ask("do something odd") == "Sorry, I couldn't do that."
    results = [m["content"] for m in model.requests[1]["messages"] if m["role"] == "tool"]
    assert "no tool called 'launch_rocket'" in results[0]
    assert "Could not run add_todo" in results[1]


def test_gives_up_politely_if_the_model_never_stops_calling_tools(make_assistant):
    assistant, model = make_assistant(*[reply(calls=[("list_todos", {})]) for _ in range(6)])
    assert "more steps" in assistant.ask("loop forever")
    assert len(model.requests) == 6


def test_earlier_conversation_is_sent_as_context(make_assistant):
    assistant, model = make_assistant(reply("Nice to meet you, Sam."), reply("Your name is Sam."))
    assistant.ask("my name is Sam")
    assistant.ask("what's my name?")
    assert [m["content"] for m in model.requests[1]["messages"][1:]] == [
        "my name is Sam", "Nice to meet you, Sam.", "what's my name?"]


class NotFound(Exception):
    status_code = 404
    error = 'model "fake-model" not found, try pulling it first'


@pytest.mark.parametrize("failure, expected", [
    (ConnectionError("refused"), "can't reach Ollama"),
    (NotFound(), "ollama pull fake-model"),
    (RuntimeError("registry.ollama.ai/x does not support tools"), "can't use tools"),
])
def test_setup_problems_become_clear_messages(make_assistant, store, failure, expected):
    assistant, _ = make_assistant(failure)
    with pytest.raises(AssistantError, match=expected):
        assistant.ask("hello")
    assert store.recent_messages() == []  # a failed turn is not saved


def test_empty_message_is_ignored(make_assistant):
    assistant, model = make_assistant()
    assert assistant.ask("   ") == ""
    assert model.requests == []
