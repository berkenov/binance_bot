"""Тесты для live_bot."""
import numpy as np
import pandas as pd
import pytest

from live_bot import calculate_position_amounts, calculate_current_zscore


class TestCalculatePositionAmounts:
    """Тесты расчёта объёма позиции."""

    def test_basic_calculation(self):
        """Проверка базового расчёта при balance=1000, beta=0.5."""
        amount_a, amount_b = calculate_position_amounts(1000, 1.5, 3.0, 0.5)
        # budget = 200, value_b = 200/1.5 = 133.33, value_a = 66.67
        assert amount_a > 0
        assert amount_b > 0
        assert abs(amount_a * 1.5 - 66.67) < 1
        assert abs(amount_b * 3.0 - 133.33) < 1

    def test_zero_balance(self):
        """При нулевом балансе — нулевые объёмы."""
        amount_a, amount_b = calculate_position_amounts(0, 1.0, 1.0, 1.0)
        assert amount_a == 0
        assert amount_b == 0

    def test_negative_budget_returns_zero(self):
        """При отрицательном балансе — нулевые объёмы."""
        amount_a, amount_b = calculate_position_amounts(-100, 1.0, 1.0, 1.0)
        assert amount_a == 0
        assert amount_b == 0

    def test_hedge_ratio_value_a_equals_beta_times_value_b(self):
        """value_a = beta * value_b."""
        balance = 1000
        price_a, price_b = 2.0, 4.0
        beta = 0.5
        amount_a, amount_b = calculate_position_amounts(balance, price_a, price_b, beta)
        value_a = amount_a * price_a
        value_b = amount_b * price_b
        assert abs(value_a - beta * value_b) < 0.01

    def test_negative_beta_uses_abs(self):
        """Отрицательная beta обрабатывается через abs."""
        amount_a, amount_b = calculate_position_amounts(1000, 1.0, 1.0, -0.5)
        assert amount_a > 0
        assert amount_b > 0


class TestCalculateCurrentZscore:
    """Тесты расчёта Z-Score."""

    def test_returns_zscore_and_beta(self):
        """Функция возвращает (z_score, beta)."""
        np.random.seed(42)
        n = 100
        price_a = pd.Series(np.exp(np.cumsum(np.random.randn(n) * 0.01)))
        price_b = pd.Series(np.exp(np.cumsum(np.random.randn(n) * 0.01) * 0.5))
        z_score, beta = calculate_current_zscore(price_a, price_b)
        assert isinstance(z_score, (int, float))
        assert isinstance(beta, (int, float))

    def test_zero_std_returns_zero_zscore(self):
        """При нулевом std возвращается z_score=0."""
        price_a = pd.Series([1.0] * 100)
        price_b = pd.Series([2.0] * 100)
        z_score, beta = calculate_current_zscore(price_a, price_b)
        assert z_score == 0
