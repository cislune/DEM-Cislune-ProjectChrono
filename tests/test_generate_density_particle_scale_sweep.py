import json

import pytest

from generate_density_particle_scale_sweep import generate_sweep, label_mm, label_us


def source_queue(tmp_path):
    root = tmp_path / "project"
    case_dir = root / "cases" / "wheel_source"
    case_dir.mkdir(parents=True)
    source = case_dir / "smooth.json"
    source.write_text(
        json.dumps(
            {
                "case_id": "process-smooth_control-r8mm-dt5us",
                "model_status": "software_process_checkout",
                "terrain": {
                    "base_particle_radius_m": 0.008,
                    "time_step_s": 0.000005,
                    "particle_density_kg_m3": 2750.0,
                    "target_bulk_density_kg_m3": 1700.0,
                },
            }
        )
    )
    queue = case_dir / "queue.json"
    queue.write_text(json.dumps({"manifests": ["cases/wheel_source/smooth.json"]}))
    return root, queue


def test_labels_are_portable():
    assert label_mm(0.006) == "6"
    assert label_us(0.00000375) == "3p75"


def test_generate_sweep_scales_timestep_with_radius(tmp_path):
    root, queue = source_queue(tmp_path)
    output = root / "cases" / "particle_sweep"
    queue_output = generate_sweep(queue, output, [0.006, 0.004])
    generated = json.loads(queue_output.read_text())
    cases = [json.loads((root / path).read_text()) for path in generated["manifests"]]
    assert cases[0]["case_id"].endswith("r6mm-dt3p75us-l200mm")
    assert cases[0]["terrain"]["time_step_s"] == pytest.approx(0.00000375)
    assert cases[0]["terrain"]["bin_travel_length_m"] == 0.2
    assert cases[0]["allowed_stages"] == ["preflight", "terrain"]
    assert cases[1]["terrain"]["base_particle_radius_m"] == 0.004
    assert cases[1]["density_particle_scale_sweep"]["source_manifest"] == (
        "cases/wheel_source/smooth.json"
    )


def test_generate_sweep_rejects_duplicate_radii(tmp_path):
    _, queue = source_queue(tmp_path)
    with pytest.raises(ValueError, match="unique"):
        generate_sweep(queue, tmp_path / "out", [0.006, 0.006])
