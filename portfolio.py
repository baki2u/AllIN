"""
portfolio.py – View your Zerodha portfolio (holdings) with P&L analysis.

One of the most popular Kite Connect API use-cases: fetch all equity holdings,
compute unrealized P&L, day's change, and display a sorted summary table.

Usage:
  python portfolio.py                        # Show all holdings sorted by value
  python portfolio.py --sort-by pnl          # Sort by unrealized P&L
  python portfolio.py --sort-by pnl_pct      # Sort by % return
  python portfolio.py --sort-by day_change   # Sort by today's change %
  python portfolio.py --top 20               # Show top 20 holdings only
  python portfolio.py --losers               # Show only loss-making holdings
  python portfolio.py --gainers              # Show only profitable holdings
"""

import argparse
import sys
from datetime import date

import pandas as pd
from tabulate import tabulate

import config
from kite_client import get_kite_client


SORT_COLUMNS = {
    "value": "current_value",
    "pnl": "unrealised_pnl",
    "pnl_pct": "pnl_pct",
    "day_change": "day_change_pct",
    "symbol": "symbol",
}


def get_holdings(kite) -> pd.DataFrame:
    """
    Fetch all equity holdings from Zerodha and enrich with P&L metrics.

    Uses ``kite.holdings()`` which returns the long-term portfolio (demat
    holdings), including average buy price, quantity, and current LTP.

    Returns:
        DataFrame with columns:
        symbol, name, qty, avg_price, ltp, current_value,
        unrealised_pnl, pnl_pct, day_change_pct, invested_value
    """
    holdings = kite.holdings()
    if not holdings:
        return pd.DataFrame()

    rows = []
    for h in holdings:
        qty = h.get("quantity", 0)
        t1_qty = h.get("t1_quantity", 0)  # unsettled (T+1) shares
        total_qty = qty + t1_qty
        if total_qty <= 0:
            continue

        avg_price = h.get("average_price", 0)
        ltp = h.get("last_price", 0)
        close = h.get("close_price", ltp)  # previous close for day-change

        invested_value = round(avg_price * total_qty, 2)
        current_value = round(ltp * total_qty, 2)
        unrealised_pnl = round(current_value - invested_value, 2)
        pnl_pct = round((unrealised_pnl / invested_value) * 100, 2) if invested_value else 0.0
        day_change_pct = round(((ltp - close) / close) * 100, 2) if close > 0 else 0.0
        day_pnl = round((ltp - close) * total_qty, 2)

        rows.append(
            {
                "symbol": h.get("tradingsymbol", ""),
                "name": h.get("exchange", ""),
                "qty": total_qty,
                "t1_qty": t1_qty,
                "avg_price": round(avg_price, 2),
                "ltp": round(ltp, 2),
                "invested_value": invested_value,
                "current_value": current_value,
                "unrealised_pnl": unrealised_pnl,
                "pnl_pct": pnl_pct,
                "day_change_pct": day_change_pct,
                "day_pnl": day_pnl,
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def print_holdings(df: pd.DataFrame) -> None:
    """Pretty-print holdings table with portfolio summary footer."""
    if df.empty:
        print("No holdings found in your portfolio.")
        return

    display = df.rename(
        columns={
            "symbol": "Symbol",
            "name": "Exch",
            "qty": "Qty",
            "t1_qty": "T1 Qty",
            "avg_price": "Avg Price (₹)",
            "ltp": "LTP (₹)",
            "invested_value": "Invested (₹)",
            "current_value": "Current (₹)",
            "unrealised_pnl": "Unreal. P&L (₹)",
            "pnl_pct": "P&L %",
            "day_change_pct": "Day Chg %",
            "day_pnl": "Day P&L (₹)",
        }
    )

    total_invested = df["invested_value"].sum()
    total_current = df["current_value"].sum()
    total_pnl = df["unrealised_pnl"].sum()
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
    total_day_pnl = df["day_pnl"].sum()

    print(f"\n{'='*80}")
    print(f"  PORTFOLIO HOLDINGS  |  {date.today()}")
    print(f"{'='*80}")
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=True, floatfmt=".2f"))
    print(f"\n{'─'*80}")
    print(f"  Holdings      : {len(df)}")
    print(f"  Invested      : ₹{total_invested:,.2f}")
    print(f"  Current Value : ₹{total_current:,.2f}")
    sign = "+" if total_pnl >= 0 else ""
    print(f"  Unrealised P&L: {sign}₹{total_pnl:,.2f}  ({sign}{total_pnl_pct:.2f}%)")
    day_sign = "+" if total_day_pnl >= 0 else ""
    print(f"  Today's P&L   : {day_sign}₹{total_day_pnl:,.2f}")
    print(f"{'='*80}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Zerodha portfolio holdings with P&L analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--top", type=int, default=None, help="Show top N holdings only")
    parser.add_argument(
        "--sort-by",
        default="value",
        choices=list(SORT_COLUMNS.keys()),
        help="Sort holdings by: value, pnl, pnl_pct, day_change, symbol (default: value)",
    )
    parser.add_argument(
        "--asc",
        action="store_true",
        help="Sort ascending (default is descending for numeric columns)",
    )
    parser.add_argument("--gainers", action="store_true", help="Show only profitable holdings")
    parser.add_argument("--losers", action="store_true", help="Show only loss-making holdings")
    args = parser.parse_args()

    try:
        kite = get_kite_client()
        df = get_holdings(kite)

        if df.empty:
            print("No holdings found.")
            sys.exit(0)

        # Filter
        if args.gainers:
            df = df[df["unrealised_pnl"] > 0]
        elif args.losers:
            df = df[df["unrealised_pnl"] < 0]

        # Sort
        sort_col = SORT_COLUMNS[args.sort_by]
        if args.sort_by == "symbol":
            ascending = True  # symbol always ascending by default
        else:
            ascending = args.asc  # numeric: default descending unless --asc flag
        df = df.sort_values(sort_col, ascending=ascending)

        # Top N
        if args.top:
            df = df.head(args.top)

        df.reset_index(drop=True, inplace=True)
        print_holdings(df)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
