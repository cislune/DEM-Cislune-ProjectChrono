from plot_solver_stability_diagnostic import repeatability_note


def test_repeatability_note_reports_gate_metrics():
    note = repeatability_note(
        {
            "status": "PASS_PROVISIONAL",
            "candidates": [
                {
                    "torque_nm": {"coefficient_of_variation": 0.08},
                    "column_strain_proxy": {"range": 0.0123},
                }
            ],
        }
    )

    assert "torque CV 8.0%" in note
    assert "column-strain range 0.0123" in note
