import json

import pytest

from generate_full_duration_solver_profile_case import generate


def test_generate_applies_selected_profile_without_changing_duration(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "case_id": "repeatability-cub-wheel-r01",
                "model_status": "same_bed_numerical_repeatability_check",
                "purpose": "baseline",
                "solver": {
                    "sort_contact_pairs": True,
                    "use_cub_force_collection": True,
                },
                "test": {"duration_s": 1.2},
                "repeatability_target": {"execution_profile": "cub"},
            }
        )
    )

    case = generate(source_path, "cub-fixed-bin-cd1")

    assert case["case_id"] == "repeatability-cub-fixed-bin-cd1-wheel-r01"
    assert case["test"]["duration_s"] == 1.2
    assert case["solver"]["cd_update_frequency"] == 1
    assert case["solver"]["disable_adaptive_bin_size"] is True
    assert case["solver"]["disable_adaptive_update_frequency"] is True
    assert case["repeatability_target"]["execution_profile"] == "cub-fixed-bin-cd1"


def test_generate_rejects_unknown_profile(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps({"case_id": "repeatability-cub-wheel"}))

    with pytest.raises(ValueError, match="Unsupported solver profile"):
        generate(source_path, "unknown")
