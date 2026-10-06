# MY_JARVIS

A personal assistant chatbot written in Python that runs entirely on your own computer. It uses a local AI model through [Ollama](https://ollama.com), so there are no API keys, no usage fees, and your conversations never leave your machine.

You can chat with it in a terminal or in your browser. Both share the same memory.

## What it can do

- **Chat** about anything, and remember the conversation between sessions
- **To-do list**: "add milk to my list", "what's on my list?", "mark the milk one done"
- **Notes**: "save a note that the wifi password is maple-guest", "what was the wifi password?"
- **Reminders**: "remind me to stretch in 20 minutes", "remind me tomorrow at 9am to call the dentist"
- **Weather**: "what's the weather in Chicago?" (free [Open-Meteo](https://open-meteo.com) service, no key needed)
- **Date and time**: "what time is it in Tokyo?"

## Setup

You need [Python 3.10 or newer](https://www.python.org/downloads/) and [Ollama](https://ollama.com/download).

**1. Download a model.** After installing Ollama, run:

```bash
ollama pull llama3.2
```

That is a small model (about 2 GB) that runs on most laptops. See [Choosing a model](#choosing-a-model) for stronger options.

**2. Get the code and install the Python packages.**

```bash
git clone https://github.com/Sujayguntoju01/MY_JARVIS.git
cd MY_JARVIS
python -m venv .venv
```

Activate the environment:

| System | Command |
| --- | --- |
| Windows | `.venv\Scripts\activate` |
| macOS / Linux | `source .venv/bin/activate` |

Then install:

```bash
python -m pip install -r requirements.txt
```

## Running it

Make sure the Ollama app is running, then:

```bash
python -m assistant        # chat in the terminal
python -m assistant web    # chat in the browser at http://127.0.0.1:5000
```

In the terminal, type `/help` to see shortcuts such as `/todos`, `/notes`, `/reminders` and `/clear`.

Reminders pop up in whichever interface is open when they come due. If nothing was open, the terminal shows what you missed the next time you start it, and the browser shows it when the page loads.

## Settings

Everything is optional and set through environment variables.

| Variable | Default | What it does |
| --- | --- | --- |
| `ASSISTANT_MODEL` | `llama3.2` | Which Ollama model to use |
| `ASSISTANT_NAME` | `Jarvis` | What the assistant calls itself |
| `ASSISTANT_UNITS` | `imperial` | `imperial` (°F, mph) or `metric` (°C, km/h) for weather |
| `ASSISTANT_DB` | `data/assistant.db` | Where your data is stored |
| `ASSISTANT_HISTORY` | `30` | How many past messages the model sees each turn |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama is listening |

Example (macOS / Linux):

```bash
ASSISTANT_NAME=Friday ASSISTANT_UNITS=metric python -m assistant
```

Example (Windows PowerShell):

```powershell
$env:ASSISTANT_NAME = "Friday"; python -m assistant
```

## Choosing a model

The assistant needs a model that supports **tool calling**, which is how it adds to-dos, sets reminders and so on. Bigger models follow instructions more reliably but need more memory.

| Model | Download size | Good for |
| --- | --- | --- |
| `llama3.2` | about 2 GB | Most laptops; the default |
| `qwen3` | about 5 GB | Computers with 16 GB of RAM or a graphics card; noticeably better at using tools |

Browse more at [ollama.com/search?c=tools](https://ollama.com/search?c=tools). To switch, pull the model and set `ASSISTANT_MODEL`.

Small models sometimes slip: they may say they added a reminder without actually doing it, or get a date wrong. The sidebar in the browser (or `/reminders` in the terminal) shows what was really saved.

## How it works

```
assistant/
├── core.py        the conversation loop: sends messages to the model, runs the tools it asks for
├── tools.py       what the assistant can do (to-dos, notes, reminders, weather, time)
├── storage.py     saves everything in a local SQLite file
├── config.py      settings
├── cli.py         terminal interface
├── web.py         browser interface (Flask)
└── templates/     the chat page
tests/             automated tests
```

Each turn, `core.py` sends your message, the recent conversation and a description of every tool to the model. If the model replies asking to use a tool, the assistant runs that Python function, sends the result back, and repeats until the model gives a normal answer.

### Adding your own ability

Tools are ordinary Python functions. Add one inside `build_tools` in `assistant/tools.py` and include it in the list at the bottom:

```python
def flip_coin() -> str:
    """Flip a coin for the user.

    Returns:
        Heads or tails.
    """
    import random
    return random.choice(["Heads", "Tails"])
```

The docstring matters: it is what the model reads to decide when to use the tool.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

The tests use a scripted stand-in for the model, so they run without Ollama.

## Privacy

Your chat history, to-dos, notes and reminders live in `data/assistant.db` on your computer; that folder is excluded from Git. The browser interface only accepts connections from your own machine. The one thing that goes over the internet is the city name when you ask about the weather.
