import json

from evaluate_refinement_selection import evaluate


def write_campaign(tmp_path):
    project = tmp_path / "project"
    cases = project / "cases" / "sensitivity"
    results = tmp_path / "results"
    cases.mkdir(parents=True)
    results.mkdir()
    scenarios = {
        "baseline": ({}, 0.9, 5e-6),
        "wheel_mu0p75": ({"wheel_friction": 0.75}, 0.75, 5e-6),
        "timestep2p5us": ({"time_step_s": 2.5e-6}, 0.9, 2.5e-6),
        "timestep7p5us": ({"time_step_s": 7.5e-6}, 0.9, 7.5e-6),
    }
    queue_paths = []
    for name, (overrides, friction, timestep) in scenarios.items():
        scenario_dir = cases / name
        scenario_dir.mkdir()
        manifest = scenario_dir / "lap01.json"
        manifest.write_text(
            json.dumps(
                {"terrain": {"wheel_friction": friction, "time_step_s": timestep}}
            )
        )
        queue = scenario_dir / "sequence_queue.json"
        queue.write_text(
            json.dumps(
                {
                    "campaign_scenario": name,
                    "sensitivity_overrides": overrides,
                    "manifests": [str(manifest.relative_to(project))],
                }
            )
        )
        queue_paths.append(str(queue.relative_to(project)))
    master = cases / "sensitivity_campaign.json"
    master.write_text(json.dumps({"scenario_queues": queue_paths}))
    return master, results


def write_result(results, scenario, calibration_error, held_error, fraction, complete=True):
    laps = list(range(1, 11)) if complete else list(range(1, 9))
    payload = {
        "status": "COMPLETE_FAIL_DENSITY_MISMATCH" if complete else "PARTIAL",
        "completed_laps": laps,
        "summaries": {
            "calibration": {
                "completed_laps": 5,
                "relative_error": calibration_error,
                "median_predicted_contact_torque_nm": 1.0 + calibration_error,
            },
            "held_out_validation": {
                "completed_laps": 5 if complete else 3,
                "relative_error": held_error,
                "median_lap_relative_error": held_error,
                "laps_within_20_percent_fraction": fraction,
                "median_predicted_contact_torque_nm": 1.2 + held_error,
            },
        },
        "compaction": {"simulated_cumulative_column_density_ratio_proxy": 1.3},
    }
    (results / f"sensitivity-{scenario}.json").write_text(json.dumps(payload))


def test_selection_uses_calibration_only_and_reports_held_out_failure(tmp_path):
    master, results = write_campaign(tmp_path)
    write_result(results, "baseline", 0.20, 0.05, 1.0)
    write_result(results, "wheel_mu0p75", 0.01, 0.40, 0.4)
    write_result(results, "timestep2p5us", 0.22, 0.07, 0.8)
    write_result(results, "timestep7p5us", 0.18, 0.06, 0.8)

    result = evaluate(results, master)

    assert result["status"] == "PARAMETER_SELECTED_HELD_OUT_FAIL"
    selected = result["wheel_friction_selection"]
    assert selected["selected_scenario"] == "wheel_mu0p75"
    assert selected["selected_wheel_friction"] == 0.75
    assert selected["held_out_assessment"]["status"] == "FAIL"
    assert result["local_sensitivity"]["status"] == "AVAILABLE"
    assert result["time_step_sensitivity"]["status"] == "AVAILABLE"


def test_selection_excludes_incomplete_low_error_case(tmp_path):
    master, results = write_campaign(tmp_path)
    write_result(results, "baseline", 0.20, 0.05, 1.0)
    write_result(results, "wheel_mu0p75", 0.01, 0.01, 1.0, complete=False)

    result = evaluate(results, master)

    assert result["status"] == "PARAMETER_SELECTED_HELD_OUT_PASS"
    selected = result["wheel_friction_selection"]
    assert selected["selected_scenario"] == "baseline"
    assert selected["excluded_scenarios"][0]["scenario"] == "wheel_mu0p75"
