"""Chat with the assistant in a terminal."""

from __future__ import annotations

import threading

from .config import load_config
from .core import Assistant, AssistantError
from .storage import Store
from .tools import friendly_time

HELP = """Just type to chat. Shortcuts:
  /todos       show your to-do list
  /notes       show your notes
  /reminders   show upcoming reminders
  /clear       forget the conversation so far (to-dos, notes and reminders stay)
  /help        show this message
  /quit        exit"""


def _watch_reminders(store: Store, stop: threading.Event, prompt: str) -> None:
    """Background thread: announce reminders when they come due."""
    while not stop.wait(15):
        for reminder in store.pop_due_reminders():
            print(f"\n\a⏰ Reminder: {reminder['text']}\n{prompt}", end="", flush=True)


def run_cli() -> None:
    config = load_config()
    store = Store(config.db_path)
    assistant = Assistant(store, config)
    prompt = "You: "

    print(f"{config.name} is ready (model: {config.model}). Type /help for shortcuts, /quit to exit.\n")
    for reminder in store.pop_due_reminders():
        print(f"⏰ While you were away: {reminder['text']} (was due {friendly_time(reminder['due_at'])})")

    stop = threading.Event()
    threading.Thread(target=_watch_reminders, args=(store, stop, prompt), daemon=True).start()

    try:
        while True:
            try:
                text = input(prompt).strip()
            except EOFError:
                break
            if not text:
                continue
            command = text.lower()
            if command in ("/quit", "/exit", "quit", "exit"):
                break
            if command == "/help":
                print(HELP)
            elif command == "/todos":
                print(assistant.tools["list_todos"](include_completed=True))
            elif command == "/notes":
                print(assistant.tools["find_notes"]())
            elif command == "/reminders":
                print(assistant.tools["list_reminders"]())
            elif command == "/clear":
                store.clear_messages()
                print("Conversation cleared.")
            else:
                try:
                    print(f"{config.name}: {assistant.ask(text)}")
                except AssistantError as error:
                    print(f"[!] {error}")
            print()
    except KeyboardInterrupt:
        print()
    finally:
        stop.set()
    print("Goodbye!")
