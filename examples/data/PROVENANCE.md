# Data provenance

## `BTCUSDT_1d_2021-2025.csv` (real market data)

| Field | Value |
|---|---|
| Source | Binance spot public market data, `GET /api/v3/klines` on `https://data-api.binance.vision` (read-only market-data host, no account, no API key) |
| Instrument | BTCUSDT, daily candles, UTC day boundaries |
| Date range | 2021-01-01 to 2025-12-31 inclusive (1,826 rows) |
| Retrieved | 2026-10-29 (UTC) |
| Method | `quantdeck.data.binance.download_csv("BTCUSDT", "2021-01-01", "2025-12-31", ...)`, unmodified except for keeping the date, open, high, low, close and volume columns |
| Adjustments | None. Prices are raw spot prices quoted in USDT (volume is in BTC). USDT is a stablecoin, not exactly one US dollar. |
| SHA-256 | `20a8aa3c272b29ec333cbdf22dcdf0515a24c18dd96a8571e305553ce20b6fde` |

It is committed so the examples and tests run offline and give the same numbers
every time. Refresh it with `quantdeck fetch BTCUSDT --start 2021-01-01 --end 2025-12-31 --out <file>`;
a refresh may differ slightly if Binance revises history. Use of this data is
subject to Binance's own terms (https://www.binance.com/en/terms); check them
before redistributing it beyond this small educational sample.

## `synthetic.csv`

A seeded random walk from `scripts/make_synthetic_data.py`. It is **not** market data.
