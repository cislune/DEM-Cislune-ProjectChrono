import json

from compare_alabama_sequence_repeats import evaluate


def write_lap(root, lap, torque, strain):
    case = root / f"case-{lap:02d}"
    case.mkdir(parents=True)
    (case / "frozen_case.json").write_text(
        json.dumps(
            {
                "sequence_condition": {
                    "lap": lap,
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
                    "p95_surface_settlement_m": 0.01,
                },
                "simulation_source_provenance": {"combined_sha256": "sim"},
                "analysis_source_provenance": {"combined_sha256": "analysis"},
            }
        )
    )


def test_compare_sequence_repeats_reports_paired_spread(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_lap(first, 1, 1.0, 0.10)
    write_lap(second, 1, 1.5, 0.12)

    result = evaluate(first, second)

    assert result["status"] == "PARTIAL_DIAGNOSTIC"
    assert result["shared_bed_match"] is True
    assert result["source_provenance_complete"] is True
    assert result["summary"]["median_torque_relative_delta_to_first"] == 0.5
    assert abs(
        result["summary"]["median_column_strain_absolute_delta"] - 0.02
    ) < 1e-12
