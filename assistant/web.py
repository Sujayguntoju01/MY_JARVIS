"""Chat with the assistant in a browser (a small Flask app)."""

from __future__ import annotations

import threading

from flask import Flask, jsonify, render_template, request

from .config import load_config
from .core import Assistant, AssistantError
from .storage import Store
from .tools import friendly_time


def create_app(assistant: Assistant | None = None) -> Flask:
    if assistant is None:
        config = load_config()
        assistant = Assistant(Store(config.db_path), config)
    store = assistant.store
    turn_lock = threading.Lock()  # one conversation turn at a time

    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html", name=assistant.config.name, model=assistant.config.model)

    @app.get("/api/history")
    def history():
        return jsonify(store.recent_messages(200))

    @app.post("/api/chat")
    def chat():
        text = str((request.get_json(silent=True) or {}).get("message", "")).strip()
        if not text:
            return jsonify(error="Type a message first."), 400
        try:
            with turn_lock:
                reply = assistant.ask(text)
        except AssistantError as error:
            return jsonify(error=str(error)), 503
        return jsonify(reply=reply)

    @app.get("/api/state")
    def state():
        """Everything the sidebar shows."""
        return jsonify(
            todos=store.list_todos(include_done=True),
            notes=store.list_notes(),
            reminders=[{**r, "when": friendly_time(r["due_at"])} for r in store.list_reminders()],
        )

    @app.post("/api/todos/<int:todo_id>/toggle")
    def toggle_todo(todo_id: int):
        done = bool((request.get_json(silent=True) or {}).get("done", True))
        if not store.set_todo_done(todo_id, done):
            return jsonify(error="No such to-do."), 404
        return jsonify(ok=True)

    @app.get("/api/reminders/due")
    def due_reminders():
        return jsonify(store.pop_due_reminders())

    @app.post("/api/clear")
    def clear():
        store.clear_messages()
        return jsonify(ok=True)

    return app


def run_web(port: int = 5000) -> None:
    app = create_app()
    print(f"Open http://127.0.0.1:{port} in your browser. Press Ctrl+C to stop.")
    # 127.0.0.1 keeps the assistant reachable from this computer only.
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
