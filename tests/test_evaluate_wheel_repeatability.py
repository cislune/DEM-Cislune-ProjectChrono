import json

from evaluate_wheel_repeatability import evaluate


def test_evaluate_repeatability_reports_metric_spread(tmp_path):
    for replicate, torque, strain in ((1, 1.0, 0.10), (2, 1.2, 0.14)):
        case = tmp_path / f"repeatability-smooth_control-r{replicate:02d}"
        case.mkdir()
        (case / "frozen_case.json").write_text(
            json.dumps(
                {
                    "repeatability_target": {
                        "candidate": "smooth_control",
                        "replicate": replicate,
                        "replicates_requested": 2,
                    }
                }
            )
        )
        (case / "wheel_performance.json").write_text(
            json.dumps(
                {
                    "mobility": {
                        "torque_y_nm": {"median_abs": torque},
                        "median_abs_drawbar_over_normal_load": 0.5 + replicate / 10,
                    },
                    "lane": {
                        "column_strain_proxy": strain,
                        "p95_surface_settlement_m": strain / 10,
                    },
                    "simulation_source_provenance": {"combined_sha256": "sim"},
                    "analysis_source_provenance": {"combined_sha256": "analysis"},
                }
            )
        )

    result = evaluate(tmp_path)

    assert result["status"] == "COMPLETE"
    summary = result["candidates"][0]
    assert summary["completed_replicates"] == 2
    assert abs(summary["torque_nm"]["range"] - 0.2) < 1e-12
    assert abs(summary["column_strain_proxy"]["range"] - 0.04) < 1e-12
    assert summary["simulation_source_hashes"] == ["sim"]
