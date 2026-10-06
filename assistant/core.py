"""The assistant's brain: sends the conversation to the local model and runs
any tools the model asks for until it has a final answer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from .config import Config, load_config
from .storage import Store
from .tools import build_tools, friendly_time

SYSTEM_PROMPT = """You are {name}, a friendly personal assistant running privately on the user's own computer.
The current local date and time is {now}.

You have tools for the user's to-do list, notes and reminders, and for looking up the weather and the time.
- When the user asks to add, show, change or remove a to-do, note or reminder, call the matching tool. Never claim you did it without calling the tool.
- For weather or the time somewhere, call the tool instead of guessing.
- For reminders, work out the exact time from the current date and time above and pass it as "YYYY-MM-DD HH:MM".
- You may call several tools in a row if a request needs it.
- For ordinary conversation and general questions, just answer; no tool is needed.

Keep replies short, warm and to the point. Report tool results in plain sentences."""


class AssistantError(Exception):
    """A problem worth showing to the user as-is (e.g. Ollama isn't running)."""


class Assistant:
    def __init__(
        self,
        store: Store,
        config: Config | None = None,
        chat_fn: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] = datetime.now,
        max_steps: int = 6,
    ):
        self.store = store
        self.config = config or load_config()
        self.clock = clock
        self.max_steps = max_steps
        self.tools = build_tools(store, units=self.config.units, now=clock)
        self._chat = chat_fn or self._ollama_chat()

    def _ollama_chat(self) -> Callable[..., Any]:
        import ollama  # imported here so tests can run without Ollama installed

        return ollama.Client(host=self.config.ollama_host).chat

    def ask(self, text: str) -> str:
        """Send one user message and return the assistant's reply."""
        text = text.strip()
        if not text:
            return ""

        messages: list[Any] = [{
            "role": "system",
            "content": SYSTEM_PROMPT.format(name=self.config.name, now=friendly_time(self.clock())),
        }]
        for past in self.store.recent_messages(self.config.history_limit):
            messages.append({"role": past["role"], "content": past["content"]})
        messages.append({"role": "user", "content": text})

        reply = self._run(messages)

        # Saved only once we have an answer, so a failed turn leaves no half-conversation.
        self.store.add_message("user", text)
        self.store.add_message("assistant", reply)
        return reply

    def _run(self, messages: list[Any]) -> str:
        for _ in range(self.max_steps):
            message = self._call_model(messages).message
            tool_calls = list(message.tool_calls or [])
            if not tool_calls:
                return (message.content or "").strip() or "Sorry, I didn't come up with an answer. Could you rephrase that?"

            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                name = call.function.name
                result = self._run_tool(name, dict(call.function.arguments or {}))
                messages.append({"role": "tool", "tool_name": name, "content": result})
        return "Sorry, that took more steps than I could manage. Could you try asking in smaller pieces?"

    def _run_tool(self, name: str, arguments: dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"There is no tool called '{name}'. Available tools: {', '.join(self.tools)}."
        try:
            return str(tool(**arguments))
        except TypeError as error:  # the model sent wrong or missing arguments
            return f"Could not run {name}: {error}"
        except Exception as error:
            return f"{name} failed: {type(error).__name__}: {error}"

    def _call_model(self, messages: list[Any]) -> Any:
        try:
            return self._chat(
                model=self.config.model,
                messages=messages,
                tools=list(self.tools.values()),
            )
        except ConnectionError as error:
            raise AssistantError(
                f"I can't reach Ollama at {self.config.ollama_host}. "
                "Make sure the Ollama app is running, then try again."
            ) from error
        except Exception as error:
            status = getattr(error, "status_code", None)
            detail = str(getattr(error, "error", "") or error)
            if status == 404 or "not found" in detail.lower():
                raise AssistantError(
                    f"The model '{self.config.model}' isn't downloaded yet. "
                    f"Run:  ollama pull {self.config.model}"
                ) from error
            if "does not support tools" in detail.lower():
                raise AssistantError(
                    f"The model '{self.config.model}' can't use tools. "
                    "Pick one that can, such as llama3.2 or qwen3 (set ASSISTANT_MODEL)."
                ) from error
            raise AssistantError(f"The model returned an error: {detail}") from error
