#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta
import sys
import os

sys.stdout.reconfigure(line_buffering=True)
os.environ['PYTHONUNBUFFERED'] = '1'

print("=" * 70)
print("ЗАПУСК БЭКТЕСТЕРА")
print("=" * 70)

try:
    from config import StrategyConfig
    from backtester import Backtester
    from data_loader import BybitDataLoader
    from analyzers.metrics import MetricsAnalyzer
    print("✅ Импорты успешны")
except Exception as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, default=None)
    parser.add_argument('--end', type=str, default=None)
    parser.add_argument('--pump', type=float, default=0.40)
    parser.add_argument('--tp', type=float, default=0.30)
    parser.add_argument('--stall', type=int, default=3)
    parser.add_argument('--workers', type=int, default=5)
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--sl-multiplier', type=float, default=2.0)
    parser.add_argument('--no-prints', action='store_true')
    parser.add_argument('--out', type=str, default='backtest_results')
    
    args = parser.parse_args()
    print(f"📋 Аргументы: {args}")
    
    if not args.end:
        args.end = datetime.now().strftime('%Y-%m-%d')
    if not args.start:
        args.start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    print(f"📅 Период: {args.start} -> {args.end}")
    
    config = StrategyConfig(
        pump_threshold=args.pump,
        tp_percent=args.tp,
        stall_bars=args.stall,
        no_prints=args.no_prints,
        sl_multiplier=args.sl_multiplier,
        output_dir=args.out
    )
    
    print("\n📦 Инициализация загрузчика...")
    loader = BybitDataLoader()
    
    print("\n🔍 Получение списка символов...")
    symbols = loader.get_usdt_perpetual_symbols()
    
    if not symbols:
        print("❌ Нет символов")
        return
    
    print(f"📊 Найдено {len(symbols)} символов")
    
    print("\n📥 Загрузка данных...")
    market_data = loader.prepare_market_data(
        symbols=symbols,
        interval='15m',
        start_date=args.start,
        end_date=args.end,
        max_workers=args.workers
    )
    
    if not market_data:
        print("❌ Нет данных")
        return
    
    print(f"\n✅ Загружено {len(market_data)} символов")
    
    print("\n⚙️ Запуск бэктеста...")
    backtester = Backtester(config)
    start_time = datetime.now()
    
    all_trades = backtester.run_multiprocess(market_data)
    
    elapsed = datetime.now() - start_time
    print(f"\n📊 Сделок: {len(all_trades)}")
    print(f"⏱️ Время: {elapsed}")
    
    print("\n💾 Сохранение...")
    metrics = backtester.save_results(market_data)
    
    if metrics:
        print("\n" + "=" * 60)
        print("ИТОГИ")
        print("=" * 60)
        print(f"📊 Всего сделок: {metrics.get('total_trades', 0)}")
        print(f"📈 Win rate: {metrics.get('win_rate', 0):.2f}%")
        print(f"💰 PNL: {metrics.get('total_pnl_usdt', 0):.2f} USDT")
        print(f"💎 Капитал: {metrics.get('total_equity', 0):.2f} USDT")
        print(f"\n💾 Результаты в папке: {args.out}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Прервано")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()