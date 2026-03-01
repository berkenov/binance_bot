# backtester.py

import pandas as pd
import os

# Шаг 1. Конфигурация симулятора (Настройки)
INITIAL_CAPITAL = 1000.0  # Начинаем с $1000
TRADE_ALLOCATION = 0.2    # В каждую сделку выделяем максимум 20% от текущего капитала
MAKER_FEE = 0.0002        # 0.02% комиссия Binance за лимитный ордер
TAKER_FEE = 0.0004        # 0.04% комиссия за рыночный ордер (например, стоп-лосс)

def load_and_split_signals(filepath='signals_report.csv'):
    # Шаг 2. Парсинг отчета о сигналах
    if not os.path.exists(filepath):
        print(f"Ошибка: Файл {filepath} не найден.")
        return {}
        
    print(f"\nЗагрузка данных из {filepath}...")
    df = pd.read_csv(filepath, index_col='timestamp', parse_dates=True)
    
    # Отфильтровать пустые (NaN) цены
    initial_len = len(df)
    df.dropna(inplace=True)
    if len(df) < initial_len:
        print(f"Выполнена очистка: удалено {initial_len - len(df)} пустых строк.")
        
    # Разделить данные на отдельные датафреймы по каждой паре
    pair_groups = df.groupby(['Asset_1', 'Asset_2'])
    
    pair_dfs = {}
    for (asset_1, asset_2), group in pair_groups:
        # Сортировка по времени обязательна для корректной симуляции
        pair_dfs[(asset_1, asset_2)] = group.sort_index()
        print(f"[{asset_1} - {asset_2}] Загружено сигналов: {len(group)}")
        
    return pair_dfs

def run_backtest(pair_dfs):
    # Текущий баланс
    current_capital = INITIAL_CAPITAL
    
    # Журналы
    trade_history = []
    portfolio_curve = []
    
    # Шаг 3. Итерация по парам и времени
    for (asset_1, asset_2), df in pair_dfs.items():
        base_1 = asset_1.split('/')[0]
        base_2 = asset_2.split('/')[0]
        
        price_col_1 = f"{base_1}_Price"
        price_col_2 = f"{base_2}_Price"
        
        # Переменные состояния
        in_position = False
        position_type = 0
        entry_price_A = 0
        entry_price_B = 0
        amount_A = 0
        amount_B = 0
        entry_time = None
        
        print(f"\nЗапуск симуляции для {asset_1} - {asset_2}...")
        
        for timestamp, row in df.iterrows():
            signal = row['Signal']
            price_A = row[price_col_1]
            price_B = row[price_col_2]
            
            # Логирование текущего капитала для кривой
            portfolio_curve.append({
                'timestamp': timestamp,
                'Capital': current_capital
            })
            
            # --- ЛОГИКА ВХОДА ---
            if not in_position and (signal == 1 or signal == -1):
                # Бюджет и аллокация
                budget = current_capital * TRADE_ALLOCATION
                
                amount_A = (budget / 2) / price_A
                amount_B = (budget / 2) / price_B
                
                entry_price_A = price_A
                entry_price_B = price_B
                entry_time = timestamp
                
                # Списываем комиссию (Maker)
                fee_usd = budget * MAKER_FEE
                current_capital -= fee_usd
                
                in_position = True
                position_type = signal
            
            # --- ЛОГИКА ВЫХОДА ---
            elif in_position and (signal == 0 or signal == -99):
                pnl_A = 0
                pnl_B = 0
                
                # Расчет PnL
                if position_type == 1:
                    # Лонг спреда: Покупали А, Шортили B
                    pnl_A = (price_A - entry_price_A) * amount_A
                    pnl_B = (entry_price_B - price_B) * amount_B
                elif position_type == -1:
                    # Шорт спреда: Шортили А, Покупали B
                    pnl_A = (entry_price_A - price_A) * amount_A
                    pnl_B = (price_B - entry_price_B) * amount_B
                    
                gross_pnl = pnl_A + pnl_B
                
                # Учет комиссии на выход
                exit_value = (entry_price_A * amount_A) + (entry_price_B * amount_B) + gross_pnl
                fee_rate = TAKER_FEE if signal == -99 else MAKER_FEE
                exit_fee_usd = exit_value * fee_rate
                
                net_pnl = gross_pnl - exit_fee_usd
                
                # Обновление баланса
                current_capital += net_pnl
                profit_percent = (net_pnl / exit_value) * 100
                
                # Запись в историю сделок
                trade_history.append({
                    'Pair': f"{asset_1} - {asset_2}",
                    'Position': 'LONG SPREAD' if position_type == 1 else 'SHORT SPREAD',
                    'Entry_Time': entry_time,
                    'Exit_Time': timestamp,
                    'Entry_Price_A': entry_price_A,
                    'Exit_Price_A': price_A,
                    'Entry_Price_B': entry_price_B,
                    'Exit_Price_B': price_B,
                    'Gross_PnL': gross_pnl,
                    'Net_PnL': net_pnl,
                    'Profit_%': profit_percent,
                    'Exit_Reason': 'Take Profit' if signal == 0 else 'Stop Loss'
                })
                
                # Сброс состояния
                in_position = False
                position_type = 0
                entry_price_A = 0
                entry_price_B = 0
                amount_A = 0
                amount_B = 0
                entry_time = None
                
    return pd.DataFrame(trade_history), pd.DataFrame(portfolio_curve), current_capital

def evaluate_metrics(trade_history_df, portfolio_curve_df, final_capital):
    # Если сделок не было
    if trade_history_df.empty:
        print("\n[ИТОГИ БЭКТЕСТА]")
        print("Нет завершенных сделок.")
        return
        
    # Шаг 4. Расчет метрик
    total_trades = len(trade_history_df)
    
    # Win Rate
    winning_trades = len(trade_history_df[trade_history_df['Net_PnL'] > 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
    
    # Total PnL
    net_profit = final_capital - INITIAL_CAPITAL
    profit_percent = (net_profit / INITIAL_CAPITAL) * 100
    
    # Max Drawdown
    portfolio_curve_df['Peak'] = portfolio_curve_df['Capital'].cummax()
    portfolio_curve_df['Drawdown'] = (portfolio_curve_df['Capital'] - portfolio_curve_df['Peak']) / portfolio_curve_df['Peak']
    max_drawdown = portfolio_curve_df['Drawdown'].min() * 100 # в процентах, отрицательное число
    
    print("\n[ИТОГИ БЭКТЕСТА]")
    print(f"Стартовый капитал: ${INITIAL_CAPITAL:.2f}")
    print(f"Финальный капитал: ${final_capital:.2f}")
    print(f"Чистая прибыль: ${net_profit:.2f} ({profit_percent:.2f}%)")
    print(f"Процент успешных сделок (Win Rate): {win_rate:.2f}%")
    print(f"Максимальная просадка: {max_drawdown:.2f}%")
    print(f"Всего сделок: {total_trades}")
    
    # Сохранение артефактов
    trade_history_df.to_csv('trade_history.csv', index=False)
    portfolio_curve_df.to_csv('portfolio_curve.csv', index=False)
    print("\nДетализация сделок сохранена в trade_history.csv")
    print("График изменения капитала сохранен в portfolio_curve.csv")

if __name__ == "__main__":
    print(f"Инициализация бэктестера...")
    print(f"Стартовый капитал: ${INITIAL_CAPITAL}")
    print(f"Аллокация на сделку: {TRADE_ALLOCATION * 100}%")
    print(f"Комиссия Maker: {MAKER_FEE * 100}%")
    print(f"Комиссия Taker: {TAKER_FEE * 100}%")
    
    pair_dfs = load_and_split_signals()
    
    if pair_dfs:
        trade_history_df, portfolio_curve_df, final_capital = run_backtest(pair_dfs)
        evaluate_metrics(trade_history_df, portfolio_curve_df, final_capital)
