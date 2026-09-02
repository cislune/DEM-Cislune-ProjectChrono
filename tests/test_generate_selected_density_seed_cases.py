import json
from pathlib import Path

import pytest

from generate_selected_density_seed_cases import generate


def inputs(tmp_path):
    source = tmp_path / "selected.json"
    source.write_text(
        json.dumps(
            {
                "case_id": "density-margin0p35",
                "terrain": {
                    "compression_release_margin": 0.35,
                    "random_seed": 77,
                },
            }
        )
    )
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({"manifests": [str(source)]}))
    ranking = tmp_path / "ranking.json"
    ranking.write_text(json.dumps([{"case_id": "density-margin0p35"}]))
    return ranking, queue


def test_generate_repeats_selected_margin_with_new_seeds(tmp_path):
    ranking, queue = inputs(tmp_path)
    output = generate(ranking, queue, tmp_path / "out", [78, 79])
    data = json.loads(output.read_text())
    cases = [json.loads(Path(path).read_text()) for path in data["manifests"]]

    assert data["selected_margin"] == 0.35
    assert [case["terrain"]["random_seed"] for case in cases] == [78, 79]
    assert all(case["terrain"]["compression_release_margin"] == 0.35 for case in cases)


def test_generate_rejects_original_seed(tmp_path):
    ranking, queue = inputs(tmp_path)
    with pytest.raises(ValueError, match="must not repeat"):
        generate(ranking, queue, tmp_path / "out", [77])
