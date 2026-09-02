import sys
import time

from run_with_inactivity_timeout import run


def test_inactivity_timeout_terminates_silent_process():
    started = time.monotonic()
    status = run(
        [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(2)"],
        0.1,
    )
    assert status == 124
    assert time.monotonic() - started < 1.0


def test_inactivity_timeout_allows_active_process():
    status = run(
        [
            sys.executable,
            "-c",
            "import time; [(print(i, flush=True), time.sleep(0.05)) for i in range(4)]",
        ],
        0.2,
    )
    assert status == 0
