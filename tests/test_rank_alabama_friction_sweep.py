import json

import pytest

from rank_alabama_friction_sweep import collect


def write_result(root, friction, predicted):
    case_dir = root / f"calibrate-alabama-wheel-friction-mu{friction}"
    case_dir.mkdir(parents=True)
    (case_dir / "frozen_case.json").write_text(
        json.dumps(
            {
                "terrain": {"wheel_friction": friction},
                "calibration_target": {"median_abs_torque_nm": 3.0},
            }
        )
    )
    (case_dir / "wheel_performance.json").write_text(
        json.dumps(
            {
                "case_id": case_dir.name,
                "status": "PASS_COMPARATIVE_METRICS",
                "mobility": {"torque_y_nm": {"median_abs": predicted}},
                "density_gate": {
                    "status": "REJECT_DENSITY_MISMATCH",
                    "achieved_to_target_ratio": 0.8,
                },
            }
        )
    )


def test_collect_ranks_absolute_torque_error(tmp_path):
    write_result(tmp_path, 0.3, 2.0)
    write_result(tmp_path, 0.7, 3.1)
    rows = collect(tmp_path)
    assert [row["wheel_friction"] for row in rows] == [0.7, 0.3]
    assert rows[0]["relative_torque_error"] == pytest.approx(0.1 / 3.0)


def test_collect_can_rescore_with_corrected_reference(tmp_path):
    write_result(tmp_path, 0.3, 0.9)
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps(
            {
                "laps": [
                    {"active_tare_corrected_abs_torque_nm": {"median": value}}
                    for value in (0.7, 0.8, 0.9, 1.0, 1.1)
                ]
            }
        )
    )
    rows = collect(tmp_path, reference)
    assert rows[0]["target_median_abs_torque_nm"] == pytest.approx(0.9)
    assert rows[0]["relative_torque_error"] == pytest.approx(0.0)
    assert rows[0]["target_metric"] == "active_tare_corrected_abs_torque_nm.median"
