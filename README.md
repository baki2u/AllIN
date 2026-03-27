# AllIN
All in using Zerodha APIs

Python scripts to screen NSE/BSE stocks and manage your account using the [Zerodha Kite Connect API](https://kite.trade/docs/connect/v3/).

## Strategies

| Script / Strategy | Description |
|---|---|
| `gainers_today.py` | Today's top intraday % gainers |
| `gainers_weekly.py` | Top gainers over the past N days (default: 7) |
| `reversal_screener.py` | Stocks reversing after 3+ consecutive losing sessions |
| `strategies.py` → `rsi_oversold_bounce` | RSI(14) crossed back above oversold threshold (~58-62% 5d win rate) |
| `strategies.py` → `volume_surge_up` | Volume ≥ 2× 20-day avg on a positive-close day (~60-65% 3d win rate) |
| `strategies.py` → `breakout_52w_high` | Price within 2% of 52-week high (~63-67% 10d win rate) |
| `strategies.py` → `sma_golden_cross` | 20-day SMA crosses above 50-day SMA (~57-60% 10d win rate) |
| `orb_strategy.py` | Aggressive 15-min Opening Range Breakout with ATR volatility filter |

## Popular Investor Account Views

These scripts use the most commonly accessed Kite Connect API endpoints
among retail investors:

| Script | Kite API used | Description |
|---|---|---|
| `portfolio.py` | `kite.holdings()` | Portfolio holdings with unrealised P&L, day-change, and total summary |
| `positions.py` | `kite.positions()` | Current open positions – intraday (day) and overnight (net) – with live P&L |
| `orders.py` | `kite.orders()` / `kite.trades()` / `kite.get_gtts()` | Today's order book, tradebook, and GTT (Good Till Triggered) orders |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API credentials

```bash
cp .env.example .env
# Edit .env and add your KITE_API_KEY and KITE_API_SECRET
```

Get your API credentials from [developers.kite.trade](https://developers.kite.trade/).

### 3. Obtain an access token (required daily)

```bash
python kite_client.py
```

This opens a browser login page. After logging in, paste the `request_token`
from the redirect URL. Copy the printed `ACCESS_TOKEN` into your `.env` file.

## Usage

### Account views (popular investor endpoints)

```bash
# Portfolio holdings with unrealised P&L
python portfolio.py
python portfolio.py --sort-by pnl          # Sort by P&L
python portfolio.py --sort-by pnl_pct      # Sort by % return
python portfolio.py --sort-by day_change   # Sort by today's change
python portfolio.py --gainers              # Show only profitable holdings
python portfolio.py --losers               # Show only loss-making holdings
python portfolio.py --top 20               # Limit to top 20

# Open positions with live P&L
python positions.py                        # Intraday + overnight
python positions.py --type day             # Intraday only
python positions.py --type net             # Overnight only
python positions.py --open-only            # Skip fully-closed positions

# Orders, trades, and GTT orders
python orders.py                           # Show everything
python orders.py --orders                  # Today's order book
python orders.py --trades                  # Today's tradebook
python orders.py --gtts                    # GTT orders
python orders.py --status OPEN             # Filter orders by status
python orders.py --gtts --status active    # Active GTTs only
```

### Screening strategies

```bash
# Run all screening strategies
python screener.py

# Run specific strategies
python screener.py gainers-today reversal
python screener.py rsi-bounce volume-surge
python screener.py --top 10 all
```

### Mix account views and strategies in one command

```bash
python screener.py portfolio positions gainers-today
python screener.py orders rsi-bounce volume-surge
```

### Individual scripts

```bash
# Today's gainers
python gainers_today.py --top 20 --min-price 50

# Weekly gainers (past 5 trading days)
python gainers_weekly.py --lookback 5 --top 15

# Reversal screener (4+ day losing streak, with volume confirmation)
python reversal_screener.py --min-loss-days 4 --confirm-volume --confirm-rsi
```

### ORB (Opening Range Breakout) backtest

```bash
# Backtest RELIANCE over 2024 with default ATR filter (1×)
python orb_strategy.py RELIANCE 2024-01-01 2024-12-31

# Stricter volatility filter – only trade high-ATR days
python orb_strategy.py RELIANCE 2024-01-01 2024-12-31 --atr-multiplier 1.5

# Disable ATR filter to see raw ORB performance
python orb_strategy.py NIFTY50 2024-01-01 2024-12-31 --no-atr-filter

# Custom target and stop-loss
python orb_strategy.py INFY 2024-01-01 2024-12-31 --target-pct 0.015 --sl-pct 0.007

# Show from screener.py
python screener.py orb-backtest
```

### Available commands for `screener.py`

```
Screening strategies:
  gainers-today   – Today's top % gainers
  gainers-weekly  – Past N-day top % gainers
  reversal        – Reversal after consecutive losses
  rsi-bounce      – RSI oversold bounce
  volume-surge    – Volume surge + positive close
  breakout-52w    – 52-week high breakout
  golden-cross    – 20-SMA crosses above 50-SMA
  all             – Run every strategy (default)

Account views:
  portfolio       – Holdings with unrealised P&L
  positions       – Open positions with live P&L
  orders          – Order book, tradebook, and GTT orders

Backtests (show usage / delegate to standalone script):
  orb-backtest    – Aggressive 15-min ORB backtest (see orb_strategy.py)
```

## Common Options

| Option | Default | Description |
|---|---|---|
| `--top N` | 20 | Number of results per strategy |
| `--min-price ₹` | 10 | Minimum stock price filter |
| `--min-volume N` | 100000 | Minimum daily volume filter |
| `--exchange` | NSE | Exchange (NSE or BSE) |
| `--lookback N` | 7 | Days to look back for weekly gainers |
| `--min-loss-days N` | 3 | Minimum consecutive losses for reversal scan |
| `--confirm-volume` | off | Require volume surge on reversal day |
| `--confirm-rsi` | off | Require RSI was oversold before reversal |
| `--rsi-threshold N` | 35 | RSI oversold threshold |
| `--vol-surge N` | 2.0 | Volume surge multiplier (× 20-day avg) |
| `--proximity-pct N` | 2.0 | % below 52-week high to qualify as breakout |

## Project Structure

```
AllIN/
├── config.py              # API credentials & strategy parameters
├── kite_client.py         # Authentication helper
├── data_fetcher.py        # Kite API data utilities & technical indicators
├── portfolio.py           # Holdings viewer with P&L (kite.holdings)
├── positions.py           # Open positions viewer (kite.positions)
├── orders.py              # Order book, tradebook & GTT orders
├── gainers_today.py       # Today's top gainers
├── gainers_weekly.py      # Weekly top gainers
├── reversal_screener.py   # Reversal after multi-day losing streak
├── strategies.py          # RSI bounce, volume surge, 52w breakout, golden cross
├── orb_strategy.py        # Aggressive 15-min ORB backtest with ATR volatility filter
├── screener.py            # Combined screener + account views entry point
├── requirements.txt
└── .env.example
```

## Disclaimer

These scripts are for educational and informational purposes only. Past
performance does not guarantee future returns. Always do your own due diligence
before making investment decisions.
