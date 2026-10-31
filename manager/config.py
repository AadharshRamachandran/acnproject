"""Typed access to the single YAML configuration file."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"


def _merge(base, override):
    """Recursively merge ``override`` into a copy of ``base``."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path=CONFIG_PATH):
    """Load a config; a top-level ``base:`` path (relative to the file) is merged under it."""
    path = Path(path)
    with open(path, encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    base = config.pop("base", None)
    if base:
        config = _merge(load_config(path.parent / base), config)
    tick = float(config["runtime"]["tick_seconds"])
    if not config["runtime"]["min_tick_seconds"] <= tick <= config["runtime"]["max_tick_seconds"]:
        raise ValueError("runtime.tick_seconds must be between configured min/max tick bounds")
    return config
