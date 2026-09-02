import json

from evaluate_candidate_lap_sequences import evaluate


def add_case(root, candidate, lap, torque, drawbar, settlement, strain):
    case = root / f"candidate-sequence-{candidate}-lap{lap:02d}"
    case.mkdir()
    (case / "frozen_case.json").write_text(
        json.dumps({"candidate_sequence": {"candidate": candidate, "lap": lap}})
    )
    (case / "wheel_performance.json").write_text(
        json.dumps(
            {
                "mobility": {
                    "torque_y_nm": {"median_abs": torque},
                    "median_abs_drawbar_over_normal_load": drawbar,
                },
                "lane": {
                    "p95_surface_settlement_m": settlement,
                    "column_strain_proxy": strain,
                },
                "density_gate": {"status": "REJECT_DENSITY_MISMATCH"},
            }
        )
    )


def test_evaluate_candidate_sequence_normalizes_to_smooth(tmp_path):
    for lap in range(1, 11):
        add_case(tmp_path, "smooth_control", lap, 1.0, 0.5, 0.01, 0.01)
        add_case(tmp_path, "broad_wave_12", lap, 1.1, 0.45, 0.012, 0.012)
    result = evaluate(tmp_path)
    broad = next(row for row in result["candidates"] if row["candidate"] == "broad_wave_12")
    assert result["status"] == "COMPLETE"
    assert broad["torque_vs_smooth"] == 1.1
    assert broad["drawbar_vs_smooth"] == 0.9
    assert broad["settlement_vs_smooth"] == 1.2
