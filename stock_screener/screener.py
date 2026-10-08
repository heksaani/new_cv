"""Stock screener that ranks a watchlist and suggests buy candidates.

The score combines a few well-known, simple signals computed from daily prices:

* 12-1 momentum   - return over the last 12 months, skipping the most recent month
* 3-month momentum
* risk-adjusted momentum - 12-1 momentum divided by annualised volatility
* closeness to the 52-week high
* trend filter    - price above its 200-day average (required), 50-day above 200-day (bonus)
* RSI(14)         - penalise very overbought names, reward pullbacks inside an uptrend

This is a research aid, not financial advice. Past price behaviour does not
guarantee future returns.

Usage:
    python screener.py                      # run once and print suggestions
    python screener.py --watch              # keep running, re-check every 60 minutes
    python screener.py --watch --interval 15 --top 5
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_WATCHLIST = HERE / "watchlist.txt"
DEFAULT_HISTORY = HERE / "history.csv"

MIN_HISTORY_DAYS = 220

# Weights for the cross-sectional percentile ranks. They sum to 1.
WEIGHTS = {
    "mom_12_1": 0.30,
    "mom_3m": 0.20,
    "risk_adj_mom": 0.30,
    "near_high": 0.20,
}


@dataclass
class Metrics:
    ticker: str
    price: float
    mom_12_1: float
    mom_3m: float
    volatility: float
    risk_adj_mom: float
    near_high: float  # price / 52-week high, 1.0 = at the high
    rsi: float
    above_sma200: bool
    sma50_above_sma200: bool
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


def load_watchlist(path: Path) -> list[str]:
    tickers = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip().upper()
        if line and line not in tickers:
            tickers.append(line)
    return tickers


def fetch_closes(tickers: list[str]) -> pd.DataFrame:
    """Download ~14 months of daily adjusted closes. Columns = tickers."""
    import yfinance as yf

    data = yf.download(
        tickers,
        period="14mo",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if data.empty:
        return pd.DataFrame()
    closes = data["Close"]
    if isinstance(closes, pd.Series):  # single ticker
        closes = closes.to_frame(tickers[0])
    return closes.dropna(how="all")


def rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = gain.iloc[-1] / last_loss
    return float(100 - 100 / (1 + rs))


def compute_metrics(ticker: str, close: pd.Series) -> Metrics | None:
    close = close.dropna()
    if len(close) < MIN_HISTORY_DAYS:
        return None

    price = float(close.iloc[-1])
    year_ago = close.iloc[-min(252, len(close))]
    month_ago = close.iloc[-21]
    mom_12_1 = float(month_ago / year_ago - 1)
    mom_3m = float(price / close.iloc[-63] - 1)

    daily = close.pct_change().dropna().iloc[-252:]
    volatility = float(daily.std() * (252 ** 0.5))
    risk_adj = mom_12_1 / volatility if volatility > 0 else 0.0

    high_52w = float(close.iloc[-252:].max())
    sma50 = float(close.iloc[-50:].mean())
    sma200 = float(close.iloc[-200:].mean())

    return Metrics(
        ticker=ticker,
        price=price,
        mom_12_1=mom_12_1,
        mom_3m=mom_3m,
        volatility=volatility,
        risk_adj_mom=risk_adj,
        near_high=price / high_52w,
        rsi=rsi(close.iloc[-120:]),
        above_sma200=price > sma200,
        sma50_above_sma200=sma50 > sma200,
    )


def score(metrics: list[Metrics]) -> list[Metrics]:
    """Score each stock against the others in the list (percentile ranks), best first."""
    if not metrics:
        return []
    df = pd.DataFrame([{k: getattr(m, k) for k in WEIGHTS} for m in metrics])
    ranks = df.rank(pct=True)
    base = sum(ranks[k] * w for k, w in WEIGHTS.items())

    for m, s in zip(metrics, base):
        s = float(s) * 100
        reasons = []
        if m.mom_12_1 > 0.20:
            reasons.append(f"strong 12m momentum ({m.mom_12_1:+.0%})")
        if m.mom_3m > 0.05:
            reasons.append(f"rising last 3m ({m.mom_3m:+.0%})")
        if m.near_high >= 0.95:
            reasons.append("near 52w high")
        if m.sma50_above_sma200:
            s += 5
            reasons.append("uptrend (50d > 200d avg)")
        if m.rsi > 75:
            s -= 10
            reasons.append(f"overbought, RSI {m.rsi:.0f} - consider waiting")
        elif 40 <= m.rsi <= 55 and m.sma50_above_sma200:
            s += 5
            reasons.append(f"pullback in uptrend, RSI {m.rsi:.0f}")
        if not m.above_sma200:
            s -= 50  # fails the trend filter; never suggested
        m.score = s
        m.reasons = reasons
    return sorted(metrics, key=lambda m: m.score, reverse=True)


def suggest(closes: pd.DataFrame, top: int) -> tuple[list[Metrics], list[str]]:
    """Return (top suggestions, tickers skipped for lack of data)."""
    metrics, skipped = [], []
    for ticker in closes.columns:
        m = compute_metrics(str(ticker), closes[ticker])
        (metrics.append(m) if m else skipped.append(str(ticker)))
    ranked = [m for m in score(metrics) if m.above_sma200]
    return ranked[:top], skipped


def format_table(picks: list[Metrics], previous: set[str]) -> str:
    if not picks:
        return "No stocks passed the trend filter right now (all below their 200-day average)."
    lines = [
        f"{'#':>2}  {'Ticker':<9}{'Price':>10}{'Score':>7}{'12-1m':>8}{'3m':>7}{'Vol':>6}{'RSI':>5}  Why",
        "-" * 100,
    ]
    for i, m in enumerate(picks, 1):
        new = " NEW" if previous and m.ticker not in previous else ""
        lines.append(
            f"{i:>2}  {m.ticker:<9}{m.price:>10.2f}{m.score:>7.1f}{m.mom_12_1:>8.0%}"
            f"{m.mom_3m:>7.0%}{m.volatility:>6.0%}{m.rsi:>5.0f}  "
            f"{'; '.join(m.reasons)}{new}"
        )
    return "\n".join(lines)


def append_history(path: Path, when: dt.datetime, picks: list[Metrics]) -> None:
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "rank", "ticker", "price", "score", "reasons"])
        for i, m in enumerate(picks, 1):
            w.writerow([when.isoformat(timespec="seconds"), i, m.ticker,
                        f"{m.price:.2f}", f"{m.score:.1f}", "; ".join(m.reasons)])


def run_once(
    tickers: list[str],
    top: int,
    history: Path | None,
    previous: set[str],
    fetch: Callable[[list[str]], pd.DataFrame] = fetch_closes,
) -> set[str]:
    now = dt.datetime.now()
    closes = fetch(tickers)
    if closes.empty:
        print(f"[{now:%Y-%m-%d %H:%M}] Could not download any price data; will retry.")
        return previous
    picks, skipped = suggest(closes, top)
    missing = sorted(set(tickers) - set(map(str, closes.columns)))

    print(f"\n=== Buy candidates {now:%Y-%m-%d %H:%M} ({len(closes.columns)} stocks screened) ===")
    print(format_table(picks, previous))
    if skipped or missing:
        print(f"Skipped (not enough data): {', '.join(skipped + missing)}")
    current = {m.ticker for m in picks}
    if previous and previous - current:
        print(f"Dropped out of the list: {', '.join(sorted(previous - current))}")
    print("Not financial advice - do your own research before buying.")

    if history:
        append_history(history, now, picks)
    return current


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST, help="file with one ticker per line")
    p.add_argument("--tickers", nargs="+", help="tickers to screen instead of the watchlist file")
    p.add_argument("--top", type=int, default=10, help="how many suggestions to show (default 10)")
    p.add_argument("--watch", action="store_true", help="keep running and re-check periodically")
    p.add_argument("--interval", type=float, default=60, help="minutes between checks in --watch mode")
    p.add_argument("--history", type=Path, default=DEFAULT_HISTORY, help="CSV log of suggestions")
    p.add_argument("--no-history", action="store_true", help="don't write the CSV log")
    args = p.parse_args(argv)

    tickers = [t.upper() for t in args.tickers] if args.tickers else load_watchlist(args.watchlist)
    if not tickers:
        print("No tickers to screen.", file=sys.stderr)
        return 1
    history = None if args.no_history else args.history

    previous: set[str] = set()
    try:
        while True:
            try:
                previous = run_once(tickers, args.top, history, previous)
            except Exception as e:  # keep the watcher alive through network hiccups
                print(f"Error during screening: {e}", file=sys.stderr)
            if not args.watch:
                return 0
            print(f"Next check in {args.interval:g} min (Ctrl+C to stop)...")
            time.sleep(args.interval * 60)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
