"""Price-time priority limit order book and matching engine.

Maintains sorted bid/ask books, validates and applies order entry,
modification, and cancellation requests, and matches crossed orders
at the resting (maker) order's price.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from src.messages import MarketDataSnapshot
from src.order import Order, OrderStatus


class OrderBook:
    def __init__(self) -> None:
        self.bids: List[Order] = []
        self.asks: List[Order] = []
        self.order_registry: Dict[str, Order] = {}
        self.trade_log: List[dict] = []

    def _sort_bids(self) -> None:
        self.bids.sort(key=lambda o: (-o.price, o.timestamp))

    def _sort_asks(self) -> None:
        self.asks.sort(key=lambda o: (o.price, o.timestamp))

    def place_order(self, order: Order) -> str:
        if order.quantity <= 0:
            return f"REJECTED: quantity must be positive, got {order.quantity}"
        if order.price <= 0:
            return f"REJECTED: price must be positive, got {order.price}"
        if order.order_id in self.order_registry:
            return f"REJECTED: duplicate order_id {order.order_id}"
        if order.side not in ("BID", "ASK"):
            return f"REJECTED: side must be BID or ASK, got {order.side}"

        self.order_registry[order.order_id] = order
        if order.side == "BID":
            self.bids.append(order)
            self._sort_bids()
        else:
            self.asks.append(order)
            self._sort_asks()

        order.transition(OrderStatus.ACKNOWLEDGED)
        order.transition(OrderStatus.OPEN)
        return "OK"

    def modify_order(
        self, order_id: str, participant_id: str, new_qty: int, new_price: float
    ) -> str:
        order = self.order_registry.get(order_id)
        if order is None:
            return f"REJECTED: order {order_id} not found"
        if order.participant_id != participant_id:
            return f"REJECTED: participant_id mismatch for order {order_id}"
        if order.status not in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
            return f"REJECTED: cannot modify order in status {order.status}"
        if new_qty <= 0:
            return f"REJECTED: new_qty must be positive, got {new_qty}"
        if new_price <= 0:
            return f"REJECTED: new_price must be positive, got {new_price}"

        order.price = new_price
        order.quantity = new_qty
        order.remaining_quantity = new_qty - order.executed_quantity
        self._sort_bids()
        self._sort_asks()
        return "OK"

    def cancel_order(self, order_id: str, participant_id: str) -> str:
        order = self.order_registry.get(order_id)
        if order is None:
            return f"REJECTED: order {order_id} not found"
        if order.participant_id != participant_id:
            return f"REJECTED: participant_id mismatch for order {order_id}"
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return f"REJECTED: cannot cancel order in status {order.status}"

        if order in self.bids:
            self.bids.remove(order)
        if order in self.asks:
            self.asks.remove(order)
        order.transition(OrderStatus.CANCELLED)
        return "OK"

    def _best_bid_for_security(self, security_id: str) -> Optional[Order]:
        matching = [o for o in self.bids if o.security_id == security_id]
        return matching[0] if matching else None

    def _best_ask_for_security(self, security_id: str) -> Optional[Order]:
        matching = [o for o in self.asks if o.security_id == security_id]
        return matching[0] if matching else None

    def match_orders(self) -> List[dict]:
        trades: List[dict] = []
        security_ids = {o.security_id for o in self.bids} | {o.security_id for o in self.asks}

        for security_id in security_ids:
            while True:
                self._sort_bids()
                self._sort_asks()
                best_bid = self._best_bid_for_security(security_id)
                best_ask = self._best_ask_for_security(security_id)

                if best_bid is None or best_ask is None:
                    break
                if best_bid.price < best_ask.price:
                    break

                maker = best_bid if best_bid.timestamp <= best_ask.timestamp else best_ask
                execution_price = maker.price
                trade_quantity = min(best_bid.remaining_quantity, best_ask.remaining_quantity)

                best_bid.fill(trade_quantity)
                best_ask.fill(trade_quantity)

                trade = {
                    "trade_id": str(uuid.uuid4()),
                    "buy_order_id": best_bid.order_id,
                    "sell_order_id": best_ask.order_id,
                    "security_id": security_id,
                    "quantity": trade_quantity,
                    "price": execution_price,
                    "timestamp": datetime.now(),
                }
                self.trade_log.append(trade)
                trades.append(trade)

                if best_bid.status == OrderStatus.FILLED:
                    self.bids.remove(best_bid)
                if best_ask.status == OrderStatus.FILLED:
                    self.asks.remove(best_ask)

        return trades

    def get_best_bid(self) -> Optional[Order]:
        return self.bids[0] if self.bids else None

    def get_best_ask(self) -> Optional[Order]:
        return self.asks[0] if self.asks else None

    def get_market_snapshot(self, security_id: str) -> MarketDataSnapshot:
        best_bid = self._best_bid_for_security(security_id)
        best_ask = self._best_ask_for_security(security_id)
        last_trade = None
        for trade in reversed(self.trade_log):
            if trade["security_id"] == security_id:
                last_trade = trade
                break

        return MarketDataSnapshot(
            security_id=security_id,
            best_bid_price=best_bid.price if best_bid else 0.0,
            best_bid_quantity=best_bid.remaining_quantity if best_bid else 0,
            best_ask_price=best_ask.price if best_ask else 0.0,
            best_ask_quantity=best_ask.remaining_quantity if best_ask else 0,
            last_traded_price=last_trade["price"] if last_trade else 0.0,
            last_traded_volume=last_trade["quantity"] if last_trade else 0,
        )
