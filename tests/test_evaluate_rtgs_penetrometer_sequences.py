import json

from evaluate_rtgs_penetrometer_sequences import evaluate


def test_evaluate_compares_normalized_trends_without_absolute_cpt_claim(tmp_path):
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps(
            {
                "campaigns": [
                    {
                        "campaign_id": "siu-1",
                        "wheel_design": "Closed_SIU",
                        "replicate": 1,
                        "points": [
                            {"laps_completed": 0, "readings": [{"value": 1}]},
                            {"laps_completed": 1, "readings": [{"value": 2}]},
                            {"laps_completed": 2, "readings": [{"value": 4}]},
                        ],
                    }
                ]
            }
        )
    )
    for lap, strain in ((1, 0.01), (2, 0.02)):
        case = tmp_path / f"rtgs-cpt-sequence-closed-siu-lap{lap:02d}"
        case.mkdir()
        (case / "frozen_case.json").write_text(
            json.dumps(
                {"rtgs_penetrometer_target": {"design": "Closed_SIU", "lap": lap}}
            )
        )
        (case / "wheel_performance.json").write_text(
            json.dumps(
                {
                    "lane": {
                        "column_strain_proxy": strain,
                        "p95_surface_settlement_m": 0.001,
                    },
                    "mobility": {
                        "torque_y_nm": {"median_abs": 2.0},
                        "median_abs_drawbar_over_normal_load": 0.1,
                    },
                    "density_gate": {"status": "REJECT_DENSITY_MISMATCH"},
                }
            )
        )
    result = evaluate(tmp_path, reference)
    campaign = result["designs"][0]["physical_campaigns"][0]
    assert result["status"] == "PARTIAL"
    assert result["evidence_role"] == "held_out_validation"
    assert campaign["matched_laps"] == [0, 1, 2]
    assert campaign["normalized_shape_pearson"] > 0.99
    assert result["designs"][0]["all_density_gates_pass"] is False
