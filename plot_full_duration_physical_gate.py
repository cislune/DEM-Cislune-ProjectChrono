#!/usr/bin/env python3
"""Plot full-duration repeatability and RIDER physical-gate evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PASS_COLOR = "#2F6B5F"
FAIL_COLOR = "#A84A45"
WITHHELD_COLOR = "#D18B2C"


def gate_color(status: str) -> str:
    if status.startswith("PASS") or status.startswith("WITHIN"):
        return PASS_COLOR
    if status.startswith("REJECT") or status.startswith("EXCEEDS"):
        return FAIL_COLOR
    return WITHHELD_COLOR


def plot(summary: dict, gate: dict, output_path: Path) -> None:
    import matplotlib.pyplot as plt

    completed = [row for row in summary["repeats"] if row.get("completed")]
    torques = [float(row["torque_nm"]) for row in completed]
    repeat_labels = [f"R{row['repeat']}" for row in completed]
    reference = float(gate["rider_steady_tare_corrected_upper_bound_nm"])
    tolerance = float(gate["upper_bound_tolerance_fraction"])
    torque_cv = float(summary["torque_nm"]["coefficient_of_variation"])
    strain_range = float(summary["column_strain_proxy"]["range"])

    figure, axes = plt.subplots(1, 3, figsize=(15.5, 5.5))
    figure.patch.set_facecolor("#F5F7F8")
    for axis in axes[:2]:
        axis.set_facecolor("white")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#D9DEE2", linewidth=0.8, alpha=0.7)

    torque_color = gate_color(gate["status"])
    axes[0].scatter(
        repeat_labels,
        torques,
        color=torque_color,
        edgecolor="white",
        linewidth=0.8,
        s=90,
        zorder=3,
    )
    axes[0].axhline(
        reference,
        color="#25323A",
        linewidth=1.2,
        label=f"RIDER upper bound: {reference:.3f} N m",
    )
    axes[0].axhline(
        reference * (1 + tolerance),
        color="#7C8790",
        linewidth=1.0,
        linestyle="--",
        label=f"Rejection threshold: +{tolerance:.0%}",
    )
    axes[0].set_title("Full-duration torque", loc="left", fontweight="bold")
    axes[0].set_ylabel("Predicted wheel torque (N m)")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")

    normalized = [torque_cv / 0.15, strain_range / 0.03]
    metric_labels = ["Torque CV", "Strain range"]
    metric_colors = [
        PASS_COLOR if value <= 1 else FAIL_COLOR for value in normalized
    ]
    bars = axes[1].bar(metric_labels, normalized, color=metric_colors, width=0.58)
    axes[1].axhline(1, color="#25323A", linewidth=1.1, linestyle="--")
    axes[1].set_title("Numerical repeatability", loc="left", fontweight="bold")
    axes[1].set_ylabel("Observed / gate limit")
    for bar, value in zip(bars, normalized):
        axes[1].text(
            bar.get_x() + bar.get_width() / 2,
            value + max(normalized + [1]) * 0.03,
            f"{value:.2f}x",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    axes[2].axis("off")
    axes[2].set_title("Validation state", loc="left", fontweight="bold")
    status_rows = [
        ("Numerical repeatability", gate["numerical_repeatability_status"]),
        ("RIDER torque plausibility", gate["physical_plausibility_status"]),
        ("Measured compaction", gate["compaction_validation_status"]),
    ]
    for index, (label, status) in enumerate(status_rows):
        y = 0.78 - index * 0.25
        axes[2].text(0.02, y, label, fontsize=10, fontweight="bold")
        axes[2].text(
            0.02,
            y - 0.08,
            status.replace("_", " "),
            fontsize=9,
            color=gate_color(status),
            wrap=True,
        )

    figure.suptitle(
        "GRASP DEM full-duration Alabama validation gate",
        x=0.055,
        y=0.98,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.055,
        0.91,
        "Selected CD1 solver profile; same imported lap-2 bed and UCF Alabama wheel condition",
        fontsize=10,
        color="#44515A",
    )
    figure.text(
        0.055,
        0.025,
        "RIDER torque retains rig losses and is an upper bound. Absolute compaction remains withheld "
        "until paired pre/post bed measurements are available.",
        fontsize=9,
        color="#44515A",
    )
    figure.tight_layout(rect=(0.035, 0.095, 0.99, 0.88))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repeat_summary", type=Path)
    parser.add_argument("physical_gate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(
        json.loads(args.repeat_summary.read_text()),
        json.loads(args.physical_gate.read_text()),
        args.output,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
