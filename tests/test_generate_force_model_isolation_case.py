import json

import pytest

from generate_force_model_isolation_case import generate


def test_generate_changes_only_diagnostic_metadata_and_force_model(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "case_id": "wheel-cd1",
                "model_status": "short_exact_manifest_solver_determinism_probe",
                "purpose": "baseline",
                "solver": {"use_cub_force_collection": True},
                "terrain": {"particle_friction": 0.5},
                "wheel": {"obj": "wheel.obj"},
            }
        )
    )

    case = generate(source_path, "frictionless_hertzian")

    assert case["case_id"] == "wheel-cd1-frictionless_hertzian"
    assert case["solver"]["contact_force_model"] == "frictionless_hertzian"
    assert case["solver"]["use_cub_force_collection"] is True
    assert case["terrain"]["particle_friction"] == 0.5
    assert case["wheel"]["obj"] == "wheel.obj"
    assert case["force_model_isolation"]["source_case_id"] == "wheel-cd1"


def test_generate_rejects_unknown_force_model(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps({"case_id": "wheel", "solver": {}}))

    with pytest.raises(ValueError, match="Unsupported contact force model"):
        generate(source_path, "mystery")
