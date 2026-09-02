import json

from generate_solver_stall_triage_cases import PROFILES, generate


def test_generate_solver_stall_triage_cases_preserves_physics(tmp_path, monkeypatch):
    project = tmp_path / "project"
    source_dir = project / "cases" / "source"
    source_dir.mkdir(parents=True)
    source = source_dir / "lap03.json"
    source.write_text(
        json.dumps(
            {
                "case_id": "lap03",
                "terrain": {"initial_state_case_id": "lap02"},
                "wheel": {"obj": "wheel.obj"},
                "test": {"duration_s": 1.2},
                "solver": {"max_velocity_m_s": 20.0},
            }
        )
    )
    monkeypatch.setattr(
        "generate_solver_stall_triage_cases.__file__", str(project / "script.py")
    )

    queue_path = generate(source, project / "cases" / "triage")

    queue = json.loads(queue_path.read_text())
    assert queue["seed_case_id"] == "lap02"
    assert len(queue["manifests"]) == len(PROFILES)
    generated = [json.loads((project / path).read_text()) for path in queue["manifests"]]
    assert {case["solver_stall_triage"]["execution_profile"] for case in generated} == set(PROFILES)
    assert all(case["test"] == {"duration_s": 1.2} for case in generated)
    assert all(case["solver"]["max_velocity_m_s"] == 20.0 for case in generated)
