# Binance Pairs Trading Bot

Торговый бот для стратегии парного трейдинга (statistical arbitrage) на Binance Futures. Использует коинтеграцию и Z-Score для генерации сигналов входа и выхода.

---

## Содержание

- [Архитектура и пайплайн](#архитектура-и-пайплайн)
- [Реализованный функционал](#реализованный-функционал)
- [Запуск](#запуск)
- [Конфигурация](#конфигурация)
- [Тесты и CI/CD](#тесты-и-cicd)
- [Планируемый функционал](#планируемый-функционал)
- [Файлы проекта](#файлы-проекта)

---

## Архитектура и пайплайн

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  data_fetcher   │────▶│  coint_analyzer   │────▶│ strategy_engine  │
│  (история цен)  │     │  (коинтеграция)   │     │  (сигналы)       │
└─────────────────┘     └──────────────────┘     └────────┬─────────┘
        │                           │                      │
        │                           ▼                      ▼
        │                  valid_pairs.csv         signals_report.csv
        │                                                │
        ▼                                                ▼
 historical_prices.csv                          ┌─────────────────┐
        │                                       │   backtester    │
        │                                       │  (симуляция)    │
        │                                       └─────────────────┘
        │                                                │
        └────────────────────────────────────────────────┤
                                                         ▼
                                                ┌─────────────────┐
                                                │   live_bot      │
                                                │ (мониторинг)    │
                                                └─────────────────┘
```

---

## Реализованный функционал

### 1. `assets_list.py`
- Список из 30 торговых пар (Binance USD-M Futures)
- Таймфрейм: 1h
- Лимит свечей: 1000

### 2. `data_fetcher.py`
- Загрузка OHLCV с Binance Futures через ccxt
- Сохранение цен закрытия в `historical_prices.csv`
- Задержка между запросами для соблюдения rate limit

### 3. `coint_analyzer.py`
- Тест коинтеграции Engle-Granger для всех пар активов
- Порог p-value: 0.05
- Вывод коинтегрированных пар в `valid_pairs.csv` (отсортировано по p-value)

### 4. `strategy_engine.py`
- Расчёт коэффициента хеджирования (β) через OLS-регрессию
- Расчёт спреда: `log(A) - β * log(B)`
- Z-Score: скользящее окно 100 свечей
- **Машина состояний** для сигналов:
  - `1` — вход в лонг спреда (купить A, продать B) при Z < -2
  - `-1` — вход в шорт спреда (продать A, купить B) при Z > 2
  - `0` — выход по тейк-профиту (Z пересекает 0)
  - `-99` — стоп-лосс при Z > 4 или Z < -4
- Сохранение сигналов в `signals_report.csv`

### 5. `backtester.py`
- Симуляция торговли по `signals_report.csv`
- Стартовый капитал: $1000, аллокация на сделку: 20%
- Учёт комиссий: Maker 0.02%, Taker 0.04%
- Расчёт PnL, Win Rate, Max Drawdown
- Сохранение: `trade_history.csv`, `portfolio_curve.csv`

### 6. `live_bot.py`
- Подключение к Binance Futures (mainnet или testnet)
- Мониторинг пар каждые 5 минут (пары из `valid_pairs.csv`)
- Расчёт Z-Score в реальном времени
- Генерация сигналов входа/выхода
- **Уведомления в Telegram** при сигналах
- **Исполнение ордеров** при `ENABLE_TRADING=true` (расчёт объёма по beta, размещение market-ордеров)
- **Логирование** в `logs/live_bot.log` (цены, Z-Score, Beta, действия)
- Сохранение состояния в `state.json`

### 7. `config.py`
- Переключение mainnet/testnet (`USE_TESTNET`)
- API-ключи Binance (из `.env` или переменных окружения)
- Telegram: токен и chat_id
- **Динамическая загрузка пар** из `valid_pairs.csv` (Топ-5 по P-Value)
- Параметры: WINDOW=100, ALLOCATION=0.2
- `ENABLE_TRADING` — включение реального исполнения ордеров
- Функции `load_state`, `save_state`, `load_top_pairs`
- Настройка логирования (консоль + файл с ротацией)

---

## Запуск

### Подготовка данных (один раз или периодически)

```bash
# 1. Загрузить исторические цены
python data_fetcher.py

# 2. Найти коинтегрированные пары
python coint_analyzer.py

# 3. Сгенерировать сигналы
python strategy_engine.py

# 4. Запустить бэктест
python backtester.py
```

### Live-мониторинг

```bash
# Настроить .env (скопировать из .env.example)
# BINANCE_API_KEY, BINANCE_SECRET

python live_bot.py
```

### Тесты

```bash
pip install -r requirements.txt
pytest tests/ -v
pytest tests/ --cov=. --cov-report=term-missing  # с отчётом покрытия
```

---

## Конфигурация

Переменные окружения (`.env` или `export`):

| Переменная | Описание |
|------------|----------|
| `USE_TESTNET` | `True` — Binance Futures Testnet, `False` — mainnet |
| `BINANCE_API_KEY` | API-ключ (testnet: testnet.binancefuture.com) |
| `BINANCE_SECRET` | Секрет API |
| `TG_BOT_TOKEN` | Токен Telegram-бота |
| `TG_CHAT_ID` | ID чата для уведомлений |
| `TOP_PAIRS` | Загружаются из `valid_pairs.csv` (fallback — захардкоженный список) |
| `WINDOW` | Окно для Z-Score (свечей) |
| `ALLOCATION` | Доля капитала на сделку (0.2 = 20%) |
| `ENABLE_TRADING` | `true` — исполнение ордеров, `false` — только сигналы (по умолчанию) |
| `Z_ENTRY_LONG` | Порог входа в лонг (по умолчанию -2.0) |
| `Z_ENTRY_SHORT` | Порог входа в шорт (по умолчанию 2.0) |
| `Z_EXIT_TP_LONG` | Тейк-профит для лонга (по умолчанию -0.5) |
| `Z_EXIT_TP_SHORT` | Тейк-профит для шорта (по умолчанию 0.5) |
| `Z_STOP_LOSS` | Стоп-лосс при \|Z\| > (по умолчанию 4.0) |

---

## Анализ и оптимизация

После 2–3 недель работы бота:

1. **Сделки** сохраняются в `live_trades.csv`
2. **Анализ:** `python analyze_live_trades.py`
3. **Отчёт:** Win Rate, PnL, Z-Score при входе/выходе, рекомендации
4. **Настройка:** изменить пороги в `.env` и перезапустить бота

---

## Тесты и CI/CD

### Тесты (pytest)

- **20 тестов** для `live_bot`, `config`, `strategy_engine`, `backtester`
- Моки для ccxt (без сетевых запросов)
- Coverage: `pytest tests/ --cov=. --cov-report=term-missing`

### GitHub Actions

- **Триггер:** push / pull_request в `main`, `develop`
- **Test job:** Python 3.10, 3.11, 3.12 — установка зависимостей, pytest, coverage
- **Lint job:** ruff

Файлы: `.github/workflows/ci.yml`, `pytest.ini`, `.coveragerc`, `ruff.toml`

---

## Планируемый функционал

### Высокий приоритет ✅ (реализовано)

| # | Функционал | Описание |
|---|------------|----------|
| 1 | **Исполнение ордеров** | Реальное размещение ордеров на Binance при сигналах. Включить: `ENABLE_TRADING=true` в `.env`. |
| 2 | **Расчёт объёма позиции** | Вычисление `amount_a`, `amount_b` по beta и ALLOCATION (хеджирование: value_a = beta × value_b). |
| 3 | **Динамический выбор пар** | Автоматическая подгрузка TOP_PAIRS из `valid_pairs.csv` (Топ-5 по P-Value). |

### Средний приоритет

| # | Функционал | Описание |
|---|------------|----------|
| 4 | **Управление плечом** | Установка leverage для каждой пары через API. |
| 5 | **Периодический пересчёт коинтеграции** | Cron/скрипт для обновления `valid_pairs.csv` и `TOP_PAIRS` раз в день/неделю. |
| 6 | **Учёт funding rate** | Корректировка стратегии или учёт funding при расчёте PnL. |
| 7 | **Ручное закрытие позиций** | Команда/скрипт для принудительного закрытия всех позиций. |

### Низкий приоритет

| # | Функционал | Описание |
|---|------------|----------|
| 8 | **Веб-интерфейс** | Дашборд: текущие позиции, Z-Score, история сделок. |
| 9 | **Telegram-команды** | Управление ботом через бота: /status, /close_all, /pause. |
| 10 | **Настраиваемые пороги** | ✅ Z-Score через .env (Z_ENTRY_LONG, Z_ENTRY_SHORT, Z_EXIT_TP_*, Z_STOP_LOSS). |
| 11 | **Поддержка data_fetcher для testnet** | Опциональное использование testnet при загрузке данных. |

---

## Файлы проекта

| Файл / папка | Назначение |
|--------------|------------|
| `assets_list.py` | Список активов, таймфрейм |
| `data_fetcher.py` | Загрузка цен с Binance |
| `coint_analyzer.py` | Тест коинтеграции |
| `strategy_engine.py` | Расчёт сигналов |
| `backtester.py` | Симуляция торговли |
| `live_bot.py` | Live-мониторинг, ордера, уведомления, логирование сделок |
| `analyze_live_trades.py` | Анализ накопленных сделок, рекомендации по порогам |
| `live_trades.csv` | История live-сделок (генерируется ботом) |
| `config.py` | Конфигурация, state, логирование |
| `state.json` | Состояние позиций |
| `logs/live_bot.log` | Лог действий бота |
| `.env` | Секреты (не в git) |
| `requirements.txt` | Зависимости Python |
| `tests/` | Тесты (pytest) |
| `.github/workflows/ci.yml` | GitHub Actions CI |
| `pytest.ini` | Настройки pytest |
| `.coveragerc` | Настройки coverage |
| `ruff.toml` | Настройки линтера |
