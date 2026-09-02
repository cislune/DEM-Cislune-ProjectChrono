import json

import pytest

from generate_full_duration_friction_case import generate


def test_generate_changes_only_wheel_friction_and_metadata(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "case_id": "full-cd1",
                "model_status": "same_bed_full_duration_solver_profile_check",
                "purpose": "baseline",
                "terrain": {"wheel_friction": 1.05, "particle_friction": 0.5},
                "solver": {"cd_update_frequency": 1},
                "test": {"duration_s": 1.2},
                "sequence_condition": {
                    "frozen_wheel_friction": 1.05,
                    "sensitivity_overrides": {"wheel_friction": 1.05},
                },
            }
        )
    )

    case = generate(source_path, 0.9)

    assert case["case_id"] == "full-cd1-wheel-mu0p9"
    assert case["terrain"]["wheel_friction"] == 0.9
    assert case["terrain"]["particle_friction"] == 0.5
    assert case["solver"]["cd_update_frequency"] == 1
    assert case["test"]["duration_s"] == 1.2
    assert case["sequence_condition"]["frozen_wheel_friction"] == 0.9
    assert case["full_duration_friction_sensitivity"]["source_wheel_friction"] == 1.05


def test_generate_rejects_nonpositive_friction(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps({"case_id": "case", "terrain": {"wheel_friction": 1.0}}))

    with pytest.raises(ValueError, match="positive"):
        generate(source_path, 0)
