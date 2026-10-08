import numpy as np
import pandas as pd

import screener


def make_closes(n=300):
    rng = np.random.default_rng(0)
    idx = pd.bdate_range(end="2026-10-01", periods=n)
    t = np.arange(n)
    return pd.DataFrame(
        {
            "UP": 100 * np.exp(0.002 * t + rng.normal(0, 0.01, n).cumsum() * 0.1),
            "FLAT": 100 + rng.normal(0, 1, n),
            "DOWN": 100 * np.exp(-0.002 * t),
            "NEW": [np.nan] * (n - 50) + list(np.linspace(10, 12, 50)),
        },
        index=idx,
    )


def test_uptrend_ranks_first_and_downtrend_excluded():
    picks, skipped = screener.suggest(make_closes(), top=10)
    tickers = [m.ticker for m in picks]
    assert tickers[0] == "UP"
    assert "DOWN" not in tickers
    assert skipped == ["NEW"]


def test_rsi_bounds():
    s = pd.Series(np.linspace(1, 2, 50))
    assert screener.rsi(s) == 100.0
    assert 0 <= screener.rsi(pd.Series(np.sin(np.arange(100) / 5) + 5)) <= 100


def test_run_once_writes_history_and_flags_new(tmp_path, capsys):
    hist = tmp_path / "h.csv"
    current = screener.run_once(["UP", "FLAT", "DOWN"], 5, hist, {"FLAT"},
                                fetch=lambda _: make_closes())
    assert "UP" in current
    out = capsys.readouterr().out
    assert "NEW" in out
    assert hist.read_text().splitlines()[0].startswith("timestamp")


def test_load_watchlist(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("# comment\naapl\nMSFT  # inline\n\naapl\n")
    assert screener.load_watchlist(f) == ["AAPL", "MSFT"]
