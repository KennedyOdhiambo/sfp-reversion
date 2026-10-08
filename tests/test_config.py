"""Setup A config smoke test: config loads and every strategy.md tunable is present."""

from sfp_reversion import get_config


def test_config_loads_with_expected_sections() -> None:
    cfg = get_config()
    for section in ("data", "levels", "sfp", "backtest", "validation", "report"):
        assert cfg.section(section), f"missing section: {section}"


def test_key_tunables_present() -> None:
    cfg = get_config()
    assert cfg.get("levels.swing_lookback") == 5
    assert cfg.get("levels.touch_tolerance_atr") == 0.1
    assert cfg.get("sfp.wick_atr") == 0.1
    assert cfg.get("sfp.close_inside_atr") == 0.05
    assert cfg.get("sfp.min_reward_risk") == 1.0
    assert cfg.get("missing.key", "fallback") == "fallback"
