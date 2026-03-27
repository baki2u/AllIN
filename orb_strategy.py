"""
orb_strategy.py – Aggressive 15-Minute Opening Range Breakout (ORB) Strategy
           implemented with the Zerodha Kite Connect API.

Strategy rules
--------------
* Opening Range  : First ``ORB_WINDOW_MIN`` minutes of the session (09:15–09:30 IST).
* Long  entry    : Candle high crosses above ORB high  → enter at ORB high.
* Short entry    : Candle low  crosses below ORB low   → enter at ORB low.
* Target         : ``ORB_TARGET_PCT``   (default 1 %) from entry.
* Stop loss      : ``ORB_STOP_LOSS_PCT`` (default 0.5 %) from entry.
* EOD square-off : Remaining open position closed at the last close of the day.

Volatility Filter (ATR)
-----------------------
Before scanning intraday candles, the strategy checks the *daily* ATR for the
instrument.  A trade is only considered on days where:

    today's ATR  >=  ORB_ATR_MIN_MULTIPLIER × rolling-average ATR

This filters out low-volatility "choppy" days where ORB breakouts tend to fail,
aiming to increase the win rate from the raw ~40 % baseline.

Usage
-----
    # Backtest a single instrument over a date range
    from orb_strategy import run_orb_backtest
    stats = run_orb_backtest("RELIANCE", "2024-01-01", "2024-12-31")
    print(stats)

    # Backtest with a custom ATR multiplier (stricter filter)
    stats = run_orb_backtest("NIFTY 50", "2024-01-01", "2024-12-31",
                              atr_min_multiplier=1.5)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd

import config
from data_fetcher import compute_atr, fetch_historical, get_instruments
from kite_client import get_kite_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal backtest engine
# ---------------------------------------------------------------------------

def _backtest_orb(
    df_15min: pd.DataFrame,
    orb_window_min: int,
    target_pct: float,
    stop_loss_pct: float,
    slippage_comm: float,
    atr_filter_dates: Optional[set],
) -> pd.DataFrame:
    """
    Core ORB backtest on a DataFrame of 15-minute candles.

    Args:
        df_15min:         15-minute OHLCV DataFrame with a DatetimeIndex.
        orb_window_min:   Length of the opening range in minutes (e.g. 15).
        target_pct:       Profit target as a fraction (e.g. 0.01 = 1 %).
        stop_loss_pct:    Stop loss as a fraction (e.g. 0.005 = 0.5 %).
        slippage_comm:    One-way cost fraction deducted from each trade.
        atr_filter_dates: Set of ``date`` objects that pass the ATR filter.
                          Pass ``None`` to disable the filter entirely.

    Returns:
        DataFrame with one row per trade containing date, type, entry, exit,
        reason, raw_return, and net_return columns.
    """
    results = []

    df_15min = df_15min.copy()
    df_15min["_date"] = df_15min.index.date
    unique_dates = df_15min["_date"].unique()

    for curr_date in unique_dates:
        # --- Volatility filter ---
        if atr_filter_dates is not None and curr_date not in atr_filter_dates:
            logger.debug("Skipping %s – failed ATR volatility filter", curr_date)
            continue

        day_data = df_15min[df_15min["_date"] == curr_date]

        # Need at least 2 candles: one to form the ORB, one to trade
        if len(day_data) < 2:
            continue

        # --- STEP 1: Define ORB (first orb_window_min minutes) ---
        start_time = day_data.index[0]
        orb_end_time = start_time + pd.Timedelta(minutes=orb_window_min)

        # Use strict less-than so the candle opening at orb_end_time is not
        # included in the range (it belongs to the trading session, not the ORB).
        orb_candles = day_data[day_data.index < orb_end_time]
        if orb_candles.empty:
            continue

        orb_high = orb_candles["high"].max()
        orb_low = orb_candles["low"].min()

        # --- STEP 2: Scan for breakout (candles after ORB window) ---
        trading_session = day_data.loc[orb_end_time:]
        if trading_session.empty:
            continue

        entry_price: float = 0.0
        exit_price: float = 0.0
        target_price: float = 0.0
        sl_price: float = 0.0
        position: Optional[str] = None  # 'LONG' or 'SHORT'
        reason: str = ""

        for _, row in trading_session.iterrows():
            if position is None:
                # Check for long breakout
                if row["high"] > orb_high:
                    position = "LONG"
                    entry_price = orb_high
                    target_price = entry_price * (1 + target_pct)
                    sl_price = entry_price * (1 - stop_loss_pct)
                # Check for short breakout
                elif row["low"] < orb_low:
                    position = "SHORT"
                    entry_price = orb_low
                    target_price = entry_price * (1 - target_pct)
                    sl_price = entry_price * (1 + stop_loss_pct)
            else:
                if position == "LONG":
                    if row["high"] >= target_price:
                        exit_price = target_price
                        reason = "TARGET"
                        break
                    elif row["low"] <= sl_price:
                        exit_price = sl_price
                        reason = "STOP_LOSS"
                        break
                elif position == "SHORT":
                    if row["low"] <= target_price:
                        exit_price = target_price
                        reason = "TARGET"
                        break
                    elif row["high"] >= sl_price:
                        exit_price = sl_price
                        reason = "STOP_LOSS"
                        break

        # --- STEP 3: EOD square-off if still in position ---
        if position and exit_price == 0.0:
            exit_price = trading_session.iloc[-1]["close"]
            reason = "EOD_EXIT"

        # --- STEP 4: Record result ---
        if position and exit_price != 0.0:
            raw_pnl = (exit_price - entry_price) / entry_price
            if position == "SHORT":
                raw_pnl = -raw_pnl

            # Deduct slippage & brokerage on every trade (brokerage + STT + slippage cost)
            net_pnl = raw_pnl - slippage_comm

            results.append(
                {
                    "date": curr_date,
                    "type": position,
                    "entry": round(entry_price, 4),
                    "exit": round(exit_price, 4),
                    "reason": reason,
                    "raw_return": round(raw_pnl, 6),
                    "net_return": round(net_pnl, 6),
                }
            )

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# ATR filter helper
# ---------------------------------------------------------------------------

def _compute_atr_filter_dates(
    df_daily: pd.DataFrame,
    atr_period: int,
    atr_min_multiplier: float,
) -> set:
    """
    Return the set of dates whose ATR is >= atr_min_multiplier × rolling-average ATR.

    The rolling average uses a window of ``atr_period * 2`` days so the
    multiplier comparison is stable.

    Args:
        df_daily:           Daily OHLCV DataFrame (DatetimeIndex or 'date' column).
        atr_period:         Wilder ATR period (default 14).
        atr_min_multiplier: Minimum ratio of today's ATR to its rolling mean.

    Returns:
        Set of ``datetime.date`` objects that pass the filter.
    """
    if df_daily.empty:
        return set()

    df = df_daily.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

    df["atr"] = compute_atr(df, period=atr_period)
    avg_window = atr_period * 2
    df["atr_avg"] = df["atr"].rolling(window=avg_window).mean()
    df.dropna(subset=["atr", "atr_avg"], inplace=True)

    mask = df["atr"] >= df["atr_avg"] * atr_min_multiplier
    return set(df.index[mask].date)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_orb_backtest(
    symbol: str,
    from_date: str | date,
    to_date: str | date,
    exchange: str = config.EXCHANGE,
    orb_window_min: int = config.ORB_WINDOW_MIN,
    target_pct: float = config.ORB_TARGET_PCT,
    stop_loss_pct: float = config.ORB_STOP_LOSS_PCT,
    slippage_comm: float = config.ORB_SLIPPAGE_COMM,
    atr_period: int = config.ORB_ATR_PERIOD,
    atr_min_multiplier: float = config.ORB_ATR_MIN_MULTIPLIER,
    use_atr_filter: bool = True,
) -> pd.DataFrame:
    """
    Run the Aggressive ORB backtest for *symbol* over the given date range
    using live Zerodha Kite Connect historical data.

    Args:
        symbol:             NSE/BSE trading symbol, e.g. ``"RELIANCE"``.
        from_date:          Start date (``"YYYY-MM-DD"`` string or ``date``).
        to_date:            End date   (``"YYYY-MM-DD"`` string or ``date``).
        exchange:           ``"NSE"`` or ``"BSE"`` (default from config).
        orb_window_min:     Opening range window in minutes (default 15).
        target_pct:         Profit-target fraction (default 1 %).
        stop_loss_pct:      Stop-loss fraction (default 0.5 %).
        slippage_comm:      Round-trip brokerage + slippage fraction (default 0.05 %).
        atr_period:         ATR look-back period for volatility filter (default 14).
        atr_min_multiplier: Minimum ratio of daily ATR to rolling-average ATR.
                            Set to ``1.0`` to trade only above-average volatility days.
                            Set to ``0.0`` (or ``use_atr_filter=False``) to disable.
        use_atr_filter:     Whether to apply the ATR volatility filter.

    Returns:
        DataFrame with columns:
            date, type, entry, exit, reason, raw_return, net_return

        Summary statistics are printed to stdout.

    Raises:
        ValueError: If the symbol is not found in the instrument list.
    """
    # Normalise dates
    if isinstance(from_date, str):
        from_date = date.fromisoformat(from_date)
    if isinstance(to_date, str):
        to_date = date.fromisoformat(to_date)

    kite = get_kite_client()

    # Resolve instrument token
    instruments_df = get_instruments(kite, exchange)
    match = instruments_df[instruments_df["tradingsymbol"] == symbol]
    if match.empty:
        raise ValueError(
            f"Symbol '{symbol}' not found on {exchange}. "
            "Check the symbol name or exchange parameter."
        )
    token = int(match.iloc[0]["instrument_token"])

    # --- Fetch 15-minute intraday candles ---
    logger.info("Fetching 15-minute data for %s (%s – %s)…", symbol, from_date, to_date)
    df_15min = fetch_historical(kite, token, from_date, to_date, interval="15minute")
    if df_15min.empty:
        logger.warning("No 15-minute data returned for %s.", symbol)
        return pd.DataFrame()

    # Set DatetimeIndex if not already set
    if "date" in df_15min.columns:
        df_15min = df_15min.set_index("date")
    df_15min.index = pd.to_datetime(df_15min.index)

    # --- Build ATR volatility filter from daily candles ---
    atr_filter_dates: Optional[set] = None
    if use_atr_filter and atr_min_multiplier > 0:
        # Fetch slightly more daily history for ATR warm-up
        daily_from = from_date - timedelta(days=atr_period * 3)
        logger.info("Fetching daily data for ATR filter…")
        df_daily = fetch_historical(kite, token, daily_from, to_date, interval="day")
        if not df_daily.empty:
            if "date" in df_daily.columns:
                df_daily = df_daily.set_index("date")
            df_daily.index = pd.to_datetime(df_daily.index)
            atr_filter_dates = _compute_atr_filter_dates(
                df_daily, atr_period, atr_min_multiplier
            )
            logger.info(
                "ATR filter: %d / %d days pass (multiplier ≥ %.2f×)",
                len(atr_filter_dates),
                len(df_daily),
                atr_min_multiplier,
            )

    # --- Run backtest ---
    stats = _backtest_orb(
        df_15min,
        orb_window_min=orb_window_min,
        target_pct=target_pct,
        stop_loss_pct=stop_loss_pct,
        slippage_comm=slippage_comm,
        atr_filter_dates=atr_filter_dates,
    )

    # --- Print summary ---
    _print_summary(stats, symbol)
    return stats


def _print_summary(stats: pd.DataFrame, symbol: str) -> None:
    """Print a formatted summary of the backtest results."""
    if stats.empty:
        print(f"\n[ORB] {symbol}: No trades triggered in the backtest period.")
        return

    total = len(stats)
    winners = (stats["net_return"] > 0).sum()
    win_rate = winners / total
    raw_cum = stats["raw_return"].sum() * 100
    net_cum = stats["net_return"].sum() * 100

    reason_counts = stats["reason"].value_counts().to_dict()

    print(f"\n{'='*55}")
    print(f"  ORB Backtest Results – {symbol}")
    print(f"{'='*55}")
    print(f"  Total Trades       : {total}")
    print(f"  Winners            : {winners}  ({win_rate:.1%})")
    print(f"  Losers             : {total - winners}")
    print(f"  Exit Breakdown     : {reason_counts}")
    print(f"  Raw  Cum. Return   : {raw_cum:+.2f}%")
    print(f"  Net  Cum. Return   : {net_cum:+.2f}%  (after slippage/costs)")
    print(f"  Avg Raw  per Trade : {stats['raw_return'].mean()*100:+.3f}%")
    print(f"  Avg Net  per Trade : {stats['net_return'].mean()*100:+.3f}%")
    print(f"{'='*55}\n")
    print("Sample trades (first 10):")
    print(stats.head(10).to_string(index=False))
    print()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Aggressive 15-min ORB backtest via Zerodha Kite Connect."
    )
    parser.add_argument("symbol", help="NSE trading symbol, e.g. RELIANCE")
    parser.add_argument("from_date", help="Start date YYYY-MM-DD")
    parser.add_argument("to_date", help="End date YYYY-MM-DD")
    parser.add_argument(
        "--exchange", default=config.EXCHANGE, help="Exchange (default: NSE)"
    )
    parser.add_argument(
        "--atr-multiplier",
        type=float,
        default=config.ORB_ATR_MIN_MULTIPLIER,
        dest="atr_multiplier",
        help=(
            "Minimum ATR / avg-ATR ratio to allow a trade (default: "
            f"{config.ORB_ATR_MIN_MULTIPLIER}). "
            "Increase to 1.2–1.5 for a stricter volatility filter."
        ),
    )
    parser.add_argument(
        "--no-atr-filter",
        action="store_true",
        dest="no_atr_filter",
        help="Disable the ATR volatility filter entirely.",
    )
    parser.add_argument(
        "--target-pct",
        type=float,
        default=config.ORB_TARGET_PCT,
        dest="target_pct",
        help=f"Profit target fraction (default: {config.ORB_TARGET_PCT})",
    )
    parser.add_argument(
        "--sl-pct",
        type=float,
        default=config.ORB_STOP_LOSS_PCT,
        dest="sl_pct",
        help=f"Stop-loss fraction (default: {config.ORB_STOP_LOSS_PCT})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    run_orb_backtest(
        symbol=args.symbol,
        from_date=args.from_date,
        to_date=args.to_date,
        exchange=args.exchange,
        target_pct=args.target_pct,
        stop_loss_pct=args.sl_pct,
        atr_min_multiplier=args.atr_multiplier,
        use_atr_filter=not args.no_atr_filter,
    )
