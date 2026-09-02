import json
import os

from audit_repeat_output_independence import audit


def make_repeat(root, repeat, content):
    case = root / repeat / "case"
    output = case / "wheel" / "slip" / "terrain motion"
    output.mkdir(parents=True)
    (case / "wheel_performance.json").write_text(json.dumps({}))
    path = output / "terrain_0000.csv"
    path.write_text(content)
    return path


def test_reports_independently_written_outputs(tmp_path):
    make_repeat(tmp_path, "r01", "same")
    make_repeat(tmp_path, "r02", "same")

    result = audit(tmp_path)

    assert result["status"] == "INDEPENDENT_OUTPUTS"
    assert result["common_output_files"] == 1


def test_detects_hardlinked_repeat_outputs(tmp_path):
    first = make_repeat(tmp_path, "r01", "same")
    second = make_repeat(tmp_path, "r02", "temporary")
    second.unlink()
    os.link(first, second)

    result = audit(tmp_path)

    assert result["status"] == "SHARED_OUTPUT_STORAGE_DETECTED"
    assert result["shared_storage_paths"] == [
        "wheel/slip/terrain motion/terrain_0000.csv"
    ]
