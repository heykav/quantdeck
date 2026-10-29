#!/usr/bin/env python3
"""Renders the README hero, the how-it-works diagram and the social preview.

Everything is generated from one real run of the bundled engine (AAPL, SMA 10/30,
bundled 2015-2024 prices), so no number in a picture is typed in by hand.

GitHub shows README SVGs through <img>: CSS and SMIL run, script does not. Every
element is fully drawn in its base state, so a viewer that ignores animation, or
asks for reduced motion, sees the finished picture. Text is plain font text with
no per-character positions.

Run from the repo root:  python3 scripts/render_assets.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "docs" / "quantdeck_src"))
import web_glue  # noqa: E402

MONO = 'ui-monospace,"SFMono-Regular","DM Mono","DejaVu Sans Mono",Menlo,Consolas,monospace'
SERIF = 'Georgia,"Times New Roman",serif'

DARK = dict(bg="#090A09", win="#111211", line="#2a2c29", grid="#1a1b1a", text="#F4F5F2",
            mute="#9a9c96", a="#00FF66", b="#B6FF2E", chip="#0d0e0c", dot="#090A09")
LIGHT = dict(bg="#F4F5F2", win="#eceeea", line="#c4c7c0", grid="#e2e3df", text="#111211",
             mute="#54564f", a="#00A84A", b="#5f9a00", chip="#e6e8e3", dot="#F4F5F2")


def run():
    csv_text = (ROOT / "docs" / "data" / "AAPL.csv").read_text()
    return json.loads(web_glue.run_web_backtest("AAPL", csv_text, 10, 30, 100000, 0))


def curve_points(values, x0, y0, w, h, n=140):
    step = max(1, len(values) // n)
    v = values[::step] + [values[-1]]
    lo, hi = min(v), max(v)
    pts = [(x0 + w * i / (len(v) - 1), y0 + h - h * (p - lo) / (hi - lo)) for i, p in enumerate(v)]
    return pts


def path_d(pts):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def chrome(c, w, title):
    return (f'<rect x="0" y="0" width="{w}" height="40" fill="{c["bg"]}"/>'
            f'<circle cx="24" cy="20" r="6" fill="#ff5f57"/><circle cx="44" cy="20" r="6" fill="#febc2e"/>'
            f'<circle cx="64" cy="20" r="6" fill="#28c840"/>'
            f'<text x="92" y="25" font-family=\'{MONO}\' font-size="13" fill="{c["mute"]}">{title}</text>'
            f'<path d="M0 40 H{w}" stroke="{c["line"]}"/>')


def hero(c, r):
    W, H = 1200, 440
    m = r["metrics"]
    pts = curve_points(r["equity_curve"], 60, 250, 1080, 130)
    d = path_d(pts)
    area = d + f" L{pts[-1][0]:.1f} 392 L{pts[0][0]:.1f} 392 Z"
    ex, ey = pts[-1]
    chips = [("TOTAL RETURN", f'{m["total_return_pct"]:.2f}%'), ("MAX DRAWDOWN", f'{m["max_drawdown_pct"]:.2f}%'),
             ("TRADES", str(m["num_trades"])), ("SHARPE", f'{m["sharpe"]:.2f}')]
    chip_svg = ""
    for i, (k, v) in enumerate(chips):
        x = 60 + i * 190
        chip_svg += (f'<rect x="{x}" y="188" width="176" height="56" rx="8" fill="{c["chip"]}" stroke="{c["line"]}"/>'
                     f'<text x="{x+14}" y="209" font-family=\'{MONO}\' font-size="10" letter-spacing="1.5" fill="{c["mute"]}">{k}</text>'
                     f'<text x="{x+14}" y="234" font-family=\'{MONO}\' font-size="20" font-weight="700" fill="{c["a"]}">{v}</text>')
    return f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="t d">
<title id="t">QuantDeck</title>
<desc id="d">A terminal window showing the QuantDeck name, its one-line pitch and a real equity curve from a bundled-data SMA 10/30 backtest of AAPL, 2015 to 2024, with the engine's own summary numbers.</desc>
<defs>
<pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="{c["grid"]}"/></pattern>
<linearGradient id="s" x1="0" x2="1"><stop offset="0" stop-color="{c["a"]}"/><stop offset="1" stop-color="{c["b"]}"/></linearGradient>
<linearGradient id="f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c["a"]}" stop-opacity=".22"/><stop offset="1" stop-color="{c["a"]}" stop-opacity="0"/></linearGradient>
<clipPath id="k"><rect width="{W}" height="{H}" rx="14"/></clipPath>
</defs>
<style>
.pulse{{animation:p 2.4s ease-in-out infinite}}
@keyframes p{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<g clip-path="url(#k)">
<rect width="{W}" height="{H}" fill="{c["win"]}"/>
<rect y="40" width="{W}" height="{H-40}" fill="{c["bg"]}"/><rect y="40" width="{W}" height="{H-40}" fill="url(#g)"/>
{chrome(c, W, "quantdeck backtest strategy.py --symbol AAPL")}
<text x="60" y="96" font-family=\'{MONO}\' font-size="13" letter-spacing="2.4" fill="{c["a"]}">EVENT-DRIVEN BACKTESTING</text>
<text x="60" y="142" font-family=\'{SERIF}\' font-size="46" font-weight="700" fill="{c["text"]}">QuantDeck</text>
<text x="62" y="168" font-family=\'{MONO}\' font-size="15" fill="{c["mute"]}">Write a strategy. Replay it on real prices. No server, no keys.</text>
{chip_svg}
<path d="M60 392 H1140" stroke="{c["line"]}"/>
<path d="{area}" fill="url(#f)"/>
<path d="{d}" fill="none" stroke="url(#s)" stroke-width="2.5" stroke-linejoin="round"/>
<circle cx="{ex:.1f}" cy="{ey:.1f}" r="9" fill="{c["b"]}" opacity=".25" class="pulse"/>
<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="{c["b"]}"/>
<text x="60" y="418" font-family=\'{MONO}\' font-size="11" fill="{c["mute"]}">Real engine output: AAPL, SMA 10/30, bundled daily prices 2015-2024, $100,000 start. A past simulation, not a prediction or advice.</text>
</g>
<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="14" fill="none" stroke="{c["line"]}"/>
</svg>
'''


def diagram(c):
    W, H = 1200, 380
    def box(x, y, w, h, title, sub, hi=False):
        st = c["a"] if hi else c["line"]
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{c["win"]}" stroke="{st}" stroke-width="{1.6 if hi else 1}"/>'
                f'<text x="{x+16}" y="{y+34}" font-family=\'{MONO}\' font-size="15" font-weight="700" fill="{c["text"]}">{title}</text>'
                f'<text x="{x+16}" y="{y+58}" font-family=\'{MONO}\' font-size="12" fill="{c["mute"]}">{sub}</text>')
    def arrow(x1, y1, x2, y2):
        return (f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{c["mute"]}" stroke-width="1.6"/>'
                f'<path d="M{x2-7} {y2-5} L{x2} {y2} L{x2-7} {y2+5}" fill="none" stroke="{c["mute"]}" stroke-width="1.6"/>')
    return f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="t d">
<title id="t">How QuantDeck works</title>
<desc id="d">Your strategy receives one bar at a time from the engine. The engine reads bars from a data feed. Orders go to a simulated paper broker that fills them at the next bar's open. Fills feed the metrics and SQLite storage.</desc>
<defs>
<pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="{c["grid"]}"/></pattern>
<clipPath id="k"><rect width="{W}" height="{H}" rx="14"/></clipPath>
</defs>
<style>@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}</style>
<g clip-path="url(#k)">
<rect width="{W}" height="{H}" fill="{c["win"]}"/>
<rect y="40" width="{W}" height="{H-40}" fill="{c["bg"]}"/><rect y="40" width="{W}" height="{H-40}" fill="url(#g)"/>
{chrome(c, W, "how-it-works")}
<text x="40" y="84" font-family=\'{MONO}\' font-size="13" letter-spacing="2.4" fill="{c["a"]}">ONE BAR AT A TIME</text>
{box(40, 120, 230, 90, "Strategy", "your code: on_bar(bar)", True)}
{box(335, 120, 230, 90, "BacktestEngine", "the loop, bar by bar")}
{box(630, 120, 230, 90, "PaperBroker", "fills, slippage, fees")}
{box(925, 120, 235, 90, "Metrics + SQLite", "return, Sharpe, drawdown")}
{arrow(270, 165, 331, 165)}{arrow(565, 165, 626, 165)}{arrow(860, 165, 921, 165)}
{box(335, 262, 230, 80, "DataFeed", "yfinance or CSV")}
{arrow(450, 262, 450, 214)}
<text x="40" y="250" font-family=\'{MONO}\' font-size="12" fill="{c["mute"]}">buy() / sell() go back</text>
<text x="40" y="268" font-family=\'{MONO}\' font-size="12" fill="{c["mute"]}">to the engine as orders</text>
<text x="630" y="250" font-family=\'{MONO}\' font-size="12" fill="{c["b"]}">Orders fill at the NEXT bar's open,</text>
<text x="630" y="268" font-family=\'{MONO}\' font-size="12" fill="{c["b"]}">so a strategy never trades on the future.</text>
<circle cx="52" cy="165" r="5" fill="{c["b"]}"><animate attributeName="cx" values="52;1140" dur="6s" repeatCount="indefinite"/></circle>
</g>
<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="14" fill="none" stroke="{c["line"]}"/>
</svg>
'''


def og(r):
    c = DARK
    m = r["metrics"]
    pts = curve_points(r["equity_curve"], 80, 330, 1120, 200)
    d = path_d(pts)
    return f'''<svg width="1280" height="630" viewBox="0 0 1280 630" xmlns="http://www.w3.org/2000/svg">
<defs><pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="{c["grid"]}"/></pattern>
<linearGradient id="s" x1="0" x2="1"><stop offset="0" stop-color="{c["a"]}"/><stop offset="1" stop-color="{c["b"]}"/></linearGradient></defs>
<rect width="1280" height="630" fill="{c["bg"]}"/><rect width="1280" height="630" fill="url(#g)"/>
{chrome(c, 1280, "quantdeck backtest strategy.py --symbol AAPL")}
<text x="80" y="130" font-family=\'{MONO}\' font-size="18" letter-spacing="3" fill="{c["a"]}">EVENT-DRIVEN BACKTESTING</text>
<text x="80" y="210" font-family=\'{SERIF}\' font-size="84" font-weight="700" fill="{c["text"]}">QuantDeck</text>
<text x="80" y="262" font-family=\'{MONO}\' font-size="24" fill="{c["mute"]}">Run the real Python engine in your browser.</text>
<path d="{d} L{pts[-1][0]:.1f} 560 L80 560 Z" fill="{c["a"]}" opacity=".10"/>
<path d="{d}" fill="none" stroke="url(#s)" stroke-width="4" stroke-linejoin="round"/>
<text x="80" y="596" font-family=\'{MONO}\' font-size="16" fill="{c["mute"]}">heykav.github.io/quantdeck   |   AAPL SMA 10/30, 2015-2024: {m["total_return_pct"]:.2f}% total return (simulation, not advice)</text>
</svg>
'''


def main():
    r = run()
    out = ROOT / "docs" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    (out / "hero.svg").write_text(hero(DARK, r))
    (out / "hero-light.svg").write_text(hero(LIGHT, r))
    (out / "how-it-works.svg").write_text(diagram(DARK))
    (out / "how-it-works-light.svg").write_text(diagram(LIGHT))
    og_svg = out / "og-source.svg"
    og_svg.write_text(og(r))
    subprocess.run(["rsvg-convert", "-w", "1280", "-o", str(ROOT / "docs" / "og-image.png"), str(og_svg)], check=True)
    og_svg.unlink()


if __name__ == "__main__":
    main()
