"""
Persistent configuration — stores last-used model and UI preferences.
Settings are saved to a JSON file next to the script.
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / ".ollama_chat_config.json"

_defaults: dict = {
    "last_model": None,
    "window_width": 1100,
    "window_height": 780,
    "window_x": None,
    "window_y": None,
}


def load() -> dict:
    """Load config from disk, returning defaults if file doesn't exist."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**_defaults, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_defaults)


def save(cfg: dict) -> None:
    """Persist config to disk."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass
