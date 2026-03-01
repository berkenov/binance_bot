import pandas as pd
import numpy as np
import statsmodels.api as sm
import os

def init_strategy_data(top_n=5):
    pairs_file = 'valid_pairs.csv'
    prices_file = 'historical_prices.csv'
    
    if not os.path.exists(pairs_file) or not os.path.exists(prices_file):
        print(f"Ошибка: Не найдены необходимые файлы данных ({pairs_file} или {prices_file}).")
        return None, None
        
    print(f"Загрузка списка пар из {pairs_file}...")
    pairs_df = pd.read_csv(pairs_file)
    
    if pairs_df.empty:
        print("Список валидных пар пуст. Остановка.")
        return None, None
        
    # Данные уже отсортированы по P-Value по возрастанию в Шаге 1,
    # поэтому просто берем первые N строк.
    top_pairs = pairs_df.head(top_n)
    
    print(f"\nВыбрано Топ-{len(top_pairs)} пар с самым низким P-Value для анализа:")
    for idx, row in top_pairs.iterrows():
        print(f"{idx+1}. {row['Asset_1']} - {row['Asset_2']} (P-Value: {row['P_Value']:.6f})")
    
    print(f"\nЗагрузка истории цен из {prices_file}...")
    # Убеждаемся, что индекс — это время (Timestamp) и он распарсен как дата
    prices_df = pd.read_csv(prices_file, index_col='timestamp', parse_dates=True)
    print(f"Загружено {len(prices_df)} свечей.")
    
    return top_pairs, prices_df

def calculate_hedge_ratios(top_pairs, prices_df):
    results = []
    
    print("\nРасчет коэффициента хеджирования (Hedge Ratio / β) для Топ-5 пар...")
    
    for idx, row in top_pairs.iterrows():
        asset_1 = row['Asset_1']
        asset_2 = row['Asset_2']
        p_value = row['P_Value']
        
        # Обход потенциальных проблем с отсутствием данных (хотя мы уже делали dropna)
        if asset_1 not in prices_df.columns or asset_2 not in prices_df.columns:
            print(f"[{asset_1} - {asset_2}] Пропуск: нет данных в prices_df.")
            continue
            
        # 1. Извлечь исторические цены
        price_a = prices_df[asset_1]
        price_b = prices_df[asset_2]
        
        # 2. Логарифмирование
        log_a = np.log(price_a)
        log_b = np.log(price_b)
        
        # 3. OLS-регрессия (log_A, log_B)
        model = sm.OLS(log_a, log_b)
        results_model = model.fit()
        
        # 4. Извлечь коэффициент beta (наклон)
        beta = results_model.params.iloc[0]
        
        # 5. Расчет Спреда
        spread = log_a - (beta * log_b)
        
        # 6. Скользящее среднее и Стандартное отклонение (окно = 100)
        window = 100
        mean_spread = spread.rolling(window=window).mean()
        std_spread = spread.rolling(window=window).std()
        
        # 7. Z-Score (Текущее натяжение)
        z_score = (spread - mean_spread) / std_spread
        
        # Создаем датафрейм для текущей пары и удаляем NaN (первые 99 строк)
        pair_df = pd.DataFrame({
            'timestamp': prices_df.index,
            'Price_A': price_a,
            'Price_B': price_b,
            'Log_A': log_a,
            'Log_B': log_b,
            'Spread': spread,
            'Mean': mean_spread,
            'Std': std_spread,
            'Z_Score': z_score
        }).dropna()
        
        results.append({
            'Asset_1': asset_1,
            'Asset_2': asset_2,
            'P_Value': p_value,
            'Hedge_Ratio': beta,
            'Data': pair_df # Сохраняем датафрейм внутри результатов
        })
        
        print(f"[{asset_1} - {asset_2}] Beta: {beta:.4f} | Окно: {window} | Свечей после dropna: {len(pair_df)}")
        
    return results # Возвращаем список словарей с датафреймами

def generate_signals(pair_df):
    """"
    Машина состояний для генерации торговых сигналов
    1: Лонг спреда (Покупка A, Продажа B)
    -1: Шорт спреда (Продажа A, Покупка B)
    0: Выход из позиции (Take Profit)
    -99: Stop-Loss (Аварийное закрытие)
    """
    signals = []
    current_position = 0 # 0 - вне рынка, 1 - лонг, -1 - шорт
    
    for _, row in pair_df.iterrows():
        z = row['Z_Score']
        signal = np.nan
        
        # 1. Проверка на стоп-лосс (Авария)
        if z > 4.0 or z < -4.0:
            if current_position != 0:
                signal = -99
                current_position = 0
            else:
                signal = 0
                
        # 2. Проверка на тейк-профит (Пересечение нуля)
        elif current_position == 1 and z >= -0.5:
            signal = 0
            current_position = 0
        elif current_position == -1 and z <= 0.5:
            signal = 0
            current_position = 0
            
        # 3. Точки входа
        elif current_position == 0:
            if z < -2.0:
                signal = 1
                current_position = 1
            elif z > 2.0:
                signal = -1
                current_position = -1
            else:
                signal = 0
        else:
            signal = current_position # Удержание позиции
            
        signals.append(signal)
        
    pair_df['Signal'] = signals
    return pair_df


if __name__ == "__main__":
    top_pairs, prices_df = init_strategy_data()
    
    if top_pairs is not None and prices_df is not None:
        analyzed_pairs = calculate_hedge_ratios(top_pairs, prices_df)
        
        print("\nГенерация сигналов...")
        signals_data = [] # Для сохранения в общий отчет
        
        for pair in analyzed_pairs:
            pair_df = pair['Data']
            asset_1 = pair['Asset_1']
            asset_2 = pair['Asset_2']
            
            # Генерация сигналов для текущей пары
            pair_df = generate_signals(pair_df)
            
            # Подсчет статистики для отчета
            entry_longs = len(pair_df[pair_df['Signal'] == 1])
            entry_shorts = len(pair_df[pair_df['Signal'] == -1])
            stop_losses = len(pair_df[pair_df['Signal'] == -99])
            
            print(f"[{asset_1} - {asset_2}] Лонгов: {entry_longs} | Шортов: {entry_shorts} | Стоп-лоссов: {stop_losses}")
            
            # Подготовка данных для итогового CSV. Оставляем только строки, где сигнал меняется
            # (моменты входа и выхода)
            pair_df = pair_df[pair_df['Signal'] != pair_df['Signal'].shift(1)].copy()
            
            base_1 = asset_1.split('/')[0]
            base_2 = asset_2.split('/')[0]
            
            pair_df = pair_df.rename(columns={
                'Price_A': f'{base_1}_Price',
                'Price_B': f'{base_2}_Price'
            })
            
            pair_df['Asset_1'] = asset_1
            pair_df['Asset_2'] = asset_2
            
            # Оставляем только нужные колонки
            cols_to_keep = ['Asset_1', 'Asset_2', f'{base_1}_Price', f'{base_2}_Price', 'Z_Score', 'Signal']
            pair_df = pair_df[cols_to_keep]
            
            signals_data.append(pair_df)
            
        # Объединяем все датафреймы пар в один
        final_report_df = pd.concat(signals_data)
        
        # Сохранение полного отчета со всеми сигналами
        output_file = 'signals_report.csv'
        final_report_df.to_csv(output_file)
        
        print(f"\nАнализ завершен! Итоговый отчет с сигналами сохранен в {output_file}")
