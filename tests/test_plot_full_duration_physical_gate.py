from plot_full_duration_physical_gate import (
    FAIL_COLOR,
    PASS_COLOR,
    WITHHELD_COLOR,
    gate_color,
)


def test_gate_color_distinguishes_pass_fail_and_withheld():
    assert gate_color("PASS_PROVISIONAL") == PASS_COLOR
    assert gate_color("WITHIN_20_PERCENT_OF_PHYSICAL_UPPER_BOUND") == PASS_COLOR
    assert gate_color("REJECT_EXCEEDS_PHYSICAL_UPPER_BOUND") == FAIL_COLOR
    assert gate_color("WITHHELD_PENDING_PAIRED_BED_MEASUREMENT") == WITHHELD_COLOR
