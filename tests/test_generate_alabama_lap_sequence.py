import json
from pathlib import Path

from generate_alabama_lap_sequence import final_state_relative_path, generate


def test_generate_chains_exact_lap_conditions(tmp_path):
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
                        "active_abs_torque_nm": {"median": 3.0},
                        "active_tare_corrected_abs_torque_nm": {
                            "median": 0.8 + index * 0.01
                        },
                        "steady_tare_corrected_abs_torque_nm": {
                            "median": 0.7 + index * 0.01
                        },
                        "active_load_kg_reported": {"median": 9.0 + index * 0.1},
                        "derived_slip": {"median": 0.08 + index * 0.001},
                        "derived_carriage_speed_m_s": {
                            "median": 0.09 + index * 0.001
                        },
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
        cases / "sequence",
        0.3,
        bed_case_id="fixed-bed",
        bed_state_sha256="state123",
    )
    queue_data = json.loads(queue.read_text())
    first = json.loads((root / queue_data["manifests"][0]).read_text())
    second = json.loads((root / queue_data["manifests"][1]).read_text())
    sixth = json.loads((root / queue_data["manifests"][5]).read_text())
    assert first["terrain"]["initial_state_case_id"] == "fixed-bed"
    assert second["terrain"]["initial_state_case_id"] == first["case_id"]
    assert second["terrain"]["initial_state_relative_path"] == final_state_relative_path(
        first["test"]["slip_ratios"][0]
    )
    assert first["sequence_condition"]["split"] == "calibration"
    assert sixth["sequence_condition"]["split"] == "held_out_validation"
    assert second["test"]["normal_load_n"] == (9.1 * 9.80665)
    assert queue_data["frozen_wheel_friction"] == 0.3
