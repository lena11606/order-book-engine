"""Order state machine and order data model.

Defines the valid order lifecycle states, the legal transitions between
them, and the Order dataclass that tracks quantity, execution progress,
and a full history of every status change it undergoes.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List


class OrderStatus:
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


VALID_TRANSITIONS: Dict[str, List[str]] = {
    OrderStatus.NEW: [OrderStatus.ACKNOWLEDGED],
    OrderStatus.ACKNOWLEDGED: [OrderStatus.OPEN, OrderStatus.REJECTED],
    OrderStatus.OPEN: [
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    ],
    OrderStatus.PARTIALLY_FILLED: [OrderStatus.FILLED, OrderStatus.CANCELLED],
    OrderStatus.FILLED: [],
    OrderStatus.CANCELLED: [],
    OrderStatus.REJECTED: [],
}


@dataclass
class Order:
    participant_id: str
    security_id: str
    side: str
    quantity: int
    price: float
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = OrderStatus.NEW
    executed_quantity: int = 0
    remaining_quantity: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    history: List[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.remaining_quantity = self.quantity
        self._log(OrderStatus.NEW)

    def transition(self, new_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition for order {self.order_id}: "
                f"{self.status} -> {new_status}"
            )
        self.status = new_status
        self._log(new_status)

    def fill(self, filled_quantity: int) -> None:
        if filled_quantity <= 0:
            raise ValueError(
                f"Fill quantity must be positive, got {filled_quantity}"
            )
        if filled_quantity > self.remaining_quantity:
            raise ValueError(
                f"Fill quantity {filled_quantity} exceeds remaining "
                f"quantity {self.remaining_quantity} for order {self.order_id}"
            )
        self.executed_quantity += filled_quantity
        self.remaining_quantity -= filled_quantity
        new_status = (
            OrderStatus.FILLED if self.remaining_quantity == 0 else OrderStatus.PARTIALLY_FILLED
        )
        if new_status != self.status:
            self.transition(new_status)

    def _log(self, status: str) -> None:
        self.history.append({"status": status, "timestamp": datetime.now()})
