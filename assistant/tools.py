"""The things the assistant can actually do.

Each tool is a plain Python function with type hints and a docstring. The
Ollama library turns those into a description the model reads, so the
docstrings here are written for the model: say what the tool does and what
each argument should look like.

To add a new ability, write another function inside `build_tools` and add it
to the list at the bottom.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo, available_timezones

import dateparser
import httpx

from .storage import Store

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# https://open-meteo.com/en/docs — WMO weather interpretation codes
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "light freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "light freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "light snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def _http_get_json(url: str, params: dict) -> dict:
    response = httpx.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def parse_when(text: str, now: datetime) -> datetime | None:
    """Turn '2026-10-07 09:00', 'in 20 minutes' or 'tomorrow at 9am' into a datetime."""
    text = str(text).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        # Smooth over a few phrasings the date parser doesn't know.
        cleaned = text.lower()
        tonight = re.search(r"\btonight\b(?:\s+at)?\s*(\d{1,2}(?::\d{2})?)?\s*([ap]m)?", cleaned)
        if tonight:  # "tonight at 8" means 8pm; bare "tonight" means 8pm too
            clock = f"{tonight.group(1) or '8'}{tonight.group(2) or 'pm'}"
            cleaned = f"{cleaned[:tonight.start()]}today at {clock}{cleaned[tonight.end():]}"
        cleaned = re.sub(r"\b(next|this|on)\s+", "", cleaned)
        parsed = dateparser.parse(
            cleaned,
            settings={"PREFER_DATES_FROM": "future", "RELATIVE_BASE": now},
        )
    if parsed is None:
        return None
    if parsed.tzinfo is not None:  # convert to this computer's local time
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def friendly_time(moment: datetime | str) -> str:
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    return f"{moment:%a %b} {moment.day}, {moment.year} at {moment:%I:%M %p}".replace(" 0", " ")


def _find_zone(name: str) -> ZoneInfo | None:
    """Accept 'Asia/Tokyo' as well as a bare city like 'Tokyo'."""
    name = name.strip()
    try:
        return ZoneInfo(name)
    except Exception:
        pass
    wanted = name.lower().replace(" ", "_")
    for zone in sorted(available_timezones()):
        if zone.lower().split("/")[-1] == wanted:
            return ZoneInfo(zone)
    return None


def build_tools(
    store: Store,
    units: str = "imperial",
    now: Callable[[], datetime] = datetime.now,
    http_get: Callable[[str, dict], dict] = _http_get_json,
) -> dict[str, Callable[..., str]]:
    """Create the tool functions, bound to this store. Returns {name: function}."""

    def _match_todo(reference: str) -> dict | None:
        """Find a to-do by its number or by part of its text."""
        todos = store.list_todos(include_done=True)
        ref = str(reference).strip().lstrip("#")
        if ref.isdigit():
            return next((t for t in todos if t["id"] == int(ref)), None)
        hits = [t for t in todos if ref.lower() in t["text"].lower()]
        open_hits = [t for t in hits if not t["done"]]
        return (open_hits or hits or [None])[0]

    # ---- time and weather -------------------------------------------------

    def get_current_time(timezone: str = "") -> str:
        """Get the current date and time.

        Args:
            timezone: Optional place to get the time for, as a city or IANA name such as "Tokyo" or "Europe/London". Leave empty for the user's local time.

        Returns:
            The current date and time.
        """
        if not timezone:
            return f"Local time: {friendly_time(now())}"
        zone = _find_zone(timezone)
        if zone is None:
            return f"Unknown timezone '{timezone}'. Use a name like 'Asia/Tokyo' or 'America/New_York'."
        return f"Time in {zone.key}: {friendly_time(datetime.now(zone))}"

    def get_weather(city: str) -> str:
        """Get the current weather and a 3-day forecast for a city.

        Args:
            city: The city name, for example "Indianapolis" or "Paris".

        Returns:
            Current conditions and the forecast.
        """
        try:
            places = http_get(GEOCODE_URL, {"name": city, "count": 1, "language": "en"})
            results = places.get("results") or []
            if not results:
                return f"I couldn't find a place called '{city}'."
            place = results[0]
            imperial = units == "imperial"
            data = http_get(FORECAST_URL, {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 3,
                "timezone": "auto",
                "temperature_unit": "fahrenheit" if imperial else "celsius",
                "wind_speed_unit": "mph" if imperial else "kmh",
            })
        except Exception as error:  # no internet, service down, etc.
            return f"The weather service could not be reached ({type(error).__name__})."

        deg = "°F" if imperial else "°C"
        speed = "mph" if imperial else "km/h"
        where = ", ".join(p for p in (place.get("name"), place.get("admin1"), place.get("country")) if p)
        cur = data.get("current", {})
        lines = [
            f"Weather in {where}: {WEATHER_CODES.get(cur.get('weather_code'), 'unknown conditions')}, "
            f"{cur.get('temperature_2m')}{deg} (feels like {cur.get('apparent_temperature')}{deg}), "
            f"humidity {cur.get('relative_humidity_2m')}%, wind {cur.get('wind_speed_10m')} {speed}."
        ]
        daily = data.get("daily", {})
        for i, day in enumerate(daily.get("time", [])):
            label = "Today" if i == 0 else datetime.fromisoformat(day).strftime("%A")
            rain = (daily.get("precipitation_probability_max") or [None] * 9)[i]
            lines.append(
                f"{label}: {WEATHER_CODES.get(daily['weather_code'][i], 'unknown')}, "
                f"high {daily['temperature_2m_max'][i]}{deg}, low {daily['temperature_2m_min'][i]}{deg}"
                + (f", {rain}% chance of precipitation" if rain is not None else "")
            )
        return "\n".join(lines)

    # ---- to-dos -----------------------------------------------------------

    def add_todo(task: str) -> str:
        """Add a task to the user's to-do list.

        Args:
            task: What needs to be done, for example "Buy milk".

        Returns:
            Confirmation with the task's number.
        """
        task = str(task).strip()
        if not task:
            return "No task text was given."
        return f"Added to-do #{store.add_todo(task)}: {task}"

    def list_todos(include_completed: bool = False) -> str:
        """Show the user's to-do list.

        Args:
            include_completed: Set true to also show tasks that are already done.

        Returns:
            The tasks, one per line.
        """
        todos = store.list_todos(include_done=bool(include_completed))
        if not todos:
            return "The to-do list is empty."
        return "\n".join(f"#{t['id']} [{'x' if t['done'] else ' '}] {t['text']}" for t in todos)

    def complete_todo(task: str) -> str:
        """Mark a to-do as done.

        Args:
            task: The task's number (like "3") or some of its text (like "milk").

        Returns:
            Confirmation of which task was completed.
        """
        todo = _match_todo(task)
        if todo is None:
            return f"No to-do matches '{task}'."
        store.set_todo_done(todo["id"], True)
        return f"Completed to-do #{todo['id']}: {todo['text']}"

    def delete_todo(task: str) -> str:
        """Remove a to-do from the list entirely.

        Args:
            task: The task's number (like "3") or some of its text (like "milk").

        Returns:
            Confirmation of which task was removed.
        """
        todo = _match_todo(task)
        if todo is None:
            return f"No to-do matches '{task}'."
        store.delete_todo(todo["id"])
        return f"Deleted to-do #{todo['id']}: {todo['text']}"

    # ---- notes ------------------------------------------------------------

    def save_note(title: str, content: str) -> str:
        """Save a note so the user can look it up later.

        Args:
            title: A short title for the note.
            content: The full text of the note.

        Returns:
            Confirmation with the note's number.
        """
        title, content = str(title).strip(), str(content).strip()
        if not (title or content):
            return "The note was empty, so nothing was saved."
        note_id = store.add_note(title or content[:40], content or title)
        return f"Saved note #{note_id}: {title or content[:40]}"

    def find_notes(search: str = "") -> str:
        """Look up the user's saved notes.

        Args:
            search: A word or phrase to search for. Leave empty to list every note.

        Returns:
            The matching notes.
        """
        notes = store.list_notes(str(search).strip())
        if not notes:
            return f"No notes match '{search}'." if search else "There are no saved notes."
        return "\n".join(f"#{n['id']} {n['title']}: {n['body']}" for n in notes)

    def delete_note(note_number: int) -> str:
        """Delete a saved note.

        Args:
            note_number: The number of the note to delete.

        Returns:
            Confirmation.
        """
        try:
            note_id = int(str(note_number).lstrip("#"))
        except ValueError:
            return "Give the note's number, for example 2."
        return f"Deleted note #{note_id}." if store.delete_note(note_id) else f"There is no note #{note_id}."

    # ---- reminders --------------------------------------------------------

    def set_reminder(message: str, when: str) -> str:
        """Set a reminder that will alert the user at a specific time.

        Args:
            message: What to remind the user about, for example "Call the dentist".
            when: When to remind them. Best as "YYYY-MM-DD HH:MM" in 24-hour local time. Phrases like "in 20 minutes" or "tomorrow at 9am" also work.

        Returns:
            Confirmation with the exact time the reminder is set for.
        """
        current = now()
        due = parse_when(when, current)
        if due is None:
            return f"I couldn't understand the time '{when}'. Use the form YYYY-MM-DD HH:MM."
        if due <= current:
            return f"{friendly_time(due)} is in the past. It is now {friendly_time(current)}."
        reminder_id = store.add_reminder(str(message).strip(), due)
        return f"Reminder #{reminder_id} set for {friendly_time(due)}: {message}"

    def list_reminders() -> str:
        """Show the reminders that have not gone off yet.

        Returns:
            Upcoming reminders, soonest first.
        """
        reminders = store.list_reminders()
        if not reminders:
            return "There are no upcoming reminders."
        return "\n".join(f"#{r['id']} {friendly_time(r['due_at'])}: {r['text']}" for r in reminders)

    def cancel_reminder(reminder_number: int) -> str:
        """Cancel an upcoming reminder.

        Args:
            reminder_number: The number of the reminder to cancel.

        Returns:
            Confirmation.
        """
        try:
            reminder_id = int(str(reminder_number).lstrip("#"))
        except ValueError:
            return "Give the reminder's number, for example 2."
        if store.delete_reminder(reminder_id):
            return f"Cancelled reminder #{reminder_id}."
        return f"There is no reminder #{reminder_id}."

    tools = [
        get_current_time, get_weather,
        add_todo, list_todos, complete_todo, delete_todo,
        save_note, find_notes, delete_note,
        set_reminder, list_reminders, cancel_reminder,
    ]
    return {tool.__name__: tool for tool in tools}
