import json

from evaluate_rtgs_ordering_validation import evaluate


def test_evaluate_separates_current_and_mobility_ordering(tmp_path):
    data = {
        "Closed_Sharp": (0.27, 0.10, 3.0, 0.14),
        "Closed_SIU": (0.23, 0.13, 6.0, 0.04),
        "Closed_Scalloped": (0.22, 0.15, 9.0, 0.06),
    }
    for design, (current, slip, torque, drawbar) in data.items():
        case = tmp_path / f"validate-rtgs-{design.lower()}-r8mm-frozen"
        case.mkdir()
        (case / "frozen_case.json").write_text(
            json.dumps(
                {
                    "ordinal_validation_target": {
                        "design": design,
                        "median_of_lap_median_abs_current_reading": current,
                        "measured_median_slip": slip,
                    }
                }
            )
        )
        (case / "wheel_performance.json").write_text(
            json.dumps(
                {
                    "mobility": {
                        "torque_y_nm": {"median_abs": torque},
                        "median_abs_drawbar_over_normal_load": drawbar,
                    },
                    "density_gate": {"status": "REJECT_DENSITY_MISMATCH"},
                }
            )
        )
    result = evaluate(tmp_path)
    assert result["motor_demand_ordering"]["concordant_pair_fraction"] == 0.0
    assert result["mobility_ordering"]["concordant_pair_fraction"] == 2 / 3
    assert result["status"] == "FAIL_MOTOR_DEMAND_ORDER_PARTIAL_MOBILITY_ORDER"
