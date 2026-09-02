import json

from generate_alabama_sensitivity_campaign import generate


def test_generate_sensitivity_keeps_lap_chain_and_holdout(tmp_path):
    root = tmp_path / "project"
    base = root / "cases" / "base"
    base.mkdir(parents=True)
    manifests = []
    for lap in range(1, 11):
        path = base / f"lap{lap:02d}.json"
        path.write_text(
            json.dumps(
                {
                    "case_id": f"base-lap{lap:02d}",
                    "terrain": {
                        "initial_state_case_id": "fixed-bed",
                        "initial_state_filename": "settled_terrain_data.csv",
                        "wheel_friction": 0.9,
                    },
                    "test": {"slip_ratios": [0.1]},
                    "sequence_condition": {
                        "lap": lap,
                        "split": "calibration" if lap <= 5 else "held_out_validation",
                    },
                }
            )
        )
        manifests.append(str(path.relative_to(root)))
    queue = base / "queue.json"
    queue.write_text(json.dumps({"manifests": manifests}))

    master = generate(
        queue,
        root / "cases" / "campaign",
        {"baseline": {}, "wheel_mu0p8": {"wheel_friction": 0.8}},
    )
    master_data = json.loads(master.read_text())
    scenario_queue = json.loads((root / master_data["scenario_queues"][1]).read_text())
    first = json.loads((root / scenario_queue["manifests"][0]).read_text())
    second = json.loads((root / scenario_queue["manifests"][1]).read_text())
    sixth = json.loads((root / scenario_queue["manifests"][5]).read_text())
    assert first["terrain"]["wheel_friction"] == 0.8
    assert first["terrain"]["initial_state_case_id"] == "fixed-bed"
    assert second["terrain"]["initial_state_case_id"] == first["case_id"]
    assert sixth["sequence_condition"]["split"] == "held_out_validation"
    assert sixth["sequence_condition"]["campaign_scenario"] == "wheel_mu0p8"
