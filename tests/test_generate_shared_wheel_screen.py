import json

from generate_shared_wheel_screen import prepare_manifest


def test_prepare_manifest_uses_smooth_case_and_release_margin(tmp_path):
    root = tmp_path / "project"
    queue_dir = root / "cases" / "wheel_screen_cpt"
    queue_dir.mkdir(parents=True)
    case_path = queue_dir / "smooth.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "screen-smooth_control-coarse-cpt-informed",
                "terrain": {"compression_release_margin": 0.0},
            }
        )
    )
    queue_path = queue_dir / "queue.json"
    queue_path.write_text(
        json.dumps({"manifests": ["cases/wheel_screen_cpt/smooth.json"]})
    )
    output = root / "cases" / "wheel_screen_shared" / "bed.json"
    prepare_manifest(queue_path, output, 0.2)
    prepared = json.loads(output.read_text())
    assert prepared["case_id"] == "wheel-shared-bed-r4mm-cpt-informed"
    assert prepared["terrain"]["compression_release_margin"] == 0.2
