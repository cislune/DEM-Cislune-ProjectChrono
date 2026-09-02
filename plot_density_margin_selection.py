#!/usr/bin/env python3
"""Plot deterministic density-margin selection and optional seed confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PASS_COLOR = "#2F6B5F"
FAIL_COLOR = "#A84A45"
POINT_COLOR = "#2F5D7C"


def margin_rows(ranking: list[dict]) -> list[dict]:
    return sorted(ranking, key=lambda row: row["compression_release_margin"])


def plot(ranking: list[dict], seed_summary: dict | None, output_path: Path) -> None:
    import matplotlib.pyplot as plt

    rows = margin_rows(ranking)
    if not rows:
        raise ValueError("Density-margin ranking is empty")
    target = float(rows[0]["target_bulk_density_kg_m3"])
    tolerance = 0.03
    margins = [float(row["compression_release_margin"]) for row in rows]
    achieved = [float(row["post_release_bulk_density_kg_m3"]) for row in rows]
    colors = [
        PASS_COLOR if abs(value / target - 1) <= tolerance else FAIL_COLOR
        for value in achieved
    ]

    figure, axes = plt.subplots(1, 2, figsize=(12.5, 5.5))
    figure.patch.set_facecolor("#F5F7F8")
    for axis in axes:
        axis.set_facecolor("white")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#D9DEE2", linewidth=0.8, alpha=0.7)

    axes[0].axhspan(
        target * (1 - tolerance),
        target * (1 + tolerance),
        color="#DDEBE6",
        alpha=0.75,
        zorder=0,
    )
    axes[0].axhline(
        target, color="#25323A", linewidth=1.2, label="Physical target"
    )

    axes[0].plot(margins, achieved, color=POINT_COLOR, linewidth=1.1, alpha=0.7)
    axes[0].scatter(margins, achieved, color=colors, s=82, zorder=3)
    for margin, density in zip(margins, achieved):
        axes[0].annotate(
            f"{density:,.0f}",
            (margin, density),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    axes[0].set_xlabel("Compression-release margin")
    axes[0].set_ylabel("Post-release bulk density (kg/m3)")
    axes[0].set_title("Margin selection", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, fontsize=8, loc="best")

    if seed_summary:
        axes[1].axhspan(
            target * (1 - tolerance),
            target * (1 + tolerance),
            color="#DDEBE6",
            alpha=0.75,
            zorder=0,
        )
        axes[1].axhline(target, color="#25323A", linewidth=1.2)
        preparations = seed_summary["preparations"]
        seeds = [str(row["random_seed"]) for row in preparations]
        seed_density = [
            float(row["post_release_bulk_density_kg_m3"]) for row in preparations
        ]
        seed_colors = [
            PASS_COLOR if abs(value / target - 1) <= tolerance else FAIL_COLOR
            for value in seed_density
        ]
        axes[1].scatter(seeds, seed_density, color=seed_colors, s=82, zorder=3)
        axes[1].plot(seeds, seed_density, color=POINT_COLOR, linewidth=1.1, alpha=0.7)
        axes[1].set_xlabel("Terrain random seed")
        axes[1].set_title("Selected margin across seeds", loc="left", fontweight="bold")
        cv = seed_summary["post_release_density_kg_m3"]["coefficient_of_variation"]
        axes[1].text(
            0.02,
            0.96,
            f"Status: {seed_summary['status'].replace('_', ' ')}\nDensity CV: {cv:.2%}",
            transform=axes[1].transAxes,
            va="top",
            fontsize=9,
        )
    else:
        errors = [abs(value - target) for value in achieved]
        axes[1].bar([f"{margin:g}" for margin in margins], errors, color=colors)
        axes[1].set_xlabel("Compression-release margin")
        axes[1].set_ylabel("Absolute density error (kg/m3)")
        axes[1].set_title("Selection error", loc="left", fontweight="bold")
        axes[1].set_ylim(bottom=0)

    figure.suptitle(
        "GRASP DEM four-millimeter bed-density calibration",
        x=0.06,
        y=0.98,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.06,
        0.91,
        "Patched DEME solver with deterministic CD1 execution profile",
        fontsize=10,
        color="#44515A",
    )
    figure.text(
        0.06,
        0.025,
        "Target band is +/-3%. Density acceptance is necessary but does not replace CPT or paired wheel-compaction validation.",
        fontsize=9,
        color="#44515A",
    )
    figure.tight_layout(rect=(0.04, 0.095, 0.99, 0.88))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ranking", type=Path)
    parser.add_argument("--seed-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ranking = json.loads(args.ranking.read_text())
    seed_summary = (
        json.loads(args.seed_summary.read_text()) if args.seed_summary else None
    )
    plot(ranking, seed_summary, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
