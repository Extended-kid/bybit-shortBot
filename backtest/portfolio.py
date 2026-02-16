from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from models import Trade
from config import StrategyConfig

class Portfolio:
    """Управление капиталом и позициями"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.initial_capital = config.initial_capital
        self.current_capital = config.initial_capital
        self.peak_capital = config.initial_capital
        self.trades: List[Trade] = []
        
        # Для equity curve
        self.equity_history: List[dict] = []
        
    def can_open_position(self) -> bool:
        """Проверка лимита позиций и достаточности капитала"""
        return self.current_capital >= self.config.trade_size_usdt
    
    def add_trade(self, trade: Trade):
        """Добавление сделки в портфель"""
        self.trades.append(trade)
        
    def update_capital(self, trade: Trade):
        """Обновление капитала после закрытия сделки"""
        self.current_capital += trade.pnl_usdt
        self.peak_capital = max(self.peak_capital, self.current_capital)
    
    def get_total_equity(self, current_prices: Dict[str, float] = None) -> float:
        """
        Расчет общей стоимости портфеля с учетом открытых позиций
        
        Args:
            current_prices: Словарь {symbol: current_price} для оценки открытых позиций
        """
        total = self.current_capital
        
        for trade in self.trades:
            if trade.exit_time is None:  # Открытая позиция
                if current_prices and trade.symbol in current_prices:
                    # Реальная цена
                    current_price = current_prices[trade.symbol]
                    unrealized = (trade.entry_price - current_price) / trade.entry_price * self.config.trade_size_usdt
                    total += unrealized
                else:
                    # Если нет текущей цены, используем последнюю известную
                    unrealized = trade.pnl_usdt if trade.pnl_usdt else 0
                    total += unrealized
        
        return total
    
    def get_open_positions_value(self) -> float:
        """Суммарная стоимость открытых позиций"""
        return len([t for t in self.trades if t.exit_time is None]) * self.config.trade_size_usdt
    
    def record_snapshot(self, timestamp, idx: int, current_prices: Dict[str, float] = None):
        """Запись состояния портфеля для equity curve"""
        total_equity = self.get_total_equity(current_prices)
        
        self.equity_history.append({
            'timestamp': timestamp,
            'idx': idx,
            'equity': total_equity,
            'cash': self.current_capital,
            'open_positions_value': self.get_open_positions_value(),
            'open_positions_count': len([t for t in self.trades if t.exit_time is None]),
            'drawdown': (self.peak_capital - total_equity) / self.peak_capital * 100 if self.peak_capital > 0 else 0
        })
        
        self.peak_capital = max(self.peak_capital, total_equity)
        
    def get_metrics(self) -> dict:
        """Расчет агрегированных метрик портфеля"""
        closed_trades = [t for t in self.trades if t.exit_time is not None]
        open_trades = [t for t in self.trades if t.exit_time is None]
        
        if not closed_trades and not open_trades:
            return {}
        
        # Считаем реализованную прибыль
        realized_profits = [t.pnl_usdt for t in closed_trades if t.pnl_usdt > 0]
        realized_losses = [t.pnl_usdt for t in closed_trades if t.pnl_usdt <= 0]
        
        # Считаем нереализованную прибыль (если есть текущие цены)
        unrealized_pnl = sum(t.pnl_usdt for t in open_trades if t.pnl_usdt) if open_trades else 0
        
        total_pnl = sum(t.pnl_usdt for t in closed_trades) + unrealized_pnl
        win_trades = len([t for t in closed_trades if t.pnl_usdt > 0])
        loss_trades = len([t for t in closed_trades if t.pnl_usdt <= 0])
        
        metrics = {
            'total_trades': len(closed_trades),
            'open_trades': len(open_trades),
            'win_trades': win_trades,
            'loss_trades': loss_trades,
            'win_rate': win_trades / len(closed_trades) * 100 if closed_trades else 0,
            'total_pnl_usdt': total_pnl,
            'realized_pnl_usdt': sum(t.pnl_usdt for t in closed_trades),
            'unrealized_pnl_usdt': unrealized_pnl,
            'total_pnl_percent': (total_pnl / self.initial_capital) * 100,
            'avg_win': np.mean(realized_profits) if realized_profits else 0,
            'avg_loss': np.mean(realized_losses) if realized_losses else 0,
            'profit_factor': abs(sum(realized_profits) / sum(realized_losses)) if realized_losses and sum(realized_losses) != 0 else float('inf'),
            'max_drawdown': max([e['drawdown'] for e in self.equity_history]) if self.equity_history else 0,
            'final_capital': self.current_capital + unrealized_pnl,
            'final_cash': self.current_capital,
            'expectancy': np.mean([t.pnl_usdt for t in closed_trades]) if closed_trades else 0,
        }
        
        return metrics