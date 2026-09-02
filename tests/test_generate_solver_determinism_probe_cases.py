import json

from generate_solver_determinism_probe_cases import PROFILES, generate


def test_generate_short_determinism_profiles(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "case_id": "source-r01",
                "wheel": {},
                "terrain": {},
                "test": {"duration_s": 1.2},
                "solver": {"use_cub_force_collection": True},
                "output": {"wheel_write_every_n_frames": 50},
                "repeatability_target": {"replicate": 1},
            }
        )
    )

    queue = generate(source, tmp_path / "cases", duration_s=0.25, write_every=10)

    assert len(queue["manifests"]) == len(PROFILES)
    for path in queue["manifests"]:
        case = json.loads(open(path).read())
        assert case["test"]["duration_s"] == 0.25
        assert case["output"]["wheel_write_every_n_frames"] == 10
        assert "repeatability_target" not in case
        assert case["determinism_probe"]["repeats_requested"] == 3
