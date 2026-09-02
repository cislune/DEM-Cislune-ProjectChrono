import json

from summarize_density_seed_repeatability import summarize


def preparation(tmp_path, seed, achieved):
    case = tmp_path / f"seed{seed}"
    terrain = case / "terrain"
    terrain.mkdir(parents=True)
    (case / "frozen_case.json").write_text(
        json.dumps(
            {
                "case_id": f"density-seed{seed}",
                "terrain": {"compression_release_margin": 0.35, "random_seed": seed},
            }
        )
    )
    path = terrain / "terrain_preparation.json"
    path.write_text(
        json.dumps(
            {
                "target_bulk_density_kg_m3": 1700.0,
                "post_release_bulk_density_kg_m3": achieved,
            }
        )
    )
    return path


def test_passes_repeatable_density_near_target(tmp_path):
    result = summarize(
        [preparation(tmp_path, 77, 1690), preparation(tmp_path, 78, 1710)]
    )

    assert result["status"] == "PASS_DENSITY_TARGET_AND_REPEATABILITY"
    assert result["repeatability_within_tolerance"] is True


def test_withholds_absolute_use_when_repeatable_but_underdense(tmp_path):
    result = summarize(
        [preparation(tmp_path, 77, 1480), preparation(tmp_path, 78, 1490)]
    )

    assert result["status"] == "PASS_REPEATABILITY_REJECT_TARGET"
    assert "Do not use" in result["decision"]
