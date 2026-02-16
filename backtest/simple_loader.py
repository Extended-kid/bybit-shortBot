#!/usr/bin/env python3
"""
Упрощенный загрузчик данных из Bybit
"""

import requests
from datetime import datetime, timedelta
import pandas as pd
import time
from tqdm import tqdm

def get_symbols(limit=10):
    """Получение списка символов"""
    url = "https://api.bybit.com/v5/market/instruments-info"
    params = {
        'category': 'linear',
        'limit': 1000
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data['retCode'] == 0:
            symbols = []
            for item in data['result']['list']:
                if item['quoteCoin'] == 'USDT' and item['status'] == 'Trading':
                    symbols.append(item['symbol'])
            return symbols[:limit]
        else:
            print(f"Error getting symbols: {data}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

def fetch_klines_simple(symbol, days=30):
    """Простая загрузка свечей"""
    url = "https://api.bybit.com/v5/market/kline"
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    
    params = {
        'category': 'linear',
        'symbol': symbol,
        'interval': '15',
        'start': int(start_time.timestamp() * 1000),
        'end': int(end_time.timestamp() * 1000),
        'limit': 200
    }
    
    try:
        print(f"Fetching {symbol}...")
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        
        if data['retCode'] == 0:
            klines = data['result']['list']
            print(f"  Got {len(klines)} candles")
            
            # Конвертируем в DataFrame
            rows = []
            for k in klines:
                rows.append({
                    'timestamp': datetime.fromtimestamp(int(k[0]) / 1000),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
                })
            
            df = pd.DataFrame(rows)
            df = df.sort_values('timestamp')
            return df
        else:
            print(f"  Error: {data.get('retMsg', 'Unknown')}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

def main():
    print("Simple Bybit Data Loader Test")
    print("=" * 50)
    
    # Получаем символы
    print("\n1. Getting symbols...")
    symbols = get_symbols(3)
    print(f"Found {len(symbols)} symbols: {symbols}")
    
    if not symbols:
        print("No symbols found. Exiting.")
        return
    
    # Загружаем данные
    print("\n2. Loading data...")
    for symbol in symbols:
        df = fetch_klines_simple(symbol, days=30)
        if df is not None:
            print(f"   {symbol}: {len(df)} candles, from {df['timestamp'].min()} to {df['timestamp'].max()}")
        time.sleep(1)  # Пауза между запросами
    
    print("\n✅ Test complete")

if __name__ == "__main__":
    main()