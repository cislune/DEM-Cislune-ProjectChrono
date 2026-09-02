import json

from generate_rtgs_ordering_validation import DESIGNS, generate


def test_generate_uses_frozen_bed_and_design_specific_conditions(tmp_path):
    root = tmp_path / "project"
    case_dir = root / "cases" / "wheel_screen_cpt"
    case_dir.mkdir(parents=True)
    for filename in DESIGNS.values():
        (case_dir / filename).write_text(
            json.dumps(
                {
                    "wheel": {"obj": f"{filename}.obj", "effective_mass_kg": 10},
                    "terrain": {},
                    "test": {},
                }
            )
        )
    profile = root / "cases" / "profile.json"
    profile.write_text(
        json.dumps(
            {"terrain": {}, "test": {}, "solver": {}, "output": {}}
        )
    )
    reference = root / "reference.json"
    reference.write_text(
        json.dumps(
            {
                "designs": {
                    design: {
                        "lap_files": 2,
                        "median_of_lap_median_abs_current_reading": current,
                        "median_of_lap_median_slip": 0.1,
                        "laps": [
                            {
                                "active_load_kg_reported": {"median": load},
                                "derived_carriage_speed_m_s": {"median": 0.09},
                            }
                            for load in (18.0, 20.0)
                        ],
                    }
                    for design, current in zip(DESIGNS, (0.27, 0.22, 0.23))
                }
            }
        )
    )
    queue = generate(
        reference,
        case_dir,
        profile,
        root / "cases" / "output",
        0.3,
        bed_case_id="fixed-bed",
        bed_state_sha256="state123",
    )
    data = json.loads(queue.read_text())
    case = json.loads((root / data["manifests"][0]).read_text())
    assert case["terrain"]["initial_state_case_id"] == "fixed-bed"
    assert case["terrain"]["wheel_friction"] == 0.3
    assert case["test"]["normal_load_n"] == 19.0 * 9.80665
    assert case["ordinal_validation_target"]["shared_bed_state_sha256"] == "state123"
