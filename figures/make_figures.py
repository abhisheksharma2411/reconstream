"""Regenerate every figure from the JSON in results/.

No number is typed in here.  If a figure and the text disagree, the figure is
right and the text is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HERE = Path(__file__).resolve().parent

LABEL = {
    "typed_horizon": "typed horizon (ours)",
    "fixed_timeout": "fixed timeout",
    "global_watermark": "merged watermark",
    "idle_watermark": "merged watermark + idleness",
    "amount_date": "amount/date matching",
}
STYLE = {
    "typed_horizon": dict(color="#1b4965", marker="o", lw=2.0, zorder=5),
    "fixed_timeout": dict(color="#c1666b", marker="s", lw=1.4),
    "global_watermark": dict(color="#5f8a68", marker="^", lw=1.4),
    "idle_watermark": dict(color="#d4a253", marker="v", lw=1.4),
    "amount_date": dict(color="#8a6a9c", marker="D", lw=1.4),
}

plt.rcParams.update({
    "font.size": 8.5, "axes.grid": True, "grid.alpha": 0.25,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "savefig.bbox": "tight",
})


def load(name):
    path = RESULTS / name
    if not path.exists():
        print(f"  skip: {name} not found")
        return None
    return json.loads(path.read_text())


def fig_frontier() -> None:
    d = load("e2_frontier.json")
    if not d:
        return
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9))
    for ax, regime in zip(axes, ("calm", "faulty")):
        curves = d["regimes"][regime]["curves"]
        for name, pts in curves.items():
            xs = [100 * p["false_break_rate"] for p in pts]
            ys = [p["mean_closure"] for p in pts]
            ax.plot(xs, ys, label=LABEL[name], ms=3, **STYLE[name])
        ax.set_xlabel("false breaks (% of obligations)")
        ax.set_title(f"{regime} traffic", fontsize=9)
        ax.set_xlim(left=-0.4)
    axes[0].set_ylabel("mean closure delay (ticks)")
    axes[1].legend(frameon=False, fontsize=7, loc="upper right")
    fig.suptitle("Soundness against timeliness: lower and further left is better",
                 fontsize=9, y=1.02)
    fig.savefig(HERE / "fig1_frontier.pdf")
    plt.close(fig)
    print("  fig1_frontier.pdf")


def fig_shift() -> None:
    d = load("e3_shift.json")
    if not d:
        return
    sweep = d["sweep"]
    xs = [100 * r["model_violation_rate"] for r in sweep]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.9), sharex=True)
    for name in sweep[0]["arms"]:
        ax1.plot(xs, [100 * r["arms"][name]["false_break_fpr"]["point"] for r in sweep],
                 label=LABEL[name], ms=3, **STYLE[name])
        ax2.plot(xs, [100 * r["arms"][name]["inadmissible_rate"]["point"] for r in sweep],
                 label=LABEL[name], ms=3, **STYLE[name])
    ax1.set_ylabel("false breaks (% of settled credits)")
    ax1.set_title("accuracy collapses", fontsize=9)
    ax2.set_ylabel("contract violations (%)")
    ax2.set_title("entitlement to decide does not", fontsize=9)
    ax2.set_ylim(0, max(2.0, ax1.get_ylim()[1]))
    for ax in (ax1, ax2):
        ax.set_xlabel("arrivals breaking the declared lateness bound (%)")
    ax1.legend(frameon=False, fontsize=7, loc="upper left")
    fig.suptitle("Under distribution shift the error is the input's, not the reconciler's",
                 fontsize=9, y=1.03)
    fig.savefig(HERE / "fig2_shift.pdf")
    plt.close(fig)
    print("  fig2_shift.pdf")


def fig_idleness() -> None:
    d = load("e4_idleness.json")
    if not d:
        return
    sweep = d["sweep"]
    period = d["config"]["bank_batch_period"]
    xs = [r["idle_timeout"] for r in sweep]
    fig, ax = plt.subplots(figsize=(3.6, 2.8))
    for regime, colour, marker in (("calm", "#1b4965", "o"), ("faulty", "#c1666b", "s")):
        ys = [100 * r["regimes"][regime]["inadmissible_rate"]["point"] for r in sweep]
        lo = [100 * r["regimes"][regime]["inadmissible_rate"]["lo"] for r in sweep]
        hi = [100 * r["regimes"][regime]["inadmissible_rate"]["hi"] for r in sweep]
        ax.plot(xs, ys, color=colour, marker=marker, ms=3.2, lw=1.6, label=f"{regime} traffic")
        ax.fill_between(xs, lo, hi, color=colour, alpha=0.15, lw=0)
    ax.axvline(period, color="#444", ls="--", lw=1.0)
    ax.annotate("bank posting period", xy=(period, ax.get_ylim()[1] * 0.72),
                xytext=(period * 1.25, ax.get_ylim()[1] * 0.82), fontsize=7,
                arrowprops=dict(arrowstyle="->", lw=0.8, color="#444"))
    ax.set_xscale("log")
    ax.set_xlabel("idleness timeout (ticks)")
    ax.set_ylabel("contract violations (%)")
    ax.set_title("The documented fix for a stalled join", fontsize=9)
    ax.legend(frameon=False, fontsize=7)
    fig.savefig(HERE / "fig3_idleness.pdf")
    plt.close(fig)
    print("  fig3_idleness.pdf")


def fig_tail() -> None:
    """Closure-delay tails at the zero-false-break operating point."""
    d = load("e2_frontier.json")
    if not d:
        return
    fig, ax = plt.subplots(figsize=(3.6, 2.8))
    zf = d["regimes"]["faulty"]["at_zero_false_breaks"]
    names = [n for n in ("typed_horizon", "idle_watermark", "fixed_timeout", "global_watermark")
             if zf.get(n)]
    ys = range(len(names))
    for y, name in zip(ys, names):
        pt = zf[name]
        ax.barh(y, pt["p99_closure"], height=0.34, color=STYLE[name]["color"], alpha=0.32,
                label="p99" if y == 0 else None)
        ax.barh(y, pt["mean_closure"], height=0.34, color=STYLE[name]["color"],
                label="mean" if y == 0 else None)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([LABEL[n] for n in names], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("closure delay (ticks)")
    ax.set_title("Break latency at zero false breaks", fontsize=9)
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    fig.savefig(HERE / "fig4_tail.pdf")
    plt.close(fig)
    print("  fig4_tail.pdf")


def main() -> None:
    print("regenerating figures from results/")
    fig_frontier()
    fig_shift()
    fig_idleness()
    fig_tail()


if __name__ == "__main__":
    main()
