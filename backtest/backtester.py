import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm
import logging
from numba import njit, prange

from config import StrategyConfig
from models import Trade, WatchlistItem
from strategy_engine import StrategyEngine
from position_manager import PositionManager
from portfolio import Portfolio
from analyzers.metrics import MetricsAnalyzer
from analyzers.exporters import ResultsExporter

logger = logging.getLogger(__name__)


class Backtester:
    """Основной класс бэктестера"""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.strategy = StrategyEngine(config)
        self.position_manager = PositionManager(config)
        self.portfolio = Portfolio(config)
        self.results_exporter = ResultsExporter(config)
        self.all_trades: List[Trade] = []

    def run_on_symbol(self, symbol: str, df: pd.DataFrame) -> List[Trade]:
        """Запуск бэктеста на одном символе"""
        symbol_trades: List[Trade] = []

        high = df["high"].values
        close = df["close"].values
        timestamp = df["timestamp"].values

        n = len(df)
        pump_window = int(self.config.pump_window)
        pump_threshold = float(self.config.pump_threshold)

        # Сбрасываем состояние для каждого символа
        self.strategy.watchlist.clear()
        self.position_manager.positions.clear()

        for idx in range(pump_window, n):
            # 1) поиск пампа (numba)
            pump_item = self.scan_for_pumps_numba(symbol, high, close, idx, pump_window, pump_threshold)
            if pump_item:
                self.strategy.add_to_watchlist(pump_item)

            # 2) обновляем watchlist
            ready_items = self.strategy.update_watchlist(df, idx)

            # 3) входы
            for item in ready_items:
                if self.portfolio.can_open_position():
                    trade = self.strategy.check_entry_conditions(item, df, idx, self.position_manager)
                    if trade:
                        success, _ = self.position_manager.open_position(trade, df, idx)
                        if success:
                            self.portfolio.add_trade(trade)
                            symbol_trades.append(trade)
                            self.all_trades.append(trade)

            # 4) TP/SL
            closed = self.position_manager.check_positions(df, idx)

            # 5) обновляем капитал по закрытым
            for symbol_closed in closed.keys():
                for tr in reversed(self.portfolio.trades):
                    if tr.symbol == symbol_closed and tr.exit_time is not None:
                        self.portfolio.update_capital(tr)
                        break

            # 6) equity snapshots
            if idx % 4 == 0:
                self.portfolio.record_snapshot(timestamp[idx], idx)

        # ✅ ВАЖНО: закрываем все оставшиеся позиции по последней свече
        last_idx = n - 1
        forced_closed = self.position_manager.force_close_all(df, last_idx, reason="eod")

        # ✅ И обновляем капитал по этим forced close
        for tr in forced_closed:
            # tr уже есть в portfolio.trades (мы добавляли при входе)
            # просто обновим капитал
            self.portfolio.update_capital(tr)

        return symbol_trades

    @staticmethod
    @njit
    def detect_pump_numba(
        high: np.ndarray, close: np.ndarray, idx: int, pump_window: int, threshold: float
    ) -> Tuple[float, int, float]:
        start_idx = idx - pump_window
        max_price = high[start_idx]
        max_idx = start_idx

        for i in prange(start_idx + 1, idx + 1):
            if high[i] > max_price:
                max_price = high[i]
                max_idx = i

        start_price = close[start_idx]
        if start_price == 0:
            return 0.0, -1, 0.0

        pump_percent = (max_price - start_price) / start_price
        if pump_percent >= threshold:
            return max_price, max_idx, pump_percent

        return 0.0, -1, 0.0

    def scan_for_pumps_numba(
        self,
        symbol: str,
        high: np.ndarray,
        close: np.ndarray,
        idx: int,
        pump_window: int,
        threshold: float,
    ) -> Optional[WatchlistItem]:
        max_price, max_idx, pump_percent = self.detect_pump_numba(high, close, idx, pump_window, threshold)
        if max_idx == -1:
            return None

        start_idx = idx - pump_window
        return WatchlistItem(
            symbol=symbol,
            pump_start_idx=start_idx,
            pump_end_idx=idx,
            local_high=max_price,
            local_high_idx=max_idx,
            pump_price_start=close[start_idx],
            pump_percent=pump_percent * 100,
            added_time_idx=idx,
            last_high_update_idx=idx,
        )

    def run_multiprocess(self, market_data: Dict[str, pd.DataFrame]) -> List[Trade]:
        """Мультипроцессинговый запуск с joblib (важно: тоже делаем EOD close)"""
        from joblib import Parallel, delayed
        import time
        import sys

        total = len(market_data)
        items = list(market_data.items())

        print(f"\n🚀 Запуск бэктеста на {total} символах (n_jobs=-2)")
        sys.stdout.flush()

        start_time = time.time()

        config_dict = self.config.__dict__.copy()

        def worker(symbol: str, df: pd.DataFrame, cfg: Dict) -> List[Trade]:
            cfg_obj = StrategyConfig(**cfg)
            strategy = StrategyEngine(cfg_obj)
            position_manager = PositionManager(cfg_obj)

            symbol_trades: List[Trade] = []

            strategy.watchlist.clear()
            position_manager.positions.clear()

            pump_window = int(cfg["pump_window"])

            for idx in range(pump_window, len(df)):
                pump_item = strategy.scan_for_pumps(symbol, df, idx)
                if pump_item:
                    strategy.add_to_watchlist(pump_item)

                ready_items = strategy.update_watchlist(df, idx)

                for item in ready_items:
                    trade = strategy.check_entry_conditions(item, df, idx, position_manager)
                    if trade:
                        success, _ = position_manager.open_position(trade, df, idx)
                        if success:
                            symbol_trades.append(trade)

                position_manager.check_positions(df, idx)

            # ✅ закрываем остаток позиций на последней свече
            last_idx = len(df) - 1
            position_manager.force_close_all(df, last_idx, reason="eod")

            return symbol_trades

        results = Parallel(n_jobs=-2, backend="loky")(
            delayed(worker)(symbol, df, config_dict) for symbol, df in tqdm(items, desc="Прогресс")
        )

        all_trades: List[Trade] = []
        for trades in results:
            if trades:
                all_trades.extend(trades)

        elapsed = time.time() - start_time
        print(f"\n✅ Бэктест завершен за {elapsed:.1f}с")
        print(f"📊 Всего сделок: {len(all_trades)}")

        self.all_trades = all_trades
        return all_trades

    def run_sequential(self, market_data: Dict[str, pd.DataFrame]) -> List[Trade]:
        """Последовательный запуск"""
        for symbol, df in tqdm(market_data.items(), desc="Backtesting"):
            self.run_on_symbol(symbol, df)
        return self.all_trades

    def save_results(self, market_data=None):
        """Сохранение результатов после завершения"""
        if not self.all_trades:
            print("❌ Нет сделок для сохранения")
            return

        print(f"\n📊 Всего сделок в all_trades: {len(self.all_trades)}")

        closed_trades = [t for t in self.all_trades if t.exit_time is not None]
        open_trades = [t for t in self.all_trades if t.exit_time is None]

        print(f"📈 Закрытых сделок: {len(closed_trades)}")
        print(f"📉 Открытых сделок: {len(open_trades)}")

        # ⚠️ Если всё сделали правильно, open_trades тут должно быть 0 (из-за eod close)
        # Оставляю твой код подсчёта unrealized, но по факту он станет 0.

        last_prices = {}
        if open_trades and market_data:
            for symbol in set(trade.symbol for trade in open_trades):
                if symbol in market_data:
                    last_prices[symbol] = float(market_data[symbol].iloc[-1]["close"])

        unrealized_pnl = 0.0
        if open_trades:
            for trade in open_trades:
                cp = last_prices.get(trade.symbol, float(trade.entry_price))
                pnl = (float(trade.entry_price) - float(cp)) / float(trade.entry_price) * float(self.config.trade_size_usdt)
                unrealized_pnl += pnl

        print(f"\n💰 Нереализованная прибыль: {unrealized_pnl:.2f} USDT")

        analyzer = MetricsAnalyzer()
        metrics = analyzer.calculate_all_metrics(
            self.all_trades,
            self.portfolio.equity_history,
            self.portfolio.initial_capital,
            self.position_manager.positions,
        )

        metrics["open_trades_count"] = len(open_trades)
        metrics["unrealized_pnl"] = unrealized_pnl
        metrics["realized_pnl"] = metrics.get("total_pnl_usdt", 0)
        metrics["total_pnl_with_open"] = metrics.get("total_pnl_usdt", 0) + unrealized_pnl

        realized_pnl = metrics.get("total_pnl_usdt", 0)
        total_equity = float(self.portfolio.initial_capital) + float(realized_pnl) + float(unrealized_pnl)
        metrics["total_equity"] = total_equity
        metrics["total_return_percent"] = (total_equity - float(self.portfolio.initial_capital)) / float(self.portfolio.initial_capital) * 100

        metrics["initial_capital"] = self.portfolio.initial_capital
        metrics["final_cash"] = float(self.portfolio.initial_capital) + float(realized_pnl)

        print(f"\n📊 Проверка капитала:")
        print(f"   Начальный капитал: {self.portfolio.initial_capital:.2f} USDT")
        print(f"   Реализованная PNL: {realized_pnl:.2f} USDT")
        print(f"   Нереализованная PNL: {unrealized_pnl:.2f} USDT")
        print(f"   Итоговый капитал: {total_equity:.2f} USDT")

        metrics["equity_history"] = self.portfolio.equity_history
        metrics["open_positions"] = len(self.position_manager.positions)

        self.results_exporter.export_all_trades(self.all_trades, metrics)
        return metrics
