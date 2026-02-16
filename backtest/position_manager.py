import pandas as pd
from typing import Dict, Optional, Tuple, List
from models import Trade
from config import StrategyConfig
from risk_manager import RiskManager


class PositionManager:
    """Управление открытыми позициями, TP/SL и принудительным закрытием"""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.positions: Dict[str, Trade] = {}  # symbol -> Trade
        self.risk_manager = RiskManager(initial_capital=config.initial_capital)

    def get_position_size(self, symbol: str) -> float:
        """
        Получить размер позиции с учетом риск-менеджера
        """
        base_size = self.config.trade_size_usdt
        multiplier = self.risk_manager.get_position_multiplier(symbol)
        return base_size * multiplier

    def open_position(self, trade: Trade, df: pd.DataFrame, idx: int) -> Tuple[bool, Optional[str]]:
        """Открытие позиции."""
        candle = df.iloc[idx]

        # Устанавливаем размер позиции через риск-менеджер
        trade.position_size = self.get_position_size(trade.symbol)
        
        # Пересчитываем комиссии с новым размером
        trade.entry_fee = trade.position_size * self.config.taker_fee

        # SL для шорта
        if float(candle["high"]) >= float(trade.sl_price):
            exit_price = float(trade.sl_price) * (1 + self.config.slippage)
            print(f"🔴 SL НА ВХОДЕ {trade.symbol}: high={float(candle['high']):.4f} >= sl={float(trade.sl_price):.4f}")
            self.close_position(trade.symbol, idx, exit_price, "sl", candle, df)
            
            # Обновляем риск-менеджер после убытка
            self.risk_manager.on_trade_result(
                pnl_usdt=trade.pnl_usdt if trade.pnl_usdt else 0,
                pnl_percent=trade.pnl_percent if trade.pnl_percent else 0,
                symbol=trade.symbol
            )
            return False, "sl_immediate"

        # TP для шорта
        if float(candle["low"]) <= float(trade.tp_price):
            exit_price = float(trade.tp_price) * (1 + self.config.slippage)
            print(f"🟢 TP НА ВХОДЕ {trade.symbol}: low={float(candle['low']):.4f} <= tp={float(trade.tp_price):.4f}")
            self.close_position(trade.symbol, idx, exit_price, "tp", candle, df)
            
            # Обновляем риск-менеджер после прибыли
            self.risk_manager.on_trade_result(
                pnl_usdt=trade.pnl_usdt if trade.pnl_usdt else 0,
                pnl_percent=trade.pnl_percent if trade.pnl_percent else 0,
                symbol=trade.symbol
            )
            return False, "tp_immediate"

        self.positions[trade.symbol] = trade
        return True, None

    def check_positions(self, df: pd.DataFrame, idx: int) -> Dict[str, str]:
        """Проверка всех открытых позиций на TP/SL"""
        closed: Dict[str, str] = {}
        candle = df.iloc[idx]

        for symbol in list(self.positions.keys()):
            trade = self.positions[symbol]

            # SL для шорта
            if float(candle["high"]) >= float(trade.sl_price):
                print(f"🔴 SL {symbol}: high={float(candle['high']):.4f} >= sl={float(trade.sl_price):.4f}")
                exit_price = float(trade.sl_price) * (1 + self.config.slippage)
                self.close_position(symbol, idx, exit_price, "sl", candle, df)
                
                # Обновляем риск-менеджер
                self.risk_manager.on_trade_result(
                    pnl_usdt=trade.pnl_usdt if trade.pnl_usdt else 0,
                    pnl_percent=trade.pnl_percent if trade.pnl_percent else 0,
                    symbol=trade.symbol
                )
                closed[symbol] = "sl"
                continue

            # TP для шорта
            if float(candle["low"]) <= float(trade.tp_price):
                print(f"🟢 TP {symbol}: low={float(candle['low']):.4f} <= tp={float(trade.tp_price):.4f}")
                exit_price = float(trade.tp_price) * (1 + self.config.slippage)
                self.close_position(symbol, idx, exit_price, "tp", candle, df)
                
                # Обновляем риск-менеджер
                self.risk_manager.on_trade_result(
                    pnl_usdt=trade.pnl_usdt if trade.pnl_usdt else 0,
                    pnl_percent=trade.pnl_percent if trade.pnl_percent else 0,
                    symbol=trade.symbol
                )
                closed[symbol] = "tp"
                continue

        return closed

    def force_close_all(self, df: pd.DataFrame, idx: int, reason: str = "eod") -> List[Trade]:
        """Принудительно закрыть все открытые позиции"""
        closed_trades: List[Trade] = []
        if not self.positions:
            return closed_trades

        candle = df.iloc[idx]
        print(f"⏰ Принудительное закрытие {len(self.positions)} позиций: {reason}")

        for symbol in list(self.positions.keys()):
            exit_price = float(candle["close"]) * (1 + self.config.slippage)
            trade = self.positions.get(symbol)
            if trade is None:
                continue

            self.close_position(symbol, idx, exit_price, reason, candle, df)
            
            # Обновляем риск-менеджер
            self.risk_manager.on_trade_result(
                pnl_usdt=trade.pnl_usdt if trade.pnl_usdt else 0,
                pnl_percent=trade.pnl_percent if trade.pnl_percent else 0,
                symbol=trade.symbol
            )
            closed_trades.append(trade)

        return closed_trades

    def close_position(self, symbol: str, idx: int, exit_price: float,
                      reason: str, candle: pd.Series, df: pd.DataFrame):
        """Закрытие позиции и расчет PnL"""
        if symbol not in self.positions:
            return

        trade = self.positions[symbol]

        # Выход
        trade.exit_time = candle["timestamp"]
        trade.exit_idx = idx
        trade.exit_price = float(exit_price)
        trade.exit_reason = reason
        trade.slippage_exit = self.config.slippage

        # Комиссии (используем trade.position_size)
        if not hasattr(trade, 'position_size') or not trade.position_size:
            trade.position_size = self.config.trade_size_usdt
            
        trade.entry_fee = trade.position_size * self.config.taker_fee
        trade.exit_fee = trade.position_size * self.config.taker_fee
        trade.fees_total = trade.entry_fee + trade.exit_fee
        trade.slippage_total = (trade.slippage_entry or 0) + (trade.slippage_exit or 0)

        # PnL (используем trade.position_size)
        price_diff = float(trade.entry_price) - float(trade.exit_price)
        trade.pnl_usdt = (price_diff / float(trade.entry_price)) * trade.position_size
        trade.pnl_usdt -= trade.fees_total
        trade.pnl_usdt -= trade.slippage_total

        trade.pnl_percent = (trade.pnl_usdt / trade.position_size) * 100.0

        # Длительность
        trade.duration_bars = idx - int(trade.entry_idx)
        trade.duration_minutes = int(trade.duration_bars) * 15

        # MFE/MAE
        trade.calculate_metrics(df)

        print(f"💰 {symbol} {reason}: PnL={trade.pnl_usdt:.2f} USDT ({trade.pnl_percent:.1f}%) | Размер: ${trade.position_size:.2f}")

        # Удаляем из активных
        del self.positions[symbol]