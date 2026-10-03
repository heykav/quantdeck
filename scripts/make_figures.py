"""Regenerate every image used by the README and the GitHub social preview.

All figures come from one real run of ``examples/offline_backtest.py`` (the SMA
crossover strategy on ``examples/data/synthetic.csv``, a seeded random walk that
is NOT market data). The script draws no random numbers of its own, so the output
is deterministic for a given matplotlib version.

    pip install -e ".[dev]"
    python scripts/make_figures.py            # writes docs/img/
    python scripts/make_figures.py --out DIR  # somewhere else

Needs matplotlib (a dev-only dependency; the quantdeck package does not use it).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from offline_backtest import run  # noqa: E402

from quantdeck.metrics import Metrics, compute_metrics, compute_trade_pnls  # noqa: E402
from quantdeck.models import OrderSide  # noqa: E402

SYNTH = "Synthetic data: seeded random walk (examples/data/synthetic.csv), not market data"
RUN_INFO = "SMA 10/30 crossover · 500 daily bars · 5 bps slippage · $1 commission/fill"
SCOPE = "Backtest only: no live or paper trading."

THEMES = {
    "dark": {
        "bg": "#0d0e12",
        "panel": "#161821",
        "fg": "#e8eaf0",
        "muted": "#9aa0b2",
        "grid": "#262a36",
        "line": "#3aa0ff",
        "dd": "#ff5c6c",
        "buy": "#3ddc97",
        "sell": "#ffb454",
        "edge": "#343947",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f4f6fa",
        "fg": "#14161d",
        "muted": "#586074",
        "grid": "#e3e6ee",
        "line": "#1667c9",
        "dd": "#d23a4a",
        "buy": "#12824f",
        "sell": "#b8620c",
        "edge": "#c9cedb",
    },
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "svg.fonttype": "path",
        "svg.hashsalt": "quantdeck",
    }
)


def _save(fig: plt.Figure, path: Path, **kw: object) -> None:
    meta = {"Software": None} if path.suffix == ".png" else {"Date": None}
    fig.savefig(path, facecolor=fig.get_facecolor(), metadata=meta, **kw)
    plt.close(fig)


def _backtest() -> tuple[list[datetime], list[float], list[tuple], Metrics]:
    engine, _ = run()
    curve = engine.equity_curve
    dates = [p.timestamp for p in curve]
    equity = [p.equity for p in curve]
    by_date = dict(zip(dates, equity, strict=True))
    fills = [(f.timestamp, by_date[f.timestamp], f.side) for f in engine.fills]
    metrics = compute_metrics(equity, compute_trade_pnls(engine.fills))
    return dates, equity, fills, metrics


def fmt_metric_rows(m: Metrics, ending_equity: float) -> list[tuple[str, str]]:
    """Same labels and number formats as the ``quantdeck backtest`` CLI table."""
    pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
    return [
        ("Total Return", f"{m.total_return_pct:.2f}%"),
        ("CAGR", f"{m.cagr_pct:.2f}%"),
        ("Volatility (ann.)", f"{m.volatility_pct:.2f}%"),
        ("Sharpe Ratio", f"{m.sharpe:.2f}"),
        ("Sortino Ratio", f"{m.sortino:.2f}"),
        ("Calmar Ratio", f"{m.calmar:.2f}"),
        ("Max Drawdown", f"{m.max_drawdown_pct:.2f}%"),
        ("Win Rate", f"{m.win_rate_pct:.2f}%"),
        ("Profit Factor", pf),
        ("Number of Trades", str(m.num_trades)),
        ("Ending Equity", f"${ending_equity:,.2f}"),
    ]


def _money_k(x: float, _pos: object = None) -> str:
    """Tick label in $k, with a decimal only when the tick needs one."""
    k = x / 1000
    return f"${k:,.0f}k" if abs(k - round(k)) < 1e-9 else f"${k:,.1f}k"


def _style_axis(ax, c) -> None:
    ax.set_facecolor(c["bg"])
    ax.grid(axis="y", color=c["grid"], lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(c["edge"])
    ax.tick_params(colors=c["muted"], labelsize=9, length=0)


def equity_figure(theme: str, dates, equity, fills, m: Metrics, out: Path) -> None:
    c = THEMES[theme]
    fig, (ax, ax_dd) = plt.subplots(
        2,
        1,
        figsize=(11, 6.6),
        dpi=150,
        facecolor=c["bg"],
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1.15], "hspace": 0.08},
    )
    peak = []
    hi = equity[0]
    for v in equity:
        hi = max(hi, v)
        peak.append(hi)
    # Same definition as compute_metrics: fall from the running peak, in %.
    drawdown = [(v - p) / p * 100 for v, p in zip(equity, peak, strict=True)]

    ax.plot(dates, peak, color=c["muted"], lw=0.8, ls=(0, (4, 3)), label="Running peak")
    ax.plot(dates, equity, color=c["line"], lw=1.8, label="Equity")
    buys = [(d, v) for d, v, s in fills if s == OrderSide.BUY]
    sells = [(d, v) for d, v, s in fills if s == OrderSide.SELL]
    ax.scatter(
        *zip(*buys, strict=True), marker="^", s=46, color=c["buy"], zorder=4, label="Buy fill"
    )
    ax.scatter(
        *zip(*sells, strict=True), marker="v", s=46, color=c["sell"], zorder=4, label="Sell fill"
    )
    _style_axis(ax, c)
    ax.yaxis.set_major_formatter(_money_k)
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.0),
        frameon=False,
        labelcolor=c["muted"],
        fontsize=9,
        ncol=4,
    )

    ax_dd.fill_between(dates, drawdown, 0, color=c["dd"], alpha=0.28, lw=0)
    ax_dd.plot(dates, drawdown, color=c["dd"], lw=1.0)
    worst = min(range(len(drawdown)), key=drawdown.__getitem__)
    # The panel is drawn from the equity curve itself; it must agree with the metric.
    assert abs(-drawdown[worst] - m.max_drawdown_pct) < 1e-9, (drawdown[worst], m)
    ax_dd.scatter([dates[worst]], [drawdown[worst]], s=18, color=c["dd"], zorder=4)
    ax_dd.annotate(
        f"max drawdown {m.max_drawdown_pct:.2f}%",
        (dates[worst], drawdown[worst]),
        xytext=(-8, 0),
        textcoords="offset points",
        color=c["fg"],
        fontsize=8.5,
        ha="right",
        va="center",
    )
    _style_axis(ax_dd, c)
    ax_dd.set_ylim(min(drawdown) * 1.3, 0.8)
    ax_dd.yaxis.set_major_formatter(lambda x, _: f"{x:.0f}%")
    ax_dd.set_ylabel("Drawdown", color=c["muted"], fontsize=9)

    fig.text(
        0.055,
        0.955,
        "Equity curve, drawdown and trades",
        color=c["fg"],
        fontsize=15,
        weight="bold",
        ha="left",
        va="top",
    )
    fig.text(
        0.055,
        0.912,
        f"{RUN_INFO}  ·  total return {m.total_return_pct:.2f}%,"
        f" max drawdown {m.max_drawdown_pct:.2f}%",
        color=c["muted"],
        fontsize=9.5,
        ha="left",
        va="top",
    )
    fig.text(0.055, 0.025, f"{SYNTH}. {SCOPE}", color=c["muted"], fontsize=8.5, ha="left")
    fig.subplots_adjust(left=0.085, right=0.975, top=0.83, bottom=0.095)
    _save(fig, out / f"equity-{theme}.png")


def metrics_figure(theme: str, m: Metrics, ending: float, out: Path) -> None:
    c = THEMES[theme]
    rows = fmt_metric_rows(m, ending)
    fig = plt.figure(figsize=(6.4, 6.0), dpi=150, facecolor=c["bg"])
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 6.4)
    ax.set_ylim(0, 6.0)
    ax.axis("off")
    ax.add_patch(
        FancyBboxPatch(
            (0.2, 0.2),
            6.0,
            5.6,
            boxstyle="round,pad=0,rounding_size=0.15",
            fc=c["panel"],
            ec=c["edge"],
            lw=1,
        )
    )
    ax.text(0.5, 5.4, "Backtest results", color=c["fg"], fontsize=15, weight="bold", va="center")
    ax.text(
        0.5,
        5.05,
        "SMA crossover on SYN (synthetic data)",
        color=c["muted"],
        fontsize=9.5,
        va="center",
    )
    top, step = 4.6, 0.335
    for i, (label, value) in enumerate(rows):
        y = top - i * step
        if i % 2 == 0:
            ax.add_patch(
                plt.Rectangle((0.3, y - step / 2), 5.8, step, fc=c["bg"], alpha=0.45, lw=0)
            )
        ax.text(0.5, y, label, color=c["muted"], fontsize=10.5, va="center")
        ax.text(
            5.9,
            y,
            value,
            color=c["fg"],
            fontsize=10.5,
            va="center",
            ha="right",
            family="DejaVu Sans Mono",
            weight="bold",
        )
    ax.text(
        0.5,
        0.62,
        "Output of compute_metrics() on the real equity curve.\n"
        "Synthetic seeded random walk, not market data. Not evidence of edge.",
        color=c["muted"],
        fontsize=7.8,
        va="center",
        linespacing=1.5,
    )
    _save(fig, out / f"metrics-{theme}.png")


def _box(ax, c, x0, y0, x1, y1, title, lines, accent=None):
    ax.add_patch(
        FancyBboxPatch(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            boxstyle="round,pad=0,rounding_size=0.12",
            fc=c["panel"],
            ec=accent or c["edge"],
            lw=1.6 if accent else 1.1,
            zorder=2,
        )
    )
    cx = (x0 + x1) / 2
    ty = y1 - 0.38
    ax.text(
        cx,
        ty,
        title,
        color=c["fg"],
        fontsize=10.5,
        weight="bold",
        ha="center",
        va="center",
        zorder=3,
    )
    for i, ln in enumerate(lines):
        ax.text(
            cx,
            ty - 0.42 - i * 0.3,
            ln,
            color=c["muted"],
            fontsize=7.8,
            ha="center",
            va="center",
            zorder=3,
            family="DejaVu Sans Mono",
        )


def _arrow(ax, c, p0, p1, label=None, lpos=None, color=None, rad=0.0, ls="-"):
    ax.add_patch(
        FancyArrowPatch(
            p0,
            p1,
            arrowstyle="-|>",
            mutation_scale=13,
            lw=1.4,
            color=color or c["muted"],
            connectionstyle=f"arc3,rad={rad}",
            linestyle=ls,
            zorder=4,
            shrinkA=0,
            shrinkB=0,
        )
    )
    if label:
        ax.text(*lpos, label, color=c["muted"], fontsize=7.8, ha="center", va="center", zorder=5)


def architecture_figure(theme: str, out: Path) -> None:
    c = THEMES[theme]
    fig = plt.figure(figsize=(12, 6.4), dpi=100, facecolor=c["bg"])
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 16)
    ax.set_ylim(-0.6, 8.0)
    ax.axis("off")
    ax.text(
        0.3,
        7.6,
        "How a backtest flows through QuantDeck",
        color=c["fg"],
        fontsize=16,
        weight="bold",
        va="center",
    )
    ax.text(
        0.3,
        7.1,
        "One pass per bar, in time order. Orders placed on bar t fill at the open of bar t+1.",
        color=c["muted"],
        fontsize=9.5,
        va="center",
    )

    # engine container
    ax.add_patch(
        FancyBboxPatch(
            (4.0, 3.15),
            7.7,
            3.35,
            boxstyle="round,pad=0,rounding_size=0.18",
            fc="none",
            ec=c["line"],
            lw=1.6,
            ls=(0, (5, 3)),
            zorder=1,
        )
    )
    ax.text(
        4.25,
        6.18,
        "BacktestEngine.run()",
        color=c["line"],
        fontsize=10.5,
        weight="bold",
        va="center",
    )
    ax.text(11.45, 6.18, "for each bar", color=c["muted"], fontsize=8.5, va="center", ha="right")

    _box(
        ax,
        c,
        0.3,
        3.75,
        3.1,
        5.75,
        "DataFeed",
        ["CSVDataFeed", "YFinanceFeed", "get_bars() -> [Bar]"],
    )
    _box(
        ax,
        c,
        4.4,
        3.4,
        7.0,
        5.6,
        "PaperBroker",
        ["process_bar(bar)", "fill queued orders", "at open +/- slippage"],
    )
    _box(ax, c, 8.7, 3.4, 11.3, 5.6, "Strategy", ["on_bar(bar)", "your rule -> buy()", "or sell()"])
    _box(ax, c, 4.4, 0.7, 7.0, 2.3, "Fills", ["engine.fills", "price, qty, commission"])
    _box(ax, c, 8.7, 0.7, 11.3, 2.3, "Equity curve", ["cash + qty x close", "one point per bar"])
    _box(
        ax,
        c,
        12.9,
        0.7,
        15.7,
        2.5,
        "Metrics",
        ["compute_metrics()", "compute_trade_pnls()", "return, Sharpe, drawdown..."],
        accent=c["line"],
    )

    _arrow(ax, c, (3.1, 4.75), (4.4, 4.75), "Bar", (3.75, 5.0))
    _arrow(ax, c, (7.0, 5.0), (8.7, 5.0), "bar t, after fills", (7.85, 5.25))
    _arrow(
        ax,
        c,
        (8.7, 4.0),
        (7.0, 4.0),
        "submit_order()\n(fills at next open)",
        (7.85, 3.6),
        color=c["buy"],
    )
    _arrow(ax, c, (5.7, 3.4), (5.7, 2.3), "fills", (6.15, 2.85))
    _arrow(ax, c, (10.0, 3.15), (10.0, 2.3), "after on_bar", (10.75, 2.75))
    _arrow(ax, c, (11.3, 1.5), (12.9, 1.5), "values", (12.1, 1.75))
    dash = {"color": c["muted"], "lw": 1.4, "ls": (0, (4, 3)), "zorder": 4}
    ax.plot([5.7, 5.7, 14.3], [0.7, 0.25, 0.25], **dash)
    _arrow(ax, c, (14.3, 0.25), (14.3, 0.7), "fills -> trade P&L", (10.0, 0.05), ls=(0, (4, 3)))

    ax.text(
        0.3,
        -0.35,
        "Drawn from src/quantdeck/engine.py, broker/paper.py, strategy.py and metrics.py. "
        "The SQLite Storage layer used by the CLI is omitted.\n"
        "Only this backtest path exists: there is no live or paper-trading engine.",
        color=c["muted"],
        fontsize=8,
        va="center",
        linespacing=1.5,
    )
    _save(fig, out / f"architecture-{theme}.svg", format="svg")


def _curve_points(equity: list[float], x0: float, x1: float, y0: float, y1: float):
    lo, hi = min(equity), max(equity)
    n = len(equity) - 1
    return [
        (x0 + (x1 - x0) * i / n, y1 - (y1 - y0) * (v - lo) / (hi - lo))
        for i, v in enumerate(equity)
    ]


def banner_svg(theme: str, equity: list[float], m: Metrics, out: Path) -> None:
    c = THEMES[theme]
    w, h = 1280, 340
    pts = _curve_points(equity[::2] + [equity[-1]], 0, w, 235, h - 20)
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{h} {line} {w},{h}"
    font = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"
     role="img" aria-labelledby="t d">
  <title id="t">QuantDeck</title>
  <desc id="d">QuantDeck, a small event-driven backtesting framework. Background: the real equity \
curve of the bundled SMA crossover example on synthetic data.</desc>
  <defs>
    <linearGradient id="f" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{c["line"]}" stop-opacity="0.28"/>
      <stop offset="1" stop-color="{c["line"]}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="{w}" height="{h}" rx="14" fill="{c["bg"]}"/>
  <rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="none" stroke="{c["edge"]}"/>
  <polygon points="{area}" fill="url(#f)"/>
  <polyline points="{line}" fill="none" stroke="{c["line"]}" stroke-width="2.5" \
stroke-linejoin="round"/>
  <g font-family="{font}">
    <text x="64" y="96" font-size="64" font-weight="700" fill="{c["fg"]}">QuantDeck</text>
    <text x="66" y="142" font-size="22" fill="{c["muted"]}">A small, event-driven backtesting \
framework for single-symbol strategies</text>
    <text x="66" y="178" font-size="16" fill="{c["muted"]}">Look-ahead safe fills · offline CSV \
data · equity curve, trades and risk metrics</text>
    <text x="{w - 32}" y="34" font-size="12" text-anchor="end" fill="{c["muted"]}">\
Line: real backtest equity on synthetic data ({m.total_return_pct:.2f}% total return). \
Backtest only, not live trading.</text>
  </g>
</svg>
"""
    (out / f"banner-{theme}.svg").write_text(svg, encoding="utf-8")


def social_preview(equity: list[float], m: Metrics, out: Path) -> None:
    c = THEMES["dark"]
    fig = plt.figure(figsize=(12.8, 6.4), dpi=100, facecolor=c["bg"])
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1280)
    ax.set_ylim(640, 0)
    ax.axis("off")
    pts = _curve_points(equity, 0, 1280, 390, 610)
    xs, ys = zip(*pts, strict=True)
    ax.fill_between(xs, ys, 640, color=c["line"], alpha=0.16, lw=0)
    ax.plot(xs, ys, color=c["line"], lw=3)
    ax.text(80, 150, "QuantDeck", color=c["fg"], fontsize=68, weight="bold", va="center")
    ax.text(
        84,
        232,
        "A small, event-driven backtesting framework\nfor single-symbol strategies",
        color=c["muted"],
        fontsize=25,
        va="top",
        linespacing=1.4,
    )
    ax.text(
        1200,
        60,
        f"Line: real backtest equity, synthetic data. {SCOPE}",
        color=c["muted"],
        fontsize=11,
        ha="right",
        va="center",
    )
    ax.text(84, 60, "github.com/heykav/quantdeck", color=c["line"], fontsize=15, va="center")
    _save(fig, out / "social-preview.png")


def main(out: Path) -> dict[str, float]:
    out.mkdir(parents=True, exist_ok=True)
    dates, equity, fills, m = _backtest()
    for theme in THEMES:
        equity_figure(theme, dates, equity, fills, m, out)
        metrics_figure(theme, m, equity[-1], out)
        architecture_figure(theme, out)
        banner_svg(theme, equity, m, out)
    social_preview(equity, m, out)
    return {"total_return_pct": m.total_return_pct, "num_trades": m.num_trades}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "img")
    print(main(parser.parse_args().out))
