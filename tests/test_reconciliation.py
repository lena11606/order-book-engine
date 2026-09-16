"""Unit tests for TradeBlotter reconciliation logic."""

import csv
import os
from datetime import datetime, timedelta

import pytest

from src.blotter import BreakType, TradeBlotter, TradeStatus


@pytest.fixture
def blotter(tmp_path):
    db_path = os.path.join(tmp_path, "blotter.db")
    b = TradeBlotter(db_path=db_path)
    yield b
    b.conn.close()


def write_confirms(tmp_path, rows):
    filepath = os.path.join(tmp_path, "confirms.csv")
    fieldnames = ["confirm_id", "trade_id", "quantity", "price", "timestamp"]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return filepath


def make_trade(trade_id, quantity=100, price=50.0, timestamp=None):
    return {
        "trade_id": trade_id,
        "buy_order_id": "BUY-1",
        "sell_order_id": "SELL-1",
        "security_id": "AAPL",
        "quantity": quantity,
        "price": price,
        "timestamp": timestamp or datetime(2026, 9, 16, 9, 30, 0),
    }


def test_missing_confirm_detected(blotter, tmp_path):
    trade = make_trade("T1")
    blotter.log_trade(trade)
    confirms_path = write_confirms(tmp_path, [])

    breaks = blotter.reconcile(confirms_path)
    break_types = [b["break_type"] for b in breaks]
    assert BreakType.MISSING_CONFIRM in break_types

    trades = blotter.get_all_trades()
    assert trades[0]["status"] == TradeStatus.BREAK


def test_qty_mismatch_detected(blotter, tmp_path):
    trade = make_trade("T1", quantity=100)
    blotter.log_trade(trade)
    confirms_path = write_confirms(
        tmp_path,
        [
            {
                "confirm_id": "C1",
                "trade_id": "T1",
                "quantity": 90,
                "price": 50.0,
                "timestamp": (trade["timestamp"] + timedelta(seconds=1)).isoformat(),
            }
        ],
    )

    breaks = blotter.reconcile(confirms_path)
    break_types = [b["break_type"] for b in breaks]
    assert BreakType.QTY_MISMATCH in break_types


def test_price_mismatch_detected(blotter, tmp_path):
    trade = make_trade("T1", price=50.0)
    blotter.log_trade(trade)
    confirms_path = write_confirms(
        tmp_path,
        [
            {
                "confirm_id": "C1",
                "trade_id": "T1",
                "quantity": 100,
                "price": 55.0,
                "timestamp": (trade["timestamp"] + timedelta(seconds=1)).isoformat(),
            }
        ],
    )

    breaks = blotter.reconcile(confirms_path)
    break_types = [b["break_type"] for b in breaks]
    assert BreakType.PRICE_MISMATCH in break_types


def test_confirmed_trade_marked_correctly(blotter, tmp_path):
    trade = make_trade("T1", quantity=100, price=50.0)
    blotter.log_trade(trade)
    confirms_path = write_confirms(
        tmp_path,
        [
            {
                "confirm_id": "C1",
                "trade_id": "T1",
                "quantity": 100,
                "price": 50.0,
                "timestamp": (trade["timestamp"] + timedelta(seconds=1)).isoformat(),
            }
        ],
    )

    breaks = blotter.reconcile(confirms_path)
    assert breaks == []

    trades = blotter.get_all_trades()
    assert trades[0]["status"] == TradeStatus.CONFIRMED
