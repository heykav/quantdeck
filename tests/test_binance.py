import hashlib
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quantdeck.cli import app
from quantdeck.data.binance import BinanceFeed, download_csv, fetch_klines, write_csv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples"))
import real_data_backtest  # noqa: E402

SAMPLE = ROOT / "examples/data/BTCUSDT_1d_2021-2025.csv"
DAY = 86_400_000
T0 = 1_609_459_200_000  # 2021-01-01 00:00 UTC


def fake_fetcher(n_candles, calls=None):
    """Mimics the klines endpoint: up to `limit` candles from startTime, daily."""
    import urllib.parse

    def get(url):
        if calls is not None:
            calls.append(url)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        start, end, limit = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
        out = []
        for i in range(n_candles):
            t = T0 + i * DAY
            if t >= start and t <= end and len(out) < limit:
                px = str(100 + i)
                out.append([t, px, px, px, px, "1.5", t + DAY - 1, "0", 1, "0", "0", "0"])
        return out

    return get


def test_fetch_pages_through_more_than_one_request():
    calls = []
    rows = fetch_klines(
        "btcusdt",
        "2021-01-01",
        "2024-12-31",
        fetcher=fake_fetcher(2500, calls),
        now_ms=T0 + 4000 * DAY,
    )
    assert len(rows) == 1461  # 2021-01-01..2024-12-31 inclusive
    assert len(calls) == 2  # 1000 + 461
    assert "symbol=BTCUSDT" in calls[0]
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)


def test_fetch_drops_candle_that_has_not_closed_yet():
    rows = fetch_klines(
        "BTCUSDT", "2021-01-01", "2021-01-10", fetcher=fake_fetcher(10), now_ms=T0 + 5 * DAY + 100
    )
    assert len(rows) == 5


def test_unsupported_interval_is_rejected():
    with pytest.raises(ValueError, match="interval"):
        fetch_klines("BTCUSDT", "2021-01-01", "2021-01-02", interval="1m")


def test_write_csv_uses_the_csv_feed_format(tmp_path):
    rows = fetch_klines(
        "X", "2021-01-01", "2021-01-03", fetcher=fake_fetcher(3), now_ms=T0 + 9 * DAY
    )
    path = write_csv(rows, tmp_path / "x.csv")
    lines = path.read_text().splitlines()
    assert lines[0] == "timestamp,open,high,low,close,volume"
    assert lines[1] == "2021-01-01,100,100,100,100,1.5"


def test_download_csv_with_no_candles_raises(tmp_path):
    with pytest.raises(ValueError, match="No candles"):
        download_csv("X", "2021-01-01", "2021-01-02", tmp_path / "x.csv", fetcher=lambda url: [])


def test_binance_feed_downloads_once_then_reads_cache(tmp_path):
    calls = []
    feed = BinanceFeed(tmp_path, fetcher=fake_fetcher(400, calls))
    first = feed.get_bars("BTCUSDT", "2021-01-01", "2021-03-01")
    again = feed.get_bars("BTCUSDT", "2021-01-01", "2021-03-01")
    assert len(first) == 60 and first == again
    assert len(calls) == 1


def test_cli_fetch_writes_csv(tmp_path, monkeypatch):
    monkeypatch.setattr("quantdeck.data.binance._http_get_json", fake_fetcher(30))
    out = tmp_path / "f.csv"
    result = CliRunner().invoke(
        app, ["fetch", "ETHUSDT", "--start", "2021-01-01", "--end", "2021-01-05", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert len(out.read_text().splitlines()) == 6


def test_committed_sample_matches_its_provenance_note():
    assert (
        hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
        in (ROOT / "examples/data/PROVENANCE.md").read_text()
    )
    lines = SAMPLE.read_text().splitlines()
    assert len(lines) - 1 == 1826
    assert lines[1].startswith("2021-01-01,28923.63") and lines[-1].startswith("2025-12-31,")


def test_committed_sample_is_clean_daily_data():
    import pandas as pd

    df = pd.read_csv(SAMPLE, parse_dates=["timestamp"])
    assert df["timestamp"].is_monotonic_increasing
    assert (df["timestamp"].diff().dropna() == pd.Timedelta(days=1)).all()
    assert (df[["open", "high", "low", "close"]] > 0).all().all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()


def test_real_data_example_is_pinned_and_buy_and_hold_pays_costs_once():
    res = real_data_backtest.run()
    sma, hold = res["SMA 10/30"], res["Buy and hold"]
    assert round(sma["metrics"].total_return_pct, 2) == 32.69
    assert round(sma["metrics"].max_drawdown_pct, 2) == 62.25
    assert (sma["fills"], sma["metrics"].num_trades, sma["rejected"]) == (76, 38, 0)
    assert round(hold["metrics"].total_return_pct, 2) == 196.68
    assert round(hold["metrics"].max_drawdown_pct, 2) == 76.34
    assert (hold["fills"], hold["rejected"]) == (1, 0)
    assert round(hold["costs"], 2) == 148.50
    assert "Buy and hold" in real_data_backtest.format_table(res)
