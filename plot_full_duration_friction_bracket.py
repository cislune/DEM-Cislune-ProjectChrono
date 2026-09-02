#!/usr/bin/env python3
"""Plot full-duration wheel-friction calibration brackets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PASS_COLOR = "#2F6B5F"
FAIL_COLOR = "#A84A45"
POINT_COLOR = "#2F5D7C"


def load_case(summary_path: Path, gate_path: Path) -> dict:
    summary = json.loads(summary_path.read_text())
    gate = json.loads(gate_path.read_text())
    completed = [row for row in summary["repeats"] if row.get("completed")]
    return {
        "wheel_friction": float(gate["wheel_friction"]),
        "torques": [float(row["torque_nm"]) for row in completed],
        "torque_median": float(summary["torque_nm"]["median"]),
        "torque_cv": float(summary["torque_nm"]["coefficient_of_variation"]),
        "strain_range": float(summary["column_strain_proxy"]["range"]),
        "status": gate["status"],
        "steady_bound": float(gate["rider_steady_tare_corrected_upper_bound_nm"]),
        "active_bound": float(gate["rider_active_tare_corrected_upper_bound_nm"]),
        "tolerance": float(gate["upper_bound_tolerance_fraction"]),
    }


def plot(cases: list[dict], output_path: Path) -> None:
    import matplotlib.pyplot as plt

    ordered = sorted(cases, key=lambda row: row["wheel_friction"])
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 5.5))
    figure.patch.set_facecolor("#F5F7F8")
    for axis in axes:
        axis.set_facecolor("white")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#D9DEE2", linewidth=0.8, alpha=0.7)

    steady_bound = ordered[0]["steady_bound"]
    active_bound = ordered[0]["active_bound"]
    rejection = steady_bound * (1 + ordered[0]["tolerance"])
    for index, case in enumerate(ordered):
        x_offsets = [index + (repeat - (len(case["torques"]) - 1) / 2) * 0.08
                     for repeat in range(len(case["torques"]))]
        axes[0].scatter(x_offsets, case["torques"], color=POINT_COLOR, s=68, zorder=3)
        axes[0].scatter(
            [index],
            [case["torque_median"]],
            marker="_",
            s=360,
            linewidth=2.4,
            color=PASS_COLOR if case["status"].startswith("PASS") else FAIL_COLOR,
            zorder=4,
        )
    axes[0].axhline(steady_bound, color="#25323A", linewidth=1.2,
                    label=f"RIDER steady upper bound: {steady_bound:.3f} N m")
    axes[0].axhline(active_bound, color="#526D82", linewidth=1.0, linestyle=":",
                    label=f"RIDER active upper bound: {active_bound:.3f} N m")
    axes[0].axhline(rejection, color="#7C8790", linewidth=1.0, linestyle="--",
                    label=f"Rejection threshold: {rejection:.3f} N m")
    axes[0].set_xticks(range(len(ordered)), [f"mu={row['wheel_friction']:g}" for row in ordered])
    axes[0].set_ylabel("Predicted median-absolute wheel torque (N m)")
    axes[0].set_title("Physical torque bracket", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, fontsize=8, loc="best")
    axes[0].margins(y=0.12)

    width = 0.34
    positions = list(range(len(ordered)))
    torque_gate = [row["torque_cv"] / 0.15 for row in ordered]
    strain_gate = [row["strain_range"] / 0.03 for row in ordered]
    axes[1].bar([x - width / 2 for x in positions], torque_gate, width,
                label="Torque CV / 15% gate", color="#2F6B5F")
    axes[1].bar([x + width / 2 for x in positions], strain_gate, width,
                label="Strain range / 0.03 gate", color="#D18B2C")
    axes[1].axhline(1, color="#25323A", linewidth=1.1, linestyle="--")
    axes[1].set_xticks(positions, [f"mu={row['wheel_friction']:g}" for row in ordered])
    axes[1].set_ylabel("Observed / numerical gate limit")
    axes[1].set_title("Numerical repeatability", loc="left", fontweight="bold")
    axes[1].legend(frameon=False, fontsize=8, loc="best")

    figure.suptitle(
        "GRASP DEM full-duration wheel-friction bracket",
        x=0.06,
        y=0.98,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.06,
        0.91,
        "Same Alabama wheel, imported bed, load, speed, slip, timestep, and CD1 solver profile",
        fontsize=10,
        color="#44515A",
    )
    figure.text(
        0.06,
        0.025,
        "Local one-bed calibration sensitivity only; held-out physical confirmation and paired compaction data remain required.",
        fontsize=9,
        color="#44515A",
    )
    figure.tight_layout(rect=(0.04, 0.095, 0.99, 0.88))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        nargs=2,
        action="append",
        metavar=("SUMMARY", "GATE"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(
        [load_case(Path(summary), Path(gate)) for summary, gate in args.case],
        args.output,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
