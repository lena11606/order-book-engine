"""Unit tests for the OrderBook matching engine."""

import time

from src.order import Order, OrderStatus
from src.order_book import OrderBook


def make_order(participant_id="P1", security_id="AAPL", side="BID", quantity=100, price=175.0, order_id=None):
    kwargs = dict(
        participant_id=participant_id,
        security_id=security_id,
        side=side,
        quantity=quantity,
        price=price,
    )
    if order_id is not None:
        kwargs["order_id"] = order_id
    return Order(**kwargs)


def test_place_order_valid():
    book = OrderBook()
    order = make_order()
    result = book.place_order(order)
    assert result == "OK"
    assert order.status == OrderStatus.OPEN
    assert order.order_id in book.order_registry
    assert order in book.bids


def test_place_order_invalid_quantity():
    book = OrderBook()
    order = make_order(quantity=0)
    result = book.place_order(order)
    assert result != "OK"
    assert order.order_id not in book.order_registry


def test_place_order_duplicate_id():
    book = OrderBook()
    order1 = make_order(order_id="DUP-1")
    order2 = make_order(order_id="DUP-1", side="ASK")
    assert book.place_order(order1) == "OK"
    result = book.place_order(order2)
    assert result != "OK"


def test_match_orders_full_fill():
    book = OrderBook()
    bid = make_order(side="BID", quantity=100, price=10)
    ask = make_order(side="ASK", quantity=100, price=9)
    book.place_order(bid)
    book.place_order(ask)
    trades = book.match_orders()
    assert len(trades) == 1
    assert trades[0]["quantity"] == 100
    assert trades[0]["price"] == bid.price  # bid was placed first -> maker
    assert bid.status == OrderStatus.FILLED
    assert ask.status == OrderStatus.FILLED
    assert not book.bids
    assert not book.asks


def test_match_orders_partial_fill():
    book = OrderBook()
    bid = make_order(side="BID", quantity=100, price=10)
    ask = make_order(side="ASK", quantity=60, price=9)
    book.place_order(bid)
    book.place_order(ask)
    trades = book.match_orders()
    assert len(trades) == 1
    assert trades[0]["quantity"] == 60
    assert bid.status == OrderStatus.PARTIALLY_FILLED
    assert bid.remaining_quantity == 40
    assert ask.status == OrderStatus.FILLED
    assert bid in book.bids
    assert ask not in book.asks


def test_match_orders_no_match():
    book = OrderBook()
    bid = make_order(side="BID", quantity=100, price=9)
    ask = make_order(side="ASK", quantity=100, price=10)
    book.place_order(bid)
    book.place_order(ask)
    trades = book.match_orders()
    assert trades == []
    assert bid in book.bids
    assert ask in book.asks


def test_price_time_priority():
    book = OrderBook()
    ask1 = make_order(participant_id="P1", side="ASK", quantity=50, price=9)
    time.sleep(0.001)
    ask2 = make_order(participant_id="P2", side="ASK", quantity=50, price=9)
    book.place_order(ask1)
    book.place_order(ask2)

    bid = make_order(participant_id="P3", side="BID", quantity=50, price=10)
    book.place_order(bid)

    trades = book.match_orders()
    assert len(trades) == 1
    assert trades[0]["sell_order_id"] == ask1.order_id
    assert ask1.status == OrderStatus.FILLED
    assert ask2.status == OrderStatus.OPEN


def test_cancel_order_valid():
    book = OrderBook()
    order = make_order()
    book.place_order(order)
    result = book.cancel_order(order.order_id, order.participant_id)
    assert result == "OK"
    assert order.status == OrderStatus.CANCELLED
    assert order not in book.bids


def test_cancel_filled_order_fails():
    book = OrderBook()
    bid = make_order(side="BID", quantity=100, price=10)
    ask = make_order(side="ASK", quantity=100, price=9)
    book.place_order(bid)
    book.place_order(ask)
    book.match_orders()

    result = book.cancel_order(bid.order_id, bid.participant_id)
    assert result != "OK"
    assert bid.status == OrderStatus.FILLED


def test_modify_wrong_participant_fails():
    book = OrderBook()
    order = make_order(participant_id="P1")
    book.place_order(order)
    result = book.modify_order(order.order_id, "P2", 50, 100.0)
    assert result != "OK"
    assert order.quantity == 100
    assert order.price == 175.0
