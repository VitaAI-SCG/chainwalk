import json
import os
import pathlib

_DEFAULT = {
    "brand_name": "ChainWalk Museum V8",
    "tagline": "Live Bitcoin Block Tours",
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "gemma3:12b",
    "docent_enabled": True,
    "docent_max_calls": 32,
    "tour_delay_secs": 30,
    "tour_sticky": True,
    "verbose": False,
}

_CONFIG = None


def _load_config_file() -> dict:
    """Load config.json from project root, if present."""
    root = pathlib.Path(__file__).resolve().parent.parent
    path = root / "config.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def get_config() -> dict:
    """
    Return merged configuration:
    - defaults
    - overridden by config.json
    - overridden by env vars
    """
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    cfg = dict(_DEFAULT)
    cfg.update(_load_config_file())

    # Env overrides
    base_url = os.getenv("SOV_OLLAMA_BASE_URL")
    model = os.getenv("SOV_OLLAMA_MODEL")
    docent_on = os.getenv("SOV_DOCENT_ON")
    docent_max = os.getenv("SOV_DOCENT_MAX_CALLS")
    tour_delay = os.getenv("SOV_TOUR_DELAY_SECS")
    tour_sticky = os.getenv("SOV_TOUR_STICKY")
    verbose = os.getenv("SOV_VERBOSE")

    if base_url:
        cfg["ollama_base_url"] = base_url
    if model:
        cfg["ollama_model"] = model
    if docent_on is not None:
        cfg["docent_enabled"] = docent_on == "1"
    if docent_max:
        try:
            cfg["docent_max_calls"] = int(docent_max)
        except ValueError:
            pass
    if tour_delay:
        try:
            cfg["tour_delay_secs"] = int(tour_delay)
        except ValueError:
            pass
    if tour_sticky is not None:
        cfg["tour_sticky"] = tour_sticky == "1"
    if verbose is not None:
        cfg["verbose"] = verbose == "1"

    _CONFIG = cfg
    return _CONFIG
