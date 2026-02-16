import pandas as pd
import os

# Путь к файлу в папке out_aggressive_2025
file_path = os.path.join('out_aggressive_2025', 'trades_all.csv')

# Проверяем, существует ли файл
if not os.path.exists(file_path):
    print(f"❌ Ошибка: Файл не найден по пути: {file_path}")
    print(f"Текущая директория: {os.getcwd()}")
    
    # Показываем содержимое папки out_aggressive_2025
    if os.path.exists('out_aggressive_2025'):
        print("\nСодержимое папки out_aggressive_2025:")
        for item in os.listdir('out_aggressive_2025'):
            print(f"  - {item}")
    else:
        print(f"\nПапка out_aggressive_2025 не найдена в {os.getcwd()}")
    exit()

print(f"✅ Файл найден: {file_path}")

# Загружаем данные
df = pd.read_csv(file_path)
print(f"Загружено {len(df)} сделок")

# Проверяем наличие нужных колонок
required_columns = ['entry_time', 'pnl_percent', 'symbol', 'exit_reason']
missing_columns = [col for col in required_columns if col not in df.columns]
if missing_columns:
    print(f"❌ Ошибка: в файле нет колонок: {missing_columns}")
    print("Доступные колонки:", df.columns.tolist())
    exit()

df['entry_time'] = pd.to_datetime(df['entry_time'])
df = df.sort_values(by='entry_time')

# Параметры симуляции
initial_capital = 1000.0  # Начальный портфель
risk_per_trade = 0.1      # Риск 1% от портфеля на сделку

# Столбцы для результатов
df['portfolio_before'] = 0.0
df['portfolio_after'] = 0.0
df['trade_pnl_percent_of_portfolio'] = 0.0
df['allocated_capital'] = 0.0
df['trade_result_usdt'] = 0.0

current_capital = initial_capital

print("\n🔄 Симуляция торговли...")

# Проходим по каждой сделке
for index, row in df.iterrows():
    df.at[index, 'portfolio_before'] = current_capital
    
    # Сумма, выделенная на сделку (1% от текущего капитала)
    allocated = current_capital * risk_per_trade
    df.at[index, 'allocated_capital'] = allocated
    
    # Результат сделки в USDT (прибыль или убыток)
    trade_result = allocated * (row['pnl_percent'] / 100.0)
    df.at[index, 'trade_result_usdt'] = trade_result
    
    # Сколько процентов от ВСЕГО портфеля составил результат этой сделки
    pnl_percent_of_portfolio = (trade_result / current_capital) * 100
    df.at[index, 'trade_pnl_percent_of_portfolio'] = pnl_percent_of_portfolio
    
    # Обновляем капитал
    current_capital += trade_result
    df.at[index, 'portfolio_after'] = current_capital

# Итоговые результаты
total_return_percent = ((current_capital - initial_capital) / initial_capital) * 100
total_return_usdt = current_capital - initial_capital

print("\n" + "="*70)
print("📊 РЕЗУЛЬТАТЫ СИМУЛЯЦИИ (риск 1% на сделку)")
print("="*70)
print(f"Начальный капитал:    ${initial_capital:,.2f}")
print(f"Конечный капитал:      ${current_capital:,.2f}")
print(f"Абсолютная прибыль:    ${total_return_usdt:,.2f}")
print(f"Общая доходность:      {total_return_percent:.2f}%")
print("="*70)

# Статистика по сделкам
total_trades = len(df)
profitable_trades = len(df[df['pnl_percent'] > 0])
losing_trades = len(df[df['pnl_percent'] < 0])
neutral_trades = len(df[df['pnl_percent'] == 0])
win_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0

print(f"\n📈 Статистика по {total_trades} сделкам:")
print(f"  Прибыльных сделок:  {profitable_trades} ({win_rate:.1f}%)")
print(f"  Убыточных сделок:    {losing_trades} ({100-win_rate:.1f}%)")
print(f"  Нейтральных сделок:  {neutral_trades}")

# Статистика по причинам выхода
print(f"\n🚪 Причины выхода из сделок:")
exit_reasons = df['exit_reason'].value_counts()
for reason, count in exit_reasons.items():
    percentage = (count / total_trades) * 100
    print(f"  {reason}: {count} ({percentage:.1f}%)")

# Максимальная просадка (если есть portfolio_after)
df['peak'] = df['portfolio_after'].cummax()
df['drawdown'] = (df['portfolio_after'] - df['peak']) / df['peak'] * 100
max_drawdown = df['drawdown'].min()
max_drawdown_date = df.loc[df['drawdown'].idxmin(), 'entry_time'] if not df['drawdown'].isna().all() else "N/A"

print(f"\n📉 Метрики риска:")
print(f"  Максимальная просадка: {max_drawdown:.2f}% (достигнута {max_drawdown_date})")
print(f"  Финальный коэффициент Шарпа (упрощенно): {(total_return_percent/100) / (df['trade_pnl_percent_of_portfolio'].std() + 0.001):.2f}")

# Топ-5 лучших и худших сделок
print(f"\n🏆 Топ-5 самых прибыльных сделок (% от портфеля):")
top_profitable = df.nlargest(5, 'trade_pnl_percent_of_portfolio')[['symbol', 'entry_time', 'pnl_percent', 'trade_pnl_percent_of_portfolio']]
for i, (_, row) in enumerate(top_profitable.iterrows(), 1):
    print(f"  {i}. {row['symbol']}: {row['trade_pnl_percent_of_portfolio']:.2f}% (исходный PnL: {row['pnl_percent']:.1f}%)")

print(f"\n💔 Топ-5 самых убыточных сделок (% от портфеля):")
top_losing = df.nsmallest(5, 'trade_pnl_percent_of_portfolio')[['symbol', 'entry_time', 'pnl_percent', 'trade_pnl_percent_of_portfolio']]
for i, (_, row) in enumerate(top_losing.iterrows(), 1):
    print(f"  {i}. {row['symbol']}: {row['trade_pnl_percent_of_portfolio']:.2f}% (исходный PnL: {row['pnl_percent']:.1f}%)")

# Посмотрим на первые несколько сделок
print(f"\n📋 Первые 5 сделок:")
print(df[['symbol', 'entry_time', 'exit_reason', 'pnl_percent', 'allocated_capital', 'trade_result_usdt', 'portfolio_after']].head(5).to_string())

# Сохраняем результаты в новый CSV файл
output_path = os.path.join('out_aggressive_2025', 'portfolio_simulation_results.csv')
df.to_csv(output_path, index=False)
print(f"\n💾 Результаты сохранены в: {output_path}")

# Создаем краткий отчет
report_path = os.path.join('out_aggressive_2025', 'simulation_report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write("="*70 + "\n")
    f.write("ОТЧЕТ ПО СИМУЛЯЦИИ ПОРТФЕЛЯ\n")
    f.write("="*70 + "\n")
    f.write(f"Начальный капитал:    ${initial_capital:,.2f}\n")
    f.write(f"Конечный капитал:      ${current_capital:,.2f}\n")
    f.write(f"Абсолютная прибыль:    ${total_return_usdt:,.2f}\n")
    f.write(f"Общая доходность:      {total_return_percent:.2f}%\n")
    f.write(f"Максимальная просадка: {max_drawdown:.2f}%\n")
    f.write(f"Всего сделок:          {total_trades}\n")
    f.write(f"Процент побед:          {win_rate:.1f}%\n")
    f.write("="*70 + "\n")

print(f"📄 Краткий отчет сохранен в: {report_path}")