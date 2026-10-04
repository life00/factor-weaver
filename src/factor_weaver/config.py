"""YAML config loading: config/<name>.yaml merged left-to-right."""

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path("config")


def load(*names: str) -> dict[str, Any]:
    """Merge the named config files; later files win on key collisions."""
    cfg: dict[str, Any] = {}
    for name in names:
        with open(CONFIG_DIR / f"{name}.yaml") as f:
            cfg |= yaml.safe_load(f) or {}
    return cfg
