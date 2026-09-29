"""The figure script must be deterministic and must report the real backtest numbers."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import make_figures  # noqa: E402

EXPECTED = {
    "banner-dark.svg",
    "banner-light.svg",
    "architecture-dark.svg",
    "architecture-light.svg",
    "equity-dark.png",
    "equity-light.png",
    "metrics-dark.png",
    "metrics-light.png",
    "social-preview.png",
}


def _digests(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_make_figures_is_deterministic_and_complete(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    summary = make_figures.main(first)
    make_figures.main(second)
    assert set(_digests(first)) == EXPECTED
    assert _digests(first) == _digests(second)
    # Same run as examples/offline_backtest.py (includes its $1 commission per fill).
    assert round(summary["total_return_pct"], 2) == -9.81
    assert summary["num_trades"] == 10


def test_social_preview_is_1280x640(tmp_path: Path) -> None:
    make_figures.main(tmp_path)
    data = (tmp_path / "social-preview.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") == 1280
    assert int.from_bytes(data[20:24], "big") == 640
