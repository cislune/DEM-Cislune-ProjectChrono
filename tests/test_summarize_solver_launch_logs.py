from summarize_solver_launch_logs import classify_log, summarize


def write_log(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_classifies_timeout_only_after_preflight_pass(tmp_path):
    timeout = tmp_path / "timeout.log"
    setup = tmp_path / "setup.log"
    write_log(
        timeout,
        "Preflight: PASS\nWheel frame: 75, simulated: 0.075 s\ncontainer_exit_status=124\n",
    )
    write_log(setup, "Preflight: FAIL\ncontainer_exit_status=2\n")

    assert classify_log(timeout)["classification"] == "SOLVER_TIMEOUT"
    assert classify_log(timeout)["maximum_wheel_frame"] == 75
    assert classify_log(setup)["classification"] == "SETUP_REJECTED"


def test_campaign_summary_separates_solver_and_setup_failures(tmp_path):
    log_root = tmp_path / "cub" / "r01" / "_logs"
    write_log(log_root / "success_all.log", "Preflight: PASS\ncontainer_exit_status=0\n")
    write_log(
        log_root / "stall_all.log",
        "Preflight: PASS\nWheel frame: 0, simulated: 0 s\ncontainer_exit_status=137\n",
    )
    write_log(log_root / "missing_all.log", "Preflight: FAIL\ncontainer_exit_status=2\n")

    result = summarize(tmp_path)
    profile = result["profiles"][0]

    assert profile["successful_launches"] == 1
    assert profile["failed_solver_launches"] == 1
    assert profile["setup_rejections"] == 1
