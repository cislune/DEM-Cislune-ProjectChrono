import json
from pathlib import Path

import dem_case_runner as runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_example_passes_preflight(tmp_path):
    case_path = PROJECT_ROOT / "examples" / "wheel_case.example.json"
    case, _, report = runner.preflight_case(case_path, PROJECT_ROOT, tmp_path)

    assert case["model_status"] == "uncalibrated_software_checkout"
    assert report["status"] == "PASS"
    assert report["physical_reference_path"] is None
    assert report["mesh"]["watertight_two_manifold"] is True


def test_controlled_record_schema_freezes_load_tolerance():
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "wheel_test_record.schema.json").read_text()
    )

    tolerance = schema["properties"]["loading"]["properties"][
        "normal_load_tolerance_fraction"
    ]
    assert tolerance["maximum"] == 0.05
