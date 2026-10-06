"""Shared test helpers. The tests use a scripted stand-in for the model, so
they run anywhere without Ollama installed."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from assistant.config import Config
from assistant.core import Assistant
from assistant.storage import Store

NOW = datetime(2026, 10, 6, 15, 0, 0)  # a Tuesday, 3:00 PM


class Clock:
    def __init__(self, moment: datetime = NOW):
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def reply(content: str = "", calls: list[tuple[str, dict]] | None = None) -> SimpleNamespace:
    """Build a response shaped like the ones the Ollama library returns."""
    tool_calls = [
        SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))
        for name, arguments in (calls or [])
    ]
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls or None))


class FakeModel:
    """Returns pre-written responses in order and records what it was sent."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def __call__(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        next_response = self.responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path, clock) -> Store:
    return Store(tmp_path / "test.db", clock=clock)


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(name="Testy", model="fake-model", ollama_host="http://127.0.0.1:11434",
                  db_path=tmp_path / "test.db", units="imperial", history_limit=30)


@pytest.fixture
def make_assistant(store, config, clock):
    def _make(*responses) -> tuple[Assistant, FakeModel]:
        model = FakeModel(*responses)
        return Assistant(store, config, chat_fn=model, clock=clock), model
    return _make
