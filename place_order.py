"""
place_order.py – Place, modify, and cancel Zerodha orders via Kite Connect.

Supports all order types:
  MARKET  – Execute at best available price (no price needed)
  LIMIT   – Execute only at the specified limit price or better
  SL      – Stop-Loss Limit: triggers at stop price, then executes as limit
  SL-M    – Stop-Loss Market: triggers at stop price, then executes at market

Products:
  CNC     – Cash and Carry (delivery equity, NSE/BSE)
  MIS     – Margin Intraday Square-off (intraday, auto-squared off at 3:20 PM)
  NRML    – Normal (F&O overnight positions)

Validity:
  DAY     – Valid for the current trading session only (default)
  IOC     – Immediate or Cancel (fill instantly or cancel remainder)

Market hours (IST):  Monday–Friday, 09:15–15:30
Pre-open session:    09:00–09:08 (auction orders)

Usage:
  # Regular orders (best available / market price)
  python place_order.py buy RELIANCE 10
  python place_order.py sell TCS 5 --product CNC

  # Limit order
  python place_order.py buy INFY 10 --order-type LIMIT --price 1500

  # Stop-Loss Limit order
  python place_order.py buy HDFCBANK 10 --order-type SL --price 1600 --trigger-price 1595

  # Stop-Loss Market order (no limit price required)
  python place_order.py sell WIPRO 20 --order-type SL-M --trigger-price 400

  # F&O / overnight position
  python place_order.py buy NIFTY24JANFUT 50 --exchange NFO --product NRML

  # Intraday with IOC validity
  python place_order.py buy RELIANCE 10 --product MIS --validity IOC

  # GTT (Good Till Triggered) – persistent conditional order
  python place_order.py gtt buy RELIANCE 10 --trigger-price 2400 --price 2395

  # Modify an existing order
  python place_order.py modify ORDER_ID --price 1510 --quantity 15

  # Cancel an existing order
  python place_order.py cancel ORDER_ID
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
from tabulate import tabulate

import config
from data_fetcher import get_instruments, get_quotes
from kite_client import get_kite_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORDER_TYPES = ["MARKET", "LIMIT", "SL", "SL-M"]
TRANSACTION_TYPES = ["BUY", "SELL"]
PRODUCTS = ["CNC", "MIS", "NRML"]
VALIDITIES = ["DAY", "IOC"]

# NSE/BSE trading window in IST
_IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)
_PRE_OPEN_START = dtime(9, 0)
_PRE_OPEN_END = dtime(9, 8)


# ---------------------------------------------------------------------------
# Market hours helpers
# ---------------------------------------------------------------------------

def _now_ist() -> datetime:
    return datetime.now(_IST)


def is_market_open() -> bool:
    """Return True if the market is currently open (09:15–15:30 IST, Mon–Fri)."""
    now = _now_ist()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return _MARKET_OPEN <= now.time() <= _MARKET_CLOSE


def is_pre_open() -> bool:
    """Return True if currently in the pre-open auction window (09:00–09:08 IST)."""
    now = _now_ist()
    if now.weekday() >= 5:
        return False
    return _PRE_OPEN_START <= now.time() < _PRE_OPEN_END


def market_status_message() -> str:
    """Return a human-readable market status string."""
    now = _now_ist()
    if now.weekday() >= 5:
        return f"Market CLOSED (weekend) – {now.strftime('%A %H:%M IST')}"
    t = now.time()
    if t < _PRE_OPEN_START:
        return f"Market CLOSED (pre-market not yet open) – {now.strftime('%H:%M IST')}"
    if _PRE_OPEN_START <= t < _PRE_OPEN_END:
        return f"PRE-OPEN auction session – {now.strftime('%H:%M IST')}"
    if _PRE_OPEN_END <= t < _MARKET_OPEN:
        return f"Market CLOSED (waiting for regular session) – {now.strftime('%H:%M IST')}"
    if _MARKET_OPEN <= t <= _MARKET_CLOSE:
        return f"Market OPEN – {now.strftime('%H:%M IST')}"
    return f"Market CLOSED (after hours) – {now.strftime('%H:%M IST')}"


# ---------------------------------------------------------------------------
# Symbol validation and LTP fetch
# ---------------------------------------------------------------------------

def validate_symbol(
    kite,
    symbol: str,
    exchange: str = config.EXCHANGE,
) -> Optional[dict]:
    """
    Validate that *symbol* exists on *exchange* in the instruments list.

    Returns:
        Instrument dict with keys: tradingsymbol, instrument_token, name,
        lot_size, tick_size, instrument_type, segment, exchange.
        Returns None if symbol is not found.
    """
    df = get_instruments(kite, exchange)
    match = df[df["tradingsymbol"] == symbol.upper()]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def get_ltp(kite, symbol: str, exchange: str = config.EXCHANGE) -> Optional[float]:
    """
    Fetch the Last Traded Price (LTP) for *symbol* on *exchange*.

    Returns:
        LTP as float, or None if unavailable.
    """
    quotes = get_quotes(kite, [symbol], exchange)
    key = f"{exchange}:{symbol.upper()}"
    quote = quotes.get(key)
    if not quote:
        return None
    return quote.get("last_price")


# ---------------------------------------------------------------------------
# Core order placement
# ---------------------------------------------------------------------------

def place_order(
    kite,
    transaction_type: str,
    symbol: str,
    quantity: int,
    order_type: str = "MARKET",
    product: str = "CNC",
    exchange: str = config.EXCHANGE,
    price: float = 0.0,
    trigger_price: float = 0.0,
    validity: str = "DAY",
    disclosed_quantity: int = 0,
    tag: str = "",
    variety: str = "regular",
) -> str:
    """
    Place an order via Kite Connect.

    Args:
        kite:               Authenticated KiteConnect instance.
        transaction_type:   "BUY" or "SELL".
        symbol:             Trading symbol (e.g. "RELIANCE").
        quantity:           Number of shares/lots.
        order_type:         "MARKET", "LIMIT", "SL", or "SL-M".
        product:            "CNC" (delivery), "MIS" (intraday), or "NRML" (F&O).
        exchange:           "NSE", "BSE", "NFO", "MCX", etc.
        price:              Limit price (required for LIMIT and SL; 0 for MARKET/SL-M).
        trigger_price:      Trigger price (required for SL and SL-M).
        validity:           "DAY" or "IOC".
        disclosed_quantity: Quantity to disclose publicly (optional).
        tag:                Optional custom tag for the order (max 20 chars).
        variety:            Kite order variety – "regular", "amo", "co", "iceberg".

    Returns:
        Order ID string on success.

    Raises:
        ValueError: On invalid parameters.
        Exception:  Kite API errors are propagated.
    """
    transaction_type = transaction_type.upper()
    order_type = order_type.upper()
    product = product.upper()
    validity = validity.upper()
    symbol = symbol.upper()

    # --- Parameter validation ---
    if transaction_type not in TRANSACTION_TYPES:
        raise ValueError(f"Invalid transaction_type '{transaction_type}'. Must be BUY or SELL.")
    if order_type not in ORDER_TYPES:
        raise ValueError(f"Invalid order_type '{order_type}'. Choose from {ORDER_TYPES}.")
    if product not in PRODUCTS:
        raise ValueError(f"Invalid product '{product}'. Choose from {PRODUCTS}.")
    if validity not in VALIDITIES:
        raise ValueError(f"Invalid validity '{validity}'. Choose from {VALIDITIES}.")
    if quantity <= 0:
        raise ValueError("Quantity must be a positive integer.")
    if order_type in ("LIMIT", "SL") and price <= 0:
        raise ValueError(f"A positive price is required for {order_type} orders.")
    if order_type in ("SL", "SL-M") and trigger_price <= 0:
        raise ValueError(f"A positive trigger_price is required for {order_type} orders.")

    kwargs = dict(
        variety=variety,
        exchange=exchange,
        tradingsymbol=symbol,
        transaction_type=transaction_type,
        quantity=quantity,
        product=product,
        order_type=order_type,
        price=price,
        trigger_price=trigger_price,
        validity=validity,
        disclosed_quantity=disclosed_quantity,
    )
    if tag:
        kwargs["tag"] = tag[:20]

    order_id = kite.place_order(**kwargs)
    return order_id


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def place_market_order(
    kite,
    transaction_type: str,
    symbol: str,
    quantity: int,
    product: str = "CNC",
    exchange: str = config.EXCHANGE,
    validity: str = "DAY",
    tag: str = "",
) -> str:
    """
    Place a MARKET order – executes at the best available price.

    This is the simplest order type: no price specification needed.
    The exchange fills the order at the current best bid (SELL) or ask (BUY).

    Returns:
        Order ID string.
    """
    return place_order(
        kite,
        transaction_type=transaction_type,
        symbol=symbol,
        quantity=quantity,
        order_type="MARKET",
        product=product,
        exchange=exchange,
        validity=validity,
        tag=tag,
    )


def place_limit_order(
    kite,
    transaction_type: str,
    symbol: str,
    quantity: int,
    price: float,
    product: str = "CNC",
    exchange: str = config.EXCHANGE,
    validity: str = "DAY",
    tag: str = "",
) -> str:
    """
    Place a LIMIT order – executes only at *price* or better.

    Returns:
        Order ID string.
    """
    return place_order(
        kite,
        transaction_type=transaction_type,
        symbol=symbol,
        quantity=quantity,
        order_type="LIMIT",
        price=price,
        product=product,
        exchange=exchange,
        validity=validity,
        tag=tag,
    )


def place_sl_order(
    kite,
    transaction_type: str,
    symbol: str,
    quantity: int,
    price: float,
    trigger_price: float,
    product: str = "CNC",
    exchange: str = config.EXCHANGE,
    validity: str = "DAY",
    tag: str = "",
) -> str:
    """
    Place a Stop-Loss Limit (SL) order.

    The order becomes active once the LTP crosses *trigger_price*, then
    executes as a limit order at *price*.

    For a SELL SL: trigger_price > price (trigger is above limit; as price
        falls through trigger, a sell limit at *price* is placed to ensure fill).
    For a BUY  SL: trigger_price < price (trigger is below limit; as price
        rises through trigger, a buy limit at *price* is placed to ensure fill).

    Returns:
        Order ID string.
    """
    return place_order(
        kite,
        transaction_type=transaction_type,
        symbol=symbol,
        quantity=quantity,
        order_type="SL",
        price=price,
        trigger_price=trigger_price,
        product=product,
        exchange=exchange,
        validity=validity,
        tag=tag,
    )


def place_slm_order(
    kite,
    transaction_type: str,
    symbol: str,
    quantity: int,
    trigger_price: float,
    product: str = "CNC",
    exchange: str = config.EXCHANGE,
    validity: str = "DAY",
    tag: str = "",
) -> str:
    """
    Place a Stop-Loss Market (SL-M) order.

    Triggers at *trigger_price* then executes as a market order (best available).
    No limit price needed – execution is guaranteed once triggered.

    Returns:
        Order ID string.
    """
    return place_order(
        kite,
        transaction_type=transaction_type,
        symbol=symbol,
        quantity=quantity,
        order_type="SL-M",
        trigger_price=trigger_price,
        product=product,
        exchange=exchange,
        validity=validity,
        tag=tag,
    )


# ---------------------------------------------------------------------------
# GTT (Good Till Triggered) orders
# ---------------------------------------------------------------------------

def place_gtt_order(
    kite,
    transaction_type: str,
    symbol: str,
    quantity: int,
    trigger_price: float,
    price: float,
    exchange: str = config.EXCHANGE,
    gtt_type: str = "single",
) -> int:
    """
    Place a GTT (Good Till Triggered) order – a persistent conditional order
    that stays active until triggered (valid for 1 year from creation).

    Extremely popular with long-term investors to buy dips or protect profits
    without active monitoring.

    Args:
        kite:             Authenticated KiteConnect instance.
        transaction_type: "BUY" or "SELL".
        symbol:           Trading symbol (e.g. "RELIANCE").
        quantity:         Number of shares.
        trigger_price:    LTP at which the GTT activates.
        price:            Limit price used when the GTT order is placed.
        exchange:         Exchange ("NSE" or "BSE").
        gtt_type:         "single" (one trigger) or "two-leg" (OCO – target + stop).

    Returns:
        GTT ID (integer).
    """
    transaction_type = transaction_type.upper()
    symbol = symbol.upper()

    if transaction_type not in TRANSACTION_TYPES:
        raise ValueError(f"Invalid transaction_type '{transaction_type}'.")
    if trigger_price <= 0:
        raise ValueError("trigger_price must be positive.")
    if price <= 0:
        raise ValueError("price must be positive.")
    if quantity <= 0:
        raise ValueError("quantity must be positive.")

    # Fetch current LTP – required by Kite's GTT API as the last_price parameter
    ltp = get_ltp(kite, symbol, exchange)
    if ltp is None:
        raise ValueError(
            f"Could not fetch LTP for {exchange}:{symbol}. "
            "Ensure the symbol is valid and market data is available."
        )

    gtt = kite.place_gtt(
        trigger_type=gtt_type,
        tradingsymbol=symbol,
        exchange=exchange,
        trigger_values=[trigger_price],
        last_price=ltp,
        orders=[
            {
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": "LIMIT",
                "product": "CNC",
                "price": price,
            }
        ],
    )
    return gtt["trigger_id"]


# ---------------------------------------------------------------------------
# Modify / Cancel
# ---------------------------------------------------------------------------

def modify_order(
    kite,
    order_id: str,
    quantity: Optional[int] = None,
    price: Optional[float] = None,
    trigger_price: Optional[float] = None,
    order_type: Optional[str] = None,
    validity: Optional[str] = None,
    disclosed_quantity: Optional[int] = None,
    variety: str = "regular",
) -> str:
    """
    Modify an existing open order.

    Only the parameters you supply will be changed; the rest retain their
    current values as reported by the exchange.

    Returns:
        Order ID string (same as input on success).

    Raises:
        Exception: Kite API errors (e.g. order already executed/cancelled).
    """
    kwargs = {"variety": variety, "order_id": order_id}
    if quantity is not None:
        kwargs["quantity"] = quantity
    if price is not None:
        kwargs["price"] = price
    if trigger_price is not None:
        kwargs["trigger_price"] = trigger_price
    if order_type is not None:
        kwargs["order_type"] = order_type.upper()
    if validity is not None:
        kwargs["validity"] = validity.upper()
    if disclosed_quantity is not None:
        kwargs["disclosed_quantity"] = disclosed_quantity

    result = kite.modify_order(**kwargs)
    return result


def cancel_order(kite, order_id: str, variety: str = "regular") -> str:
    """
    Cancel an open order.

    Returns:
        Order ID string on success.

    Raises:
        Exception: Kite API errors (e.g. order already executed).
    """
    result = kite.cancel_order(variety=variety, order_id=order_id)
    return result


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

def _print_order_result(
    action: str,
    order_id,
    symbol: str = "",
    transaction_type: str = "",
    order_type: str = "",
    quantity: int = 0,
    price: float = 0.0,
    trigger_price: float = 0.0,
    ltp: Optional[float] = None,
    exchange: str = "",
) -> None:
    """Print a summary table after placing/modifying/cancelling an order."""
    rows = [
        ["Action", action],
        ["Order ID", order_id],
    ]
    if symbol:
        rows.append(["Symbol", f"{exchange}:{symbol}" if exchange else symbol])
    if transaction_type:
        rows.append(["Side", transaction_type])
    if order_type:
        rows.append(["Order Type", order_type])
    if quantity:
        rows.append(["Quantity", quantity])
    if ltp is not None:
        rows.append(["LTP (₹)", f"{ltp:,.2f}"])
    if price > 0:
        rows.append(["Price (₹)", f"{price:,.2f}"])
    if trigger_price > 0:
        rows.append(["Trigger Price (₹)", f"{trigger_price:,.2f}"])
    rows.append(["Market Status", market_status_message()])

    print(f"\n{'='*50}")
    print(tabulate(rows, tablefmt="plain"))
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AllIN – Place, modify, and cancel Zerodha orders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- buy / sell --------------------------------------------------------
    for cmd in ("buy", "sell"):
        p = sub.add_parser(
            cmd,
            help=f"Place a {cmd.upper()} order",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        p.add_argument("symbol", help="Trading symbol (e.g. RELIANCE)")
        p.add_argument("quantity", type=int, help="Number of shares / lots")
        p.add_argument(
            "--order-type",
            default="MARKET",
            choices=ORDER_TYPES,
            help="Order type (default: MARKET – best available price)",
        )
        p.add_argument(
            "--product",
            default="CNC",
            choices=PRODUCTS,
            help="Product type (default: CNC)",
        )
        p.add_argument(
            "--exchange",
            default=config.EXCHANGE,
            help="Exchange (default from config: %(default)s)",
        )
        p.add_argument(
            "--price",
            type=float,
            default=0.0,
            help="Limit price in ₹ (required for LIMIT and SL orders)",
        )
        p.add_argument(
            "--trigger-price",
            type=float,
            default=0.0,
            help="Trigger price in ₹ (required for SL and SL-M orders)",
        )
        p.add_argument(
            "--validity",
            default="DAY",
            choices=VALIDITIES,
            help="Order validity (default: DAY)",
        )
        p.add_argument(
            "--variety",
            default="regular",
            choices=["regular", "amo", "co", "iceberg"],
            help="Order variety (default: regular)",
        )
        p.add_argument("--tag", default="", help="Optional tag (max 20 chars)")
        p.add_argument(
            "--force",
            action="store_true",
            help="Skip market-hours warning prompt and proceed anyway",
        )

    # ---- gtt ---------------------------------------------------------------
    gtt = sub.add_parser(
        "gtt",
        help="Place a GTT (Good Till Triggered) conditional order",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gtt.add_argument("side", choices=["buy", "sell"], help="BUY or SELL")
    gtt.add_argument("symbol", help="Trading symbol")
    gtt.add_argument("quantity", type=int, help="Number of shares")
    gtt.add_argument(
        "--trigger-price",
        required=True,
        type=float,
        help="LTP at which the GTT activates",
    )
    gtt.add_argument(
        "--price",
        required=True,
        type=float,
        help="Limit price to use when the GTT fires",
    )
    gtt.add_argument("--exchange", default=config.EXCHANGE, help="Exchange (default: %(default)s)")

    # ---- modify ------------------------------------------------------------
    mod = sub.add_parser("modify", help="Modify an existing open order")
    mod.add_argument("order_id", help="Order ID to modify")
    mod.add_argument("--quantity", type=int, default=None)
    mod.add_argument("--price", type=float, default=None)
    mod.add_argument("--trigger-price", type=float, default=None)
    mod.add_argument("--order-type", choices=ORDER_TYPES, default=None)
    mod.add_argument("--validity", choices=VALIDITIES, default=None)
    mod.add_argument(
        "--variety",
        default="regular",
        choices=["regular", "amo", "co", "iceberg"],
    )

    # ---- cancel ------------------------------------------------------------
    can = sub.add_parser("cancel", help="Cancel an open order")
    can.add_argument("order_id", help="Order ID to cancel")
    can.add_argument(
        "--variety",
        default="regular",
        choices=["regular", "amo", "co", "iceberg"],
    )

    # ---- status ------------------------------------------------------------
    sub.add_parser("status", help="Show current market status (hours, IST time)")

    return parser


def _confirm_outside_hours(force: bool) -> bool:
    """
    When placing an order outside regular market hours, warn the user and
    ask for confirmation (unless --force is set).

    Returns True to proceed, False to abort.
    """
    if force:
        return True
    print(f"\nWARNING: {market_status_message()}")
    print("Orders placed now will be queued as AMO (After Market Orders).")
    try:
        answer = input("Proceed anyway? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # ---- status (no Kite connection needed) --------------------------------
    if args.command == "status":
        print(f"\nMarket status: {market_status_message()}\n")
        print(f"  Regular session : 09:15 – 15:30 IST (Mon–Fri)")
        print(f"  Pre-open        : 09:00 – 09:08 IST (Mon–Fri)\n")
        sys.exit(0)

    try:
        kite = get_kite_client()
    except Exception as exc:
        print(f"Error connecting to Kite: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        # ---- buy / sell ----------------------------------------------------
        if args.command in ("buy", "sell"):
            transaction_type = args.command.upper()
            symbol = args.symbol.upper()
            exchange = args.exchange.upper()

            # Symbol validation
            instrument = validate_symbol(kite, symbol, exchange)
            if instrument is None:
                print(
                    f"Error: Symbol '{symbol}' not found on {exchange}. "
                    "Check the trading symbol spelling.",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Fetch LTP for informational display
            ltp = get_ltp(kite, symbol, exchange)

            # Market hours check
            if not is_market_open() and not is_pre_open():
                if not _confirm_outside_hours(getattr(args, "force", False)):
                    print("Order cancelled by user.")
                    sys.exit(0)

            order_id = place_order(
                kite,
                transaction_type=transaction_type,
                symbol=symbol,
                quantity=args.quantity,
                order_type=args.order_type,
                product=args.product,
                exchange=exchange,
                price=args.price,
                trigger_price=args.trigger_price,
                validity=args.validity,
                variety=args.variety,
                tag=args.tag,
            )

            _print_order_result(
                action=f"ORDER PLACED ({args.order_type})",
                order_id=order_id,
                symbol=symbol,
                transaction_type=transaction_type,
                order_type=args.order_type,
                quantity=args.quantity,
                price=args.price,
                trigger_price=args.trigger_price,
                ltp=ltp,
                exchange=exchange,
            )

        # ---- gtt -----------------------------------------------------------
        elif args.command == "gtt":
            symbol = args.symbol.upper()
            exchange = args.exchange.upper()

            instrument = validate_symbol(kite, symbol, exchange)
            if instrument is None:
                print(
                    f"Error: Symbol '{symbol}' not found on {exchange}.",
                    file=sys.stderr,
                )
                sys.exit(1)

            gtt_id = place_gtt_order(
                kite,
                transaction_type=args.side.upper(),
                symbol=symbol,
                quantity=args.quantity,
                trigger_price=args.trigger_price,
                price=args.price,
                exchange=exchange,
            )

            ltp = get_ltp(kite, symbol, exchange)
            _print_order_result(
                action="GTT ORDER PLACED",
                order_id=gtt_id,
                symbol=symbol,
                transaction_type=args.side.upper(),
                order_type="GTT",
                quantity=args.quantity,
                price=args.price,
                trigger_price=args.trigger_price,
                ltp=ltp,
                exchange=exchange,
            )

        # ---- modify --------------------------------------------------------
        elif args.command == "modify":
            result = modify_order(
                kite,
                order_id=args.order_id,
                quantity=args.quantity,
                price=args.price,
                trigger_price=getattr(args, "trigger_price", None),
                order_type=args.order_type,
                validity=args.validity,
                variety=args.variety,
            )
            _print_order_result(
                action="ORDER MODIFIED",
                order_id=result,
                price=args.price or 0.0,
                trigger_price=getattr(args, "trigger_price", None) or 0.0,
            )

        # ---- cancel --------------------------------------------------------
        elif args.command == "cancel":
            result = cancel_order(kite, order_id=args.order_id, variety=args.variety)
            _print_order_result(action="ORDER CANCELLED", order_id=result)

    except ValueError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
