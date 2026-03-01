"""Pytest fixtures and configuration."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock ccxt before live_bot is imported (avoids network calls in CI)
mock_exchange = MagicMock()
mock_exchange.load_markets = MagicMock()
mock_exchange.amount_to_precision = lambda s, a: round(float(a), 8) if a and float(a) > 0 else 0

patcher = patch("ccxt.binanceusdm", return_value=mock_exchange)
patcher.start()


@pytest.fixture
def temp_valid_pairs(tmp_path):
    """Создаёт временный valid_pairs.csv."""
    content = """Asset_1,Asset_2,P_Value
DOT/USDT:USDT,UNI/USDT:USDT,0.00001
LDO/USDT:USDT,SEI/USDT:USDT,0.00002
NEAR/USDT:USDT,UNI/USDT:USDT,0.00003
AVAX/USDT:USDT,LINK/USDT:USDT,0.00004
DOGE/USDT:USDT,LINK/USDT:USDT,0.00005
"""
    filepath = tmp_path / "valid_pairs.csv"
    filepath.write_text(content)
    return str(filepath)


@pytest.fixture
def temp_state_file(tmp_path):
    """Создаёт временный state.json."""
    content = """{
    "DOT/USDT:USDT_UNI/USDT:USDT": {
        "in_position": false,
        "position_type": 0,
        "entry_price_a": 0,
        "entry_price_b": 0,
        "amount_a": 0,
        "amount_b": 0,
        "entry_z": 0
    }
}
"""
    filepath = tmp_path / "state.json"
    filepath.write_text(content)
    return str(filepath)
