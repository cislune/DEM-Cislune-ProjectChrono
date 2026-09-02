#!/usr/bin/env python3
"""Plot solver-profile completion and response metrics for GRASP DEM diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROFILE_LABELS = {
    "cub": "CUB reduction",
    "fixed-cd20": "Fixed CD = 20",
    "cub-fixed-cd20": "CUB + fixed CD",
}


def repeatability_note(summary: dict | None) -> str:
    if not summary or not summary.get("candidates"):
        return "CUB repeatability: pending"
    candidate = summary["candidates"][0]
    torque_cv = candidate["torque_nm"]["coefficient_of_variation"]
    strain_range = candidate["column_strain_proxy"]["range"]
    torque_text = "n/a" if torque_cv is None else f"{torque_cv:.1%}"
    return (
        f"CUB repeatability: {summary['status']} | torque CV {torque_text} | "
        f"column-strain range {strain_range:.4f}"
    )


def plot(
    triage: dict,
    repeatability: dict | None,
    output_path: Path,
    reference_torque_nm: float | None = None,
) -> None:
    import matplotlib.pyplot as plt

    completed = [row for row in triage["profiles"] if row["completed"]]
    if not completed:
        raise ValueError("No completed profiles are available to plot")
    repeat_rows = []
    if repeatability and repeatability.get("candidates"):
        repeat_rows = repeatability["candidates"][0].get("replicates", [])
    labels = [
        PROFILE_LABELS.get(row["execution_profile"], row["execution_profile"])
        for row in completed
    ]
    colors = ["#2F6B5F", "#D18B2C", "#5276A7"][: len(completed)]

    panel_count = 3 if repeat_rows else 2
    figure, axes = plt.subplots(
        1,
        panel_count,
        figsize=(15.2 if repeat_rows else 11.5, 5.4),
    )
    figure.patch.set_facecolor("#F5F7F8")
    for axis in axes:
        axis.set_facecolor("white")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#D9DEE2", linewidth=0.8, alpha=0.7)

    wall_times = [row["wall_duration_s"] for row in completed]
    bars = axes[0].bar(labels, wall_times, color=colors, width=0.62)
    axes[0].set_title("Completion time", loc="left", fontweight="bold")
    axes[0].set_ylabel("Wall time (s)")
    axes[0].tick_params(axis="x", rotation=18)
    for bar, value in zip(bars, wall_times):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            value + max(wall_times) * 0.025,
            f"{value:.0f} s",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    for row, label, color in zip(completed, labels, colors):
        axes[1].scatter(
            row["column_strain_proxy"],
            row["torque_median_abs_nm"],
            s=90,
            color=color,
            edgecolor="white",
            linewidth=1.0,
            zorder=3,
        )
        axes[1].annotate(
            label,
            (row["column_strain_proxy"], row["torque_median_abs_nm"]),
            xytext=(7, 6),
            textcoords="offset points",
            fontsize=9,
        )
    axes[1].set_title("Same input, different numerical response", loc="left", fontweight="bold")
    axes[1].set_xlabel("Column-strain proxy")
    axes[1].set_ylabel("Median absolute wheel torque (N m)")
    if reference_torque_nm is not None:
        axes[1].axhline(
            reference_torque_nm,
            color="#8B3E3E",
            linestyle="--",
            linewidth=1.3,
            label=f"RIDER lap 3, tare-corrected: {reference_torque_nm:.3f} N m",
        )
        axes[1].legend(frameon=False, loc="best")

    if repeat_rows:
        repeat_rows = sorted(repeat_rows, key=lambda row: row["replicate"])
        repeat_labels = [f"R{row['replicate']}" for row in repeat_rows]
        repeat_torque = [row["torque_nm"] for row in repeat_rows]
        axes[2].plot(
            repeat_labels,
            repeat_torque,
            color="#2F6B5F",
            marker="o",
            markersize=8,
            linewidth=1.6,
        )
        axes[2].set_title("Exact CUB repeats", loc="left", fontweight="bold")
        axes[2].set_ylabel("Median absolute wheel torque (N m)")
        for label, value in zip(repeat_labels, repeat_torque):
            axes[2].annotate(
                f"{value:.3f}",
                (label, value),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )
        if reference_torque_nm is not None:
            axes[2].axhline(
                reference_torque_nm,
                color="#8B3E3E",
                linestyle="--",
                linewidth=1.3,
                label="RIDER lap 3",
            )
            axes[2].legend(frameon=False, loc="best")

    figure.suptitle(
        "GRASP DEM solver stability diagnostic",
        x=0.06,
        y=0.98,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.06,
        0.91,
        "Exact Alabama RIDER lap-3 input and byte-identical lap-2 settled state",
        fontsize=10,
        color="#44515A",
    )
    figure.text(
        0.06,
        0.025,
        repeatability_note(repeatability)
        + "\nExecution stability only; physical accuracy and bed-to-bed robustness remain separate gates.",
        fontsize=9,
        color="#44515A",
    )
    figure.tight_layout(rect=(0.04, 0.11, 0.98, 0.88))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("triage_summary", type=Path)
    parser.add_argument("--repeatability-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-torque-nm", type=float)
    args = parser.parse_args()
    triage = json.loads(args.triage_summary.read_text())
    repeatability = (
        json.loads(args.repeatability_summary.read_text())
        if args.repeatability_summary
        else None
    )
    plot(
        triage,
        repeatability,
        args.output,
        reference_torque_nm=args.reference_torque_nm,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
