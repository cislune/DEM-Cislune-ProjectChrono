import json

from plan_physical_wheel_retest import build


def write_json(path, value):
    path.write_text(json.dumps(value))
    return path


def test_plan_selects_pareto_candidate_after_repeatability_pass(tmp_path):
    candidate_path = write_json(
        tmp_path / "candidates.json",
        {
            "status": "COMPLETE",
            "candidates": [
                {"candidate": "smooth_control", "completed_laps": 10},
                {
                    "candidate": "balanced",
                    "completed_laps": 10,
                    "density_ratio_gain_vs_smooth": 1.20,
                    "drawbar_vs_smooth": 1.10,
                    "torque_vs_smooth": 1.05,
                },
                {
                    "candidate": "dominated",
                    "completed_laps": 10,
                    "density_ratio_gain_vs_smooth": 1.10,
                    "drawbar_vs_smooth": 1.00,
                    "torque_vs_smooth": 1.10,
                },
            ],
        },
    )
    repeat_path = write_json(
        tmp_path / "repeat.json", {"status": "PASS_PROVISIONAL"}
    )

    result = build(candidate_path, repeat_path)

    assert result["status"] == "READY_MVP_RETEST"
    assert result["pareto_candidates"][0]["candidate"] == "balanced"
    assert [row["wheel"] for row in result["mvp_wheels"]] == [
        "alabama_reference",
        "smooth_control",
        "balanced",
    ]
    assert len([row for row in result["test_matrix"] if row["phase"] == "MVP"]) == 9


def test_plan_holds_when_numerical_repeatability_fails(tmp_path):
    candidate_path = write_json(
        tmp_path / "candidates.json",
        {
            "status": "COMPLETE",
            "candidates": [
                {
                    "candidate": "candidate",
                    "completed_laps": 10,
                    "density_ratio_gain_vs_smooth": 1.20,
                    "drawbar_vs_smooth": 1.10,
                    "torque_vs_smooth": 1.05,
                }
            ],
        },
    )
    repeat_path = write_json(
        tmp_path / "repeat.json", {"status": "REJECT_QUALITY_GATE"}
    )

    result = build(candidate_path, repeat_path)

    assert result["status"] == "HOLD_NUMERICAL_REPEATABILITY_GATE"
