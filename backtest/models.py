from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import pandas as pd
import numpy as np

@dataclass
class WatchlistItem:
    """Элемент watchlist"""
    symbol: str
    pump_start_idx: int
    pump_end_idx: int
    local_high: float
    local_high_idx: int
    pump_price_start: float
    pump_percent: float
    added_time_idx: int
    last_high_update_idx: int
    stall_counter: int = 0
    active: bool = True
    
@dataclass
class Trade:
    """Информация о сделке"""
    # Идентификаторы
    symbol: str
    trade_id: str
    
    # Вход
    entry_time: datetime
    entry_idx: int
    entry_price: float
    entry_fee: float
    slippage_entry: float
    
    # Параметры стратегии
    local_high: float
    pump_start_time: datetime
    pump_end_time: datetime
    pump_percent: float
    
    # TP/SL - ЭТИ ПОЛЯ ДОЛЖНЫ БЫТЬ ПОСЛЕ ПАРАМЕТРОВ СТРАТЕГИИ
    tp_price: float
    sl_price: float
    
    # Размер позиции - ПОСЛЕ TP/SL
    position_size: float = 0.0
    
    # Выход
    exit_time: Optional[datetime] = None
    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    exit_fee: Optional[float] = None
    slippage_exit: Optional[float] = None
    exit_reason: Optional[str] = None
    
    # Финансовые результаты
    pnl_usdt: Optional[float] = None
    pnl_percent: Optional[float] = None
    funding_paid: float = 0.0
    fees_total: Optional[float] = None
    slippage_total: Optional[float] = None
    
    # Длительность
    duration_bars: Optional[int] = None
    duration_minutes: Optional[int] = None
    
    # MFE/MAE
    mfe: Optional[float] = None  # Max Favorable Excursion (макс прибыль)
    mae: Optional[float] = None  # Max Adverse Excursion (макс убыток)
    
    def calculate_metrics(self, df: pd.DataFrame):
        """Расчет MFE/MAE и других метрик после закрытия"""
        if self.exit_idx is not None and self.entry_idx is not None:
            segment = df.iloc[self.entry_idx:self.exit_idx + 1]
            if len(segment) > 0:
                # Для шорта: MFE - минимальная цена (наибольшая прибыль)
                min_price = segment['low'].min()
                self.mfe = (min_price - self.entry_price) * 100 / self.entry_price
                
                # MAE - максимальная цена (наибольший убыток)
                max_price = segment['high'].max()
                self.mae = (max_price - self.entry_price) * 100 / self.entry_price