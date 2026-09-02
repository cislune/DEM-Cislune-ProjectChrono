import json

from plot_full_duration_friction_bracket import load_case


def test_load_case_collects_repeat_metrics(tmp_path):
    summary_path = tmp_path / "summary.json"
    gate_path = tmp_path / "gate.json"
    summary_path.write_text(
        json.dumps(
            {
                "repeats": [
                    {"repeat": 1, "completed": True, "torque_nm": 0.7},
                    {"repeat": 2, "completed": False},
                    {"repeat": 3, "completed": True, "torque_nm": 0.72},
                ],
                "torque_nm": {"median": 0.71, "coefficient_of_variation": 0.02},
                "column_strain_proxy": {"range": 0.004},
            }
        )
    )
    gate_path.write_text(
        json.dumps(
            {
                "wheel_friction": 0.9,
                "status": "PASS_PROVISIONAL_PLAUSIBILITY",
                "rider_steady_tare_corrected_upper_bound_nm": 0.7025,
                "rider_active_tare_corrected_upper_bound_nm": 0.825,
                "upper_bound_tolerance_fraction": 0.2,
            }
        )
    )

    case = load_case(summary_path, gate_path)

    assert case["wheel_friction"] == 0.9
    assert case["torques"] == [0.7, 0.72]
    assert case["torque_median"] == 0.71
