from datetime import timedelta

from assistant.storage import Store
from conftest import NOW


def test_messages_come_back_oldest_first_and_respect_limit(store):
    for i in range(5):
        store.add_message("user", f"m{i}")
    assert [m["content"] for m in store.recent_messages(3)] == ["m2", "m3", "m4"]
    store.clear_messages()
    assert store.recent_messages() == []


def test_todo_lifecycle(store):
    first = store.add_todo("Buy milk")
    store.add_todo("Call mom")
    assert store.set_todo_done(first)
    assert [t["text"] for t in store.list_todos()] == ["Call mom"]
    assert len(store.list_todos(include_done=True)) == 2
    assert store.delete_todo(first)
    assert not store.delete_todo(first)
    assert not store.set_todo_done(999)


def test_notes_search_title_and_body(store):
    store.add_note("Wifi", "password is hunter2")
    store.add_note("Recipe", "use the wifi scale")
    store.add_note("Gift ideas", "a scarf")
    assert len(store.list_notes()) == 3
    assert {n["title"] for n in store.list_notes("wifi")} == {"Wifi", "Recipe"}


def test_due_reminders_are_delivered_exactly_once(store, clock):
    store.add_reminder("soon", NOW + timedelta(minutes=5))
    store.add_reminder("later", NOW + timedelta(hours=2))
    assert store.pop_due_reminders() == []

    clock.moment = NOW + timedelta(minutes=5)
    assert [r["text"] for r in store.pop_due_reminders()] == ["soon"]
    assert store.pop_due_reminders() == []
    assert [r["text"] for r in store.list_reminders()] == ["later"]


def test_data_survives_reopening_the_file(tmp_path):
    path = tmp_path / "nested" / "a.db"
    Store(path).add_todo("persist me")
    assert [t["text"] for t in Store(path).list_todos()] == ["persist me"]
