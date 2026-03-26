"""
positions.py – View current open positions (intraday and overnight) with P&L.

Uses ``kite.positions()`` which returns two sets of positions:
  - 'day'  : Positions opened and closed (or still open) today (intraday).
  - 'net'  : Net overnight positions carried from previous sessions.

This is one of the most frequently polled Kite Connect endpoints by active
traders to monitor their real-time P&L during market hours.

Usage:
  python positions.py              # Show all open positions
  python positions.py --type day   # Intraday positions only
  python positions.py --type net   # Overnight (net) positions only
  python positions.py --open-only  # Skip fully-closed positions (net qty = 0)
"""

import argparse
import sys
from datetime import date

import pandas as pd
from tabulate import tabulate

from kite_client import get_kite_client


def get_positions(kite, position_type: str = "all") -> pd.DataFrame:
    """
    Fetch open positions from Zerodha.

    Args:
        kite:           Authenticated KiteConnect instance.
        position_type:  'day', 'net', or 'all' (default).

    Returns:
        DataFrame with columns:
        type, symbol, exchange, product, qty, avg_price, ltp,
        pnl, day_pnl, value
    """
    data = kite.positions()

    all_positions = []
    for ptype in ("day", "net"):
        if position_type not in ("all", ptype):
            continue
        for p in data.get(ptype, []):
            qty = p.get("quantity", 0)
            avg_price = p.get("average_price", 0)
            ltp = p.get("last_price", 0)
            pnl = p.get("pnl", 0)
            day_pnl = p.get("day_pnl", pnl if ptype == "day" else 0)
            value = round(ltp * abs(qty), 2)
            unrealised_pnl = round(pnl, 2)

            all_positions.append(
                {
                    "type": ptype,
                    "symbol": p.get("tradingsymbol", ""),
                    "exchange": p.get("exchange", ""),
                    "product": p.get("product", ""),
                    "qty": qty,
                    "avg_price": round(avg_price, 2),
                    "ltp": round(ltp, 2),
                    "value": value,
                    "pnl": unrealised_pnl,
                    "day_pnl": round(day_pnl, 2),
                }
            )

    if not all_positions:
        return pd.DataFrame()
    return pd.DataFrame(all_positions)


def print_positions(df: pd.DataFrame, open_only: bool = False) -> None:
    """Pretty-print positions table with P&L summary."""
    if df.empty:
        print("No positions found.")
        return

    if open_only:
        df = df[df["qty"] != 0]

    if df.empty:
        print("No open positions found.")
        return

    for ptype, group in df.groupby("type"):
        label = "INTRADAY (DAY)" if ptype == "day" else "OVERNIGHT (NET)"
        display = group.rename(
            columns={
                "type": "Type",
                "symbol": "Symbol",
                "exchange": "Exch",
                "product": "Product",
                "qty": "Qty",
                "avg_price": "Avg Price (₹)",
                "ltp": "LTP (₹)",
                "value": "Value (₹)",
                "pnl": "P&L (₹)",
                "day_pnl": "Day P&L (₹)",
            }
        ).drop(columns=["Type"])

        total_pnl = group["pnl"].sum()
        total_day_pnl = group["day_pnl"].sum()

        print(f"\n{'='*70}")
        print(f"  {label}  |  {date.today()}")
        print(f"{'='*70}")
        print(
            tabulate(
                display,
                headers="keys",
                tablefmt="simple",
                showindex=True,
                floatfmt=".2f",
            )
        )
        sign = "+" if total_pnl >= 0 else ""
        day_sign = "+" if total_day_pnl >= 0 else ""
        print(f"\n  Positions   : {len(group)}")
        print(f"  Total P&L   : {sign}₹{total_pnl:,.2f}")
        print(f"  Today's P&L : {day_sign}₹{total_day_pnl:,.2f}")
        print(f"{'='*70}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Zerodha open positions with live P&L.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--type",
        dest="position_type",
        default="all",
        choices=["all", "day", "net"],
        help="Position type to display: all, day (intraday), net (overnight) (default: all)",
    )
    parser.add_argument(
        "--open-only",
        action="store_true",
        help="Show only positions with non-zero net quantity",
    )
    args = parser.parse_args()

    try:
        kite = get_kite_client()
        df = get_positions(kite, position_type=args.position_type)
        print_positions(df, open_only=args.open_only)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
