"""Typed, read-only access to config.yaml. All tunables live here."""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)


class Config:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def from_file(cls, path: Path = PROJECT_ROOT / "config.yaml") -> Config:
        with path.open() as fh:
            raw = yaml.safe_load(fh) or {}
        return cls(raw)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Fetch by dotted path, e.g. config.get("levels.swing_lookback")."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> dict[str, Any]:
        value = self._data.get(name, {})
        return value if isinstance(value, dict) else {}


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config.from_file()


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
