# AllIN
All in using Zerodha APIs

Python scripts to screen NSE/BSE stocks using the [Zerodha Kite Connect API](https://kite.trade/docs/connect/v3/).

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

### Run all strategies at once

```bash
python screener.py
```

### Run specific strategies

```bash
python screener.py gainers-today reversal
python screener.py rsi-bounce volume-surge
python screener.py --top 10 all
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

### Available strategy names for `screener.py`

```
gainers-today   – Today's top % gainers
gainers-weekly  – Past N-day top % gainers
reversal        – Reversal after consecutive losses
rsi-bounce      – RSI oversold bounce
volume-surge    – Volume surge + positive close
breakout-52w    – 52-week high breakout
golden-cross    – 20-SMA crosses above 50-SMA
all             – Run every strategy (default)
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
├── gainers_today.py       # Today's top gainers
├── gainers_weekly.py      # Weekly top gainers
├── reversal_screener.py   # Reversal after multi-day losing streak
├── strategies.py          # RSI bounce, volume surge, 52w breakout, golden cross
├── screener.py            # Combined screener entry point
├── requirements.txt
└── .env.example
```

## Disclaimer

These scripts are for educational and informational purposes only. Past
performance does not guarantee future returns. Always do your own due diligence
before making investment decisions.
