from plot_solver_determinism_profiles import profile_label, status_color


def test_profile_labels_are_human_readable():
    assert profile_label("cub-fixed-bin-cd20") == "CUB + fixed bin + CD20"
    assert profile_label("custom-profile") == "custom profile"


def test_gate_status_colors_distinguish_partial_and_reject():
    assert status_color("PARTIAL") != status_color("REJECT_QUALITY_GATE")
    assert status_color("PASS_PROVISIONAL") != status_color("REJECT_QUALITY_GATE")
