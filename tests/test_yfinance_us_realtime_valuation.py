"""Offline regressions for US valuation fields and the current quote contract."""

import sys
from types import SimpleNamespace

import pytest

from data_provider.yfinance_fetcher import YfinanceFetcher


class _Ticker:
    def __init__(self, info):
        self.info_payload = info
        self.info_reads = 0
        self.fast_info = SimpleNamespace(
            lastPrice=210.0, previousClose=200.0, open=205.0,
            dayHigh=212.0, dayLow=204.0, lastVolume=1000, marketCap=100000,
        )

    @property
    def info(self):
        self.info_reads += 1
        if isinstance(self.info_payload, Exception):
            raise self.info_payload
        return self.info_payload


def _quote(monkeypatch, info, code="AAPL"):
    ticker = _Ticker(info)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _: ticker))
    fetcher = YfinanceFetcher()
    monkeypatch.setattr(
        fetcher, "_get_us_stock_quote_from_stooq",
        lambda _: pytest.fail("Optional valuation failure must preserve the available price"),
    )
    return fetcher.get_realtime_quote(code), ticker


@pytest.mark.parametrize("code", ["AAPL", "VOO", "QQQ", "QQQM"])
def test_us_quotes_reuse_info_for_valuation(monkeypatch, code):
    quote, ticker = _quote(monkeypatch, {
        "shortName": "Example US asset", "trailingPE": "39.67", "priceToBook": 45.08,
        "currency": "usd",
    }, code)

    assert quote is not None
    assert quote.price == 210.0
    assert quote.change_pct == 5.0
    assert quote.pe_ratio == 39.67
    assert quote.pb_ratio == 45.08
    assert quote.market == "us"
    assert quote.currency == "USD"
    assert quote.data_quality == "partial"
    assert quote.missing_fields == ["amount"]
    assert ticker.info_reads == 1


@pytest.mark.parametrize("info,expected_pe,expected_pb", [
    ({}, None, None),
    ({"trailingPE": None, "priceToBook": None}, None, None),
    ({"trailingPE": "unavailable", "priceToBook": []}, None, None),
    ({"trailingPE": float("nan"), "priceToBook": "NaN"}, None, None),
    ({"trailingPE": "invalid", "priceToBook": 5.2}, None, 5.2),
    ({"trailingPE": 22.0, "priceToBook": {}}, 22.0, None),
    (None, None, None),
    (RuntimeError("Info endpoint unavailable"), None, None),
])
def test_missing_or_invalid_valuation_preserves_quote(monkeypatch, info, expected_pe, expected_pb):
    quote, ticker = _quote(monkeypatch, info)

    assert quote is not None
    assert quote.price == 210.0
    assert quote.pe_ratio == expected_pe
    assert quote.pb_ratio == expected_pb
    assert quote.market == "us"
    assert quote.data_quality == "partial"
    assert ("pe_ratio" in quote.missing_fields) == (expected_pe is None)
    assert ("pb_ratio" in quote.missing_fields) == (expected_pb is None)
    assert ticker.info_reads == 1


def test_us_index_does_not_use_stock_valuation(monkeypatch):
    quote, _ = _quote(monkeypatch, {"trailingPE": 20.0, "priceToBook": 5.0}, "SPX")

    assert quote is not None
    assert quote.price == 210.0
    assert quote.pe_ratio is None
    assert quote.pb_ratio is None
