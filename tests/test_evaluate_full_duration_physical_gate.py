from evaluate_full_duration_physical_gate import evaluate


def manifest(reference=0.7025):
    return {
        "sequence_condition": {
            "measured_steady_tare_corrected_median_abs_torque_nm": reference
        }
    }


def summary(status="PASS_PROVISIONAL", median=0.68):
    return {
        "status": status,
        "torque_nm": {"median": median, "minimum": 0.65, "maximum": 0.71},
    }


def test_passes_repeatable_prediction_below_physical_upper_bound():
    result = evaluate(summary(), manifest())

    assert result["status"] == "PASS_PROVISIONAL_PLAUSIBILITY"
    assert result["physical_plausibility_status"] == (
        "WITHIN_20_PERCENT_OF_PHYSICAL_UPPER_BOUND"
    )
    assert result["measured_compaction_reference_status"] == (
        "NOT_AVAILABLE_IN_RIDER_EXPORT"
    )
    assert len(result["minimum_next_physical_record"]) == 5


def test_rejects_prediction_that_exceeds_upper_bound_tolerance():
    result = evaluate(summary(median=0.90), manifest())

    assert result["status"] == "REJECT_EXCEEDS_PHYSICAL_UPPER_BOUND"


def test_repeatability_failure_controls_before_physical_comparison():
    result = evaluate(summary(status="REJECT_QUALITY_GATE"), manifest())

    assert result["status"] == "REJECT_NUMERICAL_REPEATABILITY"
