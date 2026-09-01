import json
from pathlib import Path

import pytest

from apply_cpt_calibration_to_wheel_cases import (
    CalibrationSelectionError,
    create_cases,
    select_calibration,
)


def calibration_row(status="PASS"):
    return {
        "case_id": "cpt-best",
        "selection_score": 0.1,
        "density_gate_status": status,
        "q100_ratio": 1.02,
        "post_release_bulk_density_kg_m3": 1702.0,
        "youngs_modulus_pa": 3e8,
        "particle_friction": 0.5,
        "rolling_resistance": 0.05,
        "cohesion": 50.0,
        "particle_radius_m": 0.002,
    }


def test_rejects_density_mismatch(tmp_path):
    rank = tmp_path / "rank.json"
    rank.write_text(json.dumps([calibration_row("REJECT_DENSITY_MISMATCH")]))
    with pytest.raises(CalibrationSelectionError):
        select_calibration(rank)


def test_creates_provenanced_case_without_overwriting_source(tmp_path):
    root = tmp_path / "project"
    queue_dir = root / "cases" / "wheel_screen"
    queue_dir.mkdir(parents=True)
    source = queue_dir / "screen.json"
    original = {
        "case_id": "screen-test",
        "terrain": {
            "base_particle_radius_m": 0.004,
            "youngs_modulus_pa": 1e9,
            "particle_friction": 0.4,
            "rolling_resistance": 0.02,
            "cohesion": 0.0,
        },
    }
    source.write_text(json.dumps(original))
    queue = queue_dir / "queue.json"
    queue.write_text(json.dumps({"manifests": ["cases/wheel_screen/screen.json"]}))
    rank = root / "rank.json"
    rank.write_text(json.dumps([calibration_row()]))

    generated_queue = create_cases(queue, rank, root / "cases" / "wheel_screen_cpt")
    generated = json.loads(generated_queue.read_text())
    case = json.loads((root / generated["manifests"][0]).read_text())

    assert json.loads(source.read_text()) == original
    assert case["terrain"]["youngs_modulus_pa"] == 3e8
    assert "4 mm particle resolution" in case["purpose"]
    assert case["cpt_calibration_provenance"]["resolution_transfer"][
        "absolute_prediction_status"
    ].startswith("WITHHELD")
