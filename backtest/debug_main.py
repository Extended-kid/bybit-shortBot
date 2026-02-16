#!/usr/bin/env python3
"""
Отладочная версия с принудительным выводом
"""

import argparse
import logging
from datetime import datetime, timedelta
import sys
import os

# Принудительно включаем немедленный вывод
sys.stdout.reconfigure(line_buffering=True)
os.environ['PYTHONUNBUFFERED'] = '1'

print("=" * 70, flush=True)
print("DEBUG MODE - STARTING", flush=True)
print("=" * 70, flush=True)

try:
    from config import StrategyConfig
    from backtester import Backtester
    from data_loader import BybitDataLoader
    from analyzers.metrics import MetricsAnalyzer
    
    print("✅ Imports successful", flush=True)
except Exception as e:
    print(f"❌ Import error: {e}", flush=True)
    sys.exit(1)

def main():
    print("\n📋 Parsing arguments...", flush=True)
    
    parser = argparse.ArgumentParser(description='Bybit Short Strategy Backtester')
    parser.add_argument('--start', type=str, default=None,
                       help='Start date (YYYY-MM-DD). Default: 1 year ago')
    parser.add_argument('--end', type=str, default=None,
                       help='End date (YYYY-MM-DD). Default: today')
    parser.add_argument('--pump', type=float, default=0.40,
                       help='Pump threshold (default: 0.40)')
    parser.add_argument('--tp', type=float, default=0.30,
                       help='Take profit percentage (default: 0.30)')
    parser.add_argument('--stall', type=int, default=3,
                       help='Stall bars (default: 3)')
    parser.add_argument('--symbols', type=str, nargs='+',
                       help='Specific symbols to test')
    parser.add_argument('--parallel', action='store_true',
                       help='Use multiprocessing for backtest')
    parser.add_argument('--workers', type=int, default=5,
                       help='Number of threads for data loading')
    parser.add_argument('--no-cache', action='store_true',
                       help='Disable data caching')
    parser.add_argument('--max-symbols', type=int, default=None,
                       help='Maximum number of symbols to test')
    
    args = parser.parse_args()
    print(f"✅ Arguments: {args}", flush=True)
    
    # Устанавливаем даты по умолчанию
    if not args.end:
        args.end = datetime.now().strftime('%Y-%m-%d')
        print(f"📅 Using default end date: {args.end}", flush=True)
    if not args.start:
        args.start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        print(f"📅 Using default start date: {args.start}", flush=True)
    
    # Конфигурация
    print("\n⚙️  Creating config...", flush=True)
    config = StrategyConfig(
        pump_threshold=args.pump,
        tp_percent=args.tp,
        stall_bars=args.stall
    )
    print(f"✅ Config created", flush=True)
    
    print("\n" + "=" * 70, flush=True)
    print("BYBIT USDT PERPETUAL SHORT STRATEGY BACKTESTER", flush=True)
    print("=" * 70, flush=True)
    print(f"Period: {args.start} -> {args.end}", flush=True)
    print(f"Pump threshold: {args.pump*100:.1f}%", flush=True)
    print(f"TP: {args.tp*100:.1f}% from local high", flush=True)
    print(f"Stall bars: {args.stall}", flush=True)
    print("=" * 70, flush=True)
    
    # Инициализация загрузчика
    print("\n📦 Initializing data loader...", flush=True)
    data_loader = BybitDataLoader(cache_dir='./cache')
    print("✅ Data loader initialized", flush=True)
    
    # Получение списка символов
    print("\n🔍 Fetching symbols...", flush=True)
    if args.symbols:
        symbols = args.symbols
        print(f"📊 Using specified {len(symbols)} symbols", flush=True)
    else:
        symbols = data_loader.get_usdt_perpetual_symbols()
        print(f"📊 Found {len(symbols)} total symbols", flush=True)
        if args.max_symbols:
            symbols = symbols[:args.max_symbols]
            print(f"📊 Limited to {len(symbols)} symbols", flush=True)
    
    if not symbols:
        print("❌ No symbols found!", flush=True)
        return
    
    print(f"📋 First 5 symbols: {symbols[:5]}", flush=True)
    
    # Загрузка данных
    print("\n📥 Loading market data...", flush=True)
    try:
        market_data = data_loader.prepare_market_data(
            symbols=symbols,
            interval='15m',
            start_date=args.start,
            end_date=args.end,
            max_workers=args.workers,
            use_cache=not args.no_cache
        )
        print(f"✅ Loaded {len(market_data)} symbols", flush=True)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user", flush=True)
        return
    except Exception as e:
        print(f"❌ Error loading data: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return
    
    if not market_data:
        print("❌ No data loaded. Exiting.", flush=True)
        return
    
    # Инициализация бэктестера
    print("\n⚙️  Initializing backtester...", flush=True)
    backtester = Backtester(config)
    print("✅ Backtester initialized", flush=True)
    
    # Запуск бэктеста
    print("\n🏃 Running backtest...", flush=True)
    start_time = datetime.now()
    
    try:
        if args.parallel:
            print("🔄 Using parallel mode", flush=True)
            all_trades = backtester.run_multiprocess(market_data)
        else:
            print("🔄 Using sequential mode", flush=True)
            all_trades = backtester.run_sequential(market_data)
        
        print(f"✅ Backtest complete: {len(all_trades)} trades", flush=True)
    except KeyboardInterrupt:
        print("\n⚠️  Backtest interrupted", flush=True)
        return
    except Exception as e:
        print(f"❌ Backtest error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return
    
    # Анализ результатов
    print("\n📊 Analyzing results...", flush=True)
    analyzer = MetricsAnalyzer()
    metrics = analyzer.calculate_all_metrics(
        backtester.portfolio.trades,
        backtester.portfolio.equity_history,
        backtester.portfolio.initial_capital
    )
    
    metrics['equity_history'] = backtester.portfolio.equity_history
    metrics['initial_capital'] = backtester.portfolio.initial_capital
    
    # Сохранение
    print("💾 Saving results...", flush=True)
    backtester.results_exporter.export_all_trades(all_trades, metrics)
    
    # Вывод сводки
    analyzer.print_summary(metrics)
    
    elapsed = datetime.now() - start_time
    print(f"\n⏱️  Execution time: {elapsed}", flush=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Program interrupted by user", flush=True)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}", flush=True)
        import traceback
        traceback.print_exc()
    
    print("\n👋 Press Enter to exit...", flush=True)
    input()