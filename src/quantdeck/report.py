"""Versioned, strict JSON reports. Input hashes identify files, not an environment."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from quantdeck import __version__
from quantdeck.engine import BacktestEngine
from quantdeck.metrics import Metrics


def fingerprint(path: Path) -> dict[str, str]:
    """Identify the local input without disclosing its directory."""
    return {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_destination(path: Path, inputs: list[Path]) -> None:
    """Reject aliases, including hard links, to any input or the results database."""
    for source in inputs:
        if path.resolve() == source.resolve() or (
            path.exists() and source.exists() and path.samefile(source)
        ):
            raise ValueError("Report destination must differ from strategy, CSV and database files")


def _json_value(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def create_report(
    engine: BacktestEngine,
    metrics: Metrics,
    parameters: dict[str, Any],
    strategy: dict[str, str],
    source: dict[str, str],
) -> dict[str, Any]:
    """No timestamps or random IDs: identical inputs/results serialize identically."""
    return {
        "schema_version": 1,
        "runtime": {"quantdeck": __version__, "python": platform.python_version()},
        "parameters": parameters,
        "strategy": strategy,
        "data_source": source,
        "metrics": asdict(metrics),
        "equity_curve": [asdict(point) for point in engine.equity_curve],
        "fills": [asdict(fill) for fill in engine.fills],
        "limitations": [
            "Backtest only; not evidence of live trading performance.",
            "Non-finite numeric values are represented as null.",
            "Yahoo data is not snapshotted and may change between runs.",
            "Hashes cover only the named files; custom imports and dependencies are not pinned.",
            "This report does not guarantee full reproducibility.",
        ],
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    """Serialize before touching disk; atomically replace using a unique sibling file."""
    payload = json.dumps(_json_value(report), indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
