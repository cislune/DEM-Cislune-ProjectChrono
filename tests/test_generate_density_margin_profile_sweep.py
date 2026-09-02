import json
from pathlib import Path

import pytest

from generate_density_margin_profile_sweep import generate


def source_manifest(tmp_path):
    path = tmp_path / "density-r4.json"
    path.write_text(
        json.dumps(
            {
                "case_id": "density-r4",
                "terrain": {
                    "base_particle_radius_m": 0.004,
                    "compression_release_margin": 0.18,
                    "particle_density_kg_m3": 2750.0,
                    "target_bulk_density_kg_m3": 1700.0,
                },
                "solver": {"cd_update_frequency": 20, "error_out_velocity_m_s": 30},
            }
        )
    )
    return path


def test_generate_changes_only_margin_and_solver_profile(tmp_path):
    queue_path = generate(source_manifest(tmp_path), tmp_path / "out", [0.18, 0.35])
    queue = json.loads(queue_path.read_text())
    cases = [json.loads(Path(path).read_text()) for path in queue["manifests"]]

    assert len(cases) == 2
    assert cases[0]["terrain"]["compression_release_margin"] == 0.18
    assert cases[1]["terrain"]["compression_release_margin"] == 0.35
    assert cases[0]["solver"]["cd_update_frequency"] == 1
    assert cases[0]["solver"]["disable_adaptive_bin_size"] is True
    assert cases[0]["solver"]["error_out_velocity_m_s"] == 30
    assert cases[0]["allowed_stages"] == ["preflight", "terrain"]


def test_generate_rejects_duplicate_margins(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        generate(source_manifest(tmp_path), tmp_path / "out", [0.18, 0.18])


def test_generate_rejects_impossible_density(tmp_path):
    with pytest.raises(ValueError, match="particle density"):
        generate(source_manifest(tmp_path), tmp_path / "out", [0.7])
