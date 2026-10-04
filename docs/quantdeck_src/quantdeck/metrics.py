from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass

from quantdeck.models import Fill, OrderSide, qty_tolerance

_NOISE = 1e-12


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

    Conventions (checked against independent numpy calculations in the tests):
    returns are simple period returns; volatility and Sharpe use the sample
    standard deviation (ddof=1) annualized by ``sqrt(periods_per_year)``;
    downside deviation divides by all periods; CAGR uses
    ``(len(curve) - 1) / periods_per_year`` years; max drawdown is the largest
    peak-to-trough fall as a fraction of the peak.

    Short samples: CAGR annualizes whatever span it is given, so a few bars
    can produce extreme values; if the annualized figure exceeds the float
    range it is reported as ``inf`` rather than raising ``OverflowError``.

    Ruin: the first non-positive equity value ends the curve. It is treated as
    a total loss (equity 0, return -100%, CAGR -100%, drawdown 100%) and later
    points are ignored, since a wiped-out account cannot compound back.
    Ratios whose spread is zero up to float noise (e.g. a constant growth
    rate) are reported as ``0.0``, not as an astronomically large number.
    """
    if len(equity_curve) < 2:
        raise ValueError("Need at least two equity points to compute metrics")
    if not periods_per_year > 0:
        raise ValueError(f"periods_per_year must be positive, got {periods_per_year!r}")
    if not math.isfinite(risk_free_rate):
        raise ValueError(f"risk_free_rate must be finite, got {risk_free_rate!r}")
    if not all(math.isfinite(v) for v in equity_curve):
        raise ValueError("Equity curve contains NaN or infinite values")
    if equity_curve[0] <= 0:
        raise ValueError("Starting equity must be positive")

    for i, value in enumerate(equity_curve):
        if value <= 0:
            equity_curve = [*equity_curve[:i], 0.0]
            break

    start, end = equity_curve[0], equity_curve[-1]
    total_return = (end / start) - 1

    num_periods = len(equity_curve) - 1
    years = num_periods / periods_per_year
    if end <= 0:
        cagr = -1.0
    else:
        try:
            cagr = (end / start) ** (1 / years) - 1
        except OverflowError:
            # A big gain over a very short sample annualizes past the float
            # range (e.g. 100x in one daily bar is 100**252); report inf.
            cagr = math.inf

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
    if std < _NOISE:
        std = 0.0  # constant returns: the residual is float rounding, not risk

    excess_mean = mean - risk_free_per_period
    sharpe = (excess_mean / std) * annualizer if std > 0 else 0.0
    volatility = std * annualizer

    # Downside deviation is taken about the risk-free rate over *all* periods
    # (dividing by n, not n-1) — the standard definition, since only the
    # shortfalls contribute to the sum and the flat periods are genuine zeros.
    shortfalls = [min(r - risk_free_per_period, 0.0) ** 2 for r in returns]
    downside_dev = math.sqrt(sum(shortfalls) / len(shortfalls)) if shortfalls else 0.0
    if downside_dev < _NOISE:
        downside_dev = 0.0
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
    trade's realized P&L, net of commission.

    Gross P&L is the fill-price difference times the matched quantity. Each
    fill's commission is spread over its shares pro rata, so a match is charged
    for the shares it actually covers on both the opening and closing fill.
    Positions still open at the end of the data produce no trade. Quantity
    residues within :func:`quantdeck.models.qty_tolerance` are treated as
    zero, matching how the broker settles positions.
    """
    # each lot: [sign, qty, price, commission per share]
    lots: dict[str, deque[list[float]]] = defaultdict(deque)
    pnls: list[float] = []

    for fill in fills:
        sign = 1 if fill.side == OrderSide.BUY else -1
        remaining = fill.qty
        comm_per_share = fill.commission / fill.qty if fill.qty else 0.0
        queue = lots[fill.symbol]
        # Leftovers this small are float rounding (0.3 - 0.1 - 0.1 - 0.1 is
        # not 0), not shares; keeping them would book phantom trades later.
        tol = qty_tolerance(fill.qty)

        while remaining > tol and queue and queue[0][0] != sign:
            open_sign, open_qty, open_price, open_comm = queue[0]
            matched = min(remaining, open_qty)
            gross = (fill.price - open_price) * matched * open_sign
            pnls.append(gross - (open_comm + comm_per_share) * matched)
            remaining -= matched
            if open_qty - matched <= qty_tolerance(open_qty):
                queue.popleft()
            else:
                queue[0][1] -= matched

        if remaining > tol:
            queue.append([sign, remaining, fill.price, comm_per_share])

    return pnls
