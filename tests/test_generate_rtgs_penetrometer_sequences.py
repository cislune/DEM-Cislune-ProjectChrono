import json
from pathlib import Path

from generate_rtgs_penetrometer_sequences import DESIGNS, generate, ordered_laps


def test_ordered_laps_recovers_numeric_order_from_lexically_sorted_folders():
    laps = []
    for folder in ("Laps1-5", "Laps11-15", "Laps6-10"):
        for reported_lap in range(1, 6):
            laps.append(
                {
                    "source": f"/archive/{folder}/{reported_lap}.TXT",
                    "reported_lap": reported_lap,
                }
            )
    ordered = ordered_laps(laps)
    assert [lap for lap, _ in ordered] == list(range(1, 16))
    assert Path(ordered[5][1]["source"]).parent.name == "Laps6-10"


def test_generate_chains_two_fifty_lap_held_out_sequences(tmp_path):
    root = tmp_path / "project"
    case_dir = root / "cases" / "wheel_screen_cpt"
    case_dir.mkdir(parents=True)
    for filename in DESIGNS.values():
        (case_dir / filename).write_text(
            json.dumps({"wheel": {"obj": f"{filename}.obj"}, "terrain": {}, "test": {}})
        )
    profile = root / "cases" / "profile.json"
    profile.write_text(json.dumps({"terrain": {}, "test": {}, "solver": {}, "output": {}}))
    references = root / "physical_references"
    references.mkdir()
    telemetry = references / "telemetry.json"
    telemetry.write_text(
        json.dumps(
            {
                "designs": {
                    design: {
                        "laps": [
                            {
                                "active_load_kg_reported": {"median": 20.0},
                                "derived_carriage_speed_m_s": {"median": 0.1},
                                "derived_slip": {"median": 0.1},
                            }
                            for _ in range(50)
                        ]
                    }
                    for design in DESIGNS
                }
            }
        )
    )
    penetrometer = references / "penetrometer.json"
    penetrometer.write_text(
        json.dumps(
            {
                "campaigns": [
                    {"campaign_id": f"{design}-{replicate}", "wheel_design": design}
                    for design in DESIGNS
                    for replicate in (1, 2)
                ]
            }
        )
    )
    output = root / "cases" / "rtgs"
    master = generate(
        telemetry,
        penetrometer,
        case_dir,
        profile,
        output,
        0.9,
        bed_case_id="fixed-bed",
        bed_state_sha256="bed123",
    )
    master_data = json.loads(master.read_text())
    assert len(master_data["design_queues"]) == 2
    first_queue = json.loads((root / master_data["design_queues"][0]).read_text())
    assert len(first_queue["manifests"]) == 50
    first = json.loads((root / first_queue["manifests"][0]).read_text())
    second = json.loads((root / first_queue["manifests"][1]).read_text())
    assert first["terrain"]["initial_state_case_id"] == "fixed-bed"
    assert second["terrain"]["initial_state_case_id"] == first["case_id"]
    assert first["rtgs_penetrometer_target"]["split"] == "held_out_validation"
    assert first["rtgs_penetrometer_target"]["shared_bed_state_sha256"] == "bed123"
