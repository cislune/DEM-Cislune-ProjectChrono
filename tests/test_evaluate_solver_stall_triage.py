import json

from evaluate_solver_stall_triage import evaluate


def test_evaluate_solver_stall_triage_selects_fastest_completed_profile(tmp_path):
    project = tmp_path / "project"
    cases = project / "cases" / "triage"
    cases.mkdir(parents=True)
    manifests = []
    for profile in ("cub", "fixed-cd20"):
        case_id = f"stall-{profile}"
        path = cases / f"{case_id}.json"
        path.write_text(
            json.dumps(
                {
                    "case_id": case_id,
                    "solver_stall_triage": {
                        "execution_profile": profile,
                        "solver_overrides": {},
                    },
                }
            )
        )
        manifests.append(str(path.relative_to(project)))
    queue = cases / "queue.json"
    queue.write_text(json.dumps({"manifests": manifests}))
    output = tmp_path / "output"
    logs = output / "_logs"
    logs.mkdir(parents=True)
    for profile, duration in (("cub", 400), ("fixed-cd20", 300)):
        case_id = f"stall-{profile}"
        (logs / f"20260901_{case_id}_all.log").write_text(
            f"Wheel frame: 50, simulated: 0.05 s\n"
            f"container_exit_status=0\nwall_duration_s={duration}\n"
        )
        result_dir = output / case_id
        result_dir.mkdir()
        (result_dir / "wheel_performance.json").write_text("{}")

    result = evaluate(output, queue)

    assert result["status"] == "ONE_OR_MORE_COMPLETED"
    assert result["fastest_completed_profile"] == "fixed-cd20"
    assert result["profiles"][0]["last_wheel_frame"] == 50
    assert result["profiles"][0]["last_simulated_time_s"] == 0.05
