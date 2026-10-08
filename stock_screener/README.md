# Stock screener

A small tool that ranks the stocks in your watchlist and suggests buy candidates.
It can run once or keep running in the background and re-check on a timer.

> **Not financial advice.** This tool ranks stocks using past price signals only. It knows
> nothing about valuation, earnings, news, or your own situation. Use it to find stocks
> worth a closer look.

## Setup

```bash
cd stock_screener
uv sync            # or: pip install pandas yfinance
```

## Usage

```bash
uv run screener.py                          # check once, show the top 10
uv run screener.py --watch                  # keep running, re-check every 60 min
uv run screener.py --watch --interval 30 --top 5
uv run screener.py --tickers NOKIA.HE NESTE.HE KNEBV.HE   # one-off custom list
```

Edit `watchlist.txt` to change which stocks are screened. Use Yahoo Finance symbols,
for example `NOKIA.HE` for Helsinki and `SAP.DE` for Frankfurt.

In `--watch` mode, a stock that enters the top list is marked **NEW**, and the output
also lists stocks that dropped out. Every run is added to `history.csv`, so you can
see later how the suggestions performed.

## How the score works

Prices come from Yahoo Finance via `yfinance`: about 14 months of daily data.
Each stock is scored against the rest of your watchlist:

| Signal | Weight | Meaning |
|---|---|---|
| 12-1 month momentum | 30% | Return over the past year, excluding the last month |
| Risk-adjusted momentum | 30% | The momentum above divided by volatility |
| 3 month momentum | 20% | Recent strength |
| Near 52-week high | 20% | Price compared with the 52-week high |

The total is then adjusted:

- **Trend filter:** stocks below their 200-day moving average are never suggested.
- +5 if the 50-day average is above the 200-day average (an uptrend).
- +5 if RSI(14) is 40–55 during an uptrend (a pullback, which can be a better entry point).
- −10 if RSI(14) is above 75 (overbought: the stock is still good, but you may want to wait).

## Tests

```bash
uv run --with pytest pytest -q
```
