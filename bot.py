#!/usr/bin/env python3
"""
Bybit Short Strategy Bot
Стратегия: поиск пампивших монет (>=25% за 24ч) и вход в шорт при стагнации
Оптимальные параметры из бэктеста: pump=0.25, tp=0.40, stall=4, sl=4.0
"""

import os
import sys
import time
import json
import logging
import signal
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import requests
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Создаем папку для логов
os.makedirs('data/logs', exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data/logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Импорты наших модулей
from config import BotConfig
from live.bybit_client import BybitClient
from live.order_manager import OrderManager
from live.position_tracker import PositionTracker
from live.telegram_notifier import TelegramNotifier


# =====================================
# РИСК МЕНЕДЖЕР
# =====================================
class RiskManager:
    """Управление рисками на основе истории монеты"""
    
    def __init__(self, initial_capital=10000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        self.today_pnl = 0
        self.current_date = None
        self.coin_stats = {}
        self.consecutive_losses = 0
        self.trades_history = []
        
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
    
    def on_trade_result(self, pnl_usdt, pnl_percent, symbol):
        """Обновляем состояние после сделки"""
        self.current_capital += pnl_usdt
        self.today_pnl += pnl_usdt
        
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        if pnl_usdt < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        self.update_stats(symbol, pnl_percent)


# =====================================
# ОСНОВНОЙ БОТ
# =====================================
class ShortBot:
    def __init__(self):
        self.config = BotConfig()
        self.running = True
        
        # Инициализируем компоненты
        self.client = BybitClient(
            api_key=os.getenv("BYBIT_API_KEY"),
            api_secret=os.getenv("BYBIT_API_SECRET"),
            testnet=os.getenv("BYBIT_TESTNET", "false").lower() == "true"
        )
        
        # Получаем начальный баланс
        self.initial_balance = self.get_balance()
        
        self.risk_manager = RiskManager(initial_capital=self.initial_balance)
        self.tracker = PositionTracker(os.path.join(self.config.data_dir, "state.json"))
        self.notifier = TelegramNotifier(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            chat_id=os.getenv("TELEGRAM_CHAT_ID")
        )
        
        # Для свечей
        self.last_bar_close = 0
        self._last_stall_check = 0
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("=" * 60)
        logger.info("БОТ ЗАПУЩЕН")
        logger.info(f"Начальный баланс: ${self.initial_balance:.2f}")
        logger.info(f"Параметры: pump={self.config.pump_threshold*100}%, tp={self.config.tp_percent*100}%, stall={self.config.stall_bars}")
        logger.info("=" * 60)
    
    def get_balance(self) -> float:
        """Получить текущий баланс USDT"""
        try:
            response = self.client.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            if response.get("retCode") == 0:
                balance = float(response["result"]["list"][0]["coin"][0]["walletBalance"])
                return balance
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
        return self.config.initial_capital
    
    def signal_handler(self, signum, frame):
        logger.info("Получен сигнал остановки, завершаем работу...")
        self.running = False
    
    def get_current_bar_close(self) -> int:
        """Получить время закрытия текущей 15-минутной свечи"""
        now = int(time.time())
        return (now // (15 * 60)) * (15 * 60)
    
    def get_all_tickers(self) -> List[Dict[str, Any]]:
        """Получить все тикеры"""
        try:
            response = self.client.get_tickers()
            return response["result"]["list"]
        except Exception as e:
            logger.error(f"Ошибка получения тикеров: {e}")
            return []
    
    def get_klines(self, symbol: str, max_retries: int = 3) -> Optional[List]:
        """
        Получить свечи с exponential backoff при rate limit
        """
        for attempt in range(max_retries):
            try:
                # Ждем между запросами к разным символам
                time.sleep(0.2)
                
                response = self.client.get_klines(
                    symbol=symbol,
                    interval="15",
                    limit=5
                )
                
                if response.get("retCode") == 10006:  # Rate limit
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Rate limit для {symbol}, ждем {wait_time}с")
                    time.sleep(wait_time)
                    continue
                    
                if response.get("retCode") != 0:
                    logger.error(f"Ошибка API для {symbol}: {response.get('retMsg')}")
                    return None
                    
                return response["result"]["list"]
                
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Не удалось получить свечи для {symbol}: {e}")
                    return None
                time.sleep((attempt + 1) * 2)
        
        return None
    
    def check_pump_candidate(self, ticker: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Проверить, является ли монета кандидатом на памп"""
        symbol = ticker.get("symbol", "")
        if not symbol.endswith("USDT"):
            return None
        
        try:
            last = float(ticker.get("lastPrice", 0))
            high24 = float(ticker.get("highPrice24h", 0))
            low24 = float(ticker.get("lowPrice24h", 0))
            turnover = float(ticker.get("turnover24h", 0))
            
            if last <= 0 or high24 <= 0 or low24 <= 0:
                return None
            
            # Рост от минимума
            pump_pct = (last - low24) / low24
            
            # Близость к максимуму
            near_high = last / high24
            
            # Проверяем условия
            if turnover < self.config.min_turnover_usdt:
                return None
            if pump_pct < self.config.pump_threshold:
                return None
            if near_high < self.config.near_high_ratio:
                return None
            
            return {
                "symbol": symbol,
                "last": last,
                "high24": high24,
                "low24": low24,
                "turnover": turnover,
                "pump_pct": pump_pct * 100,
                "near_high": near_high
            }
        except Exception as e:
            logger.error(f"Ошибка проверки {symbol}: {e}")
            return None
    
    def update_watchlist(self, candidates: List[Dict[str, Any]]):
        """Обновить watchlist новыми кандидатами"""
        now = int(time.time())
        added = 0
        
        for cand in candidates:
            symbol = cand["symbol"]
            
            # Проверяем cooldown
            if self.tracker.in_cooldown(symbol, self.config.cooldown_minutes):
                continue
            
            # Проверяем, есть ли уже открытая позиция
            if symbol in self.tracker.positions:
                continue
            
            # Проверяем, есть ли уже в watchlist
            if symbol in self.tracker.watchlist:
                continue
            
            # Получаем свечи для определения локального максимума
            klines = self.get_klines(symbol)
            if not klines or len(klines) < 2:
                continue
            
            # Берем последнюю закрытую свечу
            last_candle = klines[-2]
            local_high = float(last_candle[2])
            
            # Добавляем в watchlist
            self.tracker.watchlist[symbol] = {
                "local_high": local_high,
                "stall": 0,
                "blocked": False,
                "created_ts": now,
                "updated_ts": now,
                "entry_price": cand["last"]
            }
            added += 1
            logger.info(f"Добавлен в watchlist: {symbol} (памп {cand['pump_pct']:.1f}%)")
        
        if added:
            self.tracker.save()
            logger.info(f"Добавлено {added} новых монет в watchlist")
    
    def check_stall(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Проверить stall условия и вернуть готовые к входу"""
        if time.time() - self._last_stall_check < 2:
            return []
        
        self._last_stall_check = time.time()
        ready = []
        now = int(time.time())
        
        for symbol, data in list(self.tracker.watchlist.items()):
            # Проверяем TTL
            if now - data.get("created_ts", now) > self.config.watch_ttl_hours * 3600:
                logger.info(f"Удален из watchlist (TTL): {symbol}")
                del self.tracker.watchlist[symbol]
                continue
            
            # Получаем свечи
            klines = self.get_klines(symbol)
            if not klines:
                continue
            
            # Берем последнюю закрытую свечу
            last_candle = klines[-2]
            high = float(last_candle[2])
            close = float(last_candle[4])
            
            local_high = data["local_high"]
            stall = data["stall"]
            blocked = data.get("blocked", False)
            
            # Обновляем локальный максимум
            if high > local_high:
                data["local_high"] = high
                data["stall"] = 0
                data["blocked"] = False
                logger.info(f"Новый локальный максимум для {symbol}: {high:.6f}")
            else:
                data["stall"] = stall + 1
            
            data["updated_ts"] = now
            
            # Проверяем stall условие
            if data["stall"] >= self.config.stall_bars and not blocked:
                # Проверяем, не упала ли цена уже ниже TP
                tp_price = local_high * (1 - self.config.tp_percent)
                if close <= tp_price:
                    data["blocked"] = True
                    logger.info(f"⏭ {symbol}: цена уже ниже TP ({close:.6f} <= {tp_price:.6f}), блокируем")
                else:
                    ready.append((symbol, data))
        
        self.tracker.save()
        return ready
    
    def cancel_all_orders_for_symbol(self, symbol: str):
        """Отменить все открытые ордера по символу"""
        try:
            response = self.client.session.get_open_orders(
                category=self.config.category,
                symbol=symbol
            )
            
            if response.get("retCode") != 0:
                logger.error(f"Ошибка получения ордеров для {symbol}: {response.get('retMsg')}")
                return
            
            orders = response["result"]["list"]
            if not orders:
                return
            
            for order in orders:
                try:
                    cancel_response = self.client.session.cancel_order(
                        category=self.config.category,
                        symbol=symbol,
                        orderId=order["orderId"]
                    )
                    if cancel_response.get("retCode") == 0:
                        logger.info(f"Отменен ордер {order['orderId']} для {symbol} (цена: {order.get('price', 'N/A')})")
                    else:
                        logger.error(f"Ошибка отмены ордера {order['orderId']}: {cancel_response.get('retMsg')}")
                except Exception as e:
                    logger.error(f"Ошибка при отмене ордера {order.get('orderId')}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка при отмене ордеров для {symbol}: {e}")
    
    def open_position(self, symbol: str, data: Dict[str, Any]):
        """Открыть короткую позицию"""
        try:
            # Получаем текущую цену
            tickers = self.get_all_tickers()
            current_price = None
            for t in tickers:
                if t["symbol"] == symbol:
                    current_price = float(t["lastPrice"])
                    break
            
            if not current_price:
                logger.error(f"Не удалось получить цену для {symbol}")
                return
            
            # Получаем информацию об инструменте
            instr = self.client.get_instruments(symbol)
            filters = OrderManager.extract_filters(instr)
            
            # Рассчитываем размер позиции через RiskManager
            multiplier = self.risk_manager.get_position_multiplier(symbol)
            position_usdt = self.config.base_risk_per_trade * self.risk_manager.current_capital * multiplier
            
            # Рассчитываем количество
            qty = OrderManager.calculate_qty(position_usdt, current_price, filters)
            
            # Рассчитываем TP и SL
            local_high = data["local_high"]
            tp_price = local_high * (1 - self.config.tp_percent)
            sl_price = current_price * self.config.sl_multiplier
            
            # Округляем цены
            tp_price = OrderManager.round_price(tp_price, filters["tick_size"])
            sl_price = OrderManager.round_price(sl_price, filters["tick_size"])
            
            # Проверяем минимальную сумму
            if qty * current_price < filters["min_notional"]:
                logger.warning(f"{symbol}: сумма меньше минимальной, пропускаем")
                return
            
            # ========== ВАЖНО: Отменяем все старые ордера перед открытием новой позиции ==========
            logger.info(f"Отменяем старые ордера для {symbol} перед открытием позиции")
            self.cancel_all_orders_for_symbol(symbol)
            
            # Открываем позицию (market sell)
            response = self.client.place_order(
                category=self.config.category,
                symbol=symbol,
                side="Sell",
                orderType="Market",
                qty=str(qty),
                timeInForce="IOC"
            )
            
            if response.get("retCode") != 0:
                logger.error(f"Ошибка открытия позиции {symbol}: {response.get('retMsg')}")
                return
            
            # Сохраняем позицию
            position = {
                "symbol": symbol,
                "entry_price": current_price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "qty": qty,
                "open_time": int(time.time()),
                "multiplier": multiplier,
                "position_usdt": position_usdt,
                "local_high": local_high
            }
            
            self.tracker.add_position(position)
            
            # Выставляем TP и SL лимитниками
            # Снова отменяем ордера (на всякий случай, если что-то появилось за микросекунды)
            self.cancel_all_orders_for_symbol(symbol)
            
            # TP ордер
            # TP ордер (Buy Limit - закрытие шорта при падении)
            logger.info(f"Выставляем TP для {symbol} по цене {tp_price}")
            tp_response = self.client.place_order(
                category=self.config.category,
                symbol=symbol,
                side="Buy",  # 👈 TP для шорта = Buy
                orderType="Limit",
                qty=str(qty),
                price=str(tp_price),
                timeInForce="GTC",
                reduceOnly=True  # 👈 ДОБАВИТЬ (важно для TP/SL)
            )
            
            if tp_response.get("retCode") != 0:
                logger.error(f"Ошибка выставления TP для {symbol}: {tp_response.get('retMsg')}")
            else:
                logger.info(f"TP ордер для {symbol} выставлен по цене {tp_price}")
            
            # SL ордер (Buy Limit - закрытие шорта при росте)
            logger.info(f"Выставляем SL для {symbol} по цене {sl_price}")
            sl_response = self.client.place_order(
                category=self.config.category,
                symbol=symbol,
                side="Buy",  # 👈 SL для шорта = Buy
                orderType="Limit",
                qty=str(qty),
                price=str(sl_price),
                timeInForce="GTC",
                reduceOnly=True  # 👈 ДОБАВИТЬ (важно для TP/SL)
            )
            
            if sl_response.get("retCode") != 0:
                logger.error(f"Ошибка выставления SL для {symbol}: {sl_response.get('retMsg')}")
            else:
                logger.info(f"SL ордер для {symbol} выставлен по цене {sl_price}")
            
            # Уведомление в Telegram
            self.notifier.send_trade_open(
                symbol, current_price, tp_price, sl_price,
                position_usdt, multiplier
            )
            
            # Удаляем из watchlist
            del self.tracker.watchlist[symbol]
            self.tracker.save()
            
            logger.info(f"ОТКРЫТА ПОЗИЦИЯ {symbol}")
            logger.info(f"   Вход: ${current_price:.6f}")
            logger.info(f"   TP: ${tp_price:.6f} ({(tp_price/current_price-1)*100:.1f}%)")
            logger.info(f"   SL: ${sl_price:.6f} ({self.config.sl_multiplier}x)")
            logger.info(f"   Размер: ${position_usdt:.2f} ({multiplier:.1f}x)")
            
        except Exception as e:
            logger.error(f"Ошибка открытия позиции {symbol}: {e}")
    
    def check_positions(self):
        """Проверить открытые позиции"""
        for symbol, position in list(self.tracker.positions.items()):
            try:
                # Получаем текущую цену
                tickers = self.get_all_tickers()
                current_price = None
                for t in tickers:
                    if t["symbol"] == symbol:
                        current_price = float(t["lastPrice"])
                        break
                
                if not current_price:
                    continue
                
                # Проверяем TP
                if current_price <= position["tp_price"]:
                    self.close_position(symbol, "TP", current_price)
                
                # Проверяем SL
                elif current_price >= position["sl_price"]:
                    self.close_position(symbol, "SL", current_price)
                    
            except Exception as e:
                logger.error(f"Ошибка проверки {symbol}: {e}")
    
    def close_position(self, symbol: str, reason: str, price: float):
        """Закрыть позицию"""
        try:
            position = self.tracker.positions.get(symbol)
            if not position:
                return
            
            # ========== ВАЖНО: Отменяем все старые ордера перед закрытием ==========
            logger.info(f"Отменяем старые ордера для {symbol} перед закрытием позиции")
            self.cancel_all_orders_for_symbol(symbol)
            
            # Закрываем позицию (market buy)
            response = self.client.place_order(
                category=self.config.category,
                symbol=symbol,
                side="Buy",
                orderType="Market",
                qty=str(position["qty"]),
                timeInForce="IOC"
            )
            
            if response.get("retCode") != 0:
                logger.error(f"Ошибка закрытия {symbol}: {response.get('retMsg')}")
                return
            
            # Рассчитываем PnL
            entry = position["entry_price"]
            pnl_usdt = (entry - price) * position["qty"]
            pnl_percent = (entry - price) / entry * 100
            
            # Обновляем риск-менеджер
            self.risk_manager.on_trade_result(pnl_usdt, pnl_percent, symbol)
            
            # Удаляем позицию
            self.tracker.remove_position(symbol)
            
            # Еще раз отменяем ордера (на случай, если рыночный ордер не закрыл лимитники)
            self.cancel_all_orders_for_symbol(symbol)
            
            # Уведомление
            duration = int(time.time()) - position["open_time"]
            duration_str = f"{duration // 60}м {duration % 60}с"
            
            self.notifier.send_trade_close(
                symbol, entry, price, pnl_usdt, pnl_percent,
                reason, duration_str
            )
            
            logger.info(f"{'' if pnl_usdt > 0 else ''} ЗАКРЫТА {symbol}")
            logger.info(f"   Причина: {reason}")
            logger.info(f"   Вход: ${entry:.6f} -> Выход: ${price:.6f}")
            logger.info(f"   PnL: ${pnl_usdt:.2f} ({pnl_percent:.1f}%)")
            
        except Exception as e:
            logger.error(f"Ошибка закрытия {symbol}: {e}")
    
    def run(self):
        """Основной цикл бота"""
        logger.info("Запуск основного цикла")
        
        while self.running:
            try:
                # Проверяем закрытие свечи
                current_bar = self.get_current_bar_close()
                
                if current_bar != self.last_bar_close:
                    self.last_bar_close = current_bar
                    logger.info(f"Новая свеча: {datetime.fromtimestamp(current_bar)}")
                    
                    # Получаем все тикеры
                    tickers = self.get_all_tickers()
                    
                    # Ищем кандидатов на памп
                    candidates = []
                    for t in tickers:
                        cand = self.check_pump_candidate(t)
                        if cand:
                            candidates.append(cand)
                    
                    if candidates:
                        logger.info(f"Найдено кандидатов: {len(candidates)}")
                        self.update_watchlist(candidates)
                    
                    # Проверяем stall условия
                    ready = self.check_stall()
                    if ready:
                        logger.info(f"Готовы к входу: {len(ready)}")
                        for symbol, data in ready:
                            self.open_position(symbol, data)
                    
                    # Проверяем открытые позиции
                    self.check_positions()
                    
                    # Показываем статистику
                    logger.info(f"Статистика: watchlist={len(self.tracker.watchlist)}, "
                              f"positions={len(self.tracker.positions)}, "
                              f"balance=${self.risk_manager.current_capital:.2f}")
                
                time.sleep(self.config.wake_seconds)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}", exc_info=True)
                time.sleep(10)
        
        logger.info("Бот остановлен")


def main():
    bot = ShortBot()
    bot.run()


if __name__ == "__main__":
    main()