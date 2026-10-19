"""Publication-quality (matplotlib) renderings of the same four charts the
frontend draws interactively with Plotly. These exist only for the
"download figure" buttons: 300 DPI PNG and true vector PDF, suitable for
direct inclusion in a paper, which a screenshot of the interactive chart
would not be. The underlying numbers are identical -- both the frontend's
Plotly charts and these figures are built from the same analysis payload
returned by :func:`app.analysis.run_analysis`.
"""
from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

__all__ = ["render_figure"]

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["font.size"] = 11
_ACCENT = "#1b5e4f"


def _to_bytes(fig, fmt: str) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _radar_grid(radar: dict) -> plt.Figure:
    panels = radar["panels"]
    axes_labels = radar["axes"]
    n = len(panels)
    cols = min(4, max(1, math.ceil(math.sqrt(n))))
    rows = math.ceil(n / cols)
    angles = np.linspace(0, 2 * np.pi, len(axes_labels), endpoint=False).tolist()
    angles += angles[:1]

    fig, axs = plt.subplots(rows, cols, figsize=(3.1 * cols, 3.1 * rows), subplot_kw={"projection": "polar"})
    axs = np.atleast_2d(axs).reshape(rows, cols)
    for i, panel in enumerate(panels):
        ax = axs[i // cols][i % cols]
        values = panel["values"] + panel["values"][:1]
        ax.plot(angles, values, color=_ACCENT, linewidth=1.5)
        ax.fill(angles, values, color=_ACCENT, alpha=0.25)
        ax.set_ylim(0, 1)
        ax.set_yticklabels([])
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(axes_labels, fontsize=8)
        ax.set_title(panel["architecture"], fontsize=10, pad=14)
    for j in range(n, rows * cols):
        axs[j // cols][j % cols].axis("off")

    fig.suptitle("DERMS-R component profile per architecture (at each architecture's optimal ratio)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def _per_architecture(rows: list[dict]) -> plt.Figure:
    architectures = sorted({r["architecture"] for r in rows})
    ratios = sorted({r["dataset_ratio"] for r in rows})
    x = np.arange(len(architectures))
    width = 0.8 / max(1, len(ratios))

    fig, ax = plt.subplots(figsize=(max(7, 0.9 * len(architectures)), 5), constrained_layout=True)
    cmap = plt.get_cmap("viridis", len(ratios))
    for i, ratio in enumerate(ratios):
        values = []
        for arch in architectures:
            match = next((r for r in rows if r["architecture"] == arch and r["dataset_ratio"] == ratio), None)
            values.append(match["derms_r_raw"] if match else np.nan)
        ax.bar(x + i * width, values, width, label=f"r = {ratio:g}", color=cmap(i))

    ax.set_xticks(x + width * (len(ratios) - 1) / 2)
    ax.set_xticklabels(architectures, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("DERMS-R (raw)")
    ax.set_title("DERMS-R per architecture, across all evaluated ratios")
    ax.legend(fontsize=8, ncols=min(len(ratios), 5), loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)
    return fig


def _optimal(optimal: list[dict]) -> plt.Figure:
    params = np.array([o["n_parameters"] for o in optimal], dtype=float)
    acc = np.array([o["mean_val_accuracy"] for o in optimal]) * 100
    scores = np.array([o["derms_r_raw"] for o in optimal])
    names = [o["architecture"] for o in optimal]

    norm = Normalize(vmin=scores.min(), vmax=scores.max())
    cmap = plt.get_cmap("viridis")
    sizes = 60 + (scores - scores.min()) / max(1e-9, (scores.max() - scores.min())) * 600

    fig, ax = plt.subplots(figsize=(8, 5.5), constrained_layout=True)
    sc = ax.scatter(params, acc, s=sizes, c=scores, cmap=cmap, norm=norm, alpha=0.88, edgecolor="white", linewidth=1.1)
    for p, a, name in zip(params, acc, names):
        ax.annotate(name, (p, a), textcoords="offset points", xytext=(0, 9), fontsize=7.5, color="dimgray", ha="center")
    ax.set_xscale("log")
    ax.set_xlabel("Trainable parameters (log scale)")
    ax.set_ylabel("Mean validation accuracy (%)")
    ax.set_title("DERMS-R at each architecture's optimal ratio")
    ax.grid(True, which="both", alpha=0.25)
    cbar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax)
    cbar.set_label("DERMS-R (raw)")
    return fig


def _rank_bar(statistics: dict) -> plt.Figure:
    ranked = sorted(statistics["average_ranks"], key=lambda r: r["average_rank"])
    names = [r["architecture"] for r in ranked]
    ranks = [r["average_rank"] for r in ranked]

    fig, ax = plt.subplots(figsize=(max(6, 0.7 * len(names)), 4.5), constrained_layout=True)
    ax.bar(names, ranks, color=_ACCENT)
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Average rank (lower = better)")
    ax.set_title("Average DERMS-R rank per architecture")
    ax.grid(True, axis="y", alpha=0.3)
    return fig


def _cd_diagram(statistics: dict) -> plt.Figure:
    ranked = sorted(statistics["average_ranks"], key=lambda r: r["average_rank"])
    ranks = [r["average_rank"] for r in ranked]
    names = [r["architecture"] for r in ranked]
    cd = statistics["critical_difference"]
    k = statistics["k"]

    groups, i = [], 0
    while i < len(ranks):
        j = i
        while j + 1 < len(ranks) and ranks[j + 1] - ranks[i] <= cd:
            j += 1
        if j > i:
            groups.append((ranks[i], ranks[j]))
        i += 1

    # Vertical layout, top to bottom: upper label rows -> axis -> tick
    # numbers -> group bars (one row per group) -> x-axis caption. Each
    # piece's extent is computed before any fixed y-limit is picked, so
    # the caption never collides with however many group bars this
    # particular dataset happens to produce.
    y0 = 1.0
    n_label_rows = math.ceil(len(names) / 2)
    top = y0 + 0.95 + 0.14 * n_label_rows
    group_row_h = 0.1
    groups_bottom = y0 - 0.16 - 0.12 - len(groups) * group_row_h
    caption_y = groups_bottom - 0.15
    bottom = caption_y - 0.15

    fig, ax = plt.subplots(figsize=(max(8, 0.7 * k), max(3.2, 1.3 * (top - bottom))))
    ax.set_xlim(0.5, k + 0.5)
    ax.set_ylim(bottom, top)
    ax.axis("off")

    ax.plot([1, k], [y0, y0], color="black", lw=1.2)
    for t in range(1, k + 1):
        ax.plot([t, t], [y0 - 0.04, y0 + 0.04], color="black", lw=1.0)
        ax.text(t, y0 - 0.16, str(t), ha="center", fontsize=8.5, va="top")
    ax.text((k + 1) / 2, caption_y, "Average DERMS-R rank (1 = best)", ha="center", va="top", fontsize=9.5)

    cd_x0 = 1.0
    cd_y = y0 + 0.55
    ax.plot([cd_x0, cd_x0 + cd], [cd_y, cd_y], color="black", lw=1.6)
    ax.plot([cd_x0, cd_x0], [cd_y - 0.05, cd_y + 0.05], color="black", lw=1.2)
    ax.plot([cd_x0 + cd, cd_x0 + cd], [cd_y - 0.05, cd_y + 0.05], color="black", lw=1.2)
    ax.text(cd_x0 + cd / 2, cd_y + 0.1, f"CD = {cd:.2f}", ha="center", fontsize=9)

    for gi, (lo, hi) in enumerate(groups):
        bar_y = y0 - 0.16 - 0.12 - gi * group_row_h
        ax.plot([lo, hi], [bar_y, bar_y], color="black", lw=2.2)

    for i, (name, r) in enumerate(zip(names, ranks)):
        side = 1 if i % 2 == 0 else -1
        label_y = y0 + side * (0.95 + 0.14 * (i // 2))
        ax.plot([r, r], [y0, label_y], color="gray", lw=0.6)
        ax.text(r, label_y, f"{name} ({r:.1f})", ha="center",
                va="bottom" if side > 0 else "top", fontsize=8)

    ax.set_title(f"Nemenyi critical-difference diagram ($q_{{0.05}}$, k={k})", fontsize=11, pad=4)
    fig.tight_layout()
    return fig


_BUILDERS = {
    "radar": lambda payload: _radar_grid(payload["radar"]),
    "per_architecture": lambda payload: _per_architecture(payload["rows"]),
    "optimal": lambda payload: _optimal(payload["optimal"]),
    "ranks": lambda payload: _rank_bar(payload["statistics"]),
    "cd": lambda payload: _cd_diagram(payload["statistics"]),
}


def render_figure(name: str, payload: dict, fmt: str) -> bytes:
    if name not in _BUILDERS:
        raise ValueError(f"Unknown figure '{name}'; expected one of {sorted(_BUILDERS)}.")
    if fmt not in ("png", "pdf"):
        raise ValueError(f"Unknown format '{fmt}'; expected 'png' or 'pdf'.")
    if name in ("ranks", "cd") and not payload["statistics"].get("available"):
        raise ValueError(f"Statistics are not available for this dataset: {payload['statistics'].get('reason')}")
    fig = _BUILDERS[name](payload)
    return _to_bytes(fig, fmt)
