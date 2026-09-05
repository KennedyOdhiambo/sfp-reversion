"""Typed, read-only access to config.yaml (+ env secrets). All tunables live here."""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)

_ENV_OVERRIDES = {
    "data.oanda.token": "SFP_OANDA_TOKEN",
    "data.oanda.account_id": "SFP_OANDA_ACCOUNT_ID",
}


class Config:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def from_file(cls, path: Path = PROJECT_ROOT / "config.yaml") -> Config:
        with path.open() as fh:
            raw = yaml.safe_load(fh) or {}
        for dotted_key, env_var in _ENV_OVERRIDES.items():
            if os.environ.get(env_var):
                raw = _set_nested(raw, dotted_key.split("."), os.environ[env_var])
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


def _set_nested(root: dict[str, Any], parts: list[str], value: Any) -> dict[str, Any]:
    node = root
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return root


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
