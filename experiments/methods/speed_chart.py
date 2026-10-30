"""PROTOTYPE ONLY - Q3 quality-against-p95 chart (round 2). Aggregates only; no per-query data.

Input: a JSON object {arm: {"ndcg10": float | null, "p95_s": float, "note": str (optional)}}; keys starting with
"_" are ignored, and arms whose ndcg10 is null are listed in the table but not plotted. The evaluator fills ndcg10;
experiments/results/r2-q3-speed-p95.json is the template with the measured p95 values.
Output: one self-contained HTML file with an inline SVG scatter (x = p95 latency in seconds, log scale; y = dev
nDCG@10), a dashed line at the 0.5 s p95 target from docs/05-processor.md, direct labels, hover titles, and a
table view. No external libraries, no network.

usage: python experiments/methods/speed_chart.py quality.json [--out experiments/results/r2-q3-speed-chart.html]
"""
import argparse
import html
import json
import math
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGET_S = 0.5
W, H = 760, 440
ML, MR, MT, MB = 64, 150, 24, 56  # right margin leaves room for direct labels

CSS = """
:root { color-scheme: light; --surface-1:#fcfcfb; --text-primary:#0b0b0b; --text-secondary:#52514e;
  --text-muted:#75746f; --grid:#e6e5e0; --axis:#b9b8b1; --series-1:#2a78d6; --target:#e34948; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; --surface-1:#1a1a19;
  --text-primary:#f0efec; --text-secondary:#c3c2b7; --text-muted:#9a998f; --grid:#2e2e2c; --axis:#55544f;
  --series-1:#3987e5; --target:#e66767; } }
:root[data-theme="dark"] { color-scheme: dark; --surface-1:#1a1a19; --text-primary:#f0efec;
  --text-secondary:#c3c2b7; --text-muted:#9a998f; --grid:#2e2e2c; --axis:#55544f; --series-1:#3987e5;
  --target:#e66767; }
body { margin:0; background:var(--surface-1); color:var(--text-primary);
  font:14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:800px; margin:0 auto; padding:24px 16px 40px; }
h1 { font-size:20px; margin:0 0 4px; } p.sub { margin:0 0 16px; color:var(--text-secondary); }
.chart { width:100%; overflow-x:auto; } svg { display:block; width:100%; height:auto; min-width:520px; }
.grid line { stroke:var(--grid); stroke-width:1; } .axis line { stroke:var(--axis); }
.tick { fill:var(--text-muted); font-size:12px; } .axlab { fill:var(--text-secondary); font-size:12px; }
.dot { fill:var(--series-1); stroke:var(--surface-1); stroke-width:2; }
.hit { fill:transparent; } .hit:hover + .dot, .dot:hover { stroke:var(--text-primary); }
.lab { fill:var(--text-primary); font-size:12px; } .tgt { stroke:var(--target); stroke-width:2; stroke-dasharray:6 4; }
.tgtlab { fill:var(--text-secondary); font-size:12px; }
table { border-collapse:collapse; width:100%; margin-top:20px; font-variant-numeric:tabular-nums; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); }
th { color:var(--text-secondary); font-weight:600; } td.n { text-align:right; }
"""


def load(path):
    raw = json.load(open(path))
    return [(k, v) for k, v in raw.items() if not k.startswith("_")]


def nice(x, down):
    """Nearest 1-2-5 step below (down) or above x."""
    steps = [t * 10 ** e for e in range(-3, 4) for t in (1, 2, 5)]
    return max(v for v in steps if v <= x) if down else min(v for v in steps if v >= x)


def render(arms, title):
    pts = [(k, v) for k, v in arms if v.get("ndcg10") is not None and v.get("p95_s")]
    xs = [v["p95_s"] for _, v in pts] + [TARGET_S]
    ys = [v["ndcg10"] for _, v in pts] or [0.5]
    x0, x1 = nice(min(xs) * 0.8, down=True), nice(max(xs) * 1.25, down=False)
    y0 = max(0.0, math.floor((min(ys) - 0.03) * 20) / 20)
    y1 = min(1.0, math.ceil((max(ys) + 0.03) * 20) / 20)
    pw, ph = W - ML - MR, H - MT - MB

    def sx(x):
        return ML + (math.log10(x) - math.log10(x0)) / (math.log10(x1) - math.log10(x0)) * pw

    def sy(y):
        return MT + (1 - (y - y0) / (y1 - y0 or 1)) * ph

    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">', '<g class="grid">']
    xt = [t * 10 ** e for e in range(-3, 4) for t in (1, 2, 5) if x0 - 1e-9 <= t * 10 ** e <= x1 + 1e-9]
    for t in xt:
        s.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{MT}" y2="{MT + ph}"/>')
    n_y = int(round((y1 - y0) / 0.05))
    yt = [y0 + i * 0.05 for i in range(n_y + 1)]
    for t in yt:
        s.append(f'<line x1="{ML}" x2="{ML + pw}" y1="{sy(t):.1f}" y2="{sy(t):.1f}"/>')
    s.append("</g>")
    s.append(f'<g class="axis"><line x1="{ML}" x2="{ML + pw}" y1="{MT + ph}" y2="{MT + ph}"/></g>')
    for t in xt:
        s.append(f'<text class="tick" x="{sx(t):.1f}" y="{MT + ph + 18}" text-anchor="middle">{t:g}</text>')
    for t in yt:
        s.append(f'<text class="tick" x="{ML - 8}" y="{sy(t) + 4:.1f}" text-anchor="end">{t:.2f}</text>')
    s.append(f'<text class="axlab" x="{ML + pw / 2}" y="{H - 14}" text-anchor="middle">p95 latency per search, '
             f'seconds (log scale)</text>')
    s.append(f'<text class="axlab" transform="translate(16 {MT + ph / 2}) rotate(-90)" text-anchor="middle">'
             f'dev nDCG@10</text>')
    tx = sx(TARGET_S)
    s.append(f'<line class="tgt" x1="{tx:.1f}" x2="{tx:.1f}" y1="{MT}" y2="{MT + ph}"/>')
    s.append(f'<text class="tgtlab" x="{tx + 6:.1f}" y="{MT + 12}">0.5 s p95 target</text>')
    placed = []
    for k, v in sorted(pts, key=lambda kv: kv[1]["ndcg10"]):
        cx, cy = sx(v["p95_s"]), sy(v["ndcg10"])
        ly = cy + 4
        for py in placed:  # nudge labels that would collide
            if abs(py - ly) < 14:
                ly = py - 14
        placed.append(ly)
        tip = f'{k}: nDCG@10 {v["ndcg10"]:.3f}, p95 {v["p95_s"]:.2f} s' + (f' ({v["note"]})' if v.get("note") else "")
        s.append(f'<g><title>{html.escape(tip)}</title><circle class="hit" cx="{cx:.1f}" cy="{cy:.1f}" r="12"/>'
                 f'<circle class="dot" cx="{cx:.1f}" cy="{cy:.1f}" r="5"/></g>')
        s.append(f'<text class="lab" x="{cx + 10:.1f}" y="{ly:.1f}">{html.escape(k)}</text>')
    s.append("</svg>")
    rows = []
    for k, v in arms:
        q = "" if v.get("ndcg10") is None else f'{v["ndcg10"]:.3f}'
        rows.append(f'<tr><td>{html.escape(k)}</td><td class="n">{q}</td><td class="n">{v["p95_s"]:.2f}</td>'
                    f'<td>{html.escape(v.get("note", ""))}</td></tr>')
    rows = "".join(rows)
    table = ("<table><thead><tr><th>Arm</th><th>nDCG@10</th><th>p95 (s)</th><th>Note</th></tr></thead>"
             f"<tbody>{rows}</tbody></table>")
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            f"content=\"width=device-width, initial-scale=1\"><title>Search speed vs quality</title><style>{CSS}"
            f"</style></head><body><main><h1>{html.escape(title)}</h1><p class=\"sub\">Dev searches; p95 is the "
            "measured per-search latency including the rewrite call where there is one. Upper left is better.</p>"
            f"<div class=\"chart\">{''.join(s)}</div>{table}</main></body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("quality")
    ap.add_argument("--out", default=os.path.join(REPO, "experiments", "results", "r2-q3-speed-chart.html"))
    ap.add_argument("--title", default="Search quality against p95 latency (round 2, Q3)")
    a = ap.parse_args()
    arms = load(a.quality)
    open(a.out, "w").write(render(arms, a.title))
    print(f"wrote {a.out}: {sum(1 for _, v in arms if v.get('ndcg10') is not None)} arms plotted, {len(arms)} listed")


if __name__ == "__main__":
    main()
