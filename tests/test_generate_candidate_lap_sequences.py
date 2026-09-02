import json

from generate_candidate_lap_sequences import generate


def test_generate_candidate_sequences_replace_wheel_and_chain_state(tmp_path):
    root = tmp_path / "project"
    base = root / "cases" / "base"
    candidates = root / "cases" / "candidates"
    base.mkdir(parents=True)
    candidates.mkdir(parents=True)
    base_paths = []
    for lap in range(1, 11):
        path = base / f"lap{lap:02d}.json"
        path.write_text(
            json.dumps(
                {
                    "case_id": f"base-lap{lap:02d}",
                    "terrain": {
                        "initial_state_case_id": "fixed-bed",
                        "initial_state_filename": "settled_terrain_data.csv",
                    },
                    "test": {"slip_ratios": [0.1]},
                    "wheel": {"obj": "alabama.obj"},
                    "sequence_condition": {"lap": lap},
                }
            )
        )
        base_paths.append(str(path.relative_to(root)))
    base_queue = base / "queue.json"
    base_queue.write_text(json.dumps({"manifests": base_paths}))
    candidate_path = candidates / "smooth.json"
    candidate_path.write_text(
        json.dumps(
            {
                "case_id": "process-smooth_control-r8mm-dt5us-phase1p2s",
                "wheel": {"obj": "smooth.obj"},
            }
        )
    )
    candidate_queue = candidates / "queue.json"
    candidate_queue.write_text(
        json.dumps({"manifests": [str(candidate_path.relative_to(root))]})
    )

    master = generate(base_queue, candidate_queue, root / "cases" / "output")
    master_data = json.loads(master.read_text())
    queue = json.loads((root / master_data["candidate_queues"][0]).read_text())
    first = json.loads((root / queue["manifests"][0]).read_text())
    second = json.loads((root / queue["manifests"][1]).read_text())
    assert first["wheel"]["obj"] == "smooth.obj"
    assert first["candidate_sequence"]["candidate"] == "smooth_control"
    assert second["terrain"]["initial_state_case_id"] == first["case_id"]
