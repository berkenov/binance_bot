"""Тесты для config."""
import json
import os
import tempfile
from pathlib import Path

import pytest

# Импортируем до тестов, т.к. load_top_pairs вызывается при загрузке
from config import load_top_pairs, TOP_PAIRS_FALLBACK, TOP_PAIRS_N


class TestLoadTopPairs:
    """Тесты загрузки пар из valid_pairs.csv."""

    def test_returns_fallback_when_file_missing(self):
        """При отсутствии файла возвращается fallback."""
        result = load_top_pairs(filepath="/nonexistent/path.csv", top_n=5)
        assert result == TOP_PAIRS_FALLBACK

    def test_loads_from_valid_file(self, temp_valid_pairs):
        """Загружает пары из существующего файла."""
        result = load_top_pairs(filepath=temp_valid_pairs, top_n=3)
        assert len(result) == 3
        assert result[0] == ("DOT/USDT:USDT", "UNI/USDT:USDT")
        assert result[1] == ("LDO/USDT:USDT", "SEI/USDT:USDT")
        assert result[2] == ("NEAR/USDT:USDT", "UNI/USDT:USDT")

    def test_respects_top_n(self, temp_valid_pairs):
        """Учитывается параметр top_n."""
        result = load_top_pairs(filepath=temp_valid_pairs, top_n=2)
        assert len(result) == 2

    def test_empty_file_returns_fallback(self, tmp_path):
        """Пустой файл возвращает fallback."""
        empty = tmp_path / "empty.csv"
        empty.write_text("")
        result = load_top_pairs(filepath=str(empty), top_n=5)
        assert result == TOP_PAIRS_FALLBACK

    def test_file_with_less_rows_than_top_n_returns_fallback(self, tmp_path):
        """Файл с меньшим числом строк возвращает fallback."""
        content = "Asset_1,Asset_2,P_Value\nDOT/USDT:USDT,UNI/USDT:USDT,0.01\n"
        f = tmp_path / "few.csv"
        f.write_text(content)
        result = load_top_pairs(filepath=str(f), top_n=5)
        assert result == TOP_PAIRS_FALLBACK
