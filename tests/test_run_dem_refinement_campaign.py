import csv
import json

from run_dem_refinement_campaign import summarize_sensitivity


def test_summarize_sensitivity_ignores_existing_summary(tmp_path):
    result = {
        "status": "COMPLETE",
        "completed_laps": [1, 2],
        "summaries": {
            "calibration": {"relative_error": 0.1},
            "held_out_validation": {
                "relative_error": 0.2,
                "median_lap_relative_error": 0.15,
                "laps_within_20_percent_fraction": 0.5,
            },
        },
        "compaction": {
            "simulated_cumulative_column_density_ratio_proxy": 1.12,
        },
    }
    (tmp_path / "sensitivity-baseline.json").write_text(json.dumps(result))
    (tmp_path / "sensitivity-summary.json").write_text(json.dumps([{"old": True}]))

    summarize_sensitivity(tmp_path)

    summary = json.loads((tmp_path / "sensitivity-summary.json").read_text())
    assert len(summary) == 1
    assert summary[0]["scenario"] == "baseline"
    assert summary[0]["completed_laps"] == 2
    with (tmp_path / "sensitivity-summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["scenario"] == "baseline"
