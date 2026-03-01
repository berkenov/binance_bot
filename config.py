# config.py

import json
import logging
import os
from logging.handlers import RotatingFileHandler

# Загрузка .env (если установлен python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# === Binance Futures: Mainnet или Testnet ===
# True = тестовые деньги (testnet.binancefuture.com)
# False = реальная торговля (ОСТОРОЖНО!)
USE_TESTNET = True

# API ключи для Binance Futures
# Testnet: создайте ключи на https://testnet.binancefuture.com
# Mainnet: создайте ключи в настройках Binance
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")

# Telegram Настройки
TG_BOT_TOKEN = "8618153738:AAEbDalCYQoeUOvLxtkiKCInY645OKxjd48"
TG_CHAT_ID = "837500523"

# Торговые настройки
# В идеале эти пары должны подтягиваться динамически из valid_pairs.csv (Топ-5),
# но по ТЗ сейчас мы жестко кодируем их (Топ-5 лучших из бэктеста).
TOP_PAIRS = [
    ("DOT/USDT:USDT", "UNI/USDT:USDT"),
    ("LDO/USDT:USDT", "SEI/USDT:USDT"),
    ("NEAR/USDT:USDT", "UNI/USDT:USDT"),
    ("AVAX/USDT:USDT", "LINK/USDT:USDT"),
    ("DOGE/USDT:USDT", "LINK/USDT:USDT")
]

# Параметры стратегии
WINDOW = 100
ALLOCATION = 0.2
INITIAL_CAPITAL = 1000.0

def load_state():
    default_state = {}
    for asset_a, asset_b in TOP_PAIRS:
        pair_key = f"{asset_a}_{asset_b}"
        default_state[pair_key] = {
            "in_position": False,
            "position_type": 0,
            "entry_price_a": 0,
            "entry_price_b": 0,
            "amount_a": 0,
            "amount_b": 0,
            "entry_z": 0
        }
        
    try:
        with open('state.json', 'r') as f:
            state = json.load(f)
            # Если файл содержит только {}, инициализируем его дефолтным стейтом
            if not state:
                save_state(default_state)
                return default_state
            return state
    except (FileNotFoundError, json.JSONDecodeError):
        save_state(default_state)
        return default_state

def save_state(state):
    with open('state.json', 'w') as f:
        json.dump(state, f, indent=4)


def setup_logging(name='bot', level=logging.INFO, log_dir='logs'):
    """Настройка логирования: консоль + файл с ротацией."""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'{name}.log')

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Очищаем существующие хэндлеры (избегаем дублирования при повторном вызове)
    logger.handlers.clear()

    fmt = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Консоль
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Файл с ротацией (5 MB, 3 бэкапа)
    fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
