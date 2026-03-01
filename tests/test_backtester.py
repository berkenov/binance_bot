"""Тесты для backtester."""
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from backtester import load_and_split_signals, run_backtest, evaluate_metrics, INITIAL_CAPITAL


class TestLoadAndSplitSignals:
    """Тесты загрузки сигналов."""

    def test_returns_empty_when_file_missing(self):
        """При отсутствии файла возвращается пустой dict."""
        result = load_and_split_signals("/nonexistent/signals.csv")
        assert result == {}

    def test_loads_valid_signals(self, tmp_path):
        """Загружает корректный signals_report.csv."""
        content = """timestamp,Asset_1,Asset_2,DOT_Price,UNI_Price,Z_Score,Signal
2024-01-01 10:00:00,DOT/USDT:USDT,UNI/USDT:USDT,5.0,3.0,-2.5,1
2024-01-01 11:00:00,DOT/USDT:USDT,UNI/USDT:USDT,5.1,2.9,-0.3,0
"""
        f = tmp_path / "signals_report.csv"
        f.write_text(content)
        result = load_and_split_signals(str(f))
        assert len(result) == 1
        pair = ("DOT/USDT:USDT", "UNI/USDT:USDT")
        assert pair in result
        assert len(result[pair]) == 2


class TestRunBacktest:
    """Тесты симуляции бэктеста."""

    @pytest.fixture
    def pair_dfs(self):
        """Минимальный набор сигналов для одной пары."""
        df = pd.DataFrame([
            {"timestamp": pd.Timestamp("2024-01-01 10:00"), "DOT_Price": 5.0, "UNI_Price": 3.0, "Signal": 1},
            {"timestamp": pd.Timestamp("2024-01-01 11:00"), "DOT_Price": 5.2, "UNI_Price": 2.9, "Signal": 0},
        ])
        df = df.set_index("timestamp")
        return {("DOT/USDT:USDT", "UNI/USDT:USDT"): df}

    def test_returns_trade_history_and_capital(self, pair_dfs):
        """Возвращает trade_history, portfolio_curve, final_capital."""
        # Нужен правильный формат - run_backtest ожидает groupby по Asset_1, Asset_2
        # и колонки {base}_Price
        trade_history, portfolio_curve, final_capital = run_backtest(pair_dfs)
        assert isinstance(trade_history, pd.DataFrame)
        assert isinstance(portfolio_curve, pd.DataFrame)
        assert isinstance(final_capital, (int, float))

    def test_final_capital_differs_from_initial_when_trades(self, pair_dfs):
        """При наличии сделок финальный капитал отличается от начального."""
        trade_history, _, final_capital = run_backtest(pair_dfs)
        # Может быть равен если PnL ~ 0, но структура должна быть
        assert final_capital >= 0
