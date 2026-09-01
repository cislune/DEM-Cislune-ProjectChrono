import json

import pytest

from generate_density_margin_sweep import generate_sweep, margin_label


def source_queue(tmp_path):
    root = tmp_path / "project"
    case_dir = root / "cases" / "wheel_source"
    case_dir.mkdir(parents=True)
    source = case_dir / "smooth.json"
    source.write_text(
        json.dumps(
            {
                "case_id": "process-smooth_control-r8mm-dt5us-phase1p2s",
                "model_status": "software_process_checkout",
                "terrain": {
                    "base_particle_radius_m": 0.008,
                    "time_step_s": 0.000005,
                    "compression_release_margin": 0.18,
                },
            }
        )
    )
    queue = case_dir / "queue.json"
    queue.write_text(json.dumps({"manifests": ["cases/wheel_source/smooth.json"]}))
    return root, queue


def test_margin_label_is_filename_safe():
    assert margin_label(0.35) == "0p35"


def test_generate_sweep_writes_unique_cases(tmp_path):
    root, queue = source_queue(tmp_path)
    output = root / "cases" / "density_sweep"
    queue_output = generate_sweep(queue, output, [0.18, 0.55])
    generated = json.loads(queue_output.read_text())
    assert len(generated["manifests"]) == 2
    cases = [json.loads((root / path).read_text()) for path in generated["manifests"]]
    assert cases[0]["case_id"].endswith("-margin0p18")
    assert cases[1]["terrain"]["compression_release_margin"] == 0.55
    assert cases[1]["model_status"] == "density_preparation_margin_sweep"


def test_generate_sweep_rejects_duplicate_margins(tmp_path):
    _, queue = source_queue(tmp_path)
    with pytest.raises(ValueError, match="unique"):
        generate_sweep(queue, tmp_path / "out", [0.18, 0.18])
