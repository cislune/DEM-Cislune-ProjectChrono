import json

from evaluate_alabama_lap_sequence import evaluate


def test_evaluate_preserves_held_out_outlier(tmp_path):
    for lap in range(1, 11):
        case = tmp_path / f"alabama-rider-sequence-mu0p9-lap{lap:02d}"
        case.mkdir()
        split = "calibration" if lap <= 5 else "held_out_validation"
        observed = 1.0
        predicted = 2.0 if lap == 10 else 1.0
        (case / "frozen_case.json").write_text(
            json.dumps(
                {
                    "sequence_condition": {
                        "lap": lap,
                        "split": split,
                        "measured_tare_corrected_median_abs_torque_nm": observed,
                    }
                }
            )
        )
        (case / "wheel_performance.json").write_text(
            json.dumps(
                {
                    "mobility": {"torque_y_nm": {"median_abs": predicted}},
                    "lane": {"column_strain_proxy": 0.01},
                    "density_gate": {"status": "REJECT_DENSITY_MISMATCH"},
                    "status": "PASS_COMPARATIVE_METRICS",
                }
            )
        )
    result = evaluate(tmp_path)
    held_out = result["summaries"]["held_out_validation"]
    assert result["torque_validation_status"] == "PASS_MEDIAN_WITH_OUTLIER"
    assert held_out["laps_within_20_percent_fraction"] == 0.8
    assert held_out["outlier_laps_over_50_percent"] == [10]
    assert "DENSITY_MISMATCH" in result["status"]
