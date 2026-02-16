# Bybit Short Strategy Bot

Trading bot for USDT-perpetual futures on Bybit.
Strategy: detect pumped coins (>=25% in 24h) and enter short on stall.

## Quick Start

1. Clone repository
2. cp .env.example .env and fill API keys
3. pip install -r requirements.txt
4. python bot.py

## Backtest Results (2025-2026)
- Return: +285%
- Win rate: 91.4%
- Trades: 2,198

## Configuration
See config.py

## Structure
- ot.py - main bot file
- live/ - live trading modules
- acktest/ - backtester
- data/ - state and history (persistent disk)
