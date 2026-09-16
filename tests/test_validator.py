"""Unit tests for the ValidationEngine."""

import os

import pytest

from src.blotter import TradeBlotter
from src.order import Order, OrderStatus
from src.order_book import OrderBook
from src.validator import ValidationEngine


@pytest.fixture
def blotter(tmp_path):
    db_path = os.path.join(tmp_path, "blotter.db")
    b = TradeBlotter(db_path=db_path)
    yield b
    b.conn.close()


def make_order(participant_id="P1", security_id="AAPL", side="BID", quantity=100, price=175.0):
    return Order(
        participant_id=participant_id,
        security_id=security_id,
        side=side,
        quantity=quantity,
        price=price,
    )


def test_crossed_market_detected(blotter):
    book = OrderBook()
    bid = make_order(side="BID", price=100)
    ask = make_order(side="ASK", price=90)
    book.order_registry[bid.order_id] = bid
    book.order_registry[ask.order_id] = ask
    book.bids.append(bid)
    book.asks.append(ask)

    errors = ValidationEngine().validate(book, blotter)
    check_names = [e.check_name for e in errors]
    assert "CROSSED_MARKET" in check_names


def test_filled_order_with_remaining_qty_detected(blotter):
    book = OrderBook()
    order = make_order()
    book.place_order(order)
    order.status = OrderStatus.FILLED  # force inconsistent state
    book.order_registry[order.order_id] = order

    errors = ValidationEngine().validate(book, blotter)
    check_names = [e.check_name for e in errors]
    assert "FILLED_WITH_REMAINING_QTY" in check_names


def test_cancelled_order_still_in_book_detected(blotter):
    book = OrderBook()
    order = make_order()
    book.place_order(order)
    order.status = OrderStatus.CANCELLED  # force inconsistent state without removing from book

    errors = ValidationEngine().validate(book, blotter)
    check_names = [e.check_name for e in errors]
    assert "CANCELLED_ORDER_IN_BOOK" in check_names


def test_self_trade_detected(blotter):
    book = OrderBook()
    bid = make_order(participant_id="SAME", side="BID", price=10)
    ask = make_order(participant_id="SAME", side="ASK", price=9)
    book.place_order(bid)
    book.place_order(ask)
    trades = book.match_orders()
    for trade in trades:
        blotter.log_trade(trade)

    errors = ValidationEngine().validate(book, blotter)
    check_names = [e.check_name for e in errors]
    assert "SELF_TRADE" in check_names


def test_clean_book_has_no_errors(blotter):
    book = OrderBook()
    bid = make_order(participant_id="P1", side="BID", price=10)
    ask = make_order(participant_id="P2", side="ASK", price=9)
    book.place_order(bid)
    book.place_order(ask)
    trades = book.match_orders()
    for trade in trades:
        blotter.log_trade(trade)
        blotter._set_trade_status(trade["trade_id"], "CONFIRMED")

    errors = ValidationEngine().validate(book, blotter)
    critical_errors = [e for e in errors if e.severity == "CRITICAL"]
    assert critical_errors == []
