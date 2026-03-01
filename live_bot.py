import requests
import ccxt
import pandas as pd
import numpy as np
import statsmodels.api as sm
import time
from config import (
    TG_BOT_TOKEN, TG_CHAT_ID, TOP_PAIRS, WINDOW, load_state, save_state,
    USE_TESTNET, BINANCE_API_KEY, BINANCE_SECRET, setup_logging
)

logger = setup_logging('live_bot')

# Инициализируем биржу (Binance USD-M Futures)
exchange = ccxt.binanceusdm({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True},
})

if USE_TESTNET:
    exchange.set_sandbox_mode(True)
    logger.warning("Режим: BINANCE FUTURES TESTNET (тестовые деньги)")

def send_telegram_message(text):
    """
    Отправляет сообщение в Telegram-чат через HTTP API.
    """
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error("Ошибка при отправке сообщения в Telegram: %s", e)

def fetch_historical_prices(symbol, timeframe='1h', limit=WINDOW):
    """
    Загружает последние свечи для формирования окна скользящей средней 
    """
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df['close']
    except Exception as e:
        logger.error("Ошибка загрузки истории %s: %s", symbol, e)
        return None

def fetch_current_price(symbol):
    """
    Получает актуальную текущую цену инструмента
    """
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        logger.error("Ошибка получения цены %s: %s", symbol, e)
        return None

def calculate_current_zscore(price_a_series, price_b_series):
    """
    Считает бету, спред и текущий z-score по переданным сериям (длина должна быть равна WINDOW)
    """
    log_a = np.log(price_a_series)
    log_b = np.log(price_b_series)
    
    # Считаем бету по истории
    model = sm.OLS(log_a, log_b)
    results = model.fit()
    beta = results.params.iloc[0]
    
    # Считаем спред за весь период
    spread = log_a - (beta * log_b)
    
    # Берем среднее и стандартное отклонение за окно
    mean_spread = spread.mean()
    std_spread = spread.std()
    
    # Текущий Z-Score (самое последнее значение)
    current_spread = spread.iloc[-1]
    
    # Предотвращаем деление на нуль
    if std_spread == 0:
         return 0, beta
         
    z_score = (current_spread - mean_spread) / std_spread
    
    return z_score, beta

def run_monitor():
    state = load_state()
    
    logger.info("--- Проверка рынка --- %s", time.strftime('%Y-%m-%d %H:%M:%S'))

    for asset_a, asset_b in TOP_PAIRS:
        pair_key = f"{asset_a}_{asset_b}"
        pair_state = state.get(pair_key)
        
        if not pair_state:
            continue
            
        logger.info("Анализ %s - %s", asset_a, asset_b)
        
        # 1. Формируем историю для расчета Z-Score
        # Для простоты запрашиваем окно свечей + прикрепляем текущую цену
        history_a = fetch_historical_prices(asset_a, limit=WINDOW)
        history_b = fetch_historical_prices(asset_b, limit=WINDOW)
        
        if history_a is None or history_b is None:
            continue
            
        # Текущая цена
        current_price_a = fetch_current_price(asset_a)
        current_price_b = fetch_current_price(asset_b)
        
        if current_price_a is None or current_price_b is None:
            continue
            
        # Задаем единый общий Timestamp для "временной свечи"
        common_timestamp = pd.Timestamp.utcnow()
            
        # Добавляем текущую цену "Временной свечой" в конец
        history_a.loc[common_timestamp] = current_price_a
        history_b.loc[common_timestamp] = current_price_b
        
        # Оставляем ровно WINDOW элементов для расчета
        history_a = history_a.tail(WINDOW)
        history_b = history_b.tail(WINDOW)
        
        # 2. Пересчет Z-Score
        z_score, beta = calculate_current_zscore(history_a, history_b)
        
        logger.info(
            "  %s | %s | Z-Score: %.2f | Бета: %.4f | Цена A: %.6g | Цена B: %.6g | in_position: %s",
            asset_a, asset_b, z_score, beta, current_price_a, current_price_b, pair_state['in_position']
        )
        
        # 3. Проверка триггеров (Машина состояний из Этапа 3)
        in_pos = pair_state['in_position']
        pos_type = pair_state['position_type']
        
        # Вход (Лонг спреда)
        if not in_pos and z_score < -2.0:
            pair_state['in_position'] = True
            pair_state['position_type'] = 1
            pair_state['entry_z'] = z_score
            pair_state['entry_price_a'] = current_price_a
            pair_state['entry_price_b'] = current_price_b
            
            msg = f"🟢 <b>СИГНАЛ ВХОДА!</b>\nПара: {asset_a} / {asset_b}\nНаправление: ЛОНГ Спреда (Купить А, Продать B)\nZ-Score: {z_score:.2f}\nКоэфф. Хеджирования (Beta): {beta:.4f}"
            logger.info("СИГНАЛ ВХОДА ЛОНГ: %s / %s | Z: %.2f | Цена A: %.6g | Цена B: %.6g", asset_a, asset_b, z_score, current_price_a, current_price_b)
            send_telegram_message(msg)
            save_state(state)
            
        # Вход (Шорт спреда)
        elif not in_pos and z_score > 2.0:
            pair_state['in_position'] = True
            pair_state['position_type'] = -1
            pair_state['entry_z'] = z_score
            pair_state['entry_price_a'] = current_price_a
            pair_state['entry_price_b'] = current_price_b
            
            msg = f"🔴 <b>СИГНАЛ ВХОДА!</b>\nПара: {asset_a} / {asset_b}\nНаправление: ШОРТ Спреда (Продать А, Купить B)\nZ-Score: {z_score:.2f}\nКоэфф. Хеджирования (Beta): {beta:.4f}"
            logger.info("СИГНАЛ ВХОДА ШОРТ: %s / %s | Z: %.2f | Цена A: %.6g | Цена B: %.6g", asset_a, asset_b, z_score, current_price_a, current_price_b)
            send_telegram_message(msg)
            save_state(state)
            
        # Выход: Фиксация прибыли или Аварийный Стоп-лосс
        elif in_pos:
            exit_trigger = False
            exit_reason = ""
            
            # Тейк-профит: Пересечение нуля
            if pos_type == 1 and z_score >= -0.5:
                exit_trigger = True
                exit_reason = "Take Profit"
            elif pos_type == -1 and z_score <= 0.5:
                exit_trigger = True
                exit_reason = "Take Profit"
                
            # Стоп-лосс
            if z_score > 4.0 or z_score < -4.0:
                exit_trigger = True
                exit_reason = "Stop Loss"
                
            if exit_trigger:
                pair_state['in_position'] = False
                pair_state['position_type'] = 0
                
                icon = "✅" if exit_reason == "Take Profit" else "☠️"
                msg = f"{icon} <b>СИГНАЛ ВЫХОДА ({exit_reason})</b>\nПара: {asset_a} / {asset_b}\nТекущий Z-Score: {z_score:.2f}\nZ-Score при открытии: {pair_state['entry_z']:.2f}"
                logger.info(
                    "СИГНАЛ ВЫХОДА (%s): %s / %s | Z: %.2f -> %.2f | Цена A: %.6g | Цена B: %.6g",
                    exit_reason, asset_a, asset_b, pair_state['entry_z'], z_score, current_price_a, current_price_b
                )
                send_telegram_message(msg)
                save_state(state)
                
        # Небольшая пауза между парами для API Limit
        time.sleep(0.5)

if __name__ == "__main__":
    mode = "TESTNET (тестовые деньги)" if USE_TESTNET else "MAINNET (реальные деньги)"
    startup_msg = f"🟢 Бот запущен. Режим: {mode}. Мониторинг 5 пар начат."
    logger.info(startup_msg)
    send_telegram_message(startup_msg)

    # Бесконечный цикл опроса
    # На часовом фрейме разумно проверять цены каждые 1-5 минут
    monitor_interval_seconds = 300  # 5 минут

    while True:
        try:
            run_monitor()
        except Exception as e:
            logger.exception("Непредвиденная ошибка в основном цикле: %s", e)

        logger.info("Ожидание %d минут до следующей проверки...", monitor_interval_seconds // 60)
        time.sleep(monitor_interval_seconds)
