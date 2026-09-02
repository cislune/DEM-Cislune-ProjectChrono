from evaluate_force_model_isolation import evaluate


def divergence(status, frame=None):
    return {
        "status": status,
        "repeats_compared": ["r01", "r02", "r03"],
        "first_divergent_frame": frame,
        "first_divergent_time_s": frame / 1000 if frame is not None else None,
    }


def test_implicates_history_path_when_frictionless_outputs_are_identical():
    result = evaluate(
        divergence("DIVERGENT_OUTPUTS", 25),
        divergence("IDENTICAL_OUTPUTS"),
    )

    assert result["status"] == "CONTACT_HISTORY_PATH_IMPLICATED"
    assert result["frictional"]["first_divergent_frame"] == 25
    assert result["frictionless"]["first_divergent_frame"] is None


def test_reports_persistent_divergence_without_history():
    result = evaluate(
        divergence("DIVERGENT_OUTPUTS", 25),
        divergence("DIVERGENT_OUTPUTS", 50),
    )

    assert result["status"] == "DIVERGENCE_PERSISTS_WITHOUT_HISTORY"
    assert "contact detection" in result["decision"]


def test_reports_inconclusive_incomplete_repeat_set():
    result = evaluate(
        divergence("DIVERGENT_OUTPUTS", 25),
        divergence("NO_COMPLETE_REPEAT_SET"),
    )

    assert result["status"] == "INCONCLUSIVE"
