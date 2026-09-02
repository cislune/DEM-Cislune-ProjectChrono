import json

from evaluate_candidate_lap_sequences import evaluate


def add_case(
    root, candidate, lap, torque, drawbar, settlement, strain, design_hash="design"
):
    case = root / f"candidate-sequence-{candidate}-lap{lap:02d}"
    case.mkdir()
    (case / "frozen_case.json").write_text(
        json.dumps(
            {
                "candidate_sequence": {"candidate": candidate, "lap": lap},
                "provenance": {
                    "design_obj_path": f"{candidate}.obj",
                    "design_obj_sha256": design_hash,
                    "source_obj_path": f"{candidate}-collision.obj",
                    "source_obj_sha256": f"source-{candidate}",
                },
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
    assert broad["geometry_provenance_status"] == "VERIFIED_SINGLE_GEOMETRY"
    assert broad["design_obj_sha256"] == "design"


def test_evaluate_candidate_sequence_rejects_mixed_geometry(tmp_path):
    for lap in range(1, 11):
        add_case(
            tmp_path,
            "smooth_control",
            lap,
            1.0,
            0.5,
            0.01,
            0.01,
            design_hash="first" if lap < 10 else "second",
        )

    result = evaluate(tmp_path)

    assert result["status"] == "REJECT_MIXED_GEOMETRY"
