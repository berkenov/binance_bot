"""Тесты для strategy_engine."""
import numpy as np
import pandas as pd
import pytest

from strategy_engine import generate_signals


class TestGenerateSignals:
    """Тесты генерации торговых сигналов."""

    @pytest.fixture
    def pair_df(self):
        """Датафрейм с Z-Score для тестов."""
        n = 200
        np.random.seed(42)
        # Имитируем Z-Score: уход в -2.5, возврат к 0, уход в 2.5, стоп
        z = np.concatenate([
            np.linspace(0, -2.5, 50),
            np.linspace(-2.5, 0, 50),
            np.linspace(0, 2.5, 50),
            np.linspace(2.5, -0.3, 50),
        ])
        return pd.DataFrame({
            "Z_Score": z,
            "Price_A": np.ones(n) * 10,
            "Price_B": np.ones(n) * 5,
        })

    def test_generates_long_entry_at_z_below_minus_2(self, pair_df):
        """При Z < -2 генерируется сигнал 1 (long)."""
        df = generate_signals(pair_df.copy())
        assert 1 in df["Signal"].values

    def test_generates_short_entry_at_z_above_2(self, pair_df):
        """При Z > 2 генерируется сигнал -1 (short)."""
        df = generate_signals(pair_df.copy())
        assert -1 in df["Signal"].values

    def test_signal_column_exists(self, pair_df):
        """Колонка Signal добавляется."""
        df = generate_signals(pair_df.copy())
        assert "Signal" in df.columns

    def test_stop_loss_signal_minus_99(self):
        """При Z > 4 или Z < -4 в позиции генерируется -99 (стоп-лосс)."""
        # Сначала вход (z < -2), затем стоп (z > 4)
        z = np.array([0, -2.5, 5.0, 0])
        df = pd.DataFrame({"Z_Score": z, "Price_A": [1]*4, "Price_B": [1]*4})
        df = generate_signals(df)
        assert -99 in df["Signal"].values
