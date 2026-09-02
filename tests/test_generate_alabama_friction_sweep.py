import json

import pytest

from generate_alabama_friction_sweep import generate


def test_generate_uses_disjoint_physical_split_and_fixed_bed(tmp_path):
    root = tmp_path / "project"
    cases = root / "cases"
    cases.mkdir(parents=True)
    alabama = cases / "alabama.json"
    alabama.write_text(
        json.dumps(
            {
                "wheel": {"obj": "wheel.obj"},
                "cpt_calibration_provenance": {"selected_case_id": "cpt-best"},
            }
        )
    )
    profile = cases / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "terrain": {"wheel_friction": 0.6},
                "test": {},
                "solver": {},
                "output": {},
            }
        )
    )
    reference = root / "reference.json"
    reference.write_text(
        json.dumps(
            {
                "laps": [
                    {
                        "active_abs_torque_nm": {"median": 3.0 + index * 0.1},
                        "active_load_kg_reported": {"median": 9.0 + index * 0.1},
                        "derived_slip": {"median": 0.08 + index * 0.001},
                        "derived_carriage_speed_m_s": {"median": 0.1},
                    }
                    for index in range(10)
                ]
            }
        )
    )
    queue = generate(
        alabama,
        profile,
        reference,
        cases / "friction",
        [0.3, 0.7],
        bed_case_id="fixed-bed",
        bed_state_sha256="abc123",
    )
    generated_queue = json.loads(queue.read_text())
    case = json.loads((root / generated_queue["manifests"][0]).read_text())
    assert generated_queue["calibration_split"] == "Alabama RIDER laps 1-5"
    assert generated_queue["held_out_split"] == "Alabama RIDER laps 6-10"
    assert case["terrain"]["initial_state_case_id"] == "fixed-bed"
    assert case["terrain"]["wheel_friction"] == 0.3
    assert case["calibration_target"]["median_abs_torque_nm"] == 3.2
    assert case["shared_sample_preparation"]["achieved_to_target_ratio"] < 1.0


def test_generate_rejects_duplicate_friction(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        generate(
            tmp_path / "cases" / "a.json",
            tmp_path / "cases" / "p.json",
            tmp_path / "r.json",
            tmp_path / "out",
            [0.5, 0.5],
        )
