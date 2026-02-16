from pybit.unified_trading import HTTP
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

logger = logging.getLogger(__name__)

class BybitDataLoader:
    """Загрузчик данных из Bybit API"""
    
    def __init__(self, cache_dir: str = './cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Bybit API клиент
        self.session = HTTP(testnet=False)
        
        # Маппинг интервалов
        self.interval_map = {
            '1m': '1',
            '3m': '3',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '2h': '120',
            '4h': '240',
            '6h': '360',
            '12h': '720',
            '1d': 'D',
            '1w': 'W',
            '1M': 'M'
        }
        
    def get_usdt_perpetual_symbols(self, limit: int = None) -> List[str]:
        """Получение списка USDT perpetual фьючерсов"""
        try:
            print("🔍 Получаю список USDT perpetual...")
            
            response = self.session.get_instruments_info(
                category="linear",  # linear = USDT perpetual
                limit=1000
            )
            
            if response['retCode'] == 0:
                symbols = []
                for item in response['result']['list']:
                    # USDT perpetual: quoteCoin = USDT, contractType = LinearPerpetual
                    if item['quoteCoin'] == 'USDT' and item.get('contractType') == 'LinearPerpetual':
                        symbols.append(item['symbol'])
                
                if limit:
                    symbols = symbols[:limit]
                
                print(f"✅ Найдено {len(symbols)} USDT perpetual")
                return symbols
            else:
                print(f"❌ Ошибка API: {response['retMsg']}")
                return []
                
        except Exception as e:
            print(f"❌ Ошибка при получении символов: {e}")
            return []
    
    def get_klines(self, symbol: str, interval: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Загрузка ВСЕХ свечей за период с правильной пагинацией"""
        
        interval_str = self.interval_map.get(interval, '15')
        
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)
        
        all_klines = []
        current_end = end_ms
        batch_limit = 1000
        
        print(f"  Загрузка {symbol}...")
        
        with tqdm(desc=f"{symbol}", leave=False, position=1) as pbar:
            while current_end > start_ms:
                try:
                    response = self.session.get_kline(
                        category="linear",
                        symbol=symbol,
                        interval=interval_str,
                        start=start_ms,
                        end=current_end,
                        limit=batch_limit
                    )
                    
                    if response['retCode'] != 0:
                        if "too many requests" in response['retMsg'].lower():
                            time.sleep(1)
                            continue
                        else:
                            break
                    
                    data = response['result']['list']
                    if not data:
                        break
                    
                    all_klines.extend(data)
                    pbar.update(len(data))
                    
                    # Берем самую старую свечу в пачке
                    oldest_ts = int(data[-1][0])
                    
                    # Если дошли до старта - выходим
                    if oldest_ts <= start_ms:
                        break
                    
                    current_end = oldest_ts - 1
                    time.sleep(0.05)
                    
                except Exception as e:
                    print(f"  ❌ Ошибка {symbol}: {e}")
                    break
        
        if not all_klines:
            return None
        
        # Убираем дубликаты и сортируем
        seen = set()
        unique_klines = []
        for k in reversed(all_klines):  # Переворачиваем в старые->новые
            ts = int(k[0])
            if ts not in seen and start_ms <= ts <= end_ms:
                seen.add(ts)
                unique_klines.append(k)
        
        # Конвертируем
        rows = []
        for k in unique_klines:
            ts = int(k[0])
            dt = datetime.fromtimestamp(ts / 1000)
            rows.append({
                'timestamp': dt,
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
            })
        
        df = pd.DataFrame(rows)
        df['idx'] = df.index
        df['returns'] = df['close'].pct_change()
        df['range_pct'] = (df['high'] - df['low']) / df['low'] * 100
        df['funding_rate'] = 0.0001
        
        print(f"  ✅ {symbol}: {len(df)} свечей")
        return df

    
    def load_symbol_data(
        self,
        symbol: str,
        interval: str = '15m',
        start_date: str = None,
        end_date: str = None,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        КЭШ: один файл на symbol+interval: cache/{symbol}_{interval}.parquet
        - если кэш есть -> читаем и просто фильтруем по датам
        - если кэша нет -> качаем за запрошенный диапазон и сохраняем
        """

        cache_file = self.cache_dir / f"{symbol}_{interval}.parquet"

        # Границы дат
        start_dt = pd.to_datetime(start_date) if start_date else None
        end_dt = pd.to_datetime(end_date) if end_date else None

        # 1) Чтение кэша
        if use_cache and cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)

                # Фильтрация по датам (быстро)
                if start_dt is not None:
                    df = df[df["timestamp"] >= start_dt]
                if end_dt is not None:
                    df = df[df["timestamp"] <= end_dt]

                # Важно: после фильтра может стать пустым
                if df is None or len(df) == 0:
                    return None

                # Если тебе обязательно нужны эти колонки всегда:
                if "idx" not in df.columns:
                    df = df.reset_index(drop=True)
                    df["idx"] = df.index
                if "returns" not in df.columns:
                    df["returns"] = df["close"].pct_change()
                if "range_pct" not in df.columns:
                    df["range_pct"] = (df["high"] - df["low"]) / df["low"] * 100
                if "funding_rate" not in df.columns:
                    df["funding_rate"] = 0.0001

                return df

            except Exception:
                # если кэш битый -> пробуем скачать заново
                pass

        # 2) Если кэша нет или он битый -> качаем
        df = self.get_klines(symbol, interval, start_date, end_date)
        if df is None or len(df) == 0:
            return None

        # 3) Сохраняем в кэш (один файл)
        if use_cache:
            try:
                df.to_parquet(cache_file, index=False)
            except Exception:
                pass

        return df

    
    def prepare_market_data(self, symbols: List[str], interval: str = '15m',
                       start_date: str = None, end_date: str = None,
                       max_workers: int = 5, use_cache: bool = True) -> Dict[str, pd.DataFrame]:
        """Параллельная загрузка данных"""
        
        market_data = {}
        total_symbols = len(symbols)
        
        print(f"\n📥 Загрузка данных для {total_symbols} символов...")
        print(f"   Это займет примерно {total_symbols * 2 // 60} минут...\n")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(
                    self.load_symbol_data, symbol, interval, start_date, end_date, use_cache
                ): symbol for symbol in symbols
            }
            
            # Единый прогресс-бар для всех символов
            with tqdm(total=total_symbols, desc="Общий прогресс", unit=" символ") as pbar:
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        df = future.result()
                        if df is not None and len(df) > 0:
                            market_data[symbol] = df
                    except Exception as e:
                        pass  # Игнорируем ошибки отдельных символов
                    
                    pbar.update(1)
                    # Обновляем описание с текущим символом
                    pbar.set_description(f"Загружено: {len(market_data)}/{total_symbols}")
        
        print(f"\n✅ Загружено {len(market_data)} символов из {total_symbols}")
        return market_data