#!/usr/bin/env python3
"""Compare exact-manifest repeatability across DEME versions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


COLORS = ["#526D82", "#A84A45", "#2F6B5F", "#D18B2C"]


def collect(summary_path: Path, label: str) -> dict:
    summary = json.loads(summary_path.read_text())
    completed = [row for row in summary["repeats"] if row.get("completed")]
    return {
        "label": label,
        "status": summary["status"],
        "completed_repeats": summary["completed_repeats"],
        "torques": [float(row["torque_nm"]) for row in completed],
        "strains": [float(row["column_strain_proxy"]) for row in completed],
        "torque_cv": float(summary["torque_nm"]["coefficient_of_variation"]),
        "strain_range": float(summary["column_strain_proxy"]["range"]),
    }


def plot(
    series: list[dict],
    output_path: Path,
    torque_cv_gate: float = 0.15,
    strain_range_gate: float = 0.03,
) -> None:
    import matplotlib.pyplot as plt

    labels = [row["label"] for row in series]
    colors = [COLORS[index % len(COLORS)] for index in range(len(series))]
    x_values = list(range(len(series)))

    figure, axes = plt.subplots(1, 3, figsize=(15.5, 5.5))
    figure.patch.set_facecolor("#F5F7F8")
    for axis in axes:
        axis.set_facecolor("white")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#D9DEE2", linewidth=0.8, alpha=0.7)
        axis.set_xticks(x_values, labels)

    for index, row in enumerate(series):
        offsets = [
            (position - (len(row["torques"]) - 1) / 2) * 0.09
            for position in range(len(row["torques"]))
        ]
        axes[0].scatter(
            [index + offset for offset in offsets],
            row["torques"],
            color=colors[index],
            edgecolor="white",
            linewidth=0.8,
            s=75,
            zorder=3,
        )
        mean_torque = sum(row["torques"]) / len(row["torques"])
        axes[0].hlines(
            mean_torque,
            index - 0.22,
            index + 0.22,
            color="#25323A",
            linewidth=2,
        )
    axes[0].set_title("Exact-repeat torque", loc="left", fontweight="bold")
    axes[0].set_ylabel("Predicted wheel torque (N m)")

    torque_cv = [100 * row["torque_cv"] for row in series]
    bars = axes[1].bar(x_values, torque_cv, color=colors, width=0.58)
    axes[1].set_title("Torque repeatability", loc="left", fontweight="bold")
    axes[1].set_ylabel("Coefficient of variation (%)")
    axes[1].axhline(
        100 * torque_cv_gate,
        color="#25323A",
        linewidth=1.1,
        linestyle="--",
        label=f"Gate: {torque_cv_gate:.0%}",
    )
    axes[1].legend(frameon=False, loc="upper left")
    for bar, value in zip(bars, torque_cv):
        axes[1].text(
            bar.get_x() + bar.get_width() / 2,
            value + max(torque_cv + [15]) * 0.025,
            f"{value:.1f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    strain_range = [row["strain_range"] for row in series]
    bars = axes[2].bar(x_values, strain_range, color=colors, width=0.58)
    axes[2].set_title("Compaction-proxy repeatability", loc="left", fontweight="bold")
    axes[2].set_ylabel("Column-strain range")
    axes[2].axhline(
        strain_range_gate,
        color="#25323A",
        linewidth=1.1,
        linestyle="--",
        label=f"Gate: {strain_range_gate:.2f}",
    )
    axes[2].legend(frameon=False, loc="upper left")
    for bar, value in zip(bars, strain_range):
        axes[2].text(
            bar.get_x() + bar.get_width() / 2,
            value + strain_range_gate * 0.025,
            f"{value:.4f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    figure.suptitle(
        "GRASP DEM: upstream fix restores execution, not repeatability",
        x=0.055,
        y=0.98,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.055,
        0.91,
        "Same Alabama wheel, imported lap-2 particle state, manifest, and three-repeat requirement",
        fontsize=10,
        color="#44515A",
    )
    figure.text(
        0.055,
        0.025,
        "Both versions fail the <=15% torque-CV gate. The patched solver completed 3/3 launches, "
        "but wheel ranking and physical claims remain withheld.",
        fontsize=9,
        color="#44515A",
    )
    figure.tight_layout(rect=(0.035, 0.095, 0.99, 0.88))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary_json", nargs="+", type=Path)
    parser.add_argument("--labels", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--torque-cv-gate", type=float, default=0.15)
    parser.add_argument("--strain-range-gate", type=float, default=0.03)
    args = parser.parse_args()
    if len(args.summary_json) != len(args.labels):
        parser.error("--labels must contain one label per summary JSON")
    series = [
        collect(path, label)
        for path, label in zip(args.summary_json, args.labels)
    ]
    plot(
        series,
        args.output,
        torque_cv_gate=args.torque_cv_gate,
        strain_range_gate=args.strain_range_gate,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
