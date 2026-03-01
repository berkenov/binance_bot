#!/usr/bin/env python3
"""
Анализ live-сделок из live_trades.csv.
Запускать после 2-3 недель работы бота для оптимизации стратегии.
"""
import os
import sys
import pandas as pd


def analyze(filepath="live_trades.csv"):
    """Анализирует накопленные сделки и выводит отчёт."""
    if not os.path.exists(filepath):
        print(f"Файл {filepath} не найден.")
        print("Запустите бота на 2-3 недели, чтобы накопить статистику.")
        return

    df = pd.read_csv(filepath)
    if df.empty:
        print("Нет сделок для анализа.")
        return

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    n = len(df)

    print("\n" + "=" * 60)
    print("ОТЧЁТ ПО LIVE-СДЕЛКАМ")
    print("=" * 60)
    print(f"Период: {df['timestamp'].min()} — {df['timestamp'].max()}")
    print(f"Всего сделок: {n}")
    print()

    # Win Rate
    wins = (df["pnl_usd"] > 0).sum()
    losses = (df["pnl_usd"] < 0).sum()
    breakeven = (df["pnl_usd"] == 0).sum()
    win_rate = (wins / n * 100) if n > 0 else 0
    print("--- Результаты ---")
    print(f"Прибыльных: {wins} ({win_rate:.1f}%)")
    print(f"Убыточных: {losses}")
    print(f"Безубыточных: {breakeven}")
    print()

    # PnL
    total_pnl = df["pnl_usd"].sum()
    avg_pnl = df["pnl_usd"].mean()
    avg_pnl_pct = df["pnl_pct"].mean()
    print("--- PnL ---")
    print(f"Суммарный PnL: ${total_pnl:.2f}")
    print(f"Средний PnL на сделку: ${avg_pnl:.2f} ({avg_pnl_pct:.2f}%)")
    print()

    # По направлению
    print("--- По направлению ---")
    for direction in ["LONG", "SHORT"]:
        sub = df[df["direction"] == direction]
        if len(sub) > 0:
            wr = (sub["pnl_usd"] > 0).sum() / len(sub) * 100
            pnl = sub["pnl_usd"].sum()
            print(f"  {direction}: {len(sub)} сделок, Win Rate {wr:.1f}%, PnL ${pnl:.2f}")
    print()

    # По причине выхода
    print("--- По причине выхода ---")
    for reason in df["exit_reason"].unique():
        sub = df[df["exit_reason"] == reason]
        wr = (sub["pnl_usd"] > 0).sum() / len(sub) * 100
        pnl = sub["pnl_usd"].sum()
        print(f"  {reason}: {len(sub)} сделок, Win Rate {wr:.1f}%, PnL ${pnl:.2f}")
    print()

    # Z-Score при входе/выходе
    print("--- Z-Score ---")
    print(f"  При входе:  среднее {df['entry_z'].mean():.2f}, медиана {df['entry_z'].median():.2f}")
    print(f"  При выходе: среднее {df['exit_z'].mean():.2f}, медиана {df['exit_z'].median():.2f}")
    print()

    # Рекомендации
    print("--- Рекомендации для настройки ---")
    print("Текущие пороги (config.py или .env):")
    print("  Z_ENTRY_LONG, Z_ENTRY_SHORT, Z_EXIT_TP_LONG, Z_EXIT_TP_SHORT, Z_STOP_LOSS")
    print()
    if win_rate < 50 and n >= 5:
        print("⚠️  Win Rate < 50%. Рассмотрите:")
        print("   - Сужение порогов входа (например, -2.5 / +2.5 вместо -2 / +2)")
        print("   - Раньше тейк-профит (например, -0.3 / +0.3 вместо -0.5 / +0.5)")
    elif win_rate >= 55 and n >= 5:
        print("✅ Win Rate хороший. Можно попробовать:")
        print("   - Расширить пороги входа для большего числа сделок")
        print("   - Или оставить как есть")
    print()
    print("Для изменения порогов добавьте в .env:")
    print("  Z_ENTRY_LONG=-2.5")
    print("  Z_ENTRY_SHORT=2.5")
    print("  Z_EXIT_TP_LONG=-0.3")
    print("  Z_EXIT_TP_SHORT=0.3")
    print("  Z_STOP_LOSS=4.0")
    print("=" * 60)


if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else "live_trades.csv"
    analyze(filepath)
