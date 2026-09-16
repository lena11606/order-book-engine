# order-book-engine

A price-time priority order book, trade blotter, and validation engine — simulating trading desk operations infrastructure end to end.

![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![pytest](https://img.shields.io/badge/tests-pytest-green) ![stdlib](https://img.shields.io/badge/dependencies-standard%20library-lightgrey)

## Overview

Simulates the order management and trade reconciliation infrastructure used by trading desk operations teams at high-frequency trading firms and market makers. Built to demonstrate competency in exchange message protocols, price-time priority matching, order lifecycle management, and financial data reconciliation.

## Architecture

```
 Trading Firm                          Exchange
 ┌────────────┐   OrderEntryRequest   ┌──────────────────┐
 │            │ ────────────────────► │                  │
 │ Participant│   OrderModification   │    OrderBook      │
 │            │ ────────────────────► │  (matching engine)│
 │            │   OrderCancellation   │                  │
 │            │ ────────────────────► │                  │
 │            │                       │                  │
 │            │  ◄──────────────────  │                  │
 └────────────┘   OrderConfirmation   └────────┬─────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │ Order State       │
                                       │ Machine (Order)    │
                                       └────────┬─────────┘
                                                │ fills
                                                ▼
                                       ┌──────────────────┐
                                       │  Trade Blotter     │
                                       │   (SQLite)         │
                                       └────────┬─────────┘
                                                │ vs. exchange confirms
                                                ▼
                                       ┌──────────────────┐
                                       │ Reconciliation     │
                                       │ Engine (breaks)    │
                                       └────────┬─────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │ Validation Engine  │
                                       │ (sanity checks)    │
                                       └──────────────────┘
```

## Key Components

| Component | File | Description |
|---|---|---|
| Message Protocol | `src/messages.py` | FIX-style exchange messages: order entry, modification, cancellation, confirmation, crossed-order notification, market data snapshot |
| Order State Machine | `src/order.py` | `Order` dataclass with a 7-state lifecycle (`NEW` → `ACKNOWLEDGED` → `OPEN` → `PARTIALLY_FILLED`/`FILLED`/`CANCELLED`/`REJECTED`) and validated transitions |
| Matching Engine | `src/order_book.py` | Price-time priority limit order book: order entry, modification, cancellation, and matching per security |
| Trade Blotter | `src/blotter.py` | SQLite-backed trade log and exchange-confirm reconciliation with break classification |
| Validation Engine | `src/validator.py` | Order-level, book-level, reconciliation, and sanity checks across the book and blotter |
| Simulation | `main.py` | End-to-end run: place orders → match → log → reconcile → validate → error handling demo |

## Concepts Demonstrated

- Price-time priority matching (maker/resting order sets the execution price)
- FIX-style exchange message protocol
- Order state machine (7 states, explicitly defined valid transitions)
- Trade reconciliation and break classification (`MISSING_CONFIRM`, `QTY_MISMATCH`, `PRICE_MISMATCH`, `DUPLICATE`, `TIMESTAMP_ERROR`)
- Sanity-check validation layer (crossed markets, self-trades, fills worse than limit price, orphaned fills)

## How to Run

```bash
git clone <repo>
cd order-book-engine
pip install -r requirements.txt
python main.py
pytest tests/
```

## Sample Output

```
======================================================================
STEP 5: MATCH ORDERS
======================================================================
  TRADE 20b43b58-... | MSFT | qty=50 | price=417.0 | buy=ORD-007 | sell=ORD-008
  TRADE 5c0fa040-... | MSFT | qty=50 | price=416.0 | buy=ORD-007 | sell=ORD-006
  TRADE e1f4f501-... | AAPL | qty=80 | price=176.0 | buy=ORD-001 | sell=ORD-004
  TRADE 7e7c326b-... | AAPL | qty=20 | price=176.0 | buy=ORD-001 | sell=ORD-002
  Total trades executed: 4

======================================================================
STEP 8: RECONCILE BLOTTER AGAINST EXCHANGE CONFIRMS
======================================================================
  BREAK [MISSING_CONFIRM] trade=20b43b58-...: No exchange confirm found for trade 20b43b58-...
  BREAK [QTY_MISMATCH] trade=5c0fa040-...: Blotter quantity 50 != confirm quantity 55 for trade 5c0fa040-...

======================================================================
STEP 10: DEMONSTRATE INVALID-STATE HANDLING
======================================================================
  cancel_order on FILLED order ORD-001 -> REJECTED: cannot cancel order in status FILLED
  Caught expected ValueError: Invalid transition for order ORD-001: FILLED -> OPEN
  Order history for ORD-001:
    2026-09-16T02:45:41.295005 -> NEW
    2026-09-16T02:45:41.295087 -> ACKNOWLEDGED
    2026-09-16T02:45:41.295088 -> OPEN
    2026-09-16T02:45:41.295223 -> PARTIALLY_FILLED
    2026-09-16T02:45:41.295233 -> FILLED
```

## What I'd Build Next

- Real FIX protocol message format (tag=value encoding over a session layer)
- WebSocket feed via Polygon.io for live market data
- Multi-venue reconciliation across simulated exchanges
- Streamlit dashboard for real-time order book visualization
