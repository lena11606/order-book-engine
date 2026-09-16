"""Validation engine for sanity-checking order book and blotter state.

Runs order-level, book-level, reconciliation, and cross-cutting sanity
checks over an OrderBook and TradeBlotter and reports every violation
found rather than stopping at the first one.
"""

from dataclasses import dataclass
from typing import List, Optional

from src.blotter import TradeBlotter, TradeStatus
from src.order import OrderStatus
from src.order_book import OrderBook


class Severity:
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


VALID_STATUSES = {
    OrderStatus.NEW,
    OrderStatus.ACKNOWLEDGED,
    OrderStatus.OPEN,
    OrderStatus.PARTIALLY_FILLED,
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
}


@dataclass
class ValidationError:
    check_name: str
    order_id: Optional[str]
    description: str
    severity: str


class ValidationEngine:
    def validate(self, order_book: OrderBook, blotter: TradeBlotter) -> List[ValidationError]:
        errors: List[ValidationError] = []
        errors.extend(self._check_orders(order_book))
        errors.extend(self._check_book(order_book))
        errors.extend(self._check_reconciliation(order_book, blotter))
        errors.extend(self._check_sanity(order_book, blotter))
        return errors

    def _check_orders(self, order_book: OrderBook) -> List[ValidationError]:
        errors: List[ValidationError] = []
        seen_ids = set()

        for order_id, order in order_book.order_registry.items():
            if order.quantity <= 0:
                errors.append(
                    ValidationError(
                        "NON_POSITIVE_QUANTITY",
                        order_id,
                        f"Order {order_id} has non-positive quantity {order.quantity}",
                        Severity.CRITICAL,
                    )
                )
            if order.price <= 0:
                errors.append(
                    ValidationError(
                        "NON_POSITIVE_PRICE",
                        order_id,
                        f"Order {order_id} has non-positive price {order.price}",
                        Severity.CRITICAL,
                    )
                )
            if order_id in seen_ids:
                errors.append(
                    ValidationError(
                        "DUPLICATE_ORDER_ID",
                        order_id,
                        f"Duplicate order_id {order_id} found in registry",
                        Severity.CRITICAL,
                    )
                )
            seen_ids.add(order_id)

            if order.status not in VALID_STATUSES:
                errors.append(
                    ValidationError(
                        "INVALID_STATUS",
                        order_id,
                        f"Order {order_id} has invalid status {order.status}",
                        Severity.CRITICAL,
                    )
                )

            if order.status == OrderStatus.FILLED and order.remaining_quantity > 0:
                errors.append(
                    ValidationError(
                        "FILLED_WITH_REMAINING_QTY",
                        order_id,
                        f"Order {order_id} is FILLED but has remaining "
                        f"quantity {order.remaining_quantity}",
                        Severity.CRITICAL,
                    )
                )

            if order.status == OrderStatus.CANCELLED and (
                order in order_book.bids or order in order_book.asks
            ):
                errors.append(
                    ValidationError(
                        "CANCELLED_ORDER_IN_BOOK",
                        order_id,
                        f"Order {order_id} is CANCELLED but still present in the book",
                        Severity.CRITICAL,
                    )
                )

            if (
                order.status == OrderStatus.PARTIALLY_FILLED
                and order.executed_quantity == order.quantity
            ):
                errors.append(
                    ValidationError(
                        "PARTIAL_FILL_FULLY_EXECUTED",
                        order_id,
                        f"Order {order_id} is PARTIALLY_FILLED but executed_quantity "
                        f"equals original quantity {order.quantity}",
                        Severity.CRITICAL,
                    )
                )

            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                for i in range(1, len(order.history)):
                    prior_status = order.history[i - 1]["status"]
                    if prior_status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                        errors.append(
                            ValidationError(
                                "MODIFICATION_AFTER_TERMINAL_STATE",
                                order_id,
                                f"Order {order_id} was modified after reaching "
                                f"terminal state {prior_status}",
                                Severity.CRITICAL,
                            )
                        )

            if order in order_book.bids and order in order_book.asks:
                errors.append(
                    ValidationError(
                        "ORDER_IN_BOTH_BOOKS",
                        order_id,
                        f"Order {order_id} appears in both bids and asks simultaneously",
                        Severity.CRITICAL,
                    )
                )

        return errors

    def _check_book(self, order_book: OrderBook) -> List[ValidationError]:
        errors: List[ValidationError] = []
        security_ids = {o.security_id for o in order_book.bids} | {
            o.security_id for o in order_book.asks
        }
        for security_id in security_ids:
            best_bid = order_book._best_bid_for_security(security_id)
            best_ask = order_book._best_ask_for_security(security_id)
            if best_bid is not None and best_ask is not None and best_bid.price >= best_ask.price:
                errors.append(
                    ValidationError(
                        "CROSSED_MARKET",
                        None,
                        f"Best bid {best_bid.price} >= best ask {best_ask.price} "
                        f"for {security_id}",
                        Severity.CRITICAL,
                    )
                )

        for i in range(1, len(order_book.bids)):
            prev, curr = order_book.bids[i - 1], order_book.bids[i]
            if prev.price < curr.price or (
                prev.price == curr.price and prev.timestamp > curr.timestamp
            ):
                errors.append(
                    ValidationError(
                        "BIDS_NOT_SORTED",
                        curr.order_id,
                        f"Bids not sorted correctly at index {i}",
                        Severity.WARNING,
                    )
                )

        for i in range(1, len(order_book.asks)):
            prev, curr = order_book.asks[i - 1], order_book.asks[i]
            if prev.price > curr.price or (
                prev.price == curr.price and prev.timestamp > curr.timestamp
            ):
                errors.append(
                    ValidationError(
                        "ASKS_NOT_SORTED",
                        curr.order_id,
                        f"Asks not sorted correctly at index {i}",
                        Severity.WARNING,
                    )
                )

        return errors

    def _check_reconciliation(
        self, order_book: OrderBook, blotter: TradeBlotter
    ) -> List[ValidationError]:
        errors: List[ValidationError] = []
        trades = blotter.get_all_trades()
        traded_order_ids = set()
        for trade in trades:
            traded_order_ids.add(trade["buy_order_id"])
            traded_order_ids.add(trade["sell_order_id"])

        for order_id, order in order_book.order_registry.items():
            if order.status == OrderStatus.FILLED and order_id not in traded_order_ids:
                errors.append(
                    ValidationError(
                        "FILLED_ORDER_NOT_IN_BLOTTER",
                        order_id,
                        f"Order {order_id} is FILLED but has no matching trade in the blotter",
                        Severity.CRITICAL,
                    )
                )

        for trade in trades:
            if trade["status"] == TradeStatus.BREAK:
                errors.append(
                    ValidationError(
                        "UNRESOLVED_BREAK",
                        None,
                        f"Trade {trade['trade_id']} has an unresolved reconciliation break",
                        Severity.WARNING,
                    )
                )

        return errors

    def _check_sanity(
        self, order_book: OrderBook, blotter: TradeBlotter
    ) -> List[ValidationError]:
        errors: List[ValidationError] = []
        trades = blotter.get_all_trades()

        total_buy_qty = sum(t["quantity"] for t in trades)
        total_sell_qty = sum(t["quantity"] for t in trades)
        if total_buy_qty != total_sell_qty:
            errors.append(
                ValidationError(
                    "BUY_SELL_QTY_MISMATCH",
                    None,
                    f"Total executed buy quantity {total_buy_qty} != total "
                    f"executed sell quantity {total_sell_qty}",
                    Severity.CRITICAL,
                )
            )

        for trade in trades:
            buy_order = order_book.order_registry.get(trade["buy_order_id"])
            sell_order = order_book.order_registry.get(trade["sell_order_id"])
            price = trade["price"]

            if buy_order is not None and price > buy_order.price:
                errors.append(
                    ValidationError(
                        "FILL_WORSE_THAN_LIMIT",
                        buy_order.order_id,
                        f"Buy order {buy_order.order_id} paid {price} which is "
                        f"worse than its limit price {buy_order.price}",
                        Severity.CRITICAL,
                    )
                )
            if sell_order is not None and price < sell_order.price:
                errors.append(
                    ValidationError(
                        "FILL_WORSE_THAN_LIMIT",
                        sell_order.order_id,
                        f"Sell order {sell_order.order_id} received {price} which is "
                        f"worse than its limit price {sell_order.price}",
                        Severity.CRITICAL,
                    )
                )

            if (
                buy_order is not None
                and sell_order is not None
                and buy_order.participant_id == sell_order.participant_id
            ):
                errors.append(
                    ValidationError(
                        "SELF_TRADE",
                        None,
                        f"Trade {trade['trade_id']} is a self-trade for "
                        f"participant {buy_order.participant_id}",
                        Severity.CRITICAL,
                    )
                )

        return errors
