import ccxt
import pandas as pd
import time
from assets_list import SYMBOLS, TIMEFRAME, LIMIT

def fetch_historical_data():
    print("Инициализация подключения к Binance Futures...")
    
    # Настройка подключения (Binance USDⓈ-M Futures)
    exchange = ccxt.binanceusdm({
        'enableRateLimit': True,
        'options': {
            'adjustForTimeDifference': True
        }
    })
    
    closes_data = {}
    
    for symbol in SYMBOLS:
        print(f"Загрузка данных для {symbol}...")
        try:
            # Предупреждение: для фьючерсов ccxt может требовать формат 'BTC/USDT:USDT'. 
            # Метод fetch_ohlcv по умолчанию адаптирует базовые пары, но иногда необходимо указывать тип явно.
            ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=LIMIT)
            
            if not ohlcv:
                print(f"Нет данных по {symbol}")
                continue
                
            # Извлекаем только 0-й индекс (Timestamp) и 4-й индекс (Close Price)
            data = [[row[0], row[4]] for row in ohlcv]
            df = pd.DataFrame(data, columns=['timestamp', 'close'])
            
            # Приводим Timestamp к формату datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Сохраняем только цены закрытия
            closes_data[symbol] = df['close']
            
            # Обязательная задержка во избежание блокировки по IP (HTTP 429)
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Ошибка при выгрузке {symbol}: {e}")
            
    if not closes_data:
        print("Не удалось загрузить данные ни по одному инструменту.")
        return
        
    # Сбор всех закрытий в один датафрейм
    closing_prices_df = pd.DataFrame(closes_data)
    
    # Удаление строк, где отсутствуют данные для синхронности рядов
    closing_prices_df.dropna(inplace=True)
    
    output_file = 'historical_prices.csv'
    closing_prices_df.to_csv(output_file)
    print(f"\nДанные успешно выгружены.")
    print(f"Сохранено записей: {len(closing_prices_df)} в файл {output_file}")

if __name__ == "__main__":
    fetch_historical_data()
