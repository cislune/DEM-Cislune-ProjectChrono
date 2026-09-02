import json

from generate_wheel_process_checkout import build_case, generate


def candidate(name: str, radius: float, feature: float = 0.0) -> dict:
    return {
        "name": name,
        "design": {"feature_height_m": feature},
        "dem": {
            "obj": f"wheel_candidates/{name}.obj",
            "rolling_radius_m": radius,
            "envelope_radius_m": radius,
            "width_m": 0.1016,
        },
    }


def test_build_case_is_bounded_and_nonphysical():
    case = build_case(candidate("smooth_control", 0.19), 0.012, 0.00001)

    assert case["case_id"] == "process-smooth_control-r12mm-dt10us"
    assert case["model_status"] == "software_process_checkout"
    assert case["analysis"]["minimum_lane_particles"] == 5
    assert case["analysis"]["density_gate_affects_status"] is False
    assert case["terrain"]["settle_time_s"] == 0.4
    assert case["terrain"]["compression_max_time_s"] == 1.5
    assert case["test"]["duration_s"] == 0.08
    assert case["output"]["terrain_progress_every_n_frames"] == 10
    assert case["output"]["write_wheel_terrain_motion"] is True
    assert "physical_reference" not in case


def test_build_case_supports_phase_coverage_profile():
    case = build_case(
        candidate("low_grouser_16", 0.202, 0.012),
        0.008,
        0.000005,
        duration_s=1.2,
        wheel_write_every_n_frames=50,
        case_suffix="phase1p2s",
        bin_travel_length_m=0.64,
    )

    assert case["case_id"].endswith("-phase1p2s")
    assert case["test"]["duration_s"] == 1.2
    assert case["output"]["wheel_write_every_n_frames"] == 50
    assert case["output"]["wheel_progress_every_n_frames"] == 50
    assert case["terrain"]["bin_travel_length_m"] == 0.64


def test_generate_writes_bounded_candidate_ladder(tmp_path):
    catalog_dir = tmp_path / "wheel_candidates"
    catalog_dir.mkdir()
    catalog = catalog_dir / "candidate_catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "candidates": [
                    candidate("smooth_control", 0.19),
                    candidate("broad_wave_12", 0.198, 0.008),
                    candidate("chevron_wave_14", 0.199, 0.009),
                    candidate("low_grouser_16", 0.202, 0.012),
                    candidate("low_grouser_16_10mm", 0.200, 0.010),
                    candidate("staggered_wave_12", 0.204, 0.014),
                ]
            }
        )
    )

    paths = generate(catalog, tmp_path / "cases" / "checkout", 0.012, 0.00002)

    assert len(paths) == 6
    queue = json.loads((tmp_path / "cases" / "checkout" / "process_checkout_queue.json").read_text())
    assert queue["sequence"] == [
        "smooth_control",
        "broad_wave_12",
        "chevron_wave_14",
        "low_grouser_16",
        "low_grouser_16_10mm",
        "staggered_wave_12",
    ]
    assert all("dt20us" in path.name for path in paths)
