"""Exchange message protocol definitions.

Defines the FIX-style message types exchanged between a trading
participant and the exchange: order entry, modification, cancellation,
confirmations, crossed-order notifications, and market data snapshots.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Message:
    message_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class OrderEntryRequest(Message):
    message_type: str = "ORDER_ENTRY"
    participant_id: str = ""
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    security_id: str = ""
    side: str = ""  # "BID" or "ASK"
    quantity: int = 0
    price: float = 0.0


@dataclass
class OrderModificationRequest(Message):
    message_type: str = "ORDER_MODIFY"
    participant_id: str = ""
    order_id: str = ""
    new_quantity: int = 0
    new_price: float = 0.0


@dataclass
class OrderCancellationRequest(Message):
    message_type: str = "ORDER_CANCEL"
    participant_id: str = ""
    order_id: str = ""


@dataclass
class OrderConfirmation(Message):
    message_type: str = "ORDER_CONFIRM"
    order_id: str = ""
    status: str = ""  # ACKNOWLEDGED, FILLED, PARTIALLY_FILLED, CANCELLED, REJECTED
    executed_quantity: int = 0
    remaining_quantity: int = 0
    execution_price: Optional[float] = None


@dataclass
class CrossedOrdersNotification(Message):
    message_type: str = "CROSSED_ORDERS"
    crossed_order_ids: list = field(default_factory=list)
    participant_ids: list = field(default_factory=list)
    trade_prices: list = field(default_factory=list)


@dataclass
class MarketDataSnapshot(Message):
    message_type: str = "MARKET_DATA"
    security_id: str = ""
    best_bid_price: float = 0.0
    best_bid_quantity: int = 0
    best_ask_price: float = 0.0
    best_ask_quantity: int = 0
    last_traded_price: float = 0.0
    last_traded_volume: int = 0
