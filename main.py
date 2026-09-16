"""End-to-end simulation of the order book engine.

Places a mixed batch of orders across two securities, matches them,
persists and reconciles the resulting trades against a simulated
exchange confirmation feed, and runs the validation engine over the
final state. Demonstrates the order state machine, price-time
priority matching, break detection, and error handling for invalid
operations.
"""

import csv
import os

from src.blotter import TradeBlotter
from src.order import Order, OrderStatus
from src.order_book import OrderBook
from src.validator import ValidationEngine

DATA_DIR = "data"
SAMPLE_ORDERS_PATH = os.path.join(DATA_DIR, "sample_orders.csv")
EXCHANGE_CONFIRMS_PATH = os.path.join(DATA_DIR, "exchange_confirms.csv")
BLOTTER_DB_PATH = os.path.join(DATA_DIR, "blotter.db")


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def load_orders(filepath: str) -> list:
    orders = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            order = Order(
                order_id=row["order_id"],
                participant_id=row["participant_id"],
                security_id=row["security_id"],
                side=row["side"],
                quantity=int(row["quantity"]),
                price=float(row["price"]),
            )
            orders.append(order)
    return orders


def generate_exchange_confirms(trades: list, filepath: str) -> None:
    fieldnames = ["confirm_id", "trade_id", "quantity", "price", "timestamp"]
    rows = []
    for i, trade in enumerate(trades):
        confirm = {
            "confirm_id": f"CONF-{i + 1:03d}",
            "trade_id": trade["trade_id"],
            "quantity": trade["quantity"],
            "price": trade["price"],
            "timestamp": trade["timestamp"].isoformat(),
        }
        rows.append(confirm)

    if len(rows) >= 1:
        omitted = rows.pop(0)
        print(f"  (intentionally omitting confirm for trade {omitted['trade_id']} "
              f"to create a MISSING_CONFIRM break)")

    if len(rows) >= 1:
        rows[0]["quantity"] = rows[0]["quantity"] + 5
        print(f"  (intentionally corrupting quantity for trade {rows[0]['trade_id']} "
              f"to create a QTY_MISMATCH break)")

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if os.path.exists(BLOTTER_DB_PATH):
        os.remove(BLOTTER_DB_PATH)

    print_header("STEP 1-3: INITIALIZE ORDER BOOK, BLOTTER, AND VALIDATOR")
    order_book = OrderBook()
    blotter = TradeBlotter(db_path=BLOTTER_DB_PATH)
    validator = ValidationEngine()
    print("OrderBook, TradeBlotter, and ValidationEngine initialized.")

    print_header("STEP 4: PLACE ORDERS FROM data/sample_orders.csv")
    orders = load_orders(SAMPLE_ORDERS_PATH)
    for order in orders:
        result = order_book.place_order(order)
        print(
            f"  place_order {order.order_id} {order.participant_id} "
            f"{order.security_id} {order.side} {order.quantity}@{order.price} -> {result}"
        )

    print_header("STEP 5: MATCH ORDERS")
    trades = order_book.match_orders()
    for trade in trades:
        print(
            f"  TRADE {trade['trade_id']} | {trade['security_id']} | "
            f"qty={trade['quantity']} | price={trade['price']} | "
            f"buy={trade['buy_order_id']} | sell={trade['sell_order_id']}"
        )
    print(f"  Total trades executed: {len(trades)}")

    print_header("STEP 6: LOG TRADES TO BLOTTER")
    for trade in trades:
        blotter.log_trade(trade)
    print(f"  Logged {len(trades)} trades to {BLOTTER_DB_PATH}")

    print_header("STEP 7: GENERATE SIMULATED EXCHANGE CONFIRMS")
    generate_exchange_confirms(trades, EXCHANGE_CONFIRMS_PATH)
    print(f"  Wrote exchange confirms to {EXCHANGE_CONFIRMS_PATH}")

    print_header("STEP 8: RECONCILE BLOTTER AGAINST EXCHANGE CONFIRMS")
    breaks = blotter.reconcile(EXCHANGE_CONFIRMS_PATH)
    if breaks:
        for br in breaks:
            print(f"  BREAK [{br['break_type']}] trade={br['trade_id']}: {br['description']}")
    else:
        print("  No breaks found.")

    print_header("STEP 9: RUN VALIDATION ENGINE")
    validation_errors = validator.validate(order_book, blotter)
    if validation_errors:
        for err in validation_errors:
            print(f"  [{err.severity}] {err.check_name} (order={err.order_id}): {err.description}")
    else:
        print("  No validation errors found.")

    print_header("STEP 10: DEMONSTRATE INVALID-STATE HANDLING")
    filled_order = next((o for o in orders if o.status == OrderStatus.FILLED), None)
    if filled_order is not None:
        result = order_book.cancel_order(filled_order.order_id, filled_order.participant_id)
        print(f"  cancel_order on FILLED order {filled_order.order_id} -> {result}")

        try:
            filled_order.transition(OrderStatus.OPEN)
            print("  ERROR: transition should have raised ValueError")
        except ValueError as e:
            print(f"  Caught expected ValueError: {e}")

        print(f"  Order history for {filled_order.order_id}:")
        for entry in filled_order.history:
            print(f"    {entry['timestamp'].isoformat()} -> {entry['status']}")
    else:
        print("  No FILLED order found to demonstrate invalid cancellation.")

    print_header("SIMULATION COMPLETE")


if __name__ == "__main__":
    main()
