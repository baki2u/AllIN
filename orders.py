"""
orders.py – View today's orders, trades, and GTT (Good Till Triggered) orders.

Three of the most popular Kite Connect investor endpoints:

  kite.orders()     – All orders placed today with their current status.
  kite.trades()     – Confirmed trades / executions for today (tradebook).
  kite.get_gtts()   – GTT orders (set-and-forget limit triggers), extremely
                      popular with long-term Zerodha investors who want to
                      buy/sell at a target price without active monitoring.

Usage:
  python orders.py               # Show today's orders + trades + GTTs
  python orders.py --orders      # Today's order book only
  python orders.py --trades      # Today's tradebook only
  python orders.py --gtts        # GTT orders only
  python orders.py --status OPEN # Filter orders by status
"""

import argparse
import sys
from datetime import date

import pandas as pd
from tabulate import tabulate

from kite_client import get_kite_client

# Zerodha order statuses
ORDER_STATUSES = [
    "COMPLETE", "REJECTED", "CANCELLED", "OPEN",
    "PENDING", "TRIGGER PENDING",
]

# GTT order statuses
GTT_STATUSES = ["active", "triggered", "disabled", "expired", "cancelled", "rejected", "deleted"]


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def get_orders(kite) -> pd.DataFrame:
    """
    Fetch today's orders using ``kite.orders()``.

    Returns:
        DataFrame with order details including status, product, and price info.
    """
    orders = kite.orders()
    if not orders:
        return pd.DataFrame()

    rows = []
    for o in orders:
        rows.append(
            {
                "order_id": o.get("order_id", ""),
                "time": str(o.get("order_timestamp", ""))[:19],
                "symbol": o.get("tradingsymbol", ""),
                "exchange": o.get("exchange", ""),
                "type": o.get("transaction_type", ""),
                "order_type": o.get("order_type", ""),
                "product": o.get("product", ""),
                "qty": o.get("quantity", 0),
                "filled_qty": o.get("filled_quantity", 0),
                "price": o.get("price", 0),
                "avg_price": o.get("average_price", 0),
                "trigger_price": o.get("trigger_price", 0),
                "status": o.get("status", ""),
                "status_message": o.get("status_message", ""),
            }
        )
    return pd.DataFrame(rows)


def print_orders(df: pd.DataFrame, status_filter: str = None) -> None:
    """Pretty-print the order book."""
    if df.empty:
        print("No orders found for today.")
        return

    if status_filter:
        df = df[df["status"].str.upper() == status_filter.upper()]
        if df.empty:
            print(f"No orders with status '{status_filter}' found.")
            return

    display = df.rename(
        columns={
            "order_id": "Order ID",
            "time": "Time",
            "symbol": "Symbol",
            "exchange": "Exch",
            "type": "B/S",
            "order_type": "Order Type",
            "product": "Product",
            "qty": "Qty",
            "filled_qty": "Filled",
            "price": "Price (₹)",
            "avg_price": "Avg Price (₹)",
            "trigger_price": "Trigger (₹)",
            "status": "Status",
            "status_message": "Message",
        }
    ).drop(columns=["Order ID", "Message"])

    print(f"\n{'='*90}")
    print(f"  TODAY'S ORDERS  |  {date.today()}")
    print(f"{'='*90}")
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=True, floatfmt=".2f"))
    print(f"\n  Total orders: {len(df)}\n")


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def get_trades(kite) -> pd.DataFrame:
    """
    Fetch today's confirmed trades (tradebook) using ``kite.trades()``.

    Returns:
        DataFrame with execution details (fill price, fill time, quantity).
    """
    trades = kite.trades()
    if not trades:
        return pd.DataFrame()

    rows = []
    for t in trades:
        qty = t.get("quantity", 0)
        fill_price = t.get("average_price", 0)
        rows.append(
            {
                "trade_id": t.get("trade_id", ""),
                "order_id": t.get("order_id", ""),
                "time": str(t.get("fill_timestamp", ""))[:19],
                "symbol": t.get("tradingsymbol", ""),
                "exchange": t.get("exchange", ""),
                "type": t.get("transaction_type", ""),
                "product": t.get("product", ""),
                "qty": qty,
                "fill_price": round(fill_price, 2),
                "turnover": round(qty * fill_price, 2),
            }
        )
    return pd.DataFrame(rows)


def print_trades(df: pd.DataFrame) -> None:
    """Pretty-print the tradebook."""
    if df.empty:
        print("No trades executed today.")
        return

    display = df.rename(
        columns={
            "trade_id": "Trade ID",
            "order_id": "Order ID",
            "time": "Time",
            "symbol": "Symbol",
            "exchange": "Exch",
            "type": "B/S",
            "product": "Product",
            "qty": "Qty",
            "fill_price": "Fill Price (₹)",
            "turnover": "Turnover (₹)",
        }
    ).drop(columns=["Trade ID", "Order ID"])

    total_turnover = df["turnover"].sum()
    print(f"\n{'='*80}")
    print(f"  TODAY'S TRADES (TRADEBOOK)  |  {date.today()}")
    print(f"{'='*80}")
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=True, floatfmt=".2f"))
    print(f"\n  Total trades   : {len(df)}")
    print(f"  Total turnover : ₹{total_turnover:,.2f}\n")


# ---------------------------------------------------------------------------
# GTT Orders
# ---------------------------------------------------------------------------

def get_gtts(kite) -> pd.DataFrame:
    """
    Fetch all GTT (Good Till Triggered) orders using ``kite.get_gtts()``.

    GTT orders are persistent conditional orders popular with long-term
    investors who want to buy on dips or sell at targets without monitoring.

    Returns:
        DataFrame with GTT order details including trigger price and status.
    """
    gtts = kite.get_gtts()
    if not gtts:
        return pd.DataFrame()

    rows = []
    for g in gtts:
        condition = g.get("condition", {})
        orders_list = g.get("orders", [{}])
        first_order = orders_list[0] if orders_list else {}

        trigger_values = condition.get("trigger_values", [])
        trigger_str = ", ".join(str(round(t, 2)) for t in trigger_values)

        rows.append(
            {
                "gtt_id": g.get("id", ""),
                "created": str(g.get("created_at", ""))[:10],
                "expires": str(g.get("expires_at", ""))[:10],
                "symbol": condition.get("tradingsymbol", ""),
                "exchange": condition.get("exchange", ""),
                "trigger_type": g.get("type", ""),
                "last_price": round(condition.get("last_price", 0), 2),
                "trigger_price": trigger_str,
                "order_type": first_order.get("order_type", ""),
                "type": first_order.get("transaction_type", ""),
                "qty": first_order.get("quantity", 0),
                "limit_price": round(first_order.get("price", 0), 2),
                "status": g.get("status", ""),
            }
        )
    return pd.DataFrame(rows)


def print_gtts(df: pd.DataFrame, status_filter: str = None) -> None:
    """Pretty-print GTT orders."""
    if df.empty:
        print("No GTT orders found.")
        return

    if status_filter:
        df = df[df["status"].str.lower() == status_filter.lower()]
        if df.empty:
            print(f"No GTT orders with status '{status_filter}' found.")
            return

    display = df.rename(
        columns={
            "gtt_id": "GTT ID",
            "created": "Created",
            "expires": "Expires",
            "symbol": "Symbol",
            "exchange": "Exch",
            "trigger_type": "Trigger Type",
            "last_price": "LTP (₹)",
            "trigger_price": "Trigger Price(s) (₹)",
            "order_type": "Order Type",
            "type": "B/S",
            "qty": "Qty",
            "limit_price": "Limit Price (₹)",
            "status": "Status",
        }
    ).drop(columns=["GTT ID", "Created", "Expires"])

    status_counts = df["status"].value_counts().to_dict()
    print(f"\n{'='*90}")
    print(f"  GTT (GOOD TILL TRIGGERED) ORDERS")
    print(f"{'='*90}")
    print(tabulate(display, headers="keys", tablefmt="simple", showindex=True))
    print(f"\n  Total GTTs: {len(df)}")
    for s, cnt in status_counts.items():
        print(f"    {s}: {cnt}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Zerodha orders, trades, and GTT orders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--orders", action="store_true", help="Show today's order book")
    parser.add_argument("--trades", action="store_true", help="Show today's tradebook")
    parser.add_argument("--gtts", action="store_true", help="Show GTT orders")
    parser.add_argument(
        "--status",
        default=None,
        help=(
            "Filter orders by status (e.g. OPEN, COMPLETE, REJECTED). "
            "For GTTs: active, triggered, expired, etc."
        ),
    )
    args = parser.parse_args()

    # Default: show everything
    show_all = not (args.orders or args.trades or args.gtts)

    try:
        kite = get_kite_client()

        if show_all or args.orders:
            df = get_orders(kite)
            print_orders(df, status_filter=args.status)

        if show_all or args.trades:
            df = get_trades(kite)
            print_trades(df)

        if show_all or args.gtts:
            df = get_gtts(kite)
            print_gtts(df, status_filter=args.status)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
