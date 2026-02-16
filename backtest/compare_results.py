import json
from pathlib import Path
import pandas as pd
import re
import matplotlib.pyplot as plt
import numpy as np
from tabulate import tabulate

def load_all_results():
    """Загрузка всех результатов из папки out_top_grid"""
    rows = []
    
    for folder in Path("out_top_grid").iterdir():
        if not folder.is_dir():
            continue
        
        summary_file = folder / "summary.json"
        if not summary_file.exists():
            continue
        
        try:
            with open(summary_file, encoding='utf-8') as f:
                data = json.load(f)
            
            # Парсим имя папки
            name = folder.name
            params = {}
            
            pump_match = re.search(r'p(\d+)', name)
            tp_match = re.search(r'tp(\d+)', name)
            stall_match = re.search(r's(\d+)', name)
            sl_match = re.search(r'sl(\d+)', name)
            
            if pump_match:
                params['pump'] = float(pump_match.group(1)) / 100
            if tp_match:
                params['tp'] = float(tp_match.group(1)) / 100
            if stall_match:
                params['stall'] = int(stall_match.group(1))
            if sl_match:
                params['sl'] = float(sl_match.group(1)) / 10
            
            # Загружаем trades_all.csv для детального анализа
            trades_file = folder / "trades_all.csv"
            trades_df = None
            if trades_file.exists():
                trades_df = pd.read_csv(trades_file)
                trades_df['exit_reason'] = trades_df['exit_reason'].fillna('unknown')
            
            rows.append({
                'test': name,
                'folder': str(folder),
                'pump': params.get('pump', 0),
                'tp': params.get('tp', 0),
                'stall': params.get('stall', 0),
                'sl': params.get('sl', 0),
                'trades': data.get('total_trades', 0),
                'pnl': round(data.get('total_pnl_usdt', 0), 2),
                'winrate': round(data.get('win_rate', 0), 1),
                'profit_factor': round(data.get('profit_factor', 0), 2),
                'avg_win': round(data.get('avg_win', 0), 2),
                'avg_loss': round(data.get('avg_loss', 0), 2),
                'max_drawdown': round(data.get('max_drawdown', 0), 2),
                'sharpe': round(data.get('sharpe_ratio', 0), 2),
                'trades_df': trades_df
            })
        except Exception as e:
            print(f"⚠️ Ошибка загрузки {folder}: {e}")
    
    return rows

def analyze_exit_reasons(trades_df):
    """Анализ причин выхода из сделок"""
    if trades_df is None or len(trades_df) == 0:
        return {}
    
    reasons = trades_df['exit_reason'].value_counts()
    total = len(trades_df)
    
    result = {}
    for reason, count in reasons.items():
        pnl = trades_df[trades_df['exit_reason'] == reason]['pnl_usdt'].sum()
        result[reason] = {
            'count': count,
            'percentage': (count / total) * 100,
            'pnl': round(pnl, 2),
            'avg_pnl': round(pnl / count, 2) if count > 0 else 0
        }
    
    return result

def create_comparison_table(rows):
    """Создание детальной таблицы сравнения"""
    df = pd.DataFrame(rows)
    
    # Убираем колонку с DataFrame для таблицы
    display_cols = ['test', 'pump', 'tp', 'stall', 'sl', 'trades', 'pnl', 'winrate', 
                   'profit_factor', 'avg_win', 'avg_loss', 'max_drawdown', 'sharpe']
    
    comparison = df[display_cols].copy()
    return comparison.sort_values('pnl', ascending=False)

def analyze_parameter_sensitivity(df):
    """Анализ чувствительности к параметрам"""
    print("\n" + "="*80)
    print("📊 АНАЛИЗ ЧУВСТВИТЕЛЬНОСТИ К ПАРАМЕТРАМ")
    print("="*80)
    
    results = {}
    
    for param in ['pump', 'tp', 'stall', 'sl']:
        if param in df.columns:
            print(f"\n🔍 По параметру: {param.upper()}")
            
            # Группировка по параметру
            grouped = df.groupby(param).agg({
                'pnl': ['mean', 'max', 'min', 'std'],
                'winrate': 'mean',
                'trades': 'sum',
                'profit_factor': 'mean'
            }).round(2)
            
            grouped.columns = ['_'.join(col).strip() for col in grouped.columns.values]
            print(tabulate(grouped, headers='keys', tablefmt='grid', floatfmt='.2f'))
            
            results[param] = grouped
    
    return results

def find_best_parameters(df):
    """Поиск лучших параметров"""
    print("\n" + "="*80)
    print("🏆 ПОИСК ЛУЧШИХ ПАРАМЕТРОВ")
    print("="*80)
    
    # По максимальной прибыли
    best_pnl = df.nlargest(3, 'pnl')[['test', 'pump', 'tp', 'stall', 'sl', 'pnl', 'winrate', 'profit_factor']]
    print("\n📈 ТОП-3 ПО ПРИБЫЛИ:")
    print(tabulate(best_pnl, headers='keys', tablefmt='grid', floatfmt='.2f'))
    
    # По максимальному profit factor
    best_pf = df.nlargest(3, 'profit_factor')[['test', 'pump', 'tp', 'stall', 'sl', 'pnl', 'winrate', 'profit_factor']]
    print("\n🔥 ТОП-3 ПО PROFIT FACTOR:")
    print(tabulate(best_pf, headers='keys', tablefmt='grid', floatfmt='.2f'))
    
    # По минимальной просадке
    best_dd = df.nsmallest(3, 'max_drawdown')[['test', 'pump', 'tp', 'stall', 'sl', 'pnl', 'winrate', 'max_drawdown']]
    print("\n🛡️ ТОП-3 ПО МИНИМАЛЬНОЙ ПРОСАДКЕ:")
    print(tabulate(best_dd, headers='keys', tablefmt='grid', floatfmt='.2f'))
    
    # По коэффициенту Шарпа
    if 'sharpe' in df.columns:
        best_sharpe = df.nlargest(3, 'sharpe')[['test', 'pump', 'tp', 'stall', 'sl', 'pnl', 'winrate', 'sharpe']]
        print("\n📊 ТОП-3 ПО КОЭФФИЦИЕНТУ ШАРПА:")
        print(tabulate(best_sharpe, headers='keys', tablefmt='grid', floatfmt='.2f'))

def analyze_exit_reasons_all(rows):
    """Анализ причин выхода для всех тестов"""
    print("\n" + "="*80)
    print("🚪 АНАЛИЗ ПРИЧИН ВЫХОДА ИЗ СДЕЛОК")
    print("="*80)
    
    exit_data = []
    for row in rows:
        if row['trades_df'] is not None:
            reasons = analyze_exit_reasons(row['trades_df'])
            
            exit_row = {
                'test': row['test'],
                'tp_count': reasons.get('tp', {}).get('count', 0),
                'tp_pnl': reasons.get('tp', {}).get('pnl', 0),
                'sl_count': reasons.get('sl', {}).get('count', 0),
                'sl_pnl': reasons.get('sl', {}).get('pnl', 0),
                'eod_count': reasons.get('eod', {}).get('count', 0),
                'eod_pnl': reasons.get('eod', {}).get('pnl', 0),
            }
            exit_data.append(exit_row)
    
    exit_df = pd.DataFrame(exit_data)
    if not exit_df.empty:
        print("\n📊 Детальный анализ причин выхода (топ-10 по прибыли):")
        exit_df['tp_ratio'] = (exit_df['tp_count'] / exit_df[['tp_count', 'sl_count', 'eod_count']].sum(axis=1)) * 100
        exit_df = exit_df.sort_values('tp_pnl', ascending=False).head(10)
        print(tabulate(exit_df, headers='keys', tablefmt='grid', floatfmt='.2f'))

def create_visualizations(df, rows):
    """Создание графиков"""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # 1. Зависимость PnL от параметров
        ax = axes[0, 0]
        for param in ['pump', 'tp', 'sl']:
            if param in df.columns:
                param_data = df.groupby(param)['pnl'].mean()
                ax.plot(param_data.index, param_data.values, marker='o', label=param.upper())
        ax.set_title('Зависимость средней прибыли от параметров')
        ax.set_xlabel('Параметр')
        ax.set_ylabel('Средний PnL (USDT)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 2. Распределение winrate vs profit factor
        ax = axes[0, 1]
        scatter = ax.scatter(df['winrate'], df['profit_factor'], 
                           c=df['pnl'], s=df['trades']/10, alpha=0.6, cmap='viridis')
        ax.set_title('Winrate vs Profit Factor (цвет = PnL, размер = кол-во сделок)')
        ax.set_xlabel('Winrate (%)')
        ax.set_ylabel('Profit Factor')
        plt.colorbar(scatter, ax=ax, label='PnL (USDT)')
        ax.grid(True, alpha=0.3)
        
        # 3. Топ-10 монет по прибыли (из лучшего теста)
        ax = axes[1, 0]
        if rows:
            best_test = max(rows, key=lambda x: x['pnl'])
            if best_test['trades_df'] is not None:
                symbol_pnl = best_test['trades_df'].groupby('symbol')['pnl_usdt'].sum().sort_values(ascending=False).head(10)
                colors = ['green' if x > 0 else 'red' for x in symbol_pnl.values]
                ax.barh(range(len(symbol_pnl)), symbol_pnl.values, color=colors[::-1])
                ax.set_title(f"Топ-10 монет по прибыли\n(лучший тест: {best_test['test']})")
                ax.set_xlabel('PnL (USDT)')
                ax.set_yticks(range(len(symbol_pnl)))
                ax.set_yticklabels(symbol_pnl.index[::-1])
                ax.axvline(x=0, color='black', linestyle='-', alpha=0.3)
        
        # 4. Распределение TP/SL/EOD
        ax = axes[1, 1]
        exit_data = []
        for row in rows[:5]:  # Топ-5 тестов
            if row['trades_df'] is not None:
                reasons = row['trades_df']['exit_reason'].value_counts()
                exit_data.append({
                    'test': row['test'][:20],
                    'TP': reasons.get('tp', 0),
                    'SL': reasons.get('sl', 0),
                    'EOD': reasons.get('eod', 0)
                })
        
        if exit_data:
            exit_df = pd.DataFrame(exit_data)
            exit_df.set_index('test')[['TP', 'SL', 'EOD']].plot(kind='bar', stacked=True, ax=ax)
            ax.set_title('Причины выхода (топ-5 тестов)')
            ax.set_xlabel('Тест')
            ax.set_ylabel('Количество сделок')
            ax.legend()
            ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('out_top_grid/detailed_comparison.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("\n💾 Графики сохранены в out_top_grid/detailed_comparison.png")
        
    except Exception as e:
        print(f"⚠️ Ошибка создания графиков: {e}")

def main():
    print("\n" + "="*80)
    print("📊 ДЕТАЛЬНЫЙ АНАЛИЗ РЕЗУЛЬТАТОВ GRID ПОИСКА")
    print("="*80)
    
    # Загружаем все результаты
    print("\n📂 Загрузка результатов...")
    rows = load_all_results()
    
    if not rows:
        print("❌ Нет результатов в папке out_top_grid/")
        return
    
    print(f"✅ Загружено {len(rows)} тестов")
    
    # Создаем DataFrame для анализа
    df = pd.DataFrame(rows)
    
    # 1. Детальная таблица сравнения
    print("\n" + "="*80)
    print("📊 ДЕТАЛЬНАЯ ТАБЛИЦА СРАВНЕНИЯ")
    print("="*80)
    comparison = create_comparison_table(rows)
    print(tabulate(comparison.head(20), headers='keys', tablefmt='grid', floatfmt='.2f'))
    
    # 2. Анализ чувствительности
    sensitivity = analyze_parameter_sensitivity(df)
    
    # 3. Поиск лучших параметров
    best_params = find_best_parameters(df)
    
    # 4. Анализ причин выхода
    exit_analysis = analyze_exit_reasons_all(rows)
    
    # 5. Создание визуализаций
    create_visualizations(df, rows)
    
    # 6. Сохраняем полные результаты
    output_file = 'out_top_grid/full_comparison.csv'
    comparison.to_csv(output_file, index=False)
    print(f"\n💾 Полная таблица сохранена в {output_file}")
    
    # 7. Сохраняем JSON с лучшими параметрами
    best_config = {
        'best_by_pnl': rows[df['pnl'].argmax()]['test'],
        'best_by_profit_factor': rows[df['profit_factor'].argmax()]['test'],
        'best_by_sharpe': rows[df['sharpe'].argmax()]['test'] if 'sharpe' in df.columns else None,
        'best_by_drawdown': rows[df['max_drawdown'].argmin()]['test'],
        'top_parameters': {
            'pump': float(df.loc[df['pnl'].argmax(), 'pump']),
            'tp': float(df.loc[df['pnl'].argmax(), 'tp']),
            'stall': int(df.loc[df['pnl'].argmax(), 'stall']),
            'sl': float(df.loc[df['pnl'].argmax(), 'sl']),
        }
    }
    
    with open('out_top_grid/best_config.json', 'w', encoding='utf-8') as f:
        json.dump(best_config, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*80)
    print("✅ АНАЛИЗ ЗАВЕРШЕН")
    print("="*80)

if __name__ == "__main__":
    main()