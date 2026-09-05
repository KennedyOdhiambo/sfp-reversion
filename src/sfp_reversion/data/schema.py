"""Canonical OHLC frame: the contract every downstream module assumes.

Index: DatetimeIndex, timezone-aware (UTC), named "timestamp", sorted, no duplicates.
Columns: open, high, low, close, volume (float64).
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a frame. Raises ValueError on violations."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("OHLC index must be a DatetimeIndex")
    if df.index.tz is None:
        df = df.tz_localize("UTC")
    else:
        df = df.tz_convert("UTC")
    df = df.sort_index()
    if df.index.has_duplicates:
        raise ValueError("OHLC index contains duplicate timestamps")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLC missing required columns: {missing}")
    numeric = df[REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("OHLC contains non-numeric or missing values")
    if bool((numeric["high"] < numeric["low"]).any()):
        raise ValueError("OHLC contains bars where high < low")
    out = numeric.astype("float64")
    out.index.name = "timestamp"
    return out


def empty_ohlc() -> pd.DataFrame:
    return pd.DataFrame(columns=REQUIRED_COLUMNS, dtype="float64").set_index(
        pd.DatetimeIndex([], name="timestamp", tz="UTC")
    )


def concat_ohlc(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate validated frames, deduplicating on index (first wins)."""
    parts = [validate_ohlc(f) for f in frames]
    if not parts:
        return empty_ohlc()
    out = pd.concat(parts)
    out = out[~out.index.duplicated(keep="first")]
    return validate_ohlc(out)
