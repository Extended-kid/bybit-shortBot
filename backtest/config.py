from dataclasses import dataclass
from typing import Optional

@dataclass
class StrategyConfig:
    """Параметры стратегии"""
    
    no_prints: bool = False  # По умолчанию печатаем
    # Временные параметры
    timeframe: str = '15m'
    lookback_period: int = 96  # 24 часа в 15м свечах
    
    # Параметры пампа
    pump_threshold: float = 0.20  # 20% рост (смягчили)
    pump_window: int = 96  # N свечей назад для расчета пампа
    
    # Параметры стагнации
    stall_bars: int = 2  # Свечи без обновления high (смягчили)
    
    # TP/SL
    tp_percent: float = 0.15  # 15% от localHigh (смягчили)
    sl_multiplier: float = 2.0  # x2 от entry 
    
    # Риск-менеджмент
    trade_size_usdt: float = 20.0
    initial_capital: float = 1000.0
    max_concurrent_trades: int = float('inf')
    
    # Комиссии и проскальзывание
    maker_fee: float = 0.0001  # 0.01%
    taker_fee: float = 0.0006  # 0.06%
    slippage: float = 0.0005   # 0.05%
    
    # Funding
    use_funding: bool = False  # Пока отключено
    funding_check_interval: int = 8
    
    # Watchlist timeout (в свечах)
    watchlist_timeout: int = 96  # 24 часа
    
    # Пути сохранения
    output_dir: str = './backtest_results'