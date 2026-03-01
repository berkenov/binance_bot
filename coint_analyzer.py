import pandas as pd
import statsmodels.tsa.stattools as ts
import itertools
import os

def analyze_cointegration(p_value_threshold=0.05):
    input_file = 'historical_prices.csv'
    output_file = 'valid_pairs.csv'
    
    if not os.path.exists(input_file):
        print(f"Ошибка: файл {input_file} не найден. Сначала необходимо запустить data_fetcher.py.")
        return
        
    print(f"Загрузка цен из {input_file}...")
    df = pd.read_csv(input_file, index_col='timestamp', parse_dates=True)
    
    # Шаг 4. Препроцессинг данных: очистка от пустых значений (Strict Intersect)
    # Удаляем все строки, где есть хотя бы один NaN, чтобы длины рядов были строго одинаковыми
    initial_len = len(df)
    df.dropna(inplace=True)
    print(f"Очистка данных: удалено {initial_len - len(df)} строк с отсутствующими значениями. Осталось {len(df)} строк.")
    
    symbols = df.columns.tolist()
    
    if len(symbols) < 2:
        print("Недостаточно данных для формирования пар.")
        return
        
    print(f"Готово. Доступно активов: {len(symbols)}")
    
    # Формируем все возможные уникальные пары
    pairs = list(itertools.combinations(symbols, 2))
    print(f"Всего пар для проведения теста на коинтеграцию: {len(pairs)}")
    
    valid_pairs = []
    
    for idx, (sym1, sym2) in enumerate(pairs):
        series1 = df[sym1]
        series2 = df[sym2]
        
        try:
            # Тест Энгла-Грейнджера. Нулевая гипотеза - ряды не коинтегрированы.
            # Если p-value ниже порога (например 5%), гипотеза отвергается -> ряды коинтегрированы.
            score, p_value, _ = ts.coint(series1, series2)
            
            if p_value < p_value_threshold:
                valid_pairs.append({
                    'Asset_1': sym1,
                    'Asset_2': sym2,
                    'P_Value': p_value
                })
        except Exception as e:
            # Игнорируем в случае, если ряд является константой и тест не может отработать
            pass
            
    if valid_pairs:
        # Формируем итоговый csv с отчетом
        results_df = pd.DataFrame(valid_pairs)
        # Сортируем по P_Value от меньшего (более надежная связь) к большему
        results_df.sort_values(by='P_Value', ascending=True, inplace=True)
        results_df.to_csv(output_file, index=False)
        print(f"\nУспех! Найдено {len(valid_pairs)} коинтегрированных пар(ы).")
        print(f"Отчет сохранен в {output_file}")
    else:
        print("\nПо текущим данным коинтегрированных пар не обнаружено.")

if __name__ == "__main__":
    analyze_cointegration()
