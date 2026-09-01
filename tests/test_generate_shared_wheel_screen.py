import json

from generate_shared_wheel_screen import prepare_manifest, screen_queue


def test_prepare_manifest_uses_smooth_case_and_release_margin(tmp_path):
    root = tmp_path / "project"
    queue_dir = root / "cases" / "wheel_screen_cpt"
    queue_dir.mkdir(parents=True)
    case_path = queue_dir / "smooth.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "screen-smooth_control-coarse-cpt-informed",
                "terrain": {
                    "base_particle_radius_m": 0.004,
                    "compression_release_margin": 0.0,
                },
            }
        )
    )
    queue_path = queue_dir / "queue.json"
    queue_path.write_text(
        json.dumps({"manifests": ["cases/wheel_screen_cpt/smooth.json"]})
    )
    output = root / "cases" / "wheel_screen_shared" / "bed.json"
    prepare_manifest(queue_path, output, 0.2, 78)
    prepared = json.loads(output.read_text())
    assert prepared["case_id"] == "wheel-shared-bed-r4mm-cpt-informed-seed78"
    assert prepared["terrain"]["compression_release_margin"] == 0.2
    assert prepared["terrain"]["random_seed"] == 78
    assert prepared["shared_bed_generation"]["random_seed"] == 78


def test_screen_queue_distinguishes_nondefault_seed(tmp_path):
    root = tmp_path / "project"
    queue_dir = root / "cases" / "wheel_screen_cpt"
    queue_dir.mkdir(parents=True)
    case_path = queue_dir / "smooth.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "screen-smooth_control-coarse-cpt-informed",
                "terrain": {},
            }
        )
    )
    queue_path = queue_dir / "queue.json"
    queue_path.write_text(
        json.dumps({"manifests": ["cases/wheel_screen_cpt/smooth.json"]})
    )

    terrain_dir = root / "runs" / "bed" / "terrain"
    source_state = terrain_dir / "settled terrain data" / "settled.csv"
    source_state.parent.mkdir(parents=True)
    source_state.write_text("X,Y,Z\n0,0,0\n")
    (terrain_dir / "terrain_preparation.json").write_text(
        json.dumps(
            {
                "target_bulk_density_kg_m3": 1700.0,
                "post_release_bulk_density_kg_m3": 1680.0,
                "random_seed": 78,
            }
        )
    )

    output_dir = root / "cases" / "wheel_screen_shared"
    output_queue = screen_queue(queue_path, source_state, None, output_dir)
    generated_queue = json.loads(output_queue.read_text())
    generated_case = json.loads(
        (root / generated_queue["manifests"][0]).read_text()
    )
    assert generated_case["case_id"].endswith("-shared-bed-seed78")
    assert generated_case["shared_sample_preparation"]["random_seed"] == 78


def test_prepare_manifest_distinguishes_process_timestep(tmp_path):
    root = tmp_path / "project"
    queue_dir = root / "cases" / "wheel_process_checkout"
    queue_dir.mkdir(parents=True)
    case_path = queue_dir / "smooth.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "process-smooth_control-r12mm-dt20us",
                "model_status": "software_process_checkout",
                "terrain": {
                    "base_particle_radius_m": 0.012,
                    "time_step_s": 0.00002,
                },
            }
        )
    )
    queue_path = queue_dir / "queue.json"
    queue_path.write_text(
        json.dumps({"manifests": ["cases/wheel_process_checkout/smooth.json"]})
    )

    output = root / "cases" / "runtime" / "bed.json"
    prepare_manifest(queue_path, output, 0.18)

    prepared = json.loads(output.read_text())
    assert prepared["case_id"] == "wheel-shared-bed-r12mm-cpt-informed-process-dt20us"
