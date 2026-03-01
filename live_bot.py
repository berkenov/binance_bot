import requests
import ccxt
import pandas as pd
import numpy as np
import statsmodels.api as sm
import time
from config import (
    TG_BOT_TOKEN, TG_CHAT_ID, TOP_PAIRS, WINDOW, load_state, save_state,
    USE_TESTNET, BINANCE_API_KEY, BINANCE_SECRET, setup_logging,
    ALLOCATION, ENABLE_TRADING, LIVE_TRADES_FILE,
    Z_ENTRY_LONG, Z_ENTRY_SHORT, Z_EXIT_TP_LONG, Z_EXIT_TP_SHORT, Z_STOP_LOSS
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

# Загрузка маркетов для precision (лоты, шаги)
try:
    exchange.load_markets()
except Exception as e:
    logger.warning("Не удалось загрузить маркеты: %s. Торговля может быть недоступна.", e)

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

def fetch_balance():
    """Получает доступный баланс USDT на Binance Futures."""
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        return 0.0
    try:
        balance = exchange.fetch_balance()
        return float(balance.get('USDT', {}).get('free', 0) or 0)
    except Exception as e:
        logger.error("Ошибка получения баланса: %s", e)
        return 0.0

def calculate_position_amounts(balance_usdt, price_a, price_b, beta):
    """
    Расчёт объёмов позиции по beta и ALLOCATION.
    Хеджирование: value_a = beta * value_b, budget = value_a + value_b.
    """
    budget = balance_usdt * ALLOCATION
    if budget <= 0:
        return 0.0, 0.0
    # value_b = budget / (1 + beta), value_a = budget * beta / (1 + beta)
    value_b = budget / (1 + abs(beta))
    value_a = budget * abs(beta) / (1 + abs(beta))
    amount_a = value_a / price_a if price_a > 0 else 0
    amount_b = value_b / price_b if price_b > 0 else 0
    return amount_a, amount_b

def _format_amount(symbol, amount):
    """Округляет amount до допустимой точности биржи."""
    if amount <= 0:
        return 0
    try:
        return float(exchange.amount_to_precision(symbol, amount))
    except Exception:
        return round(amount, 8)

def place_entry_orders(asset_a, asset_b, position_type, amount_a, amount_b):
    """
    Размещает ордера на вход в спред.
    position_type=1: Long spread (buy A, sell B)
    position_type=-1: Short spread (sell A, buy B)
    """
    amt_a = _format_amount(asset_a, amount_a)
    amt_b = _format_amount(asset_b, amount_b)
    if amt_a <= 0 or amt_b <= 0:
        logger.error("Нулевой объём для входа: %s %.8f, %s %.8f", asset_a, amt_a, asset_b, amt_b)
        return False
    orders_ok = True
    try:
        if position_type == 1:  # Long spread: buy A, sell B
            o1 = exchange.create_order(asset_a, 'market', 'buy', amt_a)
            o2 = exchange.create_order(asset_b, 'market', 'sell', amt_b)
        else:  # Short spread: sell A, buy B
            o1 = exchange.create_order(asset_a, 'market', 'sell', amt_a)
            o2 = exchange.create_order(asset_b, 'market', 'buy', amt_b)
        logger.info("Ордера размещены: %s %s, %s %s", asset_a, o1.get('id'), asset_b, o2.get('id'))
    except Exception as e:
        logger.exception("Ошибка размещения ордеров входа: %s", e)
        orders_ok = False
    return orders_ok

def place_exit_orders(asset_a, asset_b, position_type, amount_a, amount_b):
    """
    Размещает ордера на выход из спреда (закрытие позиции).
    """
    amt_a = _format_amount(asset_a, amount_a)
    amt_b = _format_amount(asset_b, amount_b)
    if amt_a <= 0 or amt_b <= 0:
        logger.error("Нулевой объём для выхода: %s %.8f, %s %.8f", asset_a, amt_a, asset_b, amt_b)
        return False
    orders_ok = True
    try:
        if position_type == 1:  # Были long A, short B → sell A, buy B
            o1 = exchange.create_order(asset_a, 'market', 'sell', amt_a)
            o2 = exchange.create_order(asset_b, 'market', 'buy', amt_b)
        else:  # Были short A, long B → buy A, sell B
            o1 = exchange.create_order(asset_a, 'market', 'buy', amt_a)
            o2 = exchange.create_order(asset_b, 'market', 'sell', amt_b)
        logger.info("Ордера выхода размещены: %s %s, %s %s", asset_a, o1.get('id'), asset_b, o2.get('id'))
    except Exception as e:
        logger.exception("Ошибка размещения ордеров выхода: %s", e)
        orders_ok = False
    return orders_ok

def log_trade(asset_a, asset_b, position_type, entry_price_a, entry_price_b,
              exit_price_a, exit_price_b, entry_z, exit_z, exit_reason,
              amount_a, amount_b, beta):
    """
    Сохраняет сделку в live_trades.csv для последующего анализа.
    """
    import csv
    import os
    from datetime import datetime

    # Расчёт PnL (при amount=0 — симуляция на $100 для режима только сигналов)
    amt_a = amount_a if amount_a > 0 else (50 / entry_price_a if entry_price_a > 0 else 0)
    amt_b = amount_b if amount_b > 0 else (50 / entry_price_b if entry_price_b > 0 else 0)
    if position_type == 1:  # Long spread
        pnl_a = (exit_price_a - entry_price_a) * amt_a
        pnl_b = (entry_price_b - exit_price_b) * amt_b
    else:  # Short spread
        pnl_a = (entry_price_a - exit_price_a) * amt_a
        pnl_b = (exit_price_b - entry_price_b) * amt_b
    pnl_usd = pnl_a + pnl_b
    entry_value = entry_price_a * amt_a + entry_price_b * amt_b
    pnl_pct = (pnl_usd / entry_value * 100) if entry_value > 0 else 0

    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "pair": f"{asset_a}_{asset_b}",
        "direction": "LONG" if position_type == 1 else "SHORT",
        "entry_price_a": entry_price_a,
        "entry_price_b": entry_price_b,
        "exit_price_a": exit_price_a,
        "exit_price_b": exit_price_b,
        "entry_z": entry_z,
        "exit_z": exit_z,
        "exit_reason": exit_reason,
        "pnl_usd": round(pnl_usd, 4),
        "pnl_pct": round(pnl_pct, 2),
        "beta": beta,
        "amount_a": amount_a,
        "amount_b": amount_b,
    }
    file_exists = os.path.exists(LIVE_TRADES_FILE)
    with open(LIVE_TRADES_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    logger.info("Сделка записана в %s: %s %s | PnL: %.2f%%", LIVE_TRADES_FILE, row["pair"], exit_reason, pnl_pct)

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
            pair_state = {
                "in_position": False, "position_type": 0,
                "entry_price_a": 0, "entry_price_b": 0,
                "amount_a": 0, "amount_b": 0, "entry_z": 0
            }
            state[pair_key] = pair_state
            
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
        if not in_pos and z_score < Z_ENTRY_LONG:
            balance = fetch_balance() if ENABLE_TRADING else 1000.0  # для расчёта при логировании
            amount_a, amount_b = calculate_position_amounts(balance, current_price_a, current_price_b, beta)

            orders_placed = False
            if ENABLE_TRADING and amount_a > 0 and amount_b > 0:
                if place_entry_orders(asset_a, asset_b, 1, amount_a, amount_b):
                    orders_placed = True
                else:
                    logger.error("Вход отменён из-за ошибки ордеров")
                    time.sleep(0.5)
                    continue

            # Обновляем state только если разместили ордера или режим только сигналов
            if orders_placed or not ENABLE_TRADING:
                pair_state['in_position'] = True
                pair_state['position_type'] = 1
                pair_state['entry_z'] = z_score
                pair_state['entry_price_a'] = current_price_a
                pair_state['entry_price_b'] = current_price_b
                pair_state['amount_a'] = amount_a if ENABLE_TRADING else 0
                pair_state['amount_b'] = amount_b if ENABLE_TRADING else 0

            msg = f"🟢 <b>СИГНАЛ ВХОДА!</b>\nПара: {asset_a} / {asset_b}\nНаправление: ЛОНГ Спреда (Купить А, Продать B)\nZ-Score: {z_score:.2f}\nBeta: {beta:.4f}"
            if ENABLE_TRADING and orders_placed:
                msg += f"\nОбъём A: {amount_a:.6g} | B: {amount_b:.6g}"
            logger.info("СИГНАЛ ВХОДА ЛОНГ: %s / %s | Z: %.2f | Цена A: %.6g | Цена B: %.6g", asset_a, asset_b, z_score, current_price_a, current_price_b)
            send_telegram_message(msg)
            save_state(state)
            
        # Вход (Шорт спреда)
        elif not in_pos and z_score > Z_ENTRY_SHORT:
            balance = fetch_balance() if ENABLE_TRADING else 1000.0
            amount_a, amount_b = calculate_position_amounts(balance, current_price_a, current_price_b, beta)

            orders_placed = False
            if ENABLE_TRADING and amount_a > 0 and amount_b > 0:
                if place_entry_orders(asset_a, asset_b, -1, amount_a, amount_b):
                    orders_placed = True
                else:
                    logger.error("Вход отменён из-за ошибки ордеров")
                    time.sleep(0.5)
                    continue

            if orders_placed or not ENABLE_TRADING:
                pair_state['in_position'] = True
                pair_state['position_type'] = -1
                pair_state['entry_z'] = z_score
                pair_state['entry_price_a'] = current_price_a
                pair_state['entry_price_b'] = current_price_b
                pair_state['amount_a'] = amount_a if ENABLE_TRADING else 0
                pair_state['amount_b'] = amount_b if ENABLE_TRADING else 0

            msg = f"🔴 <b>СИГНАЛ ВХОДА!</b>\nПара: {asset_a} / {asset_b}\nНаправление: ШОРТ Спреда (Продать А, Купить B)\nZ-Score: {z_score:.2f}\nBeta: {beta:.4f}"
            if ENABLE_TRADING and orders_placed:
                msg += f"\nОбъём A: {amount_a:.6g} | B: {amount_b:.6g}"
            logger.info("СИГНАЛ ВХОДА ШОРТ: %s / %s | Z: %.2f | Цена A: %.6g | Цена B: %.6g", asset_a, asset_b, z_score, current_price_a, current_price_b)
            send_telegram_message(msg)
            save_state(state)
            
        # Выход: Фиксация прибыли или Аварийный Стоп-лосс
        elif in_pos:
            exit_trigger = False
            exit_reason = ""
            
            # Тейк-профит: Пересечение нуля
            if pos_type == 1 and z_score >= Z_EXIT_TP_LONG:
                exit_trigger = True
                exit_reason = "Take Profit"
            elif pos_type == -1 and z_score <= Z_EXIT_TP_SHORT:
                exit_trigger = True
                exit_reason = "Take Profit"
                
            # Стоп-лосс
            if z_score > Z_STOP_LOSS or z_score < -Z_STOP_LOSS:
                exit_trigger = True
                exit_reason = "Stop Loss"
                
            if exit_trigger:
                amt_a = pair_state.get('amount_a', 0) or 0
                amt_b = pair_state.get('amount_b', 0) or 0

                if ENABLE_TRADING and amt_a > 0 and amt_b > 0:
                    if not place_exit_orders(asset_a, asset_b, pos_type, amt_a, amt_b):
                        logger.error("Выход отменён из-за ошибки ордеров")
                        time.sleep(0.5)
                        continue

                # Логирование сделки для анализа
                log_trade(
                    asset_a, asset_b, pos_type,
                    pair_state['entry_price_a'], pair_state['entry_price_b'],
                    current_price_a, current_price_b,
                    pair_state['entry_z'], z_score, exit_reason,
                    amt_a, amt_b, beta
                )

                pair_state['in_position'] = False
                pair_state['position_type'] = 0
                pair_state['amount_a'] = 0
                pair_state['amount_b'] = 0

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
    if ENABLE_TRADING and (not BINANCE_API_KEY or not BINANCE_SECRET):
        logger.error("ENABLE_TRADING=true, но API ключи не заданы. Ордера не будут размещаться.")
    mode = "TESTNET (тестовые деньги)" if USE_TESTNET else "MAINNET (реальные деньги)"
    trade_mode = "ТОРГОВЛЯ ВКЛ" if ENABLE_TRADING else "Только сигналы (торговля выкл)"
    startup_msg = f"🟢 Бот запущен. Режим: {mode}. {trade_mode}. Мониторинг {len(TOP_PAIRS)} пар."
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
