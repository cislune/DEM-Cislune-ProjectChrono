import json

from generate_frozen_candidate_screen import CANDIDATES, generate


def test_generate_freezes_condition_and_shared_bed(tmp_path):
    root = tmp_path / "project"
    source = root / "cases" / "source"
    source.mkdir(parents=True)
    for candidate, filename in CANDIDATES.items():
        (source / filename).write_text(
            json.dumps(
                {
                    "case_id": candidate,
                    "wheel": {"obj": f"{candidate}.obj"},
                    "terrain": {},
                    "test": {},
                }
            )
        )
    queue = generate(
        source,
        root / "cases" / "output",
        0.3,
        bed_case_id="fixed-bed",
        bed_state_sha256="state123",
    )
    data = json.loads(queue.read_text())
    case = json.loads((root / data["manifests"][0]).read_text())
    assert case["terrain"]["wheel_friction"] == 0.3
    assert case["terrain"]["initial_state_case_id"] == "fixed-bed"
    assert case["test"]["normal_load_n"] == 9.05 * 9.80665
    assert case["frozen_screen_provenance"]["shared_bed_state_sha256"] == "state123"
