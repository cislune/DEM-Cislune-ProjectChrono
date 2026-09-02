#!/usr/bin/env python3
"""Plot exact-manifest solver-profile repeatability gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROFILE_LABELS = {
    "cub": "CUB",
    "cub-fixed-bin": "CUB + fixed bin",
    "cub-fixed-bin-cd20": "CUB + fixed bin + CD20",
    "cub-fixed-bin-cd1": "CUB + fixed bin + CD1",
}

STATUS_COLORS = {
    "PASS_PROVISIONAL": "#2F6B5F",
    "REJECT_QUALITY_GATE": "#A84A45",
    "PARTIAL": "#D18B2C",
}


def profile_label(profile: str) -> str:
    return PROFILE_LABELS.get(profile, profile.replace("-", " "))


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, "#7C8790")


def plot(
    comparison: dict,
    output_path: Path,
    torque_cv_gate: float = 0.15,
    strain_range_gate: float = 0.03,
) -> None:
    import matplotlib.pyplot as plt

    profiles = comparison.get("profiles", [])
    if not profiles:
        raise ValueError("No solver profiles are available to plot")

    labels = [profile_label(row["profile"]) for row in profiles]
    colors = [status_color(row["status"]) for row in profiles]
    completion = [row["completed_repeats"] for row in profiles]
    failed = [row.get("failed_attempts", 0) for row in profiles]
    torque_cv = [
        100 * row["torque_cv"] if row["torque_cv"] is not None else 0
        for row in profiles
    ]
    strain_range = [
        row["column_strain_range"]
        if row["column_strain_range"] is not None
        else 0
        for row in profiles
    ]

    figure, axes = plt.subplots(1, 3, figsize=(15.5, 5.5))
    figure.patch.set_facecolor("#F5F7F8")
    for axis in axes:
        axis.set_facecolor("white")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#D9DEE2", linewidth=0.8, alpha=0.7)
        axis.tick_params(axis="x", rotation=18)

    bars = axes[0].bar(
        labels,
        completion,
        color=colors,
        width=0.62,
        label="Completed",
    )
    axes[0].bar(
        labels,
        failed,
        bottom=completion,
        color="#C8CDD2",
        edgecolor="#7C8790",
        hatch="//",
        width=0.62,
        label="Failed launch",
    )
    axes[0].set_title("Launch outcomes", loc="left", fontweight="bold")
    axes[0].set_ylabel("Exact-input launches")
    axes[0].set_ylim(
        0,
        max(3.55, max(c + f for c, f in zip(completion, failed)) + 0.65),
    )
    axes[0].axhline(3, color="#44515A", linewidth=1.0, linestyle="--")
    for bar, value, failures in zip(bars, completion, failed):
        center = bar.get_x() + bar.get_width() / 2
        if value:
            axes[0].text(
                center,
                value / 2,
                f"{value} OK",
                ha="center",
                va="center",
                fontsize=9,
                color="white",
                fontweight="bold",
            )
        if failures:
            axes[0].text(
                center,
                value + failures / 2,
                f"{failures} FAIL",
                ha="center",
                va="center",
                fontsize=8,
                color="#44515A",
                fontweight="bold",
            )

    bars = axes[1].bar(labels, torque_cv, color=colors, width=0.62)
    axes[1].set_title("Torque repeatability", loc="left", fontweight="bold")
    axes[1].set_ylabel("Torque coefficient of variation (%)")
    axes[1].axhline(
        100 * torque_cv_gate,
        color="#44515A",
        linewidth=1.0,
        linestyle="--",
        label=f"Gate: {torque_cv_gate:.0%}",
    )
    axes[1].legend(frameon=False, loc="upper left")
    for bar, value, row in zip(bars, torque_cv, profiles):
        label = "n/a" if row["torque_cv"] is None else f"{value:.1f}%"
        axes[1].text(
            bar.get_x() + bar.get_width() / 2,
            value + max(torque_cv + [15]) * 0.025,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
        )

    bars = axes[2].bar(labels, strain_range, color=colors, width=0.62)
    axes[2].set_title("Compaction-proxy repeatability", loc="left", fontweight="bold")
    axes[2].set_ylabel("Column-strain range")
    axes[2].axhline(
        strain_range_gate,
        color="#44515A",
        linewidth=1.0,
        linestyle="--",
        label=f"Gate: {strain_range_gate:.2f}",
    )
    axes[2].legend(frameon=False, loc="upper left")
    for bar, value, row in zip(bars, strain_range, profiles):
        label = "n/a" if row["column_strain_range"] is None else f"{value:.4f}"
        axes[2].text(
            bar.get_x() + bar.get_width() / 2,
            value + max(strain_range + [strain_range_gate]) * 0.025,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
        )

    figure.suptitle(
        "GRASP DEM exact-manifest solver repeatability",
        x=0.055,
        y=0.98,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.055,
        0.91,
        "Same Alabama wheel, same lap-2 particle state, same manifest; three repeats required",
        fontsize=10,
        color="#44515A",
    )
    selected = comparison.get("selected_profile") or "none"
    figure.text(
        0.055,
        0.025,
        f"Campaign decision: {comparison.get('status', 'UNKNOWN')} | selected profile: {selected}\n"
        "Green = provisional numerical pass; red = rejected; amber = incomplete. Physical calibration is a separate gate.",
        fontsize=9,
        color="#44515A",
    )
    figure.tight_layout(rect=(0.035, 0.105, 0.99, 0.88))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison_json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--torque-cv-gate", type=float, default=0.15)
    parser.add_argument("--strain-range-gate", type=float, default=0.03)
    args = parser.parse_args()
    comparison = json.loads(args.comparison_json.read_text())
    plot(
        comparison,
        args.output,
        torque_cv_gate=args.torque_cv_gate,
        strain_range_gate=args.strain_range_gate,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
