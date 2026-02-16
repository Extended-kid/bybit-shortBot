#!/usr/bin/env python3
"""
Упрощенная версия для теста загрузки данных
"""

import requests
from datetime import datetime, timedelta
import pandas as pd
import time

def test_bybit_api():
    """Тест подключения к Bybit API"""
    print("Testing Bybit API connection...")
    
    # Тест 1: Проверка доступности API
    try:
        response = requests.get("https://api.bybit.com/v5/market/time", timeout=10)
        print(f"API Time response: {response.status_code}")
        print(response.json())
    except Exception as e:
        print(f"API Time error: {e}")
    
    # Тест 2: Получение списка символов
    try:
        url = "https://api.bybit.com/v5/market/instruments-info"
        params = {
            'category': 'linear',
            'limit': 10
        }
        response = requests.get(url, params=params, timeout=10)
        print(f"\nInstruments response: {response.status_code}")
        data = response.json()
        if data['retCode'] == 0:
            symbols = [item['symbol'] for item in data['result']['list'][:5]]
            print(f"Sample symbols: {symbols}")
        else:
            print(f"Error: {data}")
    except Exception as e:
        print(f"Instruments error: {e}")
    
    # Тест 3: Получение свечей для BTCUSDT
    try:
        url = "https://api.bybit.com/v5/market/kline"
        params = {
            'category': 'linear',
            'symbol': 'BTCUSDT',
            'interval': '15',
            'limit': 10
        }
        response = requests.get(url, params=params, timeout=10)
        print(f"\nKline response: {response.status_code}")
        data = response.json()
        if data['retCode'] == 0:
            print(f"Got {len(data['result']['list'])} candles")
            print(f"First candle: {data['result']['list'][0]}")
        else:
            print(f"Error: {data}")
    except Exception as e:
        print(f"Kline error: {e}")

if __name__ == "__main__":
    test_bybit_api()