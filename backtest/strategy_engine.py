import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from models import WatchlistItem, Trade
from config import StrategyConfig
import uuid
import logging

logger = logging.getLogger(__name__)

class StrategyEngine:
    """Ядро стратегии - детект пампа и управление watchlist"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.watchlist: Dict[str, WatchlistItem] = {}
        
    def scan_for_pumps(self, symbol: str, df: pd.DataFrame, current_idx: int) -> Optional[WatchlistItem]:
        """
        Сканирование на предмет пампа
        Памп: рост >= pump_threshold от цены pump_window свечей назад
        """
        if current_idx < self.config.pump_window:
            return None
            
        # Цена N свечей назад
        start_idx = current_idx - self.config.pump_window
        start_price = df.iloc[start_idx]['close']
        
        # Максимальная цена в окне
        window = df.iloc[start_idx:current_idx + 1]
        max_idx = window['high'].idxmax()
        max_price = window.loc[max_idx, 'high']
        
        # Расчет роста
        pump_percent = (max_price - start_price) / start_price
        
        if pump_percent >= self.config.pump_threshold:
            # Нашли памп
            if not self.config.no_prints:
                print(f"  🚀 {symbol}: Памп {pump_percent*100:.1f}% на свече {current_idx}")
            return WatchlistItem(
                symbol=symbol,
                pump_start_idx=start_idx,
                pump_end_idx=current_idx,
                local_high=max_price,
                local_high_idx=max_idx,
                pump_price_start=start_price,
                pump_percent=pump_percent * 100,
                added_time_idx=current_idx,
                last_high_update_idx=current_idx
            )
        return None
    
    def update_watchlist(self, df: pd.DataFrame, current_idx: int) -> List[WatchlistItem]:
        """
        Обновление watchlist:
        1. Проверка обновления localHigh
        2. Проверка stall condition
        3. Удаление устаревших
        """
        ready_for_entry = []
        
        for symbol in list(self.watchlist.keys()):
            item = self.watchlist[symbol]
            
            # Проверка на таймаут (24 часа)
            if current_idx - item.added_time_idx >= self.config.watchlist_timeout:
                if not self.config.no_prints:
                    print(f"  ⏰ {symbol}: Таймаут watchlist")
                del self.watchlist[symbol]
                continue
            
            # Текущая свеча
            current_candle = df.iloc[current_idx]
            
            # Обновление localHigh
            if current_candle['high'] > item.local_high:
                if not self.config.no_prints:
                    print(f"  📈 {symbol}: Обновление high {item.local_high:.4f} -> {current_candle['high']:.4f}")
                item.local_high = current_candle['high']
                item.local_high_idx = current_idx
                item.last_high_update_idx = current_idx
                item.stall_counter = 0
            else:
                item.stall_counter += 1
                if item.stall_counter == self.config.stall_bars:
                    if not self.config.no_prints:
                        print(f"  ⏸️ {symbol}: Stall condition met ({item.stall_counter} свечей без обновления)")
            
            # Проверка stall condition
            if item.stall_counter >= self.config.stall_bars:
                # Готов к входу
                ready_for_entry.append(item)
                
        return ready_for_entry
    
    def check_entry_conditions(self, item: WatchlistItem, df: pd.DataFrame, 
                          current_idx: int, position_manager) -> Optional[Trade]:
        """
        Проверка условий для входа
        """
        # Проверяем, нет ли уже открытой позиции на этот символ
        if item.symbol in position_manager.positions:
            if not self.config.no_prints:
                print(f"  ⚠️ {item.symbol}: Уже есть открытая позиция, пропускаем")
            return None
        
        current_candle = df.iloc[current_idx]
        
        # Расчет TP от localHigh
        tp_price = item.local_high * (1 - self.config.tp_percent)
        
        # Проверка: не входить если цена уже ниже TP
        if current_candle['close'] <= tp_price:
            if not self.config.no_prints:
                print(f"  ⏭️ {item.symbol}: Пропуск - цена уже ниже TP")
            return None
        
        # SL = entry * 2
        entry_price = current_candle['close'] * (1 + self.config.slippage)
        sl_price = entry_price * self.config.sl_multiplier
        if not self.config.no_prints:
            print(f"  ✅ {item.symbol}: Условия выполнены, вход по {entry_price:.4f}")
        
        trade = Trade(
            symbol=item.symbol,
            trade_id=f"{item.symbol}_{current_idx}_{uuid.uuid4().hex[:8]}",
            entry_time=current_candle['timestamp'],
            entry_idx=current_idx,
            entry_price=entry_price,
            entry_fee = self.config.trade_size_usdt * self.config.taker_fee,
            slippage_entry=self.config.slippage,
            local_high=item.local_high,
            pump_start_time=df.iloc[item.pump_start_idx]['timestamp'],
            pump_end_time=df.iloc[item.pump_end_idx]['timestamp'],
            pump_percent=item.pump_percent,
            tp_price=tp_price,
            sl_price=sl_price
        )
        
        del self.watchlist[item.symbol]
        return trade
    
    def add_to_watchlist(self, item: WatchlistItem):
        """Добавление монеты в watchlist"""
        self.watchlist[item.symbol] = item
        if not self.config.no_prints:
            print(f"  📋 {item.symbol}: Добавлен в watchlist")