#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from live.bybit_client import BybitClient

load_dotenv()

def test_connection():
    print("Testing Bybit API connection...")
    
    client = BybitClient(
        api_key=os.getenv("BYBIT_API_KEY"),
        api_secret=os.getenv("BYBIT_API_SECRET"),
        testnet=os.getenv("BYBIT_TESTNET", "false").lower() == "true"
    )
    
    try:
        response = client.get_tickers()
        tickers = response["result"]["list"][:5]
        print(f"Got {len(response['result']['list'])} tickers")
        print(f"First 5: {[t['symbol'] for t in tickers]}")
        print("Connection OK!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_connection()
