"""Trade blotter persistence and exchange reconciliation.

Persists executed trades to a SQLite database, loads exchange
confirmation feeds, and reconciles the two to detect breaks such as
missing confirmations, quantity/price mismatches, duplicates, and
timestamp inconsistencies.
"""

import csv
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List


class BreakType:
    MISSING_CONFIRM = "MISSING_CONFIRM"
    QTY_MISMATCH = "QTY_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    DUPLICATE = "DUPLICATE"
    TIMESTAMP_ERROR = "TIMESTAMP_ERROR"


class TradeStatus:
    PENDING_CONFIRM = "PENDING_CONFIRM"
    CONFIRMED = "CONFIRMED"
    BREAK = "BREAK"


PRICE_TOLERANCE = 0.01


class TradeBlotter:
    def __init__(self, db_path: str = "data/blotter.db") -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                buy_order_id TEXT,
                sell_order_id TEXT,
                security_id TEXT,
                quantity INTEGER,
                price REAL,
                timestamp TEXT,
                status TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS breaks (
                break_id TEXT PRIMARY KEY,
                trade_id TEXT,
                break_type TEXT,
                description TEXT,
                detected_at TEXT
            )
            """
        )
        self.conn.commit()

    def log_trade(self, trade: dict) -> None:
        cur = self.conn.cursor()
        timestamp = trade["timestamp"]
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        cur.execute(
            """
            INSERT INTO trades
                (trade_id, buy_order_id, sell_order_id, security_id,
                 quantity, price, timestamp, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade["trade_id"],
                trade["buy_order_id"],
                trade["sell_order_id"],
                trade["security_id"],
                trade["quantity"],
                trade["price"],
                timestamp,
                TradeStatus.PENDING_CONFIRM,
            ),
        )
        self.conn.commit()

    def load_exchange_confirms(self, filepath: str) -> List[dict]:
        confirms = []
        with open(filepath, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                confirms.append(
                    {
                        "confirm_id": row["confirm_id"],
                        "trade_id": row["trade_id"],
                        "quantity": int(row["quantity"]),
                        "price": float(row["price"]),
                        "timestamp": row["timestamp"],
                    }
                )
        return confirms

    def _record_break(self, trade_id: str, break_type: str, description: str) -> dict:
        break_row = {
            "break_id": str(uuid.uuid4()),
            "trade_id": trade_id,
            "break_type": break_type,
            "description": description,
            "detected_at": datetime.now().isoformat(),
        }
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO breaks (break_id, trade_id, break_type, description, detected_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                break_row["break_id"],
                break_row["trade_id"],
                break_row["break_type"],
                break_row["description"],
                break_row["detected_at"],
            ),
        )
        self.conn.commit()
        return break_row

    def _set_trade_status(self, trade_id: str, status: str) -> None:
        cur = self.conn.cursor()
        cur.execute("UPDATE trades SET status = ? WHERE trade_id = ?", (status, trade_id))
        self.conn.commit()

    def reconcile(self, confirms_filepath: str = "data/exchange_confirms.csv") -> List[dict]:
        breaks: List[dict] = []
        trades = self.get_all_trades()
        confirms = self.load_exchange_confirms(confirms_filepath)

        confirms_by_trade_id: Dict[str, list] = {}
        for confirm in confirms:
            confirms_by_trade_id.setdefault(confirm["trade_id"], []).append(confirm)

        seen_trade_ids = set()
        for confirm in confirms:
            if confirm["trade_id"] in seen_trade_ids:
                breaks.append(
                    self._record_break(
                        confirm["trade_id"],
                        BreakType.DUPLICATE,
                        f"Duplicate confirm found for trade {confirm['trade_id']}",
                    )
                )
            seen_trade_ids.add(confirm["trade_id"])

        seen_blotter_ids = set()
        for trade in trades:
            trade_id = trade["trade_id"]
            if trade_id in seen_blotter_ids:
                breaks.append(
                    self._record_break(
                        trade_id,
                        BreakType.DUPLICATE,
                        f"Duplicate trade found in blotter for trade {trade_id}",
                    )
                )
            seen_blotter_ids.add(trade_id)

            matching_confirms = confirms_by_trade_id.get(trade_id, [])
            if not matching_confirms:
                breaks.append(
                    self._record_break(
                        trade_id,
                        BreakType.MISSING_CONFIRM,
                        f"No exchange confirm found for trade {trade_id}",
                    )
                )
                self._set_trade_status(trade_id, TradeStatus.BREAK)
                continue

            confirm = matching_confirms[0]
            trade_has_break = False

            if confirm["quantity"] != trade["quantity"]:
                breaks.append(
                    self._record_break(
                        trade_id,
                        BreakType.QTY_MISMATCH,
                        f"Blotter quantity {trade['quantity']} != confirm "
                        f"quantity {confirm['quantity']} for trade {trade_id}",
                    )
                )
                trade_has_break = True

            if abs(confirm["price"] - trade["price"]) > PRICE_TOLERANCE:
                breaks.append(
                    self._record_break(
                        trade_id,
                        BreakType.PRICE_MISMATCH,
                        f"Blotter price {trade['price']} != confirm "
                        f"price {confirm['price']} for trade {trade_id}",
                    )
                )
                trade_has_break = True

            trade_ts = _parse_timestamp(trade["timestamp"])
            confirm_ts = _parse_timestamp(confirm["timestamp"])
            if trade_ts is not None and confirm_ts is not None and confirm_ts < trade_ts:
                breaks.append(
                    self._record_break(
                        trade_id,
                        BreakType.TIMESTAMP_ERROR,
                        f"Confirm timestamp {confirm['timestamp']} is before "
                        f"trade timestamp {trade['timestamp']} for trade {trade_id}",
                    )
                )
                trade_has_break = True

            self._set_trade_status(
                trade_id, TradeStatus.BREAK if trade_has_break else TradeStatus.CONFIRMED
            )

        total_buy_qty = sum(t["quantity"] for t in trades)
        total_sell_qty = sum(t["quantity"] for t in trades)
        if total_buy_qty != total_sell_qty:
            breaks.append(
                self._record_break(
                    "GLOBAL",
                    BreakType.QTY_MISMATCH,
                    f"Total buy quantity {total_buy_qty} != total sell "
                    f"quantity {total_sell_qty}",
                )
            )

        return breaks

    def get_breaks(self) -> List[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM breaks")
        return [dict(row) for row in cur.fetchall()]

    def get_all_trades(self) -> List[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM trades")
        return [dict(row) for row in cur.fetchall()]


def _parse_timestamp(value: str):
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
