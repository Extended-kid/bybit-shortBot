import json
from pathlib import Path
import pandas as pd
import re

rows = []
for summary in Path(".").rglob("summary.json"):
    if "out_grid48_" not in str(summary):
        continue

    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except Exception:
        continue

    name = summary.parent.name
    m = re.search(r"p([0-9.]+)_tp([0-9.]+)_s([0-9]+)", name)
    if m:
        pump = float(m.group(1))
        tp = float(m.group(2))
        stall = int(m.group(3))
    else:
        pump = tp = stall = None

    rows.append({
        "test": str(summary.parent),
        "pump": pump,
        "tp": tp,
        "stall": stall,
        "pnl": data.get("total_pnl_with_open", data.get("total_pnl_usdt", 0)),
        "realized": data.get("realized_pnl", data.get("total_pnl_usdt", 0)),
        "ret_%": data.get("total_return_percent", 0),
        "pf": data.get("profit_factor", 0),
        "trades": data.get("total_trades", 0),
        "winrate": data.get("winrate", data.get("win_rate", 0)),
    })

df = pd.DataFrame(rows)

if df.empty:
    print("❌ Нет grid48 результатов (папки out_grid48_* / summary.json не найдены)")
else:
    df = df.sort_values("pnl", ascending=False)
    print("\n🏆 TOP 20 BY PNL")
    print(df[["pump","tp","stall","pnl","pf","trades","winrate","test"]].head(20).to_string(index=False))

    print("\n🔥 TOP 10 BY PROFIT FACTOR")
    print(df.sort_values("pf", ascending=False)[["pump","tp","stall","pnl","pf","trades","winrate","test"]].head(10).to_string(index=False))
