"""
Data fetching utilities for Zerodha Kite Connect API.

Provides helpers to:
  - Load and cache the NSE/BSE instruments list
  - Fetch OHLCV historical data for a list of instruments
  - Compute common technical indicators (RSI, moving averages, volume averages)
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from kiteconnect import KiteConnect

import config


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

_instruments_cache: Optional[pd.DataFrame] = None


def get_instruments(kite: KiteConnect, exchange: str = config.EXCHANGE) -> pd.DataFrame:
    """
    Return a DataFrame of all tradeable equity instruments on *exchange*.

    Columns include: tradingsymbol, instrument_token, name, last_price, expiry,
    strike, tick_size, lot_size, instrument_type, segment, exchange.

    Results are cached in memory for the lifetime of the process.
    """
    global _instruments_cache
    if _instruments_cache is not None:
        return _instruments_cache

    instruments = kite.instruments(exchange)
    df = pd.DataFrame(instruments)
    # Keep only equity instruments (EQ segment)
    df = df[df["instrument_type"] == "EQ"].copy()
    df.reset_index(drop=True, inplace=True)
    _instruments_cache = df
    return df


# ---------------------------------------------------------------------------
# Historical data
# ---------------------------------------------------------------------------

def fetch_historical(
    kite: KiteConnect,
    instrument_token: int,
    from_date: date,
    to_date: date,
    interval: str = "day",
) -> pd.DataFrame:
    """
    Fetch OHLCV candles for a single instrument.

    Args:
        kite:             Authenticated KiteConnect instance.
        instrument_token: Kite instrument token.
        from_date:        Start date (inclusive).
        to_date:          End date (inclusive).
        interval:         Candle interval – 'day', '60minute', '30minute', etc.

    Returns:
        DataFrame with columns [date, open, high, low, close, volume].
        Returns an empty DataFrame on error.
    """
    try:
        records = kite.historical_data(
            instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
        )
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame()


def fetch_bulk_historical(
    kite: KiteConnect,
    tokens: List[int],
    from_date: date,
    to_date: date,
    interval: str = "day",
    delay_seconds: float = 0.35,
) -> Dict[int, pd.DataFrame]:
    """
    Fetch historical data for multiple instruments, respecting Kite API rate limits.

    Args:
        kite:           Authenticated KiteConnect instance.
        tokens:         List of instrument tokens.
        from_date:      Start date.
        to_date:        End date.
        interval:       Candle interval.
        delay_seconds:  Sleep between requests to avoid rate-limit (default 0.35 s).

    Returns:
        Dict mapping instrument_token -> DataFrame.
    """
    results: Dict[int, pd.DataFrame] = {}
    for token in tokens:
        df = fetch_historical(kite, token, from_date, to_date, interval)
        results[token] = df
        time.sleep(delay_seconds)
    return results


# ---------------------------------------------------------------------------
# Quote / LTP helpers
# ---------------------------------------------------------------------------

def get_quotes(
    kite: KiteConnect, symbols: List[str], exchange: str = config.EXCHANGE
) -> Dict[str, dict]:
    """
    Fetch full quote data for a list of trading symbols.

    Args:
        kite:     Authenticated KiteConnect instance.
        symbols:  List of trading symbols, e.g. ['RELIANCE', 'TCS'].
        exchange: Exchange prefix, default from config.

    Returns:
        Dict of {exchange:symbol -> quote dict}.
    """
    instrument_ids = [f"{exchange}:{sym}" for sym in symbols]
    # Kite quote() accepts at most 500 instruments at a time
    all_quotes: Dict[str, dict] = {}
    chunk_size = 500
    for i in range(0, len(instrument_ids), chunk_size):
        chunk = instrument_ids[i : i + chunk_size]
        try:
            quotes = kite.quote(chunk)
            all_quotes.update(quotes)
        except Exception:
            pass
    return all_quotes


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

def compute_rsi(series: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """
    Compute Wilder's RSI for a price series.

    Args:
        series: Closing price series (oldest first).
        period: Look-back period (default from config).

    Returns:
        RSI values as a Series (same index).
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period).mean()


def compute_volume_avg(volume: pd.Series, period: int = 20) -> pd.Series:
    """Rolling average volume."""
    return volume.rolling(window=period).mean()


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute Average True Range (ATR) using Wilder's smoothing.

    Args:
        df:     DataFrame with columns 'high', 'low', 'close'.
        period: Look-back period (default 14).

    Returns:
        ATR values as a Series (same index as *df*).
    """
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.ewm(com=period - 1, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Convenience: enrich a candle DataFrame with indicators
# ---------------------------------------------------------------------------

def enrich_with_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add RSI, 20-day SMA, and 20-day average volume columns to a candle DataFrame.

    Input DataFrame must have columns: close, volume.
    """
    if df.empty:
        return df
    df = df.copy()
    df["rsi"] = compute_rsi(df["close"])
    df["sma20"] = compute_sma(df["close"], 20)
    df["vol_avg20"] = compute_volume_avg(df["volume"], 20)
    return df


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def trading_days_ago(n: int, from_dt: Optional[date] = None) -> date:
    """
    Return the date *n* calendar days before *from_dt* (default: today).
    Not exchange-calendar-aware; used only as a conservative lookback.
    """
    base = from_dt or date.today()
    # Use ~1.5x to account for weekends/holidays; clamp to calendar days
    return base - timedelta(days=int(n * 1.5) + 5)
