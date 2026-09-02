from compare_wheel_repeatability_profiles import compare


def summary(profile, status, torque_cv, strain_range):
    return {
        "status": status,
        "execution_profiles": [profile],
        "candidates": [
            {
                "candidate": "smooth_control",
                "torque_nm": {"coefficient_of_variation": torque_cv},
                "column_strain_proxy": {"range": strain_range},
                "quality_gate": {"status": "PASS_PROVISIONAL"},
            }
        ],
    }


def test_compare_profiles_reports_uniformly_lower_spread():
    result = compare(
        summary("repeatability", "PASS_PROVISIONAL", 0.20, 0.04),
        summary("repeatability-cub", "PASS_PROVISIONAL", 0.10, 0.02),
    )

    assert result["status"] == "COMPLETE"
    assert result["finding"] == "COMPARISON_PROFILE_LOWER_SPREAD"
    row = result["candidates"][0]
    assert row["torque_cv_relative_change"] == -0.5
    assert row["column_strain_range_relative_change"] == -0.5


def test_compare_profiles_rejects_partial_summary():
    result = compare(
        summary("repeatability", "PARTIAL", 0.20, 0.04),
        summary("repeatability-cub", "PASS_PROVISIONAL", 0.10, 0.02),
    )

    assert result["status"] == "INCONCLUSIVE"
    assert result["finding"] == "INCONCLUSIVE"
    assert result["issues"] == ["REFERENCE_PARTIAL"]
