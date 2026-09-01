import json

from rank_density_margin_sweep import collect, write_outputs


def write_case(root, name, margin, achieved):
    case_dir = root / name
    terrain = case_dir / "terrain"
    terrain.mkdir(parents=True)
    (case_dir / "frozen_case.json").write_text(
        json.dumps(
            {
                "case_id": name,
                "terrain": {
                    "base_particle_radius_m": 0.008,
                    "time_step_s": 0.000005,
                    "compression_release_margin": margin,
                },
            }
        )
    )
    (terrain / "terrain_preparation.json").write_text(
        json.dumps(
            {
                "target_bulk_density_kg_m3": 1700.0,
                "post_release_bulk_density_kg_m3": achieved,
                "generated_particle_count": 100,
            }
        )
    )


def test_collect_ranks_closest_density_first(tmp_path):
    write_case(tmp_path, "far", 0.18, 1400.0)
    write_case(tmp_path, "close", 0.55, 1690.0)
    rows = collect(tmp_path)
    assert [row["case_id"] for row in rows] == ["close", "far"]
    assert rows[0]["achieved_to_target_ratio"] == 1690.0 / 1700.0


def test_write_outputs_creates_json_and_csv(tmp_path):
    rows = [
        {
            "case_id": "case",
            "base_particle_radius_m": 0.008,
            "time_step_s": 0.000005,
            "compression_release_margin": 0.5,
            "target_bulk_density_kg_m3": 1700.0,
            "post_release_bulk_density_kg_m3": 1690.0,
            "achieved_to_target_ratio": 1690.0 / 1700.0,
            "absolute_density_error_kg_m3": 10.0,
            "particle_count": 100,
        }
    ]
    write_outputs(rows, tmp_path / "ranking.json", tmp_path / "ranking.csv")
    assert json.loads((tmp_path / "ranking.json").read_text())[0]["case_id"] == "case"
    assert "compression_release_margin" in (tmp_path / "ranking.csv").read_text()
