import json

from diagnose_exact_repeat_divergence import diagnose


def make_repeat(root, repeat, frame_0, frame_25):
    case = root / repeat / "case"
    output = case / "wheel" / "slip" / "terrain motion"
    output.mkdir(parents=True)
    (case / "wheel_performance.json").write_text(json.dumps({}))
    (output / "terrain_0000.csv").write_text(frame_0)
    (output / "terrain_0025.csv").write_text(frame_25)


def test_reports_earliest_divergent_frame(tmp_path):
    make_repeat(tmp_path, "r01", "same", "first")
    make_repeat(tmp_path, "r02", "same", "second")

    result = diagnose(tmp_path)

    assert result["status"] == "DIVERGENT_OUTPUTS"
    assert result["first_divergent_frame"] == 25
    assert result["first_divergent_time_s"] == 0.025
