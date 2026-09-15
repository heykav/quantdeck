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
    max_drawdown_pct: float
    win_rate_pct: float
    num_trades: int


def compute_metrics(
    equity_curve: list[float],
    trade_pnls: list[float],
    periods_per_year: int = 252,
) -> Metrics:
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
    if len(returns) > 1:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance)
        sharpe = (mean / std) * math.sqrt(periods_per_year) if std > 0 else 0.0
    else:
        sharpe = 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)

    wins = sum(1 for pnl in trade_pnls if pnl > 0)
    win_rate = wins / len(trade_pnls) if trade_pnls else 0.0

    return Metrics(
        total_return_pct=total_return * 100,
        cagr_pct=cagr * 100,
        sharpe=sharpe,
        max_drawdown_pct=max_dd * 100,
        win_rate_pct=win_rate * 100,
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
