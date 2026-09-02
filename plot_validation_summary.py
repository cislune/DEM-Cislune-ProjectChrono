#!/usr/bin/env python3
"""Render the compact GRASP wheel DEM calibration and validation summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "ink": "#202124",
    "gray": "#7A7F87",
    "green": "#16866B",
    "teal": "#1F9E89",
    "gold": "#D39B2A",
    "red": "#C94B40",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def render(alabama_path: Path, rtgs_path: Path, candidate_path: Path, output: Path) -> None:
    alabama = load(alabama_path)
    rtgs = load(rtgs_path)
    candidates = load(candidate_path)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titleweight": "bold",
            "axes.edgecolor": "#B9BDC3",
            "axes.labelcolor": COLORS["ink"],
            "xtick.color": COLORS["ink"],
            "ytick.color": COLORS["ink"],
        }
    )
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.25), constrained_layout=True)

    laps = alabama["laps"]
    x = [row["lap"] for row in laps]
    observed = [row["observed_corrected_torque_upper_bound_nm"] for row in laps]
    predicted = [row["predicted_contact_torque_nm"] for row in laps]
    ax = axes[0]
    ax.plot(x, observed, "o-", color=COLORS["gray"], label="RIDER corrected upper bound")
    ax.plot(x, predicted, "o-", color=COLORS["green"], label="DEM contact torque")
    ax.axvspan(0.5, 5.5, color="#E8F3EF", alpha=0.75, zorder=0)
    ax.axvline(5.5, color="#B9BDC3", linewidth=1)
    ax.annotate(
        "Lap 10 outlier",
        xy=(10, predicted[-1]),
        xytext=(7.0, 2.65),
        arrowprops={"arrowstyle": "->", "color": COLORS["red"]},
        color=COLORS["red"],
    )
    ax.set_title("Alabama wheel: held-out torque")
    ax.set_xlabel("RIDER lap")
    ax.set_ylabel("Torque (N m)")
    ax.set_xticks(range(1, 11))
    ax.grid(axis="y", color="#E4E6E9", linewidth=0.8)
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    ax.text(1, 0.05, "calibration", transform=ax.get_xaxis_transform(), color=COLORS["green"])
    ax.text(6, 0.05, "held out", transform=ax.get_xaxis_transform(), color=COLORS["ink"])

    ax = axes[1]
    designs = ["Closed_Sharp", "Closed_SIU", "Closed_Scalloped"]
    motor = rtgs["motor_demand_ordering"]
    mobility = rtgs["mobility_ordering"]
    rank_sets = [
        ("Physical current", motor["physical_high_to_low_performance"]),
        ("DEM torque", motor["simulated_high_to_low_performance"]),
        ("Physical slip", mobility["physical_high_to_low_performance"]),
        ("DEM drawbar", mobility["simulated_high_to_low_performance"]),
    ]
    y = np.arange(len(rank_sets))
    for row_index, (label, ordering) in enumerate(rank_sets):
        ranks = {design: index + 1 for index, design in enumerate(ordering)}
        for design_index, design in enumerate(designs):
            ax.scatter(
                ranks[design],
                row_index,
                s=55,
                color=(COLORS["green"], COLORS["gold"], COLORS["red"])[design_index],
                label=design.replace("Closed_", "") if row_index == 0 else None,
                zorder=3,
            )
    ax.set_title("Historical RTGS ordering")
    ax.set_xlabel("Performance rank (1 = best)")
    ax.set_xlim(0.7, 3.3)
    ax.set_xticks([1, 2, 3])
    ax.set_yticks(y, [label for label, _ in rank_sets])
    ax.invert_yaxis()
    ax.grid(axis="x", color="#E4E6E9", linewidth=0.8)
    ax.legend(frameon=False, fontsize=8, loc="lower right")

    ax = axes[2]
    ordered = [
        next(row for row in candidates["candidates"] if row["candidate"] == name)
        for name in ("smooth_control", "broad_wave_12", "chevron_wave_14")
    ]
    names = ["Smooth", "Broad wave", "Chevron"]
    positions = np.arange(len(names))
    width = 0.24
    ax.bar(
        positions - width,
        [row["settlement_vs_smooth"] for row in ordered],
        width,
        color=COLORS["green"],
        label="Settlement",
    )
    ax.bar(
        positions,
        [row["torque_vs_smooth"] for row in ordered],
        width,
        color=COLORS["gold"],
        label="Torque",
    )
    ax.bar(
        positions + width,
        [row["drawbar_vs_smooth"] for row in ordered],
        width,
        color=COLORS["teal"],
        label="Drawbar efficiency",
    )
    ax.axhline(1.0, color="#8B9097", linewidth=1)
    ax.set_title("Frozen candidate comparison")
    ax.set_ylabel("Ratio to smooth control")
    ax.set_xticks(positions, names)
    ax.set_ylim(0, 1.6)
    ax.grid(axis="y", color="#E4E6E9", linewidth=0.8)
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    fig.suptitle(
        "GRASP DEM wheel calibration and validation | 2026-09-01",
        fontsize=14,
        fontweight="bold",
        color=COLORS["ink"],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alabama", type=Path, required=True)
    parser.add_argument("--rtgs", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.alabama, args.rtgs, args.candidates, args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
