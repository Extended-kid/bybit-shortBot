# test_risk.py
# Поставь в корневую папку проекта

import pandas as pd
from risk_manager import RiskManager

# Загружаем наши сделки
df = pd.read_csv('out_aggressive_2025/portfolio_simulation_results.csv')

# Создаем риск-менеджер
rm = RiskManager(initial_capital=10000)

print("📊 ТЕСТ РИСК-МЕНЕДЖЕРА")
print("="*50)

# Анализируем каждую монету
symbols = df['symbol'].unique()
for symbol in sorted(symbols)[:20]:  # Первые 20 монет
    symbol_trades = df[df['symbol'] == symbol]
    
    # Обновляем статистику по всем сделкам монеты
    for _, trade in symbol_trades.iterrows():
        rm.update_stats(symbol, trade['pnl_percent'])
    
    multiplier = rm.get_position_multiplier(symbol)
    trades_count = len(symbol_trades)
    win_rate = (len(symbol_trades[symbol_trades['pnl_percent'] > 0]) / trades_count * 100)
    
    print(f"\n{symbol}:")
    print(f"  Сделок: {trades_count}")
    print(f"  Винрейт: {win_rate:.1f}%")
    print(f"  Множитель риска: {multiplier:.2f}")
    print(f"  Размер позиции: {multiplier * 1:.2f}% от капитала")