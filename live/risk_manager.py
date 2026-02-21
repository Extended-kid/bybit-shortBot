from datetime import datetime

# risk_manager.py

class RiskManager:
    """Управление рисками на основе истории монеты"""
    
    def __init__(self, initial_capital=10000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        self.today_pnl = 0
        self.current_date = None
        self.coin_stats = {}  # История по каждой монете
        self.consecutive_losses = 0
        self.trades_history = []  # список закрытых сделок
        
    def update_stats(self, symbol, pnl_percent):
        """Обновляем статистику по монете"""
        if symbol not in self.coin_stats:
            self.coin_stats[symbol] = {
                'trades': 0,
                'profitable': 0,
                'total_pnl': 0,
                'max_loss': 0
            }
        
        stats = self.coin_stats[symbol]
        stats['trades'] += 1
        stats['total_pnl'] += pnl_percent
        
        if pnl_percent > 0:
            stats['profitable'] += 1
        else:
            stats['max_loss'] = min(stats['max_loss'], pnl_percent)
    
    def get_position_multiplier(self, symbol):
        """
        Возвращает множитель размера позиции:
        1.0 = полный размер (1% от капитала)
        0.5 = половинный размер (0.5%)
        0.25 = четверть размера (0.25%)
        """
        if symbol not in self.coin_stats:
            return 0.5  # Новая монета - половинный риск
        
        stats = self.coin_stats[symbol]
        
        # Если меньше 3 сделок - консервативно
        if stats['trades'] < 3:
            return 0.5
        
        # Если были сильные убытки (хуже -200%)
        if stats['max_loss'] < -200:
            return 0.25
        
        # Если винрейт меньше 70%
        win_rate = stats['profitable'] / stats['trades']
        if win_rate < 0.7:
            return 0.5
        
        return 1.0  # Надежная монета
    
    def can_trade_today(self, date, pnl_today=None):
        """Проверка дневных лимитов"""
        if self.current_date != date:
            self.current_date = date
            self.today_pnl = 0
        
        if pnl_today:
            self.today_pnl += pnl_today
        
        # Не торгуем если сегодня убыток больше $500
        if self.today_pnl < -500:
            return False, f"Дневной лимит убытка: {self.today_pnl:.2f}"
        
        # Не торгуем если общая просадка > 20%
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        if drawdown > 0.20:
            return False, f"Просадка {drawdown:.1%} > 20%"
        
        # Не торгуем если 3 убытка подряд
        if self.consecutive_losses >= 3:
            return False, f"3 убытка подряд"
        
        return True, "OK"
    
    def on_trade_result(self, pnl_usdt, pnl_percent, symbol):
        self.current_capital += pnl_usdt
        self.today_pnl += pnl_usdt
        
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        if pnl_usdt < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        self.update_stats(symbol, pnl_percent)
        
        # Добавляем сделку в историю
        self.trades_history.append({
            'time': datetime.now().isoformat(),
            'symbol': symbol,
            'pnl_usdt': pnl_usdt,
            'pnl_percent': pnl_percent
        })
        # Храним только последние 1000 сделок
        if len(self.trades_history) > 1000:
            self.trades_history = self.trades_history[-1000:]