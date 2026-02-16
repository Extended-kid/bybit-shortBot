import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import json
import numpy as np
import argparse

def load_results(folder_path='./backtest_results'):
    """Загрузка результатов теста из указанной папки"""
    results_dir = Path(folder_path)
    
    # Загружаем все сделки
    trades_file = results_dir / 'trades_all.csv'
    if not trades_file.exists():
        print(f"❌ Файл trades_all.csv не найден в {results_dir}")
        return None
    
    df = pd.read_csv(trades_file)
    
    # Конвертируем время
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['exit_time'] = pd.to_datetime(df['exit_time'])
    
    # Фильтруем ТОЛЬКО закрытые сделки
    df_closed = df.dropna(subset=['exit_time', 'pnl_usdt'])
    
    print(f"\n📊 Всего записей в файле: {len(df)}")
    print(f"📈 Закрытых сделок: {len(df_closed)}")
    print(f"📉 Открытых сделок: {len(df) - len(df_closed)}")
    
    if len(df_closed) == 0:
        print("❌ Нет закрытых сделок для анализа")
        return None
    
    df_closed['duration_hours'] = (df_closed['exit_time'] - df_closed['entry_time']).dt.total_seconds() / 3600
    
    return df_closed

def analyze_trades(df):
    """Детальный анализ сделок"""
    print("\n" + "=" * 60)
    print("📊 ДЕТАЛЬНЫЙ АНАЛИЗ СДЕЛОК")
    print("=" * 60)
    
    # Общая статистика
    profitable = df[df['pnl_usdt'] > 0]
    losing = df[df['pnl_usdt'] <= 0]
    
    print(f"\n📈 Всего закрытых сделок: {len(df)}")
    print(f"   Прибыльных: {len(profitable)}")
    print(f"   Убыточных: {len(losing)}")
    print(f"💰 Общая прибыль: {df['pnl_usdt'].sum():.2f} USDT")
    print(f"📊 Средняя сделка: {df['pnl_usdt'].mean():.4f} USDT")
    print(f"📈 Медианная сделка: {df['pnl_usdt'].median():.4f} USDT")
    print(f"📊 Win rate: {(len(profitable) / len(df) * 100):.1f}%")
    
    # По символам
    print("\n🏆 Топ-10 символов по прибыли:")
    symbol_pnl = df.groupby('symbol').agg({
        'pnl_usdt': ['sum', 'count', 'mean']
    }).round(4)
    symbol_pnl.columns = ['sum', 'count', 'mean']
    symbol_pnl = symbol_pnl.sort_values('sum', ascending=False)
    
    for symbol, row in symbol_pnl.head(10).iterrows():
        win_rate_symbol = (df[df['symbol'] == symbol]['pnl_usdt'] > 0).mean() * 100
        print(f"   {symbol}: {row['sum']:.2f} USDT ({int(row['count'])} сделок, WR: {win_rate_symbol:.1f}%, средняя {row['mean']:.4f})")
    
    # По причинам выхода
    if 'exit_reason' in df.columns:
        print("\n🚪 Причины выхода:")
        exit_stats = df.groupby('exit_reason').agg({
            'pnl_usdt': ['count', 'sum', 'mean']
        }).round(4)
        exit_stats.columns = ['count', 'sum', 'mean']
        print(exit_stats)
    
    # Временной анализ
    print("\n⏱️  По часам (лучшее время для торговли):")
    df['hour'] = df['entry_time'].dt.hour
    hour_stats = df.groupby('hour').agg({
        'pnl_usdt': ['count', 'sum', 'mean']
    }).round(4)
    hour_stats.columns = ['count', 'sum', 'mean']
    
    if not hour_stats.empty:
        best_hour = hour_stats['sum'].idxmax()
        print(f"   Лучший час: {best_hour}:00 (прибыль: {hour_stats.loc[best_hour, 'sum']:.2f} USDT, {int(hour_stats.loc[best_hour, 'count'])} сделок)")
    
    return {
        'total_trades': len(df),
        'profitable': len(profitable),
        'losing': len(losing),
        'total_pnl': float(df['pnl_usdt'].sum()),
        'avg_pnl': float(df['pnl_usdt'].mean()),
        'win_rate': float(len(profitable) / len(df) * 100),
        'best_symbol': str(symbol_pnl.index[0]) if not symbol_pnl.empty else None
    }

def plot_results(df, folder_path):
    """Визуализация результатов"""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. Cumulative PnL
        df_sorted = df.sort_values('entry_time')
        df_sorted['cumulative_pnl'] = df_sorted['pnl_usdt'].cumsum()
        axes[0, 0].plot(df_sorted['entry_time'], df_sorted['cumulative_pnl'], 
                        linewidth=2, color='green')
        axes[0, 0].fill_between(df_sorted['entry_time'], 0, df_sorted['cumulative_pnl'], 
                                alpha=0.3, color='green')
        axes[0, 0].set_title('Cumulative PnL Over Time')
        axes[0, 0].set_xlabel('Date')
        axes[0, 0].set_ylabel('Cumulative PnL (USDT)')
        axes[0, 0].grid(True, alpha=0.3)
        axes[0, 0].axhline(y=0, color='black', linestyle='-', alpha=0.3)
        
        # 2. PnL Distribution
        axes[0, 1].hist(df['pnl_usdt'], bins=30, edgecolor='black', alpha=0.7)
        axes[0, 1].axvline(x=0, color='red', linestyle='--', alpha=0.5, linewidth=2)
        axes[0, 1].axvline(x=df['pnl_usdt'].mean(), color='green', linestyle='--', alpha=0.5, linewidth=2, 
                          label=f'Mean: {df["pnl_usdt"].mean():.2f}')
        axes[0, 1].set_title('PnL Distribution')
        axes[0, 1].set_xlabel('PnL (USDT)')
        axes[0, 1].set_ylabel('Frequency')
        axes[0, 1].legend()
        
        # 3. Top Symbols by PnL
        symbol_pnl = df.groupby('symbol')['pnl_usdt'].sum().sort_values(ascending=False).head(15)
        if not symbol_pnl.empty:
            colors = ['green' if x > 0 else 'red' for x in symbol_pnl.values]
            axes[1, 0].barh(range(len(symbol_pnl)), symbol_pnl.values, color=colors[::-1], alpha=0.7)
            axes[1, 0].set_title('Top 15 Symbols by PnL')
            axes[1, 0].set_xlabel('PnL (USDT)')
            axes[1, 0].set_yticks(range(len(symbol_pnl)))
            axes[1, 0].set_yticklabels(symbol_pnl.index[::-1])
            axes[1, 0].axvline(x=0, color='black', linestyle='-', alpha=0.3)
        
        # 4. Win Rate by Hour
        if 'hour' in df.columns:
            hour_winrate = df.groupby('hour').apply(
                lambda x: (x['pnl_usdt'] > 0).sum() / len(x) * 100
            )
            axes[1, 1].plot(hour_winrate.index, hour_winrate.values, marker='o', linewidth=2)
            axes[1, 1].set_title('Win Rate by Hour')
            axes[1, 1].set_xlabel('Hour')
            axes[1, 1].set_ylabel('Win Rate %')
            axes[1, 1].set_xticks(range(0, 24, 3))
            axes[1, 1].grid(True, alpha=0.3)
            axes[1, 1].axhline(y=50, color='red', linestyle='--', alpha=0.5)
        
        plt.tight_layout()
        
        # Сохраняем в ту же папку
        output_file = Path(folder_path) / 'detailed_analysis.png'
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\n📊 Графики сохранены в {output_file}")
        
    except Exception as e:
        print(f"\n⚠️ Не удалось построить графики: {e}")

def main():
    parser = argparse.ArgumentParser(description='Анализ результатов бэктеста')
    parser.add_argument('--folder', type=str, default='./backtest_results',
                       help='Папка с результатами (по умолчанию: ./backtest_results)')
    args = parser.parse_args()
    
    print(f"\n📂 Анализируем папку: {args.folder}")
    
    # Загружаем данные
    df = load_results(args.folder)
    if df is None:
        return
    
    # Анализируем
    stats = analyze_trades(df)
    
    # Сохраняем статистику в ту же папку
    try:
        output_file = Path(args.folder) / 'analysis_summary.json'
        with open(output_file, 'w') as f:
            json.dump(stats, f, indent=2, default=str)
        print(f"\n💾 Статистика сохранена в {output_file}")
    except Exception as e:
        print(f"\n⚠️ Не удалось сохранить JSON: {e}")
    
    # Строим графики
    plot_results(df, args.folder)
    
    print("\n" + "=" * 60)
    print("✅ Анализ завершен")

if __name__ == "__main__":
    main()