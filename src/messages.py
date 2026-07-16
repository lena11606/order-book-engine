from dataclasses import dataclass, field
from datetime import datetime


## NOTE TO SELF: default_factory = new list for each class (ie each order)

@dataclass
class Message:
    message_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=str)

# Order Entry
@dataclass
class OrderEntryRequest(Message):
    message_type: str = "OrderEntryRequest"
    participant_id: str = ""
    order_id: str = "" #
    security_id: str = ""
    side: str = "" # BID / ASK
    quantity: int = 0
    price: float= 0.0

# Order Modification
@dataclass
class OrderModificationRequest(Message):
    message_type: str = "OrderModificationRequest"
    participant_id: str = ""
    order_id: str = "" # needs to be an existing order ID
    new_quantity: int = 0
    new_price: float= 0.0

# Order Cancellation
@dataclass
class OrderCancellationRequest(Message):
    message_type: str = "OrderCancellationRequest"
    participant_id: str = ""
    order_id: str = ""

# Order Confirmation
class OrderConfirmationRequest(Message):
    message_type: str = "OrderConfirmationRequest"
    order_id: str = ""
    status: str = ""  # "ACKNOWLEDGED", "FILLED", "PARTIALLY_FILLED", "CANCELLED", "REJECTED"
    executed_quantity: int = 0
    remaining_quantity: int = 0
    execution_price: float= 0.0

# Crossed Order Notification
# when the highest price a buyer is willing to pay > lowest price a seller is willing to accept
# bid > ask
# arbitrage! can buy at lower price & sell for higher
@dataclass
class CrossedOrderNotification(Message):
    message_type: str = "CrossedOrderNotification"
    crossed_order_ids: list = field(default_factory=list)
    participant_ids: list = field(default_factory=list)
    trade_prices: list = field(default_factory=list)

# Market Data Snapshot
@dataclass
class MarketData(Message):
    message_type: str = "MarketData"
    security_id: str = ""
    best_bid_price: float= 0.0
    best_bid_quantity: int= 0
    best_ask_price: float= 0.0
    best_ask_quantity: int= 0
    last_trade_price: float= 0.0
    last_trade_quantity: int= 0
