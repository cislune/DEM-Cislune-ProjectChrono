import json

from evaluate_solver_determinism_profiles import evaluate


def write_summary(root, profile, status, torque_cv, strain_range, attempts_recorded=3):
    target = root / profile
    target.mkdir()
    (target / "exact-repeat-summary.json").write_text(
        json.dumps(
            {
                "status": status,
                "completed_repeats": 3,
                "attempts_allowed": 6,
                "attempts_recorded": attempts_recorded,
                "torque_nm": {"coefficient_of_variation": torque_cv},
                "column_strain_proxy": {"range": strain_range},
                "repeats": [
                    {"wall_duration_s": 10.0},
                    {"wall_duration_s": 12.0},
                    {"wall_duration_s": 11.0},
                ],
            }
        )
    )


def test_selects_most_repeatable_passing_profile(tmp_path):
    write_summary(tmp_path, "profile-a", "PASS_PROVISIONAL", 0.10, 0.02)
    write_summary(tmp_path, "profile-b", "PASS_PROVISIONAL", 0.05, 0.025)
    write_summary(tmp_path, "profile-c", "REJECT_QUALITY_GATE", 0.20, 0.04)

    result = evaluate(tmp_path)

    assert result["status"] == "PASS_PROVISIONAL"
    assert result["selected_profile"] == "profile-b"
    assert result["profiles"][0]["median_wall_duration_s"] == 11.0


def test_reports_failed_launches_separately_from_completed_repeats(tmp_path):
    write_summary(
        tmp_path,
        "profile-a",
        "PASS_PROVISIONAL",
        0.10,
        0.02,
        attempts_recorded=5,
    )

    result = evaluate(tmp_path)

    assert result["profiles"][0]["completed_repeats"] == 3
    assert result["profiles"][0]["failed_attempts"] == 2
    assert result["profiles"][0]["attempts_allowed"] == 6


def test_launch_ledger_excludes_setup_rejections_from_solver_failures(tmp_path):
    write_summary(tmp_path, "profile-a", "PASS_PROVISIONAL", 0.10, 0.02)
    (tmp_path / "launch-summary.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile": "profile-a",
                        "successful_launches": 3,
                        "failed_solver_launches": 1,
                        "setup_rejections": 4,
                        "interrupted_before_solver_progress": 1,
                    }
                ]
            }
        )
    )

    result = evaluate(tmp_path)
    profile = result["profiles"][0]

    assert profile["failed_attempts"] == 1
    assert profile["attempts_recorded"] == 4
    assert profile["setup_rejections"] == 4
    assert profile["interrupted_before_solver_progress"] == 1
