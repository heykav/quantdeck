from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass

from quantdeck.models import Fill, OrderSide


@dataclass
class Metrics:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    calmar: float
    volatility_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    num_trades: int


def compute_metrics(
    equity_curve: list[float],
    trade_pnls: list[float],
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> Metrics:
    """Compute performance and risk statistics for an equity curve.

    ``risk_free_rate`` is an *annualized* rate — pass ``0.04`` for 4% — and is
    converted to a per-period rate before being subtracted from returns, so
    both Sharpe and Sortino measure return in excess of the risk-free rate
    rather than raw return. The default of ``0.0`` reproduces the original
    zero-rate behaviour exactly.

    Ratio metrics are undefined when their denominator is zero (a flat curve
    has no volatility to divide by, a strategy that never gave back its high
    water mark has no drawdown). Those cases report ``0.0`` rather than
    ``inf`` so a single lucky run can't outrank everything else in a
    comparison; ``profit_factor`` is the deliberate exception and does go to
    ``inf``, because there the zero denominator means *no losing trades at
    all*, which is genuinely the best possible outcome rather than a
    degenerate one.
    """
    if len(equity_curve) < 2:
        raise ValueError("Need at least two equity points to compute metrics")

    start, end = equity_curve[0], equity_curve[-1]
    total_return = (end / start) - 1

    num_periods = len(equity_curve) - 1
    years = num_periods / periods_per_year
    cagr = (end / start) ** (1 / years) - 1 if years > 0 and end > 0 and start > 0 else 0.0

    returns = [
        (equity_curve[i] / equity_curve[i - 1]) - 1
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] != 0
    ]

    risk_free_per_period = risk_free_rate / periods_per_year
    annualizer = math.sqrt(periods_per_year)

    if len(returns) > 1:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance)
    else:
        # A single return, or none at all, carries no dispersion information.
        mean = returns[0] if returns else 0.0
        std = 0.0

    excess_mean = mean - risk_free_per_period
    sharpe = (excess_mean / std) * annualizer if std > 0 else 0.0
    volatility = std * annualizer

    # Downside deviation is taken about the risk-free rate over *all* periods
    # (dividing by n, not n-1) — the standard definition, since only the
    # shortfalls contribute to the sum and the flat periods are genuine zeros.
    shortfalls = [min(r - risk_free_per_period, 0.0) ** 2 for r in returns]
    downside_dev = math.sqrt(sum(shortfalls) / len(shortfalls)) if shortfalls else 0.0
    sortino = (excess_mean / downside_dev) * annualizer if downside_dev > 0 else 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)

    # Calmar pairs the growth rate against the worst peak-to-trough loss, so
    # it reads as "return per unit of pain" the way Sharpe reads as return per
    # unit of wiggle.
    calmar = cagr / max_dd if max_dd > 0 else 0.0

    wins = sum(1 for pnl in trade_pnls if pnl > 0)
    win_rate = wins / len(trade_pnls) if trade_pnls else 0.0

    gross_profit = sum(pnl for pnl in trade_pnls if pnl > 0)
    gross_loss = -sum(pnl for pnl in trade_pnls if pnl < 0)
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = math.inf if gross_profit > 0 else 0.0

    return Metrics(
        total_return_pct=total_return * 100,
        cagr_pct=cagr * 100,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        volatility_pct=volatility * 100,
        max_drawdown_pct=max_dd * 100,
        win_rate_pct=win_rate * 100,
        profit_factor=profit_factor,
        num_trades=len(trade_pnls),
    )


def compute_trade_pnls(fills: list[Fill]) -> list[float]:
    """Matches fills FIFO per symbol into round-trip trades and returns each
    trade's realized P&L (fill price difference x matched quantity)."""
    lots: dict[str, deque[list]] = defaultdict(deque)  # each lot: [sign, qty, price]
    pnls: list[float] = []

    for fill in fills:
        sign = 1 if fill.side == OrderSide.BUY else -1
        remaining = fill.qty
        queue = lots[fill.symbol]

        while remaining > 0 and queue and queue[0][0] != sign:
            open_sign, open_qty, open_price = queue[0]
            matched = min(remaining, open_qty)
            pnls.append((fill.price - open_price) * matched * open_sign)
            remaining -= matched
            if matched == open_qty:
                queue.popleft()
            else:
                queue[0][1] -= matched

        if remaining > 0:
            queue.append([sign, remaining, fill.price])

    return pnls
