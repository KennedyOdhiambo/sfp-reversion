"""Block 0 smoke test: config loads and every §2 tunable is present."""
from sfp_reversion import get_config


def test_config_loads_with_expected_sections() -> None:
    cfg = get_config()
    for section in ("data", "levels", "confluence", "confirmation", "signal", "backtest"):
        assert cfg.section(section), f"missing section: {section}"


def test_key_tunables_present() -> None:
    cfg = get_config()
    assert cfg.get("levels.swing_lookback") == 5
    assert cfg.get("levels.touch_tolerance_atr") == 0.1
    assert cfg.get("confirmation.sfp.wick_atr") == 0.1
    assert cfg.get("signal.touch_confluence.2") == 1
    assert cfg.get("missing.key", "fallback") == "fallback"
