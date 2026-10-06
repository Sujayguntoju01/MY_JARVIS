from datetime import datetime

import pytest
from ollama._utils import convert_function_to_tool

from assistant.tools import FORECAST_URL, GEOCODE_URL, build_tools, friendly_time, parse_when
from conftest import NOW


@pytest.fixture
def tools(store, clock):
    return build_tools(store, now=clock)


@pytest.mark.parametrize("text, expected", [
    ("2026-10-07 09:00", datetime(2026, 10, 7, 9, 0)),
    ("2026-10-07T09:00:00", datetime(2026, 10, 7, 9, 0)),
    ("in 20 minutes", datetime(2026, 10, 6, 15, 20)),
    ("in 2 hours", datetime(2026, 10, 6, 17, 0)),
    ("tomorrow at 9am", datetime(2026, 10, 7, 9, 0)),
    ("tonight at 8", datetime(2026, 10, 6, 20, 0)),
    ("tonight at 9:30pm", datetime(2026, 10, 6, 21, 30)),
    ("tonight", datetime(2026, 10, 6, 20, 0)),
    ("next friday at 3pm", datetime(2026, 10, 9, 15, 0)),
    ("on friday at 3pm", datetime(2026, 10, 9, 15, 0)),
])
def test_parse_when(text, expected):
    assert parse_when(text, NOW) == expected


def test_parse_when_rejects_nonsense():
    assert parse_when("whenever the cows come home", NOW) is None
    assert parse_when("", NOW) is None


def test_friendly_time():
    assert friendly_time(datetime(2026, 10, 6, 15, 2)) == "Tue Oct 6, 2026 at 3:02 PM"
    assert friendly_time("2026-12-25T09:00:00") == "Fri Dec 25, 2026 at 9:00 AM"


def test_every_tool_converts_to_an_ollama_schema(tools):
    """Ollama builds each tool's description from its signature and docstring."""
    for name, function in tools.items():
        schema = convert_function_to_tool(function).function
        assert schema.name == name
        assert schema.description, f"{name} has no description"
        for argument, spec in (schema.parameters.properties or {}).items():
            assert spec.description, f"{name}.{argument} has no description"
    required = convert_function_to_tool(tools["set_reminder"]).function.parameters.required
    assert set(required) == {"message", "when"}


def test_todos_by_number_or_text(tools, store):
    assert "#1" in tools["add_todo"]("Buy milk")
    tools["add_todo"]("Call the dentist")
    assert "Buy milk" in tools["list_todos"]()

    assert "Completed to-do #2" in tools["complete_todo"]("dentist")
    assert "Completed to-do #1" in tools["complete_todo"]("1")   # models often send numbers as text
    assert tools["list_todos"]() == "The to-do list is empty."
    assert "[x] Buy milk" in tools["list_todos"](include_completed=True)

    assert "No to-do matches" in tools["complete_todo"]("laundry")
    assert "Deleted to-do #1" in tools["delete_todo"]("#1")
    assert len(store.list_todos(include_done=True)) == 1


def test_notes(tools):
    assert "Saved note #1" in tools["save_note"]("Wifi", "password is hunter2")
    assert "hunter2" in tools["find_notes"]("wifi")
    assert "No notes match" in tools["find_notes"]("garage code")
    assert tools["delete_note"]("1") == "Deleted note #1."
    assert tools["find_notes"]() == "There are no saved notes."


def test_reminders(tools, store):
    assert "Tue Oct 6, 2026 at 3:20 PM" in tools["set_reminder"]("Stretch", "in 20 minutes")
    assert "in the past" in tools["set_reminder"]("Too late", "2026-10-06 09:00")
    assert "couldn't understand" in tools["set_reminder"]("Vague", "sometime-ish")
    assert "Stretch" in tools["list_reminders"]()
    assert len(store.list_reminders()) == 1
    assert tools["cancel_reminder"](1) == "Cancelled reminder #1."
    assert tools["list_reminders"]() == "There are no upcoming reminders."


def test_time_tool(tools):
    assert tools["get_current_time"]() == "Local time: Tue Oct 6, 2026 at 3:00 PM"
    assert tools["get_current_time"]("Tokyo").startswith("Time in Asia/Tokyo:")
    assert tools["get_current_time"]("Europe/London").startswith("Time in Europe/London:")
    assert "Unknown timezone" in tools["get_current_time"]("Atlantis")


# Shaped like real Open-Meteo responses.
PLACE = {"results": [{"name": "Indianapolis", "admin1": "Indiana", "country": "United States",
                      "latitude": 39.76838, "longitude": -86.15804}]}
FORECAST = {
    "current": {"temperature_2m": 68.4, "apparent_temperature": 66.1, "relative_humidity_2m": 55,
                "weather_code": 2, "wind_speed_10m": 7.5},
    "daily": {"time": ["2026-10-06", "2026-10-07", "2026-10-08"],
              "weather_code": [2, 61, 0],
              "temperature_2m_max": [70.1, 64.0, 66.2],
              "temperature_2m_min": [51.3, 49.9, 45.0],
              "precipitation_probability_max": [10, 80, None]},
}


def test_weather_reads_the_forecast(store, clock):
    requests = []

    def fake_get(url, params):
        requests.append((url, params))
        return PLACE if url == GEOCODE_URL else FORECAST

    report = build_tools(store, units="imperial", now=clock, http_get=fake_get)["get_weather"]("Indianapolis")
    assert "Weather in Indianapolis, Indiana, United States: partly cloudy, 68.4°F" in report
    assert "Wednesday: light rain, high 64.0°F, low 49.9°F, 80% chance of precipitation" in report
    assert report.splitlines()[-1] == "Thursday: clear sky, high 66.2°F, low 45.0°F"
    assert requests[1][0] == FORECAST_URL and requests[1][1]["temperature_unit"] == "fahrenheit"

    build_tools(store, units="metric", now=clock, http_get=fake_get)["get_weather"]("Indianapolis")
    assert requests[-1][1]["temperature_unit"] == "celsius"


def test_weather_handles_unknown_city_and_no_internet(store, clock):
    unknown = build_tools(store, now=clock, http_get=lambda url, params: {})["get_weather"]("Xyzzy")
    assert "couldn't find" in unknown

    def offline(url, params):
        raise OSError("no network")

    assert "could not be reached" in build_tools(store, now=clock, http_get=offline)["get_weather"]("Paris")
