"""Unit test: indikator teknikal murni (tanpa network).

Memakai fungsi privat _sma/_rsi/_macd dari screener dengan data sintetis,
bukan panggilan Yahoo -- memastikan matematika indikator benar & testable.
"""
import pandas as pd
from app.services.screener import _sma, _rsi, _macd


def test_sma():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert _sma(s, 3) == 4.0          # (3+4+5)/3


def test_sma_insufficient_data():
    s = pd.Series([1.0, 2.0])
    assert _sma(s, 3) is None


def test_rsi_bounds():
    # Uptrend sempurna -> RSI tinggi (>= 90)
    up = pd.Series(range(1, 40), dtype=float)
    rsi_up = _rsi(up, 14)
    assert rsi_up is not None and rsi_up > 90
    # Downtrend sempurna -> RSI rendah (<= 10)
    down = pd.Series(range(40, 1, -1), dtype=float)
    rsi_down = _rsi(down, 14)
    assert rsi_down is not None and rsi_down < 10


def test_macd_structure():
    s = pd.Series([float(i) for i in range(1, 80)])
    macd = _macd(s)
    assert macd is not None
    assert {"macd", "signal", "histogram", "macd_prev", "signal_prev"} <= set(macd.keys())
