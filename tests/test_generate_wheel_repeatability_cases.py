import json
from pathlib import Path

from generate_wheel_repeatability_cases import generate


def test_generate_repeatability_cases_share_one_bed(tmp_path):
    root = tmp_path / "project"
    source_dir = root / "cases" / "screen"
    source_dir.mkdir(parents=True)
    manifests = []
    for candidate in ("smooth_control", "broad_wave_12"):
        path = source_dir / f"{candidate}.json"
        path.write_text(
            json.dumps(
                {
                    "case_id": candidate,
                    "wheel": {"obj": f"wheel_candidates/{candidate}.obj"},
                    "terrain": {"initial_state_case_id": "old-bed"},
                }
            )
        )
        manifests.append(str(path.relative_to(root)))
    queue = source_dir / "queue.json"
    queue.write_text(json.dumps({"manifests": manifests}))

    output = root / "cases" / "repeatability"
    queue_path = generate(
        queue,
        output,
        "fixed-bed",
        ("smooth_control", "broad_wave_12"),
        replicates=2,
        bed_state_sha256="bedhash",
    )

    generated = json.loads(queue_path.read_text())
    assert len(generated["manifests"]) == 4
    first = json.loads((root / generated["manifests"][0]).read_text())
    assert first["terrain"]["initial_state_case_id"] == "fixed-bed"
    assert first["repeatability_target"]["replicates_requested"] == 2
    assert first["repeatability_target"]["shared_bed_state_sha256"] == "bedhash"
