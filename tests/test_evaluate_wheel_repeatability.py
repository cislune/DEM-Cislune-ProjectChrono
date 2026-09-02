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
                        "shared_bed_state_sha256": "bed",
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
                    "project_git_revision": "abc123",
                    "project_git_dirty": False,
                }
            )
        )

    result = evaluate(tmp_path)

    assert result["status"] == "REJECT_QUALITY_GATE"
    summary = result["candidates"][0]
    assert summary["completed_replicates"] == 2
    assert abs(summary["torque_nm"]["range"] - 0.2) < 1e-12
    assert abs(summary["column_strain_proxy"]["range"] - 0.04) < 1e-12
    assert summary["simulation_source_hashes"] == ["sim"]
    assert summary["shared_bed_state_hashes"] == ["bed"]
    assert summary["quality_gate"]["issues"] == [
        "NUMERICAL_REPEATABILITY_LIMIT_EXCEEDED"
    ]


def test_evaluate_repeatability_rejects_mixed_source_provenance(tmp_path):
    for replicate, sim_hash in ((1, "sim-a"), (2, "sim-b")):
        case = tmp_path / f"repeatability-smooth_control-r{replicate:02d}"
        case.mkdir()
        (case / "frozen_case.json").write_text(
            json.dumps(
                {
                    "repeatability_target": {
                        "candidate": "smooth_control",
                        "replicate": replicate,
                        "replicates_requested": 2,
                        "shared_bed_state_sha256": "bed",
                    }
                }
            )
        )
        (case / "wheel_performance.json").write_text(
            json.dumps(
                {
                    "mobility": {
                        "torque_y_nm": {"median_abs": 1.0},
                        "median_abs_drawbar_over_normal_load": 0.5,
                    },
                    "lane": {
                        "column_strain_proxy": 0.10,
                        "p95_surface_settlement_m": 0.01,
                    },
                    "simulation_source_provenance": {
                        "combined_sha256": sim_hash
                    },
                    "analysis_source_provenance": {"combined_sha256": "analysis"},
                    "project_git_revision": "abc123",
                    "project_git_dirty": False,
                }
            )
        )

    result = evaluate(tmp_path)

    assert result["status"] == "REJECT_QUALITY_GATE"
    assert result["candidates"][0]["quality_gate"]["issues"] == [
        "MIXED_SIMULATION_SOURCE_PROVENANCE"
    ]


def test_evaluate_repeatability_passes_clean_stable_batch(tmp_path):
    for replicate, torque, strain in ((1, 1.0, 0.10), (2, 1.02, 0.11)):
        case = tmp_path / f"repeatability-smooth_control-r{replicate:02d}"
        case.mkdir()
        (case / "frozen_case.json").write_text(
            json.dumps(
                {
                    "repeatability_target": {
                        "candidate": "smooth_control",
                        "replicate": replicate,
                        "replicates_requested": 2,
                        "shared_bed_state_sha256": "bed",
                    }
                }
            )
        )
        (case / "wheel_performance.json").write_text(
            json.dumps(
                {
                    "mobility": {
                        "torque_y_nm": {"median_abs": torque},
                        "median_abs_drawbar_over_normal_load": 0.5,
                    },
                    "lane": {
                        "column_strain_proxy": strain,
                        "p95_surface_settlement_m": strain / 10,
                    },
                    "simulation_source_provenance": {"combined_sha256": "sim"},
                    "analysis_source_provenance": {"combined_sha256": "analysis"},
                    "project_git_revision": "abc123",
                    "project_git_dirty": False,
                }
            )
        )

    result = evaluate(tmp_path)

    assert result["status"] == "PASS_PROVISIONAL"
    assert result["candidates"][0]["quality_gate"]["issues"] == []


def test_evaluate_repeatability_accepts_named_profile_and_rejects_mixed_profile(
    tmp_path,
):
    for replicate, profile in ((1, "repeatability-cub"), (2, "repeatability")):
        case = tmp_path / f"{profile}-smooth_control-r{replicate:02d}"
        case.mkdir()
        (case / "frozen_case.json").write_text(
            json.dumps(
                {
                    "repeatability_target": {
                        "candidate": "smooth_control",
                        "execution_profile": profile,
                        "replicate": replicate,
                        "replicates_requested": 2,
                        "shared_bed_state_sha256": "bed",
                    }
                }
            )
        )
        (case / "wheel_performance.json").write_text(
            json.dumps(
                {
                    "mobility": {
                        "torque_y_nm": {"median_abs": 1.0},
                        "median_abs_drawbar_over_normal_load": 0.5,
                    },
                    "lane": {
                        "column_strain_proxy": 0.10,
                        "p95_surface_settlement_m": 0.01,
                    },
                    "simulation_source_provenance": {"combined_sha256": "sim"},
                    "analysis_source_provenance": {
                        "combined_sha256": "analysis"
                    },
                    "project_git_revision": "abc123",
                    "project_git_dirty": False,
                }
            )
        )

    result = evaluate(tmp_path)

    assert result["status"] == "REJECT_QUALITY_GATE"
    summary = result["candidates"][0]
    assert summary["execution_profiles"] == [
        "repeatability",
        "repeatability-cub",
    ]
    assert summary["quality_gate"]["issues"] == ["MIXED_EXECUTION_PROFILE"]
